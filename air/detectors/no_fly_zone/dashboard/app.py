"""Stream J - Streamlit dashboard. Run with ``streamlit run dashboard/app.py``.

Read-only. Reads ``detections.jsonl`` and the Parquet state files and draws
them. It never computes a detection: if a number is interesting enough to show,
it belongs in the Detection the detector already emitted.

Inputs
------
Paths entered in the sidebar, defaulting to the CLI's output layout.

Panels to build
---------------
- A Folium or pydeck map: zone polygons, aircraft tracks, detections marked.
- A detections table sorted by ``anomaly_score``, filterable by severity.
- Per-detection detail: ``explanation_facts`` and ``limitations`` verbatim.
- An exit-reason histogram, so a quiet run can be explained rather than
  assumed broken.

Failure causes
--------------
FileNotFoundError
    Inputs not produced yet. Show an empty state with the expected path, not a
    stack trace.
Malformed JSONL line
    Skip it, count it, surface the count. One bad line must not blank the page.

Notes
-----
Guard the Streamlit body behind ``if __name__ == "__main__":`` so importing
this module (as the tests do) does no I/O and renders nothing.
"""
from __future__ import annotations


def main() -> None:
    """Render the dashboard. Called only under ``streamlit run``."""
    raise NotImplementedError("stream J: dashboard")


if __name__ == "__main__":
    main()
