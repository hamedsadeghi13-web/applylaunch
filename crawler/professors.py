#!/usr/bin/env python3
"""Professor discovery. Writes docs/data/professors.json (read by the "Find a professor" page).

Pipeline (independent of the positions crawler):
  1. OpenAlex     institutions -> authors (name, ORCID, research topics, institution)
  2. ORCID public record -> job title / department (self-declared), public URLs, public e-mail (only if the owner made it public)
  3. Semantic Scholar    -> homepage (optional, only accepted when ORCID matches or the affiliation matches)
  4. Official page of the person (robots.txt respected) -> title, department, public e-mail, group / lab link,
     admission statements. LinkedIn: only the link is kept if the official page or ORCID lists it; LinkedIn is never fetched.
  5. Open positions found by crawl.py that name the professor -> strongest evidence.

Rules: e-mails are never guessed (only e-mails printed on an official page or public ORCID record, on the university's own domain);
status = 3 ("unclear") unless a page says otherwise; every status carries evidence text + link + check date.
"""
import argparse, datetime as dt, json, os, re, sys, time, zlib, threading, tempfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crawl, discover                           # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TODAY = dt.date.today()

RANK_RX = [('s', r'assistant professor|lecturer|junior professor|juniorprofessor|maître de conférences|ricercatore|universitair docent|yrd\.? ?doç|dr\. öğr'),
           ('a', r'associate professor|senior lecturer|reader\b|\bdoçent|professore associato|universitair hoofddocent|docteur hdr|privatdozent|\bPD\b'),
           ('p', r'full professor|professor\b|prof\.|professeur|professore|hoogleraar|catedrático|profesör|ordinarius')]
NOT_FACULTY = re.compile(r'(ph\.?d\.? (student|candidate)|doctoral (student|candidate|researcher)|postdoc|post-doc|research assistant|master student|undergraduate|visiting student)', re.I)
S1 = [r'(we are|i am|currently|now|actively)\s+(looking|seeking|searching|hiring|recruiting)[^.]{0,70}(phd|doctoral|postdoc|student|researcher|candidate)',
      r'(open|available|vacant)\s+(phd|doctoral|postdoc\w*|research|master)\s*(positions?|vacanc\w+|places|projects?|topics?)',
      r'(phd|doctoral|postdoc\w*)[^.]{0,40}positions?\s+(are\s+)?(available|open)',
      r'applications?\s+(are\s+)?(now\s+)?(open|invited|welcome)[^.]{0,60}(phd|doctoral|postdoc)']
S2 = [r'(prospective|interested|motivated|potential)\s+(phd\s+|master\s+)?(students|candidates|applicants)[^.]{0,90}(contact|e-?mail|get in touch|welcome|encouraged|invited)',
      r'(welcome|encourage|invite)[^.]{0,50}(enquir|inquir|applications|prospective|expressions of interest)']
S4 = [r'(not|no longer|currently not|are not|am not)\s+(currently\s+)?(accepting|taking|recruiting|looking for|admitting)[^.]{0,50}(students|phd|candidates|applications|new)',
      r'no\s+(open\s+)?(phd\s+)?(positions?|vacancies|openings)\s+(at the moment|currently|at present|available)',
      r'(group|lab)\s+is\s+(currently\s+)?full', r'fully\s+booked']
HOW_PORTAL = re.compile(r'(do not|don\'t|please do not|kindly do not|cannot)\s+(send|e-?mail|contact)[^.]{0,60}(directly|unsolicited|applications)|apply\s+(only\s+)?(through|via|using)\s+(the\s+)?(online\s+)?(application|portal|system|graduate school)|official\s+application\s+(procedure|portal)|applications?\s+must\s+be\s+submitted\s+(through|via)', re.I)
HOW_EMAIL = re.compile(r'(e-?mail|contact|write to|reach out to)\s+(me|us|the professor)|get in touch|send\s+(me|us)?\s*(your\s+)?(cv|resume|curriculum)|informal\s+(enquir|inquir)', re.I)
JOIN_LINK = re.compile(r'(join (us|the group|our group)|prospective|open positions?|openings|vacanc|opportunit|work with us|students? wanted|available (positions|projects)|phd positions?|apply)', re.I)
EMAIL_RX = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+')
OBF_RX = re.compile(r'([A-Za-z0-9._%+\-]+)\s*[\[\(]\s*at\s*[\]\)]\s*([A-Za-z0-9\-]+(?:\s*[\[\(]?\.?[\]\)]?\s*[A-Za-z0-9\-]+)*\.[a-z]{2,})', re.I)
DEPT_RX = re.compile(r'((?:Department|Faculty|School|Institute|Centre|Center|Chair|Division|Laboratory|Fakultät|Institut|Lehrstuhl|Département|Departamento|Dipartimento|Fakulte|Bölüm)\s+(?:of|for|für|de|di|del|du)?\s*[A-Z][\w&\-]*(?:(?:\s+(?:and|&|of|for))?\s+[A-Z][\w&\-]*){0,5})')


def sentence_around(text, m, width=170):
    a = max(0, m.start() - 60)
    b = min(len(text), m.end() + width - 60)
    s = re.sub(r'\s+', ' ', text[a:b]).strip()
    return s[:210]


def classify_status(text):
    """returns (status, evidence_sentence or '', accepts letters, how)"""
    hits = {1: None, 2: None, 4: None}
    for st, pats in ((1, S1), (2, S2), (4, S4)):
        for p in pats:
            m = re.search(p, text, re.I)
            if m:
                hits[st] = sentence_around(text, m)
                break
    how = 'portal' if HOW_PORTAL.search(text) else 'email' if HOW_EMAIL.search(text) else ''
    if hits[1] and hits[4]:
        return 3, '', '', how, 'conflict'
    st = 1 if hits[1] else 4 if hits[4] else 2 if hits[2] else 3
    ev = hits[1] or hits[4] or hits[2] or ''
    acc = ''
    if ev:
        low = ev.lower()
        acc = ('p' if re.search(r'phd|doctor|promotion', low) else '') + ('j' if re.search(r'postdoc|research (position|assistant|fellow)|researcher', low) else '') + ('m' if re.search(r'master|msc|thesis', low) else '')
    if st == 4 and how == '':
        how = 'portal'
    return st, ev, acc, how, ''


def find_rank(text):
    head = text[:700]
    if NOT_FACULTY.search(head[:250]) and not re.search(r'professor|prof\.|lecturer', head[:250], re.I):
        return 'x'
    for code, rx in RANK_RX:
        if re.search(rx, head, re.I):
            return code
    return ''


def rank_from_role(role):
    if not role:
        return ''
    if NOT_FACULTY.search(role) and not re.search(r'professor|lecturer', role, re.I):
        return 'x'
    for code, rx in RANK_RX:
        if re.search(rx, role, re.I):
            return code
    return ''


def inst_domains(url):
    return {discover.reg_domain(discover.host_of(url))} if url else set()


def public_emails(text, soup, ok_domains):
    found = []
    for a in soup.find_all('a', href=True):
        if a['href'].lower().startswith('mailto:'):
            found.append(a['href'][7:].split('?')[0].strip())
    found += EMAIL_RX.findall(text)
    for m in OBF_RX.finditer(text):
        found.append(m.group(1) + '@' + re.sub(r'\s*[\[\(]?\.?[\]\)]?\s*', '.', m.group(2)).strip('.'))
    out = []
    for e in found:
        e = e.strip().lower().strip('.,;')
        dom = e.split('@')[-1]
        if '@' in e and discover.reg_domain(dom) in ok_domains and not re.match(r'^(info|office|admin|webmaster|contact|secretary|sekretariat|noreply|no-reply|support|admissions?)@', e) and e not in out:
            out.append(e)
    return out


# ------------------------------------------------------------------ API clients
class API:
    """Thread-local HTTP sessions with a shared per-host request interval."""
    def __init__(self, delay=0.15):
        self.delay = delay
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_ok = {}

    def get(self, url, params=None, headers=None):
        host = urlparse(url).netloc
        with self.lock:
            now = time.time()
            at = max(now, self.next_ok.get(host, 0))
            self.next_ok[host] = at + self.delay
        if at > now:
            time.sleep(at - now)
        session = getattr(self.local, 'session', None)
        if session is None:
            session = requests.Session()
            session.headers['User-Agent'] = crawl.UA
            retry = requests.adapters.Retry(total=3, connect=3, read=2, backoff_factor=0.5,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset(['GET']), respect_retry_after_header=True)
            adapter = requests.adapters.HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            self.local.session = session
        r = session.get(url, params=params, headers=headers, timeout=(10, 25))
        r.raise_for_status()
        return r.json()


class ThreadSafeFetcher:
    """One Fetcher/session per worker, with a shared per-host politeness delay."""
    def __init__(self, delay=1.0):
        self.delay = delay
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_ok = {}

    def get(self, url):
        host = urlparse(url).netloc
        with self.lock:
            now = time.time()
            at = max(now, self.next_ok.get(host, 0))
            self.next_ok[host] = at + self.delay
        if at > now:
            time.sleep(at - now)
        fetcher = getattr(self.local, 'fetcher', None)
        if fetcher is None:
            fetcher = crawl.Fetcher(delay=0)
            self.local.fetcher = fetcher
        return fetcher.get(url)


def atomic_json(path, data):
    """Write JSON via a unique same-directory temporary file and atomic replace."""
    path = os.path.abspath(path)
    folder = os.path.dirname(path) or '.'
    os.makedirs(folder, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.tmp-', suffix='.json', dir=folder)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def oa_params():
    p = {}
    if os.environ.get('OPENALEX_API_KEY'):
        p['api_key'] = os.environ['OPENALEX_API_KEY']
    if os.environ.get('CONTACT_EMAIL'):
        p['mailto'] = os.environ['CONTACT_EMAIL']
    return p


def orcid_record(api, base, orcid):
    """public ORCID data: role title, department, urls, public email"""
    oid = orcid.rsplit('/', 1)[-1]
    h = {'Accept': 'application/json'}
    out = dict(role='', dept='', urls=[], emails=[], kw=[])
    try:
        person = api.get(f'{base}/{oid}/person', headers=h)
        out['urls'] = [(u.get('url-name') or '', (u.get('url') or {}).get('value', '')) for u in (person.get('researcher-urls') or {}).get('researcher-url', [])]
        out['emails'] = [e.get('email') for e in (person.get('emails') or {}).get('email', []) if e.get('email')]
        out['kw'] = [k.get('content') for k in (person.get('keywords') or {}).get('keyword', []) if k.get('content')][:8]
    except Exception:
        pass
    try:
        emp = api.get(f'{base}/{oid}/employments', headers=h)
        for g in emp.get('affiliation-group', []):
            for sm in g.get('summaries', []):
                e = sm.get('employment-summary') or {}
                if not e.get('end-date'):
                    out['role'] = out['role'] or (e.get('role-title') or '')
                    out['dept'] = out['dept'] or (e.get('department-name') or '')
    except Exception:
        pass
    return out


def s2_homepage(api, base, name, orcid, inst):
    try:
        j = api.get(f'{base}/author/search', params={'query': name, 'fields': 'name,affiliations,homepage,externalIds', 'limit': 5},
                    headers={'x-api-key': os.environ['S2_API_KEY']} if os.environ.get('S2_API_KEY') else None)
    except Exception:
        return ''
    oid = (orcid or '').rsplit('/', 1)[-1]
    for a in j.get('data', []):
        if not a.get('homepage'):
            continue
        if oid and (a.get('externalIds') or {}).get('ORCID') == oid:
            return a['homepage']
        if any(inst.lower()[:20] in (x or '').lower() for x in a.get('affiliations') or []) and a.get('name', '').lower() == name.lower():
            return a['homepage']
    return ''


# ------------------------------------------------------------------ one person
def enrich(p, F, api, urls, inst_dom):
    """p: dict with name, orcid, inst. Adds page/email/status ... Returns p."""
    name, last = p['name'], p['name'].split()[-1].lower()
    p['src'] = ['openalex']
    oc = {}
    if p.get('orcid'):
        oc = orcid_record(api, urls['orcid'], p['orcid'])
        p['src'].append('orcid')
        p['rk'] = rank_from_role(oc['role']) or p.get('rk', '')
        p['dept'] = oc['dept'] or p.get('dept', '')
        p['kw'] = oc['kw']
    page, other, linkedin = '', '', ''
    cands = list(oc.get('urls', []))
    for nm, u in cands:
        if not u.startswith('http'):
            continue
        h = discover.host_of(u)
        if 'linkedin.com/in/' in u:
            linkedin = linkedin or u
        elif discover.reg_domain(h) in inst_dom or discover.EDU_HOST.search(h):
            page = page or u
        elif not discover.BAD_HOST.search(h):
            other = other or u
    if not page and urls.get('s2'):
        hp = s2_homepage(api, urls['s2'], name, p.get('orcid'), p['uni'])
        if hp:
            p['src'].append('semanticscholar')
            h = discover.host_of(hp)
            if discover.reg_domain(h) in inst_dom or discover.EDU_HOST.search(h):
                page = hp
            else:
                other = other or hp
    p['other'], p['linkedin'] = other, linkedin
    text, soup, group = '', None, ''
    if page:
        try:
            html, _, final = F.get(page)
            soup = BeautifulSoup(html, 'lxml')
            for t in soup(['script', 'style', 'noscript']):
                t.decompose()
            text = re.sub(r'\s+', ' ', soup.get_text(' '))[:60000]
            if last not in text.lower():                   # the page is not about this person -> ignore it
                page, text, soup = '', '', None
            else:
                p['src'].append('official-page')
                p['page'] = final
        except Exception:
            page = ''
    if soup is not None:
        ok = set(inst_dom) | {discover.reg_domain(discover.host_of(p['page']))}
        em = public_emails(text, soup, ok)
        # the person's own address: prefer one containing the family name
        own = [e for e in em if last[:5] in e.split('@')[0]] or em[:1]
        if own:
            p['email'], p['emailSrc'] = own[0], p['page']
        rk = find_rank(text)
        p['rk'] = p.get('rk') or rk
        if not p.get('dept'):
            m = DEPT_RX.search(text[:3000])
            p['dept'] = m.group(1).strip()[:90] if m else ''
        meta = soup.find('meta', attrs={'name': re.compile('^keywords$', re.I)})
        if meta and meta.get('content'):
            p['kw'] = (p.get('kw') or []) + [k.strip() for k in meta['content'].split(',')][:8]
        join_url, same = '', discover.reg_domain(discover.host_of(p['page']))
        for a in soup.find_all('a', href=True):
            u, t = urljoin(p['page'], a['href']), a.get_text(' ', strip=True)
            if 'linkedin.com/in/' in u:
                p['linkedin'] = p['linkedin'] or u
            elif re.search(r'(research group|lab\b|laboratory|group$|group website|centre|center)', t, re.I) and len(t) < 70 and not group:
                group = u
            elif JOIN_LINK.search(t) and discover.reg_domain(discover.host_of(u)) == same and not join_url and len(t) < 80:
                join_url = u
        p['grp'] = group
        st, ev, acc, how, note = classify_status(text)
        ev_url = p['page']
        if st == 3 and join_url and not note:                 # follow ONE "join us / prospective students" link
            try:
                h2, _, f2 = F.get(join_url)
                t2 = re.sub(r'\s+', ' ', BeautifulSoup(h2, 'lxml').get_text(' '))[:40000]
                st2, ev2, acc2, how2, n2 = classify_status(t2)
                if st2 != 3:
                    st, ev, acc, how, ev_url = st2, ev2, acc2, how2 or how, f2
            except Exception:
                pass
        upd = None
        m = re.search(r'(last\s+(?:updated|modified)|updated)[:\s]+([^|]{0,40})', text, re.I)
        if m:
            upd = crawl.parse_date(m.group(2))
        if st in (1, 2) and upd and (TODAY - upd).days > 550:
            st, note = 3, 'stale'                               # old statement: do not present it as current
            ev, acc = '', ''
        p['st'], p['how'], p['acc'] = st, how, acc
        p['ev'] = {'t': ev, 'u': ev_url, 'd': TODAY.isoformat()} if ev else None
        if note == 'conflict':
            p['evNote'] = 'conflicting statements on the page'
    else:
        p.setdefault('st', 3)
        p['ev'], p['how'], p['acc'] = None, '', ''
        # a public ORCID e-mail may be used only on the university's domain
        for e in oc.get('emails', []):
            if discover.reg_domain(e.split('@')[-1].lower()) in inst_dom:
                p['email'], p['emailSrc'] = e.lower(), 'https://orcid.org/' + p['orcid'].rsplit('/', 1)[-1]
                break
    if p.get('rk') == 'x':
        return None
    p['checked'] = TODAY.isoformat()
    return p


def norm_name(n):
    n = re.sub(r'(prof\.?|dr\.?|professor|habil\.?)\s*', '', n.lower())
    return re.sub(r'[^a-zà-ÿ ]', '', n).split()


def link_positions(profs, positions):
    """positions that name a professor of the same institution = clear evidence (status 1)"""
    by = {}
    for q in positions:
        for nm in q.get('sup', []):
            t = norm_name(nm)
            if len(t) >= 2:
                by.setdefault((t[-1], t[0][0]), []).append(q)
    n = 0
    for p in profs:
        t = norm_name(p['name'])
        if len(t) < 2:
            continue
        for q in by.get((t[-1], t[0][0]), []):
            stop = {'university', 'universität', 'universiteit', 'universidad', 'the', 'of', 'for', 'and', 'institute', 'college'}
            a, b = set(re.findall(r'[a-z]{3,}', q['inst'].lower())) - stop, set(re.findall(r'[a-z]{3,}', p['uni'].lower())) - stop
            if a & b:
                p['st'], p['ev'] = 1, {'t': 'An open position lists this person as supervisor/contact: ' + q['title'][:110], 'u': q['url'], 'd': q.get('last_seen') or TODAY.isoformat()}
                p['acc'] = 'p' if q['type'] == 'PhD' else 'j' if q['type'] in ('Postdoc', 'Research job') else 'm' if q['type'] == 'Master' else ''
                p.setdefault('src', []).append('open-position')
                n += 1
                break
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--state', default=os.path.join(HERE, 'prof_state.json'))
    ap.add_argument('--out', default=os.path.join(ROOT, 'docs', 'data', 'professors.json'))
    ap.add_argument('--positions', default=os.path.join(ROOT, 'docs', 'data', 'positions.json'))
    ap.add_argument('--openalex-base', default=os.environ.get('OPENALEX_BASE', 'https://api.openalex.org'))
    ap.add_argument('--orcid-base', default=os.environ.get('ORCID_BASE', 'https://pub.orcid.org/v3.0'))
    ap.add_argument('--s2-base', default=os.environ.get('S2_BASE', 'https://api.semanticscholar.org/graph/v1'))
    ap.add_argument('--max-inst', type=int, default=int(os.environ.get('MAX_INST', 40)))
    ap.add_argument('--per-inst', type=int, default=int(os.environ.get('PER_INST', 100)))
    ap.add_argument('--min-works', type=int, default=int(os.environ.get('MIN_WORKS', 2000)))
    ap.add_argument("--publish-max", type=int, default=12000)
    ap.add_argument('--budget-min', type=int, default=int(os.environ.get('BUDGET_MIN', 240)))
    ap.add_argument('--workers', type=int, default=8)
    ap.add_argument('--delay', type=float, default=1.0)
    a = ap.parse_args()
    t0 = time.time()
    deadline = t0 + a.budget_min * 60
    state = json.load(open(a.state, encoding='utf-8')) if os.path.exists(a.state) else {}
    insts, profs = state.get('institutions', {}), state.get('professors', {})
    excluded = set(state.get('excluded', []))
    institution_cursor = int(state.get('institution_cursor', 0) or 0)
    api, F = API(), ThreadSafeFetcher(delay=a.delay)
    oa = discover.OpenAlex(a.openalex_base)
    # ---- refresh the full discovered institution registry (600-page cap retained)
    for it in oa.pages('institutions', f'type:education,works_count:>{a.min_works}', 'id,display_name,homepage_url,country_code,works_count,geo', 600):
        insts.setdefault(it['id'], dict(name=it['display_name'], cc=(it.get('country_code') or '').upper(), city=((it.get('geo') or {}).get('city') or ''), home=it.get('homepage_url') or '', last=''))
    # Round-robin selection prevents institutions with equal last-processed dates from starving.
    ordered = sorted(insts.items(), key=lambda kv: kv[0])
    if ordered:
        institution_cursor %= len(ordered)
        batch_size = min(max(1, a.max_inst), len(ordered))
        todo = [ordered[(institution_cursor + i) % len(ordered)] for i in range(batch_size)]
        institution_cursor = (institution_cursor + batch_size) % len(ordered)
    else:
        todo = []
    urls = dict(orcid=a.orcid_base, s2=a.s2_base)
    data_lock = threading.RLock()
    checkpoint_lock = threading.Lock()
    processed_authors = [0]
    last_checkpoint = [0.0]

    def save_checkpoint(force=False):
        """Persist completed work regularly; called by workers and at safe boundaries."""
        with checkpoint_lock:
            now = time.time()
            if not force and processed_authors[0] % 10 != 0 and now - last_checkpoint[0] < 30:
                return
            with data_lock:
                plist = list(profs.values())
                plist.sort(key=lambda p: (0 if p.get('page') else 1, p.get('st', 3), -(p.get('cites') or 0)))
                pub = [{k: v for k, v in p.items() if k not in ('works',) and v not in ('', None, [])} for p in plist[:a.publish_max]]
                # Save resumable state first. If the process stops before the public file,
                # the next run can rebuild it from this state without losing discoveries.
                atomic_json(a.state, dict(institutions=insts, professors=profs,
                                          excluded=sorted(excluded),
                                          institution_cursor=institution_cursor))
                atomic_json(a.out, dict(updated=TODAY.isoformat(), count=len(pub), professors=pub))
            last_checkpoint[0] = now

    # Persist institution discovery before starting the long-running enrichment stage.
    save_checkpoint(force=True)

    def one(item):
        iid, inst = item
        if time.time() > deadline:
            return 0
        got = 0
        flt = f'last_known_institutions.id:{iid},works_count:>10,cited_by_count:>50'
        try:
            r = requests.get(f'{a.openalex_base}/authors', params=dict(oa_params(), filter=flt, sort='cited_by_count:desc', **{'per-page': min(100, a.per_inst)},
                             select='id,display_name,orcid,works_count,cited_by_count,topics'), headers={'User-Agent': crawl.UA}, timeout=30)
            r.raise_for_status()
            res = r.json().get('results', [])
        except Exception as ex:
            print('  authors error', inst['name'][:30], str(ex)[:100], flush=True)
            # Rotate a temporarily failing institution instead of retrying it first forever.
            with data_lock:
                inst['last'] = TODAY.isoformat()
            save_checkpoint(force=True)
            return 0
        doms = inst_dom_of(inst)
        complete = True
        for au in res:
            if time.time() > deadline:
                complete = False
                break
            key = au['id']
            with data_lock:
                if key in excluded:
                    continue
                existing = profs.get(key)
                if existing and existing.get('checked'):
                    try:
                        if (TODAY - dt.date.fromisoformat(existing['checked'])).days < 30:
                            continue
                    except (TypeError, ValueError):
                        pass
            p = dict(id=zlib.crc32(key.encode()) & 0x7fffffff, oa=key, name=au['display_name'], orcid=au.get('orcid') or '', uni=inst['name'], cc=inst['cc'], city=inst['city'],
                     topics=[t.get('display_name') for t in (au.get('topics') or [])[:6] if t.get('display_name')], works=au.get('works_count'), cites=au.get('cited_by_count'))
            enrich_failed = False
            try:
                q = enrich(p, F, api, urls, doms)
            except Exception as ex:
                q = None
                enrich_failed = True
                print('  enrich error', p['name'], str(ex)[:100], flush=True)
            with data_lock:
                if q:
                    profs[key] = q
                    got += 1
                elif not enrich_failed and p.get('rk') == 'x':
                    excluded.add(key)
                processed_authors[0] += 1
            # Save completed discoveries before moving to the next author.
            save_checkpoint()
        if complete:
            with data_lock:
                inst['last'] = TODAY.isoformat()
            save_checkpoint(force=True)
        return got
    inst_dom_of = lambda inst: inst_dom(inst['home'])
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(one, todo))
    save_checkpoint(force=True)
    # ---- link to open positions, publish
    plist = list(profs.values())
    try:
        positions = json.load(open(a.positions, encoding='utf-8')).get('positions', [])
    except Exception:
        positions = []
    linked = link_positions(plist, positions)
    plist.sort(key=lambda p: (0 if p.get('page') else 1, p.get('st', 3), -(p.get('cites') or 0)))
    pub = []
    for p in plist[:a.publish_max]:
        pub.append({k: v for k, v in p.items() if k not in ('works',) and v not in ('', None, [])})
    save_checkpoint(force=True)
    em = sum(1 for p in plist if p.get('email'))
    print(f'PROFESSORS: {len(plist)} people from {sum(1 for i in insts.values() if i["last"])} institutions | official page {sum(1 for p in plist if p.get("page"))} | public e-mails {em} | status1 {sum(1 for p in plist if p.get("st")==1)} status2 {sum(1 for p in plist if p.get("st")==2)} status4 {sum(1 for p in plist if p.get("st")==4)} | linked to open positions {linked} | {int(time.time()-t0)}s')


def inst_dom(home):
    return {discover.reg_domain(discover.host_of(home))} if home else set()


if __name__ == '__main__':
    main()
