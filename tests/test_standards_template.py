"""The export fills the Word original in place when the standard's folder holds one (0.16.0): the owner,
2026-10-29, "can we make it exactly like the template? I still want all the columns to pop up in every page
but otherwise we need to match the template exactly."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tests.conftest import PLAN, SEED_WEIGHTS
from tests.test_standards import _stub, standards_dir

WINWORD = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft Office/root/Office16/WINWORD.EXE"
PARAMETERS = ({"name": "vehicle_type", "value": "Wheel Loader"}, {"name": "fusa_engineer", "value": "the contractor"})


@pytest.fixture
def standards(tmp_path, monkeypatch):
    return standards_dir(tmp_path, monkeypatch)


def _original(path: Path) -> Path:
    """The Word original the test standard's Markdown was imported from: the same units, its blanks unnamed
    (the Markdown's first heading is its title, so the Word file has the title only)."""
    import docx

    d = docx.Document()
    d.add_paragraph("__________ Safety Plan (test)", style="Title")
    p = d.add_paragraph()
    p.add_run("Author: ").bold = True
    p.add_run("__________")
    t = d.add_table(rows=3, cols=3)
    t.style = "Table Grid"
    for c, h in enumerate(("Deliverable", "Expected Duration/Deadline", "Status")):
        t.cell(0, c).text = h
    t.cell(1, 0).text, t.cell(1, 1).text, t.cell(1, 2).text = "Safety Plan", "__ points\n__________", "_____"
    t.cell(2, 0).text, t.cell(2, 1).text, t.cell(2, 2).text = "HARA", "__ points\n__________", "_____"
    d.sections[0].footer.paragraphs[0].text = "Proprietary & Confidential"
    path.parent.mkdir(parents=True, exist_ok=True)
    d.save(str(path))
    return path


def test_export_fills_the_word_original_when_the_standard_has_one(seeded, standards, tmp_path, monkeypatch):
    import docx
    from docx.oxml.ns import qn

    original = _original(standards / "qf-17-test" / "source" / "QF-17 test.docx")
    assert seeded.execute("plan", action="weights", what="load", file=str(SEED_WEIGHTS)).ok
    assert seeded.execute("create", entity="sprint", data={
        "number": 2, "label": "SPRINT 2", "start": "2026-10-27", "end": "2026-11-09", "status": "Active",
    }).ok
    for data in PARAMETERS:
        assert seeded.execute("create", entity="parameter", data=data).ok
    assert seeded.execute("update", entity=PLAN, id=1, set=["status=Ongoing", "jira_key=hwl-2554", "points=5"]).ok
    _stub(seeded, monkeypatch, {"HWL-2554": "In Progress"})
    listed = seeded.execute("standards", action="list")
    assert listed.ok and listed.data["standards"][0]["template"] == str(original)

    out = tmp_path / "out"
    result = seeded.execute("plan", action="export", row=1, out=str(out))
    assert result.ok, result.errors
    [built] = result.data["exports"]
    assert built["template"] == str(original) and built["exact"]["docx"] is True
    assert Path(built["files"]["docx"]) == out / "qf-17-test.docx" and Path(built["files"]["md"]).is_file()
    word = docx.Document(built["files"]["docx"])
    assert word.paragraphs[0].text == "Wheel Loader Safety Plan (test)" and word.paragraphs[0].style.name == "Title"
    assert word.core_properties.title == "Wheel Loader Safety Plan (test)"
    author = word.paragraphs[1]
    assert author.text == "Author: the contractor" and author.runs[0].bold and author.runs[0].text == "Author: "
    table = word.tables[0]
    assert table.style.name == "Table Grid" and table.rows[0]._tr.find(".//" + qn("w:tblHeader")) is not None
    assert [p.text for p in table.cell(1, 1).paragraphs] == ["5 points", "2026-11-09"]
    assert table.cell(1, 2).text == "In Progress"
    assert [p.text for p in table.cell(2, 1).paragraphs] == ["3 points", "2026-11-09"]
    assert table.cell(2, 2).text == "{{ row_2_status }}"  # unfilled stays, as the Markdown's does
    assert word.sections[0].footer.paragraphs[0].text == "Proprietary & Confidential"
    assert "==" not in word.paragraphs[0].text  # the template exactly: no marks in the Word file
    assert "==Wheel Loader==" in Path(built["files"]["md"]).read_text(encoding="utf-8")  # the source keeps them
    if WINWORD.is_file():
        assert built["exact"]["pdf"] is True and Path(built["files"]["pdf"]) == out / "qf-17-test.pdf"
        assert Path(built["files"]["pdf"]).stat().st_size > 1000
        assert not any("pdf through Word" in w for w in result.warnings)
    else:
        assert built["exact"]["pdf"] is False and Path(built["files"]["pdf"]).is_file()
        assert any("the PDF is Gutenberg's rendering" in w for w in result.warnings)


def test_a_failed_print_keeps_gutenbergs_pdf(seeded, standards, tmp_path, monkeypatch):
    """0.16.1: when Word cannot print, the PDF is Gutenberg's rendering, as 0.16.0 promised. asi_gutenberg 0.7.0
    removed that rendering before asking Word, so a failed print (no Word on the machine, as on the CI runner)
    left the export naming a PDF that was gone; 0.7.1 prints to a working name and leaves the target alone."""
    import subprocess

    _original(standards / "qf-17-test" / "source" / "QF-17 test.docx")
    for data in PARAMETERS:
        assert seeded.execute("create", entity="parameter", data=data).ok
    _stub(seeded, monkeypatch, {})

    def no_word(*args, **kwargs):
        raise OSError("no Word here")

    monkeypatch.setattr(subprocess, "run", no_word)  # what asi_gutenberg's pdf_with_word calls
    result = seeded.execute("plan", action="export", row=1, out=str(tmp_path / "out"))
    assert result.ok, result.errors
    [built] = result.data["exports"]
    assert built["exact"] == {"docx": True, "pdf": False}
    assert Path(built["files"]["pdf"]) == tmp_path / "out" / "qf-17-test.pdf" and Path(built["primary"]).is_file()
    assert Path(built["primary"]).stat().st_size > 1000
    assert any("pdf through Word failed: no Word here; the PDF is Gutenberg's rendering" in w for w in result.warnings)


def test_a_folder_without_an_original_exports_as_before(seeded, standards):
    listed = seeded.execute("standards", action="list")
    assert listed.ok and listed.data["standards"][0]["template"] is None


def test_two_originals_name_none(seeded, standards):
    _original(standards / "qf-17-test" / "source" / "one.docx")
    _original(standards / "qf-17-test" / "source" / "two.docx")
    listed = seeded.execute("standards", action="list")
    assert listed.ok and listed.data["standards"][0]["template"] is None


@pytest.mark.skipif(not WINWORD.is_file(), reason="Word is not installed here")
def test_the_pdf_is_words_print(seeded, standards, tmp_path, monkeypatch):
    _original(standards / "qf-17-test" / "source" / "QF-17 test.docx")
    for data in PARAMETERS:
        assert seeded.execute("create", entity="parameter", data=data).ok
    _stub(seeded, monkeypatch, {})
    result = seeded.execute("plan", action="export", row=1, out=str(tmp_path / "out"))
    assert result.ok, result.errors
    [built] = result.data["exports"]
    assert built["exact"] == {"docx": True, "pdf": True} and Path(built["primary"]).name == "qf-17-test.pdf"
