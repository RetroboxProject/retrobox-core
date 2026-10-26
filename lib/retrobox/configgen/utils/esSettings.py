from __future__ import annotations

import xml.etree.ElementTree as ET

from retrobox.paths import ES_SETTINGS_CFG

# Return value for ES InvertButtons (are confirm/cancel swapped)
def getInvertButtonsValue() -> bool:
    try:
        tree = ET.parse(ES_SETTINGS_CFG)
        root = tree.getroot()
        # Find the InvertButtons element and return value
        elem = root.find(".//bool[@name='InvertButtons']")
        if elem is not None:
            return elem.get('value') == 'true'
        return False  # Return False if not found
    except Exception:
        return False  # when file doesn't exist or is malformed
