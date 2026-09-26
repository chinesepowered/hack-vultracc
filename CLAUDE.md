# CLAUDE.md: Tieout (hack-vultracc)

This repo is our entry for the Vultr "Agent Arena" hackathon: **Tieout**, AI month-end close for accounting firms. An agent reconciles each client's bank account by writing and running real Python inside that client's own sealed sandbox on Vultr (no network, read-only inputs, no access to the ledger). A human approves every adjustment, and every number can be replayed and verified.

- What to build and how: **PLAN.md**. Read it fully before writing code.
- Hackathon requirements, Vultr platform facts, the sandbox design, and house rules are below. They are binding.
- Problem statement: #1 "Blast Radius Zero". All of its mandatory requirements apply.

## Priorities (in order)
1. A polished demo that does not break on stage. Boring is fine.
2. The containment story ("why does this need a sandbox?") is visible in the UI, not just claimed.
3. Enterprise realism: it should feel like software an accounting firm would buy.
4. Everything else.

## Stack (decided)
- Backend: Python 3.12, FastAPI, SQLAlchemy 2, Postgres (Vultr Managed), boto3 (Vultr Object Storage), `openai` SDK pointed at Vultr Serverless Inference, SSE for live updates. Managed with uv.
- Frontend: Vite, React, TypeScript, Tailwind, shadcn/ui. Managed with pnpm. Built to static files and served by Caddy.
- Sandbox runner: Python FastAPI plus the Docker SDK on the sandbox-host VM, gVisor runtime.
- Deploy: Docker Compose on the control-plane VM (Caddy, API). Runner as a systemd service or Compose on the sandbox host.

## House rules

- Python: use uv (never pip or poetry). Node: use pnpm.
- No em dashes in any writing: docs, UI copy, commit messages, slides.
- Never add Claude or any AI as a co-author on commits or PRs.
- Never commit secrets. The API keys and model IDs are already in `.env` (gitignored). Keep `.env.example` current with variable names only, never values.
- Do not create, resize, or delete paid Vultr resources without explicit human approval. Any script that touches the Vultr API must print what it will do and require a `--yes` flag.
- Another agent is building a different hackathon project on the same Vultr account at the same time, with the same API keys. Every Vultr resource you create must have a label starting with `tieout-` and the tag `tieout`. Never modify or delete a Vultr resource that lacks both, even if it looks unused. Never regenerate or change any API key.
- Reliability beats features. The demo must not break on stage. Every user-visible feature needs a scripted end-to-end check.
- When a Vultr fact matters, check the docs (see "Vultr platform notes") instead of guessing.
- Build the P0 demo path end to end first. No P1 work until P0 runs on Vultr behind the public URL.

## Hackathon: Vultr "The Agent Arena"

- Event page: https://cerebralvalley.ai/e/vultr-the-agent-arena
- When: Sat Sep 26, 2026 9:00 AM to Sun Sep 27, 2026 5:00 PM PDT (32 hours, in person, San Francisco).
- Hard deadline: Sep 27, 5:00 PM PDT. Feature freeze around 12:00 PM PDT on Sep 27, then polish, record a backup demo video, and rehearse.
- Teams of up to 4. Prizes: more than $10,000 across cash and credits. Host: Vultr.
- Event focus (from the event page): building infrastructure for autonomous agents, with emphasis on VM backends, serverless inference, and the compute layer agents run on.
- All projects are judged in ONE pool, regardless of problem statement.

What we heard from Vultr (not in the written guide):
- They strongly prefer real enterprise use cases.
- They gave an on-site demo about sandboxes for security and limiting blast radius. Expect judges to ask "why does this need a sandbox?" and to reward a crisp, visible containment story.
- Expect to need a publicly accessible URL for judging.

Unknown (check the participant guide or ask the organizers before the deadline): judging criteria and weights, submission format, where and when to submit. Prepare the usual: public URL, repo link, 2 to 3 minute demo video, short write-up, architecture diagram.

Team decision: the NetBird bonus has no cash prize, so it is the LAST priority.

### Participant guide: requirements (verbatim)

> **1. Blast Radius Zero: Safe Agent Execution on Vultr**
>
> Build a web-based agent that performs real work - writing and running code, or operating a real browser - with every action contained inside a sandbox running on Vultr. Your system should act as a centralized control layer that plans a task, dispatches it to an isolated execution environment, and returns verifiable output.
>
> Projects should demonstrate multi-step agentic workflows, real executed results rather than described ones, and a production-style web application - all running on Vultr infrastructure.
>
> Containment-first is required. An agent that only chats is a demo; an agent that executes safely is a product.
>
> - Deploy a VM-based backend on Vultr (mandatory)
> - Agent LLM calls must go through Vultr Serverless Inference (mandatory)
> - Vultr should be the central system of control and orchestration, not just static hosting
> - Sandboxes run as containers or throwaway instances on Vultr, never inside your app process
>   - Open Source Sandbox example solutions: OpenSandbox (https://github.com/opensandbox-group/OpenSandbox), gVisor (https://gvisor.dev/), E2B Sandboxes (https://github.com/e2b-dev/e2b)

> **2. Future of Work: AI + Robotics on Vultr**
>
> Build and deploy a web-based, enterprise-focused AI solution on Vultr infrastructure.
>
> Projects should demonstrate multi-step, agentic or rule-based workflows, realistic future-of-work use cases, and a production-style web application - all running on Vultr infrastructure.
>
> - Deploy a VM-based backend on Vultr (mandatory)
> - Vultr should be used as the central system of record and control, not just for static hosting
> - Vultr Serverless Inference is optional for agentic or reasoning workflows

> **3. Bonus Challenge - Zero-Port Access with NetBird**
>
> Serve your project through NetBird's reverse proxy instead of opening ports on your Vultr VM, and earn bonus points on top of your challenge score.
>
> NetBird terminates TLS and routes public traffic down a WireGuard tunnel to a local port- so your app is reachable in a browser while your VM keeps every inbound port closed. Self-host the management server on Vultr and the whole path stays on your own infrastructure.
>
> Earning the Bonus
> - No open ports- your public demo URL is served through NetBird, with no inbound application ports on the VM
> - Gated access- the service sits behind SSO, password, PIN, or header auth, matched to a real user role
> - Lifecycle-bound URLs- URLs are provisioned per task or session and expire with the workload that created them

### Compliance checklist (every row must be true at demo time)

| Requirement | How we meet it | How judges see it |
|---|---|---|
| Web-based agent doing real work | Agent writes and runs real code (details in PLAN.md) | Live run in the web app |
| Every action contained in a sandbox on Vultr | gVisor containers on a separate sandbox-host VM | "Blast radius" panel with attestation |
| Centralized control layer: plan, dispatch, verifiable output | Orchestrator on the control-plane VM | Step timeline, output hashes, replay or re-verification |
| Multi-step agentic workflow | Plan, write code, run, observe, repair, finish | Step timeline |
| Real executed results, not described ones | Every result is a file produced by executed code | Download artifacts, hashes |
| Production-style web app | Auth, roles, audit log, HTTPS, error states, admin page | Login and role switch in the demo |
| VM-based backend on Vultr (mandatory) | Control plane runs on a Vultr Cloud Compute VM | Architecture slide, Vultr console |
| LLM calls via Vultr Serverless Inference (mandatory) | Every LLM call goes to api.vultrinference.com; no other LLM provider anywhere in the code | Usage panel, code search |
| Vultr as central system of control and record | Control plane creates and destroys sandboxes; Vultr Managed PostgreSQL is the system of record; artifacts in Vultr Object Storage | Architecture slide |
| Sandboxes never inside the app process | API process never executes model-written code | Architecture slide, attestation |
| Real enterprise use case | See PLAN.md | Pitch |
| Public URL | Caddy with HTTPS on the control-plane VM | Judges open it |
| (Bonus, last) NetBird | Only if everything else is done | |

## Vultr platform notes (checked 2026-09-26)

### Finding docs
- Full doc index for LLMs: https://docs.vultr.com/llms.txt
- Any doc page is available as raw markdown by appending `.md`, e.g. https://docs.vultr.com/products/compute/serverless-inference/management/usage/chat.md. Use curl and grep on these.
- Account API reference: https://www.vultr.com/api/ (base `https://api.vultr.com/v2`, header `Authorization: Bearer $VULTR_API_KEY`).
- Serverless Inference API reference: https://api.vultrinference.com/

### Region
Use Silicon Valley (`sjc`) for everything, since the event is in San Francisco. Object Storage hostname there: `sjc1.vultrobjects.com`. If a product is unavailable in `sjc`, use `lax` or `sea` and note it in the README.

### Serverless Inference (mandatory for all LLM calls)
- Already provisioned for this team; the key is in `.env`. Do not create another subscription. For reference, provisioning is: Console, Products, Serverless, Inference, Add Serverless Inference. Or `POST https://api.vultr.com/v2/inference` with `{"label": "..."}`, or `vultr-cli inference create --label ...`.
- The subscription has its own API key, separate from the account API key. Find it on the subscription's Overview tab or via `GET https://api.vultr.com/v2/inference/{id}`.
- Base URL `https://api.vultrinference.com/v1`, header `Authorization: Bearer $VULTR_INFERENCE_API_KEY`. OpenAI-compatible: use the official `openai` Python SDK with `base_url` pointed here.
- Endpoints: `POST /v1/chat/completions` (tools, streaming), `POST /v1/chat/completions/RAG`, `POST /v1/messages`, `POST /v1/responses`, `POST /v1/rerank`, `POST /v1/audio/speech`, `GET /v1/audio/voices`, `POST /v1/images/generations`, vector store CRUD under `/v1/vector_store`, `GET /v1/models`, `GET /v1/usage`, `GET /v1/health`.
- Models available on our account (display name, $ per million tokens input / output):
  - BGE M3 ($0.05 / $0.00)
  - DeepSeek V4 Flash 0731 ($0.10 / $0.25)
  - DeepSeek V4.1 Flash ($0.15 / $0.60)
  - GLM 5.2 ($0.75 / $3.00)
  - GLM 5.3 ($0.75 / $3.00)
  - GLM 5.3 Flash ($0.10 / $0.35)
  - GLM 5 ($0.40 / $1.75)
  - Laguna S 2.1 ($0.09 / $0.18)
  - MiMo V2.6 Flash RL ($0.10 / $0.25)
  - MiMo V2.6 Pro RL ($0.40 / $0.80)
  - MiniMax M3 ($0.20 / $0.90)
  - Muse Glimmer 30B ($0.25 / $1.00)
  - Nemotron 3 Nano Omni ($0.10 / $0.25)
  - Nemotron 3.5 Content Safety ($0.05 / $0.15)
  - Qwen 3.8 27B ($0.15 / $1.00)
  - Qwen 3.8 Flash Next ($0.10 / $0.20)
  - Vultron Retriever Core 4.5B ($0.10 / $0.00)
  - Vultron Retriever Flash 0.8B ($0.05 / $0.00)
  - Z-Image Turbo ($0.00 / $0.00)
- Exact model IDs (from `GET /v1/models`, 2026-09-26): `glm-5.3`, `glm-5.3-flash`, `glm-5.2`, `glm-5.x-menthol` (GLM 5), `qwen3.8-27b`, `qwen3.8-flash-next`, `nemotron-3.5-content-safety`, `nemotron-3-nano-omni-30b-a3b-reasoning`, `deepseek-v4-flash-0731`, `deepseek-v4.1-flash`, `minimax-m3`, `mimo-v2.6-flash-rl`, `mimo-v2.6-pro-rl`, `muse-glimmer-30b`, `laguna-s-2.1`, `bge-reranker-v2-m3` (BGE M3), `vultron-retriever-core-qwen3.5-4.5b`, `vultron-retriever-flash-qwen3.5-0.8b`, `z-image-turbo`. Read them from env vars (already set in `.env`); never hardcode them in code.
- Roles: GLM 5.3 is the main agent model (tool calls, coding). GLM 5.3 Flash for fast, cheap inner loops. Qwen 3.8 27B is multimodal (images, screenshots, video frames). Nemotron 3.5 Content Safety is a guardrail classifier (verify its input and output format before relying on it). BGE M3 and Vultron Retriever for embeddings and reranking. Z-Image Turbo for image generation.
- The Vultr docs say tool calling only works on `kimi-k2-instruct`. That is outdated. Verified on 2026-09-26: `glm-5.3` returns standard OpenAI-style `tool_calls` with `finish_reason: "tool_calls"`. It is a reasoning model that spends reasoning tokens before answering, so set `max_tokens` generously (4096 or more) or replies can come back truncated. Keep a tiny `scripts/smoke_inference.py` to re-check at the start of each session, and build the agent loop so it can fall back to a strict JSON action protocol (the model returns `{"tool": "...", "args": {...}}` as message content, validated with pydantic, one retry on parse failure) if native tool calls misbehave.
- Snippet:
  ```python
  import os
  from openai import OpenAI

  client = OpenAI(
      base_url=os.environ["VULTR_INFERENCE_BASE_URL"],  # https://api.vultrinference.com/v1
      api_key=os.environ["VULTR_INFERENCE_API_KEY"],
  )
  resp = client.chat.completions.create(
      model=os.environ["LLM_MODEL_MAIN"],
      messages=[{"role": "user", "content": "ping"}],
      tools=[...],
      tool_choice="auto",
      temperature=0.2,
  )
  ```
- Record token usage from every response's `usage` field per run. Show it in the admin page and enforce a daily token budget.

### Compute (VMs)
- Cloud Compute instances. Ubuntu 24.04 LTS x64 is `os_id` 2284. Plan codes look like `vc2-2c-4gb`; list current ones with `GET /v2/plans`.
- Create: `POST /v2/instances` with `region`, `plan`, `os_id` (or `snapshot_id`), `label`, `hostname`, plus optional tags, firewall group, VPC attachment, cloud-init `user_data` (base64), and SSH keys. Check exact field names on the Create Instance API page. Delete: `DELETE /v2/instances/{id}`. List: `GET /v2/instances`.
- Label every resource we create with the `tieout-` prefix and tag it `tieout`. Throwaway VMs also get the tag `ephemeral`. A janitor may only delete resources that carry both `tieout` and `ephemeral`.
- Instances can be private (no public IP) behind a NAT Gateway in a VPC. Good fit for sandbox hosts.
- Snapshots: once a sandbox host is set up (Docker, gVisor, runner, pre-pulled images), snapshot it so throwaway hosts boot ready.

### Networking
- VPC Network: private network between the control plane and the sandbox hosts, same region.
- Vultr firewall groups filter INBOUND traffic only. Control outbound traffic on the host (nftables or iptables) and in containers (`--network none`).
- Only the control-plane VM is public: ports 80 and 443, plus 22 restricted to admin IPs (or use the Vultr web console).

### Object Storage (S3-compatible)
- Console: Products, Cloud Storage, Object Storage. Credentials are `s3_hostname`, `s3_access_key`, `s3_secret_key` (console, or `GET /v2/object-storage`).
- Use boto3 with `endpoint_url="https://sjc1.vultrobjects.com"`. Keep buckets private; give the browser short-lived presigned URLs. If the browser fetches from the bucket directly, configure CORS (doc: products/storage/object-storage/advanced/cors).

### Managed PostgreSQL (system of record)
- Console: Databases, PostgreSQL, same region. Attach it to the VPC or restrict trusted sources to the control-plane VM. Connect with `sslmode=require`.

### Container Registry (optional, good Vultr signal)
- Host the sandbox image in Vultr Container Registry and have sandbox hosts pull from it.

## Sandbox design (decided)

Primary approach: a small `sandbox-runner` service on a dedicated sandbox-host VM that runs each sandbox as a Docker container under gVisor (`runsc`) with networking disabled.

- Why not OpenSandbox as the primary: OpenSandbox's egress enforcement is a sidecar that its own docs say is NOT supported under gVisor (they recommend Kata, which needs hardware virtualization that ordinary cloud VMs usually lack). Plain Docker with `--network none` under gVisor gives zero network with far fewer moving parts.
- OpenSandbox is an acceptable alternative (Python SDK `opensandbox`; server via `uvx opensandbox-server init-config ~/.sandbox.toml --example docker` then `uvx opensandbox-server`; gVisor via `[secure_runtime] type = "gvisor"`, `docker_runtime = "runsc"`). If used under gVisor, block egress on the host (DOCKER-USER chain) because its sidecar will not work.
- Do not use E2B's hosted cloud: sandboxes must run on Vultr.
- gVisor's default platform (systrap) works on ordinary VMs without nested virtualization.

Install gVisor on the sandbox host (Ubuntu):
```bash
curl -fsSL https://gvisor.dev/archive.key | sudo gpg --dearmor -o /usr/share/keyrings/gvisor-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/gvisor-archive-keyring.gpg] https://storage.googleapis.com/gvisor/releases release main" | sudo tee /etc/apt/sources.list.d/gvisor.list
sudo apt-get update && sudo apt-get install -y runsc
sudo runsc install && sudo systemctl restart docker
docker run --rm --runtime=runsc hello-world
```

Every sandbox container gets these flags (tune limits per project in PLAN.md):
```
--runtime=runsc --network=none --read-only --tmpfs /tmp:rw,size=64m
--cap-drop=ALL --security-opt=no-new-privileges --pids-limit=256
--memory=<M>m --cpus=<C> --user=10001:10001
-v <host>/in:/in:ro -v <host>/work:/work -v <host>/out:/out
--label arena.sandbox=1 --label arena.tenant=<tenant> --label arena.task=<task>
```

Runner API contract (HTTP + JSON, bearer token, bound to the VPC IP only, host firewall allows only the control plane):
- `POST /v1/sandboxes` `{image, labels, limits: {cpus, memory_mb, pids, exec_timeout_s, ttl_s}, inputs: [{path, content_b64}]}` returns `{id}`. Creates host dirs, writes inputs into `in/` (read-only), starts the container with `sleep infinity`, runs the in-image attestation script, stores the attestation.
- `PUT /v1/sandboxes/{id}/files` `{path, content_b64}` writes under `/work` only.
- `POST /v1/sandboxes/{id}/exec` `{argv, timeout_s}` returns `{exit_code, stdout, stderr, duration_ms, timed_out, out_files: [{path, size, sha256}]}` with stdout and stderr truncated. Enforce the timeout inside the container with `timeout -s KILL`. Optional SSE streaming variant.
- `GET /v1/sandboxes/{id}/out/{path}` returns the file bytes.
- `GET /v1/sandboxes/{id}` returns status, labels, limits, attestation, and a docker-inspect summary (Runtime, NetworkMode, ReadonlyRootfs, CapDrop, SecurityOpt, Memory, NanoCpus, PidsLimit, image digest).
- `GET /v1/sandboxes` (admin grid) and `DELETE /v1/sandboxes/{id}`.
- Janitor: delete sandboxes past their TTL; clean orphans at startup. Global cap on concurrent sandboxes (return 429 when full).

Rules:
- Treat everything a sandbox writes as hostile. When reading `work/` or `out/` on the host: reject symlinks and non-regular files (lstat, O_NOFOLLOW, realpath must stay inside the directory), cap file size and file count.
- Bake an attestation script into every sandbox image (`/opt/attest.py`), run it at sandbox start, and store its JSON: uid and gid, effective capabilities (CapEff in /proc/self/status), network interfaces (/sys/class/net should list only `lo`), result of an outbound connection attempt (must fail), write tests on `/` and `/in` (must fail) and on `/work` and `/out` (must succeed), environment variable NAMES (expect no secrets), cgroup memory and CPU limits, kernel string. The UI renders this plus the docker-inspect summary as the "Blast radius" panel.
- Host-side writes into a bind mount while the container runs should be visible inside under gVisor (shared file access is the default for mounts). Verify early; the fallback is writing files via exec with base64.
- The control plane never executes model-written code, never mounts the Docker socket into anything, and never passes secrets to sandboxes.

## Public URL and guardrails

- The control-plane VM runs Caddy on 80 and 443 with automatic HTTPS. Point a domain at it (Vultr DNS works). Without a domain, `<ip-with-dashes>.sslip.io` style hostnames usually work with Let's Encrypt (verify).
- Sandbox hosts get no public inbound traffic, ideally no public IP at all (VPC plus NAT gateway for outbound image pulls).
- A public page that runs code is itself a blast-radius risk. Required: login with seeded demo accounts (credentials shown on the login page for judges), roles, per-user rate limits, a global cap on concurrent sandboxes, a sandbox TTL janitor, a daily token budget, and an admin kill switch that stops new work and destroys running sandboxes. Mention these in the pitch.
- Give judges one-click sample runs so it works without typing.
- A health page that checks inference, database, object storage, and the runner. All green before going on stage.

## NetBird bonus (last priority)

- Docs: https://docs.netbird.io/manage/reverse-proxy (beta), https://docs.netbird.io/manage/reverse-proxy/expose-from-cli, https://docs.netbird.io/manage/reverse-proxy/authentication
- `netbird expose` creates temporary public URLs that are removed when the command stops or the session expires, which maps to "lifecycle-bound URLs". Services can require SSO, password, PIN, or header auth.
- Self-hosting the management server needs Traefik doing TLS passthrough in front of it (docs.netbird.io/selfhosted/migration/enable-reverse-proxy).
- If done: close 80 and 443 in the Vultr firewall group, serve the app through NetBird, gate it with password or SSO mapped to our roles, and create per-task preview URLs with `netbird expose` that die with the task.
