"""
longtail_dashboard.py
---------------------
Reads the POS ledger CSV and writes longtail_dashboard.xlsx.

Run it right after the distributor POS scrubber. The scrubber appends to the ledger,
this reads the ledger, so the dashboard is current the moment the scrubber
finishes. Nothing here writes back to the ledger.

    python longtail_dashboard.py
    python longtail_dashboard.py --target 300
    python longtail_dashboard.py --out "some other name.xlsx"

TABS
  Dashboard   one screen. KPIs, the three focus groups, red/yellow/green counts.
  Partners    one row per partner. Sort or filter this to answer anything.
  Monthly     revenue by month for the last 24, plus active partner count.

KPIs close on the last COMPLETE month that has data in the ledger. The open
month is reported separately in the header. Any month with no ledger rows at
all is called out in a warning band on the Dashboard, because a gap silently
drags every trailing-12 and year-over-year number down.
"""

import os, sys, csv, time, argparse, collections
from datetime import date

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.chart import BarChart, Reference

HERE = os.path.dirname(os.path.abspath(__file__))

# The open month is only comparable to a full month after you account for how
# that calendar month normally paces. July back-loads (its last four days can be
# a third of the month), August front-loads. tracker.py already carries the
# median cumulative curve per month built from 2020-2025, so reuse it rather
# than keeping a second copy that can drift.
try:
    import importlib.util as _ilu
    _sp = _ilu.spec_from_file_location("_tr", os.path.join(HERE, "tracker.py"))
    _tr = _ilu.module_from_spec(_sp)
    _sp.loader.exec_module(_tr)
    SEASONAL_CUM = getattr(_tr, "SEASONAL_CUM", None)
except Exception:                                  # noqa: BLE001
    SEASONAL_CUM = None
LEDGER = os.path.join(HERE, "synthetic_ledger.csv")
OVERLAP_FILE = os.path.join(HERE, "overlap_partner_segmentation.xlsx")

# Partners the ledger splits across more than one key. Left side is what the
# ledger holds, right side is what they should roll up to. Add to this when you
# spot a partner counted twice.
KEY_MERGES = {
    # Same company under a DBA, FKA, account number or "(GOVT ONLY)" style
    # suffix. Each pair checked by raw name in the ledger. (Examples only;
    # the production map had about 90 entries.)
    "northwind data group fka northwind": "northwind data group",
    "harbor tech cc 460998": "harbor tech",
    "summit federal govt only": "summit federal",

    # Spelling and spacing splits (same company, one record buying, one "stopped").
    "bluepeaksystems": "blue peak systems",
    "g c micro": "gc micro",

    # Acquisitions where the buyer now orders under the new owner's name.
    "keystone it": "atlas digital",
}

# Display name for a merged partner when the most common historical name is
# no longer what they trade as. Used by the partner insights page.
NAME_OVERRIDES = {
    "atlas digital": "ATLAS DIGITAL LLC (FKA KEYSTONE IT)",
}

# End users that distributors reported in the reseller field. They are
# customers, not partners, so the partner insights page leaves them out of
# partner lists and counts. Revenue totals on the dashboard are unchanged.
# Records from the end-user-reporting distributor are handled separately.
END_USER_KEYS = {
    "riverside health system", "city of harlow", "maple county schools",
}

# ── colors ───────────────────────────────────────────────────────────────
GREEN  = PatternFill("solid", fgColor="C6EFCE")
YELLOW = PatternFill("solid", fgColor="FFEB9C")
RED    = PatternFill("solid", fgColor="FFC7CE")
GREY   = PatternFill("solid", fgColor="EDEDED")
HEAD   = PatternFill("solid", fgColor="334155")   # charcoal
ACCENT = PatternFill("solid", fgColor="99F6E4")   # accent
WARN   = PatternFill("solid", fgColor="FFC7CE")
FOG    = PatternFill("solid", fgColor="F3F4F5")

F_TITLE = Font(name="Arial", size=16, bold=True, color="334155")
F_HEAD  = Font(name="Arial", size=10, bold=True, color="FFFFFF")
F_LABEL = Font(name="Arial", size=10, bold=True, color="334155")
F_BODY  = Font(name="Arial", size=10)
F_BIG   = Font(name="Arial", size=20, bold=True, color="334155")
F_NOTE  = Font(name="Arial", size=9, italic=True, color="808080")

THIN = Side(style="thin", color="D0D0D0")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


# ── month helpers ────────────────────────────────────────────────────────
def m_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7])
    t = y * 12 + (m - 1) + n
    return "%04d-%02d" % (t // 12, t % 12 + 1)


def m_range(a, b):
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        cur = m_add(cur, 1)
    return out


def quarter_of(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return y * 4 + (m - 1) // 3


# ── load ─────────────────────────────────────────────────────────────────
def load_ledger(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        k = (r.get("partner_key") or r.get("partner_name") or "").strip().lower()
        r["_key"] = KEY_MERGES.get(k, k)
        r["_ym"] = (r.get("date") or "")[:7]
        try:
            r["_rev"] = float(r.get("revenue") or 0)
        except ValueError:
            r["_rev"] = 0.0
    return [r for r in rows if r["_key"] and len(r["_ym"]) == 7]


def load_overlap(path):
    """partner name -> (is_overlap, designation). Missing file is not fatal."""
    out = {}
    if not os.path.exists(path):
        return out
    try:
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb["Partner Detail"]
        for r in ws.iter_rows(min_row=4, values_only=True):
            if not r or not r[0]:
                continue
            name = str(r[0]).strip().upper()
            seg = str(r[2] or "")
            out[name] = (seg in ("Both", "Overlap only"), str(r[5] or "").strip())
        wb.close()
    except Exception as exc:                      # noqa: BLE001
        print("  note: could not read the overlap file (%s)" % exc)
    return out


# ── build ────────────────────────────────────────────────────────────────
def build(rows, overlap_map, target):
    months_present = sorted({r["_ym"] for r in rows})
    first, last_data = months_present[0], months_present[-1]

    today = date.today()
    open_month = "%04d-%02d" % (today.year, today.month)

    # Anchor on the newest COMPLETE month that actually carries rows.
    complete = [m for m in months_present if m < open_month]
    anchor = complete[-1] if complete else last_data

    t12 = set(m_range(m_add(anchor, -11), anchor))
    p12 = set(m_range(m_add(anchor, -23), m_add(anchor, -12)))
    d90 = set(m_range(m_add(anchor, -2), anchor))

    # Check for gaps all the way to the last complete calendar month, not just
    # to the anchor. July with no rows is exactly why the anchor fell back to
    # June, so checking only to the anchor would hide the thing that caused it.
    last_complete = m_add(open_month, -1)
    have = set(months_present)
    missing = [m for m in m_range(first, last_complete) if m not in have]

    # per partner
    P = collections.defaultdict(lambda: {
        "name": "", "life": 0.0, "t12": 0.0, "p12": 0.0,
        "last": "", "months": set(), "qtrs": set(), "namecount": collections.Counter()})
    for r in rows:
        p = P[r["_key"]]
        p["namecount"][r["partner_name"].strip().upper()] += 1
        p["life"] += r["_rev"]
        p["months"].add(r["_ym"])
        if r["_rev"] > 0:
            p["qtrs"].add(quarter_of(r["_ym"]))
        if r["_ym"] > p["last"]:
            p["last"] = r["_ym"]
        if r["_ym"] in t12:
            p["t12"] += r["_rev"]
        elif r["_ym"] in p12:
            p["p12"] += r["_rev"]

    aq = quarter_of(anchor)
    partners = []
    for key, p in P.items():
        name = p["namecount"].most_common(1)[0][0]
        is_overlap, desig = overlap_map.get(name, (False, ""))
        active90 = bool(p["months"] & d90)

        streak = 0
        while (aq - streak) in p["qtrs"]:
            streak += 1
        last4 = sum(1 for i in range(4) if (aq - i) in p["qtrs"])

        if active90:
            focus = "1. Active"
        elif is_overlap and p["t12"] > 0:
            focus = "2. Overlap, buying"
        elif is_overlap:
            focus = "3. Overlap, not buying"
        else:
            focus = "4. Other"

        if p["t12"] <= 0 and p["p12"] <= 0:
            status = "Inactive"
        elif p["p12"] <= 0:
            status = "New"
        elif p["t12"] >= p["p12"] * 1.05:
            status = "Green"
        elif p["t12"] <= p["p12"] * 0.95:
            status = "Red"
        else:
            status = "Yellow"

        quiet = len(m_range(m_add(p["last"], 1), anchor)) if p["last"] < anchor else 0

        partners.append({
            "name": name, "focus": focus,
            "overlap": "Yes" if is_overlap else "",
            "desig": desig, "last": p["last"], "quiet": quiet,
            "t12": round(p["t12"], 2), "p12": round(p["p12"], 2),
            "yoy": round(p["t12"] - p["p12"], 2),
            "status": status, "streak": streak, "last4": last4,
            "life": round(p["life"], 2),
        })
    partners.sort(key=lambda x: -x["t12"])

    # Month by month, so the answer to "this month was X, last month was Y" is
    # sitting on the dashboard instead of being derived on a call.
    rev_by_m = collections.defaultdict(float)
    for r in rows:
        rev_by_m[r["_ym"]] += r["_rev"]

    def yoy(m):
        prior = rev_by_m.get(m_add(m, -12), 0.0)
        return (rev_by_m[m] / prior - 1) if prior else None

    def mom(m):
        prior = rev_by_m.get(m_add(m, -1), 0.0)
        return (rev_by_m[m] / prior - 1) if prior else None

    ytd_months = [x for x in m_range(anchor[:4] + "-01", anchor)]
    ytd_now = sum(rev_by_m.get(x, 0.0) for x in ytd_months)
    ytd_prior = sum(rev_by_m.get(m_add(x, -12), 0.0) for x in ytd_months)

    # New and returning are the two counts that actually move month to month.
    # A per-partner red/yellow/green cannot work on a one month window: in
    # two recent back-to-back months only about 20 partners bought in both,
    # while about 55 went from nothing to something and the same number the
    # other way. Two thirds of the partners
    # active in the last year bought in exactly one month. Month over month at
    # the partner level would be almost entirely zero-to-something flips.
    first_buy = {}
    months_by_p = collections.defaultdict(set)
    for r in rows:
        if r["_rev"] <= 0:
            continue
        months_by_p[r["_key"]].add(r["_ym"])
        if r["_key"] not in first_buy or r["_ym"] < first_buy[r["_key"]]:
            first_buy[r["_key"]] = r["_ym"]

    def new_and_returning(m):
        new = ret = 0
        prior6 = set(m_range(m_add(m, -6), m_add(m, -1)))
        for k, ms in months_by_p.items():
            if m not in ms:
                continue
            if first_buy[k] == m:
                new += 1
            elif not (ms & prior6):
                ret += 1
        return new, ret

    monthly = []
    for m in m_range(m_add(anchor, -23), max(last_data, last_complete)):
        rev = rev_by_m.get(m, 0.0)
        cnt = len({r["_key"] for r in rows if r["_ym"] == m and r["_rev"] > 0})
        nw, rt = new_and_returning(m)
        monthly.append((m, round(rev, 2), cnt, m in missing, mom(m), yoy(m), nw, rt))

    # Quarter by quarter. Long tail partners buy too sporadically for a monthly
    # active count to mean much, but a quarter is long enough that a partner
    # buying on their normal cadence shows up. Active partner count per quarter
    # is the "growing the base" number leadership asks for.
    def q_months(y, n):
        return ["%04d-%02d" % (y, (n - 1) * 3 + i + 1) for i in range(3)]

    def q_stats(ms):
        rev = 0.0
        act, nw, ret = set(), 0, 0
        y0, m0 = int(ms[0][:4]), int(ms[0][5:7])
        t0 = y0 * 12 + m0 - 1
        prior2 = {"%04d-%02d" % ((t0 - i) // 12, (t0 - i) % 12 + 1)
                  for i in range(1, 7)}
        for k, ms_map in rev_by_pm.items():
            hit = any(ms_map.get(x, 0) > 0 for x in ms)
            rev += sum(ms_map.get(x, 0) for x in ms)
            if hit:
                act.add(k)
                if first_buy.get(k) in ms:
                    nw += 1
                elif not any(ms_map.get(x, 0) > 0 for x in prior2):
                    ret += 1
        return round(rev, 2), len(act), nw, ret

    rev_by_pm = collections.defaultdict(lambda: collections.defaultdict(float))
    for r in rows:
        rev_by_pm[r["_key"]][r["_ym"]] += r["_rev"]

    quarters = []
    ay, am = int(anchor[:4]), int(anchor[5:7])
    aq_n = (am - 1) // 3 + 1
    cur_q = ay * 4 + aq_n - 1
    open_q = None
    oy, om = int(open_month[:4]), int(open_month[5:7])
    open_q = oy * 4 + (om - 1) // 3
    for i in range(11, -1, -1):
        idx = open_q - i
        yy, nn = idx // 4, idx % 4 + 1
        ms = q_months(yy, nn)
        if ms[0] > last_data:
            continue
        rev, act, nw, ret = q_stats(ms)
        prev, pact, _, _ = q_stats(q_months(yy - 1, nn))
        partial = any((x > last_data) or (x in missing) or (x == open_month)
                      for x in ms)
        quarters.append({
            "label": "%d Q%d" % (yy, nn), "rev": rev, "active": act,
            "new": nw, "ret": ret,
            "rev_yoy": (rev / prev - 1) if prev else None,
            "act_delta": (act - pact) if pact else None,
            "partial": partial,
        })

    return {
        "quarters": quarters,
        "partners": partners, "monthly": monthly, "anchor": anchor,
        "last_data": last_data, "missing": missing, "target": target,
        "open_month": open_month,
        "open_rev": round(sum(r["_rev"] for r in rows if r["_ym"] == open_month), 2),
        "open_cnt": len({r["_key"] for r in rows
                         if r["_ym"] == open_month and r["_rev"] > 0}),
        "anchor_rev": round(rev_by_m.get(anchor, 0.0), 2),
        "prev_rev": round(rev_by_m.get(m_add(anchor, -1), 0.0), 2),
        "ly_rev": round(rev_by_m.get(m_add(anchor, -12), 0.0), 2),
        "anchor_mom": mom(anchor), "anchor_yoy": yoy(anchor),
        "ytd_now": round(ytd_now, 2), "ytd_prior": round(ytd_prior, 2),
        "ytd_months": len(ytd_months),
        "open_projection": project_open_month(rows, open_month),
    }


def project_open_month(rows, open_month):
    """
    Where the open month lands if it paces like a normal one. Returns None when
    the seasonal curve is unavailable or too few business days have passed for
    the divisor to be stable.
    """
    if not SEASONAL_CUM:
        return None
    y, mo = int(open_month[:4]), int(open_month[5:7])
    curve = SEASONAL_CUM.get(mo)
    if not curve:
        return None
    import calendar
    from datetime import date as _d
    ndays = calendar.monthrange(y, mo)[1]
    bdays = [dd for dd in range(1, ndays + 1) if _d(y, mo, dd).weekday() < 5]
    have = sorted({r["date"][8:10] for r in rows if r["_ym"] == open_month})
    if not have:
        return None
    through = int(have[-1])
    elapsed = len([dd for dd in bdays if dd <= through])
    if elapsed < 3:
        return None
    share = curve[min(elapsed, len(curve)) - 1]
    mtd = sum(r["_rev"] for r in rows if r["_ym"] == open_month)
    return round(mtd / share, 2) if share else None


# ── write ────────────────────────────────────────────────────────────────
def label(ym):
    return "%s %s" % (["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul",
                       "Aug", "Sep", "Oct", "Nov", "Dec"][int(ym[5:7]) - 1], ym[:4])


def write(d, out):
    wb = openpyxl.Workbook()

    # ---------- Partners ----------
    ws = wb.create_sheet("Partners")
    cols = ["Partner", "Focus", "Overlap", "Designation", "Last POS",
            "Months Quiet", "Trailing 12", "Prior 12", "YoY $", "YoY %",
            "Status", "Qtrs in a Row", "Qtrs of Last 4", "Lifetime"]
    ws.append(cols)
    for c in range(1, len(cols) + 1):
        cell = ws.cell(1, c)
        cell.font, cell.fill = F_HEAD, HEAD
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for p in d["partners"]:
        pct = (p["t12"] / p["p12"] - 1) if p["p12"] > 0 else None
        ws.append([p["name"], p["focus"], p["overlap"], p["desig"],
                   label(p["last"]) if p["last"] else "", p["quiet"],
                   p["t12"], p["p12"], p["yoy"], pct,
                   p["status"], p["streak"], p["last4"], p["life"]])

    fillmap = {"Green": GREEN, "Yellow": YELLOW, "Red": RED, "Inactive": GREY}
    for i in range(len(d["partners"])):
        r = i + 2
        for c in range(1, len(cols) + 1):
            ws.cell(r, c).font = F_BODY
        for c in (7, 8, 9, 14):
            ws.cell(r, c).number_format = '$#,##0;($#,##0);-'
        ws.cell(r, 10).number_format = '0.0%;(0.0%);-'
        for c in (6, 12, 13):
            ws.cell(r, c).alignment = Alignment(horizontal="center")
        f = fillmap.get(d["partners"][i]["status"])
        if f:
            ws.cell(r, 11).fill = f
        ws.cell(r, 11).alignment = Alignment(horizontal="center")

    n = len(d["partners"]) + 1
    ws.auto_filter.ref = "A1:N%d" % n
    ws.freeze_panes = "B2"
    for c, w in zip("ABCDEFGHIJKLMN",
                    [40, 20, 8, 22, 11, 8, 13, 12, 12, 9, 10, 8, 8, 14]):
        ws.column_dimensions[c].width = w
    ws.row_dimensions[1].height = 30

    # ---------- Monthly ----------
    wm = wb.create_sheet("Monthly")
    wm.append(["Month", "Revenue", "vs Prior Month", "vs Same Month Last Year",
               "Partners Who Bought", "First Time Ever", "Back After 6+ Mo Quiet",
               "Note"])
    for c in range(1, 9):
        wm.cell(1, c).font, wm.cell(1, c).fill = F_HEAD, HEAD
        wm.cell(1, c).alignment = Alignment(horizontal="center")
    for m, rev, cnt, gap, mm, yy, nw, rt in d["monthly"]:
        wm.append([label(m), rev, mm, yy, cnt, nw, rt,
                   "NO DATA IN LEDGER" if gap else
                   ("open month, partial" if m == d["open_month"] else "")])
    for r in range(2, len(d["monthly"]) + 2):
        for c in range(1, 9):
            wm.cell(r, c).font = F_BODY
        wm.cell(r, 2).number_format = '$#,##0'
        for c in (3, 4):
            wm.cell(r, c).number_format = '0.0%;(0.0%);-'
            wm.cell(r, c).alignment = Alignment(horizontal="center")
            v = wm.cell(r, c).value
            if isinstance(v, (int, float)):
                wm.cell(r, c).fill = GREEN if v > 0.05 else (RED if v < -0.05 else YELLOW)
        for c in (5, 6, 7):
            wm.cell(r, c).alignment = Alignment(horizontal="center")
        if wm.cell(r, 8).value == "NO DATA IN LEDGER":
            for c in range(1, 9):
                wm.cell(r, c).fill = WARN
    wm.freeze_panes = "A2"
    for c, w in zip("ABCDEFGH", [12, 14, 15, 22, 20, 15, 21, 20]):
        wm.column_dimensions[c].width = w

    ch = BarChart()
    ch.type, ch.style, ch.title = "col", 10, "Long tail revenue by month"
    ch.y_axis.title, ch.x_axis.title = "Revenue", None
    ch.height, ch.width = 7.5, 26
    ch.add_data(Reference(wm, min_col=2, min_row=1, max_row=len(d["monthly"]) + 1),
                titles_from_data=True)
    ch.set_categories(Reference(wm, min_col=1, min_row=2, max_row=len(d["monthly"]) + 1))
    ch.legend = None
    wm.add_chart(ch, "J2")

    # ---------- Quarterly ----------
    wq = wb.create_sheet("Quarterly")
    wq.append(["Quarter", "Revenue", "vs Same Q Last Year", "Active Partners",
               "Active vs Last Year", "First Time Ever", "Back After 6+ Mo Quiet",
               "Note"])
    for c in range(1, 9):
        wq.cell(1, c).font, wq.cell(1, c).fill = F_HEAD, HEAD
        wq.cell(1, c).alignment = Alignment(horizontal="center", vertical="center",
                                            wrap_text=True)
    for q in d["quarters"]:
        wq.append([q["label"], q["rev"], q["rev_yoy"], q["active"], q["act_delta"],
                   q["new"], q["ret"],
                   "PARTIAL QUARTER, do not compare" if q["partial"] else ""])
    for i, q in enumerate(d["quarters"]):
        r = i + 2
        for c in range(1, 9):
            wq.cell(r, c).font = F_BODY
        wq.cell(r, 2).number_format = '$#,##0'
        wq.cell(r, 3).number_format = '0.0%;(0.0%);-'
        wq.cell(r, 5).number_format = '+0;-0;0'
        for c in (3, 4, 5, 6, 7):
            wq.cell(r, c).alignment = Alignment(horizontal="center")
        if q["partial"]:
            for c in range(1, 9):
                wq.cell(r, c).fill = GREY
        else:
            v = q["rev_yoy"]
            if isinstance(v, float):
                wq.cell(r, 3).fill = GREEN if v > 0.05 else (RED if v < -0.05 else YELLOW)
            dv = q["act_delta"]
            if isinstance(dv, int):
                wq.cell(r, 5).fill = GREEN if dv > 0 else (RED if dv < 0 else YELLOW)
    wq.freeze_panes = "A2"
    wq.row_dimensions[1].height = 30
    for c, w in zip("ABCDEFGH", [12, 14, 19, 15, 17, 15, 21, 26]):
        wq.column_dimensions[c].width = w

    chq = BarChart()
    chq.type, chq.style = "col", 10
    chq.title = "Active partners per quarter"
    chq.height, chq.width = 7.5, 20
    chq.add_data(Reference(wq, min_col=4, min_row=1, max_row=len(d["quarters"]) + 1),
                 titles_from_data=True)
    chq.set_categories(Reference(wq, min_col=1, min_row=2,
                                 max_row=len(d["quarters"]) + 1))
    chq.legend = None
    wq.add_chart(chq, "J2")

    # ---------- Dashboard ----------
    ws = wb["Sheet"]
    ws.title = "Dashboard"
    P = "Partners"
    NROWS = len(d["partners"]) + 1          # last used row on the Partners tab

    ws["A1"] = "Long Tail Partner Dashboard"
    ws["A1"].font = F_TITLE
    ws["A2"] = ("KPIs close on %s.  Ledger has data through %s.  %s so far: $%s "
                "across %d partners.  Built %s." %
                (label(d["anchor"]), label(d["last_data"]), label(d["open_month"]),
                 "{:,.0f}".format(d["open_rev"]), d["open_cnt"],
                 date.today().isoformat()))
    ws["A2"].font = F_NOTE

    row = 4
    if d["missing"]:
        ws.cell(row, 1, "MISSING DATA: no ledger rows for %s. Every trailing-12 and "
                        "year-over-year number below is understated until you process "
                        "those POS files and re-run." %
                        ", ".join(label(m) for m in d["missing"]))
        ws.cell(row, 1).font = Font(name="Arial", size=10, bold=True, color="9C0006")
        for c in range(1, 9):
            ws.cell(row, c).fill = WARN
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        row += 2

    def block(title, r):
        ws.cell(r, 1, title).font = F_LABEL
        ws.cell(r, 1).fill = ACCENT
        for c in range(1, 9):
            ws.cell(r, c).fill = ACCENT
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=8)
        return r + 1

    def kpi(r, c, big, lab, fmt=None):
        ws.cell(r, c, big)
        ws.cell(r, c).font = F_BIG
        ws.cell(r, c).alignment = Alignment(horizontal="center")
        if fmt:
            ws.cell(r, c).number_format = fmt
        ws.cell(r + 1, c, lab)
        ws.cell(r + 1, c).font = F_BODY
        ws.cell(r + 1, c).alignment = Alignment(horizontal="center", wrap_text=True)
        for rr in (r, r + 1):
            ws.cell(rr, c).fill = FOG
            ws.cell(rr, c).border = BOX

    row = block("MONTH BY MONTH  (say this one out loud)", row)
    kpi(row, 1, d["anchor_rev"], label(d["anchor"]), '$#,##0')
    kpi(row, 3, d["prev_rev"], label(m_add(d["anchor"], -1)), '$#,##0')
    kpi(row, 5, d["anchor_mom"] if d["anchor_mom"] is not None else "n/a",
        "Change vs prior month", '0.0%;(0.0%)')
    kpi(row, 7, d["anchor_yoy"] if d["anchor_yoy"] is not None else "n/a",
        "vs %s" % label(m_add(d["anchor"], -12)), '0.0%;(0.0%)')
    row += 3

    this_year = [q for q in d["quarters"] if q["label"].startswith(d["anchor"][:4])]
    if this_year:
        row = block("QUARTER BY QUARTER, %s  (active partners is the base)"
                    % d["anchor"][:4], row)
        for i, q in enumerate(this_year[:4]):
            c = 1 + i * 2
            kpi(row, c, q["active"],
                "%s active%s" % (q["label"], "  (partial)" if q["partial"] else ""))
            ws.cell(row + 2, c, q["rev"])
            ws.cell(row + 2, c).number_format = '$#,##0'
            ws.cell(row + 2, c).font = F_BODY
            ws.cell(row + 2, c).alignment = Alignment(horizontal="center")
            ws.cell(row + 2, c).fill = FOG
            ws.cell(row + 2, c).border = BOX
            if not q["partial"] and isinstance(q["act_delta"], int):
                ws.cell(row, c).fill = GREEN if q["act_delta"] > 0 else (
                    RED if q["act_delta"] < 0 else YELLOW)
        row += 4

    row = block("YEAR TO DATE AND OPEN MONTH", row)
    kpi(row, 1, d["ytd_now"], "%s YTD (%d months)" % (d["anchor"][:4], d["ytd_months"]),
        '$#,##0')
    kpi(row, 3, d["ytd_prior"], "Same months last year", '$#,##0')
    kpi(row, 5, (d["ytd_now"] / d["ytd_prior"] - 1) if d["ytd_prior"] else "n/a",
        "YTD change", '0.0%;(0.0%)')
    kpi(row, 7, d["open_projection"] if d["open_projection"] else d["open_rev"],
        "%s, %s" % (label(d["open_month"]),
                    "projected full month" if d["open_projection"] else "so far"),
        '$#,##0')
    row += 3

    row = block("PARTNER COUNTS", row)
    kpi(row, 1, '=COUNTIF(%s!B:B,"1. Active")' % P, "Bought in last 90 days")
    kpi(row, 3, d["target"], "Target (leadership)")
    kpi(row, 5, '=COUNTIF(%s!G:G,">0")' % P, "Bought in last 12 months")
    kpi(row, 7, '=COUNTA(%s!A2:A%d)' % (P, NROWS), "Partners in ledger, all time")
    row += 3

    row = block("REVENUE, TRAILING 12 VS PRIOR 12", row)
    kpi(row, 1, '=SUM(%s!G:G)' % P, "Trailing 12", '$#,##0')
    kpi(row, 3, '=SUM(%s!H:H)' % P, "Prior 12", '$#,##0')
    kpi(row, 5, '=IF(C%d=0,0,A%d/C%d-1)' % (row, row, row), "Change", '0.0%;(0.0%)')
    kpi(row, 7, '=A%d-C%d' % (row, row), "Dollars", '$#,##0;($#,##0)')
    row += 3

    row = block("GREEN, YELLOW, RED  (per partner, 12 months vs the 12 before)", row)
    for i, (lab_, fill) in enumerate([("Green", GREEN), ("Yellow", YELLOW),
                                      ("Red", RED), ("New", None)]):
        c = 1 + i * 2
        kpi(row, c, '=COUNTIF(%s!K:K,"%s")' % (P, lab_), lab_ + " partners")
        if fill:
            ws.cell(row, c).fill = fill
    row += 3

    row = block("THE THREE FOCUS GROUPS", row)
    for i, (key, lab_) in enumerate([("1. Active", "Active partners"),
                                     ("2. Overlap, buying", "Overlap resellers buying"),
                                     ("3. Overlap, not buying", "Overlap resellers not buying"),
                                     ("4. Other", "Everyone else")]):
        c = 1 + i * 2
        kpi(row, c, '=COUNTIF(%s!B:B,"%s")' % (P, key), lab_)
    row += 3

    row = block("CONSISTENCY", row)
    kpi(row, 1, '=COUNTIF(%s!L:L,">=4")' % P, "4+ quarters in a row")
    kpi(row, 3, '=COUNTIF(%s!M:M,4)' % P, "Bought all of last 4 quarters")
    kpi(row, 5, '=COUNTIF(%s!M:M,3)' % P, "3 of last 4 quarters")
    kpi(row, 7, '=COUNTIF(%s!F:F,">=24")' % P, "Quiet 24 months or more")
    row += 4

    ws.cell(row, 1, "How to read this").font = F_LABEL
    row += 1
    for line in [
        "Three lenses, on purpose. Year over year per partner shows who is growing. Quarter by quarter shows whether the base is widening. Month by month is what you say on a call.",
        "Active partners per quarter is the base number. A quarter is the shortest window where a long tail partner buying on their normal cadence still shows up, so the count means something.",
        "A partial quarter is greyed out on the Quarterly tab. Never compare it to a full one.",
        "The colors are a 12-month comparison on purpose. A one-month version does not work: in two recent back-to-back months only about 20 partners bought in both, and two thirds of active partners buy in a single month all year. Month to month, a partner is mostly on or off, not up or down.",
        "For month-to-month movement use the Monthly tab: revenue, how many partners bought, how many were first-time, and how many came back after six quiet months. Those counts move every month and mean something.",
        "Month by month is the number to quote on a call. Trailing 12 smooths out one bad month and is the number to quote in a review.",
        "The open month projection paces the month-to-date against how that calendar month normally books, from tracker.py. July back-loads, August front-loads. Do not compare a part-month to a full month without it.",
        "Every number recalculates from the Partners tab. Filter that tab and the counts here do not move; they always cover all partners.",
        "Trailing 12 = the twelve months ending %s. Prior 12 = the twelve before that." % label(d["anchor"]),
        "Green means trailing 12 beat prior 12 by more than 5 percent. Red means it fell more than 5 percent. Yellow is in between.",
        "New = bought in the last twelve months with nothing in the twelve before. Inactive = nothing in either window.",
        "Red includes partners who went to zero, not only partners who shrank. That is the point of the color.",
        "Active means POS in the last three complete months, which is the 90 day window.",
        "Overlap flag comes from overlap_partner_segmentation.xlsx. Refresh that file when the overlap list changes.",
        "A partner counted twice under two spellings gets merged in KEY_MERGES at the top of longtail_dashboard.py.",
    ]:
        ws.cell(row, 1, line).font = F_BODY
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=8)
        row += 1

    for c, w in zip("ABCDEFGH", [22, 3, 22, 3, 22, 3, 22, 3]):
        ws.column_dimensions[c].width = w
    ws.sheet_view.showGridLines = False

    try:
        wb.save(out)
    except PermissionError:
        base, ext = os.path.splitext(out)
        alt = "%s_%s%s" % (base, time.strftime("%Y%m%d_%H%M%S"), ext)
        wb.save(alt)
        print("")
        print("  %s is open in Excel, so it could not be overwritten." % os.path.basename(out))
        print("  Saved here instead: %s" % os.path.basename(alt))
        print("  Close the workbook and re-run to write the normal file.")
        return alt
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=300)
    ap.add_argument("--out", default=os.path.join(HERE, "longtail_dashboard.xlsx"))
    ap.add_argument("--ledger", default=LEDGER)
    a = ap.parse_args()

    if not os.path.exists(a.ledger):
        print("No ledger at %s. Run the scrubber first." % a.ledger)
        return 1

    rows = load_ledger(a.ledger)
    overlap = load_overlap(OVERLAP_FILE)
    d = build(rows, overlap, a.target)
    write(d, a.out)

    print("Dashboard written: %s" % a.out)
    print("  KPIs close on %s, ledger runs to %s" % (d["anchor"], d["last_data"]))
    print("  %d partners, %d active in last 90 days" %
          (len(d["partners"]), sum(1 for p in d["partners"] if p["focus"] == "1. Active")))
    if d["missing"]:
        print("  WARNING missing months: %s" % ", ".join(d["missing"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
