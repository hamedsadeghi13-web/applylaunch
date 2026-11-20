#!/usr/bin/env python3
"""Dynamic source discovery and vetting.

Finds NEW sources (universities, research institutes, funders, portals), tests whether real ads can be extracted
from them, and records the result in crawler/registry.json. crawl.py crawls only sources with status "verified".

Where candidates come from
  1. OpenAlex institutions + funders (public scholarly API: universities, research institutes, government bodies, funders)
  2. seeds.json            curated list of well-known portals (EURAXESS, jobs.ac.uk, DAAD ...), vetted like all others
  3. snowball              education-looking sites linked from portals that were already verified
  4. web search API        optional, needs a key in the secret BRAVE_API_KEY (never stored in the repository)

Status of every source (a source is "verified" ONLY if at least one real, current position was extracted):
  verified | unverified (listing found, nothing extractable now) | js_required (needs an adapter) |
  blocked_robots | unreachable | no_listing
"""
import argparse, datetime as dt, json, os, re, sys, time, zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl                                     # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TODAY = dt.date.today()

LISTING_RX = re.compile(r'(jobs?\b|careers?|vacanc|stellen|karriere|offres?|emploi|vacature|recrutement|convocator|concurso|phd|doctoral|doctorate|promotion|postdoc|studentship|scholarship|stipend|research positions?|open positions?|work with us|join us|bewerb|open calls?)', re.I)
DEPT_RX = re.compile(r'(faculty|department|school of|institute|fakult|département|departamento|dipartimento|laborator|\blab\b|research cent)', re.I)
SECOND_LEVEL = {'ac', 'co', 'edu', 'gov', 'org', 'com', 'or', 'ne', 'go'}
EDU_HOST = re.compile(r'(\.edu(\.[a-z]{2})?$|\.ac\.[a-z]{2}$|(^|\.)uni-|univ|hochschule|politecnico|institut|research|\.ethz\.|\.kth\.|\.tudelft\.)', re.I)
BAD_HOST = re.compile(r'(linkedin|indeed|glassdoor|facebook|twitter|x\.com|youtube|instagram|reddit|quora|wikipedia|medium\.com|google|bing|amazon|pinterest|tiktok|researchgate|academia\.edu|github|scribd|slideshare)', re.I)
RE_INTERVAL = {'verified': 7, 'unverified': 30, 'js_required': 60, 'no_listing': 45, 'unreachable': 14, 'blocked_robots': 90}


def host_of(url):
    n = urlparse(url).netloc.lower()
    if re.match(r'^(\d+\.){3}\d+', n):                      # IP address (tests): keep the port, it identifies the site
        return n
    return re.sub(r'^www\d?\.', '', n.split(':')[0])


def reg_domain(host):
    if re.match(r'^(\d+\.){3}\d+', host):
        return host
    p = host.split('.')
    if len(p) >= 3 and p[-2] in SECOND_LEVEL and len(p[-1]) == 2:
        return '.'.join(p[-3:])
    return '.'.join(p[-2:])


def sid_for(url):
    return 'R' + format(zlib.crc32(reg_domain(host_of(url)).encode()) & 0xffffffff, '08x')


# ------------------------------------------------------------------ vetting
def find_listing_links(soup, base, limit=6):
    base_dom = reg_domain(host_of(base))
    scored = {}
    for a in soup.find_all('a', href=True):
        h = a['href'].strip()
        if h.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        u = urljoin(base, h)
        if not u.startswith('http') or crawl.BAD_EXT.search(u):
            continue
        same = reg_domain(host_of(u)) == base_dom
        t = a.get_text(' ', strip=True)
        sc = (2 if LISTING_RX.search(t) else 0) + (1 if LISTING_RX.search(urlparse(u).path) else 0)
        if sc and (same or re.search(r'(workday|personio|smartrecruiters|successfactors|jobs\.)', host_of(u))):
            scored[u] = max(scored.get(u, 0), sc + (1 if same else 0))
    return [u for u, _ in sorted(scored.items(), key=lambda x: -x[1])][:limit]


def find_depts(soup, base, limit=4):
    base_dom = reg_domain(host_of(base))
    out = []
    for a in soup.find_all('a', href=True):
        u = urljoin(base, a['href'].strip())
        if u.startswith('http') and reg_domain(host_of(u)) == base_dom and DEPT_RX.search(a.get_text(' ', strip=True)) and u not in out and not crawl.BAD_EXT.search(u):
            out.append(u)
        if len(out) >= limit:
            break
    return out


def rss_links(soup, base):
    return [urljoin(base, l['href']) for l in soup.find_all('link', href=True)
            if 'alternate' in (l.get('rel') or []) and re.search(r'(rss|atom)', l.get('type') or '', re.I)][:2]


def looks_js_only(html):
    soup = BeautifulSoup(html, 'lxml')
    n_script = len(soup.find_all('script', src=True))
    for t in soup(['script', 'style', 'noscript']):
        t.decompose()
    txt = soup.get_text(' ', strip=True)
    return len(txt) < 400 and (n_script >= 2 or bool(re.search(r'id="(root|app|__next)"|__NEXT_DATA__|ng-app', html)))


def vet(entry, F, deadline_ts):
    """Test one source. Returns the entry updated with status / reason / quality / listing / rss / sitemap / wp."""
    e = dict(entry)
    now = TODAY.isoformat()
    e['vetted'] = now
    home = e['url']
    try:
        html, ctype, final = F.get(home)
    except PermissionError:
        e.update(status='blocked_robots', reason='robots.txt does not allow automated access', quality=0)
        return e
    except Exception as ex:
        e.update(status='unreachable', reason=str(ex)[:80], quality=0)
        return e
    soup = BeautifulSoup(html, 'lxml')
    listing = find_listing_links(soup, final)
    rss = rss_links(soup, final)
    depts = find_depts(soup, final) if e.get('type') in ('university', 'institute') else []
    js_hint = looks_js_only(html)
    if e.get('type', '').startswith('aggregator') and not listing:
        listing = [final]                                    # portals list ads on their own pages
    for d in depts[:3]:                                      # faculties / departments / labs
        try:
            dh, _, dfinal = F.get(d)
            listing += find_listing_links(BeautifulSoup(dh, 'lxml'), dfinal, 2)
        except Exception:
            pass
    sitemap = []
    try:
        base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
        F.allowed(base + '/')
        sm = F.robots.get(urlparse(final).netloc)
        sitemap = list(getattr(sm, 'site_maps', lambda: None)() or [])[:2] or [base + '/sitemap.xml']
    except Exception:
        pass
    outl = sorted({host_of(urljoin(final, a['href'])) for a in soup.find_all('a', href=True) if EDU_HOST.search(host_of(urljoin(final, a['href']))) and reg_domain(host_of(urljoin(final, a['href']))) != reg_domain(host_of(final))})[:20]
    e['outlinks'] = outl
    trial = dict(e, listing=list(dict.fromkeys(listing))[:6], rss=rss, sitemap=sitemap, id=e['id'])
    stat, recs, _ = crawl.crawl_source(trial, F, {}, 6, deadline_ts)
    used = dict(listing=trial['listing'], rss=rss, sitemap=sitemap)
    if not recs:                                             # WordPress REST probe (labs, departments)
        try:
            base = f"{urlparse(final).scheme}://{urlparse(final).netloc}"
            F.get(base + '/wp-json/wp/v2/posts?per_page=1&_fields=link')
            t2 = dict(e, listing=[], rss=[], sitemap=[], wp=base, id=e['id'])
            stat, recs, _ = crawl.crawl_source(t2, F, {}, 6, deadline_ts)
            if recs:
                used = dict(listing=[], rss=[], sitemap=[], wp=base)
        except Exception:
            pass
    valid = len(recs)
    e['js'] = bool(stat.get('js'))
    e['method_used'] = stat.get('method', '')
    if valid:
        with_dl = sum(1 for r in recs if r.get('deadline'))
        q = 30 + 10 * min(valid, 5) + (10 if (rss or used.get('rss')) else 0) + (10 if with_dl * 2 >= valid else 0)
        e.update(status='verified', reason=f'{valid} real position(s) extracted at vetting', quality=min(100, q), **used,
                 sample=[r['title'][:80] for r in recs[:2]])
    elif js_hint and not stat.get('found'):
        e.update(status='js_required', reason='page is built with JavaScript; the browser pass found nothing extractable yet - needs a custom adapter (see adapters.py)' if stat.get('js') else 'page is built with JavaScript; add an "api" adapter (see adapters.py)', quality=0, **used)
    elif listing or rss:
        e.update(status='unverified', reason='listing page found but no current position could be extracted', quality=10, **used)
    else:
        e.update(status='no_listing', reason='no jobs / PhD / scholarship page found from the home page', quality=0)
    return e


# ------------------------------------------------------------------ candidate producers
class OpenAlex:
    def __init__(self, base):
        self.base = base.rstrip('/')
        self.params = {}
        if os.environ.get('OPENALEX_API_KEY'):
            self.params['api_key'] = os.environ['OPENALEX_API_KEY']
        if os.environ.get('CONTACT_EMAIL'):
            self.params['mailto'] = os.environ['CONTACT_EMAIL']
        self.s = requests.Session()
        self.s.headers['User-Agent'] = crawl.UA

    def pages(self, path, flt, select, max_items):
        cursor, got = '*', 0
        while cursor and got < max_items:
            try:
                r = self.s.get(f'{self.base}/{path}', params=dict(self.params, filter=flt, select=select, **{'per-page': 100, 'cursor': cursor, 'sort': 'works_count:desc'}), timeout=30)
                r.raise_for_status()
                j = r.json()
            except Exception as ex:
                print('  OpenAlex error:', str(ex)[:100], flush=True)
                return
            for it in j.get('results', []):
                got += 1
                yield it
            cursor = (j.get('meta') or {}).get('next_cursor')


def oa_candidates(oa, per_kind, min_works):
    kinds = [('institutions', 'type:education,works_count:>%d' % min_works, 'university'),
             ('institutions', 'type:facility|government|nonprofit,works_count:>%d' % (min_works * 2), 'institute'),
             ('funders', 'works_count:>%d' % (min_works * 2), 'funder')]
    CCS = 'DE NL SE DK NO FI CH AT BE FR GB IE ES PT IT PL CZ HU GR TR EE LV LT SI SK HR RO BG IS LU US CA AU NZ JP KR CN SG HK TW MY TH VN IN SA AE QA IL EG ZA BR MX CL AR CO PK IR RU UA'.split()
    # one single-page request per country (OpenAlex answers cursor paging with 401 when no API key is set), so every country is covered
    plan = [(path, flt + ',country_code:' + cc, typ, 100) for path, flt, typ in kinds for cc in CCS]
    for path, flt, typ, limit in plan:
        sel = 'id,display_name,homepage_url,country_code,ror,works_count,geo' if path == 'institutions' else 'id,display_name,homepage_url,country_code,works_count'
        for it in oa.pages(path, flt, sel, limit):
            u = it.get('homepage_url')
            if not u or not u.startswith('http'):
                continue
            cc = (it.get('country_code') or '').upper()
            yield dict(id=sid_for(u), name=it.get('display_name', host_of(u)), type=typ, country=crawl.ISO_NAME.get(cc, cc), cc=cc or None,
                       city=((it.get('geo') or {}).get('city') or ''), url=u, search=None, method='auto', active=True, via='openalex',
                       oa=it.get('id'), ror=it.get('ror'), works=it.get('works_count'))


WD_URL = 'https://query.wikidata.org/sparql'
WD_TYPES = {'university': 'wd:Q3918 wd:Q875538 wd:Q15936437 wd:Q902104 wd:Q23002054', 'institute': 'wd:Q31855 wd:Q1664720 wd:Q2467461 wd:Q16519632'}


def wikidata_candidates(per_country=150):
    """Second, independent directory: official websites of universities and research institutes recorded in Wikidata."""
    CCS = 'DE NL SE DK NO FI CH AT BE FR GB IE ES PT IT PL CZ HU GR TR EE LV LT SI SK HR RO BG IS LU US CA AU NZ JP KR CN SG HK TW MY TH VN IN SA AE QA IL EG ZA BR MX CL AR CO PK IR RU UA'.split()
    for cc in CCS:
        for typ, qs in WD_TYPES.items():
            q = ('SELECT ?i ?iLabel ?site WHERE { VALUES ?t { %s } ?i wdt:P31 ?t; wdt:P856 ?site; wdt:P17 ?c. ?c wdt:P297 "%s". '
                 'FILTER NOT EXISTS { ?i wdt:P576 ?end } SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } LIMIT %d') % (qs, cc, per_country)
            try:
                r = requests.get(WD_URL, params={'query': q, 'format': 'json'}, headers={'User-Agent': crawl.UA, 'Accept': 'application/sparql-results+json'}, timeout=60)
                rows = r.json()['results']['bindings'] if r.status_code == 200 else []
            except Exception as ex:
                print('  Wikidata error:', str(ex)[:80], flush=True)
                rows = []
            for b in rows:
                u = b['site']['value']
                if not u.startswith('http') or BAD_HOST.search(host_of(u)):
                    continue
                yield dict(id=sid_for(u), name=b.get('iLabel', {}).get('value', host_of(u))[:90], type=typ, country=crawl.ISO_NAME.get(cc, cc), cc=cc, city='', url=u,
                           search=None, method='auto', active=True, via='wikidata')
            time.sleep(1.0)


def seed_candidates(path):
    if os.path.exists(path):
        for s in json.load(open(path, encoding='utf-8')):
            yield dict(id=sid_for(s['url']), name=s['name'], type=s.get('type', 'aggregator-global'), country=s.get('country', 'Global'), cc=None, city='',
                       url=s['url'], search=None, method='auto', active=True, via='hub-seed', hub=True)


def search_candidates(base, queries, countries):
    key = os.environ.get('BRAVE_API_KEY')
    if not key:
        return
    for q in queries:
        for c in countries:
            try:
                r = requests.get(base, params={'q': q.format(country=c), 'count': 20}, headers={'X-Subscription-Token': key, 'Accept': 'application/json'}, timeout=20)
                res = r.json().get('web', {}).get('results', [])
            except Exception:
                continue
            for it in res:
                u = it.get('url', '')
                h = host_of(u)
                if not h or BAD_HOST.search(h):
                    continue
                yield dict(id=sid_for(u), name=(it.get('title') or h)[:80], type='aggregator-search', country=c, cc=None, city='',
                           url=f'{urlparse(u).scheme}://{urlparse(u).netloc}/', search=None, method='auto', active=True, via='search')
            time.sleep(1.1)


SEARCH_QUERIES = ['PhD positions {country} university vacancies', 'fully funded PhD scholarship {country} international students',
                  'research positions and postdoc jobs {country} institute', 'master scholarships {country} government funding']


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--registry', default=os.path.join(HERE, 'registry.json'))
    ap.add_argument('--sources', default=os.path.join(HERE, 'sources.json'))
    ap.add_argument('--seeds', default=os.path.join(HERE, 'seeds.json'))
    ap.add_argument('--openalex-base', default=os.environ.get('OPENALEX_BASE', 'https://api.openalex.org'))
    ap.add_argument('--search-base', default='https://api.search.brave.com/res/v1/web/search')
    ap.add_argument('--max-new', type=int, default=int(os.environ.get('MAX_NEW', 450)))
    ap.add_argument('--max-revet', type=int, default=int(os.environ.get('MAX_REVET', 120)))
    ap.add_argument('--min-works', type=int, default=int(os.environ.get('MIN_WORKS', 500)))
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--delay', type=float, default=float(os.environ.get('DELAY', 1.0)))
    ap.add_argument('--budget-min', type=int, default=int(os.environ.get('BUDGET_MIN', 120)))
    a = ap.parse_args()
    t0 = time.time()
    deadline_ts = t0 + a.budget_min * 60
    reg = json.load(open(a.registry, encoding='utf-8')) if os.path.exists(a.registry) else {'sources': []}
    entries = {s['id']: s for s in reg['sources']}
    curated = json.load(open(a.sources, encoding='utf-8')) if os.path.exists(a.sources) else []
    known_dom = {reg_domain(host_of(s['url'])) for s in curated if s.get('url')} | {reg_domain(host_of(s['url'])) for s in entries.values()}
    # ---- 1. new candidates (duplicates are rejected by registrable domain)
    cands, dup = [], 0

    def push(c):
        nonlocal dup
        d = reg_domain(host_of(c['url']))
        if d in known_dom or not d:
            dup += 1
            return
        known_dom.add(d)
        c['discovered'] = TODAY.isoformat()
        cands.append(c)
    gens = [seed_candidates(a.seeds), oa_candidates(OpenAlex(a.openalex_base), a.max_new, a.min_works), wikidata_candidates()]
    # snowball: education-looking domains linked from verified portals
    snow = [dict(id=sid_for('https://' + h), name=h, type='university', country='', cc=None, city='', url='https://' + h + '/', search=None, method='auto', active=True, via='snowball')
            for s in entries.values() if s.get('status') == 'verified' and s.get('hub') for h in s.get('outlinks', [])]
    gens.append(iter(snow))
    countries = sorted({s.get('country') for s in curated if s.get('country') and s['country'] not in ('Global', 'Multi', 'Europe')})[:12]
    gens.append(search_candidates(a.search_base, SEARCH_QUERIES, countries))
    # each independent method gets its own share, so no single directory fills the whole quota
    quota = max(20, a.max_new // max(1, len(gens)))
    by_via = {}
    for g in gens:
        n0 = len(cands)
        for c in g:
            push(c)
            if len(cands) - n0 >= quota:
                break
        by_via[g.__name__ if hasattr(g, '__name__') else 'list'] = len(cands) - n0
    print('candidates by method:', by_via, flush=True)
    new = cands[:a.max_new]
    # ---- 2. which existing entries are due for a re-test
    due = []
    for s in entries.values():
        iv = RE_INTERVAL.get(s.get('status'), 30)
        if not s.get('vetted') or (TODAY - dt.date.fromisoformat(s['vetted'])).days >= iv:
            due.append(s)
    due = sorted(due, key=lambda s: s.get('vetted', ''))[:a.max_revet]
    crawl.render.configure(float(os.environ.get('RENDER_BUDGET_MIN', 30)))
    F = crawl.Fetcher(delay=a.delay)

    def work(e):
        if time.time() > deadline_ts:
            return None
        try:
            return vet(e, F, deadline_ts)
        except Exception as ex:
            return dict(e, status='unreachable', reason='error: ' + str(ex)[:60], vetted=TODAY.isoformat(), quality=0)
    def save():
        import guard
        out = sorted(guard.snapshot(entries).values(), key=lambda s: (-s.get('quality', 0), s['name']))
        json.dump(dict(updated=TODAY.isoformat(), sources=out), open(a.registry, 'w', encoding='utf-8'), ensure_ascii=False, indent=0)
        return out

    def work2(e):
        r = work(e)
        if r:
            entries[r['id']] = r
        return r
    import guard
    guard.start(deadline_ts, save, grace=240)
    ex = ThreadPoolExecutor(a.workers)
    list(ex.map(work2, new + due))
    ex.shutdown(wait=False)
    out = save()
    from collections import Counter
    c = Counter(s.get('status') for s in out)
    print(f'DISCOVERY: {len(new)} new candidates found ({dup} duplicates rejected), {len(due)} re-tested | registry now {len(out)} sources: {dict(c)}')


if __name__ == '__main__':
    main()
