# ADR 0001 — Fondations locales V0.1

Date : 5 novembre 2026. Statut : accepté pour la V0.1.

Le document d’architecture décrit la cible V1.0 et une feuille de route. Le présent jalon livre seulement les fondations indispensables : un monolithe Python dont le domaine ne dépend pas de FastAPI, une API, un frontend React/TypeScript, PostgreSQL et Redis sous Compose.

## Décisions

- `investigation.domain` définit les identités et les montants sans dépendre de l’API, de SQLAlchemy, de Redis ou de Celery. Les contrats de fournisseurs sont dans `connectors` ; aucune URL de fournisseur ni clé n’est configurée.
- Identifiants de chaîne sous forme `namespace:reference`. Les clés EVM d’adresses incluent la chaîne et les 20 octets normalisés. Les chaînes non EVM ont une place dans le format de chaîne ; leur validation d’adresses/actifs et leur stockage spécifique ne sont pas implémentés.
- `NUMERIC(78,0)` avec borne uint256 en base, type SQLAlchemy ramené en `int`, chaînes décimales dans les contrats OpenAPI. Le frontend met en forme les chaînes sans calcul en flottants. Les métadonnées de décimales sont nullable et sourcées.
- Une observation conserve l’inclusion (chaîne, hash de bloc, transaction, origine et position), le hash parent, les ordres, la finalité structurée et la provenance. L’unicité autorise plusieurs inclusions historiques dans des blocs différents. Cela prépare le stockage d’orphelins, sans implémenter la détection des réorganisations.
- Les opérations associent plusieurs mouvements avec des rôles. Les assertions de labels et allocations ont des tables distinctes ; leurs moteurs et endpoints attendent les jalons suivants. Aucune opération ne contient de score d’identité ou d’allocation implicite.
- Un run conserve graines, paramètres, bornes et hashes, politique, versions, snapshots de labels, limites, causes d’arrêt et manifest. Le seul run peuplé est un snapshot de fixture explicitement synthétique ; les nouveaux runs sont `unsupported`. Aucun job fictif ni collecte implicite.
- Le chargement de démonstration est un service Compose ponctuel après migration, rejouable grâce à des identifiants déterministes ; il n’est jamais lancé à l’import de l’API. Le fixture UTF-8 est versionné et son JSON canonique reçoit une empreinte SHA-256.
- Les petites pièces de démonstration restent en JSON dans PostgreSQL. Le stockage objet n’est pas nécessaire au jalon. L’empreinte n’affirme aucune authenticité sur chaîne.
- La table est la première vue de consultation ; le graphe, les expansions et la chronologie synchronisée appartiennent à la V0.3. Les bibliothèques qui ne servent pas le jalon (Cytoscape, Celery, web3, etc.) ne sont pas installées.
- L’instance est locale mono-utilisateur et ses ports sont liés à la boucle locale. Pas de faux mécanisme d’authentification par identifiant fourni par le client. Les dossiers ne sont pas présentés comme privés entre utilisateurs ; OIDC et autorisation attendent la V0.8.

## Conséquences

L’application démontre les contrats et la séparation scientifique des couches, sans prouver un traçage réel. Les trois chaînes proposées par la cible apparaissent comme **non prises en charge**. Un historique vide complet est distinct d’un fournisseur indisponible (`data: null`, `unsupported`, couverture absente et limites explicites).

Les tests d’exactitude et de contraintes doivent passer sur PostgreSQL réel. SQLite ne constitue pas un substitut pour ce critère. Les tests de migration effectuent un aller/retour sur une base dédiée vide et comparent le schéma migré aux modèles.

Les migrations ultérieures devront conserver ces séparations et adapter explicitement les contrats plutôt que réécrire cette migration initiale.
