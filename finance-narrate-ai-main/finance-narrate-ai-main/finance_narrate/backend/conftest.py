"""conftest.py — adds the backend directory to sys.path so that
`models` and `processor` can be imported without package prefixes."""

import sys
from pathlib import Path

# Ensure the backend directory is on the path when pytest is invoked
# from any working directory.
sys.path.insert(0, str(Path(__file__).parent))
