# FactChecker Intelligent Contract (GenLayer)

`FactChecker` is a decentralized, AI-driven fact-verification Intelligent Contract deployed on the GenLayer network. It automates claims verification by fetching evidence from external web sources, evaluating source credibility and content stance via LLM-powered validators, and deterministically settling verdicts on-chain.

---

## ⚡ Resolution of Validator Rejection & Consensus Protocol

In response to initial validator feedback regarding non-deterministic execution and consensus divergence, **v3.2** introduces strict deterministic rules:

### 1. Canonical Evidence Set Binding
- **Issue:** Independent node search queries (`gl.nondet.web.render`) produced slightly different URL candidate sets.
- **Fix:** In `discover_next`, external search retrieval output is alphabetically sorted, capped, and passed through `gl.eq_principle.prompt_comparative`. Validators must commit to an **identical 1-to-1 array of discovered URLs** before persisting state.

### 2. Full Weight-Affecting Field Atomic Consensus
- **Issue:** Nodes previously only agreed on text stances (`SUPPORTS` / `REFUTES`), while `is_primary` status and `specificity` metrics varied, leading to divergent weight calculations.
- **Fix:** In `read_next_source`, prompt comparative evaluation enforces atomic consensus over a unified JSON payload containing:
  - `stance` (`SUPPORTS` | `REFUTES` | `INSUFFICIENT`)
  - `is_primary` (`boolean`)
  - `specificity` (`1` | `2` | `3`)
  - `weight` (`integer`)

  The consensus rule mandates 100% identity across all four weight-affecting properties simultaneously across all participating validators.

### 3. State-Locked Adjudication
- `finish_verification` calculates the final claim status based strictly on the state-bound integer weights accumulated during source reading, ensuring fully reproducible execution outcomes.

---

## 🔄 State Machine & Workflow

1. **`submit_claim(claim: str, url: str) -> int`**: Registers a claim record and attaches optional party-supplied evidence URLs.
2. **`start_verification(claim_id: int) -> str`**: Transitions claim state from `PENDING` to `DISCOVERING`.
3. **`discover_next(claim_id: int) -> str`**: Queries search endpoints and reaches consensus on the canonical list of candidate URLs.
4. **`begin_reading(claim_id: int) -> str`**: Enqueues selected candidate sources for detailed reading and sets state to `GATHERING`.
5. **`read_next_source(claim_id: int) -> str`**: Fetches page content, invokes comparative LLM prompts, atomically binds all weight parameters, and appends proof records.
6. **`finish_verification(claim_id: int) -> str`**: Aggregates verified weight scores and locks the provisional verdict (`TRUE`, `FALSE`, or `INSUFFICIENT_EVIDENCE`).

---

## 🛠️ Deployment & Execution Standards

- **SDK Header:** `# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }`
- **Class Model:** Inherits from `gl.Contract` utilizing `DynArray[str]` state storage.
- **ABI Parsing Safety:** Public methods use strictly standard primitive types (`int`, `str`, `list[str]`) for AST/ABI compatibility.
