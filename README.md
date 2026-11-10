# Nick Brown: channel management, data and AI

Portfolio site. Static HTML, hosted on GitHub Pages.

## What's here

- `index.html`: home page with project search and filters
- `projects/`: six case studies, some with small interactive demos
- `demos/`: full working demos (Partner Insights, Daily Tracker, Salon Offer Builder)
- `code/`: public versions of the scripts behind the demos
- `assets/bot.js`: the "Ask about my work" bot. It runs in the browser and matches questions against answers written from the case studies. No API key, no server.

## The data is fake

Every partner, end user, invoice and dollar in the demos is synthetic. `code/make_synthetic_ledger.py` generates a ledger with the same shape and quirks as the real one, and the demos are built from it with the same code that ran in production.

Rebuild the demos:

```
cd code
python make_synthetic_ledger.py synthetic_ledger.csv
DEMO_TODAY=2026-11 python partner_insights.py --no-snapshots --out ../demos/partner-insights.html
python build_tracker_demo.py --out ../demos/tracker.html
```
