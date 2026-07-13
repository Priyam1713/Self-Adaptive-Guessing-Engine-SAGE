"""Measurement harness for the 20-questions occupation guessing engine.

Plays one simulated game for every occupation in the seed knowledge base and
reports accuracy and question-cost distributions. This is pure measurement: no
learning/teaching functions are ever called, so the knowledge base is identical
for every game and results are reproducible.

Usage:
    python benchmark.py                # benchmark every occupation
    python benchmark.py --limit 60     # only the first 60 (quick smoke run)
    python benchmark.py --verbose      # print a line per game

The engine's public API (engine.py, simulate.py) is imported, never
reimplemented.
"""

from __future__ import annotations

import argparse
import random

import numpy as np

import engine
from simulate import live_profile, simulated_answer

SEED = 42
FULL_BUDGET = engine.ROUND_LIMITS[-1]   # questions counted for a lost game


# ---------------------------------------------------------------- one game

def play_one(kb: dict, name: str, rng: random.Random) -> dict:
    """Play a single game against the simulated player for `name`.

    Mirrors play.py / simulate.play_auto exactly, but calls no learning
    functions. Returns per-game measurements.
    """
    profile = live_profile(kb, name)
    game = engine.Game(kb, rng=rng)

    q1 = None            # questions asked when the FIRST guess was made
    won_round = 0        # 1/2/3, or 0 = lost
    total_at_win = None  # questions asked at the winning guess

    for round_no, limit in enumerate(engine.ROUND_LIMITS, start=1):
        while len(game.asked) < limit and not game.should_guess():
            qid, _ = game.next_question()
            if qid is None:
                break
            answer = simulated_answer(profile, kb, qid)
            game.record_answer(qid, answer)

        if q1 is None:
            q1 = len(game.asked)

        guess = game.make_guess()
        if guess == name:
            won_round = round_no
            total_at_win = len(game.asked)
            break
        game.reject_guess(guess)

    return {
        "name": name,
        "q1": q1,
        "won_round": won_round,
        # A lost game never won, so its winning cost is the full budget.
        "total_at_win": total_at_win if total_at_win is not None else FULL_BUDGET,
        "w": kb["careers"][name].get("prior", 1.0),
    }


# ---------------------------------------------------------------- statistics

def wmean(values, weights) -> float:
    values = np.asarray(values, dtype=float)
    weights = np.asarray(weights, dtype=float)
    total = weights.sum()
    if total <= 0:
        return float("nan")
    return float((values * weights).sum() / total)


def stat_block(values, weights) -> dict:
    a = np.asarray(values, dtype=float)
    if a.size == 0:
        return {"mean": float("nan"), "wmean": float("nan"),
                "p50": float("nan"), "p90": float("nan"), "max": float("nan")}
    return {
        "mean": float(a.mean()),
        "wmean": wmean(values, weights),
        "p50": float(np.percentile(a, 50)),
        "p90": float(np.percentile(a, 90)),
        "max": float(a.max()),
    }


def fmt_block(label: str, s: dict) -> str:
    return (f"  {label:<26} mean {s['mean']:6.2f}   wmean {s['wmean']:6.2f}   "
            f"p50 {s['p50']:5.1f}   p90 {s['p90']:5.1f}   max {s['max']:5.0f}")


# ---------------------------------------------------------------- reporting

def histogram(values, bins: int = 10, width: int = 40) -> list[str]:
    a = np.asarray(values, dtype=float)
    lines = []
    if a.size == 0:
        return ["  (no data)"]
    lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        hi = lo + 1.0
    edges = np.linspace(lo, hi, bins + 1)
    counts, _ = np.histogram(a, bins=edges)
    peak = int(counts.max()) or 1
    for i in range(bins):
        left, right = edges[i], edges[i + 1]
        bar = "#" * int(round(counts[i] / peak * width))
        lines.append(f"  [{left:5.1f}, {right:5.1f})  {int(counts[i]):4d}  {bar}")
    return lines


def report(rows: list[dict], priors_present: bool) -> None:
    n = len(rows)
    q1 = [r["q1"] for r in rows]
    w = [r["w"] for r in rows]
    win_total = [r["total_at_win"] for r in rows]

    first_hits = sum(1 for r in rows if r["won_round"] == 1)
    within3 = sum(1 for r in rows if r["won_round"] != 0)
    losses = [r["name"] for r in rows if r["won_round"] == 0]

    print("=" * 78)
    print("OCCUPATION GUESSER BENCHMARK")
    print("=" * 78)
    if not priors_present:
        print("(priors not yet loaded - weighted stats equal unweighted)")
    print()

    print("OVERALL")
    print(f"  games                 {n}")
    print(f"  first-guess accuracy  {100.0 * first_hits / n:5.1f}%   ({first_hits}/{n})")
    print(f"  within-3 accuracy     {100.0 * within3 / n:5.1f}%   ({within3}/{n})")
    print(f"  losses                {len(losses)}")
    if losses:
        shown = losses[:40]
        for name in shown:
            print(f"      LOST: {name}")
        if len(losses) > 40:
            print(f"      ... and {len(losses) - 40} more")
    print()

    print("QUESTIONS TO FIRST GUESS")
    print(fmt_block("first guess", stat_block(q1, w)))
    print()

    print("QUESTIONS TO CORRECT GUESS  (lost games counted as full budget "
          f"= {FULL_BUDGET})")
    print(fmt_block("correct guess", stat_block(win_total, w)))
    print()

    # --- common vs rare -----------------------------------------------------
    ordered = sorted(rows, key=lambda r: r["w"], reverse=True)
    k = min(50, n)
    top = ordered[:k]
    bottom = ordered[-k:]

    def grp(group):
        gq1 = [r["q1"] for r in group]
        acc = 100.0 * sum(1 for r in group if r["won_round"] == 1) / len(group)
        return float(np.mean(gq1)), acc

    top_mean, top_acc = grp(top)
    bot_mean, bot_acc = grp(bottom)
    print(f"COMMON vs RARE  (by weight; top {k} and bottom {k})")
    print(f"  {'group':<14} {'mean q->1st':>12} {'first-guess acc':>18}")
    print(f"  {'top ' + str(k):<14} {top_mean:>12.2f} {top_acc:>17.1f}%")
    print(f"  {'bottom ' + str(k):<14} {bot_mean:>12.2f} {bot_acc:>17.1f}%")
    print()

    print("HISTOGRAM  questions to first guess")
    for line in histogram(q1):
        print(line)
    print("=" * 78)


# ---------------------------------------------------------------- main

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None,
                        help="benchmark only the first N occupations")
    parser.add_argument("--verbose", action="store_true",
                        help="print a line per game")
    args = parser.parse_args()

    kb = engine.build_seed_kb()
    names = list(kb["careers"])
    if args.limit is not None:
        names = names[:args.limit]

    priors_present = any("prior" in v for v in kb["careers"].values())

    rows = []
    for name in names:
        rng = random.Random(SEED)
        row = play_one(kb, name, rng)
        rows.append(row)
        if args.verbose:
            outcome = f"round {row['won_round']}" if row["won_round"] else "LOST"
            print(f"  {name:<50} q1={row['q1']:>2}  {outcome:<8}"
                  f"  win@{row['total_at_win']}")

    if args.verbose:
        print()
    report(rows, priors_present)


if __name__ == "__main__":
    main()
