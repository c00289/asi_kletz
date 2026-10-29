"""WidgetFactory: field type -> form widget. Every widget exposes get/set/clear/focus_field."""

from __future__ import annotations

import datetime as dt
import tkinter as tk
import webbrowser
from tkinter import ttk
from typing import Any, ClassVar

from ..schema import FieldSpec, FieldType, LookupRegistry


class FieldWidget(ttk.Frame):
    """A form control for one field. Subclasses implement build/get/set."""

    def __init__(self, master: tk.Misc, spec: FieldSpec, lookups: LookupRegistry, **options: Any) -> None:
        super().__init__(master)
        self.spec = spec
        self.lookups = lookups
        self.options = options
        self.build()

    def build(self) -> None:
        raise NotImplementedError

    def get(self) -> Any:
        raise NotImplementedError

    def set(self, value: Any) -> None:
        raise NotImplementedError

    def clear(self) -> None:
        self.set(None)

    def focus_field(self) -> None:
        self.focus_set()


class EntryWidget(FieldWidget):
    def build(self) -> None:
        self.var = tk.StringVar()
        self.entry = ttk.Entry(self, textvariable=self.var, width=self.options.get("width", 40))
        self.entry.pack(side="left", fill="x", expand=True)

    def get(self) -> Any:
        text = self.var.get().strip()
        return text or None

    def set(self, value: Any) -> None:
        self.var.set("" if value is None else str(value))

    def focus_field(self) -> None:
        self.entry.focus_set()


class MultilineWidget(FieldWidget):
    def build(self) -> None:
        self.text = tk.Text(
            self, height=self.options.get("height", 4), width=self.options.get("width", 60), wrap="word"
        )
        bar = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=bar.set)
        self.text.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")

    def get(self) -> Any:
        text = self.text.get("1.0", "end-1c").strip()
        return text or None

    def set(self, value: Any) -> None:
        self.text.delete("1.0", "end")
        if value is not None:
            self.text.insert("1.0", str(value))

    def focus_field(self) -> None:
        self.text.focus_set()


class BoolWidget(FieldWidget):
    def build(self) -> None:
        self.var = tk.BooleanVar(value=False)
        text = self.spec.header if self.options.get("show_label", True) else ""
        self.check = ttk.Checkbutton(self, text=text, variable=self.var)
        self.check.pack(side="left", anchor="w")

    def get(self) -> bool:
        return bool(self.var.get())

    def set(self, value: Any) -> None:
        self.var.set(bool(value))

    def focus_field(self) -> None:
        self.check.focus_set()


class DateWidget(EntryWidget):
    def build(self) -> None:
        self.options.setdefault("width", 14)
        super().build()
        ttk.Button(self, text="Today", width=6, command=self.today).pack(side="left", padx=(4, 0))
        ttk.Label(self, text="YYYY-MM-DD", style="Muted.TLabel").pack(side="left", padx=(6, 0))

    def today(self) -> None:
        self.set(dt.date.today().isoformat())


class UrlWidget(EntryWidget):
    def build(self) -> None:
        self.options.setdefault("width", 50)
        super().build()
        ttk.Button(self, text="Open", width=6, command=self.open).pack(side="left", padx=(4, 0))

    def open(self) -> None:
        url = self.get()
        if url:
            webbrowser.open(url)


class ReadOnlyWidget(EntryWidget):
    """An entry in state ``readonly``: a calculated field or a loader's, shown so it can be selected and
    copied, never typed into; the form never sends it (``EntityScreen.form_data``)."""

    def build(self) -> None:
        if self.spec.type is FieldType.INT:
            self.options.setdefault("width", 10)
        super().build()
        self.entry.configure(state="readonly")


PLACEHOLDER_COLOUR = "grey55"


class PointsWidget(EntryWidget):
    """The Points entry (owner, 2026-10-28): the row's default greyed as a placeholder while empty; the moment the
    typed value differs from the default a caption beside it says ``default 3``; clearing the entry returns to
    the default (``get()`` is ``None``). ``set_default`` hands it the row's default before ``set``."""

    def build(self) -> None:
        self.options.setdefault("width", 10)
        super().build()
        self.default: int | None = None
        self.showing_placeholder = False
        self.caption_var = tk.StringVar()
        self.caption = ttk.Label(self, textvariable=self.caption_var, style="Muted.TLabel")
        self.caption.pack(side="left", padx=(6, 0))
        self.entry.bind("<FocusIn>", lambda e: self._hide_placeholder(), add="+")
        self.entry.bind("<FocusOut>", lambda e: self._show_placeholder_if_empty(), add="+")
        self.var.trace_add("write", lambda *_: self._refresh_caption())

    def set_default(self, value: Any) -> None:
        """The number the placeholder and the caption name; ``None`` when there is none."""
        self.default = int(value) if value not in (None, "") else None
        self._show_placeholder_if_empty()
        self._refresh_caption()

    def _show_placeholder_if_empty(self) -> None:
        if self.default is not None and not self.showing_placeholder and not self.var.get().strip():
            self.showing_placeholder = True
            self.var.set(str(self.default))
            self.entry.configure(foreground=PLACEHOLDER_COLOUR)

    def _hide_placeholder(self) -> None:
        if self.showing_placeholder:
            self.showing_placeholder = False
            self.var.set("")
            self.entry.configure(foreground="")

    def get(self) -> Any:
        if self.showing_placeholder:
            return None
        text = self.var.get().strip()
        return text or None

    def set(self, value: Any) -> None:
        self._hide_placeholder()
        self.var.set("" if value is None else str(value))
        self._show_placeholder_if_empty()
        self._refresh_caption()

    def _refresh_caption(self) -> None:
        typed = self.get()
        if self.default is not None and typed is not None and typed != str(self.default):
            self.caption_var.set(f"default {self.default}")
        else:
            self.caption_var.set("")


LOAD_TICKETS = "Load tickets"
NOT_IN_LIST = "not in the fetched list"


class JiraPickerWidget(FieldWidget):
    """The Jira ticket picker (owner, 2026-10-29: "for every work product allow the user to select a Jira
    ticket"): a combobox whose list is the issues of the window's last JIRA Live Data fetch, shown as
    ``HWL-2554  Perform Platform Safety Plan``; typing filters the list on key or summary; picking one stores
    the key alone; the entry stays free text, so a key not in the list can still be typed; a cleared box
    clears the key. ``Load tickets`` beside it runs the live screen's fetch (``options["load"]``); after a
    fetch the status of the picked ticket shows beside the box, read from the fetched rows, nothing stored."""

    def build(self) -> None:
        self.var = tk.StringVar()
        self.issues: list[dict[str, Any]] = []
        self.combo = ttk.Combobox(self, textvariable=self.var, width=self.options.get("width", 44), values=[])
        self.combo.pack(side="left", fill="x", expand=True)
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.picked())
        self.combo.bind("<KeyRelease>", lambda e: self.filter(self.var.get()))
        self.load_button = ttk.Button(self, text=LOAD_TICKETS, command=self._load)
        self.load_button.pack(side="left", padx=(4, 0))
        self.status_var = tk.StringVar()
        ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel").pack(side="left", padx=(6, 0))
        self.var.trace_add("write", lambda *_: self.refresh_status())

    def _load(self) -> None:
        load = self.options.get("load")
        if load is not None:
            load()

    @staticmethod
    def label(issue: dict[str, Any]) -> str:
        return f"{issue['key']}  {issue.get('summary') or ''}".rstrip()

    def set_issues(self, issues: list[dict[str, Any]]) -> None:
        """The fetched rows (``key``, ``summary``, ``status``); the list and the status follow."""
        self.issues = [i for i in issues if i.get("key")]
        self.filter("")  # the whole list: typing narrows it, a key already in the box does not hide it
        self.refresh_status()

    def filter(self, text: str) -> list[str]:
        """The list narrowed to the issues whose key or summary contains ``text`` (case-insensitive)."""
        needle = (text or "").strip().casefold()
        shown = [
            i for i in self.issues
            if not needle or needle in str(i["key"]).casefold() or needle in str(i.get("summary") or "").casefold()
        ]
        if not shown and needle:  # a picked label (key + summary) narrows to its own issue
            shown = [i for i in self.issues if self.label(i).casefold() == needle]
        values = [self.label(i) for i in shown]
        self.combo["values"] = values
        return values

    def picked(self) -> None:
        """A pick from the list: the key alone stays in the box."""
        text = self.var.get().strip()
        if text:
            self.var.set(text.split()[0].upper())

    def get(self) -> Any:
        text = self.var.get().strip()
        if not text:
            return None
        for issue in self.issues:
            if text.casefold() == self.label(issue).casefold():
                return str(issue["key"])
        return text.split()[0].upper() if " " not in text else text

    def set(self, value: Any) -> None:
        self.var.set("" if value is None else str(value))

    def refresh_status(self) -> None:
        key = (self.get() or "").upper()
        issue = next((i for i in self.issues if str(i["key"]).upper() == key), None)
        if issue is not None:
            self.status_var.set(str(issue.get("status") or ""))
        elif key and self.issues:
            self.status_var.set(NOT_IN_LIST)
        else:
            self.status_var.set("")

    def focus_field(self) -> None:
        self.combo.focus_set()


PEOPLE_HINT = "one per line: Name <email>"
NOT_A_ROLE = "not a role: the Value holds the text"
LOOK_UP = "Look up"


def append_line(text: tk.Text, line: str) -> None:
    """``line`` on a line of its own at the end of ``text`` (a disabled box is opened for the write)."""
    state = str(text.cget("state"))
    text.configure(state="normal")
    try:
        current = text.get("1.0", "end-1c")
        if current and not current.endswith("\n"):
            text.insert("end", "\n")
        text.insert("end", line)
    finally:
        text.configure(state=state)


class PeopleWidget(MultilineWidget):
    """The people of a role (0.19.0, the owner: "an array of human names sorted alphabetically ... must include
    email alongside name"): a small text box, one person per line as ``Name <email>``, with the hint beside it.
    ``get()`` is the typed text (the verb's guard parses, validates and sorts it; an error names the role and
    the line); ``set()`` takes the stored array and shows it one line per person. ``set_enabled(False)`` greys
    the box for a parameter that is not a role (the Parameters screen: the Value entry holds its text).
    0.20.0: a **Look up** button beside it (``options["lookup"]``, the screen's Outlook search; the picked
    ``Name <email>`` line lands through ``insert_line``)."""

    def build(self) -> None:
        self.options.setdefault("height", 3)
        self.options.setdefault("width", 48)
        super().build()
        side = ttk.Frame(self)
        side.pack(side="left", anchor="n", padx=(6, 0))
        self.hint_var = tk.StringVar(value=PEOPLE_HINT)
        self.hint = ttk.Label(side, textvariable=self.hint_var, style="Muted.TLabel")
        self.hint.pack(anchor="w")
        self.lookup_button: ttk.Button | None = None
        if self.options.get("lookup") is not None:
            self.lookup_button = ttk.Button(side, text=LOOK_UP, command=self.look_up)
            self.lookup_button.pack(anchor="w", pady=(4, 0))
        self.enabled = True

    def look_up(self) -> Any:
        """The Outlook search (0.20.0): the screen opens it; the pick is appended as a line."""
        lookup = self.options.get("lookup")
        return lookup(self.insert_line) if lookup is not None and self.enabled else None

    def insert_line(self, line: str) -> None:
        append_line(self.text, line)

    def set(self, value: Any) -> None:
        from ..schema.people import people_lines

        enabled = self.enabled
        self.set_enabled(True)
        super().set(people_lines(value) if isinstance(value, (list, tuple)) else value)
        self.set_enabled(enabled)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.text.configure(state="normal" if enabled else "disabled")
        self.hint_var.set(PEOPLE_HINT if enabled else NOT_A_ROLE)
        if self.lookup_button is not None:
            self.lookup_button.state(["!disabled"] if enabled else ["disabled"])


URLS_HINT = "one per line, http(s); the first is the link"
THE_LINK = " (the link)"
OPEN = "Open"
FIND_PAGE = "Find page"
NO_SESSION_HINT = "Find page needs an Atlassian session: run `asi-hopper auth login` once"


def link_text(url: str, index: int = 1, hosts: dict[str, Any] | None = None) -> str:
    """One link line of the URLs editor: the kind as a prefix (0.22.0), the URL, and ``(the link)`` on the
    first: ``confluence: https://asirobots.atlassian.net/wiki/... (the link)``."""
    from ..schema.urls import url_kind

    return f"{url_kind(url, hosts)}: {url}" + (THE_LINK if index == 0 else "")


class UrlsWidget(MultilineWidget):
    """The work product URLs of a deliverable (0.20.0, the owner: "each deliverable may have multiple url...
    on multiple urls just go to first; list of urls is sequential"): a small text box, one URL per line, in
    the order typed (the verb's guard validates: absolute http(s), none twice; it never sorts), and beside it
    the links as clickable text, one per line, each prefixed with its kind (0.22.0: ``confluence``, ``jira``,
    ``sharepoint``, ``placeholder``, ``other`` or a kind of kletz.toml's ``[urls] hosts``, handed in as
    ``hosts``), the first marked as the link, with an **Open** button that launches the first in the browser; a
    click (left or right) on any line launches that one. 0.23.0: a **Find page** button beside Open
    (``options["find"]``, the screen's Confluence search; the picked page URL lands through ``insert_url``),
    greyed when Hopper has no Atlassian session (``options["find_enabled"]``)."""

    def build(self) -> None:
        self.options.setdefault("height", 3)
        self.options.setdefault("width", 56)
        self.hosts: dict[str, Any] = dict(self.options.pop("hosts", None) or {})
        super().build()
        self.side = ttk.Frame(self)
        self.side.pack(side="left", anchor="n", padx=(6, 0))
        head = ttk.Frame(self.side)
        head.pack(anchor="w")
        self.open_button = ttk.Button(head, text=OPEN, width=6, command=self.open_first, state="disabled")
        self.open_button.pack(side="left")
        self.find_button: ttk.Button | None = None
        self.find_enabled = bool(self.options.get("find_enabled", True))
        if self.options.get("find") is not None:
            self.find_button = ttk.Button(head, text=FIND_PAGE, command=self.find_page)
            self.find_button.pack(side="left", padx=(4, 0))
            self.find_button.state(["!disabled"] if self.find_enabled else ["disabled"])
        ttk.Label(head, text=URLS_HINT, style="Muted.TLabel").pack(side="left", padx=(6, 0))
        self.links_box = ttk.Frame(self.side)
        self.links_box.pack(anchor="w", pady=(2, 0))
        self.link_labels: list[ttk.Label] = []
        self.text.bind("<KeyRelease>", lambda e: self.refresh_links(), add="+")
        self.text.bind("<FocusOut>", lambda e: self.refresh_links(), add="+")

    def urls(self) -> list[str]:
        """The lines of the box that look like URLs, in order (what the links show; the guard has the last word)."""
        from ..schema.urls import is_url

        text = self.text.get("1.0", "end-1c")
        return [line.strip() for line in text.replace(";", "\n").splitlines() if is_url(line.strip())]

    def refresh_links(self) -> list[str]:
        for label in self.link_labels:
            label.destroy()
        self.link_labels = []
        urls = self.urls()
        for index, url in enumerate(urls):
            label = ttk.Label(self.links_box, text=link_text(url, index, self.hosts), style="Link.TLabel",
                              cursor="hand2")
            label.pack(anchor="w")
            label.bind("<Button-1>", lambda e, u=url: self.open_url(u))
            label.bind("<Button-3>", lambda e, u=url: self.open_url(u))
            self.link_labels.append(label)
        self.open_button.configure(state="normal" if urls else "disabled")
        return urls

    def open_first(self) -> str | None:
        urls = self.urls()
        if not urls:
            return None
        self.open_url(urls[0])
        return urls[0]

    def find_page(self) -> Any:
        """Find page (0.23.0): the screen opens the Confluence search; the pick is appended as a line. Nothing
        when Hopper has no session (the button is greyed; the hint says what to run)."""
        find = self.options.get("find")
        if find is None or not self.find_enabled:
            return None
        return find(self.insert_url)

    def insert_url(self, url: str) -> list[str]:
        """``url`` on a line of its own at the end of the box; the links follow."""
        append_line(self.text, url)
        return self.refresh_links()

    @staticmethod
    def open_url(url: str) -> None:
        webbrowser.open(url)

    def set(self, value: Any) -> None:
        from ..schema.urls import urls_lines

        super().set(urls_lines(value) if isinstance(value, (list, tuple)) else value)
        self.refresh_links()


class EnumWidget(FieldWidget):
    def build(self) -> None:
        self.var = tk.StringVar()
        values = list(self.lookups.get(self.spec.lookup or "", ()))
        self.combo = ttk.Combobox(self, textvariable=self.var, values=values, width=self.options.get("width", 30))
        self.combo.pack(side="left", fill="x", expand=True)

    def get(self) -> Any:
        text = self.var.get().strip()
        return text or None

    def set(self, value: Any) -> None:
        self.var.set("" if value is None else str(value))

    def focus_field(self) -> None:
        self.combo.focus_set()


class WidgetFactory:
    """Produces the right widget for a field type; new types are added by registration."""

    _registry: ClassVar[dict[FieldType, type[FieldWidget]]] = {
        FieldType.TEXT: EntryWidget,
        FieldType.INT: EntryWidget,
        FieldType.MULTILINE: MultilineWidget,
        FieldType.BOOL: BoolWidget,
        FieldType.DATE: DateWidget,
        FieldType.URL: UrlWidget,
        FieldType.ENUM: EnumWidget,
        FieldType.JSON: MultilineWidget,  # the JSON text as typed; a field with picker="people" gets PeopleWidget
    }

    def __init__(self, lookups: LookupRegistry) -> None:
        self.lookups = lookups

    @classmethod
    def register(cls, field_type: FieldType, widget: type[FieldWidget]) -> type[FieldWidget]:
        cls._registry[field_type] = widget
        return widget

    def create(self, master: tk.Misc, spec: FieldSpec, **options: Any) -> FieldWidget:
        if spec.hidden:  # a hidden field (the uid) has no widget: the form skips it, a caller asking for one is wrong
            raise ValueError(f"field {spec.name!r} is hidden and has no widget")
        if spec.calculated or spec.readonly:  # shown, copyable, never typed into
            return ReadOnlyWidget(master, spec, self.lookups, **options)
        if spec.default_from:  # the Points entry: the default as a placeholder, a caption when the value differs
            return PointsWidget(master, spec, self.lookups, **options)
        if spec.picker == "jira":  # a ticket picked from the last live fetch; `load` runs the fetch
            return JiraPickerWidget(master, spec, self.lookups, **options)
        if spec.picker == "people":  # a role's people, one per line (0.19.0); `lookup` opens the Outlook search
            return PeopleWidget(master, spec, self.lookups, **options)
        if spec.picker == "urls":  # the work product URLs, one per line, the first the link (0.20.0)
            return UrlsWidget(master, spec, self.lookups, **options)
        if spec.type is FieldType.INT:
            options.setdefault("width", 10)
        return self._registry[spec.type](master, spec, self.lookups, **options)
