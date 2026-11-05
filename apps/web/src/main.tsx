import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, coverageLabel } from './api';
import type { Bundle, Capabilities, Case, CaseCreate, CaseDetail, Operation, Run, Snapshot } from './api';
import { formatAmount } from './amount.mjs';
import './style.css';

const short = (value: string) => value.length > 25 ? `${value.slice(0, 14)}…${value.slice(-6)}` : value;
const json = (value: unknown) => JSON.stringify(value, null, 2);

function App() {
  const [cases, setCases] = useState<Case[]>([]);
  const [capabilities, setCapabilities] = useState<Capabilities>();
  const [caseId, setCaseId] = useState('');
  const [detail, setDetail] = useState<CaseDetail>();
  const [runId, setRunId] = useState('');
  const [operations, setOperations] = useState<Operation[]>([]);
  const [bundles, setBundles] = useState<Bundle[]>([]);
  const [moreOperations, setMoreOperations] = useState(false);
  const [bundleId, setBundleId] = useState('');
  const [proofId, setProofId] = useState('');
  const [selectedId, setSelectedId] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [seedKind, setSeedKind] = useState<'transaction' | 'address'>('transaction');
  const [maxTransactions, setMaxTransactions] = useState(10);
  const collectionKey = useRef('');
  const run = detail?.runs.find(item => item.id === runId);
  const selected = operations.find(item => item.id === selectedId);
  const selectedBundle = bundles.find(item => item.id === bundleId);
  const selectedObservation = selected?.movements[0]?.observation;
  const proofSnapshotId = proofId || selectedObservation?.snapshot_id || selectedBundle?.snapshot_id;

  useEffect(() => {
    let active = true;
    Promise.all([api<Case[]>('/cases'), api<Capabilities>('/capabilities')])
      .then(([items, caps]) => { if (active) { setCases(items); setCapabilities(caps); setCaseId(items[0]?.id ?? ''); } })
      .catch(err => { if (active) setError(String(err.message)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!caseId) return;
    const controller = new AbortController();
    setDetail(undefined); setRunId(''); setOperations([]); setBundles([]); setSnapshot(undefined); setError('');
    collectionKey.current = '';
    api<CaseDetail>(`/cases/${caseId}`, { signal: controller.signal })
      .then(value => { setDetail(value); setRunId(value.runs.at(-1)?.id ?? ''); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [caseId]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    setOperations([]); setBundles([]); setSnapshot(undefined); setSelectedId(''); setBundleId(''); setProofId('');
    Promise.all([
      api<Operation[]>(`/runs/${runId}/operations?limit=50`, { signal: controller.signal }),
      api<Bundle[]>(`/runs/${runId}/transactions`, { signal: controller.signal }),
    ])
      .then(([items, transactions]) => {
        setOperations(items); setMoreOperations(items.length === 50); setBundles(transactions);
        setSelectedId(items[0]?.id ?? '');
        if (!items.length) setBundleId(transactions[0]?.id ?? '');
      })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [runId]);

  useEffect(() => {
    setSnapshot(undefined);
    const snapshotId = proofSnapshotId;
    if (!snapshotId) return;
    const controller = new AbortController();
    api<Snapshot>(`/snapshots/${snapshotId}`, { signal: controller.signal })
      .then(setSnapshot).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [proofSnapshotId]);

  async function createCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget);
    const body: CaseCreate = {
      title: String(form.get('title')), description: '',
      seeds: [{ chain_id: String(form.get('chain')), kind: seedKind, reference: String(form.get('reference')),
        window: seedKind === 'address' ? { start_block: String(form.get('start')), end_block: String(form.get('end')) } : {} }],
    };
    try {
      const created = await api<Case>('/cases', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: json(body) });
      setCases(items => [...items, created]); setCaseId(created.id); setShowForm(false);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function captureRun() {
    setBusy(true); setError('');
    try {
      collectionKey.current ||= crypto.randomUUID();
      const value = await api<Run>(`/cases/${caseId}/runs`, { method: 'POST',
        headers: { 'Idempotency-Key': collectionKey.current, 'Content-Type': 'application/json' },
        body: json({ max_transactions: maxTransactions }),
      });
      setDetail(current => current ? { ...current, runs: [...current.runs, value] } : current); setRunId(value.id);
      collectionKey.current = '';
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  async function loadMoreOperations() {
    setBusy(true);
    try {
      const items = await api<Operation[]>(`/runs/${runId}/operations?limit=50&offset=${operations.length}`);
      setOperations(current => [...current, ...items]); setMoreOperations(items.length === 50);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Ariadne, accueil"><span className="brand-mark">A</span> ARIADNE</a>
      <p className="eyebrow">Investigation blockchain</p>
      <div className="side-heading"><h2>Dossiers locaux</h2><span>V0.2.0</span></div>
      <nav aria-label="Dossiers">{cases.map(item => <button disabled={busy} className={`case-link ${item.id === caseId ? 'active' : ''}`} key={item.id} onClick={() => setCaseId(item.id)}>
        <span>{item.is_demo ? 'DÉMONSTRATION' : 'DOSSIER LOCAL'}</span>{item.title.replace('Démonstration · ', '')}
      </button>)}</nav>
      <button className="secondary new-case" onClick={() => setShowForm(value => !value)} aria-expanded={showForm}>+ Nouveau dossier</button>
      <div className="provider-list"><h2>Fournisseurs configurés</h2>{capabilities?.providers.map(provider => <div className="provider" key={provider.chain_id}><code>{provider.chain_id}</code><span>{provider.transaction_bundle ? (provider.address_history ? 'RPC + indexeur' : 'RPC seul') : 'Indisponible'}</span></div>)}
        <p>Ethereum uniquement.<br />La disponibilité est vérifiée lors de la collecte.</p>
      </div>
      <p className="local-note">Environnement local sans compte.<br />Dossiers conservés sur cette instance.</p>
    </aside>
    <main>
      <header className="topbar"><span>Espace d’investigation <span aria-hidden="true">/</span> Ethereum</span><span className="version">V0.2.0 · local</span></header>
      <div className="workspace">
        {detail?.is_demo && <div className="demo-banner" role="note"><strong>Démonstration</strong><span>Le scénario fourni est entièrement synthétique. Il ne décrit aucune transaction réelle.</span></div>}
        {detail && !detail.is_demo && <div className="collection-banner" role="note"><strong>Collecte Ethereum</strong><span>Transferts ETH de premier niveau et événements Transfer au format ERC-20. Aucune attribution ni allocation.</span></div>}
        {error && <div className="error" role="alert">{error} <button onClick={() => window.location.reload()}>Recharger</button></div>}
        {showForm && <form className="panel create-form" onSubmit={createCase}><h2>Nouveau dossier local</h2><p>Enregistrez une transaction ou une adresse, puis lancez une collecte bornée avec les fournisseurs configurés côté serveur.</p>
          <label>Titre<input name="title" required maxLength={200} /></label>
          <label>Réseau<select name="chain"><option value="eip155:1">Ethereum · eip155:1</option><option value="eip155:8453">Base · eip155:8453</option><option value="eip155:42161">Arbitrum One · eip155:42161</option></select></label>
          <label>Type de graine<select value={seedKind} onChange={event => setSeedKind(event.target.value as 'transaction' | 'address')}><option value="transaction">Transaction</option><option value="address">Adresse et plage de blocs</option></select></label>
          <label>{seedKind === 'transaction' ? 'Hash de transaction' : 'Adresse'}<input key={seedKind} name="reference" required pattern={seedKind === 'transaction' ? '0x[0-9a-fA-F]{64}' : '0x[0-9a-fA-F]{40}'} placeholder={seedKind === 'transaction' ? '0x… (64 caractères hexadécimaux)' : '0x… (40 caractères hexadécimaux)'} /></label>
          {seedKind === 'address' && <div className="block-range"><label>Bloc de début<input name="start" required inputMode="numeric" pattern="0|[1-9][0-9]*" /></label><label>Bloc de fin<input name="end" required inputMode="numeric" pattern="0|[1-9][0-9]*" /></label><p>10 000 blocs au maximum. Un RPC et une clé Etherscan V2 sont nécessaires.</p></div>}
          <button disabled={busy} className="primary">Enregistrer le dossier</button>
        </form>}
        {loading && <p role="status">Chargement des dossiers…</p>}
        {!loading && !caseId && !error && <p>Aucun dossier. Créez une graine locale ou chargez le jeu de démonstration.</p>}
        {detail && <>
          <div className="page-heading"><div><p className="eyebrow">Dossier / {detail.is_demo ? 'Démonstration' : 'Local'}</p><h1>{detail.title.replace('Démonstration · ', '')}</h1><p>{detail.description || 'Graine enregistrée. Les résultats ci-dessous correspondent au run sélectionné.'}</p></div><span className="badge">{detail.is_demo ? 'Données synthétiques' : 'Dossier de collecte'}</span></div>
          <section className="panel run-toolbar" aria-label="Exécution"><label>Snapshot du run<select value={runId} onChange={event => setRunId(event.target.value)} disabled={busy || !detail.runs.length}>{!detail.runs.length && <option value="">Aucun run</option>}{detail.runs.map(item => <option value={item.id} key={item.id}>{item.id.slice(0, 8)} · {item.state}</option>)}</select></label>
            {run && <span className="badge warning">{coverageLabel(run.coverage_status)}</span>}
            {!detail.is_demo && <><label>Transactions max.<input className="count-input" type="number" min={1} max={20} value={maxTransactions} disabled={busy} onChange={event => { setMaxTransactions(Number(event.target.value)); collectionKey.current = ''; }} /></label><button className="primary" disabled={busy} onClick={captureRun}>{busy ? 'Collecte en cours…' : 'Collecter Ethereum'}</button></>}
          </section>
          {busy && <p role="status">Requête bornée en cours. Les résultats et limites seront enregistrés dans le run.</p>}
          {!detail.is_demo && run?.coverage_status === 'unsupported' && <p className="availability-note">Collecte indisponible pour ce run. Consultez les causes d’arrêt et la configuration des fournisseurs.</p>}
          <div className="layers" aria-label="Séparation des couches"><div><span>01 / Observations</span><strong>{operations.reduce((count, item) => count + item.movements.length, 0)} mouvements affichés</strong><p>Quantités brutes et pièces sources</p></div><div><span>02 / Attribution</span><strong>Aucune assertion</strong><p>Aucune identité ni contrôle déduit</p></div><div><span>03 / Allocation analytique</span><strong>Aucune allocation</strong><p>Politique : {run?.allocation_policy ?? 'none'}</p></div></div>
          <div className="investigation-grid">
            <section className="panel movements"><div className="panel-heading"><h2>Opérations & mouvements</h2><span className="muted">Vue tabulaire</span></div>
              <p className="table-hint">Sélectionnez une opération pour examiner sa preuve.</p>
              <div className="table-scroll" tabIndex={0} aria-label="Table des mouvements, défilement horizontal si nécessaire"><table><thead><tr><th>Opération / bloc</th><th>Parcours observé</th><th>Montant exact</th></tr></thead><tbody>{operations.map(operation => <React.Fragment key={operation.id}>{operation.movements.map(({ observation: item, role }) => <tr key={`${item.id}-${role}`} className={selectedId === operation.id ? 'selected' : ''}>
                <td><button className="operation-button" aria-pressed={selectedId === operation.id} onClick={() => { setSelectedId(operation.id); setBundleId(''); setProofId(''); }}>Transfert · {item.block_number}</button><small>{item.chain_id} · {item.origin === 'log' ? 'Événement ERC-20' : item.origin}</small></td>
                <td><code title={item.source_address_id}>{short(item.source_address_id)}</code><span className="direction">vers</span><code title={item.target_address_id}>{short(item.target_address_id)}</code></td>
                <td><strong className="amount">{formatAmount(item.amount_raw, item.asset.decimals)} {item.asset.symbol ?? ''}</strong><small className="raw">{item.amount_raw} unités brutes</small><small title={item.asset_id}>{short(item.asset_id)}</small></td>
              </tr>)}</React.Fragment>)}</tbody></table></div>
              {moreOperations && <button className="secondary more-button" disabled={busy} onClick={loadMoreOperations}>Afficher les opérations suivantes</button>}
              {run && operations.length === 0 && <p className="empty">Aucun mouvement normalisé pour ce run. Consultez les transactions conservées et les limites de couverture.</p>}
            </section>
            <aside className="panel evidence" aria-label="Détails et preuves"><div className="panel-heading"><h2>Pièce & provenance</h2><span className="badge">{snapshot?.is_demo ? 'Démonstration' : snapshot ? 'Pièce de collecte' : 'Aucune sélection'}</span></div>
              {!!run?.manifest.length && <label className="proof-picker">Pièce conservée<select value={proofSnapshotId ?? ''} onChange={event => { setProofId(event.target.value); setSelectedId(''); setBundleId(''); }}><option value="">Choisir une pièce</option>{run.manifest.map((piece: { snapshot_id?: string }) => <option value={piece.snapshot_id} key={piece.snapshot_id}>{piece.snapshot_id}</option>)}</select></label>}
              {selected && <><dl><dt>Opération</dt><dd><code>{selected.id}</code></dd><dt>Règle de normalisation</dt><dd>{selected.decoder_version}</dd><dt>État de décodage</dt><dd>{selected.decoding_status}</dd><dt>Actif et métadonnées</dt><dd><code>{selectedObservation?.asset_id}</code><br />{selectedObservation?.asset.metadata_source}</dd><dt>Finalité / canonicalité à la collecte</dt><dd>{selected.is_demo ? 'Inconnues · données synthétiques' : `${selectedObservation?.finality.status ?? 'unknown'} / ${selectedObservation?.canonicality}`}</dd></dl>
                <details><summary>Références des preuves</summary><pre>{json(selected.evidence_refs)}</pre></details>
              </>}
              {selectedBundle && <dl><dt>Transaction</dt><dd><code>{selectedBundle.tx_hash}</code></dd><dt>Résultat du reçu</dt><dd>{selectedBundle.transaction_status === 0 ? 'Échouée · aucun transfert effectif' : 'Réussie'}</dd></dl>}
              {snapshot ? <><dl><dt>Source</dt><dd>{snapshot.source}</dd><dt>Récupération</dt><dd>{snapshot.retrieved_at}</dd></dl><details><summary>{snapshot.is_demo ? 'Contenu de la pièce synthétique' : 'Contenu de la pièce conservée'}</summary><pre>{json(snapshot.content)}</pre></details><dl><dt>SHA-256 du contenu conservé</dt><dd><code className="hash">{snapshot.sha256}</code></dd></dl><p className="muted">L’empreinte contrôle l’intégrité de la pièce conservée ; elle ne prouve pas sa véracité initiale.</p></> : <p className="empty">Sélectionnez une opération, une transaction ou une pièce du manifest.</p>}
            </aside>
          </div>
          {!!bundles.length && <section className="panel transactions"><div className="panel-heading"><h2>Transactions conservées</h2><span className="muted">Reçus, logs et blocs</span></div>{bundles.map(item => <div className="transaction-row" key={item.id}><button className="operation-button" onClick={() => { setBundleId(item.id); setSelectedId(''); setProofId(''); }}>{short(item.tx_hash)}</button><span>Bloc {item.block_number}</span><span>{item.transaction_status === 0 ? 'Échouée · aucun transfert effectif' : 'Réussie'}</span></div>)}</section>}
          {run && <section className="panel run-details"><div className="panel-heading"><h2>Périmètre figé du run</h2><span className="muted">{run.id}</span></div><p>Limites de couverture</p><ul>{(run.coverage.limits as string[] | undefined)?.map(limit => <li key={limit}>{limit}</li>)}</ul><p>Causes d’arrêt : <code>{run.stop_reasons.join(' · ')}</code></p><details><summary>Graines, paramètres, bornes, versions et manifest</summary><pre>{json(run)}</pre></details></section>}
          <details className="panel seed-details"><summary>Graines du dossier</summary><pre>{json(detail.seeds)}</pre></details>
        </>}
        <footer>Ariadne V0.2.0 · Ethereum borné · Aucune attribution, allocation ou continuation inter-chaînes</footer>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
