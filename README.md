# Cascade — Natural-Language Procedures → Executable, Auditable Workflows

> Turn a plain-English Standard Operating Procedure (SOP) into a runnable, auditable
> decision workflow — no engineer required. With an agentic fallback for the messy cases.

Cascade is an **agentic AI** tool that reads a procedure written in ordinary English
(e.g. *"When an order is delayed more than 3 days and the warehouse is overloaded, notify
the customer; otherwise reschedule it. If they've already complained twice, escalate to a
manager."*) and **compiles** it into a decision **graph** that the system can execute
**deterministically** and **explainably**. When a case doesn't fit any workflow, a
**tool-using agent** handles it instead.

Think of it as **"Zapier/n8n, but you describe the workflow in plain English instead of
dragging boxes — and an AI agent covers what the workflow can't."**

---

## The problem it solves

Every operations / customer-support / compliance team has a rulebook of SOPs. Today they
have two bad options:

1. **Humans follow the rulebook manually** — slow, inconsistent, doesn't scale.
2. **Engineers hard-code the rules into software** — every rule change needs a developer
   and a deployment; ops teams wait weeks.

Cascade removes the engineer from the loop: an ops manager writes the procedure in English,
Cascade compiles it into an executable workflow, and when the policy changes they just edit
the English and recompile.

## Who it's for

- **Primary user:** a non-technical **operations / support / process manager** who owns the
  procedures.
- **Secondary beneficiary:** the **engineering team**, freed from hard-coding business rules.
- **Also cares:** **compliance / audit teams** — every run produces a trace showing exactly
  *why* each decision was made.

---

## How it works (30-second version)

```
Plain-English SOP
      │
      ▼
[ COMPILER ]  ── Gemini (LLM) turns the SOP into a decision graph (JSON)
      │            └─ if the SOP is ambiguous, it asks clarifying questions instead of guessing
      ▼
[ Editable Graph UI ]  ── user reviews / tweaks the graph (human-in-the-loop)
      │
      ▼
[ ROUTER ]  ── workflow-first, agent-fallback
      ├─ case fits a workflow → [ RUNTIME ] runs the graph DETERMINISTICALLY (no LLM)
      │                            └─ fetch data → evaluate decisions → take actions
      └─ no matching workflow  → [ AGENT ] a tool-using ReAct loop resolves it
                                    └─ think → call a tool → observe → repeat → finish
      ▼
[ Execution Trace ]  ── shows which nodes ran / which steps the agent took, and WHY
```

The key idea: **the AI thinks once at compile time; execution is deterministic and
auditable** for known cases — and a **tool-using agent** handles the unknown ones at run time.

---

## Features

- **SOP → graph compiler** (Gemini) with **structured JSON output**.
- **Ambiguity clarification** — vague SOPs trigger clarifying questions instead of guesses.
- **Human-in-the-loop editing** — review and tweak the generated graph before running.
- **Deterministic runtime** — topological execution + branch pruning, no LLM at run time.
- **Router** — "workflow-first, agent-fallback": run the graph if it fits, else use the agent.
- **Agent Mode** — a genuine **tool-calling ReAct loop** (think → act → observe → repeat) for
  messy / unknown cases; shown live step-by-step in the UI.
- **Dynamic run inputs** — the Run panel shows exactly the fields each workflow needs
  (`wbn`, `content_id`, `alert_id`, …) plus editable **case facts** to drive any branch.
- **SOP library** — save / load / delete compiled workflows; 5 built-in example domains.
- **Execution trace** — full "what ran / what was skipped / why" audit log.
- **Mock tools** — the workflow's actions are simulated locally, so the app runs standalone.
- **Graph visualization** — interactive, editable diagram with live path highlighting.
- **Runs with or without a key** — no key → deterministic mock mode; with a Gemini key →
  real LLM compilation + real agentic loop.

### Built-in example domains (short → long)
IT incident (Ops) · Refund request (E-commerce) · Payment failure (SaaS) ·
Delivery delay (Logistics) · Content moderation (Trust & Safety).

Deliberately **out of scope** (kept simple on purpose): parallel branches, loops,
real databases/auth, multiple LLM providers, RAG, fine-tuning.

---

## Tech stack (and why)

| Layer | Choice | Why |
|---|---|---|
| Frontend | **React + Vite** | Fast, standard, easy Vercel deploy |
| Graph UI | **React Flow (`@xyflow/react`)** | Interactive, **editable** node graphs + path highlighting (Mermaid is static-only) |
| Backend | **Python + FastAPI** | Clean typed APIs; great for LLM + graph logic; serverless-friendly |
| LLM | **Google Gemini** (free tier) | Free, strong structured-output/function-calling; used **only at compile time** |
| Storage | **Local JSON files** | Graphs are small; no DB needed for a standalone demo |
| Hosting | **Vercel** (frontend) + **Render** (backend) | Both free; Render is reliable for a Python service (Vercel-serverless backend is also supported) |

See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for the full "what / why / how" of every piece,
and [`DEPLOY.md`](./DEPLOY.md) for step-by-step deployment.

---

## Project structure

```
SOP Project/
├── README.md              ← you are here
├── ARCHITECTURE.md        ← deep dive: tech choices, flows, concepts (incl. Agent Mode + Router)
├── INTERVIEW_QA.md        ← simple-English Q&A for interview prep
├── DEPLOY.md              ← step-by-step GitHub + Vercel/Render deployment
├── backend/               ← FastAPI: compiler + runtime + router + agent + mock tools
│   ├── requirements.txt
│   ├── .env.example
│   ├── vercel.json        ← Vercel serverless routing (alt backend host)
│   ├── render.yaml        ← Render blueprint (recommended backend host)
│   ├── api/index.py       ← Vercel entrypoint (exports the ASGI app)
│   ├── smoke_test.py      ← quick end-to-end check (no key needed)
│   ├── agent_demo.py      ← watch the agent loop turn-by-turn in the terminal
│   └── app/
│       ├── graph_schema.py  ← the decision-graph data model (contract)
│       ├── tools.py         ← mock tools (the "hands") + per-run case facts
│       ├── compiler.py      ← SOP → graph (Gemini + no-key mock fallback, 5 domains)
│       ├── validator.py     ← guardrail: schema/DAG/tool checks
│       ├── runtime.py       ← deterministic engine (topo sort + branch pruning + trace)
│       ├── agent.py         ← Agent Mode: tool-calling ReAct loop (Gemini + mock)
│       ├── router.py        ← workflow-first, agent-fallback routing
│       ├── library.py       ← SOP library (samples + save/load/delete)
│       ├── config.py        ← settings (GEMINI_API_KEY optional)
│       └── main.py          ← FastAPI endpoints
└── frontend/              ← React + Vite + React Flow
    ├── package.json
    ├── .env.example
    ├── index.html
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx          ← layout: library, SOP input, clarify, run, case facts, agent, trace
        ├── GraphView.jsx    ← React Flow graph + path highlighting
        ├── api.js           ← backend client
        └── styles.css
```

---

## Getting started (local)

### Prerequisites
- Python 3.11+
- Node.js 18+
- A free **Gemini API key** (https://aistudio.google.com/apikey)

### Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export GEMINI_API_KEY=your_key_here   # Windows: set GEMINI_API_KEY=...
uvicorn app.main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
# open http://localhost:5173
```

---

## Deployment (free)

Frontend on **Vercel**, backend on **Render** (recommended). Your `GEMINI_API_KEY` is set as
an environment variable in the hosting dashboard — never committed. Full step-by-step in
[`DEPLOY.md`](./DEPLOY.md).

---

## The concepts this project demonstrates

Agentic AI (tool-calling ReAct loop) · LLM-as-compiler (natural language → executable) ·
workflow-vs-agent routing · structured LLM output · prompt engineering · deterministic &
auditable AI · DAG execution (topological sort + branch pruning) · LLM output validation ·
human-in-the-loop.

For plain-English explanations of each (and interview answers), see
[`INTERVIEW_QA.md`](./INTERVIEW_QA.md).
