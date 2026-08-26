import { useEffect, useState } from 'react';
import { api } from './api';
import GraphView from './GraphView.jsx';

// Branching-flow logo mark
function Logo() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="12" r="2.4" />
      <circle cx="19" cy="6" r="2.4" />
      <circle cx="19" cy="18" r="2.4" />
      <path d="M7.2 10.8 16.8 7.2M7.2 13.2 16.8 16.8" />
    </svg>
  );
}

export default function App() {
  const [sopText, setSopText] = useState('');
  const [graph, setGraph] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [validation, setValidation] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [runResult, setRunResult] = useState(null);
  const [entry, setEntry] = useState({}); // dynamic run inputs from graph.entry_fields
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [samples, setSamples] = useState([]);
  const [libraryItems, setLibraryItems] = useState([]);
  const [caseData, setCaseData] = useState({});
  const [toolFields, setToolFields] = useState({}); // toolName -> [case fields it reads]
  const [saveTitle, setSaveTitle] = useState('');
  const [saveMsg, setSaveMsg] = useState('');
  const [agentMode, setAgentMode] = useState(false);
  const [agentResult, setAgentResult] = useState(null);
  const [handleText, setHandleText] = useState('An order is delayed and the customer is upset, please handle it.');
  const [handleId, setHandleId] = useState('CASE-123');
  const [routeInfo, setRouteInfo] = useState(null);

  useEffect(() => {
    api.health().catch(() => {});
    api.samples().then((r) => {
      setSamples(r.samples || []);
      if (r.samples?.[0]) setSopText(r.samples[0].sop_text);
    }).catch(() => {});
    api.caseDefaults().then((r) => setCaseData(r.defaults || {})).catch(() => {});
    api.tools().then((r) => {
      const m = {};
      (r.tools || []).forEach((t) => { m[t.name] = t.case_fields || []; });
      setToolFields(m);
    }).catch(() => {});
    refreshLibrary();
  }, []);

  // Only the case fields the CURRENT workflow actually uses (from its fetch tools).
  const relevantFields = graph
    ? Array.from(new Set(
        graph.nodes
          .filter((n) => n.type === 'fetch' && n.tool)
          .flatMap((n) => toolFields[n.tool] || [])
      ))
    : [];
  const fieldsToShow = relevantFields.length ? relevantFields : Object.keys(caseData);

  const nodeLabel = (id) => graph?.nodes.find((n) => n.id === id)?.label || id;

  // Suggest a sample value that fits the actual field name.
  // e.g. wbn -> WBN123, content_id -> CON-123, alert_id -> ALE-123, subscription_id -> SUB-123
  const sampleFor = (f) => {
    if (/wbn|waybill/i.test(f)) return 'WBN123';
    const base = f.replace(/_?id$/i, '').replace(/[^a-z0-9]/gi, '');
    const prefix = (base.slice(0, 3) || 'ref').toUpperCase();
    return `${prefix}-123`;
  };

  // When a workflow loads, initialize its run inputs from entry_fields
  // (keeping any values the user already typed for the same field name).
  useEffect(() => {
    if (!graph) { setEntry({}); return; }
    const fields = graph.entry_fields || [];
    setEntry((prev) => {
      const next = {};
      fields.forEach((f) => { next[f] = prev[f] ?? sampleFor(f); });
      return next;
    });
    setSaveTitle(graph.sop_title || 'Untitled workflow');
    setSaveMsg('');
  }, [graph]);

  function setCaseField(key, raw) {
    let val = raw;
    if (typeof caseData[key] === 'boolean') val = raw === 'true' || raw === true;
    else if (typeof caseData[key] === 'number') val = raw === '' ? 0 : Number(raw);
    setCaseData({ ...caseData, [key]: val });
  }

  function refreshLibrary() {
    api.library().then((r) => setLibraryItems(r.items || [])).catch(() => {});
  }

  async function handleCompile(useAnswers) {
    setBusy(true); setError(''); setRunResult(null); setSelectedId(null);
    try {
      const res = await api.compile(sopText, useAnswers ? answers : null);
      if (res.type === 'clarification') {
        setQuestions(res.needs_clarification || []);
        setGraph(null);
      } else {
        setGraph(res.graph);
        setValidation(res.validation || []);
        setQuestions([]);
        setAnswers({});
      }
    } catch (e) { setError(String(e)); }
    setBusy(false);
  }

  async function handleRun() {
    if (!graph) return;
    setBusy(true); setError(''); setAgentResult(null);
    try {
      if (agentMode) {
        // Force the tool-using agent, using the SOP text as its policy guidance.
        const res = await api.agentRun(sopText, entry, caseData, sopText);
        setAgentResult(res);
        setRunResult(null);
      } else {
        setRunResult(await api.run(graph, entry, caseData));
      }
    } catch (e) { setError(String(e)); }
    setBusy(false);
  }

  async function applyNodeEdit(nodeId, patch) {
    const nextNodes = graph.nodes.map((n) => (n.id === nodeId ? { ...n, ...patch } : n));
    const nextGraph = { ...graph, nodes: nextNodes };
    setGraph(nextGraph);
    setRunResult(null);
    try { const v = await api.validate(nextGraph); setValidation(v.problems || []); }
    catch { /* ignore */ }
  }

  function loadSample(id) {
    const s = samples.find((x) => x.id === id);
    if (s) { setSopText(s.sop_text); setGraph(null); setRunResult(null); setQuestions([]); }
  }

  async function loadSaved(id) {
    setBusy(true); setError('');
    try {
      const item = await api.libraryGet(id);
      if (item.graph) {
        setGraph(item.graph);
        setSopText(item.sop_text || '');
        setRunResult(null); setSelectedId(null); setQuestions([]);
        setValidation([]);
      }
    } catch (e) { setError(String(e)); }
    setBusy(false);
  }

  async function autoHandle() {
    setBusy(true); setError(''); setRouteInfo(null); setAgentResult(null); setRunResult(null);
    // Fill the id under all common entry-field names so whatever the matched
    // workflow expects is populated.
    const entryAll = {
      wbn: handleId, content_id: handleId, alert_id: handleId,
      subscription_id: handleId, order_id: handleId, user_id: handleId,
    };
    try {
      const res = await api.handle(handleText, entryAll, caseData, false);
      setRouteInfo({ route: res.route, reason: res.reason, title: res.matched_title });
      if (res.route === 'workflow') {
        setGraph(res.graph);
        setRunResult(res.run);
        setAgentResult(null);
      } else {
        setAgentResult(res.agent);
        setRunResult(null);
      }
    } catch (e) { setError(String(e)); }
    setBusy(false);
  }

  async function deleteSaved(id) {
    try { await api.remove(id); refreshLibrary(); }
    catch (e) { setError(String(e)); }
  }

  async function saveToLibrary() {
    if (!graph) return;
    const title = (saveTitle || '').trim() || 'Untitled workflow';
    setSaveMsg('Saving…'); setError('');
    try {
      const res = await api.save(title, sopText, graph);
      if (res && res.error) { setError(res.error); setSaveMsg(''); return; }
      setSaveMsg('Saved ✓');
      refreshLibrary();
    } catch (e) { setError(String(e)); setSaveMsg(''); }
  }

  const selectedNode = graph?.nodes.find((n) => n.id === selectedId);

  return (
    <div className="app">
      <header className="topbar">
        <div className="logo"><Logo /></div>
        <div className="brand-block">
          <div className="brand">Cascade</div>
          <div className="tagline">Compile plain-English procedures into runnable, auditable workflows</div>
        </div>
      </header>

      <div className="layout">
        {/* LEFT */}
        <aside className="left">
          <section className="card">
            <h3>📝 Add / edit a procedure</h3>
            <p className="muted-note" style={{ marginTop: 0 }}>
              Write ANY procedure in plain English below, or start from an example.
            </p>
            <label>Examples to try (optional)</label>
            <select className="select" value="" onChange={(e) => e.target.value && loadSample(e.target.value)}>
              <option value="">— start from an example —</option>
              {samples.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
            </select>
            <label style={{ marginTop: 12 }}>Your procedure</label>
            <textarea value={sopText} onChange={(e) => setSopText(e.target.value)} rows={7}
              placeholder="e.g. When a payment fails twice, pause the subscription and email the customer…" />
            <button className="primary" disabled={busy} onClick={() => handleCompile(false)}>
              {busy ? 'Compiling…' : '⚙ Compile to workflow'}
            </button>
          </section>

          <section className="card">
            <h3>💾 Saved workflows</h3>
            {libraryItems.length === 0 ? (
              <div className="muted-note">None yet — compile a procedure and click “Save to library”.</div>
            ) : (
              <ul className="lib-list">
                {libraryItems.map((it) => (
                  <li key={it.id}>
                    <span>{it.title}</span>
                    <span className="lib-actions">
                      <button className="mini" onClick={() => loadSaved(it.id)}>Load</button>
                      <button className="mini danger" title="Delete"
                        onClick={() => deleteSaved(it.id)}>✕</button>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card">
            <h3>🧭 Auto-handle a case (router)</h3>
            <p className="muted-note" style={{ marginTop: 0 }}>
              Type an incoming case. The router searches your saved workflows — if one
              matches it runs deterministically; if not, the agent handles it.
            </p>
            <label>Incoming case</label>
            <textarea value={handleText} onChange={(e) => setHandleText(e.target.value)} rows={3} />
            <label style={{ marginTop: 8 }}>Case id</label>
            <input value={handleId} onChange={(e) => setHandleId(e.target.value)} />
            <button className="primary" disabled={busy} onClick={autoHandle}>🧭 Route &amp; handle</button>
            {routeInfo && (
              <div className={`route-badge ${routeInfo.route}`}>
                {routeInfo.route === 'workflow' ? '🧩 Routed to WORKFLOW' : '🤖 Routed to AGENT'}
                <div className="route-reason">{routeInfo.reason}</div>
              </div>
            )}
          </section>

          {questions.length > 0 && (
            <section className="card clarify">
              <h4>🤔 A few details needed</h4>
              {questions.map((q) => (
                <div key={q} className="qa">
                  <label>{q}</label>
                  <input value={answers[q] || ''}
                    onChange={(e) => setAnswers({ ...answers, [q]: e.target.value })} />
                </div>
              ))}
              <button className="primary" disabled={busy} onClick={() => handleCompile(true)}>
                Submit &amp; compile
              </button>
            </section>
          )}

          {graph && (
            <section className="card">
              <h3>▶ Run a case</h3>
              {(graph.entry_fields || []).length > 0 ? (
                (graph.entry_fields || []).map((f) => (
                  <div key={f}>
                    <label>{f}</label>
                    <input value={entry[f] ?? ''}
                      onChange={(e) => setEntry({ ...entry, [f]: e.target.value })} />
                  </div>
                ))
              ) : (
                <div className="muted-note">This workflow takes no input.</div>
              )}

              <label style={{ marginTop: 12 }}>Case facts for this workflow (drive the decisions)</label>
              <div className="case-grid">
                {fieldsToShow.map((k) => {
                  const v = caseData[k];
                  return (
                    <div key={k} className="case-field">
                      <span>{k}</span>
                      {typeof v === 'boolean' ? (
                        <select value={String(v)} onChange={(e) => setCaseField(k, e.target.value)}>
                          <option value="true">true</option>
                          <option value="false">false</option>
                        </select>
                      ) : (
                        <input type={typeof v === 'number' ? 'number' : 'text'} value={v ?? ''}
                          onChange={(e) => setCaseField(k, e.target.value)} />
                      )}
                    </div>
                  );
                })}
              </div>

              <label className="agent-toggle" style={{ marginTop: 12 }}>
                <input type="checkbox" checked={agentMode}
                  onChange={(e) => setAgentMode(e.target.checked)} />
                <span>🤖 Agent mode <small>(let an AI agent handle it with tools, instead of the fixed workflow)</small></span>
              </label>
              <button className={agentMode ? 'agent-btn' : 'run'} disabled={busy} onClick={handleRun}>
                {agentMode ? '🤖 Run with agent' : 'Run workflow'}
              </button>

              <label style={{ marginTop: 12 }}>Save this workflow as</label>
              <div className="save-row">
                <input value={saveTitle} onChange={(e) => setSaveTitle(e.target.value)}
                  placeholder="Workflow name" />
                <button className="mini" onClick={saveToLibrary}>💾 Save</button>
              </div>
              {saveMsg && <div className="save-msg">{saveMsg}</div>}
              {validation.length > 0 && (
                <div className="warn">
                  <b>⚠ Validation issues</b>
                  <ul>{validation.map((p) => <li key={p}>{p}</li>)}</ul>
                </div>
              )}
            </section>
          )}

          {error && <div className="warn">{error}</div>}
        </aside>

        {/* CENTER */}
        <main className="center">
          {graph ? (
            <GraphView graph={graph} runResult={runResult} selectedId={selectedId}
              onSelectNode={setSelectedId} />
          ) : (
            <div className="empty">
              <div className="empty__icon"><Logo /></div>
              <div className="empty__title">Your workflow appears here</div>
              <div className="empty__sub">Pick a sample or describe a procedure, then hit “Compile”.</div>
            </div>
          )}
        </main>

        {/* RIGHT */}
        <aside className="right">
          {selectedNode ? (
            <section className="card" key={selectedNode.id}>
              <h3>✏️ Edit node</h3>
              <div className="pill">{selectedNode.type} · {selectedNode.id}</div>
              {selectedNode.type === 'decision' ? (
                <>
                  <label>Condition</label>
                  <textarea key={`cond-${selectedNode.id}`} defaultValue={selectedNode.condition} rows={3}
                    onBlur={(e) => applyNodeEdit(selectedNode.id, { condition: e.target.value })} />
                </>
              ) : (
                <>
                  <label>Tool inputs (JSON)</label>
                  <textarea key={`inp-${selectedNode.id}`} defaultValue={JSON.stringify(selectedNode.inputs, null, 2)} rows={5}
                    onBlur={(e) => {
                      try { applyNodeEdit(selectedNode.id, { inputs: JSON.parse(e.target.value) }); }
                      catch { setError('inputs must be valid JSON'); }
                    }} />
                </>
              )}
              <p className="hint">Edit, then click away to apply (auto re-validates).</p>
            </section>
          ) : graph && !runResult ? (
            <section className="card hint-card">
              <p>💡 Click a node to edit it · drag nodes to rearrange · then run a case.</p>
            </section>
          ) : null}

          {runResult && (
            <section className="card">
              <h3>📜 Execution trace</h3>
              {runResult.action_log?.length > 0 && (
                <div className="actions">
                  {runResult.action_log.map((a, i) => <div key={i}>{a}</div>)}
                </div>
              )}
              <ol className="trace">
                {runResult.trace?.map((s) => (
                  <li key={s.order} className={`step ${s.status}`}>
                    <span className="step__dot" />
                    <div>
                      <b>{nodeLabel(s.node)}</b> <span className="step__type">{s.type}</span>
                      <span className={`step__status ${s.status}`}>{s.status}</span>
                      {s.tool && <div className="why">🔧 {s.tool}</div>}
                      {s.type === 'decision' && s.status === 'ran' && (
                        <div className="why">→ {String(s.result)} · chose “{s.chose}”</div>
                      )}
                      {s.reason && <div className="why">{s.reason}</div>}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}

          {agentResult && (
            <section className="card">
              <h3>🤖 Agent run <span className="pill">{agentResult.mode} mode</span></h3>
              <p className="hint" style={{ marginTop: 0 }}>
                The agent decided each step itself, calling tools in a loop.
              </p>
              <ol className="agent-steps">
                {agentResult.steps?.map((s, i) => (
                  <li key={i} className="agent-step">
                    {s.thought && <div className="agent-thought">🤔 {s.thought}</div>}
                    {s.tool && (
                      <div className="agent-act">
                        🔧 <b>{s.tool}</b>({Object.keys(s.args || {}).length ? JSON.stringify(s.args) : ''})
                        <div className="agent-obs">↳ {JSON.stringify(s.observation)}</div>
                      </div>
                    )}
                    {s.final && <div className="agent-final">✅ {s.final}</div>}
                  </li>
                ))}
              </ol>
              <div className="agent-answer">✅ {agentResult.final}</div>
              {agentResult.action_log?.length > 0 && (
                <div className="actions" style={{ marginTop: 10 }}>
                  {agentResult.action_log.map((a, i) => <div key={i}>{a}</div>)}
                </div>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
