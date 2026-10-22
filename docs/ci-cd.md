# Stratégie CI/CD

1. **Branches** : `main` est toujours déployable ; une branche par sujet ; pull request relue avant fusion (squash). Détails dans `CONTRIBUTING.md`.
2. **Déclenchement** : la CI (`.github/workflows/ci.yml`) tourne sur chaque pull request et à chaque push sur `main`.
3. **Étapes** : lint (`ruff`), tests (`pytest`), construction de l'image Docker (étape `final`), publication.
4. **Publication** : seulement depuis `main`, vers `ghcr.io/<propriétaire>/<dépôt>`. Sur une pull request, l'image est construite mais pas publiée.
5. **Tag** : `YYYYMMDDHHMMSS-sha` (date UTC du build + 7 premiers caractères du commit), pour savoir quand et d'où vient l'image.
6. **Garde-fous** : un ruleset sur `main` exige une pull request, une approbation et les vérifications `test` et `image` vertes. [À adapter : « Appliqué par GitHub. » ou « Configuré mais non appliqué par GitHub sur un dépôt privé gratuit ; respecté par convention. »]
7. **Preuve que le rouge bloque** : une pull request volontairement cassée a rendu `test` rouge et empêché `image` de démarrer (capture : `docs/img/ci-rouge.png`).
8. **Versions** : Python 3.12 en CI et dans Docker ; Python 3.10+ accepté en local.
9. **Secrets** : seul `GITHUB_TOKEN` (fourni par GitHub) est utilisé ; `.env` n'est jamais commité ni copié dans l'image.
10. **Pas encore fait, volontairement** : déploiement automatique (TD 7), matrice de versions, cache de build.