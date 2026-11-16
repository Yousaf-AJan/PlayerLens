"""Render populated/blank inputs and verify report and CLI contracts."""

import json

from PIL import Image
import pytest

from playerlens.cli import main
from playerlens.eda import build_eda
from playerlens import eda_report
from playerlens.validation import validate_csv


@pytest.mark.parametrize("blank", [False, True])
def test_cli_renders_complete_local_report_and_preserves_source(csv_factory, tmp_path, blank):
    path = csv_factory([{"review": "" if blank else "Synthetic controls feel good", "voted_up": "True"}])
    before = path.read_bytes()
    output = tmp_path / "eda"
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 0
    assert path.read_bytes() == before
    summary = json.loads((output / "summary.json").read_text())
    assert summary["rows"] == 1
    assert summary["aspect_usefulness_share"] is None
    manifest = json.loads((output / "run.json").read_text())
    assert manifest["complete"] is True
    assert set(manifest["outputs"]) == {p.name for p in output.iterdir()} - {"run.json"}
    images = list(output.glob("*.png"))
    assert len(images) == 7
    for image_path in images:
        with Image.open(image_path) as image:
            assert image.width >= 800
            image.verify()
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "Dataset-wide quantitative findings" in report
    assert "Qualitative development examples" in report
    assert "No reserved development examples" in report


def test_reports_are_deterministic_except_run_metadata(csv_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(eda_report, "_figures", lambda *_: [])
    path = csv_factory([{"review": "same phrase"}, {"review": "SAME PHRASE", "votes_up": ""}])
    eda = build_eda(validate_csv(path))
    first, second = tmp_path / "first", tmp_path / "second"
    eda_report.write_eda_report(eda, first, path)
    eda_report.write_eda_report(eda, second, path)
    for file in first.iterdir():
        if file.name != "run.json":
            assert file.read_bytes() == (second / file.name).read_bytes()
    assert json.loads((first / "run.json").read_text())["output_path"] != json.loads((second / "run.json").read_text())["output_path"]


def test_record_errors_write_flagged_reports_and_return_one(csv_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(eda_report, "_figures", lambda *_: [])
    path = csv_factory([{"voted_up": "maybe"}])
    output = tmp_path / "eda"
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 1
    assert json.loads((output / "run.json").read_text())["status"] == "invalid"
    assert "**invalid**" in (output / "report.md").read_text()


def test_fatal_validation_writes_no_reports(csv_factory, tmp_path):
    path = csv_factory([{"id": ""}])
    output = tmp_path / "eda"
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 2
    assert not output.exists()


def test_source_directory_and_existing_output_are_protected(csv_factory, tmp_path):
    path = csv_factory()
    before = path.read_bytes()
    assert main(["eda", "--input", str(path), "--output", str(path.parent / "reports")]) == 2
    output = tmp_path / "reports"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("untouched")
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 2
    assert sentinel.read_text() == "untouched"
    assert list(output.iterdir()) == [sentinel]
    assert path.read_bytes() == before


def test_io_failure_has_no_completion_manifest(csv_factory, tmp_path, monkeypatch):
    def denied(*_):
        raise PermissionError("Synthetic rendering I/O failure")
    monkeypatch.setattr(eda_report, "_figures", denied)
    path = csv_factory()
    output = tmp_path / "eda"
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 2
    assert not (output / "run.json").exists()


def test_reserved_text_is_literal_and_unreserved_text_is_not_exported(csv_factory, tmp_path, monkeypatch):
    monkeypatch.setattr(eda_report, "_figures", lambda *_: [])
    path = csv_factory([
        {"id": "133794078", "review": "<script>Synthetic reserved</script>\nnext line"},
        {"id": "99999", "review": "Synthetic unreserved phrase"},
    ])
    output = tmp_path / "eda"
    assert main(["eda", "--input", str(path), "--output", str(output)]) == 0
    report = (output / "report.md").read_text(encoding="utf-8")
    assert "    <script>Synthetic reserved</script>" in report
    assert "Synthetic unreserved phrase" not in report
    assert "99999" not in (output / "development_examples.csv").read_text()
