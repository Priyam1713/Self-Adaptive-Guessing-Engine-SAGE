"""Ground a player's claimed occupation before it touches the knowledge base.

The naive "lost -> ask the player -> believe them" loop has three trust gaps:

  1. Existence: is what they typed even a real, distinct occupation, or a
     joke / typo / description too vague to mean anything?
  2. Answer honesty: did they actually answer our questions the way a real
     person in that role does, or did they misread/misclick/troll? Their
     raw session answers are never independently checked against anything.
  3. Question design: asking the player to *invent* a discriminating
     question puts curation of the model on the least reliable source in
     the loop.

This module closes gap 1 and 2 with one Gemini call per lost game
(`verify_occupation`): it decides whether the claim names a real occupation,
gives its canonical title and definition, and - independently of anything
the player answered - states how a typical person in that role would answer
every question the model tracks. `engine.learn_verified` then updates the
knowledge base from *that* grounded profile, never from the player's raw
answers (see its docstring). Gap 3 is closed by `synthesize_discriminator`,
which derives a new discriminating question from verified facts about both
occupations with no player round-trip.

Requires `pip install google-genai` and a `GEMINI_API_KEY` environment
variable (free tier). If the package is missing, the key is unset, or a
call fails for any reason (including rate limits), both functions return
None - callers must treat that as "unverified", not "verified false". See
engine.learn_verified / play.py for how the None case is handled (the claim
is quarantined, never merged into the knowledge base).
"""

from __future__ import annotations

import os
import time

MODEL = "gemini-2.5-flash"

try:
    from google import genai
    from google.genai import types
    from pydantic import BaseModel
    from typing import Literal

    class _GroundedAnswer(BaseModel):
        id: str
        answer: Literal["yes", "no", "unknown"]

    class _Verification(BaseModel):
        is_real_occupation: bool
        canonical_title: str
        definition: str
        sector_hint: str
        answers: list[_GroundedAnswer]

    class _Discriminator(BaseModel):
        question: str
        answer_for_a: Literal["yes", "no"]
        answer_for_b: Literal["yes", "no"]

    _SDK_READY = True
except ImportError:
    _SDK_READY = False


def _client():
    if not _SDK_READY:
        return None
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def _call(client, prompt: str, schema, temperature: float):
    """One structured-output call with a single short retry on transient
    errors - kept to a max of 2 attempts total to respect free-tier limits."""
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        temperature=temperature,
        max_output_tokens=8192,
    )
    last_err = None
    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=MODEL, contents=prompt, config=config,
            )
            return response.parsed or schema.model_validate_json(response.text)
        except Exception as e:
            last_err = e
            if attempt == 0:
                time.sleep(2.0)
    return None


def verify_occupation(claimed_title: str, questions: dict[str, dict]) -> dict | None:
    """Ground a claimed occupation: does it exist, what does it mean, and
    how would a typical person in that role answer every tracked question?

    `questions` is kb["questions"] (qid -> {"text": ..., ...}).
    Returns None if verification is unavailable or failed - the caller must
    NOT treat that as "not a real occupation"; see engine.learn_verified.
    On success: {"is_real_occupation": bool, "canonical_title": str,
    "definition": str, "sector_hint": str, "answers": {qid: "yes"/"no"/"unknown"}}.
    """
    client = _client()
    if client is None:
        return None

    q_block = "\n".join(f"{qid}: {q['text']}" for qid, q in questions.items())
    prompt = (
        "You are verifying a claim in an occupation-guessing game. A player "
        f'claims their job is: "{claimed_title}"\n\n'
        "Step 1: Decide if this is a real, recognized occupation or "
        "employment status (this includes non-employment states like "
        "student, retired, unemployed, or homemaker). Reject joke answers, "
        "gibberish, or descriptions too vague to be a distinct role (e.g. "
        '"worker", "guy who does stuff").\n\n'
        "Step 2: If real, give its standard canonical job title, a "
        "one-sentence definition, and a short sector hint using one of "
        "these category styles: \"healthcare & medicine\", \"engineering\", "
        "\"software & information technology\", \"science & research\", "
        "\"education\", \"law, government & public safety\", \"business, "
        "finance & management\", \"sales, marketing & customer service\", "
        "\"arts, media & entertainment\", \"sports & fitness\", "
        "\"hospitality, food & tourism\", \"transport & logistics\", "
        "\"construction & skilled trades\", \"manufacturing & production\", "
        "\"agriculture, nature & animals\", \"personal & community "
        "services\", or \"not currently employed\".\n\n"
        "Step 3: If real, answer EVERY question below exactly as a "
        "TYPICAL, experienced person in that occupation would answer about "
        'their own daily work - "yes", "no", or "unknown" only if the '
        "question genuinely does not apply or varies too much to "
        "generalize. Answer in the occupation's ordinary, general-"
        "population sense, not an unusual specialization, unless the "
        "claimed title names that specialization explicitly. Answer every "
        "single id listed, in order.\n\n"
        f"Questions (id: text):\n{q_block}\n\n"
        "If the occupation is not real, still return an empty answers list."
    )

    data = _call(client, prompt, _Verification, temperature=0.1)
    if data is None:
        return None
    return {
        "is_real_occupation": data.is_real_occupation,
        "canonical_title": data.canonical_title.strip(),
        "definition": data.definition.strip(),
        "sector_hint": data.sector_hint.strip(),
        "answers": {a.id: a.answer for a in data.answers},
    }


def synthesize_discriminator(occupation_a: str, occupation_b: str,
                             existing_questions: list[str]) -> dict | None:
    """Auto-derive a yes/no question that separates two confused occupations
    from the model's own world knowledge - no player round-trip.

    Returns {"question", "answer_for_career_a", "answer_for_career_b"} (same
    shape as question_gen.generate_discriminator, so callers can use either
    interchangeably) or None if unavailable/failed.
    """
    client = _client()
    if client is None:
        return None

    existing = "\n".join(f"- {q}" for q in existing_questions)
    prompt = (
        "I run a 20-questions-style game that guesses a person's occupation "
        "from yes/no questions. My model keeps confusing these two real "
        f"occupations:\n  Occupation A: {occupation_a}\n"
        f"  Occupation B: {occupation_b}\n\n"
        "Write ONE new yes/no question that a person would answer "
        "differently depending on which of the two occupations they "
        "actually have. Requirements:\n"
        "- Answerable by anyone about their own daily work (no jargon).\n"
        "- Must NOT mention or trivially reveal either occupation's name.\n"
        f"- Must NOT duplicate any of these existing questions:\n{existing}\n\n"
        "State the most likely answer for each occupation."
    )

    data = _call(client, prompt, _Discriminator, temperature=0.4)
    if data is None or data.answer_for_a == data.answer_for_b:
        return None
    return {
        "question": data.question.strip(),
        "answer_for_career_a": data.answer_for_a,
        "answer_for_career_b": data.answer_for_b,
    }
