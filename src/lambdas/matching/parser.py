"""DMS CDC record parser.

Parses Kinesis records from DMS into weather event dicts.
Supports both the DMS envelope format and direct event format (local dev).
"""

import json
import logging

logger = logging.getLogger(__name__)


def parse_dms_record(raw_data: str) -> dict | None:
    """Parse a DMS CDC envelope from Kinesis.

    DMS wraps row data in an envelope:
    {
      "data": {"location_lat": -34.6, "location_lon": -58.4, ...},
      "metadata": {"operation": "insert", "table-name": "weather_data", ...}
    }
    """
    try:
        envelope = json.loads(raw_data)
    except json.JSONDecodeError:
        logger.error("Malformed JSON in Kinesis record, skipping")
        return None

    # Handle both DMS envelope format and direct event format
    if "data" in envelope and "metadata" in envelope:
        metadata = envelope["metadata"]
        if metadata.get("table-name") != "weather_data":
            return None
        if metadata.get("operation") not in ("insert", "load"):
            return None
        return envelope["data"]

    # Direct format (e.g., from simulator in local dev)
    if "location_lat" in envelope and "location_lon" in envelope:
        return envelope

    logger.warning("Unrecognized Kinesis record format, skipping")
    return None
