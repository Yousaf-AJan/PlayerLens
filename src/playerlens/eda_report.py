"""Write local EDA tables, static figures and a readable report."""

from datetime import datetime, timezone
from importlib.metadata import version
import json
import os
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
import pandas as pd

from playerlens.eda import EDAResult


def _markdown_table(table: pd.DataFrame) -> str:
    """Small dependency-free Markdown tables; no optional tabulate package."""
    def cell(value: object) -> str:
        if pd.isna(value):
            return "not estimable"
        if isinstance(value, float):
            return f"{value:.4f}"
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    lines = ["| " + " | ".join(map(str, table.columns)) + " |",
             "| " + " | ".join("---" for _ in table.columns) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in table.itertuples(index=False, name=None)]
    return "\n".join(lines)


def _figures(eda: EDAResult, output: Path) -> list[str]:
    # Local font cache; Agg renders files without opening a GUI or using the network.
    os.environ.setdefault("MPLCONFIGDIR", str(Path(".cache/matplotlib").resolve()))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = []
    colors = ("#246d87", "#c36747", "#8b9299")
    with plt.rc_context({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titleweight": "bold", "figure.facecolor": "white"}):
        def save(fig, name):
            try:
                fig.savefig(output / name, dpi=150, bbox_inches="tight")
                names.append(name)
            finally:
                plt.close(fig)

        rec = eda.tables["recommendations"]
        fig, ax = plt.subplots(figsize=(8, 4))
        bars = ax.bar(rec["group"], rec["review_count"], color=colors)
        ax.bar_label(bars, padding=3)
        ax.set(title="Overall Steam recommendations", ylabel="Reviews (all records)")
        ax.margins(y=.15)
        save(fig, "recommendations.png")

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        lengths = eda.tables["lengths"]
        axes[0].bar(lengths["group"], lengths["review_count"], color=colors[0])
        axes[0].set(title="Review length bands", xlabel="Whitespace words", ylabel="Reviews")
        axes[0].tick_params(axis="x", rotation=25)
        words = eda.tables["distributions"].query("field == 'words'")
        if not words.empty:
            axes[1].step(words["value"], words["cumulative_share"], where="post", color=colors[0])
            axes[1].set_xscale("log")
        else:
            axes[1].text(.5, .5, "No nonblank reviews", ha="center", transform=axes[1].transAxes)
        axes[1].set(title="Nonblank length: cumulative distribution", xlabel="Words (log scale)",
                    ylabel="Share of nonblank reviews", ylim=(0, 1.02))
        fig.tight_layout()
        save(fig, "lengths.png")

        fig, ax = plt.subplots(figsize=(8, 4))
        sizes = eda.tables["duplicate_sizes"]
        for mode, color in zip(("exact", "normalised"), colors):
            subset = sizes.loc[sizes["mode"].eq(mode)]
            if not subset.empty:
                ax.plot(subset["group_size"], subset["text_groups"], "o-", label=mode, color=color)
        if not sizes.empty:
            ax.set_xscale("log")
            ax.set_yscale("log")
            ax.legend()
        else:
            ax.text(.5, .5, "No nonblank text", ha="center", transform=ax.transAxes)
        ax.set(title="Text group sizes (nonblank reviews)", xlabel="Reviews per text group (log)",
               ylabel="Number of text groups (log)")
        save(fig, "duplicates.png")

        fig, axes = plt.subplots(1, 2, figsize=(12, 4))
        playtime = eda.tables["playtime"]
        axes[0].bar(playtime["group"], playtime["review_count"], color=colors[0])
        axes[0].set(title="Playtime at review", ylabel="Reviews")
        axes[0].tick_params(axis="x", rotation=25)
        valid = playtime.loc[playtime["recommended_share"].notna()]
        axes[1].bar(valid["group"], valid["recommended_share"] * 100, color=colors[0])
        axes[1].set(title="Recommended within each playtime band", ylabel="% of valid recommendations", ylim=(0, 105))
        axes[1].tick_params(axis="x", rotation=25)
        for index, row in enumerate(valid.itertuples()):
            suffix = " *" if row.recommendation_low_volume else ""
            axes[1].text(index, row.recommended_share * 100 + 1, f"n={row.recommendation_denominator}{suffix}", ha="center", fontsize=8)
        fig.suptitle("Minutes / 60; * denominator below 20", fontsize=10)
        fig.tight_layout()
        save(fig, "playtime.png")

        fig, ax = plt.subplots(figsize=(8, 4))
        votes = eda.tables["distributions"].query("field == 'votes_up'")
        if not votes.empty:
            ax.hist(np.log1p(votes["value"].to_numpy(dtype=float)), bins=25,
                    weights=votes["review_count"], color=colors[0], edgecolor="white")
        else:
            ax.text(.5, .5, "No valid helpful-vote counts", ha="center", transform=ax.transAxes)
        ax.set(title="Helpful-vote distribution", xlabel="log(1 + votes_up), natural log", ylabel="Reviews with valid vote counts")
        save(fig, "helpful_votes.png")

        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
        daily = eda.tables["daily"]
        if not daily.empty:
            dates = pd.to_datetime(daily["period_start"])
            axes[0].bar(dates, daily["review_count"], color=colors[0])
            axes[1].plot(dates, daily["recommended_share"] * 100, "o-", color=colors[0], markersize=3)
            low = daily["recommendation_low_volume"] & daily["recommended_share"].notna()
            if low.any():
                axes[1].scatter(dates.loc[low], daily.loc[low, "recommended_share"] * 100, color=colors[1], label="denominator <20")
                axes[1].legend(loc="best")
            for boundary in (dates.iloc[0], dates.iloc[-1]):
                for ax in axes:
                    ax.axvline(boundary, color=colors[1], linestyle="--", alpha=.7)
        else:
            axes[0].text(.5, .5, "No valid source dates", ha="center", transform=axes[0].transAxes)
        axes[0].set(title="Daily observations in this CSV (boundary days partial)", ylabel="Reviews")
        axes[1].set(ylabel="Recommended / valid (%)", xlabel="Source calendar date; timezone unknown", ylim=(0, 105))
        fig.autofmt_xdate()
        fig.tight_layout()
        save(fig, "dates.png")

        fig, axes = plt.subplots(1, 2, figsize=(12, 6), sharex=True)
        terms = eda.tables["terms"]
        for ax, group, title in zip(axes, ("recommended", "not_recommended"), ("Recommended", "Not recommended")):
            subset = terms.loc[terms["view"].eq("all_reviews") & terms["group"].eq(group)].head(15).iloc[::-1]
            if subset.empty:
                ax.text(.5, .5, "No eligible terms", ha="center", transform=ax.transAxes)
            else:
                ax.barh(subset["term"], subset["share"] * 100, color=colors[0])
            denominator = eda.summary["term_denominators"][group]["all_reviews"]
            ax.set(title=f"{title}: n={denominator} nonblank", xlabel="% of nonblank reviews containing term")
        fig.suptitle("Common terms are vocabulary counts, not aspect/opinion predictions", fontsize=11)
        fig.tight_layout()
        save(fig, "terms.png")
    return names


def write_eda_report(eda: EDAResult, output: Path, source: Path, started: str | None = None) -> dict:
    """Refuse existing content; run.json is written last as completion marker."""
    source, output = source.resolve(), output.resolve()
    if output == source.parent or source.parent in output.parents:
        raise ValueError("Output must be outside the input directory to protect source data.")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("EDA output must be a new or empty directory; choose a fresh --output path.")
    clock = perf_counter()
    output.mkdir(parents=True, exist_ok=True)
    outputs = []
    (output / "summary.json").write_text(json.dumps(eda.summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    outputs.append("summary.json")
    for name, table in eda.tables.items():
        filename = name + ".csv"
        table.to_csv(output / filename, index=False, lineterminator="\n")
        outputs.append(filename)
    figures = _figures(eda, output)
    outputs += figures

    summary = eda.summary
    stats = eda.tables["numeric_summary"]
    report = ["# PlayerLens: exploratory data analysis", "",
              "## Dataset-wide quantitative findings", "",
              f"Source SHA-256: `{summary['input']['sha256']}`. "
              f"Validation status: **{summary['validation']['status']}**; "
              f"{summary['validation']['error_count']} errors, {summary['validation']['warning_count']} warnings.", "",
              f"The CSV contains **{summary['rows']:,}** reviews, "
              f"**{summary['text']['nonblank']:,}** nonblank texts and **{summary['text']['blank']:,}** blanks. "
              f"**{summary['text']['nonblank_five_words_or_fewer']:,}** nonblank reviews have at most five whitespace words.", "",
              "Shares are fractions in CSV/JSON. Undefined rates are empty CSV cells / JSON null. "
              "Repeated reviews remain in primary summaries; unique-text results are separately labelled.", ""]
    for heading, name in (("Recommendation counts (denominator: all rows)", "recommendations"),
                          ("Field issues (a review can have multiple issues)", "quality"),
                          ("Review length bands", "lengths"), ("Duplicate text", "duplicates"),
                          ("Playtime at review", "playtime")):
        report += ["### " + heading, "", _markdown_table(eda.tables[name]), ""]
    report += ["### Numeric distributions", "", "Text lengths exclude blanks. Numeric summaries exclude missing/invalid values; "
               "see valid and missing counts. Quantiles use linear interpolation. Mean, median and tail percentiles describe this snapshot, not a population.", "",
               _markdown_table(stats.loc[stats["group"].eq("all")]), "",
               "### Descriptive recommendation-group comparisons", "",
               "Compare within-group summaries, not raw group totals: the two recommendation groups "
               "have very different sizes. No significance or causal interpretation is implied. "
               "Length summaries exclude blank text; playtime/vote summaries retain those records when their numeric values are valid.", "",
               _markdown_table(stats.loc[stats["group"].isin(("recommended", "not_recommended")),
                                         ["group", "field", "valid", "missing_or_invalid", "median", "mean", "p90", "positive_share"]]), "",
               "### Helpful votes by review length", "",
               "The positive_share denominator is the valid vote count within each length band. "
               "Vote totals reflect accumulated attention with unknown exposure, not review quality or an exposure-adjusted rate.", "",
               _markdown_table(stats.loc[stats["group"].str.startswith("words:") & stats["field"].eq("votes_up"),
                                         ["group", "valid", "missing_or_invalid", "zero", "median", "p90", "positive_share", "low_volume"]]), "",
               "### Weekly calendar observations", "",
               f"Missing/invalid source dates: {summary['dates_missing_or_invalid']}. "
               "Weeks are Monday–Sunday. Boundary days/weeks are conservatively partial. "
               "Zero-count days mean no rows in this snapshot, not no Steam activity.", "",
               _markdown_table(eda.tables["weekly"]), "",
               "### Common-term sensitivity", "",
               "terms.csv reports top 20 terms per cohort and view. Each term counts once per review; "
               "denominators include all nonblank reviews, even those yielding no eligible tokens. "
               "The unique-normalised-text view deduplicates separately within each recommendation group; "
               "groups can overlap across recommendations. These are descriptive words, not detected aspects or sentiments.", ""]
    report += ["Checklist options (including unchecked ones), quotations and references to other games "
               "can contribute terms. Vocabulary presence does not establish a selected opinion about Elden Ring.", ""]
    for figure in figures:
        report += [f"![{figure.removesuffix('.png').replace('_', ' ')}]({figure})", ""]
    report += ["## Qualitative development examples — not a population estimate", "",
               "Only the eight previously inspected development-only IDs are eligible below. "
               "Their related groups must remain outside final evaluation. These examples are not representative, "
               "are not new annotation labels, and cannot estimate the percentage of aspect-useful reviews. "
               "A brief review can name a feature; a long one need not provide usable feature evidence. "
               "Aspect usefulness remains unmeasured until manually validated labels exist.", ""]
    examples = eda.tables["development_examples"]
    if examples.empty:
        report += ["No reserved development examples occur in this input.", ""]
    for row in examples.itertuples(index=False):
        report += [f"### Review {row.id} ({row.recommendation}; {row.words} words)", ""]
        # Indented code preserves original wording without rendering HTML/Markdown.
        report += ["    " + line for line in row.review.splitlines() or [""]]
        report += [""]
    report += ["## Limits and reproducibility", "",
               "One game, a short date range, unknown collection completeness and source timezone. "
               "No causal, game-update, review-bombing, long-term, or cross-game conclusions. "
               "Recommendations are not aspect-level sentiment labels; helpful votes are not ground truth or a rate. "
               "Language metadata is not verified language classification. Source licence verification is pending.", "",
               "Cells with fewer than 20 eligible records are flagged in tables. "
               "Undefined statistics remain missing; no statistical significance or model quality is claimed. "
               "Playtime uses author_playtime_at_review / 60; consistency warnings remain visible in quality.csv. "
               "No original values are corrected or removed.", "",
               "summary.json and CSVs are deterministic for the same input/settings/software. "
               "run.json contains machine paths, times and versions; PNG pixel identity across machines is not guaranteed. "
               "A missing run.json means report generation did not complete. All generated content, "
               "including the original development examples, must remain local and ignored.", "",
               "## Output tables", ""]
    report += [f"- [{name}]({name})" for name in outputs if name.endswith((".csv", ".json"))]
    (output / "report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    outputs.append("report.md")
    manifest = {
        "started_at_utc": started or datetime.now(timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "report_seconds": perf_counter() - clock,
        "input_path": str(source), "output_path": str(output), "input_sha256": summary["input"]["sha256"],
        "settings": summary["settings"], "python": platform.python_version(), "platform": platform.platform(),
        "dependencies": {name: version(name) for name in ("playerlens", "pandas", "numpy", "matplotlib")},
        "status": summary["validation"]["status"], "complete": True, "outputs": outputs,
    }
    (output / "run.json").write_text(json.dumps(manifest, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    return manifest
