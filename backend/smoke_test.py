"""Quick end-to-end smoke test of the core (mock mode, no API key).

Run: python3 smoke_test.py
Verifies: compile (mock) -> validate -> run (both decision branches).
"""
from app.compiler import compile_sop
from app.validator import validate_graph
from app.runtime import run_graph
from app.tools import ACTION_LOG


def show(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


# 1) Clarification path (very short SOP)
show("1) CLARIFICATION PATH (vague SOP)")
res = compile_sop("handle delays")
print("kind:", res.kind, "| questions:", res.questions)
assert res.kind == "clarification"

# 2) Compile a full SOP
show("2) COMPILE FULL SOP")
sop = ("When an order is delayed more than 3 days and the warehouse is overloaded, "
       "notify the customer; otherwise reschedule. If the customer has complained "
       "twice, escalate to a manager.")
res = compile_sop(sop)
print("kind:", res.kind)
assert res.kind == "graph"
graph = res.graph
problems = validate_graph(graph)
print("validation problems:", problems)
assert problems == []
print("nodes:", [n.id for n in graph.nodes])

# 3) Run — case A: 1 complaint (no escalate), delayed+overloaded -> notify
show("3) RUN — case A (1 complaint -> delay path -> notify)")
ACTION_LOG.clear()
out = run_graph(graph, {"wbn": "WBN123"})
print("ran:", out["summary"]["ran"])
print("skipped:", out["summary"]["skipped"])
print("actions:", out["action_log"] if "action_log" in out else ACTION_LOG)
for step in out["trace"]:
    if step["type"] == "decision":
        print("  decision", step["node"], "->", step.get("result"), "chose", step.get("chose"))

print("\nAll assertions passed ✅")
