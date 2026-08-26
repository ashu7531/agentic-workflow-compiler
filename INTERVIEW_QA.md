# Cascade — Interview Q&A (simple English)

This is your prep sheet. Every answer is written in plain, simple language so you can explain
the project confidently — even if you haven't looked at the code in a while. Read the short
answer first; the "if they dig deeper" notes help with follow-ups.

---

## A. The basics

### Q1. What is this project?
It's a tool that takes a company procedure written in plain English and turns it into a
workflow that runs automatically. For example, a support rule like *"if an order is more than
3 days late and the warehouse is busy, tell the customer; otherwise reschedule it"* becomes a
running, automated flow. So instead of a human following the rulebook or an engineer coding
it, you just write the rule in English and the system runs it.

### Q2. Why did you build it? What problem does it solve?
Every operations and support team has rulebooks (SOPs). Automating them normally needs
engineers to hard-code the logic, so every small rule change takes weeks of dev work. My tool
lets a non-technical manager write the rule in English and get a running workflow in minutes.
It saves engineering time and makes the process consistent.

### Q3. Who are the users?
Mainly non-technical **operations / customer-support / process managers** who own the
procedures. It also helps **engineers** (they stop hard-coding rules) and **compliance teams**
(because every run produces an audit trail of why each decision was made).

### Q4. Give me a real example.
Support SOP: *"When an order is delayed: if it's more than 3 days late and the warehouse is
overloaded, notify the customer; otherwise reschedule. If the customer complained twice,
escalate to a manager."* You paste that in, the tool builds a flowchart, and then for a real
order it automatically checks the data and takes the right action — and shows you exactly why.

---

## B. How it works

### Q5. How does it actually work, step by step?
1. You paste the SOP in English.
2. An LLM (Gemini) **compiles** it into a decision graph — a flowchart of steps.
3. You can review and edit that graph (I don't blindly trust the AI).
4. A **runtime** then executes the graph step by step: it fetches data, evaluates the
   decisions, and takes actions.
5. It outputs a **trace** showing which steps ran, which were skipped, and why.

### Q6. Where exactly is the AI used?
Only in the **compile** step — turning English into the graph. Once the graph exists, running
it is plain code with **no AI**. That's on purpose (see Q9).

### Q7. When there's a decision, does it call an API?
No — a **decision** node is just an `if`; it only picks a branch. The API call happens at the
**action** node on the branch that was chosen. So: fetch data (API) → decide (just logic) →
act (API).

### Q8. What are "tools"? Are they real?
Tools are the functions that fetch data or perform actions (like "send notification" or
"reschedule"). In my demo they're **mocked** — they return fake data or just log the action —
so the whole app runs on a laptop with nothing external. In production you'd point the same
tool names at real APIs.

### Q9. Why compile once and run deterministically instead of letting the AI decide live?
Because LLMs are non-deterministic and can hallucinate. If the AI decided every step live, the
same case might behave differently each time — bad for business rules. By using AI only to
build the graph and then running it with plain code, I get **repeatability, auditability, low
cost, and low latency** at run time. This is my main design decision and my favorite talking
point.

### Q10. How does the runtime know what order to run steps in?
It uses a **topological sort** (Kahn's algorithm) on the graph so each step runs only after
the steps it depends on. When a decision picks a branch, it **cuts** the other branch so those
steps are skipped. Because skipping is purely based on the data, the whole run is deterministic.

### Q11. What if the SOP is vague or missing details?
The compiler doesn't guess — it **asks clarifying questions** (e.g. "Notify by email or SMS?").
The user answers, and then it builds the graph. The "brain" asking the questions is the same
Gemini call at compile time.

### Q12. How do you make sure the AI's output is valid?
After Gemini returns the graph, I **validate** it: is it valid JSON matching my schema? Do all
referenced tools exist? Is it a proper flowchart with no loops? Does every decision have
branches? If something's off, the user can fix it in the editable graph UI.

---

## C. Tech choices

### Q13. What's the tech stack and why?
- **Frontend:** React + Vite (fast, standard, easy to deploy).
- **Graph UI:** React Flow — because I needed an **editable, interactive** graph with path
  highlighting; Mermaid.js only draws static pictures.
- **Backend:** Python + FastAPI (clean APIs, natural fit for LLM + graph logic).
- **LLM:** Google Gemini (free tier, good at structured output).
- **Storage:** local JSON files (graphs are small; no DB needed).
- **Hosting:** Vercel (free, shareable).

### Q14. Why Gemini and not OpenAI?
Mainly the **free tier** and strong structured-output support. The design isn't locked to
Gemini — I could swap the LLM since it's only used in one place (compile).

### Q15. Why React Flow over Mermaid?
Mermaid renders a static diagram from text — you can't click and edit it. I needed users to
**edit** the graph and to **animate the execution path**, which is exactly what React Flow is
built for.

### Q16. How is it deployed / hosted for free?
Frontend on Vercel, backend as Vercel Python serverless functions. That works because my
backend is **stateless and quick** (one Gemini call to compile, fast in-memory execution to
run). If it ever needed long-running processes, I'd move the backend to Render or Railway
(also free).

---

## D. Concepts (be ready to define these simply)

### Q17. What is "agentic AI"?
Software where an AI doesn't just answer a question but takes steps and uses tools to get
something done. My project is agentic because the workflow uses tools to fetch data and
perform actions.

### Q18. What is "structured output"?
Making the LLM return data in a strict format (here, JSON matching my graph schema) instead of
free text — so my code can use it reliably.

### Q19. What is a DAG / topological sort (in simple terms)?
A DAG is a flowchart with no loops. A topological sort is just ordering the boxes so each box
runs only after the boxes it depends on. That's how my runtime knows the order.

### Q20. What is "auditable / deterministic AI" and why does it matter?
Deterministic = same input always gives the same result. Auditable = you can see exactly why
it decided what it did. This matters a lot for businesses in regulated areas (finance,
insurance, healthcare) that can't use a black box.

### Q21. What is MCP and how does it relate?
MCP (Model Context Protocol) is a standard way for AI systems to call external tools. My tools
could be exposed via MCP in production, so the same workflow could plug into any real system
through a standard interface.

---

## E. Market & scope

### Q22. What's the market demand for this?
It fits a hot area often called **"agentic process automation"** — automating multi-step
business processes with AI. Tools like Zapier, n8n, and Dify show the demand. My angle —
turning a plain-English procedure into an **auditable, deterministic** workflow — is less
common and appeals to teams that need explainability.

### Q23. How is this different from Zapier / n8n?
Those need you to build the workflow by dragging boxes and configuring each step. Mine lets you
describe it in **plain English** and compiles the workflow for you. And it emphasizes
**auditability** (a trace of every decision).

### Q24. What did YOU build vs. reuse?
I built the hardest part — the **English-to-graph compiler** — plus the tools, the UI, and the
standalone wiring. The deterministic-execution idea (topological order + branch pruning) I
adapted from studying a real production engine, but I built my own clean version.

### Q25. What are the limitations?
v1 only supports sequential steps and if/else (no parallel branches or loops). Determinism
depends on the tools being deterministic. Messy SOPs may need clarification or a human edit.
No auth or real database — it's a focused demo.

### Q26. How would you scale / improve it?
Add parallel branches and loops, expose tools via a real MCP server, add an evaluation set to
measure compiler accuracy, add versioning of SOPs, and connect real APIs instead of mocks.

---

## F. Likely curveballs

### Q27. Isn't this just a wrapper around an LLM?
No. The LLM is used in exactly one place (compile). The real engineering is the **graph
runtime** (topological execution, branch pruning, deterministic tracing), the **validation**
of the AI's output, and the **human-in-the-loop** design. The LLM proposes; my system executes
and verifies.

### Q28. What was the hardest part?
Getting the LLM to reliably turn messy English into a **correct, valid graph**. That took
careful prompt design (schema + examples), plus validation and the clarification flow for when
the SOP is ambiguous.

### Q29. What did you learn?
How to make LLM output reliable with structured output + validation, how deterministic graph
execution works (topological sort, branch pruning), and the trade-off between letting an AI act
freely vs. compiling its plan once and running it deterministically.

### Q30. Why is "compile once, run deterministically" better than a live agent?
A live agent re-decides every time, which is slower, costs more, and can be inconsistent. My
approach fixes the logic at compile time, so execution is fast, cheap, repeatable, and
auditable — while still being flexible, because changing the rule is just editing the English
and recompiling.


---

## G. Agent Mode & routing (the agentic part)

### Q31. Is this just one Gemini API call?
For the *compile* step, essentially yes — turning English into a graph is one structured
call. But the project also has **Agent Mode**, which is a genuine **tool-calling loop**: the
LLM decides an action, we run a tool, feed the result back, and it decides the next action —
repeatedly — until the case is resolved. That's many orchestrated calls with autonomous tool
use, not a single call.

### Q32. What's the difference between the workflow and the agent?
Both use the SOP. The **workflow** is the SOP frozen into a fixed flowchart, run the same way
every time — great for common, predictable cases. The **agent** is given the SOP as guidance
plus a toolbox, and it reasons case-by-case, calling tools in a loop — for messy or novel
cases no fixed flowchart covers.

### Q33. When does each one run? Who decides?
A **router** decides, on a "workflow-first, agent-fallback" basis: it tries to compile a
workflow for the case; if one exists, it runs deterministically; if not (or the workflow gets
stuck), it hands the case to the agent. The router lives in our platform, so the client just
forwards cases and registers tools.

### Q34. What makes it "agentic" and not just generation?
Three things: it runs in a **loop**, it **uses tools** (takes real actions), and it **decides
its own next step** based on what it observed. Generation is one prompt → one answer; an agent
is think → act → observe → repeat.

### Q35. Why keep the deterministic workflow at all — why not always use the agent?
Because for the 90% of common, well-defined cases the workflow is **faster, cheaper, and
auditable** (same input → same path, every time). The agent is slower, costs more LLM calls,
and is less predictable. So you use the workflow where you can and the agent only for the long
tail. Knowing *when to use which* is the real design skill.

### Q36. How does the agent avoid doing something wrong?
It can only call tools that exist (no inventing actions), it has a step cap so it can't loop
forever, it's guided by the SOP/policy text, and when unsure it escalates to a human. In a
fuller version you'd add output guardrails and a shadow (observe-only) mode before letting it
take live actions.
