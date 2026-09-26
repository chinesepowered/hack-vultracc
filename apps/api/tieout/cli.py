"""Command line entry points.

    uv run python -m tieout.cli run --client blue-harbor-coffee [--check]
    uv run python -m tieout.cli replay --run-dir .local-runs/<run_id>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import secrets
import sys
import time
from decimal import Decimal
from pathlib import Path

from .agent import Agent, replay
from .config import REPO_ROOT, settings
from .inputs import build_inputs, client_dir, load_profile


def printer(prefix: str):
    async def emit(kind: str, payload: dict) -> None:
        t = time.strftime("%H:%M:%S")
        if kind == "tool_call":
            args = payload.get("args", {})
            detail = args.get("name") or args.get("purpose") or args.get("summary") or ""
            print(f"{t} {prefix} -> {payload['tool']}: {detail}")
        elif kind == "tool_result":
            out = (payload.get("stdout") or "").strip().splitlines()
            print(f"{t} {prefix} <- exit={payload.get('exit_code')} {payload.get('duration_ms')}ms | " + " / ".join(out[-3:])[:300])
            if payload.get("exit_code"):
                print("     stderr:", (payload.get("stderr") or "")[-600:])
        elif kind == "llm":
            print(f"{t} {prefix} llm#{payload['call']} {payload['model']} in={payload['tokens_in']} out={payload['tokens_out']} {payload['latency_ms']}ms")
        elif kind == "thought":
            txt = (payload.get("text") or "").replace("\n", " ")
            if txt:
                print(f"{t} {prefix} thought: {txt[:240]}")
        elif kind == "sandbox_created":
            att = payload.get("attestation") or {}
            print(f"{t} {prefix} sandbox {payload['sandbox_id']} on {payload.get('host')} attestation_ok={att.get('ok')}")
        elif kind == "validation":
            print(f"{t} {prefix} validation ok={payload['ok']} {payload['errors'][:3]}")
        elif kind == "run_finished":
            print(f"{t} {prefix} finished status={payload['status']} recon={payload['recon_status']} diff={payload['difference']} "
                  f"tools={payload['tool_calls']} tokens={payload['tokens_in']}+{payload['tokens_out']} {payload['duration_ms']}ms err={payload['error']}")
    return emit


def check_against_expected(client_id: str, result: dict) -> list[str]:
    exp = json.loads((client_dir(client_id) / "expected.json").read_text())

    def key(e):
        return (e["kind"], Decimal(e["amount"]), e.get("bank_ref") or None, e.get("gl_ref") or None)

    want = sorted(key(e) for e in exp["exceptions"])
    got = sorted(key(e) for e in result["exceptions"])
    problems = []
    if got != want:
        problems.append(f"exceptions differ: missing={sorted(set(want) - set(got))} extra={sorted(set(got) - set(want))}")
    if result["difference"] != "0.00":
        problems.append(f"difference {result['difference']}")
    if result["status"] != exp["status"]:
        problems.append(f"status {result['status']} != {exp['status']}")
    return problems


async def cmd_run(args) -> int:
    run_id = args.run_id or f"run_{time.strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(3)}"
    profile = load_profile(args.client)
    inputs = build_inputs(args.client, run_id)
    labels = {"arena.tenant": args.client, "arena.task": run_id}
    agent = Agent(run_id=run_id, profile=profile, inputs=inputs, emit=printer(args.client[:18]), labels=labels)
    out = await agent.run()
    rdir = REPO_ROOT / ".local-runs" / run_id
    rdir.mkdir(parents=True, exist_ok=True)
    for name, data in out.files.items():
        (rdir / name).write_bytes(data)
    for name, data in inputs.items():
        (rdir / f"in_{name}").write_bytes(data)
    meta = {"run_id": run_id, "client_id": args.client, "status": out.status, "error": out.error, "hashes": out.hashes,
            "steps": out.steps_json(), "memo": out.memo, "summary": out.summary, "tokens_in": out.tokens_in, "tokens_out": out.tokens_out}
    (rdir / "run.json").write_text(json.dumps(meta, indent=2))
    print(f"outputs in {rdir}")
    if out.memo:
        print("--- memo ---\n" + out.memo)
    if args.check and out.result:
        problems = check_against_expected(args.client, out.result)
        print("CHECK:", "PASS" if not problems else problems)
        return 0 if not problems else 1
    return 0 if out.status == "succeeded" else 1


async def cmd_replay(args) -> int:
    rdir = Path(args.run_dir)
    meta = json.loads((rdir / "run.json").read_text())
    inputs = {p.name.removeprefix("in_"): p.read_bytes() for p in rdir.glob("in_*")}
    res = await replay(steps=meta["steps"], inputs=inputs, emit=printer("replay"), labels={"arena.tenant": meta["client_id"]})
    same = {k: meta["hashes"].get(k) == v for k, v in res.hashes.items()}
    print("replay hashes match:", same)
    return 0 if res.ok and all(same.values()) and len(same) == len(meta["hashes"]) else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="tieout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--client", required=True)
    r.add_argument("--run-id")
    r.add_argument("--check", action="store_true")
    p = sub.add_parser("replay")
    p.add_argument("--run-dir", required=True)
    args = ap.parse_args()
    return asyncio.run(cmd_run(args) if args.cmd == "run" else cmd_replay(args))


if __name__ == "__main__":
    sys.exit(main())
