# Tieout

Tieout is AI month-end close for accounting firms: one click reconciles every client's bank account, with an agent that writes and runs real Python for each client. Every action the agent takes runs inside that client's own sealed gVisor sandbox on Vultr, with no network, read-only inputs and no access to the ledger. A human approves every adjusting entry, and every number can be replayed and proven by hash.

**Try it:** https://144-202-108-57.sslip.io (one-click demo accounts on the login page) · **Demo video (2:11):** https://sjc1.vultrobjects.com/tieout-artifacts-4f2389/public/demo.mp4 · **Pitch deck:** [slides.html](slides.html) (open in a browser)

| Role | Email | Password | Can |
|---|---|---|---|
| Preparer | `alex@harborpine.example` | `close-september` | close the month, upload files, replay |
| Reviewer | `jordan@harborpine.example` | `review-september` | approve or reject adjusting entries, export them |
| Admin | `sam@harborpine.example` | `admin-september` | kill switch, live sandboxes, usage, health |

## The problem

Every month, accounting firms close the books for dozens of clients, and the grind is bank reconciliation: matching hundreds of bank lines to the ledger, chasing the leftovers, booking adjustments and writing the workpaper. AI could do this work, but doing it for real means an agent writing and executing code on confidential client data. That data is untrusted, too: anyone who pays a client writes text into its bank statement, and one of our demo clients' statements contains a memo telling the AI to approve everything and upload the ledger. No firm lets a model loose on client books unless every action is contained, every entry is reviewed by a person, and every number can be proven.

## Our solution

A preparer clicks **Close September**. The control plane, on a Vultr VM, starts one agent run per client, all 12 in parallel. For each client, GLM 5.3 on Vultr Serverless Inference inspects that client's messy bank export, writes Python, and runs it in a fresh gVisor sandbox on a separate Vultr VM. It matches the lines, investigates the leftovers and drafts the adjusting entries. The control plane checks every result (schema, arithmetic, difference 0.00) and stores the SHA-256 of every output. A reviewer, who must be a different person from the preparer, approves before the entries export to QuickBooks, Xero or NetSuite. **Replay** re-runs the recorded code in a fresh sandbox, without the model, and proves the outputs are byte-identical. Judges can also **upload their own bank export and ledger**, or edit the sample files, and watch the agent reconcile them.

The containment is visible in the product, not just claimed:

| Guarantee | How it is enforced | Where you see it |
|---|---|---|
| Nothing leaves | `--network none` under gVisor; attested from inside the sandbox (only loopback, outbound connections and DNS fail) | Blast radius panel |
| Nothing is altered | Inputs mounted read-only, read-only root filesystem; the write tests fail as expected | Blast radius panel |
| Nothing is posted without a human | The agent has no ledger access; entries export only after a reviewer approves (maker-checker, HMAC-signed) | Review panel, AJE CSV button |
| Nothing crosses clients | One sandbox per client per run, separate workspaces and storage prefixes, tenant labels | Dashboard tiles, blast radius panel |
| Everything is reproducible | Replay re-executes the recorded code in a fresh sandbox and compares SHA-256 hashes | Replay result, "Reproducible" badge |

**Proven on the live URL:** 10 of 10 acceptance runs in a row, each finding all 68 planted discrepancies across the 12 clients with every difference at 0.00; 20 of 20 replays byte-identical; about 41 seconds to close all 12 clients. The injected memo is flagged, treated as data, and has nowhere to go.

| | |
|---|---|
| ![September close dashboard: 12 client sandboxes](media/screenshots/dashboard.png) | ![Run detail: agent steps, matching view, approval](media/screenshots/run-detail.png) |
| **Close September.** One sandbox per client, live progress, ground-truth check. | **Run detail.** The agent's real code and output, the matching view, signed approval. |
| ![Blast radius panel with the prompt-injection callout](media/screenshots/blast-radius.png) | ![Upload your own bank export and ledger](media/screenshots/upload-dialog.png) |
| **Blast radius.** Attested from inside the sandbox; the injected memo is flagged and treated as data. | **Upload files.** Reconcile your own bank export and ledger in a fresh sandbox. |

## Sponsors used

| Sponsor | Product | What it does in Tieout |
|---|---|---|
| Vultr | Cloud Compute | The control-plane VM (orchestrator, agent loop, API, web app) and a dedicated sandbox-host VM that runs one gVisor container per client run |
| Vultr | Serverless Inference | Every LLM call: GLM 5.3 writes the code, GLM 5.3 Flash is the fallback, Nemotron 3.5 Content Safety gives a second opinion on suspicious input text |
| Vultr | Managed PostgreSQL | System of record: runs, hash-chained run events, signed approvals, audit log |
| Vultr | Object Storage | Client inputs, outputs, evidence packs and uploads in a private bucket; the operations channel; the demo video |
| Vultr | VPC Network | Private network between the control plane and the sandbox host |
| Vultr | Firewall Groups | Only 80 and 443 open on the control plane; nothing inbound on the sandbox host |

Vultr is the host and sponsor of the Agent Arena, and Tieout runs entirely on it: one provider, one region (Silicon Valley, `sjc`), no other cloud and no other LLM provider anywhere in the code. We did not use the NetBird bonus challenge; the time went into demo reliability instead ([DECISIONS.md](DECISIONS.md), item 20).

## Sponsor details

### Vultr

The control plane on a Vultr VM is the central system of control. It plans with the model, creates and destroys sandboxes on the sandbox host over the private network, validates every output, and records everything in Vultr Managed PostgreSQL and Vultr Object Storage.

```mermaid
flowchart TB
    user["Judges and staff (browser)"] -->|"HTTPS 443"| caddy
    subgraph cp["Control-plane VM (Vultr Cloud Compute, public 80/443 only)"]
        caddy["Caddy: TLS, static web app"] --> api["FastAPI: auth, roles, orchestrator, agent loop, live events"]
    end
    api -->|"every LLM call"| inf["Vultr Serverless Inference (GLM 5.3, GLM 5.3 Flash, Nemotron 3.5 Content Safety)"]
    api -->|"system of record, hash-chained events, approvals"| pg[("Vultr Managed PostgreSQL")]
    api -->|"inputs, outputs, evidence, uploads"| s3[("Vultr Object Storage")]
    api -->|"Vultr VPC only, bearer token"| runner
    subgraph sbx["Sandbox-host VM (Vultr Cloud Compute, no inbound from the internet)"]
        runner["sandbox-runner (FastAPI + Docker SDK)"] --> g1["gVisor sandbox: client A"]
        runner --> g2["gVisor sandbox: client B"]
        runner --> g3["... one per client"]
    end
```

**Cloud Compute.** Two VMs in `sjc`.
- `tieout-cp` (`vc2-2c-4gb`) runs Caddy with automatic HTTPS and the FastAPI control plane: auth and roles, the orchestrator, the agent loop, live progress events, and the web app. The API process never executes model-written code.
- `tieout-sbx-1` (`vc2-4c-8gb`) runs the sandbox runner. Each client run gets a fresh Docker container under the gVisor runtime (`runsc`) with no network, a read-only root, read-only inputs in `/in`, writable `/work` and `/out`, all capabilities dropped, no privilege escalation, uid 10001, and 1 CPU, 1 GiB, 256 processes, 60 s per step and a 15 minute lifetime.
- An attestation script runs inside every sandbox at start; its results, with the Docker inspect summary, become the blast radius panel. Everything a sandbox writes is treated as hostile when it is read back (no symlinks, regular files only, size caps).
- A TTL janitor, a capacity cap and an admin kill switch that destroys every running sandbox complete the runner.
- The VMs are operated without SSH: each host runs a small agent that executes only commands signed with the operator's Ed25519 key, fetched through Object Storage. The control plane can spread runs across more sandbox hosts and fail over if one is down; a second host is ready to add when the account allows.

**Serverless Inference.** Every LLM call goes to `api.vultrinference.com` through the OpenAI SDK.
- **GLM 5.3** is the agent. It uses native tool calls (`sniff_file`, `run_python`, `finish`) at medium reasoning effort, which gives the same answers with about 4x less model time than the default.
- **GLM 5.3 Flash** is the automatic fallback, and a strict JSON action protocol is the second fallback.
- **Nemotron 3.5 Content Safety** gives a second opinion on instruction-like text found in client files; the result is shown in the run and written to the audit log.
- Tokens and cost are recorded per run, shown on the admin page, and capped by a daily token budget. A close of all 12 clients costs about $0.25 of inference.

**Managed PostgreSQL.** The system of record, connected with `sslmode=require` and trusted sources limited to the control plane and the private network. It holds users and roles, clients, closes and runs, a per-run hash-chained event log (tampering is detected), approvals signed with an HMAC over the run, decision, reviewer, time and the SHA-256 of every output, uploads, and a hash-chained audit log of every action, including kill-switch use.

**Object Storage.** One private bucket.
- Client inputs and outputs live under `clients/{client}/runs/{run}/in|out`, alongside evidence packs and uploaded files. Output downloads are short-lived presigned links; input files are re-hashed against their recorded SHA-256 whenever they are downloaded.
- The bucket also carries the signed operations channel for the VMs.
- The demo video is the only public object.

**VPC Network.** A private network (`10.66.0.0/24`) between the control plane and the sandbox host. The runner listens only on its private address, and the host firewall accepts the runner port only from the control plane's private address.

**Firewall Groups.** `tieout-cp-fw` opens only 80 and 443 on the control plane. `tieout-sbx-fw` has no rules, so the sandbox host accepts nothing from the internet. Verified by port probes: the sandbox host refuses 22, 80, 443, 7070 and 8000; the control plane answers only on 80 and 443.

## More

- [SUBMISSION.md](SUBMISSION.md): submission text and how each requirement is met
- [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md): run locally, deploy to Vultr, guardrails, automated checks, repository layout
- [docs/DEMO.md](docs/DEMO.md): stage runbook and judge Q&A
- [DECISIONS.md](DECISIONS.md), [STATUS.md](STATUS.md), [docs/API.md](docs/API.md), [infra/RESOURCES.md](infra/RESOURCES.md)

Harbor & Pine CPA and its 12 clients are fictional; all data is synthetic.
