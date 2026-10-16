# Politique de sécurité

## Signaler une vulnérabilité

Ne publie pas de faille dans une issue publique. Utilise le signalement privé de GitHub (**Security → Report a vulnerability**) sur ce dépôt. Tu recevras une réponse sous 7 jours.

## Modèle de menace

Le projet est prévu pour un usage **local ou sur réseau de confiance**.

- Le dashboard n'a pas de connexion utilisateur ; il ne doit pas être exposé à Internet sans reverse proxy authentifié.
- L'API (`:8000`) est protégée par l'en-tête `X-API-Key` (`AGENCE_API_KEY`).
- Les agents lisent du contenu web non fiable (risque d'injection de prompt). Toute action externe (publication, email, campagne) exige une validation humaine, et les campagnes publicitaires sont créées en pause.
- L'outil `fetch_page` bloque les adresses non publiques (SSRF).

## Secrets

Tous les secrets vivent dans `.env` (ignoré par git, généré par `scripts/init_env.sh`). Si un secret a été committé ou partagé, fais-le tourner immédiatement : clés OmniRoute, jetons Meta/Google, mots de passe générés.
