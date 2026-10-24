"""Inspect a document's stored structure tree (``secondbrain structure``).

Reads the per-document structure captured at ingest time — heading nodes
(parts/chapters/sections/subsections) with physical page ranges and printed
page labels, plus audio segments — from the structure store
(:class:`secondbrain.storage.structure_sqlite.StructureStore`) and renders it
in the same Rich style as the other inspection commands. Documents ingested
before structure-aware ingestion have no stored tree and get explicit
re-ingest guidance (exit 0); unknown sources fail with a clean, non-zero
error.

The tree key is the *exact* ``source_file`` string stored in the qdrant
payload — the path exactly as it was passed to ``secondbrain ingest``
(``str(path)``, never resolved) — so :func:`resolve_source_file` accepts a
path or source key and reconciles relative/absolute spellings before falling
back to an unambiguous basename match over the ingested sources.
"""

from __future__ import annotations

import contextlib
import logging
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import click
from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from secondbrain.cli import cli
from secondbrain.cli.errors import handle_cli_errors

if TYPE_CHECKING:
    from secondbrain.storage.structure_sqlite import (
        AudioSegment,
        DocumentStructure,
        PageLabelRange,
        StructureNode,
        StructureStore,
    )

logger = logging.getLogger(__name__)
console = Console(markup=True)


@dataclass(frozen=True)
class ResolvedSource:
    """Outcome of resolving a CLI argument to a stored ``source_file`` key.

    Attributes:
        source_file: The resolved key, or ``None`` when unresolved.
        candidates: Stored keys matching the argument; populated only when
            the match is ambiguous, so the error can list them.
    """

    source_file: str | None = None
    candidates: list[str] = field(default_factory=list)


def _open_structure_store() -> StructureStore:
    """Open the structure store on the configured shared SQLite database.

    Returns
    -------
        A fresh :class:`StructureStore` bound to ``cfg.sqlite_path``.
    """
    from secondbrain.storage.structure_sqlite import StructureStore

    return StructureStore()


def _list_source_keys() -> list[str]:
    """Enumerate the ingested ``source_file`` keys, best-effort.

    The vector store's ``source_file`` payload values are the authoritative
    key set — the structure-store contract pins tree keys to exactly those
    strings. Enumeration is only needed for the fallback resolution and for
    telling "ingested but treeless" apart from "unknown", so every failure
    degrades to an empty list instead of failing the command.

    Returns
    -------
        The distinct stored ``source_file`` strings, or ``[]`` when the
        vector store is unreachable.
    """
    from secondbrain.storage import StorageFactory

    try:
        storage = StorageFactory.create_from_config()
    except Exception as e:
        logger.debug(
            "Could not create vector storage for source-key enumeration: %s: %s",
            type(e).__name__,
            e,
        )
        return []
    try:
        return list(storage.list_source_files())
    except Exception as e:
        logger.debug(
            "Could not enumerate source keys (%s: %s); structure lookups "
            "fall back to exact and path-normalized matches only",
            type(e).__name__,
            e,
        )
        return []
    finally:
        storage.close()


def _path_variants(doc: str) -> list[str]:
    """Return the normalized/absolute spellings of *doc* ingest may have stored.

    Ingest keys trees by ``str(Path(user_input))`` — the path as passed, never
    resolved — so a relative-vs-absolute mismatch is reconciled by trying
    ``str(Path(doc))`` (separator/``.`` normalization), ``Path.absolute()``
    (cwd-joined) and ``Path.resolve()`` (symlinks and ``..`` collapsed), in
    that order.

    Args:
        doc: The user-supplied path or source key.

    Returns
    -------
        Deduplicated variants that differ from the verbatim argument.
    """
    try:
        path = Path(doc)
    except OSError, ValueError:  # e.g. embedded NUL byte
        return []
    variants = [str(path), str(path.absolute())]
    with contextlib.suppress(OSError):
        variants.append(str(path.resolve()))
    unique: list[str] = []
    for variant in variants:
        if variant != doc and variant not in unique:
            unique.append(variant)
    return unique


def _ends_with_path(key: str, tail: str) -> bool:
    """Check whether *key* ends with *tail* at a path-component boundary.

    Args:
        key: A stored ``source_file`` key.
        tail: The user-supplied path suffix to look for.

    Returns
    -------
        True when *key* ends with *tail* and the character before the match
        (if any) is a path separator, so ``a/x.pdf`` never matches ``x.pdf``
        inside ``max.pdf``.
    """
    if not key.endswith(tail):
        return False
    boundary = len(key) - len(tail)
    return boundary == 0 or key[boundary - 1] in "/\\"


def resolve_source_file(
    store: StructureStore,
    doc: str,
    stored_keys: Sequence[str] | None,
) -> ResolvedSource:
    """Resolve a CLI *doc* argument to the exact stored ``source_file`` key.

    Ingest stores the tree under the path string exactly as it was passed to
    ``secondbrain ingest`` (``str(path)`` — never resolved), and the qdrant
    payload ``source_file`` carries the same string, so lookups must find that
    exact string. Resolution proceeds cheapest-first:

    1. The argument itself, verbatim (the common case: the same path the
       document was ingested with).
    2. Normalized/absolute spellings of the argument (``str(Path(doc))``,
       ``Path.absolute()``, ``Path.resolve()``) — covers a relative-vs-
       absolute mismatch when the working directory matches the ingest-time
       one.
    3. Key-set fallback over *stored_keys* (the vector-store enumeration):
       keys ending with the argument at a path boundary, then keys sharing
       the argument's basename. Unique only — a single candidate resolves;
       when several match, candidates that actually hold a stored tree are
       preferred, and if that is still ambiguous the candidates are returned
       unresolved for the error listing.

    Args:
        store: The structure store to look trees up in.
        doc: The user-supplied path or source key.
        stored_keys: The ingested ``source_file`` keys (vector store
            enumeration), or ``None`` when enumeration is unavailable.

    Returns
    -------
        A :class:`ResolvedSource` with ``source_file`` set on success, or
        ``None`` alongside the ambiguous candidate list (empty for unknown
        sources).
    """
    if doc and store.load_tree(doc) is not None:
        return ResolvedSource(source_file=doc)

    for variant in _path_variants(doc):
        if store.load_tree(variant) is not None:
            return ResolvedSource(source_file=variant)

    if stored_keys is None or not doc:
        return ResolvedSource()

    name = Path(doc).name
    tiers: dict[int, list[str]] = {3: [], 2: [], 1: []}
    for key in stored_keys:
        if key == doc:
            tiers[3].append(key)
        elif _ends_with_path(key, doc):
            tiers[2].append(key)
        elif Path(key).name == name:
            tiers[1].append(key)
    candidates = [key for rank in (3, 2, 1) for key in tiers[rank]]

    if not candidates:
        return ResolvedSource()

    treeful = [key for key in candidates if store.has_tree(key)]
    if len(treeful) == 1:
        return ResolvedSource(source_file=treeful[0])
    if len(candidates) == 1:
        return ResolvedSource(source_file=candidates[0])
    return ResolvedSource(candidates=candidates)


def _format_timestamp(seconds: float) -> str:
    """Render a media timestamp as ``mm:ss`` (``h:mm:ss`` past one hour)."""
    total = max(0, int(seconds))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def _format_page_range(node: StructureNode) -> str | None:
    """Render a node's physical page range as ``p. N`` / ``pp. N-M``."""
    if node.page_start is None:
        return None
    if node.page_end is None or node.page_end == node.page_start:
        return f"p. {node.page_start}"
    return f"pp. {node.page_start}–{node.page_end}"  # noqa: RUF001 - display format


def _label_lookup(page_labels: Sequence[PageLabelRange]) -> dict[int, str]:
    """Map each covered physical page to its printed ``/PageLabels`` label."""
    lookup: dict[int, str] = {}
    for label_range in page_labels:
        for page in range(label_range.page_start, label_range.page_end + 1):
            lookup[page] = label_range.label
    return lookup


def _printed_range(lookup: dict[int, str], node: StructureNode) -> str | None:
    """Render the printed page labels a node's page span maps to.

    Args:
        lookup: Page → printed label map from :func:`_label_lookup`.
        node: The tree node to decorate.

    Returns
    -------
        ``"printed i"``, ``"printed 3-8"`` etc., or ``None`` when neither
        the node's start nor end page carries a known label.
    """
    if node.page_start is None:
        return None
    start_label = lookup.get(node.page_start)
    end_label = lookup.get(
        node.page_end if node.page_end is not None else node.page_start
    )
    if start_label is None and end_label is None:
        return None
    if start_label is None:
        return f"printed {end_label}"
    if end_label is None or end_label == start_label:
        return f"printed {start_label}"
    return f"printed {start_label}–{end_label}"  # noqa: RUF001 - display format


def _node_text(node: StructureNode, lookup: dict[int, str]) -> Text:
    """Build the one-line tree label for a node.

    Format: ``kind [number] — title · pp. 7-12 · printed 3-8`` (pages swap
    for ``mm:ss-mm:ss`` on audio nodes; decorations are omitted when the
    node carries no such data).
    """
    text = Text()
    if node.number:
        text.append(f"{node.kind} {node.number}", style="cyan")
    else:
        text.append(node.kind, style="cyan")
    text.append(f" — {node.title}")
    details: list[str] = []
    page_range = _format_page_range(node)
    if page_range:
        details.append(page_range)
    if node.t_start is not None:
        start = _format_timestamp(node.t_start)
        end = _format_timestamp(node.t_end) if node.t_end is not None else None
        details.append(f"{start}–{end}" if end else start)  # noqa: RUF001 - display format
    printed = _printed_range(lookup, node)
    if printed:
        details.append(printed)
    if details:
        text.append("  ·  " + " · ".join(details), style="dim")
    return text


def _build_tree(structure: DocumentStructure) -> Tree:
    """Build the Rich tree for a stored structure.

    Args:
        structure: The stored document structure.

    Returns
    -------
        A :class:`rich.tree.Tree` rooted at the source key with one branch
        per node, nested by ``parent_id`` (orphans of missing parents surface
        at the top level; cycles are cut).
    """
    lookup = _label_lookup(structure.page_labels)
    children: dict[str | None, list[StructureNode]] = {}
    for node in structure.nodes:
        children.setdefault(node.parent_id, []).append(node)

    known_ids = {node.node_id for node in structure.nodes}
    roots = children.get(None, [])
    roots += [
        node
        for node in structure.nodes
        if node.parent_id is not None and node.parent_id not in known_ids
    ]

    root = Tree(Text(structure.source_file, style="bold cyan"))
    visited: set[str] = set()

    def attach(branch: Tree, nodes: list[StructureNode]) -> None:
        for node in nodes:
            if node.node_id in visited:
                continue  # cycle guard for drifted data
            visited.add(node.node_id)
            child = branch.add(_node_text(node, lookup))
            descendants = children.get(node.node_id)
            if descendants:
                attach(child, descendants)

    attach(root, roots)
    return root


def _render_page_labels(page_labels: Sequence[PageLabelRange]) -> None:
    """Print the stored ``/PageLabels`` runs as a Rich table (when any)."""
    if not page_labels:
        return
    table = Table(title="Printed page labels (/PageLabels)")
    table.add_column("Physical pages", style="magenta", no_wrap=True)
    table.add_column("Printed label", style="cyan")
    table.add_column("Style", style="dim")
    for label_range in page_labels:
        pages = (
            str(label_range.page_start)
            if label_range.page_start == label_range.page_end
            else f"{label_range.page_start}–{label_range.page_end}"  # noqa: RUF001 - display format
        )
        table.add_row(pages, label_range.label, label_range.style or "—")
    console.print()
    console.print(table)


def _render_audio_segments(audio_segments: Sequence[AudioSegment]) -> None:
    """Print the stored audio segments as a Rich table (when any)."""
    if not audio_segments:
        return
    table = Table(title="Audio segments")
    table.add_column("Seg", justify="right", style="cyan", no_wrap=True)
    table.add_column("Start", style="magenta", no_wrap=True)
    table.add_column("End", style="magenta", no_wrap=True)
    table.add_column("Title")
    for segment in audio_segments:
        table.add_row(
            str(segment.seg_id),
            _format_timestamp(segment.t_start),
            _format_timestamp(segment.t_end),
            segment.title or "—",
        )
    console.print()
    console.print(table)


def _render_structure(structure: DocumentStructure) -> None:
    """Render a stored structure: tree, then page labels, then audio."""
    console.print(f"[bold]Document structure[/bold]: {escape(structure.source_file)}")
    meta: list[str] = []
    if structure.captured_at:
        meta.append(f"captured {structure.captured_at}")
    active_sources = sorted(
        key for key, enabled in structure.sources.items() if enabled
    )
    if active_sources:
        meta.append("sources: " + ", ".join(active_sources))
    if meta:
        console.print("[dim]" + escape(" · ".join(meta)) + "[/dim]")
    console.print(_build_tree(structure))
    _render_page_labels(structure.page_labels)
    _render_audio_segments(structure.audio_segments)


def _print_treeless_guidance(source_file: str) -> None:
    """Print the re-ingest guidance shown for documents without a tree."""
    console.print(
        f"[yellow]No stored structure tree for {escape(source_file)}[/yellow]"
    )
    console.print(
        "This document was ingested before structure-aware ingestion (or its "
        "structure could not be captured at ingest time)."
    )
    console.print(
        "Re-ingest it to capture the structure tree — unchanged chunks keep "
        "their stored embeddings; only the structural payload is refreshed:"
    )
    console.print(
        f"  [cyan]secondbrain ingest {escape(source_file)} --no-skip-existing[/cyan]"
    )


@handle_cli_errors
@cli.command()
@click.argument("doc")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Dump the raw stored structure as JSON instead of the rendered tree",
)
def structure(doc: str, as_json: bool) -> None:
    """Inspect the stored structure tree of an ingested document.

    DOC: Path or source key of the document (the same string it was ingested
    with).
    """
    with _open_structure_store() as store:
        resolved = resolve_source_file(store, doc, _list_source_keys())
        if resolved.source_file is None:
            if resolved.candidates:
                console.print(
                    f"[red]Error: '{escape(doc)}' matches multiple stored "
                    "source files[/red]"
                )
                for candidate in resolved.candidates:
                    marker = " (has stored tree)" if store.has_tree(candidate) else ""
                    console.print(f"  - {escape(candidate)}{marker}")
                console.print(
                    "[yellow]Pass one of the paths above exactly as it was "
                    "ingested[/yellow]"
                )
            else:
                console.print(
                    f"[red]Error: no stored document matches '{escape(doc)}'[/red]"
                )
                console.print(
                    "[yellow]Structure lookups use the path exactly as it "
                    "was passed to ingest; run 'secondbrain ls --all' to "
                    "see the stored source paths[/yellow]"
                )
            sys.exit(1)
        tree = store.load_tree(resolved.source_file)

    if tree is None or not (tree.nodes or tree.page_labels or tree.audio_segments):
        _print_treeless_guidance(resolved.source_file)
        return

    if as_json:
        console.print_json(tree.model_dump_json(indent=2))
        return

    _render_structure(tree)
