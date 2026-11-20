#!/usr/bin/env python3
"""Honest numbers about what the system really found. Writes docs/data/report.json and a Markdown summary
(shown on the GitHub Actions run page).   python crawler/report.py [--audit 40] [--score labeled.csv]"""
import argparse, csv, json, os, random, sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
def load(p, d):
    try:
        return json.load(open(p, encoding='utf-8'))
    except Exception:
        return d

ap = argparse.ArgumentParser()
ap.add_argument('--audit', type=int, default=0, help='write a random sample of professor statuses for manual checking')
ap.add_argument('--score', help='labeled audit CSV (column "label": ok / wrong) -> precision of the status detection')
a = ap.parse_args()

if a.score:
    rows = list(csv.DictReader(open(a.score, encoding='utf-8')))
    lab = [r for r in rows if r.get('label', '').strip().lower() in ('ok', 'wrong')]
    for st in ('1', '2', '4'):
        sub = [r for r in lab if r['status'] == st]
        if sub:
            print(f'status {st}: {sum(1 for r in sub if r["label"].lower()=="ok")}/{len(sub)} correct = {100*sum(1 for r in sub if r["label"].lower()=="ok")/len(sub):.0f}%')
    sys.exit()

curated = load(os.path.join(HERE, 'sources.json'), [])
reg = load(os.path.join(HERE, 'registry.json'), {}).get('sources', [])
state = load(os.path.join(HERE, 'state.json'), {})
pos = load(os.path.join(ROOT, 'docs', 'data', 'positions.json'), {}).get('positions', [])
pstate = load(os.path.join(HERE, 'prof_state.json'), {})
profs = load(os.path.join(ROOT, 'docs', 'data', 'professors.json'), {}).get('professors', [])

per_src = Counter(p.get('sid') for p in state.get('positions', {}).values())
sstat = state.get('sources', {})
reg_status = Counter(s.get('status') for s in reg)
extractable_curated = sum(1 for s in curated if per_src.get(s['id']))
extractable_reg = sum(1 for s in reg if s.get('status') == 'verified')
meth = Counter()
for sid, v in sstat.items():
    m = v.get('method') or ('unreachable' if not v.get('ok') else 'no-extraction')
    meth[m] += 1
js_src = [v for v in sstat.values() if v.get('js')]
js_ok = [v for v in js_src if 'playwright' in (v.get('method') or '')]
cc_pos = Counter(p.get('cc') for p in pos if p.get('cc'))
reg_cc = Counter((s.get('cc') or s.get('country') or '?') for s in reg)
cur_cc = Counter((s.get('country') or '?') for s in curated)
import datetime as _dt
new_today = sum(1 for p in state.get('positions', {}).values() if p.get('first_seen') == _dt.date.today().isoformat())
meta = state.get('meta', {})
extraction = dict(
    by_method=dict(meth),
    js_sources_detected=len(js_src), js_sources_extracted_with_browser=len(js_ok),
    sources_needing_custom_adapter=sorted([k for k, v in sstat.items() if v.get('needs_adapter')])[:200],
    needs_adapter_count=sum(1 for v in sstat.values() if v.get('needs_adapter')),
    registry_js_required=sum(1 for s in reg if s.get('status') == 'js_required'),
    browser=meta.get('render', {}), duplicates_dropped_last_run=meta.get('duplicates_dropped'), stale_or_expired_dropped_last_run=meta.get('expired_or_stale_dropped'),
    failed_sources=sum(1 for v in sstat.values() if not v.get('ok')), new_positions_first_seen_today=new_today,
    discovery_by_method=dict(Counter(s.get('via', '?') for s in reg)),
    positions_by_country=dict(cc_pos.most_common()), discovered_sources_by_country=dict(reg_cc.most_common()))
rep = dict(
    extraction=extraction,
    sources=dict(curated=len(curated), discovered=len(reg), discovered_by_status=dict(reg_status),
                 curated_reachable=sum(1 for s in curated if sstat.get(s['id'], {}).get('ok')),
                 curated_with_real_positions=extractable_curated, discovered_verified=extractable_reg,
                 really_extractable_total=extractable_curated + extractable_reg),
    positions=dict(total=len(pos), by_type=dict(Counter(p['type'] for p in pos)), with_deadline=sum(1 for p in pos if p.get('deadline')),
                   with_salary=sum(1 for p in pos if p.get('salary')), countries=len({p['cc'] for p in pos})),
    professors=dict(total=len(profs), institutions_processed=sum(1 for i in pstate.get('institutions', {}).values() if i.get('last')),
                    with_official_page=sum(1 for p in profs if p.get('page')), with_public_email=sum(1 for p in profs if p.get('email')),
                    status=dict(Counter(p.get('st', 3) for p in profs)), with_evidence_link=sum(1 for p in profs if p.get('ev')),
                    from_open_positions=sum(1 for p in profs if 'open-position' in p.get('src', []))),
    note='Status detection accuracy is NOT measured automatically. Run: python crawler/report.py --audit 40, label the CSV (ok/wrong), then --score.')

# ---- global institution database + coverage numbers for the home page (docs/data/coverage.json)
idb = load(os.path.join(HERE, 'institutions.json'), {})
irecs = idb.get('institutions', {})
NAME2CC = {}
try:
    sys.path.insert(0, HERE)
    import crawl as _c
    NAME2CC = {v.lower(): k for k, v in _c.ISO_NAME.items()}
except Exception:
    pass
def cc_of(s):
    c = (s.get('cc') or '').upper()
    return c if len(c) == 2 else NAME2CC.get((s.get('country') or '').lower(), '')
ver = [s for s in reg if s.get('status') == 'verified']
src_cc = {cc_of(s) for s in curated + ver} - {''}
cities = {(s.get('city') or '').strip().lower() for s in curated + ver} - {''}
inst_cc = Counter(r['cc'] for r in irecs.values())
inst_doms = {}
for r in irecs.values():
    if r.get('w'):
        inst_doms[r['w']] = r
ver_doms = set()
import re as _re
def _dom(u):
    h = _re.sub(r'^www\d?\.', '', (u.split('//')[-1].split('/')[0]).lower())
    p = h.split('.')
    return '.'.join(p[-3:]) if len(p) >= 3 and p[-2] in ('co', 'com', 'ac', 'edu', 'org', 'gov') and len(p[-1]) == 2 else '.'.join(p[-2:])
ver_doms = {_dom(s['url']) for s in ver + curated if s.get('url') and (per_src.get(s['id']) or s.get('status') == 'verified')}
inst_with_src = sum(1 for r in irecs.values() if r.get('w') and _dom(r['w']) in ver_doms)
reg_by_dom = {_dom(s['url']): s for s in reg if s.get('url')}
checked = sum(1 for r in irecs.values() if r.get('w') and _dom(r['w']) in reg_by_dom)
pages_found = Counter()
for s in reg:
    for k in (s.get('pages') or {}):
        pages_found[k] += 1
prog = idb.get('progress', {})
rep['institutions'] = dict(
    total=len(irecs), countries=len(inst_cc), with_website=sum(1 for r in irecs.values() if r.get('w')), with_ror=sum(1 for r in irecs.values() if r.get('ror')),
    by_directory=dict(Counter(x for r in irecs.values() for x in r.get('s', []))), checked_for_opportunities=checked, with_verified_source=inst_with_src,
    pages_identified=dict(pages_found), directory_tasks_done={d: sum(1 for v in c.values() if v.get('done')) for d, c in prog.items()},
    top_countries=dict(inst_cc.most_common(25)), updated=idb.get('updated'))
coverage = dict(updated=_dt.date.today().isoformat(), countries=len(src_cc), cities=len(cities), universities=max(len(irecs), sum(1 for s in curated + ver if s.get('type') == 'university')), sources=len(curated) + len(ver),
                institutions_countries=len(inst_cc), institutions_with_website=rep['institutions']['with_website'], institutions_checked=checked, institutions_with_source=inst_with_src)
os.makedirs(os.path.join(ROOT, 'docs', 'data'), exist_ok=True)
json.dump(coverage, open(os.path.join(ROOT, 'docs', 'data', 'coverage.json'), 'w'))
json.dump(rep, open(os.path.join(ROOT, 'docs', 'data', 'report.json'), 'w'), indent=1)
md = f"""## ApplyLaunch run report
| | |
|---|---|
| Curated sources / reachable / with real positions | {len(curated)} / {rep['sources']['curated_reachable']} / {extractable_curated} |
| Newly discovered sources / verified (extractable) | {len(reg)} / {extractable_reg}  ({dict(reg_status)}) |
| **Sources really extractable (total)** | **{extractable_curated + extractable_reg}** |
| Real current positions | {len(pos)} ({rep['positions']['by_type']}) |
| Professors found / with official page / public e-mail | {len(profs)} / {rep['professors']['with_official_page']} / {rep['professors']['with_public_email']} |
| Sources by extraction method | {dict(meth)} |
| JavaScript sources detected / extracted with the browser | {len(js_src)} / {len(js_ok)} |
| Sources needing a custom adapter | {extraction['needs_adapter_count']} |
| New positions first seen today | {new_today} |
| Duplicates / stale dropped (last run) | {meta.get('duplicates_dropped')} / {meta.get('expired_or_stale_dropped')} |
| Countries with positions | {len(cc_pos)} |
| Admission status 1/2/3/4 | {rep['professors']['status']} |
| Institutions in the global database / countries / checked for opportunities / with a verified source | {rep['institutions']['total']} / {rep['institutions']['countries']} / {checked} / {inst_with_src} |
| Professors with an evidence link | {rep['professors']['with_evidence_link']} |
"""
print(md)
if os.environ.get('GITHUB_STEP_SUMMARY'):
    open(os.environ['GITHUB_STEP_SUMMARY'], 'a').write(md)
if a.audit:
    ev = [p for p in profs if p.get('ev')]
    random.seed(1)
    sample = random.sample(ev, min(a.audit, len(ev)))
    with open(os.path.join(HERE, 'audit_sample.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['name', 'uni', 'status', 'evidence', 'url', 'label'])
        for p in sample:
            w.writerow([p['name'], p['uni'], p.get('st'), p['ev']['t'], p['ev']['u'], ''])
    print('audit sample written to crawler/audit_sample.csv')
