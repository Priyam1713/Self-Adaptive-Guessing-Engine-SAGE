"""Automated self-test of the ever-learning loop. Run: python simulate.py

Simulates players whose answers come from a hidden occupation profile:
  1. Accuracy: every occupation in the taxonomy is identified from its own
     answers within the 20(+5) question budget.
  2. Drill-down showcase: transcript of the engine finding a niche role
     (propulsion engineer) from the top of the hierarchy.
  3. Learning new occupations: an unknown job is taught once, then guessed.
  4. Mistake-driven questions: a confusable pair gets a discriminator.
  5. Name resolution: typos and aliases.

No API key needed - question generation is stubbed where exercised.
"""

from __future__ import annotations

import random
import sys

import engine
from engine import ANSWER_WEIGHTS


def simulated_answer(profile: dict[str, float], kb: dict, qid: str) -> str:
    """A player forced to answer yes/no, saying 'not sure' only when torn."""
    p = profile.get(qid, kb["questions"][qid]["default"])
    if p >= 0.6:
        return "yes"
    if p <= 0.4:
        return "no"
    return "unknown"


def play_auto(kb: dict, true_name: str, profile: dict[str, float],
              rng: random.Random, transcript: list | None = None) -> tuple[int, list[str]]:
    """Play one full game against a simulated player, mirroring play.py.

    Returns (won_round, wrong_guesses) and applies learning.
    won_round: 1/2/3 = which guess was right, 0 = lost.
    """
    game = engine.Game(kb, rng=rng)
    wrong = []

    def round_(limit):
        while len(game.asked) < limit and not game.should_guess():
            qid, _ = game.next_question()
            if qid is None:
                break
            a = simulated_answer(profile, kb, qid)
            game.record_answer(qid, a)
            if transcript is not None:
                transcript.append((kb["questions"][qid]["text"], a, game.viable_count()))

    for round_no, limit in enumerate(engine.ROUND_LIMITS, start=1):
        round_(limit)
        guess = game.make_guess()
        if guess == true_name:
            engine.learn_from_game(kb, true_name, game.asked, wrong, won_round=round_no)
            return round_no, wrong
        wrong.append(guess)
        game.reject_guess(guess)

    engine.learn_from_game(kb, true_name, game.asked, wrong, won_round=0)
    return 0, wrong


def live_profile(kb: dict, name: str) -> dict[str, float]:
    return {qid: engine.p_yes(kb, name, qid) for qid in kb["questions"]}


def test_accuracy(strict: bool = True) -> None:
    print("TEST 1: identify every occupation in the taxonomy from its own answers")
    kb = engine.build_seed_kb()
    assert all(engine.normalize_name(n) == n for n in kb["careers"]), \
        "career keys must be normalized"
    rng = random.Random(7)
    wins = {1: 0, 2: 0, 3: 0}
    lost = 0
    failures = []
    for name in list(kb["careers"]):
        won, wrong = play_auto(kb, name, live_profile(kb, name), rng)
        if won:
            wins[won] += 1
        else:
            lost += 1
            failures.append((name, wrong))
    total = sum(wins.values()) + lost
    print(f"  guess 1: {wins[1]}/{total} ({wins[1]/total:.0%}), "
          f"guess 2: {wins[2]}, guess 3: {wins[3]}, lost: {lost}")
    for name, wrong in failures[:40]:
        print(f"  LOST: {name:<50} (guessed {wrong})")
    if len(failures) > 40:
        print(f"  ... and {len(failures) - 40} more")
    if strict:
        assert lost == 0, f"{lost} occupations could not be identified"
        print("  PASS\n")
    else:
        print()


def test_drilldown_showcase() -> None:
    print("TEST 2: drill-down showcase - propulsion engineer")
    kb = engine.build_seed_kb()
    transcript = []
    won, wrong = play_auto(kb, "propulsion engineer",
                           live_profile(kb, "propulsion engineer"),
                           random.Random(1), transcript=transcript)
    for i, (text, ans, remaining) in enumerate(transcript, 1):
        print(f"  Q{i:>2}. {text:<72} -> {ans:<12} [{remaining} left]")
    print(f"  result: guessed in round {won} (wrong guesses: {wrong})")
    assert won in (1, 2)
    print("  PASS\n")


def test_learn_new_career() -> None:
    print("TEST 3: learn a brand-new occupation from one lost game")
    kb = engine.build_seed_kb()
    rng = random.Random(11)
    lighthouse_keeper = {  # not in the taxonomy
        "indoors": .6, "ships": .8, "earth_env": .7, "protect": .8, "shifts": .95,
        "nine2five": .05, "government": .6, "self_emp": .1, "public": .1,
        "screen": .3, "degree": .05, "high_pay": .2, "fix_repair": .7,
        "tools": .6, "hands": .6, "physical": .5, "machines_op": .3,
        "travel": .1, "uniform": .3, "emergency": .5, "danger": .3,
        "people_core": .05, "data_info": .1, "make_physical": .1,
        "buildings": .4, "electric_wire": .4, "sales": .01, "teach": .02,
    }
    won, _ = play_auto(kb, "lighthouse keeper", lighthouse_keeper, rng)
    assert won == 0 and "lighthouse keeper" in kb["careers"], "occupation was not added"
    sector, field = kb["careers"]["lighthouse keeper"]["path"]
    print(f"  game 1: lost as expected; added under {sector} > {field}")

    qids = engine.teaching_questions(kb, "lighthouse keeper", limit=10)
    engine.teach_career(kb, "lighthouse keeper",
                        {qid: simulated_answer(lighthouse_keeper, kb, qid) for qid in qids})
    print(f"  teach mode: filled {len(qids)} profile gaps")

    results = [play_auto(kb, "lighthouse keeper", lighthouse_keeper, rng)[0] for _ in range(3)]
    print(f"  games 2-4 results (1=first-guess win): {results}")
    assert all(r in (1, 2) for r in results), "engine did not learn the new occupation"
    print("  PASS\n")


def test_discriminator_question() -> None:
    print("TEST 4: a generated question separates two confusable occupations")
    kb = engine.build_seed_kb()
    rng = random.Random(3)

    clone = dict(live_profile(kb, "propulsion engineer"))
    kb["careers"]["rocket test technician"] = {
        "plays": 0, "aliases": [], "path": ["engineering", "aerospace engineering"],
        "profile": {qid: {"yes": p * 10, "no": (1 - p) * 10} for qid, p in clone.items()},
    }
    dist = engine.profile_distance(kb, "propulsion engineer", "rocket test technician")
    print(f"  profile distance before: {dist:.3f} "
          f"(needs discriminator: {dist < engine.CONFUSION_DISTANCE})")
    assert dist < engine.CONFUSION_DISTANCE

    qid = engine.add_question(
        kb, "Did your role require an engineering degree (rather than technician training)?",
        "user",
        {"propulsion engineer": ANSWER_WEIGHTS["yes"],
         "rocket test technician": ANSWER_WEIGHTS["no"]},
    )
    print(f'  added question "{kb["questions"][qid]["text"]}"')

    eng_profile = dict(clone); eng_profile[qid] = 0.95
    tech_profile = dict(clone); tech_profile[qid] = 0.05

    won_eng, _ = play_auto(kb, "propulsion engineer", eng_profile, rng)
    won_tech, _ = play_auto(kb, "rocket test technician", tech_profile, rng)
    print(f"  propulsion engineer: round {won_eng}, rocket test technician: round {won_tech}")
    assert won_eng >= 1 and won_tech >= 1 and 0 not in (won_eng, won_tech)
    print("  PASS\n")


def test_alias_and_fuzzy() -> None:
    print("TEST 5: name resolution (typos and aliases)")
    kb = engine.build_seed_kb()
    resolved, suggestion = engine.resolve_career(kb, "Propulsion Enginer")
    assert resolved is None and suggestion == "propulsion engineer", (resolved, suggestion)
    engine.add_alias(kb, "propulsion engineer", "rocket engineer")
    resolved, _ = engine.resolve_career(kb, "Rocket Engineer")
    assert resolved == "propulsion engineer"
    print("  typo suggestion + alias resolution work")
    print("  PASS\n")


if __name__ == "__main__":
    strict = "--report" not in sys.argv
    test_accuracy(strict=strict)
    if strict:
        test_drilldown_showcase()
        test_learn_new_career()
        test_discriminator_question()
        test_alias_and_fuzzy()
        print("All simulation tests passed.")
