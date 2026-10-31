# Design

## Context

See `proposal.md` — Why. Current mechanics (all in
`src/secondbrain/rag/pipeline/_fallback_mixin.py` unless noted):

- Callers pre-split the source: `_generate_single_chapter_summary` (L666),
  the multi-chapter loop (L627), the anthology path (L758) and the
  whole-document fallback (L840) all call `_split_bounded(chunks)` (default
  `_SUMMARY_WINDOW_CHARS = 3500`, page-sorted, sentence-aligned), then pass
  `windows=` into `_summarize_bounded` (L970).
- `_summarize_bounded` formats each window via `_format_context` capped at
  `rag_max_context_chars` (16k), single-passes when the formatted sum fits
  `_SINGLE_PASS_MAX_CHARS` (320k), else maps one digest per window and
  reduces once. The cap at L1008-1016 is a silent `windows[:50]` slice when
  `len(windows) > _MAX_MAP_REDUCE_WINDOWS (50)`.
- `_reduce_digest_overview` (L1124) picks framing at L1178-1198: the digest
  framing unconditionally says "cover every part in order".
- The whole-document fallback (L817-847) is the precedent for honest notes:
  `_WHOLE_DOCUMENT_OVERVIEW_NOTE` is streamed via `_on_chunk` AND returned
  as part of the text, keeping display and storage byte-identical.
- `document/summarizer.py::_window_excerpts` (L497-529) mirrors the defect at
  the CLI layer: hard budget `max_input_chars × max_windows` (16k × 8) drops
  trailing excerpts head-fully.

## Goals / Non-Goals

**Goals:**

- Full-source coverage within the existing map-call/window budgets
  (no increase in LLM-call count, temperature, or token caps).
- Honest disclosure whenever coverage must be partial (note + framing),
  through both the display and storage channels.
- Mirror the same contract in the CLI summarizer.
- The three cheap chat-UX repairs (F2 thinking-stream separators + per-window
  progress, F3 spinner pause around log emits, F5 intent progress label) ride
  along without spec-level change (the reasoning-display policy is already
  specified in `conversational-rag`).

**Non-Goals:**

- Concurrent map digests (F4) — deferred; the sequential map pass is
  unchanged.
- `_map_reduce_stream`'s separate `items[:_MAX_MAP_REDUCE_WINDOWS]` slice
  (L1646): that path fans out one generation per pre-formed heading/section
  summary, where 50 items is a genuine pathology ceiling; its docstring
  already documents the intent. Left unchanged.
- Any change to `_SINGLE_PASS_MAX_CHARS`, `_MAP_DIGEST_MAX_TOKENS`,
  `_SUMMARY_REDUCE_MAX_TOKENS`, or streaming guards. (`_OVERVIEW_MAX_WORDS`
  was originally excluded too, but verification exposed its 1200 ceiling
  trimming a legitimate 1255-word draft — see D6.)

## Decisions

### D1 — Adaptive re-split inside `_summarize_bounded`, callers untouched

When the incoming `windows` exceed the map-call limit, flatten them back
into chunks (window boundaries are plain grouping) and re-split with
`_split_bounded(chunks, max_chars=adaptive)` before formatting contexts.
Callers keep passing their default 3500-char pre-splits; only the oversized
path re-splits.

- *Alternative rejected:* change callers to pass raw chunks — touches four
  call sites and the whole-document path (which samples first) for no
  behavioral gain.
- Adaptive size: `adaptive = max(_SUMMARY_WINDOW_CHARS,
  ceil(total_source_chars / _MAX_MAP_REDUCE_WINDOWS))`, clamped to a new
  `_MAX_SUMMARY_WINDOW_CHARS = 8_000` (about 2.3× today's window; keeps the
  formatted context comfortably under the 16k `rag_max_context_chars` cap at
  the observed ~2× formatting overhead). Chapter 15 needs
  ceil(393k/50) ≈ 7.9k → fits under 8k, so it takes the full-coverage path.

### D2 — Spread-sample fallback when the floor binds

Only when `ceil(total / 50) > _MAX_SUMMARY_WINDOW_CHARS` (i.e. a source
above ~400k source chars) is full coverage impossible. Then sample chunks
evenly across the full page range via the existing `_page_spread_sample`
pattern — the limit is sized from the mean chunk length so the sampled
total fits `50 × _MAX_SUMMARY_WINDOW_CHARS` — re-split the sample at its
own adaptive size, and set `partial_coverage = True`. Never a
head-truncation slice.

### D3 — Coverage note and framing plumbing

- New constant `_CHAPTER_PARTIAL_COVERAGE_NOTE`, mirroring
  `_WHOLE_DOCUMENT_OVERVIEW_NOTE` in style and placement ("the overview
  below is built from an evenly spread sample of the chapter; its coverage
  is partial").
- Emission mirrors `_generate_whole_document_overview` (L834-847): the note
  goes to `_on_chunk` (content channel, with its `\n\n` separator) AND into
  the returned text ahead of the overview. It is emitted inside
  `_summarize_bounded` — after the caller-streamed heading, before the
  overview — so all four call sites get note + parity for free.
- `_reduce_digest_overview` gains a `partial_coverage: bool = False`
  parameter; when true the digest framing swaps "cover every part in order"
  for sample framing ("the digests below cover an evenly spread sample of
  {heading}, in reading order; write the overview from this sample; do not
  present it as the complete source"). The single-pass framing
  (`parts_are_digests=False`) is untouched — it is complete by construction.

### D4 — CLI summarizer mirror (`document/summarizer.py`)

`_window_excerpts` keeps its signature and contract; internally it delegates
to a planner returning `(windows, partial)`:

- `ceil(total / max_input_chars) <= max_windows` → greedy windows over the
  full source at adaptive size (windows ≤ `max_input_chars`; size
  `ceil(total / max_windows)` when that exceeds the default) → full
  coverage, no note.
- Otherwise → even-spread sample of the ordered excerpts (index-spread,
  first and last always kept) sized to `max_windows × max_input_chars`,
  then windowed; `partial = True`.
- `_summarize` prepends the note constant to the final (merged) summary when
  `partial` — the CLI prints it verbatim, same contract as the chat path.

- *Alternative rejected:* return the note via a side channel/attribute —
  the plain-string return is the module's existing contract.

### D5 — Chat-UX repairs (implementation-only)

- **F2 separators**: `_ThinkingStream` (cli/chat_helpers.py L31-150) tracks
  element state; a reasoning emission that arrives when a previous thinking
  element has closed gets a preceding separator, and
  `_separate_before_answer` (L116) stays the boundary before answer content.
  Consecutive map-window reasoning blocks therefore render as distinct
  collapsed elements instead of gluing.
- **F2 progress**: `_map_window_digest` forwards a one-line progress marker
  ("· window i/N") on the reasoning channel ahead of each window's
  reasoning — content channel stays pure (the reasoning-display spec
  forbids non-answer text on the content stream).
- **F3 spinner pause**: the spinner wrapper in `_run_chat_with_spinner`
  (L203) exposes a pause/resume the chat loop takes around log/thinking
  emissions, so Rich spinner frames never interleave with written lines.
  Pause is a no-op when the spinner is not active.
- **F5 intent label**: the broad-coverage label at chat_helpers L334/L553
  appends the parsed target from `rag/intent_parser.py` when present
  ("broad coverage · chapter 15").

### D6 — Overview word ceiling raised to 1600 (added during verification)

The live chapter-15 replay proved the truncation fix but exposed a
pre-existing failure of the `_OVERVIEW_MAX_WORDS = 1200` runaway guard: the
full-coverage map pass produced a legitimate 1255-word, ten-paragraph draft,
and `_finalize_overview` trimmed the **stored** copy at a sentence boundary
("...manage VM snapshots.") while the terminal had streamed the complete
draft — the exact amputation the guard's own rationale says must never
happen to a normal draft. Every other finalize post-pass was a no-op on that
draft (the stored text is a whitespace-normalized prefix of the displayed
text), so the word trim was the sole divergence.

Decision: raise the ceiling to 1600 — headroom above the largest observed
legitimate draft, while genuine runaway loops (historically thousands of
words) stay capped. The rationale comment records the replay evidence, and
unit tests pin both behaviors: a 1255-word draft survives finalization
unchanged, a double-ceiling draft is still cut at a sentence boundary.
Re-verification on the captured replay draft: `_trim_to_word_budget(draft,
1600)` leaves it unchanged, and `_trim_to_word_budget(draft, 1200)`
reproduces the old stored cut exactly.

- *Alternative rejected:* scaling the ceiling with chapter size — a larger
  design change belonging to its own proposal; 1600 covers the observed
  worst case with margin.

## Risks / Trade-offs

- [Larger windows (≈2× source) may make individual digests terser] →
  digest token cap and figure-grounding post-passes are unchanged; the
  reduce stage still reads every digest. Acceptance is the replay check:
  chapter-15 summary must name `modifyvm`, `snapshot`, `storageattach`.
- [Sources above ~400k chars still get partial coverage] → disclosed via
  note + framing; the sample is page-spread with first and last chunks
  always included.
- [Note lands mid-answer in multi-chapter runs] → scoped to the chapter's
  own section (after its heading), which is the honest placement; parity
  contract covered by a unit test.
- [Spinner pause across threads] → pause/resume only act on an active
  spinner owned by the wrapper thread; otherwise no-op, so background
  failure modes degrade to today's interleaving, not worse.
- [Adaptive windows change digest boundaries for previously-capped runs]
  → previously such runs silently lost ~half the source; any change here is
  an improvement, and small-source paths are byte-identical.

## Migration Plan

No config, schema, or API changes. Deploy = merge; rollback = revert.
Verification after apply: `pytest` the four targeted test files, then a
live replay of the chapter-15 request against UserManual.pdf checking the
acceptance criteria (named commands present, ≤50 map calls, parity).
