"""Interactive career-guessing game. Run: python play.py

Think of any occupation - the game asks simple yes/no questions (say "not
sure" when genuinely torn) and identifies it within 30 questions, guessing
after at most 22, 26, and 30. Every question is chosen live to eliminate
the maximum number of remaining candidates, drilling from sector level down
to niche roles. If no existing question can split the leaders, the game
synthesizes a brand-new discriminating question on the spot.

Wrong three times -> the game asks what the occupation was, but it does not
take that claim on faith. It verifies the claim (does this occupation even
exist, and how would a typical person in it answer every question the model
tracks?) before writing anything to the knowledge base, and it never trusts
the player's own in-game answers as ground truth for that write - only the
independently-verified profile. See job_verification.py and
engine.learn_verified for why. Question design is likewise never delegated
back to the player: confused occupation pairs are auto-split by a
synthesized question, not by asking "can you suggest one?".

Verification requires `pip install google-genai` and a GEMINI_API_KEY
environment variable (free tier works). Without it, an unverifiable claim is
quarantined - held aside, never merged into the knowledge base - until you
run with --reconcile once a key is available.

Flags:
  --reset       rebuild knowledge.json from the taxonomy + O*NET data
  --stats       print knowledge-base statistics and exit
  --reconcile   attempt to verify and learn everything in the pending queue
"""

from __future__ import annotations

import sys
import time

import engine
import job_verification
import question_gen
from engine import ANSWER_WEIGHTS

ANSWER_KEYS = {
    "y": "yes", "yes": "yes",
    "n": "no", "no": "no",
    "s": "unknown", "ns": "unknown", "not sure": "unknown",
    "i": "unknown", "idk": "unknown", "u": "unknown", "unknown": "unknown",
    "dont know": "unknown", "don't know": "unknown",
}

GUESS_LABELS = ("First guess", "Second guess", "Final guess")


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def ask_answer(number: int, text: str) -> str:
    print(f"\nQ{number}. {text}")
    while True:
        raw = ask("    [y]es / [n]o / [s] not sure > ").lower()
        if raw in ANSWER_KEYS:
            return ANSWER_KEYS[raw]
        print("    Please answer y, n, or s.")


def ask_yes_no(prompt: str) -> bool:
    while True:
        raw = ask(prompt + " [y/n] > ").lower()
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False


def synthesize_live(kb: dict, game: engine.Game) -> str | None:
    """No existing question splits the leaders: mint one mid-game."""
    pair = game.stuck_pair()
    if pair is None:
        return None
    a, b = pair
    existing = [q["text"] for q in kb["questions"].values()]
    gen = question_gen.generate_discriminator(a, b, existing)
    if not gen or engine.question_already_exists(kb, gen["question"]):
        return None
    qid = engine.add_question(kb, gen["question"], "llm-live", {
        a: ANSWER_WEIGHTS[gen["answer_for_career_a"]],
        b: ANSWER_WEIGHTS[gen["answer_for_career_b"]],
    })
    print("    (I just thought of a new question for this exact situation...)")
    return qid


def run_question_round(kb: dict, game: engine.Game, limit: int,
                       announced: set) -> None:
    """Ask questions until the guess trigger fires or the budget runs out."""
    while len(game.asked) < limit and not game.should_guess():
        qid = None
        if len(game.asked) >= 10:
            qid = synthesize_live(kb, game)
        if qid is None:
            qid, _ = game.next_question()
        if qid is None:
            break
        answer = ask_answer(len(game.asked) + 1, kb["questions"][qid]["text"])
        game.record_answer(qid, answer)
        remaining = game.viable_count()
        print(f"    [{remaining} candidate{'s' if remaining != 1 else ''} remaining]")
        sector, mass = game.sector_mass()[0]
        if mass >= 0.85 and sector not in announced and remaining > 1:
            announced.add(sector)
            print(f"    (Narrowing in: your work looks like *{sector}*.)")


def confirm_guess(game: engine.Game, label: str) -> tuple[bool, str]:
    guess = game.make_guess()
    conf = game.top(1)[0][1]
    print(f"\n{label}: I think you are a(n) *{guess}*  (confidence {conf:.0%})")
    if ask_yes_no("Am I right?"):
        return True, guess
    game.reject_guess(guess)
    return False, guess


def learn_true_career(kb: dict, game: engine.Game, wrong_guesses: list[str]) -> None:
    """Get the claimed occupation from the player and verify it before
    touching the knowledge base - never learn from the raw claim or from
    the player's own in-game answers directly (see engine.learn_verified)."""
    name = ask("\nI give up! What is your occupation? > ")
    if not name:
        return

    print("    Let me check that before I learn anything from it...")
    verification = job_verification.verify_occupation(name, kb["questions"])
    report = engine.learn_verified(kb, name, verification, game.asked, wrong_guesses)
    render_verified_report(kb, name, report)
    handle_discriminators(kb, report["confusions"])


def render_verified_report(kb: dict, claimed_name: str, report: dict) -> None:
    if report["status"] == "quarantined":
        print("  I couldn't verify this occupation right now (no GEMINI_API_KEY "
              "set, or the lookup failed), so I'm holding it aside without "
              "touching my knowledge base. Run `python play.py --reconcile` "
              "once verification is available to let me learn it properly.")
        return

    if report["status"] == "rejected":
        print(f'  I couldn\'t confirm "{engine.normalize_name(claimed_name)}" is a '
              "real, distinct occupation, so I'm not adding it - that would just "
              "teach myself bad information.")
        return

    if report["disagreements"]:
        print(f"  (Note: {report['disagreements']} of your answers this game didn't "
              "match how a typical person in this role usually responds. I'm "
              "learning from the verified profile instead of your raw answers, "
              "so this won't corrupt my knowledge base.)")

    if report["is_new"]:
        sector, field = kb["careers"][report["career"]]["path"]
        print(f'  New occupation verified and learned: "{report["career"]}" '
              f"- filed under {sector} > {field}. I will recognize it next time!")
        if report["definition"]:
            print(f'  {report["definition"]}')
    else:
        print(f'  Verified and reinforced my existing knowledge of '
              f'"{report["career"]}".')


def handle_discriminators(kb: dict, pairs: list[tuple[str, str]]) -> None:
    """For each confused pair, synthesize a discriminating question ourselves
    from verified facts (Gemini, then Claude as fallback) - no player
    round-trip. A question the player invented is exactly the kind of
    unverified input this whole module exists to avoid."""
    for true_career, guessed in pairs:
        print(f'\n  Learning to tell "{true_career}" and "{guessed}" apart...')
        existing = [q["text"] for q in kb["questions"].values()]
        gen = job_verification.synthesize_discriminator(true_career, guessed, existing)
        if gen is None:
            gen = question_gen.generate_discriminator(true_career, guessed, existing)
        if gen and not engine.question_already_exists(kb, gen["question"]):
            engine.add_question(kb, gen["question"], "auto", {
                true_career: ANSWER_WEIGHTS[gen["answer_for_career_a"]],
                guessed: ANSWER_WEIGHTS[gen["answer_for_career_b"]],
            })
            print(f'  Learned: "{gen["question"]}"')
        else:
            print("  (Couldn't synthesize a good discriminator this time - "
                  "I'll try again after more games.)")


def play_one_game(kb: dict) -> None:
    game = engine.Game(kb)
    wrong_guesses: list[str] = []
    announced: set = set()
    print(f"\nThink of an occupation - any of the {len(kb['careers'])} I know "
          "(by any job title), or one I have never heard of. "
          "I will guess it within 30 questions!")

    for round_no, limit in enumerate(engine.ROUND_LIMITS):
        if round_no == 1:
            print("\nHmm, let me ask a few more questions...")
        elif round_no == 2:
            print("\nAlright, last few questions...")
        run_question_round(kb, game, limit, announced)
        correct, guess = confirm_guess(game, GUESS_LABELS[round_no])
        if correct:
            pairs = engine.learn_from_game(kb, guess, game.asked, wrong_guesses,
                                           won_round=round_no + 1)
            print("Great! I have reinforced what I know about that occupation.")
            handle_discriminators(kb, pairs)
            return
        wrong_guesses.append(guess)

    learn_true_career(kb, game, wrong_guesses)


def print_stats(kb: dict) -> None:
    s = kb["stats"]
    total = max(1, s["games"])
    sectors = {c["path"][0] for c in kb["careers"].values()}
    aliases = sum(len(c["aliases"]) for c in kb["careers"].values())
    pending = len(kb.get("pending_review", []))
    print(f"Games played:        {s['games']}")
    print(f"Won on guess 1/2/3:  {s['wins_first']} / {s['wins_second']} / "
          f"{s.get('wins_third', 0)}"
          f"  ({(s['wins_first'] + s['wins_second'] + s.get('wins_third', 0)) / total:.0%} overall)")
    print(f"Lost (then learned): {s['losses']} ({s['losses'] / total:.0%})")
    print(f"Verified learns:     {s.get('verified_learns', 0)}")
    print(f"Rejected (not real): {s.get('rejected_unreal', 0)}")
    print(f"Pending verification:{pending:>4} (run --reconcile once GEMINI_API_KEY is set)")
    print(f"Occupations known:   {len(kb['careers'])} across {len(sectors)} sectors")
    print(f"Job titles known:    {aliases + len(kb['careers'])} (incl. aliases)")
    learned_q = sum(1 for q in kb["questions"].values() if q["source"] != "seed")
    print(f"Questions known:     {len(kb['questions'])} ({learned_q} learned)")


def cmd_reconcile(kb: dict, limit: int = 15) -> None:
    """Retry verification for everything quarantined by learn_true_career,
    capped per run to stay polite to the free-tier rate limit."""
    pending = kb.get("pending_review", [])
    if not pending:
        print("Nothing pending - every claim has already been resolved.")
        return
    batch = pending[:limit]
    print(f"Reconciling {len(batch)} of {len(pending)} pending claim(s)...")
    remaining = pending[limit:]
    resolved = 0
    for i, item in enumerate(batch):
        title = item["claimed_title"]
        print(f'\n  [{i + 1}/{len(batch)}] Verifying "{title}"...')
        verification = job_verification.verify_occupation(title, kb["questions"])
        asked = [tuple(pair) for pair in item["asked"]]
        report = engine.learn_verified(kb, title, verification, asked,
                                       item["wrong_guesses"])
        render_verified_report(kb, title, report)
        if report["status"] == "quarantined":
            remaining.append(item)
        else:
            resolved += 1
            if report["status"] == "learned":
                handle_discriminators(kb, report["confusions"])
        if i < len(batch) - 1:
            time.sleep(1.5)  # be gentle with the free tier
    kb["pending_review"] = remaining
    engine.save_kb(kb)
    print(f"\nDone. {resolved} resolved, {len(remaining)} still pending.")


def main() -> None:
    if "--reset" in sys.argv:
        engine.save_kb(engine.build_seed_kb())
        print("Knowledge base reset to the seed taxonomy + O*NET data.")
        return
    kb = engine.load_kb()
    if "--stats" in sys.argv:
        print_stats(kb)
        return
    if "--reconcile" in sys.argv:
        cmd_reconcile(kb)
        return

    print("=" * 64)
    print("  SAGE - Self-Adaptive Guessing Engine")
    print("=" * 64)
    sectors = {c["path"][0] for c in kb["careers"].values()}
    aliases = sum(len(c["aliases"]) for c in kb["careers"].values())
    print(f"I know {len(kb['careers'])} occupations across {len(sectors)} sectors, "
          f"answering to {aliases + len(kb['careers'])} job titles, "
          f"with {len(kb['questions'])} questions.")

    while True:
        play_one_game(kb)
        engine.save_kb(kb)
        print("\n(Knowledge saved.)")
        if not ask_yes_no("\nPlay again?"):
            print_stats(kb)
            print("Thanks for teaching me!")
            break


if __name__ == "__main__":
    main()
