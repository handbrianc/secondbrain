"""Leak detection and scrubbing helpers for the RAG pipeline.

Identifies reasoning/self-correction leakage in generated text and
produces cleaned versions with the leaked spans removed.
"""

from __future__ import annotations

import re

# Reasoning-leakage markers.  When the model cannot faithfully reproduce dense
# source content it can emit its own chain-of-thought self-talk as the "answer"
# (e.g. "... 22,631 filings? Actually '16,758'? No, ... I'm misreading ... I'll
# just say ...").  Such output is lexically diverse enough to pass the repetition
# guard, so these first-person recall/guessing phrases are checked explicitly.
# A healthy summary never narrates its own reading or uncertainty; detecting one
# marks the window implausible and routes it through the low-temperature retry.
_REASONING_LEAK_MARKERS = (
    "i'm misreading",
    "i am misreading",
    "i misread",
    "i'm struggling",
    "i am struggling",
    "i'm not sure",
    "i am not sure",
    "i'm overthinking",
    "i'm going to stop",
    "i'm going to guess",
    "i give up",
    "i can't recall",
    "i cannot recall",
    "i can't remember",
    "i cannot remember",
    "i don't remember",
    "i'm wasting time",
    "i'm reading",
    "i am reading",
    "i'll just say",
    "i will just say",
    "i'll trust",
    "i'll quote",
    "let me re-read",
    "let me reread",
    "let me re-check",
    "let me recheck",
    "let me reconsider",
    "let me scroll up",
    "let me scroll",
    "let me search",
    "let me quote",
    "let me guess",
    "actually, no",
    "actually no",
    "no, wait",
    "no wait",
    "wait, actually",
    "actually, wait",
    "i meant",
    "wait no",
    "or rather",
    "? actually,",
    "? actually ",
    "i'll just copy",
    "let me trace",
    "let me look",
    "let me check",
    "let me re-read the snippet",
    "let me look at the exact",
)


# Message the OpenAI provider emits when a reasoning spiral exhausts the
# reasoning budget before any content is produced. Treated as a dead end in the
# one-shot path and regenerated at low temperature instead of being surfaced.
_REASONING_BUDGET_FALLBACK_PREFIX = "I got stuck in repetitive reasoning"


def _contains_reasoning_leak(text_lower: str) -> bool:
    """Return True when *text_lower* reveals leaked chain-of-thought self-talk."""
    if any(marker in text_lower for marker in _REASONING_LEAK_MARKERS):
        return True
    return bool(
        _NUMERIC_SELF_CORRECT_RE.search(text_lower)
        or _NUMERIC_HEDGE_RE.search(text_lower)
    )


# Self-correction the model sometimes emits DIRECTLY into the content stream
# while re-verifying a figure it is unsure of (e.g. "77.?? (wait, the text says
# 78.29 percent)") -- just before it stalls.  Reasoning suppression cannot catch
# these because they arrive as content tokens, not reasoning.  Detect them early
# and recover with a clean low-temperature retry rather than streaming the leak.
#
# Only high-signal markers qualify: a mid-stream abort costs the whole window,
# so bare phrases such as "the text says" are excluded -- verbose models use
# them as ordinary citations, and a false trip here regenerates (or, if the
# retry trips too, silently drops) a perfectly good window.  Compound
# corrections like "77.29? Actually the text says 78.29" remain caught by the
# figure-then-hedge regex below.
_CONTENT_SELF_CORRECTION_MARKERS = (
    "??",
    "(wait,",
    "(wait ",
    ", wait -",
    " wait - ",
    "- wait,",
    "(the text says",
    "(text says",
    "(the text specifies",
    "(text specifies",
    "(text gives",
    "(the text gives",
    "(the text states",
    "(text states",
    "(the source states",
)


def _is_content_self_correction(text_lower: str) -> bool:
    """Return True when streamed content begins correcting an earlier figure."""
    return any(marker in text_lower for marker in _CONTENT_SELF_CORRECTION_MARKERS)


# The model sometimes leaks an inline numeric self-correction directly into the
# summary prose while unsure of a figure: it writes a candidate value, then
# immediately rejects it with "? No" and writes the corrected value, e.g.
# "a test accuracy of 48? No--45.78 percent".  None of the token-level markers
# above match a bare "<digit>? No", so catch it explicitly and drop only the
# rejected candidate ("48? No--") while keeping the corrected figure, which
# grounding then verifies against the source.
_NUMERIC_SELF_CORRECT_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*\?\s*(?:no|nope)\b[\s,;:\u2014\u2013-]*",
    re.IGNORECASE,
)


# Broader figure-then-hedge detector for compound self-corrections the "? No"
# strip regex cannot express, e.g. "77.29? Actually the text says 78.29
# percent".  Detection only: stripping stays conservative so grounding still
# sees the corrected value.
_NUMERIC_HEDGE_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*\?\s*(?:no|nope|actually|wait|oops|correction)\b",
    re.IGNORECASE,
)


# Scrub patterns for leaks the detector caught, ordered specific -> general,
# paired with the replacement each leaves behind.  The first two consume the
# rejected candidate plus its hedging machinery entirely; the parenthetical
# form keeps the captured correction because it lives inside "(wait, the text
# says X)".  Grounding then verifies the surviving value against the source.
_LEAK_SCRUB_RES: tuple[tuple[re.Pattern[str], str], ...] = (
    (_NUMERIC_SELF_CORRECT_RE, ""),
    (
        re.compile(
            r"\b\d+(?:[.,]\d+)?\s*\?\s*(?:no|nope|actually|wait|oops|correction)\b"
            r"[\s,;:\u2014\u2013-]*(?:(?:the )?text (?:says|states|gives|specifies)\s*)?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            # The candidate may be truncated ("77.??"), so allow a decimal
            # point without trailing digits before the question marks.
            r"\b\d+(?:[.,]\d*)?\s*\?{0,2}\s*\(wait,?\s*(?:the )?text "
            r"(?:says|states|gives|specifies)\s*([^)]*)\)",
            re.IGNORECASE,
        ),
        r"\1",
    ),
)


def _scrub_self_correction(text: str) -> str:
    """Remove self-correction artifacts from *text*, keeping corrected values.

    Applied repeatedly so stacked corrections ("48? No--45.78? Actually 43.05")
    collapse to the final value.  Only meaningful on text the detector flagged;
    the patterns require a figure followed by a hedge, which clean prose does
    not contain.
    """
    for _ in range(3):
        scrubbed = text
        for pattern, repl in _LEAK_SCRUB_RES:
            scrubbed = pattern.sub(repl, scrubbed)
        if scrubbed == text:
            return scrubbed
        text = scrubbed
    return text


def _strip_numeric_self_correction(text: str) -> str:
    """Remove leaked "<candidate>? No--" self-correction artifacts from *text*."""
    if not text:
        return text
    return _scrub_self_correction(text)


def _is_stream_leak(text_lower: str) -> bool:
    """Return True when streamed content reveals an inline self-correction."""
    if _is_content_self_correction(text_lower):
        return True
    return bool(
        _NUMERIC_SELF_CORRECT_RE.search(text_lower)
        or _NUMERIC_HEDGE_RE.search(text_lower)
    )
