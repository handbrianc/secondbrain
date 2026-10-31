# Proposal

## Why

Broad-coverage chapter summaries silently truncate oversized sources. In the
audited UserManual.pdf chat sessions, chapter 15 (pp. 271–468, ≈393k source
chars) is split into 99 × 3,500-char windows, but `_summarize_bounded` caps
the map pass at `_MAX_MAP_REDUCE_WINDOWS` (50) with a plain `windows[:50]`
slice — pages ≈368–468 (§15.25–15.55) are dropped with no signal, while the
reduce prompt still asserts the digests "cover every part in order". The
replayed chapter-15 digest consequently never mentions `modifyvm` (§15.35,
p. 402), `snapshot` (§15.46, p. 442), or `storageattach` (§15.48, p. 448),
although the user asked for a full chapter overview. The CLI summarizer
(`secondbrain summarize`) has the same defect: `_window_excerpts` enforces a
hard budget of `rag_max_context_chars × max_windows` (16k × 8 = 128k chars)
by dropping trailing excerpts, keeping only about the first third of
chapter 15. While fixing these two sites, three adjacent chat-UX defects
observed in the same sessions (unseparated thinking streams, spinner/log
interleaving, generic progress label) are fixed cheaply alongside.

## What Changes

- `_summarize_bounded` (`rag/pipeline/_fallback_mixin.py`) stops silently
  truncating: an oversized source is re-split into adaptive windows sized so
  the complete source fits within `_MAX_MAP_REDUCE_WINDOWS` map calls; only
  when a per-window size floor makes full coverage impossible is an even
  page-spread sample taken (reusing the `_page_spread_sample` pattern) —
  never a head-truncation slice.
- A partial-coverage note constant (mirroring `_WHOLE_DOCUMENT_OVERVIEW_NOTE`)
  is emitted to the live stream AND included in the stored answer whenever
  coverage is partial, preserving `_reduce_digest_overview`'s documented
  display/storage parity contract.
- `_reduce_digest_overview`'s digest framing is parameterized by coverage:
  "cover every part in order" applies only when the parts cover the complete
  source; partial runs get honest framing that reflects the partial coverage.
- `document/summarizer.py::_window_excerpts` mirrors the fix: windows spread
  across the full source within `max_windows` (adaptive window size) instead
  of dropping trailing excerpts, with the same partial-coverage disclosure.
- The overview word ceiling `_OVERVIEW_MAX_WORDS` is raised 1200 → 1600
  (added during verification): the live replay's chapter-15 draft was a
  legitimate 1255 words and the old ceiling trimmed the stored copy short of
  what the terminal streamed; 1600 keeps the runaway guard with headroom.
- Chat UX (implementation-only, no spec change): `_ThinkingStream` gains
  separators between consecutive thinking elements and before the answer, the
  map pass reports per-window "· window i/N" progress on the reasoning
  channel, the Rich spinner pauses around log/thinking emissions so frames do
  not interleave, and the intent label shows live progress ("broad coverage ·
  chapter 15").
- Deferred (out of scope): concurrent map digests (audit finding F4).

## Capabilities

### New Capabilities

- `document-summarization`: the bounded-window contract for the CLI document
  summarizer (`secondbrain summarize`): windows must spread across the full
  source within the window cap, and partial coverage must be disclosed,
  never silent.

### Modified Capabilities

- `rag-pipeline`: adds coverage/disclosure requirements for the bounded-window
  chapter and overview summary path (`_summarize_bounded` /
  `_reduce_digest_overview`): full source coverage via adaptive window
  sizing, a spread-sample fallback with an honest partial-coverage note, and
  coverage-aware reduce framing — all with display/storage parity.

## Impact

- **Code**: `src/secondbrain/rag/pipeline/_fallback_mixin.py` (adaptive
  re-split, spread-sample fallback, note constant, framing parameter);
  `src/secondbrain/document/summarizer.py` (`_window_excerpts`, disclosure);
  `src/secondbrain/cli/chat_helpers.py` + `src/secondbrain/rag/intent_parser.py`
  (thinking-stream separators, spinner pause, progress label).
- **Tests**: `tests/unit/rag/test_pipeline_digest_guards.py`,
  `tests/unit/rag/test_chapter_coverage_guards.py`,
  `tests/unit/rag/test_pipeline_streaming_guards.py`,
  `tests/test_document/test_summarizer_windowed.py`.
- **Behavior**: map-call budget stays ≤ 50 (chat path) / ≤ `max_windows`
  (CLI path); per-window source size grows (≈7.9k chars for chapter 15,
  still well under the 16k formatted-context cap). Window ordering
  (page-sorted, sentence-aligned boundaries), temperature, and token caps are
  unchanged. The overview word ceiling rises 1200 → 1600.
- **Acceptance**: a replayed chapter-15 summary names `modifyvm`, `snapshot`,
  and `storageattach`; map calls stay ≤ 50; the stored answer equals the
  displayed answer (parity), including any coverage note.
