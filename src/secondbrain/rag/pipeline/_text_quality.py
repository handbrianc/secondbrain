"""Text-quality helpers for the RAG pipeline.

Deterministic metric-figure pruning, sentence/word-bounded trimming,
figure grounding against source context, and the function-word /
diversity vocabulary used to judge whether generated prose derailed.
"""

from __future__ import annotations

import re

# Function words used by the derailment detector.  Normal English prose keeps a
# steady share of determiners/pronouns/prepositions/auxiliaries sprinkled through
# it; a high-temperature "word-salad" degeneration crams content words together
# with almost none, and — unlike repetitive token-soup — stays high-diversity, so
# the repetition-based plausibility check alone misses it.  A trailing window low
# in function words is a strong signal that the stream has derailed.
_FUNCTION_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "some",
        "any",
        "no",
        "not",
        "none",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "from",
        "by",
        "with",
        "without",
        "about",
        "into",
        "through",
        "over",
        "under",
        "between",
        "among",
        "across",
        "against",
        "during",
        "before",
        "after",
        "above",
        "below",
        "up",
        "down",
        "off",
        "out",
        "via",
        "per",
        "and",
        "or",
        "but",
        "nor",
        "so",
        "yet",
        "because",
        "while",
        "though",
        "although",
        "if",
        "than",
        "then",
        "when",
        "where",
        "which",
        "who",
        "whom",
        "whose",
        "what",
        "how",
        "why",
        "as",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "am",
        "do",
        "does",
        "did",
        "done",
        "have",
        "has",
        "had",
        "having",
        "will",
        "would",
        "can",
        "could",
        "shall",
        "should",
        "may",
        "might",
        "must",
        "it",
        "its",
        "he",
        "she",
        "they",
        "them",
        "their",
        "we",
        "us",
        "our",
        "you",
        "your",
        "i",
        "me",
        "my",
        "him",
        "her",
    }
)


# A derailed trailing window is one whose function-word share falls below this
# fraction; normal prose (even dense technical writing) stays well above 0.1.
_DERAIL_FUNCTION_WORD_RATIO = 0.08


# ... or whose type-token ratio is this high.  A rambling "word-salad" stream
# keeps enough function words to defeat the ratio above, but it churns out an
# almost unbroken run of novel words, so nearly every token in a trailing window
# is unique — something normal prose (which reuses terms and closed-class words)
# never approaches.  This catches the high-diversity derailment the ratio alone
# misses.
_DERAIL_TYPE_TOKEN_RATIO = 0.85


# The type-token signal only counts as derailment when the window is ALSO low in
# function words (below this gate).  A genuinely useful summary — even a terse,
# varied one — still carries a normal share of determiners/prepositions; gating
# on it stops the novelty signal from firing on legitimate diverse prose and
# cutting a good section short, while still catching rambling word-salad, which
# drops well below this share of function words.
_DERAIL_TTR_FN_GATE = 0.25


# Correlation-like metrics are mathematically bounded to [-1, 1]: an information
# coefficient (IC) / rank-IC / correlation / R-squared can never exceed 1 in
# absolute value.  A small model under long or truncated context can emit a
# provably impossible value (e.g. "an average weekly IC of 3.32 and 6.68").  These
# patterns identify a value-bearing metric so the deterministic prune can strip
# anything outside the bound, with no reliance on the model.  The value-start
# pattern tolerates a hedge word ("an IC of around 4") between connector and
# value, since generated prose routinely hedges the impossible numbers it emits.
_METRIC_BOUNDED_RE = re.compile(
    r"(?:information\s+coefficient|rank[\s-]?ic|\bic\b|correlation(?:\s+coefficient)?|"
    r"\br\s*squared\b|r\s*[²2]\b|coefficient\s+of\s+determination)",
    re.IGNORECASE,
)


_METRIC_VALUE_START_RE = re.compile(
    r"\s*(?:of|:|=|is)\s*(?:approximately|approx\.?|around|about)?\s*"
    r"-?\d+(?:[.,]\d+)?",
    re.IGNORECASE,
)


_METRIC_VALUE_CONT_RE = re.compile(
    r"\s*(?:and|&|[,;/\u2013-]|\s)+\s*-?\d+(?:[.,]\d+)?", re.IGNORECASE
)


_NUM_RE = re.compile(r"-?\d+(?:[.,]\d+)?")


def _prune_implausible_metric_figures(text: str) -> str:
    """Deterministically remove metric values that are physically impossible.

    Every generated summary figure is checked against the hard mathematical bound
    for correlation-like metrics (|value| <= 1).  Where a value violates it, the
    trailing numeric clause is dropped, leaving the metric named without a
    nonsensical number (e.g. "an average weekly IC of 3.32 and 6.68" becomes
    "an average weekly IC").  Applies regardless of what the model "believed",
    so a fabricated statistic can never reach the final answer.
    """
    if not text:
        return text
    parts: list[str] = []
    last = 0
    for match in _METRIC_BOUNDED_RE.finditer(text):
        rest = text[match.end() :]
        clause = _METRIC_VALUE_START_RE.match(rest)
        if not clause:
            continue
        end = match.end() + clause.end()
        span = text[end:]
        while True:
            cont = _METRIC_VALUE_CONT_RE.match(span)
            if not cont:
                break
            end += cont.end()
            span = text[end:]
        values = _NUM_RE.findall(text[match.end() + clause.start() : end])
        peak = 0.0
        for value in values:
            try:
                magnitude = abs(float(value.replace(",", "")))
            except ValueError:
                continue
            if magnitude > peak:
                peak = magnitude
        if peak > 1.0:
            parts.append(text[last : match.end()])
            last = end
    if not parts:
        return text
    parts.append(text[last:])
    return "".join(parts)


# Figure-grounding verification.  The chapter/section summary path can still
# confabulate a specific figure that the source never states (e.g. inventing a
# backtest year like "2023-2027").  These helpers drop any high-specificity
# numeric figure in the generated summary that the source context does not
# contain, so a fabricated number never reaches the final answer — the same
# fail-closed philosophy as :func:`_prune_implausible_metric_figures`.
_GROUNDING_FIGURE_RE = re.compile(
    r"\b(\d+(?:[.,]\d+)?)\s*(%|percent|million|billion|thousand)?(?!\d)",
    re.IGNORECASE,
)


_GROUNDING_MAGNITUDE = {
    "million": 10**6,
    "billion": 10**9,
    "thousand": 10**3,
}


def _trim_to_sentence_end(text: str) -> str:
    """Cut *text* back to the last complete sentence if it ends mid-sentence.

    A bounded window whose stream hit the token/time cap stops mid-generation;
    cutting back to the last sentence terminal keeps the chapter overview from
    ending on a dangling fragment (e.g. "...the convolution").
    """
    s = text.rstrip()
    if not s or re.search(r"[.!?][\"'\u201d\u2019]?\s*$", s):
        return s
    cut = -1
    for m in re.finditer(r"[.!?][\"'\u201d\u2019]?\s", s):
        cut = m.end()
    if cut <= 0:
        return s
    return s[:cut].rstrip()


def _trim_to_word_budget(text: str, max_words: int) -> str:
    """Cap *text* at *max_words*, cutting back to the last complete sentence.

    The overview's length bound is enforced here -- deterministically, after
    generation -- instead of via a numeric prompt constraint.  Asking the
    model for "at most N words" is counterproductive: it cannot count words
    reliably, so it burns its reasoning budget counting and re-drafting.
    When no sentence terminal exists inside the budget (one runaway sentence),
    the raw word cut is kept rather than returning an empty overview.
    """
    words = re.finditer(r"\S+", text)
    cut = -1
    for i, m in enumerate(words):
        if i == max_words:
            cut = m.start()
            break
    if cut < 0:
        return text
    prefix = text[:cut].rstrip()
    trimmed = _trim_to_sentence_end(prefix)
    if trimmed:
        return trimmed
    return prefix


def _ends_on_sentence(text: str) -> bool:
    """Return True when *text* already ends on a completed sentence terminal.

    Detects the GLM failure mode where the server output cap amputates content
    mid-sentence but the stream returns normally -- no exception reaches the
    dead-stream recovery path, so the mid-sentence tail must be found here.
    """
    return bool(re.search(r"[.!?][\"'\u201d\u2019]?\s*$", text.rstrip()))


def _grounding_figure_key(
    match: re.Match[str],
) -> tuple[str | None, float | None, bool]:
    """Normalise a figure match to ``(canonical key, numeric value, is_decimal)``.

    The *key* identifies the figure in a unit-and-percent aware way so that
    "60 million", "60,000,000", and "60m" collide.  Small whole counts (< 1000,
    e.g. "15 indicators") return ``key=None`` and are never pruned, so a
    paraphrased count in the summary is not destroyed just because the source
    phrases it differently.
    """
    raw = match.group(1)
    unit = (match.group(2) or "").lower()
    try:
        num = float(raw.replace(",", ""))
    except ValueError:
        return None, None, False
    if unit in ("%", "percent"):
        val = num if num % 1 else int(num)
        return f"{val}%", num, False
    if unit in _GROUNDING_MAGNITUDE:
        scaled = num * _GROUNDING_MAGNITUDE[unit]
        return f"{int(scaled)}", scaled, False
    if num.is_integer():
        n = int(num)
        if n >= 1000:
            return f"Y{n}", float(n), False
        return None, None, False
    return str(num), num, True


def _ground_figures(summary: str, context: str) -> str:
    """Remove high-specificity numeric figures in *summary* absent from *context*.

    A chapter/section summary must state figures from the source document.  If
    the model produced a specific figure (a year, a percentage, a decimal, or a
    large magnitude count) that does not appear — even against a small rounding
    tolerance for decimals — it is treated as a fabrication and dropped.

    Parameters
    ----------
    summary:
        The generated summary text to vet.
    context:
        The source document context the summary was derived from.

    Returns
    -------
    str
        The summary with ungrounded figures removed; unchanged when every figure
        checks out.
    """
    grounded: set[str] = set()
    context_values: list[float] = []
    for m in _GROUNDING_FIGURE_RE.finditer(context):
        key, value, _is_decimal = _grounding_figure_key(m)
        if key is not None:
            grounded.add(key)
        if value is not None and not (key and key.startswith("Y")):
            context_values.append(value)

    drops: list[tuple[int, int]] = []
    for m in _GROUNDING_FIGURE_RE.finditer(summary):
        key, value, _is_decimal = _grounding_figure_key(m)
        if key is None or key in grounded:
            continue
        # Years must match exactly (2023 is not "close to" 2013).  Every other
        # class of figure tolerates a small rounding margin so a correctly
        # rounded value (3.7 vs 3.57) is not destroyed.
        if key.startswith("Y"):
            drops.append(m.span())
            continue
        if value is not None and any(
            abs(value - c) <= max(abs(c), abs(value)) * 0.05 for c in context_values
        ):
            continue
        drops.append(m.span())

    if not drops:
        return summary
    out: list[str] = []
    last = 0
    for start, end in drops:
        out.append(summary[last:start])
        last = end
    out.append(summary[last:])
    return "".join(out)
