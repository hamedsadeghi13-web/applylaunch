#!/usr/bin/env python3
"""ApplyLaunch crawler.

Reads crawler/sources.json (886 portals, universities, funders), visits each source politely,
finds PhD / Master / scholarship / research postings, extracts the facts and writes
docs/data/positions.json for the website. Runs automatically every day via GitHub Actions.

Local test:  python crawler/crawl.py --limit 20
"""
import argparse, datetime as dt, json, os, re, sys, threading, time, zlib
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse, urldefrag
import urllib.robotparser as rp

import requests
from bs4 import BeautifulSoup

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
UA = os.environ.get('CRAWLER_UA', 'ApplyLaunchBot/1.0 (academic opportunity search; respects robots.txt)')
TODAY = dt.date.today()
sys.path.insert(0, HERE)
import render                                              # optional headless browser for JavaScript-built pages
MAX_RENDER_DETAIL = 8                                      # detail pages rendered with the browser per source and run

# ------------------------------------------------------------------ keyword lists
TYPES = [  # first match wins (checked on the title, then on the start of the page)
    ('professor', 'professor;lecturer;chair of;professur;habilitation;assistant professor;associate professor;tenure'),
    ('postdoc', 'postdoc;post-doc;postdoctoral;post doctoral'),
    ('phd', 'phd;ph.d;doctoral;doctorate;doctoral researcher;doctoral candidate;doktorand;promotionsstelle;doctorant;promovend;dottorato;doctorado;doutoramento;phd student;promotion;doktora'),
    ('master', 'master;msc;m.sc;m.arch;mphil;masters programme;master programme;yüksek lisans'),
    ('scholar', 'scholarship;fellowship;stipend;bursary;studentship;grant for;burs'),
    ('intern', 'internship;intern;praktikum;trainee'),
    ('job', 'research associate;research assistant;research fellow;researcher;wissenschaftliche;chercheur;junior researcher;project assistant;scientist'),
]
TYPES = [(n, k.split(';')) for n, k in TYPES]
FUND_FULL = 'fully funded;full funding;fully-funded;funded phd;paid position;employment contract;tv-l;tv-ö;e13;e 13;salary;gehalt;vergütung;stipend;tuition waiver;tuition fees waived;full scholarship;salaire;remuneration;bruttogehalt;loon;cao'.split(';')
FUND_SELF = 'self-funded;self funded;unfunded;no funding;own funding'.split(';')
FUND_PART = 'partial funding;partially funded;partial scholarship;fee waiver only;top-up;part-funded'.split(';')
DEADLINE_RX = re.compile(r'(deadline|closing date|apply by|application deadline|clos(?:e|es|ing)(?: date| on)?|due date|must be received by|submitted by|bewerbungsfrist|bewerbung bis|date limite|sluitingsdatum|einsendeschluss|scadenza|fecha límite|fin de plazo|son başvuru)[^0-9a-zA-Z]{0,6}.{0,60}', re.I)
MONTHS = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'mai': 5, 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'okt': 10, 'nov': 11, 'dec': 12, 'dez': 12}
MON = r'(jan|feb|mar|apr|may|mai|jun|jul|aug|sep|oct|okt|nov|dec|dez)[a-z]*'
SKIP_LINK = re.compile(r'^(login|log in|sign in|register|privacy|cookie|contact|about|home|read more|more details|apply now|next|previous|imprint|impressum)', re.I)
POSTING_URL = re.compile(r'/(jobs?|vacanc[a-z]*|offres?|stellen[a-z]*|vacatures?|positions?|opportunit[a-z]*|phd[a-z-]*|studentships?|projects?|angebot[a-z]*|scholarships?|funding)/[^?#]*\d{3,}|[?&](jobid|job_id|vacancyid|vacancy_id|positionid|id|ref|jobref)=\d{3,}|/offres/20\d\d-\d+', re.I)
BAD_EXT = re.compile(r'\.(pdf|jpe?g|png|gif|svg|zip|docx?|xlsx?|pptx?|mp4|css|js)(\?|$)', re.I)

# country names -> ISO2 (English names + common local/alias forms)
CN = {
 'Afghanistan':'AF','Albania':'AL','Algeria':'DZ','Argentina':'AR','Armenia':'AM','Australia':'AU','Austria':'AT','Azerbaijan':'AZ','Bahrain':'BH','Bangladesh':'BD','Belarus':'BY','Belgium':'BE','Bolivia':'BO','Bosnia and Herzegovina':'BA','Brazil':'BR','Bulgaria':'BG','Cambodia':'KH','Canada':'CA','Chile':'CL','China':'CN','Colombia':'CO','Costa Rica':'CR','Croatia':'HR','Cuba':'CU','Cyprus':'CY','Czechia':'CZ','Czech Republic':'CZ','Denmark':'DK','Ecuador':'EC','Egypt':'EG','Estonia':'EE','Ethiopia':'ET','Finland':'FI','France':'FR','Georgia':'GE','Germany':'DE','Ghana':'GH','Greece':'GR','Hong Kong':'HK','Hungary':'HU','Iceland':'IS','India':'IN','Indonesia':'ID','Iran':'IR','Iraq':'IQ','Ireland':'IE','Israel':'IL','Italy':'IT','Japan':'JP','Jordan':'JO','Kazakhstan':'KZ','Kenya':'KE','Kuwait':'KW','Latvia':'LV','Lebanon':'LB','Lithuania':'LT','Luxembourg':'LU','Malaysia':'MY','Malta':'MT','Mexico':'MX','Morocco':'MA','Nepal':'NP','Netherlands':'NL','The Netherlands':'NL','New Zealand':'NZ','Nigeria':'NG','North Macedonia':'MK','Norway':'NO','Oman':'OM','Pakistan':'PK','Peru':'PE','Philippines':'PH','Poland':'PL','Portugal':'PT','Qatar':'QA','Romania':'RO','Russia':'RU','Saudi Arabia':'SA','Serbia':'RS','Singapore':'SG','Slovakia':'SK','Slovenia':'SI','South Africa':'ZA','South Korea':'KR','Korea':'KR','Spain':'ES','Sri Lanka':'LK','Sweden':'SE','Switzerland':'CH','Taiwan':'TW','Thailand':'TH','Tunisia':'TN','Turkey':'TR','Türkiye':'TR','Turkiye':'TR','Uganda':'UG','Ukraine':'UA','United Arab Emirates':'AE','UAE':'AE','United Kingdom':'GB','UK':'GB','Great Britain':'GB','England':'GB','Scotland':'GB','Wales':'GB','United States':'US','USA':'US','U.S.A.':'US','Uruguay':'UY','Uzbekistan':'UZ','Venezuela':'VE','Vietnam':'VN','Viet Nam':'VN',
 'Deutschland':'DE','Österreich':'AT','Schweiz':'CH','Suisse':'CH','Svizzera':'CH','Nederland':'NL','België':'BE','Belgique':'BE','Italia':'IT','España':'ES','Sverige':'SE','Norge':'NO','Suomi':'FI','Danmark':'DK','Polska':'PL','Česko':'CZ','Magyarország':'HU','Ελλάδα':'GR','Portugal ':'PT',
}
CN_RX = re.compile(r'(?<![A-Za-z])(' + '|'.join(re.escape(k.strip()) for k in sorted(CN, key=len, reverse=True)) + r')(?![A-Za-z])')
ISO_NAME = {}
for k, v in CN.items():
    ISO_NAME.setdefault(v, k.strip())
ISO_NAME.update({'GB': 'United Kingdom', 'US': 'United States', 'CZ': 'Czechia', 'NL': 'Netherlands', 'KR': 'South Korea', 'TR': 'Turkey', 'AE': 'United Arab Emirates', 'VN': 'Vietnam'})

# ------------------------------------------------------------------ polite fetching
class Fetcher:
    def __init__(self, delay=1.0, timeout=20):
        self.delay, self.timeout = delay, timeout
        self.s = requests.Session()
        self.s.headers.update({'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,application/xml,application/rss+xml;q=0.9,*/*;q=0.5', 'Accept-Language': 'en,de;q=0.7,fr;q=0.6'})
        self.lock = threading.Lock()
        self.next_ok = {}
        self.robots = {}

    def _wait(self, host):
        with self.lock:
            now = time.time()
            at = max(now, self.next_ok.get(host, 0))
            self.next_ok[host] = at + self.delay
        if at > now:
            time.sleep(at - now)

    def allowed(self, url):
        p = urlparse(url)
        host = p.netloc
        if host not in self.robots:
            r = rp.RobotFileParser()
            try:
                resp = self.s.get(f'{p.scheme}://{host}/robots.txt', timeout=10)
                if resp.status_code == 200 and len(resp.text) < 500000:
                    r.parse(resp.text.splitlines())
                else:
                    r.parse([])
            except Exception:
                r.parse([])
            self.robots[host] = r
        try:
            return self.robots[host].can_fetch(UA, url)
        except Exception:
            return True

    def get(self, url):
        """returns (text, content_type) or raises"""
        if not self.allowed(url):
            raise PermissionError('robots.txt')
        self._wait(urlparse(url).netloc)
        r = self.s.get(url, timeout=(10, self.timeout), allow_redirects=True)
        if r.status_code >= 400:
            raise RuntimeError(f'HTTP {r.status_code}')
        if len(r.content) > 3_000_000:
            raise RuntimeError('too large')
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != 'iso-8859-1' else r.apparent_encoding
        return r.text, r.headers.get('content-type', ''), r.url

# ------------------------------------------------------------------ helpers
def has_any(s, kws):
    s = s.lower()
    return any(k in s for k in kws)

def norm_url(u):
    u = urldefrag(u)[0].strip()
    p = urlparse(u)
    q = '&'.join(x for x in p.query.split('&') if x and not x.lower().startswith(('utm_', 'fbclid', 'gclid', 'session')))
    return f'{p.scheme}://{p.netloc.lower()}{p.path.rstrip("/") or "/"}' + (f'?{q}' if q else '')

def parse_date(s):
    s = s or ''
    m = re.search(r'(\d{1,2})(?:st|nd|rd|th|\.)?(?:\s+of)?[\s.\-/]+' + MON + r'\.?,?[\s.\-/]*(\d{4})', s, re.I)
    if m:
        return _mk(int(m.group(3)), MONTHS.get(m.group(2).lower()[:3]), int(m.group(1)))
    m = re.search(MON + r'\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})', s, re.I)
    if m:
        return _mk(int(m.group(3)), MONTHS.get(m.group(1).lower()[:3]), int(m.group(2)))
    m = re.search(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r'(\d{1,2})[./](\d{1,2})[./](\d{4})', s)
    if m:
        return _mk(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    return None

def _mk(y, mo, d):
    try:
        return dt.date(y, mo, d)
    except Exception:
        return None

def find_deadline(text):
    for m in DEADLINE_RX.finditer(text[:60000]):
        d = parse_date(m.group(0))
        if d:
            return d
    return None

CUR = {'€': 'EUR', 'eur': 'EUR', 'euro': 'EUR', '$': 'USD', 'usd': 'USD', '£': 'GBP', 'gbp': 'GBP', 'chf': 'CHF', 'sek': 'SEK', 'nok': 'NOK', 'dkk': 'DKK', 'cad': 'CAD', 'aud': 'AUD', 'pln': 'PLN', 'czk': 'CZK', 'jpy': 'JPY', '¥': 'JPY', 'krw': 'KRW', 'cny': 'CNY', 'sgd': 'SGD', 'try': 'TRY', 'aed': 'AED', 'huf': 'HUF'}

FXE = {'EUR': 1, 'USD': .92, 'GBP': 1.17, 'CHF': 1.05, 'SEK': .09, 'NOK': .085, 'DKK': .134, 'CAD': .67, 'AUD': .6, 'PLN': .23, 'CZK': .04, 'HUF': .0025, 'JPY': .006, 'KRW': .00068, 'CNY': .127, 'SGD': .69, 'TRY': .027, 'AED': .25}

def find_salary(text):
    """returns (monthly_amount, currency) or (None, None)"""
    for m in re.finditer(r'(salary|stipend|gross|remuneration|gehalt|brutto|compensation|tv-l|tv-ö|monthly|per month|vergütung|salaire|loon)', text[:80000], re.I):
        seg = text[max(0, m.start() - 60): m.end() + 160]
        mm = re.search(r'(€|\$|£|¥|EUR|USD|GBP|CHF|SEK|NOK|DKK|CAD|AUD|PLN|CZK|JPY|KRW|CNY|SGD|TRY|AED|HUF)\s?(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+)|(\d{1,3}(?:[.,\s]\d{3})*(?:[.,]\d+)?|\d+)\s?(€|\$|£|EUR|USD|GBP|CHF|SEK|NOK|DKK|CAD|AUD|PLN|CZK|JPY|KRW|CNY|SGD|TRY|AED|HUF|euro)', seg, re.I)
        if not mm:
            continue
        cur = (mm.group(1) or mm.group(4)).lower()
        raw = mm.group(2) or mm.group(3)
        raw = re.sub(r'[\s]', '', raw)
        if re.search(r'[.,]\d{3}$', raw) or re.search(r'[.,]\d{3}[.,]', raw):
            raw = re.sub(r'[.,]', '', raw)
        else:
            raw = raw.replace(',', '.')
        try:
            v = float(raw)
        except ValueError:
            continue
        low = seg.lower()
        if re.search(r'per year|annual|p\.a\.|per annum|jährlich|pro jahr|per jaar|par an|/year|yearly', low):
            v /= 12
        elif re.search(r'per week|weekly', low):
            v *= 4.33
        c = CUR.get(cur, cur.upper())
        if 300 <= v * FXE.get(c, 1) <= 15000:
            return round(v), c
    return None, None

def find_duration(text):
    for m in re.finditer(r'(duration|period|contract|fixed[- ]term|befristet|laufzeit|durée|duur|length)', text[:80000], re.I):
        seg = text[m.start(): m.end() + 90]
        mm = re.search(r'(\d+(?:[.,]\d)?)\s*(years?|yrs?|months?|jahre?n?|monate?n?|ans|jaar|maanden|mois)', seg, re.I)
        if mm:
            n = float(mm.group(1).replace(',', '.'))
            if mm.group(2).lower().startswith(('month', 'monat', 'mois', 'maand')):
                n = round(n / 12, 1)
            if 0.2 <= n <= 8:
                return f'{n:g} years'
    return 'Not stated'

def yes_no(text, word, neg):
    t = text.lower()
    if re.search(neg, t):
        return 'No'
    return 'Yes' if word in t else 'Not stated'

def find_country(text, default=None):
    m = CN_RX.search(text)
    if m:
        return CN[m.group(1)] if m.group(1) in CN else CN.get(m.group(1) + ' ')
    return default

# ------------------------------------------------------------------ analysis of one posting page
def jsonld_jobs(soup):
    out = []
    for tag in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(tag.string or tag.get_text() or '')
        except Exception:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                t = x.get('@type')
                if t == 'JobPosting' or (isinstance(t, list) and 'JobPosting' in t):
                    out.append(x)
                for k in ('@graph', 'itemListElement', 'item'):
                    if k in x:
                        stack.append(x[k])
    return out

# keywords are matched as WORDS (a keyword may continue into a longer word only if listed that way), never as bare substrings:
# "intern" used to match "international", "burs" matched "Bursa", "master" matched "Mastering" ...
_STRICT = {'intern', 'master', 'burs', 'promotion', 'grant for', 'chair of', 'msc', 'm.sc', 'trainee', 'tenure'}
def _kw_rx(k):
    return re.compile(r'(?<![a-z\u00c0-\u024f])' + re.escape(k) + (r"(?:s|'s|e?s)?(?![a-z\u00c0-\u024f])" if k in _STRICT else ''))
_TYPE_RX = [(n, [_kw_rx(k) for k in kws]) for n, kws in TYPES]

def classify(title, body):
    for scope in (title, body[:800]):
        s = scope.lower()
        for name, rxs in _TYPE_RX:
            if any(r.search(s) for r in rxs):
                return name
    return None

_TYPE_NAME = {'phd': 'PhD', 'master': 'Master', 'scholar': 'Scholarship', 'postdoc': 'Postdoc', 'intern': 'Internship', 'job': 'Research job'}

def retype_stored(pos):
    """One-time repair of records that were typed with the old substring rule (e.g. 'International ...' stored as Internship).
    Nothing is deleted: a record that no longer looks like an internship becomes the generic 'Research job' type."""
    n = 0
    for r in pos.values():
        t = classify(r.get('title', ''), '')
        new = _TYPE_NAME.get(t) if t and t != 'professor' else None
        if new and new != r.get('type') and (r.get('type') == 'Internship' or not r.get('retyped')):
            r['type'], r['retyped'] = new, True; n += 1
        elif not new and r.get('type') == 'Internship':
            r['type'], r['retyped'] = 'Research job', True; n += 1
    return n

def analyse(url, html, src, hub, jobld=None):
    soup = BeautifulSoup(html, 'lxml')
    for t in soup(['script', 'style', 'noscript', 'nav', 'footer', 'header', 'form']):
        if not (t.name == 'script' and t.get('type') == 'application/ld+json'):
            t.decompose()
    jl = jobld or (jsonld_jobs(soup) or [None])[0]
    h1 = soup.find('h1')
    title = ''
    if jl and jl.get('title'):
        title = str(jl['title'])
    elif h1:
        title = h1.get_text(' ', strip=True)
    elif soup.title:
        title = soup.title.get_text(' ', strip=True)
    title = re.sub(r'\s+', ' ', title).strip()[:170]
    if len(title) < 8:
        return None, 'no title'
    body = re.sub(r'\s+', ' ', (BeautifulSoup(str(jl.get('description', '')), 'lxml').get_text(' ') + ' ' if jl and jl.get('description') else '') + soup.get_text(' '))[:120000]
    typ = classify(title, body)
    if typ in (None, 'professor'):
        return None, 'type'
    if typ == 'job' and not re.search(r'phd|doctoral|research|science|scientific|wissenschaft', title, re.I):
        return None, 'type'
    low = body.lower()
    full, selff, part = has_any(low, FUND_FULL), has_any(low, FUND_SELF), has_any(low, FUND_PART)
    funding = 'Partial' if (full and (selff or part)) or part else 'Full' if full else 'Self-funded' if selff else 'Unclear'
    # deadline
    dl = None
    if jl and jl.get('validThrough'):
        dl = parse_date(str(jl['validThrough']))
    dl = dl or find_deadline(body)
    if dl and dl < TODAY:
        return None, 'expired'
    if dl and (dl - TODAY).days > 900:
        dl = None
    # salary
    sal, cur = None, None
    bs = jl.get('baseSalary') if jl else None
    if isinstance(bs, dict):
        v = bs.get('value')
        val = v.get('value') or v.get('minValue') if isinstance(v, dict) else v
        try:
            val = float(val)
            unit = (v.get('unitText') if isinstance(v, dict) else '') or ''
            if unit.upper() == 'YEAR':
                val /= 12
            elif unit.upper() == 'WEEK':
                val *= 4.33
            if 300 <= val * FXE.get(str(bs.get('currency') or 'EUR').upper(), 1) <= 15000:
                sal, cur = round(val), str(bs.get('currency') or 'EUR').upper()
        except Exception:
            pass
    if sal is None:
        sal, cur = find_salary(body)
    # place
    city, cc = src.get('city') or '', None
    inst = ''
    if jl:
        org = jl.get('hiringOrganization')
        inst = (org.get('name') if isinstance(org, dict) else org) or ''
        loc = jl.get('jobLocation')
        loc = loc[0] if isinstance(loc, list) and loc else loc
        addr = (loc or {}).get('address', {}) if isinstance(loc, dict) else {}
        if isinstance(addr, dict):
            city = addr.get('addressLocality') or city
            ac = addr.get('addressCountry')
            ac = ac.get('name') if isinstance(ac, dict) else ac
            if ac:
                cc = ac.upper() if len(str(ac)) == 2 else CN.get(str(ac).strip().title()) or CN.get(str(ac).strip())
    sc = (src.get('country') or '').strip()
    fixed_country = src.get('type') in ('university', 'institute', 'national-board', 'architecture-board') and (sc in CN or bool(src.get('cc')))
    if not cc:
        cc = (src.get('cc') or CN[sc]) if fixed_country else (find_country(title + ' ' + body[:2500]) or (CN.get(sc) if sc in CN else None))
    if not cc:
        return None, 'country'
    if src.get('type') in ('university', 'institute'):
        inst = inst or src['name']
    if not inst:
        m = re.search(r'((?:University|Universität|Université|Universiteit|Universidad|Università|Politecnico|ETH|Institute|Institut|College) (?:of |for )?[A-Z][\w\-\' ]{2,45})|([A-Z][\w\-\']+(?: [A-Z][\w\-\']+){0,3} (?:University|Universität|Universiteit|Institute|Hochschule)(?: (?:of |für )?[A-Z][\w\-]+)?)', body[:4000])
        inst = (m.group(0) if m else hub).strip()[:90]
    sup = []
    for m in re.finditer(r'(?:Prof\.?(?: Dr\.?)?(?: habil\.?)?|Professor|Dr\.) ([A-ZÀ-Ý][\w\-\']+(?: [A-ZÀ-Ý][\w\-\']+){1,2})', body[:20000]):
        if m.group(1) not in sup:
            sup.append(m.group(1))
    meta = soup.find('meta', attrs={'name': re.compile('^keywords$', re.I)})
    topics = (meta.get('content', '') if meta else '')[:200]
    ielts = ''
    m = re.search(r'IELTS[^.]{0,50}?\b([5-8](?:\.[05])?)\b', body)
    if m:
        ielts = m.group(1)
    fee = ''
    m = re.search(r'(application|admission)\s+fee[^.]{0,30}?(€|\$|£|EUR|USD|GBP|CHF)\s?(\d{2,4})', body, re.I)
    if m:
        fee = m.group(3)
    elif re.search(r'no (application|admission) fee|application is free|free of charge', low):
        fee = 'None'
    rec = dict(
        id=zlib.crc32(norm_url(url).encode()) & 0x7fffffff, title=title, inst=inst, city=city or '', country=ISO_NAME.get(cc) or (sc if fixed_country and sc not in ('Global', 'Europe', 'Multi') else cc), cc=cc,
        type={'phd': 'PhD', 'master': 'Master', 'scholar': 'Scholarship', 'postdoc': 'Postdoc', 'intern': 'Internship', 'job': 'Research job'}[typ],
        hub=hub, url=url, deadline=dl.isoformat() if dl else None, funding=funding, duration=find_duration(body),
        salary=sal, currency=cur, portfolio=yes_no(body, 'portfolio', r'no portfolio|portfolio (is )?not required'),
        proposal=yes_no(body, 'proposal', r'no (research )?proposal|proposal (is )?not required'),
        fee=fee or 'Not stated', ielts=ielts, gre='Yes' if re.search(r'\bGRE\b', body) and not re.search(r'no GRE|GRE (is )?not (required|needed)|without GRE|GRE waived', body, re.I) else '', topics=topics, sup=sup[:3])
    return rec, 'ok'

# ------------------------------------------------------------------ one source
def listing_candidates(text, ctype, base):
    """returns (candidates [(url, text)], direct_jobs [jsonld dicts])"""
    cands, jobs = [], []
    stripped = text.lstrip()[:200].lower()
    if 'xml' in ctype or stripped.startswith(('<?xml', '<rss', '<feed')):
        soup = BeautifulSoup(text, 'xml')
        for it in soup.find_all(['item', 'entry']):
            link = it.find('link')
            href = (link.get('href') if link and link.get('href') else link.get_text(strip=True) if link else '')
            t = it.find('title')
            if href:
                cands.append((urljoin(base, href), t.get_text(' ', strip=True) if t else ''))
        return cands, jobs
    soup = BeautifulSoup(text, 'lxml')
    jobs = jsonld_jobs(soup)
    for a in soup.find_all('a', href=True):
        h = a['href'].strip()
        if h.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        u = urljoin(base, h)
        if not u.startswith('http') or BAD_EXT.search(u):
            continue
        t = a.get_text(' ', strip=True)
        if POSTING_URL.search(u):
            cands.append((u, t))
            continue
        if len(t) < 12 or SKIP_LINK.match(t):
            continue
        tl = t.lower()
        if any(k in tl for _, kws in TYPES if _ != 'professor' for k in kws):
            cands.append((u, t))
    seen, out = set(), []
    for u, t in cands:
        k = norm_url(u)
        if k not in seen:
            seen.add(k)
            out.append((u, t))
    return out, jobs

def crawl_source(src, F, state_pos, max_links, deadline_ts):
    stat = dict(ok=False, found=0, new=0, seen=0, err='', method='', js=False, needs_adapter=False, rendered=0)
    methods = []
    hub = src['name']
    urls = []
    for u in list(src.get('listing') or []) + [src.get('search'), src.get('url')] + list(src.get('rss') or []):
        if u and u.startswith('http') and u not in urls:
            urls.append(u)
    new_recs, touched = [], []
    cands_all, direct = [], []
    js_listing = set()
    import adapters
    extra_c, extra_raw = adapters.run(src, F)
    cands_all += extra_c
    for raw in extra_raw[:max_links * 3]:
        rec = adapters.record_from_fields(raw, src, hub)
        if rec:
            new_recs.append(rec)
    if extra_c or extra_raw:
        stat['ok'] = True
        methods.append('adapter')
    for lu in urls[:5]:
        if time.time() > deadline_ts:
            break
        try:
            text, ctype, final = F.get(lu)
        except Exception as e:
            stat['err'] = str(e)[:80]
            continue
        stat['ok'] = True
        c, jobs = listing_candidates(text, ctype, final)
        if c or jobs:
            methods.append('rss' if ('xml' in ctype or text.lstrip()[:200].lower().startswith(('<?xml', '<rss', '<feed'))) else 'html')
        elif render.looks_js(text) or src.get('js'):
            # the light method found nothing and the page is an empty JavaScript shell -> retry with the headless browser
            stat['js'] = True
            try:
                snaps, rfinal = render.render(lu)
                stat['rendered'] += 1
                for snap in snaps:
                    c2, j2 = listing_candidates(snap, 'text/html', rfinal)
                    c += c2
                    jobs += j2
                if c or jobs:
                    methods.append('playwright')
                    js_listing.add(norm_url(rfinal))
            except Exception as e:
                stat['err'] = ('browser: ' + str(e))[:80]
            if not (c or jobs):
                stat['needs_adapter'] = True
        cands_all += c
        direct += jobs
    # direct JSON-LD postings found on listing pages
    for j in direct[:max_links]:
        u = j.get('url') or j.get('sameAs') or (urls[0] if urls else '')
        if not u:
            continue
        try:
            rec, why = analyse(urljoin(urls[0], u), '<html></html>', src, hub, jobld=j)
        except Exception:
            continue
        if rec:
            new_recs.append(rec)
    n_open = 0
    seen = set()
    for u, t in cands_all:
        k = norm_url(u)
        if k in seen:
            continue
        seen.add(k)
        if k in state_pos:
            touched.append(k)
            stat['seen'] += 1
            continue
        if n_open >= max_links or time.time() > deadline_ts:
            continue
        n_open += 1
        try:
            html, _, final = F.get(u)
            if stat['js'] and stat['rendered'] <= MAX_RENDER_DETAIL and render.looks_js(html):     # detail pages of a JS site are JS-built too
                try:
                    snaps, final = render.render(u, pages=1)
                    html = snaps[-1]
                    stat['rendered'] += 1
                    if 'playwright' not in methods:
                        methods.append('playwright')
                except Exception:
                    pass
            rec, why = analyse(final, html, src, hub)
        except Exception:
            continue
        if rec:
            rec['_k'] = norm_url(final)
            new_recs.append(rec)
    for r in new_recs:
        r['sid'] = src['id']
    stat['found'] = len(cands_all)
    stat['new'] = len(new_recs)
    stat['method'] = '+'.join(dict.fromkeys(methods))
    if new_recs or stat['seen']:
        stat['needs_adapter'] = False
    return stat, new_recs, touched

# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sources', default=os.path.join(HERE, 'sources.json'))
    ap.add_argument('--state', default=os.path.join(HERE, 'state.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', 'data', 'positions.json'))
    ap.add_argument('--limit', type=int, default=0, help='only the first N sources (testing)')
    ap.add_argument('--workers', type=int, default=int(os.environ.get('WORKERS', 24)))
    ap.add_argument('--max-links', type=int, default=int(os.environ.get('MAX_LINKS', 40)))
    ap.add_argument('--budget-min', type=int, default=int(os.environ.get('BUDGET_MIN', 300)))
    ap.add_argument('--delay', type=float, default=float(os.environ.get('DELAY', 1.0)))
    a = ap.parse_args()
    t0 = time.time()
    deadline_ts = t0 + a.budget_min * 60
    sources = json.load(open(a.sources, encoding='utf-8'))
    reg_path = os.path.join(HERE, 'registry.json')           # sources found by discover.py
    if os.path.exists(reg_path):
        known = {s['id'] for s in sources}
        sources += [r for r in json.load(open(reg_path, encoding='utf-8')).get('sources', []) if r.get('status') in ('verified', 'js_required') and r['id'] not in known]
    state = json.load(open(a.state, encoding='utf-8')) if os.path.exists(a.state) else {}
    pos = state.get('positions', {})
    print('retyped stored positions:', retype_stored(pos), flush=True)
    sstat = state.get('sources', {})
    # sources that failed many times in a row are retried only once a week
    def due(s):
        st = sstat.get(s['id'], {})
        if st.get('fails', 0) >= 6 and st.get('last_try') and (TODAY - dt.date.fromisoformat(st['last_try'])).days < 7:
            return False
        return s.get('active', True)
    todo = [s for s in sources if due(s)]
    todo.sort(key=lambda s: sstat.get(s['id'], {}).get('last_try', ''))   # least recently visited first, so every source is covered over time
    if a.limit:
        todo = todo[:a.limit]
    render.configure(float(os.environ.get('RENDER_BUDGET_MIN', 45)))
    F = Fetcher(delay=a.delay)
    lock = threading.Lock()
    done = [0]
    dup_n, stale_n = [0], [0]

    def work(s):
        if time.time() > deadline_ts:
            return
        try:
            stat, recs, touched = crawl_source(dict(s, js=bool(sstat.get(s['id'], {}).get('js') or s.get('js'))), F, pos, a.max_links, deadline_ts)
        except Exception as e:
            stat, recs, touched = dict(ok=False, err=str(e)[:80], found=0, new=0, seen=0), [], []
        with lock:
            now = TODAY.isoformat()
            for k in touched:
                pos[k]['last_seen'] = now
            for r in recs:
                k = r.pop('_k', None) or norm_url(r['url'])
                r['first_seen'] = now
                r['last_seen'] = now
                pos[k] = r
            old = sstat.get(s['id'], {})
            sstat[s['id']] = dict(name=s['name'], last_try=now, ok=stat['ok'], found=stat['found'], new=stat['new'], err=stat['err'],
                                  fails=0 if stat['ok'] else old.get('fails', 0) + 1,
                                  method=stat.get('method') or old.get('method', ''), js=bool(stat.get('js') or old.get('js')),
                                  needs_adapter=bool(stat.get('needs_adapter')), rendered=stat.get('rendered', 0))
            done[0] += 1
            if done[0] % 25 == 0:
                print(f'  {done[0]}/{len(todo)} sources, {len(pos)} positions, {int(time.time()-t0)}s', flush=True)

    def save():
        """clean + publish + checkpoint (end of run, every 15 min, and by the watchdog)"""
        import guard
        pos_c, ss_c = guard.snapshot(pos), guard.snapshot(sstat)
        out, seen_key = [], set()
        dup_n[0] = stale_n[0] = 0
        for k, r in list(pos_c.items()):
            dl = dt.date.fromisoformat(r['deadline']) if r.get('deadline') else None
            stale = (TODAY - dt.date.fromisoformat(r['last_seen'])).days > 21
            if (dl and dl < TODAY) or stale:
                del pos_c[k]
                stale_n[0] += 1
                continue
            dk = (re.sub(r'\W+', '', r['title'].lower()), re.sub(r'\W+', '', (r['inst'] or '').lower()))
            if dk in seen_key:
                dup_n[0] += 1
                continue
            seen_key.add(dk)
            out.append(r)
        out.sort(key=lambda r: (r['deadline'] or '9999', r['title']))
        pub = [{k: v for k, v in r.items() if k != 'sid'} for r in out]
        os.makedirs(os.path.dirname(a.out) or '.', exist_ok=True)
        json.dump(dict(updated=TODAY.isoformat(), count=len(pub), positions=pub), open(a.out, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        meta = dict(updated=TODAY.isoformat(), render=render.stats(), duplicates_dropped=dup_n[0], expired_or_stale_dropped=stale_n[0])
        json.dump(dict(positions=pos_c, sources=ss_c, meta=meta), open(a.state, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
        return out, ss_c

    import guard
    guard.start(deadline_ts, save)
    ex = ThreadPoolExecutor(a.workers)
    list(ex.map(work, todo))
    ex.shutdown(wait=False)
    out, ss_c = save()
    ok = sum(1 for v in ss_c.values() if v.get('ok'))
    print(f'DONE: {len(out)} positions | {done[0]} sources visited this run | {ok}/{len(ss_c)} sources reachable | {int(time.time()-t0)}s')

if __name__ == '__main__':
    main()
