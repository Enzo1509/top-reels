"""
Top Reels du Jour — Analyse automatique de Reels Instagram (comptes publics)
=============================================================================
1. Récupère les Reels récents des comptes listés via Apify
2. Calcule un score de performance pour chaque Reel
3. Envoie le Top 3 du jour dans une base Notion

Prérequis :
  pip install requests
  Variables d'environnement : APIFY_TOKEN, NOTION_TOKEN
"""

import os
import sys
import time
import requests
from datetime import datetime, timedelta, timezone

# ─────────────────────────── CONFIGURATION ───────────────────────────

# Les comptes Instagram publics à surveiller (sans le @)
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

# Fenêtre d'analyse : Reels publiés dans les X dernières heures
FENETRE_HEURES = 24

# Nombre de Reels max récupérés par compte (impacte le coût Apify)
REELS_PAR_COMPTE = 10

# Nombre de gagnants par jour
TOP_N = 3

# Clés API (à définir en variables d'environnement, jamais en dur dans le code)
APIFY_TOKEN = os.environ["APIFY_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]

# Base Notion créée pour toi (ne pas modifier sauf si tu recrées la base)
NOTION_DATABASE_ID = "a57b8dd142444d65a2e8849f09f31456"

# Acteur Apify utilisé pour scraper les Reels
APIFY_ACTOR = "apify~instagram-reel-scraper"

RANGS = ["🥇 1er", "🥈 2ème", "🥉 3ème", "4ème", "5ème"]

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

def analyser(items):
    """Filtre les Reels récents et calcule leur score."""
    limite = datetime.now(timezone.utc) - timedelta(hours=FENETRE_HEURES)
    reels = []

    for item in items:
        # Date de publication
        ts = item.get("timestamp")
        if not ts:
            continue
        try:
            date_pub = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            continue
        if date_pub < limite:
            continue  # trop ancien

        vues = item.get("videoPlayCount") or item.get("videoViewCount") or 0
        likes = item.get("likesCount") or 0
        comms = item.get("commentsCount") or 0

        engagement = round((likes + comms) / vues * 100, 2) if vues else 0.0

        # Score : les vues comptent, mais l'engagement est fortement valorisé
        # (un Reel avec bcp d'interactions par vue = contenu qui accroche)
        score = round(vues * (1 + (engagement / 100) * 5))

        reels.append({
            "compte": item.get("ownerUsername", "?"),
            "lien": item.get("url", ""),
            "vues": vues,
            "likes": likes,
            "commentaires": comms,
            "engagement": engagement,
            "score": score,
            "legende": (item.get("caption") or "")[:150],
            "date": date_pub,
        })

    reels.sort(key=lambda r: r["score"], reverse=True)
    print(f"→ {len(reels)} Reels publiés dans les {FENETRE_HEURES} dernières heures")
    return reels[:TOP_N]


# ─────────────────────────── 3. ENVOI VERS NOTION ───────────────────────────

def envoyer_notion(top_reels):
    """Crée une page Notion par Reel gagnant."""
    aujourd_hui = datetime.now().strftime("%Y-%m-%d")
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    for i, reel in enumerate(top_reels):
        titre = f"@{reel['compte']} — {reel['legende'][:60] or 'Reel'}"
        page = {
            "parent": {"database_id": NOTION_DATABASE_ID},
            "properties": {
                "Reel": {"title": [{"text": {"content": titre}}]},
                "Date": {"date": {"start": aujourd_hui}},
                "Rang": {"select": {"name": RANGS[i]}},
                "Compte": {"rich_text": [{"text": {"content": "@" + reel["compte"]}}]},
                "Lien": {"url": reel["lien"] or None},
                "Vues": {"number": reel["vues"]},
                "Likes": {"number": reel["likes"]},
                "Commentaires": {"number": reel["commentaires"]},
                "Engagement %": {"number": reel["engagement"]},
                "Score": {"number": reel["score"]},
                "Légende": {"rich_text": [{"text": {"content": reel["legende"]}}]},
            },
        }
        r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=page, timeout=30)
        if r.status_code == 200:
            print(f"   ✅ {RANGS[i]} : @{reel['compte']} ({reel['vues']:,} vues, score {reel['score']:,})")
        else:
            print(f"   ❌ Erreur Notion pour @{reel['compte']} : {r.status_code} {r.text[:200]}")
        time.sleep(0.4)  # respecter le rate limit Notion


# ─────────────────────────── MAIN ───────────────────────────

if __name__ == "__main__":
    items = recuperer_reels()
    top = analyser(items)

    if not top:
        print("Aucun Reel publié dans la fenêtre d'analyse. Rien à envoyer.")
        sys.exit(0)

    print(f"\n🏆 Top {len(top)} du jour :")
    envoyer_notion(top)
    print("\nTerminé ✨")
