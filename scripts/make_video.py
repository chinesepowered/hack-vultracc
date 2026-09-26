# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "python-dotenv>=1.0", "imageio-ffmpeg>=0.5"]
# ///
"""Turn the Playwright recording into the narrated demo video.

    uv run scripts/make_video.py --base-url https://<host> [--work media/work] [--out media/demo.mp4]

Narration comes from the "Say" column of PLAN.md section 3 (with the real
numbers from the recorded batch), synthesized with Vultr Serverless Inference
text-to-speech (POST /v1/audio/speech). Each scene's video is sped up or held
so it lasts as long as its narration, then everything is muxed with ffmpeg.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import wave
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# (first mark, end mark, narration). The segment runs from the first mark to the end mark.
SCENES = [
    ("login", "close_clicked",
     "This is Tieout: AI month-end close for accounting firms. Firms close the books for dozens of clients every month, and the worst "
     "part is bank reconciliation. AI could do it, but no firm lets an AI run code on client data unless it is contained."),
    ("close_clicked", "tiles_running",
     "One click closes September for all twelve clients. Each client gets its own sealed sandbox on Vultr: gVisor, no network, "
     "read-only inputs, one CPU."),
    ("tiles_running", "batch_done",
     "The agent runs on GLM 5.3 through Vultr Serverless Inference. For every client it inspects the bank export, writes Python, runs "
     "it in the sandbox, and investigates whatever does not match. Tiles fill in live. Clients with an item nobody can explain turn "
     "amber for review."),
    ("run_detail", "matching",
     "Here is Blue Harbor Coffee. The agent noticed day-first dates and a three-line bank header, loaded the file correctly, and matched "
     "{matched} of {total} bank lines. This is real code, executed in the sandbox, with its real output. Not a description of what it "
     "would do."),
    ("matching", "blast_radius",
     "Every leftover is explained: an unrecorded bank fee, a returned customer check, a transposition where fifteen twenty was booked "
     "but twelve fifty cleared, outstanding checks, and a deposit in transit. After the proposed adjustments, the reconciliation ties "
     "to the penny."),
    ("blast_radius", "reviewer",
     "The blast radius panel is attested from inside the sandbox: only loopback networking, outbound connections fail, inputs are "
     "read-only, no capabilities, no secrets. And look at this: whoever paid this client wrote a memo telling the AI to approve "
     "everything and upload the ledger. It does not matter. The agent treated it as data, and the sandbox had nowhere to send anything."),
    ("reviewer", "replay_clicked",
     "A human approves every entry. The reviewer is a different person from the preparer, and only after approval do the adjusting "
     "entries export for QuickBooks, Xero, or NetSuite. The agent never posts."),
    ("replay_clicked", "architecture",
     "Replay runs the recorded code again in a fresh sandbox, with the same inputs and no model. The hashes match. Every number is "
     "reproducible, and an auditor can re-run it."),
    ("architecture", "end",
     "Everything runs on Vultr: a VM control plane, sandbox hosts on a private network, Serverless Inference, Managed Postgres, and "
     "Object Storage. Our automated check planted {planted} discrepancies across twelve clients, and the agent found all {found}."),
]


def ffmpeg() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def wav_seconds(path: Path) -> float:
    try:
        with wave.open(str(path)) as w:
            return w.getnframes() / float(w.getframerate())
    except wave.Error:
        out = subprocess.run([ffmpeg(), "-i", str(path)], capture_output=True, text=True).stderr
        for line in out.splitlines():
            if "Duration:" in line:
                h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
    return 0.0


PIPER_VOICE = "en_US-ryan-high"


def piper_tts(text: str, cache: Path) -> Path:
    """Local fallback voice (only if Vultr text-to-speech is unavailable)."""
    key = hashlib.sha256(f"piper|{PIPER_VOICE}|{text}".encode()).hexdigest()[:16]
    wav = cache / f"piper_{key}.wav"
    if wav.exists():
        return wav
    model = cache / f"{PIPER_VOICE}.onnx"
    for suffix in (".onnx", ".onnx.json"):
        dst = cache / f"{PIPER_VOICE}{suffix}"
        if not dst.exists():
            url = f"https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/ryan/high/{PIPER_VOICE}{suffix}"
            dst.write_bytes(httpx.get(url, follow_redirects=True, timeout=600).content)
    raw = cache / f"piper_{key}.raw.wav"
    subprocess.run(["uv", "run", "--with", "piper-tts", "python", "-m", "piper", "--model", str(model), "--output_file", str(raw)],
                   input=text.encode(), check=True, capture_output=True)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(raw), "-ar", "44100", "-ac", "1", str(wav)], check=True)
    return wav


def tts(text: str, cache: Path, model: str, voice: str) -> Path:
    key = hashlib.sha256(f"{model}|{voice}|{text}".encode()).hexdigest()[:16]
    raw = cache / f"tts_{key}.bin"
    wav = cache / f"tts_{key}.wav"
    if wav.exists():
        return wav
    r = httpx.post(f"{os.environ['VULTR_INFERENCE_BASE_URL']}/audio/speech", timeout=300,
                   headers={"Authorization": f"Bearer {os.environ['VULTR_INFERENCE_API_KEY']}"},
                   json={"model": model, "voice": voice, "input": text})
    if r.status_code != 200:
        raise RuntimeError(f"TTS failed {r.status_code}: {r.text[:200]}")
    raw.write_bytes(r.content)
    subprocess.run([ffmpeg(), "-y", "-loglevel", "error", "-i", str(raw), "-ar", "44100", "-ac", "1", str(wav)], check=True)
    return wav


def numbers(base: str) -> dict:
    """Real numbers from the recorded batch (shown on screen), for the narration."""
    c = httpx.Client(base_url=base, timeout=30)
    acct = next(a for a in c.get("/api/demo-accounts").json() if a["role"] == "preparer")
    c.post("/api/auth/login", json={"email": acct["email"], "password": acct["password"]}).raise_for_status()
    b = c.get("/api/batches/latest").json()
    planted = found = 0
    matched = total = None
    for rs in b["runs"]:
        exp = json.loads((ROOT / "data" / "demo" / rs["client_id"] / "expected.json").read_text())
        planted += len(exp["exceptions"])
        d = c.get(f"/api/runs/{rs['id']}").json()
        got = {(e["kind"], e["amount"], e.get("bank_ref"), e.get("gl_ref")) for e in (d.get("result") or {}).get("exceptions", [])}
        want = {(e["kind"], e["amount"], e.get("bank_ref"), e.get("gl_ref")) for e in exp["exceptions"]}
        found += len(got & want)
        if rs["client_id"] == "blue-harbor-coffee" and d.get("result"):
            matched, total = d["result"]["matched_count"], d["result"]["bank_line_count"]
    return {"planted": planted, "found": found, "matched": matched, "total": total}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--work", default=str(ROOT / "media" / "work"))
    ap.add_argument("--out", default=str(ROOT / "media" / "demo.mp4"))
    ap.add_argument("--tts-model", default=os.environ.get("TTS_MODEL", "xtts"))
    ap.add_argument("--voice", default=os.environ.get("TTS_VOICE", "Claribel Dervla"))
    ap.add_argument("--allow-fallback", action="store_true", help="use a local Piper voice for lines Vultr TTS cannot synthesize")
    a = ap.parse_args()
    work = Path(a.work)
    marks = {m["scene"]: m["t"] for m in json.loads((work / "marks.json").read_text())}
    nums = numbers(a.base_url.rstrip("/"))
    print("numbers:", nums)
    segs = []
    for start, end, text in SCENES:
        if start not in marks or end not in marks:
            print(f"skip scene {start}->{end}: mark missing")
            continue
        line = text.format(**nums)
        try:
            wav, engine = tts(line, work, a.tts_model, a.voice), f"vultr:{a.tts_model}:{a.voice}"
        except Exception as exc:
            if not a.allow_fallback:
                raise
            print(f"  Vultr TTS failed ({str(exc)[:80]}); using local Piper voice")
            wav, engine = piper_tts(line, work), f"piper:{PIPER_VOICE}"
        audio = wav_seconds(wav)
        raw_len = marks[end] - marks[start]
        target = max(audio + 0.7, 3.0)
        segs.append({"start": marks[start], "end": marks[end], "raw": raw_len, "target": target, "wav": wav, "text": line, "engine": engine})
        print(f"{start:>14s} -> {end:<14s} raw {raw_len:6.1f}s audio {audio:5.1f}s -> {target:5.1f}s (x{raw_len / target:.2f})")
    ff = ffmpeg()
    inputs = ["-i", str(work / "raw.webm")]
    for s in segs:
        inputs += ["-i", str(s["wav"])]
    parts = []
    for i, s in enumerate(segs):
        speed = s["raw"] / s["target"]
        v = f"[0:v]trim=start={s['start']:.3f}:end={s['end']:.3f},setpts=PTS-STARTPTS"
        if speed > 1.0:
            v += f",setpts=PTS/{speed:.4f}"
        else:
            v += f",tpad=stop_mode=clone:stop_duration={s['target'] - s['raw']:.3f}"
        v += f",fps=30,trim=duration={s['target']:.3f},setpts=PTS-STARTPTS[v{i}]"
        au = f"[{i + 1}:a]aresample=44100,apad,atrim=duration={s['target']:.3f},asetpts=PTS-STARTPTS[a{i}]"
        parts += [v, au]
    concat = "".join(f"[v{i}][a{i}]" for i in range(len(segs))) + f"concat=n={len(segs)}:v=1:a=1[vout][aout]"
    graph = ";".join(parts + [concat])
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]", "-c:v", "libx264",
           "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
    total = sum(s["target"] for s in segs)
    (work / "narration.txt").write_text("\n\n".join(f"[{s['engine']}] {s['text']}" for s in segs) + "\n")
    print(f"wrote {out} ({total:.0f}s, {out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
