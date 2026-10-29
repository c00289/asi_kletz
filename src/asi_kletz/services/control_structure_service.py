"""Control structures: the rules of the seven entities and the operations on a whole structure (0.24.0).

The rules of docs/control-structure-plan.md, section 2, live in one rule object per entity, attached
to the entity's ``EntityService`` by ``Brain.service`` (``guard``, ``on_load``, ``before_delete``,
``after_change``), so they hold whichever verb writes the row (``create cs_signal`` as much as the
factory): a part names a structure that exists and a parent that exists; a controller's key and
an edge's key are unique within the structure; a signal's kind matches its edge's; a signal id
is unique within the structure (a refusal when a person types it, a warning when a file is loaded
whole, because the owner's structure carries a few duplicates it inherited), except that one signal on
two edges leaving the same controller is one feedback to two receivers and legitimate; a control action
pointing up the hierarchy or feedback pointing down is a warning, never a refusal (lateral stop
paths exist); a row with dependants (a structure, a controller, an edge) is deleted with
``cascade`` or not at all; the lists (``control_actions``, ``variables``, ``updated_by``,
``references``) are JSON arrays, typed one item per line (``schema/lists.py``). Every change publishes
``cs.changed`` with the structure's slug.

``ControlStructureService`` (``brain.control_structures``) holds what works on a structure as
a whole: resolve by id, uid or slug; the parts; the plain **dataset** form the factory builders
produce and ``create_from_dataset`` loads in one transaction; ``validate``; ``delete`` with
cascade; ``duplicate`` as a deep copy under a new slug.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound, ValidationError
from ..schema import FieldType, normalise_uid, slugify
from ..schema.fields import json_text
from ..schema.lists import list_of
from ..stpa.drawio_reader import expand_refs

if TYPE_CHECKING:
    from ..brain import Brain
    from .entity_service import EntityService

STRUCTURE_ENTITY = "control_structure"
# the parts in the order a dataset lists them, which is the order they are loaded (parents first)
PART_ENTITIES = (
    "cs_controller", "cs_algorithm", "cs_process_model_entry", "cs_edge", "cs_signal", "cs_note",
)
DATASET_KEYS = {
    "cs_controller": "controllers",
    "cs_algorithm": "algorithms",
    "cs_process_model_entry": "process_model_entries",
    "cs_edge": "edges",
    "cs_signal": "signals",
    "cs_note": "notes",
}
SIGNAL_PREFIXES = {"CA": "control_action", "FB": "feedback"}
_PRIVATE = ("id", "uid", "created_at", "updated_at", "structure")


def _rows(brain: Brain, entity: str, **filters: Any) -> list[dict[str, Any]]:
    """Rows of ``entity`` matching ``filters``, read through the repository (no events, no audit)."""
    return brain.service(entity).repo.list(filters or None)


def _merged(clean: Mapping[str, Any], stored: Mapping[str, Any] | None) -> dict[str, Any]:
    """The row as it will be after the write: the stored row with the changes on top."""
    return {**(stored or {}), **clean}


class EntityRules:
    """The rules of one entity, in the shape ``EntityService`` takes them: ``guard(current, clean)`` before a
    create or an update, ``on_load(clean)`` on a file's row, ``before_delete(stored, cascade, actor)`` inside
    the delete, ``after_change(action, row, actor)`` after the commit. ``attach`` wires them. The lists of
    the entity (its ``FieldType.JSON`` fields) are normalised to JSON arrays on every path."""

    def __init__(self, brain: Brain, entity: str) -> None:
        self.brain = brain
        self.entity = entity
        self.schema = brain.registry.get(entity)
        self.lookups = brain.lookups
        self.storage = brain.storage
        self.events = brain.events

    def attach(self, service: EntityService) -> EntityService:
        service.guard = self.guard
        service.on_load = self.on_load
        service.before_delete = self.before_delete
        service.after_change = self.after_change
        return service

    # -- the shared vocabulary ----------------------------------------------------------------
    def refuse(self, *errors: str) -> None:
        raise ValidationError(self.schema.name, list(errors))

    def require_lookup(self, row: Mapping[str, Any], field: str) -> None:
        spec = self.schema.field(field)
        allowed = self.lookups.get(spec.lookup or "", ())
        value = row.get(field)
        if value is not None and value not in allowed:
            self.refuse(f"{field}: {value!r} is not one of {', '.join(allowed)}")

    def lists(self, clean: dict[str, Any], *, every: bool) -> None:
        """Every JSON field in ``clean`` becomes the JSON text of its list; with ``every`` (a create or a
        load) a field not given becomes the empty list, so the column never holds NULL."""
        for spec in self.schema.fields:
            if spec.type is not FieldType.JSON:
                continue
            if spec.name not in clean and not every:
                continue
            try:
                clean[spec.name] = json_text(list_of(clean.get(spec.name)))
            except ValueError as exc:
                self.refuse(f"{spec.name}: {exc}")

    def guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str]:
        self.lists(clean, every=current is None)
        return self.check(clean, current)

    def on_load(self, clean: dict[str, Any]) -> list[str]:
        self.lists(clean, every=True)
        return []

    # -- the hooks a subclass fills -------------------------------------------------------------
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        """Entity rules on a create (``stored`` is ``None``) or an update (``stored`` is the row as it
        is, ``clean`` the fields about to change). Returns warnings; raises ``ValidationError`` to
        refuse. The default has no rules."""
        return []

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        """Called inside the transaction before the row goes; raises to refuse, or deletes dependants."""

    def after_change(self, action: str, row: dict[str, Any], actor: str) -> None:
        """Called after a create, update or delete was committed and the entity event published."""


class CsRowRules(EntityRules):
    """Shared behaviour of the seven entities: lookups refused, ``cs.changed`` after a change."""

    def structure_of(self, row: Mapping[str, Any]) -> dict[str, Any]:
        slug = row.get("structure")
        found = _rows(self.brain, STRUCTURE_ENTITY, slug=slug) if slug else []
        if not found:
            self.refuse(f"structure: no control structure has the slug {slug!r}")
        return found[0]

    def after_change(self, action: str, row: dict[str, Any], actor: str) -> None:
        if self.brain.control_structures.bulk:
            return  # one event for the whole load, published by the structure service
        slug = row.get("slug") if self.schema.name == STRUCTURE_ENTITY else row.get("structure")
        self.events.publish(
            "cs.changed", structure=slug, entity=self.schema.name, action=action, id=row.get("id"), actor=actor
        )


class ControlStructureRowRules(CsRowRules):
    """``control_structure``: a unique slug (from the name when not given), immutable while parts exist."""

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        if stored is None:
            if not clean.get("slug"):
                clean["slug"] = slugify(str(row.get("name") or ""))
            if clean.get("status") is None:
                clean["status"] = "Draft"
            if clean.get("revision") is None:
                clean["revision"] = 1
            row = _merged(clean, stored)
        elif "slug" in clean and clean["slug"] != stored.get("slug"):
            if any(_rows(self.brain, e, structure=stored["slug"]) for e in PART_ENTITIES):
                self.refuse("slug: the parts point at it; duplicate the structure under the new slug instead")
        if not row.get("slug"):
            self.refuse("slug: a value is required")
        twins = [
            r for r in _rows(self.brain, STRUCTURE_ENTITY, slug=row["slug"])
            if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"slug: {row['slug']!r} is already the slug of control structure {twins[0]['id']}")
        self.require_lookup(row, "status")
        return []

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        counts = {e: len(_rows(self.brain, e, structure=stored["slug"])) for e in PART_ENTITIES}
        held = {e: n for e, n in counts.items() if n}
        if held and not cascade:
            self.refuse(
                "the structure has parts (" + ", ".join(f"{n} {e}" for e, n in held.items())
                + "); delete with --cascade to take them along"
            )
        for entity in reversed(PART_ENTITIES):
            self.brain.service(entity).repo.delete_where(structure=stored["slug"])
        self.storage.audit(actor, "cs.delete", STRUCTURE_ENTITY, stored["id"], {"slug": stored["slug"], **held})


class CsPartRules(CsRowRules):
    """A part of a structure: its structure exists; its order defaults to the next in its group."""

    group_field: str | None = None  # the field the order counts within (a controller's key, an edge's key)

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        self.structure_of(row)
        if stored is None and clean.get("order") is None:
            filters = {"structure": row["structure"]}
            if self.group_field and row.get(self.group_field) is not None:
                filters[self.group_field] = row[self.group_field]
            siblings = _rows(self.brain, self.schema.name, **filters)
            clean["order"] = max((r.get("order") or 0 for r in siblings), default=0) + 1
        return []

    def controller_of(self, row: Mapping[str, Any], field: str = "controller") -> dict[str, Any]:
        key = row.get(field)
        found = _rows(self.brain, "cs_controller", structure=row.get("structure"), key=key) if key else []
        if not found:
            self.refuse(f"{field}: no controller of structure {row.get('structure')!r} has the key {key!r}")
        return found[0]


class CsControllerRules(CsPartRules):
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        if stored is None:
            if not clean.get("key"):
                clean["key"] = slugify(str(row.get("name") or ""))
            if clean.get("kind") is None:
                clean["kind"] = "controller"
            row = _merged(clean, stored)
        elif "key" in clean and clean["key"] != stored.get("key"):
            users = self.dependants(stored)
            if any(users.values()):
                self.refuse("key: other rows point at it (" + ", ".join(f"{n} {e}" for e, n in users.items() if n)
                            + "); change them first")
        if not row.get("key"):
            self.refuse("key: a value is required")
        twins = [
            r for r in _rows(self.brain, "cs_controller", structure=row["structure"], key=row["key"])
            if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"key: {row['key']!r} is already a controller of this structure")
        self.require_lookup(row, "kind")
        return warnings

    def dependants(self, row: Mapping[str, Any]) -> dict[str, int]:
        slug, key = row["structure"], row["key"]
        edges = [e for e in _rows(self.brain, "cs_edge", structure=slug) if key in (e["source"], e["target"])]
        edge_keys = {e["key"] for e in edges}
        signals = [s for s in _rows(self.brain, "cs_signal", structure=slug) if s["edge"] in edge_keys]
        return {
            "cs_algorithm": len(_rows(self.brain, "cs_algorithm", structure=slug, controller=key)),
            "cs_process_model_entry": len(_rows(self.brain, "cs_process_model_entry", structure=slug, controller=key)),
            "cs_edge": len(edges),
            "cs_signal": len(signals),
        }

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        held = {e: n for e, n in self.dependants(stored).items() if n}
        if held and not cascade:
            self.refuse(
                "the controller has dependants (" + ", ".join(f"{n} {e}" for e, n in held.items())
                + "); delete with --cascade to take them along"
            )
        slug, key = stored["structure"], stored["key"]
        edge_repo = self.brain.service("cs_edge").repo
        signal_repo = self.brain.service("cs_signal").repo
        for edge in _rows(self.brain, "cs_edge", structure=slug):
            if key in (edge["source"], edge["target"]):
                signal_repo.delete_where(structure=slug, edge=edge["key"])
                edge_repo.delete(edge["id"])
        self.brain.service("cs_algorithm").repo.delete_where(structure=slug, controller=key)
        self.brain.service("cs_process_model_entry").repo.delete_where(structure=slug, controller=key)
        note_repo = self.brain.service("cs_note").repo
        for note in _rows(self.brain, "cs_note", structure=slug, attached_to=key):
            note_repo.update(note["id"], {"attached_to": None})  # the note stays, detached
        if held:
            self.storage.audit(
                actor, "cs.cascade", "cs_controller", stored["id"], {"structure": slug, "key": key, **held},
            )


class CsAlgorithmRules(CsPartRules):
    group_field = "controller"

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        self.controller_of(_merged(clean, stored))
        return warnings


class CsProcessModelEntryRules(CsPartRules):
    group_field = "controller"

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        self.controller_of(_merged(clean, stored))
        return warnings


class CsEdgeRules(CsPartRules):
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        if stored is None:
            if not clean.get("key"):
                taken = {e["key"] for e in _rows(self.brain, "cs_edge", structure=row["structure"])}
                n = len(taken) + 1
                while f"e{n}" in taken:
                    n += 1
                clean["key"] = f"e{n}"
            if clean.get("kind") is None:
                clean["kind"] = "control_action"
            row = _merged(clean, stored)
        if not row.get("key"):
            self.refuse("key: a value is required")
        twins = [
            r for r in _rows(self.brain, "cs_edge", structure=row["structure"], key=row["key"])
            if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"key: {row['key']!r} is already an edge of this structure")
        self.require_lookup(row, "kind")
        source = self.controller_of(row, "source")
        target = self.controller_of(row, "target")
        if stored is not None and "kind" in clean and clean["kind"] != stored.get("kind"):
            carried = _rows(self.brain, "cs_signal", structure=row["structure"], edge=stored["key"])
            other = [s["signal_id"] for s in carried if s.get("kind") not in (None, clean["kind"])]
            if other:
                self.refuse(f"kind: the edge carries {', '.join(other)}, whose kind is {stored.get('kind')}")
        if stored is not None and "key" in clean and clean["key"] != stored.get("key"):
            if _rows(self.brain, "cs_signal", structure=row["structure"], edge=stored["key"]):
                self.refuse("key: the edge's signals point at it; change them first")
        warnings.extend(direction_warnings(row, source, target))
        return warnings

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        signals = _rows(self.brain, "cs_signal", structure=stored["structure"], edge=stored["key"])
        if signals and not cascade:
            self.refuse(f"the edge carries {len(signals)} signal(s); delete with --cascade to take them along")
        if signals:
            self.brain.service("cs_signal").repo.delete_where(structure=stored["structure"], edge=stored["key"])
            self.storage.audit(actor, "cs.cascade", "cs_edge", stored["id"],
                               {"structure": stored["structure"], "key": stored["key"], "cs_signal": len(signals)})


def direction_warnings(edge: Mapping[str, Any], source: Mapping[str, Any], target: Mapping[str, Any]) -> list[str]:
    """A control action should point down the hierarchy (a lower ``order`` is higher up) and feedback
    up; the other way round is a warning, never a refusal, and a lateral arrow is neither."""
    so, to = source.get("order"), target.get("order")
    if so is None or to is None or so == to:
        return []
    kind = edge.get("kind")
    if kind == "control_action" and so > to:
        return [
            f"edge {edge.get('key')}: control action from {source['key']} points up the hierarchy to {target['key']}"
        ]
    if kind == "feedback" and so < to:
        return [f"edge {edge.get('key')}: feedback from {source['key']} points down the hierarchy to {target['key']}"]
    return []


class CsSignalRules(CsPartRules):
    group_field = "edge"

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        edges = []
        if row.get("edge"):
            edges = _rows(self.brain, "cs_edge", structure=row.get("structure"), key=row.get("edge"))
        if not edges:
            self.refuse(f"edge: no edge of structure {row.get('structure')!r} has the key {row.get('edge')!r}")
        edge = edges[0]
        if row.get("kind") is None:
            clean["kind"] = edge.get("kind")
            row = _merged(clean, stored)
        self.require_lookup(row, "kind")
        if row.get("kind") != edge.get("kind"):
            self.refuse(
                f"kind: {row.get('kind')!r} does not match edge {edge['key']}, which carries {edge.get('kind')}"
            )
        if stored is None and clean.get("placeholder") is None:
            clean["placeholder"] = False
        twins = [
            s for s in _rows(self.brain, "cs_signal", structure=row["structure"], signal_id=row.get("signal_id"))
            if stored is None or s["id"] != stored["id"]
        ]
        # the same signal on two edges leaving the same controller is one feedback (or one control action)
        # to two receivers: legitimate, information at most (`cs validate` lists it under `info`); a twin
        # on an edge from another source is a duplicate id, a warning in a file loaded whole, a refusal typed
        edges_by_key = {e["key"]: e for e in _rows(self.brain, "cs_edge", structure=row["structure"])}
        strangers = [t for t in twins if (edges_by_key.get(t["edge"]) or {}).get("source") != edge.get("source")]
        if strangers:
            where = ", ".join(sorted({t["edge"] for t in strangers}))
            message = f"signal_id: {row.get('signal_id')!r} is already carried by edge {where}"
            if self.brain.control_structures.bulk:
                warnings.append(message)  # a file loaded whole keeps what it says; `cs validate` repeats it
            else:
                self.refuse(message)
        return warnings


class CsNoteRules(CsPartRules):
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        if row.get("attached_to"):
            self.controller_of(row, "attached_to")
        return warnings


RULE_CLASSES: dict[str, type[EntityRules]] = {
    STRUCTURE_ENTITY: ControlStructureRowRules,
    "cs_controller": CsControllerRules,
    "cs_algorithm": CsAlgorithmRules,
    "cs_process_model_entry": CsProcessModelEntryRules,
    "cs_edge": CsEdgeRules,
    "cs_signal": CsSignalRules,
    "cs_note": CsNoteRules,
}


class ControlStructureService:
    """What works on a structure as a whole (``brain.control_structures``)."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.bulk = False  # while a dataset is loaded whole: one cs.changed at the end, duplicates as warnings

    def rules_for(self, entity: str) -> EntityRules | None:
        """The rule object of one of the seven entities, or ``None`` for any other; ``Brain.service`` attaches it."""
        cls = RULE_CLASSES.get(entity)
        return cls(self.brain, entity) if cls else None

    # -- reads ----------------------------------------------------------
    def resolve(self, ref: Any) -> dict[str, Any]:
        """The structure behind ``ref``: an id, a uid or a slug."""
        service = self.brain.service(STRUCTURE_ENTITY)
        if isinstance(ref, Mapping) and "slug" in ref:
            return dict(ref)
        text = str(ref).strip()
        if not text:
            raise CommandError("a control structure id, uid or slug is required")
        if text.isdigit() or (isinstance(ref, int) and not isinstance(ref, bool)):
            return service.get(int(text))
        if normalise_uid(text) is not None:
            return service.get_by_uid(text)
        rows = service.repo.list({"slug": text})
        if not rows:
            raise NotFound(f"control structure {text!r} not found (by id, uid or slug)")
        return rows[0]

    def parts(self, slug: str) -> dict[str, list[dict[str, Any]]]:
        """Every part of the structure, keyed as a dataset is (``controllers`` ...), in schema order."""
        return {DATASET_KEYS[e]: _rows(self.brain, e, structure=slug) for e in PART_ENTITIES}

    def counts(self, slug: str) -> dict[str, int]:
        return {key: len(rows) for key, rows in self.parts(slug).items()}

    def summary(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {**row, "counts": self.counts(row["slug"])}

    def dataset(self, ref: Any) -> dict[str, Any]:
        """The structure as a plain dataset: ``structure`` (its fields) and the six part lists, every
        row without id, uid, timestamps and the structure slug. What the factory builders produce
        and ``create_from_dataset`` loads; ``duplicate`` and the round-trip tests go through it."""
        row = self.resolve(ref)
        structure = {k: v for k, v in row.items() if k not in ("id", "uid", "created_at", "updated_at")}
        out: dict[str, Any] = {"structure": structure}
        for key, rows in self.parts(row["slug"]).items():
            out[key] = [{k: v for k, v in r.items() if k not in _PRIVATE} for r in rows]
        return out

    # -- writes ---------------------------------------------------------
    def create_from_dataset(
        self, dataset: Mapping[str, Any], actor: str = "python", **overrides: Any
    ) -> tuple[dict[str, Any], list[str]]:
        """Create a structure and all its parts from a dataset in one transaction. ``overrides``
        (``name``, ``slug``, ``system``, ``source`` ...) replace the dataset's structure fields. Every
        row goes through its service, so the rules hold; a duplicate signal id in the file is a
        warning. Audited once as ``cs.new`` with the counts; one ``cs.changed`` with action ``new``."""
        head = {
            k: v for k, v in dict(dataset.get("structure") or {}).items()
            if k not in ("id", "uid", "created_at", "updated_at")
        }
        head.update({k: v for k, v in overrides.items() if v is not None})
        if not head.get("name"):
            raise CommandError("a control structure needs a name")
        warnings: list[str] = []
        self.bulk = True
        try:
            with self.brain.storage.transaction():
                row, w = self.brain.service(STRUCTURE_ENTITY).create(head, actor)
                warnings.extend(w)
                slug = row["slug"]
                for entity in PART_ENTITIES:
                    service = self.brain.service(entity)
                    for index, part in enumerate(dataset.get(DATASET_KEYS[entity]) or [], start=1):
                        data = {k: v for k, v in dict(part).items() if k not in _PRIVATE}
                        data["structure"] = slug
                        try:
                            _, w = service.create(data, actor)
                        except ValidationError as exc:
                            raise ValidationError(entity, [f"row {index}: {e}" for e in exc.errors]) from None
                        warnings.extend(f"{entity} {index}: {x}" for x in w)
                counts = self.counts(slug)
                self.brain.storage.audit(actor, "cs.new", STRUCTURE_ENTITY, row["id"], {"slug": slug, **counts})
        finally:
            self.bulk = False
        self.brain.events.publish(
            "cs.changed", structure=slug, entity=STRUCTURE_ENTITY, action="new", id=row["id"], actor=actor,
        )
        return self.summary(row), warnings

    def duplicate(
        self, ref: Any, name: str, slug: str | None = None, actor: str = "python"
    ) -> tuple[dict[str, Any], list[str]]:
        """A deep copy under a new slug (from the new name when not given), status Draft, revision 1."""
        source = self.resolve(ref)
        if not name or not str(name).strip():
            raise CommandError("duplicate needs --name")
        dataset = self.dataset(source)
        new_slug = slug or slugify(name)
        row, warnings = self.create_from_dataset(
            dataset, actor, name=name, slug=new_slug, status="Draft", revision=1,
            source=f"duplicate of {source['slug']}",
        )
        self.brain.storage.audit(
            actor, "cs.duplicate", STRUCTURE_ENTITY, row["id"], {"from": source["slug"], "slug": new_slug},
        )
        return row, warnings

    def delete(self, ref: Any, cascade: bool = False, actor: str = "python") -> dict[str, Any]:
        row = self.resolve(ref)
        counts = self.counts(row["slug"])
        self.brain.service(STRUCTURE_ENTITY).delete(int(row["id"]), actor, cascade=cascade)
        return {"id": row["id"], "slug": row["slug"], "deleted": {STRUCTURE_ENTITY: 1, **counts}}

    # -- validation -----------------------------------------------------
    def validate(self, ref: Any) -> dict[str, Any]:
        """Every rule checked on the stored rows: errors (what the service would refuse), warnings
        (direction, duplicate signal ids, references to signals the structure does not carry) and info
        (a signal shared by two edges leaving the same controller, which is legitimate)."""
        row = self.resolve(ref)
        slug = row["slug"]
        parts = self.parts(slug)
        errors: list[str] = []
        warnings: list[str] = []
        kinds = self.brain.lookups.get("cs_controller_kind", ())
        edge_kinds = self.brain.lookups.get("cs_edge_kind", ())
        controllers = {c["key"]: c for c in parts["controllers"]}
        if len(controllers) != len(parts["controllers"]):
            errors.append("controller keys are not unique")
        for c in parts["controllers"]:
            if c.get("kind") not in kinds:
                errors.append(f"controller {c['key']}: kind {c.get('kind')!r} is not one of {', '.join(kinds)}")
        for a in parts["algorithms"]:
            if a["controller"] not in controllers:
                errors.append(f"algorithm {a['code']}: controller {a['controller']!r} does not exist")
        for p in parts["process_model_entries"]:
            if p["controller"] not in controllers:
                errors.append(
                    f"process model entry {p.get('heading')!r}: controller {p['controller']!r} does not exist"
                )
        edges = {e["key"]: e for e in parts["edges"]}
        if len(edges) != len(parts["edges"]):
            errors.append("edge keys are not unique")
        for e in parts["edges"]:
            if e.get("kind") not in edge_kinds:
                errors.append(f"edge {e['key']}: kind {e.get('kind')!r} is not one of {', '.join(edge_kinds)}")
            for end in ("source", "target"):
                if e[end] not in controllers:
                    errors.append(f"edge {e['key']}: {end} {e[end]!r} does not exist")
            if e["source"] in controllers and e["target"] in controllers:
                warnings.extend(direction_warnings(e, controllers[e["source"]], controllers[e["target"]]))
        info: list[str] = []
        carried: dict[str, list[str]] = {}
        for s in parts["signals"]:
            edge = edges.get(s["edge"])
            if edge is None:
                errors.append(f"signal {s['signal_id']}: edge {s['edge']!r} does not exist")
            elif s.get("kind") != edge.get("kind"):
                errors.append(
                    f"signal {s['signal_id']}: kind {s.get('kind')!r} does not match edge {edge['key']}"
                    f" ({edge.get('kind')})"
                )
            carried.setdefault(s["signal_id"], []).append(s["edge"])
        for sid, on in carried.items():
            if len(on) > 1:
                on = sorted(on, key=lambda key: ((edges.get(key) or {}).get("order") or 0, key))
                sources = {(edges.get(key) or {}).get("source") for key in on}
                if len(sources) == 1 and None not in sources:
                    # one signal to two receivers from the same controller (the owner's structure has two
                    # such feedback signals): shared, not duplicated
                    source = next(iter(sources))
                    info.append(f"signal {sid} is shared by {len(on)} edges from {source}: {', '.join(on)}")
                else:
                    warnings.append(f"signal {sid} is carried by {len(on)} edges: {', '.join(on)}")
        for p in parts["process_model_entries"]:
            for field in ("control_actions", "updated_by"):
                for sid in expand_refs(" ".join(str(x) for x in list_of(p.get(field)))):
                    if sid not in carried:
                        warnings.append(
                            f"process model entry {p.get('heading')!r} names {sid} in {field}, which no edge carries"
                        )
        for n in parts["notes"]:
            if n.get("attached_to") and n["attached_to"] not in controllers:
                errors.append(f"note {n['id']}: attached to {n['attached_to']!r}, which does not exist")
        return {
            "id": row["id"], "slug": slug, "name": row["name"],
            "counts": {k: len(v) for k, v in parts.items()},
            "ok": not errors, "errors": errors, "warnings": warnings, "info": info,
        }
