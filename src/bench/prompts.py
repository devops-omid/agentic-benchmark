"""Deterministic filler prompts sized by characters to approximate a target token count."""

CHARS_PER_TOKEN = 3.6
FILLER_SENTENCE = "The quick brown fox jumps over the lazy dog near the riverbank."


def filler_prompt(target_tokens: int) -> str:
    unit = len(FILLER_SENTENCE) + 1
    body_chars = int(target_tokens * CHARS_PER_TOKEN)
    repeats = max(1, (body_chars + unit - 1) // unit)
    return (
        "Reply with one short sentence confirming you read the context below.\n"
        + " ".join([FILLER_SENTENCE] * repeats)
    )
