# Data provenance and validation

## Source and limits

- Source: [noahx1 / Elden Ring Steam Reviews on Kaggle](https://www.kaggle.com/datasets/noahx1/elden-ring-steam-reviews).
- Local input: `data/raw/elden_ring_steam_reviews.csv` (not distributed in this repository).
- Inspected SHA-256: `f2dd7890ce8bb04a5ab4eabbb2ef7be23ffde54c1d9ecad45dc3c3e954c38c53`.
- Licence: prior inspection reported Kaggle listing CC0; independent verification
  is pending because the source page was not readable through the inspection tool.
  Do not describe the licence as independently confirmed.
- Collection filters, completeness, and source timestamp timezone are unverified.

The local file has 9,794 rows and 16 columns. All language values are `english`,
which is metadata rather than a verified language judgement. Reviews span
2023-01-29 14:32:52 through 2023-03-07 14:19:11 in the source's unspecified timezone.
This is a short historical snapshot, not a complete game history or a random
sample of all Steam players. Recommendation counts are 9,201 true and 593 false.

There are 31 blank reviews and 4,711 nonblank reviews with five or fewer
whitespace-separated words. Nonblank text has 357 exact repeated-text groups
(1,421 occurrences beyond the first in each group), or 363 groups and 1,800
additional occurrences after Unicode/case/whitespace normalisation. Repetition
does not establish spam, coordination, or illegitimacy.

## Validation policy

All required columns must exist; extra columns are preserved and listed. Duplicate
or blank column names, malformed rows, invalid UTF-8, an empty dataset, and
missing/invalid/duplicate IDs stop processing. IDs are nonempty ASCII digit strings:
leading zeroes survive and IDs are never converted to numbers.

Every original field is retained as text in the in-memory `raw` table. A separate
`validated` table contains parsed values; neither table is exported in Milestone 1.
Literal review strings such as `NA` and `null` remain text. Only empty/whitespace
review strings are blank. Markup, punctuation, negation, and line endings inside
review fields are not cleaned at this stage.

- Booleans accept case-insensitive `true` or `false`, with surrounding whitespace
  stripped for parsing. `0`, `1`, and arbitrary nonempty strings are rejected.
- Dates require `YYYY-MM-DD HH:MM:SS` and valid calendar/time values. No timezone
  or local-time conversion is imposed.
- Numeric fields require nonnegative base-10 integers fitting signed 64-bit storage.
  Negative, fractional, infinite, or missing values are reported rather than filled.
- The original `recieved_for_free` spelling is preserved.
- Invalid/missing scalar fields produce errors and nullable parsed values. No rows
  are dropped. Blank review text produces a warning; other summaries still count
  that record. Missing language metadata produces an error.
- Playtime at review exceeding lifetime playtime produces a consistency warning;
  source values are not changed.

Steam documents `playtime_at_review` and the other playtime fields in **minutes**.
The CSV's `author_` fields are treated as corresponding source fields; no conversion
is needed for the foundation report. Later comparisons will derive hours using
`author_playtime_at_review / 60`, not observed lifetime playtime.
[Steam field definitions](https://partner.steamgames.com/doc/webapi/IUserReviewsService?language=english)

Duplicate normalisation uses Unicode NFKC, case folding, and whitespace collapse.
It is solely a grouping key. Blank reviews are excluded from duplicate counts;
repeated texts remain separate records. Near-duplicate grouping and evaluation
splits are future work, not established by these summary counts.

## Reproducibility

`summary.json` is independent of machine paths, run times, and output directory.
`issues.csv` has deterministic ordering. `run.json` separately records run times,
absolute local paths, package versions, settings, and the checksum of the bytes
actually parsed. Settings include seed 42, although full-input validation does
not sample or use randomness. The summary has no stochastic operations.

For a repeatability check, run validation twice with different output folders and
compare `summary.json` and `issues.csv` byte-for-byte. Run manifests will differ.
A changed input should change the checksum. A successful summary does not verify
that language labels, recommendations, or review statements are true.

Dependencies follow the official [Pandas installation guidance](https://pandas.pydata.org/docs/getting_started/install.html),
[Pytest setup guidance](https://docs.pytest.org/en/stable/getting-started.html),
and [pip repeatable-install guidance](https://pip.pypa.io/en/stable/topics/repeatable-installs/).
The tested versions are recorded in `requirements-lock.txt`; no model is installed.
