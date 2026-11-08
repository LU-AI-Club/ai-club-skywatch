from contracts import Detection


def extra_columns(detection: Detection) -> dict:
    """Use shared detection columns and metadata without adding extra columns."""
    return {}
