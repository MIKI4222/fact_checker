# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
"""FactChecker v2 - claim adjudication through a real evidence protocol."""

import json
from genlayer import *

# --- protocol limits -------------------------------------------------------
MAX_EVIDENCE_SOURCES = 6          # hard cap on nondet rounds per adjudication
MIN_INDEPENDENT_DOMAINS = 3       # distinct registrable domains required
MAX_PER_RESOLVER = 3              # slots one resolver family may occupy
MIN_AUTHORITATIVE_SOURCES = 2     # of which this many must be tier A/B
PAGE_CHARS = 2400                 # model input budget per source
RENDER_CHARS = 8000               # raw text kept before focusing
FOCUS_HEAD = 700                  # opening block: title, dateline, lede
FOCUS_WINDOW = 320                # context kept around each claim keyword

# --- authority tiers -------------------------------------------------------
TIER_A = "A"                      # primary / official
TIER_B = "B"                      # established secondary
TIER_C = "C"                      # general press
TIER_D = "D"                      # low authority
TIERS = (TIER_A, TIER_B, TIER_C, TIER_D)
TIER_WEIGHTS = {TIER_A: 10000, TIER_B: 7000, TIER_C: 4000, TIER_D: 1500}

# --- freshness -------------------------------------------------------------
FRESH_DAYS = 180                  # full weight while newer than this
STALE_DAYS = 1825                 # floor weight once older than this
FRESHNESS_FLOOR = 3000
UNKNOWN_DATE_WEIGHT = 5000        # undated pages lose half their weight

# --- anti cherry-picking ---------------------------------------------------
PARTY_SUPPLIED_CAP = 4000         # max weight for a URL supplied by a party

# --- verdict thresholds (basis points of the 0..10000 margin) --------------
DECISIVE_MARGIN = 3000
CONFLICT_MARGIN = 1200

# --- lifecycle -------------------------------------------------------------
CHALLENGE_WINDOW_DAYS = 7
SUBMISSION_BOND = 100
CHALLENGE_BOND = 250
SUBMITTER_REWARD = 50
STARTING_CREDITS = 1000

STATUS_PENDING = "PENDING"
STATUS_PROVISIONAL = "PROVISIONAL"
STATUS_CHALLENGED = "CHALLENGED"
STATUS_FINAL = "FINAL"

STATUS_DISCOVERING = "DISCOVERING"
STATUS_GATHERING = "GATHERING"
STATUS_RESOLVING = "RESOLVING"

VERDICT_TRUE = "TRUE"
VERDICT_FALSE = "FALSE"
VERDICT_DISPUTED = "DISPUTED"
VERDICT_INSUFFICIENT = "INSUFFICIENT_EVIDENCE"

STANCE_SUPPORTS = "SUPPORTS"
STANCE_REFUTES = "REFUTES"
STANCE_UNRELATED = "UNRELATED"
STANCE_INSUFFICIENT = "INSUFFICIENT"
STANCES = (STANCE_SUPPORTS, STANCE_REFUTES, STANCE_UNRELATED, STANCE_INSUFFICIENT)

SEED_SOURCES = (
    ("who.int", TIER_A), ("un.org", TIER_A), ("worldbank.org", TIER_A),
    ("imf.org", TIER_A), ("europa.eu", TIER_A), ("nasa.gov", TIER_A),
    ("cdc.gov", TIER_A), ("noaa.gov", TIER_A), ("bls.gov", TIER_A),
    ("census.gov", TIER_A), ("sec.gov", TIER_A), ("nih.gov", TIER_A),
    ("reuters.com", TIER_B), ("apnews.com", TIER_B), ("bbc.co.uk", TIER_B),
    ("bbc.com", TIER_B), ("nature.com", TIER_B), ("science.org", TIER_B),
    ("britannica.com", TIER_B), ("ourworldindata.org", TIER_B),
    ("doi.org", TIER_B),
    ("nytimes.com", TIER_C), ("theguardian.com", TIER_C), ("ft.com", TIER_C),
    ("bloomberg.com", TIER_C), ("wsj.com", TIER_C), ("economist.com", TIER_C),
    ("wikipedia.org", TIER_C), ("arxiv.org", TIER_C),
)


# --- pure helpers ----------------------------------------------------------

def _norm_address(value) -> str:
    return str(value).strip().lower()


def _norm_domain(url) -> str:
    text = str(url).strip().lower()
    if text.startswith("https://"):
        text = text[8:]
    elif text.startswith("http://"):
        text = text[7:]
    if text.startswith("www."):
        text = text[4:]
    text = text.split("/")[0]
    text = text.split("?")[0]
    text = text.split("#")[0]
    return text


def _registrable(domain: str) -> str:
    parts = str(domain).split(".")
    if len(parts) <= 2:
        return str(domain)
    if parts[-2] in ("co", "com", "org", "net", "gov", "ac", "edu") and len(parts[-1]) == 2:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _identity(url) -> str:
    base = _registrable(_norm_domain(url))
    if base != "doi.org":
        return base
    parts = str(url).split("doi.org/")
    if len(parts) < 2:
        return base
    prefix = parts[1].split("/")[0]
    if prefix.startswith("10.") and len(prefix) <= 12:
        return "doi.org/" + prefix
    return base


def _days_from_civil(year: int, month: int, day: int) -> int:
    y = year
    if month <= 2:
        y = y - 1
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    mp = (month + 9) % 12
    doy = (153 * mp + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def _parse_date(value) -> int:
    text = str(value).strip()
    if len(text) < 10:
        return -1
    try:
        year = int(text[0:4])
        month = int(text[5:7])
        day = int(text[8:10])
    except Exception:
        return -1
    if year < 1900 or year > 2200 or month < 1 or month > 12 or day < 1 or day > 31:
        return -1
    return _days_from_civil(year, month, day)


def _freshness_weight(published, as_of) -> int:
    start = _parse_date(published)
    now = _parse_date(as_of)
    if start < 0 or now < 0:
        return UNKNOWN_DATE_WEIGHT
    age = now - start
    if age < -2:
        return UNKNOWN_DATE_WEIGHT
    if age <= FRESH_DAYS:
        return 10000
    if age >= STALE_DAYS:
        return FRESHNESS_FLOOR
    span = STALE_DAYS - FRESH_DAYS
    return 10000 - ((10000 - FRESHNESS_FLOOR) * (age - FRESH_DAYS)) // span


def _clamp(value: int, low: int, high: int) -> int:
    if value < low:
        return low
    if value > high:
        return high
    return value


def _extract_json(raw) -> dict:
    text = str(raw).replace("```json", "").replace("```", "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    try:
        parsed = json.loads(text)
    except Exception:
        return {}
    if isinstance(parsed, dict):
        return parsed
    return {}


def _civil_from_days(days: int) -> str:
    z = int(days) + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    if m <= 2:
        y = y + 1
    return "%04d-%02d-%02d" % (y, m, d)


def _clock_to_day(value) -> str:
    if value is None:
        return ""
    
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            value = int(text)
        elif _parse_date(text[:10]) > 0:
            return text[:10]
        else:
            return ""

    if isinstance(value, (int, float)):
        ts = int(value)
        # Обработка миллисекунд от ноды
        if ts > 100000000000:
            ts = ts // 1000
        
        if ts <= 0:
            return ""
            
        return _civil_from_days(ts // 86400)
        
    return ""


BLOCK_MARKERS = (
    "unusual traffic", "verifying you are human", "verify you are human",
    "are you a robot", "i am not a robot", "captcha", "challenge-platform",
    "ddg-challenge", "anomaly detected", "access denied", "403 forbidden",
    "429 too many requests", "rate limit", "enable javascript and cookies",
    "please enable javascript", "checking your browser", "cloudflare",
)

_SEARCH_INFRA_DOMAINS = (
    "duckduckgo.com", "bing.com", "google.com", "gdeltproject.org",
    "crossref.org", "marginalia.nu", "microsoft.com", "w3.org", "schema.org",
)


def _looks_blocked(text):
    lowered = str(text)[:4000].lower()
    for marker in BLOCK_MARKERS:
        if marker in lowered:
            return True
    return False


_ASSET_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".ico", ".bmp", ".tif",
    ".css", ".js", ".json", ".xml", ".rss", ".zip", ".gz", ".mp4", ".mp3",
    ".woff", ".woff2", ".ttf", ".eot",
)


def _keywords(claim) -> list:
    words = []
    for raw in str(claim).lower().split():
        token = ""
        for char in raw:
            if char.isalnum():
                token = token + char
        if len(token) >= 5 and token not in words:
            words.append(token)
    return words[:8]


def _focus_text(page, claim) -> str:
    text = str(page)
    if len(text) <= PAGE_CHARS:
        return text

    lowered = text.lower()
    ranges = [(0, FOCUS_HEAD)]
    for word in _keywords(claim):
        at = lowered.find(word, FOCUS_HEAD)
        if at < 0:
            continue
        start = at - FOCUS_WINDOW // 2
        if start < FOCUS_HEAD:
            start = FOCUS_HEAD
        end = at + FOCUS_WINDOW
        if end > len(text):
            end = len(text)
        ranges.append((start, end))
    ranges.sort()

    merged = []
    for start, end in ranges:
        if len(merged) > 0 and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
            continue
        merged.append((start, end))

    pieces = []
    used = 0
    for start, end in merged:
        if used >= PAGE_CHARS:
            break
        if used + (end - start) > PAGE_CHARS:
            end = start + (PAGE_CHARS - used)
        pieces.append(text[start:end])
        used = used + (end - start)
    return " [...] ".join(pieces)


def _urls_from_text(text) -> list:
    body = str(text).replace("\\/", "/")
    stops = " \t\r\n\"'<>()[]{}|\\^`"
    found = []
    index = 0
    while True:
        start = body.find("http", index)
        if start < 0:
            break
        if not (body.startswith("http://", start) or body.startswith("https://", start)):
            index = start + 4
            continue
        end = start
        while end < len(body) and body[end] not in stops:
            end = end + 1
        candidate = body[start:end]
        while len(candidate) > 0 and candidate[-1] in ".,;:!?'\"":
            candidate = candidate[:-1]
        if len(candidate) > 12 and len(candidate) <= 400:
            lowered = candidate.lower().split("?")[0]
            if not lowered.endswith(_ASSET_SUFFIXES):
                found.append(candidate)
        index = end + 1
    return found


def _search_url(claim: str) -> str:
    query = ""
    for char in str(claim).strip()[:200]:
        if char.isalnum():
            query = query + char
        elif char == " ":
            query = query + "+"
        elif char in "-_.":
            query = query + char
    while "++" in query:
        query = query.replace("++", "+")
    return "https://duckduckgo.com/html/?q=" + query.strip("+")


def _search_urls(claim: str) -> list:
    query = _search_url(claim).split("?q=")[1]
    return [
        "https://lite.duckduckgo.com/lite/?q=" + query,
        "https://api.crossref.org/works?rows=20&select=URL,title&query=" + query,
        "https://api.gdeltproject.org/api/v2/doc/doc?query=" + query
        + "&mode=artlist&maxrecords=60&sort=hybridrel&format=json",
    ]


class FactChecker(gl.Contract):
    """Claim adjudication pool arbitrated by GenLayer validators."""

    config: str
    sources: DynArray[str]
    accounts: DynArray[str]
    claims: DynArray[str]

    def __init__(self):
        self.config = json.dumps({"owner": _norm_address(gl.message.sender_address)}, sort_keys=True)
        for domain, tier in SEED_SOURCES:
            self.sources.append(json.dumps({"domain": domain, "tier": tier}, sort_keys=True))

    def _cfg(self) -> dict:
        return json.loads(self.config)

    def _only_owner(self) -> None:
        assert _norm_address(gl.message.sender_address) == self._cfg()["owner"], "Only the owner may do this"

    def _find_source(self, domain: str) -> int:
        for index in range(len(self.sources)):
            record = json.loads(self.sources[index])
            if record["domain"] == domain:
                return index
        return -1

    def _tier_of(self, domain: str) -> str:
        index = self._find_source(domain)
        if index < 0:
            if "/" in domain:
                index = self._find_source(domain.split("/")[0])
            if index < 0:
                return ""
        tier = str(json.loads(self.sources[index])["tier"])
        if tier in TIER_WEIGHTS:
            return tier
        return ""

    def _find_account(self, address: str) -> int:
        wanted = _norm_address(address)
        for index in range(len(self.accounts)):
            record = json.loads(self.accounts[index])
            if record["address"] == wanted:
                return index
        return -1

    def _balance_of(self, address: str) -> int:
        index = self._find_account(address)
        if index < 0:
            return STARTING_CREDITS
        return int(json.loads(self.accounts[index])["balance"])

    def _set_balance(self, address: str, balance: int) -> None:
        wanted = _norm_address(address)
        index = self._find_account(wanted)
        record = json.dumps({"address": wanted, "balance": int(balance)}, sort_keys=True)
        if index < 0:
            self.accounts.append(record)
        else:
            self.accounts[index] = record

    def _debit(self, address: str, amount: int) -> None:
        current = self._balance_of(address)
        assert current >= int(amount), "Insufficient bond balance"
        self._set_balance(address, current - int(amount))

    def _credit(self, address: str, amount: int) -> None:
        self._set_balance(address, self._balance_of(address) + int(amount))

    def _claim_at(self, claim_id: int) -> dict:
        index = int(claim_id)
        assert 0 <= index < len(self.claims), "Claim does not exist"
        return json.loads(self.claims[index])

    def _store_claim(self, claim_id: int, record: dict) -> None:
        self.claims[int(claim_id)] = json.dumps(record, sort_keys=True)

    @gl.public.write
    def register_source(self, domain: str, tier: str) -> None:
        self._only_owner()
        assert tier in TIER_WEIGHTS, "Tier must be A, B, C or D"
        name = _registrable(_norm_domain(domain))
        assert len(name) > 3, "Domain is not valid"
        index = self._find_source(name)
        record = json.dumps({"domain": name, "tier": tier}, sort_keys=True)
        if index < 0:
            self.sources.append(record)
        else:
            self.sources[index] = record

    @gl.public.write
    def remove_source(self, domain: str) -> None:
        self._only_owner()
        name = _registrable(_norm_domain(domain))
        index = self._find_source(name)
        assert index >= 0, "Domain is not registered"
        self.sources[index] = json.dumps({"domain": name, "tier": "-"}, sort_keys=True)

    @gl.public.write
    def submit_claim(self, claim: str, url: str) -> int:
        text = str(claim).strip()
        assert 12 <= len(text) <= 400, "Claim must be between 12 and 400 characters"
        submitter = _norm_address(gl.message.sender_address)
        self._debit(submitter, SUBMISSION_BOND)

        party_urls = []
        supplied = str(url).strip()
        if supplied != "":
            assert supplied.startswith("http://") or supplied.startswith("https://"), "URL must start with http:// or https://"
            party_urls.append(supplied)

        claim_id = len(self.claims)
        self.claims.append(
            json.dumps(
                {
                    "id": claim_id,
                    "submitter": submitter,
                    "claim": text,
                    "party_urls": party_urls,
                    "status": STATUS_PENDING,
                    "verdict": "",
                    "confidence": 0,
                    "as_of": "",
                    "deadline_day": 0,
                    "challenger": "",
                    "argument": "",
                    "evidence": [],
                    "rounds": [],
                    "resolution": "",
                },
                sort_keys=True
            )
        )
        return claim_id

    def _today(self) -> str:
        try:
            day_str = _clock_to_day(gl.block.timestamp)
            if day_str != "":
                return day_str
        except Exception:
            pass

        return "2026-09-08"

    def _discover_endpoint(self, endpoint: str) -> dict:
        def read_endpoint() -> str:
            try:
                page = gl.nondet.web.render(endpoint, mode="text")[:12000]
            except Exception:
                return json.dumps({"urls": [], "outcome": "unreachable"}, sort_keys=True)
            if len(page) < 200:
                return json.dumps({"urls": [], "outcome": "empty"}, sort_keys=True)
            if _looks_blocked(page):
                return json.dumps({"urls": [], "outcome": "blocked"}, sort_keys=True)
            collected = []
            for candidate in _urls_from_text(page):
                base = _registrable(_norm_domain(candidate))
                if base == "" or base in _SEARCH_INFRA_DOMAINS:
                    continue
                if candidate not in collected:
                    collected.append(candidate)
            collected.sort()
            return json.dumps({"urls": collected[:40], "outcome": "ok"}, sort_keys=True)

        try:
            raw = gl.eq_principle.prompt_comparative(
                read_endpoint,
                principle=(
                    "Both outputs are JSON objects holding a urls list. They agree when at "
                    "least half of the domains appearing in one list also appear in the other, "
                    "or when both lists are empty. Ordering, counts and exact paths may differ."
                ),
            )
        except Exception:
            return {"urls": [], "outcome": "consensus failed"}
        parsed = _extract_json(raw)
        found = parsed.get("urls", [])
        result = []
        if isinstance(found, list):
            for item in found:
                if isinstance(item, str) and item.startswith("http"):
                    result.append(item)
        outcome = parsed.get("outcome", "ok")
        return {"urls": result, "outcome": outcome if isinstance(outcome, str) else "ok"}

    def _open_discovery(self, claim_id: int, entry: dict, mode: str) -> str:
        as_of = self._today()
        assert as_of != "", "Runtime clock is unavailable"

        endpoints = _search_urls(entry["claim"])
        entry["as_of"] = as_of
        entry["endpoints"] = endpoints
        entry["endpoint_cursor"] = 0
        entry["productive"] = 0
        entry["discovered"] = []
        entry["tried"] = []
        entry["discovery_mode"] = mode
        entry["evidence"] = []
        entry["selected"] = []
        entry["cursor"] = 0
        entry["status"] = STATUS_DISCOVERING
        self._store_claim(claim_id, entry)

        return json.dumps(
            {
                "claim_id": int(claim_id),
                "status": STATUS_DISCOVERING,
                "as_of": as_of,
                "endpoints": len(endpoints),
                "next_step": "discover_next",
            },
            sort_keys=True
        )

    def _discovery_done(self, entry: dict) -> bool:
        if int(entry.get("productive", 0)) >= 2:
            return True
        return int(entry.get("endpoint_cursor", 0)) >= len(entry.get("endpoints", []))

    def _read_source(self, claim: str, url: str, as_of: str) -> dict:
        claim_text = str(claim)
        source_url = str(url)
        today = str(as_of)

        def read_page() -> str:
            try:
                page = gl.nondet.web.render(source_url, mode="text")[:RENDER_CHARS]
            except Exception:
                return json.dumps({"stance": STANCE_INSUFFICIENT, "published": "",
                                   "specificity": 0, "is_primary": False, "quote": "",
                                   "note": "source could not be retrieved"}, sort_keys=True)
            if len(page) < 40:
                return json.dumps({"stance": STANCE_INSUFFICIENT, "published": "",
                                   "specificity": 0, "is_primary": False, "quote": "",
                                   "note": "source returned no readable text"}, sort_keys=True)
            if _looks_blocked(page):
                return json.dumps({"stance": STANCE_INSUFFICIENT, "published": "",
                                   "specificity": 0, "is_primary": False, "quote": "",
                                   "note": "source served an anti-bot page"}, sort_keys=True)
            focused = _focus_text(page, claim_text)
            prompt = (
                "Judge ONLY what this page states about the statement. "
                "Never use outside knowledge.\n\n"
                "STATEMENT: " + claim_text + "\n"
                "SOURCE URL: " + source_url + "\n"
                "TODAY (UTC): " + today + "\n"
                "PAGE TEXT (excerpted):\n" + focused + "\n\n"
                "Return this exact JSON schema and nothing else:\n"
                "{\"stance\": \"SUPPORTS or REFUTES or UNRELATED or INSUFFICIENT\",\n"
                " \"published\": \"YYYY-MM-DD or empty string\",\n"
                " \"specificity\": 0 to 100,\n"
                " \"is_primary\": true or false,\n"
                " \"quote\": \"at most 200 characters copied verbatim from the page\",\n"
                " \"note\": \"one short sentence\"}\n\n"
                "INSUFFICIENT: on topic but does not settle it. "
                "UNRELATED: does not address it. "
                "specificity: how directly the page addresses the exact statement."
            )
            return gl.nondet.exec_prompt(prompt)

        try:
            raw = gl.eq_principle.prompt_comparative(
                read_page,
                principle=(
                    "The stance field must be identical and the published field must be the same date. "
                    "The specificity field may differ by at most 20. Wording of quote and note may differ."
                ),
            )
        except Exception:
            raw = ""
        parsed = _extract_json(raw)

        stance = str(parsed.get("stance", STANCE_INSUFFICIENT)).upper()
        if stance not in STANCES:
            stance = STANCE_INSUFFICIENT

        specificity = parsed.get("specificity", 0)
        try:
            specificity = _clamp(int(specificity), 0, 100)
        except Exception:
            specificity = 0

        return {
            "stance": stance,
            "published": str(parsed.get("published", ""))[:10],
            "specificity": specificity,
            "is_primary": bool(parsed.get("is_primary", False)),
            "quote": str(parsed.get("quote", ""))[:200],
            "note": str(parsed.get("note", ""))[:200],
        }

    def _select_evidence(self, discovered: list, party_urls: list) -> list:
        selected = []
        seen = []
        buckets = {TIER_A: [], TIER_B: [], TIER_C: [], TIER_D: []}

        for url in discovered:
            domain = _identity(url)
            if domain == "" or domain in seen:
                continue
            tier = self._tier_of(domain)
            if tier == "":
                continue
            seen.append(domain)
            buckets[tier].append({"url": str(url), "domain": domain, "tier": tier, "party": False})

        families = {}
        for tier in TIERS:
            for item in buckets[tier]:
                if len(selected) >= MAX_EVIDENCE_SOURCES:
                    break
                family = item["domain"].split("/")[0]
                used = families.get(family, 0)
                if used >= MAX_PER_RESOLVER:
                    continue
                families[family] = used + 1
                selected.append(item)

        for url in party_urls:
            if len(selected) >= MAX_EVIDENCE_SOURCES:
                break
            domain = _identity(url)
            if domain == "" or domain in seen:
                continue
            seen.append(domain)
            tier = self._tier_of(domain)
            if tier == "":
                tier = TIER_D
            selected.append({"url": str(url), "domain": domain, "tier": tier, "party": True})

        return selected

    def _gather_evidence(self, claim: str, selected: list, as_of: str) -> list:
        records = []
        for item in selected:
            reading = self._read_source(claim, item["url"], as_of)
            weight = TIER_WEIGHTS[item["tier"]]
            weight = weight * _freshness_weight(reading["published"], as_of) // 10000
            weight = weight * (3000 + 70 * reading["specificity"]) // 10000
            if reading["is_primary"]:
                weight = weight * 12000 // 10000
            if item["party"] and weight > PARTY_SUPPLIED_CAP:
                weight = PARTY_SUPPLIED_CAP
            if reading["stance"] in (STANCE_UNRELATED, STANCE_INSUFFICIENT):
                weight = 0
            records.append(
                {
                    "url": item["url"],
                    "domain": item["domain"],
                    "tier": item["tier"],
                    "party_supplied": item["party"],
                    "stance": reading["stance"],
                    "published": reading["published"],
                    "freshness": _freshness_weight(reading["published"], as_of),
                    "specificity": reading["specificity"],
                    "is_primary": reading["is_primary"],
                    "weight": weight,
                    "quote": reading["quote"],
                    "note": reading["note"],
                }
            )
        return records

    def _adjudicate(self, records: list) -> dict:
        support = 0
        refute = 0
        counted = []
        authoritative = []
        best_support_weight = -1
        best_refute_weight = -1
        best_support_tier = "D"
        best_refute_tier = "D"

        for record in records:
            if int(record["weight"]) <= 0:
                continue
            if record["domain"] not in counted:
                counted.append(record["domain"])
            if record["tier"] in (TIER_A, TIER_B) and not record["party_supplied"]:
                if record["domain"] not in authoritative:
                    authoritative.append(record["domain"])
            
            t_weight = TIER_WEIGHTS.get(record["tier"], 0)
            if record["stance"] == STANCE_SUPPORTS:
                support = support + int(record["weight"])
                if t_weight > best_support_weight:
                    best_support_weight = t_weight
                    best_support_tier = record["tier"]
            elif record["stance"] == STANCE_REFUTES:
                refute = refute + int(record["weight"])
                if t_weight > best_refute_weight:
                    best_refute_weight = t_weight
                    best_refute_tier = record["tier"]

        total = support + refute
        quorum = len(counted) >= MIN_INDEPENDENT_DOMAINS and len(authoritative) >= MIN_AUTHORITATIVE_SOURCES

        if total == 0 or not quorum:
            return {
                "verdict": VERDICT_INSUFFICIENT,
                "confidence": 0,
                "support_weight": support,
                "refute_weight": refute,
                "independent_domains": len(counted),
                "authoritative_domains": len(authoritative),
                "rationale": "Evidence quorum not met: " + str(len(counted))
                + " independent domains, " + str(len(authoritative)) + " authoritative.",
            }

        margin = abs(support - refute) * 10000 // total
        winner = VERDICT_TRUE if support > refute else VERDICT_FALSE

        if margin < CONFLICT_MARGIN:
            verdict = VERDICT_DISPUTED
            rationale = "Credible sources materially conflict at a margin of " + str(margin) + " bps."
        elif margin < DECISIVE_MARGIN:
            winning_weight = best_support_weight if winner == VERDICT_TRUE else best_refute_weight
            losing_weight = best_refute_weight if winner == VERDICT_TRUE else best_support_weight
            winning_tier = best_support_tier if winner == VERDICT_TRUE else best_refute_tier
            losing_tier = best_refute_tier if winner == VERDICT_TRUE else best_support_tier

            if winning_weight > losing_weight:
                verdict = winner
                rationale = (
                    "Margin of " + str(margin) + " bps resolved by source authority: tier "
                    + winning_tier + " over tier " + losing_tier + "."
                )
            else:
                verdict = VERDICT_DISPUTED
                rationale = "Margin of " + str(margin) + " bps is below the decisive threshold with no authority advantage."
        else:
            verdict = winner
            rationale = (
                "Decisive weighted majority: " + str(support) + " support against "
                + str(refute) + " refute across " + str(len(counted)) + " independent domains."
            )

        confidence = margin if verdict in (VERDICT_TRUE, VERDICT_FALSE) else 0
        return {
            "verdict": verdict,
            "confidence": confidence,
            "support_weight": support,
            "refute_weight": refute,
            "independent_domains": len(counted),
            "authoritative_domains": len(authoritative),
            "rationale": rationale,
        }

    @gl.public.write
    def challenge(self, claim_id: int, counter_url: str, argument: str) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_PROVISIONAL, "Claim is not open for challenge"

        challenger = _norm_address(gl.message.sender_address)
        assert challenger != entry["submitter"], "The submitter cannot challenge their own claim"
        assert len(str(argument).strip()) >= 10, "An argument is required"

        domain = _registrable(_norm_domain(counter_url))
        assert self._tier_of(domain) != "", "Counter evidence must come from a registered source"

        today = self._today()
        assert today != "", "Runtime clock is unavailable"
        assert _parse_date(today) <= int(entry["deadline_day"]), "The challenge window has closed"

        self._debit(challenger, CHALLENGE_BOND)
        entry["challenger"] = challenger
        entry["argument"] = str(argument).strip()[:400]
        entry["party_urls"] = entry["party_urls"] + [str(counter_url).strip()]
        entry["status"] = STATUS_CHALLENGED
        self._store_claim(claim_id, entry)

        return json.dumps({"claim_id": int(claim_id), "challenger": challenger, "bond": CHALLENGE_BOND}, sort_keys=True)

    @gl.public.write
    def finalize(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_PROVISIONAL, "Claim is not provisional"

        today = self._today()
        assert today != "", "Runtime clock is unavailable"
        assert _parse_date(today) > int(entry["deadline_day"]), "The challenge window is still open"

        self._credit(entry["submitter"], SUBMISSION_BOND)
        if entry["verdict"] in (VERDICT_TRUE, VERDICT_FALSE):
            self._credit(entry["submitter"], SUBMITTER_REWARD)

        entry["status"] = STATUS_FINAL
        entry["resolution"] = "UNCHALLENGED: finalized on " + today
        self._store_claim(claim_id, entry)

        return json.dumps({"claim_id": int(claim_id), "verdict": entry["verdict"], "status": STATUS_FINAL}, sort_keys=True)

    @gl.public.write
    def start_verification(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_PENDING, "Claim is not pending"
        return self._open_discovery(claim_id, entry, "verification")

    @gl.public.write
    def discover_next(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_DISCOVERING, "No discovery round is open"

        if self._discovery_done(entry):
            return json.dumps(
                {
                    "claim_id": int(claim_id),
                    "discovered": len(entry["discovered"]),
                    "endpoints_remaining": 0,
                    "endpoint_results": entry["tried"],
                    "next_step": "begin_reading",
                    "note": "acquisition is complete",
                },
                sort_keys=True
            )

        cursor = int(entry["endpoint_cursor"])
        endpoint = entry["endpoints"][cursor]
        report = self._discover_endpoint(endpoint)

        added = 0
        discovered = entry["discovered"]
        for url in report["urls"]:
            if url not in discovered:
                discovered.append(url)
                added = added + 1

        entry["discovered"] = discovered
        entry["endpoint_cursor"] = cursor + 1
        if added > 0:
            entry["productive"] = int(entry["productive"]) + 1
        outcome = report["outcome"]
        entry["tried"] = entry["tried"] + [
            {"endpoint": endpoint, "outcome": outcome, "urls": added}
        ]
        self._store_claim(claim_id, entry)

        remaining = len(entry["endpoints"]) - entry["endpoint_cursor"]
        if self._discovery_done(entry):
            remaining = 0

        return json.dumps(
            {
                "claim_id": int(claim_id),
                "endpoint": endpoint,
                "outcome": outcome,
                "urls_added": added,
                "discovered": len(discovered),
                "endpoints_remaining": remaining,
                "next_step": "discover_next" if remaining > 0 else "begin_reading",
            },
            sort_keys=True
        )

    @gl.public.write
    def begin_reading(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_DISCOVERING, "No discovery round is open"

        selected = self._select_evidence(entry["discovered"], entry["party_urls"])
        resolving = entry["discovery_mode"] == "resolution"

        entry["selected"] = selected
        entry["evidence"] = []
        entry["cursor"] = 0
        entry["status"] = STATUS_RESOLVING if resolving else STATUS_GATHERING
        entry["rounds"] = entry["rounds"] + [
            {
                "round": len(entry["rounds"]) + 1,
                "type": "resolution discovery" if resolving else "discovery",
                "as_of": entry["as_of"],
                "endpoint_results": entry["tried"],
                "selected": len(selected),
            }
        ]
        self._store_claim(claim_id, entry)

        queue = []
        for item in selected:
            queue.append(item["domain"])

        return json.dumps(
            {
                "claim_id": int(claim_id),
                "status": entry["status"],
                "discovered": len(entry["discovered"]),
                "selected": len(selected),
                "queue": queue,
                "endpoint_results": entry["tried"],
                "next_step": "read_next_source" if len(selected) > 0 else (
                    "finish_resolution" if resolving else "finish_verification"
                ),
            },
            sort_keys=True
        )

    @gl.public.write
    def read_next_source(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] in (STATUS_GATHERING, STATUS_RESOLVING), "No evidence round is open"

        selected = entry["selected"]
        cursor = int(entry["cursor"])

        finish = "finish_verification"
        if entry["status"] == STATUS_RESOLVING:
            finish = "finish_resolution"

        if cursor >= len(selected):
            return json.dumps(
                {
                    "claim_id": int(claim_id),
                    "sources_read": cursor,
                    "remaining": 0,
                    "next_step": finish,
                    "note": "every selected source has already been read",
                },
                sort_keys=True
            )

        records = self._gather_evidence(entry["claim"], [selected[cursor]], entry["as_of"])
        entry["evidence"] = entry["evidence"] + records
        entry["cursor"] = cursor + 1
        self._store_claim(claim_id, entry)

        remaining = len(selected) - entry["cursor"]

        record = records[0]
        return json.dumps(
            {
                "claim_id": int(claim_id),
                "source": record["url"],
                "domain": record["domain"],
                "tier": record["tier"],
                "stance": record["stance"],
                "weight": record["weight"],
                "note": record["note"],
                "remaining": remaining,
                "next_step": "read_next_source" if remaining > 0 else finish,
            },
            sort_keys=True
        )

    @gl.public.write
    def finish_verification(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_GATHERING, "No verification round is open"

        outcome = self._adjudicate(entry["evidence"])

        entry["verdict"] = outcome["verdict"]
        entry["confidence"] = outcome["confidence"]
        entry["deadline_day"] = _parse_date(entry["as_of"]) + CHALLENGE_WINDOW_DAYS
        entry["status"] = STATUS_PROVISIONAL
        entry["rounds"] = entry["rounds"] + [
            {
                "round": len(entry["rounds"]) + 1,
                "type": "initial",
                "as_of": entry["as_of"],
                "outcome": outcome,
            }
        ]
        self._store_claim(claim_id, entry)

        return json.dumps(
            {
                "claim_id": int(claim_id),
                "verdict": outcome["verdict"],
                "confidence": outcome["confidence"],
                "sources_used": len(entry["evidence"]),
                "independent_domains": outcome["independent_domains"],
                "authoritative_domains": outcome["authoritative_domains"],
                "rationale": outcome["rationale"],
            },
            sort_keys=True
        )

    @gl.public.write
    def start_resolution(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_CHALLENGED, "There is no open challenge"

        entry["previous_verdict"] = entry["verdict"]
        return self._open_discovery(claim_id, entry, "resolution")

    @gl.public.write
    def finish_resolution(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        assert entry["status"] == STATUS_RESOLVING, "No resolution round is open"

        outcome = self._adjudicate(entry["evidence"])
        previous = entry["previous_verdict"]
        final = outcome["verdict"]

        if final != previous:
            self._credit(entry["challenger"], CHALLENGE_BOND + SUBMISSION_BOND)
            resolution = "CHALLENGE_UPHELD: verdict changed from " + previous + " to " + final
        else:
            self._credit(entry["submitter"], SUBMISSION_BOND + CHALLENGE_BOND // 2)
            resolution = "CHALLENGE_REJECTED: verdict " + final + " confirmed on re-adjudication"

        entry["verdict"] = final
        entry["confidence"] = outcome["confidence"]
        entry["status"] = STATUS_FINAL
        entry["resolution"] = resolution
        entry["rounds"] = entry["rounds"] + [
            {
                "round": len(entry["rounds"]) + 1,
                "type": "challenge",
                "as_of": entry["as_of"],
                "outcome": outcome,
            }
        ]
        self._store_claim(claim_id, entry)

        return json.dumps({"claim_id": int(claim_id), "verdict": final, "resolution": resolution}, sort_keys=True)

    @gl.public.view
    def get_owner(self) -> str:
        return str(self._cfg()["owner"])

    @gl.public.view
    def get_source_tier(self, domain: str) -> str:
        return self._tier_of(_registrable(_norm_domain(domain)))

    @gl.public.view
    def get_sources(self) -> list[str]:
        result = []
        for index in range(len(self.sources)):
            result.append(self.sources[index])
        return result

    @gl.public.view
    def get_balance(self, address: str) -> int:
        return self._balance_of(address)

    @gl.public.view
    def get_claim(self, claim_id: int) -> str:
        index = int(claim_id)
        assert 0 <= index < len(self.claims), "Claim does not exist"
        return self.claims[index]

    @gl.public.view
    def get_progress(self, claim_id: int) -> str:
        entry = self._claim_at(claim_id)
        status = entry["status"]
        selected = entry.get("selected", [])
        cursor = int(entry.get("cursor", 0))
        remaining = len(selected) - cursor
        if remaining < 0:
            remaining = 0

        queue = []
        for item in selected:
            queue.append(item["domain"])

        if status == STATUS_PENDING:
            next_step = "start_verification"
        elif status == STATUS_DISCOVERING:
            next_step = "begin_reading" if self._discovery_done(entry) else "discover_next"
        elif status == STATUS_GATHERING:
            next_step = "read_next_source" if remaining > 0 else "finish_verification"
        elif status == STATUS_RESOLVING:
            next_step = "read_next_source" if remaining > 0 else "finish_resolution"
        elif status == STATUS_PROVISIONAL:
            next_step = "challenge or finalize"
        elif status == STATUS_CHALLENGED:
            next_step = "start_resolution"
        else:
            next_step = "none, the claim is final"

        return json.dumps(
            {
                "claim_id": int(claim_id),
                "status": status,
                "selected_count": len(selected),
                "sources_read": cursor,
                "remaining": remaining,
                "endpoints_tried": len(entry.get("tried", [])),
                "discovered": len(entry.get("discovered", [])),
                "queue": queue,
                "verdict": entry["verdict"],
                "next_step": next_step,
            },
            sort_keys=True
        )

    @gl.public.view
    def get_evidence(self, claim_id: int) -> str:
        return json.dumps(self._claim_at(claim_id)["evidence"], sort_keys=True)

    @gl.public.view
    def get_all_claims(self) -> list[str]:
        result = []
        for index in range(len(self.claims)):
            result.append(self.claims[index])
        return result

    @gl.public.view
    def get_claims_count(self) -> int:
        return len(self.claims)

    @gl.public.view
    def get_today(self) -> str:
        return self._today()

    @gl.public.view
    def get_stats(self) -> str:
        pending = 0
        provisional = 0
        challenged = 0
        final = 0
        true_count = 0
        false_count = 0
        disputed = 0
        insufficient = 0
        for index in range(len(self.claims)):
            record = json.loads(self.claims[index])
            status = record["status"]
            if status == STATUS_PENDING:
                pending = pending + 1
            elif status == STATUS_PROVISIONAL:
                provisional = provisional + 1
            elif status == STATUS_CHALLENGED:
                challenged = challenged + 1
            elif status == STATUS_FINAL:
                final = final + 1
            verdict = record["verdict"]
            if verdict == VERDICT_TRUE:
                true_count = true_count + 1
            elif verdict == VERDICT_FALSE:
                false_count = false_count + 1
            elif verdict == VERDICT_DISPUTED:
                disputed = disputed + 1
            elif verdict == VERDICT_INSUFFICIENT:
                insufficient = insufficient + 1
        return json.dumps(
            {
                "owner": self._cfg()["owner"],
                "registered_sources": len(self.sources),
                "claims_total": len(self.claims),
                "pending": pending,
                "provisional": provisional,
                "challenged": challenged,
                "final": final,
                "verdict_true": true_count,
                "verdict_false": false_count,
                "verdict_disputed": disputed,
                "verdict_insufficient": insufficient,
            },
            sort_keys=True
        )
