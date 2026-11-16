# Reproducible exploratory data analysis

PlayerLens explores a local Elden Ring Steam-review snapshot before building any
aspect or opinion analysis. EDA describes the data; it does not classify review
topics, infer sentiment, or measure model performance.

## Environment and local commands

Use 64-bit Python 3.13 from the repository root. The tested Windows environment is
pinned in `requirements-lock.txt`; `pyproject.toml` declares direct dependencies.
Pandas provides tables/calculations and Matplotlib renders static figures. NumPy
is already a Pandas dependency and supplies the plotted log transformation.

Initial environment setup requires explicit permission for network access:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --cache-dir .cache/pip --only-binary=:all: -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-index --no-build-isolation --no-deps -e .
.\.venv\Scripts\python.exe -m pip check
```

After setup, validation, EDA and tests run locally without network access:

```powershell
.\.venv\Scripts\python.exe -m playerlens validate
.\.venv\Scripts\python.exe -m playerlens eda
# For another run, choose a fresh output directory:
.\.venv\Scripts\python.exe -m playerlens eda --input data/raw/elden_ring_steam_reviews.csv --output artifacts/eda-next
```

The EDA writer requires a new or empty output directory. It rejects paths inside
the source directory. Exit codes are 0 for successful analysis (possibly warnings),
1 for record-level errors with clearly flagged reports, and 2 for structural,
identity or I/O failure. A completed report has a `run.json` completion marker,
written last. An I/O failure may leave an incomplete directory; use a fresh path
and never mistake partial outputs for a completed run.

All outputs remain local under ignored `artifacts/`. The report includes original
text only for the eight previously inspected development-only IDs. Do not commit
or upload it. See [data provenance and validation](DATA.md) for source limitations.

## Architecture

```text
CSV -> validate_csv() -> ValidationResult
                            |
                            v
                       build_eda()
                            |
                            v
                 EDAResult(summary, tables)
                            |
                            v
                    write_eda_report()
                            |
                            v
                  CSV + JSON + PNG + Markdown
```

`eda.py` performs calculations without file access, chart rendering or mutations
to the validator's original/parsed tables. One plain result dataclass groups the
outputs. `eda_report.py` handles presentation and writing; plotting imports are
lazy, so the validation command remains independent of plotting. `cli.py` selects
the operation and retains existing validation behaviour.

The output directory is flat: `report.md`, deterministic `summary.json`, run
metadata, descriptive CSV tables and seven PNG figures. There is no database,
notebook dependency, server, annotation interface, ML model or inference step.

## Definitions and calculations

- **Records and recommendations:** one count per unique review ID. Primary
  analytics retain repeated text. Recommendation distribution shares use all
  rows and show an unknown/invalid category. Within-group recommended shares use
  only valid recommendations, with the numerator, denominator and unknown count
  reported. Synthetic example: one true, one false and one missing gives a
  recommended share of 1/2 among valid values, not 1/3.
- **Text:** blank means empty/whitespace, not literal `NA` or `null`. Word counts
  use original whitespace splitting; characters include original formatting and
  whitespace. Numeric text-length summaries exclude blanks, while the separate
  blank band retains those records. Length bands are blank, 1–5, 6–20, 21–50,
  51–100, 101–200 and over 200 words. None is a classifier of useful content.
- **Duplicates:** reuse the validator's NFKC/casefold/whitespace comparison key.
  Report distinct texts, repeated groups, reviews in groups and occurrences beyond
  the first. With three identical reviews, these last three counts are 1, 3 and 2.
  Blank texts are excluded. Repetition does not prove spam. The separately labelled
  unique-text term view is a sensitivity analysis, not a replacement population.
- **Playtime:** use `author_playtime_at_review / 60` for hours. Bands are under 10,
  10–under 50, 50–under 100, 100+, and unknown/invalid. Compute thresholds from
  original minutes without rounding. A value at 600 minutes enters the 10-hour
  band. Consistency warnings are retained without correcting or deleting values;
  lifetime playtime is not substituted.
- **Helpful votes:** summarize `votes_up`, including zeros and missing/invalid
  values, by recommendation and length group. Report median, quantiles, mean,
  zero/positive counts and positive share among valid observations. The plot uses
  natural `log(1 + votes)` so zeros remain visible and the long tail fits.
  Accumulated vote counts lack exposure denominators and do not establish quality.
- **Dates:** preserve source calendar values and their unknown timezone. Include
  zero-observation days between the first/last valid dates and Monday–Sunday weeks.
  Flag boundary days/weeks as partial and retain missing-date counts. A missing
  day in the CSV is not evidence that Steam received no reviews that day.
- **Terms:** temporary count-only preprocessing uses NFKC/casefold, removes URLs
  and recognizable HTML/BBCode tags, and counts Unicode words of at least two
  letters, allowing apostrophes. A fixed, recorded function-word list retains
  negators such as `not`, `no` and `never`. No stemming, lemmatization, topic lexicon,
  opinion inference, sentence segmentation or prepared-text dataset is introduced.
  Count each term once per review, sort ties alphabetically and retain the top 20
  for all/recommended/not-recommended/unknown cohorts. Denominators include every
  nonblank review, even text yielding no eligible terms. Unique-normalized-text
  sensitivity deduplicates within each cohort; the same text can occur in both
  recommendation groups. These are vocabulary counts, not aspect labels.
  Checklist options (including unchecked choices), quotations and other-game
  references can contribute words; counts do not identify endorsed opinions.
- **Missing and small groups:** invalid parsed values remain missing. JSON uses
  null and CSV an empty cell for undefined statistics; no zero-denominator rate
  becomes zero. Report field-level issues separately from distinct affected-review
  counts because one review can have multiple issues. Flag eligible groups below
  20 observations; distinguish total-review from recommendation denominators.

Numeric quantiles use Pandas linear interpolation. For synthetic values 1, 3 and
5, the median is 3 and the 25th percentile is 2. Means are calculated in floating
point to avoid signed-integer accumulation overflow. Medians and upper percentiles
make skew visible; neither supports population or causal claims on its own.

## Reading the outputs

| Output | Contents |
| --- | --- |
| `summary.json` | Input checksum, validation status, counts, settings and explicit unestimated aspect-usefulness share |
| `recommendations.csv`, `quality.csv` | Recommendation distribution and field-issue totals |
| `lengths.csv`, `playtime.csv` | Complete cohorts, counts, eligible denominators and recommendation shares |
| `duplicates.csv`, `duplicate_sizes.csv` | Exact/normalized repeated-text counts and group-size distribution |
| `numeric_summary.csv` | Length, playtime and helpful-vote summaries overall, by recommendation and by length band |
| `distributions.csv` | Aggregated value frequencies and cumulative shares used in plots |
| `daily.csv`, `weekly.csv` | Calendar observations, partial periods, denominators and volume flags |
| `terms.csv` | Document frequencies and unique-text sensitivity views |
| `development_examples.csv` | Original text for pre-reserved development examples only; local and not representative |
| `*.png`, `report.md` | Seven figures and a readable report with quantitative/qualitative sections |
| `run.json` | Completion marker, input/output paths, versions, timestamps, settings, output inventory and report-writing time |

The cumulative length plot answers "what fraction of nonblank reviews have at
most this many words?" Its log horizontal axis makes both short reviews and long
tails visible. Playtime chart annotations show recommendation denominators, and
date charts/tables identify partial periods rather than presenting them as full
calendar coverage. Review-length bands form a categorical histogram, with a
separate blank category.

The qualitative examples are already reserved for development along with their
related groups. They illustrate what text looks like, not a reviewed annotation
dataset. Do not derive an aspect-useful percentage, expand the taxonomy, infer
topic-specific opinions automatically, or use their groups for final evaluation.

## Verification and Windows temporary directories

Tests use synthetic CSVs, hand-calculated expected results and real PNG smoke
checks. They cover denominators, invalid/missing values, empty groups, duplicate
reconciliation, quantiles, playtime boundaries, calendar gaps, fixed example
selection, source/table preservation, deterministic reports and I/O failures.

Use a fresh scratch parent for each run (pytest requires the parent to exist):

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:MPLCONFIGDIR = Join-Path (Get-Location).Path '.cache/matplotlib'
$edaScratch = Join-Path '.cache/verification' ('eda-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $edaScratch -Force | Out-Null
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider --basetemp (Join-Path $edaScratch 'pytest')
```

The managed Windows sandbox may deny access to pytest's restricted temporary
directories even inside the project. An explicitly approved outside-sandbox test
run can resolve this execution restriction without changing system permissions
or tests. Record it as an environment limitation; do not claim the sandbox itself
is fixed. Do not delete protected old temporary directories to make a run pass.

Run validation and EDA against the real input separately from synthetic tests.
Compare the SHA-256 before/after and reconcile totals against validation. Two
fresh EDA outputs must have identical JSON/CSV/report content except `run.json`.
Plot pixels are not required to match across platforms, fonts or library versions.
Dependencies are pinned for this tested Windows/Python environment, not an
artifact-hash lock or a universal cross-platform guarantee.
