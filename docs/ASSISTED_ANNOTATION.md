# Assisted pilot review (provisional)

This revision replaces the expectation of manually labeling all 200 selected
reviews. Existing preparation, groups, sampling, exclusions, source evidence,
manual annotations and the advanced form are preserved. The first assistant uses
transparent rules, not a pretrained model. No downloads, training or new dependencies.

## Run locally

From C:\Projects\PlayerLens:

```powershell
# Already generated for the current pilot; run only for a fresh proposal directory:
.\.venv\Scripts\python.exe -B -m playerlens propose
# Open the default assisted pilot:
.\.venv\Scripts\python.exe -B -m playerlens annotate
# Existing advanced form remains available separately:
.\.venv\Scripts\python.exe -B -m playerlens annotate --mode manual
# Regeneration preserves earlier runs and requires a new output path:
.\.venv\Scripts\python.exe -B -m playerlens propose --output data/proposals/m3-assisted-v2
.\.venv\Scripts\python.exe -B -m playerlens annotate --proposals data/proposals/m3-assisted-v2 --decisions data/annotations/m3-assisted-v2
```

Open the printed 127.0.0.1 URL. Telemetry is disabled. Nothing is served publicly.
The UI reads precomputed proposals; startup does not run models or inference.
Use one active browser/session. No source review is uploaded anywhere.

## Review a few examples first

1. Read the **complete original review**, shown first. Look for opinions the rules
   missed; do not restrict your reading to the candidate quotations.
2. **Add missing aspect** is beside the original and always available, even with
   no proposals. It immediately opens aspect/opinion/evidence controls below.
3. For each candidate choose Approve, Correct, Reject, or Defer. Nothing is approved
   by default. Abstained opinions require Correct or Defer, not Approve.
4. Correct using dropdowns and supporting passages. Optional exact quotations and
   a selectable occurrence narrow the source span. Choose evidence opinions as well
   as the overall opinion. Mixed needs supported praise and criticism or explicitly
   mixed evidence. Other specific feature needs a feature name.
5. Save draft at any point. To save a checked assisted review, resolve deferred
   cards/questions and tick **I read the complete original and checked for missing
   aspects**. Give content flags when there are no usable labels. A checked assisted
   review is still not an independent reference.
6. Save before navigation, confirm saved/discarded work, then Open selected review.
   Existing decisions reload and can be edited. Saves retain backups and revisions.
7. After just 3–5 reviews (or even one), save feedback in the prominent final
   section and pause. Tell the assistant what felt difficult. Finishing all 20 is
   not a prerequisite for usability feedback. Feedback remains development-only.

Your feedback is in data/annotations/m3-assisted-v1/pilot_feedback.json. Checked
and draft decisions live under assisted/development/. Only explicit saves write
human decisions. Unsaved widget state is not durable across browser/session loss.

## What the rules do

proposals.py operates on existing source-linked passages. Aspect vocabularies detect
explicit phrases independently of opinion. Source-offset clauses split at sentence,
line and contrast boundaries. Opinion cues must be within six intervening word
tokens of the aspect's first matched phrase in the clause. Negation uses a limited
three-token window; complex negation abstains. Multiple aspects in one clause cause
opinion abstention rather than transferring a general adjective to every feature.

Explicit hedges can propose reviewer uncertainty. Limited has/includes/supports
constructions can propose neutral. No polarity cue alone does not establish neutral.
Supported opposing opinions aggregate to mixed. General game-level phrases and a
small audio/price vocabulary allow general/other-feature candidates. Absent matches
mean **no supported proposal**, not that the review contains no aspects.

Sarcasm markers, checklist selections, quote/strike tags and recognized comparisons
or other-game references conservatively abstain on opinions. Attribution detection
is incomplete and can miss unfamiliar game names. Each card retains exact original
quotes, offsets, rule IDs and abstention reason. Steam recommendation is not used
for any inference. Rule matches are explanations, not calibrated probabilities.

This v1 has narrow vocabulary, heuristic clause boundaries/negation, incomplete
attribution, no reliable sarcasm understanding and frequent abstention. Topic
matches can themselves be wrong. Unknown aspects and implicit opinions are often
missed. Long-review context remains available, but independent clauses can lose
linguistic context; use the full original. Rules are deliberately not claimed accurate.

## Architecture and provenance

Existing preparation -> proposals.py -> proposal_store.py immutable JSONL run ->
assisted_app.py cards -> existing annotation validator/atomic storage -> separate
human assisted decisions. The CLI only dispatches and launches localhost Streamlit.

- Machine proposals: data/proposals/m3-assisted-v1/proposals.jsonl plus hashed run
  manifest. Never overwritten; implementation/vocabulary/guideline changes require
  a fresh run. Preparation identity and group membership are checked on load.
- Assisted decisions: record_kind=assisted_review, proposal_visible=true,
  eligible_as_reference=false, linked to their original proposal run. Approval or
  correction cannot automatically promote these records to reference labels.
- Independent references: none are generated by this interface. Legacy records
  are preserved and cannot be assumed independent merely because status=reviewed.

No database is needed. Existing atomic JSON writing, backup copies, evidence
validation and stale-revision protection are reused. Use a new decision directory
when changing the proposal run; no silent migration/rebinding occurs. The existing
manual workflow and docs/ANNOTATION.md remain unchanged, including its guideline
hash. The newer assisted workflow takes precedence over its older usage instructions.

## Isolation and smaller evaluation

Only development pilot reviews appear in the UI. `propose --cohort development`
can generate suggestions for the existing selected development cohorts; it does
not authorize test review. Existing groups, splits and exclusions stay unchanged.
Related reviews never inherit labels. Test/reference modes and freezing stay locked.

After pilot feedback and explicit guideline/taxonomy readiness approval, a later
blind workflow can label 20 reviews from distinct groups in the existing
representative test cohort (currently 60 reviews/52 groups). Suggestions and
prediction-selected evidence must be hidden throughout blind annotation. Its own
subset manifest must not modify the existing split. A distinct-group constraint
changes inclusion probabilities: report a diagnostic subset, not an unbiased
population estimate. Forty blind reviews is a possible later expansion; zero blind
references means no independently measured predictive accuracy.

Freeze candidate settings before opening evaluation results and retain the separate
Milestone 6 readiness gate. Twenty references give weak support for rare aspects and
opinions. Report supports, undefined results, errors and abstention; include missed
aspects when measuring recall. Assisted acceptance rates are workflow statistics,
never accuracy. Enriched/challenge cohorts must be reported separately. A single
reviewer still introduces subjectivity and possible project-familiarity bias.

All seven categories remain provisional. This bounded proposal helper is an approved
Milestone 3 workflow exception; the full Milestone 4 baseline study and Milestone 5
semantic experiments have not begun. No final model evaluation is performed here.
