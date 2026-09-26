# Submission: Tieout

**Project name:** Tieout

**One-line pitch:** AI month-end close for accounting firms, where every client's books are reconciled by an agent running in its own sealed gVisor sandbox on Vultr.

**Problem statement addressed:** 1. Blast Radius Zero: Safe Agent Execution on Vultr (it also fits 2. Future of Work: an enterprise AI workflow for accounting firms).

## Description (about 250 words)

Accounting firms close the books for dozens of clients every month, and the grind is bank reconciliation: matching hundreds of bank lines to the ledger, chasing leftovers, booking adjustments and writing the workpaper. AI could do it, but no firm lets a model run code on client data unless it is contained, reviewable and provable.

Tieout is that control layer. A preparer clicks "Close September" and the orchestrator on a Vultr VM starts one run per client, in parallel. For each client the runner creates a fresh gVisor container on a separate sandbox host: no network, read-only inputs, read-only root, no capabilities, non-root, strict CPU, memory and time limits. The agent (GLM 5.3 on Vultr Serverless Inference) inspects that client's messy bank export, writes Python, runs it in the sandbox, investigates the leftovers and drafts adjusting entries. Every number comes from executed code, validated by the control plane; the reconciliation ties to 0.00.

The containment is visible, not claimed: each run shows an attestation produced inside the sandbox (only loopback, outbound connection refused, write tests), the Docker inspect summary, the files it could read and the files that left, with SHA-256 hashes. One client's bank memo contains a prompt injection aimed at the AI; the agent treats it as data and the sandbox had nowhere to send anything anyway.

A reviewer approves every entry (maker-checker) before the AJE file exports for QuickBooks, Xero or NetSuite. Replay re-runs the recorded code in a fresh sandbox and proves the outputs are identical by hash. Every event is stored in a hash chain in Vultr Managed PostgreSQL; artifacts live in Vultr Object Storage.

## How each mandatory requirement is met

| Requirement | How Tieout meets it |
|---|---|
| Web-based agent doing real work | The agent writes and executes Python that reconciles real (synthetic) bank and ledger files and produces a workpaper, AJE file and result.json |
| Every action contained in a sandbox on Vultr | Every tool call runs in a per-client gVisor container (`--network none`, read-only root and inputs, no capabilities, uid 10001, 1 CPU, 1 GiB, 60 s per step) on a dedicated sandbox-host VM |
| Centralized control layer: plan, dispatch, verifiable output | The control plane plans with the LLM, dispatches each step to the runner over the private VPC, validates outputs (schema, arithmetic, input hashes) and stores hashes; Replay verifies |
| Multi-step agentic workflow | Inspect bank file, inspect ledger file, load and match, investigate leftovers, classify and write outputs, finish; errors from validation go back to the model |
| Real executed results | Outputs are files produced by executed code, downloadable with their SHA-256 |
| Production-style web app | Login, roles (preparer, reviewer, admin), maker-checker approvals, hash-chained audit log, HTTPS, rate limits, kill switch, admin and health pages |
| VM-based backend on Vultr (mandatory) | Control plane on a Vultr Cloud Compute VM (Caddy + FastAPI) |
| LLM calls via Vultr Serverless Inference (mandatory) | Every LLM call goes to `api.vultrinference.com` (GLM 5.3, GLM 5.3 Flash fallback); no other LLM provider exists in the code |
| Vultr as the central system of control and record | The control plane creates and destroys sandboxes; Vultr Managed PostgreSQL is the system of record; Vultr Object Storage holds inputs, outputs and evidence |
| Sandboxes never inside the app process | The API never executes model-written code; sandboxes are gVisor containers on a separate VM reachable only over the VPC |

## Vultr products used

Cloud Compute (control-plane VM and sandbox-host VM), VPC Network, Firewall Groups, Serverless Inference (GLM 5.3, GLM 5.3 Flash, text-to-speech for the demo video narration), Managed Databases for PostgreSQL, Object Storage.

## Links

- Public URL: _(see STATUS.md; updated at deploy)_
- Repository: https://github.com/chinesepowered/hack-vultracc
- Demo video: _(Object Storage link added after recording)_

## Demo accounts

| Role | Email | Password |
|---|---|---|
| Preparer | alex@harborpine.example | close-september |
| Reviewer | jordan@harborpine.example | review-september |
| Admin | sam@harborpine.example | admin-september |
