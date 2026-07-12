"""Import the O*NET occupation database into the game's knowledge format.

Produces onet_data.json: {name: {"path", "profile", "aliases"}} which
engine.build_seed_kb() merges with the hand-authored taxonomy.

Sources (O*NET 29.1, CC-BY 4.0, US Dept. of Labor / onetcenter.org):
  Occupation Data     -> 1,016 occupations + descriptions
  Alternate Titles    -> ~55,000 real-world job titles, kept as aliases
  Work Context (CX)   -> indoors, hazards, vehicles, hands, heights...
  Knowledge (IM)      -> medicine, law, chemistry, food, arts...
  Work Activities (IM)-> repairing, analyzing, teaching, selling...
  Job Zones           -> education / training requirements

Numeric elements map to question probabilities through a soft threshold
curve; title/description keywords fill in the niche attributes numbers
can't express. Occupations that no question in the bank can distinguish
are merged (absorbed as aliases) - they become separate again the moment
a discriminating question exists.

Usage: python onet_import.py [path-to-db_29_1_text.zip]
"""

from __future__ import annotations

import io
import json
import math
import os
import re
import sys
import urllib.request
import zipfile
from difflib import SequenceMatcher

import taxonomy

ZIP_URL = "https://www.onetcenter.org/dl_files/database/db_29_1_text.zip"
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "onet_data.json")

# ---------------------------------------------------------------- helpers

def smooth(x: float, lo: float, hi: float) -> float:
    """Map a 0-1 element score to a probability with a soft threshold band."""
    if hi <= lo:
        return 0.5
    t = (x - lo) / (hi - lo)
    t = max(0.0, min(1.0, t))
    t = t * t * (3 - 2 * t)  # smoothstep
    return round(0.04 + 0.92 * t, 3)


def singular(word: str) -> str:
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def name_parts(title: str) -> list[str]:
    """'Chefs and Head Cooks' -> ['chef', 'head cook'] ; 'lawyer / attorney' -> both."""
    t = re.sub(r"\(.*?\)", "", title.lower())
    parts = re.split(r"\s*(?:/|,| and | & )\s*", t)
    out = []
    for p in parts:
        p = " ".join(singular(w) for w in p.split())
        if p:
            out.append(p)
    return out


# ------------------------------------------------- element -> question map

SECTOR_BY_SOC = {
    "11": "business, finance & management", "13": "business, finance & management",
    "15": "software & information technology", "17": "engineering",
    "19": "science & research", "21": "personal & community services",
    "23": "law, government & public safety", "25": "education",
    "27": "arts, media & entertainment", "29": "healthcare & medicine",
    "31": "healthcare & medicine", "33": "law, government & public safety",
    "35": "hospitality, food & tourism", "37": "personal & community services",
    "39": "personal & community services", "41": "sales, marketing & customer service",
    "43": "business, finance & management", "45": "agriculture, nature & animals",
    "47": "construction & skilled trades", "49": "construction & skilled trades",
    "51": "manufacturing & production", "53": "transport & logistics",
    "55": "law, government & public safety",
}


def derive_profile(e: dict[str, float], jz: int, soc: str) -> dict[str, float]:
    """Turn O*NET element scores (already scaled 0-1) into question beliefs."""

    def g(name, default=0.0):
        return e.get(name, default)

    p: dict[str, float] = {}
    xi, xo = g("Indoors, Environmentally Controlled", .7), g("Outdoors, Exposed to Weather")
    p["indoors"] = smooth((xi + (1 - xo)) / 2, .35, .75)
    p["screen"] = smooth(g("Working with Computers"), .55, .85)
    p["public"] = smooth(.7 * g("Deal With External Customers") + .3 * g("Contact With Others", .5), .45, .8)
    p["people_core"] = smooth(.6 * g("Assisting and Caring for Others") +
                              .4 * g("Customer and Personal Service"), .5, .85)
    p["data_info"] = smooth((g("Analyzing Data or Information") + g("Processing Information") +
                             g("Documenting/Recording Information")) / 3, .5, .85)
    p["hands"] = smooth(g("Spend Time Using Your Hands to Handle, Control, or Feel Objects, Tools, or Controls"), .45, .8)
    p["physical"] = smooth((g("Performing General Physical Activities") +
                            g("Spend Time Standing") + g("Spend Time Walking and Running")) / 3, .4, .7)
    p["tools"] = smooth(max(g("Repairing and Maintaining Mechanical Equipment"),
                            .75 * g("Spend Time Using Your Hands to Handle, Control, or Feel Objects, Tools, or Controls")), .45, .75)
    p["machines_op"] = smooth(g("Operating Vehicles, Mechanized Devices, or Equipment"), .5, .85)
    p["uniform"] = smooth(max(g("Wear Common Protective or Safety Equipment such as Safety Shoes, Glasses, Gloves, Hearing Protection, Hard Hats, or Life Jackets"),
                              1.15 * g("Wear Specialized Protective or Safety Equipment such as Breathing Apparatus, Safety Harness, Full Protection Suits, or Radiation Protection")), .4, .75)
    p["danger"] = smooth(max(g("Exposed to Hazardous Conditions"), g("Exposed to Hazardous Equipment"),
                             .8 * g("Exposed to High Places"), .8 * g("Exposed to Radiation"),
                             .6 * g("Exposed to Disease or Infections"),
                             .6 * g("Deal With Physically Aggressive People")), .35, .7)
    p["heights"] = smooth(max(g("Exposed to High Places"),
                              g("Spend Time Climbing Ladders, Scaffolds, or Poles")), .4, .75)
    p["driving"] = smooth(g("In an Enclosed Vehicle or Equipment"), .5, .85)
    p["manage"] = smooth((g("Guiding, Directing, and Motivating Subordinates") +
                          g("Coordinating the Work and Activities of Others")) / 2, .5, .8)
    p["teach"] = smooth(.6 * g("Training and Teaching Others") + .4 * g("Education and Training"), .58, .85)
    p["creative"] = smooth(.55 * g("Thinking Creatively") + .55 * g("Fine Arts"), .5, .8)
    p["writing"] = smooth(.4 * g("Letters and Memos") + .6 * g("English Language"), .55, .85)
    p["speaking"] = smooth(g("Public Speaking"), .45, .8)
    p["numbers"] = smooth(.6 * g("Mathematics") + .4 * g("Economics and Accounting"), .45, .75)
    p["adv_math"] = smooth(g("Mathematics"), .62, .88)
    p["sales"] = smooth(.5 * g("Selling or Influencing Others") + .5 * g("Sales and Marketing"), .5, .8)
    p["market_promo"] = smooth(g("Sales and Marketing"), .6, .88)
    p["legal"] = smooth(g("Law and Government"), .55, .85)
    p["science"] = smooth(max(g("Physics"), .9 * g("Chemistry"), .9 * g("Biology")), .5, .8)
    p["living"] = smooth(max(g("Biology"), .7 * g("Medicine and Dentistry")), .45, .8)
    p["healthcare"] = smooth(g("Medicine and Dentistry"), .45, .75)
    p["patients"] = smooth(.55 * g("Medicine and Dentistry") + .45 * g("Assisting and Caring for Others"), .55, .8)
    p["care_daily"] = smooth(g("Assisting and Caring for Others"), .62, .88)
    p["mental_health"] = smooth(.6 * g("Therapy and Counseling") + .4 * g("Psychology"), .55, .85)
    p["hardware"] = smooth(.7 * g("Repairing and Maintaining Electronic Equipment") +
                           .3 * g("Computers and Electronics"), .5, .8)
    p["comms_net"] = smooth(g("Telecommunications"), .55, .85)
    p["buildings"] = smooth(g("Building and Construction"), .45, .78)
    p["fix_repair"] = smooth(max(g("Repairing and Maintaining Mechanical Equipment"),
                                 g("Repairing and Maintaining Electronic Equipment")), .45, .75)
    p["factory"] = smooth(g("Production and Processing"), .5, .82)
    p["food_domain"] = smooth(g("Food Production"), .5, .82)
    p["hist_culture"] = smooth(g("History and Archeology"), .55, .85)
    p["language_dom"] = smooth(g("Foreign Language"), .55, .85)
    p["earth_env"] = smooth(g("Geography"), .55, .85)
    p["religion"] = smooth(g("Philosophy and Theology"), .55, .85)
    p["protect"] = smooth(max(.8 * g("Responsible for Others' Health and Safety"),
                              g("Public Safety and Security")), .55, .85)
    p["enforce"] = smooth(.5 * g("Evaluating Information to Determine Compliance with Standards") +
                          .5 * g("Public Safety and Security"), .52, .82)
    p["design"] = smooth(.55 * g("Design") + .45 * g("Drafting, Laying Out, and Specifying Technical Devices, Parts, and Equipment"), .5, .8)
    p["visual"] = smooth(.5 * g("Design") + .5 * g("Fine Arts"), .55, .85)
    p["test_qa"] = smooth(g("Inspecting Equipment, Structures, or Materials"), .58, .88)
    p["data_work"] = smooth(g("Analyzing Data or Information"), .62, .9)
    p["hiring"] = smooth(g("Personnel and Human Resources"), .6, .88)
    p["finance_ind"] = smooth(g("Economics and Accounting"), .6, .88)
    p["money_others"] = smooth(g("Economics and Accounting"), .68, .92)
    p["chemicals"] = smooth(g("Chemistry"), .55, .85)
    p["shipping"] = smooth(g("Transportation"), .55, .85)
    p["news_media"] = smooth(g("Communications and Media"), .58, .88)
    p["content"] = smooth(g("Communications and Media"), .6, .9)
    p["office"] = smooth(.5 * g("Administrative") + .5 * min(xi, g("Working with Computers")), .45, .8)
    p["clean"] = 0.0  # keyword-driven

    # Job Zone -> education / pay
    p["degree"] = {1: .04, 2: .07, 3: .35, 4: .88, 5: .95}.get(jz, .4)
    p["long_training"] = {1: .02, 2: .05, 3: .15, 4: .45, 5: .85}.get(jz, .3)
    p["high_pay"] = {1: .12, 2: .25, 3: .42, 4: .6, 5: .75}.get(jz, .4)

    if soc.startswith("55"):
        p["military"] = .97
        p["government"] = .97
        p["uniform"] = .98
    if soc.startswith("33"):
        p["government"] = .7
    if soc.startswith(("29", "31")):
        p["healthcare"] = max(p.get("healthcare", 0), .8)

    # drop values indistinguishable from the question default (keeps KB lean)
    q_defs = {qid: d for qid, (d, _) in taxonomy.QUESTIONS.items()}
    return {qid: v for qid, v in p.items()
            if qid in q_defs and abs(v - q_defs[qid]) >= 0.12}


# keyword rules: regex on title+description -> attribute floors
KEYWORD_RULES: list[tuple[str, dict[str, float]]] = [
    (r"\bengineer", {"engineer_id": .9}),
    (r"aerospace|aircraft|avionics|aviation|airline|flight|aeronautic", {"aircraft": .9, "vehicles": .7}),
    (r"\bpilots?\b|flight attendant", {"aircraft": .9, "travel": .8, "shifts": .8}),
    (r"air traffic", {"aircraft": .9, "shifts": .85}),
    (r"marine|ship|vessel|sailors|maritime|dredge", {"ships": .85, "water": .8}),
    (r"\bfish", {"water": .8, "animals": .6, "indoors": .05}),
    (r"rail|locomotive|subway|streetcar", {"rail": .9, "vehicles": .8}),
    (r"automotive|motor vehicle|\bbus\b|truck|taxi|ambulance driver", {"vehicles": .85}),
    (r"engine\b|engines\b|diesel", {"engines": .8}),
    (r"power plant|petroleum|\bgas\b|nuclear|solar|wind energy|energy|power line|powerhouse", {"energy": .8}),
    (r"electrician|electrical", {"electric_wire": .8}),
    (r"plumb|pipefitter|pipelayer", {"pipes": .9}),
    (r"roof", {"heights": .9, "buildings": .8}),
    (r"insulation.*mechanical", {"pipes": .7}),
    (r"mining|miners|quarry|drill.*earth|extraction", {"mining": .85, "rocks": .7}),
    (r"software|programmer|developer|web develop", {"code": .9, "software": .9}),
    (r"database|network|systems administrator|computer support|information technology", {"servers": .8, "software": .8}),
    (r"information security|cybersecurity", {"cyber": .9, "software": .8}),
    (r"video game", {"games": .9}),
    (r"statistic|actuar", {"data_work": .85, "adv_math": .9}),
    (r"dental|dentist|orthodont", {"teeth": .9, "body_part": .9}),
    (r"optom|ophthalm|optician", {"eyes": .9, "body_part": .9}),
    (r"audiolog|hearing aid", {"hearing": .9, "body_part": .8}),
    (r"podiatr", {"feet": .9, "body_part": .9}),
    (r"chiropract|massage|physical therap", {"spine_joints": .85}),
    (r"anesthes", {"anesthesia": .95}),
    (r"surgeon|surgical", {"surgery": .9}),
    (r"obstetric|midwi[fv]", {"births": .9}),
    (r"psychiatr|psycholog|counselor|therapist|mental health", {"mental_health": .8}),
    (r"substance abuse|addiction", {"addiction": .9}),
    (r"nurse|nursing", {"patients": .85, "uniform": .9}),
    (r"physician|doctors|medical|clinical", {"healthcare": .8}),
    (r"veterinar|animal", {"animals": .85}),
    (r"pharmac", {"prescribe": .4, "healthcare": .85}),
    (r"funeral|mortician|embalmer|coroner", {"death": .9}),
    (r"epidemiolog|oncolog", {"serious_ill": .8}),
    (r"emergency|paramedic|firefighter|911", {"emergency": .9}),
    (r"police|sheriff|detective|correctional|bailiff|parole|probation", {"enforce": .9, "government": .9, "uniform": .8}),
    (r"judge|magistrate|lawyer|attorney|court", {"courtroom": .8, "legal": .9}),
    (r"tax\b|taxation", {"taxes": .9, "numbers": .9}),
    (r"payroll", {"payroll": .9}),
    (r"insurance", {"insurance": .9}),
    (r"loan|credit", {"loans": .85}),
    (r"new accounts", {"finance_ind": .85, "loans": .65, "public": .9}),
    (r"securities|trader|brokerage", {"trading": .8, "finance_ind": .9}),
    (r"real estate|property manager", {"property": .9}),
    (r"human resources|recruit", {"hiring": .9}),
    (r"teacher|instructor|professor|tutor", {"teach": .9}),
    (r"postsecondary|professor", {"teach_higher": .9}),
    (r"preschool|kindergarten|childcare", {"children": .9, "young_kids": .9}),
    (r"elementary school|middle school|secondary school", {"children": .85}),
    (r"special education|disabilit", {"disabilities": .85}),
    (r"librar", {"data_info": .85}),
    (r"farm|agricultur|crop|ranch", {"crops": .7, "plants": .6, "indoors": .1}),
    (r"forest|logging|tree", {"plants": .7, "wood": .6, "indoors": .1}),
    (r"landscap|grounds|garden|nursery worker", {"plants": .85, "indoors": .1}),
    (r"chef|cook|culinary|food prep|baker", {"cook": .9, "food_domain": .9}),
    (r"bartend|brewer|winemaker|sommelier", {"alcohol": .9, "food_domain": .8}),
    (r"waiter|waitress|restaurant|barista|dishwasher", {"hospitality": .85, "food_domain": .8}),
    (r"hotel|lodging|concierge", {"hospitality": .9}),
    (r"travel|tour guide", {"travel": .7, "hospitality": .6}),
    (r"janitor|maids|housekeep|custodian|cleaner", {"clean": .9}),
    (r"barber|hairdress|hairstyl|cosmetolog", {"hair": .9, "beauty": .9}),
    (r"manicur|skincare|makeup", {"nails_skin": .9, "beauty": .9}),
    (r"athlete|sports|coach|umpire|referee|fitness|exercise", {"fit_sport": .85}),
    (r"musician|singer|music", {"music_dom": .85, "perform": .6, "creative": .7}),
    (r"actor|actress|dancer|choreograph|entertainer", {"perform": .9, "creative": .7}),
    (r"artist|illustrat|painters.*(?!construction)", {"drawing": .6, "creative": .8}),
    (r"photograph", {"photos": .9, "creative": .7}),
    (r"film|video|camera|broadcast", {"video_anim": .8, "film_stage": .6}),
    (r"news|journalist|reporter|editor", {"news_media": .85, "writing": .85}),
    (r"writer|author|poet", {"writing": .9, "creative": .8, "content": .8}),
    (r"interpreter|translator", {"language_dom": .9}),
    (r"designer", {"design": .9, "creative": .7}),
    (r"fashion|apparel|garment|sewer|tailor|textile", {"fashion": .7, "sew": .7}),
    (r"jewel|gem", {"precious": .9}),
    (r"welder|welding|solder", {"metal": .9, "danger": .6}),
    (r"machinist|sheet metal|forging|metal work|boilermaker|foundry|steel", {"metal": .85, "factory": .7}),
    (r"carpenter|woodwork|cabinetmak", {"wood": .9}),
    (r"mason|brick|concrete|stone|cement", {"stone_brick": .9}),
    (r"glazier|glass", {"glass": .85}),
    (r"clergy|religious|chaplain", {"religion": .9}),
    (r"geolog|geoscien|seismic", {"rocks": .85, "earth_env": .8}),
    (r"environmental|conservation", {"pollution": .8, "earth_env": .7}),
    (r"meteorolog|atmospheric", {"earth_env": .9}),
    (r"biolog|microbiol|biochem|zoolog|botan", {"microbes": .4, "living": .9, "lab": .6}),
    (r"genetic", {"genes": .9, "lab": .7}),
    (r"chemist|chemical technician", {"chemicals": .9, "lab": .7}),
    (r"laboratory|\blab\b", {"lab": .85}),
    (r"research|scientist", {"research": .8, "science": .7}),
    (r"archaeolog|anthropolog|historian|museum|curator|archiv", {"hist_culture": .85}),
    (r"astronom|physicist", {"adv_math": .85, "science": .9}),
    (r"mathematic", {"adv_math": .95}),
    (r"logistic|freight|cargo|warehouse|shipping|courier|postal", {"shipping": .8}),
    (r"crane|hoist|derrick", {"machines_op": .9, "heights": .6}),
    (r"government|legislat|regulatory", {"government": .8}),
    (r"urban planner|city plan", {"government": .7, "buildings": .7}),
    (r"military|infantry|artillery|special forces", {"military": .95, "danger": .8}),
    (r"telemarket|call center|customer service", {"public": .85, "screen": .7}),
    (r"cashier|retail|salesperson|sales clerk", {"sales": .85, "public": .9}),
    (r"model(s|ing)?\b", {"perform": .7, "fashion": .7}),
    (r"security guard|surveillance", {"protect": .85, "uniform": .8}),
    (r"lifeguard", {"water": .9, "protect": .9}),
    (r"event|meeting.*convention", {"events_org": .85}),
    (r"advertis|marketing|public relations|promotion", {"market_promo": .9}),
    (r"accountant|auditor|bookkeep", {"numbers": .95, "data_info": .9}),
    (r"clerk|secretar|administrative assistant|receptionist|office", {"office": .8, "data_info": .7}),
]


# ---------------------------------------------------------------- parsing

def load_zip(path: str | None) -> zipfile.ZipFile:
    if path and os.path.exists(path):
        return zipfile.ZipFile(path)
    cache = os.path.join(os.path.dirname(OUT_PATH), "onet_db.zip")
    if not os.path.exists(cache):
        print(f"downloading {ZIP_URL} ...")
        urllib.request.urlretrieve(ZIP_URL, cache)
    return zipfile.ZipFile(cache)


def read_table(z: zipfile.ZipFile, name: str):
    with z.open(f"db_29_1_text/{name}") as f:
        text = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
        header = next(text).rstrip("\n").split("\t")
        for line in text:
            yield dict(zip(header, line.rstrip("\n").split("\t")))


def build(zip_path: str | None = None) -> dict:
    z = load_zip(zip_path)

    occs: dict[str, dict] = {}
    for row in read_table(z, "Occupation Data.txt"):
        title = row["Title"]
        if title.endswith("All Other"):
            continue  # catch-all buckets carry no identity
        occs[row["O*NET-SOC Code"]] = {
            "title": title, "desc": row["Description"], "e": {}, "jz": 3, "aliases": [],
        }

    for row in read_table(z, "Job Zones.txt"):
        if row["O*NET-SOC Code"] in occs:
            occs[row["O*NET-SOC Code"]]["jz"] = int(row["Job Zone"])

    def load_elements(fname: str, scale: str):
        for row in read_table(z, fname):
            code = row["O*NET-SOC Code"]
            if code not in occs or row["Scale ID"] != scale:
                continue
            if row.get("Recommend Suppress") == "Y":
                continue
            v = float(row["Data Value"])
            occs[code]["e"][row["Element Name"]] = max(0.0, min(1.0, (v - 1) / 4))

    load_elements("Work Context.txt", "CX")
    load_elements("Knowledge.txt", "IM")
    load_elements("Work Activities.txt", "IM")

    for row in read_table(z, "Alternate Titles.txt"):
        code = row["O*NET-SOC Code"]
        if code in occs:
            occs[code]["aliases"].append(row["Alternate Title"].lower().strip())

    # "Helpers--Roofers" etc. are junior twins of their parent trade: no
    # yes/no question separates helper from trade, so fold them in as aliases.
    for code in [c for c, o in occs.items() if o["title"].startswith("Helpers--")]:
        remainder = occs[code]["title"][len("Helpers--"):]
        target = next((c for c, o in occs.items() if o["title"] == remainder), None)
        if target is None:
            tok = remainder.split(",")[0].split()[0]
            cands = [c for c, o in occs.items()
                     if c != code and o["title"].split()[0] == tok]
            target = cands[0] if len(cands) == 1 else None
        if target:
            occs[target]["aliases"].append(occs[code]["title"].lower())
            occs[target]["aliases"].extend(occs[code]["aliases"])
            occs[target].setdefault("absorbed", []).append(code)
            del occs[code]

    # ---- profiles
    for code, o in occs.items():
        prof = derive_profile(o["e"], o["jz"], code)
        text = (o["title"] + " . " + o["desc"] + " . " +
                " ".join(o["aliases"][:40])).lower()
        for pattern, attrs in KEYWORD_RULES:
            if re.search(pattern, o["title"].lower()) or re.search(pattern, text[:400]):
                for qid, val in attrs.items():
                    if val > prof.get(qid, 0.0):
                        prof[qid] = val
        o["profile"] = prof

    # ---- merge occupations no yes/no question can tell apart
    # An occupation pair is "indistinguishable" when no question puts one in
    # the yes-bin and the other in the no-bin (a hard difference), and at
    # most a couple of questions differ between decisive and "not sure"
    # (soft differences). Such pairs would burn guesses without information,
    # so the weaker one is absorbed as an alias - it becomes a separate node
    # again the moment a discriminating question enters the bank.
    import numpy as np

    q_ids = list(taxonomy.QUESTIONS)
    q_default = {qid: d for qid, (d, _) in taxonomy.QUESTIONS.items()}

    def bin_row(prof) -> np.ndarray:
        row = np.empty(len(q_ids), dtype=np.int8)
        for j, qid in enumerate(q_ids):
            v = prof.get(qid, q_default[qid])
            row[j] = 1 if v >= .6 else (0 if v <= .4 else 2)
        return row

    def separable(rows: np.ndarray, i: int, j: int,
                  max_soft: int) -> bool:
        a, b = rows[i], rows[j]
        diff = a != b
        hard = ((a == 1) & (b == 0)) | ((a == 0) & (b == 1))
        return bool(hard.any()) or int(diff.sum()) > max_soft

    codes = list(occs)
    rows = np.stack([bin_row(occs[c]["profile"]) for c in codes])
    code_idx = {c: i for i, c in enumerate(codes)}

    absorbed: set[str] = set()
    merges = 0

    def absorb(keep: str, lose: str):
        nonlocal merges
        occs[keep]["aliases"].append(occs[lose]["title"].lower())
        occs[keep]["aliases"].extend(occs[lose]["aliases"])
        occs[keep].setdefault("absorbed", []).append(lose)
        occs[keep]["absorbed"].extend(occs[lose].get("absorbed", []))
        absorbed.add(lose)
        merges += 1

    # pass 1: same SOC minor group, up to 2 soft differences
    by_group: dict[str, list[str]] = {}
    for code in codes:
        by_group.setdefault(code[:5], []).append(code)
    for group_codes in by_group.values():
        for i, a in enumerate(group_codes):
            if a in absorbed:
                continue
            for b in group_codes[i + 1:]:
                if b in absorbed:
                    continue
                if not separable(rows, code_idx[a], code_idx[b], max_soft=2):
                    absorb(a, b)

    # pass 2: global, at most 1 soft difference (conservative across sectors)
    remaining = [c for c in codes if c not in absorbed]
    for i, a in enumerate(remaining):
        if a in absorbed:
            continue
        for b in remaining[i + 1:]:
            if b in absorbed:
                continue
            if not separable(rows, code_idx[a], code_idx[b], max_soft=1):
                absorb(a, b)

    for code in absorbed:
        del occs[code]

    # ---- match against the hand taxonomy (by name, then by profile)
    _, hand = taxonomy.compile()

    hand_names = list(hand)
    hand_rows = np.stack([bin_row(hand[n]["profile"]) for n in hand_names])

    def hand_twin(o) -> str | None:
        """Hand occupation this O*NET occupation cannot be distinguished from."""
        r = bin_row(o["profile"])
        diff = hand_rows != r
        hard = ((hand_rows == 1) & (r == 0)) | ((hand_rows == 0) & (r == 1))
        ok = ~hard.any(axis=1) & (diff.sum(axis=1) <= 1)
        idx = np.nonzero(ok)[0]
        return hand_names[idx[0]] if len(idx) else None
    hand_index: dict[str, str] = {}
    for name in hand:
        for part in name_parts(name):
            hand_index[part] = name

    def match_hand(o) -> str | None:
        cands = name_parts(o["title"]) + [a for a in o["aliases"][:25]]
        for cand in cands:
            cand = " ".join(singular(w) for w in cand.split())
            if cand in hand_index:
                return hand_index[cand]
        for cand in name_parts(o["title"]):
            best, score = None, 0.0
            for part, name in hand_index.items():
                r = SequenceMatcher(None, cand, part).ratio()
                if r > score:
                    best, score = name, r
            if score >= 0.92:
                return best
        return None

    def display_name(title: str) -> str:
        # singularize the last word of each " and "-joined segment:
        # "Orthotists and Prosthetists" -> "orthotist and prosthetist"
        segs = title.lower().split(" and ")
        out = []
        for seg in segs:
            words = seg.split()
            if words:
                words[-1] = singular(words[-1])
            out.append(" ".join(words))
        return " and ".join(out)

    out: dict[str, dict] = {}
    matched = 0
    for code, o in occs.items():
        hand_name = match_hand(o) or hand_twin(o)
        display = display_name(o["title"])
        aliases = sorted({a for a in o["aliases"] if a and a != display})
        socs = [code] + o.get("absorbed", [])
        if hand_name:
            matched += 1
            prev = out.setdefault("__merge__", {}).get(hand_name)
            if prev:  # two O*NET occupations mapping to one hand leaf
                prev["aliases"] = sorted(set(prev["aliases"]) | set(aliases))[:200]
                prev["soc"].extend(socs)
            else:
                out["__merge__"][hand_name] = {
                    "aliases": aliases[:200],
                    "fill": o["profile"],
                    "soc": socs,
                }
        else:
            sector = SECTOR_BY_SOC.get(code[:2], "business, finance & management")
            out[display] = {
                "path": [sector, f"SOC {code[:5]}x"],
                "profile": o["profile"],
                "aliases": aliases[:200],
                "soc": socs,
            }

    # drop aliases claimed by multiple occupations - they identify nothing
    counts: dict[str, int] = {}
    def alias_lists():
        for key, spec in out.items():
            if key == "__merge__":
                for m in spec.values():
                    yield m["aliases"]
            else:
                yield spec["aliases"]
    for aliases in alias_lists():
        for a in set(aliases):
            counts[a] = counts.get(a, 0) + 1
    dropped = 0
    for aliases in alias_lists():
        keep = [a for a in aliases if counts[a] == 1]
        dropped += len(aliases) - len(keep)
        aliases[:] = keep

    print(f"O*NET import: {len(occs)} occupations after {merges} indistinguishable merges")
    print(f"  matched to hand taxonomy: {matched}; new occupations: {len(out) - 1}")
    print(f"  ambiguous aliases dropped: {dropped}")
    return out


if __name__ == "__main__":
    data = build(sys.argv[1] if len(sys.argv) > 1 else None)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    size = os.path.getsize(OUT_PATH) / 1e6
    print(f"wrote {OUT_PATH} ({size:.1f} MB)")
