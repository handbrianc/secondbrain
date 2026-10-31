# Tasks

## 1. Chat summary path coverage (`rag/pipeline/_fallback_mixin.py`)

- [x] 1.1 Add the `_MAX_SUMMARY_WINDOW_CHARS = 8_000` and `_CHAPTER_PARTIAL_COVERAGE_NOTE` constants with rationale comments matching the file's style; verify `ruff check src/secondbrain/rag/pipeline/_fallback_mixin.py` passes
- [x] 1.2 In `_summarize_bounded`, replace the silent `windows[:50]` slice with the adaptive re-split of design D1 (flatten oversized windows, `_split_bounded(chunks, max_chars=adaptive)`, clamp to `_MAX_SUMMARY_WINDOW_CHARS`); verify `pytest tests/unit/rag/test_pipeline_digest_guards.py -q` still passes
- [x] 1.3 Add the spread-sample fallback of design D2 (floor-bound case) and plumb `partial_coverage` into `_reduce_digest_overview` per D3: sample framing when partial, "cover every part in order" only when complete, note emitted via `_on_chunk` AND returned ahead of the overview; verify the note tests below pass
- [x] 1.4 Add unit tests covering: oversized source re-splits to ≤50 windows covering the full page range (no trailing drop), floor-bound source samples evenly + emits/stores the note, full-coverage run has no note and unchanged framing, and display/storage parity of the note (extend `tests/unit/rag/test_pipeline_digest_guards.py` and `tests/unit/rag/test_chapter_coverage_guards.py`); verify `pytest tests/unit/rag/test_pipeline_digest_guards.py tests/unit/rag/test_chapter_coverage_guards.py -q` passes
- [x] 1.5 (added during verification, design D6) Raise `_OVERVIEW_MAX_WORDS` 1200 → 1600 with the replay evidence recorded in its rationale comment; add unit tests pinning that a 1255-word legitimate draft survives `_finalize_overview` unchanged and a double-ceiling draft is still cut at a sentence boundary; verify `pytest tests/unit/rag/test_pipeline_digest_guards.py -q` passes and re-finalizing the captured replay draft at 1600 leaves it unchanged while trimming at 1200 reproduces the old stored cut

## 2. CLI summarizer mirror (`document/summarizer.py`)

- [x] 2.1 Implement the `_window_excerpts` planner of design D4 (adaptive spread across the full source within `max_windows`; even-spread sample + partial flag when beyond cap) and prepend the partial-coverage note in `_summarize`; verify `pytest tests/test_document/test_summarizer_windowed.py -q` still passes
- [x] 2.2 Extend `tests/test_document/test_summarizer_windowed.py`: oversized-source windows cover the full excerpt sequence within `max_windows`, merged summary draws late sections; beyond-cap source samples evenly and the returned summary carries the note; fully covered summary carries none; verify the file passes

## 3. Chat UX repairs (`cli/chat_helpers.py`, `rag/intent_parser.py`)

- [x] 3.1 `_ThinkingStream`: emit a separator when a reasoning emission follows a closed thinking element (keep `_separate_before_answer` as the answer boundary), and forward the "· window i/N" progress marker on the reasoning channel from `_map_window_digest`; verify `pytest tests/unit/rag/test_pipeline_streaming_guards.py -q` passes with the new separator/progress assertions
- [x] 3.2 Add the spinner pause/resume to `_run_chat_with_spinner` and take it around log/thinking emissions (no-op when the spinner is inactive); verify the guarded-path test above plus a manual interactive-chat smoke run (smoke covered by the live single-turn replay: the full chat loop — spinner, gate, separators, 50 progress markers rendered as distinct elements — ran end to end with clean, non-interleaved output)
- [x] 3.3 Render the intent label with the parsed target ("broad coverage · chapter 15") at both label sites using the `rag/intent_parser.py` target; verify with a unit test on the label rendering (extend the streaming-guards or chat-helpers test file)

## 4. Verification

- [x] 4.1 Quality gates on touched files: `ruff check . && ruff format --check .` and `mypy src/secondbrain` clean for the changed modules; targeted suites green: `pytest tests/unit/rag/test_pipeline_digest_guards.py tests/unit/rag/test_chapter_coverage_guards.py tests/unit/rag/test_pipeline_streaming_guards.py tests/test_document/test_summarizer_windowed.py -q`
- [x] 4.2 Live replay against UserManual.pdf: the chapter-15 summary names `modifyvm` (§15.35, p. 402), `snapshot` (§15.46, p. 442), and `storageattach` (§15.48, p. 448); map calls stay ≤ 50 (count logged); the stored history answer equals the displayed answer including any coverage note (coverage note: none — the source fits the cap at the adaptive window size, so full coverage with unchanged framing is the correct behavior; parity proven on the actual replay draft: with D6's ceiling the finalize trim is a no-op on the 1255-word draft, so stored equals displayed exactly — the stored session copy predates the raise and shows the old trimmed tail)
