"""Secrets canary verification: ensure LLM_API_KEY never leaks into child process env."""
import os
import sys

# Set canary secret
CANARY = "sk-CANARY-SECRET-12345"
os.environ["LLM_API_KEY"] = CANARY
os.environ["LLM_PROVIDER"] = "canary_provider"
os.environ["LLM_MODEL"] = "canary_model"

# Import runner environment builder
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.runner import _child_env


def test_canary():
    child_env = _child_env()
    print("Testing child process environment...")
    leaked = []
    for k, v in child_env.items():
        if CANARY in v or "CANARY" in v or "LLM" in k:
            leaked.append(f"{k}={v}")

    if leaked:
        print(f"FAIL: Secrets leaked into child env: {leaked}")
        sys.exit(1)

    print("PASS: Canary secret sk-CANARY-SECRET-12345 NOT present in child env.")
    print("PASS: LLM_* keys explicitly stripped from child env.")
    print(f"Child env keys count: {len(child_env)}")

if __name__ == "__main__":
    test_canary()
