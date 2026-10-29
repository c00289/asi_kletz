"""The Control structures screen (0.24.0, docs/control-structure-plan.md phase 3, moved here from the sister
tool): the stacked tree, the form, the verbs behind every button, New from…, Delete asking, Validate, the
Export… dialog and its defaults, the preview re-rendered after a save, the preferences, the dashboard tile
and the automation surface. escher's ``build`` is monkeypatched to write stub files with a competent OCR
report, so the suite passes on CI without the engine; the structure is the synthetic one."""

from __future__ import annotations

import gc
import json
import time
import tkinter as tk
from pathlib import Path

import pytest

from asi_kletz.gui.control_structure_screen import PREF_EXPORT_DIR, stack
from asi_kletz.gui.dashboard import STPA_TILES
from asi_kletz.gui.screens import CONTROL_STRUCTURES_SCREEN
from asi_kletz.prefs import prefs_path
from asi_kletz.stpa.factory import DEFAULT_FORMATS, FORMATS
from tests.test_control_structures import COUNTS, UP_HILL, synthetic


def _tk_available() -> bool:
    try:
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        del root
        gc.collect()
        return True
    except tk.TclError:
        return False


pytestmark = pytest.mark.skipif(not _tk_available(), reason="no display for tkinter")


def png_bytes() -> bytes:
    """A small white PNG (Pillow comes with asi_escher): enough for the preview label to load."""
    import io

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 6), "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def window(brain):
    from asi_kletz.gui.main_window import MainWindow

    win = MainWindow(brain, interactive=False)
    win.withdraw()
    yield win
    win.close()
    del win
    gc.collect()


@pytest.fixture
def built(brain):
    row, _warnings = brain.control_structures.create_from_dataset(synthetic(), "test")
    return row


@pytest.fixture
def stub_escher(monkeypatch):
    """``asi_escher.build`` writes stub files and answers a competent OCR report; ``calls`` records each."""
    import asi_escher
    from asi_escher.ocr import OcrReport

    calls: list[dict] = []
    png = png_bytes()

    def build(diagram, out_dir, name=None, opts=None, dpi=160, formats=DEFAULT_FORMATS, provenance=True, ocr=False):
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        written = {}
        for fmt in formats:
            path = out / f"{name}.{fmt}"
            path.write_bytes(png if fmt == "png" else b"<stub/>")
            written[fmt] = str(path)
        calls.append({"name": name, "out": str(out), "formats": tuple(formats), "ocr": ocr, "title": diagram.title})
        report = None
        if ocr:
            expected = [str(n) for n in getattr(diagram, "nodes", [])]
            report = OcrReport(png=written.get("png", ""), expected=expected, available=True, language="test",
                               found=list(expected))
        return {**written, "size": (640, 480), "nodes": 9, "edges": 9, "issues": [], "ocr": report}

    monkeypatch.setattr(asi_escher, "build", build)
    return calls


def pump_until(window, condition, limit: float = 10.0) -> None:
    deadline = time.monotonic() + limit
    while not condition() and time.monotonic() < deadline:
        window.update()
        time.sleep(0.02)
    for _ in range(3):
        window.update()
    assert condition(), "the background work did not finish in time"


def _prefs() -> dict:
    path = Path(prefs_path())
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


# -- registration, the tile, the automation surface ------------------------------------------
def test_the_screen_is_registered_and_the_tile_opens_it(window, built, stub_escher):
    keys = [k for k, _ in window.factory.items()]
    assert CONTROL_STRUCTURES_SCREEN in keys and keys.index(CONTROL_STRUCTURES_SCREEN) < keys.index("transfer")
    assert window.factory.title(CONTROL_STRUCTURES_SCREEN) == "Control structures"
    assert STPA_TILES[0] == ("control_structure", "CS STRUCTURES", CONTROL_STRUCTURES_SCREEN)
    dash = window.show("dashboard")
    assert dash._stpa_vars["control_structure"].get() == "1" and dash._stpa_vars["stpa_analysis"].get() == "0"
    tile = next(
        t for t in dash.stpa_tiles.winfo_children()
        if any(str(c.cget("text")) == "CS STRUCTURES" for c in t.winfo_children())
    )
    assert tile.bind("<Button-1>")  # clickable: the tile opens the screen
    # the automation surface selects the screen by its key, as /screen {"show": "control_structures"} does
    assert window.server is not None
    result = window.server.show_screen(CONTROL_STRUCTURES_SCREEN)
    assert result.ok and result.data == {"screen": CONTROL_STRUCTURES_SCREEN, "title": "Control structures"}
    assert window.current_key == CONTROL_STRUCTURES_SCREEN and window.title().endswith("Control structures")
    listed = window.server.screens_data()["screens"]
    assert any(s["key"] == CONTROL_STRUCTURES_SCREEN and s["current"] for s in listed)


# -- the stack ----------------------------------------------------------------------------------
def test_stack_lists_a_controller_with_its_parts_and_unique_iids(brain, built):
    parts = brain.control_structures.parts(built["slug"])
    lines = stack(parts)
    iids = [line[0] for line in lines]
    assert len(iids) == len(set(iids)) == 34  # 8 controllers + 3 + 2 + 9 edges + 10 signals + Notes + 1
    assert [line[2] for line in lines if line[1] == 0] == [c["name"] for c in parts["controllers"]] + ["Notes"]
    # under the vehicle controller: its two algorithms, its entry, then the arrow it sends with its signal
    start = iids.index("controller:vehicle_controller")
    under = [line for line in lines[start + 1:] if line[1] > 0][:4]
    assert [u[0].split(":")[0] for u in under] == ["algorithm", "algorithm", "entry", "edge"]
    entry = next(line for line in lines if line[0].startswith("entry:") and "CA-20" in line[2])
    assert entry[4] == "Machine state, Obstacle list"  # the variables, one line each in the row, joined here
    edge = next(line for line in lines if line[0] == "edge:e4")
    assert edge[2].strip() == "↓ drive_actuators" and edge[3] == "control_action" and edge[4] == "1 signal"
    signal = lines[iids.index("edge:e4") + 1]
    assert signal[0].startswith("signal:") and signal[1] == 2 and signal[2].strip() == "CA-20"
    feedback = next(line for line in lines if line[0] == "edge:e2")
    assert feedback[2].strip() == "↑ remote_operator" and feedback[3] == "feedback"
    assert lines[-1][5] == "cs_note" and lines[-1][2].strip().startswith("Stops within")
    # a repeated key (a workbook edited by hand) opens the group again with a suffixed iid
    twice = dict(parts, controllers=parts["controllers"] + [dict(parts["controllers"][0])])
    twins = [line[0] for line in stack(twice) if line[0].startswith("controller:remote_operator")]
    assert twins == ["controller:remote_operator", "controller:remote_operator#2"]
    # an edge whose source is no controller is still painted, under its own group
    orphan = dict(parts, edges=parts["edges"] + [{"id": 99, "key": "e99", "kind": "feedback", "source": "ghost",
                                                  "target": "work_site"}])
    texts = [line[2] for line in stack(orphan)]
    assert "Edges without a source" in texts


def test_the_screen_stacks_the_structure_and_selecting_rows_fills_the_form(window, built, stub_escher):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    assert len(screen.tree.get_children()) == 1
    row = screen.tree.item(str(built["id"]))["values"]
    assert row[:3] == ["Demo Loader Control Structure", "Demo loader", "Draft"] and row[4:] == list(COUNTS.values())
    screen.select_structure(built["id"])
    assert len(screen.parts_tree.get_children()) == 34 and len(set(screen.parts_tree.get_children())) == 34
    assert "Control structure 1 selected" in window.status_text()
    screen.select_part("controller:vehicle_controller")
    assert screen.editing == "cs_controller" and screen.selected[0] == "cs_controller"
    assert screen.widgets["name"].get() == "Vehicle Controller" and screen.widgets["kind"].get() == "controller"
    assert "structure" not in screen.widgets and screen.form_box.cget("text").startswith("CS Controller details · row")
    assert "uid" not in screen.widgets  # the hidden identity has no widget (docs/hidden-identity-plan.md)
    signal_id = screen.parts["signals"][0]["id"]
    screen.select_part(f"signal:{signal_id}")
    assert screen.form_data() == {
        "edge": "e1", "order": "1", "signal_id": "CA-01", "kind": "control_action", "name": "Mission start",
        "placeholder": False,
    }
    assert list(screen.widgets["edge"].combo["values"]) == [e["key"] for e in screen.parts["edges"]]
    entry_id = screen.parts["process_model_entries"][0]["id"]
    screen.select_part(f"entry:{entry_id}")
    assert screen.widgets["variables"].get() == ["Mission state", "Site clearance"]  # one per line
    screen.select_part("notes")  # a group line: no form
    assert screen.editing is None and screen.selected is None
    # the search keeps the lines that open a match's groups
    screen.search_var.set("CA-20")
    shown = screen.parts_tree.get_children()
    assert "controller:vehicle_controller" in shown and "edge:e4" in shown and "controller:work_site" not in shown
    assert any(iid.startswith("signal:") for iid in shown)
    screen.search_var.set("")
    assert len(screen.parts_tree.get_children()) == 34


# -- Save, New child, Delete through the verbs -------------------------------------------------
def test_save_and_new_child_write_through_the_verbs_and_re_render_the_preview(window, brain, built, stub_escher):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    screen.select_structure(built["id"])
    pump_until(window, lambda: screen.last_preview is not None)
    assert len(stub_escher) == 1 and stub_escher[0]["formats"] == ("drawio", "png") and stub_escher[0]["ocr"]
    assert stub_escher[0]["out"] == str(Path(brain.out_dir) / "figures")
    assert screen.preview_path == str(Path(brain.out_dir) / "figures" / f"{built['slug']}.png")
    assert "OCR: competent" in screen.verdict_var.get() and "0 layout issues" in screen.verdict_var.get()
    assert screen._photo is not None

    screen.select_part("controller:vehicle_controller")
    screen.widgets["responsibility"].set("Turns a mission into drive and tool commands.\nStops on a fault.")
    result = screen.save()
    assert result.ok and result.verb == "update"
    stored = brain.service("cs_controller").repo.list({"structure": built["slug"], "key": "vehicle_controller"})[0]
    assert stored["responsibility"].endswith("Stops on a fault.")
    assert brain.storage.audit_tail(1)[0]["actor"] == "gui"
    assert window.status_text().startswith("Saved controller")
    pump_until(window, lambda: len(stub_escher) == 2)  # re-rendered after the save, off the Tk thread
    assert screen.parts_tree.selection() == ("controller:vehicle_controller",)

    # a process-model entry's lists are edited one item per line and saved as lists
    entry_id = screen.parts["process_model_entries"][1]["id"]
    screen.select_part(f"entry:{entry_id}")
    screen.widgets["variables"].set("Machine state\nObstacle list\nBucket height")
    assert screen.save().ok
    stored = brain.service("cs_process_model_entry").get(entry_id)
    assert stored["variables"] == ["Machine state", "Obstacle list", "Bucket height"]

    # New child: for a controller the default is an algorithm under it
    screen.select_part("controller:vehicle_controller")
    assert [e for e, _ in screen.child_options()] == [
        "cs_algorithm", "cs_process_model_entry", "cs_edge", "cs_note", "cs_controller",
    ]
    screen.new_child("cs_algorithm")
    assert screen.editing == "cs_algorithm" and screen.selected is None
    assert screen.widgets["controller"].get() == "vehicle_controller" and "new" in screen.form_box.cget("text")
    screen.widgets["code"].set("V3")
    screen.widgets["name"].set("Bucket control")
    result = screen.save()
    assert result.ok and result.verb == "create"
    assert brain.execute("count", entity="cs_algorithm").data["count"] == 4
    assert screen.selected == ("cs_algorithm", result.data["id"]) and screen.parts_tree.selection() == (
        f"algorithm:{result.data['id']}",
    )
    counts = screen.tree.item(str(built["id"]))["values"][4:]
    assert counts[1] == 4  # the structures' row counts follow
    # a signal under the selected edge, its kind from the edge
    screen.select_part("edge:e4")
    assert [e for e, _ in screen.child_options()] == ["cs_signal", "cs_edge"]
    screen.new_child()  # not interactive: the first option, no menu
    assert screen.editing == "cs_signal" and screen.widgets["edge"].get() == "e4"
    screen.widgets["signal_id"].set("CA-21")
    screen.widgets["name"].set("Tool command")
    assert screen.save().ok
    assert brain.service("cs_signal").repo.list({"structure": built["slug"], "signal_id": "CA-21"})[0]["kind"] == (
        "control_action"
    )
    # a refusal is a status-bar error, nothing written
    screen.new_child("cs_signal")
    screen.widgets["edge"].set("e4")
    screen.widgets["signal_id"].set("CA-01")  # carried by e1, from another controller
    failed = screen.save()
    assert not failed.ok and window.status_text().startswith("Error:") and "already carried" in window.status_text()
    assert brain.execute("count", entity="cs_signal").data["count"] == 11
    # Ctrl+N reaches the screen as New child
    assert screen.new.__func__ is screen.new_child.__func__


def test_delete_asks_first_and_cascades(window, brain, built, stub_escher, monkeypatch):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    screen.select_structure(built["id"])
    asked: list[str] = []

    def refuse(title, message):
        asked.append(message)
        return False

    monkeypatch.setattr(window, "confirm", refuse)
    screen.select_part("controller:vehicle_controller")
    assert not screen.delete_part().ok and asked and "go with it" in asked[-1]
    assert brain.execute("count", entity="cs_controller").data["count"] == 8
    assert not screen.delete_structure().ok and "33 parts" in asked[-1]
    assert brain.execute("count", entity="control_structure").data["count"] == 1

    monkeypatch.setattr(window, "confirm", lambda title, message: True)
    screen.select_part("edge:e4")
    assert screen.delete_part().ok
    assert brain.execute("count", entity="cs_edge").data["count"] == 8
    assert brain.execute("count", entity="cs_signal").data["count"] == 9  # CA-20 went with its edge
    assert screen.selected is None and window.status_text().startswith("Deleted edge")
    screen.select_part("controller:vehicle_controller")
    assert screen.delete_part().ok
    assert brain.execute("count", entity="cs_controller").data["count"] == 7
    assert brain.execute("count", entity="cs_algorithm").data["count"] == 1  # V1 and V2 went with the controller
    assert brain.storage.audit_tail(3)[-1]["actor"] == "gui"
    assert screen.delete_structure().ok
    assert brain.execute("count", entity="control_structure").data["count"] == 0
    assert brain.execute("count", entity="cs_signal").data["count"] == 0
    assert screen.structure_id is None and len(screen.tree.get_children()) == 0
    assert screen.verdict_var.get() == "No structure selected."


# -- New from…, Duplicate, Import ----------------------------------------------------------------
def test_new_from_blank_and_clone(window, brain, built, stub_escher):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    dialog = screen.new_from()
    names = [b["name"] for b in dialog.builders]
    assert names == ["blank", "template:wheel_loader_master", "from_drawio", "from_datasets", "clone"]
    assert dialog.builder_var.get() == "blank" and str(dialog.path_entry["state"]) == "disabled"
    dialog.builder_var.set("template:wheel_loader_master")
    dialog._on_builder()
    assert "Unavailable" in dialog.description_var.get() and str(dialog.ok_button["state"]) == "disabled"
    dialog.builder_var.set("from_drawio")
    dialog._on_builder()
    assert str(dialog.path_entry["state"]) == "normal" and dialog.path_label.cget("text") == "File"
    dialog.builder_var.set("from_datasets")
    dialog._on_builder()
    assert dialog.path_label.cget("text") == "Folder"

    dialog.builder_var.set("blank")
    dialog._on_builder()
    dialog.name_var.set("Second loader")
    dialog.system_var.set("Demo loader B")
    result = dialog.ok()
    assert result.ok and result.data["slug"] == "second_loader" and result.data["counts"]["controllers"] == 0
    assert not dialog.winfo_exists()
    assert screen.structure_id == result.data["id"] and len(screen.tree.get_children()) == 2
    assert window.status_text().startswith("Created control structure")
    assert brain.storage.audit_tail(1)[0]["actor"] == "gui"
    assert screen.child_options() == [("cs_controller", {}), ("cs_note", {})]

    dialog = screen.new_from()
    assert list(dialog.source_box["values"]) == [built["slug"], "second_loader"]
    dialog.builder_var.set("clone")
    dialog._on_builder()
    assert str(dialog.source_box["state"]) == "readonly"
    dialog.name_var.set("Loader clone")
    dialog.source_var.set(built["slug"])
    result = dialog.ok()
    assert result.ok and result.data["counts"] == COUNTS and result.data["source"] == f"duplicate of {built['slug']}"
    assert len(screen.parts_tree.get_children()) == 34
    # a blank name is a refusal the window reports
    dialog = screen.new_from()
    dialog.builder_var.set("blank")
    dialog._on_builder()
    assert not dialog.ok().ok and window.status_text().startswith("Error:") and dialog.winfo_exists()
    dialog.cancel()


def test_duplicate_and_import_drawio(window, brain, built, stub_escher, tmp_path, monkeypatch):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    assert not screen.duplicate().ok  # nothing selected
    screen.select_structure(built["id"])
    result = screen.duplicate()  # not interactive: "<name> (copy)"
    assert result.ok and result.data["name"] == "Demo Loader Control Structure (copy)"
    assert screen.structure_id == result.data["id"] and "Duplicated" in window.status_text()
    # import: the real escher writes the file (no stub for this one), the screen reads it back
    import asi_escher

    monkeypatch.undo()
    monkeypatch.setattr("asi_escher.ocr.ocr_check", lambda *a, **k: pytest.fail("no OCR without a PNG"))
    exported = brain.factory.export(built["slug"], tmp_path / "x", ("drawio",), ocr=False, actor="test")
    assert exported["paths"]["drawio"].endswith(".drawio") and asi_escher.__version__
    assert not screen.import_drawio().ok  # not interactive and no path: no dialog
    imported = screen.import_drawio(exported["paths"]["drawio"])
    assert imported.ok and imported.data["counts"] == COUNTS
    assert window.status_text().startswith("Imported") and screen.structure_id == imported.data["id"]
    assert len(screen.tree.get_children()) == 3


# -- Validate ------------------------------------------------------------------------------------
def test_validate_shows_the_warnings_in_the_panel_and_the_status_bar(window, brain, built, stub_escher):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    assert not screen.validate().ok
    screen.select_structure(built["id"])
    result = screen.validate()
    assert result.ok and screen.last_validation["warnings"] == [UP_HILL]
    assert list(screen.validation.get(0, "end")) == [f"warning: {UP_HILL}"]
    assert window.status_text() == f"Valid: 0 errors, 1 warning, 0 info — {UP_HILL}"
    # a shared feedback (one signal to two receivers from one controller) is information, not a warning
    brain.execute("create", entity="cs_edge", data={"structure": built["slug"], "key": "e10", "kind": "feedback",
                                                    "source": "perception", "target": "site_supervisor"})
    brain.execute("create", entity="cs_signal", data={"structure": built["slug"], "edge": "e10",
                                                      "signal_id": "FB-11", "name": "Obstacle list"})
    screen.validate()
    lines = list(screen.validation.get(0, "end"))
    assert lines == [f"warning: {UP_HILL}", "info: signal FB-11 is shared by 2 edges from perception: e7, e10"]
    assert window.status_text().startswith("Valid: 0 errors, 1 warning, 1 info")
    # a broken row is an error, first in the panel
    note = brain.service("cs_note").repo.list({"structure": built["slug"]})[0]
    brain.service("cs_note").repo.update(note["id"], {"attached_to": "ghost"})
    assert not screen.validate().ok
    assert screen.validation.get(0).startswith("error: note") and window.status_text().startswith("Invalid: 1 error")


# -- Export… ------------------------------------------------------------------------------------
def test_export_dialog_defaults_select_all_select_none_and_export(window, brain, built, stub_escher, tmp_path):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    assert screen.export() is None and "Select a control structure" in window.status_text()
    screen.select_structure(built["id"])
    dialog = screen.export()
    assert dialog.formats() == DEFAULT_FORMATS == ("drawio", "png") and dialog.ocr_var.get() is True
    assert dialog.folder_var.get() == str(Path(brain.out_dir) / "control_structures")
    assert dialog.preview_var.get().splitlines() == [
        str(Path(brain.out_dir) / "control_structures" / f"{built['slug']}.drawio"),
        str(Path(brain.out_dir) / "control_structures" / f"{built['slug']}.png"),
    ]
    dialog.select_all()
    assert dialog.formats() == FORMATS == ("drawio", "png", "svg")
    dialog.select_none()
    assert dialog.formats() == () and dialog.preview_var.get() == "(no format selected)"
    assert dialog.export() is None and "at least one format" in window.status_text()
    dialog.format_vars["svg"].set(True)
    dialog.format_vars["png"].set(True)
    dialog.ocr_var.set(True)
    out = tmp_path / "chosen"
    dialog.folder_var.set(str(out))
    assert dialog.preview_var.get().splitlines() == [
        str(out / f"{built['slug']}.png"), str(out / f"{built['slug']}.svg"),
    ]
    before = len(stub_escher)
    fetch = dialog.export()
    assert fetch is not None and str(dialog.export_button["state"]) == "disabled"
    assert dialog.status_var.get() == "Exporting…" and window.status_text().startswith("Exporting ")
    pump_until(window, lambda: dialog.result is not None)
    result = dialog.result
    assert result.ok and result.verb == "cs" and result.data["formats"] == ["png", "svg"]
    assert result.data["files"] == [str(out / f"{built['slug']}.png"), str(out / f"{built['slug']}.svg")]
    assert all(Path(f).is_file() for f in result.data["files"]) and result.data["ocr_verdict"] == "competent"
    assert stub_escher[before]["formats"] == ("png", "svg") and stub_escher[before]["ocr"] is True
    assert window.status_text() == (
        f"Exported Demo Loader Control Structure: {out / (built['slug'] + '.png')}, "
        f"{out / (built['slug'] + '.svg')} (OCR: competent)"
    )
    assert dialog.status_var.get().splitlines() == [
        f"Written: {out / (built['slug'] + '.png')}", f"Written: {out / (built['slug'] + '.svg')}", "OCR: competent",
    ]
    assert str(dialog.export_button["state"]) == "normal" and str(dialog.vscode_button["state"]) == "disabled"
    assert screen.last_export is result
    # the same Result an agent gets from the verb: audited as gui, published
    audit = [a for a in brain.storage.audit_tail(5) if a["action"] == "cs.export"]
    assert audit and audit[0]["actor"] == "gui" and audit[0]["payload"]["ocr_verdict"] == "competent"
    assert any(e["topic"] == "cs.exported" for e in brain.events.last(5))
    # the folder is remembered: the next dialog opens on it
    assert _prefs()[PREF_EXPORT_DIR] == str(out)
    dialog.close()
    again = screen.export()
    assert again.folder_var.get() == str(out) and again.formats() == DEFAULT_FORMATS and again.ocr_var.get()
    # the OCR box off: the verb runs with --no-ocr
    again.ocr_var.set(False)
    again.export()
    pump_until(window, lambda: again.result is not None)
    assert again.result.ok and again.result.data["ocr_verdict"] == "ocr skipped" and stub_escher[-1]["ocr"] is False
    assert window.status_text().endswith("(OCR: ocr skipped)")
    again.close()


def test_export_failure_is_reported_in_the_dialog_and_the_status_bar(window, brain, built, stub_escher, monkeypatch):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    screen.select_structure(built["id"])
    pump_until(window, lambda: screen.last_preview is not None)
    import asi_escher

    def broken(*args, **kwargs):
        raise RuntimeError("renderer down")

    monkeypatch.setattr(asi_escher, "build", broken)
    dialog = screen.export()
    dialog.export()
    pump_until(window, lambda: dialog.result is not None)
    assert not dialog.result.ok and dialog.status_var.get().startswith("Failed: ")
    assert window.status_text().startswith("Error:") and "renderer down" in window.status_text()
    assert str(dialog.export_button["state"]) == "normal"
    dialog.close()
    # the preview says so too, and recovers on the next render
    screen.render_preview()
    pump_until(window, lambda: screen.verdict_var.get().startswith("Preview failed"))
    assert screen.preview_path is None


# -- Open in VS Code ------------------------------------------------------------------------------
def test_open_in_vscode_names_the_file_when_code_is_on_the_path(window, brain, built, stub_escher):
    screen = window.show(CONTROL_STRUCTURES_SCREEN)
    assert screen.open_in_vscode() is None and "render or export first" in window.status_text()
    screen.code_path = None
    screen.select_structure(built["id"])
    pump_until(window, lambda: screen.last_preview is not None)
    assert str(screen.vscode_button["state"]) == "disabled"  # no `code` on the PATH
    screen.code_path = "code"
    screen.last_preview = None
    screen.render_preview()
    pump_until(window, lambda: len(stub_escher) == 2 and screen.last_preview is not None)
    assert str(screen.vscode_button["state"]) == "normal"
    drawio = str(Path(brain.out_dir) / "figures" / f"{built['slug']}.drawio")
    assert screen.open_in_vscode() == drawio  # not interactive: no process, the status bar names the command
    assert window.status_text() == f"Open in VS Code: code {drawio}"
    dialog = screen.export()
    dialog.export()
    pump_until(window, lambda: dialog.result is not None)
    assert str(dialog.vscode_button["state"]) == "normal"
    assert dialog.open_in_vscode() == dialog.result.data["paths"]["drawio"]
    dialog.close()
