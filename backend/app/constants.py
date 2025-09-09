from __future__ import annotations

# Required columns from PRD (fail if Planning Whse missing)
REQUIRED_COLUMNS = {
    "SO",
    "Line",
    "Customer",
    "shipping_city",
    "shipping_state",
    "Ready Weight",
    "RPcs",
    "Grd",
    "Size",
    "Width",
    "Earliest Due",
    "Latest Due",
    "Planning Whse",
}

# Synonyms mapping for flexible header recognition (case-insensitive)
SYNONYMS = {
    "shipping_state": {"shipping_state", "state", "ship state", "ship to state", "shipping state"},
    "shipping_city": {"shipping_city", "city", "ship city", "ship to city", "shipping city"},
    "zone": {"zone", "zone id"},
    "route": {"route", "route id", "route code"},
    "planning whse": {"planning whse", "planning warehouse", "planning whs"},
}

NO_MULTI_STOP_CUSTOMERS = [
    "Sabre Tubular Structures",
    "GamTex",
    "Cmcr Fort Worth",
    "Ozark Steel LLC",
    "Gachman Metals & Recycling Co",
    "Sabre",
    "Sabre - Kennedale",
    "Sabre Industries",
    "Sabre Southbridge Plate STP",
    "Petrosmith Equipment LP",
    "W&W AFCO STEEL",
    "Red Dot Corporation",
]
