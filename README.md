# 🎬 Top Reels du Jour — Guide d'installation

Ce système analyse chaque jour les Reels de comptes Instagram publics et envoie le Top 3 dans ta base Notion **« 🎬 Top Reels du Jour »** (déjà créée dans ton workspace).

## Comment ça marche

```
Apify (scraping) → Script Python (scoring) → Notion (Top 3 du jour)
```

Le score valorise les vues **et** l'engagement : `score = vues × (1 + taux_engagement × 5)`. Un Reel avec 50k vues et 8% d'engagement battra un Reel avec 80k vues et 1% d'engagement. Tu peux ajuster cette formule dans `top_reels.py` (fonction `analyser`).

## Étape 1 — Compte Apify (~5 min)

1. Crée un compte gratuit sur https://apify.com (5$/mois de crédit offert, largement suffisant pour quelques comptes par jour)
2. Va dans **Settings → API & Integrations** et copie ton **API token**

## Étape 2 — Intégration Notion (~5 min)

1. Va sur https://www.notion.so/my-integrations
2. Clique **New integration**, nomme-la « Top Reels », sélectionne ton workspace
3. Copie le **Internal Integration Secret** (commence par `ntn_` ou `secret_`)
4. **Important** : ouvre la base « 🎬 Top Reels du Jour » dans Notion → menu `•••` en haut à droite → **Connections** → ajoute ton intégration « Top Reels »

## Étape 3 — Configurer le script

Dans `top_reels.py`, remplace la liste `COMPTES` par les vrais comptes à surveiller :

```python
COMPTES = ["nomducompte1", "nomducompte2", ...]
```

## Étape 4 — Automatisation quotidienne (gratuit avec GitHub)

1. Crée un dépôt **privé** sur https://github.com et pousse ces fichiers dedans
2. Dans le dépôt : **Settings → Secrets and variables → Actions → New repository secret**
   - `APIFY_TOKEN` = ton token Apify
   - `NOTION_TOKEN` = ton secret Notion
3. C'est tout ! Le script tourne chaque jour à 20h UTC (modifiable dans `.github/workflows/daily.yml`)
4. Pour tester tout de suite : onglet **Actions** → « Top Reels quotidien » → **Run workflow**

### Alternative : sur ton propre ordi

```bash
pip install requests
export APIFY_TOKEN="ton_token"
export NOTION_TOKEN="ton_secret"
python top_reels.py
```

## Réglages utiles (en haut de `top_reels.py`)

| Variable | Rôle | Défaut |
|---|---|---|
| `FENETRE_HEURES` | Ne garder que les Reels publiés dans les X dernières heures | 24 |
| `REELS_PAR_COMPTE` | Nombre de Reels scrapés par compte (impacte le coût Apify) | 10 |
| `TOP_N` | Nombre de gagnants envoyés dans Notion | 3 |

## ⚠️ À savoir

- Le scraping de comptes tiers est contraire aux CGU d'Instagram. Apify assume ce risque à ta place, mais le service peut connaître des interruptions quand Instagram change ses protections. C'est normal — relance simplement le lendemain.
- Seules les métriques **publiques** sont accessibles (vues, likes, commentaires). Le reach, les partages et le taux de complétion ne sont visibles que par le propriétaire du compte.
- Si l'acteur `apify/instagram-reel-scraper` change de format de sortie, vérifie les noms de champs (`videoPlayCount`, `likesCount`...) dans la console Apify et ajuste la fonction `analyser`.
