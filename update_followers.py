"""
A compléter avec l'acteur Instagram Profile Scraper.
Ce script devra récupérer les followers et écrire followers.json.
"""

import json

# Exemple de structure
followers = {
    # "username": 123456
}

with open("followers.json","w",encoding="utf-8") as f:
    json.dump(followers,f,indent=2,ensure_ascii=False)

print("followers.json mis à jour")
