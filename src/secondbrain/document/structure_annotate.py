"""Per-chunk structural annotation against a captured tree (lane 1b).

Implements design §7 of openspec ``add-structure-aware-ingestion``:
:func:`annotate_chunks` walks chunks in reading order and adds structural
payload keys — ``node_id``, ``heading_path``, ``chapter_id``, ``section_id``,
``section_label`` (plus ``t_start``/``t_end`` for audio segment nodes) — by
either *anchoring* a chunk whose text starts with a node's heading forms or
*inheriting* the deepest tree node whose range contains the chunk position.

Contract (design §7 hard constraint): annotation only ADDS keys — chunk
text, page, hashes and existing fields are untouched, so ``text_hash``-keyed
dedup keeps every stored point valid. The function never mutates its input
and never raises: on any internal failure it warns and returns shallow
copies of the input.

Matching model
--------------

* **Anchor** — a chunk anchors to the deepest range-containing node whose
  heading forms match the chunk text head. Heading forms are compared as
  whitespace-collapsed, case-folded prefixes with a word boundary: for
  numbered nodes ``"<number> <title>"`` (plus ``"Chapter <number>"`` /
  ``"Part <number>"``), for unnumbered nodes the bare ``title``.
* **Inherit** — otherwise the chunk inherits the deepest range-containing
  node. Range containment is decided on the chunk's position: ``page`` for
  page-based trees, the chunk dict's optional ``t_start``/``t_end`` keys for
  audio (time-based) trees. A chunk with no usable position (``page`` < 1
  and no time keys), or ambiguous ownership across same-page branches, is
  left un-annotated so it stays refreshable.
* **Sticky inheritance (ordered mode)** — callers that walk chunks in true
  reading order pass ``ordered=True`` (the fresh-ingest processor worker and
  the qdrant refresh, after it sorts points on ``(page_number, page_pos)``).
  The walk then carries the previous chunk's annotation target as a sticky
  owner: an unanchored page-mode chunk whose position still lies in the
  owner's range inherits the owner (design D2 rule 2 of
  ``fix-chunk-heading-context``). Anchors update the owner; the owner is
  never reset by unannotated chunks (containment is re-checked per chunk, so
  an oscillating page that leaves the owner's range falls through to the
  most-recent-start rule); time mode (audio) never applies it and stays
  stateless.
* **Most-recent-start fallback (ordered mode)** — an unanchored page-mode
  chunk with no applicable sticky owner inherits the candidate ordered last
  in the tree's reading order (greatest ``(start, level, reading index)``),
  i.e. the heading most recently opened at or before its position (design D2
  rule 3). Ordered mode therefore resolves whenever any candidate exists;
  the same-page ambiguity bail-out is reserved for unordered callers.
  ``ordered=False`` (the default) keeps the unordered behavior
  byte-for-byte.
* **Payload keys** — ``node_id``/``heading_path``/``chapter_id`` are always
  added once a node is found; ``section_id``/``section_label`` only when the
  target has a numbered non-part ancestor-or-self; ``t_start``/``t_end``
  only when the target node carries time bounds. Chunks that match no node
  get no new keys at all.

Order-independence note: without ``ordered`` the per-chunk containment
filter makes results independent of chunk order for well-formed (nested)
trees. Ordered mode trades that independence for reading-order
disambiguation and is reserved for callers that guarantee reading order;
the qdrant ``refresh_structural_payload`` sorts its points on
``(page_number, page_pos)`` and annotates them in ONE ordered pass (design
D3 of ``fix-chunk-heading-context``).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from secondbrain.storage.structure_sqlite import DocumentStructure, StructureNode

logger = logging.getLogger(__name__)

__all__ = [
    "ANNOTATION_PAYLOAD_KEYS",
    "annotate_chunks",
    "is_time_mode_tree",
]

# Payload keys annotate_chunks adds. Consumed by the processor worker (doc
# dict assembly) and by the qdrant payload refresh, which copies exactly
# these keys onto refreshed point payloads.
ANNOTATION_PAYLOAD_KEYS: tuple[str, ...] = (
    "node_id",
    "heading_path",
    "chapter_id",
    "section_id",
    "section_label",
    "t_start",
    "t_end",
)

_INF = float("inf")


def annotate_chunks(
    chunks: Sequence[Mapping[str, Any]],
    tree: DocumentStructure,
    *,
    ordered: bool = False,
) -> list[Mapping[str, Any]]:
    """Annotate chunks with structural payload keys from *tree*.

    Walks *chunks* in reading order, anchoring each chunk whose text starts
    with a node's heading forms and otherwise inheriting the deepest node
    whose range contains the chunk position (design §7). With
    ``ordered=True`` the walk additionally carries the previous chunk's
    annotation target as a sticky owner that unanchored page-mode chunks
    inherit while its range still contains their position (design D2) —
    reading order is what resolves same-page sibling sections. Only adds
    keys — text, page, hashes and existing fields are untouched, so
    ``text_hash`` dedup keeps every stored point valid.

    Args:
        chunks: Chunk dicts in reading order (the processor worker's
            post-dedup list). Never mutated; unknown keys are preserved.
        tree: The captured document tree (``DocumentStructure``).
        ordered: True only from callers that guarantee reading order — the
            fresh-ingest processor worker and the qdrant
            ``refresh_structural_payload`` (after it sorts points on
            ``(page_number, page_pos)``). Default False keeps today's
            stateless, order-independent behavior.

    Returns
    -------
        One shallow copy per input chunk, in the same order. Copies of
        chunks that anchor or inherit a tree node carry the added payload
        keys (:data:`ANNOTATION_PAYLOAD_KEYS`, partially); the rest are
        unchanged copies. Never raises: on any internal failure the input is
        returned as plain shallow copies and a warning is logged.
    """
    try:
        return _annotate_all(chunks, tree, ordered=ordered)
    except Exception as e:
        logger.warning(
            "Chunk annotation failed (%s: %s); returning unannotated copies",
            type(e).__name__,
            e,
        )
        return [dict(chunk) for chunk in chunks]


# ---------------------------------------------------------------------------
# Tree index (per-call precomputation)
# ---------------------------------------------------------------------------


def is_time_mode_tree(nodes: Iterable[StructureNode]) -> bool:
    """Return whether the tree is time-keyed (audio).

    True when the tree carries time spans and no page spans. This is the
    single source of the time-mode rule — :class:`_TreeIndex`
    keys its span lookups with it, and the qdrant payload refresh uses it to
    decide whether stored ``t_start``/``t_end`` are legitimate annotation
    input (audio) or stale extras to delete (page-keyed documents).
    """
    has_time_node = any(node.t_start is not None for node in nodes)
    has_page_node = any(node.page_start is not None for node in nodes)
    return has_time_node and not has_page_node


class _TreeIndex:
    """Precomputed node lookup structures for one annotation pass.

    Nodes with a usable range (page or time span) are kept in reading order
    with their span, level and original index; heading forms are precomputed
    per node id.
    """

    def __init__(self, tree: DocumentStructure) -> None:
        self.by_id: dict[str, StructureNode] = {}
        self.parent_of: dict[str, str] = {}
        self.forms: dict[str, list[str]] = {}
        entries: list[tuple[float, float, int, int, StructureNode]] = []
        for index, node in enumerate(tree.nodes):
            self.by_id[node.node_id] = node
            if node.parent_id is not None:
                self.parent_of[node.node_id] = node.parent_id
            self.forms[node.node_id] = _normalized_heading_forms(node)
            span = _node_span(node)
            if span is None:
                continue
            start, end = span
            entries.append((start, end, node.level, index, node))
        # Time-keyed nodes (audio) and page-keyed nodes never mix: one
        # document is one medium. Time mode is chosen when the tree carries
        # time spans and no page spans, so page-0 chunks (unknown page) can
        # never be inherited by arbitrary audio segments.
        self.time_mode = is_time_mode_tree(tree.nodes)
        # Sort by (start, level, reading order) so same-start children push
        # after their parent and the deepest container is the last match.
        ordered = sorted(entries, key=lambda e: (e[0], e[2], e[3]))
        self.sorted_nodes: list[StructureNode] = [entry[4] for entry in ordered]
        self.sorted_spans: list[tuple[float, float]] = [
            (entry[0], entry[1]) for entry in ordered
        ]


def _node_span(node: StructureNode) -> tuple[float, float] | None:
    """Return the node's ``(start, end)`` position span, or None.

    Page spans win over time spans (a page-numbered node is a document
    node); a missing end bound means "open ended" (infinity).
    """
    if node.page_start is not None:
        start = float(node.page_start)
        end = float(node.page_end) if node.page_end is not None else _INF
        return (start, end)
    if node.t_start is not None:
        end = float(node.t_end) if node.t_end is not None else _INF
        return (float(node.t_start), end)
    return None


def _chunk_span(
    chunk: Mapping[str, Any], time_mode: bool
) -> tuple[float, float] | None:
    """Return the chunk's ``(start, end)`` position span, or None.

    Audio trees (time mode) require numeric ``t_start``/``t_end`` keys on
    the chunk; page trees require a ``page`` >= 1 (0 means unknown). A chunk
    with no usable position is left un-annotated.
    """
    if time_mode:
        t_start = _as_number(chunk.get("t_start"))
        if t_start is None:
            return None
        t_end = _as_number(chunk.get("t_end"))
        return (t_start, t_end if t_end is not None else t_start)
    page = _as_number(chunk.get("page"))
    if page is None or page < 1:
        return None
    return (page, page)


def _as_number(value: Any) -> float | None:
    """Return *value* as a float when it is a plain (non-bool) number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


# ---------------------------------------------------------------------------
# Heading forms (anchor matching)
# ---------------------------------------------------------------------------


def _normalized_heading_forms(node: StructureNode) -> list[str]:
    """Return the node's whitespace-collapsed, case-folded heading forms.

    Numbered nodes match ``"<number> <title>"`` and the word-shaped
    ``"Chapter <number>"`` / ``"Part <number>"`` prefixes; unnumbered nodes
    match their bare title only (a bare title is too weak a signal for a
    numbered node, whose number+title form is already authoritative).
    """
    title = " ".join(node.title.split()).casefold()
    if not title:
        return []
    number = node.number
    if not number:
        return [title]
    number = " ".join(number.split()).casefold()
    word = "part" if node.kind == "part" else "chapter"
    return [f"{number} {title}", f"{word} {number}"]


def _matches_form(chunk_norm: str, form: str) -> bool:
    """Prefix match with a word boundary (or exact equality).

    The boundary keeps "Chapter 5" from matching "Chapter 51" and "5.2
    Installing" from matching "5.23 Installing...".
    """
    if not chunk_norm.startswith(form):
        return False
    rest = chunk_norm[len(form) :]
    return not rest or not rest[0].isalnum()


# ---------------------------------------------------------------------------
# Annotation core
# ---------------------------------------------------------------------------


def _annotate_all(
    chunks: Sequence[Mapping[str, Any]],
    tree: DocumentStructure,
    *,
    ordered: bool = False,
) -> list[Mapping[str, Any]]:
    """Annotate every chunk (single failure domain inside annotate_chunks)."""
    index = _TreeIndex(tree)
    result: list[Mapping[str, Any]] = []
    pushed = 0
    total_nodes = len(index.sorted_nodes)
    # Ordered mode (design D2): the sticky owner is the previous chunk's
    # annotation target. It is offered only to page-mode chunks — audio
    # (time mode) annotation stays stateless — and it is never reset by
    # unannotated chunks: containment is re-checked per chunk below, so a
    # stale owner is harmless (an oscillating page that leaves the owner's
    # range falls through to the conservative rule).
    last_owner: str | None = None
    sticky = ordered and not index.time_mode
    for chunk in chunks:
        span = _chunk_span(chunk, index.time_mode)
        if span is None:
            result.append(dict(chunk))
            continue
        # Advance the node pointer: every node starting at or before this
        # chunk's position becomes visible. The pointer only moves forward;
        # a later chunk with an earlier position (overlap windows may
        # oscillate pages) is still handled because containment is filtered
        # per chunk below.
        while pushed < total_nodes and index.sorted_spans[pushed][0] <= span[0]:
            pushed += 1
        out, owner = _annotate_chunk(
            chunk,
            span,
            index,
            pushed,
            last_owner=last_owner if sticky else None,
            ordered_fallback=sticky,
        )
        if owner is not None:
            last_owner = owner
        result.append(out)
    return result


def _annotate_chunk(
    chunk: Mapping[str, Any],
    span: tuple[float, float],
    index: _TreeIndex,
    pushed: int,
    last_owner: str | None = None,
    ordered_fallback: bool = False,
) -> tuple[dict[str, Any], str | None]:
    """Annotate one chunk; return the shallow copy and its owner's node id.

    The owner id is the node the chunk was annotated with (anchor, sticky
    inheritance, or the most-recent-start / conservative containment rule) —
    ``None`` when the chunk got no keys. *last_owner* is the ordered caller's
    sticky-owner candidate, already gated to page mode by
    :func:`_annotate_all`: when its node is among the containment candidates
    it takes the chunk outright (design D2 rule 2). Otherwise, in ordered
    mode (*ordered_fallback*), the chunk inherits the most recently started
    candidate — the candidate ordered last in the tree's reading order
    (design D2 rule 3), which keeps ordered mode resolving whenever any
    candidate exists. Unordered callers keep today's conservative rule
    (deepest candidate, chain-consistency bail).
    """
    out = dict(chunk)
    candidates = [
        i
        for i in range(pushed)
        if index.sorted_spans[i][0] <= span[0] <= index.sorted_spans[i][1]
    ]
    if not candidates:
        return out, None

    chunk_text = chunk.get("text")
    chunk_norm = " ".join(str(chunk_text).split()).casefold() if chunk_text else ""
    target_index: int | None = None
    if chunk_norm:
        anchor_matches = [
            i
            for i in candidates
            if any(
                _matches_form(chunk_norm, form)
                for form in index.forms.get(index.sorted_nodes[i].node_id, ())
            )
        ]
        if anchor_matches:
            target_index = max(
                anchor_matches,
                key=lambda i: (index.sorted_nodes[i].level, i),
            )
    if target_index is not None:
        target = index.sorted_nodes[target_index]
    elif last_owner is not None and last_owner in {
        index.sorted_nodes[i].node_id for i in candidates
    }:
        # Sticky inheritance (design D2 rule 2): reading order says the
        # previous chunk's owner still covers this chunk's position — trust
        # it over the same-page sibling ambiguity the conservative rule
        # bails on.
        target = index.by_id[last_owner]
    elif ordered_fallback:
        # Most-recent-start fallback (design D2 rule 3): with no applicable
        # sticky owner, reading order still resolves ownership — the
        # candidate ordered last is the heading most recently opened at or
        # before this chunk's position (sorted_nodes is ordered by
        # (start, level, reading index), so the last candidate is the
        # most-recent-start one).
        target = index.sorted_nodes[candidates[-1]]
    else:
        target_index = max(candidates, key=lambda i: (index.sorted_nodes[i].level, i))
        if not index.time_mode:
            # Page ranges cannot locate unanchored prose relative to two
            # same-page sibling headings. Do not invent reliable ownership.
            chain_ids = {
                node.node_id
                for node in _walk_chain(index.sorted_nodes[target_index], index)
            }
            if any(index.sorted_nodes[i].node_id not in chain_ids for i in candidates):
                return out, None
        target = index.sorted_nodes[target_index]
    _apply_annotation(out, target, index)
    return out, target.node_id


def _apply_annotation(
    out: dict[str, Any], target: StructureNode, index: _TreeIndex
) -> None:
    """Add the structural payload keys for *target* onto *out*.

    ``node_id``/``heading_path``/``chapter_id`` are always added;
    ``section_id``/``section_label`` only when the target has a numbered
    non-part ancestor-or-self; ``t_start``/``t_end`` only when the target
    node carries time bounds (audio segment nodes).
    """
    out["node_id"] = target.node_id
    out["heading_path"] = target.heading_path
    top = _top_level_ancestor(target, index)
    out["chapter_id"] = top.number if top.number else top.node_id
    section = _numbered_section(target, index)
    if section is not None:
        out["section_id"] = section.number
        out["section_label"] = section.title
    if target.t_start is not None:
        out.setdefault("t_start", target.t_start)
    if target.t_end is not None:
        out.setdefault("t_end", target.t_end)


def _walk_chain(target: StructureNode, index: _TreeIndex) -> list[StructureNode]:
    """Return the target's ancestor chain, target first, root last.

    Cycles and dangling parent ids are guarded: the walk stops at the first
    missing node or an already-visited id.
    """
    chain = [target]
    seen = {target.node_id}
    cursor = index.parent_of.get(target.node_id)
    while cursor is not None:
        node = index.by_id.get(cursor)
        if node is None or node.node_id in seen:
            break
        chain.append(node)
        seen.add(node.node_id)
        cursor = index.parent_of.get(node.node_id)
    return chain


def _top_level_ancestor(target: StructureNode, index: _TreeIndex) -> StructureNode:
    """Return the root of the target's ancestor chain (target itself if top)."""
    chain = _walk_chain(target, index)
    return chain[-1]


def _numbered_section(target: StructureNode, index: _TreeIndex) -> StructureNode | None:
    """Return the nearest ancestor-or-self that is a numbered non-part node."""
    for node in _walk_chain(target, index):
        if node.number is not None and node.kind != "part":
            return node
    return None
