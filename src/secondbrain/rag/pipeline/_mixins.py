"""Cohesive helper-method mixins for the RAG pipeline.

These mixin classes group the RAG pipeline's pure/structural/fallback helpers so
:class:`secondbrain.rag.pipeline.RAGPipeline` can inherit them, decomposing the
former single massive class. Every method operates on ``self`` state that is
always present on the composed ``RAGPipeline`` instance.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
import unicodedata
from collections import Counter
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, ClassVar

from secondbrain.config import config
from secondbrain.conversation import ConversationSession
from secondbrain.exceptions import ServiceUnavailableError
from secondbrain.rag.document_router import DocumentRouter
from secondbrain.rag.intent_parser import QueryIntent
from secondbrain.rag.pipeline._attributes import _RAGPipelineState
from secondbrain.rag.pipeline._constants import (
    BROAD_COVERAGE_TRIGGERS,
    CHAPTER_ENUMERATION_PATTERNS,
    ENUMERATE_CHAPTER_SIGNALS,
)

logger = logging.getLogger(__name__)


# Upper bound on how many independent map-reduce LLM calls one summarisation may
# issue.  Without this, a dense multi-chapter book or a chapter with many
# sections would fan out into dozens of sequential, thinking-mode LLM calls,
# making the chat appear frozen on "Thinking..." for minutes.
_MAX_MAP_REDUCE_WINDOWS = 50

# Temperature for deterministic map-reduce *summary* generation (chapter and
# section overviews). Summaries must faithfully reproduce the source figures, so
# they are generated near-deterministically instead of at the default creative
# temperature (which makes the model regenerate numbers rather than copy them).
# This matches the low temperature the degenerate-window retry already uses.
SUMMARY_TEMPERATURE = 0.1

# Max wall-clock seconds a single summary window may run before it is aborted as
# unresolvable.  A model can spend its whole budget re-verifying figures in its
# reasoning, emitting only sporadic content and never stabilizing; the cap
# guarantees the overall summary always terminates and returns to the prompt.
# On abort the window's partial content is retained (trimmed to a clean
# sentence), so a slow final window still contributes its ending instead of the
# chapter overview dropping it.
#
# Heavy-reasoning models can legitimately think for minutes before any content
# streams, so the default is generous and overridable via
# SECONDBRAIN_SUMMARY_WINDOW_MAX_SECONDS.  The previous 150s (tuned for
# DeepSeek) silently dropped GLM windows whose thinking alone approached the
# budget: the collapsed-thinking counter printed, then the timeout fired before
# the first content token and the window vanished from the overview.  600s was
# sized for the 8000-token budget; with _SUMMARY_REDUCE_MAX_TOKENS at 32768 a
# healthy dense-chapter stream can legitimately run past 600s, and aborting it
# here discards minutes of completed reasoning and restarts the whole
# generation, so the wall must exceed the budget's realistic drain time.
_WINDOW_MAX_SECONDS = max(
    60,
    int(os.environ.get("SECONDBRAIN_SUMMARY_WINDOW_MAX_SECONDS", "1200")),
)

# Source characters per summary window.  Splitting the body into bounded windows
# like this is what keeps every generation small -- fast, under the request
# timeout, and too short to drive the model into a figure-verification loop --
# which is what makes the summary path robust for any source size.  Windows are
# small enough that each window's summary completes well within the output token
# cap, so the last window is not truncated mid-sentence.
_SUMMARY_WINDOW_CHARS = 3500

# Output token caps for the summary paths (single-pass overview, and the
# two-pass map-reduce fallback: map digest -> reduce overview).  These are
# ceilings, NOT length targets: the prompts bound the visible length (terse
# digests, overview per the caller's instruction), and the final overview's
# length is enforced deterministically by _OVERVIEW_MAX_WORDS below -- never
# by a numeric constraint in a prompt, which only triggers word-counting
# loops in the model's reasoning.  The generous ceilings exist because
# GLM-class servers spend the SAME max_tokens budget on hidden reasoning and
# visible content -- a tight cap amputates the content mid-sentence at
# finish_reason=length, which is exactly what silently cut off summary
# windows under the previous 1200-token per-window cap.  8000 was itself
# amputated on the densest chapters (GLM burned it on reasoning alone while
# drafting and re-verifying every figure), leaving nothing for the overview;
# 32768 leaves ~4x the observed worst-case reasoning spend for the answer.
_MAP_DIGEST_MAX_TOKENS = 4000
_SUMMARY_REDUCE_MAX_TOKENS = 32768

# A chapter whose formatted source fits within this budget is summarized in
# ONE streamed call over the complete text (~80k tokens at ~4 chars/token --
# comfortably inside a 128k+ context window).  The two-pass map-reduce path
# below is only the fallback for genuinely oversized sources.
_SINGLE_PASS_MAX_CHARS = 320_000

# Reduce-prompt hierarchy: when the map-reduce fallback produces more than
# _HIERARCHY_THRESHOLD digests, they are first condensed into balanced groups
# of at most _HIERARCHY_GROUP_SIZE (one non-streamed call per group) so the
# final reduce reads a handful of merged digests instead of dozens of "Part N"
# fragments.  Group calls may fail; the raw digests are then passed through,
# so condensation is a size optimization that never regresses coverage.
_HIERARCHY_GROUP_SIZE = 8
_HIERARCHY_THRESHOLD = 12

# Front-matter "about this book" pages describe every chapter in prose:
# "Chapter 9 , AI Cloud Platforms for IoT , introduces major cloud platforms ...".
# These body-role sentences are the only "Chapter N" matches in books extracted
# without real heading/toc_entry chunks, and pinning a chapter's start page to
# the page its description sits on collapses the chapter's page range to that
# front-matter page and starves its content bucket.  The pattern requires the
# comma form ("Chapter N , Title") plus a description verb shortly after, so
# genuine headings ("Chapter 9: AI Cloud Platforms", "9 AI Cloud Platforms") and
# cross-references ("see Chapter 9 on page 144") never match.
_CHAPTER_DESC_RE = re.compile(
    r"Chapter\s+(\d+)\s*,\s+[A-Z].{0,240}?\b(?:introduces|explores|focuses|"
    r"dives|delves|provides|covers|describes|examines|presents|outlines|"
    r"walks|discusses|explains|emphasizes|helps|contains|shows|builds|"
    r"teaches|prepares|starts|takes|brings|opens|closes|gives|guides|"
    r"includes|is\b)",
    re.DOTALL,
)

# Tail of a front-matter chapter-description sentence inside a captured title:
# "... , introduces the core concepts of IoT and edge computing ...".  Trimming
# at the description verb leaves the bare chapter title.  The leading comma is
# required so ordinary titles ("How Regularization Introduces Robustness") are
# never cut.
_CHAPTER_DESC_TAIL_RE = re.compile(
    r",\s+(?:introduces|explores|focuses|dives|delves|provides|covers|describes|"
    r"examines|presents|outlines|walks|discusses|explains|emphasizes|helps|"
    r"contains|shows|builds|teaches|prepares|starts|takes|brings|opens|closes|"
    r"gives|guides|includes|is\b).*$",
)

# Front-matter ToC listing lines, parsed for the chapter pin/phantom-kill
# reconciliation tier.  Docling flattens the printed ToC into two row shapes:
# bare listing lines ("12 Bayesian Deep Learning 310") and Chapter-prefixed
# rows ("Chapter 4: Unsupervised Graph Learning 107") that run-on into the
# next entry on the same flattened line.  The per-line anchor plus the lazy
# 2-90 char letter-started title keeps a run-on section row ("584 Using
# Spearman's rank correlation ...") from satisfying the trailing page capture;
# roman-numeral rows ("IX Old Chapters 55") and multi-line fragments (page
# number orphaned on the next line) match neither shape and parse to nothing.
_TOC_LISTING_LINE_RE = re.compile(r"^\s*(\d{1,2})\s+([A-Za-z].{2,90}?)\s+(\d{1,3})\s*$")
_TOC_CHAPTER_ENTRY_RE = re.compile(
    r"Chapter\s+(\d{1,2})\s*[:.\-]\s*([A-Za-z].{2,90}?)\s+(\d{1,3})\b"
)
# Same Chapter-prefixed row WITHOUT a trailing page number (a wrapped entry,
# or one whose page number was lost in extraction).  A roster chapter with
# such a row in the ToC region is ambiguous, so the tier keeps (never kills)
# it and logs instead.
_TOC_CHAPTER_MENTION_RE = re.compile(r"Chapter\s+(\d{1,2})\s*[:.\-]")
# Coverage floor for the reconciliation tier: the parsed ToC must list at
# least this fraction of the roster chapters before a pin or a phantom kill
# may act; below it the tier is fully disabled.
_TOC_MIN_COVERAGE = 0.6

# Deterministic word ceiling for the final overview, enforced by trimming at
# a sentence boundary after generation (in _finalize_overview).  The prompt
# asks for a short overview in prose terms; the bound itself lives here so
# the model never burns reasoning counting words.  It is a runaway guard, NOT
# a length target: the reduce call streams its draft live, so any normal
# draft must survive finalization unchanged -- observed three-paragraph
# overviews run 500-900 words, and a tighter ceiling silently amputated the
# stored/history answer well short of the text the user had just read.
_OVERVIEW_MAX_WORDS = 1200

# Mid-stream guard for a live-streaming map-reduce window: once this many
# characters have accumulated, if the buffered text is already degenerate
# (repetitive/token-soup), we abort the stream immediately so a runaway window
# cannot stream an unbounded number of tokens (the summary path now uses the
# global unbounded max_tokens).  A short buffer is never treated as flooding so
# the first sentence of a normal summary always streams.
_STREAM_FLOOD_MIN_CHARS = 120

# Cap for the low-temperature *retry* of a degenerate window.  The retry is a
# recovery fallback, not the user-facing answer, so keeping it bounded prevents
# a still-degenerate retry from silently streaming a huge token-soup response.
_RETRY_MAX_TOKENS = 4096

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


_PAGE_REF_RE = re.compile(r"\bpage\s+(\d{1,4})\b", re.IGNORECASE)

# Leading "[ N ]" stub inserted by the fast-PDF extractor for the printed page
# number; it is extraction noise, not page content, so it is stripped from
# verbatim page output.
_PAGE_MARKER_RE = re.compile(r"^\[\s*\d{1,4}\s*\]\s*")

# A whole line that is just "[ N ]" — the printed-page-number stub may appear on
# its own line (e.g. under a section heading) rather than at the chunk start.
_PAGE_STUB_LINE_RE = re.compile(r"^\s*\[\s*\d{1,4}\s*\]\s*$", re.MULTILINE)


def _boundary_overlap(prev: str, nxt: str) -> int:
    """Longest k such that ``prev[-k:] == nxt[:k]`` (collapse chunk overlap)."""
    max_k = min(len(prev), len(nxt))
    for k in range(max_k, 0, -1):
        if prev[-k:] == nxt[:k]:
            return k
    return 0


class _StreamAbortError(Exception):
    """Internal control-flow signal to stop a streaming window early."""


class _StreamLeakError(Exception):
    """Internal signal: a window leaked reasoning/self-correction into content."""


# Characters withheld from the live stream before flushing, so a self-correction
# leak is caught on the buffered tail and the window aborted before it streams.
_STREAM_LEAK_HOLD = 120


if TYPE_CHECKING:  # pragma: no cover - import cycle avoided at runtime
    pass


class _FormattingMixin(_RAGPipelineState):
    """Context/prompt/history formatting helpers."""

    def _format_context(
        self,
        chunks: list[dict[str, Any]],
        max_chars: int | None = None,
    ) -> str:
        if max_chars is None:
            max_chars = self._config.rag_max_context_chars
        r"""Format retrieved chunks into context text.

        Args:
            chunks: List of search results with chunk_text, source_file.
            max_chars: Maximum context length.

        Returns:
            Formatted context string.

        Example:
            >>> chunks = [{"chunk_text": "Hello", "source_file": "doc.pdf", "page": 1}]
            >>> pipeline._format_context(chunks)
            'Source: doc.pdf (page 1)\nHello\n\n'
        """
        if not chunks:
            return ""

        context_parts = []
        total_chars = 0

        for chunk in chunks:
            chunk_text = chunk.get("chunk_text", chunk.get("text", ""))
            source_file = chunk.get("source_file", chunk.get("source", "unknown"))
            page = chunk.get("page", chunk.get("page_number", "unknown"))
            chunk_role = chunk.get("chunk_role")

            # Truncate chunk if too long
            if len(chunk_text) > self._config.rag_chunk_preview_chars:
                chunk_text = chunk_text[: self._config.rag_chunk_preview_chars] + "..."

            tags: list[str] = []
            if chunk_role:
                tags.append(chunk_role)
            if chunk_role in ("heading", "toc_entry") or chunk_role is None:
                label = self._infer_section_label(chunk_text, chunk_role)
                if label:
                    tags.append(label)
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            source_line = f"Source: {source_file} (page {page}{tag_str})"
            chunk_entry = f"{source_line}\n{chunk_text}\n"

            # Check if adding this chunk exceeds max_chars
            if total_chars + len(chunk_entry) > max_chars:
                break

            context_parts.append(chunk_entry)
            total_chars += len(chunk_entry)

        return "\n\n".join(context_parts)

    def _build_prompt(
        self,
        query: str,
        context: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build prompt for LLM with context and query.

        Template:
        ```
        [System instructions about using context]

        === DOCUMENT CONTEXT START ===
        {context}
        === DOCUMENT CONTEXT END ===

        {conversation_history if present}

        Question: {query}

        Answer:
        ```

        Args:
            query: User query text.
            context: Formatted, context from retrieved chunks.
            conversation_history: Optional conversation history.

        Returns:
            Complete prompt text for LLM.

        Example:
            >>> prompt = pipeline._build_prompt("What is Python?", context)
            >>> "You are a helpful assistant" in prompt
            True
        """
        system_prompt = config().rag_system_prompt

        # Build prompt
        prompt_parts = [system_prompt]

        # Add context with clear delimiters
        if context:
            prompt_parts.append("\n\n=== DOCUMENT CONTEXT START ===\n")
            prompt_parts.append(context)
            prompt_parts.append("\n=== DOCUMENT CONTEXT END ===\n")
        else:
            prompt_parts.append(
                "\n\nNote: No relevant context was found in the documents."
            )

        # Add conversation history if present
        if conversation_history:
            history_text = self._format_history(conversation_history)
            prompt_parts.append(f"\n\nConversation History:\n{history_text}")

        # Add query
        prompt_parts.append(f"\n\nQuestion: {query}\n\nAnswer:")

        return "".join(prompt_parts)

    def _dedupe_by_text_hash(
        self, chunks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Remove duplicate chunks by 512-byte text prefix hash.

        Used by iterative RAG to collapse repeated chunks across
        multiple per-section search iterations.

        Args:
            chunks: List of chunk dicts with 'chunk_text' key.

        Returns:
            Deduplicated list preserving first occurrence order.
        """
        seen: set[int] = set()
        result: list[dict[str, Any]] = []
        for chunk in chunks:
            text = chunk.get("chunk_text", "")[:512]
            h = hash(text)
            if h not in seen:
                seen.add(h)
                result.append(chunk)
        return result

    def _format_history(
        self,
        history: list[dict[str, Any]],
    ) -> str:
        """Format conversation history for prompt.

        Args:
            history: List of message dictionaries with role and content.

        Returns:
            Formatted history string.

        Example:
            >>> history = [{"role": "user", "content": "Hello"}]
            >>> pipeline._format_history(history)
            "User: Hello"
        """
        if not history:
            return ""

        lines = []
        for msg in history:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            lines.append(f"{role.capitalize()}: {content}")

        return "\n".join(lines)

    def _create_error_response(
        self,
        error: str,
        query: str,
    ) -> dict[str, Any]:
        """Create an error response with graceful degradation.

        Args:
            error: Error message describing the failure.
            query: The original query.

        Returns:
            Dictionary with error response data.

        Example:
            >>> pipeline._create_error_response("Connection failed", "test query")
            {"answer": "I apologize...", "query": "test query"}
        """
        return {
            "answer": f"I apologize, but I encountered an error: {error}. Please try again.",
            "query": query,
        }


class _StructureMixin(_RAGPipelineState):
    """Chapter/section detection and structural helpers."""

    def _derive_chapter_roster(self, structure_chunks: list[dict[str, Any]]) -> str:
        import re

        if self._chunks_are_code_like(structure_chunks):
            # No prose structure to enumerate (see _chunks_are_code_like) — emit
            # an empty header so the LLM never sees a fabricated chapter index.
            return ""

        ch_entries, ch_good, appendix_entries = self._derive_chapter_numbers(
            structure_chunks
        )
        ch_titles: dict[int, str] = {}
        for ch_num, _src, title in ch_entries:
            if ch_num in ch_good and ch_num not in ch_titles:
                ch_titles[ch_num] = title if title else "Unknown"

        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        sec_entries: list[tuple[int, str, str]] = []
        seen_sec: set[str] = set()
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if major < 1 or major > 30:
                    continue
                full_match = m.group(0)
                sec_num = full_match.split()[0] if full_match else ""
                raw_title = (m.group(3) or "").strip().rstrip(".")
                if len(raw_title) < 2:
                    continue
                sec_key = f"{major}.{sec_num.split('.')[1] if '.' in sec_num else '0'}"
                if sec_key not in seen_sec:
                    seen_sec.add(sec_key)
                    sec_entries.append((major, sec_num, raw_title))

        sec_entries.sort(key=lambda x: (x[0], *[int(p) for p in x[1].split(".") if p]))

        # When authoritative "Chapter N" headings were detected, section numbers
        # from any other major are body-text noise (dataframe dumps, page stubs),
        # not real chapters — they must not spawn fabricated `[Chapter N]` lines.
        if ch_good:
            sec_entries = [s for s in sec_entries if s[0] in ch_good]

        # Group detected subsections by their parent chapter.
        sec_by_major: dict[int, list[tuple[str, str]]] = {}
        for major, sn, title in sec_entries:
            sec_by_major.setdefault(major, []).append((sn, title))

        # Build the index from the UNION of reliably-detected chapter headings
        # (ch_good) and chapters that have recognised subsections, so a chapter
        # whose heading was detected but whose section headers were not seen in
        # the probe chunks still appears instead of silently vanishing.
        chapter_nums = sorted(set(ch_good) | set(sec_by_major))

        lines: list[str] = []
        # Cap subsection detail per chapter so one long chapter cannot starve
        # the rest of the index, but never drop a chapter heading itself.
        max_subsections_per_chapter = 30
        for major in chapter_nums:
            sections = sec_by_major.get(major, [])
            ch_title = ch_titles.get(major)
            if ch_title and sections:
                first, _t = sections[0]
                lines.append(f"[Chapter {major}] {first} — {ch_title}")
            elif ch_title:
                lines.append(f"[Chapter {major}] — {ch_title}")
            elif sections:
                sn, title = sections[0]
                lines.append(f"[Chapter {major}] {sn} — {title}")
            else:
                continue
            for sn, title in sections[1:max_subsections_per_chapter]:
                lines.append(f"  {sn} — {title}")

        if appendix_entries:
            lines.append("")
            for label, _src, title in appendix_entries:
                lines.append(f"[Appendix {label}] — {title}")

        header = (
            "DOCUMENT STRUCTURE INDEX (enumerate ALL of the following in your answer):\n"
            + "\n".join(lines)
            + "\n\n"
        )
        return header

    _SECTION_LABEL_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Chapter|Section|Appendix|Part)\s+\S+",
        re.IGNORECASE,
    )

    @staticmethod
    def _infer_section_label(chunk_text: str, chunk_role: str | None) -> str | None:
        if chunk_role not in ("heading", "toc_entry"):
            return None
        m = _StructureMixin._SECTION_LABEL_RE.search(chunk_text[:200])
        if m:
            label = m.group(0)
            after = chunk_text[m.end() :].split("\n")[0].strip().rstrip(".:-—")
            if after:
                return f"{label}: {after}"
            return label
        return None

    def _is_enumerate_chapters_query(self, query: str) -> bool:
        """Detect queries explicitly requesting chapter-by-chapter enumeration.

        Matches phrases like "summarize all 21 chapters", "chapter 1", "give me an overview of each chapter".
        Returns True when query mentions chapter numbers AND implies enumeration (not just a single chapter lookup).

        Args:
            query: User query string.

        Returns:
            True if query explicitly enumerates chapters.
        """
        q = query.lower()
        has_chapter_ref = any(p.search(q) for p in CHAPTER_ENUMERATION_PATTERNS)
        has_enum_signal = any(t in q for t in ENUMERATE_CHAPTER_SIGNALS)
        return has_chapter_ref and has_enum_signal

    _APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s+(.{2,60})",
    )
    _BARE_APPENDIX_RE: ClassVar[re.Pattern[str]] = re.compile(
        r"(?:^|\n)\s*(?:Appendix|APPENDIX|Annex|ANNEX)\s+([A-Za-z])\s*[.:-]?\s*(.{2,80})",
        re.MULTILINE,
    )

    @staticmethod
    def _chunks_are_code_like(structure_chunks: list[dict[str, Any]]) -> bool:
        """Return True when structure-probe chunks look like source code, not prose.

        Structural chapter extraction is only meaningful for prose manuals.
        Source code — especially bundled/minified output — sets off the
        chapter/section regexes on version numbers, identifiers and SVG/data
        path fragments (e.g. ``8.5``, ``7.0.0``, ``25.8``), producing
        hallucinated chapters for documents that have none.  This gate is
        intentionally conservative: it only fires on unambiguous code signals
        (near-zero whitespace density, or pervasive code punctuation), so
        genuine prose documents are never suppressed.

        Parameters
        ----------
        structure_chunks :
            List of probe chunk dicts (each with a ``chunk_text`` key).

        Returns
        -------
        bool
            True when the sampled content is clearly code, False otherwise.
        """
        if not structure_chunks:
            return False
        text = "".join(
            (c.get("chunk_text") or "")[:4000] for c in structure_chunks[:24]
        )
        n = len(text)
        if n < 200:
            # Too little signal to classify — never suppress a prose document.
            return False

        # Signal 1: bundled / minified output has almost no whitespace at all
        # (prose has a blank between essentially every word, ~15%+ whitespace).
        whitespace = sum(1 for ch in text if ch.isspace())
        if whitespace / n < 0.05:
            return True

        # Signal 2: code punctuation density.  Braces, semicolons, and
        # operators appear constantly in source code (formatted or not) but are
        # essentially absent from prose.  Parens and quotes are excluded as
        # they occur in ordinary writing.
        code_punct = "{};=<>&|#`"
        density = sum(1 for ch in text if ch in code_punct) / n
        return density > 0.02

    @staticmethod
    def _clean_chapter_title(title: str) -> str:
        """Return a TOC chapter title with page numbers and run-on entries removed.

        Dotted ToC heads look like ``Chapter 8 The ML4T Workflow ....... 223``.
        Docling-flattened ToCs drop the dots and run consecutive entries together,
        separating them with bare page numbers only ("Title 147 Next section 148
        More"). The capture regexes therefore grab the following entries too, so
        the text is cut at the first standalone page number that precedes a
        capitalized continuation (the start of the next entry); trailing page
        numbers and run-on description sentences are then stripped, leaving the
        real chapter heading.
        """
        # NFKD + combining-mark stripping canonicalizes the docling spellings
        # of accented titles (precomposed U+00EF vs decomposed i + U+0308) so
        # both clean to the same complete string instead of being split or
        # mangled at the non-ASCII mark.
        title = "".join(
            ch
            for ch in unicodedata.normalize("NFKD", title)
            if not unicodedata.combining(ch)
        )
        title = re.sub(r"\s*\.{2,}[.\-\u2013\u2014]*", " ", title)
        title = re.sub(r"\s+", " ", title).strip()
        title = re.split(r"\s+\d{1,4}\s+(?=[A-Z(])", title)[0]
        title = re.sub(r"[\s.\u2026:\-\u2013\u2014]*\d+\s*$", "", title)
        # Front-matter description sentences run the captured title on into the
        # sentence body ("Chapter 3 , Machine Learning for IoT , explores
        # supervised and unsupervised ..."); cut at the description verb so the
        # heading carries the chapter title only.
        title = _CHAPTER_DESC_TAIL_RE.sub("", title)
        return title.strip(" \t\r\n.,:;-\u2013\u2014")

    @staticmethod
    def _front_matter_desc_pages(structure_chunks: list[Any]) -> dict[int, int]:
        """Map chapter number -> page of its front-matter description sentence.

        Books extracted without heading/toc_entry roles still carry per-chapter
        prose descriptions in the front matter ("Chapter 9 , AI Cloud Platforms
        for IoT , introduces ...").  Those sentences used to serve as page
        anchors for the very chapters they describe, pinning them to the
        front-matter page instead of their real start.  Callers use the result
        to refuse anchoring a chapter on its description page.
        """
        desc_pages: dict[int, int] = {}
        for c in structure_chunks:
            page = int(c.get("page_number") or 0)
            text = c.get("chunk_text") or ""
            for m in _CHAPTER_DESC_RE.finditer(text):
                desc_pages.setdefault(int(m.group(1)), page)
        return desc_pages

    @staticmethod
    def _toc_chapter_listings(
        structure_chunks: list[Any],
    ) -> tuple[dict[int, tuple[str, int]], set[int]]:
        """Parse front-matter ToC listing rows into chapter -> (title, page).

        Returns (listings, mentions).  Chapter rows arrive in the two shapes
        the module ToC regexes describe; a "Chapter N :.-" row whose trailing
        page number was lost in extraction is collected separately as an
        ambiguous mention so the reconciliation tier can keep (never kill)
        its chapter.
        """
        listings: dict[int, tuple[str, int]] = {}
        mentions: set[int] = set()
        for c in structure_chunks:
            text = c.get("chunk_text") or ""
            for line in text.split("\n"):
                m = _TOC_LISTING_LINE_RE.match(line)
                if m:
                    listings.setdefault(
                        int(m.group(1)), (m.group(2).strip(), int(m.group(3)))
                    )
                    continue
                entry = _TOC_CHAPTER_ENTRY_RE.search(line)
                if entry:
                    listings.setdefault(
                        int(entry.group(1)),
                        (entry.group(2).strip(), int(entry.group(3))),
                    )
                mention = _TOC_CHAPTER_MENTION_RE.search(line)
                if mention:
                    mentions.add(int(mention.group(1)))
        return listings, mentions

    @staticmethod
    def _toc_listing_pages(
        structure_chunks: list[Any],
        desc_pages: dict[int, int],
        roster: set[int],
    ) -> tuple[dict[int, tuple[str, int]], set[int]]:
        """Gate the ToC parse to the region and coverage the tier trusts.

        Only chunks strictly below the earliest chapter-description page are
        parsed: that front-matter span is where the printed ToC lives, and
        the description pages mark where the book's prose begins.  With no
        description evidence, or when the parse lists fewer than
        ``_TOC_MIN_COVERAGE`` of the roster chapters, the tier is disabled
        and both results come back empty so neither a pin nor a phantom kill
        can act.
        """
        if not desc_pages or not roster:
            return {}, set()
        cap = min(desc_pages.values())
        region = [c for c in structure_chunks if int(c.get("page_number") or 0) < cap]
        if not region:
            return {}, set()
        listings, mentions = _StructureMixin._toc_chapter_listings(region)
        matched = sum(1 for ch in roster if ch in listings)
        if matched / len(roster) < _TOC_MIN_COVERAGE:
            return {}, set()
        return listings, mentions

    @staticmethod
    def _detect_chapter_openings(body_chunks: list[Any]) -> dict[int, int]:
        """Map chapter numbers to their start page from body-opening headers.

        Some books (e.g. ML4T) tag chapter openings as *body* chunks in a
        magazine style -- a ``[ 591 ]`` printed-page marker, then a bare chapter
        number line, then a capitalized title -- so they are invisible to the
        heading/TOC structure probe.  This scans body chunks for those openings
        to fill in every real chapter boundary, so each chapter's page range is
        bounded by the next chapter's start and the next chapter's content
        cannot leak into the previous chapter's bucket.
        """
        marker = re.compile(r"^\[\s*\d{1,4}\s*\]\s*\r?\n?")
        dot_leader = re.compile(r"\.{2,}")
        page_suffix = re.compile(r"\d+\s*$")
        starts: dict[int, int] = {}
        for c in body_chunks:
            page = int(c.get("page_number", 0) or 0)
            if page < 20:  # front matter / TOC
                continue
            text = (c.get("chunk_text") or "").lstrip()
            m = marker.match(text)
            if m:
                text = text[m.end() :].lstrip()
            head = text.split("\n")[0].strip()
            if not (head.isdigit() and 1 <= int(head) <= 30):
                continue
            for ln in text.split("\n")[1:3]:
                t = ln.strip()
                if len(t) < 4 or not re.match(r"^[A-Z]", t):
                    continue
                if dot_leader.search(t) or page_suffix.search(t.rstrip()):
                    break
                starts.setdefault(int(head), page)
                break
        return starts

    def _derive_chapter_numbers(
        self, structure_chunks: list[dict[str, Any]]
    ) -> tuple[list[tuple[int, str, str]], set[int], list[tuple[str, str, str]]]:
        """Return reliable chapter and appendix entries from structure chunks.

        Returns (entries, chapter_level_nums, appendix_entries) where
        chapter_level_nums are chapter numbers from CHAPTER_N_RE/BARE_CHAPTER_RE
        (reliable titles) and appendix_entries are (appendix_label, source, title).
        """
        import re

        if self._chunks_are_code_like(structure_chunks):
            # Code files (bundled JS, source, etc.) have no prose chapter
            # structure — the regexes below would just hallucinate chapters
            # from version numbers and identifiers.  Suppress entirely so the
            # pipeline falls through to generic search.
            return [], set(), []

        entries: list[tuple[int, str, str]] = []
        appendix_entries: list[tuple[str, str, str]] = []
        seen: set[tuple[int, str]] = set()
        seen_appendix: set[tuple[str, str]] = set()
        dot_leader = re.compile(r"\.{2,}[.\-]+")
        section_re = re.compile(r"(\d+)(?:\.(\d+))+(?:\s+(.+))?")
        chapter_n_re = re.compile(
            r"(?:Chapter\s+(\d+)\s*[:\-]?\s*|(?:Module|Lesson)\s+(\d+)\s*[:\-]\s*)"
            r"((?:(?!\.{2,})(?!\s+\d{1,4}\s*[\r\n])(?!\n\s*(?:\n|(?:Chapter|Module|Lesson|Appendix)\s+\d+))"
            r"[A-Za-z0-9 ,'\-():/+\s.\u2013\u2014]){2,120})",
            re.IGNORECASE,
        )
        bare_chapter_re = re.compile(
            r"(?:^|\n)\s*(\d{1,2})\.?\s+([A-Za-z][A-Za-z0-9\s\-\(\),'/:.\u2013\u2014]{4,80})",
            re.MULTILINE,
        )
        # Patterns for appendix detection
        appendix_n_re = self._APPENDIX_RE
        bare_appendix_re = self._BARE_APPENDIX_RE
        seen_sec: set[int] = set()
        sec_limit = 0

        # Pass 1: CHAPTER_N_RE + APPENDIX_N_RE (most reliable patterns)
        desc_titles: dict[tuple[int, str], str] = {}
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            for dm in _CHAPTER_DESC_RE.finditer(raw):
                dch = int(dm.group(1))
                dtitle = self._clean_chapter_title(
                    re.sub(r"^Chapter\s+\d+\s*,\s*", "", dm.group(0))
                )
                if len(dtitle) >= 4 and (dch, source) not in desc_titles:
                    desc_titles[(dch, source)] = dtitle
            for nm in chapter_n_re.finditer(raw):
                major = int(nm.group(1) or nm.group(2))
                if major < 1 or major > 30 or (major, source) in seen:
                    continue
                title = self._clean_chapter_title(nm.group(3))
                if len(title) < 2:
                    continue
                # Mid-sentence cross-references ("discussed in Chapter 12 of
                # Doing Bayesian Data Analysis by Kruschke") capture a
                # lowercase run-on as the title; real headings never start
                # lowercase.
                if title[0].islower():
                    continue
                fw = title.lower().split()[0] if title.split() else ""
                if fw in (
                    "contents",
                    "copyright",
                    "licensed",
                    "license",
                    "trolltech",
                    "red",
                    "bootstrap",
                    "of",
                    "and",
                    "in",
                    "by",
                    "from",
                    "with",
                    "for",
                    "to",
                ):
                    continue
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    continue
                seen.add((major, source))
                entries.append((major, source, title))
            for am in appendix_n_re.finditer(raw):
                label = am.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = self._clean_chapter_title(am.group(2))
                if len(title) < 2:
                    continue
                # Skip false positives: mid-sentence references like
                # "Appendix A of the Specification" (title starts with
                # a preposition/article/conjunction, not a heading).
                _fpa = title.lower().split()[0] if title.split() else ""
                if _fpa in (
                    "of",
                    "to",
                    "in",
                    "for",
                    "the",
                    "and",
                    "or",
                    "by",
                    "with",
                    "from",
                    "at",
                    "on",
                    "is",
                    "are",
                    "its",
                    "this",
                    "that",
                    "was",
                    "were",
                    "been",
                ):
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

        # Rescue roster titles captured from preface cross-references:
        # "(covered in Chapter 10). My goal is …" captures "). My goal is …"
        # as the title — garbage that can never match a heading.  The
        # verb-gated description sentence carries the real title, so swap
        # it in when the roster title starts with punctuation.
        for i, (major, source, title) in enumerate(entries):
            rescued = desc_titles.get((major, source))
            if rescued and title and not title[0].isalnum():
                entries[i] = (major, source, rescued)

        # Authoritative "Chapter N" headings (from chapter_n_re in pass 1) define
        # the true chapter span.  When present, bare-number and section matches
        # may corroborate within that span but must not invent chapters beyond
        # it — otherwise noisy body text (e.g. "12 Selection and Assignment" or
        # dataframe dumps) fabricates chapters for books whose chapters are all
        # explicitly labeled "Chapter N".
        auth_max = max((e[0] for e in entries), default=0)

        # Pass 2: bare_chapter_re + bare_appendix_re
        ft_catch = re.compile(
            r"\d+\s+(\d{1,2})\s+([A-Za-z][A-Za-z0-9\s\-\(\),'/:.\u2013\u2014]{4,80})"
        )
        legal_starts = {
            "contents",
            "copyright",
            "licensed",
            "license",
            "trolltech",
            "red",
            "bootstrap",
            "a",
            "an",
            "the",
            "you",
            "your",
            "this",
            "each",
            "by",
            "if",
            "as",
            "subject",
            "whereas",
            "notwithstanding",
            "accepting",
            "submission",
            "disclaimer",
            "disclaimers",
            "limitation",
            "at",  # "15 At least moderately important"
            # Report / white-paper false-positive starters — these
            # first words appear in non-chapter section headings
            # (e.g. "8 Key findings", "22 Question:") and would
            # otherwise be hallucinated as chapter numbers.
            "key",
            "question",
            "questions",
            "figure",
            "table",
        }
        for chunk in structure_chunks:
            raw = chunk.get("chunk_text", "")
            source = chunk.get("source_file", "")
            cleaned = dot_leader.sub("", raw, count=1).strip()

            for bm in bare_chapter_re.finditer(raw):
                major = int(bm.group(1))
                if (
                    major < 1
                    or major > 30
                    or (auth_max > 0 and major > auth_max)
                    or (major, source) in seen
                ):
                    continue
                title = self._clean_chapter_title(bm.group(2))
                if len(title) < 4:
                    continue
                fw = (title.lower().split()[0] if title.split() else "").rstrip(":;,.")
                if fw in legal_starts:
                    continue
                if title[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title, re.IGNORECASE):
                    continue
                seen.add((major, source))
                entries.append((major, source, title))

            for bam in bare_appendix_re.finditer(raw):
                label = bam.group(1).upper()
                if (label, source) in seen_appendix:
                    continue
                title = self._clean_chapter_title(bam.group(2))
                if len(title) < 4:
                    continue
                seen_appendix.add((label, source))
                appendix_entries.append((label, source, title))

            for fm in ft_catch.finditer(raw):
                major_ft = int(fm.group(1))
                if (
                    major_ft < 1
                    or major_ft > 30
                    or (auth_max > 0 and major_ft > auth_max)
                    or (major_ft, source) in seen
                ):
                    continue
                title_ft = self._clean_chapter_title(fm.group(2))
                if len(title_ft) < 6:
                    continue
                fw_ft = (
                    title_ft.lower().split()[0] if title_ft.split() else ""
                ).rstrip(":;,.")
                if fw_ft in legal_starts:
                    continue
                if title_ft[0].islower():
                    continue
                if re.search(r"\bon\s+page\s+\d+", title_ft, re.IGNORECASE):
                    continue
                seen.add((major_ft, source))
                entries.append((major_ft, source, title_ft))

            seen_max = max([s[0] for s in seen], default=0)
            sec_limit = seen_max + 3 if seen_max > 0 else 999
            for m in section_re.finditer(cleaned):
                major = int(m.group(1))
                if (
                    major < 1
                    or major > 30
                    or major in seen_sec
                    or (major, source) in seen
                    or (seen_max > 0 and major > sec_limit)
                ):
                    continue
                raw_title = (m.group(3) or "").strip()
                clean_title = raw_title.rstrip(".")
                if len(clean_title) < 2:
                    continue
                fw = clean_title.lower().split()[0] if clean_title.split() else ""
                if re.match(r"\d+(?:\.\d+)*$", fw):
                    clean_title = ""
                seen_sec.add(major)

        # Phase 3: chunk-boundary recovery for chapters
        if entries:
            found_nums = {e[0] for e in entries}
            all_seen = {s[0] for s in seen}
            lo = min(found_nums)
            hi = max(found_nums)
            for gap_n in range(lo + 1, hi):
                if gap_n in all_seen:
                    continue
                for i in range(len(structure_chunks) - 1):
                    cur = structure_chunks[i]
                    nxt = structure_chunks[i + 1]
                    cur_text = cur.get("chunk_text", "")
                    src_cur = cur.get("source_file", "")
                    if (
                        f"Chapter {gap_n}" not in cur_text
                        and f"chapter {gap_n}" not in cur_text
                    ):
                        continue
                    idx = cur_text.lower().find(f"chapter {gap_n}")
                    remaining = len(cur_text) - idx
                    if remaining > 80 or (gap_n, src_cur) in seen:
                        continue
                    nxt_text = nxt.get("chunk_text", "").strip()
                    first_line = nxt_text.split("\n")[0].strip()
                    if (
                        len(first_line) >= 4
                        and first_line[0].isupper()
                        and not first_line[0].islower()
                        and not re.search(r"^\d+\.\d+", first_line)
                    ):
                        title = re.sub(r"\s*\d+\s*$", "", first_line).rstrip(".")
                        seen.add((gap_n, src_cur))
                        entries.append((gap_n, src_cur, title))

        entries.sort(key=lambda x: x[0])
        appendix_entries.sort(key=lambda x: x[0])

        # Post-validation: drop outlier chapters that are likely false
        # positives from over-eager pass-2 regex patterns (bare_chapter_re,
        # ft_catch).  Find the longest consecutive run of chapter numbers;
        # if it accounts for >= 60 % of detected chapters AND there are
        # at least 5 total entries (too few data points makes the ratio
        # unreliable), exclude chapters outside that run.
        if len(entries) >= 5:
            all_nums = sorted({e[0] for e in entries})
            runs: list[list[int]] = [[all_nums[0]]]
            for n in all_nums[1:]:
                if n == runs[-1][-1] + 1:
                    runs[-1].append(n)
                else:
                    runs.append([n])
            main_run = max(runs, key=len)
            if len(main_run) / len(all_nums) >= 0.60:
                main_set = set(main_run)
                entries = [e for e in entries if e[0] in main_set]
                seen = {(n, s) for (n, s) in seen if n in main_set}

        # LLM fallback: classify unmatched appendix candidates
        if not appendix_entries and self._llm_provider is not None:
            llm_candidates: list[str] = []
            llm_sources: list[str] = []
            seen_keywords: set[str] = {str(e[0]) for e in entries}
            seen_keywords.update(al[0] for al in appendix_entries)
            for chunk in structure_chunks:
                raw = chunk.get("chunk_text", "").strip()
                src = chunk.get("source_file", "")
                first_line = raw.split("\n")[0].strip()
                if not first_line or len(first_line) > 120:
                    continue
                first_word = first_line.split()[0].lower() if first_line.split() else ""
                if first_word in seen_keywords:
                    continue
                if not any(
                    k in first_line.lower()
                    for k in ("appendix", "annex", "supplement", "supplementary")
                ):
                    continue
                candidate = first_line[:120]
                llm_candidates.append(candidate)
                llm_sources.append(src)

            if llm_candidates:
                candidates_prompt = (
                    "Classify each of the following document headings. "
                    "If it is an appendix, respond with APPENDIX:<label> on its own line, "
                    "where label is a single letter like A, B, C. "
                    "If it is a chapter heading, respond with CHAPTER. "
                    "If neither, respond with NONE. "
                    "One response per line, in order.\n\n"
                    + "\n".join(
                        f"{i + 1}. {c}" for i, c in enumerate(llm_candidates[:5])
                    )
                )
                try:
                    llm_reply = self._llm_provider.generate(
                        prompt=candidates_prompt,
                        temperature=0.1,
                        max_tokens=200,
                    )
                    for i, line in enumerate(llm_reply.strip().split("\n")):
                        line = line.strip()
                        if i >= len(llm_candidates):
                            break
                        if line.startswith("APPENDIX:"):
                            label = line.split(":", 1)[1].strip().upper()
                            if label and len(label) == 1 and label.isalpha():
                                candidate_text = llm_candidates[i]
                                parts = candidate_text.split(None, 2)
                                title = parts[-1] if len(parts) > 1 else candidate_text
                                title = title.rstrip(".:-")
                                key = (label, llm_sources[i])
                                if key not in seen_appendix:
                                    seen_appendix.add(key)
                                    appendix_entries.append(
                                        (label, llm_sources[i], title)
                                    )
                except Exception:
                    logger.debug("LLM appendix fallback failed", exc_info=True)

        return entries, {s[0] for s in seen}, appendix_entries

    def _is_broad_coverage_query(self, query: str) -> bool:
        q = query.lower().strip()
        return any(t in q for t in BROAD_COVERAGE_TRIGGERS)

    def _probe_document_structure(
        self,
        top_k: int = 10000,
        source_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Probe for document structural elements (TOC/section headers) via chunk_role.

        Attempts targeted structural-role filters first; falls back to raw
        top-K retrieval when few candidates are found (handles documents whose
        chunks lack explicit element_type/chunk_role markers).

        Args:
            top_k: How many structural candidates to retrieve (default 10000).
            source_filter: Optional source_file filter to scope to one document.

        Returns:
            List of chunk dicts with 'chunk_text', 'page_number',
            'source_file', 'chunk_id'.
        """
        # Structural roles that signal TOC/section/heading content.  The Qdrant
        # OR-filter matches a chunk when its element_type OR chunk_role is one of
        # these — identical to the former legacy "$or" filter query.
        element_types = [
            "heading",
            "toc_entry",
            "body",
            "paragraph",
            "title",
            "section",
            "header",
        ]
        chunk_roles = [
            "body",
            "caption",
            "navigation",
            "heading",
            "toc_entry",
            "title",
            "section",
            "header",
        ]
        storage = self._searcher.storage
        try:
            result = list(
                storage.find_structural_chunks(
                    element_types=element_types,
                    chunk_roles=chunk_roles,
                    source_prefix=source_filter,
                    limit=10000,
                )
            )
            if len(result) < 5:
                # Fall back to ALL chunks for the source (or all chunks when no
                # source_filter given), ordered by page and limited to top_k —
                # preserves the former legacy fallback query.
                result = list(
                    storage.find_structural_chunks(
                        source_prefix=source_filter,
                        limit=top_k,
                    )
                )
        except Exception:  # storage unavailable → no structure to probe
            logger.debug("Structure probing failed", exc_info=True)
            return []
        return [dict(c) for c in result]

    def _generic_one_shot(
        self,
        query: str,
        top_k: int,
        show_sources: bool,
        source_filter: str | None = None,
    ) -> dict[str, Any]:
        """Fallback one-shot retrieval when document structure probing fails."""
        chunks = self._searcher.search(
            query,
            top_k=top_k,
            source_filter=source_filter,
        )
        if not self._has_relevant_chunks(chunks):
            return {"answer": self._handle_no_results(query), "query": query}
        context = self._format_context(chunks)
        prompt = self._build_prompt(query, context)

        # Summary overviews reproduce figures exactly: reinforce it calmly (one
        # figure, then move on -- the anti-spiral phrasing), then vet below.
        intent = self._intent_parser.parse(query).intent
        is_summary = intent in (
            QueryIntent.CHAPTER_ENUMERATE,
            QueryIntent.SECTION_ENUMERATE,
            QueryIntent.BROAD_COVERAGE,
        )
        if is_summary:
            prompt += (
                "\n\nYou are summarizing source material. Quote figures (percentages, "
                "counts, years, metrics, returns) EXACTLY as stated in the retrieved "
                "context; never invent, estimate, round, or 'correct' a value the "
                "source does not state. This rule applies to prose statistics only -- "
                "do not fixate on reproducing code details or function arguments "
                "(e.g. list(range(...))) verbatim. State each figure once, "
                "confidently, and move on."
            )

        # Summary queries generate non-streaming, are vetted (grounded, and a
        # spiral/fallback/leak regenerated deterministically), then emitted once --
        # so raw drafting is never shown and a reasoning spiral can never surface
        # in the terminal. Other queries keep live streaming.
        if is_summary:
            answer = self._vet_answer(self._generate(prompt), prompt, context)
            if self._on_chunk and answer:
                self._on_chunk(answer, None)
        else:
            answer, streamed = self._stream_generate(prompt)
            if not streamed and self._on_chunk and answer:
                self._on_chunk(answer, None)
            answer = self._vet_answer(answer, prompt, context)

        result: dict[str, Any] = {"answer": answer, "query": query}
        if show_sources:
            result["sources"] = chunks
        return result

    def _vet_answer(self, text: str, prompt: str, context: str) -> str:
        """Ground figures to the source and regenerate deterministically if broken.

        Drops figures the source never stated, and when the text is empty, is the
        reasoning-budget fallback (the model spiraled before writing content), or
        leaks chain-of-thought self-talk, re-generates at low temperature for a
        clean, deterministic result instead of shipping a dead end.
        """
        answer = _prune_implausible_metric_figures(text)
        answer = _ground_figures(answer, context)
        if (
            not answer.strip()
            or answer.strip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX)
            or _contains_reasoning_leak(answer.lower())
        ):
            clean = self._generate_guarded(prompt, temperature=0.1)
            if clean:
                answer = _ground_figures(
                    _prune_implausible_metric_figures(clean), context
                )
        # A spiral that even the low-temperature retry could not recover is a dead
        # end -- return empty so callers fall back to a useful default (e.g. the
        # chapter roster) instead of surfacing the "I got stuck" fallback.
        if answer.strip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX):
            return ""
        return answer


class _FallbackMixin(_RAGPipelineState):
    """No-results fallback, grounded re-retrieval, and relevance helpers."""

    def _contextual_search(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
    ) -> list[dict[str, Any]] | None:
        """Check whether *query* is a grounded follow-up and run the sync search.

        Only attempts retrieval when the query references an entity from the
        conversation (a genuine follow-up). Returns the retrieved chunks when
        relevant, or ``None`` when the query is not a follow-up, nothing relevant
        is retrieved, or the search fails — so the caller can fall through to the
        knowledge fallback.
        """
        terms = self._extract_contextual_terms(conversation_history)
        if not terms or not self._query_references_context(query, terms):
            return None
        contextual_query = self._build_contextual_search_query(
            query, conversation_history
        )
        if not contextual_query.strip():
            return None
        try:
            chunks = self._searcher.search(contextual_query, top_k=top_k)
        except Exception as exc:
            logger.warning(
                "Contextual re-retrieval failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not self._has_relevant_chunks(chunks):
            return None
        return chunks

    async def _contextual_search_async(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
    ) -> list[dict[str, Any]] | None:
        """Async variant of :meth:`_contextual_search` (uses ``search_async``)."""
        terms = self._extract_contextual_terms(conversation_history)
        if not terms or not self._query_references_context(query, terms):
            return None
        contextual_query = self._build_contextual_search_query(
            query, conversation_history
        )
        if not contextual_query.strip():
            return None
        try:
            if hasattr(self._searcher, "search_async"):
                chunks = await self._searcher.search_async(
                    contextual_query, top_k=top_k
                )
            else:
                chunks = self._searcher.search(contextual_query, top_k=top_k)
        except Exception as exc:
            logger.warning(
                "Contextual re-retrieval failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not self._has_relevant_chunks(chunks):
            return None
        return chunks

    def _generate(self, prompt: str) -> str:
        """Run the LLM synchronously with the pipeline's temperature/max_tokens."""
        return self._llm_provider.generate(
            prompt=prompt,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )

    async def _agenerate(self, prompt: str) -> str:
        """Run the LLM asynchronously (falls back to the sync ``generate``)."""
        if hasattr(self._llm_provider, "agenerate"):
            return await self._llm_provider.agenerate(
                prompt=prompt,
                temperature=self._config.llm_temperature,
                max_tokens=self._config.llm_max_tokens,
            )
        return self._llm_provider.generate(
            prompt=prompt,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )

    def _stream_generate(self, prompt: str, prefix: str = "") -> tuple[str, bool]:
        """Generate a response, streaming through ``_on_chunk`` when possible.

        When streaming is enabled, the provider supports ``stream_chat`` and an
        ``_on_chunk`` callback is registered, ``prefix`` (if any) is emitted
        first and the answer is forwarded token by token. Otherwise falls back
        to the synchronous ``_generate``.

        Returns:
            Tuple of ``(answer, streamed)`` where ``streamed`` indicates the
            output was already pushed through ``_on_chunk`` and the caller must
            not re-emit it.
        """
        can_stream = (
            self._config.streaming_enabled
            and self._on_chunk is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        if not can_stream:
            return self._generate(prompt), False
        if prefix and self._on_chunk:
            self._on_chunk(prefix, None)
        messages = [{"role": "user", "content": prompt}]
        accumulated: list[str] = []

        def on_chunk(content: str, _reasoning: str | None) -> None:
            if content:
                accumulated.append(content)
            if self._on_chunk and (content or _reasoning):
                self._on_chunk(content, _reasoning)

        self._llm_provider.stream_chat(
            messages=messages,
            on_chunk=on_chunk,
            temperature=self._config.llm_temperature,
            max_tokens=self._config.llm_max_tokens,
        )
        return "".join(accumulated), True

    def _is_plausible_summary(self, text: str) -> bool:
        """Detect degenerate/token-soup output (repetitive or low-diversity text).

        Mirrors ``summarizer.Summarizer._is_plausible_summary`` so the RAG chat
        path applies the same guard against context-overflow degeneration that
        the dedicated summariser uses. A genuinely useful answer is non-trivial
        in length and lexically varied; repetitive or single-token-dominated
        output signals that the model ran out of budget and corrupted.
        """
        if not text or len(text.strip()) < 40:
            return False
        if _contains_reasoning_leak(text.lower()):
            return False
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())
        if not tokens:
            return False
        counts = Counter(tokens)
        most_common_frac = counts.most_common(1)[0][1] / len(tokens)
        if most_common_frac > 0.4:
            return False
        unique_frac = len(counts) / len(tokens)
        return unique_frac >= 0.2

    @staticmethod
    def _trim_rehashed_tail(text: str) -> str:
        """Drop a trailing re-statement that adds almost no new content.

        When the model emits the same material twice (a second, re-worded pass
        over the same topics), keep only the first pass.  A trailing run is
        treated as redundant when it reuses the earlier coverage without
        introducing new material: either its content words (excluding function
        words) are almost all already covered, or it re-states the same
        proper-noun/technical entities of the preceding text and adds (at most)
        none that are new.  A genuinely progressive summary that adds new topics
        is never cut.
        """
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        if len(sentences) < 6:
            return text

        def _terms(piece: str) -> list[str]:
            return [
                w
                for w in re.findall(r"[A-Za-z0-9']+", piece.lower())
                if w not in _FUNCTION_WORDS
            ]

        def _entities(piece: str) -> set[str]:
            # Reliable entities: mid-sentence proper nouns ("LeNet5", "AlexNet")
            # and any technical identifier with a digit ("VGG16", "2012").
            # Sentence-initial capitals ("Here", "Chapter") are not proper nouns.
            ents: set[str] = set()
            for m in re.finditer(r"\b[A-Z][A-Za-z0-9]*\b", piece):
                prefix = piece[: m.start()].rstrip()
                at_sentence_start = (
                    prefix == ""
                    or prefix.endswith((".", "!", "?"))
                    or prefix.endswith("\n")
                )
                token = m.group(0)
                if (not at_sentence_start) or any(c.isdigit() for c in token):
                    ents.add(token.lower())
            for m in re.finditer(r"[A-Za-z0-9]*\d[A-Za-z0-9]*", piece):
                ents.add(m.group(0).lower())
            return ents

        for start in range(len(sentences) // 2, len(sentences) - 1):
            if len(sentences) - start < 3:
                break
            head = set(_terms(" ".join(sentences[:start])))
            rest = _terms(" ".join(sentences[start:]))
            if not rest:
                continue
            novel = sum(1 for w in rest if w not in head) / len(rest)
            if novel < 0.20:
                return " ".join(sentences[:start]).strip()
            head_entities = _entities(" ".join(sentences[:start]))
            tail_entities = _entities(" ".join(sentences[start:]))
            if not tail_entities:
                continue
            overlap = len(tail_entities & head_entities) / len(tail_entities)
            new_entities = tail_entities - head_entities
            if overlap >= 0.7 and len(new_entities) <= 1:
                return " ".join(sentences[:start]).strip()
        return text

    def _generate_guarded(
        self,
        prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate a chat answer, rerunning once if the output looks degenerate.

        Option C (fail-closed + gibberish guard): if the first response fails
        the plausibility check, retry at a low temperature. If the retry is
        still implausible, return an empty string so the caller can fall back
        to a cleaner default rather than surfacing token-soup to the user.

        *temperature* / *max_tokens* override the default sampling parameters for
        the first call; the retry always uses temperature 0.1.
        """
        temp = temperature if temperature is not None else self._config.llm_temperature
        tokens = max_tokens if max_tokens is not None else self._config.llm_max_tokens
        text = self._llm_provider.generate(
            prompt=prompt,
            temperature=temp,
            max_tokens=tokens,
        )
        if self._is_plausible_summary(text):
            return text
        logger.warning(
            "RAG output failed plausibility check; retrying at low temperature"
        )
        text = self._llm_provider.generate(
            prompt=prompt,
            temperature=0.1,
            max_tokens=tokens,
        )
        if self._is_plausible_summary(text):
            return text
        logger.error("RAG output still implausible; returning empty")
        return ""

    def _generate_multi_chapter_summary(
        self,
        chapter_keys: list[int],
        chapter_buckets: dict[int, list[dict[str, Any]]],
        ch_titles: dict[int, str],
    ) -> str:
        """Produce a chapter-by-chapter overview via bounded windows per chapter.

        Chapters whose bucket is empty (page-range detection found no body text
        in their range) are still listed, with an explicit placeholder note, so
        a partial overview is visible to the reader instead of silently
        omitting chapters.
        """
        all_parts: list[str] = []
        for ch_num in chapter_keys:
            bucket = chapter_buckets.get(ch_num)
            title = ch_titles.get(ch_num, "")
            heading = f"Chapter {ch_num}" + (f" — {title}" if title else "")
            if not bucket:
                # An empty bucket means the chapter's page range contained no
                # body chunks (usually a mis-pinned start page).  Emit an
                # explicit placeholder: silently omitting chapters made a
                # partial overview look complete.
                note = (
                    "No document content was retrieved for this chapter "
                    "(its detected page range contains no body text), so no "
                    "summary could be generated."
                )
                if self._on_chunk:
                    # The returned text joins blocks with "\n\n"; the live
                    # stream needs its own separators or chapters glue together.
                    self._on_chunk(
                        (f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n")
                        + note,
                        None,
                    )
                all_parts.append(f"{heading}\n\n{note}")
                continue
            if self._on_chunk:
                # The returned text joins blocks with "\n\n"; the live stream
                # needs its own separators or consecutive chapters glue together.
                self._on_chunk(
                    f"{heading}\n\n" if not all_parts else f"\n\n{heading}\n\n",
                    None,
                )
            instruction = (
                f"Provide a brief, focused summary of {heading} using ONLY the "
                "document content below. 2-4 sentences. Never add information from "
                "outside this document or from prior knowledge. Quote any numbers, "
                "years, statistics, and metrics EXACTLY as they appear in the "
                "content below; never invent, estimate, round, or 'correct' a "
                "figure the source does not state -- if a specific number is not "
                "clearly present, omit it rather than guessing. Do not hedge, "
                "second-guess, or correct figures, and do not reproduce code "
                "details or function arguments (e.g. list(range(...))) verbatim."
            )
            summary = self._summarize_bounded(
                heading=heading,
                windows=self._split_bounded(bucket),
                instruction=instruction,
            )
            if summary.strip():
                all_parts.append(f"{heading}\n\n{summary}")
        return "\n\n".join(all_parts)

    def _generate_single_chapter_summary(
        self,
        chunks: list[dict[str, Any]],
        chapter_num: int | str,
        chapter_title: str,
        *,
        foreign_titles: list[str] | None = None,
    ) -> str:
        """Produce a comprehensive chapter overview via bounded windows.

        The chapter is split into small, character-bounded windows, each is
        condensed into a terse internally-held digest grounded to its own
        source (map), and one final streamed call writes the whole overview
        from the digests in a single voice (reduce) -- so the instruction's
        length bound applies once to the chapter, not once per window. The
        streaming guards (leak scrubbing, dead-stream continuation,
        low-temperature retry) apply to the reduce call; a window whose digest
        is unusable is skipped, never surfaced.
        """
        chunks = self._filter_chunks_to_chapter(
            chunks, chapter_num, foreign_titles=foreign_titles
        )
        windows = self._split_bounded(chunks)
        if not windows:
            return ""
        heading = f"Chapter {chapter_num} (overview)"
        instruction = (
            f"Summarize the following portion of chapter {chapter_num} "
            f"({chapter_title}). Use ONLY the document content below. Write a "
            "flowing prose overview in six to ten short paragraphs, one "
            "topic per paragraph, then STOP -- do "
            "not fill extra space or restate. Cover the "
            "main topics, key concepts, and supporting details. Do "
            "NOT use headings, sub-headers, or bullet lists. Do NOT open with "
            "meta-framing such as 'This portion covers...' -- begin directly "
            "with the substance. Quote any numbers, years, statistics, and "
            "metrics EXACTLY as they appear in the content below; never invent, "
            "estimate, round, or 'correct' a figure the source does not state "
            "-- if a specific number is not clearly present, omit it rather "
            "than guessing. State each figure once and move on; do not hedge, "
            "second-guess, or correct figures. Cover each study's experimental "
            "setup -- data universe, feature construction and selection, and "
            "training or evaluation windows -- and any benchmark comparison "
            "the content draws, not only its headline results. When the "
            "content states conflicting values for the same fact (for example "
            "different years in narrative and citations), report the "
            "narrative value without editorializing about the discrepancy. "
            "When the content reports values from separate experiments or "
            "evaluation settings, give each value its own sentence tied to "
            "its own setup rather than combining different runs into one "
            "sentence that reads as self-contradiction. "
            "Do not reproduce code details or "
            "function arguments (e.g. list(range(...))) verbatim. Do not print "
            "any notes, disclaimers, or headings such as 'Note', 'Important', or "
            "'Not in this chapter'. Write the overview exactly once: treat "
            "your first complete draft as final -- do not produce a "
            "preliminary draft and then a second, tightened version of the "
            "same overview, and do not re-verify the quoted figures after "
            "drafting. Keep internal planning to brief selection and "
            "structure decisions only. If some "
            "content below does not belong to "
            "this chapter, summarize only the content that does and never add "
            "general knowledge or commentary about other chapters."
        )
        if self._on_chunk:
            self._on_chunk(f"{heading}:\n\n", None)
        body = self._summarize_bounded(
            heading=heading, windows=windows, instruction=instruction
        )
        if not body.strip():
            return ""
        return f"{heading}:\n\n{body}"

    def _split_bounded(
        self,
        chunks: list[dict[str, Any]],
        *,
        max_chars: int | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Split *chunks* into contiguous windows of bounded source characters.

        Input is sorted into numerical page order (stable, so within-page reading
        order is preserved) before windowing so the emitted summary windows follow
        the document's page sequence rather than retrieval/interleaving order.
        Boundaries are then aligned to sentence ends via
        :meth:`_align_window_boundaries` so no window's source stops mid-sentence.
        """
        ordered = sorted(
            chunks,
            key=lambda c: c.get("page_number", c.get("page", 0)) or 0,
        )
        budget = max_chars or _SUMMARY_WINDOW_CHARS
        windows: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        current_chars = 0
        for chunk in ordered:
            text = chunk.get("chunk_text", chunk.get("text", ""))
            if text and current and current_chars + len(text) > budget:
                windows.append(current)
                current = []
                current_chars = 0
            current.append(chunk)
            current_chars += len(text)
        if current:
            windows.append(current)
        return self._align_window_boundaries(windows)

    @staticmethod
    def _align_window_boundaries(
        windows: list[list[dict[str, Any]]],
    ) -> list[list[dict[str, Any]]]:
        """Move the mid-sentence tail of each window to the next window's front.

        Ingest chunking cuts mid-sentence, and a window whose source ends
        mid-sentence makes the summary mirror the truncation: the live stream
        ends mid-word and :func:`_trim_to_sentence_end` later discards the
        tail as wasted generation.  The fragment after the last sentence
        terminal of a window is therefore prepended to the next window.  A
        terminal-free trailing chunk is left alone: carrying whole chunks
        forward could chain-merge every window into one.  Payload dicts are
        copied on modification so the caller's chunks are never mutated.
        """
        for idx in range(len(windows) - 1):
            window = windows[idx]
            if not window:
                continue
            tail = window[-1]
            key = "chunk_text" if "chunk_text" in tail else "text"
            if key not in tail:
                continue
            text = str(tail[key])
            ends = [m.end() for m in re.finditer(r"[.!?][\"'\u201d\u2019]?\s", text)]
            if not ends:
                continue
            remainder = text[ends[-1] :].strip()
            if not remainder:
                continue
            nxt = windows[idx + 1][0]
            nkey = "chunk_text" if "chunk_text" in nxt else "text"
            if nkey not in nxt:
                continue
            trimmed = dict(tail)
            trimmed[key] = text[: ends[-1]].rstrip()
            windows[idx] = [*window[:-1], trimmed]
            merged = dict(nxt)
            merged[nkey] = f"{remainder} {str(nxt[nkey]).lstrip()}"
            windows[idx + 1][0] = merged
        return windows

    def _summarize_bounded(
        self,
        *,
        heading: str,
        windows: list[list[dict[str, Any]]],
        instruction: str,
    ) -> str:
        """Summarize *windows* in one streamed call over the complete source.

        PRIMARY (single pass): when the formatted source fits within
        ``_SINGLE_PASS_MAX_CHARS``, one LLM call receives the whole chapter and
        writes the overview.  This is both cheaper and more faithful than any
        staged pipeline: the per-call reasoning/planning overhead is paid once
        instead of once per window, no intermediate digest can drop detail, and
        there are no per-window seams to recover from.

        FALLBACK (map-reduce, oversized sources only): each window is condensed
        into a terse internal digest (map -- digest content never streams), and
        one final streamed call writes the overview from the digests (reduce).
        A window whose digest is unusable is skipped, never surfaced.
        """
        contexts: list[str] = []
        for window in windows:
            ctx = self._format_context(
                window, max_chars=self._config.rag_max_context_chars
            )
            if ctx.strip():
                contexts.append(ctx)
        if not contexts:
            return ""
        if sum(len(ctx) for ctx in contexts) <= _SINGLE_PASS_MAX_CHARS:
            return self._reduce_digest_overview(
                heading,
                contexts,
                instruction,
                parts_are_digests=False,
                numbered_parts=False,
            )
        if len(windows) > _MAX_MAP_REDUCE_WINDOWS:
            logger.warning(
                "summary source exceeds the single-pass budget and has %d "
                "windows; capping map pass at %d",
                len(windows),
                _MAX_MAP_REDUCE_WINDOWS,
            )
            windows = windows[:_MAX_MAP_REDUCE_WINDOWS]
            contexts = contexts[:_MAX_MAP_REDUCE_WINDOWS]
        digests: list[str] = []
        total = len(contexts)
        for index, ctx in enumerate(contexts, 1):
            digest = self._map_window_digest(heading, ctx, index, total)
            if digest:
                digests.append(digest)
        if not digests:
            return ""
        return self._reduce_digest_overview(
            heading, digests, instruction, parts_are_digests=True
        )

    def _map_window_digest(
        self,
        heading: str,
        ctx: str,
        index: int,
        total: int,
    ) -> str:
        """Condense one source window into an internal, grounded digest.

        The digest is deliberately small so the reduce pass sees a compact,
        faithful skeleton of the chapter instead of a stack of full-window
        essays -- that is what finally makes the overview's deterministic
        length ceiling effective.  Its size is shaped by "terse digest
        paragraph" phrasing rather than a numeric word bound, which would
        only trigger word-counting loops in the model's reasoning.
        Reasoning streams (visible activity) but content stays
        internal. On a stream failure the digest is regenerated once via
        :meth:`_generate_guarded`; an unusable digest is skipped with a warning
        so one bad window cannot stall the whole overview.
        """
        prompt = self._build_prompt(
            (
                f"You are preparing an internal digest of Part {index} of "
                f"{total} of {heading}.\n\nWrite a terse digest paragraph that "
                "records, in source order: the topics the part "
                "covers; every figure or table it presents, quoted with its "
                'exact label (e.g. "Figure 18.5", "Table 18.2") and subject; '
                "and the key numeric results, copied exactly from the source. "
                "Plain prose only -- no headers, bullets, transitions, or "
                "commentary. Never mention page numbers. State each figure "
                "once. Never add anything the source does not contain."
            ),
            ctx,
        )
        can_stream = self._config.streaming_enabled and hasattr(
            self._llm_provider, "stream_chat"
        )
        digest = ""
        if can_stream:
            pieces: list[str] = []
            digest_start = time.monotonic()

            def _fwd_map(chunk: str, reasoning: str | None) -> None:
                if time.monotonic() - digest_start > _WINDOW_MAX_SECONDS:
                    raise TimeoutError("map digest exceeded time budget")
                # Reasoning streams so the user sees live activity; the digest
                # content itself must never reach the screen.
                if reasoning and self._on_chunk:
                    self._on_chunk("", reasoning)
                if chunk:
                    pieces.append(chunk)

            try:
                returned = self._llm_provider.stream_chat(
                    messages=[{"role": "user", "content": prompt}],
                    on_chunk=_fwd_map,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_MAP_DIGEST_MAX_TOKENS,
                )
                digest = "".join(pieces) or (returned or "")
            except Exception as e:
                logger.warning(
                    "map digest stream failed (%s: %s); regenerating",
                    type(e).__name__,
                    e,
                )
        if not digest.strip():
            try:
                digest = self._generate_guarded(
                    prompt,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_MAP_DIGEST_MAX_TOKENS,
                )
            except Exception as e:
                logger.warning(
                    "map digest generation failed (%s: %s); skipping part %d/%d",
                    type(e).__name__,
                    e,
                    index,
                    total,
                )
                return ""
        if not digest.strip():
            return ""
        digest = _strip_numeric_self_correction(_scrub_self_correction(digest))
        digest = _prune_implausible_metric_figures(digest)
        digest = _ground_figures(digest, ctx)
        digest = _trim_to_sentence_end(digest)
        if not digest.strip() or not self._is_plausible_summary(digest):
            logger.warning("map digest %d/%d unusable; skipping", index, total)
            return ""
        return digest

    def _reduce_digest_overview(
        self,
        heading: str,
        parts: list[str],
        instruction: str,
        *,
        parts_are_digests: bool,
        numbered_parts: bool = True,
    ) -> str:
        """Write the final overview from *parts* in one streamed LLM call.

        Serves both summary paths: the single-pass primary (raw source parts,
        ``numbered_parts=False``) and the map-reduce reduce stage (terse
        digests, numbered in reading order).  When the digest count exceeds
        ``_HIERARCHY_THRESHOLD``, the digests are first condensed into balanced
        groups so the reduce prompt stays readable.

        A single call is what gives the overview one voice, an effective
        length bound, and no per-window seams. All streaming guards apply here:
        withheld-tail leak scrubbing, dead-stream continuation, and the
        low-temperature retry. Two GLM failure modes that raise no exception
        are handled explicitly below: a normal return whose content was
        amputated mid-sentence by the server output cap, and a normal return
        with no content at all.
        """
        emit = self._on_chunk
        can_stream = (
            self._config.streaming_enabled
            and emit is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        grounding_context = "\n\n".join(parts)
        if parts_are_digests and len(parts) > _HIERARCHY_THRESHOLD:
            # Grounding keeps the raw digests (best figure fidelity); only the
            # reduce prompt switches to the condensed groups.
            parts = self._condense_digest_groups(heading, parts)
        if numbered_parts:
            joined = "\n\n".join(
                f"--- Part {i} ---\n{p}" for i, p in enumerate(parts, 1)
            )
        else:
            joined = "\n\n".join(parts)
        if parts_are_digests:
            framing = (
                "The document content below consists of terse digests of the "
                f"consecutive parts of {heading}, in reading order. Write the "
                "final overview as ONE coherent piece of prose that weaves the "
                "digests into a single narrative: cover every part in order "
                "with one consistent voice; never use per-part headers or "
                "'Part N' labels; never name a figure or table the digests do "
                "not contain, and when you do cite one, quote its label "
                "exactly as the digests give it; never mention page numbers; "
                "end on a complete statement."
            )
        else:
            framing = (
                f"The document content below covers {heading}. Write the final "
                "overview as ONE coherent piece of prose with one consistent "
                "voice: never name a figure or table the content does not "
                "contain, and when you do cite one, quote its label exactly "
                "as the content gives it; never mention page numbers; end on "
                "a complete statement."
            )
        prompt = instruction + "\n\n" + framing + "\n\n" + joined

        if not can_stream:
            try:
                text = self._generate_guarded(
                    prompt,
                    temperature=SUMMARY_TEMPERATURE,
                    max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
                )
            except Exception as e:
                logger.warning("summary reduce failed (%s: %s)", type(e).__name__, e)
                return ""
            final = self._finalize_overview(text, grounding_context)
            if not final.strip() or not self._is_plausible_summary(final):
                return ""
            if emit:
                # Non-streaming mode still surfaces the completed overview through
                # the callback so the chat shows progressive output.
                emit(f"\n\n{final}\n\n", None)
            return final

        pieces: list[str] = []
        reduce_start = time.monotonic()
        # Withhold a short tail of streamed content so a self-correction leak
        # is caught on the buffered text before it reaches the screen.
        hold: list[str] = [""]
        flushed = [0]

        def _emit_streamed(text: str) -> None:
            if text and emit:
                emit(text, None)

        def _flush_hold() -> None:
            # `flushed` must advance with the emission: the leak scrubber's
            # already-emitted-prefix comparison depends on it staying exact.
            if hold[0]:
                flushed[0] += len(hold[0])
                _emit_streamed(hold[0])
                hold[0] = ""

        def _fwd(chunk: str, reasoning: str | None) -> None:
            if time.monotonic() - reduce_start > _WINDOW_MAX_SECONDS:
                raise TimeoutError("summary reduce exceeded time budget")
            if reasoning and emit:
                emit("", reasoning)
            if not chunk:
                return
            pieces.append(chunk)
            hold[0] += chunk
            joined = "".join(pieces)
            if _is_stream_leak(joined.lower()):
                # A scrubbable leak confined to the withheld tail is cut out
                # and streaming continues; only a leak that would alter
                # already-emitted text (or resists scrubbing) aborts the
                # overview to the retry path.
                scrubbed = _scrub_self_correction(joined)
                if (
                    scrubbed != joined
                    and scrubbed[: flushed[0]] == joined[: flushed[0]]
                    and not _is_stream_leak(scrubbed.lower())
                ):
                    pieces.clear()
                    pieces.append(scrubbed)
                    hold[0] = scrubbed[flushed[0] :]
                    return
                raise _StreamLeakError()
            if len(hold[0]) > _STREAM_LEAK_HOLD:
                committed = hold[0][:-_STREAM_LEAK_HOLD]
                hold[0] = hold[0][-_STREAM_LEAK_HOLD:]
                _emit_streamed(committed)
                flushed[0] += len(committed)

        text = ""
        try:
            returned = self._llm_provider.stream_chat(
                messages=[{"role": "user", "content": prompt}],
                on_chunk=_fwd,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
            _flush_hold()
            text = "".join(pieces) or (returned or "")
            if text and not pieces:
                # A provider that returned the whole text without streaming
                # chunks: seed the buffer so a follow-up continuation extends
                # this draft instead of dropping it.
                pieces.append(text)
        except _StreamLeakError:
            # The overview leaked an inline self-correction into content:
            # regenerate rather than ship it. Pre-leak chunks may already be
            # on screen; the retry replaces the draft.
            text = ""
        except Exception as e:  # the stream died mid-flight; recover it
            logger.warning(
                "summary reduce stream aborted (%s: %s)", type(e).__name__, e
            )
            text = "".join(pieces)
            _flush_hold()
            if text.strip():
                # Idle-timeout stalls and provider drops kill long
                # reasoning-heavy generations mid-sentence; one streamed
                # continuation completes the draft so the overview is not
                # silently truncated.
                self._resume_summary(prompt, text, _fwd)
                _flush_hold()
                text = "".join(pieces)

        if not text.strip():
            # Covers both a stream that died before any content and the GLM
            # "normal" empty return (reasoning consumed the whole output
            # budget): one clean regeneration before the overview is abandoned.
            retry = self._low_temp_retry(
                prompt, True, heading, max_tokens=_SUMMARY_REDUCE_MAX_TOKENS
            )
            if retry is None:
                return ""
            # _fwd must operate on the adopted draft so a follow-up
            # continuation extends it instead of resurrecting dead pieces.
            pieces.clear()
            pieces.append(retry)
            hold[0] = ""
            flushed[0] = len(retry)
            text = retry

        if not _ends_on_sentence(text):
            # GLM-class servers cap thinking+content with one output budget and
            # can return "normally" with the content amputated mid-sentence --
            # no exception reaches the handler above. A streamed continuation
            # completes the draft so the overview does not end mid-word.
            self._resume_summary(prompt, text, _fwd)
            _flush_hold()
            text = "".join(pieces)

        return self._finalize_or_retry_overview(
            text,
            prompt=prompt,
            heading=heading,
            grounding_context=grounding_context,
        )

    def _condense_digest_groups(self, heading: str, digests: list[str]) -> list[str]:
        """Condense a large digest set into balanced groups for the reduce prompt.

        ``len(digests)`` is split into the fewest groups whose size stays within
        ``_HIERARCHY_GROUP_SIZE`` (balanced sizes, no singleton trailing group),
        and each group is merged into one terser digest by a non-streamed call.
        A group whose condensation fails or reads as garbage falls back to its
        raw digests, so a failed optimization call cannot lose coverage.
        """
        n = len(digests)
        n_groups = -(-n // _HIERARCHY_GROUP_SIZE)
        size = -(-n // n_groups)
        merged: list[str] = []
        for start in range(0, n, size):
            group = digests[start : start + size]
            condensed = self._condense_digest_group(heading, group)
            merged.append(condensed if condensed.strip() else "\n\n".join(group))
        return merged

    def _condense_digest_group(self, heading: str, group: list[str]) -> str:
        """Merge one group of digests into a single terser digest, or '' on failure."""
        prompt = self._build_prompt(
            (
                f"You are condensing intermediate digests of {heading}.\n\nThe "
                "digests below cover consecutive parts in reading order. Merge "
                "them into ONE terser digest that preserves, in source order: "
                "every topic; every figure or table label, quoted exactly as "
                "the digests give it; and every numeric result, copied exactly "
                "from the digests. Plain prose only -- no headers, bullets, or "
                "commentary. Never mention page numbers. Never add anything "
                "the digests do not contain."
            ),
            "\n\n".join(f"--- Digest {i} ---\n{d}" for i, d in enumerate(group, 1)),
        )
        try:
            condensed = self._generate_guarded(
                prompt,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning(
                "digest group condensation failed (%s: %s); passing raw digests",
                type(e).__name__,
                e,
            )
            return ""
        condensed = _strip_numeric_self_correction(_scrub_self_correction(condensed))
        condensed = _prune_implausible_metric_figures(condensed)
        condensed = _ground_figures(condensed, "\n\n".join(group))
        condensed = _trim_to_sentence_end(condensed)
        if not condensed.strip() or not self._is_plausible_summary(condensed):
            return ""
        return condensed

    def _finalize_or_retry_overview(
        self,
        text: str,
        *,
        prompt: str,
        heading: str,
        grounding_context: str,
    ) -> str:
        """Ground and trim the reduced overview, regenerating once if degenerate."""
        final = self._finalize_overview(text, grounding_context)
        if not final.strip():
            return ""
        if not self._is_plausible_summary(final):
            retry = self._low_temp_retry(
                prompt, True, heading, max_tokens=_SUMMARY_REDUCE_MAX_TOKENS
            )
            if retry is not None:
                final = self._finalize_overview(retry, grounding_context)
        return final

    @staticmethod
    def _finalize_overview(text: str, grounding_context: str) -> str:
        """Apply the deterministic post-passes to a reduced overview.

        Scrubbing, metric pruning, figure grounding against *grounding_context*
        (the digests, or the raw source for a single-pass overview), the
        deterministic word ceiling, and sentence-end trimming mean a leaked or
        fabricated figure still cannot ship and an overlong draft is cut at a
        sentence boundary rather than trusted to the model's own counting.
        """
        text = _strip_numeric_self_correction(_scrub_self_correction(text))
        text = _prune_implausible_metric_figures(text)
        text = _ground_figures(text, grounding_context)
        text = _trim_to_word_budget(text, _OVERVIEW_MAX_WORDS)
        return _trim_to_sentence_end(text)

    def _resume_summary(
        self,
        prompt: str,
        partial: str,
        on_chunk: Callable[[str, str | None], None],
    ) -> None:
        """Stream a continuation that completes an overview cut off mid-sentence.

        Provider drops, idle-timeout stalls, and the server-side output cap of
        reasoning models (thinking and content share one token budget, so
        content can be amputated with a normal, exception-free return) all
        truncate long generations mid-sentence; regenerating from scratch would
        repeat minutes of thinking, so the model is shown its own draft and
        asked to continue seamlessly. Chunks flow through the caller's
        ``on_chunk`` guard, so leak scrubbing, hold buffering, and the time
        budget keep applying. Failures are logged and swallowed: the caller
        keeps the partial draft.
        """
        resume_prompt = (
            prompt + "\n\nYour draft was cut off mid-sentence before it could "
            "finish. Draft so far:\n<draft>\n"
            + partial
            + "\n</draft>\nContinue seamlessly from that exact point: first "
            "complete the unfinished sentence, then finish the overview, "
            "ending on a complete statement. Output ONLY the continuation -- "
            "never repeat text already present in the draft."
        )
        try:
            self._llm_provider.stream_chat(
                messages=[{"role": "user", "content": resume_prompt}],
                on_chunk=on_chunk,
                temperature=SUMMARY_TEMPERATURE,
                max_tokens=_SUMMARY_REDUCE_MAX_TOKENS,
            )
        except Exception as e:
            logger.warning(
                "summary continuation failed (%s: %s); keeping partial",
                type(e).__name__,
                e,
            )

    @staticmethod
    def _detect_section_label(text: str, chapter_num: int | str) -> str | None:
        """Return the section key (e.g. ``"18.2"``) a chunk belongs to, if any.

        Only honours a section number that appears at a *heading* position (start
        of the chunk or start of a line), where true section headers live.  A
        line-start ``18.N`` is ignored when the preceding text is a
        figure/table/equation/listing reference (e.g. a wrapped "Figure [newline]
        18.2"), which would otherwise fabricate phantom sections from captions;
        such content folds into the chapter overview.
        """
        chapter_s = str(chapter_num)
        heading_re = re.compile(rf"(?:^|\n)\s*{re.escape(chapter_s)}\.(\d+)\b")
        ref_indicator = re.compile(
            r"(figure|table|equation|listing|eq\.?|page|p\.)\s*$",
            re.IGNORECASE,
        )
        for m in heading_re.finditer(text):
            if ref_indicator.search(text[: m.start()]):
                continue
            return f"{chapter_s}.{m.group(1)}"
        return None

    @staticmethod
    def _leading_section_chapter(text: str) -> str | None:
        """Return the chapter number of the first real numbered heading in *text*.

        Mirrors ``_detect_section_label``'s heading-position guard: only a section
        number at the start of the chunk or start of a line counts, and a
        line-start number that directly follows a figure/table/equation/listing
        reference (e.g. a wrapped "Figure [newline] 18.2") is ignored as a
        caption.  Unlike ``_detect_section_label`` this is chapter-agnostic, which
        lets us attribute a chunk to *whatever* chapter its section heading names.
        """
        heading_re = re.compile(r"(?:^|\n)\s*(\d+)\.\d+(?:\.\d+)?\b")
        ref_indicator = re.compile(
            r"(figure|table|equation|listing|eq\.?|page|p\.)\s*$",
            re.IGNORECASE,
        )
        for m in heading_re.finditer(text):
            if ref_indicator.search(text[: m.start()]):
                continue
            return m.group(1)
        return None

    @staticmethod
    def _filter_chunks_to_chapter(
        chunks: list[dict[str, Any]],
        chapter_num: int | str,
        foreign_titles: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Drop retrieved chunks that belong to a *later* chapter.

        ``final_chunks`` for a single-chapter target is collected by page range,
        and page-range boundaries are imperfect, so the next chapter's content
        can leak into the target chapter's bucket.  This filter removes each
        chunk whose numbered section heading belongs to another chapter or whose
        opening line names another chapter's title, and also drops every chunk
        on or after the first page that opens with an explicitly later "Chapter
        N" heading -- which clears the next chapter's body paragraphs that carry
        no section prefix of their own.
        """
        chapter_s = str(chapter_num)
        target_n = int(chapter_s) if str(chapter_s).isdigit() else None
        seen_foreign = {f.strip().lower() for f in (foreign_titles or []) if f.strip()}
        title_starts = [" ".join(t.split()[:4]) for t in seen_foreign]
        ch_open_re = re.compile(r"^(?:Chapter|Module|Lesson)\s+(\d+)\b", re.IGNORECASE)
        printed_page_re = re.compile(r"^\[\s*\d{1,4}\s*\]\s*")

        def _opens_heading_after(text: str) -> bool:
            if target_n is None:
                return False
            s = printed_page_re.sub("", text.lstrip(), count=1).lstrip()
            hm = ch_open_re.match(s)
            if hm and int(hm.group(1)) > target_n:
                return True
            first_line = (s.splitlines()[0] if s else "").strip()
            return (
                first_line.isdigit()
                and 1 <= int(first_line) <= 30
                and int(first_line) > target_n
            )

        def _opens_foreign_title(text: str) -> bool:
            if not title_starts:
                return False
            low = text.lstrip().lower()
            return any(low.startswith(t) for t in title_starts)

        def _page(c: dict[str, Any]) -> int:
            return int(c.get("page_number", c.get("page", 0)) or 0)

        anchor = min(
            (
                _page(c)
                for c in chunks
                if _opens_heading_after(c.get("chunk_text", c.get("text", "")))
            ),
            default=None,
        )
        cutoff = anchor if (anchor is not None and anchor > 1) else None
        kept: list[dict[str, Any]] = []
        for c in chunks:
            text = c.get("chunk_text", c.get("text", ""))
            lead = _FallbackMixin._leading_section_chapter(text)
            if lead is not None and lead != chapter_s:
                continue
            if _opens_foreign_title(text):
                continue
            if cutoff is not None and _page(c) >= cutoff:
                continue
            kept.append(c)
        return kept

    def _map_reduce_stream(
        self,
        items: list[tuple[str, str]],
        *,
        temperature: float | None = None,
    ) -> str:
        """Stream map-reduce window generations in order and concatenate.

        *items* is a list of ``(heading, prompt)`` pairs.  Fan-out is guarded to
        ``_MAX_MAP_REDUCE_WINDOWS`` — a generous safety ceiling against a
        pathologically large source, not a normal truncation limit — so all
        legitimate windows are processed in full.

        Each window runs through :meth:`_generate_window_guarded`, which streams
        its ``heading``, reasoning, and content live to ``_on_chunk`` so the
        interactive chat progresses in real time.  Content is validated for
        plausibility as it flows (a runaway tail aborts the stream) and once more
        on completion — a degenerate window is retried at a low temperature or
        skipped, never surfaced in the final answer.

        ``temperature`` optionally overrides the sampling temperature for every
        window (used by the summary path to keep figure-heavy output faithful).

        Returns the concatenated answer (falling back to it when no content was
        streamed at all).
        """
        if not items:
            return ""
        capped = items[:_MAX_MAP_REDUCE_WINDOWS]
        parts: list[tuple[str, str]] = []
        for heading, prompt in capped:
            summary = self._trim_rehashed_tail(
                self._generate_window_guarded(prompt, heading, temperature=temperature)
            )
            if summary:
                parts.append((heading, summary))
        return "\n\n".join(f"{h}\n{s}" for h, s in parts)

    def _generate_window_guarded(
        self,
        prompt: str,
        heading: str,
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Generate one map-reduce window, streaming reasoning and content live.

        In a streaming-enabled session, the heading is emitted first and then
        reasoning + content tokens are forwarded to ``_on_chunk`` as they arrive,
        so the chat streams in real time instead of buffering a whole window.
        Sampling uses ``llm_temperature`` / ``llm_max_tokens`` (unless overridden).

        A mid-stream flood guard detects derailment as it accumulates and
        **aborts the stream immediately**, so a runaway window cannot stream an
        unbounded number of tokens.  Because a derailed window's clean prefix is
        truncated (it ends at the degradation point), the window is **retried at
        temperature 0.1** so a complete, stable summary replaces the partial —
        otherwise a chapter that degrades midway would silently lose every
        section that followed.  When the retried window still degenerates, it is
        skipped, so token-soup never reaches the user.

        Returns the validated answer text (or an empty string when skipped), and
        streams the ``heading`` + answer through ``_on_chunk`` on success.
        """
        temp = temperature if temperature is not None else self._config.llm_temperature
        tokens = max_tokens if max_tokens is not None else self._config.llm_max_tokens

        can_stream = (
            self._config.streaming_enabled
            and self._on_chunk is not None
            and hasattr(self._llm_provider, "stream_chat")
        )
        if not can_stream:
            answer = self._generate_guarded(prompt, temperature=temp, max_tokens=tokens)
            if answer and self._on_chunk:
                self._on_chunk(f"{heading}\n\n{answer}\n\n", None)
            return answer

        buffered: list[str] = []  # everything streamed (incl. any derailed tail)
        clean: list[str] = []  # longest prefix that stayed acceptable as it streamed
        reason_log: list[str] = []  # accumulated chain-of-thought for spiral detection
        heading_shown = False
        derailed = False

        def on_chunk(content: str, reasoning: str | None) -> None:
            nonlocal heading_shown
            if reasoning:
                reason_log.append(reasoning)
                if self._is_reasoning_spiral("".join(reason_log)):
                    raise _StreamAbortError()
                # Reasoning is consumed only for spiral detection -- it is never
                # forwarded to the terminal, so a chain-of-thought spiral or the
                # raw thinking block is not shown to the user.
            if content:
                buffered.append(content)
                joined = "".join(buffered)
                # Flush before streaming a chunk that would trip the flood guard,
                # so a derailed tail is never surfaced, and never reaches `clean`.
                if self._is_flooding(joined):
                    raise _StreamAbortError()
                # A figure-verification leak arriving as content (e.g. "?? (wait,
                # the text says ...)") precedes a stall -- abort and clean-retry.
                if _is_content_self_correction(joined.lower()):
                    raise _StreamAbortError()
                # Never surface the provider's "I got stuck in repetitive
                # reasoning" dead-end; treat it as a derail and relax-retry.
                if joined.lstrip().startswith(_REASONING_BUDGET_FALLBACK_PREFIX):
                    raise _StreamAbortError()
                if self._on_chunk:
                    if not heading_shown:
                        self._on_chunk(f"{heading}\n\n", None)
                        heading_shown = True
                    self._on_chunk(content, None)
                clean.append(content)

        messages = [{"role": "user", "content": prompt}]
        try:
            self._llm_provider.stream_chat(
                messages=messages,
                on_chunk=on_chunk,
                temperature=temp,
                max_tokens=tokens,
            )
        except _StreamAbortError:
            derailed = True
        except (ServiceUnavailableError, RuntimeError) as e:
            # A stalled or errored stream (provider idle-timeout, API error, read
            # failure) must not surface as a hard failure after a long silence;
            # treat it like a derail so the window is regenerated deterministically.
            logger.warning(
                "RAG window stream degraded (%s: %s); regenerating at low temperature",
                type(e).__name__,
                e,
            )
            derailed = True

        # A window that derailed mid-stream is incomplete: the clean prefix ends
        # at the degradation point, dropping whatever the chapter covered after it.
        # Retry at low temperature to salvage a complete, stable summary instead of
        # surfacing a chapter cut off mid-way.  Only when the retry is also unusable
        # do we fall back to the clean prefix (or skip).
        if derailed:
            logger.warning(
                "RAG window degraded mid-stream; retrying at low temperature for a complete summary"
            )
            retry = self._low_temp_retry(
                prompt, heading_shown, heading, max_tokens=tokens
            )
            if retry is not None:
                return retry

        # Word-salad is judged on this COMPLETED window — reliable, unlike a
        # mid-stream partial — so a legitimate dense summary passes here, while a
        # genuine whole-window salad falls through to a low-temperature retry below.
        text = "".join(clean)
        if self._is_plausible_summary(text) and not self._looks_derailed(text):
            return text
        logger.warning(
            "RAG window derailed before producing usable content; retrying at low temperature"
        )
        retry = self._low_temp_retry(
            prompt, heading_shown, heading, max_tokens=_RETRY_MAX_TOKENS
        )
        if retry is not None:
            return retry
        logger.warning("RAG window output still implausible; skipping section")
        return ""

    def _low_temp_retry(
        self,
        prompt: str,
        heading_shown: bool,
        heading: str,
        *,
        max_tokens: int,
    ) -> str | None:
        """Regenerate a window at temperature 0.1 and return it if acceptable.

        Used when a window degrades (derails mid-stream or is implausible as a
        whole) so the caller can surface a complete, stable summary rather than
        a truncated or degenerate one.  Returns ``None`` when the retry is also
        unacceptable, so the caller decides the fallback.
        """
        # Attempt 1 asks for exact source figures, which the model can obsess over
        # and burn its reasoning budget on; relax that pressure on the retry so it
        # can actually complete a summary instead of looping again.
        retry_prompt = (
            prompt
            + "\n\nYour previous attempt became stuck re-verifying exact figures. "
            "Write a complete, confident overview now: state key numbers once, "
            "approximate values are acceptable. Do not try to confirm, re-derive, "
            "or second-guess any value -- present a flowing summary and finish."
        )
        try:
            retry = self._llm_provider.generate(
                prompt=retry_prompt,
                temperature=0.1,
                max_tokens=max_tokens,
            )
        except Exception as e:
            # Best-effort by contract: a provider timeout or transport error
            # here must never crash the surrounding summary loop.
            logger.warning(
                "RAG window retry failed (%s: %s); skipping window",
                type(e).__name__,
                e,
            )
            return None
        if _is_stream_leak(retry.lower()):
            logger.warning(
                "RAG window retry still leaked a self-correction; skipping window"
            )
            return None
        if not self._is_acceptable(retry):
            logger.warning("RAG window retry unacceptable; skipping window")
            return None
        if self._on_chunk:
            if heading_shown:
                self._on_chunk(f"\n\n{retry}\n\n", None)
            else:
                self._on_chunk(f"{heading}\n\n{retry}\n\n", None)
        return retry

    def _is_acceptable(self, text: str) -> bool:
        """Return True when a window answer is safe to surface.

        An answer is acceptable only if it is plausible (non-repetitive, adequately
        long) *and* has not derailed into agrammatic word-salad — the high-diversity
        degeneration that repetition-based checks alone miss.
        """
        return self._is_plausible_summary(text) and not self._looks_derailed(text)

    def _is_flooding(self, text: str) -> bool:
        """Return True once a live-streaming window degenerates into repetition.

        A stream must be aborted only on a genuine runaway tail — repetitive or
        single-token-dominated output (:meth:`_is_plausible_summary`).  It must
        NOT consult :meth:`_looks_derailed`: that word-salad diversity heuristic
        false-positives on the high-diversity partial buffer of a *legitimate*
        dense technical summary (a list of model/technique names spiking
        type-token ratio), so using it here truncates good summaries mid-sentence.
        Word-salad is judged on a whole completed window (the low-temperature
        retry path), never as a streaming abort signal.

        A short buffer is never treated as flooding so the first sentence of a
        normal summary always streams.
        """
        if len(text.strip()) < _STREAM_FLOOD_MIN_CHARS:
            return False
        return not self._is_plausible_summary(text)

    def _is_reasoning_spiral(self, reasoning: str) -> bool:
        """Return True when chain-of-thought reasoning has degenerated.

        Reasoning that derails (the "thinking spiral" that can also leak into the
        final answer) reveals itself by dense, repeated first-person
        self-verification: a stream of "No... wait... actually... let me re-read...
        misread" hedges, and/or an unbounded string of implausible metric guesses
        ("above 98%? No, above 103%?").  A short, normal planning block is never
        treated as a spiral — this requires a long, hedge-dense, or
        impossible-figure reasoning run.
        """
        if not reasoning or len(reasoning) < 400:
            return False
        low = reasoning.lower()
        words = re.findall(r"[a-z']+", low)
        if not words:
            return False
        hedges = len(
            re.findall(
                r"\b(no\b|wait\b|actually\b|hmm\b|hold on\b|correction\b|"
                r"misread\b|re-?read\b|re-?check\b|check again\b|let me look\b|"
                r"let me trace\b|i mis\b)",
                low,
            )
        )
        if hedges >= 10 and hedges / len(words) >= 0.12:
            return True
        above = [int(n) for n in re.findall(r"above\s+(\d+)\s*(?:percent|%)", low)]
        return bool(len(above) >= 4 and max(above) > 100)

    def _looks_derailed(self, text: str) -> bool:
        """Return True when a trailing span of text is rambling word-salad.

        Two complementary signals over the most recent tokens:

        - **Function-word share**: a genuine summary (even dense technical
          writing) keeps a steady share of determiners/prepositions/auxiliaries;
          a pure agrammatic degeneration crams content words together with
          almost none.
        - **Type-token ratio**: a derailment often keeps enough function words to
          hide from the ratio above, yet churns out an almost unbroken run of
          novel words, so nearly every recent token is unique — never true of
          prose, which reuses terms and closed-class words.
        """
        tokens = re.findall(r"[A-Za-z0-9']+", text.lower())[-120:]
        if len(tokens) < 40:
            return False
        function_count = sum(1 for t in tokens if t in _FUNCTION_WORDS)
        fn_ratio = function_count / len(tokens)
        if fn_ratio < _DERAIL_FUNCTION_WORD_RATIO:
            return True
        type_token_ratio = len(set(tokens)) / len(tokens)
        # Novel-rambling counts only when it is also low in function words, so it
        # cannot fire on a legitimate but diverse/terse summary.
        return (
            type_token_ratio > _DERAIL_TYPE_TOKEN_RATIO
            and fn_ratio < _DERAIL_TTR_FN_GATE
        )

    @staticmethod
    def _no_result_notice(query: str) -> str:
        """Return the static notice when no relevant documents are found."""
        return f"I couldn't find relevant documents for your query: {query}"

    @staticmethod
    def _apply_llm_fallback(notice: str, llm_answer: object) -> str:
        """Append a non-empty LLM answer to the static *notice*."""
        if isinstance(llm_answer, str) and llm_answer.strip():
            return f"{notice}\n\n{llm_answer}"
        return notice

    def _build_knowledge_fallback_prompt(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Build a self-contained instruction prompt for the LLM knowledge fallback.

        The prompt explains that no matching documents exist in the local
        knowledge base and instructs the model to answer using the supplied
        conversation context (if any) and its own general knowledge — or to
        honestly state it has no information.

        When ``conversation_history`` is provided and non-empty, a
        "Relevant conversation context" section (built with
        :meth:`_format_history`) is inserted before the no-documents
        instructions so a multi-turn follow-up can leverage earlier turns in the
        chat session. When it is None/empty, the prompt is stateless and matches
        the original single-turn behaviour exactly.

        Args:
            query: The user's original query.
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session to give the
                model conversational context.

        Returns:
            The instruction prompt to send to the LLM.
        """
        conversation_section = ""
        if conversation_history:
            formatted = self._format_history(conversation_history)
            if formatted:
                conversation_section = (
                    "Relevant conversation context (from this chat session):\n"
                    f"{formatted}\n\n"
                )
        return (
            f"The user asked: {query}\n\n"
            f"{conversation_section}"
            "There are no matching documents for this question in the local "
            "knowledge base, so no retrieved context is available.\n"
            "Using ONLY the conversation context above and your own general "
            "knowledge, answer THE user's CURRENT question stated at the top - "
            "not earlier questions in the conversation context, and not the "
            "prior topic if the user has changed subjects. If you do NOT have "
            "enough information, reply with a short, honest statement that you "
            "do not have information on it. Do not fabricate facts or present "
            "guesswork as established knowledge."
        )

    def _build_contextual_search_query(
        self, query: str, conversation_history: list[dict[str, Any]] | None = None
    ) -> str:
        """Derive an augmented retrieval query from recent conversation terms.

        Appends distinctive named entities and technical tokens (e.g. a person
        name and a hyphenated term such as "ADOS-2") extracted from the most
        recent conversation turns so a multi-turn follow-up like "what
        challenges will brian face..." can retrieve the source document for the
        actual entity (Brian Hand / an ADOS-2 report), rather than relying on a
        generic knowledge answer.

        Args:
            query: The user's latest (rewritten) query.
            conversation_history: Recent conversation messages.

        Returns:
            The *query* augmented with extracted terms, or *query* unchanged
            when no usable history/terms are available.
        """
        terms = self._extract_contextual_terms(conversation_history)
        if not terms:
            return query
        return f"{query} {' '.join(terms)}"

    def _extract_contextual_terms(
        self,
        conversation_history: list[dict[str, Any]] | None,
        max_terms: int = 5,
        recent_turns: int = 20,
    ) -> list[str]:
        """Extract the most distinctive entity/technical terms from conversation.

        Counts occurrences of multi-word proper nouns and hyphenated tokens
        containing digits (e.g. "ADOS-2") across the recent *recent_turns*
        messages, preferring terms that recur — repeated entities are the most
        likely subject — so an entity established several turns back is still
        captured. Sentence-leading filler words are skipped. Technical tokens
        get a small boost since they are strong document discriminators.

        Args:
            conversation_history: Recent conversation messages.
            max_terms: Maximum number of terms to return.
            recent_turns: How many of the most recent messages to scan.

        Returns:
            At most *max_terms* unique terms, ranked by descending frequency
            with ties broken by first appearance, or an empty list.
        """
        if not conversation_history:
            return []
        text = "\n".join(
            m.get("content", "") for m in conversation_history[-recent_turns:]
        )
        filler = {
            "The",
            "According",
            "Based",
            "Yes",
            "This",
            "That",
            "Since",
            "Using",
            "Please",
            "Note",
            "As",
            "Our",
            "Do",
            "Not",
            "Only",
            "There",
            "I",
            "You",
            "Your",
            "If",
            "In",
            "On",
            "For",
            "A",
            "An",
            "But",
            "And",
            "So",
            "It",
            "We",
            "Or",
            "Because",
            "Regarding",
        }
        names = [
            n
            for n in re.findall(r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+", text)
            if n.split()[0] not in filler
        ]
        technical = re.findall(r"[A-Za-z][A-Za-z0-9]*-[A-Za-z0-9]*[0-9]+\b", text)
        technical_set = set(technical)
        counts = Counter(names + technical)
        seen: dict[str, int] = {}
        for token in names + technical:
            seen.setdefault(token, len(seen))

        def _rank(token: str) -> tuple[int, int]:
            boost = 1 if token in technical_set else 0
            return (-(counts[token] + boost), seen[token])

        ranked = sorted(counts, key=_rank)
        return ranked[:max_terms]

    def _query_references_context(self, query: str, terms: list[str]) -> bool:
        """Whether *query* refers to any entity named by an extracted term.

        Restricts the grounded re-retrieval to genuine multi-turn follow-ups,
        which reference an entity established in earlier turns (e.g. a follow-up
        about "brian" cites the extracted "Brian Hand"). A fresh, self-contained
        question such as "what is the speed of light" shares no tokens with the
        history terms and must not be re-queried with unrelated conversation
        topics, which would otherwise return irrelevant-but-high-scoring chunks.

        Args:
            query: The user's latest query.
            terms: Contextual terms extracted from the conversation history.

        Returns:
            True if the query references a history entity, False otherwise.
        """
        lowered = query.lower()
        for term in terms:
            for token in term.split():
                base = token.lower().rstrip("'s").split("-")[0]
                if len(base) >= 3 and base in lowered:
                    return True
        return False

    def _save_turn(
        self,
        session: ConversationSession,
        query: str,
        answer: str,
    ) -> None:
        """Persist one chat turn (user message + assistant answer) to a session.

        All ``chat()`` exit paths call this so that follow-up turns always see
        the most recent exchange, even when the answer came from a no-source
        fallback path (which otherwise would not be recorded).
        """
        if not answer or not answer.strip():
            return
        session.add_message("user", query)
        session.add_message("assistant", answer)

    def _grounded_context_retry(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any] | None:
        """Re-query the vector DB with a context-augmented query.

        Only attempted when the query references an entity from the
        conversation (a genuine follow-up). If relevant chunks are found,
        return a dict with a grounded RAG answer. Returns None when the query is
        not a follow-up or nothing relevant is retrieved, so the caller can use
        the knowledge fallback.
        """
        chunks = self._contextual_search(query, conversation_history, top_k)
        if chunks is None:
            return None
        context_text = self._format_context(chunks)
        prompt = self._build_prompt(query, context_text, conversation_history or [])
        try:
            answer, streamed = self._stream_generate(prompt)
        except Exception as exc:
            logger.warning(
                "Grounded generation failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not answer or not answer.strip():
            return None
        if not streamed and self._on_chunk and answer:
            self._on_chunk(answer, None)
        result: dict[str, Any] = {
            "answer": answer,
            "query": query,
            "rewritten_query": query,
            "grounded_retry": True,
        }
        if show_sources:
            result["sources"] = chunks
        return result

    async def _grounded_context_retry_async(
        self,
        query: str,
        conversation_history: list[dict[str, Any]] | None,
        top_k: int,
        show_sources: bool,
    ) -> dict[str, Any] | None:
        """Async variant of :meth:`_grounded_context_retry`.

        Identical contract (returns a grounded answer dict if the query is a
        follow-up referencing history and relevant chunks are found, else None)
        but uses the provider's async ``search_async``/``agenerate`` when
        available, falling back to the sync equivalents otherwise.
        """
        chunks = await self._contextual_search_async(query, conversation_history, top_k)
        if chunks is None:
            return None
        context_text = self._format_context(chunks)
        prompt = self._build_prompt(query, context_text, conversation_history or [])
        try:
            answer = await self._agenerate(prompt)
        except Exception as exc:
            logger.warning(
                "Grounded generation failed: %s: %s", type(exc).__name__, exc
            )
            return None
        if not answer or not answer.strip():
            return None
        result: dict[str, Any] = {
            "answer": answer,
            "query": query,
            "rewritten_query": query,
            "grounded_retry": True,
        }
        if show_sources:
            result["sources"] = chunks
        return result

    def _has_relevant_chunks(self, chunks: list[dict[str, Any]]) -> bool:
        """Return True if any retrieved chunk meets the relevance score threshold.

        A chunk counts as relevant when its cosine-similarity ``score`` is at
        least ``rag_min_similarity_threshold``. When none of the chunks carry a
        ``score`` they are all treated as relevant, so existing behaviour is
        preserved for score-less context (e.g. unit-test fixtures). When at least
        one chunk has a score, only the scored chunks are evaluated — a single
        score-less chunk cannot bypass the threshold gate on an otherwise-scored
        batch. Returns False only when *chunks* is empty or every scored chunk
        falls below the threshold.

        Args:
            chunks: Retrieved chunk dicts (each may carry a ``score``).

        Returns:
            True if there is usable relevant context, False otherwise.
        """
        if not chunks:
            return False
        scored = [c["score"] for c in chunks if c.get("score") is not None]
        if not scored:
            return True  # no score signal at all -> do not gate (backward compatible)
        return any(s >= self._config.rag_min_similarity_threshold for s in scored)

    def _handle_no_results(
        self,
        query: str,
        allow_llm_fallback: bool = True,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Handle case when no documents retrieved.

        Always reports that no relevant documents were found in the knowledge
        base. When ``allow_llm_fallback`` is True and the
        ``rag_llm_fallback_enabled`` config flag is set, it additionally asks the
        LLM to answer from its own knowledge (and the supplied conversation
        context, if any) and appends that answer when non-empty. The static
        notice is always returned first.

        Args:
            query: Original query.
            allow_llm_fallback: Whether this call may use the LLM knowledge
                fallback. Pass False to return only the static notice (e.g. when
                the LLM has already failed in the same request).
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session, threaded into
                the fallback prompt so a multi-turn follow-up can use earlier
                turns even when no documents matched.

        Returns:
            The static no-results notice, or the notice followed by a non-empty
            LLM knowledge answer when the fallback is enabled and succeeds.

        Example:
            >>> pipeline._handle_no_results("What is Python?")
            "I couldn't find relevant documents for your query: What is Python?"
        """
        notice = self._no_result_notice(query)

        if not allow_llm_fallback or not self._config.rag_llm_fallback_enabled:
            return notice

        prompt = self._build_knowledge_fallback_prompt(
            query, conversation_history=conversation_history
        )
        try:
            llm_answer, streamed = self._stream_generate(prompt, prefix=f"{notice}\n\n")
        except Exception as exc:
            logger.warning(
                "LLM knowledge fallback failed for query %r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return notice

        result = self._apply_llm_fallback(notice, llm_answer)
        if not streamed and self._on_chunk and result:
            self._on_chunk(result, None)
        return result

    async def _handle_no_results_async(
        self,
        query: str,
        allow_llm_fallback: bool = True,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> str:
        """Async variant of :meth:`_handle_no_results`.

        Identical behaviour to the sync version but uses the provider's async
        ``agenerate`` method when available for the LLM knowledge fallback. Falls
        back to the sync ``generate`` method when ``agenerate`` is unavailable.
        Never raises: on any failure the static notice is returned unchanged.

        Args:
            query: Original query.
            allow_llm_fallback: Whether this call may use the LLM knowledge
                fallback.
            conversation_history: Optional list of prior message dicts (with
                ``role``/``content`` keys) from the chat session, threaded into
                the fallback prompt so a multi-turn follow-up can use earlier
                turns even when no documents matched.

        Returns:
            Fallback response text.
        """
        notice = self._no_result_notice(query)

        if not allow_llm_fallback or not self._config.rag_llm_fallback_enabled:
            return notice

        prompt = self._build_knowledge_fallback_prompt(
            query, conversation_history=conversation_history
        )
        try:
            llm_answer = await self._agenerate(prompt)
        except Exception as exc:
            logger.warning(
                "LLM knowledge fallback (async) failed for query %r: %s: %s",
                query,
                type(exc).__name__,
                exc,
            )
            return notice

        return self._apply_llm_fallback(notice, llm_answer)


class _RoutingMixin(_RAGPipelineState):
    """Document routing and source-filter helpers."""

    def _get_document_router(self) -> DocumentRouter:
        """Return the DocumentRouter, creating it lazily if needed."""
        if self._document_router is None:
            try:
                self._document_router = DocumentRouter(
                    storage=self._searcher.storage,
                )
            except Exception:
                self._document_router = DocumentRouter()
        return self._document_router

    def _resolve_source_filter(self, query: str) -> str | None:
        """Resolve a user query to a source_file filter if a doc is named.

        Returns a source_file path string or None if no document is referenced.
        """
        router = self._get_document_router()
        doc_name = router.extract_document_name(query)
        if doc_name is not None:
            return router.resolve_source_file(doc_name)
        return None

    # ------------------------------------------------------------------
    # Page-number lookup ("what is on page N")
    # ------------------------------------------------------------------

    def _answer_page_query(self, query: str) -> dict[str, Any] | None:
        """Return the verbatim text of the requested printed page, else ``None``.

        A page-number query is an exact lookup: resolve the printed page to its
        chunks and return the page text as-is. No LLM is invoked, so the output
        is the raw, complete page text with no commentary, excerpts, or truncation.
        Returns ``None`` for any query without a page reference, so the caller
        falls back to the normal semantic path and non-page queries are unaffected.
        """
        chunks = self._page_query_chunks(query)
        if chunks is None:
            return None
        if not chunks:
            return self._page_not_found(query)
        return {
            "answer": self._stitch_page_text(chunks),
            "query": query,
            "sources": chunks,
        }

    @staticmethod
    def _stitch_page_text(chunks: list[dict[str, Any]]) -> str:
        """Return the page's verbatim text by stitching *chunks* in order.

        Removes each chunk's leading ``[ N ]`` extraction stub and collapses the
        small boundary overlap between consecutive chunks so the result reads as
        a single, clean page rather than overlapping slices.
        """
        parts: list[str] = []
        for c in chunks:
            text = (c.get("chunk_text") or c.get("text") or "").strip()
            if not text:
                continue
            marker = _PAGE_MARKER_RE.match(text)
            if marker:
                text = text[marker.end() :].strip()
            if _PAGE_STUB_LINE_RE.search(text):
                text = "\n".join(
                    line
                    for line in text.splitlines()
                    if not _PAGE_STUB_LINE_RE.match(line)
                ).strip()
            parts.append(text)
        if not parts:
            return ""
        result = parts[0]
        for nxt in parts[1:]:
            k = _boundary_overlap(result, nxt)
            result += nxt[k:] if k else "\n" + nxt
        return result

    def _page_query_chunks(self, query: str) -> list[dict[str, Any]] | None:
        """Resolve a page-reference query to its chunks, or ``None`` to skip.

        Returns ``None`` when the query has no page reference (or the backend
        cannot do a page lookup) so the caller falls back to semantic search;
        returns ``[]`` when a referenced page has no matching chunks.
        """
        printed = self._printed_page_from_query(query)
        if printed is None:
            return None
        storage = getattr(self._searcher, "storage", None)
        if storage is None or not hasattr(storage, "find_chunks"):
            return None
        source = self._resolve_source_filter(query)
        try:
            found = storage.find_chunks(source_file=source, printed_page=printed)
            found = self._expand_page_chunks(storage, source, list(found))
        except Exception as exc:  # pragma: no cover - backend-dependent
            logger.warning(
                "Page lookup failed; falling back to semantic search: %s", exc
            )
            return None
        return [dict(c) for c in found]

    @staticmethod
    def _printed_page_from_query(query: str) -> int | None:
        """Return the printed page number referenced in *query*, or ``None``."""
        match = _PAGE_REF_RE.search(query)
        if match is None:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    def _expand_page_chunks(
        self,
        storage: Any,
        source: str | None,
        primary: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Broaden a page lookup to the whole physical page(s).

        ``printed_page`` is derived per-chunk from a ``[ N ]`` marker, so only the
        first chunk of a page carries it while the page's continuation chunks
        (same physical ``page_number``, no marker) are omitted. Expand to every
        chunk sharing the marker chunk's physical page so the full printed page
        is returned instead of the marker-bearing slice.
        """
        if not primary:
            return primary
        page_nums = {
            int(c["page_number"]) for c in primary if c.get("page_number") is not None
        }
        if not page_nums or not hasattr(storage, "find_chunks"):
            return primary
        try:
            full = storage.find_chunks(
                source_file=source, page_number=sorted(page_nums)
            )
        except Exception:  # pragma: no cover - backend-dependent
            return primary
        by_id: dict[str, Any] = {}
        for c in primary:
            by_id[c.get("chunk_id", id(c))] = c
        for c in full:
            by_id.setdefault(c.get("chunk_id", id(c)), c)
        merged = list(by_id.values())
        # Order within a page by the ingest ``page_pos``. Chunks lacking it
        # (pre-reingest legacy data) sort last, in their returned order.
        return sorted(
            merged,
            key=lambda c: (
                int(c.get("page_number") or -1),
                int(c["page_pos"]) if c.get("page_pos") is not None else 10**9,
            ),
        )

    def _page_not_found(self, query: str) -> dict[str, Any]:
        """Graceful answer when a referenced printed page has no chunks."""
        return {
            "answer": (
                "The available documents do not contain a page matching that "
                "number in their printed page index."
            ),
            "query": query,
            "sources": [],
        }

    async def _answer_page_query_async(self, query: str) -> dict[str, Any] | None:
        """Async twin of :meth:`_answer_page_query`.

        Resolves a "what is on page N" query to its printed-page chunks and
        returns the page text verbatim (no LLM). ``find_chunks`` is a synchronous
        storage call, so it runs via ``asyncio.to_thread`` to keep the event loop
        responsive.
        """
        chunks = await asyncio.to_thread(self._page_query_chunks, query)
        if chunks is None:
            return None
        if not chunks:
            return self._page_not_found(query)
        return {
            "answer": self._stitch_page_text(chunks),
            "query": query,
            "sources": chunks,
        }

    def _list_sources_result(self, query: str) -> dict[str, Any]:
        """Build a deterministic answer enumerating ALL distinct sources.

        Routes around vector search on purpose: semantic search is bounded by
        ``top_k`` and relevance, so it would silently drop sources as the
        corpus grows. A native ``distinct`` aggregation returns every unique
        source regardless of database size.

        Returns a result dict whose "answer" is a numbered enumeration of the
        source files (no LLM call, no embedding generation).
        """
        try:
            source_files: list[str] = list(self._searcher.list_source_files())
        except Exception as e:
            logger.warning("list_source_files failed: %s: %s", type(e).__name__, e)
            return {
                "answer": "I couldn't list the stored sources right now. Please try again.",
                "query": query,
                "list_sources": True,
            }

        source_files = sorted({s for s in source_files if s}, key=str.lower)

        if not source_files:
            return {
                "answer": (
                    "I don't have any documents stored yet. "
                    "Ingest some with `secondbrain ingest <path>` first."
                ),
                "query": query,
                "list_sources": True,
            }

        plural = "source" if len(source_files) == 1 else "sources"
        lines = [f"I found {len(source_files)} unique {plural}:"]
        lines.extend(f"  {i}. {s}" for i, s in enumerate(source_files, 1))
        return {
            "answer": "\n".join(lines),
            "query": query,
            "list_sources": True,
        }

    def _rewrite_query_with_history(
        self,
        query: str,
        session: ConversationSession,
    ) -> str:
        """Rewrite query using conversation history.

        Args:
            query: Current user query.
            session: ConversationSession with history.

        Returns:
            Rewritten query or original if rewriter not available.

        Example:
            >>> session = ConversationSession.create("test", storage)
            >>> pipeline._rewrite_query_with_history("What about it?", session)
            "What about it?"  # No rewriter, returns original
        """
        if self._rewriter is None:
            return query

        history = session.get_history(limit=self._context_window)
        if not history:
            return query

        try:
            return self._rewriter.rewrite_query(query, history)
        except Exception as e:
            logger.warning("Query rewriting failed: %s: %s", type(e).__name__, e)
            return query
