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
OVERRIDES = os.path.join(DATA, "overrides.json")

def load_overrides():
    """Manual curation layer: roaster patches + skip patterns survive every refresh."""
    if not os.path.exists(OVERRIDES):
        return {}
    try:
        return json.load(open(OVERRIDES))
    except Exception:
        print("  ! overrides.json unreadable — ignoring", file=sys.stderr)
        return {}

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
    ("fucking-strong-coffee", "Fucking Strong Coffee", "fuckingstrongcoffee.nl"),
    ("92-origins", "92 Origins", "92origins.com"),
    ("amstel-koffie", "Amstel Koffie", "www.amstelkoffie.nl"),
    ("arabicafelix", "Arabicafelix", "arabicafelix.nl"),
    ("bakkum-beans", "Bakkum Beans", "bakkumbeans.com"),
    ("baobab-coffee-roasters", "Baobab Coffee Roasters", "baobabcoffee.nl"),
    ("be-good-coffee", "Be Good Coffee", "begoodcoffee.com"),
    ("beans-coffee-roasters", "Beans Coffee Roasters", "beanscoffeeroaster.com"),
    ("betuws-bakkie", "Betuws Bakkie", "betuwsbakkie.nl"),
    ("bitterzoet-coffee-roasters", "Bitterzoet Coffee Roasters", "bitterzoetcoffee.com"),
    ("blue-city-roasters", "Blue City Roasters", "bluecityroasters.nl"),
    ("brazuca-coffee", "Brazuca Coffee", "www.brazucacoffee.com"),
    ("cornelissen-coffeeroasters", "Cornelissen Coffeeroasters", "cornelissencoffeeroasters.com"),
    ("de-koffiekoopman", "De Koffiekoopman", "dekoffiekoopman.nl"),
    ("de-zeeuwse-sommelier", "De Zeeuwse Sommelier", "dezeeuwsesommelier.nl"),
    ("eddys-coffee", "Eddy's Coffee", "eddyscoffee.com"),
    ("five-ways-coffee-roasters", "Five Ways Coffee Roasters", "fivewayscoffee.com"),
    ("footnote-coffee", "Footnote Coffee", "footnotecoffee.com"),
    ("uncommon-coffee", "Uncommon Coffee", "uncommonams.com"),
]
GB_BASE = "https://grachtenbeans.nl/wp-json/wp/v2"

SKIP = ['alessi','filter papers','theefilters','papieren','filters','mok ','mug','beker','cup','thermos','proefpakket','abonnement','subscription','cadeau-box','gift card','giftcard','theefilter','capsules voor','t-shirt','workshop','cursus','cupping','training','koffiemachine','grinder',
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
    fails = 0
    for slug, rname, domain in SHOPIFY:
        if fails >= 5:
            print(f"  shopify: aborting after {fails} consecutive failures (rate limit?)", file=sys.stderr)
            break
        page = 1
        while True:
            raw = fetch(f"https://{domain}/products.json?limit=250&page={page}")
            if not raw:
                fails += 1
                break
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
        time.sleep(0.8)  # be polite, avoid 429s
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
            # roaster slug from URL: /koffiebrander/<slug>/<product>/
            m = re.search(r"/koffiebrander/([^/]+)/", p.get("link") or "")
            rslug = m.group(1) if m and m.group(1) not in ("uncategorised", "niet-gecategoriseerd") else None
            out.append({
                "id": slugify_id(rslug or "gb", name),
                "gb_id": p["id"],
                "name": name,
                "roaster_slug": rslug,
                "detail_url": p["link"],
                "last_checked": p.get("modified", ""),
                "source": "grachtenbeans",
            })
    print(f"  grachtenbeans: {len(out)} products across {pages} pages")
    return out

def pull_woo():
    """Pull live catalogs from WooCommerce stores (Store REST API, no key needed)."""
    ov = load_overrides()
    stores = list(ov.get("woocommerce_stores", {}).items())
    out = []
    for slug, url in stores:
        host = url.split("//")[-1].rstrip("/")
        for page in (1, 2):
            try:
                raw = fetch(f"https://{host}/wp-json/wc/store/products?per_page=50&page={page}")
                if not raw: break
                prods = json.loads(raw)
                if not isinstance(prods, list) or not prods: break
            except Exception:
                break
            for p in prods:
                title = re.sub(r"&#\d+;|&[a-z]+;", "", p.get("name") or "").strip()
                tl = title.lower()
                if any(k in tl for k in SKIP): continue
                if not any(k in tl for k in COFFEE_KW): continue
                try:
                    price = float((p.get("prices") or {}).get("price", 0)) / 100 or None
                except Exception:
                    price = None
                imgs = p.get("images") or []
                img = None
                if imgs:
                    img = (imgs[0] if isinstance(imgs[0], str) else (imgs[0].get("src") or None)) or None
                out.append({
                    "id": slugify_id(slug, title),
                    "name": title,
                    "roaster_slug": slug,
                    "price_eur": round(price, 2) if price else None,
                    "in_stock": bool(p.get("is_in_stock", True)),
                    "buy_url": p.get("permalink") or f"https://{host}",
                    "image_url": img,
                    "source": "woo",
                })
            if len(prods) < 50: break
    print(f"  woocommerce: {len(out)} products from {len(stores)} stores")
    return out

def stable_key(c):
    """gb entries keyed by gb_id; shopify/woo by id"""
    return f"{c['source']}:{c.get('gb_id') or c['id']}"

HEALTH = os.path.join(DATA, "health.json")

def load_health():
    try:
        return json.load(open(HEALTH))
    except Exception:
        return {}

BREW_PATTERNS = [
    (r"\bespresso\b", "espresso"),
    (r"\bfilter\b|\bpour.?over\b|\bbatch brew\b|\bfilterkoffie\b", "filter"),
    (r"\bomni\b", "omni"),
]
PRICE_MIN, PRICE_MAX = 3.0, 100.0  # sane range for 250g-ish retail bags

def validate_and_tag(coffee):
    """Price sanity check + brew-method tagging. Returns list of warnings."""
    warnings = []
    p = coffee.get("price_eur")
    if p is not None and not (PRICE_MIN <= p <= PRICE_MAX):
        warnings.append(f"price €{p} out of range")
    brew = set()
    text = (coffee.get("name") or "").lower()
    for pat, tag in BREW_PATTERNS:
        if re.search(pat, text):
            brew.add(tag)
    if brew:
        coffee["brew_methods"] = sorted(brew)
    return warnings

def update_health(source, ok, count, error=""):
    """Track per-source pull health."""
    h = load_health()
    h[source] = {
        "last_ok": time.strftime("%Y-%m-%d %H:%M:%S") if ok else h.get(source, {}).get("last_ok"),
        "last_attempt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "last_count": count,
        "last_error": error or None,
        "ok": ok,
    }
    with open(HEALTH, "w") as f:
        json.dump(h, f, ensure_ascii=False, indent=1)

def archive_snapshot():
    """Keep 4 weekly snapshots before overwriting."""
    if not os.path.exists(SNAPSHOT):
        return
    arch = os.path.join(DATA, "snapshots")
    os.makedirs(arch, exist_ok=True)
    week = time.strftime("%Y-W%W")
    dst = os.path.join(arch, f"snapshot-{week}.json")
    if not os.path.exists(dst):
        import shutil
        shutil.copy2(SNAPSHOT, dst)
        # prune archives older than 4 weeks
        cutoff = time.time() - 4 * 7 * 86400
        for f in os.listdir(arch):
            fp = os.path.join(arch, f)
            if os.path.getmtime(fp) < cutoff:
                os.remove(fp)
        print(f"  archived previous snapshot → snapshots/snapshot-{week}.json")

def main():
    dry = "--dry-run" in sys.argv
    ov = load_overrides()
    skip_extra = [s.lower() for s in ov.get("coffee_filters", {}).get("skip_patterns", [])]
    removed_roasters = set(ov.get("removed_roasters", {}).keys())
    roaster_patches = {k: v for k, v in ov.get("roasters", {}).items() if not k.startswith("_")}

    # extra Shopify stores from overrides.roasters (any entry with a shopify-capable domain)
    for slug, patch in roaster_patches.items():
        site = (patch.get("website") or "").replace("https://", "").replace("http://", "").rstrip("/")
        if site and slug not in [s for s, _, _ in SHOPIFY]:
            SHOPIFY.append((slug, patch.get("name", slug), site))

    print("Pulling catalogues…")
    shopify = pull_shopify()
    update_health("shopify", len(shopify) > 0, len(shopify),
                  "" if shopify else "no products pulled from any store")
    woo = pull_woo()
    update_health("woocommerce", len(woo) > 0, len(woo),
                  "" if woo else "no products pulled from any store")
    gb = pull_grachtenbeans()
    update_health("grachtenbeans", len(gb) > 100, len(gb),
                  "" if len(gb) > 100 else f"suspiciously low count: {len(gb)}")

    prev = {}
    if os.path.exists(SNAPSHOT):
        snap = json.load(open(SNAPSHOT))
        prev = {stable_key(c): c for c in snap}

    cur_list = shopify + woo + gb
    # dedupe: same id, or same roaster+normalized-name, or same buy_url
    def _norm(s): return re.sub(r"[^a-z0-9]", "", (s or "").lower())
    seen_id, seen_name, seen_url = set(), set(), set()
    deduped = []
    for c in cur_list:
        if c.get("source") == "grachtenbeans" and not c.get("roaster_slug"):
            continue  # unknown roaster, generic name — not useful
        k_id = c.get("id") or stable_key(c)
        k_name = (c.get("roaster_slug"), _norm(c.get("name")))
        k_url = (c.get("buy_url") or c.get("detail_url") or "").split("?")[0]
        if k_id in seen_id: continue
        if k_name[0] and k_name in seen_name: continue
        if k_url and k_url in seen_url and k_url.startswith("http"): continue
        seen_id.add(k_id); seen_name.add(k_name)
        if k_url: seen_url.add(k_url)
        deduped.append(c)
    cur_list = deduped

    # apply overrides: drop removed roasters, filter skip patterns, patch roaster fields
    if skip_extra:
        for c in cur_list:
            t = (c.get("name") or "").lower()
            if any(s in t for s in skip_extra):
                c["_skip"] = True
        cur_list = [c for c in cur_list if not c.pop("_skip", False)]

    cur = {stable_key(c): c for c in cur_list}

    # price validation + brew tagging
    price_warnings = []
    for c in cur_list:
        w = validate_and_tag(c)
        if w:
            price_warnings.append((c.get("name"), w[0]))

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
    if price_warnings:
        print(f"PRICE WARNINGS: {len(price_warnings)}")
        for name, w in price_warnings[:10]:
            print(f"  ! {w} — {name[:50]}")
    for pc in price_changes[:10]:
        print(f"  €{pc['was']} → €{pc['now']}  {pc['coffee'][:55]}")
    for a in added[:5]:
        print(f"  + {a['name'][:60]}")

    if not dry:
        archive_snapshot()
        with open(SNAPSHOT, "w") as f:
            json.dump(cur_list, f, ensure_ascii=False)
        print("\nsnapshot updated → data/snapshot.json")
    else:
        print("\ndry run — snapshot NOT updated")

if __name__ == "__main__":
    main()
