"""
Top Reels du Jour — Analyse automatique de Reels Instagram (comptes publics)
=============================================================================
1. Récupère les Reels récents des comptes listés via Apify
2. Charge followers.json (mis à jour chaque lundi par update_followers.py)
3. Calcule un score de VIRALITÉ normalisé par la taille du compte
4. Envoie le Top 3 du jour dans une base Notion

Prérequis :
  pip install requests
  Variables d'environnement : APIFY_TOKEN, NOTION_TOKEN
"""

import json
import math
import os
import sys
import time

import requests
from datetime import datetime, timedelta, timezone

# ─────────────────────────── CONFIGURATION ───────────────────────────

# Les comptes Instagram publics à surveiller (sans le @)
# ⚠️ Vérifie : "faye.belincii" et "fayebelincii" ressemblent à un doublon
COMPTES = [
    "gingerlilyxo",
    "brookesoftalk",
    "lucy_baby.xo",
    "arahoneycomb",
    "faye.belincii",
    "linnanoir",
    "mintychocolatecookie",
    "siennaxcobre_",
    "fayebelincii",
    "kiarapeachlegit",
    "sophie.lin.x",
    "tana.scovaaa",
    "cyber.kittennxo",
    "sera.changg",
    "adr1anaper3z",
    "remyperetz.xo",
    "aerithsylvara",
    "reese.vuitton",
    "brunettechloem",
    "fionaxparker",
    "ambeerrspamm_",
]

# Fenêtre d'analyse : Reels publiés entre [J-2 20:00 UTC → J-1 20:00 UTC].
# La fenêtre est ancrée sur HEURE_ANCRAGE (l'heure du cron), PAS sur l'heure
# réelle du run : même si GitHub Actions lance le cron avec 40 min de retard
# (fréquent), les bornes ne bougent pas → chaque Reel est analysé exactement
# une fois, et a toujours entre 24h et 48h de vie au moment du scoring.
# ⚠️ Doit correspondre à l'heure du cron quotidien dans le workflow GitHub.
HEURE_ANCRAGE = 20  # 20:00 UTC

# Référence pour le facteur de vélocité (24h = une journée de vie)
HEURES_REFERENCE = 24

# Nombre de Reels max récupérés par compte (impacte le coût Apify).
# ⚠️ L'acteur renvoie les Reels les plus RÉCENTS en premier : les Reels
# de 0-24h (hors fenêtre) consomment des slots avant d'atteindre ceux de
# 24-48h qu'on veut analyser. Sur un compte qui poste 5 Reels/jour, il
# faut ~10 slots rien que pour traverser les dernières 48h → 15 par sécurité.
REELS_PAR_COMPTE = 15

# Nombre de gagnants par jour
TOP_N = 3

# Seuil minimum de vues pour être classé.
# Indispensable avec un score normalisé par followers : sans ce seuil,
# un Reel à 300 vues sur un compte de 1 500 followers écraserait tout
# le classement avec zéro signal statistique.
MIN_VUES = 1000

# Valeur de repli si un compte est absent de followers.json
# (utilisée uniquement tant que le workflow hebdo n'a pas tourné)
FOLLOWERS_PAR_DEFAUT = 50000

# Fichier généré chaque lundi par update_followers.py
FICHIER_FOLLOWERS = "followers.json"

# Clés API (variables d'environnement, jamais en dur dans le code)
APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
NOTION_TOKEN = os.environ.get("NOTION_TOKEN")

# Base Notion créée pour toi (ne pas modifier sauf si tu recrées la base)
NOTION_DATABASE_ID = "a57b8dd142444d65a2e8849f09f31456"

# Acteur Apify utilisé pour scraper les Reels
APIFY_ACTOR = "apify~instagram-reel-scraper"

RANGS = ["🥇 1er", "🥈 2ème", "🥉 3ème", "4ème", "5ème"]

# ─────────────────────────── 0. FOLLOWERS ───────────────────────────

def charger_followers():
    """Charge followers.json → {username_minuscule: followersCount}."""
    if not os.path.exists(FICHIER_FOLLOWERS):
        print(f"⚠️  {FICHIER_FOLLOWERS} introuvable — valeur par défaut "
              f"({FOLLOWERS_PAR_DEFAUT:,}) utilisée pour tous les comptes.")
        print("   → Lance le workflow « Mise à jour followers » dans GitHub Actions.")
        return {}

    try:
        with open(FICHIER_FOLLOWERS, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
    except (json.JSONDecodeError, OSError) as e:
        print(f"⚠️  {FICHIER_FOLLOWERS} illisible ({e}) — valeurs par défaut utilisées.")
        return {}

    followers = {k.strip().lower(): int(v) for k, v in data.items()
                 if isinstance(v, (int, float)) and v > 0}
    print(f"→ {len(followers)} comptes chargés depuis {FICHIER_FOLLOWERS}")
    return followers


def followers_de(username, followers_map):
    """Retourne le nombre de followers d'un compte, avec repli intelligent."""
    count = followers_map.get(username.strip().lower())
    if count:
        return count, True

    # Repli : médiane des comptes connus, sinon valeur par défaut
    if followers_map:
        valeurs = sorted(followers_map.values())
        mediane = valeurs[len(valeurs) // 2]
        return mediane, False
    return FOLLOWERS_PAR_DEFAUT, False


# ─────────────────────────── 1. SCRAPING APIFY ───────────────────────────

def recuperer_reels():
    """Lance l'acteur Apify et retourne la liste brute des Reels."""
    print(f"→ Lancement du scraping Apify pour {len(COMPTES)} comptes...")

    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/run-sync-get-dataset-items"
    payload = {
        "username": COMPTES,
        "resultsLimit": REELS_PAR_COMPTE,
    }
    resp = requests.post(
        url,
        params={"token": APIFY_TOKEN},
        json=payload,
        timeout=600,  # le scraping peut prendre plusieurs minutes
    )
    resp.raise_for_status()
    items = resp.json()
    print(f"→ {len(items)} Reels récupérés au total")
    return items


# ─────────────────────────── 2. SCORING ───────────────────────────

def calculer_score(vues, likes, comms, followers, heures_ecoulees):
    """
    Score de viralité normalisé par la taille du compte.

    ratio       = vues / followers        → performance relative au compte
    engagement  = (likes + 3×comms)/vues  → les commentaires pèsent 3× plus
                                            (signal d'accroche bien plus fort
                                            qu'un like passif)
    log10(vues+10)                        → récompense le volume absolu, en
                                            douceur, pour départager deux
                                            ratios proches
    facteur récence                       → un Reel posté il y a 4h qui a déjà
                                            explosé bat un Reel posté il y a
                                            22h aux mêmes stats (vélocité)

    Le score final n'a pas d'unité — il sert uniquement à classer.
    """
    if not vues or not followers:
        return 0.0, 0.0, 0.0

    ratio = vues / followers
    engagement_pondere = (likes + 3 * comms) / vues

    # Facteur de vélocité : sqrt(24 / heures), plafonné à 2.0.
    # Avec la fenêtre ancrée 24-48h, l'âge des Reels au moment du run va de
    # ~24h à ~48h. Le facteur compense le fait qu'un Reel posté en fin de
    # fenêtre a eu moins de temps pour accumuler ses vues : à vues égales,
    # le plus récent a une vélocité supérieure et mérite un meilleur score.
    heures = max(heures_ecoulees, 3.0)  # plancher de sécurité
    facteur_recence = min(math.sqrt(HEURES_REFERENCE / heures), 2.0)

    score = ratio * (1 + engagement_pondere * 5) * math.log10(vues + 10) * facteur_recence
    return round(score, 3), round(ratio, 3), engagement_pondere


def fenetre_analyse():
    """Retourne (début, fin) = [J-2 HEURE_ANCRAGE → J-1 HEURE_ANCRAGE] en UTC.

    Concrètement : run du 18/07 à 20:05 (ou 20:47, ou même 23:00)
      → fin   = 17/07 20:00
      → début = 16/07 20:00
    Tout Reel de cette fenêtre a donc AU MINIMUM 24h de vie (posté au plus
    tard le 17 à 20:00, run au plus tôt le 18 à 20:00) et au maximum ~48h.
    Les bornes étant ancrées sur HEURE_ANCRAGE et non sur l'heure réelle du
    run, deux runs quotidiens successifs couvrent des fenêtres parfaitement
    disjointes et contiguës, quel que soit le retard du cron GitHub.
    """
    maintenant = datetime.now(timezone.utc)
    ancre = maintenant.replace(hour=HEURE_ANCRAGE, minute=0, second=0, microsecond=0)
    if ancre > maintenant:
        # Run lancé avant HEURE_ANCRAGE (ex. run manuel le matin)
        ancre -= timedelta(days=1)
    fin = ancre - timedelta(days=1)      # J-1 à 20:00
    debut = fin - timedelta(days=1)      # J-2 à 20:00
    return debut, fin


def analyser(items, followers_map):
    """Garde les Reels de la fenêtre 24-48h et calcule leur score de viralité."""
    maintenant = datetime.now(timezone.utc)
    debut, fin = fenetre_analyse()
    reels = []
    ignores_vues = 0

    for item in items:
        # Date de publication
        ts = item.get("timestamp")
        if not ts:
            continue
        try:
            date_pub = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if not (debut <= date_pub < fin):
            continue  # hors fenêtre 24-48h

        vues = item.get("videoPlayCount") or item.get("videoViewCount") or 0
        likes = item.get("likesCount") or 0
        comms = item.get("commentsCount") or 0

        if vues < MIN_VUES:
            ignores_vues += 1
            continue  # trop peu de vues pour un signal fiable

        compte = item.get("ownerUsername", "?")
        followers, followers_connus = followers_de(compte, followers_map)
        heures_ecoulees = (maintenant - date_pub).total_seconds() / 3600

        engagement_simple = round((likes + comms) / vues * 100, 2)
        score, ratio, _ = calculer_score(vues, likes, comms, followers, heures_ecoulees)

        reels.append({
            "compte": compte,
            "lien": item.get("url", ""),
            "vues": vues,
            "likes": likes,
            "commentaires": comms,
            "engagement": engagement_simple,
            "followers": followers,
            "followers_estimes": not followers_connus,
            "ratio": ratio,
            "score": score,
            "legende": (item.get("caption") or "")[:150],
            "date": date_pub,
        })

    reels.sort(key=lambda r: r["score"], reverse=True)
    print(f"→ {len(reels)} Reels retenus ({ignores_vues} ignorés sous {MIN_VUES:,} vues) "
          f"dans la fenêtre {debut.strftime('%d/%m %H:%M')} → {fin.strftime('%d/%m %H:%M')} UTC")
    return reels[:TOP_N]


# ─────────────────────────── 3. ENVOI VERS NOTION ───────────────────────────

# Propriétés ajoutées par la V2 — si elles n'existent pas encore dans ta base
# Notion, le script réessaie automatiquement sans elles (voir README).
PROPRIETES_V2 = ("Followers", "Vues/Follower")


def envoyer_notion(top_reels):
    """Crée une page Notion par Reel gagnant.

    La colonne Date reçoit la date de fin de la fenêtre analysée (fenêtre
    J-2 20:00 → J-1 20:00, étiquetée J-1) : chaque run quotidien produit
    ainsi une date unique et cohérente, même s'il tourne en retard.
    """
    _, fin_fenetre = fenetre_analyse()
    jour_analyse = fin_fenetre.strftime("%Y-%m-%d")
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    for i, reel in enumerate(top_reels):
        suffixe = " (est.)" if reel["followers_estimes"] else ""
        titre = f"@{reel['compte']} — {reel['legende'][:60] or 'Reel'}"
        proprietes = {
            "Reel": {"title": [{"text": {"content": titre}}]},
            "Date": {"date": {"start": jour_analyse}},
            "Rang": {"select": {"name": RANGS[i]}},
            "Compte": {"rich_text": [{"text": {"content": "@" + reel["compte"] + suffixe}}]},
            "Lien": {"url": reel["lien"] or None},
            "Vues": {"number": reel["vues"]},
            "Likes": {"number": reel["likes"]},
            "Commentaires": {"number": reel["commentaires"]},
            "Engagement %": {"number": reel["engagement"]},
            "Score": {"number": reel["score"]},
            "Légende": {"rich_text": [{"text": {"content": reel["legende"]}}]},
            # Nouvelles propriétés V2
            "Followers": {"number": reel["followers"]},
            "Vues/Follower": {"number": reel["ratio"]},
        }
        page = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": proprietes}

        r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=page, timeout=30)

        # Si la base Notion n'a pas encore les nouvelles colonnes → retry sans elles
        if r.status_code == 400 and any(p in r.text for p in PROPRIETES_V2):
            for p in PROPRIETES_V2:
                proprietes.pop(p, None)
            print(f"   ⚠️  Colonnes {PROPRIETES_V2} absentes de la base Notion — envoi sans elles "
                  f"(ajoute-les pour voir le ratio, cf. README)")
            r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=page, timeout=30)

        if r.status_code == 200:
            print(f"   ✅ {RANGS[i]} : @{reel['compte']} — {reel['vues']:,} vues / "
                  f"{reel['followers']:,} followers{suffixe} → ratio {reel['ratio']}, "
                  f"score {reel['score']}")
        else:
            print(f"   ❌ Erreur Notion pour @{reel['compte']} : {r.status_code} {r.text[:200]}")
        time.sleep(0.4)  # respecter le rate limit Notion


# ─────────────────────────── MAIN ───────────────────────────

if __name__ == "__main__":
    if not APIFY_TOKEN or not NOTION_TOKEN:
        print("❌ Variables d'environnement APIFY_TOKEN et NOTION_TOKEN requises.")
        sys.exit(1)

    followers_map = charger_followers()
    items = recuperer_reels()
    top = analyser(items, followers_map)

    if not top:
        print("Aucun Reel publié dans la fenêtre d'analyse. Rien à envoyer.")
        sys.exit(0)

    print(f"\n🏆 Top {len(top)} du jour :")
    envoyer_notion(top)
    print("\nTerminé ✨")
