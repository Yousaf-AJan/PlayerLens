"""Synthetic data only: the real dataset is never needed by unit tests."""

import csv

import pytest

from playerlens.validation import REQUIRED_COLUMNS


@pytest.fixture
def review_record():
    return {
        "id": "001", "language": "english", "review": "Synthetic review: crashes constantly.",
        "created": "2023-01-29 14:32:52", "voted_up": "False", "votes_up": "0",
        "comment_count": "0", "steam_purchase": "True", "recieved_for_free": "False",
        "written_during_early_access": "False", "author_num_games_owned": "4",
        "author_num_reviews": "1", "author_playtime_forever": "120",
        "author_playtime_last_two_weeks": "60", "author_playtime_at_review": "90",
        "author_last_played": "2023-03-07 14:30:53",
    }


@pytest.fixture
def csv_factory(tmp_path, review_record):
    def create(overrides=None, *, columns=REQUIRED_COLUMNS, encoding="utf-8"):
        path = tmp_path / "raw" / "input.csv"
        path.parent.mkdir(exist_ok=True)
        updates = overrides if overrides is not None else [{}]
        with path.open("w", encoding=encoding, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            for index, changes in enumerate(updates):
                writer.writerow(review_record | {"id": f"{index + 1:03d}"} | changes)
        return path
    return create
