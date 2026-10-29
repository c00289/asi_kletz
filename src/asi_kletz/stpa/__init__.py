"""STPA: control structures and the step objects read from a Confluence page (0.24.0, from the sister tool).

``ControlStructureFactory`` (``brain.factory``; docs/control-structure-plan.md) builds a structure
several ways (``blank``, ``template:wheel_loader_master``, ``from_drawio``, ``from_datasets``,
``clone``) and is the one place that turns the rows into an ``asi_escher.Diagram`` (``to_diagram``)
and writes the files (``export``). ``drawio_reader.read_drawio`` parses a draw.io file into the plain
dataset the factory loads, standard library only, as the script it was ported from.

``StpaFactory`` (``brain.stpa_factory``; asi_hopper/docs/confluence-integration-plan.md, section 7)
builds an STPA analysis (``blank``, ``from_bundle``, ``from_confluence``, ``clone``) and exports it;
``confluence_reader.read_stpa_page`` turns the Markdown body of an STPA page into the dataset of
losses, hazards, UCAs, scenarios and constraints, over asi_hopper's page anatomy.
"""

from .drawio_reader import read_dataset_folder, read_drawio
from .factory import FORMATS, Builder, ControlStructureFactory, register_builder
from .stpa_factory import StpaFactory, read_bundle, register_stpa_builder

# ``confluence_reader`` is imported where it is used: it stands on asi_hopper's page anatomy, and
# ``import asi_kletz`` (and the window's start-up) never loads asi_hopper
__all__ = [
    "FORMATS",
    "Builder",
    "ControlStructureFactory",
    "StpaFactory",
    "read_bundle",
    "read_dataset_folder",
    "read_drawio",
    "register_builder",
    "register_stpa_builder",
]
