"""Descriptive EDA over an existing validation result; no I/O or predictions."""

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
import re
import unicodedata

import pandas as pd

from playerlens.validation import ValidationResult, normalise_for_duplicates

DEVELOPMENT_IDS = (
    "133794078", "134145932", "133044877", "133185284", "133591153",
    "133830629", "132060506", "133903884",
)
LENGTH_BANDS = ("blank", "1-5", "6-20", "21-50", "51-100", "101-200", ">200")
PLAYTIME_BANDS = ("under 10h", "10-under 50h", "50-under 100h", "100h+", "unknown/invalid")
RECOMMENDATIONS = ("recommended", "not_recommended", "unknown/invalid")
# A small, fixed function-word list, not a feature/opinion vocabulary. Negators stay.
STOPWORDS = frozenset("a an the and or but if as at by for from in into of on to with "
                      "is are was were be been being it its this that these those "
                      "i me my we our you your he she they their them have has had "
                      "do does did so than then there here very just also".split())
SETTINGS = {
    "schema_version": 1, "seed": 42, "sampling": "none; full input",
    "word_count": "original whitespace split", "quantile_interpolation": "linear",
    "length_bands": list(LENGTH_BANDS), "playtime_bands": list(PLAYTIME_BANDS),
    "playtime_source": "author_playtime_at_review; minutes / 60",
    "low_volume_below": 20, "top_terms": 20,
    "term_preprocessing": "NFKC, casefold, remove URLs/HTML/BBCode, Unicode words; no stemming",
    "term_frequency": "number of eligible reviews containing a term; one occurrence per review",
    "term_stopwords": sorted(STOPWORDS), "development_example_ids": list(DEVELOPMENT_IDS),
}


@dataclass
class EDAResult:
    summary: dict
    tables: dict[str, pd.DataFrame]


def _share(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _cohort(label: str, rows: pd.DataFrame) -> dict:
    """Every recommendation rate carries its own valid-value denominator."""
    counts = rows["recommendation"].value_counts()
    yes = int(counts.get("recommended", 0))
    no = int(counts.get("not_recommended", 0))
    nonblank = int(rows["nonblank"].sum())
    return {
        "group": label, "review_count": len(rows), "nonblank": nonblank,
        "blank": len(rows) - nonblank, "recommended": yes, "not_recommended": no,
        "unknown_recommendation": len(rows) - yes - no,
        "recommendation_denominator": yes + no,
        "recommended_share": _share(yes, yes + no),
        "text_denominator": nonblank,
        "short_nonblank": int((rows["nonblank"] & rows["words"].le(5)).sum()),
        "low_volume": len(rows) < 20,
        "recommendation_low_volume": yes + no < 20,
    }


def _numeric(label: str, field: str, values: pd.Series) -> dict:
    valid = values.dropna()
    # Convert before reductions so signed Int64 addition cannot overflow.
    numeric = valid.astype(float)
    row = {"group": label, "field": field, "review_count": len(values),
           "valid": len(valid), "missing_or_invalid": len(values) - len(valid),
           "zero": int(valid.eq(0).sum()), "positive": int(valid.gt(0).sum()),
           "positive_share": _share(int(valid.gt(0).sum()), len(valid)),
           "low_volume": len(valid) < 20}
    row.update({name: float(numeric.quantile(q, interpolation="linear")) if len(valid) else None
                for name, q in (("min", 0), ("q25", .25), ("median", .5),
                                ("q75", .75), ("p90", .9), ("p99", .99), ("max", 1))})
    row["mean"] = float(numeric.mean()) if len(valid) else None
    return row


def _length_band(count: int, nonblank: bool) -> str:
    if not nonblank:
        return "blank"
    for limit, label in zip((5, 20, 50, 100, 200), LENGTH_BANDS[1:-1]):
        if count <= limit:
            return label
    return ">200"


def _playtime_band(minutes: object) -> str:
    if pd.isna(minutes):
        return "unknown/invalid"
    for limit, label in zip((600, 3000, 6000), PLAYTIME_BANDS):
        if minutes < limit:
            return label
    return "100h+"


def term_set(text: str) -> set[str]:
    """Temporary count-only representation, never substituted for source text."""
    text = unicodedata.normalize("NFKC", text).casefold()
    text = re.sub(r"https?://\S+|www\.\S+", " ", text)
    text = re.sub(r"</?[a-z][^>]*>|\[/?(?:b|i|u|s|strike|url|quote|list|h[1-6])(?:=[^\]]*)?\]", " ", text)
    words = re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)*", text)
    return {word for word in words if len(word) > 1 and word not in STOPWORDS}


def _terms(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    nonblank = frame.loc[frame["nonblank"]]
    cohorts = [("all", nonblank)] + [(label, nonblank.loc[nonblank["recommendation"].eq(label)])
                                      for label in RECOMMENDATIONS]
    for label, cohort in cohorts:
        for view in ("all_reviews", "unique_normalised_texts"):
            eligible = cohort if view == "all_reviews" else cohort.drop_duplicates("duplicate_key")
            counts = Counter(term for terms in eligible["terms"] for term in terms)
            ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:20]
            for rank, (term, count) in enumerate(ordered, 1):
                rows.append({"view": view, "group": label, "rank": rank, "term": term,
                             "document_count": count, "denominator": len(eligible),
                             "share": _share(count, len(eligible)), "low_volume": len(eligible) < 20})
    return pd.DataFrame(rows, columns=["view", "group", "rank", "term", "document_count",
                                      "denominator", "share", "low_volume"])


def _periods(frame: pd.DataFrame, weekly: bool) -> pd.DataFrame:
    """Fill calendar gaps; dates retain the source's unknown timezone."""
    columns = ["period_start", "period_end", "partial", *list(_cohort("", frame))]
    dated = frame.loc[frame["day"].notna()]
    if dated.empty:
        return pd.DataFrame(columns=columns)
    first, last = min(dated["day"]), max(dated["day"])
    start = first - timedelta(days=first.weekday()) if weekly else first
    step = timedelta(days=7 if weekly else 1)
    rows = []
    while start <= last:
        end = start + step - timedelta(days=1)
        mask = dated["day"].ge(start) & dated["day"].le(end)
        # Boundary days are partial even when a complete timestamp range is unknown.
        partial = start <= first <= end or start <= last <= end
        rows.append({"period_start": start.isoformat(), "period_end": end.isoformat(),
                     "partial": partial, **_cohort(start.isoformat(), dated.loc[mask])})
        start += step
    return pd.DataFrame(rows, columns=columns)


def build_eda(result: ValidationResult) -> EDAResult:
    """Build aggregate tables without mutating raw or validated input tables."""
    frame = result.validated.copy(deep=True)
    text = result.raw["review"]
    frame["nonblank"] = text.str.strip().ne("")
    frame["words"] = text.str.split().str.len()
    frame["characters"] = text.str.len()
    frame["length_band"] = [_length_band(n, b) for n, b in zip(frame["words"], frame["nonblank"])]
    frame["recommendation"] = frame["voted_up"].map({True: "recommended", False: "not_recommended"}).fillna("unknown/invalid")
    frame["playtime_band"] = frame["author_playtime_at_review"].map(_playtime_band)
    frame["playtime_hours"] = frame["author_playtime_at_review"].astype("Float64") / 60
    frame["duplicate_key"] = text.map(normalise_for_duplicates)
    frame["terms"] = text.map(term_set)
    frame["day"] = frame["created"].map(lambda value: None if pd.isna(value) else value.date())

    tables = {}
    tables["recommendations"] = pd.DataFrame([
        {"group": label, "review_count": int(frame["recommendation"].eq(label).sum()),
         "denominator": len(frame), "share": _share(int(frame["recommendation"].eq(label).sum()), len(frame))}
        for label in RECOMMENDATIONS])
    tables["lengths"] = pd.DataFrame([_cohort(label, frame.loc[frame["length_band"].eq(label)]) for label in LENGTH_BANDS])
    tables["playtime"] = pd.DataFrame([_cohort(label, frame.loc[frame["playtime_band"].eq(label)]) for label in PLAYTIME_BANDS])
    quality = {}
    for issue in result.issues:
        key = (issue.field, issue.code, issue.severity)
        quality.setdefault(key, set()).add(issue.data_row)
    tables["quality"] = pd.DataFrame([
        {"field": key[0], "code": key[1], "severity": key[2], "affected_reviews": len(indices),
         "denominator": len(frame), "share": _share(len(indices), len(frame))}
        for key, indices in sorted(quality.items())],
        columns=["field", "code", "severity", "affected_reviews", "denominator", "share"])

    duplicates, sizes = [], []
    nonblank = frame.loc[frame["nonblank"]]
    for mode, values in (("exact", nonblank["review"]), ("normalised", nonblank["duplicate_key"])):
        counts = values.value_counts()
        repeated = counts.loc[counts.gt(1)]
        duplicates.append({"mode": mode, "nonblank_denominator": len(nonblank),
                           "distinct_texts": len(counts), "repeated_groups": len(repeated),
                           "reviews_in_groups": int(repeated.sum()),
                           "additional_occurrences": int((repeated - 1).sum())})
        for size, count in sorted(Counter(counts.tolist()).items()):
            sizes.append({"mode": mode, "group_size": size, "text_groups": count,
                          "review_count": size * count})
    tables["duplicates"] = pd.DataFrame(duplicates)
    tables["duplicate_sizes"] = pd.DataFrame(sizes, columns=["mode", "group_size", "text_groups", "review_count"])

    numeric_rows, distribution = [], []
    cohorts = [("all", frame)] + [(label, frame.loc[frame["recommendation"].eq(label)]) for label in RECOMMENDATIONS]
    cohorts += [("words:" + label, frame.loc[frame["length_band"].eq(label)]) for label in LENGTH_BANDS]
    for field in ("words", "characters", "playtime_hours", "votes_up"):
        for label, cohort in cohorts:
            values = cohort.loc[cohort["nonblank"], field] if field in ("words", "characters") else cohort[field]
            numeric_rows.append(_numeric(label, field, values))
        eligible = frame.loc[frame["nonblank"], field] if field in ("words", "characters") else frame[field]
        counts = eligible.dropna().value_counts().sort_index()
        cumulative = 0
        for value, count in counts.items():
            cumulative += int(count)
            distribution.append({"field": field, "value": float(value), "review_count": int(count),
                                 "denominator": int(counts.sum()), "cumulative_share": cumulative / int(counts.sum())})
    tables["numeric_summary"] = pd.DataFrame(numeric_rows)
    tables["distributions"] = pd.DataFrame(distribution, columns=["field", "value", "review_count", "denominator", "cumulative_share"])
    tables["daily"] = _periods(frame, weekly=False)
    tables["weekly"] = _periods(frame, weekly=True)
    tables["terms"] = _terms(frame)

    # Only pre-reserved development IDs can expose individual text in the report.
    examples = frame.loc[frame["id"].isin(DEVELOPMENT_IDS), ["id", "review", "recommendation", "words"]].copy()
    order = {review_id: index for index, review_id in enumerate(DEVELOPMENT_IDS)}
    tables["development_examples"] = examples.sort_values("id", key=lambda ids: ids.map(order)).reset_index(drop=True)
    summary = {
        "input": dict(result.summary["input"]), "settings": dict(SETTINGS),
        "validation": dict(result.summary["validation"]), "rows": len(frame),
        "overall": _cohort("all", frame), "dates_missing_or_invalid": int(frame["day"].isna().sum()),
        "text": dict(result.summary["text"]), "duplicates": dict(result.summary["duplicates"]),
        "recommendations": dict(result.summary["recommendations"]),
        "example_count": len(examples), "aspect_usefulness_share": None,
        "aspect_usefulness_status": "not estimated; requires manually validated labels",
        "term_denominators": {label: {"all_reviews": len(cohort.loc[cohort["nonblank"]]),
                                      "unique_normalised_texts": cohort.loc[cohort["nonblank"], "duplicate_key"].nunique()}
                              for label, cohort in cohorts[:4]},
    }
    return EDAResult(summary, tables)
