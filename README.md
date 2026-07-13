# SAGE — Self-Adaptive Guessing Engine

Guess any job title in the world, ~10 questions on average.

Think of any job — *propulsion engineer*, *actuary*, *air traffic controller*,
*embalmer*, *sommelier*, or *not employed at all* — and SAGE identifies
it with **simple yes/no questions** (say "not sure" only when genuinely torn).
The first identification comes within **15 questions worst case** — common
occupations in 6–8, ~10 on average for a random worker — with recovery guesses
at 22 and 30 for the hard tail. Wrong three times? It asks what the job was —
but it doesn't just believe you. See [Trust](#trust-verifying-before-learning)
below for why, and how it learns without ever corrupting itself.

## Run it

```
pip install -r requirements.txt   # numpy is the only hard dependency
python play.py               # play (creates knowledge.json on first run)
python play.py --stats       # knowledge-base statistics
python play.py --reset       # rebuild knowledge.json from taxonomy + O*NET data
python play.py --reconcile   # verify + learn everything currently quarantined
python simulate.py           # automated verification of the whole loop (offline)
python benchmark.py          # measure questions-to-guess across all occupations
python onet_import.py        # (optional) re-import the O*NET database
```

Optionally:

- `pip install google-genai pydantic` + a `GEMINI_API_KEY` env var (free tier)
  enables **verification** of claimed occupations after a loss — get a key at
  [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Without
  it, unverifiable claims are quarantined rather than learned (see below) —
  the game still plays fine, it just won't grow from losses until you run
  `--reconcile` with a key set.
- `pip install anthropic` + an `ANTHROPIC_API_KEY` is used as a secondary
  fallback for discriminator-question synthesis if Gemini is unavailable.

**Never commit an API key.** Set it as an environment variable
(`GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) — nothing in this repo reads keys from
a file, and none should ever be hardcoded into source.

## Coverage — how "56 million titles" really works

Raw title strings (the ~56M in title databases) are overwhelmingly synonyms:
"Sr. Backend Engineer II" is a software developer; "Hacker" is — per the
historical record — a forestry worker who hacks wood. The world's real
structure is a few thousand distinguishable *occupations* wearing millions of
title *aliases*. The engine works at both levels:

- **977 occupations** — a hand-tuned 17-sector hierarchy merged with the full
  **O*NET occupation database** (US Dept. of Labor, CC-BY; the successor to
  the 13,000-title DOT). Occupations that no yes/no question can tell apart
  are folded together until a discriminating question exists.
- **~31,700 title aliases** from O*NET's alternate-titles file, so "full stack
  developer", "scrum master", or "crime scene investigator" resolve to the
  right occupation (with player confirmation — title data is noisy).
- **Anything else is learned**: "astronaut" isn't even in O*NET; one lost
  game teaches it, and it's first-guessed forever after.

**The information budget is real**: 30 balanced yes/no questions distinguish
2^30 ≈ 1.07 *billion* outcomes. ~1,000 occupations need only log2(977) ≈ 10
bits; even all 13,000 DOT titles need just 13.7. The budget is therefore
mostly noise margin — the binding constraint is never the question count but
the knowledge matrix, which is exactly what grows every game.

## Huffman-weighted optimality (labor-statistics priors)

Uniform priors make every occupation cost ~log2(977) ≈ 10 bits. But
occupations aren't uniform: the engine seeds each one's prior with its real
**US national employment** (BLS OEWS May 2024, 831 detailed SOC codes,
154.2M workers, joined through each occupation's SOC codes). Greedy entropy
splitting over a weighted posterior balances probability *mass* instead of
candidate *count* — a Huffman-shaped tree where retail workers and nurses sit
near the root and wood patternmakers (180 employees nationwide) sit deep:

- Common occupations (top 50 by employment): **8.3 questions average, 90%
  first-guess accuracy**.
- Employment-weighted average to first guess: **9.9 questions** — below the
  uniform-prior bound of 10 bits, exactly as the theory predicts.
- Worst case to the first guess: **15 questions** (hard cap).
- Rare occupations pay the tail price on the first attempt but are clamped
  to at most ~log2(100) ≈ 6.6 bits of handicap, and after a wrong first
  guess the engine performs **prior annealing**: failing on the common-job
  region is itself evidence for the rare region, so recovery rounds
  (≤22, ≤30 questions) switch to the evidence-only posterior and rare jobs
  fight fair. Result: still **100% identified within three guesses, zero
  losses**.

The trade is explicit and measurable (`python benchmark.py`): forcing the
first identification attempt at ≤15 questions drops single-guess accuracy to
~57% overall (from 96% when guessing at ≤22) — but the guess-early/recover
protocol turns those misses into second-guess wins, and the *expected*
number of questions for a randomly chosen worker falls to ~10.

## What it looks like

```
Q 8. Would the word 'engineer' appear in your job title?     -> yes  [137 left]
Q12. Does your work involve aircraft or spacecraft?          -> yes  [10 left]
Q14. Do you work on engines, motors, or propulsion systems?  -> yes  [2 left]
First guess: I think you are a(n) *propulsion engineer*
```

977 candidates → 2 in fourteen yes/no answers, drilling sector → field → niche.

## Architecture

```
taxonomy.py     hand-tuned hierarchy: 17 sectors, 146 questions with world
                defaults, attribute inheritance
onet_import.py  O*NET database -> profiles (numeric work-context/knowledge/
                activity data + keyword rules), alias corpus, twin-merging,
                SOC codes for the employment join
onet_data.json  the imported O*NET layer (rebuildable offline)
employment.json BLS OEWS May 2024 national employment per SOC code (priors)
engine.py       numpy-vectorized Bayesian survivor tracking + live
                decision-tree computation, employment priors + annealing,
                verified learning (learn_verified), pending-claim quarantine
job_verification.py  Gemini-powered occupation verification: existence,
                definition, and a full grounded answer profile - independent
                of anything the player typed during the game
play.py         game loop: elimination display, sector narrowing, guessing,
                mid-game question synthesis, verify-before-learn flow,
                --reconcile for the quarantine queue
question_gen.py Claude-powered fallback for discriminator-question synthesis
simulate.py     automated self-tests (fully offline - verification is tested
                against a hand-built result, not a live API call)
benchmark.py    measurement harness: questions-to-guess distributions
knowledge.json  the living model - updated after every game
```

### The optimal decision tree, computed live

A fixed decision tree goes stale the moment knowledge changes, so the tree is
computed one node at a time during play: the next question is always the one
with **maximum expected entropy reduction over the current survivors** — the
greedy rule an optimal decision tree applies at each node. Three details make
it work in the real world:

- **Real answer model.** Expected gain is computed knowing that survivors
  whose belief sits mid-range will answer "not sure" (which carries zero
  evidence), so the selector prefers questions that produce *decisive*
  answers instead of questions that only look good under an idealized
  binary model.
- **Gaussian answer matching.** Answers score against beliefs with a kernel
  that peaks where answer matches belief, with a floor so one odd answer
  dampens a candidate but never eliminates it — humans misread questions.
- **Tiered questions by construction.** Broad splitters (uniform? computer?
  degree?) carry high gain early; niche discriminators (anesthesia? taxes?
  engines? wood?) only become informative — and only get asked — once the
  field has narrowed. Nothing is hand-ordered; each question's usefulness is
  tracked from the share of remaining uncertainty it actually removed, so
  weak questions fade and new ones earn their way in.

### The O*NET layer (`onet_import.py`)

Each of O*NET's occupations carries measured workplace data. The importer maps
it onto the question bank — *Exposed to High Places* → heights, *Medicine and
Dentistry* knowledge → healthcare, Job Zone → degree/training — then layers
keyword rules from titles and descriptions for attributes numbers can't
express ("orthodontist" → teeth, "welding" → metal). Occupation pairs with no
yes-vs-no disagreement on any question are folded together (absorbed as
aliases), because keeping them separate would burn guesses without
information; they unfold the moment a discriminating question is minted.

### Learning — the fallback for what the model misses

- Guess right → the occupation's cells shift toward the answers given
  (counts are capped, so beliefs drift with the world rather than fossilize).
- Wrong three times → the game asks what the job was, then **verifies it**
  before writing anything — see [Trust](#trust-verifying-before-learning).
- Repeatedly confused pairs — or a mid-game stall where no existing question
  splits the leaders — trigger **question synthesis**: the model derives a
  new discriminating question itself (Gemini, then Claude as fallback) from
  verified facts about both occupations. No player round-trip; a question the
  player invented is exactly the kind of unverified input the trust layer
  exists to avoid.

## Trust: verifying before learning

An earlier version of this loop was "lost → ask the player → believe them" —
three separate ways that breaks:

1. **Existence.** Nothing confirmed the claimed job was real. A typo, a
   joke, or a vague non-answer ("stuff") would still get written to the
   knowledge base as a genuine occupation.
2. **Answer honesty.** The player's answers *during the game* were trusted
   as ground truth for updating that occupation's profile — with no check
   that they'd actually answered the way a real person in that job would.
   One confused or dishonest playthrough could quietly corrupt an
   occupation's beliefs, including *existing* ones.
3. **Question design delegated to the least reliable source.** When two
   occupations were confused, the game asked the *player* to invent a
   discriminating question — the model outsourcing its own curation.

`job_verification.py` (Gemini, structured JSON output) closes all three with
one call per lost game: it decides whether the claim names a real occupation,
returns its canonical title and definition, and — independently of anything
the player answered — states how a *typical* person in that role would
answer every question SAGE tracks. `engine.learn_verified` then:

- **Rejects** claims Gemini can't confirm are real occupations. Nothing is
  written.
- **Quarantines** claims it can't verify at all (no API key, network/API
  error) into `kb["pending_review"]` — held aside, never merged, until
  `python play.py --reconcile` succeeds later. Unverifiable is not the same
  as false; it's just not yet trusted.
- **Learns from the grounded profile, never the player's raw answers.** The
  session's answers are used for exactly one thing: counting how many
  disagreed with the grounded profile, surfaced back to the player for
  transparency. A fabricated "yes" during the game cannot move a cell toward
  "yes" — proven in `simulate.py` TEST 6(c), where a nurse's `code` belief
  stayed near 0 even though the simulated session answered `code: yes`.
- **Canonicalizes before creating a duplicate**: the verified title is
  re-checked against the occupation hierarchy (catching synonyms the static
  alias corpus missed — Gemini correctly folded "librarian assistant" into
  the existing O*NET occupation "library assistants, clerical" in testing)
  before deciding an occupation is genuinely new.

`--reconcile` batches through the pending queue with a short delay between
calls, capped per run, to stay inside the free tier.

## Verified behavior (`python simulate.py`, `python benchmark.py`)

| Test | Result |
|---|---|
| Identify all 977 occupations from own answers | 100% within 3 guesses, 0 lost, ≤30 questions total |
| Questions to first guess | weighted mean 9.9, p90 15, max 15 |
| Common occupations (top 50 by employment) | 8.3 questions avg, 90% first guess |
| Drill-down: propulsion engineer | 977 → 2 candidates in 14 yes/no questions, first guess |
| Learn unknown occupation | added + placed in hierarchy; first-guess wins in all following games |
| Discriminator question for a manufactured twin pair | both separated, first guess |
| Typo / title-alias resolution | pass |
| Verification integrity (unverifiable → quarantined, not-real → rejected, fabricated session answers → not learned, verified-new → learned + sector-filed) | 4/4 pass, offline |

End-to-end CLI check (live Gemini calls): an adversarial player who answered
every question "no" was correctly guessed wrong three times, then claimed "air
traffic controller" — the game flagged that 12 of 30 answers didn't match a
real ATC's typical responses, learned from the verified profile instead, and
autonomously synthesized three discriminating questions with zero player
prompts. Separately, "astronaut" (absent from O*NET) verified and learned in
one session was first-guessed by a fresh process in the next.

*Honest caveat*: those numbers are against simulated players answering
consistently with the knowledge base. Real people answer noisily — that is
what the three-guess protocol, the likelihood floor, and the learning loop
absorb, and why the model genuinely improves with play: every game
recalibrates beliefs toward how real people describe their jobs.

## License & attribution

Code is MIT-licensed (see LICENSE).

Occupation data and alternate titles derived from the O*NET 29.1 Database
(U.S. Department of Labor, Employment and Training Administration), licensed
under CC BY 4.0. Employment priors from the BLS Occupational Employment and
Wage Statistics program (May 2024 national estimates, public domain). This
project is not endorsed by USDOL/ETA or BLS.
