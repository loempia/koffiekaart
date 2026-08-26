# ☕ KoffieKaart

**Every Dutch specialty coffee roastery, one map of flavour.**

KoffieKaart is an independent, searchable index of the Dutch specialty coffee scene — 370+ roasteries, ~4,900 coffees, with live prices and stock pulled straight from roasters' own webshops. We never sell coffee; every "Buy" button links directly to the roastery.

🔗 **Live site:** https://loempia.github.io/koffiekaart/

![KoffieKaart](https://img.shields.io/badge/coffees-4,900+-c2571b) ![live-priced](https://img.shields.io/badge/live--priced-990+-3d7a4f) ![roasteries](https://img.shields.io/badge/roasteries-372-2b2118)

---

## What it does

- **Search that speaks coffee** — type `natural ethiopia`, `acidic kenya`, or `fucking strong decaf`; every term matches against names, origins, processes, and tasting notes
- **Filters** — process (natural / washed / honey / experimental), acidity, origin, roast level, province, brew method (espresso / filter / omni), decaf, and *live catalogue only*
- **Live data** — prices and stock status pulled directly from 118+ connected webshops (Shopify + WooCommerce APIs)
- **Watchlist** — tap ♡ on any coffee to keep an eye on it (stored locally, no account needed)
- **Shareable URLs** — every search and filter combination is a URL: `?q=purple&origin=Colombia&live=1`
- **Buy direct** — links go straight to the roastery's product page or website, zero markup

## How the data works

Three sources, merged and deduplicated:

| Source | Coverage | Data |
|---|---|---|
| **Shopify stores** (34 roasters) | live | price, stock, image, direct product URL |
| **WooCommerce stores** (86 roasters) | live | price, stock, image, direct product URL |
| **grachtenbeans.nl index** (~250 roasters) | catalogue | origin, process, tasting notes, acidity, roast level |

Live sources are polled on every refresh; the grachtenbeans index provides catalogue depth (origin/process/taste taxonomies) for roasters without public APIs. Where a roaster appears in both, live data wins.

## Refreshing the data

```bash
python3 scripts/refresh.py            # pull everything, update snapshot, write changes.json
python3 scripts/refresh.py --dry-run  # diff only, don't overwrite
```

Then rebuild `data/data.js` (see `scripts/build_data.py` logic inside refresh output) and push — GitHub Pages deploys automatically.

The refresh pipeline includes:

- **Deduplication** — by ID, roaster + normalized name, and product URL
- **Price validation** — flags anything outside €3–€100 (caught espresso machines at €6,149 and workshops)
- **Health checks** — `data/health.json` tracks last successful pull per source; rate-limit guards abort gracefully after 5 consecutive failures
- **Snapshot archives** — 4 weeks of weekly backups in `data/snapshots/`
- **Brew-method tagging** — espresso/filter/omni detected from product names and Shopify tags

## Manual curation

`data/overrides.json` is the human layer — corrections here survive every refresh:

```jsonc
{
  "roasters": {
    "some-brander": {
      "name": "Some Brander",
      "website": "https://somesite.nl",
      "city": "Utrecht"
    }
  },
  "removed_roasters": {
    "goodbeans": "Belgian shop, out of scope"
  },
  "coffee_filters": {
    "skip_patterns": ["proefpakket", "abonnement", "workshop"]
  },
  "woocommerce_stores": { "slug": "https://shop-url.nl" }
}
```

Adding a roaster entry with a Shopify domain automatically adds it to the live-pull list.

## Project layout

```
├── index.html              # the entire app (vanilla JS, no build step)
├── data/
│   ├── data.js             # generated dataset loaded by the site
│   ├── coffees.json        # merged coffee records
│   ├── roasters.json       # roastery directory
│   ├── overrides.json      # manual curation (survives refreshes)
│   ├── snapshot.json       # last pulled catalogue
│   ├── snapshots/          # weekly archives (4 weeks)
│   ├── health.json         # per-source pull status
│   └── changes.json        # diff report (new / gone / price changes)
└── scripts/
    └── refresh.py          # the whole pipeline
```

## Known limitations

- **Roast dates aren't indexed** — public Shopify/WooCommerce APIs don't expose them, and <1% of product descriptions contain explicit dates. Using listing dates instead would be misleading, so we don't.
- **~130 roasters fall back to search links** — mostly micro-roasters without a discoverable own webshop; their "Buy" button opens a pre-filled Google search rather than a dead link.
- **The grachtenbeans index is only as good as its source** — we correct known errors via `overrides.json` (e.g. non-Dutch roasters, mislabeled cities), but can't verify every one of ~3,000 indexed coffees.

## Contributing

Spot a wrong price, a missing roastery, or a roaster that doesn't exist anymore? Open an issue or edit `data/overrides.json` directly and PR — the curation layer is designed for exactly that.

---

*Made with ♥ and too much caffeine. KoffieKaart is not affiliated with any roastery; all product links lead to the roasters themselves.*
