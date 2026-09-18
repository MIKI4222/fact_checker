# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
import json
from genlayer import *

class FactChecker(gl.Contract):
    claims: DynArray[str]

    def __init__(self):
        pass

    def _domain(self, url: str) -> str:
        c = url.replace("https://", "").replace("http://", "").replace("www.", "")
        return c.split("/")[0].lower()

    def _tier(self, d: str) -> str:
        if d in ["who.int", "sec.gov", "un.org", "nasa.gov", "cdc.gov"]:
            return "A"
        if d in ["reuters.com", "apnews.com", "nature.com", "bbc.com"]:
            return "B"
        if d in ["nytimes.com", "ft.com", "bloomberg.com", "theguardian.com"]:
            return "C"
        return "D"

    def _weight(self, tier: str, stance: str, party: bool) -> int:
        if stance == "INSUFFICIENT":
            return 0
        w = 1500
        if tier == "A":
            w = 13000
        elif tier == "B":
            w = 7000
        elif tier == "C":
            w = 4000
        if party and w > 4000:
            w = 4000
        return w

    def _keywords(self, claim: str) -> list:
        stop = ["the", "and", "for", "was", "were", "are", "has", "have",
                "had", "that", "this", "with", "from", "its"]
        words = []
        for raw in claim.lower().split():
            w = ""
            for ch in raw:
                if ch.isalnum():
                    w = w + ch
            if len(w) < 3:
                continue
            if w in stop:
                continue
            if w not in words:
                words.append(w)
        return words

    @gl.public.write
    def submit_claim(self, claim: str, url: str) -> int:
        cid = len(self.claims)
        sel = []
        if len(url.strip()) > 0:
            u = url.strip()
            d = self._domain(u)
            sel.append({"url": u, "domain": d, "tier": self._tier(d), "party": True})
        rec = {
            "id": cid,
            "claim": claim,
            "submitter": str(gl.message.sender_address),
            "status": "PENDING",
            "verdict": "",
            "confidence": 0,
            "selected": sel,
            "cursor": 0,
            "pending": {},
            "evidence": []
        }
        self.claims.append(json.dumps(rec, sort_keys=True))
        return cid

    @gl.public.write
    def add_source(self, claim_id: int, url: str) -> str:
        c = json.loads(self.claims[claim_id])
        u = url.strip()
        for item in c["selected"]:
            if item["url"] == u:
                return "DUPLICATE"
        if len(c["selected"]) >= 5:
            return "QUEUE_FULL"
        d = self._domain(u)
        c["selected"].append({"url": u, "domain": d, "tier": self._tier(d), "party": False})
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "ADDED"

    @gl.public.write
    def start_verification(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        if c["status"] != "PENDING":
            return "ALREADY_STARTED"
        c["status"] = "GATHERING"
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "GATHERING"

    @gl.public.write
    def fetch_next_source(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        if len(c["pending"]) > 0:
            return "PENDING_NOT_JUDGED"
        if c["cursor"] >= len(c["selected"]):
            return "COMPLETED"

        t = c["selected"][c["cursor"]]
        url = t["url"]
        keywords = self._keywords(c["claim"])

        def fetch_page() -> str:
            try:
                res = gl.nondet.web.request(url, method="GET")
                body = res.body
                if isinstance(body, bytes):
                    body = body.decode("utf-8", errors="ignore")
                raw = str(body)[:120000]
            except Exception:
                return "FAILED_TO_LOAD"

            if len(raw) < 30:
                return "FAILED_TO_LOAD"

            for tag in ["script", "style"]:
                close = "</" + tag + ">"
                parts = raw.split("<" + tag)
                kept = parts[0]
                for i in range(1, len(parts)):
                    if close in parts[i]:
                        kept = kept + " " + parts[i].split(close, 1)[1]
                raw = kept

            low = raw.lower()
            start = -1
            for anchor in ["<h1", "<article", "<main"]:
                pos = low.find(anchor)
                if pos >= 0:
                    start = pos
                    break
            if start > 0:
                raw = raw[start:]

            pieces = []
            for seg in raw.split("<"):
                if ">" in seg:
                    piece = seg.split(">", 1)[1]
                else:
                    piece = seg
                for pair in [["&nbsp;", " "], ["&#160;", " "], ["&ndash;", "-"],
                             ["&mdash;", "-"], ["&amp;", "&"]]:
                    while pair[0] in piece:
                        piece = piece.replace(pair[0], pair[1])
                piece = " ".join(piece.split())
                if len(piece) > 0:
                    pieces.append(piece)

            text = " ".join(pieces)
            text = " ".join(text.split())
            if len(text) < 30:
                return "FAILED_TO_LOAD"

            if len(text) <= 2000:
                return text

            low_text = text.lower()
            best_start = 0
            best_score = -1
            i = 0
            while i < len(text):
                window = low_text[i:i + 1800]
                score = 0
                for word in keywords:
                    score = score + window.count(word)
                if score > best_score:
                    best_score = score
                    best_start = i
                i = i + 600

            excerpt = text[best_start:best_start + 1800]
            if best_start > 0:
                excerpt = text[:180] + " ... " + excerpt
            return excerpt[:2000]

        excerpt = gl.eq_principle.prompt_comparative(
            fetch_page,
            principle="Both texts are excerpts of the same web page and are equivalent if they discuss the same subject matter. Differences in wording or length are acceptable. A failure marker is only equivalent to another failure marker."
        )

        c["cursor"] += 1
        c["pending"] = {
            "url": url,
            "domain": t["domain"],
            "tier": t["tier"],
            "party": t["party"],
            "text": excerpt
        }
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "FETCHED"

    @gl.public.write
    def judge_pending_source(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        p = c["pending"]
        if len(p) == 0:
            return "NOTHING_PENDING"

        claim_text = c["claim"]
        page_text = p["text"]

        def eval_stance() -> str:
            prompt = (
                "You verify a factual claim against the content of a web page. "
                "The content may include website navigation text, which you ignore.\n\n"
                "Claim: " + claim_text + "\n\n"
                "Content: " + page_text + "\n\n"
                "Answer with EXACTLY ONE word: SUPPORTS if the content confirms "
                "the claim, REFUTES if it contradicts the claim, INSUFFICIENT "
                "if the content does not mention the subject of the claim."
            )
            a = gl.nondet.exec_prompt(prompt).strip().upper()
            if "REFUT" in a:
                return "REFUTES"
            if "SUPPORT" in a:
                return "SUPPORTS"
            return "INSUFFICIENT"

        stance = gl.eq_principle.prompt_comparative(
            eval_stance,
            principle="Both outputs must be the same single verdict word."
        ).strip().upper()

        if stance != "SUPPORTS" and stance != "REFUTES":
            stance = "INSUFFICIENT"

        c["evidence"].append({
            "url": p["url"],
            "domain": p["domain"],
            "tier": p["tier"],
            "party_supplied": p["party"],
            "stance": stance,
            "weight": self._weight(p["tier"], stance, p["party"])
        })
        c["pending"] = {}
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return stance

    @gl.public.write
    def drop_pending_source(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        c["pending"] = {}
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return "DROPPED"

    @gl.public.write
    def finish_verification(self, claim_id: int) -> str:
        c = json.loads(self.claims[claim_id])
        sup = 0
        ref = 0
        for e in c["evidence"]:
            if e["stance"] == "SUPPORTS":
                sup = sup + e["weight"]
            elif e["stance"] == "REFUTES":
                ref = ref + e["weight"]

        total = sup + ref
        verdict = "INSUFFICIENT_EVIDENCE"
        conf = 0

        if sup >= 4000 and sup > (ref * 1.5):
            verdict = "TRUE"
            conf = int((sup * 100) / total)
        elif ref >= 4000 and ref > (sup * 1.5):
            verdict = "FALSE"
            conf = int((ref * 100) / total)
        elif total > 0:
            verdict = "DISPUTED"
            conf = 50

        if conf > 99:
            conf = 99

        c["verdict"] = verdict
        c["confidence"] = conf
        c["status"] = "PROVISIONAL"
        self.claims[claim_id] = json.dumps(c, sort_keys=True)
        return verdict

    @gl.public.view
    def get_claim(self, claim_id: int) -> str:
        return self.claims[claim_id]

    @gl.public.view
    def total_claims(self) -> int:
        return len(self.claims)
