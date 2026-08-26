#!/usr/bin/env python3
"""
KoffieKaart refresh script.

Re-pulls the current catalogue (grachtenbeans WP API + 14 Shopify webshops),
diffs it against the previous snapshot, and reports:
  - NEW coffees that appeared
  - GONE coffees that disappeared
  - PRICE changes on coffees you can see prices for

Usage:
  python3 scripts/refresh.py            # update snapshot + write changes.json
  python3 scripts/refresh.py --dry-run  # diff only, don't overwrite snapshot
"""
import json, re, sys, urllib.request, os, time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
SNAPSHOT = os.path.join(DATA, "snapshot.json")

SHOPIFY = [
    ("black-bloom", "Black & Bloom", "blackandbloom.nl"),
    ("bocca-coffee", "Bocca Coffee", "bocca.nl"),
    ("giraffe-coffee-roasters", "Giraffe Coffee Roasters", "giraffecoffee.com"),
    ("sprout-coffee-roasters", "Sprout Coffee Roasters", "sproutcoffeeroasters.art"),
    ("stooker-specialty-coffee", "Stooker Specialty Coffee", "stookerspecialtycoffee.com"),
    ("wide-awake", "Wide Awake Coffee Club", "wideawake.coffee"),
    ("five-ways-coffee", "Five Ways Coffee", "fivewayscoffee.com"),
    ("goodbeans", "Good Beans", "goodbeans.nl"),
    ("espressofabriek", "Espressofabriek", "espressofabriek.nl"),
    ("rum-baba", "Rum Baba", "rumbaba.nl"),
    ("fascino", "Fascino Coffee", "fascino-coffee.com"),
    ("wakuli", "Wakuli", "wakuli.nl"),
    ("koffie-van-hoorn", "Koffie van Hoorn", "koffievanhoorn.nl"),
    ("de-koffiemeester", "De Koffiemeester", "dekoffiemeester.nl"),
]
GB_BASE = "https://grachtenbeans.nl/wp-json/wp/v2"

SKIP = ['alessi','filter papers','theefilters','papieren','filters','mok ','mug','beker','cup','thermos',
        'abonnement','subscription','proefpakket','giftcard','gift card','cadeaukaart','voucher',
        'machine','grinder','molen','kan ','server','pitcher','tamper','kettle','waterkoker','weegschaal',
        'scale','brewer','aeropress','v60','chemex','french press','moka','portafilter',
        'cleaning','ontkalker','brush','borstel','t-shirt','shirt','tote','cap ','pet ','hoodie','poster',
        'likorette','liqueur','frisdrank','chocolade repen','koek','cookie','stroopwafel',
        'accessoire','accessory','boeken','book','cursus','workshop','training']
COFFEE_KW = ['ethiopia','ethiopië','colombia','colombie','kenya','kenia','guatemala','brazil','brazilië',
             'peru','rwanda','honduras','nicaragua','costa rica','el salvador','indonesia','sumatra','java',
             'yemen','india','burundi','uganda','panama','ecuador','bolivia','mexico','china','yirgacheffe',
             'sidamo','guji','huila','nariño','cauca','natural','washed','gewassen','honey','espresso',
             'filter','omni','blend','decaf','koffiebonen','bonen','beans','single origin','dark roast',
             'light roast','medium roast']

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "KoffieKaart/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "strict")
        except Exception as e:
            if attempt == 2:
                print(f"  ! failed {url}: {e}", file=sys.stderr)
                return None
            time.sleep(2)

def strip_html(s):
    return re.sub(r"<[^>]+>", " ", s or "")

def slugify_id(roaster_slug, name):
    key = f"{roaster_slug}-{re.sub(r'[^a-z0-9]+','-',(name or '').lower())}".strip("-")
    return re.sub(r"-+", "-", key)[:120]

def pull_shopify():
    out = []
    for slug, rname, domain in SHOPIFY:
        page = 1
        while True:
            raw = fetch(f"https://{domain}/products.json?limit=250&page={page}")
            if not raw: break
            try:
                products = json.loads(raw).get("products", [])
            except Exception:
                break
            if not products: break
            for p in products:
                title = p.get("title") or ""
                tl = title.lower()
                if any(k in tl for k in SKIP): continue
                if not any(k in tl for k in COFFEE_KW): continue
                variants = p.get("variants") or []
                try:
                    price = min(float(v["price"]) for v in variants if v.get("price"))
                except (ValueError, KeyError):
                    price = None
                available = any(v.get("available") for v in variants)
                img = ((p.get("images") or [{}])[0]).get("src")
                out.append({
                    "id": slugify_id(slug, title),
                    "name": title,
                    "roaster_slug": slug,
                    "price_eur": round(price, 2) if price else None,
                    "in_stock": available,
                    "buy_url": f"https://{domain}/products/{p.get('handle')}",
                    "source": "shopify",
                })
            if len(products) < 250: break
            page += 1
        print(f"  shopify {rname}: ok")
    return out

def pull_grachtenbeans():
    # total pages
    req = urllib.request.Request(f"{GB_BASE}/product?per_page=100&page=1&_fields=id", headers={"User-Agent":"KoffieKaart/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        pages = int(r.headers.get("X-WP-TotalPages", "43"))
    out = []
    for page in range(1, pages + 1):
        raw = fetch(f"{GB_BASE}/product?per_page=100&page={page}&_fields=id,slug,title,link,modified,roaster,class_list")
        if not raw: continue
        try:
            products = json.loads(raw)
        except Exception:
            continue
        roaster_names = {}
        for p in products:
            name = re.sub(r"&#8217;", "'", p["title"]["rendered"])
            name = re.sub(r"\s+", " ", name).strip()
            rid = p["roaster"][0] if p.get("roaster") else None
            out.append({
                "id": slugify_id("", "") or None,
                "gb_id": p["id"],
                "name": name,
                "detail_url": p["link"],
                "last_checked": p.get("modified", ""),
                "source": "grachtenbeans",
            })
    print(f"  grachtenbeans: {len(out)} products across {pages} pages")
    return out

def stable_key(c):
    """gb entries keyed by gb_id; shopify by id"""
    return f"{c['source']}:{c.get('gb_id') or c['id']}"

def main():
    dry = "--dry-run" in sys.argv
    print("Pulling catalogues…")
    shopify = pull_shopify()
    gb = pull_grachtenbeans()

    prev = {}
    if os.path.exists(SNAPSHOT):
        snap = json.load(open(SNAPSHOT))
        prev = {stable_key(c): c for c in snap}

    cur_list = shopify + gb
    cur = {stable_key(c): c for c in cur_list}

    added, gone, price_changes, stock_changes = [], [], [], []
    for k, c in cur.items():
        if k not in prev:
            added.append(c); continue
        p = prev[k]
        if c.get("price_eur") is not None and p.get("price_eur") is not None and c["price_eur"] != p["price_eur"]:
            price_changes.append({"coffee": c["name"], "roaster": c["roaster_slug"],
                                  "was": p["price_eur"], "now": c["price_eur"], "url": c.get("buy_url")})
        if "in_stock" in c and "in_stock" in p and c["in_stock"] != p["in_stock"]:
            stock_changes.append({"coffee": c["name"], "back": c["in_stock"], "url": c.get("buy_url")})
    for k, c in prev.items():
        if k not in cur:
            gone.append(c)

    report = {
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_now": len(cur),
        "new": [{"coffee": a["name"], "roaster": a.get("roaster_slug"), "url": a.get("buy_url") or a.get("detail_url")} for a in added[:200]],
        "gone": [{"coffee": g["name"]} for g in gone[:200]],
        "price_changes": price_changes[:200],
        "stock_changes": stock_changes[:200],
    }
    with open(os.path.join(DATA, "changes.json"), "w") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    print(f"\n=== KoffieKaart refresh {report['generated']} ===")
    print(f"catalogue now: {len(cur)} coffees ({len(prev)} before)")
    print(f"NEW:   {len(added)}   GONE: {len(gone)}   PRICE CHANGES: {len(price_changes)}   STOCK: {len(stock_changes)}")
    for pc in price_changes[:10]:
        print(f"  €{pc['was']} → €{pc['now']}  {pc['coffee'][:55]}")
    for a in added[:5]:
        print(f"  + {a['name'][:60]}")

    if not dry:
        with open(SNAPSHOT, "w") as f:
            json.dump(cur_list, f, ensure_ascii=False)
        print("\nsnapshot updated → data/snapshot.json")
    else:
        print("\ndry run — snapshot NOT updated")

if __name__ == "__main__":
    main()
