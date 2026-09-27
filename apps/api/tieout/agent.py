"""The reconciliation agent loop.

The control plane plans with the LLM (Vultr Serverless Inference) and
dispatches every action to the client's own sandbox through the runner. This
process never executes model-written code: it only writes the code into the
sandbox and asks the runner to run it there.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Awaitable, Callable

from tieout_lib.schema import validate_result

from .config import settings
from .llm import LLM
from .runner_client import RunnerClient, RunnerError

log = logging.getLogger("tieout.agent")

Emit = Callable[[str, dict], Awaitable[None]]
REQUIRED_OUTPUTS = ["result.json", "workpaper.xlsx", "ajes.csv", "lines.json"]
SANDBOX_LIMITS = {"cpus": 1.0, "memory_mb": 1024, "pids": 256, "exec_timeout_s": 60, "ttl_s": 900}
STDOUT_TO_MODEL = 8000
STDERR_TO_MODEL = 4000

TOOLS = [
    {"type": "function", "function": {
        "name": "sniff_file",
        "description": "Inspect one input CSV in /in (runs `python -m tieout_lib.sniff /in/<name>` in the sandbox) and return how to load it.",
        "parameters": {"type": "object", "properties": {
            "name": {"type": "string", "description": "File name in /in, e.g. bank_statement.csv"}}, "required": ["name"]}}},
    {"type": "function", "function": {
        "name": "run_python",
        "description": "Write the code to /work/step_<n>.py and run it in the sandbox (cwd /work, 60 s limit, no network). "
                       "Returns exit_code, stdout (first 8 KB), stderr tail and the files in /out.",
        "parameters": {"type": "object", "properties": {
            "purpose": {"type": "string", "description": "One short sentence: what this step does"},
            "code": {"type": "string", "description": "Complete Python script"}}, "required": ["purpose", "code"]}}},
    {"type": "function", "function": {
        "name": "finish",
        "description": "Finish the run. The control plane validates /out/result.json (schema, arithmetic, difference 0.00). "
                       "If it is invalid you get the errors back and should fix them.",
        "parameters": {"type": "object", "properties": {
            "summary": {"type": "string", "description": "One or two sentences for the dashboard"},
            "memo_markdown": {"type": "string", "description": "Reviewer memo in Markdown, 120 to 250 words"}},
            "required": ["summary", "memo_markdown"]}}},
]


@dataclass
class Step:
    n: int
    tool: str
    argv: list[str]
    purpose: str
    code: str | None = None
    script: str | None = None
    exit_code: int | None = None
    duration_ms: int | None = None
    timed_out: bool = False


class RunStopped(RuntimeError):
    """The admin kill switch or the daily budget ended the run."""


@dataclass
class AgentOutcome:
    status: str = "failed"
    recon_status: str | None = None
    result: dict | None = None
    memo: str | None = None
    summary: str | None = None
    files: dict[str, bytes] = field(default_factory=dict)
    hashes: dict[str, str] = field(default_factory=dict)
    steps: list[Step] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    llm_calls: int = 0
    model: str | None = None
    sandbox_id: str | None = None
    sandbox_host: str | None = None
    attestation: dict | None = None
    docker_summary: dict | None = None
    image_digest: str | None = None
    error: str | None = None

    def steps_json(self) -> list[dict]:
        return [asdict(s) for s in self.steps]


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_system_prompt() -> str:
    pdir = Path(settings.prompts_dir)
    tmpl = (pdir / "recon_system.md").read_text()
    api = (pdir / "tieout_lib_api.md").read_text()
    return tmpl.replace("{API_REFERENCE}", api)


def user_brief(profile: dict, inputs: dict[str, bytes]) -> str:
    files = "\n".join(f"- /in/{name} ({len(data):,} bytes)" for name, data in sorted(inputs.items()))
    return (
        f"Client: {profile['name']} (client_id {profile['client_id']}), {profile.get('industry', '')}.\n"
        f"Period: {profile['period']} ({profile['period_start']} to {profile['period_end']}). "
        f"Reconcile the bank account to general ledger cash account {profile.get('gl_cash_account', '1010')}. "
        f"Materiality: {profile.get('materiality', 'n/a')}.\n"
        f"Files:\n{files}\n"
        "Follow the workflow, write the outputs with write_outputs(), then call finish."
    )


def tidy_text(text: str) -> str:
    """House style for model-written text shown in the product: no em dashes."""
    text = re.sub(r"\s*\u2014\s*", ", ", text or "")
    text = re.sub(r"(?<=\d)\u2013(?=\d)", "-", text)
    return re.sub(r"\s*\u2013\s*", ", ", text)


def _clip(s: str, n: int, tail: bool = False) -> str:
    if len(s) <= n:
        return s
    return ("...[truncated]\n" + s[-n:]) if tail else (s[:n] + f"\n...[truncated {len(s) - n} chars]")


def _parse_json_action(text: str) -> tuple[str, dict] | None:
    """Fallback protocol: {"tool": "...", "args": {...}} as message content."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and isinstance(obj.get("tool"), str) and isinstance(obj.get("args", {}), dict):
        return obj["tool"], obj.get("args", {})
    return None


class Agent:
    def __init__(self, *, run_id: str, profile: dict, inputs: dict[str, bytes], emit: Emit, llm: LLM | None = None,
                 runner: RunnerClient | None = None, labels: dict | None = None,
                 should_stop: Callable[[], Awaitable[str | None]] | None = None, max_tool_calls: int | None = None,
                 run_timeout_s: int | None = None, start_events: list[tuple[str, dict]] | None = None):
        self.run_id = run_id
        self.profile = profile
        self.inputs = inputs
        self.emit = emit
        self.llm = llm or LLM()
        self.runner = runner or RunnerClient()
        self.labels = labels or {}
        self.should_stop = should_stop
        self.max_tool_calls = max_tool_calls or settings.max_tool_calls
        self.run_timeout_s = run_timeout_s or settings.run_timeout_s
        self.out = AgentOutcome(model=self.llm.model)
        self.start_events = start_events or []
        self.tool_calls = 0
        self.sid: str | None = None

    # ------------------------------------------------------------ sandbox
    async def _create_sandbox(self) -> None:
        sb = await self.runner.create(image=settings.sandbox_image, labels=self.labels, limits=SANDBOX_LIMITS, inputs=self.inputs)
        self.sid = sb["id"]
        self.out.sandbox_id = sb["id"]
        self.out.sandbox_host = sb.get("host")
        self.out.attestation = sb.get("attestation")
        self.out.docker_summary = sb.get("docker")
        self.out.image_digest = (sb.get("docker") or {}).get("ImageDigest")
        await self.emit("sandbox_created", {
            "sandbox_id": self.sid, "host": sb.get("host"), "attestation": sb.get("attestation"), "docker": sb.get("docker"),
            "limits": SANDBOX_LIMITS, "inputs": [{"name": k, "sha256": sha256(v), "bytes": len(v)} for k, v in sorted(self.inputs.items())],
        })

    async def _destroy_sandbox(self) -> None:
        if self.sid:
            try:
                await self.runner.delete(self.sid)
                await self.emit("sandbox_destroyed", {"sandbox_id": self.sid})
            except Exception as exc:  # the janitor will reap it on TTL
                log.warning("delete sandbox %s: %s", self.sid, exc)

    # --------------------------------------------------------------- tools
    async def tool_sniff(self, args: dict) -> dict:
        name = str(args.get("name", "")).strip().removeprefix("/in/")
        if name not in self.inputs:
            return {"error": f"unknown file {name!r}; files in /in: {sorted(self.inputs)}"}
        n = len(self.out.steps) + 1
        argv = ["python", "-m", "tieout_lib.sniff", f"/in/{name}"]
        step = Step(n=n, tool="sniff_file", argv=argv, purpose=f"Inspect {name}")
        res = await self.runner.exec(self.sid, argv, settings.exec_timeout_s)
        step.exit_code, step.duration_ms, step.timed_out = res["exit_code"], res["duration_ms"], res["timed_out"]
        self.out.steps.append(step)
        try:
            payload = json.loads(res["stdout"])
        except json.JSONDecodeError:
            payload = {"error": "sniff failed", "stderr": _clip(res["stderr"], STDERR_TO_MODEL, tail=True)}
        await self.emit("tool_result", {"n": n, "tool": "sniff_file", "exit_code": res["exit_code"], "duration_ms": res["duration_ms"],
                                        "stdout": _clip(res["stdout"], 12000), "stderr": _clip(res["stderr"], 2000, tail=True),
                                        "out_files": res.get("out_files", [])})
        return payload

    async def tool_python(self, args: dict) -> dict:
        code = str(args.get("code", ""))
        purpose = str(args.get("purpose", ""))[:300]
        if not code.strip():
            return {"error": "code is empty"}
        n = len(self.out.steps) + 1
        script = f"step_{n}.py"
        await self.runner.put_file(self.sid, script, code.encode())
        argv = ["python", f"/work/{script}"]
        step = Step(n=n, tool="run_python", argv=argv, purpose=purpose, code=code, script=script)
        res = await self.runner.exec(self.sid, argv, settings.exec_timeout_s)
        step.exit_code, step.duration_ms, step.timed_out = res["exit_code"], res["duration_ms"], res["timed_out"]
        self.out.steps.append(step)
        outs = res.get("out_files", [])
        await self.emit("tool_result", {"n": n, "tool": "run_python", "exit_code": res["exit_code"], "duration_ms": res["duration_ms"],
                                        "timed_out": res["timed_out"], "stdout": _clip(res["stdout"], 12000),
                                        "stderr": _clip(res["stderr"], 4000, tail=True), "out_files": outs,
                                        "rejected_out_files": res.get("rejected_out_files", [])})
        return {"exit_code": res["exit_code"], "duration_ms": res["duration_ms"], "timed_out": res["timed_out"],
                "stdout": _clip(res["stdout"], STDOUT_TO_MODEL), "stderr_tail": _clip(res["stderr"], STDERR_TO_MODEL, tail=True),
                "out_files": [f"{f['path']} ({f['size']} bytes)" for f in outs]}

    async def tool_finish(self, args: dict) -> tuple[bool, dict]:
        errors: list[str] = []
        try:
            raw = await self.runner.get_out(self.sid, "result.json")
        except RunnerError as exc:
            errs = [f"/out/result.json not found or unreadable ({exc.detail}). Run write_outputs() first."]
            await self.emit("validation", {"ok": False, "errors": errs})
            return False, {"ok": False, "errors": errs}
        res, errors = validate_result(raw)
        if res is not None:
            if res.client_id != self.profile["client_id"]:
                errors.append(f"client_id is {res.client_id!r}, expected {self.profile['client_id']!r}")
            if res.run_id != self.run_id:
                errors.append(f"run_id is {res.run_id!r}, expected {self.run_id!r} (write_outputs reads it from /in/run_context.json)")
            want = {k: sha256(v) for k, v in self.inputs.items()}
            got = {i.name: i.sha256 for i in res.inputs}
            if got != want:
                errors.append("inputs listed in result.json do not match the files in /in")
        files: dict[str, bytes] = {"result.json": raw}
        for name in REQUIRED_OUTPUTS[1:]:
            try:
                files[name] = await self.runner.get_out(self.sid, name)
            except RunnerError:
                errors.append(f"/out/{name} is missing: use write_outputs()")
        await self.emit("validation", {"ok": not errors, "errors": errors[:20]})
        if errors:
            return False, {"ok": False, "errors": errors[:20], "hint": "fix the problems, re-run write_outputs, then call finish again"}
        self.out.result = json.loads(raw)
        self.out.recon_status = res.status
        self.out.files = files
        self.out.hashes = {k: sha256(v) for k, v in files.items()}
        self.out.summary = tidy_text(str(args.get("summary", "")))[:500]
        self.out.memo = tidy_text(str(args.get("memo_markdown", "")))[:6000]
        return True, {"ok": True}

    # ---------------------------------------------------------------- loop
    async def _dispatch(self, name: str, args: dict) -> tuple[bool, dict]:
        self.tool_calls += 1
        n = len(self.out.steps) + 1
        await self.emit("tool_call", {"n": n if name != "finish" else None, "tool": name,
                                      "args": {k: (tidy_text(v)[:6000] if k in ("memo_markdown", "summary", "purpose") else v) for k, v in args.items()}})
        if name == "sniff_file":
            return False, await self.tool_sniff(args)
        if name == "run_python":
            return False, await self.tool_python(args)
        if name == "finish":
            return await self.tool_finish(args)
        return False, {"error": f"unknown tool {name!r}; use sniff_file, run_python or finish"}

    async def _loop(self) -> None:
        messages = [{"role": "system", "content": load_system_prompt()},
                    {"role": "user", "content": user_brief(self.profile, self.inputs)}]
        nudges = 0
        while True:
            if self.should_stop:
                reason = await self.should_stop()
                if reason:
                    raise RunStopped(reason)
            if self.tool_calls >= self.max_tool_calls:
                ok, _ = await self.tool_finish({"summary": "Tool budget reached", "memo_markdown": ""})
                if ok:
                    self.out.memo = self.out.memo or "The agent reached its tool budget after writing valid outputs."
                    return
                raise RuntimeError(f"tool budget of {self.max_tool_calls} calls reached without a valid result")
            reply = await self.llm.chat(messages, tools=TOOLS)
            self.out.llm_calls += 1
            self.out.tokens_in += reply.tokens_in
            self.out.tokens_out += reply.tokens_out
            self.out.model = reply.model
            msg = reply.message
            content = msg.content or ""
            await self.emit("llm", {"call": self.out.llm_calls, "model": reply.model, "tokens_in": reply.tokens_in,
                                    "tokens_out": reply.tokens_out, "latency_ms": reply.latency_ms, "finish_reason": reply.finish_reason})
            if content.strip() or reply.reasoning:
                await self.emit("thought", {"text": tidy_text(_clip(content.strip(), 3000)),
                                            "reasoning": tidy_text(_clip((reply.reasoning or "").strip(), 3000))})
            calls = msg.tool_calls or []
            if calls:
                messages.append({"role": "assistant", "content": content or None, "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls]})
                done = False
                for c in calls:
                    try:
                        args = json.loads(c.function.arguments or "{}")
                        if not isinstance(args, dict):
                            raise ValueError("arguments must be a JSON object")
                    except (json.JSONDecodeError, ValueError) as exc:
                        result, finished = {"error": f"invalid JSON arguments: {exc}"}, False
                    else:
                        finished, result = await self._dispatch(c.function.name, args)
                    messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result, default=str)})
                    done = done or finished
                if done:
                    return
                continue
            action = _parse_json_action(content)
            if action:
                name, args = action
                messages.append({"role": "assistant", "content": content})
                finished, result = await self._dispatch(name, args)
                if finished:
                    return
                messages.append({"role": "user", "content": f"Result of {name}:\n{json.dumps(result, default=str)}"})
                continue
            nudges += 1
            if nudges > 2:
                raise RuntimeError("the model stopped calling tools")
            messages.append({"role": "assistant", "content": content or "(no content)"})
            messages.append({"role": "user", "content": "Continue by calling exactly one tool: sniff_file, run_python or finish. "
                             'If native tool calls are unavailable, reply with only a JSON object {"tool": "<name>", "args": {...}}.'})

    async def run(self) -> AgentOutcome:
        t0 = time.monotonic()
        await self.emit("run_started", {"client_id": self.profile["client_id"], "model": self.llm.model,
                                        "fallback_model": self.llm.fallback_model, "max_tool_calls": self.max_tool_calls,
                                        "inputs": [{"name": k, "sha256": sha256(v), "bytes": len(v)} for k, v in sorted(self.inputs.items())]})
        for etype, payload in self.start_events:  # e.g. untrusted_text findings from the control plane scan
            await self.emit(etype, payload)
        try:
            await self._create_sandbox()
            await asyncio.wait_for(self._loop(), timeout=self.run_timeout_s)
            self.out.status = "succeeded"
        except asyncio.TimeoutError:
            self.out.error = f"run exceeded {self.run_timeout_s} s"
        except asyncio.CancelledError:  # only the kill switch (or a shutdown) cancels a run
            self.out.status, self.out.error = "stopped", "run cancelled"
            raise
        except RunStopped as exc:
            self.out.status, self.out.error = "stopped", str(exc)
        except Exception as exc:
            reason = await self.should_stop() if self.should_stop else None
            if reason:  # the kill switch (or budget) ended the run mid-step: a stop, not a failure
                self.out.status, self.out.error = "stopped", reason
            else:
                log.exception("run %s failed", self.run_id)
                self.out.error = str(exc)[:1000]
        finally:
            await self._destroy_sandbox()
            await self.emit("run_finished", {
                "status": self.out.status, "recon_status": self.out.recon_status, "error": self.out.error,
                "duration_ms": int((time.monotonic() - t0) * 1000), "tool_calls": self.tool_calls, "llm_calls": self.out.llm_calls,
                "tokens_in": self.out.tokens_in, "tokens_out": self.out.tokens_out, "hashes": self.out.hashes,
                "difference": (self.out.result or {}).get("difference"), "summary": self.out.summary,
            })
        return self.out


@dataclass
class ReplayOutcome:
    ok: bool
    hashes: dict[str, str]
    files: dict[str, bytes]
    attestation: dict | None
    docker_summary: dict | None
    sandbox_id: str | None
    sandbox_host: str | None
    error: str | None = None


async def replay(*, steps: list[dict], inputs: dict[str, bytes], emit: Emit, runner: RunnerClient | None = None,
                 labels: dict | None = None) -> ReplayOutcome:
    """Re-run every recorded step, in order, in a fresh sandbox with the same inputs. No LLM involved."""
    runner = runner or RunnerClient()
    sid = None
    try:
        sb = await runner.create(image=settings.sandbox_image, labels=labels or {}, limits=SANDBOX_LIMITS, inputs=inputs)
        sid = sb["id"]
        await emit("sandbox_created", {"sandbox_id": sid, "host": sb.get("host"), "attestation": sb.get("attestation"),
                                       "docker": sb.get("docker"), "limits": SANDBOX_LIMITS,
                                       "inputs": [{"name": k, "sha256": sha256(v), "bytes": len(v)} for k, v in sorted(inputs.items())]})
        for s in steps:
            if s.get("script") and s.get("code") is not None:
                await runner.put_file(sid, s["script"], s["code"].encode())
            res = await runner.exec(sid, s["argv"], settings.exec_timeout_s)
            await emit("replay_step", {"n": s["n"], "tool": s["tool"], "argv": s["argv"], "exit_code": res["exit_code"],
                                       "duration_ms": res["duration_ms"], "stdout": _clip(res["stdout"], 4000),
                                       "stderr": _clip(res["stderr"], 2000, tail=True)})
        files = {}
        for name in REQUIRED_OUTPUTS:
            try:
                files[name] = await runner.get_out(sid, name)
            except RunnerError:
                pass
        return ReplayOutcome(ok=True, hashes={k: sha256(v) for k, v in files.items()}, files=files, attestation=sb.get("attestation"),
                             docker_summary=sb.get("docker"), sandbox_id=sid, sandbox_host=sb.get("host"))
    except Exception as exc:
        log.exception("replay failed")
        return ReplayOutcome(ok=False, hashes={}, files={}, attestation=None, docker_summary=None, sandbox_id=sid, sandbox_host=None,
                             error=str(exc)[:1000])
    finally:
        if sid:
            try:
                await runner.delete(sid)
                await emit("sandbox_destroyed", {"sandbox_id": sid})
            except Exception:
                pass
