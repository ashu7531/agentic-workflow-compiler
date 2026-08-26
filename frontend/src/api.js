// Thin API client for the SOPilot backend.
// Override the backend URL at build time with VITE_API_URL (e.g. your Vercel backend).
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  health: () => fetch(`${BASE}/health`).then((r) => r.json()),
  compile: (sop_text, answers) => post('/compile', { sop_text, answers }),
  validate: (graph) => post('/validate', { graph }),
  run: (graph, entry, caseData) => post('/run', { graph, entry, case: caseData }),
  caseDefaults: () => fetch(`${BASE}/case-defaults`).then((r) => r.json()),
  tools: () => fetch(`${BASE}/tools`).then((r) => r.json()),
  samples: () => fetch(`${BASE}/samples`).then((r) => r.json()),
  library: () => fetch(`${BASE}/library`).then((r) => r.json()),
  libraryGet: (id) => fetch(`${BASE}/library/${id}`).then((r) => r.json()),
  save: (title, sop_text, graph) => post('/library', { title, sop_text, graph }),
  remove: (id) => fetch(`${BASE}/library/${id}`, { method: 'DELETE' }).then((r) => r.json()),
  handle: (case_text, entry, caseData, force_agent) =>
    post('/handle', { case_text, entry, case: caseData, force_agent }),
  agentRun: (case_text, entry, caseData, policy_text) =>
    post('/agent-run', { case_text, entry, case: caseData, policy_text }),
};
