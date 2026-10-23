# Contrôles de qualité, métriques et alerte

Après chaque passe (toutes les 30 minutes), la tâche Airflow `controler` vérifie des **faits sur
les vraies données**, enregistre les **métriques** de la passe et **alerte** sur Discord quand un
fait est faux.

## Pourquoi ce n'est pas dans la CI

| | La CI | Les contrôles |
|---|---|---|
| Ce qu'ils vérifient | Le **code** des règles, sur des exemples construits (`tests/`) | Des **faits** sur les données réelles de la base |
| Quand | À chaque pull request | Après chaque passe, en exploitation |
| Si ça échoue | On corrige le code avant de fusionner | On alerte l'équipe : les données ont un problème maintenant |

## Les huit contrôles

Code : `src/gazette/controles.py`. Chacun répond « vérifié » ou « en échec » avec une valeur mesurée.

| Identifiant | Fait vérifié | Seuil | Si c'est faux |
|---|---|---|---|
| `C01_aucune_date_future` | Aucun article gardé n'a une date postérieure à sa collecte | 0 (tolérance d'horloge : 10 min) | Bug de date ou de fuseau : regarder `R04_date_future` dans `src/gazette/regles.py` |
| `C02_aucun_titre_vide` | Aucun article gardé n'a un titre vide | 0 | La règle `R01_titre_vide` ne joue pas son rôle |
| `C03_aucun_article_trop_ancien` | Aucun article gardé n'avait plus de 24 h à sa collecte | 0 | La règle `R13_trop_ancien` ne joue pas son rôle |
| `C04_taux_rejet_par_source` | Le taux de rejet d'une source ne dépasse pas le seuil, sur la journée UTC | 80 % (au moins 5 articles traités) | Une règle est trop gourmande, ou la source a changé de format : lire le rapport du jour (`rapports/`) |
| `C05_extrait_borne` | Aucun extrait gardé ne dépasse 300 caractères | 0 | La normalisation ne borne plus l'extrait |
| `C06_aucun_html` | Aucun titre ni extrait gardé ne contient de balise HTML | 0 | La normalisation laisse passer du HTML |
| `C07_aucune_source_en_sommeil` | Aucune source n'est en sommeil | 0 | Voir le journal `source_mise_en_sommeil`, corriger, puis `python -m gazette.db reveiller "Nom"` |
| `C08_collecte_recente` | Une source au moins a été lue avec succès depuis moins de 2 h | 2 h | La collecte est à l'arrêt : machine éteinte, réseau, Airflow en panne |

Choix de seuils :
- **C04** : une source qui n'a que 1 à 4 articles traités n'a pas de taux significatif (un seul
  rejet donnerait 100 %), elle n'est pas jugée. Le seuil se règle avec la variable
  `GAZETTE_SEUIL_TAUX_REJET` (0,8 par défaut).
- **C08** : 2 h, soit quatre passes de suite sans aucune réussite. Quand la collecte échoue
  entièrement, le DAG s'arrête avant le nettoyage, mais `controler` tourne quand même
  (`trigger_rule="all_done"`) : c'est précisément là qu'il faut alerter.

## Outil : des contrôles écrits à la main

Des requêtes SQL et du Python, plutôt qu'un outil dédié (Great Expectations, Soda…).
- **Pour :** huit faits simples (des comptages), aucun service ni dépendance en plus, résultats
  lisibles et testés dans le même dépôt, budget zéro.
- **Contre :** nous maintenons nous-mêmes les contrôles, et nous n'avons pas l'interface de
  rapport de ces outils.
- **À reconsidérer** si les contrôles se multiplient ou si une autre équipe doit les écrire.

## Métriques

Une métrique est un chiffre horodaté. Elles sont enregistrées dans la table **`metriques`**
(nom, étiquette, valeur, date), ce qui garde l'**historique** : on voit une dérive d'un jour à
l'autre. Les compteurs de chaque tâche sont aussi dans l'onglet **XCom** d'Airflow.

| Nom | Étiquette | Publiée par | Sens |
|---|---|---|---|
| `collecte_recus`, `collecte_ecrits`, `collecte_ignores` | | `collecter` | Articles reçus des flux, écrits (nouveaux), ignorés (déjà présents) |
| `collecte_sources_inchangees`, `collecte_sources_en_erreur`, `collecte_sources_en_sommeil` | | `collecter` | État des sources à la passe |
| `collecte_duree_secondes` | | `collecter` | Durée de la passe |
| `nettoyage_entres`, `nettoyage_gardes`, `nettoyage_rejetes`, `nettoyage_illisibles` | | `nettoyer` | Articles traités à la passe, gardés, rejetés, fichiers illisibles |
| `nettoyage_rejets_par_regle` | règle | `nettoyer` | Rejets de la passe par règle |
| `jour_traites`, `jour_gardes`, `jour_rejetes`, `jour_taux_rejet` | | `controler` | Cumul de la journée UTC |
| `jour_traites_par_source`, `jour_rejetes_par_source`, `jour_taux_rejet_par_source` | source | `controler` | Cumul de la journée, par source |
| `jour_rejets_par_regle` | règle | `controler` | Rejets de la journée par règle |
| `controles_en_echec` | | `controler` | Nombre de contrôles en échec |
| `controle_ok`, `controle_valeur` | contrôle | `controler` | 1 si vérifié (0 sinon) ; valeur mesurée |

Les appels `stats.gauge(...)` d'Airflow ne sont pas utilisés : ils sont ignorés tant qu'aucun
outil de collecte (StatsD, OpenTelemetry) n'est activé, ce qui viendra avec la supervision (TD 8).
La table `metriques` pourra alors être lue telle quelle.

```sql
-- Taux de rejet par source, les 10 dernières mesures
SELECT mesure_le, etiquette, round(valeur::numeric, 3) AS taux
FROM metriques WHERE nom = 'jour_taux_rejet_par_source'
ORDER BY mesure_le DESC LIMIT 10;
```

## Alerte Discord

### Mettre en place le canal

1. Dans Discord, sur le serveur de l'équipe : paramètres du canal (ou du serveur) → **Intégrations**
   → **Webhooks** → créer un webhook, choisir le canal, **copier l'adresse du webhook**.
2. La coller dans `.env`, ligne `DISCORD_WEBHOOK_URL=...`.
3. Tester : `docker compose run --rm app python -m gazette.controles test-alerte`. Un message
   doit apparaître dans le canal.
4. Pour Airflow : `docker compose --profile orchestration up -d --build` (l'image contient notre
   code, et le conteneur lit `.env`).

**L'adresse du webhook est un secret** : quiconque la connaît peut écrire dans le canal. Elle
reste dans `.env` (ignoré par Git), n'apparaît jamais dans un message d'erreur ni dans le journal,
et les mentions (`@everyone`) sont désactivées dans les messages. Si elle fuite : supprimer le
webhook dans Discord et en créer un autre.

### Quand l'alerte sonne

Pour éviter un message toutes les 30 minutes pour la même panne, l'état de chaque contrôle est
gardé dans la table `controles_etat`.

| Situation | Message |
|---|---|
| Un contrôle passe de « vérifié » à « en échec » | **ALERTE** |
| Il reste en échec depuis 24 h ou plus | **RAPPEL** (une fois par 24 h) |
| Il redevient vérifié | **RÉTABLI** |
| Il reste en échec depuis moins de 24 h, ou reste vérifié | Aucun message |

Un seul message par passe, même si plusieurs contrôles changent d'état. Si Discord n'est pas
joignable, les métriques sont tout de même enregistrées, la tâche passe au rouge dans Airflow et
l'alerte est retentée à la passe suivante. Sans `DISCORD_WEBHOOK_URL`, les contrôles tournent et
le manque est signalé dans le journal (`alerte_non_configuree`).

Les contrôles ne font **pas** échouer la tâche quand un fait est faux : l'alerte est le signal.
Sinon une panne connue rendrait toutes les passes rouges dans Airflow et cacherait les vraies
erreurs de tâche.

### Déclencher l'alerte pour de vrai

```bash
# Lancer les contrôles maintenant
docker compose run --rm app python -m gazette.controles

# Provoquer l'alerte : baisser le seuil de rejet à 5 %
docker compose run --rm -e GAZETTE_SEUIL_TAUX_REJET=0.05 app python -m gazette.controles
```

La source en sommeil est elle aussi une vraie panne : `C07` alerte tant qu'une source de
`sources.csv` est en sommeil (aujourd'hui La Voix du Nord, qui refuse les robots).

## Limites connues

- Le taux de rejet (`C04`) est calculé sur la journée **UTC** : il est peu significatif en début
  de journée, d'où le minimum de 5 articles.
- Si la machine ou Airflow s'arrête, la tâche de contrôle ne tourne pas non plus : c'est le rôle du
  battement de cœur externe (Healthchecks), prévu avec la supervision.
- Le premier jour compte tout l'arriéré du brut, traité en une fois.
