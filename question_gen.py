"""Generate new discriminating questions when the model confuses two careers.

Primary path: ask the LLM for a yes/no question that splits the confused pair,
with structured JSON output so the answer plugs straight into the knowledge
base. Requires the `anthropic` package and API credentials; if either is
missing (or the call fails) the caller falls back to asking the player for a
question instead - the game keeps learning either way.
"""

from __future__ import annotations

import json

MODEL = "claude-opus-4-8"

_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {
            "type": "string",
            "description": "A single yes/no question a person could answer "
                           "about their own job. Must not reveal either career name.",
        },
        "answer_for_career_a": {"type": "string", "enum": ["yes", "no"]},
        "answer_for_career_b": {"type": "string", "enum": ["yes", "no"]},
    },
    "required": ["question", "answer_for_career_a", "answer_for_career_b"],
    "additionalProperties": False,
}


def generate_discriminator(career_a: str, career_b: str,
                           existing_questions: list[str]) -> dict | None:
    """Return {"question", "answer_for_career_a", "answer_for_career_b"} or
    None if the LLM path is unavailable or fails."""
    try:
        import anthropic
    except ImportError:
        return None

    existing = "\n".join(f"- {q}" for q in existing_questions)
    prompt = (
        "I run a 20-questions game that guesses a person's career from yes/no "
        "questions. My model keeps confusing these two careers:\n"
        f"  Career A: {career_a}\n"
        f"  Career B: {career_b}\n\n"
        "Write ONE new yes/no question that a person would answer differently "
        "depending on which of the two careers they have. Requirements:\n"
        "- Answerable by anyone about their own job (no jargon).\n"
        "- Must NOT mention or trivially reveal either career name.\n"
        "- Must NOT duplicate any existing question:\n"
        f"{existing}\n\n"
        "Also state the most likely answer for each career."
    )

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
            messages=[{"role": "user", "content": prompt}],
        )
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        if data["answer_for_career_a"] == data["answer_for_career_b"]:
            return None  # not a discriminator; don't pollute the question pool
        return data
    except Exception:
        return None
