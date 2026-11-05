# ADR 0002 — Ethereum borné V0.2.0

Date : 5 novembre 2026. Statut : accepté pour la V0.2.0. Complète l’ADR 0001 sans modifier la migration V0.1.

## Acquisition et périmètre

Deux sources distinctes : Etherscan V2 identifie les transactions candidates d’une adresse par `txlist` et `tokentx` ; un RPC Ethereum mainnet fournit les transactions, reçus, logs et blocs qui fondent les observations. Les montants et noms de tokens annoncés par l’indexeur ne sont pas des preuves de mouvement. Les deux flux sont nécessaires pour ne pas ignorer un destinataire de tokens qui n’est ni initiateur ni destinataire de la transaction externe. Les endpoints officiels sont documentés séparément : [transactions normales](https://docs.etherscan.io/api-reference/endpoint/txlist) et [transferts ERC-20](https://docs.etherscan.io/api-reference/endpoint/tokentx).

Seul `eip155:1` est collecté. Le RPC est configuré par `ETHEREUM_RPC_URL`, l’indexeur par `ETHERSCAN_API_KEY`, exclusivement côté serveur. Sans RPC, le run est `unsupported` ; sans clé d’indexeur, une transaction explicite reste collectable et une adresse est indisponible. Aucun fournisseur public ni fixture n’est substitué automatiquement à un fournisseur absent.

La V0.2 ne collecte que les transferts ETH de premier niveau réussis et les logs au format `Transfer(address,address,uint256)` à trois topics. Les événements de zéro unité sont conservés ; les événements ERC-721 à quatre topics sont exclus. Une émission au format attendu ne prouve pas la conformité complète d’un contrat ni une valeur économique. Les décimales restent facultatives, conformément à [ERC-20](https://eips.ethereum.org/EIPS/eip-20) ; elles sont demandées au hash du bloc, sans repli sur l’état courant. Une erreur ou une métadonnée non standard laisse `decimals=null` et préserve le montant brut.

## Cohérence et provenance

Le connecteur contrôle `eth_chainId`. Le normaliseur vérifie les hashes, hauteurs et indices de transaction entre transaction, reçu et bloc ; l’inclusion dans la liste ordonnée du bloc ; les positions uniques des logs et l’absence du marqueur `removed`. Le bloc est relu par numéro pour confirmer la canonicalité au moment de la collecte. Le statut d’un reçu échoué empêche toute observation de transfert effectif ; la transaction et le reçu restent consultables. Ce contrôle repose sur le fournisseur RPC, sans preuve cryptographique indépendante.

Les tags `safe` et `finalized` sont conservés séparément avec leurs hashes et hauteurs, selon l’[API JSON-RPC Ethereum](https://ethereum.org/developers/docs/apis/json-rpc/). Des tags absents ou contradictoires ne deviennent pas une finalité positive. Une inclusion non finalisée rend le run partiel. Le système ne surveille pas encore les réorganisations et ne recalcule pas les dérivations historiques.

La migration `0002` ajoute les bundles transaction/reçu/bloc, leurs associations aux runs et les métadonnées d’actif figées par observation. Les pièces JSON et leurs empreintes sont conservées, y compris les requêtes ayant échoué, sans URL secrète ni clé. La réutilisation d’un bundle rattache ses anciennes pièces au manifest du nouveau run ; une normalisation contradictoire est signalée plutôt qu’écrasée. Les métadonnées d’une collecte ne modifient pas rétroactivement les observations ou la démonstration.

## Bornes et complétude

La collecte est synchrone et limitée : 10 transactions par défaut, 20 au maximum, 200 mouvements, 100 appels, budget réseau de 45 secondes, 24 Mio reçus au total et 4 Mio par réponse. Une plage d’adresse comprend au maximum 10 000 blocs et doit être explicite. L’API conserve aussi les graines historiques avec période ISO ; leur collecte nécessite alors une plage de blocs explicite, et la couverture porte sur l’intersection déclarée. Les limites atteintes restent dans le run.

L’indexeur utilise des pages triées et pagine séparément les deux flux. Une page pleine ne prouve pas que l’historique est terminé. Au plafond de résultats, la plage est subdivisée ; si un seul bloc dépasse encore ce plafond, la troncature reste explicite. Le collecteur effectue au maximum 12 pages par graine et s’arrête aussi à ses autres budgets. Une panne après une page exploitable conserve les candidats déjà vérifiables et produit `partial`. Les curseurs conservés sont des éléments de diagnostic ; il n’existe pas d’API de reprise V0.3.

`complete_within_declared_scope` porte seulement sur les sources, plages, transactions et formats déclarés, jamais sur tous les mouvements de valeur d’une adresse. Les traces, frais, retraits de consensus, NFT et protocoles composites sont explicitement hors périmètre. Une transaction inconnue, une source indisponible et un historique vide complet sont des résultats différents.

Une seule collecte s’exécute à la fois sur l’instance locale, protégée par verrou transactionnel PostgreSQL. La clé d’idempotence restitue le run existant et refuse une modification des paramètres. Il n’y a ni file, ni worker, ni garantie de reprise après arrêt du processus : une interruption avant commit peut annuler le run. Ces garanties attendent la V0.3.

## Validation

Le corpus public conservé concerne trois transactions du bloc Ethereum 26347604 : ETH, logs ERC-20 et échec. Les tests hors ligne rejouent ces réponses publiques, et des réponses synthétiques explicitement réservées aux tests exercent pagination, troncature, erreurs et budgets. Les scripts de capture et de vérification live exigent un endpoint explicite ; ils ne sont ni un fournisseur applicatif ni une dépendance de la CI.

La démo V0.1 reste synthétique, séparée des dossiers de collecte et en lecture seule. L’instance reste locale mono-utilisateur sans authentification. Aucun graphe, job durable, swap, bridge, attribution ou allocation n’est introduit.
