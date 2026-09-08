# FactChecker v2 — On-Chain Claim Adjudication Protocol

FactChecker v2 is an **Intelligent Contract** deployed on the [GenLayer](https://genlayer.com) network. It moves beyond simple "single-prompt" LLM wrappers by executing a multi-stage, evidence-based adjudication protocol directly within decentralized validator consensus.

## 🌟 Key Features

* **Multi-Source Evidence Acquisition (`gl.nondet`)**: Automatically discovers and gathers claims from open search endpoints (DuckDuckGo, Crossref, GDELT) and independent web domains rather than relying on a single hardcoded URL.
* **Source Authority Tiers & Freshness Decay**: Evaluates sources across predefined authority tiers (Tier A: WHO/SEC/UN, Tier B: Reuters/Nature, Tier C/D) and applies time-decay algorithms (`_freshness_weight`) to penalize outdated data.
* **Anti-Cherry-Picking Controls**: Caps the maximum weight given to submitter-supplied URLs (`PARTY_SUPPLIED_CAP = 4000`) to guarantee that independent sources drive the verdict.
* **Consensus via Equivalence Principle (`gl.eq_principle`)**: Validators independently render web pages, strip non-relevant layout/JS blocks, run focused LLM stance analysis (`SUPPORTS` / `REFUTES`), and reach agreement on non-deterministic web data.
* **Economic Challenge & Resolution Lifecycle**: Implements a bond-backed state machine (`PENDING` → `DISCOVERING` → `GATHERING` → `PROVISIONAL` → `CHALLENGED` → `FINAL`) with financial incentives (submission bonds, submitter rewards, and challenger stake redistribution).

---

## 🔄 Protocol Lifecycle

[submit_claim] ──> PENDING
│
[start_verification]
│
▼
┌──────────── DISCOVERING ◄──────────┐
│         (discover_next loop)       │
└──────────────────┬─────────────────┘
│ [begin_reading]
▼
┌───────────── GATHERING ◄───────────┐
│        (read_next_source loop)     │
└──────────────────┬─────────────────┘
│ [finish_verification]
▼
PROVISIONAL ──(Challenge Window: 7 Days)
│
┌───────────┴───────────┐
│                       │
[challenge]               [finalize]
│                       │
▼                       ▼
CHALLENGED                 FINAL
│ (resolution loop)
▼
[finish_resolution]
│
▼
FINAL


---

## 📜 Contract Architecture

### Core Methods

| Method | Type | Description |
| :--- | :--- | :--- |
| `submit_claim(claim, url)` | `write` | Submits a new claim and locks a `SUBMISSION_BOND` (100 credits). |
| `start_verification(claim_id)` | `write` | Initializes the web discovery pipeline for the claim. |
| `discover_next(claim_id)` | `write` | Fetches evidence links using `gl.nondet` across search endpoints. |
| `begin_reading(claim_id)` | `write` | Filters and selects top independent domains across authority tiers. |
| `read_next_source(claim_id)` | `write` | Renders the page, extracts context around claim keywords, and uses LLM to derive stance (`SUPPORTS`/`REFUTES`). |
| `finish_verification(claim_id)` | `write` | Calculates weighted consensus margin and sets provisional verdict. |
| `challenge(claim_id, counter_url, argument)` | `write` | Locks `CHALLENGE_BOND` (250 credits) to contest a provisional verdict with new evidence. |
| `finish_resolution(claim_id)` | `write` | Re-adjudicates the claim; rewards challenger if verdict changes, or submitter if upheld. |
| `finalize(claim_id)` | `write` | Confirms the provisional verdict after the challenge window closes. |

---

## 🛠️ Deployment & Testing

### Deploying on GenLayer Studio

1. Open [GenLayer Studio](https://studio.genlayer.com/).
2. Create a new contract file `FactChecker.py` and paste the source code.
3. Deploy the contract.

### Running Automated Walkthrough

To verify the contract using python test tools or GenLayer CLI:

```bash
# Run tests via GenLayer SDK/CLI
genlayer test
🛡️ Authority Tiers Reference
Tier A (Weight: 10,000): Primary official organizations (who.int, sec.gov, un.org, nasa.gov, cdc.gov).

Tier B (Weight: 7,000): Established wire services & academic journals (reuters.com, apnews.com, nature.com, bbc.com).

Tier C (Weight: 4,000): Major global news outlets (nytimes.com, ft.com, bloomberg.com, theguardian.com).

Tier D (Weight: 1,500): Unverified or general web sources.
