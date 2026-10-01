"""Makes ``python -m air.detectors.no_fly_zone.live`` work."""
from __future__ import annotations

import sys

from .runner import main

if __name__ == "__main__":
    sys.exit(main())
