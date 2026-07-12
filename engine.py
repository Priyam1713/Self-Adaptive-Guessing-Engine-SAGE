"""Ever-learning Bayesian engine over a hierarchical occupation taxonomy.

Scale
-----
Occupations come from two sources merged at build time: the hand-authored
hierarchy (taxonomy.py) and the O*NET occupation database (onet_data.json,
built by onet_import.py) - roughly 1,000 distinguishable occupations wearing
~50,000 real-world job-title aliases. Titles resolve to occupations; unknown
occupations are learned from play. Inference is numpy-vectorized so the
candidate set can keep growing.

Knowledge model
---------------
Each (occupation, question) cell holds pseudo-counts {yes, no}; belief =
yes / (yes + no). Unset cells fall back to the question's world default
(near 0 for "do you work on aircraft?", near 0.5 for behavioral questions),
which is what lets thousands of occupations coexist without a dense matrix.

Inference & question selection (the optimal decision tree, computed live)
--------------------------------------------------------------------------
Answers are a simple yes / no (plus "not sure", which carries no evidence).
The next question always maximizes expected elimination - the expected
entropy reduction over the current survivors, exactly the greedy rule an
optimal decision tree applies at each node, recomputed live so the tree
reshapes itself whenever knowledge changes. Expected gain is computed under
the real answer model: survivor mass whose belief sits mid-range answers
"not sure" and yields nothing, so the selector prefers questions that
produce decisive answers. Answers score against beliefs with a Gaussian
kernel with a floor: one odd answer dampens a candidate, never kills it.

Budget: 30 questions, three guesses (after <=22, <=26, <=30 questions).
30 balanced yes/no questions can distinguish 2^30 = 1.07 billion outcomes;
~1,000 occupations need only ~10 bits, so most of the budget is noise margin.

Learning (the fallback for what the model misses)
-------------------------------------------------
Wins reinforce, losses correct, unknown occupations are imprinted and placed
next to their nearest neighbor, repeated confusions mint new questions, and
each question's usefulness is tracked from the share of remaining
uncertainty it actually removed in real games.
"""

from __future__ import annotations

import json
import math
import os
import random
from difflib import get_close_matches

import numpy as np

import taxonomy

_DIR = os.path.dirname(os.path.abspath(__file__))
KB_PATH = os.path.join(_DIR, "knowledge.json")
ONET_PATH = os.path.join(_DIR, "onet_data.json")
EMPLOYMENT_PATH = os.path.join(_DIR, "employment.json")

ANSWER_WEIGHTS = {
    "yes": 1.0,
    "no": 0.0,
    "unknown": 0.5,
    # legacy graded answers remain accepted
    "probably": 0.75,
    "probably_not": 0.25,
}

SIGMA = 0.30             # answer-noise width of the Gaussian match kernel
LIK_FLOOR = 0.06         # one contradictory answer dampens, never eliminates
SEED_STRENGTH = 10.0     # pseudo-observations behind hand-authored values
ONET_STRENGTH = 8.0      # pseudo-observations behind O*NET-derived values
CELL_CAP = 40.0          # max pseudo-counts per cell (enables belief drift)
NEW_CELL_PRIOR = 2.0     # virtual counts a fresh cell inherits from the default
NEW_CAREER_WEIGHT = 6.0  # how strongly one teaching game imprints a new occupation
GAME_STRENGTH = 2.0      # per-game evidence weight for known occupations
CONFUSION_DISTANCE = 0.15
USEFULNESS_EMA = 0.25

ROUND_LIMITS = (15, 22, 30)          # question budget before guesses 1, 2, 3
GUESS_CONFIDENCE = (0.80, 0.70, 0.60)
FIRST_GUESS_MIN_ASKED = 4
LEAD_RATIO = 4.0         # guess early when the leader is this far ahead of #2
CLAMP_RATIO = 100.0      # max employment-prior spread (keeps rare jobs findable)
GAIN_FLOOR = 0.04        # below this, no existing question splits the survivors
PRUNE_RATIO = 1e-3       # careers below top*ratio are ignored in gain computation


# ---------------------------------------------------------------- knowledge

def build_seed_kb() -> dict:
    q_defs, careers_src = taxonomy.compile()
    questions = {
        qid: {"text": q["text"], "default": q["default"],
              "source": "seed", "asked": 0, "usefulness": 0.5}
        for qid, q in q_defs.items()
    }
    careers = {}
    for name, spec in careers_src.items():
        cells = {
            qid: {"yes": round(p * SEED_STRENGTH, 3),
                  "no": round((1 - p) * SEED_STRENGTH, 3)}
            for qid, p in spec["profile"].items()
        }
        careers[normalize_name(name)] = {"plays": 0, "aliases": [], "path": spec["path"],
                                         "profile": cells}

    if os.path.exists(ONET_PATH):
        with open(ONET_PATH, "r", encoding="utf-8") as f:
            onet = json.load(f)
        merges = onet.pop("__merge__", {})
        for hand_name, m in merges.items():
            entry = careers.get(normalize_name(hand_name))
            if not entry:
                continue
            entry["aliases"] = sorted(set(entry["aliases"]) | set(m["aliases"]))[:250]
            entry["soc"] = m.get("soc", [])
            for qid, p in m["fill"].items():  # fill gaps only - hand values win
                if qid in questions and qid not in entry["profile"]:
                    entry["profile"][qid] = {"yes": round(p * ONET_STRENGTH, 3),
                                             "no": round((1 - p) * ONET_STRENGTH, 3)}
        for name, spec in onet.items():
            key = normalize_name(name)
            if key in careers:
                careers[key]["aliases"] = sorted(
                    set(careers[key]["aliases"]) | set(spec["aliases"]))[:250]
                careers[key].setdefault("soc", []).extend(spec.get("soc", []))
                continue
            cells = {
                qid: {"yes": round(p * ONET_STRENGTH, 3),
                      "no": round((1 - p) * ONET_STRENGTH, 3)}
                for qid, p in spec["profile"].items() if qid in questions
            }
            careers[key] = {"plays": 0, "aliases": spec["aliases"][:250],
                            "path": spec["path"], "profile": cells,
                            "soc": spec.get("soc", [])}

    _attach_priors(careers)
    return {
        "version": 3,
        "stats": {"games": 0, "wins_first": 0, "wins_second": 0,
                  "wins_third": 0, "losses": 0},
        "questions": questions,
        "careers": careers,
        "confusions": {},
    }


def _attach_priors(careers: dict) -> None:
    """Attach employment-based priors (Huffman-style weighting).

    With occupation frequencies as priors, greedy entropy splitting balances
    probability *mass* instead of candidate *count* - common occupations get
    isolated in few questions, rare ones ride the long tail, and the average
    beats log2(N). The spread is clamped so no occupation starts more than
    ~log2(CLAMP_RATIO) bits behind: rarity may cost extra questions, never
    findability. Priors shape speed only - correctness comes from evidence.
    """
    if not os.path.exists(EMPLOYMENT_PATH):
        return
    with open(EMPLOYMENT_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    detail = data.get("employment") or {}
    major = data.get("employment_major") or {}
    if not detail and not major:
        return

    variants: dict[str, int] = {}   # KB occupations sharing one detailed SOC
    major_counts: dict[str, int] = {}
    for entry in careers.values():
        socs = entry.get("soc", [])
        for code in socs:
            variants[code[:7]] = variants.get(code[:7], 0) + 1
        if socs:
            major_counts[socs[0][:2]] = major_counts.get(socs[0][:2], 0) + 1

    emp: dict[str, float] = {}
    for name, entry in careers.items():
        total = 0.0
        for code in entry.get("soc", []):
            d = code[:7]
            if d in detail:
                total += detail[d] / max(1, variants.get(d, 1))
            elif code[:2] in major:
                total += major[code[:2]] / max(1, major_counts.get(code[:2], 1))
        if total > 0:
            emp[name] = total
    if not emp:
        return

    vals = sorted(emp.values())
    p30 = vals[int(len(vals) * 0.3)]
    top = vals[-1]
    for name, entry in careers.items():
        if name in emp:
            continue
        if entry["path"][0] == "not currently employed":
            emp[name] = top * 0.5   # players think of these often enough
        else:
            emp[name] = p30         # hand-authored niches: below median, findable

    floor = top / CLAMP_RATIO
    for name, entry in careers.items():
        entry["prior"] = min(max(emp[name], floor), top)
    mean = sum(c["prior"] for c in careers.values()) / len(careers)
    for entry in careers.values():
        entry["prior"] = round(entry["prior"] / mean, 4)


def load_kb(path: str = KB_PATH) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            kb = json.load(f)
        if kb.get("version") == 3:
            return kb
    kb = build_seed_kb()
    save_kb(kb, path)
    return kb


def save_kb(kb: dict, path: str = KB_PATH) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)


def normalize_name(name: str) -> str:
    return " ".join(name.strip().lower().split())


def _name_variants(name: str) -> list[str]:
    """'sommelier (wine expert)' -> ['sommelier']; 'waiter / server' -> both."""
    base = normalize_name(__import__("re").sub(r"\(.*?\)", " ", name))
    parts = [normalize_name(p) for p in base.split("/")]
    return [p for p in {base, *parts} if p and p != name]


def resolve_career(kb: dict, name: str) -> tuple[str | None, str | None]:
    """Resolve a typed job title to a known occupation.

    Checks occupation names (and their own variants), then the ~50k title
    aliases, then containment and fuzzy matches. Returns
    (exact_or_alias_match, fuzzy_suggestion). Callers should confirm with the
    player whenever the match wasn't the occupation's own name - real-world
    title data is noisy.
    """
    name = normalize_name(name)
    if name in kb["careers"]:
        return name, None
    alias_map: dict[str, str] = {}
    for cname in kb["careers"]:  # an occupation's own name variants win...
        for variant in _name_variants(cname):
            alias_map.setdefault(variant, cname)
    for cname, entry in kb["careers"].items():  # ...over imported title aliases
        for alias in entry.get("aliases", []):
            alias_map.setdefault(alias, cname)
    if name in alias_map:
        return alias_map[name], None
    # containment: "senior propulsion engineer" contains "propulsion engineer"
    # (multi-word candidates only - single generic words match everything)
    pool = list(kb["careers"].keys()) + list(alias_map.keys())
    padded = f" {name} "
    best = None
    for cand in pool:
        if " " in cand and f" {cand} " in padded:
            if best is None or len(cand) > len(best):
                best = cand
    if best:
        return None, (best if best in kb["careers"] else alias_map[best])
    close = get_close_matches(name, pool, n=1, cutoff=0.85)
    if close:
        hit = close[0]
        return None, (hit if hit in kb["careers"] else alias_map[hit])
    return None, None


# ---------------------------------------------------------------- inference

def p_yes(kb: dict, career: str, qid: str) -> float:
    cell = kb["careers"][career]["profile"].get(qid)
    if not cell:
        return kb["questions"][qid]["default"]
    total = cell["yes"] + cell["no"]
    if total <= 0:
        return kb["questions"][qid]["default"]
    return cell["yes"] / total


def likelihood(answer_weight: float, prob_yes: float) -> float:
    """Gaussian match between an answer and a belief (see class docstring)."""
    if answer_weight == 0.5:
        return 1.0
    d = (answer_weight - prob_yes) / SIGMA
    return (1 - LIK_FLOOR) * math.exp(-0.5 * d * d) + LIK_FLOOR


def _lik_vec(answer_weight: float, p: np.ndarray) -> np.ndarray:
    d = (answer_weight - p) / SIGMA
    return (1 - LIK_FLOOR) * np.exp(-0.5 * d * d) + LIK_FLOOR


def _H(w: np.ndarray) -> float:
    nz = w[w > 1e-12]
    return float(-(nz * np.log2(nz)).sum())


class Game:
    """One round of play: posterior tracking, question choice, guessing."""

    def __init__(self, kb: dict, rng: random.Random | None = None):
        self.kb = kb
        self.rng = rng or random.Random()
        self.names = list(kb["careers"])
        # employment prior x gentle local-popularity boost: real play counts
        # refine the prior over time without drowning the labor statistics
        weights = np.array(
            [kb["careers"][n].get("prior", 1.0) * (1 + 0.3 * kb["careers"][n]["plays"])
             for n in self.names], dtype=float)
        self.post = weights / weights.sum()
        # evidence-only shadow posterior (uniform-ish prior): after a wrong
        # first guess the employment prior has done its job - failing on the
        # common-job region is evidence FOR the rare region, so recovery
        # switches to this one and rare occupations fight fair
        flat = np.array([1 + 0.3 * kb["careers"][n]["plays"] for n in self.names],
                        dtype=float)
        self.post_flat = flat / flat.sum()
        self.asked: list[tuple[str, float]] = []   # (question_id, answer_weight)
        self.excluded: list[str] = []              # wrong guesses this game
        self.guesses_made = 0
        self._cols: dict[str, np.ndarray] = {}
        self._sector_of = [kb["careers"][n]["path"][0] for n in self.names]

    def _col(self, qid: str) -> np.ndarray:
        col = self._cols.get(qid)
        if col is None:
            d = self.kb["questions"][qid]["default"]
            careers = self.kb["careers"]
            col = np.fromiter(
                ((c["yes"] / t if (t := c["yes"] + c["no"]) > 0 else d)
                 if (c := careers[n]["profile"].get(qid)) else d
                 for n in self.names),
                dtype=float, count=len(self.names))
            self._cols[qid] = col
        return col

    # -- survivors -----------------------------------------------------------

    def viable_count(self) -> int:
        """How many occupations are still realistically in the running."""
        return int((self.post >= self.post.max() * 0.01).sum())

    def sector_mass(self) -> list[tuple[str, float]]:
        """Posterior mass aggregated up the hierarchy, strongest sector first."""
        mass: dict[str, float] = {}
        for sector, p in zip(self._sector_of, self.post):
            mass[sector] = mass.get(sector, 0.0) + float(p)
        return sorted(mass.items(), key=lambda kv: kv[1], reverse=True)

    # -- question selection --------------------------------------------------

    def scored_questions(self) -> list[tuple[float, str]]:
        """All unasked questions with their elimination power, best first.

        Gain is expected entropy reduction over the survivors under the real
        answer model: survivors are grouped by the answer they would give
        (yes if belief >= .6, no if <= .4, otherwise "not sure"); not-sure
        mass contributes nothing.
        """
        asked_ids = {qid for qid, _ in self.asked}
        mask = self.post >= self.post.max() * PRUNE_RATIO
        w = self.post[mask]
        w = w / w.sum()
        h_now = _H(w)
        scored = []
        for qid, q in self.kb["questions"].items():
            if qid in asked_ids:
                continue
            p = self._col(qid)[mask]
            yes_m = p >= 0.6
            no_m = p <= 0.4
            h_after = float(w[~yes_m & ~no_m].sum()) * h_now
            for a, m in ((1.0, yes_m), (0.0, no_m)):
                pa = float(w[m].sum())
                if pa < 1e-9:
                    continue
                post = w * _lik_vec(a, p)
                post = post / post.sum()
                h_after += pa * _H(post)
            gain = max(0.0, h_now - h_after)
            scored.append((gain * (0.7 + 0.6 * q.get("usefulness", 0.5)), qid))
        scored.sort(reverse=True)
        return scored

    def next_question(self) -> tuple[str | None, float]:
        """Pick the question expected to eliminate the most candidates.

        Slight randomness among the near-best keeps games varied and gives
        newly minted questions airtime.
        """
        scored = self.scored_questions()
        if not scored:
            return None, 0.0
        top = [s for s in scored[:3] if s[0] > 0.75 * scored[0][0]] or scored[:1]
        weights = [s[0] + 1e-9 for s in top]
        choice = self.rng.choices(top, weights=weights, k=1)[0]
        return choice[1], scored[0][0]

    def stuck_pair(self) -> tuple[str, str] | None:
        """If no existing question can split the leaders, return the pair a
        newly synthesized question should discriminate."""
        scored = self.scored_questions()
        if scored and scored[0][0] >= GAIN_FLOOR:
            return None
        top2 = self.top(2)
        if len(top2) == 2 and top2[0][1] >= 0.2 and top2[1][1] >= 0.15:
            return top2[0][0], top2[1][0]
        return None

    # -- answers ---------------------------------------------------------

    def record_answer(self, qid: str, answer: str) -> None:
        w_ans = ANSWER_WEIGHTS[answer]
        h_before = _H(self.post)
        if w_ans != 0.5:
            lik = _lik_vec(w_ans, self._col(qid))
            post = self.post * lik
            s = post.sum()
            if s > 0:
                self.post = post / s
            flat = self.post_flat * lik
            s = flat.sum()
            if s > 0:
                self.post_flat = flat / s
        self.asked.append((qid, w_ans))
        q = self.kb["questions"][qid]
        q["asked"] = q.get("asked", 0) + 1
        # Usefulness = share of *remaining* uncertainty this question removed;
        # "not sure" answers are not the question's fault.
        if w_ans != 0.5 and h_before > 0.1:
            realized = max(0.0, h_before - _H(self.post))
            frac = min(1.0, realized / h_before)
            u = q.get("usefulness", 0.5)
            q["usefulness"] = round((1 - USEFULNESS_EMA) * u + USEFULNESS_EMA * frac, 4)

    # -- guessing ----------------------------------------------------------

    def top(self, n: int = 3) -> list[tuple[str, float]]:
        idxs = np.argsort(self.post)[::-1][:n]
        return [(self.names[i], float(self.post[i])) for i in idxs]

    def should_guess(self) -> bool:
        asked = len(self.asked)
        r = min(self.guesses_made, len(ROUND_LIMITS) - 1)
        if asked >= ROUND_LIMITS[r]:
            return True
        top2 = self.top(2)
        best = top2[0][1]
        second = top2[1][1] if len(top2) > 1 else 0.0
        if r == 0:
            if asked < FIRST_GUESS_MIN_ASKED:
                return False
            if best >= GUESS_CONFIDENCE[0]:
                return True
            # early decisive-lead guess, but only when the leader is a common
            # occupation - that is where the prior-weighted (Huffman) payoff
            # lives; a rare leader with a big lead is more often a confusion
            # and deserves the remaining question budget instead
            leader_common = self.kb["careers"][top2[0][0]].get("prior", 1.0) >= 1.0
            return leader_common and best >= 0.5 and best >= LEAD_RATIO * second
        return best >= GUESS_CONFIDENCE[r]

    def make_guess(self) -> str:
        self.guesses_made += 1
        return self.top(1)[0][0]

    def reject_guess(self, career: str) -> None:
        """Player said no: eliminate this occupation; after the first wrong
        guess, drop the employment prior (see post_flat above)."""
        self.excluded.append(career)
        if self.guesses_made >= 1:
            self.post = self.post_flat
        for c in self.excluded:
            if c in self.names:
                i = self.names.index(c)
                self.post[i] = 0.0
                self.post_flat[i] = 0.0
        s = self.post.sum()
        if s > 0:
            self.post = self.post / s
        else:
            self.post = np.full(len(self.names), 1.0 / len(self.names))
            for c in self.excluded:
                if c in self.names:
                    self.post[self.names.index(c)] = 0.0
            self.post /= self.post.sum()
        s = self.post_flat.sum()
        if s > 0:
            self.post_flat = self.post_flat / s


# ---------------------------------------------------------------- learning

def _nudge_cell(kb: dict, profile: dict, qid: str, weight: float,
                strength: float = 1.0) -> None:
    default = kb["questions"][qid]["default"]
    cell = profile.setdefault(qid, {"yes": NEW_CELL_PRIOR * default,
                                    "no": NEW_CELL_PRIOR * (1 - default)})
    total = cell["yes"] + cell["no"]
    if total + strength > CELL_CAP:  # decay old evidence so beliefs can drift
        scale = (CELL_CAP - strength) / total
        cell["yes"] *= scale
        cell["no"] *= scale
    cell["yes"] = round(cell["yes"] + strength * weight, 4)
    cell["no"] = round(cell["no"] + strength * (1 - weight), 4)


def profile_distance(kb: dict, a: str, b: str) -> float:
    """Mean absolute belief difference over questions either occupation sets."""
    pa = kb["careers"][a]["profile"]
    pb = kb["careers"][b]["profile"]
    qids = set(pa) | set(pb)
    if not qids:
        return 1.0
    return sum(abs(p_yes(kb, a, q) - p_yes(kb, b, q)) for q in qids) / len(qids)


def nearest_career(kb: dict, asked: list[tuple[str, float]],
                   exclude: str) -> str | None:
    """Existing occupation whose beliefs best match this game's answers."""
    informative = [(qid, w) for qid, w in asked if w != 0.5]
    if not informative:
        return None
    best, best_d = None, float("inf")
    for name in kb["careers"]:
        if name == exclude:
            continue
        d = sum(abs(w - p_yes(kb, name, qid)) for qid, w in informative)
        if d < best_d:
            best, best_d = name, d
    return best


def learn_from_game(kb: dict, true_career: str, asked: list[tuple[str, float]],
                    wrong_guesses: list[str], won_round: int) -> list[tuple[str, str]]:
    """Update the knowledge base after a game.

    won_round: 1/2/3 = which guess was right, 0 = lost.
    Returns confusion pairs (true, guessed) that deserve a new
    discriminating question.
    """
    true_career = normalize_name(true_career)
    is_new = true_career not in kb["careers"]
    if is_new:
        neighbor = nearest_career(kb, asked, exclude=true_career)
        path = kb["careers"][neighbor]["path"] if neighbor else ["uncategorized", "uncategorized"]
        kb["careers"][true_career] = {"plays": 0, "aliases": [], "path": list(path),
                                      "profile": {}}

    entry = kb["careers"][true_career]
    strength = NEW_CAREER_WEIGHT if is_new else GAME_STRENGTH
    for qid, w in asked:
        if w == 0.5:  # "not sure" carries no evidence
            continue
        _nudge_cell(kb, entry["profile"], qid, w, strength)
    entry["plays"] += 1

    kb["stats"]["games"] += 1
    key = {1: "wins_first", 2: "wins_second", 3: "wins_third"}.get(won_round, "losses")
    kb["stats"][key] = kb["stats"].get(key, 0) + 1

    needs_discriminator = []
    for guessed in wrong_guesses:
        guessed = normalize_name(guessed)
        if guessed == true_career or guessed not in kb["careers"]:
            continue
        pair = "||".join(sorted([true_career, guessed]))
        kb["confusions"][pair] = kb["confusions"].get(pair, 0) + 1
        if kb["confusions"][pair] >= 2 or profile_distance(kb, true_career, guessed) < CONFUSION_DISTANCE:
            needs_discriminator.append((true_career, guessed))
    return needs_discriminator


def question_spread(kb: dict, qid: str) -> float:
    """Variance of the yes-belief across occupations - global discriminating power."""
    ps = [p_yes(kb, c, qid) for c in kb["careers"]]
    m = sum(ps) / len(ps)
    return sum((p - m) ** 2 for p in ps) / len(ps)


def teaching_questions(kb: dict, career: str, limit: int = 10) -> list[str]:
    """Questions this occupation has (almost) no data for, most informative first."""
    career = normalize_name(career)
    profile = kb["careers"][career]["profile"]
    candidates = []
    for qid, q in kb["questions"].items():
        cell = profile.get(qid)
        total = (cell["yes"] + cell["no"]) if cell else 0.0
        if total >= 4.0:
            continue
        score = q.get("usefulness", 0.5) * (0.25 + question_spread(kb, qid))
        candidates.append((score, qid))
    candidates.sort(reverse=True)
    return [qid for _, qid in candidates[:limit]]


def teach_career(kb: dict, career: str, answers: dict[str, str]) -> None:
    """Directly imprint answers (answer strings) onto an occupation's profile."""
    profile = kb["careers"][normalize_name(career)]["profile"]
    for qid, answer in answers.items():
        w = ANSWER_WEIGHTS[answer]
        if w == 0.5 or qid not in kb["questions"]:
            continue
        _nudge_cell(kb, profile, qid, w, NEW_CAREER_WEIGHT)


def add_alias(kb: dict, career: str, alias: str) -> None:
    alias = normalize_name(alias)
    entry = kb["careers"][normalize_name(career)]
    if alias not in entry["aliases"] and alias != career:
        entry["aliases"].append(alias)


def add_question(kb: dict, text: str, source: str,
                 seed_answers: dict[str, float] | None = None,
                 default: float = 0.05) -> str:
    """Add a new question, optionally seeding beliefs for specific occupations.

    New questions default low: they are minted as niche discriminators, so a
    random unrelated occupation would almost certainly answer "no".
    """
    base = "gen_" + "".join(ch for ch in text.lower() if ch.isalnum())[:24]
    qid = base
    n = 1
    while qid in kb["questions"]:
        n += 1
        qid = f"{base}_{n}"
    kb["questions"][qid] = {"text": text.strip(), "source": source,
                            "default": default, "asked": 0, "usefulness": 0.6}
    for career, weight in (seed_answers or {}).items():
        career = normalize_name(career)
        if career in kb["careers"]:
            _nudge_cell(kb, kb["careers"][career]["profile"], qid, weight,
                        strength=SEED_STRENGTH * 0.6)
    return qid


def question_already_exists(kb: dict, text: str) -> bool:
    """Cheap near-duplicate check on question wording."""
    def norm(t: str) -> set:
        return {w for w in "".join(ch if ch.isalnum() or ch == " " else " "
                                   for ch in t.lower()).split() if len(w) > 2}
    new = norm(text)
    if not new:
        return True
    for q in kb["questions"].values():
        old = norm(q["text"])
        if old and len(new & old) / len(new | old) > 0.75:
            return True
    return False
