# Fact Checker — GenLayer Intelligent Contract

An intelligent fact-checking contract for GenLayer.

The contract verifies factual claims against web pages using:

- GenLayer nondeterministic web access;
- GenLayer's equivalence principle;
- LLM-based claim evaluation;
- deterministic evidence aggregation;
- source reliability tiers and evidence weights.

The contract is designed so that every nondeterministic operation is executed inside an equivalence-principle callback.

---

## Important Fix

The original contract was rejected because its source-reading path called:

```python
gl.nondet.web.render(...)
```

outside a callback governed by the equivalence principle.

The corrected implementation moves the web request into a callback:

```python
def fetch_page() -> str:
    res = gl.nondet.web.request(url, method="GET")
    ...
    return text

excerpt = gl.eq_principle.prompt_comparative(
    fetch_page,
    principle="Both texts are excerpts of the same web page..."
)
```

The LLM evaluation is also executed inside an equivalence-principle callback:

```python
def eval_stance() -> str:
    answer = gl.nondet.exec_prompt(prompt)
    ...
    return answer

stance = gl.eq_principle.prompt_comparative(
    eval_stance,
    principle="Both outputs must be the same single verdict word."
)
```

This ensures that nondeterministic operations are validly reachable and can be compared by GenLayer validators.

---

## Current Contract

The current lightweight contract is:

```text
fact_checker_lite.py
```

The contract class is:

```python
FactChecker
```

The contract uses explicit source URLs. Automatic source discovery was removed from this lightweight version to reduce deployment size and improve reliability on the Bradbury testnet.

---

## Features

- Submit a factual claim with an initial source URL.
- Add additional evidence sources.
- Fetch web content through `gl.nondet.web.request`.
- Execute web fetching inside an equivalence-principle callback.
- Remove JavaScript and CSS content from downloaded HTML.
- Extract readable article text.
- Select a relevant text window using claim keywords.
- Evaluate evidence with an LLM.
- Execute LLM evaluation inside an equivalence-principle callback.
- Assign evidence weights based on source reliability.
- Calculate `TRUE`, `FALSE`, `DISPUTED`, or `INSUFFICIENT_EVIDENCE`.
- Store the complete verification record on-chain.

---

## Contract Methods

### `submit_claim`

Creates a new claim and adds the supplied URL as the first source.

```text
submit_claim(claim, url)
```

Example:

```text
claim:
The WHO declared COVID-19 a pandemic in March 2020
```

```text
url:
https://www.who.int/news/item/27-04-2020-who-timeline---covid-19
```

Returns:

```text
0
```

The returned value is the claim ID.

---

### `add_source`

Adds another source to an existing claim.

```text
add_source(claim_id, url)
```

Possible results:

```text
ADDED
DUPLICATE
QUEUE_FULL
```

The contract accepts up to five sources per claim.

Use ordinary URLs only. Do not pass Markdown links.

Correct:

```text
https://www.who.int/news/item/27-04-2020-who-timeline---covid-19
```

Incorrect:

```text
[WHO Timeline](https://www.who.int/news/item/27-04-2020-who-timeline---covid-19)
```

---

### `start_verification`

Starts verification for a claim.

```text
start_verification(claim_id)
```

Example:

```text
start_verification(0)
```

Expected result:

```text
GATHERING
```

---

### `fetch_next_source`

Fetches the next source and stores an evidence excerpt.

```text
fetch_next_source(claim_id)
```

The web request is executed inside an equivalence-principle callback.

Possible results:

```text
FETCHED
COMPLETED
PENDING_NOT_JUDGED
```

Meaning:

- `FETCHED` — a source was downloaded and stored in `pending`;
- `COMPLETED` — all selected sources have been processed;
- `PENDING_NOT_JUDGED` — the previous source must be judged first.

The method performs the following operations:

1. Sends a nondeterministic web request.
2. Removes JavaScript and CSS content.
3. Removes HTML tags.
4. Decodes common HTML entities.
5. Extracts readable text.
6. Selects a relevant excerpt using claim keywords.
7. Stores the excerpt in `pending`.

---

### `judge_pending_source`

Evaluates the pending source against the claim.

```text
judge_pending_source(claim_id)
```

Possible results:

```text
SUPPORTS
REFUTES
INSUFFICIENT
```

The LLM must return exactly one verdict word.

The result is normalized to one of:

```text
SUPPORTS
REFUTES
INSUFFICIENT
```

The result is then stored in the claim's `evidence` array.

---

### `drop_pending_source`

Removes a pending source without judging it.

```text
drop_pending_source(claim_id)
```

Expected result:

```text
DROPPED
```

---

### `finish_verification`

Calculates the final verdict using the stored evidence.

```text
finish_verification(claim_id)
```

Possible results:

```text
TRUE
FALSE
DISPUTED
INSUFFICIENT_EVIDENCE
```

The calculation is deterministic and does not call the web or an LLM.

---

### `get_claim`

Returns the complete JSON record for a claim.

```text
get_claim(claim_id)
```

Example:

```text
get_claim(0)
```

---

### `total_claims`

Returns the total number of stored claims.

```text
total_claims()
```

---

## Verification Flow

The normal verification flow is:

```text
submit_claim
start_verification
fetch_next_source
judge_pending_source
fetch_next_source
finish_verification
get_claim
```

For one source, the complete sequence is:

```text
submit_claim(claim, url)       -> 0
start_verification(0)          -> GATHERING
fetch_next_source(0)           -> FETCHED
judge_pending_source(0)       -> SUPPORTS
fetch_next_source(0)           -> COMPLETED
finish_verification(0)         -> TRUE
get_claim(0)                   -> final JSON result
```

---

## Tested Claim

The following claim was successfully verified:

```text
The WHO declared COVID-19 a pandemic in March 2020
```

Source:

```text
https://www.who.int/news/item/27-04-2020-who-timeline---covid-19
```

The extracted evidence included:

```text
11 March 2020 Deeply concerned both by the alarming levels of spread and severity, and by the alarming levels of inaction, WHO made the assessment that COVID-19 can be characterized as a pandemic.
```

Expected verification result:

```text
verdict:
TRUE
```

```text
confidence:
99
```

```text
stance:
SUPPORTS
```

```text
tier:
A
```

```text
weight:
4000
```

---

## Example Final Claim Record

A successfully verified claim has the following structure:

```json
{
  "claim": "The WHO declared COVID-19 a pandemic in March 2020",
  "confidence": 99,
  "cursor": 1,
  "evidence": [
    {
      "domain": "who.int",
      "party_supplied": true,
      "stance": "SUPPORTS",
      "tier": "A",
      "url": "https://www.who.int/news/item/27-04-2020-who-timeline---covid-19",
      "weight": 4000
    }
  ],
  "id": 0,
  "pending": {},
  "status": "PROVISIONAL",
  "verdict": "TRUE"
}
```

---

## Source Reliability Tiers

The contract assigns sources to reliability tiers.

### Tier A

```text
who.int
sec.gov
un.org
nasa.gov
cdc.gov
```

Base weight:

```text
13000
```

### Tier B

```text
reuters.com
apnews.com
nature.com
bbc.com
```

Base weight:

```text
7000
```

### Tier C

```text
nytimes.com
ft.com
bloomberg.com
theguardian.com
```

Base weight:

```text
4000
```

### Tier D

All other domains.

Base weight:

```text
1500
```

---

## Party-Supplied Source Limit

A source supplied directly by the claim submitter is marked as:

```json
{
  "party": true
}
```

Party-supplied sources are limited to a maximum weight of:

```text
4000
```

This prevents one source submitted by the claimant from dominating the entire result.

---

## Verdict Rules

The contract calculates the final verdict using the total evidence weights.

### TRUE

A claim is marked as `TRUE` when:

```text
supporting weight >= 4000
```

and:

```text
supporting weight > refuting weight * 1.5
```

### FALSE

A claim is marked as `FALSE` when:

```text
refuting weight >= 4000
```

and:

```text
refuting weight > supporting weight * 1.5
```

### DISPUTED

A claim is marked as `DISPUTED` when there is both supporting and refuting evidence, but neither side has a sufficient majority.

### INSUFFICIENT_EVIDENCE

A claim is marked as `INSUFFICIENT_EVIDENCE` when there is not enough valid supporting or refuting evidence.

---

## Equivalence Principle

The contract uses the equivalence principle in two places.

### Web Fetching

```python
def fetch_page() -> str:
    res = gl.nondet.web.request(url, method="GET")
    ...
    return excerpt

excerpt = gl.eq_principle.prompt_comparative(
    fetch_page,
    principle="Both texts are excerpts of the same web page and are equivalent if they discuss the same subject matter."
)
```

The validators do not need to produce byte-for-byte identical HTML. They only need to agree that the excerpts discuss the same subject.

### LLM Evaluation

```python
def eval_stance() -> str:
    answer = gl.nondet.exec_prompt(prompt)
    ...
    return "SUPPORTS"

stance = gl.eq_principle.prompt_comparative(
    eval_stance,
    principle="Both outputs must be the same single verdict word."
)
```

All validators must return the same normalized verdict:

```text
SUPPORTS
REFUTES
INSUFFICIENT
```

---

## HTML Processing

The contract receives raw HTML from the web request.

The extraction process:

1. Downloads the page.
2. Removes JavaScript blocks.
3. Removes CSS blocks.
4. Removes HTML tags.
5. Decodes common HTML entities.
6. Normalizes whitespace.
7. Splits the text into deterministic windows.
8. Selects the window containing the most claim keywords.
9. Stores a maximum excerpt of approximately 2000 characters.

The contract is designed to avoid sending navigation menus and JavaScript code to the LLM whenever possible.

---

## Deployment

The contract can be deployed from GenLayer Studio.

Use the following dependency header at the top of the Python file:

```python
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
```

The deployed file should contain:

```text
fact_checker_lite.py
```

The contract class should be:

```python
FactChecker
```

Recommended deployment procedure:

1. Open GenLayer Studio.
2. Create or open a Python contract file.
3. Paste the complete `fact_checker_lite.py` source.
4. Confirm that the class is named `FactChecker`.
5. Select the target GenLayer testnet.
6. Deploy the contract.
7. Wait until the deployment transaction is finalized.
8. Run the verification sequence.

---

## Studio Test

Use the following values in GenLayer Studio.

Claim:

```text
The WHO declared COVID-19 a pandemic in March 2020
```

URL:

```text
https://www.who.int/news/item/27-04-2020-who-timeline---covid-19
```

Claim ID:

```text
0
```

Call sequence:

```text
submit_claim
```

Arguments:

```text
claim:
The WHO declared COVID-19 a pandemic in March 2020
```

```text
url:
https://www.who.int/news/item/27-04-2020-who-timeline---covid-19
```

Then:

```text
start_verification
```

Argument:

```text
0
```

Then:

```text
fetch_next_source
```

Argument:

```text
0
```

Then:

```text
get_claim
```

Argument:

```text
0
```

Verify that `pending.text` contains text related to:

```text
11 March 2020
```

and:

```text
COVID-19 can be characterized as a pandemic
```

Then call:

```text
judge_pending_source
```

Argument:

```text
0
```

Expected result:

```text
SUPPORTS
```

Then call:

```text
fetch_next_source
```

Argument:

```text
0
```

Expected result:

```text
COMPLETED
```

Finally call:

```text
finish_verification
```

Argument:

```text
0
```

Expected result:

```text
TRUE
```

---

## Important Limitations

This lightweight version intentionally does not include automatic source discovery.

The following features are not part of the current lightweight contract:

```text
discover_next
Crossref discovery
DuckDuckGo discovery
automatic URL parsing
web.render-based source reading
```

Sources must be supplied explicitly with:

```text
submit_claim
```

or:

```text
add_source
```

The current implementation is optimized for:

- smaller deployment size;
- reliable deployment on Bradbury;
- short validator execution time;
- simple deterministic state transitions;
- explicit and auditable evidence sources.

---

## Security and Determinism Notes

The contract does not trust a single validator.

Web requests and LLM responses are nondeterministic, so they are executed inside GenLayer's equivalence-principle callbacks.

The final verdict calculation is deterministic:

- evidence is stored on-chain;
- source tier calculation is deterministic;
- evidence weights are deterministic;
- final verdict rules are deterministic.

The contract does not use a single raw LLM response without consensus.

---

## Successful Test Summary

The corrected contract successfully demonstrated:

```text
web.request inside an equivalence-principle callback:
ACCEPTED
AGREE
```

```text
LLM evaluation inside an equivalence-principle callback:
ACCEPTED
AGREE
```

```text
Final verdict:
TRUE
```

```text
Confidence:
99
```

This confirms that the original deployment rejection was fixed by moving the nondeterministic page-reading operation into the equivalence-principle callback.

---

## Project Structure

The main contract file is:

```text
fact_checker_lite.py
```

Recommended repository structure:

```text
.
├── fact_checker_lite.py
├── README.md
└── tests/
```

---

## License

No license is currently specified for this project.
