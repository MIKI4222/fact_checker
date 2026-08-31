# AI Fact Checker

An Intelligent Contract on GenLayer that verifies factual claims using AI validator consensus.

## How it works

1. Anyone submits a **claim** + a **URL** with supporting evidence
2. AI validators independently fetch the URL and read its content
3. Validators reach consensus via `gl.eq_principle.prompt_comparative`
4. The verdict (**TRUE** / **FALSE**) and AI reasoning are stored permanently on-chain

## Contract methods

| Method | Type | Description |
|--------|------|-------------|
| `submit_claim(claim, url)` | Write | Submit a claim with evidence URL |
| `verify_claim(claim_id)` | Write | Trigger AI consensus verification |
| `get_claim(claim_id)` | Read | Get a single claim result |
| `get_all_claims()` | Read | Get all claims |
| `total_claims()` | Read | Total number of claims |

## GenLayer features used

- `gl.nondet.web.render` — fetches live web content
- `gl.nondet.exec_prompt` — queries LLM for verdict
- `gl.eq_principle.prompt_comparative` — reaches validator consensus

## Deployed contract

**Network:** Bradbury Testnet  
**Address:** `0x90...0723`

## Tech stack

- Python Intelligent Contract (GenLayer)
- GenLayer Bradbury Testnet
