"""Server-side screening engine. Runs on the host, not the browser, so
there's no CORS restriction calling the OpenSanctions API directly."""

import csv
import io
import re
import unicodedata
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher

import requests

API_URL = "https://api.opensanctions.org"


def risk_label(score):
    if score >= 0.85:
        return "Possible hit"
    if score >= 0.6:
        return "Needs review"
    return "Low relevance"


def overall_result(os_matches, uae_matches, un_matches=None):
    un_matches = un_matches or []
    all_scores = ([m.get("score", 0) for m in os_matches] + [m.get("score", 0) for m in uae_matches]
                  + [m.get("score", 0) for m in un_matches])
    if not all_scores:
        return "Clear"
    return risk_label(max(all_scores))


def call_match(queries, api_key, limit=20):
    resp = requests.post(
        f"{API_URL}/match/default",
        headers={"Content-Type": "application/json", "Authorization": f"ApiKey {api_key}"},
        json={"queries": queries},
        timeout=30,
    )
    if not resp.ok:
        detail = ""
        try:
            detail = resp.json().get("detail", "")
        except Exception:
            pass
        raise RuntimeError(f"API error {resp.status_code}: {detail or resp.text[:200]}")
    return resp.json()


def build_query(row, limit=20):
    properties = {"name": [row["name"]]}
    if row.get("country"):
        properties["country"] = [row["country"]]
    if row.get("birthDate"):
        properties["birthDate"] = [row["birthDate"]]
    return {"schema": row.get("schema", "Person"), "properties": properties}


def fetch_entity_detail(entity_id, api_key):
    try:
        resp = requests.get(f"{API_URL}/entities/{entity_id}",
                             headers={"Authorization": f"ApiKey {api_key}"}, timeout=20)
    except Exception:
        return None
    if resp.status_code == 429:
        raise RuntimeError("API error 429: rate limited")
    if not resp.ok:
        return None
    return resp.json()


def extract_entity_detail(raw, primary_caption=""):
    if not raw:
        return {}
    props = raw.get("properties", {}) or {}
    out = {
        "also_known_as": [a for a in props.get("alias", []) + props.get("weakAlias", []) if a and a != primary_caption][:10],
        "birth_dates": props.get("birthDate", [])[:3],
        "countries": props.get("country", [])[:5],
        "positions": props.get("position", [])[:5],
        "sanctions": [],
    }
    for s in (raw.get("referents") or []):
        pass  # referents not used at this depth
    for prog in props.get("sanctions", []) if isinstance(props.get("sanctions"), list) else []:
        out["sanctions"].append({"authority": "", "program": str(prog), "reason": "", "startDate": ""})
    return out


def screen_one(row, api_key, threshold, limit=20, fetch_detail=True):
    """Screens a single row against OpenSanctions. Returns list of match dicts."""
    data = call_match({"q1": build_query(row, limit)}, api_key, limit=limit)
    results = [m for m in data["responses"]["q1"].get("results", []) if (m.get("score") or 0) >= threshold]
    if fetch_detail:
        for m in results:
            m["_detail"] = extract_entity_detail(
                fetch_entity_detail(m.get("id"), api_key), primary_caption=m.get("caption", ""))
    return results


def screen_batch(rows, api_key, threshold, limit=20, fetch_detail=True, progress_cb=None):
    """Screens up to 100 rows per OpenSanctions batch call. Returns a dict
    keyed by row index -> list of matches."""
    all_results = {}
    batches = [rows[i:i + 100] for i in range(0, len(rows), 100)]
    done = 0
    for b_idx, batch in enumerate(batches):
        queries = {f"n{i}": build_query(r, limit) for i, r in enumerate(batch)}
        data = call_match(queries, api_key, limit=limit)
        for i, r in enumerate(batch):
            matches = [m for m in data["responses"][f"n{i}"].get("results", []) if (m.get("score") or 0) >= threshold]
            if fetch_detail and matches:
                for m in matches:
                    m["_detail"] = extract_entity_detail(
                        fetch_entity_detail(m.get("id"), api_key), primary_caption=m.get("caption", ""))
            all_results[done + i] = matches
        done += len(batch)
        if progress_cb:
            progress_cb(done, len(rows))
    return all_results


# ---------- UAE Local Terrorist List (fuzzy match, in-memory) ----------

def normalize_name(name):
    if not name:
        return ""
    name = unicodedata.normalize("NFKD", name)
    name = "".join(c for c in name if not unicodedata.combining(c))
    name = re.sub(r"[^A-Za-z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip().upper()


def name_similarity(a, b):
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    direct = SequenceMatcher(None, na, nb).ratio()
    sorted_a = " ".join(sorted(na.split()))
    sorted_b = " ".join(sorted(nb.split()))
    sorted_ratio = SequenceMatcher(None, sorted_a, sorted_b).ratio()
    return max(direct, sorted_ratio)


def load_uae_list_from_csv_text(csv_text):
    records = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        records.append(row)
    return records


def match_uae_local_list(query_name, records, threshold):
    results = []
    for rec in records:
        if rec.get("status") != "Listed":
            continue
        candidates = [rec.get("full_name_latin", ""), rec.get("family_name_latin", "")]
        best = max((name_similarity(query_name, c) for c in candidates if c and c != "-"), default=0.0)
        if best >= threshold:
            results.append({"score": best, "record": rec})
    results.sort(key=lambda r: -r["score"])
    return results


UAE_CLASSIFICATION_MAP = {
    "يباهرإ صخش": "Terrorist Individual",
    "يباهرإ ميظنت": "Terrorist Organization",
    "يباهرإ نايك": "Terrorist Entity",
}


def uae_classification_en(classification_ar):
    return UAE_CLASSIFICATION_MAP.get((classification_ar or "").strip(), "Terrorist Designation")


def format_uae_listing_decision(ar_text):
    if not ar_text:
        return "\u2014"
    nums = re.findall(r"\d+", ar_text)
    if len(nums) >= 2:
        return f"UAE Cabinet Resolution No. {nums[-1]} of {nums[0]}"
    if nums:
        return f"UAE Cabinet Resolution (Ref. {nums[0]})"
    return "UAE Cabinet Resolution (see source list)"


UAE_PLACE_MAP = {
    ")انيلما( رصم": "Egypt (Minya)", ")ةزيجلا( رصم": "Egypt (Giza)",
    "- ستيك تناس سيفان": "Saint Kitts and Nevis", "ءاضيبلا - نميلا": "Yemen - Al Bayda",
    "اخلما زعت": "Taiz - Al Makha, Yemen", "اسمنلا": "Austria", "اكيرمأ": "United States",
    "انق-يدامح عجن": "Naga Hammadi - Qena, Egypt", "ايبيل": "Libya",
    "ايبيل - سلبارط": "Tripoli - Libya", "ايروس": "Syria", "ايروس - قشمد": "Damascus - Syria",
    "ايريجين وناك": "Kano, Nigeria", "ايريجين ياساكاي": "Yakasai, Nigeria",
    "ايريجين يمير": "Rimi, Nigeria", "ايسور": "Russia", "ايكرت": "Turkey",
    "ايناطيرب": "United Kingdom", "ةرهاقلا - رصم": "Cairo - Egypt", "ةقراشلا": "Sharjah, UAE",
    "ةميخلا سار ،سمرلا": "Al Rams, Ras Al Khaimah, UAE",
    "ةيبرعلا ةكلملما - ةدج ةيدوعسلا": "Jeddah - Kingdom of Saudi Arabia",
    "ةيدوعسلا": "Saudi Arabia", "تاراملإا": "United Arab Emirates",
    "تاراملإا - ةريجفلا": "Fujairah - UAE", "تاراملإا - ةقراشلا": "Sharjah - UAE",
    "تاراملإا - يبد": "Dubai - UAE", "تاراملإا - يبظوبأ": "Abu Dhabi - UAE",
    "تاراملإا ،نامجع ةرامإ": "Emirate of Ajman, UAE",
    "تاراملإا ،يبظوبا ةرامإ": "Emirate of Abu Dhabi, UAE", "تاراملاا": "United Arab Emirates",
    "تيوكلا": "Kuwait", "تيوكلا / ةيدوعسلا": "Saudi Arabia / Kuwait",
    "تيوكلا ةلود": "State of Kuwait", "دنهلا": "India", "ديوسلا": "Sweden",
    "ديوسلا :ةيلاحلا ايريبيل :ةقباسلا": "Formerly Liberia, currently Sweden",
    "رصم": "Egypt", "رصم - جاهوس": "Sohag - Egypt", "رطق": "Qatar", "قارعلا": "Iraq",
    "لاموصلا": "Somalia", "ناتسكاب": "Pakistan", "ناتسناغفأ": "Afghanistan",
    "ناريإ": "Iran", "ناريا": "Iran", "نانبل": "Lebanon", "ندرلأا": "Jordan",
    "نميلا": "Yemen", "نوئيس - نميلا": "Yemen - Seiyun", "نيرحبلا": "Bahrain",
    "هيدوعسلا": "Saudi Arabia", "يروس": "Syrian", "يريجين": "Nigerian",
    "يناريإ": "Iranian", "ينانبل": "Lebanese", "-": "\u2014", "": "\u2014",
}


def uae_place_en(ar_text):
    ar_text = (ar_text or "").strip()
    if not ar_text:
        return "\u2014"
    return UAE_PLACE_MAP.get(ar_text, "(see source list \u2014 not available in Latin script)")


# ---------- UN Consolidated Sanctions List (fuzzy match, in-memory) ----------

def _un_xml_text(node, *candidates):
    for tag in candidates:
        el = node.find(tag)
        if el is not None and el.text:
            return el.text.strip()
    return ""


def parse_un_xml_text(xml_text):
    root = ET.fromstring(xml_text)
    records = []
    for section_tag, kind in (("INDIVIDUALS", "Person"), ("ENTITIES", "Entity")):
        section = root.find(section_tag)
        if section is None:
            continue
        node_tag = "INDIVIDUAL" if kind == "Person" else "ENTITY"
        for node in section.findall(node_tag):
            name_parts = [
                _un_xml_text(node, "FIRST_NAME"), _un_xml_text(node, "SECOND_NAME"),
                _un_xml_text(node, "THIRD_NAME"), _un_xml_text(node, "FOURTH_NAME"),
            ]
            full_name = " ".join(p for p in name_parts if p and p.lower() != "na")
            aliases = []
            for alias_tag in ("INDIVIDUAL_ALIAS", "ENTITY_ALIAS"):
                for al in node.findall(alias_tag):
                    a = _un_xml_text(al, "ALIAS_NAME")
                    if a and a.lower() != "na":
                        aliases.append(a)
            nationality = ", ".join(
                v.text.strip() for v in node.findall(".//NATIONALITY/VALUE")
                if v.text and v.text.strip().lower() != "na"
            )
            dob = ""
            for dob_node in node.findall(".//INDIVIDUAL_DATE_OF_BIRTH"):
                dob = _un_xml_text(dob_node, "DATE", "YEAR") or dob
            ref = _un_xml_text(node, "REFERENCE_NUMBER", "DATAID")
            list_type = _un_xml_text(node, "UN_LIST_TYPE")
            listed_on = _un_xml_text(node, "LISTED_ON")
            if not full_name:
                continue
            records.append({
                "category": kind, "reference": ref, "full_name": full_name,
                "aliases": aliases, "nationality": nationality, "dob": dob,
                "un_list_type": list_type, "listed_on": listed_on,
            })
    return records


def parse_un_html_text(html_text):
    """Fallback parser for the UN site's rendered HTML/text export,
    matching the '**REF** Name: 1: X 2: Y 3: Z 4: W ... Nationality: ...'
    layout. Best-effort: if the UN changes this layout, this may return
    fewer records than the XML parser would."""
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"&nbsp;|&amp;", " ", text)
    text = re.sub(r"\s+", " ", text)

    pattern = re.compile(
        r"([A-Z]{2,3}[a-z]?\.\d{3,4})\s*Name:\s*1:\s*(.*?)\s*2:\s*(.*?)\s*3:\s*(.*?)\s*4:\s*(.*?)\s*"
        r"(?:Title:.*?)?(?:Designation:.*?)?DOB:\s*(.*?)\s*POB:.*?"
        r"Good quality a\.k\.a\.:\s*(.*?)\s*Low quality a\.k\.a\.:\s*(.*?)\s*"
        r"Nationality:\s*(.*?)\s*(?:Passport)",
        re.IGNORECASE,
    )
    records = []
    for m in pattern.finditer(text):
        ref, n1, n2, n3, n4, dob, good_aka, low_aka, nationality = m.groups()
        parts = [n1, n2, n3, n4]
        full_name = " ".join(p.strip() for p in parts if p and p.strip().lower() != "na")
        if not full_name:
            continue
        aliases = []
        for aka_block in (good_aka, low_aka):
            if not aka_block or aka_block.strip().lower() == "na":
                continue
            pieces = re.split(r"\b[a-z]\)\s*", aka_block)
            aliases.extend(p.strip() for p in pieces if p.strip())
        records.append({
            "category": "Person", "reference": ref.strip(), "full_name": full_name,
            "aliases": aliases, "nationality": nationality.strip(),
            "dob": "" if dob.strip().lower() == "na" else dob.strip(),
            "un_list_type": "", "listed_on": "",
        })
    return records


def load_un_list_from_text(raw_text, is_xml):
    try:
        return parse_un_xml_text(raw_text) if is_xml else parse_un_html_text(raw_text)
    except Exception:
        return []


def match_un_list(query_name, records, threshold):
    results = []
    for rec in records:
        candidates = [rec.get("full_name", "")] + rec.get("aliases", [])
        best = max((name_similarity(query_name, c) for c in candidates if c), default=0.0)
        if best >= threshold:
            results.append({"score": best, "record": rec})
    results.sort(key=lambda r: -r["score"])
    return results
