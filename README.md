# Ariadne · V0.1

Socle local du [document d’architecture](architecture-tracage-blockchain-v1.md) : monolithe modulaire Python, FastAPI, React/TypeScript, PostgreSQL et Redis. **Seule la V0.1 est implémentée.**

Le dossier **« Démonstration » contient exclusivement des données synthétiques**. Aucun réseau n’est collecté, aucun protocole réel n’est décodé et aucun lien inter-chaînes n’est inféré. Les adresses et hashes du fixture ne doivent pas servir à rechercher des transactions réelles.

## Lancement depuis un clone

Prérequis : Git, Docker Engine/Docker Desktop démarré, Docker Compose v2.27 ou ultérieur, accès réseau pour les images et les dépendances. Aucun fournisseur blockchain ni secret RPC nécessaire. Node et Python sur l’hôte ne sont pas nécessaires pour lancer l’application.

Depuis la racine du clone, sous PowerShell :

```powershell
Copy-Item .env.example .env
docker compose up --build -d
docker compose ps -a
```

Sous Linux/macOS, remplacer la première commande par `cp .env.example .env`. Le premier build télécharge les dépendances. PostgreSQL devient sain, Alembic applique `0001`, le service `demo` charge une fois le fixture, puis l’API et le frontend démarrent. Les services `migrate` et `demo` doivent sortir avec le code **0** ; c’est leur état normal.

- Interface : <http://localhost:8080>
- OpenAPI interactif : <http://localhost:8000/docs>
- Disponibilité PostgreSQL/migration/Redis : <http://localhost:8000/health/ready>
- Vivacité du processus API : <http://localhost:8000/health/live>

Si un port est occupé, changer `WEB_PORT` ou `API_PORT` dans `.env`. Les ports PostgreSQL et Redis ne sont pas publiés ; API et web sont liés à `127.0.0.1`. Cette version **sans authentification est réservée à une instance locale mono-utilisateur** : elle ne garantit pas des dossiers privés entre plusieurs utilisateurs. Ne pas la publier derrière un proxy public.

```powershell
docker compose logs --tail 100 migrate demo api web
docker compose stop
docker compose up -d
```

Les données restent dans les volumes `postgres_data` et `redis_data`. `docker compose down` conserve aussi ces volumes. Le mot de passe d’exemple sert au développement local ; le modifier après création du volume ne modifie pas le rôle PostgreSQL existant.

## Parcours minimal

1. Ouvrir le dossier **Démonstration · Transfert puis dispersion**.
2. Lire les trois mouvements ; le premier conserve exactement **1,000000000000000001 ETH**, soit `1000000000000000001` unités brutes.
3. Sélectionner un transfert puis ouvrir ses références et le contenu de la pièce synthétique.
4. Inspecter la couverture partielle, les causes d’arrêt et le manifest du run. La finalité et la canonicalité réelles restent inconnues.
5. Créer éventuellement un dossier avec un hash EVM, puis « Figer un run sans analyse ». Ce run conserve la graine et renvoie `unsupported`, sans importer le scénario de démonstration ni appeler un fournisseur.

Les panneaux **Observations**, **Attribution** et **Allocation analytique** sont séparés. Aucune identité, aucun label d’entité, aucun prix et aucune allocation ne sont inventés. Le fixture illustre seulement des transferts ; il ne valide pas un décodeur sur des transactions publiques. Les frais et soldes initiaux sont hors scénario.

## Vérifications reproductibles

Tests Python, migrations aller/retour, absence de dérive du schéma et contrats API sur un PostgreSQL de test isolé :

```powershell
docker compose --profile verification run --build --rm tests
docker compose --profile verification stop test-postgres
```

La base `ariadne_test` est distincte des données de l’application et utilise un stockage temporaire. Le test refuse une base non vide ou dont le nom ne contient pas `ariadne_test`. Les modifications de chaque test sont annulées ; les migrations de test sont retirées à la fin.

Vérification HTTP de la pile lancée, sans dépendance Python tierce :

```powershell
python scripts/smoke.py
```

Sans Python hôte, exécuter le script dans le conteneur :

```powershell
docker compose exec -T api python - < scripts/smoke.py
```

Cette dernière redirection est pour les shells POSIX. Sous PowerShell :

```powershell
Get-Content -Raw -Encoding UTF8 scripts/smoke.py | docker compose exec -T api python -
```

Build, formatage des montants et parcours navigateur (Node 24.12+, navigateur Playwright à télécharger une fois) :

```powershell
cd apps/web
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Le test navigateur utilise la pile Compose à `http://127.0.0.1:8080`. La variable `WEB_URL` permet de changer cette cible. Les tests des montants n’utilisent jamais une conversion du montant en `Number`.

## Développement

Python 3.12 est la référence conteneurisée. Les dépendances Python sont figées dans `requirements.lock`, celles du frontend dans `apps/web/package-lock.json` ; les images ont des tags de version explicites.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.lock
.venv/Scripts/python.exe -m pip install --no-deps -e .
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m scripts.export_openapi
cd apps/web
npm run generate:api
npm run dev
```

Sans `TEST_DATABASE_URL`, les tests PostgreSQL sont explicitement sautés. Ils ne sont pas remplacés par SQLite : son stockage numérique ne valide pas les entiers EVM à 256 bits. Pour les exécuter hors Compose, fournir une base PostgreSQL **dédiée vide** dont le nom contient `ariadne_test` et, pour le contrôle de disponibilité complet, `REDIS_URL`.

Le serveur Vite relaie `/api` vers `127.0.0.1:8000` (l’API Compose). Une API exécutée hors conteneur utilise `DATABASE_URL`, ou `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, et `REDIS_URL`. Aucun endpoint RPC utilisateur n’est accepté.

## Organisation et contrats

```text
apps/api/             adaptation FastAPI et OpenAPI
apps/web/             interface React/TypeScript, types générés depuis OpenAPI
src/investigation/    identités, quantités, contrats, schéma et fixture synthétique
src/connectors/       interface fournisseur et implémentation indisponible
src/decoders/          emplacement réservé, aucun décodeur réel
src/workers/           emplacement réservé, aucun job en V0.1
migrations/           migration Alembic initiale figée
infra/                images et proxy nginx
tests/                invariants, intégration PostgreSQL, parcours Playwright
docs/adr/              décisions de périmètre
docs/releases/v0.1.md  vérifications effectuées et critères non couverts
```

Les adresses sont identifiées par chaîne + octets normalisés, avec affichage séparé ; les actifs par chaîne + contrat ou `/native`, jamais par symbole. Les montants sont des `int` Python, `NUMERIC(78,0)` PostgreSQL avec contraintes uint256, et des chaînes décimales dans l’API. Les décimales d’un actif peuvent être inconnues. Une observation référence un bloc (hash inclus), une transaction, sa position, sa source et sa pièce. Les opérations portent les références et versions de regroupement, avec une association permettant plusieurs mouvements. Les runs conservent des snapshots plutôt que recalculer les preuves à la lecture.

Les endpoints V0.1 sont listés dans `/docs` et [docs/openapi.json](docs/openapi.json) : capacités, dossiers, graines, runs, opérations, observations et pièces. `POST /cases/{id}/runs` exige `Idempotency-Key` ; un rejeu retrouve le même run. Les listes de dossiers et d’opérations acceptent `limit` (1–100) et `offset`. Les routes jobs, graphe, expansion, SSE, labels, annotations et exports de l’architecture cible ne sont pas livrées dans cette version.

Les tables `label_assertions` et `allocations` définissent uniquement leurs contrats initiaux, sans service d’enrichissement ou moteur d’allocation. Redis est démarré et vérifié, sans cache ni file de tâches artificiels. Les petites pièces synthétiques sont conservées en PostgreSQL ; le stockage S3, Celery, OIDC et l’observabilité avancée attendent leurs jalons.

Voir [la décision V0.1](docs/adr/0001-fondations-v0.1.md) et [le bilan de livraison](docs/releases/v0.1.md). La V0.2 n’a pas commencé.
