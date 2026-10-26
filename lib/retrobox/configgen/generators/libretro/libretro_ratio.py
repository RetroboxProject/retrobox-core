"""RetroArch aspect ratio names and their ``aspect_ratio_index`` values."""

from __future__ import annotations

# the position of each name is the value of RetroArch's aspect_ratio_index
RATIO_INDEXES = (
    "4/3", "16/9", "16/10", "16/15", "21/9", "1/1", "2/1", "3/2", "3/4", "4/1",
    "9/16", "5/4", "6/5", "7/9", "8/3", "8/7", "19/12", "19/14", "30/17", "32/9",
    "config", "squarepixel", "core", "custom", "full",
)  # fmt: skip

# index used when a ratio name is not in RATIO_INDEXES
CORE_RATIO_INDEX = RATIO_INDEXES.index("core")
CUSTOM_RATIO_INDEX = RATIO_INDEXES.index("custom")
