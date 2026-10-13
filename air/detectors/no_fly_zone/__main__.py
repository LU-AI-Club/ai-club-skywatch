"""Makes ``python -m air.detectors.no_fly_zone`` work."""
from __future__ import annotations

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
