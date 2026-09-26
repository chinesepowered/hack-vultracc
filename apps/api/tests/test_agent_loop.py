"""Agent loop plumbing with a scripted LLM and the real sandbox runner (no inference cost).

Covers: parallel tool calls, the JSON action fallback, a premature finish that
the control plane rejects, recovery, and Replay reproducing every hash.
Skipped when no runner is reachable.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import httpx
import pytest

from tieout.agent import Agent, replay
from tieout.inputs import build_inputs, load_profile
from tieout.llm import LLMReply
from tieout.runner_client import RunnerClient

RUNNER_URL = os.environ.get("TEST_RUNNER_URL", "http://127.0.0.1:7070")
RUNNER_TOKEN = os.environ.get("TEST_RUNNER_TOKEN") or os.environ.get("SANDBOX_RUNNER_TOKEN_LOCAL", "")


def _runner_up() -> bool:
    try:
        return httpx.get(f"{RUNNER_URL}/v1/health", timeout=2).json().get("ok", False) and bool(RUNNER_TOKEN)
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _runner_up(), reason="no local sandbox runner (set TEST_RUNNER_TOKEN)")

LOAD = """
from tieout_lib import *
bank = load_bank("/in/bank_statement.csv")
gl = load_gl("/in/gl_cash_detail.csv")
prior = load_prior("/in/prior_outstanding.csv")
m = match_all(bank, gl, prior)
print(m.summary())
"""
WRITE = LOAD + """
profile = load_profile("/in/client_profile.json")
exceptions = classify_unmatched(m.unmatched_bank, m.unmatched_gl, period_end=profile["period_end"], prior_outstanding=m.prior_open, gl=gl, bank=bank)
ajes = propose_ajes(exceptions, profile, period_end=profile["period_end"])
recon = reconcile(bank_ending=statement_balances(bank)["closing"], gl_ending=ledger_balances(gl)["closing"], exceptions=exceptions, ajes=ajes)
write_outputs("/out", client=profile, recon=recon, matches=m, exceptions=exceptions, ajes=ajes, bank=bank, gl=gl)
"""


def call(i: int, name: str, args: dict):
    return SimpleNamespace(id=f"call_{i}", function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def reply(content: str = "", calls=None) -> LLMReply:
    msg = SimpleNamespace(content=content, tool_calls=calls or None)
    return LLMReply(message=msg, model="scripted", tokens_in=100, tokens_out=50, latency_ms=1, finish_reason="tool_calls", reasoning=None)


class ScriptedLLM:
    model = "scripted"
    fallback_model = "scripted"

    def __init__(self):
        self.turn = 0
        self.seen_tool_results: list[str] = []

    async def chat(self, messages, tools=None, **kw):
        self.turn += 1
        self.seen_tool_results.extend(m["content"] for m in messages if m.get("role") in ("tool", "user") and "Result of" in str(m.get("content", "")))
        if self.turn == 1:  # parallel sniffs
            return reply("Inspecting both files.", [call(1, "sniff_file", {"name": "bank_statement.csv"}),
                                                    call(2, "sniff_file", {"name": "gl_cash_detail.csv"})])
        if self.turn == 2:  # JSON action fallback instead of a native tool call
            return reply(json.dumps({"tool": "run_python", "args": {"purpose": "Load and match", "code": LOAD}}))
        if self.turn == 3:  # premature finish: must be rejected (no result.json yet)
            return reply("", [call(3, "finish", {"summary": "done?", "memo_markdown": "too early"})])
        if self.turn == 4:
            last_tool = [m for m in messages if m.get("role") == "tool"][-1]["content"]
            assert '"ok": false' in last_tool and "result.json" in last_tool
            return reply("Writing outputs.", [call(4, "run_python", {"purpose": "Classify and write outputs", "code": WRITE})])
        return reply("Ties at 0.00.", [call(5, "finish", {"summary": "Reconciled", "memo_markdown": "Difference 0.00 — all explained."})])


async def test_agent_loop_end_to_end_with_scripted_llm():
    client_id = "blue-harbor-coffee"
    run_id = "run_test_scripted"
    events: list[tuple[str, dict]] = []

    async def emit(kind, payload):
        events.append((kind, payload))

    runner = RunnerClient(RUNNER_URL, RUNNER_TOKEN)
    inputs = build_inputs(client_id, run_id)
    agent = Agent(run_id=run_id, profile=load_profile(client_id), inputs=inputs, emit=emit, llm=ScriptedLLM(), runner=runner,
                  labels={"arena.tenant": client_id, "arena.task": run_id})
    out = await agent.run()
    assert out.status == "succeeded", out.error
    assert out.result["difference"] == "0.00"
    assert [s.tool for s in out.steps] == ["sniff_file", "sniff_file", "run_python", "run_python"]
    assert "—" not in out.memo  # house style applied to model text
    kinds = [k for k, _ in events]
    assert kinds[0] == "run_started" and "sandbox_created" in kinds and kinds[-1] == "run_finished"
    assert [p["ok"] for k, p in events if k == "validation"] == [False, True]
    rep = await replay(steps=out.steps_json(), inputs=inputs, emit=emit, runner=runner, labels={"arena.tenant": client_id})
    assert rep.ok and rep.hashes == out.hashes
