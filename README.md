# PlayerLens

PlayerLens is a local analysis project that explores Steam player reviews to understand how players feel about specific game features. It uses an Elden Ring review dataset to look beyond the overall recommended or not-recommended verdict.

## Purpose

An overall recommendation can hide a mixed experience: a player may recommend a game while criticising its performance, or dislike it while praising its world
design. PlayerLens aims to identify the topics discussed in each review and the opinions expressed about those topics, with supporting passages from the original text.

The intended outcome is an interactive dashboard for exploring common praise and criticism, comparing feedback across recommendation and playtime groups, and examining the reviews behind each finding. Topic detection and opinion analysis
will be evaluated against manually labelled examples so their accuracy and limitations can be understood.

## Project directory structure

```text
PlayerLens/
|-- src/
|   `-- playerlens/
|       |-- __init__.py       # Package information
|       |-- __main__.py       # Python module entry point
|       |-- cli.py            # Command-line interface
|       `-- validation.py     # Dataset checks and summaries
|-- tests/
|   |-- conftest.py           # Synthetic review fixtures
|   `-- test_validation.py    # Validation and CLI tests
|-- docs/
|   `-- DATA.md               # Data provenance and validation policies
|-- data/
|   `-- raw/                  # Original local review dataset
|-- artifacts/                # Generated local reports and outputs
|-- .gitignore                # Local data and generated-file exclusions
|-- pyproject.toml            # Package configuration and dependencies
|-- requirements-lock.txt     # Pinned dependencies
`-- README.md
```

Source reviews and generated outputs remain local. Original review text is preserved so analysis can be traced back to its evidence.

## Project flow

The intended processing flow is:

```text
Data Validation
    -> Text Preparation and Passage Extraction
    -> Data Exploration and Manual Annotation
    -> Rule-Based Baseline and Semantic Matching
    -> Review-Level Aggregation
    -> Evaluation
    -> Interactive Dashboard
```

1. **Data validation:** check the CSV structure, review IDs, field values, missing content, and duplicate text while preserving the source dataset.
2. **Text preparation and passage extraction:** prepare review text for analysis and divide long reviews into linked passages without losing their context.
3. **Data exploration and manual annotation:** examine the dataset and label review topics, opinions, and supporting evidence for development and evaluation.
4. **Rule-based baseline and semantic matching:** compare explicit text rules with meaning-based matching to detect topics and opinions about each topic.
5. **Review-level aggregation:** combine passage findings into one result per review and topic, retaining mixed or uncertain opinions.
6. **Evaluation:** compare predictions with manually reviewed labels and examine accuracy, coverage, and errors.
7. **Interactive dashboard:** present feedback patterns, comparisons, supporting reviews, and evaluation results.
