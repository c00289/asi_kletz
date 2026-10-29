"""Brain: the in-process API that wires every layer together.

A ``Brain`` owns one database. Front ends (CLI today, GUI and local server later)
hold a Brain and call ``execute``; Python callers can also reach the services
directly through ``service(entity)``.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .automation.events import EventBus
from .commands import Dispatcher, Result
from .locks import guard
from .models import ModelFactory
from .repositories import RepositoryFactory
from .schema import LookupRegistry, SchemaRegistry, default_lookups, default_registry
from .schema.definitions import CADENCE_RULE, CAPACITY_RULE, DEFAULT_POINTS, SPRINT_CAPACITY, SPRINT_LENGTH
from .services import (
    ConfluenceService,
    EntityService,
    HolidayService,
    JiraService,
    PlanScheduleService,
    SprintService,
    StandardsService,
    TrackerService,
    TransferService,
    WorkProductService,
)
from .storage import StorageFactory
from .version import SCHEMA_VERSION, __version__

log = logging.getLogger(__name__)

DEFAULT_DB_NAME = "kletz.db"
DEFAULT_WORKBOOK_NAME = "kletz.xlsx"
DEFAULT_OUT_NAME = "out"
ENV_DB = "ASI_KLETZ_DB"
ENV_WORKBOOK = "ASI_KLETZ_WORKBOOK"
ENV_OUT = "ASI_KLETZ_OUT"
ENV_CONFIG = "ASI_KLETZ_CONFIG"
ENV_STANDARDS = "ASI_KLETZ_STANDARDS"
CONFIG_NAME = "kletz.toml"
DEFAULT_STANDARDS = "../asi_standards"  # the sibling repo of parametrised standards, beside this one
DEFAULT_EVIDENCE_NAME = "evidence"  # the Hopper page bundles `confluence evidence` writes (0.23.0), beside the database
CONFIG_KEYS = ("db", "workbook", "out", "standards_dir", "evidence_dir")  # file paths, resolved against the config file
CONFIG_TEXT_KEYS = (  # document metadata, the live JQL and the tracker's header lines, kept verbatim
    "doc_id", "project", "jira_live_jql", "tracker_title", "tracker_byline", "tracker_scope", "tracker_jira_scope",
)
CONFIG_BOOL_KEYS = ("jira_live_autofetch",)  # copied only when the TOML value is a real boolean; absent = false
CONFIG_INT_KEYS = ("default_points",)  # copied only when the TOML value is an integer
IGNORED_KEYS = {  # a key that was a setting once and is a rule now: ignored with a warning naming the rule
    "sprint_capacity": CAPACITY_RULE,  # 0.10.0: capacity is 8, fixed
    "sprint_days": CADENCE_RULE,  # 0.18.0: a sprint is 14 days, Tuesday to Monday, the owner's law of 2026-10-29
}
REVISION_FIELDS = ("rev", "date", "author", "description")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read ``kletz.toml``: the ``path`` given, else ``$ASI_KLETZ_CONFIG``, else ``./kletz.toml``.

    Keys ``db``, ``workbook`` and ``out`` are paths; a relative one resolves against the config
    file's own directory, so the workbook and the generated views can live in another folder.
    ``doc_id`` and ``project`` are the Safety Plan document's metadata and ``[[revision]]``
    tables are its revision history (``revisions``, a list of dicts in file order).
    ``jira_live_jql`` is the JQL of the JIRA Live Data window and ``jira_live_autofetch`` (a TOML
    boolean; a string is ignored so the default applies) whether its first show fetches. The
    default is ``False`` (``services.jira_service.AUTOFETCH_DEFAULT``): the window never connects
    to Jira unless the file says ``true`` or the engineer presses Refresh. ``tracker_title``,
    ``tracker_byline``, ``tracker_scope`` and ``tracker_jira_scope`` are the header lines of the Weekly
    Activity Tracker text. ``sprint_capacity`` is ignored since 0.10.0 (capacity is the rule, 8, fixed) and
    ``sprint_days`` since 0.18.0 (a sprint is 14 days, Tuesday to Monday, the owner's law of 2026-10-29): when
    present, ``warnings`` carries one line per key naming the rule.
    ``default_points`` (default 2) is the floor a Safety Plan row weighs when it has neither points nor the
    panel's default. ``standards_dir`` is the folder of parametrised standards (default ``../asi_standards``
    beside the config file). ``evidence_dir`` (0.23.0) is where ``confluence evidence`` writes its Hopper page
    bundles (default ``evidence/`` beside the database) and ``[confluence] space`` the space ``confluence
    search`` and the Find page window look in by default (``STPA``). Missing file: ``{}``.
    """
    import tomllib

    file = Path(path or os.environ.get(ENV_CONFIG) or Path.cwd() / CONFIG_NAME)
    if not file.is_file():
        return {}
    with file.open("rb") as handle:
        data = tomllib.load(handle)
    config: dict[str, Any] = {"path": str(file)}
    for key in CONFIG_KEYS:
        value = data.get(key)
        if value:
            value = Path(str(value)).expanduser()
            config[key] = str(value if value.is_absolute() else (file.parent / value).resolve())
    for key in CONFIG_TEXT_KEYS:
        value = data.get(key)
        if value:
            config[key] = str(value).strip()
    for key in CONFIG_BOOL_KEYS:
        value = data.get(key)
        if isinstance(value, bool):
            config[key] = value
    for key in CONFIG_INT_KEYS:
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            config[key] = value
    for key, rule in IGNORED_KEYS.items():
        if key in data:
            config.setdefault("warnings", []).append(f"{key} = {data[key]!r} in kletz.toml is ignored: {rule}")
    revisions = data.get("revision")
    if isinstance(revisions, list):
        config["revisions"] = [
            {field: str(item.get(field, "")).strip() for field in REVISION_FIELDS}
            for item in revisions
            if isinstance(item, dict)
        ]
    # 0.22.0: ``[urls] hosts = {jama = "jama.example.com", dms = ["dms.example.com", "*.dms.example.org"]}``
    # names more URL kinds than the built-in five (schema/urls.py); a value that is not a host or a list of
    # hosts is ignored with a warning. Optional, and not asked for: the plan's "so a pasted link is not mislabelled".
    urls = data.get("urls")
    if isinstance(urls, dict) and isinstance(urls.get("hosts"), dict):
        hosts: dict[str, list[str]] = {}
        for name, value in urls["hosts"].items():
            values = value if isinstance(value, list) else [value]
            if values and all(isinstance(v, str) and v.strip() for v in values):
                hosts[str(name).strip().lower()] = [v.strip() for v in values]
            else:
                config.setdefault("warnings", []).append(
                    f"[urls] hosts.{name} = {value!r} in kletz.toml is ignored: write a host or a list of hosts"
                )
        config["url_hosts"] = hosts
    # 0.23.0: ``[confluence] space = "STPA"``, the space `confluence search` and the Find page window look in
    # when none is given; a value that is not text is ignored with a warning
    confluence = data.get("confluence")
    if isinstance(confluence, dict) and "space" in confluence:
        space = confluence["space"]
        if isinstance(space, str) and space.strip():
            config["confluence_space"] = space.strip().upper()
        else:
            config.setdefault("warnings", []).append(
                f"[confluence] space = {space!r} in kletz.toml is ignored: write a space key such as \"STPA\""
            )
    return config


def resolve_db_path(db_path: str | Path | None, config: dict[str, Any] | None = None) -> str:
    """Explicit argument, else ``$ASI_KLETZ_DB``, else ``db`` in kletz.toml, else ./kletz.db."""
    if db_path is not None:
        return str(db_path)
    config = load_config() if config is None else config
    return os.environ.get(ENV_DB) or config.get("db") or str(Path.cwd() / DEFAULT_DB_NAME)


def resolve_out_dir(out_dir: str | Path | None, db_path: str, config: dict[str, Any]) -> str:
    """Explicit argument, else ``$ASI_KLETZ_OUT``, else ``out`` in kletz.toml, else ``out/`` next to the database."""
    if out_dir is not None:
        return str(out_dir)
    if os.environ.get(ENV_OUT):
        return os.environ[ENV_OUT]
    if config.get("out"):
        return str(config["out"])
    if db_path == ":memory:":
        return str(Path.cwd() / DEFAULT_OUT_NAME)
    return str(Path(db_path).with_name(DEFAULT_OUT_NAME))


class Brain:
    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        registry: SchemaRegistry | None = None,
        lookups: LookupRegistry | None = None,
        backend: str = "sqlite",
        workbook_path: str | Path | None = None,
        out_dir: str | Path | None = None,
        wait: float = 0.0,
        standards_dir: str | Path | None = None,
    ) -> None:
        """Open the database at ``db_path`` after taking the family lock.

        ``wait`` is how many seconds to queue for the slot (polling every 250 ms) before
        ``PrimaryToolBusy`` is raised; the default refuses at once. A refused Brain never opens
        the SQLite file.
        """
        from .schema import definitions  # noqa: F401  (registers the built-in entities)

        self.registry = registry or default_registry
        self.lookups = lookups or default_lookups
        self.config = load_config()
        self.db_path = resolve_db_path(db_path, self.config)
        self._slot_held = False
        guard.acquire(self.db_path, wait)  # raises PrimaryToolBusy; the family slot first, then this database
        self._slot_held = True
        try:
            self.storage = StorageFactory.create(backend, path=self.db_path)
        except BaseException:
            guard.release(self.db_path)
            self._slot_held = False
            raise
        self.migration = self.storage.ensure_schema(self.registry)
        self.migration["uids_stamped"] = self.storage.stamp_uids(self.registry)  # a 0.8.x file opens as 0.9.0
        self.events = EventBus()
        self.models = ModelFactory(self.registry)
        self.repositories = RepositoryFactory(self.storage, self.registry)
        self._services: dict[str, EntityService] = {}
        self.sprints = SprintService(self)  # the agile rules: eight points a sprint, close and carry, the planner
        self.schedule = PlanScheduleService(self)  # the plan's calculated sprint and deadline, kept current
        self.standards = StandardsService(self)  # the parametrised standards a plan row is exported into
        self.work_products = WorkProductService(self)  # the work product URLs of a plan row (0.20.0)
        self._standards_dir = str(standards_dir) if standards_dir is not None else None
        self.transfer = TransferService(self)
        self.jira = JiraService(self)  # read only; asi_hopper is imported when a jira verb runs, never here
        self.confluence = ConfluenceService(self)  # read only too (0.23.0); the same lazy import rule
        self.tracker = TrackerService(self)  # the Weekly Activity Tracker text, in and out
        self.holidays = HolidayService(self)  # the holidays the planner skips, loaded from a JSON list
        self.dispatcher = Dispatcher(self)
        self.config_warnings: list[str] = list(self.config.get("warnings", []))
        for warning in self.config_warnings:
            log.warning("%s", warning)
        # the capacity rule: every sprint that is not Closed is 8 points, set here the first time a database
        # written before the rule is opened (audited once with the count), nothing on a database that follows it
        self.migration["capacity_enforced"] = self.sprints.enforce_capacity()
        # 0.13.0: an item written before the plan_uid column points at its plan row by uid too
        self.migration["plan_uids_filled"] = self.sprints.fill_plan_uids()
        # the plan's floor (kletz.toml) must be known before the first recompute below
        self.default_points: int = int(self.config.get("default_points") or DEFAULT_POINTS)
        # the calculated sprint and deadline of every plan row, written where they moved (a database written
        # before 0.11.0 gets them here for the first time)
        self.migration["scheduled"] = self.schedule.recompute()["changed"]
        if workbook_path is not None:
            self.workbook_path = str(workbook_path)
        elif os.environ.get(ENV_WORKBOOK):
            self.workbook_path = os.environ[ENV_WORKBOOK]
        elif self.config.get("workbook"):
            self.workbook_path = self.config["workbook"]
        elif self.db_path == ":memory:":
            self.workbook_path = DEFAULT_WORKBOOK_NAME
        else:
            self.workbook_path = str(Path(self.db_path).with_name(DEFAULT_WORKBOOK_NAME))
        # generated views (diagrams, documents) and the Safety Plan document's metadata
        self.out_dir = resolve_out_dir(out_dir, self.db_path, self.config)
        self.doc_id: str = self.config.get("doc_id", "")
        self.project: str = self.config.get("project", "")
        self.revisions: list[dict[str, str]] = [dict(r) for r in self.config.get("revisions", [])]
        # 0.22.0: the owner's extra URL kinds (``[urls] hosts`` in kletz.toml), read by ``url_kind`` wherever a
        # URL is labelled: the export's Work product cell, the form's link lines, ``plan urls --audit``
        self.url_hosts: dict[str, list[str]] = {k: list(v) for k, v in self.config.get("url_hosts", {}).items()}
        # 0.23.0: the space `confluence search` looks in when none is given (``[confluence] space``, else STPA)
        self.confluence_space: str = str(self.config.get("confluence_space") or "")
        # the capacity and the length are the rules (fixed, never from the config): 8 points, 14 days
        self.sprint_capacity: int = SPRINT_CAPACITY
        self.sprint_length: int = SPRINT_LENGTH

    @property
    def standards_dir(self) -> str:
        """The folder of parametrised standards: the argument, else ``$ASI_KLETZ_STANDARDS``, else
        ``standards_dir`` in kletz.toml, else ``../asi_standards`` beside the config file (or the working
        directory when there is none). Read when asked, so a test can point it elsewhere after opening."""
        if self._standards_dir is not None:
            return self._standards_dir
        if os.environ.get(ENV_STANDARDS):
            return os.environ[ENV_STANDARDS]
        if self.config.get("standards_dir"):
            return str(self.config["standards_dir"])
        base = Path(self.config["path"]).parent if self.config.get("path") else Path.cwd()
        return str((base / DEFAULT_STANDARDS).resolve())

    @property
    def evidence_dir(self) -> str:
        """Where ``confluence evidence`` writes its Hopper page bundles (0.23.0): ``evidence_dir`` in kletz.toml
        (resolved against the file), else ``evidence/`` beside the database (the working directory for
        ``:memory:``). Created by the first bundle, never here."""
        if self.config.get("evidence_dir"):
            return str(self.config["evidence_dir"])
        if self.db_path == ":memory:":
            return str(Path.cwd() / DEFAULT_EVIDENCE_NAME)
        return str(Path(self.db_path).with_name(DEFAULT_EVIDENCE_NAME))

    # -- access ---------------------------------------------------------
    def service(self, entity: str) -> EntityService:
        schema = self.registry.get(entity)
        if schema.name not in self._services:
            service = EntityService(
                schema, self.repositories.for_entity(schema), self.storage, self.lookups, self.events
            )
            if schema.name == "sprint":
                service.guard = self.sprints.guard  # the capacity rule on every create and update of a sprint
            if schema.name == "safety_plan_row":
                # the calculated fields and the panel's default stay out; the urls parsed, in order (0.20.0)
                service.guard = self._plan_guard
                service.on_load = self.work_products.loaded  # a file's urls parsed; `no ticket attached` is no key
            if schema.name == "parameter":
                service.guard = self.standards.parameter_guard  # a name once per standard; a role holds people
                service.on_load = self.standards.parameter_loaded  # a file's people parsed, validated, sorted
            if schema.name == "sprint_item":
                service.guard = self.sprints.link_item  # plan_row and plan_uid name the same row; the uid wins
                service.on_load = self.sprints.link_loaded  # a file's plan_uid re-resolves plan_row
            if schema.name in ("safety_plan_row", "sprint", "sprint_item"):
                service.after = self.schedule.on_change  # a change here can move a deadline
            self._services[schema.name] = service
        return self._services[schema.name]

    def _plan_guard(self, current: dict[str, Any] | None, clean: dict[str, Any]) -> list[str]:
        """The plan row's rules, in order: the schedule's (calculated fields, defaults, points), then the
        work product's (urls, the no-ticket text)."""
        warnings = list(self.schedule.guard(current, clean) or ())
        warnings.extend(self.work_products.guard(current, clean) or ())
        return warnings

    def execute(
        self, verb: str, args: dict[str, Any] | None = None, *, actor: str = "python", **kwargs: Any
    ) -> Result:
        """Run a command.

        ``brain.execute("get", {"entity": "safety_plan_row", "id": 1})`` and
        ``brain.execute("get", entity="safety_plan_row", id=1)`` are the same call.
        """
        merged = dict(args or {})
        merged.update(kwargs)
        return self.dispatcher.execute(verb, merged, actor)

    def execute_dict(self, payload: dict[str, Any], actor: str | None = None) -> Result:
        return self.dispatcher.execute_dict(payload, actor)

    def status(self) -> dict[str, Any]:
        locks = guard.describe(self.db_path)
        return {
            "app_version": __version__,
            "schema_version": SCHEMA_VERSION,
            "database": self.storage.describe(),
            "workbook_path": self.workbook_path,
            "out_dir": self.out_dir,
            "doc_id": self.doc_id,
            "project": self.project,
            "revisions": [dict(r) for r in self.revisions],
            "sprint_capacity": self.sprint_capacity,
            "sprint_length_days": self.sprint_length,
            "default_points": self.default_points,
            "standards_dir": self.standards_dir,
            "evidence_dir": self.evidence_dir,
            "confluence_space": self.confluence.space,
            "config_warnings": list(self.config_warnings),
            "tracker": {"title": self.tracker.title, "byline": self.tracker.byline, "scope": self.tracker.scope},
            "config_path": self.config.get("path"),
            "lock_dir": locks["lock_dir"],
            "locks": {"family": locks["family"], "database": locks["database"]},
            "entities": {s.name: self.service(s.name).count() for s in self.registry},
            "commands": self.dispatcher.factory.verbs(),
            "recent_audit": self.storage.audit_tail(5),
            "recent_events": self.events.last(5),
        }

    def close(self) -> None:
        """Close the storage and drop this Brain's hold on the slots. Idempotent."""
        if self._slot_held:
            try:
                self.storage.close()
            finally:
                self._slot_held = False
                guard.release(self.db_path)

    def __enter__(self) -> Brain:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"Brain(db_path={self.db_path!r}, entities={len(self.registry)})"
