# Contributing

Merci de votre intérêt pour l'intégration Pronote pour Home Assistant !

## Signaler un bug

Utilisez le [bug report template](.github/ISSUE_TEMPLATE/bug_report.yml).

## Suggérer une fonctionnalité

Utilisez le [feature request template](.github/ISSUE_TEMPLATE/feature_request.yml).

## Pull requests

1. Forkez le dépôt
2. Créez une branche dédiée : `git checkout -b feat/ma-feature`
3. Installez le runner pre-commit : `prek install` (ou `pre-commit install` si vous préférez la version Python)
4. Code + tests : `pytest --cov=custom_components/pronote`
5. Lint : `ruff check . && ruff format .`
6. Type check : `mypy custom_components/pronote`
7. Commit (conventional commits) : `feat: …`
8. Poussez et ouvrez une PR vers `main`

## Setup local

Voir [.devcontainer/](.devcontainer/) ou installez manuellement les dépendances de `requirements_dev.txt`.

## Gestion des dépendances

Ce dépôt utilise **Renovate** (et non Dependabot). Les PR de mise à jour sont
ouvertes par le bot `@renovate[bot]`. Voir le [dashboard Renovate](../../issues?q=is:issue+author:app/renovate).
