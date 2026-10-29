"""Read a draw.io control structure into the plain dataset the factory loads. Standard library only.

Two dialects of file are understood and give the same dataset:

- **asi_escher's own output** (``<mxfile host="asi_escher">``, what ``cs export`` writes): one
  vertex cell per box whose HTML label carries the name and the three sections (responsibility,
  the orange algorithms, the blue process model), one edge cell per arrow with the signal lines as
  its value, note cells with ``shape=note``. The sections come back exactly: escher wraps long
  lines at ``WRAP_WIDTH`` characters, so an algorithm is recognised by the code that starts it, a
  process-model entry by the dash the factory puts in front of it (``- CA-20 Drive command: ...``)
  and a responsibility line by the greedy-wrap rule (a line follows the one before it only where
  its first word would not have fitted there).
- **A hand-drawn file** (any other host): the logic of the owner's ``control_structure_to_datasets``
  script, ported. A controller is a top-level box that encloses other boxes or ends an arrow; the
  boxes inside it are its "Responsibility" text, its "... process model" box (a title, then
  heading lines with bullet lines ``• Variables: a; b`` and ``• Updated by FB-01 ...``) and its
  algorithm boxes (``V1 — Name``); any other box inside is a note attached to it; a free box is a
  note attached to the nearest controller. The kind of a box is read from its style (a double
  border is the controlled process, a dashed one the environment, a rounded one a human
  controller) and can be given per name through ``kinds``; the default is ``controller``.

``read_dataset_folder`` reads the six JSON files of the Roy's Brain envelope
(``controllers.json`` ... ``notes.json``) into the same dataset.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

from ..errors import NotFound

WRAP_WIDTH = 42  # asi_escher's WRAP_WIDTH_CONTROL: characters per line inside a box
SIGNAL_RE = re.compile(r"^(CA|FB)-([A-Za-z0-9]+(?:-[A-Za-z0-9]+)*)\s*(.*)$")
SIGNAL_REF_RE = re.compile(r"\b(CA|FB)-(?:WL-\d+|X\d+|\d+)(?:/\d+)*\b")
ALGORITHM_RE = re.compile(r"^([A-Z]{1,3}\d+[A-Za-z]?)\s+[—–-]\s+(.*)$")
ALGORITHM_CODE_RE = re.compile(r"^[A-Z]{1,4}\d+[A-Za-z]?$")  # the first token of an escher algorithm line
BULLET = "- "  # the factory draws every process-model entry behind one; the reader splits on it (ASCII on
# purpose: the Windows OCR engine answers through PowerShell in the console code page, where a typographic
# bullet becomes a control byte that breaks the report)
PREFIX_KIND = {"CA": "control_action", "FB": "feedback"}
# asi_escher's colours (render.THEME): the two sections and the two arrow kinds
ALGORITHMS_FILL = "#FFF3E0"
PROCESS_MODEL_FILL = "#E3F2FD"
EDGE_COLOURS = {"#C62828": "control_action", "#1565C0": "feedback"}
DATASET_FILES = ("controllers", "algorithms", "process_model_entries", "signals", "edges", "notes")


# ---------------------------------------------------------------- text helpers
def clean_text(value: str | None) -> str:
    """draw.io label HTML to plain text, newlines kept."""
    text = html.unescape(value or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</div>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return "\n".join(lines).strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def expand_refs(text: str) -> list[str]:
    """``CA-02/03/04`` -> ``CA-02, CA-03, CA-04``; ``FB-WL-2`` stays; each once, in order."""
    refs: list[str] = []
    for match in SIGNAL_REF_RE.finditer(text):
        token = match.group(0)
        prefix, body = token[:2], token[3:]
        parts = body.split("/")
        refs.append(f"{prefix}-{parts[0]}")
        refs.extend(f"{prefix}-{extra}" for extra in parts[1:])
    return list(dict.fromkeys(refs))


def unwrap(lines: list[str], width: int = WRAP_WIDTH) -> list[str]:
    """Undo a greedy word wrap at ``width``: a line continues the previous one only where its
    first word would not have fitted there (what ``textwrap.wrap`` does), so an explicit line
    break (a new item) is told apart from a wrapped one."""
    out: list[str] = []
    for line in lines:
        if out:
            first = line.split(" ", 1)[0]
            if len(out[-1]) + 1 + len(first) > width:
                out[-1] = _join(out[-1], line)
                continue
        out.append(line)
    return out


def _join(previous: str, line: str) -> str:
    """``line`` continued ``previous`` in the drawing: joined without a space after a hyphen break."""
    return previous + line if previous.endswith("-") else previous + " " + line


def group_algorithms(lines: list[str]) -> list[str]:
    """Wrapped algorithm lines back into one per algorithm: a line starting with a code begins one."""
    out: list[str] = []
    for line in lines:
        first = line.split(" ", 1)[0]
        if out and not ALGORITHM_CODE_RE.match(first):
            out[-1] = _join(out[-1], line)
        else:
            out.append(line)
    return out


def group_entries(lines: list[str]) -> tuple[str, list[str]]:
    """The process-model section back into its title and its entries: the title is every line
    before the first bullet, an entry starts at a bullet and runs to the next."""
    title: list[str] = []
    entries: list[str] = []
    for line in lines:
        if line.startswith(BULLET):
            entries.append(line[len(BULLET):].strip())
        elif entries:
            entries[-1] = _join(entries[-1], line)
        else:
            title.append(line)
    return " ".join(title), entries


def split_list(text: str, separators: str) -> list[str]:
    """Split on any separator character, not inside parentheses."""
    parts, depth, current = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        if ch in separators and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    parts.append("".join(current))
    return [p.strip().rstrip(".") for p in parts if p.strip()]


def render_entry(entry: Mapping[str, Any]) -> str:
    """A process-model entry as one line: ``heading: variable; variable; updated by FB-01, FB-02``.
    The factory draws entries this way and ``parse_entry`` reads them back."""
    parts: list[str] = []
    variables = [str(v) for v in entry.get("variables") or []]
    updated_by = [str(v) for v in entry.get("updated_by") or []]
    if variables:
        parts.append("; ".join(variables))
    if updated_by:
        parts.append("updated by " + ", ".join(updated_by))
    heading = str(entry.get("heading") or "")
    return heading + (": " + "; ".join(parts) if parts else "")


def parse_entry(line: str) -> dict[str, Any]:
    """The inverse of ``render_entry``."""
    heading, sep, rest = line.partition(": ")
    variables: list[str] = []
    updated_by: list[str] = []
    if sep:
        for part in split_list(rest, ";"):
            if part.lower().startswith("updated by"):
                updated_by.extend(split_list(part[len("updated by"):].lstrip(": "), ","))
            else:
                variables.append(part)
    return {
        "heading": heading.strip(),
        "control_actions": expand_refs(heading),
        "variables": variables,
        "updated_by": updated_by,
        "references": expand_refs(line),
    }


# ---------------------------------------------------------------- the file
def load_cells(path: str | Path) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    """``(page name, host, cells)``; a cell is ``id, raw, text, style, vertex, edge, source, target, rect``."""
    file = Path(path)
    if not file.is_file():
        raise NotFound(f"file not found: {file}")
    try:
        root = ET.parse(file).getroot()
    except ET.ParseError as exc:
        raise NotFound(f"{file.name} is not a draw.io file: {exc}") from None
    if root.tag != "mxfile":
        raise NotFound(f"{file.name} is not a draw.io file (no <mxfile> root)")
    diagram = root.find("diagram")
    model = diagram.find("mxGraphModel") if diagram is not None else root
    if model is None:
        raise NotFound(f"{file.name} holds a compressed diagram; save it uncompressed (File > Properties)")
    cells = []
    for cell in model.iter("mxCell"):
        if cell.get("id") in {"0", "1"}:
            continue
        geo = cell.find("mxGeometry")
        rect = None
        if geo is not None and cell.get("vertex") == "1":
            rect = (
                float(geo.get("x", 0)), float(geo.get("y", 0)), float(geo.get("width", 0)), float(geo.get("height", 0)),
            )
        cells.append({
            "id": cell.get("id"),
            "raw": cell.get("value") or "",
            "text": clean_text(cell.get("value")),
            "style": cell.get("style") or "",
            "vertex": cell.get("vertex") == "1",
            "edge": cell.get("edge") == "1",
            "source": cell.get("source"),
            "target": cell.get("target"),
            "rect": rect,
        })
    return (diagram.get("name") if diagram is not None else None), root.get("host"), cells


def read_drawio(path: str | Path, kinds: Mapping[str, str] | None = None) -> dict[str, Any]:
    """The dataset of the draw.io file at ``path``: ``structure`` (name from the page, source the
    file name), ``controllers``, ``algorithms``, ``process_model_entries``, ``edges``, ``signals``,
    ``notes`` and ``warnings`` (what could not be read as drawn)."""
    page, host, cells = load_cells(path)
    name = Path(path).stem
    if host == "asi_escher":
        data = _read_escher(cells)
        title = page or name
    else:
        data = _read_drawn(cells, kinds or {})
        title = page or name
    data["structure"] = {"name": title, "source": Path(path).name}
    return data


def kind_from_style(style: str, fallback: str = "controller") -> str:
    """The box kind escher's draw.io style encodes; a hand-drawn style gives the same hints."""
    if "double=1" in style:
        return "controlled_process"
    if "dashed=1" in style:
        return "environment"
    if "arcSize=50" in style:
        return "sensor"
    if "strokeWidth=2;" in style:
        return "actuator"
    if "arcSize=10" in style and "rounded=1" in style:
        return "human_controller"
    if "fillColor=#F5F5F5" in style:
        return "external_system"
    return fallback


def _style_value(style: str, key: str) -> str | None:
    match = re.search(rf"(?:^|;){re.escape(key)}=([^;]*)", style)
    return match.group(1) if match else None


def _is_provenance(cell: Mapping[str, Any]) -> bool:
    return cell["id"] == "provenance" or cell["text"].startswith("asi_escher ")


# ---------------------------------------------------------------- escher's dialect
_DIV_RE = re.compile(r'<div style="([^"]*)">(.*?)</div>', re.DOTALL)


def _lines(fragment: str) -> list[str]:
    return [line for line in clean_text(fragment).split("\n") if line.strip()]


def _read_escher(cells: list[dict[str, Any]]) -> dict[str, Any]:
    controllers: list[dict[str, Any]] = []
    algorithms: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    warnings: list[str] = []
    boxes: list[dict[str, Any]] = []
    note_cells: list[dict[str, Any]] = []
    for cell in cells:
        if not cell["vertex"] or _is_provenance(cell):
            continue
        if "shape=note" in cell["style"]:
            note_cells.append(cell)
        elif cell["text"]:
            boxes.append(cell)
    boxes.sort(key=lambda c: (c["rect"][1], c["rect"][0]))
    key_of_cell: dict[str, str] = {}
    for order, cell in enumerate(boxes, start=1):
        raw = cell["raw"]
        head, _, _rest = raw.partition("<div")
        name = clean_text(head).split("\n")[0]
        row = {
            "key": cell["id"], "order": order, "name": name, "kind": kind_from_style(cell["style"]),
            "responsibility": "", "process_model_title": "", "note": "",
        }
        controllers.append(row)
        key_of_cell[cell["id"]] = row["key"]
        sections = _DIV_RE.findall(raw)
        seen = 0
        for css, body in sections:
            lines = _lines(body)
            if "border-top" in css:
                kind = "responsibility"
            elif ALGORITHMS_FILL.lower() in css.lower():
                kind = "algorithms"
            elif PROCESS_MODEL_FILL.lower() in css.lower():
                kind = "process_model"
            else:
                kind = ("responsibility", "algorithms", "process_model")[min(seen, 2)]
            seen += 1
            if kind == "responsibility":
                row["responsibility"] = "\n".join(unwrap(lines))
            elif kind == "algorithms":
                for index, line in enumerate(group_algorithms(lines), start=1):
                    code, _, text = line.partition(" ")
                    algorithms.append({"controller": row["key"], "order": index, "code": code, "name": text.strip()})
            else:
                title, found = group_entries(lines)
                row["process_model_title"] = title
                for index, line in enumerate(found, start=1):
                    entries.append({"controller": row["key"], "order": index, **parse_entry(line)})
    edges, signals = _edges(cells, key_of_cell, warnings)
    for index, cell in enumerate(note_cells, start=1):
        notes.append({"order": index, "text": cell["text"], "attached_to": _nearest(cell, boxes, key_of_cell)})
    return {
        "controllers": controllers, "algorithms": algorithms, "process_model_entries": entries,
        "edges": edges, "signals": signals, "notes": notes, "warnings": warnings,
    }


def _edges(
    cells: list[dict[str, Any]], key_of_cell: Mapping[str, str], warnings: list[str]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    edges: list[dict[str, Any]] = []
    signals: list[dict[str, Any]] = []
    order = 0
    for cell in cells:
        if not cell["edge"]:
            continue
        source, target = key_of_cell.get(cell["source"] or ""), key_of_cell.get(cell["target"] or "")
        if not source or not target:
            warnings.append(f"edge {cell['id']}: an end is not a controller; skipped")
            continue
        order += 1
        lines = [line for line in cell["text"].split("\n") if line.strip()]
        matches = [SIGNAL_RE.match(line) for line in lines]
        prefixes = {m.group(1) for m in matches if m}
        if len(prefixes) == 1:
            kind = PREFIX_KIND[prefixes.pop()]
        else:
            colour = _style_value(cell["style"], "strokeColor") or ""
            kind = EDGE_COLOURS.get(colour.upper(), "control_action")
            if len(prefixes) > 1:
                warnings.append(f"edge {cell['id']}: carries both CA and FB lines; read as {kind}")
        edge = {"key": cell["id"], "order": order, "kind": kind, "source": source, "target": target}
        edges.append(edge)
        for line_no, (line, match) in enumerate(zip(lines, matches, strict=True), start=1):
            if not match:
                warnings.append(f"edge {cell['id']}: line {line!r} is not a signal (CA-xx / FB-xx); skipped")
                continue
            prefix, number, text = match.groups()
            if PREFIX_KIND[prefix] != kind:
                warnings.append(f"edge {cell['id']}: {prefix}-{number} does not match the edge's kind; skipped")
                continue
            signals.append({
                "edge": edge["key"], "order": line_no, "signal_id": f"{prefix}-{number}", "kind": kind,
                "name": text.strip(), "placeholder": number.startswith(("WL", "X")),
            })
    return edges, signals


def _nearest(cell: Mapping[str, Any], boxes: list[dict[str, Any]], key_of_cell: Mapping[str, str]) -> str | None:
    vx, vy, vw, vh = cell["rect"]
    cx, cy = vx + vw / 2, vy + vh / 2
    best, best_d = None, None
    for box in boxes:
        x, y, w, h = box["rect"]
        dx = max(x - cx, 0, cx - (x + w))
        dy = max(y - cy, 0, cy - (y + h))
        d = dx * dx + dy * dy
        if best_d is None or d < best_d:
            best, best_d = box, d
    return key_of_cell.get(best["id"]) if best else None


# ---------------------------------------------------------------- the hand-drawn dialect
def _contains(outer: tuple, inner: tuple) -> bool:
    ox, oy, ow, oh = outer
    ix, iy, iw, ih = inner
    return ix >= ox and iy >= oy and ix + iw <= ox + ow and iy + ih <= oy + oh


def _area(rect: tuple) -> float:
    return rect[2] * rect[3]


def _containers(vertices: list[dict[str, Any]], edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A top-level vertex that encloses other vertices or ends an arrow; free text boxes are neither."""
    endpoints = {e["source"] for e in edges} | {e["target"] for e in edges}
    out = []
    for v in vertices:
        others = [o for o in vertices if o is not v]
        inside = any(_contains(o["rect"], v["rect"]) and _area(o["rect"]) > _area(v["rect"]) for o in others)
        encloses = any(_contains(v["rect"], o["rect"]) and _area(v["rect"]) > _area(o["rect"]) for o in others)
        if not inside and (encloses or v["id"] in endpoints):
            out.append(v)
    return out


def _parent(vertex: dict[str, Any], containers: list[dict[str, Any]]) -> dict[str, Any] | None:
    inside = [c for c in containers if c is not vertex and _contains(c["rect"], vertex["rect"])]
    return min(inside, key=lambda c: _area(c["rect"])) if inside else None


def parse_process_model(text: str) -> tuple[str, list[dict[str, Any]]]:
    """A hand-drawn process-model box: the title line, then heading lines, each followed by bullet
    lines (``• Variables: a; b``, ``• Updated by FB-01, FB-02``; any other bullet is kept as a
    variable). Returns ``(title, entries)`` with the entries numbered in order."""
    lines = [line for line in text.split("\n") if line.strip()]
    title = lines[0] if lines else ""
    entries: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    raw: list[list[str]] = []
    for line in lines[1:]:
        stripped = line.strip()
        if stripped.startswith("•"):
            bullet = stripped.lstrip("•").strip()
            if current is None:
                current = {"heading": "", "variables": [], "updated_by": []}
                entries.append(current)
                raw.append([])
            lower = bullet.lower()
            if lower.startswith("variables:"):
                current["variables"].extend(split_list(bullet.split(":", 1)[1], ";"))
            elif lower.startswith("updated by"):
                current["updated_by"].extend(split_list(bullet[len("updated by"):].lstrip(": "), ";,"))
            else:
                current["variables"].append(bullet)
            raw[-1].append(stripped)
        else:
            current = {"heading": stripped, "variables": [], "updated_by": []}
            entries.append(current)
            raw.append([stripped])
    for index, (entry, lines_of) in enumerate(zip(entries, raw, strict=True), start=1):
        entry["order"] = index
        entry["control_actions"] = expand_refs(entry["heading"])
        entry["references"] = expand_refs(" ".join(lines_of))
    return title, entries


def _read_drawn(cells: list[dict[str, Any]], kinds: Mapping[str, str]) -> dict[str, Any]:
    vertices = [c for c in cells if c["vertex"] and c["rect"] is not None and not _is_provenance(c)]
    edge_cells = [c for c in cells if c["edge"]]
    containers = _containers(vertices, edge_cells)
    container_ids = {c["id"] for c in containers}
    controllers: list[dict[str, Any]] = []
    by_cell: dict[str, dict[str, Any]] = {}
    key_of_cell: dict[str, str] = {}
    for order, c in enumerate(sorted(containers, key=lambda c: (c["rect"][1], c["rect"][0])), start=1):
        name = c["text"].split("\n")[0]
        row = {
            "key": slug(name) or c["id"], "order": order, "name": name,
            "kind": kinds.get(name) or kind_from_style(c["style"]),
            "responsibility": "", "process_model_title": "", "note": "",
        }
        controllers.append(row)
        by_cell[c["id"]] = row
        key_of_cell[c["id"]] = row["key"]
    algorithms: list[dict[str, Any]] = []
    entries: list[dict[str, Any]] = []
    notes: list[dict[str, Any]] = []
    warnings: list[str] = []
    for v in vertices:
        if v["id"] in container_ids:
            continue
        parent = _parent(v, containers)
        text = v["text"]
        first = text.split("\n")[0] if text else ""
        if parent is None:
            if text:
                notes.append({"text": text, "attached_to": _nearest(v, containers, key_of_cell)})
            continue
        ctl = by_cell[parent["id"]]
        algorithm = ALGORITHM_RE.match(first)
        if first.lower() == "responsibility":
            ctl["responsibility"] = "\n".join(line for line in text.split("\n")[1:] if line.strip())
        elif "process model" in first.lower():
            title, found = parse_process_model(text)
            ctl["process_model_title"] = title
            entries.extend({"controller": ctl["key"], **entry} for entry in found)
        elif algorithm:
            code, name = algorithm.groups()
            digits = re.sub(r"\D", "", code)
            algorithms.append({
                "controller": ctl["key"], "order": int(digits) if digits else 0, "code": code, "name": name.strip(),
            })
        elif text:
            notes.append({"text": text, "attached_to": ctl["key"]})
    for note in notes:
        for ctl in controllers:
            if ctl["key"] == note["attached_to"] and not ctl["note"]:
                ctl["note"] = note["text"]
    for index, note in enumerate(notes, start=1):
        note["order"] = index
    algorithms.sort(key=lambda a: (a["controller"], a["order"]))
    edges, signals = _edges(cells, key_of_cell, warnings)
    return {
        "controllers": controllers, "algorithms": algorithms, "process_model_entries": entries,
        "edges": edges, "signals": signals, "notes": notes, "warnings": warnings,
    }


# ---------------------------------------------------------------- the dataset folder
def _envelope_rows(file: Path) -> list[dict[str, Any]]:
    try:
        payload = json.loads(file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise NotFound(f"{file.name} is not JSON: {exc}") from None
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise NotFound(f"{file.name} is not a dataset (no 'rows' list)")
    return rows


def read_dataset_folder(folder: str | Path) -> dict[str, Any]:
    """The six JSON files of the Roy's Brain envelope as one dataset. ``controllers.json`` and
    ``edges.json`` are required; the others may be absent. The script's names are mapped to the
    entity fields (``id`` to ``key`` or ``code``, ``controller_id`` to ``controller``, ``edge_id``
    to ``edge``, ``source_id`` / ``target_id`` to ``source`` / ``target``); a process-model entry's
    stray ``items`` are kept as variables; a signal without an id is skipped with a warning; an
    edge of kind ``mixed`` takes the kind of its first signal."""
    root = Path(folder)
    if not root.is_dir():
        raise NotFound(f"folder not found: {root}")
    files = {name: root / f"{name}.json" for name in DATASET_FILES}
    for name in ("controllers", "edges"):
        if not files[name].is_file():
            raise NotFound(f"{root} has no {name}.json")
    raw = {name: (_envelope_rows(file) if file.is_file() else []) for name, file in files.items()}
    warnings: list[str] = []
    controllers = [
        {
            "key": c.get("id") or slug(str(c.get("name") or "")), "order": c.get("order") or index,
            "name": c.get("name") or "", "kind": c.get("kind") or "controller",
            "responsibility": c.get("responsibility") or "\n".join(c.get("responsibility_lines") or []),
            "process_model_title": c.get("process_model_title") or "", "note": c.get("note") or "",
        }
        for index, c in enumerate(raw["controllers"], start=1)
    ]
    algorithms = [
        {
            "controller": a.get("controller_id") or a.get("controller"), "order": a.get("order") or index,
            "code": a.get("id") or a.get("code"), "name": a.get("name") or "",
        }
        for index, a in enumerate(raw["algorithms"], start=1)
    ]
    entries: list[dict[str, Any]] = []
    per_controller: dict[str, int] = {}
    for p in raw["process_model_entries"]:
        controller = p.get("controller_id") or p.get("controller")
        per_controller[controller] = per_controller.get(controller, 0) + 1
        entries.append({
            "controller": controller, "order": p.get("order") or per_controller[controller],
            "heading": p.get("heading") or "", "control_actions": list(p.get("control_actions") or []),
            "variables": [*(p.get("variables") or []), *(p.get("items") or [])],
            "updated_by": list(p.get("updated_by") or []), "references": list(p.get("references") or []),
        })
    signals_by_edge: dict[str, list[dict[str, Any]]] = {}
    for s in raw["signals"]:
        signals_by_edge.setdefault(s.get("edge_id") or s.get("edge"), []).append(s)
    edges: list[dict[str, Any]] = []
    for index, e in enumerate(raw["edges"], start=1):
        key = e.get("id") or e.get("key") or f"e{index}"
        kind = e.get("kind")
        if kind not in PREFIX_KIND.values():
            first = next((s for s in signals_by_edge.get(key, []) if s.get("kind") in PREFIX_KIND.values()), None)
            kind = first["kind"] if first else "control_action"
            warnings.append(f"edge {key}: kind {e.get('kind')!r} read as {kind}")
        edges.append({
            "key": key, "order": e.get("order") or index, "kind": kind,
            "source": e.get("source_id") or e.get("source"), "target": e.get("target_id") or e.get("target"),
        })
    signals: list[dict[str, Any]] = []
    for edge in edges:
        for index, s in enumerate(signals_by_edge.get(edge["key"], []), start=1):
            if not s.get("signal_id"):
                warnings.append(f"edge {edge['key']}: signal {s.get('name')!r} has no id; skipped")
                continue
            signals.append({
                "edge": edge["key"], "order": s.get("order") or index, "signal_id": s["signal_id"],
                "kind": s.get("kind") or edge["kind"], "name": s.get("name") or "",
                "placeholder": bool(s.get("placeholder")),
            })
    notes = [
        {"order": index, "text": n.get("text") or "", "attached_to": n.get("attached_to") or None}
        for index, n in enumerate(raw["notes"], start=1)
        if n.get("text")
    ]
    return {
        "structure": {"name": root.name, "source": str(root)},
        "controllers": controllers, "algorithms": algorithms, "process_model_entries": entries,
        "edges": edges, "signals": signals, "notes": notes, "warnings": warnings,
    }
