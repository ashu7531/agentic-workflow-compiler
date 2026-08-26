# Cascade — Architecture & Design (the "what / why / how" of everything)

This document is written so that **anyone** — a new engineer, or you before an interview —
can read it top to bottom and fully understand what the system is, why each technology was
chosen, and how every flow works. It goes from the big picture down to the details.

---

## 1. What is this project, in one paragraph

Cascade takes a **Standard Operating Procedure written in plain English** and uses an LLM to
**compile** it into a **decision graph** (a set of nodes and edges describing what to check,
what to decide, and what to do). That graph is then **executed by a deterministic runtime** —
no LLM involved at run time — so the same input always produces the same path, and every run
emits a full **trace** explaining why each step ran or was skipped. A user can **review and
edit** the generated graph before running it (human-in-the-loop). Actions (like "notify the
customer") are performed by **tools**, which are mocked locally so the whole thing runs
standalone.

The core insight: **the AI does the thinking once, at compile time. Execution is
deterministic, auditable, and cheap.**

---

## 2. Why this design (the guiding principles)

1. **Compile once, run deterministically.** LLMs are non-deterministic and can hallucinate.
   If we let an LLM decide every step live, the same case could behave differently each time —
   unacceptable for business rules. So we use the LLM *only* to produce the graph, then run
   that graph with plain code. This gives us **repeatability, auditability, low latency, and
   low cost** at run time.
2. **Human-in-the-loop.** We never blindly trust the LLM's output. The user reviews and can
   edit the graph before it runs. The LLM proposes; the human approves.
3. **Ask, don't guess.** If the SOP is missing information, the compiler asks clarifying
   questions instead of inventing details.
4. **Tool-agnostic.** The engine doesn't hard-code any specific system. Actions go through a
   generic tool interface, so the same workflow can call mock tools (demo) or real APIs
   (production) without changing the engine.
5. **Keep v1 small.** Sequential + if/else only. No parallelism/loops. A small, correct core
   beats a big, fragile one.

---

## 3. The big-picture architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (React)                            │
│                                                                          │
│  [SOP text box] ──compile──▶  [Editable Graph View (React Flow)]         │
│                                     │                                    │
│                               [Run panel + inputs]                       │
│                                     │                                    │
│                          [Execution trace / path highlight]              │
└───────────────────────────────┬──────────────────────────────────────┬─┘
                                 │ HTTP (JSON)                           │
                                 ▼                                       │
┌────────────────────────────────────────────────────────────────────┐ │
│                          BACKEND (FastAPI)                           │ │
│                                                                      │ │
│  POST /compile   ── COMPILER ──▶ Gemini ──▶ graph JSON  (or          │ │
│                                              clarifying questions)   │ │
│  POST /validate  ── schema/DAG validation                            │ │
│  POST /run       ── RUNTIME (deterministic graph engine)             │ │
│                        │                                             │ │
│                        ▼                                             │ │
│                     TOOLS (mock: get_tracking, notify, reschedule…)  │ │
└──────────────────────────────────────────────────────────────────────┘ │
                                 ▲                                         │
                                 └── Google Gemini API (compile time only) ┘
```

Three logical parts (all bundled in one repo so it's standalone):
- **Compiler** — the AI brain (English → graph). Uses Gemini.
- **Runtime** — the deterministic executor (graph → actions + trace). Plain Python.
- **Tools** — the "hands" that perform actions. Mocked locally; pluggable in production.

---

## 4. The data model: the decision graph

A compiled SOP is a **graph document** made of nodes and edges.

### Node types (only three — kept deliberately small)

| Type | Purpose | Calls a tool? | Example |
|---|---|---|---|
| **fetch** | Get information needed to decide | ✅ reads via a tool | `get_tracking(wbn)` → `{days_late: 5}` |
| **decision** | Choose a branch based on data | ❌ pure logic | `days_late > 3 AND overloaded?` |
| **action** | Perform the outcome | ✅ writes/does via a tool | `send_notification(...)` |

Key clarification: **a decision node never calls an API — it's just an `if`.** The API call
happens at the **action node** on whichever branch the decision picks.

### Edges
Edges connect nodes. Two kinds:
- **data edges** carry a value from one node's output into another node's input (a *binding*).
- **control edges** come out of a decision node into its branch targets; the runtime may
  "cut" the un-taken ones.

### Graph JSON (simplified shape)
```json
{
  "nodes": [
    {"id": "fetch_tracking", "type": "fetch", "tool": "get_tracking", "inputs": {"wbn": "entry.wbn"}},
    {"id": "fetch_facility", "type": "fetch", "tool": "get_facility_status", "inputs": {}},
    {"id": "decide_delay", "type": "decision",
     "condition": "fetch_tracking.days_late > 3 and fetch_facility.overloaded == true"},
    {"id": "notify", "type": "action", "tool": "send_notification", "inputs": {"wbn": "entry.wbn"}},
    {"id": "reschedule", "type": "action", "tool": "reschedule_delivery", "inputs": {"wbn": "entry.wbn"}}
  ],
  "edges": [
    {"from": "fetch_tracking", "to": "decide_delay"},
    {"from": "fetch_facility", "to": "decide_delay"},
    {"from": "decide_delay", "to": "notify", "branch": "true"},
    {"from": "decide_delay", "to": "reschedule", "branch": "false"}
  ]
}
```

---

## 5. Flow #1 — Compile (English → graph)

**Endpoint:** `POST /compile` with `{ "sop_text": "..." }`

1. The backend builds a **prompt** that includes: the SOP text, the exact graph JSON schema,
   the list of available tools (names + what each does), and a few worked examples
   (few-shot). It instructs Gemini to output **only** valid graph JSON — *or*, if the SOP is
   missing required info, a list of clarifying questions.
2. Gemini returns one of two things:
   - **Graph JSON** → we parse it.
   - **`{"needs_clarification": ["Notify via email or SMS?", ...]}`** → we return those to the
     UI. The user answers, and we call `/compile` again with the SOP + answers appended.
3. **Validation** (`/validate` logic, run automatically): is it valid JSON matching the
   schema? Do all referenced tools exist? Is it acyclic (a DAG)? Does every decision have
   branches? If invalid, we surface a clear error (the human can then fix it in the UI).

**Why Gemini here:** turning fuzzy English into a strict structure is exactly what LLMs are
good at, and Gemini's structured-output mode makes the JSON reliable. This is the one place
AI is genuinely required.

**Concepts used:** LLM structured output, prompt engineering (few-shot + schema), LLM output
validation/guardrails, ambiguity handling.

---

## 6. Flow #2 — Review & edit (human-in-the-loop)

The graph is rendered in the UI with **React Flow** as an interactive diagram. The user can:
- read the flow visually,
- edit a node's condition or values, add/remove a node,
- then save the (possibly edited) graph.

**Why:** we treat the LLM as a *proposer*, not an authority. This also means we don't need a
complex automatic "self-repair" loop in v1 — the human is the repair mechanism.

---

## 7. Flow #3 — Run (deterministic execution)

**Endpoint:** `POST /run` with `{ "graph": {...}, "entry": {"wbn": "WBN123"} }`

The runtime engine (plain Python — **no LLM**) does:

1. **Topological sort** (Kahn's algorithm): order the nodes so that every node runs only
   after the nodes it depends on. (This is why the graph must be acyclic.)
2. **Execute forward.** For each node in order, if it's "live":
   - **fetch** → call its tool, store the output.
   - **decision** → evaluate its condition against already-fetched data → choose a branch →
     **cut** the edges to the *other* branches (so their exclusive nodes become dead/skip).
   - **action** → call its tool to perform the outcome.
3. **Branch pruning / liveness:** a node runs only if it's reachable through an un-cut edge.
   The set of skipped nodes is a **pure function of the decision outputs**, which are a pure
   function of the input data → fully deterministic.
4. **Trace:** every step records what ran, what was skipped, the values on each edge, and why
   each decision went the way it did.

**Output:** the final state + a **human-readable trace** the UI animates (taken branch green,
skipped branch grey).

**Concepts used:** DAG / graph theory, topological sort, branch pruning, deterministic
execution, auditability.

---

## 8. The tools layer (the "hands")

Actions and data-fetches are performed by **tools** — small functions with a name, a
description, and typed inputs/outputs. In this standalone project they are **mocked**:

```python
def get_tracking(wbn):        return {"days_late": 5}          # fake data
def get_facility_status():    return {"overloaded": True}
def get_complaint_count(wbn): return {"count": 1}
def send_notification(**k):   log("📧 delay email sent"); return {"ok": True}
def reschedule_delivery(**k): log("📅 rescheduled");       return {"ok": True}
def escalate_to_manager(**k): log("⏫ escalated");          return {"ok": True}
```

**Why mocks:** they stand in for real external systems so the app is 100% self-contained and
runs on a laptop. The engine calls tools through a generic interface, so in production you'd
point the same tool names at real APIs (or **MCP**-exposed tools) without changing the engine.
This is why the project is "standalone for the demo, pluggable in production."

---

## 9. Why each technology (rationale)

- **React + Vite (frontend):** fast dev, standard, trivial Vercel deploy.
- **React Flow / `@xyflow/react` (graph UI):** we need an **editable, interactive** graph with
  live path highlighting. React Flow is purpose-built for this. Mermaid.js only renders
  *static* diagrams from text, so it can't do the editing/animation we need.
- **Python + FastAPI (backend):** clean, typed HTTP APIs; Python is the natural home for LLM
  SDKs and graph logic; FastAPI runs well as a Vercel serverless function.
- **Google Gemini (LLM):** free tier, strong structured-output/function-calling; used only at
  compile time, so cost and latency at run time are zero.
- **Local JSON storage:** graphs are tiny; a database would be overkill for a standalone demo.
- **Vercel hosting:** free and shareable. Our backend is **stateless and quick** (one Gemini
  call to compile; fast in-memory execution to run), which fits serverless. Fallback for
  heavier needs: Render/Railway free tier.

---

## 10. Boundaries, assumptions, and honest limitations

- **Determinism assumes deterministic tools.** Our mock tools return fixed data, so runs are
  reproducible. Real APIs would introduce real-world variability (that's expected).
- **v1 supports sequential + if/else only.** No parallel branches, loops, or nested
  sub-workflows (the production system this was inspired by does; we deliberately scoped down).
- **Compiler quality depends on prompt + examples.** Messy or contradictory SOPs may need the
  clarification flow or a human edit. That's by design, not a bug.
- **No auth / multi-tenant / real persistence** — out of scope for a demo.

---

## 11. What is reused vs. built new

Inspired by a real production system (a logistics company's SOP-execution engine). In that
system the compiler and runtime live in separate services. Here:
- **Built new (the valuable, AI-heavy part):** the SOP→graph **compiler**, the **mock tools**,
  the **UI**, the standalone wiring, and (optionally) an eval set.
- **Adapted from a reference runtime:** the deterministic execution idea (topological order +
  branch pruning + trace). We build a clean, self-contained version.

So the hardest, most impressive piece — turning English into an executable graph — is
genuinely original work.

---

## 12. Glossary (plain English)

- **SOP** — Standard Operating Procedure; a written rulebook for handling a situation.
- **Compile** — turn the English SOP into a structured graph.
- **Graph / DAG** — nodes (steps) connected by edges (arrows); "acyclic" means no loops.
- **Topological sort** — ordering steps so each runs after the steps it depends on.
- **Branch pruning** — skipping the path a decision didn't choose.
- **Deterministic** — same input → same output, every time.
- **Trace** — the log of what ran, what was skipped, and why.
- **Tool** — a function that fetches data or performs an action (mocked here).
- **Human-in-the-loop** — a person reviews/edits the AI's output before it's used.
- **MCP (Model Context Protocol)** — a standard way for AI systems to call external tools;
  relevant because our tools could be exposed via MCP in production.


---

## 13. Agent Mode + the Router (the genuinely agentic part)

Everything above is the **deterministic** path: compile an SOP into a fixed graph and
execute it exactly. That's ideal for the common, well-defined cases. But real operations
have a messy "long tail" — novel or multi-intent cases no fixed flowchart anticipated. For
those we add **Agent Mode**, and a **Router** to decide which path a case takes.

### 13.1 Deterministic workflow vs. Agent — the difference
Both use the SOP/policies. The difference is *how*:
- **Workflow** = the SOP frozen into a fixed graph, executed the same way every time (fast,
  cheap, auditable, but only handles what was pre-built).
- **Agent** = the SOP handed to an LLM as *guidance*, plus a toolbox; the LLM decides each
  next action itself in a loop — **think → call a tool → observe → think → …** — until it
  resolves the case or escalates (flexible, handles the unknown, but slower / non-deterministic).

The agent is a genuine **ReAct-style tool-calling loop** (`backend/app/agent.py`), not a
single generation call. Each round the model chooses one action (call a tool, or finish);
we execute the tool, feed the result back, and loop (capped at `MAX_STEPS`).

### 13.2 The Router — "workflow-first, agent-fallback"
`backend/app/router.py` (`handle_case`) decides, and it lives in **our platform**, not the
client's code (routing is core intelligence):
1. Try to **compile** the case into a workflow.
2. If a valid workflow results → **run it deterministically**.
3. If not (unknown domain / needs clarification) → **hand it to the agent**.
A `force_agent` flag lets the UI demo the agent on any case.

```
incoming case
   → Router: can we compile a workflow?
        ├─ yes → deterministic workflow run  (fast, auditable)
        └─ no  → tool-using Agent loop        (flexible, handles the unknown)
   → both call the same tools; both return a trace
```

### 13.3 Two AI backends for the agent
- **Gemini mode** (key set): a real ReAct loop — the LLM emits a JSON action each turn
  (`{action:"tool"|"final", ...}`), we execute tools and feed observations back.
- **Mock mode** (no key): a deterministic, domain-aware scripted loop so the feature is
  fully demoable without a key (clearly labelled "mock mode" in the UI).

### 13.4 Endpoints
- `POST /handle` — the front door: routes a case to workflow or agent (`{route, ...}`).
- `POST /agent-run` — run the agent directly (used by the UI's "Agent mode" toggle).

### 13.5 The honest trade-off (interview point)
- Workflow: fast, consistent, auditable — but rigid.
- Agent: adaptive, handles novelty — but slower, costs more LLM calls, less predictable.
- The engineering skill is the **routing decision** (deterministic where possible, agentic
  where necessary) — exactly how production agent systems are built.
