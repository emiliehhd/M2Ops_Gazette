## 5. Règles d'exclusion

Les règles sont dans `src/gazette/regles.py` (réglages en haut du fichier, une fonction par règle, liste ordonnée `REGLES`). Quand plusieurs règles s'appliquent à un article, **seule la première, dans l'ordre ci-dessous, est comptée** : c'est elle qui apparaît dans le rapport.

Deux principes :

- **Les règles sont déterministes.** Elles ne lisent jamais l'heure de la machine : la fraîcheur se mesure par rapport à `recupere_le` (le moment de la collecte). Rejouer le même brut donne exactement le même résultat.
- **Les règles de contenu passent avant la fraîcheur** (R13), pour qu'un article ancien *et* publicitaire soit compté comme publicitaire : sinon la règle de fraîcheur masquerait les autres dans le rapport.

| Identifiant | Ce qu'elle écarte | Pourquoi | Exemple | Cas dans l'échantillon du 23/10 (310 articles) |
|---|---|---|---|---|
| `R01_titre_vide` | Titre vide ou blanc | Article inexploitable | « » | 0 |
| `R02_encodage_casse` | Titre ou extrait contenant encore `Ã`, `â€` ou `�` après normalisation | Texte illisible ; la normalisation répare les cas simples, celle-ci écarte le reste | « L'Ã©conomie en crise » | 0 |
| `R03_date_absente` | Date de publication absente ou illisible | Fraîcheur impossible à contrôler (c'est la raison de l'exclusion du Parisien au TD 1) | `publie_le` vide | 0 |
| `R04_date_future` | Publiée plus de 10 minutes après la collecte | Date fausse (fuseau, erreur de saisie) | Publiée demain | 0 (l'avance maximale observée est une date 25 secondes *avant* la collecte) |
| `R05_publi` | Titre ou rubrique contenant « contenu partenaire », « publi-reportage », « contenu sponsorisé », « brand content », « partenariat commercial » | Contenu payé, pas de l'actualité éditoriale | « Contenu partenaire : trois astuces pour votre jardin » | 0 |
| `R06_autopromo` | Le journal se vend lui-même : titre commençant par « <Journal> lance / propose / recrute… », « Découvrez … avec <Journal> », « Rejoignez / Abonnez-vous à <Journal> » | Offre commerciale, pas de l'actualité | « La Dépêche du Midi lance son espace jeux… » ; « …découvrez la Chine avec La Dépêche du Midi » | **2** (La Dépêche du Midi) |
| `R07_horoscope` | « horoscope » ou « astrologie » dans le titre ou la rubrique | Pas de l'actualité | « Horoscope du jeudi 23 octobre » | 0 |
| `R08_programme_tv` | « programme TV », « que regarder à la télé », « ce soir à la télé »… | Pas de l'actualité | « Programme TV de ce soir » | 0 |
| `R09_jeux` | Quiz, mots croisés / fléchés, sudoku, jeu-concours, « gagnez », « tentez de gagner », « espace jeux » ; rubriques « Jeux », « Mots croisés », « Loto » | Pas de l'actualité | « Quiz : testez vos connaissances » | 0 |
| `R10_rubrique_exclue` | Rubriques « Magazine Lifestyle » et « Magazine Automobile » | Conseils pratiques et témoignages de particuliers, hors actualité (et données personnelles possibles) | « Témoignage. « J'ai peur de reprendre du poids » : Émilie raconte… » | **2** (Le Progrès) |
| `R11_replay` | Titre commençant par « REPLAY » | Rediffusion d'un « DIRECT » sur le même événement : doublon | « REPLAY. Manifestations du 24 octobre : … » | **2** (La Dépêche du Midi) |
| `R12_avis_deces` | « avis de décès », « avis d'obsèques », « faire-part », « remerciements de la famille… » | Données personnelles de particuliers | « Avis de décès : M. Dupont nous a quittés… » | 0 |
| `R13_trop_ancien` | Publié plus de 24 h avant sa collecte | Contrainte du cadrage (un article a moins de 24 h) | Publié il y a 372 jours | **6** (La Dépêche du Midi 5, Le Figaro 1) |
| `R14_doublon_exact` | Même titre (sans accents, majuscules ni espaces en trop) qu'un article déjà gardé **de la même source** | Même article republié | Deux fois le même titre | 0 |
| `R15_doublon_approx` | Titre dont au moins 80 % des mots sont ceux d'un article déjà gardé **de la même source** (Jaccard ≥ 0,8) | Même article légèrement retitré | Même titre avec un mot de plus | 0 |

**Résultat sur l'échantillon du 23/10/2026 :** 310 articles entrés, 298 gardés, 12 rejetés (3,9 %). Par règle : R13 (6), R06 (2), R10 (2), R11 (2). Par source : La Dépêche du Midi 9 sur 101 (9 %), Le Progrès 2 sur 21 (10 %), Le Figaro 1 sur 22 (5 %), les cinq autres sources 0. Aucun taux n'approche le seuil de 80 % du contrôle de qualité.

**À savoir :** neuf règles sur quinze n'ont rien écarté dans cet échantillon (une seule passe, un seul matin). Elles sont testées sur des exemples construits, pas encore sur de vraies données : les trois prochains matins diront si elles sont utiles, inutiles ou trop gourmandes.

### Choix et limites

- **Les doublons ne se cherchent que dans une même source.** Deux journaux qui parlent du même sujet (la mort de Jean-Paul Huchon, six sources) ne sont pas des doublons : c'est ce que la gazette doit montrer. Le rapprochement entre sources est le travail du TD 5.
- **Seuil de similarité à 0,8.** À 0,6, deux articles distincts de La Dépêche du Midi sur la manifestation du 24 octobre à Toulouse (« un parcours plus éloigné du centre-ville » et « accord préfecture-syndicats pour un parcours plus éloigné du centre-ville ») étaient rapprochés à tort ; leur similarité réelle est de 0,69. Un titre de moins de 4 mots n'est jamais comparé (« Édito », « Billet » reviennent chaque jour).
- **« Carnet noir » et « Nécrologie » ne sont pas des rubriques exclues.** Dans l'échantillon, elles portent sur la mort d'une personnalité publique, un vrai sujet d'actualité. Les vrais avis de décès de particuliers sont écartés par leur titre (R12).
- **« People » n'est pas exclue**, ni « Concours » dans un titre (un concours de beauté n'est pas un jeu), ni « jeu » au sens sportif, ni « DIRECT » (seul le « REPLAY » est écarté).
- **Non implémentées volontairement :**
  - *les dépêches d'agence reprises à l'identique* : aucun marqueur d'agence (AFP, Reuters) dans les titres ni les extraits de l'échantillon. Piste : rapprocher les extraits entre sources (similarité très haute) ;
  - *les éditoriaux, chroniques et tribunes* : ils reflètent bien ce dont parlent les rédactions (décision éditoriale à rediscuter après trois matins) ;
  - *les jeux télévisés présentés en rubrique « Télé - médias »* : un sujet de rédaction légitime, une règle sur la rubrique écarterait aussi de vraies informations sur les médias.
- **Une règle trop gourmande** se repère dans le rapport : un taux de rejet élevé pour une règle et une source (voir étape 4).
