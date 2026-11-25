# Text preparation and annotation architecture

CSV -> existing validate_csv -> source-linked passages + duplicate groups ->
seeded cohort/split manifest -> pilot-only Streamlit form -> local human JSON.

text_preparation.py is pure: prepare_text creates a conservative NFC/whitespace
view, and extract_passages partitions original Python character offsets [start,end).
IDs hash review ID, original text hash, version and offsets. Core spans reconstruct
the original. Adjacent cores are context, not extra observations. Short text,
negation, checklist markers and tails survive. Only decorative BBCode b/i/u/h tags
are removed from the derived view. Unknown/semantic markup remains literal.
Whitespace words are not model word pieces: Milestone 5 must implement token-aware
windows respecting its actual tokenizer. The simple boundary heuristic can make
imperfect sentence splits; full originals and neighboring spans remain accessible.

sampling.py reuses validation's NFKC/casefold/whitespace duplicate key. Blank
records are singletons. Character trigrams (plus bigrams for strings <=24 chars)
use rare-first prefix indexing and exact Jaccard screening >=0.5. Canonically
ordered SequenceMatcher with autojunk=False verifies similarity: >=0.9 near,
0.8-0.9 precautionary related. Connected components stay within a split.
Thresholds detect textual reuse, not all semantic paraphrases. Transitive links
can overgroup templates; short matches can be coincidental; no score is a
probability. Negation/selection symbols are never removed. Wording changes that
reverse sentiment may still group together. Never copy labels between members.

Synthetic shared-context good -> bad, good -> not good, and reversed checklist
selections score approximately 0.969, 0.976 and 0.938 respectively. Their normalized
keys differ; their isolation groups agree. Tests verify this distinction.

Seeded SHA-256 ranks over review IDs avoid row-order dependence. Groups are built
before sampling; whole-group assignments balance non-pilot cohort counts with
forced development groups first. Unsampled group assignments are also saved for
future development restrictions. See ANNOTATION.md for all cohort frames/limits.

```powershell
.\.venv\Scripts\python.exe -B -m playerlens prepare
# Reruns require a fresh directory; do not overwrite annotated runs:
.\.venv\Scripts\python.exe -B -m playerlens prepare --output data/processed/m3-next
```

Preparation writes reviews.jsonl, passages.jsonl, groups.jsonl,
sampling_manifest.jsonl, summary.json and run.json under ignored data/processed/m3-ready.
The manifest includes every ID, group, cohort or null, split, forced-development
flag and challenge reasons (0 sarcasm marker, 1 negation, 2 contrast, 3 short).
run.json is written last with output hashes, source checksum, versions and timing.
A missing marker is incomplete output. Readers verify artifacts and the current
source checksum. The persistent data/annotations/development_exclusions.json
ledger unions old and newly reserved group members; exclusions are never discarded.
Validation errors stop preparation; blank warnings do not remove records.

Original data is never rewritten. No original or held-out review text should be
printed during verification. Only counts and hashes are needed. All actual data,
labels, exclusions and outputs are ignored; public tests/docs use synthetic text.

Tests follow docs/EDA.md's Windows scratch-parent and cache procedure. Sandbox
restricted temp access may require approved normal-user outside-sandbox execution;
do not change ACLs or weaken tests. Compare deterministic output hashes between
fresh runs with identical ledger input; timestamps/timings in run.json can differ.

Verified pilot checkpoint: 9,794 reviews, 10,887 passages, 6,932 groups;
largest related component 569 reviews. Targets achieved: pilot 20 development;
representative 60 development/60 test; enriched 20/20; challenge 10/10.
Whole-group constraints retain 110 development and 90 test annotations targeted.
Five deterministic artifacts match across two completed runs; all core spans
reconstruct original reviews. Full preparation took 55.78s and 52.02s locally;
these observations are not controlled performance benchmarks. The current default
prepared directory is data/processed/m3-ready; earlier ignored m3 and m3-pilot
runs are development verification outputs, not annotation workspaces.
