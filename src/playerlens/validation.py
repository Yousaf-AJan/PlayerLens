"""Read a CSV snapshot, validate its fields, and summarise without changing it."""

from collections import Counter
import csv
from dataclasses import asdict, dataclass
from datetime import datetime
import hashlib
import io
from pathlib import Path
import re
import unicodedata

import pandas as pd

BOOLEAN_COLUMNS = (
    "voted_up", "steam_purchase", "recieved_for_free", "written_during_early_access",
)
NUMERIC_COLUMNS = (
    "votes_up", "comment_count", "author_num_games_owned", "author_num_reviews",
    "author_playtime_forever", "author_playtime_last_two_weeks",
    "author_playtime_at_review",
)
DATE_COLUMNS = ("created", "author_last_played")
REQUIRED_COLUMNS = (
    "id", "language", "review", "created", "voted_up", "votes_up", "comment_count",
    "steam_purchase", "recieved_for_free", "written_during_early_access",
    "author_num_games_owned", "author_num_reviews", "author_playtime_forever",
    "author_playtime_last_two_weeks", "author_playtime_at_review", "author_last_played",
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
SETTINGS = {
    "schema_version": 1,
    "encoding": "utf-8-sig",
    "date_format": DATE_FORMAT,
    "timestamp_timezone": "unknown; preserve source calendar values",
    "boolean_values": ["true", "false"],
    "scalar_whitespace": "strip for parsing; preserve original fields",
    "numeric_policy": "nonnegative base-10 integers fitting signed Int64",
    "text_missing_policy": "empty or whitespace only; literal NA/null retained",
    "duplicate_normalization": "Unicode NFKC, casefold, collapse whitespace",
    "short_review_max_words": 5,
    "word_count": "whitespace split",
    "sampling": "none; validate full input",
    "seed": 42,
}


class DatasetValidationError(ValueError):
    """Structural or identity failure: no usable dataset may be returned."""


@dataclass(frozen=True)
class Issue:
    data_row: int
    review_id: str
    field: str
    code: str
    severity: str
    value: str
    message: str


@dataclass
class ValidationResult:
    raw: pd.DataFrame
    validated: pd.DataFrame
    summary: dict
    issues: list[Issue]


def is_missing(value: object) -> bool:
    """Check a scalar; textual NA/null are legitimate strings, not missing values."""
    return bool(pd.isna(value)) or (isinstance(value, str) and not value.strip())


def parse_boolean(value: object) -> bool:
    if is_missing(value):
        raise ValueError("missing Boolean")
    normalised = str(value).strip().casefold()
    if normalised not in {"true", "false"}:
        raise ValueError("expected True or False")
    return normalised == "true"


def parse_date(value: object) -> datetime:
    if is_missing(value):
        raise ValueError("missing date")
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", text):
        raise ValueError(f"expected {DATE_FORMAT}")
    return datetime.strptime(text, DATE_FORMAT)


def parse_nonnegative_integer(value: object) -> int:
    if is_missing(value):
        raise ValueError("missing integer")
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise ValueError("expected a nonnegative integer")
    number = int(text)
    if number > 2**63 - 1:
        raise ValueError("integer exceeds signed Int64 range")
    return number


def normalise_for_duplicates(text: str) -> str:
    """Grouping key only; never replace the original review with this value."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _read_snapshot(content: bytes) -> pd.DataFrame:
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        columns = next(reader, [])
        if not columns or len(set(columns)) != len(columns) or any(not c.strip() for c in columns):
            raise DatasetValidationError("CSV header is empty or contains blank/duplicate columns.")
        missing = sorted(set(REQUIRED_COLUMNS) - set(columns))
        if missing:
            raise DatasetValidationError(f"Missing required columns: {', '.join(missing)}")
        records = []
        for record in reader:
            if not record:  # Ignore completely empty physical lines, not blank review fields.
                continue
            if len(record) != len(columns):
                raise DatasetValidationError(
                    f"Data row {len(records) + 1} has {len(record)} fields; expected {len(columns)}."
                )
            records.append(record)
    except (UnicodeError, csv.Error) as exc:
        raise DatasetValidationError(f"Invalid UTF-8/CSV: {exc}") from exc
    if not records:
        raise DatasetValidationError("CSV contains no data rows.")
    raw = pd.DataFrame(records, columns=columns, dtype=str)
    invalid_ids = ~raw["id"].str.fullmatch(r"[0-9]+")
    if invalid_ids.any():
        rows = (raw.index[invalid_ids] + 1).tolist()
        raise DatasetValidationError(f"Blank or invalid review IDs at data rows {rows[:10]}.")
    duplicate_ids = raw["id"].duplicated(keep=False)
    if duplicate_ids.any():
        rows = (raw.index[duplicate_ids] + 1).tolist()
        raise DatasetValidationError(f"Duplicate review IDs at data rows {rows[:10]}.")
    return raw


def _duplicate_summary(texts: list[str]) -> dict:
    counts = Counter(texts)
    return {
        "groups": sum(count > 1 for count in counts.values()),
        "additional_occurrences": sum(count - 1 for count in counts.values()),
        "rows_in_groups": sum(count for count in counts.values() if count > 1),
    }


def validate_csv(path: str | Path) -> ValidationResult:
    """Validate the exact bytes hashed here; invalid fields become nullable values.

    Fatal schema/ID/CSV errors raise DatasetValidationError. Other problems are
    returned as issues, with no dropped rows. Original fields remain in raw.
    """
    content = Path(path).read_bytes()
    raw = _read_snapshot(content)
    validated = raw.copy(deep=True)
    issues: list[Issue] = []

    def issue(index: int, field: str, code: str, message: str, severity: str = "error") -> None:
        issues.append(Issue(index + 1, raw.at[index, "id"], field, code, severity,
                            raw.at[index, field], message))

    for columns, parser, dtype in (
        (BOOLEAN_COLUMNS, parse_boolean, "boolean"),
        (NUMERIC_COLUMNS, parse_nonnegative_integer, "Int64"),
        (DATE_COLUMNS, parse_date, "object"),
    ):
        for column in columns:
            parsed = []
            for index, value in raw[column].items():
                try:
                    parsed.append(parser(value))
                except ValueError as exc:
                    parsed.append(pd.NA)
                    issue(index, column, "missing" if is_missing(value) else "invalid", str(exc))
            validated[column] = pd.Series(parsed, dtype=dtype)

    for index, row in raw.iterrows():
        if is_missing(row["review"]):
            issue(index, "review", "blank_review", "No nonblank review text.", "warning")
        if is_missing(row["language"]):
            issue(index, "language", "missing", "Missing language metadata.")
        at_review = validated.at[index, "author_playtime_at_review"]
        lifetime = validated.at[index, "author_playtime_forever"]
        if not is_missing(at_review) and not is_missing(lifetime) and at_review > lifetime:
            issue(index, "author_playtime_at_review", "exceeds_lifetime",
                  "Playtime at review exceeds observed lifetime playtime.", "warning")

    nonblank = [text for text in raw["review"] if not is_missing(text)]
    words = [len(text.split()) for text in nonblank]
    errors = [item for item in issues if item.severity == "error"]
    recommendation = validated["voted_up"]
    date_summary = {}
    for column in DATE_COLUMNS:
        values = [value for value in validated[column] if not is_missing(value)]
        date_summary[column] = {
            "valid": len(values),
            "missing_or_invalid": len(raw) - len(values),
            "min": min(values).strftime(DATE_FORMAT) if values else None,
            "max": max(values).strftime(DATE_FORMAT) if values else None,
        }
    numeric_summary = {}
    for column in NUMERIC_COLUMNS:
        values = validated[column].dropna()
        numeric_summary[column] = {
            "valid": len(values), "missing_or_invalid": len(raw) - len(values),
            "min": int(values.min()) if len(values) else None,
            "max": int(values.max()) if len(values) else None,
        }
    summary = {
        "settings": dict(SETTINGS),
        "input": {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)},
        "rows": len(raw), "columns": list(raw.columns),
        "extra_columns": sorted(set(raw.columns) - set(REQUIRED_COLUMNS)),
        "unique_ids": int(raw["id"].nunique()),
        "languages": dict(sorted(Counter(raw["language"]).items())),
        "recommendations": {
            "recommended": int(recommendation.eq(True).sum()),
            "not_recommended": int(recommendation.eq(False).sum()),
            "missing_or_invalid": int(recommendation.isna().sum()),
        },
        "text": {
            "blank": len(raw) - len(nonblank), "nonblank": len(nonblank),
            "nonblank_five_words_or_fewer": sum(count <= 5 for count in words),
            "max_words": max(words, default=0),
        },
        "duplicates": {
            "exact_nonblank": _duplicate_summary(nonblank),
            "normalised_nonblank": _duplicate_summary([normalise_for_duplicates(t) for t in nonblank]),
        },
        "dates": date_summary, "numeric_fields": numeric_summary,
        "validation": {
            "status": "invalid" if errors else "valid_with_warnings" if issues else "valid",
            "error_count": len(errors), "warning_count": len(issues) - len(errors),
            "rows_with_errors": len({item.data_row for item in errors}),
            "rows_with_issues": len({item.data_row for item in issues}),
            "issue_counts": dict(sorted(Counter(f"{i.field}:{i.code}" for i in issues).items())),
        },
    }
    return ValidationResult(raw, validated, summary, issues)


def write_issues(path: Path, issues: list[Issue]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(Issue.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(asdict(item) for item in issues)
