# Pilot annotation guidelines (provisional v1)

The seven categories are provisional until the user completes and reviews all
20 pilot reviews. No labels are generated automatically. No taxonomy is frozen.

## Topics and boundaries

| Topic | Include |
| --- | --- |
| Performance/stability | Frame rate, stutter, crashes, technical reliability |
| Combat/difficulty | Combat mechanics, enemy/boss design, challenge and fairness |
| Exploration/world design | Discovery, traversal, environments and world structure |
| Story/lore | Narrative, characters and storytelling |
| Controls/camera | Inputs, targeting, camera and controlling actions |
| Online play / Multiplayer | Human co-op, invasions, PvP and online functionality |
| Progression/build variety | Leveling, upgrades, resource costs and character/build choices |

These are boundaries to discuss, not assumptions about review content. Dodge
timing or boss attacks do not alone establish progression feedback. Leveling
costs differ from encounter difficulty. Use both topics only when the text
supports each. Button names alone do not establish build variety. Summoning
creatures alone does not establish human multiplayer. References to another
game are not evidence about the target game.

Use General feedback for game-level praise/criticism without a specific aspect.
Use Other specific feature with a short feature name (for example audio or price)
when the evidence does not fit a provisional topic. Never force a topic.

## Opinions and evidence

- praise: favorable opinion; criticism: unfavorable opinion.
- mixed: supported positive and negative opinions about the same aspect.
- neutral: descriptive mention without a clear favorable/unfavorable opinion.
- uncertain: the reviewer expresses uncertainty, not the annotator's uncertainty.

One overall opinion per topic (or named other feature), with as many evidence rows
as necessary. Repeat the same overall opinion on those rows; evidence opinions
can differ. Mixed requires praise plus criticism, or explicitly mixed evidence.
Select the smallest sufficient passage/quote retaining negation and attribution.
Blank quote selects the entire chosen passage. Occurrence is one-based when an
exact quote appears repeatedly. Evidence is checked against original characters.
Adjacent passage context and the full original are always available.

Synthetic example: "Combat feels satisfying, but bosses become repetitive."
can support mixed combat feedback with both sides retained. It does not establish
an opinion about progression, controls, or performance.

Preserve checklist selections: unchecked options are not endorsed. Include the
heading when interpreting an option. Difficulty is not inherently criticism.
Sarcasm requires context; if interpretation is unresolved, save a draft and note
the question. Do not use Steam recommendation to resolve aspect opinion.

## Completion and ambiguity

Save draft for incomplete work. Mark reviewed only after reading the complete
review and checking every aspect, opinion and evidence span. Resolve annotator
questions first. Drafts are never evaluation ground truth. General feedback,
insufficient_detail, off_topic, ambiguous, and blank permit honest no-aspect cases.
Explain ambiguous/off-topic decisions in notes. A confidently identified ambiguous
review is different from an unresolved annotator question.

After pilot review, inspect per-topic support and difficult boundaries, especially
online play, combat and progression. The eight historically reserved examples
provide no clear target-game online-play evidence; this is not a prevalence estimate.
Do not remove unsupported categories automatically. The user decides refinements.

## Local workflow

From the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m playerlens annotate
```

Open the printed localhost URL. Read the original, expand passages, and add rows
in the evidence table. Choose topic, overall opinion, passage number and evidence
opinion. Optionally enter an exact quote and occurrence. Use a separate feature
name for each Other specific feature. Save draft or mark reviewed explicitly.
Save before navigation, confirm the navigation checkbox, then open the selected
review. Reopen previously saved reviews to edit them. Restarting the app reloads
saved annotations; unsaved form entries are not durable.

Only the pilot is exposed. Test mode and freezing are locked. Use one active
annotation browser/session. JSON files stay under ignored data/annotations/m3/
development. Each edit retains the prior JSON in .json.bak. Stale saves fail.
If JSON is corrupt, preserve it and inspect the backup. Explicit Python recovery
using playerlens.annotation.restore_backup(path) saves a .json.damaged copy;
no automatic recovery or label migration occurs. A changed guideline/taxonomy
hash requires explicit re-review; do not edit this document mid-session.

No cloud service, model, inference, telemetry, or public host is used. The interface
binds to 127.0.0.1. A manual browser usability review remains a user checkpoint.

## Sampling and evaluation limits

Pilot: eight known development examples plus twelve seeded selections, favoring
additional groups. It is not representative. Representative: 120 uniformly ranked
remaining review IDs after pilot removal, retaining repetitions, blanks and short
reviews. Enriched: 40 additional not-recommended reviews from remaining IDs.
Challenge: 20 remaining examples using explicit sarcasm, negation, contrast and
short-text indicators. Indicators are not verified sentiment or sarcasm labels.
Targets can be missed; saved achieved counts are authoritative.

Seed 42 and grouped splits apply. Development exclusions and related groups never
enter test. Roughly half of each non-pilot cohort targets test; group constraints
can change achieved ratios. Final evaluation must report cohorts separately,
sampling frames, exclusions, eligible denominators, small supports and uncertainty.
Neither enriched/challenge results nor this historical snapshot represent all
players. Single-reviewer labels are subjective; no inter-annotator agreement is
claimed. Test content/labels must not guide taxonomy, rules or model tuning.
