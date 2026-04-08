"""
CARE Operations Portal
======================
Two tools in one:
  1. Risk Assessment Scorer â upload a PDF, answer questions, get tier + price
  2. Report Tracker â upload reports, track weekly counts per client
"""

import os, json, datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "care-portal-2026")

# ---------------------------------------------------------------------------
# DATA STORE (in-memory; resets on redeploy â fine for tracking)
# ---------------------------------------------------------------------------
DATA_FILE = "/tmp/care_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return {"reports": [], "clients": DEFAULT_CLIENTS}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, default=str)

DEFAULT_CLIENTS = [
    {"name": "Michael Champion",  "phone": "07523405620", "address": "Unit 3, 26 Rodney Close, Gosport, PO13 8EJ",
     "support_per_week": 3, "residency_per_week": 3, "council": "Gosport"},
    {"name": "Brendon Smith",     "phone": "07360690464", "address": "64 Winterslow Drive, Havant, PO9 5DZ",
     "support_per_week": 4, "residency_per_week": 3, "council": "Havant"},
    {"name": "Danny Gattrell",    "phone": "07552759608", "address": "Flat 4, Delme Court, Maytree Road, Fareham, PO16 0HX",
     "support_per_week": 1, "residency_per_week": 2, "council": "Havant"},
    {"name": "Ricky Shields",     "phone": "07350870715", "address": "Flat 151, The Round House, Gunwharf Quays, PO1 3SH",
     "support_per_week": 0, "residency_per_week": 2, "council": "Havant"},
    {"name": "Alfi Antsy",        "phone": "07491326845", "address": "Flat 1, 32 Arundel Street, Portsmouth, PO1 1NL",
     "support_per_week": 7, "residency_per_week": 7, "council": "Brighton"},
    {"name": "David Cager",       "phone": "07904050873", "address": "Unit 1, 26 Rodney Close, Gosport, PO13 8EJ",
     "support_per_week": 2, "residency_per_week": 1, "council": "Brighton"},
    {"name": "Lee O'Shaughnessy", "phone": "07852504386", "address": "Unit 4, 39 Manners Road, Southsea, PO4 0BA",
     "support_per_week": 2, "residency_per_week": 2, "council": "Gosport"},
    {"name": "Peter Watter",      "phone": "07974168183", "address": "Flat 5, 37 Granada Road, Southsea, PO4 0RZ",
     "support_per_week": 2, "residency_per_week": 1, "council": "Havant"},
    {"name": "Daniel Flanagan",   "phone": "07873928927", "address": "Flat 3, 37 Granada Road, Southsea, PO4 0RZ",
     "support_per_week": 1, "residency_per_week": 1, "council": "Havant"},
]

# ---------------------------------------------------------------------------
# RISK ASSESSMENT RUBRIC
# ---------------------------------------------------------------------------
RISK_FACTORS = {
    "Violence & Threats": {
        "Common assault / minor violence":          {"historic": 1, "recent": 2},
        "Multiple / aggravated assault":            {"historic": 3, "recent": 5},
        "Serious assault (GBH, weapons used)":      {"historic": 6, "recent": 8},
        "Threats to kill":                          {"historic": 4, "recent": 6},
        "Public order (affray / violent disorder)":  {"historic": 4, "recent": 6},
        "Weapons possession (knife / firearm / acid)": {"historic": 5, "recent": 7},
        "Dangerous dog / banned breed":             {"historic": 3, "recent": 5},
    },
    "Sexual Offences": {
        "Sexual offence - non-contact":             {"historic": 6, "recent": 8},
        "Sexual offence - contact":                 {"historic": 7, "recent": 9},
        "Sex Offenders Register non-compliance":    {"historic": 7, "recent": 9},
    },
    "Domestic Abuse": {
        "Domestic abuse - perpetrator":             {"historic": 5, "recent": 7},
        "Coercive / controlling behaviour":         {"historic": 5, "recent": 7},
        "Domestic abuse - victim":                  {"historic": 2, "recent": 3},
    },
    "Arson & Safety": {
        "Arson - low risk":                         {"historic": 3, "recent": 4},
        "Arson - high risk (deliberate harm)":      {"historic": 7, "recent": 8},
        "Tampering with safety systems":            {"historic": 4, "recent": 6},
    },
    "Drugs & Organised Crime": {
        "Substance misuse - alcohol":               {"historic": 2, "recent": 3},
        "Substance misuse - drugs (use)":           {"historic": 3, "recent": 5},
        "County lines / drug supply / trafficking": {"historic": 7, "recent": 8},
        "Drug manufacture / cultivation":           {"historic": 5, "recent": 7},
        "Gang / OCG affiliation":                   {"historic": 6, "recent": 8},
    },
    "Acquisitive & Property Crime": {
        "Robbery":                                  {"historic": 5, "recent": 7},
        "Burglary":                                 {"historic": 3, "recent": 5},
        "Criminal damage":                          {"historic": 2, "recent": 4},
    },
    "Mental Health & Self-Harm": {
        "Self-harm / suicidal ideation":            {"historic": 3, "recent": 5},
        "Mental health crisis / sectioning":        {"historic": 4, "recent": 6},
        "Personality disorder / complex needs":     {"historic": 3, "recent": 5},
    },
    "Anti-Social Behaviour": {
        "ASB / noise / neighbour disputes":         {"historic": 2, "recent": 3},
        "Harassment / stalking":                    {"historic": 4, "recent": 6},
        "Criminal behaviour order breach":          {"historic": 3, "recent": 5},
    },
}

PRICING_TIERS = [
    {"name": "Low Standard",    "min": 0,  "max": 5,  "HMO": [55, 55],   "1 Bed": [70, 70],   "2 Bed": [85, 85],   "3 Bed": [120, 120], "4 Bed": [140, 140]},
    {"name": "Low Enhanced",    "min": 6,  "max": 8,  "HMO": [75, 80],   "1 Bed": [90, 95],   "2 Bed": [105, 110], "3 Bed": None,       "4 Bed": None},
    {"name": "Medium Standard", "min": 9,  "max": 11, "HMO": [100, 110], "1 Bed": [115, 125], "2 Bed": [130, 140], "3 Bed": None,       "4 Bed": None},
    {"name": "Medium Enhanced",  "min": 12, "max": 15, "HMO": [120, 130], "1 Bed": [135, 145], "2 Bed": [150, 160], "3 Bed": None,       "4 Bed": None},
    {"name": "High Standard",   "min": 16, "max": 19, "HMO": [140, 150], "1 Bed": [155, 165], "2 Bed": [170, 180], "3 Bed": None,       "4 Bed": None},
    {"name": "High Enhanced",   "min": 20, "max": 30, "HMO": [160, 190], "1 Bed": [175, 205], "2 Bed": [190, 220], "3 Bed": None,       "4 Bed": None},
]

VISIT_PROFILES = {
    "Low Standard":    "0 residency + 0 support / week",
    "Low Enhanced":    "1 residency + 0-1 support / week",
    "Medium Standard": "2 residency + 1-2 support / week",
    "Medium Enhanced":  "3 residency + 1-2 support / week",
    "High Standard":   "4 residency + 1-2 support / week",
    "High Enhanced":   "5-6 residency + 1-2 support / week",
}

VISIT_RATES = {
    "Residency (single-manned)": 138.60,
    "Residency (double-manned)": 207.00,
    "Support (single-manned)": 45.00,
    "Support (double-manned)": 90.00,
}

def get_tier(score):
    for t in PRICING_TIERS:
        if t["min"] <= score <= t["max"]:
            return t
    return PRICING_TIERS[-1]

# ---------------------------------------------------------------------------
# WEEK HELPERS
# ---------------------------------------------------------------------------
def get_week_start(dt=None):
    """Return Monday 00:00 of the week containing dt."""
    if dt is None:
        dt = datetime.date.today()
    elif isinstance(dt, str):
        dt = datetime.date.fromisoformat(dt)
    return dt - datetime.timedelta(days=dt.weekday())

def get_week_label(week_start):
    end = week_start + datetime.timedelta(days=6)
    return f"{week_start.strftime('%d/%m/%y')} - {end.strftime('%d/%m/%y')}"

# ---------------------------------------------------------------------------
# ROUTES
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template("index.html")

# --- RISK SCORER ---
@app.route("/scorer")
def scorer():
    return render_template("scorer.html", risk_factors=RISK_FACTORS)

@app.route("/scorer/calculate", methods=["POST"])
def scorer_calculate():
    data = request.json
    factors = data.get("factors", [])
    property_type = data.get("property_type", "1 Bed")
    bills = data.get("bills_included", False)
    double_manned = data.get("double_manned", False)
    client_name = data.get("client_name", "")

    total = 0
    breakdown = []
    for f in factors:
        cat = f["category"]
        factor = f["factor"]
        timing = f["timing"]
        if cat in RISK_FACTORS and factor in RISK_FACTORS[cat]:
            score = RISK_FACTORS[cat][factor][timing]
            total += score
            breakdown.append({"category": cat, "factor": factor, "timing": timing, "score": score})

    total = min(total, 30)
    tier = get_tier(total)
    price_range = tier.get(property_type)

    result = {
        "client_name": client_name,
        "total_score": total,
        "tier_name": tier["name"],
        "property_type": property_type,
        "bills_included": bills,
        "double_manned": double_manned,
        "breakdown": breakdown,
        "visit_profile": VISIT_PROFILES[tier["name"]],
    }

    if price_range is None:
        result["error"] = f"No pricing for {property_type} at {tier['name']} tier."
    else:
        low, high = price_range
        if bills:
            low += 15
            high += 15
        result["nightly_low"] = low
        result["nightly_high"] = high

        # Weekly visit cost estimate
        if double_manned:
            result["visit_rates"] = {
                "residency": VISIT_RATES["Residency (double-manned)"],
                "support": VISIT_RATES["Support (double-manned)"],
            }
        else:
            result["visit_rates"] = {
                "residency": VISIT_RATES["Residency (single-manned)"],
                "support": VISIT_RATES["Support (single-manned)"],
            }

    return jsonify(result)

# --- REPORT TRACKER ---
@app.route("/tracker")
def tracker():
    data = load_data()
    clients = data["clients"]
    reports = data["reports"]

    # Build week options (last 8 weeks + next 2)
    today = datetime.date.today()
    weeks = []
    for offset in range(-8, 3):
        ws = get_week_start(today + datetime.timedelta(weeks=offset))
        weeks.append({"start": ws.isoformat(), "label": get_week_label(ws)})

    selected_week = request.args.get("week", get_week_start(today).isoformat())
    ws = datetime.date.fromisoformat(selected_week)
    we = ws + datetime.timedelta(days=6)

    # Count reports per client for the selected week
    tracker_data = []
    for c in clients:
        support_count = sum(
            1 for r in reports
            if r["client"] == c["name"] and r["type"] == "support"
            and ws.isoformat() <= r["date"] <= we.isoformat()
        )
        residency_count = sum(
            1 for r in reports
            if r["client"] == c["name"] and r["type"] == "residency"
            and ws.isoformat() <= r["date"] <= we.isoformat()
        )
        tracker_data.append({
            "name": c["name"],
            "address": c["address"],
            "support_done": support_count,
            "support_required": c["support_per_week"],
            "residency_done": residency_count,
            "residency_required": c["residency_per_week"],
        })

    return render_template("tracker.html",
        clients=tracker_data,
        weeks=weeks,
        selected_week=selected_week,
        week_label=get_week_label(ws),
    )

@app.route("/tracker/upload", methods=["POST"])
def tracker_upload():
    data = load_data()
    client = request.form.get("client")
    report_type = request.form.get("report_type")
    report_date = request.form.get("report_date")
    files = request.files.getlist("files")

    count = max(len(files), 1)
    for i in range(count):
        data["reports"].append({
            "client": client,
            "type": report_type,
            "date": report_date,
            "uploaded_at": datetime.datetime.now().isoformat(),
            "filename": files[i].filename if i < len(files) else "manual entry",
        })

    save_data(data)
    week = get_week_start(datetime.date.fromisoformat(report_date)).isoformat()
    return redirect(url_for("tracker", week=week))

@app.route("/tracker/bulk-upload", methods=["POST"])
def tracker_bulk_upload():
    """Upload multiple report files, auto-detect client and type from filename."""
    data = load_data()
    files = request.files.getlist("files")
    added = 0

    CLIENT_CODES = {}
    for c in data["clients"]:
        parts = c["name"].split()
        if len(parts) >= 2:
            code = parts[0][0] + "." + parts[1][0]
            CLIENT_CODES[code.upper()] = c["name"]
            # Also try first name match
            CLIENT_CODES[parts[0].upper()] = c["name"]

    for f in files:
        fn = f.filename.upper()
        # Detect type
        rtype = "residency" if "RESIDENCY" in fn else "support" if "SUPPORT" in fn else "unknown"
        # Detect client
        client = None
        for code, name in CLIENT_CODES.items():
            if code in fn.upper().replace(" ", ""):
                client = name
                break
        # Detect date (DD.MM.YY or DD_MM_YY)
        import re
        date_match = re.search(r'(\d{2})[._](\d{2})[._](\d{2})', fn)
        rdate = None
        if date_match:
            d, m, y = date_match.groups()
            rdate = f"20{y}-{m}-{d}"

        if client and rdate and rtype != "unknown":
            data["reports"].append({
                "client": client,
                "type": rtype,
                "date": rdate,
                "uploaded_at": datetime.datetime.now().isoformat(),
                "filename": f.filename,
            })
            added += 1

    save_data(data)
    return jsonify({"added": added, "total_files": len(files)})

@app.route("/tracker/reset", methods=["POST"])
def tracker_reset():
    data = load_data()
    data["reports"] = []
    save_data(data)
    return redirect(url_for("tracker"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
