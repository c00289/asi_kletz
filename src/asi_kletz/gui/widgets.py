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
        if spec.type is FieldType.INT:
            options.setdefault("width", 10)
        return self._registry[spec.type](master, spec, self.lookups, **options)
