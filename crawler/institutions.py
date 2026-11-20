#!/usr/bin/env python3
"""Global database of higher-education institutions  ->  crawler/institutions.json

Only openly licensed directories are harvested (CC0 data):
  * ROR  (Research Organization Registry)      https://api.ror.org            - CC0
  * OpenAlex institutions                     https://api.openalex.org        - CC0
  * Wikidata (official websites of universities) https://query.wikidata.org   - CC0
NOT used (see docs / README): WHED (IAU) - its terms forbid copying substantial parts without IAU's consent.

The job is incremental: it works through (directory, country, page) tasks, saves a checkpoint every few minutes and at
the time limit, and the next run continues exactly where it stopped. Records are merged (never duplicated) by
ROR id, Wikidata id or registrable domain + country, and are never deleted.
"""
import argparse, datetime as dt, json, os, re, sys, threading, time
from urllib.parse import urlparse

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guard  # noqa: E402

UA = os.environ.get('CRAWLER_UA', 'ApplyLaunchBot/1.0 (academic opportunity search; respects robots.txt)')
TODAY = dt.date.today().isoformat()
# every ISO 3166-1 alpha-2 country / territory that can have universities
ISO = ('AD AE AF AG AI AL AM AO AR AS AT AU AW AZ BA BB BD BE BF BG BH BI BJ BM BN BO BR BS BT BW BY BZ CA CD CF CG CH CI CK CL CM CN CO CR CU CV CW CY CZ DE DJ DK DM DO DZ '
       'EC EE EG ER ES ET FI FJ FM FO FR GA GB GD GE GF GH GI GL GM GN GP GQ GR GT GU GW GY HK HN HR HT HU ID IE IL IN IQ IR IS IT JM JO JP KE KG KH KI KM KN KP KR KW KY KZ '
       'LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PR PS PT PW PY '
       'QA RE RO RS RU RW SA SB SC SD SE SG SI SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TG TH TJ TL TM TN TO TR TT TV TW TZ UA UG US UY UZ VA VC VE VG VI VN VU WS XK YE ZA ZM ZW').split()
SECOND = {'co', 'com', 'ac', 'edu', 'org', 'gov', 'net', 'ne', 'or', 'go'}
BAD = re.compile(r'(linkedin|facebook|twitter|instagram|youtube|wikipedia|wikidata|google|github|researchgate)', re.I)


def reg_domain(url):
    h = urlparse(url if '//' in url else '//' + url).netloc.lower().split(':')[0]
    h = re.sub(r'^www\d?\.', '', h)
    p = h.split('.')
    if len(p) >= 3 and p[-2] in SECOND and len(p[-1]) == 2:
        return '.'.join(p[-3:])
    return '.'.join(p[-2:]) if len(p) >= 2 else h


def good_url(u):
    return bool(u) and u.startswith('http') and not BAD.search(urlparse(u).netloc)


_SAVE_LOCK = threading.Lock()


class DB:
    def __init__(self, path):
        self.path = path
        j = {}
        if os.path.exists(path):
            try:
                j = json.load(open(path, encoding='utf-8'))
            except Exception:
                j = {}
        self.recs = j.get('institutions', {})
        self.progress = j.get('progress', {})
        self.idx = {}
        for k, r in self.recs.items():
            self._index(k, r)
        self.added = self.merged = 0

    def _keys(self, r):
        ks = []
        if r.get('ror'):
            ks.append('ror:' + r['ror'])
        if r.get('wd'):
            ks.append('wd:' + r['wd'])
        if r.get('w'):
            ks.append('dom:' + reg_domain(r['w']) + '|' + (r.get('cc') or ''))
        if not ks:
            ks.append('nm:' + re.sub(r'\W+', '', (r.get('n') or '').lower()) + '|' + (r.get('cc') or ''))
        return ks

    def _index(self, k, r):
        for x in self._keys(r):
            self.idx.setdefault(x, k)

    def add(self, src, n, cc, w='', ror='', wd='', oa='', city=''):
        n = (n or '').strip()
        if not n or not cc:
            return
        r = dict(n=n[:120], cc=cc.upper(), w=w if good_url(w) else '', ror=(ror or '').replace('https://ror.org/', ''), wd=(wd or '').split('/')[-1], oa=(oa or '').split('/')[-1], c=city or '')
        hit = next((self.idx[x] for x in self._keys(r) if x in self.idx), None)
        if hit:
            e = self.recs[hit]
            for f in ('w', 'ror', 'wd', 'oa', 'c'):
                if r[f] and not e.get(f):
                    e[f] = r[f]
            if src not in e['s']:
                e['s'].append(src)
            self._index(hit, e)
            self.merged += 1
            return
        r['s'] = [src]
        r['d'] = TODAY
        key = 'I' + format(len(self.recs) + 1, '06d')
        while key in self.recs:
            key += 'x'
        self.recs[key] = r
        self._index(key, r)
        self.added += 1

    def save(self):
        with _SAVE_LOCK:
            tmp = self.path + '.tmp'
            snap = dict(updated=TODAY, progress=json.loads(json.dumps(self.progress)), institutions=dict(self.recs))
            json.dump(snap, open(tmp, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
            os.replace(tmp, self.path)


def get_json(url, params, tries=3, timeout=40):
    last = ''
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers={'User-Agent': UA, 'Accept': 'application/json'}, timeout=timeout)
            if r.status_code == 200:
                return r.json(), ''
            last = f'HTTP {r.status_code}'
            if r.status_code in (401, 403, 404, 400):
                break
            time.sleep(2 + 3 * i)
        except Exception as ex:
            last = str(ex)[:80]
            time.sleep(2 + 3 * i)
    return None, last


# ---------------------------------------------------------------- directories (each returns (items_added, finished))
def ror_page(db, cc, page):
    j, err = get_json('https://api.ror.org/v2/organizations', {'filter': f'country.country_code:{cc},types:education,status:active', 'page': page})
    if j is None:
        return None, err
    items = j.get('items', [])
    for it in items:
        name = next((x['value'] for x in it.get('names', []) if 'ror_display' in x.get('types', [])), '')
        site = next((x['value'] for x in it.get('links', []) if x.get('type') == 'website'), '')
        wd = ''
        for x in it.get('external_ids', []):
            if x.get('type') == 'wikidata':
                wd = x.get('preferred') or (x.get('all') or [''])[0]
        city = ''
        for loc in it.get('locations', []):
            city = (loc.get('geonames_details') or {}).get('name', '') or city
        db.add('ror', name, cc, site, it.get('id', ''), wd, '', city)
    total = j.get('number_of_results', 0)
    return (len(items) == 0 or page * 20 >= min(total, 10000)), ''


def oa_page(db, cc, page):
    p = {'filter': f'type:education,country_code:{cc}', 'per-page': 200, 'page': page, 'sort': 'works_count:desc', 'select': 'id,display_name,homepage_url,country_code,ror,geo,ids'}
    if os.environ.get('OPENALEX_API_KEY'):
        p['api_key'] = os.environ['OPENALEX_API_KEY']
    if os.environ.get('CONTACT_EMAIL'):
        p['mailto'] = os.environ['CONTACT_EMAIL']
    j, err = get_json('https://api.openalex.org/institutions', p)
    if j is None:
        return None, err
    res = j.get('results', [])
    for it in res:
        db.add('openalex', it.get('display_name'), cc, it.get('homepage_url') or '', it.get('ror') or '', (it.get('ids') or {}).get('wikidata') or '', it.get('id'), (it.get('geo') or {}).get('city') or '')
    total = (j.get('meta') or {}).get('count', 0)
    return (len(res) == 0 or page * 200 >= min(total, 10000)), ''


WD_TYPES = 'wd:Q3918 wd:Q875538 wd:Q15936437 wd:Q902104 wd:Q23002054 wd:Q31855 wd:Q1664720'


def wd_page(db, cc, page):
    q = ('SELECT ?i ?iLabel ?site WHERE { VALUES ?t { %s } ?i wdt:P31 ?t; wdt:P17 ?c. ?c wdt:P297 "%s". OPTIONAL { ?i wdt:P856 ?site } '
         'FILTER NOT EXISTS { ?i wdt:P576 ?end } SERVICE wikibase:label { bd:serviceParam wikibase:language "en". } } LIMIT 500 OFFSET %d') % (WD_TYPES, cc, (page - 1) * 500)
    j, err = get_json('https://query.wikidata.org/sparql', {'query': q, 'format': 'json'}, tries=2, timeout=60)
    if j is None:
        return None, err
    rows = j['results']['bindings']
    for b in rows:
        db.add('wikidata', b.get('iLabel', {}).get('value', ''), cc, b.get('site', {}).get('value', ''), '', b['i']['value'])
    return (len(rows) < 500 or page >= 6), ''


DIRS = [('ror', ror_page, 0.25), ('openalex', oa_page, 0.2), ('wikidata', wd_page, 1.5)]


def main():
    global db
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'institutions.json'))
    ap.add_argument('--budget-min', type=int, default=int(os.environ.get('BUDGET_MIN', 60)))
    ap.add_argument('--countries', default='')
    a = ap.parse_args()
    deadline = time.time() + a.budget_min * 60
    db = DB(a.out)
    ccs = a.countries.split(',') if a.countries else ISO
    print(f'start: {len(db.recs)} institutions already in the database', flush=True)
    guard.start(deadline, db.save, grace=120, every=240)
    fails = {d[0]: 0 for d in DIRS}
    # one pass over all (directory, country) tasks that are not finished; a directory that keeps failing is skipped for this run
    tasks = [(d, cc) for cc in ccs for d in DIRS]
    for (name, fn, pause), cc in tasks:
        if time.time() > deadline - 30:
            break
        prog = db.progress.setdefault(name, {}).setdefault(cc, {'page': 1, 'done': False})
        if prog['done'] or fails[name] >= 8:
            continue
        while not prog['done'] and time.time() < deadline - 30:
            fin, err = fn(db, cc, prog['page'])
            if fin is None:
                fails[name] += 1
                print(f'  {name} {cc} page {prog["page"]}: {err}', flush=True)
                break
            fails[name] = 0
            if fin:
                prog['done'] = True
            else:
                prog['page'] += 1
            time.sleep(pause)
        if prog['done']:
            n = sum(1 for r in db.recs.values() if r['cc'] == cc)
            print(f'  {name} {cc} done  (database now has {n} for {cc}; total {len(db.recs)})', flush=True)
    db.save()
    left = sum(1 for d in DIRS for cc in ccs if not db.progress.get(d[0], {}).get(cc, {}).get('done'))
    by = {}
    for r in db.recs.values():
        by[r['cc']] = by.get(r['cc'], 0) + 1
    print(f'INSTITUTIONS: {len(db.recs)} in {len(by)} countries | added this run {db.added}, merged duplicates {db.merged} | tasks left {left} | with website {sum(1 for r in db.recs.values() if r["w"])}', flush=True)


if __name__ == '__main__':
    main()
