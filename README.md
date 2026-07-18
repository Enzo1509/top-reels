# 🎬 Top Reels du Jour — Guide d'installation (V2)

Ce système analyse chaque jour les Reels de comptes Instagram publics et envoie le Top 3 dans ta base Notion **« 🎬 Top Reels du Jour »**.

**Nouveauté V2** : le score est désormais **normalisé par le nombre de followers** de chaque compte. Le classement fait ressortir les Reels qui **surperforment par rapport à la taille du créateur**, pas simplement ceux qui ont le plus de vues.

## Comment ça marche

```
Lundi 06:00 UTC   : Apify (profile-scraper) → update_followers.py → followers.json (commité dans le repo)
Chaque jour 20:00 : Apify (reel-scraper)    → top_reels.py (scoring) → Notion (Top 3)
```

**Fenêtre d'analyse (V2.1)** : chaque run analyse les Reels publiés entre **avant-hier 20:00 UTC et hier 20:00 UTC**. Au moment du run (20:00), chaque Reel a donc entre **24h et 48h de vie** — assez pour que ses stats soient stabilisées et comparables. Les bornes sont ancrées sur 20:00 UTC pile (variable `HEURE_ANCRAGE`), pas sur l'heure réelle du run : même si GitHub Actions lance le cron avec 40 min de retard (fréquent), aucun Reel n'est jamais analysé deux fois ni oublié. ⚠️ Si tu changes l'heure du cron quotidien dans le workflow, mets `HEURE_ANCRAGE` en cohérence.

## La formule de score V2

```
ratio      = vues / followers                    # performance relative au compte
engagement = (likes + 3 × commentaires) / vues   # les commentaires pèsent 3× plus
récence    = min(√(24 / heures_depuis_publi), 2) # bonus vélocité, plafonné

score = ratio × (1 + engagement × 5) × log10(vues + 10) × récence
```

Pourquoi ces choix (et pourquoi c'est mieux que `vues/followers` brut) :

- **`vues / followers`** est le cœur de la détection de viralité : un Reel à 60k vues sur un compte de 20k followers (ratio 3.0) est un bien meilleur signal qu'un Reel à 200k vues sur un compte de 500k followers (ratio 0.4).
- **Commentaires ×3** : un commentaire demande un effort réel, c'est le signal d'accroche le plus fort accessible publiquement. Un like passif ne prédit presque rien.
- **`log10(vues + 10)`** départage deux ratios proches en faveur du volume absolu, sans laisser les gros comptes tout écraser.
- **Facteur de récence** : à stats égales, un Reel posté il y a 4h qui a déjà accumulé ses vues a une vélocité bien supérieure à un Reel posté il y a 22h. C'est lui qui a le plus fort potentiel viral restant. Le facteur est plafonné à ×2 et plancher à 3h pour ne pas sur-récompenser un Reel trop frais avec trop peu de données.
- **`MIN_VUES = 1000`** (réglable) : garde-fou indispensable. Sans lui, un Reel à 300 vues sur un compte de 1 500 followers obtiendrait un ratio énorme avec zéro signal statistique et polluerait le classement.

## Étape 1 — Compte Apify (~5 min)

1. Crée un compte gratuit sur https://apify.com (5$/mois de crédit offert)
2. Va dans **Settings → API & Integrations** et copie ton **API token**

Deux acteurs sont utilisés :

- `apify/instagram-reel-scraper` (quotidien)
- `apify/instagram-profile-scraper` — ID `dSCLg0C3YEZ83HzYX` (hebdomadaire, followers)

## Étape 2 — Intégration Notion (~5 min)

1. Va sur https://www.notion.so/my-integrations
2. Clique **New integration**, nomme-la « Top Reels », sélectionne ton workspace
3. Copie le **Internal Integration Secret** (commence par `ntn_` ou `secret_`)
4. **Important** : ouvre la base « 🎬 Top Reels du Jour » → menu `•••` → **Connections** → ajoute ton intégration

### Nouvelles colonnes Notion (V2)

Ajoute ces deux propriétés **Number** à ta base pour voir les nouvelles métriques :

- `Followers`
- `Vues/Follower`

Si tu ne les ajoutes pas, le script fonctionne quand même (il réessaie automatiquement sans ces colonnes), mais tu perds l'affichage du ratio dans Notion.

## Étape 3 — Configurer le script

Dans `top_reels.py`, la liste `COMPTES` est la **seule source de vérité** : `update_followers.py` la lit automatiquement. Tu ajoutes/retires un compte à un seul endroit.

## Étape 4 — Automatisation (gratuit avec GitHub)

1. Crée un dépôt **privé** sur https://github.com et pousse ces fichiers dedans
2. **Settings → Secrets and variables → Actions → New repository secret** :
   - `APIFY_TOKEN` = ton token Apify
   - `NOTION_TOKEN` = ton secret Notion
3. **Première fois** : onglet **Actions** → « Mise à jour followers (hebdo) » → **Run workflow** pour générer `followers.json` immédiatement (sinon le score utilise une estimation jusqu'au lundi suivant)
4. Ensuite tout est automatique :
   - Lundis 06:00 UTC : mise à jour de `followers.json` (commité automatiquement dans le repo)
   - Chaque jour 20:00 UTC : Top 3 envoyé dans Notion

### Alternative : sur ton propre ordi

```bash
pip install -r requirements.txt
export APIFY_TOKEN="ton_token"
export NOTION_TOKEN="ton_secret"

python update_followers.py   # une fois par semaine
python top_reels.py          # chaque jour
```

## Réglages utiles (en haut de `top_reels.py`)

| Variable | Rôle | Défaut |
|---|---|---|
| `HEURE_ANCRAGE` | Borne fixe de la fenêtre 24-48h (= heure du cron, UTC) | 20 |
| `HEURES_REFERENCE` | Référence du facteur de vélocité (24h = une journée) | 24 |
| `REELS_PAR_COMPTE` | Nombre de Reels scrapés par compte (coût Apify) | 15 |
| `TOP_N` | Nombre de gagnants envoyés dans Notion | 3 |
| `MIN_VUES` | Seuil minimum de vues pour être classé | 1000 |
| `FOLLOWERS_PAR_DEFAUT` | Repli si `followers.json` absent | 50000 |

## ⚠️ À savoir

- Le scraping de comptes tiers est contraire aux CGU d'Instagram. Apify assume ce risque, mais le service peut connaître des interruptions quand Instagram change ses protections. Relance simplement le lendemain.
- Seules les métriques **publiques** sont accessibles (vues, likes, commentaires). Le reach, les partages et le taux de complétion ne sont visibles que par le propriétaire du compte.
- Si un compte est absent de `followers.json` (compte privé, renommé, échec de scraping), le script utilise la **médiane** des comptes connus et marque le résultat « (est.) » dans Notion.
- Si un acteur Apify change de format de sortie, vérifie les noms de champs (`videoPlayCount`, `likesCount`, `followersCount`...) dans la console Apify.
- Un compte renommé sur Instagram doit être mis à jour dans `COMPTES` — sinon il disparaîtra du scraping et de `followers.json`.
