# Ariadne · V0.2.0

Application locale d’investigation Ethereum conforme au [jalon V0.2](architecture-tracage-blockchain-v1.md) : découverte bornée par adresse, collecte RPC de transactions/reçus/logs/blocs, transferts ETH de premier niveau et événements ERC-20 standard, montants exacts et provenance consultable. **La V0.3 n’est pas commencée.**

Le dossier **Démonstration** reste entièrement synthétique. Il n’est jamais utilisé comme résultat ou comme fournisseur de secours pour un dossier de collecte. Les dossiers non synthétiques sont alimentés uniquement par les fournisseurs configurés côté serveur.

## Lancement et mise à jour depuis V0.1

Prérequis : Docker Engine/Docker Desktop démarré, Docker Compose 2.27+, accès réseau pour les images et dépendances. Aucun Node ni Python hôte nécessaire pour lancer la pile.

Sur un nouveau clone, sous PowerShell :

```powershell
Copy-Item .env.example .env
docker compose up --build -d --wait --wait-timeout 180
docker compose ps -a
```

Sous Linux/macOS : `cp .env.example .env` pour la première commande. Pour une instance V0.1 existante, **conserver son `.env` et ses volumes**, ajouter les variables facultatives ci-dessous, puis lancer la même commande Compose. Alembic applique `0002` après `0001`, sans recréer les tables V0.1 ; la démo existante est conservée. Les services ponctuels `migrate` et `demo` doivent sortir à **0**.

- Interface : <http://localhost:8080>
- OpenAPI : <http://localhost:8000/docs>
- Disponibilité PostgreSQL, migration et Redis : <http://localhost:8000/health/ready>
- Vivacité : <http://localhost:8000/health/live>

Les ports sont modifiables via `WEB_PORT` et `API_PORT`. Seuls web et API sont publiés, sur `127.0.0.1`. PostgreSQL et Redis restent privés au réseau Compose. L’instance est **locale, mono-utilisateur, sans authentification** ; elle ne garantit pas l’isolation de dossiers entre plusieurs utilisateurs et ne doit pas être exposée publiquement.

```powershell
docker compose logs --tail 100 migrate demo api web
docker compose stop
docker compose up -d
```

`docker compose down` conserve les volumes applicatifs. Ne pas utiliser `down -v` pour une mise à jour. Le mot de passe PostgreSQL d’exemple est destiné au développement ; le changer dans `.env` ne modifie pas un rôle déjà créé dans un volume existant.

## Configurer la collecte Ethereum

Dans `.env`, configurer les fournisseurs choisis par l’administration :

```dotenv
ETHEREUM_RPC_URL=https://votre-fournisseur-rpc-ethereum-mainnet
ETHERSCAN_API_KEY=votre-cle-etherscan-v2
```

Puis appliquer la configuration : `docker compose up -d --force-recreate api`. L’URL RPC peut contenir un secret : ne pas la committer, la transmettre au navigateur ou la mettre dans un corps de requête utilisateur. Seul HTTPS est accepté, sauf HTTP sur boucle locale pour un nœud local hors Compose. L’application ne propose aucun formulaire d’URL RPC et ne suit pas les redirections des fournisseurs.

| Configuration | Comportement |
|---|---|
| Aucun fournisseur | Démonstration consultable ; nouveaux runs `unsupported`, sans donnée simulée |
| RPC Ethereum seul | Collecte d’une transaction explicite ; historique par adresse indisponible |
| RPC + clé Etherscan V2 | Découverte `txlist` + `tokentx` dans une plage de blocs, puis vérification RPC de chaque transaction retenue |
| RPC d’une autre chaîne | Collecte refusée avec `rpc_chain_mismatch` |
| RPC/clé défaillants, quota, reçus manquants | État partiel ou indisponible et causes visibles ; aucune substitution silencieuse |

`GET /api/v1/capabilities` décrit les capacités **configurées**, pas un historique déjà collecté ou une garantie de disponibilité. Base et Arbitrum restent `unsupported`. Les coûts, quotas réels et profondeurs historiques dépendent des offres choisies. Les clés et URL secrètes sont masquées dans les erreurs et pièces conservées.

## Parcours

1. Consulter le dossier **Démonstration · Transfert puis dispersion** pour le parcours synthétique V0.1, avec conservation exacte du wei dans `1,000000000000000001 ETH`.
2. Créer un dossier Ethereum avec un **hash de transaction** ou une **adresse et une plage de blocs**. Les bornes sont inclusives et limitées à 10 000 blocs.
3. Choisir le maximum de transactions (10 par défaut, 20 au maximum) et cliquer sur **Collecter Ethereum**. La requête est synchrone et bornée ; elle n’est pas une tâche en arrière-plan.
4. Lire les mouvements normalisés, sélectionner une opération, puis consulter ses pièces, sa position, son actif exact et sa finalité observée. Un ERC-20 est identifié par son contrat, jamais par son symbole.
5. Examiner aussi les **Transactions conservées** : un reçu échoué reste inspectable et ne crée aucun transfert effectif. Le manifest permet de consulter les requêtes de découverte, les pièces RPC et les erreurs, même sans mouvement normalisé.
6. Vérifier la couverture, les causes d’arrêt, les bornes et les versions du run. Les pages suivantes de la table affichent les opérations supplémentaires déjà collectées ; elles ne déclenchent aucun appel blockchain.

Les observations, attributions et allocations restent distinctes. Aucun label d’entité, prix, swap, lien inter-chaînes ou allocation n’est produit. Un événement au format ERC-20 n’atteste pas à lui seul la conformité du token ou sa valeur économique.

## Bornes et états

- 100 appels, budget réseau de 45 s, 24 Mio reçus au total et 4 Mio par réponse ; maximum de 200 mouvements par run.
- Au maximum 12 pages de découverte par graine, avec rythme prudent des appels Etherscan. Les pages pleines sont poursuivies ; au plafond de résultats, les plages sont subdivisées. Un bloc trop dense, un quota atteint ou une panne conserve une limite explicite.
- Une seule collecte à la fois sur l’instance locale ; une seconde requête concurrente reçoit 409. Une même `Idempotency-Key` restitue le même run et refuse d’autres paramètres. La clé est conservée dans l’interface lors d’une tentative échouée tant que ses paramètres ne changent pas.
- `complete_within_declared_scope` : complet uniquement pour les sources, transactions, plages et formats déclarés. `partial` : collecte ou finalité incomplète. `unsupported` : réseau, fournisseur ou mode indisponible. `unknown` : transaction introuvable sans preuve d’absence définitive.

Les transferts ETH internes, frais, retraits de consensus, NFT et protocoles composites sont hors périmètre. Une absence d’activité dans les flux de l’indexeur n’affirme pas une absence universelle d’activité économique. Les décimales d’un contrat peuvent rester inconnues : le montant brut exact reste disponible.

Le contrôle RPC rapproche transaction, reçu, logs et inclusion dans le bloc, puis vérifie le hash retenu par numéro de bloc. Canonicalité et finalité sont observées **au moment de la collecte**, sans surveillance continue des réorganisations. Les tags `safe` et `finalized` restent distincts. Une interruption du processus avant commit peut annuler le run : jobs durables, reprise, annulation et SSE attendent la V0.3.

Les graines V0.1 avec période ISO sont conservées. Pour collecter une telle adresse via l’API, fournir une plage `block_range` explicite ; la couverture porte sur l’intersection de cette plage avec la période. Le frontend V0.2 crée directement des graines à bornes de blocs.

## Vérifications reproductibles

Suite hors ligne, corpus public conservé, migrations aller/retour et tests d’intégration sur PostgreSQL dédié :

```powershell
docker compose --profile verification run --build --rm tests
docker compose --profile verification stop test-postgres
```

La base `ariadne_test` est isolée et temporaire. Les tests refusent une base non vide ou mal nommée, vérifient la préservation d’un dossier V0.1 pendant la migration, comparent le schéma aux modèles et ne contactent jamais un fournisseur externe. Aucun test d’exactitude PostgreSQL n’est remplacé par SQLite.

Contrôle HTTP de la pile démarrée, avec Python hôte sans dépendance tierce :

```powershell
python scripts/smoke.py
```

Sans Python hôte, sous PowerShell :

```powershell
Get-Content -Raw -Encoding UTF8 scripts/smoke.py | docker compose exec -T api python -
```

Sous un shell POSIX : `docker compose exec -T api python - < scripts/smoke.py`.

Frontend, Node 24.12+ :

```powershell
cd apps/web
npm ci
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Les tests utilisent `http://127.0.0.1:8080` (modifiable par `WEB_URL`). Le scénario de fournisseur absent n’est exécuté que si aucun RPC n’est configuré ; il crée un dossier de vérification local sans observation simulée.

## Corpus public et contrôle live facultatif

Les fichiers `tests/fixtures/ethereum/{native,erc20,failed}.json` contiennent des réponses publiques capturées, séparées du fixture synthétique de l’application. Les attentes revues sont dans `expected.json` : bloc **26347604**, un transfert ETH de `13230000000000000` wei, quatre mouvements ERC-20 bruts, et aucun mouvement effectif pour la transaction échouée. Les pièces incluent les limites réelles du fournisseur, notamment l’indisponibilité de certains états historiques pour les décimales.

Vérifier ces mêmes transactions contre un RPC configuré explicitement, hors CI :

```powershell
$env:LIVE_RPC_URL='https://votre-rpc-ethereum-mainnet'
.venv/Scripts/python.exe -m scripts.verify_live
```

Ce script est en lecture seule et n’écrit pas en base. Il ne teste pas l’indexeur Etherscan. Pour renouveler le corpus, `scripts.capture_corpus` exige `CORPUS_RPC_URL` et accepte `CORPUS_BLOCK_NUMBER`. Il écrit les pièces de test, qui doivent être revues avec les attentes avant validation ; il n’alimente pas les dossiers de l’application.

## Développement et structure

Python 3.12 est la référence conteneurisée. `requirements.lock` et `apps/web/package-lock.json` figent les dépendances ; HTTPX est maintenant une dépendance d’exécution. Les types frontend sont générés depuis OpenAPI.

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

Sans `TEST_DATABASE_URL`, les tests PostgreSQL sont explicitement sautés. Pour les exécuter hors Compose, fournir une base PostgreSQL **dédiée vide** dont le nom contient `ariadne_test`, et `REDIS_URL` pour le contrôle de disponibilité. Le développement Vite relaie `/api` vers l’API locale sur le port 8000.

```text
apps/api/                   API, dépendances et OpenAPI
apps/web/                   React/TypeScript et types générés
src/connectors/             transport borné, JSON-RPC Ethereum, Etherscan V2
src/investigation/          domaine, normalisation pure, collecte et persistance
migrations/                 0001 fondations, 0002 bundles Ethereum
tests/fixtures/ethereum/    corpus public et attentes revues
tests/integration/          tests PostgreSQL et API, sans réseau externe
tests/e2e/                  parcours navigateur
docs/adr/                   décisions de conception
docs/releases/              bilans et vérifications par jalon
```

Les identités incluent la chaîne ; les montants sont des `int` Python, `NUMERIC(78,0)` PostgreSQL bornés à uint256, et des chaînes décimales dans l’API. Les observations conservent leurs pièces et métadonnées figées. Les opérations sont des regroupements de mouvements sourcés ; les labels et allocations ont des tables distinctes, sans moteur dans cette version.

Contrats : `/docs` et [OpenAPI versionné](docs/openapi.json). `POST /api/v1/cases/{id}/runs` accepte `max_transactions` et éventuellement `block_range`, avec `Idempotency-Key` obligatoire ; `GET /api/v1/runs/{id}/transactions` expose les bundles y compris les échecs. Les routes graphe, jobs, SSE, expansions, labels, annotations et exports ne sont pas implémentées.

[Décision V0.2.0](docs/adr/0002-ethereum-borne-v0.2.0.md) · [Bilan V0.2.0 et limites de validation](docs/releases/v0.2.0.md) · [Bilan historique V0.1](docs/releases/v0.1.md).
