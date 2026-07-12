"""Interactive career-guessing game. Run: python play.py

Think of any occupation - the game asks simple yes/no questions (say "not
sure" when genuinely torn) and identifies it within 30 questions, guessing
after at most 22, 26, and 30. Every question is chosen live to eliminate
the maximum number of remaining candidates, drilling from sector level down
to niche roles. If no existing question can split the leaders, the game
synthesizes a brand-new discriminating question on the spot (Claude API,
if available). Wrong three times -> it asks, learns, and never loses that
occupation the same way again. The knowledge base is saved after every game.

Flags:
  --reset     rebuild knowledge.json from the taxonomy + O*NET data
  --stats     print knowledge-base statistics and exit
"""

from __future__ import annotations

import sys

import engine
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
    """Get the real occupation from the player (resolving titles) and learn."""
    name = ask("\nI give up! What is your occupation? > ")
    if not name:
        return
    resolved, suggestion = engine.resolve_career(kb, name)
    # Title data is noisy: confirm any match that isn't the occupation's own
    # name before trusting it ("hacker" is a historical title for... forestry).
    if resolved is not None and resolved != engine.normalize_name(name):
        if not ask_yes_no(f'So your occupation is a kind of "{resolved}"?'):
            resolved = None
    if resolved is None and suggestion is not None:
        if ask_yes_no(f'Is "{engine.normalize_name(name)}" a kind of "{suggestion}"?'):
            engine.add_alias(kb, suggestion, name)
            resolved = suggestion
    true_career = resolved or engine.normalize_name(name)
    is_new = resolved is None

    pairs = engine.learn_from_game(kb, true_career, game.asked, wrong_guesses, won_round=0)
    if is_new:
        sector, field = kb["careers"][true_career]["path"]
        print(f'New occupation "{true_career}" - filing it under '
              f"{sector} > {field}. I will recognize it next time!")
        offer_teach_mode(kb, true_career)
    handle_discriminators(kb, pairs)


def offer_teach_mode(kb: dict, career: str) -> None:
    """Fill profile gaps so a new occupation competes fairly in future games."""
    qids = engine.teaching_questions(kb, career, limit=10)
    if len(qids) < 3:
        return
    print(f'\nMy picture of "{career}" still has gaps.')
    if not ask_yes_no(f"Answer {len(qids)} quick extra questions so I learn it properly?"):
        return
    answers = {}
    for i, qid in enumerate(qids, 1):
        answers[qid] = ask_answer(i, kb["questions"][qid]["text"])
    engine.teach_career(kb, career, answers)
    print("Thanks - profile completed.")


def handle_discriminators(kb: dict, pairs: list[tuple[str, str]]) -> None:
    """For each confused pair, mint a new question (LLM first, then player)."""
    for true_career, guessed in pairs:
        print(f'\nI keep mixing up "{true_career}" and "{guessed}" - '
              "let me learn a question that tells them apart.")
        existing = [q["text"] for q in kb["questions"].values()]
        gen = question_gen.generate_discriminator(true_career, guessed, existing)

        if gen and not engine.question_already_exists(kb, gen["question"]):
            print(f'  Generated: "{gen["question"]}"')
            print(f'  ({true_career}: {gen["answer_for_career_a"]}, '
                  f'{guessed}: {gen["answer_for_career_b"]})')
            if ask_yes_no("  Does that look like a fair question?"):
                engine.add_question(kb, gen["question"], "llm", {
                    true_career: ANSWER_WEIGHTS[gen["answer_for_career_a"]],
                    guessed: ANSWER_WEIGHTS[gen["answer_for_career_b"]],
                })
                print("  Learned. I will use it in future games.")
                continue

        print("  Can you suggest a yes/no question that separates them?")
        text = ask("  Question (or press Enter to skip) > ")
        if not text:
            continue
        if engine.question_already_exists(kb, text):
            print("  I already have a very similar question - skipping.")
            continue
        ans = "yes" if ask_yes_no(f'  For a "{true_career}", is the answer yes?') else "no"
        seed = {true_career: ANSWER_WEIGHTS[ans],
                guessed: ANSWER_WEIGHTS["no" if ans == "yes" else "yes"]}
        engine.add_question(kb, text, "user", seed)
        print("  Learned. I will use it in future games.")


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
    print(f"Games played:        {s['games']}")
    print(f"Won on guess 1/2/3:  {s['wins_first']} / {s['wins_second']} / "
          f"{s.get('wins_third', 0)}"
          f"  ({(s['wins_first'] + s['wins_second'] + s.get('wins_third', 0)) / total:.0%} overall)")
    print(f"Lost (then learned): {s['losses']} ({s['losses'] / total:.0%})")
    print(f"Occupations known:   {len(kb['careers'])} across {len(sectors)} sectors")
    print(f"Job titles known:    {aliases + len(kb['careers'])} (incl. aliases)")
    learned_q = sum(1 for q in kb["questions"].values() if q["source"] != "seed")
    print(f"Questions known:     {len(kb['questions'])} ({learned_q} learned)")


def main() -> None:
    if "--reset" in sys.argv:
        engine.save_kb(engine.build_seed_kb())
        print("Knowledge base reset to the seed taxonomy + O*NET data.")
        return
    kb = engine.load_kb()
    if "--stats" in sys.argv:
        print_stats(kb)
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
