"""Hand-calculated synthetic cases; no real reviews, models or network."""

import pandas as pd
import pytest

from playerlens.eda import build_eda, term_set
from playerlens.validation import validate_csv


def test_counts_denominators_and_input_preservation(csv_factory):
    result = validate_csv(csv_factory([
        {"review": "not bad", "voted_up": "True"},
        {"review": "", "voted_up": "False"},
        {"review": "specific feature detail", "voted_up": ""},
    ]))
    raw, parsed = result.raw.copy(deep=True), result.validated.copy(deep=True)
    eda = build_eda(result)
    overall = eda.summary["overall"]
    assert overall["review_count"] == 3
    assert overall["recommendation_denominator"] == 2
    assert overall["recommended_share"] == .5
    assert overall["text_denominator"] == 2
    assert overall["short_nonblank"] == 2
    assert eda.tables["recommendations"]["review_count"].tolist() == [1, 1, 1]
    assert eda.tables["recommendations"]["denominator"].tolist() == [3, 3, 3]
    assert eda.summary["aspect_usefulness_share"] is None
    assert eda.summary["example_count"] == 0
    pd.testing.assert_frame_equal(result.raw, raw)
    pd.testing.assert_frame_equal(result.validated, parsed)


def test_quality_counts_fields_without_claiming_distinct_reviews(csv_factory):
    eda = build_eda(validate_csv(csv_factory([{"voted_up": "", "votes_up": ""}, {}])))
    assert eda.summary["validation"]["rows_with_errors"] == 1
    assert eda.summary["validation"]["error_count"] == 2
    assert eda.tables["quality"]["affected_reviews"].tolist() == [1, 1]
    assert eda.tables["quality"]["share"].tolist() == [.5, .5]


@pytest.mark.parametrize(("count", "expected"), [
    (0, "blank"), (1, "1-5"), (5, "1-5"), (6, "6-20"), (20, "6-20"),
    (21, "21-50"), (50, "21-50"), (51, "51-100"), (100, "51-100"),
    (101, "101-200"), (200, "101-200"), (201, ">200"),
])
def test_length_boundaries(count, expected, csv_factory):
    eda = build_eda(validate_csv(csv_factory([{"review": " ".join(["synthetic"] * count)}])))
    lengths = eda.tables["lengths"].set_index("group")
    assert lengths.at[expected, "review_count"] == 1
    assert lengths["review_count"].sum() == 1


def test_numeric_quantiles_and_blank_exclusion(csv_factory):
    rows = [{"review": "word " * n, "votes_up": str(v)} for n, v in ((1, 0), (3, 0), (5, 2), (0, 100))]
    eda = build_eda(validate_csv(csv_factory(rows)))
    stats = eda.tables["numeric_summary"].query("group == 'all'").set_index("field")
    assert stats.at["words", "valid"] == 3
    assert stats.at["words", "median"] == 3
    assert stats.at["words", "q25"] == 2
    assert stats.at["votes_up", "median"] == 1
    assert stats.at["votes_up", "mean"] == 25.5
    assert stats.at["votes_up", "positive_share"] == .5
    dist = eda.tables["distributions"].query("field == 'words'")
    assert dist["denominator"].tolist() == [3, 3, 3]
    assert dist["cumulative_share"].tolist() == [1 / 3, 2 / 3, 1]


def test_duplicate_reconciliation_and_sensitivity(csv_factory):
    eda = build_eda(validate_csv(csv_factory([
        {"review": "Game game game", "voted_up": "True"},
        {"review": "game GAME game", "voted_up": "False"},
        {"review": "Game game game", "voted_up": "True"},
        {"review": " "},
    ])))
    dup = eda.tables["duplicates"].set_index("mode")
    assert dup.at["exact", "repeated_groups"] == 1
    assert dup.at["exact", "additional_occurrences"] == 1
    assert dup.at["normalised", "reviews_in_groups"] == 3
    assert dup.at["normalised", "additional_occurrences"] == 2
    assert eda.summary["rows"] == 4  # Primary counts retain repetitions and blanks.
    sizes = eda.tables["duplicate_sizes"]
    assert sizes.groupby("mode")["review_count"].sum().tolist() == [3, 3]
    terms = eda.tables["terms"].query("group == 'all' and term == 'game'").set_index("view")
    assert terms.at["all_reviews", "document_count"] == 3
    assert terms.at["unique_normalised_texts", "document_count"] == 1
    assert terms["share"].tolist() == [1, 1]


def test_playtime_minutes_boundaries_and_missing_values(csv_factory):
    values = ("0", "599", "600", "2999", "3000", "5999", "6000", "", "-1")
    rows = [{"author_playtime_at_review": value, "author_playtime_forever": "10000"} for value in values]
    eda = build_eda(validate_csv(csv_factory(rows)))
    bands = eda.tables["playtime"].set_index("group")
    assert bands["review_count"].tolist() == [2, 2, 2, 1, 2]
    stats = eda.tables["numeric_summary"].query("group == 'all' and field == 'playtime_hours'").iloc[0]
    assert stats["valid"] == 7
    assert stats["missing_or_invalid"] == 2
    assert stats["max"] == 100


def test_consistency_warning_is_visible_without_altering_playtime(csv_factory):
    eda = build_eda(validate_csv(csv_factory([{"author_playtime_at_review": "6000"}])))
    assert eda.tables["playtime"].set_index("group").at["100h+", "review_count"] == 1
    assert "exceeds_lifetime" in eda.tables["quality"]["code"].tolist()


def test_dates_gaps_monday_weeks_partial_periods_and_unknown_recommendations(csv_factory):
    rows = [
        {"created": "2023-01-29 14:00:00", "voted_up": "True"},
        {"created": "2023-01-30 12:00:00", "voted_up": ""},
        {"created": "2023-02-07 12:00:00", "voted_up": "False"},
        {"created": ""},
    ]
    eda = build_eda(validate_csv(csv_factory(rows)))
    daily = eda.tables["daily"].set_index("period_start")
    assert daily.at["2023-01-31", "review_count"] == 0
    assert pd.isna(daily.at["2023-01-31", "recommended_share"])
    assert pd.isna(daily.at["2023-01-30", "recommended_share"])
    assert daily["review_count"].sum() == 3
    assert eda.summary["dates_missing_or_invalid"] == 1
    weekly = eda.tables["weekly"]
    assert weekly["period_start"].tolist() == ["2023-01-23", "2023-01-30", "2023-02-06"]
    assert weekly["partial"].tolist() == [True, False, True]
    assert weekly["review_count"].tolist() == [1, 1, 1]
    assert weekly["low_volume"].all()


def test_all_missing_empty_groups_have_undefined_not_zero_statistics(csv_factory):
    eda = build_eda(validate_csv(csv_factory([
        {"review": "  ", "voted_up": "", "votes_up": "", "created": "", "author_playtime_at_review": ""},
    ])))
    assert eda.summary["overall"]["recommended_share"] is None
    assert eda.tables["terms"].empty
    assert eda.tables["daily"].empty
    assert eda.tables["weekly"].empty
    assert eda.tables["duplicate_sizes"].empty
    assert eda.tables["numeric_summary"]["median"].isna().all()


def test_negators_formatting_and_document_frequency(csv_factory):
    assert term_set("[b]Not[/b] no never <i>bad</i> https://example.com/hidden") == {"not", "no", "never", "bad"}
    eda = build_eda(validate_csv(csv_factory([
        {"review": "zebra zebra apple"}, {"review": "zebra apple"}, {"review": "the and"},
    ])))
    terms = eda.tables["terms"].query("group == 'all' and view == 'all_reviews'")
    assert terms["term"].tolist() == ["apple", "zebra"]
    assert terms["document_count"].tolist() == [2, 2]
    assert terms["denominator"].tolist() == [3, 3]
    assert terms["share"].tolist() == [2 / 3, 2 / 3]


def test_only_previously_reserved_ids_expose_text(csv_factory):
    eda = build_eda(validate_csv(csv_factory([
        {"id": "134145932", "review": "Synthetic reserved example"},
        {"id": "999999999", "review": "Synthetic unreserved text"},
        {"id": "133794078", "review": "Another synthetic reserved example"},
    ])))
    assert eda.tables["development_examples"]["id"].tolist() == ["133794078", "134145932"]
    assert eda.summary["example_count"] == 2
    assert eda.summary["aspect_usefulness_share"] is None


def test_largest_valid_vote_values_do_not_overflow_mean(csv_factory):
    eda = build_eda(validate_csv(csv_factory([{"votes_up": str(2**63 - 1)}] * 2)))
    row = eda.tables["numeric_summary"].query("group == 'all' and field == 'votes_up'").iloc[0]
    assert row["mean"] > 0
    assert row["mean"] == float(2**63 - 1)


def test_low_volume_uses_the_eligible_denominator(csv_factory):
    eda = build_eda(validate_csv(csv_factory([{"voted_up": "True"}] * 19 + [{"voted_up": ""}])))
    overall = eda.summary["overall"]
    assert overall["review_count"] == 20
    assert overall["low_volume"] is False
    assert overall["recommendation_denominator"] == 19
    assert overall["recommendation_low_volume"] is True
    assert overall["recommended_share"] == 1
