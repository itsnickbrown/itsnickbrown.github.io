"""
build_tracker_demo.py
Builds the daily partner tracker page from the POS ledger. Public demo version
of tracker.py: reads the ledger instead of 100+ distributor snapshot files, but
produces the same charts, KPIs and the seasonal month-end projection.

    python build_tracker_demo.py --ledger synthetic_ledger.csv --out tracker.html
"""
import csv, json, argparse, calendar, collections, datetime as dt

# Median share of a month's revenue booked by business day N (built from five
# years of history in production). July back-loads, August front-loads.
def seasonal_curve(month):
    skew = {7: 1.35, 8: .8, 9: 1.15, 12: 1.25, 3: 1.2, 6: 1.2}.get(month, 1.0)
    days = 22
    return [round(((d + 1) / days) ** skew, 4) for d in range(days)]


def bdays(y, m, through=None):
    n = calendar.monthrange(y, m)[1]
    return [d for d in range(1, (through or n) + 1) if dt.date(y, m, d).weekday() < 5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="synthetic_ledger.csv")
    ap.add_argument("--template", default="tracker_template.html")
    ap.add_argument("--out", default="tracker.html")
    ap.add_argument("--since", default="2026-07-01")
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.ledger, encoding="utf-8"))]
    for r in rows:
        r["rev"] = float(r["revenue"] or 0)
    daily_rows = [r for r in rows if r["date"] >= a.since]
    as_of = max(r["date"] for r in rows)
    y, m = int(as_of[:4]), int(as_of[5:7])
    open_ym = as_of[:7]

    # daily new revenue, one point per business day
    by_day = collections.defaultdict(float)
    for r in daily_rows:
        by_day[r["date"]] += r["rev"]
    d0 = dt.date.fromisoformat(a.since)
    d1 = dt.date.fromisoformat(as_of)
    daily, cum, run = [], [], 0.0
    while d0 <= d1:
        if d0.weekday() < 5:
            k = d0.isoformat()
            daily.append({"date": k, "revenue": round(by_day.get(k, 0), 2)})
            run += by_day.get(k, 0)
            cum.append({"date": k, "cumulative": round(run, 2)})
        d0 += dt.timedelta(days=1)

    # MTD revenue and MTD partners by month
    mtd, pmtd = {}, {}
    for ym in sorted({x["date"][:7] for x in daily}):
        label = dt.date(int(ym[:4]), int(ym[5:]), 1).strftime("%b %Y")
        tot, seen, s1, s2 = 0.0, set(), [], []
        for x in [x for x in daily if x["date"].startswith(ym)]:
            tot += x["revenue"]
            seen |= {r["partner_key"] for r in daily_rows if r["date"] == x["date"]}
            dnum = int(x["date"][8:])
            s1.append({"day": dnum, "mtd": round(tot, 2)})
            s2.append({"day": dnum, "partners": len(seen)})
        mtd[label], pmtd[label] = s1, s2

    # 24-month partner history
    hist = collections.defaultdict(lambda: [set(), 0.0])
    for r in rows:
        hist[r["date"][:7]][0].add(r["partner_key"])
        hist[r["date"][:7]][1] += r["rev"]
    months = sorted(hist)[-25:-1]
    partner_hist = [{"month": k, "partners": len(hist[k][0]), "revenue": round(hist[k][1], 2), "gap": False}
                    for k in months]

    # partner totals since tracking started, top 5 daily lines, top purchases
    tot = collections.defaultdict(lambda: {"rev": 0.0, "orders": set(), "first": "9", "last": ""})
    name = {}
    for r in daily_rows:
        t = tot[r["partner_key"]]
        name[r["partner_key"]] = r["partner_name"]
        t["rev"] += r["rev"]; t["orders"].add(r["doc_no"])
        t["first"] = min(t["first"], r["date"]); t["last"] = max(t["last"], r["date"])
    ranked = sorted(tot, key=lambda k: -tot[k]["rev"])
    totals = [{"n": name[k], "o": len(tot[k]["orders"]), "r": round(tot[k]["rev"], 2),
               "f": tot[k]["first"], "l": tot[k]["last"]} for k in ranked[:20]]
    top5 = {}
    for k in ranked[:5]:
        pd = collections.defaultdict(float)
        for r in daily_rows:
            if r["partner_key"] == k:
                pd[r["date"]] += r["rev"]
        top5[name[k]] = [{"date": x["date"], "revenue": round(pd.get(x["date"], 0), 2)} for x in daily]
    recent = [r for r in daily_rows if r["date"] >= (d1 - dt.timedelta(days=10)).isoformat()]
    buys = sorted(recent, key=lambda r: -r["rev"])[:10]
    top_buys = [{"p": r["partner_name"], "d": r["distributor"], "part": r["part_no"], "q": r["qty"],
                 "r": r["rev"], "eu": r["end_user"]} for r in buys]

    # open-month projection: MTD divided by the share a normal month books by now
    mtd_rev = sum(x["revenue"] for x in daily if x["date"].startswith(open_ym))
    elapsed = len(bdays(y, m, int(as_of[8:])))
    remaining = len(bdays(y, m)) - elapsed
    curve = seasonal_curve(m)
    share = curve[min(elapsed, len(curve)) - 1]
    proj = mtd_rev / share if elapsed >= 3 and share else None
    flat = mtd_rev / elapsed * (elapsed + remaining) if elapsed else 0

    data = {"asOf": as_of, "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "daily": daily, "cumul": cum, "monthly": mtd, "partnerMtd": pmtd, "partnerHist": partner_hist,
            "top5": top5, "totals": totals, "topBuys": top_buys, "openMonth": open_ym,
            "kpi": {"mtd": round(mtd_rev, 2), "partnersMtd": len({r["partner_key"] for r in daily_rows if r["date"].startswith(open_ym)}),
                    "unique": len(tot), "ledgerPartners": len({r["partner_key"] for r in rows}),
                    "elapsed": elapsed, "remaining": remaining,
                    "runRate": round(mtd_rev / elapsed, 2) if elapsed else 0,
                    "proj": round(proj, 2) if proj else None, "flat": round(flat, 2), "share": share,
                    "lastFull": partner_hist[-1]}}
    tpl = open(a.template, encoding="utf-8").read()
    open(a.out, "w", encoding="utf-8").write(
        tpl.replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":")).replace("</", "<\\/")))
    print("wrote", a.out, "| as of", as_of, "| projection", data["kpi"]["proj"])


if __name__ == "__main__":
    main()
