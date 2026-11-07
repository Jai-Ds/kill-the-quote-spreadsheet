"""Loads the company base data workbook, and handles saved run state."""
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "Base Data" / "Kesavi_Base_Data.xlsx"
REPLIES = ROOT / "vendor_replies"
RUNTIME = Path(os.environ.get("PROTO_RUNTIME", ROOT / "runtime"))   # tests use their own folder
RUNTIME.mkdir(parents=True, exist_ok=True)
(RUNTIME / "cache").mkdir(exist_ok=True)
STATE = RUNTIME / "state.json"


@lru_cache(maxsize=None)
def sheet(name):
    df = pd.read_excel(BASE, sheet_name=name, header=3)
    return df.dropna(how="all")


@lru_cache(maxsize=1)
def company():
    c = sheet("Company")
    return dict(zip(c["Parameter"], c["Value"]))


@lru_cache(maxsize=1)
def fx_rate():
    fx = sheet("FX_Rates")
    fx = fx[pd.to_datetime(fx["Date"], errors="coerce").notna() & fx["Rate"].notna()].copy()
    fx["Date"] = pd.to_datetime(fx["Date"])
    row = fx.sort_values("Date").iloc[-1]
    return float(row["Rate"]), row["Date"].date()


def rm_table():
    rm = sheet("RM_Master").copy()
    return rm[rm["RM code"].astype(str).str.startswith("RM-")]


def spec_strength(spec_text):
    """Reads '20% rosmarinic acid' into (20.0, '%', 'rosmarinic acid')."""
    m = re.search(r"([\d,\.]+)\s*(%|ppm)\s*(.*)", str(spec_text))
    if not m:
        return None, None, None
    return float(m.group(1).replace(",", "")), m.group(2), m.group(3).strip().lower()


def vendors():
    return sheet("Vendor_Master")


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"extractions": {}, "patches": {}, "clarifications": {}, "rfx": None, "rfx_sent": False, "rfx_chat": [], "analyst": []}


def save_state(s):
    STATE.write_text(json.dumps(s, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


GLOSSARY = [
    ("ppm", "Parts per million. 1 ppm is 1 mg in 1 kg, and 10,000 ppm is 1%."),
    ("ppm peptide", "How much active peptide is in the solution. 1,000 ppm peptide is 1 g of peptide in each kg of solution. The rest is water or carrier, so at 800 ppm you need 1.25 kg to get the same peptide."),
    ("% active", "Share of the material that is the working ingredient, such as 98% active D-Panthenol."),
    ("Marker", "The compound measured to state strength. 20% rosmarinic acid can't be compared with a figure on carnosic acid."),
    ("Spec kg", "Kg of material at our specified strength, so that different strengths compare fairly."),
    ("HPLC, GC", "Lab test methods used to measure strength or purity."),
    ("cP", "Centipoise, a unit of viscosity (thickness)."),
    ("COA", "Certificate of Analysis: lab results for one batch."),
    ("SDS", "Safety Data Sheet."),
    ("OTIF", "On time, in full: share of deliveries that arrived on time with the full quantity."),
    ("MOQ", "Minimum order quantity."),
    ("Landed cost", "Price after discount, duty, freight and currency conversion."),
    ("FG-301, FG-600", "The two finished packs: 30 mL and 60 mL."),
]
