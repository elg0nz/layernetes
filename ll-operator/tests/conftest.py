"""Make the flat handler modules importable without installing a top-level
`operator` package (which would shadow the Python stdlib module)."""

import pathlib
import sys

OPERATOR_DIR = pathlib.Path(__file__).resolve().parents[1] / "operator"
if str(OPERATOR_DIR) not in sys.path:
    sys.path.insert(0, str(OPERATOR_DIR))
