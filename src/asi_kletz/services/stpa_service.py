"""STPA analyses: the rules of the six entities and the operations on a whole analysis (0.24.0).

The rules of asi_hopper/docs/confluence-integration-plan.md, section 7.1, live in one rule object per
entity (the shape of ``control_structure_service.EntityRules``, attached by ``Brain.service``), so they
hold whichever verb writes the row (``create stpa_uca`` as much as the factory): a part names an
analysis that exists; a code (L1, H4.3, UCA14, CSTR28) is unique within the analysis and immutable while
other rows point at it; a hazard code listed on a UCA, a loss on a hazard, a constraint on a scenario or
the UCA of a scenario must exist in the analysis, as a **warning**, never a refusal (the pages cite
``[H4]`` where only H4.3 to H4.5 are listed, and a scenario row may have an empty UCA cell); a dotted
hazard's parent is the code before its last dot when that hazard exists; the ``source_*`` fields of an
analysis read from Confluence change only through ``refresh``; one analysis per (page id, version) at
most; an analysis with parts is deleted with ``cascade`` or not at all. Every change publishes
``stpa.changed`` with the analysis's slug.

``StpaService`` (``brain.stpa``) holds what works on an analysis as a whole: resolve by id, uid or
slug; the parts; the plain **dataset** form the reader produces and ``create_from_dataset`` loads in
one transaction; ``validate``; ``delete`` with cascade; ``duplicate``; ``compare`` (the refresh
report: new, changed and retired objects by code) and ``apply_refresh`` (the report applied, every
Kletz-side field kept); ``link_structure`` (``cs_controller`` and ``cs_signal`` proposed by name).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound, ValidationError
from ..schema import normalise_uid, slugify
from ..schema.lists import list_of
from .control_structure_service import EntityRules, _merged, _rows

if TYPE_CHECKING:
    from ..brain import Brain

ANALYSIS_ENTITY = "stpa_analysis"
# the parts in the order they are loaded: what is pointed at before what points (a scenario names its
# UCA and its constraints)
PART_ENTITIES = ("stpa_loss", "stpa_hazard", "stpa_uca", "stpa_constraint", "stpa_scenario")
DATASET_KEYS = {
    "stpa_loss": "losses",
    "stpa_hazard": "hazards",
    "stpa_uca": "ucas",
    "stpa_scenario": "scenarios",
    "stpa_constraint": "constraints",
}
# what the page says about each object: the refresh compares these and writes these; every other
# field (a note, cs_controller, cs_signal, the analysis's status) is Kletz's and is kept
PAGE_FIELDS = {
    "stpa_loss": ("text",),
    "stpa_hazard": ("text", "parent", "losses", "retired"),
    "stpa_uca": ("controller", "control_action", "category", "text", "hazards", "retired", "duplicate_of"),
    "stpa_scenario": ("uca", "counterpart", "types", "causal_factors", "beliefs", "constraints", "retired"),
    "stpa_constraint": ("text",),
}
SOURCE_FIELDS = (
    "source_kind",
    "source_page_id",
    "source_url",
    "source_version",
    "source_body_sha256",
    "source_taken_at",
    "source_bundle",
)
SCENARIO_TYPES = (1, 2, 3, 4)
_PRIVATE = ("id", "uid", "created_at", "updated_at", "analysis")
_CODE_RE = re.compile(r"^(UCA|CA|CSTR|H|L)(\d+(?:\.\d+)*)$")


def code_key(code: str) -> tuple[str, tuple[int, ...]]:
    """A sort key that puts UCA2 before UCA10 and H4.3 after H4."""
    match = _CODE_RE.match(str(code or "").strip())
    if not match:
        return (str(code), ())
    return (match.group(1), tuple(int(p) for p in match.group(2).split(".")))


def scenario_key(row: Mapping[str, Any]) -> str:
    """How the refresh names a scenario row, which has no code: ``row 12``."""
    return f"row {row.get('row')}" if row.get("row") is not None else f"order {row.get('order')}"


def _items(value: Any) -> list[Any]:
    """The list behind a JSON field as the rules see it (``clean`` may still hold the JSON text)."""
    try:
        return list_of(value)
    except ValueError:
        return []


class StpaRowRules(EntityRules):
    """Shared behaviour of the six entities: lookups refused, ``stpa.changed`` after a change."""

    @property
    def bulk(self) -> bool:
        return bool(self.brain.stpa.bulk)

    def after_change(self, action: str, row: dict[str, Any], actor: str) -> None:
        if self.bulk:
            return  # one event for the whole load or refresh, published by the analysis service
        slug = row.get("slug") if self.schema.name == ANALYSIS_ENTITY else row.get("analysis")
        self.events.publish(
            "stpa.changed", analysis=slug, entity=self.schema.name, action=action, id=row.get("id"), actor=actor
        )


class StpaAnalysisRowRules(StpaRowRules):
    """``stpa_analysis``: a unique slug (from the name when not given), immutable while parts exist; one
    analysis per (page id, version); the source fields read only once read from Confluence."""

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        if stored is None:
            if not clean.get("slug"):
                clean["slug"] = slugify(str(row.get("name") or ""))
            if clean.get("status") is None:
                clean["status"] = "Draft"
            if clean.get("source_kind") is None:
                clean["source_kind"] = "hand"
            row = _merged(clean, stored)
        else:
            if "slug" in clean and clean["slug"] != stored.get("slug"):
                if any(_rows(self.brain, e, analysis=stored["slug"]) for e in PART_ENTITIES):
                    self.refuse("slug: the parts point at it; duplicate the analysis under the new slug instead")
            if stored.get("source_kind") == "confluence" and not self.bulk:
                moved = [f for f in SOURCE_FIELDS if f in clean and clean[f] != stored.get(f)]
                if moved:
                    self.refuse(f"{', '.join(moved)}: read from Confluence; `stpa refresh` is the way the source moves")
        if not row.get("slug"):
            self.refuse("slug: a value is required")
        twins = [
            r for r in _rows(self.brain, ANALYSIS_ENTITY, slug=row["slug"]) if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"slug: {row['slug']!r} is already the slug of STPA analysis {twins[0]['id']}")
        if row.get("source_page_id") and row.get("source_version") is not None:
            same_page = [
                r
                for r in _rows(
                    self.brain,
                    ANALYSIS_ENTITY,
                    source_page_id=row["source_page_id"],
                    source_version=row["source_version"],
                )
                if stored is None or r["id"] != stored["id"]
            ]
            if same_page:
                self.refuse(
                    f"source: analysis {same_page[0]['id']} ({same_page[0]['slug']}) already holds page "
                    f"{row['source_page_id']} v{row['source_version']}"
                )
        self.require_lookup(row, "status")
        self.require_lookup(row, "source_kind")
        if row.get("control_structure"):
            if not _rows(self.brain, "control_structure", slug=row["control_structure"]):
                self.refuse(f"control_structure: no control structure has the slug {row['control_structure']!r}")
        return []

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        counts = {e: len(_rows(self.brain, e, analysis=stored["slug"])) for e in PART_ENTITIES}
        held = {e: n for e, n in counts.items() if n}
        if held and not cascade:
            self.refuse(
                "the analysis has parts ("
                + ", ".join(f"{n} {e}" for e, n in held.items())
                + "); delete with --cascade to take them along"
            )
        for entity in reversed(PART_ENTITIES):
            self.brain.service(entity).repo.delete_where(analysis=stored["slug"])
        self.storage.audit(actor, "stpa.delete", ANALYSIS_ENTITY, stored["id"], {"slug": stored["slug"], **held})


class StpaPartRules(StpaRowRules):
    """A part of an analysis: its analysis exists; its order defaults to the next one."""

    def analysis_of(self, row: Mapping[str, Any]) -> dict[str, Any]:
        slug = row.get("analysis")
        found = _rows(self.brain, ANALYSIS_ENTITY, slug=slug) if slug else []
        if not found:
            self.refuse(f"analysis: no STPA analysis has the slug {slug!r}")
        return found[0]

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        self.analysis_of(row)
        if stored is None and clean.get("order") is None:
            siblings = _rows(self.brain, self.schema.name, analysis=row["analysis"])
            clean["order"] = max((r.get("order") or 0 for r in siblings), default=0) + 1
        return []

    def codes_of(self, entity: str, analysis: str) -> set[str]:
        """The codes of ``entity`` in the analysis, plus the ones a load in progress is about to write
        (a struck UCA may be the duplicate of one listed after it)."""
        known = {r["code"] for r in _rows(self.brain, entity, analysis=analysis)}
        if self.bulk:
            known |= self.brain.stpa.incoming.get(entity, set())
        return known

    def missing(self, row: Mapping[str, Any], field: str, entity: str, label: str) -> list[str]:
        """A warning per code in the list ``field`` that no row of ``entity`` carries."""
        wanted = [str(c).strip() for c in _items(row.get(field)) if str(c).strip()]
        if not wanted:
            return []
        known = self.codes_of(entity, row["analysis"])
        unknown = [c for c in wanted if c not in known]
        if not unknown:
            return []
        who = row.get("code") or scenario_key(row)
        return [f"{who}: {field} names {', '.join(unknown)}, which the analysis has no {label} for"]


class StpaCodedRules(StpaPartRules):
    """A part with a code: required, unique within the analysis, immutable while rows point at it."""

    def references(self, stored: Mapping[str, Any]) -> dict[str, int]:
        """How many rows point at ``stored`` by its code (what a code change or a delete must respect)."""
        return {}

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        code = " ".join(str(row.get("code") or "").split())
        if not code:
            self.refuse("code: a value is required")
        if "code" in clean or stored is None:
            clean["code"] = code
        if stored is not None and "code" in clean and clean["code"] != stored.get("code"):
            users = {e: n for e, n in self.references(stored).items() if n}
            if users:
                self.refuse(
                    "code: other rows point at it ("
                    + ", ".join(f"{n} {e}" for e, n in users.items())
                    + "); change them first"
                )
        twins = [
            r
            for r in _rows(self.brain, self.schema.name, analysis=row["analysis"], code=code)
            if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"code: {code!r} is already a {self.schema.label} of this analysis")
        return warnings


class StpaLossRules(StpaCodedRules):
    def references(self, stored: Mapping[str, Any]) -> dict[str, int]:
        hazards = _rows(self.brain, "stpa_hazard", analysis=stored["analysis"])
        return {"stpa_hazard": sum(1 for h in hazards if stored["code"] in _items(h.get("losses")))}


class StpaHazardRules(StpaCodedRules):
    def references(self, stored: Mapping[str, Any]) -> dict[str, int]:
        slug, code = stored["analysis"], stored["code"]
        ucas = _rows(self.brain, "stpa_uca", analysis=slug)
        return {
            "stpa_uca": sum(1 for u in ucas if code in _items(u.get("hazards"))),
            "stpa_hazard": len(_rows(self.brain, "stpa_hazard", analysis=slug, parent=code)),
        }

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        known = self.codes_of("stpa_hazard", row["analysis"]) - ({stored["code"]} if stored else set())
        if not row.get("parent") and "." in row["code"]:
            above = row["code"].rsplit(".", 1)[0]
            if above in known:
                clean["parent"] = above
                row = _merged(clean, stored)
        if row.get("parent") and row["parent"] not in known:
            warnings.append(f"{row['code']}: parent {row['parent']} is not a hazard of the analysis")
        warnings.extend(self.missing(row, "losses", "stpa_loss", "loss"))
        return warnings


class StpaUcaRules(StpaCodedRules):
    def references(self, stored: Mapping[str, Any]) -> dict[str, int]:
        slug, code = stored["analysis"], stored["code"]
        return {
            "stpa_scenario": len(_rows(self.brain, "stpa_scenario", analysis=slug, uca=code)),
            "stpa_uca": len(_rows(self.brain, "stpa_uca", analysis=slug, duplicate_of=code)),
        }

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        self.require_lookup(row, "category")
        warnings.extend(self.missing(row, "hazards", "stpa_hazard", "hazard"))
        twin = row.get("duplicate_of")
        if twin and twin not in self.codes_of("stpa_uca", row["analysis"]):
            warnings.append(f"{row['code']}: duplicate of {twin}, which is not a UCA of the analysis")
        return warnings


class StpaScenarioRules(StpaPartRules):
    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        if "types" in clean:
            types: list[int] = []
            for item in _items(clean.get("types")):
                try:
                    number = int(str(item).strip())
                except ValueError:
                    self.refuse(f"types: {item!r} is not a scenario type (1 to 4)")
                if number not in SCENARIO_TYPES:
                    self.refuse(f"types: {number} is not a scenario type (1 to 4)")
                if number not in types:
                    types.append(number)
            clean["types"] = types
            self.lists(clean, every=False)  # the integers back as the JSON array
            row = _merged(clean, stored)
        who = scenario_key(row)
        if not row.get("uca"):
            warnings.append(f"{who}: no UCA")
        elif row["uca"] not in self.codes_of("stpa_uca", row["analysis"]):
            warnings.append(f"{who}: UCA {row['uca']} is not a UCA of the analysis")
        warnings.extend(self.missing(row, "constraints", "stpa_constraint", "constraint"))
        return warnings


class StpaConstraintRules(StpaCodedRules):
    def references(self, stored: Mapping[str, Any]) -> dict[str, int]:
        scenarios = _rows(self.brain, "stpa_scenario", analysis=stored["analysis"])
        return {"stpa_scenario": sum(1 for s in scenarios if stored["code"] in _items(s.get("constraints")))}


STPA_RULE_CLASSES: dict[str, type[EntityRules]] = {
    ANALYSIS_ENTITY: StpaAnalysisRowRules,
    "stpa_loss": StpaLossRules,
    "stpa_hazard": StpaHazardRules,
    "stpa_uca": StpaUcaRules,
    "stpa_scenario": StpaScenarioRules,
    "stpa_constraint": StpaConstraintRules,
}


def _same(a: Any, b: Any) -> bool:
    if isinstance(a, list) or isinstance(b, list):
        return [str(x) for x in (a or [])] == [str(x) for x in (b or [])]
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)
    return (a if a not in ("", None) else None) == (b if b not in ("", None) else None)


class StpaService:
    """What works on an analysis as a whole (``brain.stpa``)."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.bulk = False  # while a dataset is loaded whole or a refresh is applied: one stpa.changed at the end
        self.incoming: dict[str, set[str]] = {}  # the codes that load is about to write, per entity

    def rules_for(self, entity: str) -> EntityRules | None:
        """The rule object of one of the six entities, or ``None`` for any other; ``Brain.service`` attaches it."""
        cls = STPA_RULE_CLASSES.get(entity)
        return cls(self.brain, entity) if cls else None

    def _begin_bulk(self, dataset: Mapping[str, Any]) -> None:
        self.incoming = {
            e: {str(r.get("code")) for r in dataset.get(DATASET_KEYS[e]) or [] if r.get("code")}
            for e in PART_ENTITIES
            if e != "stpa_scenario"
        }
        self.bulk = True

    def _end_bulk(self) -> None:
        self.bulk = False
        self.incoming = {}

    # -- reads ----------------------------------------------------------
    def resolve(self, ref: Any) -> dict[str, Any]:
        """The analysis behind ``ref``: an id, a uid or a slug."""
        service = self.brain.service(ANALYSIS_ENTITY)
        if isinstance(ref, Mapping) and "slug" in ref:
            return dict(ref)
        text = str(ref).strip()
        if not text:
            raise CommandError("an STPA analysis id, uid or slug is required")
        if text.isdigit() or (isinstance(ref, int) and not isinstance(ref, bool)):
            return service.get(int(text))
        if normalise_uid(text) is not None:
            return service.get_by_uid(text)
        rows = service.repo.list({"slug": text})
        if not rows:
            raise NotFound(f"STPA analysis {text!r} not found (by id, uid or slug)")
        return rows[0]

    def parts(self, slug: str) -> dict[str, list[dict[str, Any]]]:
        """Every part of the analysis, keyed as a dataset is (``losses`` ...), in schema order."""
        return {DATASET_KEYS[e]: _rows(self.brain, e, analysis=slug) for e in PART_ENTITIES}

    def counts(self, slug: str) -> dict[str, int]:
        return {key: len(rows) for key, rows in self.parts(slug).items()}

    def summary(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {**row, "counts": self.counts(row["slug"])}

    def dataset(self, ref: Any) -> dict[str, Any]:
        """The analysis as a plain dataset: ``analysis`` (its fields) and the five part lists, every row
        without id, uid, timestamps and the analysis slug. What the reader produces and
        ``create_from_dataset`` loads."""
        row = self.resolve(ref)
        head = {k: v for k, v in row.items() if k not in ("id", "uid", "created_at", "updated_at")}
        out: dict[str, Any] = {"analysis": head}
        for key, rows in self.parts(row["slug"]).items():
            out[key] = [{k: v for k, v in r.items() if k not in _PRIVATE} for r in rows]
        return out

    # -- writes ---------------------------------------------------------
    def create_from_dataset(
        self, dataset: Mapping[str, Any], actor: str = "python", **overrides: Any
    ) -> tuple[dict[str, Any], list[str]]:
        """Create an analysis and all its parts from a dataset in one transaction. ``overrides``
        (``name``, ``slug``, ``system`` ...) replace the dataset's analysis fields. Every row goes
        through its service, so the rules hold and a dangling code is a warning. Audited once as
        ``stpa.new`` with the counts; one ``stpa.changed`` with action ``new``."""
        head = {
            k: v
            for k, v in dict(dataset.get("analysis") or {}).items()
            if k not in ("id", "uid", "created_at", "updated_at")
        }
        head.update({k: v for k, v in overrides.items() if v is not None})
        if not head.get("name"):
            raise CommandError("an STPA analysis needs a name")
        warnings: list[str] = []
        self._begin_bulk(dataset)
        try:
            with self.brain.storage.transaction():
                row, w = self.brain.service(ANALYSIS_ENTITY).create(head, actor)
                warnings.extend(w)
                slug = row["slug"]
                for entity in PART_ENTITIES:
                    service = self.brain.service(entity)
                    for index, part in enumerate(dataset.get(DATASET_KEYS[entity]) or [], start=1):
                        data = {k: v for k, v in dict(part).items() if k not in _PRIVATE}
                        data["analysis"] = slug
                        try:
                            _, w = service.create(data, actor)
                        except ValidationError as exc:
                            raise ValidationError(entity, [f"row {index}: {e}" for e in exc.errors]) from None
                        warnings.extend(f"{entity}: {x}" for x in w)
                counts = self.counts(slug)
                self.brain.storage.audit(actor, "stpa.new", ANALYSIS_ENTITY, row["id"], {"slug": slug, **counts})
        finally:
            self._end_bulk()
        self.brain.events.publish(
            "stpa.changed",
            analysis=slug,
            entity=ANALYSIS_ENTITY,
            action="new",
            id=row["id"],
            actor=actor,
        )
        return self.summary(row), warnings

    def duplicate(
        self, ref: Any, name: str, slug: str | None = None, actor: str = "python"
    ) -> tuple[dict[str, Any], list[str]]:
        """A deep copy under a new slug (from the new name when not given), status Draft, source ``hand``
        (the copy is not the page's any more; its cites still say where every object came from)."""
        source = self.resolve(ref)
        if not name or not str(name).strip():
            raise CommandError("duplicate needs --name")
        dataset = self.dataset(source)
        new_slug = slug or slugify(name)
        head = {k: v for k, v in dataset["analysis"].items() if k not in SOURCE_FIELDS}
        dataset["analysis"] = {**head, "source_kind": "hand", "note": f"duplicate of {source['slug']}"}
        row, warnings = self.create_from_dataset(dataset, actor, name=name, slug=new_slug, status="Draft")
        self.brain.storage.audit(
            actor,
            "stpa.duplicate",
            ANALYSIS_ENTITY,
            row["id"],
            {"from": source["slug"], "slug": new_slug},
        )
        return row, warnings

    def delete(self, ref: Any, cascade: bool = False, actor: str = "python") -> dict[str, Any]:
        row = self.resolve(ref)
        counts = self.counts(row["slug"])
        self.brain.service(ANALYSIS_ENTITY).delete(int(row["id"]), actor, cascade=cascade)
        return {"id": row["id"], "slug": row["slug"], "deleted": {ANALYSIS_ENTITY: 1, **counts}}

    # -- validation -----------------------------------------------------
    def validate(self, ref: Any) -> dict[str, Any]:
        """Every rule checked on the stored rows: errors (what the service would refuse) and warnings
        (dangling codes, UCAs without a scenario, constraints only referenced, duplicate texts, UCAs
        naming a controller the attached structure does not have)."""
        row = self.resolve(ref)
        slug = row["slug"]
        parts = self.parts(slug)
        errors: list[str] = []
        warnings: list[str] = []
        categories = self.brain.lookups.get("stpa_uca_category", ())
        codes: dict[str, set[str]] = {}
        for key in ("losses", "hazards", "ucas", "constraints"):
            seen = [p["code"] for p in parts[key]]
            codes[key] = set(seen)
            if len(codes[key]) != len(seen):
                errors.append(f"{key}: codes are not unique")
        for h in parts["hazards"]:
            if h.get("parent") and h["parent"] not in codes["hazards"]:
                warnings.append(f"{h['code']}: parent {h['parent']} is not a hazard of the analysis")
            for loss in _items(h.get("losses")):
                if loss not in codes["losses"]:
                    warnings.append(f"{h['code']}: loss {loss} is not a loss of the analysis")
        texts: dict[str, list[str]] = {}
        with_scenario = {s["uca"] for s in parts["scenarios"] if s.get("uca")}
        structure = row.get("control_structure")
        controllers: dict[str, dict[str, Any]] = {}
        if structure:
            found = _rows(self.brain, "cs_controller", structure=structure)
            controllers = {c["key"]: c for c in found}
            if not _rows(self.brain, "control_structure", slug=structure):
                errors.append(f"control_structure: no control structure has the slug {structure!r}")
        for u in parts["ucas"]:
            if u.get("category") not in (None, *categories):
                errors.append(f"{u['code']}: category {u.get('category')!r} is not one of {', '.join(categories)}")
            for hazard in _items(u.get("hazards")):
                if hazard not in codes["hazards"]:
                    warnings.append(f"{u['code']}: hazard {hazard} is not a hazard of the analysis")
            if u.get("duplicate_of") and u["duplicate_of"] not in codes["ucas"]:
                warnings.append(f"{u['code']}: duplicate of {u['duplicate_of']}, which is not a UCA of the analysis")
            if u["code"] not in with_scenario and not u.get("retired"):
                warnings.append(f"{u['code']}: no loss scenario names it")
            text = " ".join(str(u.get("text") or "").split()).casefold()
            if text:
                texts.setdefault(text, []).append(u["code"])
            if u.get("cs_controller") and controllers and u["cs_controller"] not in controllers:
                errors.append(f"{u['code']}: cs_controller {u['cs_controller']!r} is not in {structure}")
            if structure and u.get("controller") and not u.get("cs_controller"):
                if not match_controller(u["controller"], controllers.values())[0]:
                    warnings.append(f"{u['code']}: controller {u['controller']!r} is not in structure {structure}")
        for who in texts.values():
            if len(who) > 1:
                warnings.append(f"{', '.join(who)} have the same text")
        for s in parts["scenarios"]:
            who = scenario_key(s)
            if not s.get("uca"):
                warnings.append(f"{who}: no UCA")
            elif s["uca"] not in codes["ucas"]:
                warnings.append(f"{who}: UCA {s['uca']} is not a UCA of the analysis")
            for t in _items(s.get("types")):
                if int(t) not in SCENARIO_TYPES:
                    errors.append(f"{who}: type {t} is not a scenario type (1 to 4)")
            for c in _items(s.get("constraints")):
                if c not in codes["constraints"]:
                    warnings.append(f"{who}: constraint {c} is not a constraint of the analysis")
        for c in parts["constraints"]:
            if not str(c.get("text") or "").strip():
                warnings.append(f"{c['code']}: only referenced, never spelled out")
        return {
            "id": row["id"],
            "slug": slug,
            "name": row["name"],
            "counts": {k: len(v) for k, v in parts.items()},
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
        }

    # -- refresh ----------------------------------------------------------
    def compare(self, ref: Any, dataset: Mapping[str, Any]) -> dict[str, Any]:
        """The refresh report: ``dataset`` (the page read again) against the stored objects, by code
        (a scenario by its row): ``new``, ``changed`` (the page fields that differ, before and after),
        ``retired`` (gone from the page or now struck). Nothing is written."""
        row = self.resolve(ref)
        stored = self.parts(row["slug"])
        report: dict[str, Any] = {
            "id": row["id"],
            "slug": row["slug"],
            "name": row["name"],
            "source": {k: v for k, v in dict(dataset.get("analysis") or {}).items() if k in SOURCE_FIELDS},
            "new": {},
            "changed": {},
            "retired": {},
            "removed": {},
            "counts": {},
            "warnings": [str(w) for w in dataset.get("warnings") or []],
            "same": True,
        }
        for entity in PART_ENTITIES:
            key = DATASET_KEYS[entity]
            incoming = list(dataset.get(key) or [])
            have = {self._key(entity, r): r for r in stored[key]}
            want = {self._key(entity, r): r for r in incoming}
            new = [k for k in want if k not in have]
            changed: list[dict[str, Any]] = []
            for k, fresh in want.items():
                old = have.get(k)
                if old is None:
                    continue
                diff = {
                    f: {"before": old.get(f), "after": fresh.get(f)}
                    for f in PAGE_FIELDS[entity]
                    if not _same(old.get(f), fresh.get(f))
                }
                if diff:
                    changed.append({"key": k, "fields": diff})
            gone = [k for k in have if k not in want]
            retired = [k for k in gone if "retired" in PAGE_FIELDS[entity] and not have[k].get("retired")]
            removed = [k for k in gone if "retired" not in PAGE_FIELDS[entity]]
            report["counts"][key] = {"stored": len(have), "page": len(want)}
            for bucket, items in (("new", new), ("changed", changed), ("retired", retired), ("removed", removed)):
                if items:
                    report[bucket][key] = items
                    report["same"] = False
        return report

    @staticmethod
    def _key(entity: str, row: Mapping[str, Any]) -> str:
        return scenario_key(row) if entity == "stpa_scenario" else str(row.get("code") or "")

    def apply_refresh(self, ref: Any, dataset: Mapping[str, Any], actor: str = "python") -> dict[str, Any]:
        """Apply ``compare``'s report: new objects created, changed ones updated on their page fields
        only (every Kletz-side field kept), gone ones retired (or removed when they cannot be), every
        cite moved to the new version, the analysis's ``source_*`` moved to the page read. One audit
        entry per object changed (the ordinary create / update / delete entries) plus ``stpa.refresh``
        with the counts; one ``stpa.changed`` with action ``refresh``."""
        row = self.resolve(ref)
        report = self.compare(row, dataset)
        slug = row["slug"]
        stored = self.parts(slug)
        touched = {"created": 0, "updated": 0, "retired": 0, "removed": 0, "cited": 0}
        self._begin_bulk(dataset)
        try:
            with self.brain.storage.transaction():
                for entity in PART_ENTITIES:
                    key = DATASET_KEYS[entity]
                    service = self.brain.service(entity)
                    have = {self._key(entity, r): r for r in stored[key]}
                    want = {self._key(entity, r): r for r in dataset.get(key) or []}
                    for k, fresh in want.items():
                        old = have.get(k)
                        if old is None:
                            data = {f: v for f, v in dict(fresh).items() if f not in _PRIVATE}
                            service.create({**data, "analysis": slug}, actor)
                            touched["created"] += 1
                            continue
                        changes = {f: fresh.get(f) for f in PAGE_FIELDS[entity] if not _same(old.get(f), fresh.get(f))}
                        if changes:
                            service.update(int(old["id"]), {**changes, "cite": fresh.get("cite")}, actor)
                            touched["updated"] += 1
                        elif not _same(old.get("cite"), fresh.get("cite")):
                            service.repo.update(int(old["id"]), {"cite": fresh.get("cite")})  # the baseline moved
                            touched["cited"] += 1
                    for k, old in have.items():
                        if k in want:
                            continue
                        if "retired" in PAGE_FIELDS[entity]:
                            if not old.get("retired"):
                                service.update(int(old["id"]), {"retired": True}, actor)
                                touched["retired"] += 1
                        else:
                            service.delete(int(old["id"]), actor)
                            touched["removed"] += 1
                source = report["source"]
                if source:
                    self.brain.service(ANALYSIS_ENTITY).update(int(row["id"]), source, actor)
                self.brain.storage.audit(actor, "stpa.refresh", ANALYSIS_ENTITY, row["id"], {"slug": slug, **touched})
        finally:
            self._end_bulk()
        self.brain.events.publish(
            "stpa.changed",
            analysis=slug,
            entity=ANALYSIS_ENTITY,
            action="refresh",
            id=row["id"],
            actor=actor,
        )
        return {**report, "applied": True, "touched": touched, "counts": self.counts(slug)}

    # -- linking to a control structure ---------------------------------
    def link_structure(
        self, ref: Any, structure: str | None = None, *, apply: bool = False, actor: str = "python"
    ) -> dict[str, Any]:
        """Propose ``cs_controller`` and ``cs_signal`` for every UCA by name: the UCA's controller text
        against the structure's controller names and keys, its control action against the names of the
        signals leaving that controller, case-insensitively. Exact matches apply with ``apply``; partial
        ones are reported with their candidates and never written."""
        row = self.resolve(ref)
        slug = structure or row.get("control_structure")
        if not slug:
            raise CommandError("link needs --structure <slug>, or an analysis that already names one")
        target = self.brain.control_structures.resolve(slug)
        parts = self.brain.control_structures.parts(target["slug"])
        controllers = list(parts["controllers"])
        proposals: list[dict[str, Any]] = []
        for u in self.parts(row["slug"])["ucas"]:
            controller, candidates = match_controller(u.get("controller") or "", controllers)
            signal, signal_candidates = None, []
            if controller is not None:
                leaving = [e["key"] for e in parts["edges"] if e["source"] == controller["key"]]
                signals = [s for s in parts["signals"] if s["edge"] in leaving]
                signal, signal_candidates = match_signal(u.get("control_action") or "", signals)
            status = (
                "exact"
                if controller is not None and signal is not None
                else ("partial" if candidates or signal_candidates or controller is not None else "none")
            )
            proposals.append(
                {
                    "code": u["code"],
                    "controller": u.get("controller"),
                    "control_action": u.get("control_action"),
                    "cs_controller": controller["key"] if controller else None,
                    "cs_signal": signal["signal_id"] if signal else None,
                    "candidates": {
                        "controllers": [c["key"] for c in candidates],
                        "signals": [f"{s['signal_id']} {s.get('name') or ''}".strip() for s in signal_candidates],
                    },
                    "status": status,
                    "id": u["id"],
                    "current": {"cs_controller": u.get("cs_controller"), "cs_signal": u.get("cs_signal")},
                }
            )
        applied = 0
        if apply:
            service = self.brain.service("stpa_uca")
            with self.brain.storage.transaction():
                if row.get("control_structure") != target["slug"]:
                    self.brain.service(ANALYSIS_ENTITY).update(
                        int(row["id"]),
                        {"control_structure": target["slug"]},
                        actor,
                    )
                for p in proposals:
                    if p["status"] != "exact":
                        continue
                    changes = {k: p[k] for k in ("cs_controller", "cs_signal") if p["current"][k] != p[k]}
                    if changes:
                        service.update(int(p["id"]), changes, actor)
                        applied += 1
                self.brain.storage.audit(
                    actor,
                    "stpa.link",
                    ANALYSIS_ENTITY,
                    row["id"],
                    {"slug": row["slug"], "structure": target["slug"], "applied": applied},
                )
        return {
            "id": row["id"],
            "slug": row["slug"],
            "structure": target["slug"],
            "applied": applied if apply else None,
            "ucas": [{k: v for k, v in p.items() if k not in ("id", "current")} for p in proposals],
            "exact": sum(1 for p in proposals if p["status"] == "exact"),
            "partial": sum(1 for p in proposals if p["status"] == "partial"),
            "none": sum(1 for p in proposals if p["status"] == "none"),
        }


def _norm(text: Any) -> str:
    return " ".join(str(text or "").replace("_", " ").split()).casefold()


def match_controller(text: str, controllers: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The controller whose name or key equals ``text`` case-insensitively, else ``None`` and the
    controllers whose name contains it (or that it contains)."""
    wanted = _norm(text)
    if not wanted:
        return None, []
    rows = list(controllers)
    for c in rows:
        if wanted in (_norm(c.get("name")), _norm(c.get("key"))):
            return c, []
    partial = [c for c in rows if wanted in _norm(c.get("name")) or _norm(c.get("name")) in wanted]
    return None, partial


def match_signal(text: str, signals: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """The signal whose name (or id) equals ``text`` case-insensitively, else the partial candidates."""
    wanted = _norm(text)
    if not wanted:
        return None, []
    rows = list(signals)
    for s in rows:
        if wanted in (_norm(s.get("name")), _norm(s.get("signal_id"))):
            return s, []
    partial = [
        s for s in rows if wanted in _norm(s.get("name")) or (_norm(s.get("name")) and _norm(s.get("name")) in wanted)
    ]
    return None, partial
