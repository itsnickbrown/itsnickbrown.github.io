"""
make_synthetic_ledger.py
Builds a fake POS ledger shaped like the real one: same columns, same quirks
(seed months dated the 15th, sporadic long-tail buying, a few name splits and
end users in the reseller field). Every company, person and number is invented.
"""
import csv, random, math, datetime as dt, sys

random.seed(42)
OUT = sys.argv[1] if len(sys.argv) > 1 else "synthetic_ledger.csv"

A = ["North", "Blue", "Iron", "Summit", "Clear", "Bright", "Granite", "Harbor", "Pioneer", "Cedar",
     "Atlas", "Keystone", "Silver", "Redwood", "Lakeside", "Prairie", "Falcon", "Beacon", "Copper",
     "Sterling", "Evergreen", "Riverbend", "Highland", "Coastal", "Frontier", "Liberty", "Union",
     "Patriot", "Meridian", "Vector", "Apex", "Orbit", "Signal", "Crest", "Anchor", "Bluff", "Canyon",
     "Delta", "Echo", "Foundry", "Gateway", "Horizon", "Juniper", "Kestrel", "Lantern", "Mosaic"]
B = ["Network", "Data", "Tech", "Systems", "Micro", "Digital", "IT", "Cyber", "Cloud", "Logic",
     "Wire", "Link", "Grid", "Byte", "Core", "Fiber", "Secure", "Infra"]
C = ["Solutions", "Group", "Partners", "Integration", "Services", "Technologies", "Inc", "LLC",
     "Corp", "Federal", "Direct", "Supply"]
STATES = ["MD", "VA", "TX", "CA", "FL", "GA", "NC", "OH", "IL", "CO", "WA", "NY", "PA", "AZ", "MA",
          "MN", "TN", "UT", "MI", "NJ", "MO", "OR", "SC", "KY", "AL"]
EU_A = ["Riverside", "Harlow", "Maple", "Oak Hill", "Brookfield", "Fairview", "Stonegate", "Westbrook",
        "Clearwater", "Pine Ridge", "Lakeview", "Ashford", "Kingsley", "Millbrook", "Hartwell", "Elmwood"]
EU_B = ["Health System", "County Schools", "Regional Airport", "Water Authority", "University",
        "Medical Center", "Logistics", "Credit Union", "Public Library", "Manufacturing", "Casino Resort",
        "City Government", "Transit District", "Distribution Center", "Naval Station", "Energy Co-op"]
DISTS = ["DIST NORTH", "DIST WEST", "DIST EAST"]
PARTS = [  # part, unit price, weight
    ("LT-100", 2650, 10), ("LT-200", 3400, 7), ("LT-10G-KIT", 6316, 4), ("LT-100G", 8999, .4),
    ("WA-PRO-KIT", 4236, 6), ("NA-300", 9559, 1.5), ("NA-500-KIT", 14200, .6), ("SA-SITE", 12396, 1),
    ("CT-50", 590, 8), ("SUP-1YS-LT", 420, 9), ("SUP-3YS-NA", 2890, 4), ("SUP-1YS-WA", 610, 5),
    ("CL-SUB-PE", 7800, .4), ("ACC-CASE", 95, 6), ("ACC-SFP", 180, 5), ("ACC-BATT", 140, 4)]
PW = [p[2] for p in PARTS]

# seasonal weights by month (Q-end and Sep fiscal push)
SEASON = {1: .85, 2: .8, 3: 1.15, 4: 1.0, 5: .9, 6: 1.1, 7: .95, 8: .85, 9: 1.35, 10: 1.0, 11: .7, 12: .9}

def name():
    return f"{random.choice(A)} {random.choice(B)} {random.choice(C)}".upper()

names, partners = set(), []
while len(partners) < 640:
    n = name()
    if n in names:
        continue
    names.add(n)
    size = random.paretovariate(1.25)              # long tail
    start = dt.date(2020, 1, 1) + dt.timedelta(days=random.randint(0, 2350))
    partners.append({
        "name": n, "key": " ".join(w for w in n.lower().split() if w not in ("inc", "llc", "corp")),
        "state": random.choice(STATES), "size": size, "start": start,
        "rate": min(.9, .03 + .06 * size),          # chance of buying in a given month
        "dists": random.sample(DISTS, random.choice([1, 1, 1, 2])),
        "eus": [f"{random.choice(EU_A)} {random.choice(EU_B)}".upper() for _ in range(random.randint(1, 8))],
        "life": random.choice([18, 30, 48, 80, 999, 999]),   # months until they drift away
    })
# a few end users reported in the reseller field
for i in range(6):
    eu = f"{random.choice(EU_A)} {random.choice(EU_B)}".upper()
    partners.append({"name": eu, "key": eu.lower(), "state": random.choice(STATES), "size": .5,
                     "start": dt.date(2021, 1, 1), "rate": .05, "dists": ["DIST EAST"], "eus": [""],
                     "life": 999, "enduser": True})

LAST = dt.date(2026, 11, 6)
rows, doc = [], 7000000

def month_iter(a, b):
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        yield y, m
        m += 1
        if m == 13:
            y, m = y + 1, 1

for p in partners:
    for k, (y, m) in enumerate(month_iter(p["start"], LAST)):
        if k > p["life"]:
            if random.random() > .02:
                continue
        growth = 1 + .02 * (y - 2020)
        if random.random() > p["rate"] * SEASON[m] * growth:
            continue
        if (y, m) == (LAST.year, LAST.month) and random.random() > LAST.day / 30 * 1.2:
            continue
        seed = (y, m) < (2026, 7)
        last_day = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)).day
        if (y, m) == (LAST.year, LAST.month):
            last_day = LAST.day
        n_orders = 1 + (random.random() < min(.6, .08 * p["size"]))
        for _ in range(n_orders):
            doc += random.randint(3, 40)
            day = 15 if seed else random.randint(1, last_day)
            d = dt.date(y, m, day)
            if d > LAST:
                continue
            eu = random.choice(p["eus"])
            dist = random.choice(p["dists"])
            for ln in range(1, random.choice([1, 1, 2, 3]) + 1):
                part, price, _ = random.choices(PARTS, PW)[0]
                qty = 1 + int(random.expovariate(1 / (.15 + min(p["size"], 8) * .12)))
                qty = min(qty, 12)
                rev = round(qty * price * random.uniform(.88, 1.0), 2)
                if random.random() < .015:
                    rev = -rev                         # a credit
                rows.append({
                    "date": d.isoformat(), "partner_key": p["key"], "partner_name": p["name"],
                    "state": p["state"], "doc_no": "" if (seed and random.random() < .5) else str(doc),
                    "line_no": "" if seed else str(ln), "part_no": part, "qty": qty, "revenue": rev,
                    "end_user": eu, "distributor": dist,
                    "source_file": "SEED REPORT" if seed else f"{dist.lower().replace(' ', '_')}_daily.xlsx"})

rows.sort(key=lambda r: r["date"])
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"{len(rows):,} rows, {len(partners)} partners -> {OUT}")
