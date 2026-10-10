# Configurer les intégrations

Chaque intégration est optionnelle. Sans elle, l'agent concerné continue et signale la donnée manquante dans son livrable ; une action non configurée échoue proprement après validation, sans bloquer les autres.

Deux niveaux de configuration :

- **`.env`** : clés globales de l'agence (redémarrer l'API après modification).
- **Paramètres JSON du client** (dashboard, page Clients) : identifiants propres au client.

```json
{
  "timezone": "Africa/Tunis",
  "daily_watch": true,
  "weekly_report": true,
  "crm_followups": false,
  "ga4_property_id": "123456789",
  "search_console_site": "sc-domain:client.com",
  "google_ads_customer_id": "123-456-7890",
  "meta_ad_account_id": "act_1234567890",
  "postiz_integration_ids": ["id-linkedin", "id-instagram"],
  "listmonk_list_ids": [3]
}
```

## OmniRoute (obligatoire)

1. http://localhost:20128 : connecte au moins un fournisseur.
2. API Keys : crée une clé, mets-la dans `OMNIROUTE_API_KEY`.
3. Optionnel : combos par rôle et clés par client avec `scripts/omniroute_setup.py` (voir le README).
4. Pour les visuels : renseigne `MODEL_IMAGE` (et `MODEL_TTS` pour les voix off) avec un modèle exposé par OmniRoute sur `/v1/images` et `/v1/audio`.
5. Pour la mémoire sémantique des brand kits volumineux : `MODEL_EMBEDDING`. Sans lui, le brand kit complet est injecté (suffisant pour la plupart des clients).

## Recherche web

SearXNG tourne en local (profil `core`) et suffit. Pour des résultats de meilleure qualité, ajoute `TAVILY_API_KEY`.

## Postiz (publication sociale)

1. `scripts/start.sh social`, puis crée un compte sur http://localhost:4007 (désactive ensuite les inscriptions avec `DISABLE_REGISTRATION: "true"` dans `docker-compose.yml`).
2. Connecte les comptes sociaux du client. Chaque réseau nécessite une application développeur (LinkedIn, Meta, X, TikTok…) dont les identifiants s'ajoutent dans l'environnement du service `postiz` (`LINKEDIN_CLIENT_ID`, `FACEBOOK_APP_ID`, etc., voir la documentation Postiz).
3. Settings -> Public API : copie la clé dans `POSTIZ_API_KEY`.
4. Récupère les identifiants des canaux du client (outil `list_social_channels`, ou l'API `GET /api/public/v1/integrations`) et renseigne `postiz_integration_ids` dans les paramètres du client. Vide = tous les canaux.

Postiz s'appuie sur Temporal. Temporal (stockage SQL) n'accepte que trois attributs de recherche de type Text : le service est lancé avec `SKIP_ADD_CUSTOM_SEARCH_ATTRIBUTES=true` pour les laisser à Postiz. Si le backend Postiz boucle sur « cannot have more than 3 search attribute of type Text », supprime les attributs de démonstration :

```bash
docker compose --profile core --profile social exec temporal sh -c 'for a in CustomTextField CustomStringField; do echo y | tctl --address temporal:7233 admin cluster remove-search-attributes --name $a; done'
docker compose --profile core --profile social restart postiz
```

## Google (GA4, Search Console, Google Ads)

Les outils utilisent un jeton OAuth 2.0 (`GOOGLE_OAUTH_ACCESS_TOKEN`) avec les scopes `analytics.readonly`, `webmasters.readonly` et `adwords`. Pour un jeton durable, génère un refresh token (OAuth Playground ou `gcloud auth application-default login --scopes=...`) et rafraîchis l'access token via une tâche n8n ou cron.

- GA4 : `ga4_property_id` (Admin -> Paramètres de la propriété).
- Search Console : `search_console_site` (`sc-domain:exemple.com` ou URL du préfixe).
- Google Ads : `GOOGLE_ADS_DEVELOPER_TOKEN`, `GOOGLE_ADS_LOGIN_CUSTOMER_ID` (compte MCC de l'agence) et `google_ads_customer_id` par client. Les campagnes sont toujours créées en PAUSE.

## Meta Ads

`META_ACCESS_TOKEN` : token d'utilisateur système (Business Manager) avec `ads_read` et `ads_management`. Par client : `meta_ad_account_id`. Les campagnes sont créées en PAUSE.

## Twenty CRM

`scripts/start.sh crm`, crée l'espace de travail sur http://localhost:3002, puis Settings -> APIs -> Create key : mets-la dans `TWENTY_API_KEY`.

## Listmonk (emailing)

http://localhost:9002 (admin / `ADMIN_PASSWORD`). Configure un serveur SMTP (Settings -> SMTP), crée un utilisateur API (Users -> New, type API) : `LISTMONK_API_USER` et `LISTMONK_API_TOKEN`. Par client : `listmonk_list_ids`. Les campagnes sont créées en brouillon, sauf si l'agent propose `send: true` et que tu le valides.

## Langfuse

`scripts/start.sh observability` : le projet `agence-ia` est créé automatiquement avec `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` de `.env`. Connexion sur http://localhost:3001 avec `ADMIN_EMAIL` / `ADMIN_PASSWORD`. Redémarre l'API après le premier démarrage de Langfuse pour activer les traces.
