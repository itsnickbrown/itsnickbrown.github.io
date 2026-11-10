"""
dedupe_ledger.py
----------------
One-time cleanup for the double counting found on 2026-08-28.

Every cumulative distributor file re-added invoice lines that were already in
the ledger, because make_line_id hashed raw Excel values whose types drifted
between exports (line_no 3 vs 3.0). One month read 93% high because of it. One
distributor also renamed a reseller mid-month, which put the same small sale in
four times under two spellings.

pos_common.make_line_id is fixed, so this will not happen again. This script
cleans what is already in the ledger.

Rows from the corporate seed are LEFT ALONE. They have no line_no and only half
carry a doc_no, so two separate units of the same part to the same end user in
the same month cannot be told apart from a duplicate. Deduping those would
delete real revenue.

    python dedupe_ledger.py --dry-run
    python dedupe_ledger.py
"""

import os, csv, sys, argparse, collections

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "synthetic_ledger.csv")
SEED = "SEED REPORT"


def norm(v):
    s = str(v or "").strip()
    if s.lower() in ("nan", "nat", "none"):
        return ""
    try:
        f = float(s)
    except (TypeError, ValueError):
        return s.upper()
    return str(int(f)) if f == int(f) else ("%.4f" % f).rstrip("0").rstrip(".")


def key(r):
    """Distributor + invoice + line. Unique inside one distributor. The reseller
    name is deliberately not in here."""
    return (norm(r.get("distributor")), norm(r.get("doc_no")), norm(r.get("line_no")),
            str(r.get("date", ""))[:10], norm(r.get("part_no")),
            norm(r.get("qty")), norm(r.get("revenue")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--ledger", default=LEDGER)
    a = ap.parse_args()

    with open(a.ledger, newline="", encoding="utf-8-sig") as fh:
        rd = csv.DictReader(fh)
        cols, rows = rd.fieldnames, list(rd)

    seen, out, dropped = set(), [], []
    for r in rows:
        if r.get("source_file") == SEED or not (norm(r.get("doc_no")) and norm(r.get("line_no"))):
            out.append(r)
            continue
        k = key(r)
        if k in seen:
            dropped.append(r)
        else:
            seen.add(k)
            out.append(r)

    money = sum(float(r.get("revenue") or 0) for r in dropped)
    bym = collections.defaultdict(lambda: [0, 0.0])
    for r in dropped:
        bym[r["date"][:7]][0] += 1
        bym[r["date"][:7]][1] += float(r.get("revenue") or 0)

    print("ledger rows   : %d" % len(rows))
    print("duplicate rows: %d" % len(dropped))
    print("revenue removed: $%s" % "{:,.2f}".format(money))
    for m in sorted(bym):
        print("   %s  %d rows  $%s" % (m, bym[m][0], "{:,.2f}".format(bym[m][1])))

    if a.dry_run:
        print("\ndry run, nothing written")
        return 0

    bak = a.ledger + ".predupe"
    if not os.path.exists(bak):
        os.replace(a.ledger, bak)
    else:
        os.remove(a.ledger)
    with open(a.ledger, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(out)
    print("\nwrote %d rows to %s" % (len(out), a.ledger))
    print("previous copy kept at %s" % bak)
    return 0


if __name__ == "__main__":
    sys.exit(main())
