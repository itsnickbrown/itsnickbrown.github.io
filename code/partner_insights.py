"""
partner_insights.py
-------------------
Builds partner_insights.html from the POS ledger CSV. One page to answer:
who is buying, who is new, who keeps coming back, who went quiet, and how
this month compares to last month and last year. Every table drills down to
the end users, products and orders behind each partner.

Runs inside the nightly update after the dashboard. Safe to run on its own:
  python partner_insights.py
  python partner_insights.py --out "C:/somewhere/partner_insights.html"

Definitions (a partner "bought" in a month if it has any ledger row that month,
credits included):
  Repeat     bought this month AND in at least one of the 12 months before it
  Brand new  first ledger row ever is this month (history starts Jan 2020)
  Returning  bought before, but nothing in the 12 months before this month
  Growing    trailing 12 revenue beats the prior 12 by more than 5%
  Declining  trailing 12 revenue falls more than 5% short of the prior 12
  Gone quiet bought in 2+ of the 12 months ending 3 months ago, nothing in the
             last 3, and still bought something in the trailing 12

The three follow-up buckets on the partner table never overlap. Each partner
lands in one, checked in this order: Stopped, then Gone quiet, then Declining.

Partners whose only distributor is the end-user-reporting distributor are left
out. That distributor puts the end user in the reseller field, so those records
are customers, not resellers.

Orders = distinct invoice numbers. Corporate seed rows without an invoice count
one order per date + end user + distributor.

The page does its month math in the browser from the embedded data, so the
month picker can re-anchor every card, chart and table without a rebuild.
"""

import os, sys, csv, json, re, argparse
from datetime import date, datetime
from collections import defaultdict, Counter

HERE = os.path.dirname(os.path.abspath(__file__))
SEED = "SEED REPORT"
LINES_FROM = "2024-01"          # line-level detail kept from this month on


def canon_distributor(name):
    return str(name or "").strip().upper()

# Same merges the dashboard uses, so a partner is one partner everywhere.
# Public version: example entries only.
KEY_MERGES = {"northwind data group fka northwind": "northwind data group"}
END_USER_KEYS = set()
NAME_OVERRIDES = {}
EU_REPORTING_DIST = "DIST EAST"   # distributor that puts the end user in the reseller field


def family(part):
    """Map a part number prefix to a product line. Real prefixes replaced."""
    p = (part or "").upper().strip()
    if re.search(r"\dYS", p):
        return "Support contracts"
    for prefix, fam in (("LT-100G", "Link tester 100G"), ("LT-10G", "Link tester 10G"),
                        ("LT-", "Link tester"), ("WA-", "Wi-Fi analyzer"),
                        ("NA-", "Network analyzer"), ("SA-", "Security assessment"),
                        ("CT-", "Cable tester"), ("CL-", "Cloud subscription")):
        if p.startswith(prefix):
            return fam
    return "Accessories / other"


def fnum(v):
    try:
        return float(v or 0)
    except ValueError:
        return 0.0


def norm_doc(v):
    v = (v or "").strip()
    return v[:-2] if v.endswith(".0") else v


def ym_add(ym, n):
    y, m = int(ym[:4]), int(ym[5:7]) - 1 + n
    return f"{y + m // 12:04d}-{m % 12 + 1:02d}"


def load(path):
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            d = (r.get("date") or "")[:10]
            k = (r.get("partner_key") or "").strip()
            if len(d) != 10 or not k:
                continue
            rows.append({
                "date": d, "ym": d[:7], "key": KEY_MERGES.get(k, k),
                "name": (r.get("partner_name") or r.get("raw_name") or k).strip(),
                "state": (r.get("state") or "").strip(),
                "doc": norm_doc(r.get("doc_no")),
                "part": (r.get("part_no") or "").strip(),
                "qty": fnum(r.get("qty")), "rev": fnum(r.get("revenue")),
                "eu": " ".join((r.get("end_user") or "").split()),
                "dist": canon_distributor(r.get("distributor")),
                "seed": (r.get("source_file") or "") == SEED,
            })
    return rows


def build(rows, snapshot_mtd):
    # Partners seen only through the end-user-reporting distributor.
    dists = defaultdict(set)
    for r in rows:
        dists[r["key"]].add(r["dist"])
    eu_only = {k for k, s in dists.items() if s == {EU_REPORTING_DIST}}
    # End users reported as resellers (END_USER_KEYS above).
    rows = [r for r in rows if r["key"] not in eu_only and r["key"] not in END_USER_KEYS]
    rows.sort(key=lambda r: r["date"])

    first_ym, last_ym = rows[0]["ym"], rows[-1]["ym"]
    months = [first_ym]
    while months[-1] < last_ym:
        months.append(ym_add(months[-1], 1))
    idx = {m: i for i, m in enumerate(months)}
    as_of = rows[-1]["date"]

    P = {}
    E = {}
    for r in rows:
        i = idx[r["ym"]]
        p = P.get(r["key"])
        if p is None:
            p = P[r["key"]] = {"names": Counter(), "states": Counter(), "dists": Counter(),
                               "m": defaultdict(lambda: [0.0, set()]), "eu": {},
                               "px": defaultdict(lambda: defaultdict(float)),
                               "fd": r["date"], "ld": r["date"], "life": 0.0}
        p["names"][r["name"]] += 1
        if r["state"]:
            p["states"][r["state"]] += 1
        p["dists"][r["dist"]] += 1
        oid = r["doc"] or f'{r["date"]}|{r["eu"]}|{r["dist"]}'
        p["m"][i][0] += r["rev"]
        p["m"][i][1].add(oid)
        p["ld"] = r["date"]
        p["life"] += r["rev"]
        p["px"][family(r["part"])][r["date"][:4]] += r["rev"]
        if r["eu"]:
            eu = p["eu"].setdefault(r["eu"].upper(), {"n": r["eu"], "rev": 0.0, "o": set(),
                                                    "fd": r["date"], "ld": r["date"]})
            eu["rev"] += r["rev"]; eu["o"].add(oid); eu["ld"] = r["date"]

            ek = re.sub(r"[^A-Z0-9]+", " ", r["eu"].upper()).strip()
            if ek:
                e = E.get(ek)
                if e is None:
                    e = E[ek] = {"names": Counter(), "p": Counter(),
                                 "m": defaultdict(lambda: [0.0, set()]),
                                 "fd": r["date"], "ld": r["date"]}
                e["names"][r["eu"]] += 1
                e["p"][r["key"]] += r["rev"] if r["rev"] > 0 else 0.01
                e["m"][i][0] += r["rev"]
                e["m"][i][1].add(oid)
                e["ld"] = r["date"]

    keys = sorted(P, key=lambda k: -P[k]["life"])
    pidx = {k: n for n, k in enumerate(keys)}

    def best_name(c):
        top = c.most_common()
        hi = top[0][1]
        return max((n for n, v in top if v == hi), key=len)

    partners = []
    for k in keys:
        p = P[k]
        eus = sorted(p["eu"].values(), key=lambda e: -e["rev"])
        partners.append({
            "k": k, "n": NAME_OVERRIDES.get(k) or best_name(p["names"]),
            "s": p["states"].most_common(1)[0][0] if p["states"] else "",
            "d": " / ".join(d for d, _ in p["dists"].most_common()),
            "fd": p["fd"], "ld": p["ld"], "f": min(p["m"]),
            "m": [[i, round(v[0], 2), len(v[1])] for i, v in sorted(p["m"].items())],
            "eu": [[e["n"], round(e["rev"], 2), len(e["o"]), e["fd"], e["ld"]] for e in eus[:12]],
            "euN": len(eus),
            "px": {fam: {y: round(v, 2) for y, v in ys.items()} for fam, ys in p["px"].items()},
        })

    end_users = []
    for ek, e in E.items():
        end_users.append({
            "n": best_name(e["names"]),
            "p": [pidx[k] for k, _ in e["p"].most_common(3)],
            "pN": len(e["p"]),
            "fd": e["fd"], "ld": e["ld"], "f": min(e["m"]),
            "m": [[i, round(v[0], 2), len(v[1])] for i, v in sorted(e["m"].items())],
        })

    lines = [[r["date"], pidx[r["key"]], r["doc"], r["part"], family(r["part"]),
              round(r["qty"], 2), round(r["rev"], 2), r["eu"], r["dist"]]
             for r in rows if r["ym"] >= LINES_FROM]

    # Open month: the current calendar month, if the ledger has reached it.
    today_ym = os.environ.get("DEMO_TODAY", date.today().strftime("%Y-%m"))
    open_idx = idx[last_ym] if last_ym >= today_ym else -1
    anchor = open_idx - 1 if open_idx > 0 else len(months) - 1

    # Like-for-like pace for the open month. Only possible against months that
    # carry real invoice dates; corporate seed months are all dated the 15th.
    pace = None
    if open_idx >= 0:
        day = int(as_of[8:10])

        def through(ym):
            sub = [r for r in rows if r["ym"] == ym]
            if not sub or all(r["seed"] for r in sub):
                return None
            sub = [r for r in sub if int(r["date"][8:10]) <= day]
            return {"partners": len({r["key"] for r in sub}),
                    "rev": round(sum(r["rev"] for r in sub), 2)}
        pace = {"day": day, "pm": through(ym_add(last_ym, -1)), "py": through(ym_add(last_ym, -12))}

    # Ledger fallback for the MTD chart when snapshots are not readable.
    if not snapshot_mtd:
        snapshot_mtd = {}
        for ym in months[-5:]:
            sub = [r for r in rows if r["ym"] == ym]
            if not sub or all(r["seed"] for r in sub):
                continue
            seen, pts = set(), []
            for r in sub:
                seen.add(r["key"])
                dnum = int(r["date"][8:10])
                if pts and pts[-1]["day"] == dnum:
                    pts[-1]["partners"] = len(seen)
                else:
                    pts.append({"day": dnum, "partners": len(seen)})
            y, m = ym.split("-")
            snapshot_mtd[date(int(y), int(m), 1).strftime("%b %Y")] = pts

    return {
        "months": months, "asOf": as_of, "openIdx": open_idx, "anchor": anchor,
        "partners": partners, "endUsers": end_users, "lines": lines,
        "linesFrom": LINES_FROM, "pace": pace, "mtd": snapshot_mtd,
        "euOnly": len(eu_only), "rows": len(rows),
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


def snapshot_mtd(folder, keep=5):
    """Partners MTD curves from the scrubber snapshots, same source as the
    tracker chart. Returns {} on any problem and the ledger fallback is used."""
    try:
        import tracker
        files = tracker.find_snapshot_files(folder)
        snaps = []
        for d, path in files:
            try:
                partners, orders_map, _, _ = tracker.read_snapshot(path)
                snaps.append((d, partners, orders_map))
            except Exception:
                pass
        mtd = tracker.build_partner_mtd(snaps)
        order = sorted(mtd, key=lambda k: datetime.strptime(k, "%b %Y"))[-keep:]
        return {k: mtd[k] for k in order}
    except Exception as e:
        print(f"  Note: snapshot MTD chart falling back to ledger dates ({e})")
        return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=os.path.join(HERE, "synthetic_ledger.csv"))
    ap.add_argument("--out", default=os.path.join(HERE, "partner_insights.html"))
    ap.add_argument("--no-snapshots", action="store_true")
    ap.add_argument("--template", default=os.path.join(HERE, "partner_insights_template.html"))
    a = ap.parse_args()

    if not os.path.exists(a.ledger):
        print(f"Ledger not found: {a.ledger}")
        sys.exit(1)

    print("Building partner insights...")
    rows = load(a.ledger)
    mtd = {} if a.no_snapshots else snapshot_mtd(HERE)
    data = build(rows, mtd)

    tpl_path = a.template
    with open(tpl_path, encoding="utf-8") as f:
        tpl = f.read()
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    html = tpl.replace("/*__DATA__*/null", payload)

    try:
        with open(a.out, "w", encoding="utf-8") as f:
            f.write(html)
        out = a.out
    except PermissionError:
        out = a.out.replace(".html", datetime.now().strftime("_%Y%m%d_%H%M%S.html"))
        with open(out, "w", encoding="utf-8") as f:
            f.write(html)
        print("  partner_insights.html was locked, saved a copy instead.")

    m = data["months"]
    print(f"Wrote: {out}")
    print(f"  POS through {data['asOf']} | {len(data['partners']):,} partners | "
          f"{len(data['endUsers']):,} end users | anchor month {m[data['anchor']]}")


if __name__ == "__main__":
    main()
