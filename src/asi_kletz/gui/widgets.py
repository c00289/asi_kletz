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
        if spec.type is FieldType.INT:
            options.setdefault("width", 10)
        return self._registry[spec.type](master, spec, self.lookups, **options)
