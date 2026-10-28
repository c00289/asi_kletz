"""ASI Kletz: a schema-driven functional-safety safety-plan API.

The package is a FuSa API first and a set of front ends second. Everything a
front end can do goes through the same command path (see ``asi_kletz.commands``),
so a human at a CLI, a Python caller, or an AI agent all drive the same core.

Quick start::

    from asi_kletz import Brain

    with Brain("kletz.db") as brain:
        result = brain.execute("create", {"entity": "safety_plan_row",
                                          "data": {"deliverable": "Safety Plan", "status": "Ongoing"}})
        print(result.to_json())
"""

from .version import SCHEMA_VERSION, __version__

__all__ = ["Brain", "PrimaryToolBusy", "SCHEMA_VERSION", "__version__"]


def __getattr__(name: str):
    # Lazy import keeps ``import asi_kletz`` cheap and avoids import cycles.
    if name == "Brain":
        from .brain import Brain

        return Brain
    if name == "PrimaryToolBusy":
        from .locks import PrimaryToolBusy

        return PrimaryToolBusy
    raise AttributeError(name)
