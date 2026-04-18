"""XML renderer for prefix records."""

from __future__ import annotations

import io
import xml.etree.ElementTree as ET

from paic.renderers._dict import record_to_dict


def render(records: list, options: dict | None = None) -> bytes:
    """Render records as well-formed XML parseable by xml.etree.ElementTree."""
    root = ET.Element("prefixes")
    root.set("count", str(len(records)))

    for rec in records:
        entry = ET.SubElement(root, "prefix")
        for key, val in record_to_dict(rec).items():
            child = ET.SubElement(entry, key)
            child.text = str(val) if val is not None else ""

    buf = io.BytesIO()
    ET.ElementTree(root).write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue()
