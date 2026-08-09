# Troubleshooting

## Connexion refusée

- Vérifiez l'URL Pronote de votre établissement
- Vérifiez identifiant / mot de passe
- Si ENT : vérifiez que l'option est activée pour votre compte

## Déconnexions périodiques

- Vérifiez que vous utilisez la dernière version de l'intégration
- Consultez les journaux (Paramètres → Système → Journaux, filtrer par `pronote`)

## Capteurs manquants

Certaines données (menus, moyennes) ne sont disponibles que si l'établissement
les active côté Pronote.

## Signaler un problème

Ouvrez une [issue](https://github.com/foXaCe/hass-pronote/issues) avec :
- Version de l'intégration et de Home Assistant
- Étapes de reproduction
- Logs pertinents (⚠ supprimez toute donnée sensible : identifiants, jetons, données personnelles, URL privée de l'établissement)
