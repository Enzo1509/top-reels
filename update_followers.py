"""
Mise à jour hebdomadaire des followers — Instagram Profile Scraper (Apify)
===========================================================================
1. Récupère automatiquement la liste COMPTES depuis top_reels.py
2. Lance l'acteur apify/instagram-profile-scraper (dSCLg0C3YEZ83HzYX)
3. Attend la fin du run et récupère le dataset
4. Écrit followers.json  →  { "username": followersCount, ... }

Prérequis :
  pip install requests
  Variable d'environnement : APIFY_TOKEN
"""

import json
import os
import sys

import requests

# On importe la liste des comptes directement depuis top_reels.py
# (une seule source de vérité : tu modifies COMPTES à un seul endroit)
from top_reels import COMPTES

APIFY_TOKEN = os.environ.get("APIFY_TOKEN")
APIFY_ACTOR_ID = "dSCLg0C3YEZ83HzYX"  # apify/instagram-profile-scraper
FICHIER_SORTIE = "followers.json"


def recuperer_followers():
    """Lance l'acteur profile-scraper et retourne {username_minuscule: followersCount}."""
    if not APIFY_TOKEN:
        print("❌ Variable d'environnement APIFY_TOKEN manquante.")
        sys.exit(1)

    # Déduplication (insensible à la casse) au cas où COMPTES contient des doublons
    usernames = sorted({c.strip().lower() for c in COMPTES if c.strip()})
    print(f"→ Scraping des profils de {len(usernames)} comptes...")

    url = f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}/run-sync-get-dataset-items"
    payload = {"usernames": usernames}

    resp = requests.post(
        url,
        params={"token": APIFY_TOKEN},
        json=payload,
        timeout=600,  # le scraping de profils peut prendre plusieurs minutes
    )
    resp.raise_for_status()
    items = resp.json()
    print(f"→ {len(items)} profils récupérés")

    followers = {}
    for item in items:
        username = (item.get("username") or "").strip().lower()
        count = item.get("followersCount")
        if not username:
            continue
        if count is None:
            print(f"   ⚠️  Pas de followersCount pour @{username} (compte privé ou introuvable ?)")
            continue
        followers[username] = int(count)
        print(f"   ✅ @{username} : {count:,} followers")

    # Comptes demandés mais absents du résultat
    manquants = [u for u in usernames if u not in followers]
    for u in manquants:
        print(f"   ⚠️  @{u} absent du résultat Apify — il gardera son ancienne valeur si elle existe")

    return followers


def fusionner_avec_existant(nouveaux):
    """Conserve les anciennes valeurs pour les comptes non récupérés cette semaine."""
    anciens = {}
    if os.path.exists(FICHIER_SORTIE):
        try:
            with open(FICHIER_SORTIE, "r", encoding="utf-8") as f:
                anciens = json.load(f) or {}
        except (json.JSONDecodeError, OSError):
            anciens = {}

    # Normalisation des clés existantes en minuscules
    anciens = {k.strip().lower(): v for k, v in anciens.items() if isinstance(v, (int, float))}

    fusion = {**anciens, **nouveaux}  # les nouvelles valeurs écrasent les anciennes

    # On ne garde que les comptes encore présents dans COMPTES
    actifs = {c.strip().lower() for c in COMPTES}
    fusion = {k: v for k, v in fusion.items() if k in actifs}
    return fusion


if __name__ == "__main__":
    nouveaux = recuperer_followers()

    if not nouveaux:
        print("❌ Aucun follower récupéré. followers.json n'est PAS modifié (on garde l'ancien).")
        sys.exit(1)

    fusion = fusionner_avec_existant(nouveaux)

    with open(FICHIER_SORTIE, "w", encoding="utf-8") as f:
        json.dump(fusion, f, indent=2, ensure_ascii=False, sort_keys=True)

    print(f"\n✅ {FICHIER_SORTIE} mis à jour : {len(fusion)} comptes")
