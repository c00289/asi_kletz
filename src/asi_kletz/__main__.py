"""Allow ``python -m asi_kletz <verb> ...``."""

from .automation.cli import main

raise SystemExit(main())
