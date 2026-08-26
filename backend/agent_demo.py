"""Watch the agent loop turn-by-turn from the terminal.

Run:  python3 agent_demo.py
- No GEMINI_API_KEY  -> mock mode (scripted loop; shows the SHAPE of the loop).
- With GEMINI_API_KEY -> real ReAct loop (Gemini decides each step live).
"""
from app.agent import run_agent
from app.config import get_settings

CASE = "A shipment is delayed and the customer is upset — please handle it."
ENTRY = {"wbn": "WBN123"}
FACTS = {"days_late": 5, "overloaded": True, "complaint_count": 1}

print("=" * 64)
print("MODE:", "gemini (real LLM loop)" if get_settings().has_llm else "mock (scripted loop)")
print("CASE:", CASE)
print("FACTS:", FACTS)
print("=" * 64)

result = run_agent(CASE, ENTRY, FACTS, policy_text=CASE)

for i, step in enumerate(result["steps"], 1):
    print(f"\n── Round {i} ──")
    if step.get("thought"):
        print("  🤔 THINK :", step["thought"])
    if step.get("tool"):
        print("  🔧 ACT   :", f"{step['tool']}({step.get('args', {})})")
        print("  👀 OBSERVE:", step["observation"])
    if step.get("final"):
        print("  ✅ FINAL :", step["final"])

print("\n" + "=" * 64)
print("FINAL ANSWER:", result["final"])
print("ACTIONS TAKEN:", result["action_log"])
print("=" * 64)
