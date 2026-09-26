# /// script
# requires-python = ">=3.11"
# dependencies = ["openai>=1.40", "python-dotenv>=1.0"]
# ///
"""Smoke test for Vultr Serverless Inference.

Lists models, then runs one native tool call on LLM_MODEL_MAIN and one on
LLM_MODEL_FAST, printing latency and token usage. Run it at the start of every
session:  uv run scripts/smoke_inference.py
"""

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

client = OpenAI(
    base_url=os.environ["VULTR_INFERENCE_BASE_URL"],
    api_key=os.environ["VULTR_INFERENCE_API_KEY"],
    timeout=90,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run Python code in the sandbox and return stdout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source"},
                    "purpose": {"type": "string", "description": "One line: why"},
                },
                "required": ["code", "purpose"],
            },
        },
    }
]


def main() -> int:
    ids = sorted(m.id for m in client.models.list().data)
    print("models:", ", ".join(ids))
    ok = True
    for var in ("LLM_MODEL_MAIN", "LLM_MODEL_FAST"):
        model = os.environ[var]
        if model not in ids:
            print(f"{var}={model} NOT in model list")
            ok = False
            continue
        t0 = time.time()
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a careful accountant who writes Python. Always use the run_python tool."},
                {"role": "user", "content": "Compute 1520.00 - 1250.00 and check whether the difference is divisible by 9."},
            ],
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.1,
            max_tokens=4096,
        )
        dt = time.time() - t0
        choice = resp.choices[0]
        calls = choice.message.tool_calls or []
        print(f"{var}={model}: {dt:.1f}s finish={choice.finish_reason} tool_calls={len(calls)} usage={resp.usage}")
        for c in calls:
            args = json.loads(c.function.arguments)
            print("  ->", c.function.name, json.dumps(args)[:300])
        if not calls:
            print("  content:", (choice.message.content or "")[:300])
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
