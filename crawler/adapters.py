"""Extraction adapters for sources that do not simply list ads as HTML links.

Each adapter is declared in the source record (sources.json / registry.json) and is only used when the
source allows it (robots.txt is checked by the Fetcher for every request):

  "sitemap": ["https://x.edu/sitemap.xml"]        posting URLs are taken from the sitemap
  "wp":      "https://lab.example.org"             WordPress REST API search (many labs/departments run WordPress)
  "api":     {url, items, map, headers?}          a public JSON API (for sites that render with JavaScript)

For a JavaScript-only site, add an "api" block once you know its JSON endpoint (browser dev tools -> Network).
A source whose pages cannot be read by any adapter is marked status=js_required and is NEVER shown as verified.
"""
import json, re
from urllib.parse import urljoin, urlparse
import crawl

KW_URL = re.compile(r'(job|vacanc|stellen|position|phd|doctor|promotion|studentship|scholarship|fellowship|postdoc|opening|offre|vacature|career|recruit|ausschreibung)', re.I)


def sitemap_urls(F, sm_urls, cap=400, depth=1):
    out = []
    for sm in sm_urls[:4]:
        try:
            text, _, final = F.get(sm)
        except Exception:
            continue
        locs = re.findall(r'<loc>\s*([^<\s]+)\s*</loc>', text)
        if '<sitemapindex' in text and depth > 0:
            subs = [l for l in locs if KW_URL.search(l)] or locs[:2]
            out += sitemap_urls(F, subs[:3], cap, depth - 1)
        else:
            out += [l for l in locs if KW_URL.search(l) and not crawl.BAD_EXT.search(l)]
        if len(out) >= cap:
            break
    return out[:cap]


def wp_candidates(F, base, q='phd'):
    out = []
    for term in (q, 'doctoral', 'scholarship', 'position'):
        try:
            text, _, _ = F.get(base.rstrip('/') + f'/wp-json/wp/v2/posts?search={term}&per_page=20&_fields=link,title,date')
            for it in json.loads(text):
                t = it.get('title', {}).get('rendered', '') if isinstance(it.get('title'), dict) else ''
                if it.get('link'):
                    out.append((it['link'], re.sub('<[^>]+>', '', t)))
        except Exception:
            break
    return out


def _dig(obj, path):
    for p in [x for x in (path or '').split('.') if x]:
        if isinstance(obj, list):
            obj = obj[int(p)] if p.isdigit() and int(p) < len(obj) else None
        elif isinstance(obj, dict):
            obj = obj.get(p)
        else:
            return None
    return obj


def api_items(F, cfg):
    try:
        text, _, _ = F.get(cfg['url'])
        items = _dig(json.loads(text), cfg.get('items', ''))
    except Exception:
        return []
    out = []
    for it in items or []:
        raw = {k: _dig(it, v) for k, v in (cfg.get('map') or {}).items()}
        if raw.get('url'):
            raw['url'] = urljoin(cfg['url'], str(raw['url']))
        out.append(raw)
    return out


def run(src, F):
    cands, raws = [], []
    if src.get('sitemap'):
        cands += [(u, '') for u in sitemap_urls(F, src['sitemap'])]
    if src.get('wp'):
        cands += wp_candidates(F, src['wp'])
    if src.get('api'):
        raws += api_items(F, src['api'])
    return cands, raws


def record_from_fields(raw, src, hub):
    """Build a position record from API fields (title, url, deadline, description, org, city, country, salary ...)."""
    title = re.sub(r'\s+', ' ', str(raw.get('title') or '')).strip()[:170]
    if len(title) < 8 or not raw.get('url'):
        return None
    body = re.sub(r'<[^>]+>', ' ', str(raw.get('description') or ''))
    typ = crawl.classify(title, body)
    if typ in (None, 'professor'):
        return None
    dl = crawl.parse_date(str(raw.get('deadline') or '')) or crawl.find_deadline(body)
    if dl and dl < crawl.TODAY:
        return None
    sc = (src.get('country') or '').strip()
    cc = src.get('cc') or crawl.CN.get(str(raw.get('country') or '').strip()) or crawl.find_country(title + ' ' + body[:2000]) or crawl.CN.get(sc)
    if not cc:
        return None
    low = body.lower()
    full, selff = crawl.has_any(low, crawl.FUND_FULL), crawl.has_any(low, crawl.FUND_SELF)
    return dict(id=__import__('zlib').crc32(crawl.norm_url(raw['url']).encode()) & 0x7fffffff, title=title,
                inst=str(raw.get('org') or src.get('name') or '')[:90], city=str(raw.get('city') or src.get('city') or ''),
                country=crawl.ISO_NAME.get(cc, cc), cc=cc,
                type={'phd': 'PhD', 'master': 'Master', 'scholar': 'Scholarship', 'postdoc': 'Postdoc', 'intern': 'Internship', 'job': 'Research job'}[typ],
                hub=hub, url=raw['url'], deadline=dl.isoformat() if dl else None,
                funding='Partial' if full and selff else 'Full' if full else 'Self-funded' if selff else 'Unclear',
                duration=crawl.find_duration(body), salary=None, currency=None, portfolio='Not stated', proposal='Not stated',
                fee='Not stated', ielts='', gre='', topics='', sup=[])
