"""Unit tests for audio structure capture + topic segmentation (task 10).

Covers design §5's audio contract: ASR timestamps → ``segment`` nodes with
``t_start``/``t_end``, the no-timestamps degradation to a single
whole-document segment, the dispatcher routing, and the LLM topic
segmentation windowing (≤20 windows, one call per window, failure → []).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from secondbrain.document.structure_capture import (
    audio_topic_segments,
    capture_audio_structure,
    capture_structure,
)
from secondbrain.storage.structure_sqlite import DocumentStructure

pytestmark = pytest.mark.unit


def asr_item(text: str, start: float | None, end: float | None) -> Any:
    """A docling-shaped ASR segment: TextItem with TrackSource timestamps."""
    source = (
        [SimpleNamespace(start_time=start, end_time=end, voice="SPEAKER_00")]
        if start is not None and end is not None
        else []
    )
    return SimpleNamespace(text=text, label="TEXT", source=source, prov=[])


def asr_document(*items: Any) -> Any:
    return SimpleNamespace(texts=list(items))


class TestCaptureAudioStructure:
    def test_timestamped_segments_become_segment_nodes(self, tmp_path: Path) -> None:
        path = tmp_path / "talk.m4a"
        doc = asr_document(
            asr_item("today we discuss rockets", 30.0, 60.0),
            asr_item("welcome everyone to the show", 0.0, 30.0),
        )
        tree = capture_audio_structure(doc, path)

        assert tree is not None
        assert tree.source_file == str(path)
        assert tree.sources == {"audio": True}
        assert [n.node_id for n in tree.nodes] == ["seg01", "seg02"]  # time order
        first, second = tree.nodes
        assert first.kind == "segment"
        assert first.level == 1
        assert first.parent_id is None
        assert first.number is None
        assert first.page_start is None
        assert (first.t_start, first.t_end) == (0.0, 30.0)
        assert (second.t_start, second.t_end) == (30.0, 60.0)
        assert first.title == "welcome everyone to the show"
        assert first.heading_path == "Segment 01"

    def test_long_excerpts_cut_on_word_boundaries(self, tmp_path: Path) -> None:
        path = tmp_path / "talk.m4a"
        long_text = " ".join(["word"] * 40)
        tree = capture_audio_structure(
            asr_document(asr_item(long_text, 0.0, 5.0)), path
        )

        assert tree is not None
        title = tree.nodes[0].title
        assert len(title) <= 60
        assert title.split() == ["word"] * (len(title.split()))
        # Word-aligned cut: the excerpt stays a prefix of the collapsed text.
        assert " ".join(long_text.split()).startswith(title)

    def test_no_timestamps_degrades_to_single_whole_document_segment(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "talk.m4a"
        doc = asr_document(
            asr_item("first words without any timestamps", None, None),
            asr_item("more words", None, None),
        )
        tree = capture_audio_structure(doc, path)

        assert tree is not None
        assert len(tree.nodes) == 1
        only = tree.nodes[0]
        assert only.node_id == "seg01"
        assert (only.t_start, only.t_end) == (0.0, None)
        assert only.title == "first words without any timestamps"

    def test_empty_document_yields_none(self, tmp_path: Path) -> None:
        assert capture_audio_structure(asr_document(), tmp_path / "talk.m4a") is None
        assert (
            capture_audio_structure(asr_document(asr_item("   ", 1.0, 2.0)), tmp_path)
            is None
        )
        assert capture_audio_structure(None, tmp_path / "talk.m4a") is None

    def test_never_raises_on_hostile_items(self, tmp_path: Path) -> None:
        hostile = SimpleNamespace(text=object(), label=None, source=object(), prov=1)
        assert capture_audio_structure(asr_document(hostile), tmp_path) is None


class TestDispatcherRouting:
    def test_audio_file_type_routes_to_audio_capture(self, tmp_path: Path) -> None:
        path = tmp_path / "talk.m4a"
        doc = asr_document(asr_item("hello world", 0.0, 3.5))
        tree = capture_structure(path, docling_doc=doc, file_type="audio")
        assert tree is not None
        assert [n.node_id for n in tree.nodes] == ["seg01"]
        assert (tree.nodes[0].t_start, tree.nodes[0].t_end) == (0.0, 3.5)

    def test_audio_suffix_without_file_type_hint_routes_too(
        self, tmp_path: Path
    ) -> None:
        path = tmp_path / "talk.m4a"
        tree = capture_structure(path, docling_doc=None, file_type="")
        assert tree is None  # no ASR document → honest degrade

    def test_audio_without_asr_document_degrades_to_none(self, tmp_path: Path) -> None:
        assert (
            capture_structure(
                tmp_path / "talk.m4a", docling_doc=None, file_type="audio"
            )
            is None
        )


class FakeLLM:
    """Records prompts; returns a fixed title."""

    def __init__(self, reply: str = "Space Rockets", fail: bool = False) -> None:
        self.prompts: list[str] = []
        self._reply = reply
        self._fail = fail

    def generate(
        self, prompt: str, temperature: float = 0.7, max_tokens: int = 4096
    ) -> str:
        self.prompts.append(prompt)
        if self._fail:
            raise RuntimeError("llm down")
        return self._reply


class TestAudioTopicSegments:
    def _tree(self, segment_count: int, t_end: float = 100.0) -> DocumentStructure:
        from secondbrain.storage.structure_sqlite import StructureNode

        step = t_end / segment_count
        return DocumentStructure(
            source_file="/tmp/talk.m4a",
            nodes=[
                StructureNode(
                    node_id=f"seg{i + 1:02d}",
                    kind="segment",
                    level=1,
                    title=f"excerpt {i + 1}",
                    t_start=i * step,
                    t_end=(i + 1) * step,
                    heading_path=f"Segment {i + 1:02d}",
                )
                for i in range(segment_count)
            ],
            sources={"audio": True},
        )

    def test_one_row_per_segment_node_with_window_titles(self) -> None:
        tree = self._tree(4)
        llm = FakeLLM()
        texts = ["transcript part one about engines ", "more transcript text " * 30]

        rows = audio_topic_segments(tree, texts, llm=llm)

        assert len(rows) == 4
        assert [row.seg_id for row in rows] == [1, 2, 3, 4]
        assert rows[0].t_start == 0.0
        assert rows[-1].t_end == 100.0
        assert all(row.title == "Space Rockets" for row in rows)
        # One LLM call per window (≤4 nodes → ≤4 windows).
        assert len(llm.prompts) == 4
        assert "[0.0s]" in llm.prompts[0] or "[" in llm.prompts[0]

    def test_windows_bounded_to_max_windows(self) -> None:
        tree = self._tree(60)
        llm = FakeLLM()
        texts = ["word " * 500]

        rows = audio_topic_segments(tree, texts, llm=llm, max_windows=20)

        assert len(rows) == 60  # one row per node, titles shared per window
        assert len(llm.prompts) == 20

    def test_no_llm_or_no_segments_yields_empty(self) -> None:
        assert audio_topic_segments(self._tree(3), ["text"], llm=None) == []
        treeless = DocumentStructure(source_file="/tmp/x.pdf", nodes=[])
        assert audio_topic_segments(treeless, ["text"], llm=FakeLLM()) == []

    def test_llm_failure_yields_empty(self) -> None:
        assert (
            audio_topic_segments(self._tree(2), ["text " * 50], llm=FakeLLM(fail=True))
            == []
        )

    def test_empty_transcript_yields_rows_with_none_titles(self) -> None:
        rows = audio_topic_segments(self._tree(2), [], llm=FakeLLM())
        assert len(rows) == 2
        assert all(row.title is None for row in rows)
