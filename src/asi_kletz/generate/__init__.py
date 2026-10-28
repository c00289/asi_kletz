"""Generated views of the Safety Plan: diagrams through asi_escher, documents through asi_gutenberg.

Like the workbook, every file produced here is a *view* regenerated from the database and
never read back. Diagrams and documents are added by registration::

    from asi_kletz.generate import Spec, Param, register_diagram

    @register_diagram(Spec("my_view", "My view", "What it shows", params=(Param("phase", required=True),)))
    def my_view(brain, params, ctx):
        ...

Importing this package registers the built-in catalogs but imports no generator library;
asi_escher and asi_gutenberg (and with them matplotlib and reportlab) load only when a
builder runs.
"""

from . import diagrams, documents  # noqa: E402, F401  (registers the built-in catalogs)
from .base import (
    BuildContext,
    DiagramFactory,
    DocumentFactory,
    GeneratorFactory,
    Param,
    Spec,
    check_params,
    register_diagram,
    register_document,
)

__all__ = [
    "BuildContext",
    "DiagramFactory",
    "DocumentFactory",
    "GeneratorFactory",
    "Param",
    "Spec",
    "check_params",
    "register_diagram",
    "register_document",
]
