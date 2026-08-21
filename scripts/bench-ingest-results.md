# Ingest Core-Scaling Diagnostic Results

Date: 2026-08-18
Corpus: generated plain-text corpus, 8 files

## Measured table (verbatim)

| cores | wall_s | files/s | peak_rss_MB | success |
|-------|--------|---------|-------------|---------|
| 1 | 7.85 | 1.02 | 684.77 | 8 |
| 2 | 8.25 | 0.97 | 684.77 | 8 |
| 4 | 9.14 | 0.88 | 684.77 | 8 |
| 8 | 9.84 | 0.81 | 689.70 | 8 |

## Computed metrics

- `n_files` = 8 (from `success` column; all rows = 8)
- `N_opt` = 1 (minimum `wall_s` = 7.85, achieved at `cores=1`)
- `rss_ratio` = 1.007 = (peak_rss at `cores=8`, the largest tested = 689.70 MB) / (peak_rss at `cores=2` = 684.77 MB)
- `max_tested_cores` = 8
- `wall_max` / `wall_min` = 9.84 / 7.85 = 1.254

## Arithmetic

- rss_ratio = 689.70 / 684.77 = 1.007199497641544
- wall_max / wall_min = 9.84 / 7.85 = 1.2535031847133757

## Rule application (fixed total order, first match wins)

1. CONFIRMED requires `N_opt < max_tested_cores` (1 < 8 ✓) AND `rss_ratio >= 1.5` (1.007 < 1.5 ✗) → not met.
2. EMBEDDING requires `wall_max / wall_min <= 1.2` (1.254 > 1.2 ✗) → not met.
3. NONE otherwise → met.

VERDICT: NONE. Wall time rises with core count (1.254x from 1 to 8 cores) and peak RSS is flat (ratio 1.007), so no scaling bottleneck is confirmed and the run is not embedding-bound.
