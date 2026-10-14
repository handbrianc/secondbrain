"""Cohesive helper-method mixins for the RAG pipeline.

The former single 4500-line module was decomposed into cohesive sibling
modules by topic: text quality (``_text_quality``), leak scrubbing
(``_leak_scrub``), streaming control (``_streaming``), and one module per
mixin class (``_formatting_mixin``, ``_structure_mixin``,
``_fallback_mixin``, ``_routing_mixin``).  This module remains as a
compatibility shim re-exporting the full historical surface so existing
``from secondbrain.rag.pipeline._mixins import ...`` paths keep working.
"""

from secondbrain.rag.pipeline._fallback_mixin import (
    _CHAPTER_OVERVIEW_INSTRUCTION as _CHAPTER_OVERVIEW_INSTRUCTION,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _HIERARCHY_GROUP_SIZE as _HIERARCHY_GROUP_SIZE,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _HIERARCHY_THRESHOLD as _HIERARCHY_THRESHOLD,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _MAP_DIGEST_MAX_TOKENS as _MAP_DIGEST_MAX_TOKENS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _MAX_MAP_REDUCE_WINDOWS as _MAX_MAP_REDUCE_WINDOWS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _OVERVIEW_MAX_WORDS as _OVERVIEW_MAX_WORDS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _RETRY_MAX_TOKENS as _RETRY_MAX_TOKENS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _SINGLE_PASS_MAX_CHARS as _SINGLE_PASS_MAX_CHARS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _STREAM_FLOOD_MIN_CHARS as _STREAM_FLOOD_MIN_CHARS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _STREAM_LEAK_HOLD as _STREAM_LEAK_HOLD,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _SUMMARY_REDUCE_MAX_TOKENS as _SUMMARY_REDUCE_MAX_TOKENS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _SUMMARY_WINDOW_CHARS as _SUMMARY_WINDOW_CHARS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _WINDOW_MAX_SECONDS as _WINDOW_MAX_SECONDS,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    SUMMARY_TEMPERATURE as SUMMARY_TEMPERATURE,
)
from secondbrain.rag.pipeline._fallback_mixin import (
    _FallbackMixin as _FallbackMixin,
)
from secondbrain.rag.pipeline._formatting_mixin import (
    _FormattingMixin as _FormattingMixin,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _CONTENT_SELF_CORRECTION_MARKERS as _CONTENT_SELF_CORRECTION_MARKERS,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _LEAK_SCRUB_RES as _LEAK_SCRUB_RES,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _NUMERIC_HEDGE_RE as _NUMERIC_HEDGE_RE,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _NUMERIC_SELF_CORRECT_RE as _NUMERIC_SELF_CORRECT_RE,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _REASONING_BUDGET_FALLBACK_PREFIX as _REASONING_BUDGET_FALLBACK_PREFIX,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _REASONING_LEAK_MARKERS as _REASONING_LEAK_MARKERS,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _contains_reasoning_leak as _contains_reasoning_leak,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _is_content_self_correction as _is_content_self_correction,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _is_stream_leak as _is_stream_leak,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _scrub_self_correction as _scrub_self_correction,
)
from secondbrain.rag.pipeline._leak_scrub import (
    _strip_numeric_self_correction as _strip_numeric_self_correction,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _PAGE_FOOTER_LINE_RE as _PAGE_FOOTER_LINE_RE,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _PAGE_MARKER_RE as _PAGE_MARKER_RE,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _PAGE_REF_RE as _PAGE_REF_RE,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _PAGE_STUB_LINE_RE as _PAGE_STUB_LINE_RE,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _boundary_overlap as _boundary_overlap,
)
from secondbrain.rag.pipeline._routing_mixin import (
    _RoutingMixin as _RoutingMixin,
)
from secondbrain.rag.pipeline._streaming import (
    _StreamAbortError as _StreamAbortError,
)
from secondbrain.rag.pipeline._streaming import (
    _StreamLeakError as _StreamLeakError,
)
from secondbrain.rag.pipeline._streaming import (
    _WindowStreamSink as _WindowStreamSink,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _BOILERPLATE_CAPTION_RE as _BOILERPLATE_CAPTION_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _BOILERPLATE_TITLE_RE as _BOILERPLATE_TITLE_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _CHAPTER_DESC_RE as _CHAPTER_DESC_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _CHAPTER_DESC_TAIL_RE as _CHAPTER_DESC_TAIL_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _TOC_CHAPTER_ENTRY_RE as _TOC_CHAPTER_ENTRY_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _TOC_CHAPTER_MENTION_RE as _TOC_CHAPTER_MENTION_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _TOC_LISTING_LINE_RE as _TOC_LISTING_LINE_RE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _TOC_MIN_COVERAGE as _TOC_MIN_COVERAGE,
)
from secondbrain.rag.pipeline._structure_mixin import (
    _StructureMixin as _StructureMixin,
)
from secondbrain.rag.pipeline._text_quality import (
    _DERAIL_FUNCTION_WORD_RATIO as _DERAIL_FUNCTION_WORD_RATIO,
)
from secondbrain.rag.pipeline._text_quality import (
    _DERAIL_TTR_FN_GATE as _DERAIL_TTR_FN_GATE,
)
from secondbrain.rag.pipeline._text_quality import (
    _DERAIL_TYPE_TOKEN_RATIO as _DERAIL_TYPE_TOKEN_RATIO,
)
from secondbrain.rag.pipeline._text_quality import (
    _FUNCTION_WORDS as _FUNCTION_WORDS,
)
from secondbrain.rag.pipeline._text_quality import (
    _GROUNDING_FIGURE_RE as _GROUNDING_FIGURE_RE,
)
from secondbrain.rag.pipeline._text_quality import (
    _GROUNDING_MAGNITUDE as _GROUNDING_MAGNITUDE,
)
from secondbrain.rag.pipeline._text_quality import (
    _METRIC_BOUNDED_RE as _METRIC_BOUNDED_RE,
)
from secondbrain.rag.pipeline._text_quality import (
    _METRIC_VALUE_CONT_RE as _METRIC_VALUE_CONT_RE,
)
from secondbrain.rag.pipeline._text_quality import (
    _METRIC_VALUE_START_RE as _METRIC_VALUE_START_RE,
)
from secondbrain.rag.pipeline._text_quality import (
    _NUM_RE as _NUM_RE,
)
from secondbrain.rag.pipeline._text_quality import (
    _ends_on_sentence as _ends_on_sentence,
)
from secondbrain.rag.pipeline._text_quality import (
    _ground_figures as _ground_figures,
)
from secondbrain.rag.pipeline._text_quality import (
    _grounding_figure_key as _grounding_figure_key,
)
from secondbrain.rag.pipeline._text_quality import (
    _prune_implausible_metric_figures as _prune_implausible_metric_figures,
)
from secondbrain.rag.pipeline._text_quality import (
    _trim_to_sentence_end as _trim_to_sentence_end,
)
from secondbrain.rag.pipeline._text_quality import (
    _trim_to_word_budget as _trim_to_word_budget,
)
