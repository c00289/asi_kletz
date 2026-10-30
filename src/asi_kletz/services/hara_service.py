"""HARA: the rules of the nine entities and the operations on a whole HARA (0.28.0).

The owner, 2026-10-30: "lets parametrize the hara ... the workbook is complicated as hell". The dissection in
Roy's Brain (work product playground/hara/dissection) found one computation in the whole workbook: the MPLr of
an assessment row is a lookup of (function, use case, failure mode) in the rating table, the answer taken from
the column of the vehicle code in Document Information. The workbook's second generation of that formula keyed
on a vehicle code nobody filled in; its first generation pointed three of four context sheets at the foundation
vehicle's column and one at the wheel loader's. Here the rule is finished: ``HaraService.recompute`` writes the
``mplr`` of every assessment row from ``hara_rating`` and the HARA's ``vehicle_code``; ``summary`` derives the
Summary sheet (the highest MPLr per hazard and context, the other standards' terms); ``check`` says where the
computed value and the workbook's typed one (``stated_mplr``, ``cumulative_mplr``) differ.

The rules live in one rule object per entity (the shape of ``control_structure_service.EntityRules``, attached
by ``Brain.service``), so they hold whichever verb writes the row: a part names a HARA that exists; a vehicle's
letter, a function's, use case's or failure mode's name and a rating's (function, use case, failure mode) key
are unique within the HARA; ``ratings`` is a JSON object of annex letter to MPLr (typed as ``G: b`` lines);
``mplr`` is calculated and refused on a create or an update; an assessment's hazard and scenario follow from
its event code; an approval's role is a slug, never a name; a HARA with parts is deleted with ``cascade`` or
not at all. Every change publishes ``hara.changed`` with the HARA's slug.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ..errors import CommandError, NotFound, ValidationError
from ..schema import normalise_uid, slugify
from ..schema.definitions import (
    CUMULATIVE_CODE,
    HARA_CONTEXTS,
    MPLR_SCALE,
    MPLR_TO_AGPLR,
    MPLR_TO_PLR,
    MPLR_TO_SIL,
)
from ..schema.fields import json_text
from ..schema.lists import list_of
from .control_structure_service import EntityRules, _merged, _rows

if TYPE_CHECKING:
    from ..brain import Brain

HARA_ENTITY = "hara"
# the parts in the order a dataset lists them, which is the order they are loaded
PART_ENTITIES = (
    "hara_vehicle",
    "hara_function",
    "hara_use_case",
    "hara_failure_mode",
    "hara_assumption",
    "hara_rating",
    "hara_assessment",
    "hara_approval",
)
DATASET_KEYS = {
    "hara_vehicle": "vehicles",
    "hara_function": "functions",
    "hara_use_case": "use_cases",
    "hara_failure_mode": "failure_modes",
    "hara_assumption": "assumptions",
    "hara_rating": "ratings",
    "hara_assessment": "assessments",
    "hara_approval": "approvals",
}
NAMED = {"hara_vehicle": "letter", "hara_function": "name", "hara_use_case": "name", "hara_failure_mode": "name"}
NOT_FOUND = "-"  # the rating table has no such (function, use case, failure mode)
_PRIVATE = ("id", "uid", "created_at", "updated_at", "hara")
_EVENT_RE = re.compile(r"^(H-\d+)(?:\.(\d+))?(?:\.(\d+))?$")
_RATING_LINE = re.compile(r"^\s*([A-Za-z]+)\s*[:=]\s*(.*?)\s*$")
_SCALE_RANK = {value: index for index, value in enumerate(MPLR_SCALE)}


def norm_key(*parts: Any) -> tuple[str, ...]:
    """The lookup key of a rating or an assessment: each part's words joined by one space, casefolded, a
    trailing asterisk dropped (the Use Case List marks the base use cases ``Travel/Roading *``; some assessment
    rows type the name without it, and the workbook's exact-match formula answered ``-`` for those)."""
    return tuple(" ".join(str(p or "").split()).casefold().rstrip("* ").strip() for p in parts)


def norm_mplr(value: Any) -> str:
    """An MPLr as the scale spells it: ``QM``, ``a`` to ``e``; ``-`` kept (not found); an empty cell, a 0 or
    anything else (the second generation's use-case names) is the empty string."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text or text == "0":
        return ""
    if text == NOT_FOUND:
        return NOT_FOUND
    if text.casefold() == "qm":
        return "QM"
    if text.lower() in ("a", "b", "c", "d", "e"):
        return text.lower()
    return ""


def highest(values: Any) -> str:
    """The highest MPLr among ``values`` on the scale (QM lowest); ``""`` when none is a rating."""
    best = ""
    for value in values:
        rating = norm_mplr(value)
        if rating in _SCALE_RANK and (best == "" or _SCALE_RANK[rating] > _SCALE_RANK[best]):
            best = rating
    return best


def equivalents(mplr: str) -> dict[str, str]:
    """The other standards' terms for an MPLr, as the workbook's Summary states them."""
    rating = norm_mplr(mplr)
    return {
        "mplr": rating,
        "plr": MPLR_TO_PLR.get(rating, ""),
        "agplr": MPLR_TO_AGPLR.get(rating, ""),
        "sil": MPLR_TO_SIL.get(rating, ""),
    }


def split_event(code: Any) -> tuple[str, str, str]:
    """``("H-1", "H-1.1", "H-1.1.1")`` for an event code; the parts that are not there are empty."""
    text = " ".join(str(code or "").split())
    match = _EVENT_RE.match(text)
    if not match:
        return "", "", text
    hazard = match.group(1)
    scenario = f"{hazard}.{match.group(2)}" if match.group(2) else ""
    event = f"{scenario}.{match.group(3)}" if match.group(3) else ""
    return hazard, scenario, event or scenario or hazard


def ratings_of(value: Any) -> dict[str, str]:
    """The ratings object behind a value: a dict kept (keys upper-cased, values normalised), a JSON object
    parsed, any other text one ``LETTER: rating`` per line (``;`` separates too); blank is ``{}``."""
    if value is None:
        return {}
    if isinstance(value, Mapping):
        out = {}
        for key, rating in value.items():
            letter = str(key).strip().upper()
            if letter:
                out[letter if letter != CUMULATIVE_CODE.upper() else CUMULATIVE_CODE] = norm_mplr(rating)
        return out
    text = str(value).strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            raise ValueError(f"{text[:40]!r} is not a JSON object") from None
        if not isinstance(parsed, dict):
            raise ValueError(f"{text[:40]!r} is not a JSON object")
        return ratings_of(parsed)
    out = {}
    for line in re.split(r"[;\r\n]+", text):
        if not line.strip():
            continue
        match = _RATING_LINE.match(line)
        if not match:
            raise ValueError(f"{line.strip()!r} is not a `LETTER: rating` line")
        out[match.group(1).upper()] = norm_mplr(match.group(2))
    return out


class HaraRowRules(EntityRules):
    """Shared behaviour of the nine entities: ``hara.changed`` after a change unless a load is in flight."""

    @property
    def bulk(self) -> bool:
        return bool(self.brain.hara.bulk)

    def after_change(self, action: str, row: dict[str, Any], actor: str) -> None:
        if self.bulk:
            return
        slug = row.get("slug") if self.schema.name == HARA_ENTITY else row.get("hara")
        self.events.publish(
            "hara.changed", hara=slug, entity=self.schema.name, action=action, id=row.get("id"), actor=actor
        )


class HaraDocumentRules(HaraRowRules):
    """``hara``: a unique slug (from the name when not given), immutable while parts exist; a vehicle code that
    is an annex letter or ``cumulative``; an analysis that exists when named."""

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        if stored is None:
            if not clean.get("slug"):
                clean["slug"] = slugify(str(row.get("name") or ""))
            if clean.get("status") is None:
                clean["status"] = "Draft"
            row = _merged(clean, stored)
        elif "slug" in clean and clean["slug"] != stored.get("slug"):
            if any(_rows(self.brain, e, hara=stored["slug"]) for e in PART_ENTITIES):
                self.refuse("slug: the parts point at it")
        if not row.get("slug"):
            self.refuse("slug: a value is required")
        twins = [
            r for r in _rows(self.brain, HARA_ENTITY, slug=row["slug"]) if stored is None or r["id"] != stored["id"]
        ]
        if twins:
            self.refuse(f"slug: {row['slug']!r} is already the slug of HARA {twins[0]['id']}")
        if "vehicle_code" in clean and clean["vehicle_code"] not in (None, ""):
            code = str(clean["vehicle_code"]).strip()
            if code.casefold() == CUMULATIVE_CODE:
                clean["vehicle_code"] = CUMULATIVE_CODE
            elif len(code) == 1 and code.isalpha():
                clean["vehicle_code"] = code.upper()
            else:
                self.refuse(f"vehicle_code: {code!r} is neither an annex letter (A to Z) nor `{CUMULATIVE_CODE}`")
        self.require_lookup(row, "status")
        if row.get("analysis") and not _rows(self.brain, "stpa_analysis", slug=row["analysis"]):
            self.refuse(f"analysis: no STPA analysis has the slug {row['analysis']!r}")
        return []

    def before_delete(self, stored: dict[str, Any], cascade: bool, actor: str) -> None:
        counts = {e: len(_rows(self.brain, e, hara=stored["slug"])) for e in PART_ENTITIES}
        held = {e: n for e, n in counts.items() if n}
        if held and not cascade:
            self.refuse(
                "the HARA has parts ("
                + ", ".join(f"{n} {e}" for e, n in held.items())
                + "); delete with --cascade to take them along"
            )
        for entity in reversed(PART_ENTITIES):
            self.brain.service(entity).repo.delete_where(hara=stored["slug"])
        self.storage.audit(actor, "hara.delete", HARA_ENTITY, stored["id"], {"slug": stored["slug"], **held})


class HaraPartRules(HaraRowRules):
    """A part of a HARA: its HARA exists; its order defaults to the next one; the named parts are unique."""

    def hara_of(self, row: Mapping[str, Any]) -> dict[str, Any]:
        slug = row.get("hara")
        found = _rows(self.brain, HARA_ENTITY, slug=slug) if slug else []
        if not found:
            self.refuse(f"hara: no HARA has the slug {slug!r}")
        return found[0]

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        row = _merged(clean, stored)
        self.hara_of(row)
        if stored is None and clean.get("order") is None:
            if self.bulk:
                clean["order"] = self.brain.hara.next_order(self.schema.name, row["hara"])
            else:
                siblings = _rows(self.brain, self.schema.name, hara=row["hara"])
                clean["order"] = max((r.get("order") or 0 for r in siblings), default=0) + 1
        field = NAMED.get(self.schema.name)
        if field:
            value = " ".join(str(row.get(field) or "").split())
            if field == "letter":
                value = value.upper()
            if not value:
                self.refuse(f"{field}: a value is required")
            if field in clean or stored is None:
                clean[field] = value
            if not self.bulk:
                twins = [
                    r
                    for r in _rows(self.brain, self.schema.name, hara=row["hara"])
                    if (stored is None or r["id"] != stored["id"]) and norm_key(r.get(field)) == norm_key(value)
                ]
                if twins:
                    self.refuse(f"{field}: {value!r} is already a {self.schema.label} of this HARA")
        return []


class HaraRatingRules(HaraPartRules):
    """``hara_rating``: the ratings object normalised; one row per (function, use case, failure mode)."""

    def lists(self, clean: dict[str, Any], *, every: bool) -> None:
        if "ratings" in clean or every:
            try:
                clean["ratings"] = json_text(ratings_of(clean.get("ratings")))
            except ValueError as exc:
                self.refuse(f"ratings: {exc}")

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        for field in ("function", "use_case", "failure_mode"):
            if field in clean or stored is None:
                clean[field] = " ".join(str(row.get(field) or "").split())
        row = _merged(clean, stored)
        if "cumulative" in clean:
            clean["cumulative"] = norm_mplr(clean["cumulative"]) or (
                NOT_FOUND if clean["cumulative"] == NOT_FOUND else ""
            )
        if not self.bulk:
            key = norm_key(row["function"], row["use_case"], row["failure_mode"])
            twins = [
                r
                for r in _rows(self.brain, self.schema.name, hara=row["hara"])
                if (stored is None or r["id"] != stored["id"])
                and norm_key(r.get("function"), r.get("use_case"), r.get("failure_mode")) == key
            ]
            if twins:
                self.refuse(f"a rating of {' / '.join(key)} already exists (row {twins[0]['id']})")
        return warnings


class HaraAssessmentRules(HaraPartRules):
    """``hara_assessment``: the context is one of the four; the hazard and the scenario follow from the event;
    ``mplr`` is calculated (``recompute`` writes it) and refused here."""

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        if clean.get("mplr") not in (None, "") and not self.brain.hara.computing:
            self.refuse(
                "mplr: calculated from the rating table and the HARA's vehicle code; `hara recompute` writes it"
            )
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        self.require_lookup(row, "context")
        if "event" in clean or stored is None:
            hazard, scenario, event = split_event(row.get("event"))
            clean["event"] = event
            if hazard:
                clean.setdefault("hazard", hazard)
                clean["hazard"] = clean["hazard"] or hazard
                if scenario:
                    clean["scenario"] = clean.get("scenario") or scenario
        for field in ("stated_mplr", "cumulative_mplr", "sg_mplr"):
            if field in clean:
                raw = clean[field]
                clean[field] = NOT_FOUND if str(raw or "").strip() == NOT_FOUND else norm_mplr(raw)
        return warnings


class HaraApprovalRules(HaraPartRules):
    """``hara_approval``: the role is a slug, the decision Y or N."""

    def check(self, clean: dict[str, Any], stored: dict[str, Any] | None) -> list[str]:
        warnings = super().check(clean, stored)
        row = _merged(clean, stored)
        if "role" in clean or stored is None:
            role = slugify(str(row.get("role") or ""))
            if not role:
                self.refuse("role: a value is required")
            clean["role"] = role
        if "decision" in clean and clean["decision"] not in (None, ""):
            clean["decision"] = str(clean["decision"]).strip().upper()[:1]
            row = _merged(clean, stored)
        self.require_lookup(row, "decision")
        if "event" in clean or stored is None:
            clean["event"] = split_event(row.get("event"))[2]
        return warnings


HARA_RULE_CLASSES: dict[str, type[EntityRules]] = {
    HARA_ENTITY: HaraDocumentRules,
    "hara_vehicle": HaraPartRules,
    "hara_function": HaraPartRules,
    "hara_use_case": HaraPartRules,
    "hara_failure_mode": HaraPartRules,
    "hara_assumption": HaraPartRules,
    "hara_rating": HaraRatingRules,
    "hara_assessment": HaraAssessmentRules,
    "hara_approval": HaraApprovalRules,
}


class HaraService:
    """What works on a HARA as a whole (``brain.hara``)."""

    def __init__(self, brain: Brain) -> None:
        self.brain = brain
        self.bulk = False  # while a dataset is loaded whole: one hara.changed at the end, no per-row uniqueness scans
        self.computing = False  # while recompute writes the calculated mplr
        self._orders: dict[tuple[str, str], int] = {}

    def rules_for(self, entity: str) -> EntityRules | None:
        cls = HARA_RULE_CLASSES.get(entity)
        return cls(self.brain, entity) if cls else None

    def on_change(self, entity: str):
        """The ``after`` hook of ``hara``, ``hara_rating`` and ``hara_assessment``: a committed create, update,
        delete or load recomputes the MPLr of the HARA touched (every HARA after a load, which names no row);
        nothing while a dataset is being loaded whole (``create_from_dataset`` recomputes once at the end)."""

        def after(action: str, row_id: int | None) -> None:
            if self.bulk or self.computing:
                return
            if action == "load" or row_id is None:
                for row in _rows(self.brain, HARA_ENTITY):
                    self.recompute(row, "system", audit=False)
                return
            if action == "delete" and entity == HARA_ENTITY:
                return
            row = self.brain.service(entity).repo.get(int(row_id))
            slug = (row or {}).get("slug") if entity == HARA_ENTITY else (row or {}).get("hara")
            if slug and _rows(self.brain, HARA_ENTITY, slug=slug):
                self.recompute(slug, "system", audit=False)

        return after

    def next_order(self, entity: str, slug: str) -> int:
        key = (entity, slug)
        self._orders[key] = self._orders.get(key, 0) + 1
        return self._orders[key]

    # -- reads ----------------------------------------------------------
    def resolve(self, ref: Any) -> dict[str, Any]:
        """The HARA behind ``ref``: an id, a uid or a slug."""
        service = self.brain.service(HARA_ENTITY)
        if isinstance(ref, Mapping) and "slug" in ref:
            return dict(ref)
        text = str(ref).strip()
        if not text:
            raise CommandError("a HARA id, uid or slug is required")
        if text.isdigit() or (isinstance(ref, int) and not isinstance(ref, bool)):
            return service.get(int(text))
        if normalise_uid(text) is not None:
            return service.get_by_uid(text)
        rows = service.repo.list({"slug": text})
        if not rows:
            raise NotFound(f"HARA {text!r} not found (by id, uid or slug)")
        return rows[0]

    def parts(self, slug: str) -> dict[str, list[dict[str, Any]]]:
        return {DATASET_KEYS[e]: _rows(self.brain, e, hara=slug) for e in PART_ENTITIES}

    def counts(self, slug: str) -> dict[str, int]:
        return {DATASET_KEYS[e]: self.brain.service(e).count({"hara": slug}) for e in PART_ENTITIES}

    def summary(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """The HARA row with its counts and the counts of its STPA analysis's step 1."""
        out = {**row, "counts": self.counts(row["slug"])}
        if row.get("analysis"):
            out["step1"] = {
                "losses": self.brain.service("stpa_loss").count({"analysis": row["analysis"]}),
                "hazards": self.brain.service("stpa_hazard").count({"analysis": row["analysis"]}),
                "constraints": self.brain.service("stpa_constraint").count({"analysis": row["analysis"]}),
            }
        return out

    def dataset(self, ref: Any) -> dict[str, Any]:
        """The HARA as a plain dataset: ``hara`` (its fields) and the eight part lists, every row without id,
        uid, timestamps and the HARA slug. What the reader produces and ``create_from_dataset`` loads."""
        row = self.resolve(ref)
        head = {k: v for k, v in row.items() if k not in ("id", "uid", "created_at", "updated_at")}
        out: dict[str, Any] = {"hara": head}
        for key, rows in self.parts(row["slug"]).items():
            out[key] = [{k: v for k, v in r.items() if k not in _PRIVATE} for r in rows]
        return out

    def hazards(self, row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        """The step-1 hazards of the HARA's STPA analysis by code (H-1, H-1.1, H-1.1.1), or ``{}``."""
        if not row.get("analysis"):
            return {}
        return {h["code"]: h for h in _rows(self.brain, "stpa_hazard", analysis=row["analysis"])}

    def constraints(self, row: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        if not row.get("analysis"):
            return {}
        return {c["code"]: c for c in _rows(self.brain, "stpa_constraint", analysis=row["analysis"])}

    # -- writes ---------------------------------------------------------
    def create_from_dataset(
        self, dataset: Mapping[str, Any], actor: str = "python", **overrides: Any
    ) -> tuple[dict[str, Any], list[str]]:
        """Create a HARA and all its parts from a dataset in one transaction, its STPA analysis first when the
        dataset carries one (``stpa``: the analysis and its losses, hazards and constraints, loaded through
        ``StpaService.create_from_dataset``; its slug becomes the HARA's ``analysis``). ``overrides`` (``name``,
        ``slug``, ``vehicle_code`` ...) replace the dataset's HARA fields. Every row goes through its service, so
        the rules hold. Then every assessment's MPLr is computed. Audited once as ``hara.new`` with the counts;
        one ``hara.changed`` with action ``new``."""
        head = {
            k: v
            for k, v in dict(dataset.get("hara") or {}).items()
            if k not in ("id", "uid", "created_at", "updated_at")
        }
        head.update({k: v for k, v in overrides.items() if v is not None})
        if not head.get("name"):
            raise CommandError("a HARA needs a name")
        warnings: list[str] = [str(w) for w in dataset.get("warnings") or []]
        slug = head.get("slug") or slugify(str(head["name"]))
        head["slug"] = slug
        self.bulk = True
        self._orders = {}
        try:
            with self.brain.storage.transaction():
                stpa = dataset.get("stpa")
                if stpa and not head.get("analysis"):
                    analysis = dict(stpa.get("analysis") or {})
                    analysis.setdefault("name", f"{head['name']} (step 1)")
                    analysis.setdefault("slug", slug)
                    analysis.setdefault("system", head.get("system"))
                    analysis.setdefault("source_kind", "workbook")
                    made, w = self.brain.stpa.create_from_dataset({**stpa, "analysis": analysis}, actor)
                    warnings.extend(f"stpa: {x}" for x in w)
                    head["analysis"] = made["slug"]
                row, w = self.brain.service(HARA_ENTITY).create(head, actor)
                warnings.extend(w)
                for entity in PART_ENTITIES:
                    service = self.brain.service(entity)
                    seen: set[tuple[str, ...]] = set()
                    for index, part in enumerate(dataset.get(DATASET_KEYS[entity]) or [], start=1):
                        data = {k: v for k, v in dict(part).items() if k not in _PRIVATE}
                        data["hara"] = slug
                        key = self._unique_key(entity, data)
                        if key is not None:
                            if key in seen:
                                warnings.append(f"{entity}: row {index} repeats {' / '.join(key)}; skipped")
                                continue
                            seen.add(key)
                        try:
                            _, w = service.create(data, actor)
                        except ValidationError as exc:
                            raise ValidationError(entity, [f"row {index}: {e}" for e in exc.errors]) from None
                        warnings.extend(f"{entity}: {x}" for x in w)
                computed = self.recompute(row, actor, audit=False)
                counts = self.counts(slug)
                self.brain.storage.audit(
                    actor, "hara.new", HARA_ENTITY, row["id"], {"slug": slug, **counts, "mplr": computed["changed"]}
                )
        finally:
            self.bulk = False
            self._orders = {}
        self.brain.events.publish(
            "hara.changed", hara=slug, entity=HARA_ENTITY, action="new", id=row["id"], actor=actor
        )
        return {**self.summary(self.resolve(slug)), "mplr": computed}, warnings

    @staticmethod
    def _unique_key(entity: str, data: Mapping[str, Any]) -> tuple[str, ...] | None:
        if entity in NAMED:
            return norm_key(data.get(NAMED[entity]))
        if entity == "hara_rating":
            return norm_key(data.get("function"), data.get("use_case"), data.get("failure_mode"))
        return None

    def delete(self, ref: Any, cascade: bool = False, actor: str = "python") -> dict[str, Any]:
        """Delete the HARA (its parts with ``cascade``). The STPA analysis it names goes too when it was read
        from a workbook and holds no UCA and no scenario (step 3 never began); otherwise it stays and the
        answer says so."""
        row = self.resolve(ref)
        counts = self.counts(row["slug"])
        self.brain.service(HARA_ENTITY).delete(int(row["id"]), actor, cascade=cascade)
        deleted: dict[str, Any] = {HARA_ENTITY: 1, **counts}
        kept = None
        analysis = row.get("analysis")
        if analysis and cascade:
            found = _rows(self.brain, "stpa_analysis", slug=analysis)
            if found:
                begun = self.brain.service("stpa_uca").count({"analysis": analysis}) + self.brain.service(
                    "stpa_scenario"
                ).count({"analysis": analysis})
                if found[0].get("source_kind") == "workbook" and not begun:
                    deleted["stpa"] = self.brain.stpa.delete(analysis, True, actor)["deleted"]
                else:
                    kept = analysis
        return {"id": row["id"], "slug": row["slug"], "deleted": deleted, "analysis_kept": kept}

    # -- the one computation --------------------------------------------
    def rating_index(self, slug: str) -> dict[tuple[str, ...], dict[str, Any]]:
        """The rating table by normalised (function, use case, failure mode)."""
        index: dict[tuple[str, ...], dict[str, Any]] = {}
        for r in _rows(self.brain, "hara_rating", hara=slug):
            index.setdefault(norm_key(r.get("function"), r.get("use_case"), r.get("failure_mode")), r)
        return index

    @staticmethod
    def mplr_for(rating: Mapping[str, Any] | None, vehicle_code: str | None) -> str:
        """The rule: no rating row is ``-``; the vehicle's column (``cumulative`` reads the cumulative one);
        an empty cell is ``""``; no vehicle code is ``""``."""
        if rating is None:
            return NOT_FOUND
        code = str(vehicle_code or "").strip()
        if not code:
            return ""
        if code.casefold() == CUMULATIVE_CODE:
            return norm_mplr(rating.get("cumulative"))
        try:
            ratings = ratings_of(rating.get("ratings"))
        except ValueError:
            return ""
        return norm_mplr(ratings.get(code.upper()))

    def recompute(self, ref: Any, actor: str = "python", *, audit: bool = True) -> dict[str, Any]:
        """Write the ``mplr`` of every assessment row of the HARA from the rating table and the vehicle code,
        where it moved. Answers the counts: rows, changed, not found (no rating key), empty (no rating for the
        vehicle), and the vehicle code used."""
        row = self.resolve(ref)
        slug = row["slug"]
        index = self.rating_index(slug)
        service = self.brain.service("hara_assessment")
        changed = not_found = empty = 0
        rows = _rows(self.brain, "hara_assessment", hara=slug)
        self.computing = True
        try:
            with self.brain.storage.transaction():
                for a in rows:
                    rating = index.get(norm_key(a.get("function"), a.get("use_case"), a.get("failure_mode")))
                    value = self.mplr_for(rating, row.get("vehicle_code"))
                    if value == NOT_FOUND:
                        not_found += 1
                    elif value == "":
                        empty += 1
                    if (a.get("mplr") or "") != value:
                        service.repo.update(int(a["id"]), {"mplr": value})
                        changed += 1
                if audit:
                    self.brain.storage.audit(
                        actor,
                        "hara.recompute",
                        HARA_ENTITY,
                        row["id"],
                        {"slug": slug, "rows": len(rows), "changed": changed, "vehicle_code": row.get("vehicle_code")},
                    )
        finally:
            self.computing = False
        if audit and changed and not self.bulk:
            self.brain.events.publish(
                "hara.changed", hara=slug, entity="hara_assessment", action="recompute", id=None, actor=actor
            )
        return {
            "rows": len(rows),
            "changed": changed,
            "not_found": not_found,
            "empty": empty,
            "vehicle_code": row.get("vehicle_code"),
            "ratings": len(index),
        }

    def hazard_summary(self, ref: Any) -> dict[str, Any]:
        """The Summary sheet, derived: per hazard H-n, the highest computed MPLr of its assessment rows in each
        context, the highest overall, the other standards' terms; beside them what the workbook typed (the
        cumulative hazard MPLr on each context's first row, the SG MPLr) and the highest stated MPLr."""
        row = self.resolve(ref)
        slug = row["slug"]
        hazards = self.hazards(row)
        constraints = self.constraints(row)
        assessments = _rows(self.brain, "hara_assessment", hara=slug)
        by_hazard: dict[str, dict[str, Any]] = {}
        for a in assessments:
            code = a.get("hazard") or split_event(a.get("event"))[0]
            if not code:
                continue
            entry = by_hazard.setdefault(
                code,
                {
                    "hazard": code,
                    "text": (hazards.get(code) or {}).get("text") or "",
                    "safety_goal": "",
                    "safety_goal_text": "",
                    "contexts": {c: "" for c in HARA_CONTEXTS},
                    "stated_contexts": {c: "" for c in HARA_CONTEXTS},
                    "typed_cumulative": {c: "" for c in HARA_CONTEXTS},
                    "typed_sg_mplr": "",
                    "rows": 0,
                    "_computed": {c: [] for c in HARA_CONTEXTS},
                    "_stated": {c: [] for c in HARA_CONTEXTS},
                },
            )
            context = a.get("context") or ""
            entry["rows"] += 1
            if context in entry["_computed"]:
                entry["_computed"][context].append(a.get("mplr"))
                entry["_stated"][context].append(a.get("stated_mplr"))
                if a.get("cumulative_mplr") and not entry["typed_cumulative"][context]:
                    entry["typed_cumulative"][context] = norm_mplr(a["cumulative_mplr"])
            if a.get("safety_goal") and not entry["safety_goal"]:
                entry["safety_goal"] = a["safety_goal"]
            if a.get("sg_mplr") and not entry["typed_sg_mplr"]:
                entry["typed_sg_mplr"] = norm_mplr(a["sg_mplr"])
        # hazards of step 1 without a single assessment row still have a line: the Summary lists every hazard
        for code, h in hazards.items():
            if "." in code or code in by_hazard:
                continue
            by_hazard[code] = {
                "hazard": code,
                "text": h.get("text") or "",
                "safety_goal": "",
                "safety_goal_text": "",
                "contexts": {c: "" for c in HARA_CONTEXTS},
                "stated_contexts": {c: "" for c in HARA_CONTEXTS},
                "typed_cumulative": {c: "" for c in HARA_CONTEXTS},
                "typed_sg_mplr": "",
                "rows": 0,
                "_computed": {c: [] for c in HARA_CONTEXTS},
                "_stated": {c: [] for c in HARA_CONTEXTS},
            }
        goals_by_hazard = {}
        for code, c in constraints.items():
            for line in str(c.get("note") or "").splitlines():
                if line.startswith("hazard:"):
                    goals_by_hazard.setdefault(line.split(":", 1)[1].strip(), code)
        lines = []
        for code in sorted(by_hazard, key=_hazard_key):
            entry = by_hazard[code]
            for context in HARA_CONTEXTS:
                entry["contexts"][context] = highest(entry["_computed"][context])
                entry["stated_contexts"][context] = highest(entry["_stated"][context])
            entry["mplr"] = highest(entry["contexts"].values())
            entry["stated_mplr"] = highest(entry["stated_contexts"].values())
            entry["typed_mplr"] = entry["typed_sg_mplr"] or highest(entry["typed_cumulative"].values())
            entry.update({k: v for k, v in equivalents(entry["mplr"]).items() if k != "mplr"})
            if not entry["safety_goal"]:
                entry["safety_goal"] = goals_by_hazard.get(code, "")
            goal = constraints.get(entry["safety_goal"]) if entry["safety_goal"] else None
            entry["safety_goal_text"] = (goal or {}).get("text") or ""
            entry["agrees"] = entry["mplr"] == entry["typed_mplr"] if entry["typed_mplr"] else None
            del entry["_computed"], entry["_stated"]
            lines.append(entry)
        return {
            "id": row["id"],
            "slug": slug,
            "name": row["name"],
            "vehicle_code": row.get("vehicle_code"),
            "contexts": list(HARA_CONTEXTS),
            "hazards": lines,
            "agree": sum(1 for e in lines if e["agrees"] is True),
            "differ": sum(1 for e in lines if e["agrees"] is False),
            "untyped": sum(1 for e in lines if e["agrees"] is None),
        }

    def check(self, ref: Any) -> dict[str, Any]:
        """Where the computed MPLr and the workbook's typed values differ: per context, how many rows agree
        with ``stated_mplr``, differ, have no key in the rating table, have no stated value; the first few
        differing rows as examples; and the hazard Summary's agreement. Nothing is written."""
        row = self.resolve(ref)
        slug = row["slug"]
        contexts: dict[str, dict[str, Any]] = {}
        for a in _rows(self.brain, "hara_assessment", hara=slug):
            c = contexts.setdefault(
                a.get("context") or "?",
                {"rows": 0, "agree": 0, "differ": 0, "not_found": 0, "unstated": 0, "examples": []},
            )
            c["rows"] += 1
            computed = a.get("mplr") or ""
            stated = norm_mplr(a.get("stated_mplr")) or (NOT_FOUND if (a.get("stated_mplr") or "") == NOT_FOUND else "")
            if computed == NOT_FOUND:
                c["not_found"] += 1
            if not stated:
                c["unstated"] += 1
                continue
            if computed == stated:
                c["agree"] += 1
            else:
                c["differ"] += 1
                if len(c["examples"]) < 5:
                    c["examples"].append(
                        {
                            "event": a.get("event"),
                            "function": a.get("function"),
                            "use_case": a.get("use_case"),
                            "failure_mode": a.get("failure_mode"),
                            "computed": computed,
                            "stated": stated,
                        }
                    )
        summary = self.hazard_summary(row)
        unknown = self.unknown_names(slug)
        return {
            "id": row["id"],
            "slug": slug,
            "name": row["name"],
            "vehicle_code": row.get("vehicle_code"),
            "contexts": contexts,
            "summary": {k: summary[k] for k in ("agree", "differ", "untyped")},
            "hazards_differing": [
                {"hazard": e["hazard"], "computed": e["mplr"], "typed": e["typed_mplr"]}
                for e in summary["hazards"]
                if e["agrees"] is False
            ],
            "unknown": unknown,
        }

    def unknown_names(self, slug: str) -> dict[str, list[str]]:
        """Functions, use cases and failure modes the assessment rows or the ratings use that the lists do not
        hold, and events the STPA analysis has no hazard for."""
        row = self.resolve(slug)
        functions = {norm_key(f["name"])[0] for f in _rows(self.brain, "hara_function", hara=slug)}
        use_cases = {norm_key(u["name"])[0] for u in _rows(self.brain, "hara_use_case", hara=slug)}
        modes = {norm_key(m["name"])[0] for m in _rows(self.brain, "hara_failure_mode", hara=slug)}
        hazards = set(self.hazards(row))
        out: dict[str, set[str]] = {"functions": set(), "use_cases": set(), "failure_modes": set(), "events": set()}
        for entity in ("hara_assessment", "hara_rating"):
            for r in _rows(self.brain, entity, hara=slug):
                for field, known, bucket in (
                    ("function", functions, "functions"),
                    ("use_case", use_cases, "use_cases"),
                    ("failure_mode", modes, "failure_modes"),
                ):
                    value = norm_key(r.get(field))[0]
                    if value and value not in known:
                        out[bucket].add(str(r.get(field)))
                if entity == "hara_assessment" and hazards and r.get("event") and r["event"] not in hazards:
                    out["events"].add(str(r["event"]))
        return {k: sorted(v) for k, v in out.items()}

    def validate(self, ref: Any) -> dict[str, Any]:
        """Every rule checked on the stored rows: errors (what the service would refuse) and warnings (names
        the lists do not hold, events the analysis has no hazard for, a vehicle code no vehicle row carries)."""
        row = self.resolve(ref)
        slug = row["slug"]
        errors: list[str] = []
        warnings: list[str] = []
        for entity, field in NAMED.items():
            seen: dict[tuple[str, ...], int] = {}
            for r in _rows(self.brain, entity, hara=slug):
                seen[norm_key(r.get(field))] = seen.get(norm_key(r.get(field)), 0) + 1
            for key, n in seen.items():
                if n > 1:
                    errors.append(f"{entity}: {key[0]!r} appears {n} times")
        keys: dict[tuple[str, ...], int] = {}
        for r in _rows(self.brain, "hara_rating", hara=slug):
            k = norm_key(r.get("function"), r.get("use_case"), r.get("failure_mode"))
            keys[k] = keys.get(k, 0) + 1
        for k, n in keys.items():
            if n > 1:
                errors.append(f"hara_rating: {' / '.join(k)} is rated {n} times")
        code = row.get("vehicle_code")
        letters = {v["letter"] for v in _rows(self.brain, "hara_vehicle", hara=slug)}
        if code and code != CUMULATIVE_CODE and letters and code not in letters:
            warnings.append(f"vehicle_code {code} is not a vehicle of the HARA (it has {', '.join(sorted(letters))})")
        if not code:
            warnings.append("no vehicle code: no MPLr is computed")
        if row.get("analysis") and not _rows(self.brain, "stpa_analysis", slug=row["analysis"]):
            errors.append(f"analysis: no STPA analysis has the slug {row['analysis']!r}")
        for bucket, names in self.unknown_names(slug).items():
            for name in names:
                warnings.append(f"{bucket}: {name!r} is used but not listed")
        return {
            "id": row["id"],
            "slug": slug,
            "name": row["name"],
            "counts": self.counts(slug),
            "ok": not errors,
            "errors": errors,
            "warnings": warnings,
        }


def _hazard_key(code: str) -> tuple[int, ...]:
    numbers = re.findall(r"\d+", code)
    return tuple(int(n) for n in numbers) if numbers else (10**6,)


def rating_value(rating: Mapping[str, Any], letter: str) -> str:
    """The MPLr a rating row holds under ``letter`` (or ``cumulative``), as a sheet prints it."""
    return HaraService.mplr_for(rating, letter)


__all__ = [
    "DATASET_KEYS",
    "HARA_ENTITY",
    "NOT_FOUND",
    "PART_ENTITIES",
    "HaraService",
    "equivalents",
    "highest",
    "list_of",
    "norm_key",
    "norm_mplr",
    "rating_value",
    "ratings_of",
    "split_event",
]
