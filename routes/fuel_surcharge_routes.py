from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
from auth import get_current_user
from database import db
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fuel-surcharge", tags=["Fuel Surcharge"])


# ---------------------------------------------------------------------------
# DOE Fuel Surcharge Table (USD/gallon)
# Source: ATA / U.S. Department of Energy
# Base: $1.25 | Increment: $0.05 | Mirrors frontend fuel-surcharge-api.js exactly
# ---------------------------------------------------------------------------
DOE_TABLE = [
    {"min": 0.00,  "max": 1.259, "cpm": 0.000, "pct": 0.0 },
    {"min": 1.26,  "max": 1.309, "cpm": 0.010, "pct": 0.5 },
    {"min": 1.31,  "max": 1.359, "cpm": 0.015, "pct": 0.8 },
    {"min": 1.36,  "max": 1.409, "cpm": 0.020, "pct": 1.0 },
    {"min": 1.41,  "max": 1.459, "cpm": 0.025, "pct": 1.3 },
    {"min": 1.46,  "max": 1.509, "cpm": 0.030, "pct": 1.5 },
    {"min": 1.51,  "max": 1.559, "cpm": 0.035, "pct": 1.8 },
    {"min": 1.56,  "max": 1.609, "cpm": 0.040, "pct": 2.0 },
    {"min": 1.61,  "max": 1.659, "cpm": 0.045, "pct": 2.3 },
    {"min": 1.66,  "max": 1.709, "cpm": 0.050, "pct": 2.5 },
    {"min": 1.71,  "max": 1.759, "cpm": 0.055, "pct": 2.8 },
    {"min": 1.76,  "max": 1.809, "cpm": 0.060, "pct": 3.0 },
    {"min": 1.81,  "max": 1.859, "cpm": 0.065, "pct": 3.3 },
    {"min": 1.86,  "max": 1.909, "cpm": 0.070, "pct": 3.5 },
    {"min": 1.91,  "max": 1.959, "cpm": 0.075, "pct": 3.8 },
    {"min": 1.96,  "max": 2.009, "cpm": 0.080, "pct": 4.0 },
    {"min": 2.01,  "max": 2.059, "cpm": 0.085, "pct": 4.3 },
    {"min": 2.06,  "max": 2.109, "cpm": 0.090, "pct": 4.5 },
    {"min": 2.11,  "max": 2.159, "cpm": 0.095, "pct": 4.8 },
    {"min": 2.16,  "max": 2.209, "cpm": 0.100, "pct": 5.0 },
    {"min": 2.21,  "max": 2.259, "cpm": 0.105, "pct": 5.3 },
    {"min": 2.26,  "max": 2.309, "cpm": 0.110, "pct": 5.5 },
    {"min": 2.31,  "max": 2.359, "cpm": 0.115, "pct": 5.8 },
    {"min": 2.36,  "max": 2.409, "cpm": 0.120, "pct": 6.0 },
    {"min": 2.41,  "max": 2.459, "cpm": 0.125, "pct": 6.3 },
    {"min": 2.46,  "max": 2.509, "cpm": 0.130, "pct": 6.5 },
    {"min": 2.51,  "max": 2.559, "cpm": 0.135, "pct": 6.8 },
    {"min": 2.56,  "max": 2.609, "cpm": 0.140, "pct": 7.0 },
    {"min": 2.61,  "max": 2.659, "cpm": 0.145, "pct": 7.3 },
    {"min": 2.66,  "max": 2.709, "cpm": 0.150, "pct": 7.5 },
    {"min": 2.71,  "max": 2.759, "cpm": 0.155, "pct": 7.8 },
    {"min": 2.76,  "max": 2.809, "cpm": 0.160, "pct": 8.0 },
    {"min": 2.81,  "max": 2.859, "cpm": 0.165, "pct": 8.3 },
    {"min": 2.86,  "max": 2.909, "cpm": 0.170, "pct": 8.5 },
    {"min": 2.91,  "max": 2.959, "cpm": 0.175, "pct": 8.8 },
    {"min": 2.96,  "max": 3.009, "cpm": 0.180, "pct": 9.0 },
    {"min": 3.01,  "max": 3.059, "cpm": 0.185, "pct": 9.3 },
    {"min": 3.06,  "max": 3.109, "cpm": 0.190, "pct": 9.5 },
    {"min": 3.11,  "max": 3.159, "cpm": 0.195, "pct": 9.8 },
    {"min": 3.16,  "max": 3.209, "cpm": 0.200, "pct": 10.0},
    {"min": 3.21,  "max": 3.259, "cpm": 0.205, "pct": 10.3},
    {"min": 3.26,  "max": 3.309, "cpm": 0.210, "pct": 10.5},
    {"min": 3.31,  "max": 3.359, "cpm": 0.215, "pct": 10.8},
    {"min": 3.36,  "max": 3.409, "cpm": 0.220, "pct": 11.0},
    {"min": 3.41,  "max": 3.459, "cpm": 0.225, "pct": 11.3},
    {"min": 3.46,  "max": 3.509, "cpm": 0.230, "pct": 11.5},
    {"min": 3.51,  "max": 3.559, "cpm": 0.235, "pct": 11.8},
    {"min": 3.56,  "max": 3.609, "cpm": 0.240, "pct": 12.0},
    {"min": 3.61,  "max": 3.659, "cpm": 0.245, "pct": 12.3},
    {"min": 3.66,  "max": 3.709, "cpm": 0.250, "pct": 12.5},
    {"min": 3.71,  "max": 3.759, "cpm": 0.255, "pct": 12.8},
    {"min": 3.76,  "max": 3.809, "cpm": 0.260, "pct": 13.0},
    {"min": 3.81,  "max": 3.859, "cpm": 0.265, "pct": 13.3},
    {"min": 3.86,  "max": 3.909, "cpm": 0.270, "pct": 13.5},
    {"min": 3.91,  "max": 3.959, "cpm": 0.275, "pct": 13.8},
    {"min": 3.96,  "max": 4.009, "cpm": 0.280, "pct": 14.0},
    {"min": 4.01,  "max": 4.059, "cpm": 0.285, "pct": 14.3},
    {"min": 4.06,  "max": 4.109, "cpm": 0.290, "pct": 14.5},
    {"min": 4.11,  "max": 4.159, "cpm": 0.295, "pct": 14.8},
    {"min": 4.16,  "max": 4.209, "cpm": 0.300, "pct": 15.0},
    {"min": 4.21,  "max": 4.259, "cpm": 0.305, "pct": 15.3},
    {"min": 4.26,  "max": 4.309, "cpm": 0.310, "pct": 15.5},
    {"min": 4.31,  "max": 4.359, "cpm": 0.315, "pct": 15.8},
    {"min": 4.36,  "max": 4.409, "cpm": 0.320, "pct": 16.0},
    {"min": 4.41,  "max": 4.459, "cpm": 0.325, "pct": 16.3},
    {"min": 4.46,  "max": 4.509, "cpm": 0.330, "pct": 16.5},
    {"min": 4.51,  "max": 4.559, "cpm": 0.335, "pct": 16.8},
    {"min": 4.56,  "max": 4.609, "cpm": 0.340, "pct": 17.0},
    {"min": 4.61,  "max": 4.659, "cpm": 0.345, "pct": 17.3},
    {"min": 4.66,  "max": 4.709, "cpm": 0.350, "pct": 17.5},
    {"min": 4.71,  "max": 4.759, "cpm": 0.355, "pct": 17.8},
    {"min": 4.76,  "max": 9999,  "cpm": 0.360, "pct": 18.0},
]

# ---------------------------------------------------------------------------
# CTA Fuel Surcharge Table (CAD/L)
# Source: Canadian Trucking Alliance
# Base: $1.20/L | Increment: $0.06/L | Each step adds 1%
# ---------------------------------------------------------------------------
def _build_cta_table() -> list:
    rows = [{"min": 0.0, "max": 1.199, "pct": 0.0}]
    base = 1.20
    pct = 2.0
    while pct <= 40.0:
        lo = round(base, 3)
        hi = round(base + 0.059, 3)
        rows.append({"min": lo, "max": hi, "pct": pct})
        base = round(base + 0.06, 3)
        pct = round(pct + 1.0, 1)
    # Last row covers anything above the table
    rows[-1]["max"] = 9999
    return rows

CTA_TABLE = _build_cta_table()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _r2(n: float) -> float:
    """Financial rounding to 2 decimal places."""
    return round(n + 1e-10, 2)


def _fmt(n: float) -> str:
    return f"${n:,.2f}"


def _get_doe_row(price: float) -> dict:
    for row in DOE_TABLE:
        if row["min"] <= price <= row["max"]:
            return row
    return DOE_TABLE[-1]


def _get_cta_row(price: float) -> dict:
    for row in CTA_TABLE:
        if row["min"] <= price <= row["max"]:
            return row
    return CTA_TABLE[-1]


def _build_fsc_table(current_price: float) -> list:
    """Annotated DOE table for the frontend — isActive flags current row."""
    result = []
    for row in DOE_TABLE:
        is_active = row["min"] <= current_price <= row["max"]
        max_display = "above" if row["max"] == 9999 else f"${row['max']:.3f}"
        result.append({
            "isActive":   is_active,
            "range":      f"${row['min']:.3f} – {max_display}",
            "cpmDisplay": f"${row['cpm']:.3f}/mi",
            "pctDisplay": f"{row['pct']:.1f}%",
            "cpm": row["cpm"],
            "pct": row["pct"],
            "min": row["min"],
            "max": row["max"],
        })
    return result


def _build_cta_fsc_table(current_price: float) -> list:
    """Annotated CTA table for the frontend."""
    result = []
    for row in CTA_TABLE:
        is_active = row["min"] <= current_price <= row["max"]
        max_display = "above" if row["max"] == 9999 else f"${row['max']:.3f}"
        result.append({
            "isActive":   is_active,
            "range":      f"${row['min']:.3f} – {max_display}",
            "pctDisplay": f"{row['pct']:.1f}%",
            "pct": row["pct"],
            "min": row["min"],
            "max": row["max"],
        })
    return result


async def _check_paid(current_user) -> bool:
    """Return True if user is a platform admin or has an active subscription."""
    if str(getattr(current_user, "role", "")).replace("UserRole.", "") == "platform_admin":
        return True
    if not current_user.tenant_id:
        return False
    company = await db.companies.find_one({"id": current_user.tenant_id})
    if not company:
        return False
    if company.get("subscription_status") == "active":
        return True
    return any(s.get("status") == "active" for s in company.get("subscriptions", []))


async def _save_history(current_user, payload: dict) -> str:
    doc = {
        "type": "fuel-surcharge",
        "user_id": str(current_user.id),
        "company_id": str(getattr(current_user, "tenant_id", "") or ""),
        "data": payload,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    result = await db.history.insert_one(doc)
    return str(result.inserted_id)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class FuelSurchargeRequest(BaseModel):
    method: str                          # cpm | pct | flat | formula | cta_table
    fuelPrice: float
    miles: Optional[float] = None
    linehaul: Optional[float] = 0.0
    flatCpm: Optional[float] = 0.0
    flatTotal: Optional[float] = 0.0
    baseFuel: Optional[float] = None
    mpg: Optional[float] = None
    currency: str = "USD"               # USD | CAD
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# POST /api/fuel-surcharge/calculate
# ---------------------------------------------------------------------------

@router.post("/calculate", response_model=dict)
async def calculate_fuel_surcharge(
    data: FuelSurchargeRequest,
    current_user=Depends(get_current_user),
):
    method = data.method.lower()
    fuel_price = data.fuelPrice
    miles = data.miles or 0.0
    linehaul = data.linehaul or 0.0

    # ── Validation ────────────────────────────────────────────────────────────
    if method not in {"cpm", "pct", "flat", "formula", "cta_table"}:
        return JSONResponse(
            status_code=400,
            content={"error": "method must be one of: cpm, pct, flat, formula, cta_table"},
        )
    if fuel_price < 0:
        return JSONResponse(status_code=400, content={"error": "fuelPrice must be non-negative"})
    if method in {"cpm", "pct", "formula"} and miles <= 0:
        return JSONResponse(status_code=400, content={"error": f"miles is required for method '{method}'"})
    if method == "flat" and miles <= 0 and (not data.flatTotal or data.flatTotal <= 0):
        return JSONResponse(status_code=400, content={"error": "flat method requires miles or flatTotal"})
    if method == "formula":
        if data.baseFuel is None:
            return JSONResponse(status_code=400, content={"error": "baseFuel is required for formula method"})
        if not data.mpg or data.mpg <= 0:
            return JSONResponse(status_code=400, content={"error": "mpg must be positive for formula method"})
    if method == "cta_table" and linehaul <= 0:
        return JSONResponse(status_code=400, content={"error": "linehaul is required for cta_table method"})

    # ── Calculation ───────────────────────────────────────────────────────────
    surcharge = 0.0
    surcharge_label = ""
    breakdown: List[dict] = []
    active_row: dict = {}

    if method == "cpm":
        row = _get_doe_row(fuel_price)
        surcharge = _r2(row["cpm"] * miles)
        surcharge_label = f"${row['cpm']:.3f}/mi × {miles:,.0f} mi"
        max_display = "∞" if row["max"] == 9999 else f"${row['max']:.3f}"
        breakdown = [
            {"label": "DOE Fuel Price Band", "value": f"${row['min']:.3f} – {max_display}", "highlight": False},
            {"label": "FSC Rate (CPM)",       "value": f"${row['cpm']:.3f}/mi",             "highlight": False},
            {"label": "Miles",                "value": f"{miles:,.0f}",                      "highlight": False},
            {"label": "Fuel Surcharge",       "value": _fmt(surcharge),                      "highlight": True},
        ]
        active_row = row

    elif method == "pct":
        row = _get_doe_row(fuel_price)
        surcharge = _r2(linehaul * (row["pct"] / 100))
        surcharge_label = f"{row['pct']:.1f}% of {_fmt(linehaul)}"
        max_display = "∞" if row["max"] == 9999 else f"${row['max']:.3f}"
        breakdown = [
            {"label": "DOE Fuel Price Band", "value": f"${row['min']:.3f} – {max_display}", "highlight": False},
            {"label": "FSC Rate (%)",        "value": f"{row['pct']:.1f}%",                 "highlight": False},
            {"label": "Linehaul Rate",       "value": _fmt(linehaul),                        "highlight": False},
            {"label": "Fuel Surcharge",      "value": _fmt(surcharge),                       "highlight": True},
        ]
        active_row = row

    elif method == "flat":
        flat_total = data.flatTotal or 0.0
        flat_cpm = data.flatCpm or 0.0
        if flat_total > 0:
            surcharge = _r2(flat_total)
            surcharge_label = "Flat Amount"
            breakdown = [
                {"label": "Method",         "value": "Flat Total",    "highlight": False},
                {"label": "Flat Amount",    "value": _fmt(flat_total), "highlight": False},
                {"label": "Fuel Surcharge", "value": _fmt(surcharge),  "highlight": True},
            ]
        else:
            surcharge = _r2(flat_cpm * miles)
            surcharge_label = f"${flat_cpm:.3f}/mi × {miles:,.0f} mi"
            breakdown = [
                {"label": "Method",         "value": "Custom CPM",       "highlight": False},
                {"label": "Custom Rate",    "value": f"${flat_cpm:.3f}/mi", "highlight": False},
                {"label": "Miles",          "value": f"{miles:,.0f}",    "highlight": False},
                {"label": "Fuel Surcharge", "value": _fmt(surcharge),    "highlight": True},
            ]
        active_row = {}

    elif method == "formula":
        base_fuel = data.baseFuel
        mpg = data.mpg
        cost_per_mile = (fuel_price - base_fuel) / mpg
        surcharge = _r2(max(0.0, cost_per_mile * miles))
        surcharge_label = f"({_fmt(fuel_price)} − {_fmt(base_fuel)}) ÷ {mpg} mpg × {miles:,.0f} mi"
        breakdown = [
            {"label": "Current Fuel Price", "value": _fmt(fuel_price),                          "highlight": False},
            {"label": "Base Fuel Price",    "value": _fmt(base_fuel),                           "highlight": False},
            {"label": "Price Difference",   "value": _fmt(max(0.0, fuel_price - base_fuel)),    "highlight": False},
            {"label": "Truck MPG",          "value": f"{mpg} mpg",                              "highlight": False},
            {"label": "Extra Cost/Mile",    "value": f"${max(0.0, cost_per_mile):.4f}",         "highlight": False},
            {"label": "Miles",              "value": f"{miles:,.0f}",                           "highlight": False},
            {"label": "Fuel Surcharge",     "value": _fmt(surcharge),                           "highlight": True},
        ]
        active_row = {}

    elif method == "cta_table":
        row = _get_cta_row(fuel_price)
        surcharge = _r2(linehaul * (row["pct"] / 100))
        surcharge_label = f"{row['pct']:.1f}% of {_fmt(linehaul)}"
        max_display = "above" if row["max"] == 9999 else f"${row['max']:.3f}"
        breakdown = [
            {"label": "CTA Fuel Price Band", "value": f"${row['min']:.3f} – {max_display}", "highlight": False},
            {"label": "FSC Rate (%)",         "value": f"{row['pct']:.1f}%",                "highlight": False},
            {"label": "Linehaul Rate",        "value": _fmt(linehaul),                      "highlight": False},
            {"label": "Fuel Surcharge",       "value": _fmt(surcharge),                     "highlight": True},
        ]
        active_row = row

    total_with_lh = _r2(linehaul + surcharge)
    fsc_percent = _r2((surcharge / linehaul) * 100) if linehaul > 0 else 0.0

    # Build annotated table for frontend (DOE for most methods, CTA for cta_table)
    fsc_table = _build_cta_fsc_table(fuel_price) if method == "cta_table" else _build_fsc_table(fuel_price)

    # ── History saving (paid subscribers only) ────────────────────────────────
    saved_to_history = False
    history_id = None

    is_paid = await _check_paid(current_user)
    if is_paid:
        history_payload = {
            "method": method,
            "currency": data.currency,
            "fuelPrice": fuel_price,
            "miles": miles,
            "linehaul": linehaul,
            "surcharge": surcharge,
            "totalWithLH": total_with_lh,
            "fscPercent": fsc_percent,
            "description": data.description,
        }
        history_id = await _save_history(current_user, history_payload)
        saved_to_history = True

    # ── Response (matches frontend's exact shape) ─────────────────────────────
    return {
        "surcharge":       surcharge,
        "surchargeLabel":  surcharge_label,
        "breakdown":       breakdown,
        "totalWithLH":     total_with_lh,
        "fscPercent":      fsc_percent,
        "fsc":             active_row,
        "fscTable":        fsc_table,
        "saved_to_history": saved_to_history,
        "history_id":      history_id,
    }


# ---------------------------------------------------------------------------
# GET /api/fuel-surcharge/rates  (no auth — used by the CTA/DOE tab display)
# ---------------------------------------------------------------------------

@router.get("/rates", response_model=dict)
async def get_fsc_rates():
    """Return both DOE and CTA tables with metadata. No auth required."""
    doe_annotated = [
        {
            "range":      f"${r['min']:.3f} – " + ("above" if r['max'] == 9999 else f"${r['max']:.3f}"),
            "cpmDisplay": f"${r['cpm']:.3f}/mi",
            "pctDisplay": f"{r['pct']:.1f}%",
            "cpm": r["cpm"],
            "pct": r["pct"],
            "min": r["min"],
            "max": r["max"],
        }
        for r in DOE_TABLE
    ]
    cta_annotated = [
        {
            "range":      f"${r['min']:.3f} – " + ("above" if r['max'] == 9999 else f"${r['max']:.3f}"),
            "pctDisplay": f"{r['pct']:.1f}%",
            "pct": r["pct"],
            "min": r["min"],
            "max": r["max"],
        }
        for r in CTA_TABLE
    ]
    return {
        "doe_table": doe_annotated,
        "cta_table": cta_annotated,
        "defaults": {
            "doe": {"base_fuel": 1.25, "increment": 0.05, "currency": "USD", "unit": "gallon"},
            "cta": {"base_fuel": 1.20, "increment": 0.06, "currency": "CAD", "unit": "litre"},
        },
    }
