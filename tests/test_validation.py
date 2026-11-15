from datetime import datetime
import json

import pandas as pd
import pytest

from playerlens.cli import main
from playerlens.validation import (
    BOOLEAN_COLUMNS, DATE_COLUMNS, NUMERIC_COLUMNS, REQUIRED_COLUMNS,
    DatasetValidationError, parse_boolean, parse_date, parse_nonnegative_integer,
    validate_csv,
)


@pytest.mark.parametrize(("value", "expected"), [
    ("True", True), ("False", False), (" false ", False), ("TRUE", True),
])
def test_boolean_values_are_not_string_truthiness(value, expected):
    assert parse_boolean(value) is expected


@pytest.mark.parametrize("value", [None, pd.NA, float("nan"), "", " ", "0", "yes", "null"])
def test_boolean_missing_and_invalid_are_not_false(value):
    with pytest.raises(ValueError):
        parse_boolean(value)


def test_dates_keep_source_calendar_without_inventing_timezone():
    parsed = parse_date("2023-01-29 14:32:52")
    assert parsed == datetime(2023, 1, 29, 14, 32, 52)
    assert parsed.tzinfo is None


@pytest.mark.parametrize("value", [
    None, pd.NA, "", "2023-02-29 00:00:00", "2023-01-29", "2023-1-29 00:00:00",
    "2023-01-29 24:00:00", "2023-01-29 00:00:00Z",
])
def test_invalid_or_missing_dates(value):
    with pytest.raises(ValueError):
        parse_date(value)


@pytest.mark.parametrize("value", [None, "", "-1", "1.5", "NaN", "inf", "1e3", str(2**63)])
def test_numeric_missing_or_invalid(value):
    with pytest.raises(ValueError):
        parse_nonnegative_integer(value)


def test_zero_and_integer_range_are_valid():
    assert parse_nonnegative_integer(" 0 ") == 0
    assert parse_nonnegative_integer(str(2**63 - 1)) == 2**63 - 1


def test_original_review_and_ids_survive_parsing(csv_factory):
    original = "[b]Synthetic[/b], not bad!\nNA; null; caf\u00e9."
    path = csv_factory([{"review": original}], encoding="utf-8-sig")
    before = path.read_bytes()
    result = validate_csv(path)
    assert path.read_bytes() == before
    assert result.raw.at[0, "id"] == "001"
    assert result.raw.at[0, "voted_up"] == "False"
    assert not result.validated.at[0, "voted_up"]
    assert result.raw.at[0, "review"] == original
    assert result.validated.at[0, "review"] == original
    assert result.summary["validation"]["status"] == "valid"


def test_blank_and_short_texts_and_duplicate_counts(csv_factory):
    path = csv_factory([
        {"review": "Good GAME"}, {"review": "good game"}, {"review": "good game"},
        {"review": "   \n"}, {"review": ""}, {"review": "NA"},
        {"review": "null"}, {"review": "Crashes constantly"}, {"review": "one two three four five six"},
    ])
    result = validate_csv(path)
    assert result.summary["text"] == {
        "blank": 2, "nonblank": 7, "nonblank_five_words_or_fewer": 6, "max_words": 6,
    }
    assert result.summary["duplicates"]["exact_nonblank"] == {
        "groups": 1, "additional_occurrences": 1, "rows_in_groups": 2,
    }
    assert result.summary["duplicates"]["normalised_nonblank"] == {
        "groups": 1, "additional_occurrences": 2, "rows_in_groups": 3,
    }
    assert len(result.validated) == 9
    assert result.summary["validation"]["warning_count"] == 2


@pytest.mark.parametrize("column", BOOLEAN_COLUMNS + NUMERIC_COLUMNS + DATE_COLUMNS + ("language",))
def test_missing_fields_are_reported_without_dropping_rows(column, csv_factory):
    result = validate_csv(csv_factory([{column: ""}, {}]))
    assert len(result.validated) == 2
    assert result.raw.at[0, column] == ""
    assert any(item.field == column and item.code == "missing" for item in result.issues)
    assert result.summary["validation"]["rows_with_errors"] == 1
    if column != "language":
        assert pd.isna(result.validated.at[0, column])


def test_invalid_fields_and_recommendation_denominator(csv_factory):
    result = validate_csv(csv_factory([
        {"voted_up": "yes", "created": "not a date", "votes_up": "-1"},
        {"voted_up": ""}, {"voted_up": "True"}, {},
    ]))
    assert result.summary["recommendations"] == {
        "recommended": 1, "not_recommended": 1, "missing_or_invalid": 2,
    }
    assert result.summary["validation"]["error_count"] == 4
    assert result.summary["validation"]["rows_with_errors"] == 2
    assert result.summary["dates"]["created"]["valid"] == 3
    assert result.summary["numeric_fields"]["votes_up"]["min"] == 0


def test_all_invalid_fields_have_null_extrema(csv_factory):
    result = validate_csv(csv_factory([{"created": "", "votes_up": ""}]))
    assert result.summary["dates"]["created"]["min"] is None
    assert result.summary["numeric_fields"]["votes_up"]["max"] is None
    json.dumps(result.summary, allow_nan=False)


def test_playtime_consistency_is_a_warning_not_a_correction(csv_factory):
    result = validate_csv(csv_factory([{"author_playtime_at_review": "121"}]))
    assert result.validated.at[0, "author_playtime_at_review"] == 121
    assert result.summary["validation"]["warning_count"] == 1
    assert result.summary["validation"]["error_count"] == 0


@pytest.mark.parametrize("review_id", ["", " ", "12.0", "abc", " 001", "\u0661"])
def test_invalid_ids_stop_processing(review_id, csv_factory):
    with pytest.raises(DatasetValidationError, match="invalid review IDs"):
        validate_csv(csv_factory([{"id": review_id}]))


def test_duplicate_ids_stop_processing(csv_factory):
    with pytest.raises(DatasetValidationError, match="Duplicate review IDs"):
        validate_csv(csv_factory([{"id": "123"}, {"id": "123"}]))


def test_missing_column_stops_processing(csv_factory):
    with pytest.raises(DatasetValidationError, match="Missing required columns: review"):
        validate_csv(csv_factory(columns=[c for c in REQUIRED_COLUMNS if c != "review"]))


def test_extra_columns_are_preserved(csv_factory):
    result = validate_csv(csv_factory([{"extra": "kept"}], columns=REQUIRED_COLUMNS + ("extra",)))
    assert result.raw.at[0, "extra"] == "kept"
    assert result.summary["extra_columns"] == ["extra"]


@pytest.mark.parametrize("content", [
    "", "id,id\n1,1\n", "id,\n1,1\n", "\xff",
])
def test_invalid_header_or_encoding_stops_processing(content, tmp_path):
    path = tmp_path / "broken.csv"
    path.write_bytes(content.encode("latin-1"))
    with pytest.raises(DatasetValidationError):
        validate_csv(path)


def test_bad_row_width_and_broken_quoting_stop_processing(csv_factory):
    path = csv_factory()
    with path.open("a", encoding="utf-8") as handle:
        handle.write("too,few,columns\n")
    with pytest.raises(DatasetValidationError, match="Data row 2"):
        validate_csv(path)
    path = csv_factory()
    with path.open("a", encoding="utf-8") as handle:
        handle.write('"unterminated')
    with pytest.raises(DatasetValidationError, match="Invalid UTF-8/CSV"):
        validate_csv(path)


def test_header_only_dataset_is_rejected(csv_factory):
    with pytest.raises(DatasetValidationError, match="no data rows"):
        validate_csv(csv_factory([]))


def test_summary_reproducibility_and_checksum_invalidation(csv_factory):
    path = csv_factory()
    first = validate_csv(path).summary
    assert validate_csv(path).summary == first
    path = csv_factory([{"review": "A different synthetic review."}])
    assert validate_csv(path).summary["input"]["sha256"] != first["input"]["sha256"]


def test_cli_reports_are_deterministic_and_manifest_separate(csv_factory, tmp_path):
    path = csv_factory([{"review": ""}, {}])
    output = tmp_path / "reports"
    args = ["validate", "--input", str(path), "--output", str(output)]
    assert main(args) == 0
    summary = (output / "summary.json").read_bytes()
    issues = (output / "issues.csv").read_bytes()
    assert main(args) == 0
    assert (output / "summary.json").read_bytes() == summary
    assert (output / "issues.csv").read_bytes() == issues
    manifest = json.loads((output / "run.json").read_text(encoding="utf-8"))
    assert manifest["input_sha256"] == json.loads(summary)["input"]["sha256"]
    assert "started_at_utc" in manifest
    assert "dependencies" in manifest


def test_cli_invalid_records_write_report_and_return_one(csv_factory, tmp_path):
    path = csv_factory([{"voted_up": "maybe"}])
    output = tmp_path / "reports"
    assert main(["validate", "--input", str(path), "--output", str(output)]) == 1
    assert "voted_up,invalid,error,maybe" in (output / "issues.csv").read_text()


def test_cli_fatal_failure_has_no_reports(csv_factory, tmp_path, capsys):
    path = csv_factory([{"id": ""}])
    output = tmp_path / "reports"
    assert main(["validate", "--input", str(path), "--output", str(output)]) == 2
    assert not output.exists()
    assert "Validation failed" in capsys.readouterr().err


def test_cli_protects_source_directory(csv_factory):
    path = csv_factory()
    before = path.read_bytes()
    assert main(["validate", "--input", str(path), "--output", str(path.parent)]) == 2
    assert path.read_bytes() == before
