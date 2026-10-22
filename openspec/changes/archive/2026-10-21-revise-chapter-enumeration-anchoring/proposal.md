# Chapter Enumeration Anchoring from Document Evidence — Proposal

## Why

"Summarize by chapter" on `/home/bchand/UserManual.pdf` (VirtualBox 7.2,
1200 stored pages) enumerated only 9 of 18 chapters, summarized 5 of those
from the wrong content (ToC rows, §1.2 feature prose, license texts), and
emitted one placeholder. Reproduced exactly with the LLM stubbed and traced
pin-by-pin (tier replay against live Qdrant). Derived page ranges were:

```
{1:(3,3), 5:(4,4), 6:(5,21), 7:(22,22), 8:(23,23), 15:(24,598),
 16:(599,658), 17:(659,947), 18:(948,∞)}
```

Root causes, all general (not document-specific):

1. **Offset-0 books get no footer offset.** `_FOOTER_PAGE_RE`
   (`fast_text.py:79`) only matches `"N / M"` footers; this book's
   1,222 bare-number footers (`29`, `125`, `271`) never parse, so
   `footer_page_offset()` returns `None` even though footers agree
   perfectly (printed == stored). Line 147 additionally rejects
   `printed == physical` (`0 < printed < physical`), so offset-0 books are
   structurally impossible to resolve.
2. **The strongest chapter signal is never used as a pin tier.** Every
   chapter's first numbered section heading (`N.1`, heading-role chunk)
   sits at its true opener region — verified for all 18 chapters
   (1.1@20, 2.1@29, 3.1@43, 4.1@47, 5.1@51, 6.1@89, 7.1@103, 8.1@125,
   9.1@143, 10.1@161, 11.1@175, 12.1@235, 13.1@237, 14.1@263, 15.1@271,
   16.1@469, 17.1@475, 18.1@481). The pipeline instead relies on
   title-anchor and digit scans that misfire on this class of book
   (banner-less openers, title-like mid-chapter headings).
3. **Weak anchors run first and pre-empt strong evidence.** The
   heading-title anchor pass (Tier 1) pinned ch7 to the §1.2 feature
   heading "Guest Additions" @22, ch16 to the license heading
   "REFERENCES" @599 (case-insensitive sub-word match), and dropped the
   one true anchor it found (ch17 @480, the Change Log page) because the
   false ch16@599 pin won monotone selection by cardinality.
4. **Scan tiers pin from front-matter noise.** `sec_header_re` matched
   `1.1`/`5.1`/`6.1` inside ToC rows that docling left as body chunks
   (pages 3–5); the body-title scan matched the §1.3 cross-reference
   sentence "15 VBoxManage on page 271, the command-line…" @24 (it lacks
   the `on page NNN` guard the section scan has); the loose-digit scan
   pinned ch8@23, ch17@659, ch18@948 from digits in prose/license text.
5. **Run-on ToC recovery found 11 correct openers and threw them away.**
   It recovered (title, printed page) for 11 chapters whose printed
   numbers equal the stored pages (2→29, 3→43, 7→103, 8→125, 9→143,
   10→161, 11→175, 12→235, 14→263, 15→271, 17→475 — all verified against
   stored body pages), but the tier hard-requires a footer offset, which
   cause 1 made unavailable.
6. **Chapters without a page range vanish silently.** Ranges are built
   only for pinned chapters; 2, 3, 4, 9–14 (sandwiched between false pins
   with <2-page gaps, where interpolation refuses) got no range and were
   omitted from the output with no placeholder — the placeholder exists
   only for chapters *with* a range and an empty bucket.
7. **Stale prompt rule.** `config/rag.py` rule 12 hard-codes "21 chapters"
   from a previous document.

## What Changes

- **Footer offset accepts bare-number footers and offset 0**
  (`document/fast_text.py`): optional `/total` suffix, `printed <= physical`
  majority gate. Books whose ToC/footer numbers are physical positions
  (very common for regenerated PDFs) now resolve.
- **New section-heading evidence tier (first pin tier)**: chapter N is
  pinned provisionally at the page of its first `N.1` heading-role chunk
  (minus one page when that page carries body chunks — opener intro;
  else at the heading's page; ±1-page precision documented). Runs before
  all other tiers, guarded by the front-matter floor, boilerplate pages,
  and a dot-leader density guard (ToC rows in heading role must not pin).
- **Evidence-validated offset for run-on ToC rows**: when the footer
  offset is unavailable, derive the printed→stored offset as the majority
  of (N.1 heading page − recovered printed page) across recovered rows;
  refuse the tier when no majority exists. Run-on/listing pins (exact
  printed-page evidence) now *override* provisional section-heading pins
  instead of skipping them; fuzzy anchors never override either.
- **Heading-title anchors matched at token granularity**: whole-token,
  case-insensitive match of every roster-title token in the heading
  (whitespace-squash comparison retained for glued/spaced variants),
  with a small token-count slack for version suffixes. Kills
  "REFERENCES"→"Reference" and "Change logs are also available at:"→
  "Change Log" without breaking ALL-CAPS or glued/spaced openers.
  ToC-pin precedence over anchors is deliberately reversed (ToC printed
  pages are exact evidence; anchors are fuzzy) — one existing test is
  updated to encode the new order.
- **Cross-reference and ToC-page guards on scans**: the body-title scan
  gains the `on page NNN` cross-reference guard; the section-number and
  loose-digit scans skip dot-leader-dense (ToC-like) pages.
- **Enumeration completeness safety net**: every roster chapter is
  enumerated; a chapter with no derived page range is emitted with the
  explicit "no document content was retrieved" placeholder instead of
  vanishing.
- **Prompt rule 12 made count-agnostic** (no hard-coded chapter count).

## Impact

- **Spec delta**: `rag-pipeline` (chapter enumeration anchoring).
- **Code**: `document/fast_text.py` (footer pattern + offset-0 gate),
  `rag/pipeline/_pipeline.py` (new tier wiring, override semantics,
  range-completeness), `rag/pipeline/_structure_mixin.py` (evidence tier,
  token anchors, evidence offset, scan guards), `config/rag.py` (rule 12).
- **Compatibility**: banner-bearing books (labeled docling) keep working —
  anchors still fill chapters the evidence tier cannot pin, and the
  monotone-window contract is unchanged. ML4T magazine openings, PVE
  glued-ToC shapes, and slide-deck handling are regression-gated by the
  existing suite.
- **Risks**: the new tier could pin a chapter at a ToC-like heading-role
  chunk on a mislabeled page (mitigated by the dot-leader guard and the
  front-matter floor); run-on override changes pin precedence for chapters
  where an anchor was previously preferred (deliberate, covered by tests).
- **Verification**: unit fixtures for eight document archetypes
  (offset-0/bare-footers, printed-offset footers, footer-less evidence
  only, banner-less numbered, glued ToC, magazine openings, ALL-CAPS
  headings, unnumbered tail chapters), the existing regression suite, and
  a live end-to-end rerun against the real ingested VirtualBox manual
  expecting all 18 chapters enumerated with correct/near-correct ranges.
