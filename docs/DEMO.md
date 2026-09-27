# Stage demo runbook (3 minutes)

Open the public URL (see STATUS.md) in a browser at 1440x900 or larger. Before going on stage: open **Admin** as Sam and check that health is all green and the kill switch is off; press **Warm up** once.

| Time | Do | Say |
|---|---|---|
| 0:00 | Login page. Click **Sign in as Alex** (preparer). Dashboard shows the last close. | "Accounting firms close the books for dozens of clients every month. The worst part is bank reconciliation. AI could do it, but no firm lets an AI run code on client data unless it's contained." |
| 0:20 | Click **Close September**. Tiles switch to running and show gVisor, No network, Read-only, 1 CPU. | "Each client gets its own sealed sandbox on Vultr." |
| 0:35 | Tiles fill in live: steps, matched count, exceptions. Some turn amber (needs review). | (let it run; about 40 seconds) |
| 0:50 | Click the **Blue Harbor Coffee Roasters** tile. Show the timeline: the sniff step found DD/MM dates and a 3-line header; expand a Run Python step to show code and real output. | "This is real code, executed in the sandbox. Not a description of what it would do." |
| 1:15 | Matching view (curves), then the **Exceptions** tab and the reconciliation card: bank fee, NSF check, the 1,520.00 vs 1,250.00 transposition, outstanding checks, deposit in transit; difference 0.00. | "Every leftover is explained, and the reconciliation ties to the penny." |
| 1:40 | Scroll to the **Blast radius** panel and the orange **instruction-like text** callout. | "Whoever paid this client wrote the memo text on their transaction. If that text tries to steer the agent, it doesn't matter: no network, read-only inputs, no ledger access." |
| 2:05 | User menu, **Switch to Jordan (Reviewer)**. Add a comment, **Approve**. Click **Download AJE CSV**. | "A human approves every entry. The agent never posts." |
| 2:25 | Click **Replay**. Wait for the green **Reproducible** badge (about 15 s). | "Every number is reproducible. An auditor can re-run it." |
| 2:45 | Open **How it works** (architecture and the ground-truth card: 68 of 68 planted discrepancies found). | "All on Vultr: VM control plane, sandbox hosts on a private network, Serverless Inference, Managed Postgres, Object Storage." |

## If something goes wrong live
- **A client tile turns red:** keep talking; click the tile and use **Re-run**, or continue with Blue Harbor. A failed run is contained and visible, which is the point.
- **The close is slow:** open **Previous closes** and pick the last completed one; everything on it is a real recorded run.
- **"A close is already running":** someone started one; open it from the dashboard (it is live) or wait.
- **Kill switch is on:** sign in as Sam, Admin, turn it off (it also auto-resumes after 15 minutes in the public demo).
- **Rate limit message:** open a previous close instead of starting a new one.
- **Whole site down:** play the narrated video (`media/demo.mp4`, link in SUBMISSION.md) and use the 4-slide pitch deck (`slides.html` in the repo root; open it in a browser, arrow keys to move).

## Judge Q&A (short answers)
- **Why a sandbox?** The code may be wrong and the data is untrusted (a bank memo in the demo tries to instruct the AI). No network, read-only inputs, no ledger access, one sandbox per client.
- **Why an LLM if you have a library?** The library does the math; the agent adapts to each client's messy export, investigates leftovers, decides timing versus error, drafts entries and writes the memo. Numbers come only from executed code.
- **Hallucinated numbers?** Every number is computed in the sandbox, validated by the control plane, reproducible by Replay, and approved by a human before export.
- **Is the public URL safe?** Login, roles, per-user and per-IP limits, sandbox cap, TTL janitor, kill switch, token budget, no secrets in sandboxes, sandbox host with no inbound traffic from the internet.
- **How does it scale?** Add sandbox hosts behind the same runner contract (the control plane already spreads runs across hosts and fails over if one is down); high-sensitivity clients could get a dedicated throwaway VM.
- **Is it hardcoded for the 12 demo clients?** No. Click **Upload files**, download the sample files from the dialog, change an amount or add a bank fee, and upload them back (or upload your own export). The agent works out the format in a fresh sandbox and finds what you changed, usually in about 25 s.
- **What if an upload contains something malicious?** It is data in a read-only mount of a sandbox with no network; instruction-like text is flagged and treated as data, and each file's SHA-256 is in the audit log.
