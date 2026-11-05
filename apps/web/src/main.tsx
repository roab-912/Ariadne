import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { api, coverageLabel } from './api';
import type { Capabilities, Case, CaseCreate, CaseDetail, Operation, Run, Snapshot } from './api';
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
  const [selectedId, setSelectedId] = useState('');
  const [snapshot, setSnapshot] = useState<Snapshot>();
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const run = detail?.runs.find(item => item.id === runId);
  const selected = operations.find(item => item.id === selectedId);

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
    setDetail(undefined); setRunId(''); setOperations([]); setSnapshot(undefined); setError('');
    api<CaseDetail>(`/cases/${caseId}`, { signal: controller.signal })
      .then(value => { setDetail(value); setRunId(value.runs[0]?.id ?? ''); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [caseId]);

  useEffect(() => {
    if (!runId) return;
    const controller = new AbortController();
    setOperations([]); setSnapshot(undefined); setSelectedId('');
    api<Operation[]>(`/runs/${runId}/operations`, { signal: controller.signal })
      .then(items => { setOperations(items); setSelectedId(items[0]?.id ?? ''); })
      .catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [runId]);

  useEffect(() => {
    setSnapshot(undefined);
    const snapshotId = selected?.movements[0]?.observation.snapshot_id;
    if (!snapshotId) return;
    const controller = new AbortController();
    api<Snapshot>(`/snapshots/${snapshotId}`, { signal: controller.signal })
      .then(setSnapshot).catch(err => { if (!controller.signal.aborted) setError(err.message); });
    return () => controller.abort();
  }, [selectedId, operations]);

  async function createCase(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError('');
    const form = new FormData(event.currentTarget);
    const body: CaseCreate = {
      title: String(form.get('title')), description: '',
      seeds: [{ chain_id: String(form.get('chain')), kind: 'transaction', reference: String(form.get('hash')), window: {} }],
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
      const value = await api<Run>(`/cases/${caseId}/runs`, { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() } });
      setDetail(current => current ? { ...current, runs: [...current.runs, value] } : current); setRunId(value.id);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <div className="shell">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Ariadne, accueil"><span className="brand-mark">A</span> ARIADNE</a>
      <p className="eyebrow">Investigation blockchain</p>
      <div className="side-heading"><h2>Dossiers locaux</h2><span>V0.1</span></div>
      <nav aria-label="Dossiers">{cases.map(item => <button className={`case-link ${item.id === caseId ? 'active' : ''}`} key={item.id} onClick={() => setCaseId(item.id)}>
        <span>{item.is_demo ? 'DÉMONSTRATION' : 'DOSSIER LOCAL'}</span>{item.title.replace('Démonstration · ', '')}
      </button>)}</nav>
      <button className="secondary new-case" onClick={() => setShowForm(value => !value)} aria-expanded={showForm}>+ Nouveau dossier</button>
      <div className="provider-list"><h2>Couverture réelle</h2>{capabilities?.providers.map(provider => <div className="provider" key={provider.chain_id}><code>{provider.chain_id}</code><span>Non configuré</span></div>)}
        <p>Aucun réseau collecté.<br />Aucun appel fournisseur.</p>
      </div>
      <p className="local-note">Environnement local sans compte.<br />Dossiers conservés sur cette instance.</p>
    </aside>
    <main>
      <header className="topbar"><span>Espace d’investigation <span aria-hidden="true">/</span> Fondations</span><span className="version">V0.1 · local</span></header>
      <div className="workspace">
        <div className="demo-banner" role="note"><strong>Démonstration</strong><span>Le scénario fourni est entièrement synthétique. Il ne décrit aucune transaction réelle.</span></div>
        {error && <div className="error" role="alert">{error} <button onClick={() => window.location.reload()}>Recharger</button></div>}
        {showForm && <form className="panel create-form" onSubmit={createCase}><h2>Nouveau dossier local</h2><p>Enregistre une graine uniquement. La collecte et l’analyse ne sont pas disponibles en V0.1.</p>
          <label>Titre<input name="title" required maxLength={200} /></label>
          <label>Réseau<select name="chain"><option value="eip155:1">Ethereum · eip155:1</option><option value="eip155:8453">Base · eip155:8453</option><option value="eip155:42161">Arbitrum One · eip155:42161</option></select></label>
          <label>Hash de transaction<input name="hash" required pattern="0x[0-9a-fA-F]{64}" placeholder="0x… (64 caractères hexadécimaux)" /></label>
          <button disabled={busy} className="primary">Enregistrer le dossier</button>
        </form>}
        {loading && <p role="status">Chargement des dossiers…</p>}
        {!loading && !caseId && !error && <p>Aucun dossier. Créez une graine locale ou chargez le jeu de démonstration.</p>}
        {detail && <>
          <div className="page-heading"><div><p className="eyebrow">Dossier / {detail.is_demo ? 'Démonstration' : 'Local'}</p><h1>{detail.title.replace('Démonstration · ', '')}</h1><p>{detail.description || 'Graine enregistrée. Aucune donnée collectée.'}</p></div><span className="badge">{detail.is_demo ? 'Données synthétiques' : 'Sans collecte'}</span></div>
          <section className="panel run-toolbar" aria-label="Exécution"><label>Snapshot du run<select value={runId} onChange={event => setRunId(event.target.value)} disabled={!detail.runs.length}>{!detail.runs.length && <option value="">Aucun run</option>}{detail.runs.map(item => <option value={item.id} key={item.id}>{item.id.slice(0, 8)} · {item.state}</option>)}</select></label>
            {run && <span className="badge warning">{coverageLabel(run.coverage_status)}</span>}
            {!detail.is_demo && <button className="secondary" disabled={busy} onClick={captureRun}>Figer un run sans analyse</button>}
          </section>
          <div className="layers" aria-label="Séparation des couches"><div><span>01 / Observations</span><strong>{operations.reduce((count, item) => count + item.movements.length, 0)} mouvements affichés</strong><p>Quantités brutes et pièces sources</p></div><div><span>02 / Attribution</span><strong>Aucune assertion</strong><p>Aucune identité ni contrôle déduit</p></div><div><span>03 / Allocation analytique</span><strong>Aucune allocation</strong><p>Politique : {run?.allocation_policy ?? 'none'}</p></div></div>
          <div className="investigation-grid">
            <section className="panel movements"><div className="panel-heading"><h2>Opérations & mouvements</h2><span className="muted">Vue tabulaire</span></div>
              <p className="table-hint">Sélectionnez une opération pour examiner sa preuve.</p>
              <div className="table-scroll"><table><thead><tr><th>Opération / bloc</th><th>Parcours observé</th><th>Montant exact</th></tr></thead><tbody>{operations.map(operation => <React.Fragment key={operation.id}>{operation.movements.map(({ observation: item, role }) => <tr key={`${item.id}-${role}`} className={selectedId === operation.id ? 'selected' : ''}>
                <td><button className="operation-button" aria-pressed={selectedId === operation.id} onClick={() => setSelectedId(operation.id)}>Transfert · {item.block_number}</button><small>{item.chain_id} · {item.origin}</small></td>
                <td><code title={item.source_address_id}>{short(item.source_address_id)}</code><span className="direction">vers</span><code title={item.target_address_id}>{short(item.target_address_id)}</code></td>
                <td><strong className="amount">{formatAmount(item.amount_raw, item.asset.decimals)} {item.asset.symbol ?? 'Actif inconnu'}</strong><small className="raw">{item.amount_raw} unités brutes</small></td>
              </tr>)}</React.Fragment>)}</tbody></table></div>
              {run && operations.length === 0 && <p className="empty">Aucune observation. Ce run n’exécute ni collecte ni analyse.</p>}
            </section>
            <aside className="panel evidence" aria-label="Détails et preuves"><div className="panel-heading"><h2>Pièce & provenance</h2><span className="badge">{selected?.is_demo ? 'Démonstration' : 'Aucune sélection'}</span></div>
              {selected ? <><dl><dt>Opération</dt><dd><code>{selected.id}</code></dd><dt>Règle de regroupement</dt><dd>{selected.decoder_version}</dd><dt>État de décodage</dt><dd>{selected.decoding_status} · aucun décodeur réel</dd><dt>Source</dt><dd>{snapshot?.source ?? 'Chargement…'}</dd><dt>Finalité / canonicalité</dt><dd>Inconnues · données synthétiques</dd></dl>
                <details><summary>Références des preuves</summary><pre>{json(selected.evidence_refs)}</pre></details>
                {snapshot && <><details><summary>Contenu de la pièce synthétique</summary><pre>{json(snapshot.content)}</pre></details><dl><dt>SHA-256 du contenu conservé</dt><dd><code className="hash">{snapshot.sha256}</code></dd></dl><p className="muted">Cette empreinte contrôle l’intégrité du fixture, sans attester une réalité sur chaîne.</p></>}
              </> : <p className="empty">Sélectionnez une opération.</p>}
            </aside>
          </div>
          {run && <section className="panel run-details"><div className="panel-heading"><h2>Périmètre figé du run</h2><span className="muted">{run.id}</span></div><p>Limites de couverture</p><ul>{(run.coverage.limits as string[] | undefined)?.map(limit => <li key={limit}>{limit}</li>)}</ul><p>Causes d’arrêt : <code>{run.stop_reasons.join(' · ')}</code></p><details><summary>Graines, paramètres, bornes, versions et manifest</summary><pre>{json(run)}</pre></details></section>}
          <details className="panel seed-details"><summary>Graines du dossier</summary><pre>{json(detail.seeds)}</pre></details>
        </>}
        <footer>Ariadne V0.1 · Fondations uniquement · Aucune collecte, attribution ou continuation inter-chaînes</footer>
      </div>
    </main>
  </div>;
}

createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>);
