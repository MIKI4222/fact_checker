# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from genlayer import *


class FactChecker(gl.Contract):
    claims: DynArray[str]

    def __init__(self):
        pass

    # ==================== HELPERS ====================

    def _get_domain(self, url: str) -> str:
        clean = url.replace("https://", "").replace("http://", "").replace("www.", "")
        return clean.split("/")[0].lower()

    def _get_tier(self, domain: str) -> str:
        if domain in ["who.int", "sec.gov", "un.org", "nasa.gov", "cdc.gov"]:
            return "A"
        elif domain in ["reuters.com", "apnews.com", "nature.com", "bbc.com", "bbc.co.uk"]:
            return "B"
        elif domain in ["nytimes.com", "ft.com", "bloomberg.com", "theguardian.com"]:
            return "C"
        return "D"

    # ==================== PUBLIC WRITE METHODS ====================

    @gl.public.write
    def submit_claim(self, claim: str, url: str) -> int:
        claim_id = len(self.claims)
        party_urls = []
        selected = []

        if len(url.strip()) > 0:
            clean_url = url.strip()
            domain = self._get_domain(clean_url)
            party_urls.append(clean_url)
            selected.append({
                "url": clean_url,
                "domain": domain,
                "tier": self._get_tier(domain),
                "party": True
            })

        endpoints = [
            f"https://lite.duckduckgo.com/lite/?q={claim.replace(' ', '+')}",
            f"https://api.crossref.org/works?rows=20&select=URL,title&query={claim.replace(' ', '+')}"
        ]

        claim_record = {
            "id": claim_id,
            "claim": claim,
            "submitter": str(gl.message.sender_address),
            "status": "PENDING",
            "verdict": "",
            "confidence": 0,
            "endpoints": endpoints,
            "endpoint_cursor": 0,
            "discovered": [],
            "selected": selected,
            "cursor": 0,
            "evidence": []
        }

        self.claims.append(json.dumps(claim_record, sort_keys=True))
        return claim_id

    @gl.public.write
    def start_verification(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        if c["status"] != "PENDING":
            return "ALREADY_STARTED"
        c["status"] = "DISCOVERING"
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "DISCOVERING"

    @gl.public.write
    def discover_next(self, claim_id: int) -> str:
        """Collects evidence URLs with CANONICAL VALIDATOR AGREEMENT on the URL list."""
        c = json.loads(self.claims[claim_id])
        if c["status"] != "DISCOVERING":
            return "ERROR_NOT_DISCOVERING"

        if c["endpoint_cursor"] >= len(c["endpoints"]):
            c["status"] = "GATHERING"
            self.claims[claim_id] = json.dumps(c, sort_keys=True)
            return "GATHERING"

        ep = c["endpoints"][c["endpoint_cursor"]]
        c["endpoint_cursor"] += 1

        def fetch_canonical_urls() -> str:
            discovered_urls = []
            try:
                rendered = gl.nondet.web.render(ep, mode="text")
                if rendered and len(rendered) > 50:
                    for token in rendered.split('"'):
                        if token.startswith("http://") or token.startswith("https://"):
                            if "duckduckgo" not in token and "crossref" not in token:
                                discovered_urls.append(token.split('#')[0])
            except Exception:
                pass

            # CANONICAL BINDING: Sort alphabetically and return top 5 as deterministic JSON
            unique_sorted = sorted(list(set(discovered_urls)))[:5]
            return json.dumps(unique_sorted, sort_keys=True)

        # Consensus enforces 100% agreement on the exact list of discovered URLs
        consensus_urls_str = gl.eq_principle.prompt_comparative(
            fetch_canonical_urls,
            principle="The array of discovered URLs must be exactly identical in content and order."
        )

        canonical_urls = json.loads(consensus_urls_str)
        for u in canonical_urls:
            if u not in c["discovered"]:
                c["discovered"].append(u)

        if c["endpoint_cursor"] >= len(c["endpoints"]):
            c["status"] = "GATHERING"

        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "OK"

    @gl.public.write
    def begin_reading(self, claim_id: int) -> str:
        """Selects top canonical candidate URLs into reading queue."""
        c = json.loads(self.claims[claim_id])
        c["status"] = "GATHERING"

        all_candidates = sorted(list(set(c["discovered"])))
        existing_urls = {item["url"] for item in c["selected"]}

        for url in all_candidates:
            if url not in existing_urls:
                domain = self._get_domain(url)
                c["selected"].append({
                    "url": url,
                    "domain": domain,
                    "tier": self._get_tier(domain),
                    "party": False
                })
                existing_urls.add(url)
                if len(c["selected"]) >= 5:
                    break

        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "GATHERING"

    @gl.public.write
    def read_next_source(self, claim_id: int) -> str:
        """Reads source and enforces CONFLICT-FREE CONSENSUS on ALL weight-affecting fields."""
        c = json.loads(self.claims[claim_id])
        if c["cursor"] >= len(c["selected"]):
            return "COMPLETED"

        target = c["selected"][c["cursor"]]
        c["cursor"] += 1
        url = target["url"]

        page_text = ""
        try:
            page_text = gl.nondet.web.render(url, mode="text")
            if page_text and len(page_text) > 2000:
                page_text = page_text[:2000]
        except Exception:
            page_text = "FAILED_TO_LOAD"

        prompt = (
            "Analyze if the webpage content SUPPORTS, REFUTES, or is INSUFFICIENT to verify the claim.\n"
            f"Claim: \"{c['claim']}\"\n"
            f"Source Content: \"{page_text}\"\n\n"
            "Reply strictly with JSON only: "
            "{\"stance\": \"SUPPORTS\"|\"REFUTES\"|\"INSUFFICIENT\", \"is_primary\": true|false, \"specificity\": 1|2|3}"
        )

        def eval_source() -> str:
            res = gl.nondet.exec_prompt(prompt)
            res = res.replace("```json", "").replace("```", "").strip()

            stance = "INSUFFICIENT"
            is_primary = False
            specificity = 1
            try:
                parsed = json.loads(res)
                stance = str(parsed.get("stance", "INSUFFICIENT"))
                is_primary = bool(parsed.get("is_primary", False))
                specificity = int(parsed.get("specificity", 1))
            except Exception:
                pass

            # Calculate deterministic weight inside validator thread
            tier_weights = {"A": 10000, "B": 7000, "C": 4000, "D": 1500}
            base_weight = tier_weights.get(target["tier"], 1500)
            primary_mult = 1.3 if is_primary else 1.0
            specificity_mult = 0.5 + (specificity * 0.25)

            raw_weight = int(base_weight * primary_mult * specificity_mult)
            if target["party"]:
                raw_weight = min(raw_weight, 4000)
            if stance == "INSUFFICIENT":
                raw_weight = 0

            # FULL BINDING: The return JSON explicitly seals stance, primary status, specificity AND final weight
            return json.dumps({
                "stance": stance,
                "is_primary": is_primary,
                "specificity": specificity,
                "weight": raw_weight
            }, sort_keys=True)

        # STRICT CONSENSUS RULE: Binds all weight-affecting fields together
        consensus_payload = gl.eq_principle.prompt_comparative(
            eval_source,
            principle="The stance, is_primary, specificity, and weight values in the JSON output MUST be EXACTLY identical."
        )

        eval_res = json.loads(consensus_payload)

        evidence_entry = {
            "url": url,
            "domain": target["domain"],
            "tier": target["tier"],
            "party_supplied": target["party"],
            "stance": eval_res.get("stance", "INSUFFICIENT"),
            "is_primary": eval_res.get("is_primary", False),
            "specificity": eval_res.get("specificity", 1),
            "weight": eval_res.get("weight", 0)
        }

        c["evidence"].append(evidence_entry)
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "OK"

    @gl.public.write
    def finish_verification(self, claim_id: int) -> str:
        """Aggregates weighted evidence and commits final verdict."""
        c = json.loads(self.claims[claim_id])

        support_weight = sum(e["weight"] for e in c["evidence"] if e["stance"] == "SUPPORTS")
        refute_weight = sum(e["weight"] for e in c["evidence"] if e["stance"] == "REFUTES")

        verdict = "INSUFFICIENT_EVIDENCE"
        confidence = 0

        if support_weight >= 8000 and support_weight > (refute_weight * 1.5):
            verdict = "TRUE"
            total = support_weight + refute_weight
            confidence = min(99, int((support_weight / total) * 100)) if total > 0 else 80
        elif refute_weight >= 8000 and refute_weight > (support_weight * 1.5):
            verdict = "FALSE"
            total = support_weight + refute_weight
            confidence = min(99, int((refute_weight / total) * 100)) if total > 0 else 80
        elif support_weight > 0 or refute_weight > 0:
            verdict = "DISPUTED"
            confidence = 50

        c["verdict"] = verdict
        c["confidence"] = confidence
        c["status"] = "PROVISIONAL"

        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return verdict

    # ==================== PUBLIC VIEW METHODS ====================

    @gl.public.view
    def get_claim(self, claim_id: int) -> str:
        return self.claims[claim_id]

    @gl.public.view
    def get_all_claims(self) -> list[str]:
        return list(self.claims)

    @gl.public.view
    def total_claims(self) -> int:
        return len(self.claims)
