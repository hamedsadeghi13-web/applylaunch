"""Page understanding for ApplyLaunch: what does a page really offer?

 kind_of_title()  : 'opening' | 'programme' | 'info' | 'noise'   (rule based, title level - also used on stored records)
 type_of()        : PhD / Master / Scholarship / Postdoc / Internship / Research job / None  (whole words only, title first)
 describe/requirements/research_topics : text taken from the source page (not only the headline)

Principles (they came out of an audit of 18,976 records):
  * a keyword counts only as a WHOLE WORD (or a listed inflection): 'intern' never matches 'international', 'internal', 'internet' ...
  * the page body is evidence for the SUBJECT of an opportunity, but not for its TYPE unless the title is itself an opportunity
  * news, ceremonies, people pages, navigation pages and career blogs are not opportunities: they are kept (nothing is deleted) but flagged
"""
import re

L = r'a-zA-ZÀ-ɏͰ-ϿЀ-ӿ؀-ۿ'      # letters (latin ext., greek, cyrillic, arabic)
def W(words, tail=''):
    """compile a list of alternatives as whole words (optionally followed by a listed tail such as plural endings)"""
    return re.compile(r'(?<![' + L + r'])(?:' + '|'.join(words) + r')' + tail + r'(?![' + L + r'])', re.I)

# ---------------------------------------------------------------- type
_T = {
 'postdoc':  W([r'post[- ]?docs?', r'postdoctoral', r'post[- ]doctoral', r'postdoctorant\w*', r'post-?doctorat', r'postdoktorand\w*', r'postdoktoral\w*', r'investigador posdoctoral', r'posdoc\w*']),
 'phd':      W([r'ph\.?\s?d\.?', r'doctoral', r'doctorate', r'doctorat', r'doctorants?', r'doctorado', r'doctoranda?', r'doktorand\w*', r'doktorarbeit', r'doktoratsstudium', r'doktora', r'dottorato', r'doutoramento', r'doutorado', r'promovend\w*', r'promotionsstelle', r'promotionsstipendi\w+', r'promotionsprogramm', r'promotionsstudium', r'dphil', r'thesis position']),
 'master':   W([r'master', r'masters', r'master[’\']s', r'msc', r'm\.sc\.?', r'm\.arch\.?', r'mphil', r'mres', r'mba', r'llm', r'ma', r'm\.a\.', r'maestr[ií]a', r'm[aá]ster', r'mestrado', r'laurea magistrale', r'yüksek lisans', r'masterstudium', r'masterstudiengang', r'masterprogramm\w*', r'master[- ]?thesis', r'masterarbeit']),
 'scholar':  W([r'scholarships?', r'fellowships?', r'stipend\w*', r'bursar(?:y|ies)', r'studentships?', r'bourses?', r'borse? di studio', r'becas?', r'bolsas?', r'burs', r'stipendi\w+', r'stipendiat\w*', r'stipendije', r'grants?', r'sponsorship']),
 'intern':   W([r'interns?', r'internships?', r'praktikum', r'praktikant\w*', r'pflichtpraktikum', r'trainee\w*', r'stagiaires?', r'pr[aá]cticas', r'becari[oa]s?', r'est[aá]gio', r'stajyer\w*', r'stage (?:h/f|f/h|de fin d.[eé]tudes|master|m2|ing[eé]nieur)', r'werkstudent\w*']),
 'job':      W([r'research (?:assistant|associate|fellow|scientist|engineer|officer|staff|technician|support|specialist)s?', r'wiss\.? mitarbeit\w*', r'wissenschaftliche[rn]? mitarbeiter\w*', r'junior researcher', r'project (?:assistant|scientist|officer|researcher)', r'projektmitarbeit\w*', r'doctoral researcher', r'ing[eé]nieur d.[eé]tudes?']),
 'jobw':     W([r'researchers?', r'wissenschaftliche[rn]?', r'wiss\.? mitarbeit\w*', r'wiss\.? mitarbeit\w*', r'chercheu[rs]e?s?', r'ing[eé]nieur d.[eé]tudes?', r'investigador\w*', r'scientists?', r'forscher\w*', r'junior researcher', r'project (?:assistant|scientist|officer|researcher)', r'projektmitarbeit\w*', r'doctoral researcher', r'lecturer', r'professor\w*']),
}
_ORDER = ['postdoc', 'phd', 'intern', 'master', 'scholar', 'job', 'jobw']      # first match wins (title evidence)
_NAME = {'phd': 'PhD', 'master': 'Master', 'scholar': 'Scholarship', 'postdoc': 'Postdoc', 'intern': 'Internship', 'job': 'Research job', 'jobw': 'Research job'}

def type_of(title, lead=''):
    """whole-word type of an opportunity; the title decides, the first 400 characters of the main text only break a tie when the title says nothing"""
    for scope in (title, lead[:400]):
        if not scope:
            continue
        for k in _ORDER:
            if _T[k].search(scope):
                if k == 'jobw' and not ROLE.search(scope):
                    continue      # generic noun (researchers, scientists, lecturer...) is a type only when the text is a vacancy
                return _NAME[k]
        if scope is title and False:
            pass
    return None

# ---------------------------------------------------------------- kind
_UP = r'A-ZÀ-ÖØ-Þ'
_lo = r'a-zà-öø-ÿ'
NEWS = W([
 r'defen[cs]e', r'defended', r'viva', r'soutenances?', r'verteidigung', r'ph\.?d\.?[- ]?verja', r'congratulat\w*', r'congrats', r'awarded', r'wins', r'won', r'honou?rary', r'honoris causa', r'honou?rs',
 r'joins', r'appointed', r'appoints', r'elected', r'inaugura\w*', r'welcomes', r'bienvenue', r'bienvenid\w*', r'willkommen', r'graduation', r'graduating', r'commencement', r'ceremony', r'luncheon', r'gala',
 r'celebrat\w*', r'celebraci\w+', r'anniversary', r'press release', r'pressemitteilung', r'presseinformation', r'communiqu[eé]', r'newsletter', r'news', r'noticias?', r'actualit[eé]s?', r'nachrichten',
 r'blog', r'podcast', r'interview', r'spotlight', r'success stor(?:y|ies)', r'stories', r'story', r'webinar', r'keynote', r'open day', r'info[- ]?(?:session|veranstaltung)', r'infobijeenkomst', r'exhibition', r'exposition', r'ausstellung',
 r'calendar', r'committee', r'council', r'association', r'board', r'elections?', r'[eé]lections?', r'elecciones', r'feria', r'pr[eé]sentation', r'presentaci[oó]n', r'contact\w*', r'contatti', r'kontakt\w*', r'results?', r'lista', r'list of (?:candidates|winners)', r'report', r'partnerships?', r'co-?operations?', r'cooperaci[oó]n', r'collaborations?', r'networks?', r'dissertations?', r'people', r'profiles?', r'bags', r'unleash', r'sharing', r'afishohet', r'dates', r'timetable', r'schedule', r'festival', r'alumn[ai]', r'alumni', r'testimonials?', r'promotie', r'orientation', r'receives?', r'announces?', r'launches', r'launched', r'unveils?', r'hosts?', r'highlights?', r'recap', r'report on', r'visit(?:s|ed)? (?:from|by|to)',
 r'meet', r'meets', r'met', r'selected', r'chosen', r'gradu[eé]s?', r'diploma ceremony', r'events? gallery', r'photo gallery', r'poster', r'congr[eè]s', r'conference', r'symposium', r'workshop', r'seminar', r'colloquium', r'lecture series', r'inaugural lecture',
 r'career fair', r'job fair', r'fair', r'open house', r'campus tour', r'ranking', r'rankings', r'honou?rs? awarded', r'prize winners?', r'winners?', r'fêtes?', r'jornada', r'jornadas', r'journ[eé]e', r'journ[eé]es', r'tag der', r'sommerfest',
])
QA = re.compile(r'^(what|how|why|who|which|is|are|can|should|do|does)\b|\?|worth it|\b(careers?|jobs?) (opportunities )?(after|in|for|scope)\b|what can i do|best (government )?jobs|career scope|^benefits of|\bjourney\b|\btips\b|\bguide to\b|\bfaq\b|frequently asked|how to\b', re.I)
PERSON = re.compile(r'^(?:prof\.?|dr\.?|ing\.?|mgr\.?|doc\.?|assoc\.? prof\.?|professor|[eE]x\.?)\s+[' + _UP + r']|,\s*ph\.?d\.?\s*\.?$|\bph\.?d\.?\s*\|', re.I)
NAMEPIPE = re.compile(r'^[' + _UP + r'][' + _lo + r"'’-]+(?: [" + _UP + r'][' + _lo + r"'’-]+){1,2}\s*[|–-]\s*\S")
NAV_FIRST = re.compile(r'^inter(?:national\w*|nal\w*|nat\w*|nacional\w*|nazional\w*|ne|na|ni|no|nes|nas)(?![' + L + r']*ship)', re.I)
NAV_FULL = re.compile(r'^(?:international|about(?: us)?|contact(?: us)?|home|human resources|career services?|careers?|our researchers|researchers[’\']? days|attachments|programme composition|team|people|staff|events?|calendar|vice-rectorate.*|referat.*|office|hr|jobs? in [a-z ]+|jobs?|study|studies|research|admission|apply|downloads?|publications?|facilities|international)$', re.I)
ROLE = re.compile(r'\((?:m|w|f|d|x|i)(?:[/|](?:m|w|f|d|x|i)){1,3}\)|(?<![' + L + r'])(?:m/f/d|f/m/d|m/w/d|w/m/d|d/m/w|h/f|f/h|m/w|m/f|gn|all genders)(?![' + L + r'])|\*in\b|\*r\b|:in\b|/-?in\b|\bposition\b|\bvacanc|\bopening\b|\bjob offer|offre d.emploi|\bstelle\b|\bstellen(?:ausschreibung|angebot)|\bcall for (?:applications?|candidates|proposals?|expressions)|\bis hiring\b|\bwe are (?:hiring|looking)|\brecruit(?:ing|ment)\b|\bapplications? (?:are )?(?:open|invited|now open)|\bapply (?:now|by)\b|\bpieteikšan|\bpieteikumu|\bcall\b.*\bapplications?\b|\bconvocatoria|\bappel [àa] candidatures?|\bbewerbung', re.I)
DEG = re.compile(r'(?<![' + L + r'])(?:master|msc|m\.sc\.?|m\.arch\.?|ma|mphil|mres|mba|llm|bachelor|bsc|b\.sc\.?|ba|b\.arch\.?|ph\.?d\.?|doctorate|doctor|doctoral|doctorat|doctorado|dottorato|diplom\w*|certificate|maestr[ií]a|licenciatura|abschluss|studiengang|studium|programa|programme|program)(?![' + L + r'])', re.I)
GENERIC = re.compile(r'^(?:(?:the|our|all|your|a|an|new|about|my|international|doctoral|graduate|postgraduate|masters?|master[’\']?s|ph\.?d\.?|phd|programmes?|programs?|degrees?|studies|study|courses?|school|schools|admissions?|admission|requirements|information|overview|general|students?|studierende|awards?|funding|scholarships?|fellowships?|stipend\w*|bursar\w*|grants?|financial|aid|support|opportunities|announcements?|information|f[oö]rder\w*|m[oö]glichkeiten|traineeships?|internships?|co-?op|positions?|vacancies|jobs?|careers?|apply|applying|application|doctorados?|doctorat|ecoles?|écoles?|doctorales?|doctoral|school|and|&|in|for|to|of|at|here|now|et|und|de|des|du|la|le|les|en|für|zu|der|die|das|el|los|las|programa|programas|programme|a|e|o|di|della)\b[\s,.:;|&\-–—()/]*)+$', re.I)

def _first_part(t):
    return re.split(r'\s+[|–—]\s+|\s+-\s+', t, 1)[0].strip()

def kind_of_title(title, has_jobposting=False):
    """opening: a concrete position/call/scholarship; programme: a named degree programme; info: gateway/listing/FAQ; noise: news, ceremony, person, navigation"""
    t = re.sub(r'\s+', ' ', str(title or '')).strip()
    if not t:
        return 'noise'
    if has_jobposting:
        return 'opening'
    fp = _first_part(t)
    has_role = bool(ROLE.search(t))
    ty = type_of(t)
    # --- noise
    if NAV_FULL.match(fp) or (NAV_FIRST.match(fp) and not has_role and not (ty in ('PhD', 'Master', 'Scholarship', 'Postdoc') )):
        return 'noise'
    if QA.search(t) and not has_role:
        return 'noise'
    if (PERSON.search(t) or (NAMEPIPE.match(t) and type_of(fp) is None)) and not has_role:
        return 'noise'
    if len(fp.split()) <= 5 and re.search(r'(?<![' + L + r'])internation\w*|internacional\w*|internazional\w*|intern(?:al|e|a)\b', fp, re.I) and ty not in ('PhD', 'Master', 'Scholarship', 'Postdoc', 'Internship') and not has_role:
        return 'noise'
    if NEWS.search(t) and not has_role:
        return 'noise'
    # --- opening
    if has_role:
        return 'opening'
    if ty == 'Internship':
        return 'opening' if len(t.split()) >= 2 and not GENERIC.match(t) else 'info'
    if ty in ('Postdoc', 'PhD', 'Master', 'Job', 'Research job'):
        if GENERIC.match(fp):
            return 'info'
        w = fp.split()
        if ty in ('PhD', 'Master') and DEG.search(fp):
            return 'programme'
        if ty in ('Postdoc', 'Research job'):
            return 'opening' if len(w) >= 3 else 'info'
        return 'programme'
    if ty == 'Scholarship':
        if GENERIC.match(fp):
            return 'info'
        w = fp.split()
        named = bool(re.search(r'\b(?:19|20)\d\d\b', fp)) or any(x[0:1].isupper() for x in w[1:]) or len(w) >= 4
        return 'opening' if named else 'info'
    return 'info'

# ---------------------------------------------------------------- page text
_BOILER = re.compile(r'cookie|consent|gdpr|banner|breadcrumb|sidebar|menu|navbar|nav-|social|share|newsletter|subscribe|skip|footer|header|widget|related|comment|search', re.I)
def main_text(soup):
    """text of the main content: <main>/<article>/role=main when present, otherwise the body without boilerplate blocks"""
    node = soup.find('main') or soup.find('article') or soup.find(attrs={'role': 'main'}) or soup.body or soup
    for t in list(node.find_all(True)):
        try:
            cls = ' '.join(t.get('class') or []) + ' ' + str(t.get('id') or '')
        except Exception:
            continue
        if t.name in ('aside', 'nav', 'footer', 'header', 'form', 'script', 'style', 'noscript') or (cls.strip() and _BOILER.search(cls) and len(t.get_text(' ', strip=True)) < 800):
            t.decompose()
    return re.sub(r'\s+', ' ', node.get_text(' ', strip=True))

def _clip(s, n):
    s = re.sub(r'\s+', ' ', s).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    k = max(cut.rfind('. '), cut.rfind('; '), cut.rfind(' '))
    return cut[:k if k > n * .6 else n].rstrip(' ,;:') + '…'

def describe(soup, jl, text, n=520):
    """what the page says about the opportunity: JSON-LD description > meta description > first real sentences of the main text"""
    parts = []
    if jl and jl.get('description'):
        parts.append(re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', str(jl['description']))).strip())
    for k in ({'name': 'description'}, {'property': 'og:description'}):
        m = soup.find('meta', attrs=k)
        if m and len(m.get('content', '')) > 40:
            parts.append(m['content'].strip())
    if not parts:
        sents = [s for s in re.split(r'(?<=[.!?])\s+', text) if 50 <= len(s) <= 400 and not re.search(r'cookie|javascript|©|copyright|all rights reserved', s, re.I)]
        parts.append(' '.join(sents[:3]))
    return _clip(' '.join(parts), n)

REQ = re.compile(r'(?:eligib\w*|requirements?|qualifications?|prerequisites?|admission (?:criteria|requirements?|conditions)|entry requirements?|who can apply|applicants? (?:must|should|need|have to)|candidates? (?:must|should|need|are expected)|you (?:have|hold|should have|must have|will have|bring)|we expect|must (?:hold|have|be)|should (?:hold|have)|required|profile|voraussetzung\w*|anforderung\w*|ihr profil|bewerber\w* (?:sollten|müssen)|zulassung\w*|conditions? d.admission|conditions requises|profil recherch[eé]|pr[eé]requis|requisitos|perfil|requisiti|ammissione|gereksinim|ba[sş]vuru ko[sş]ul\w*|bachelor|master[’\']?s degree|degree in|ielts|toefl|gpa|gre\b|language (?:skills|proficiency)|fluent|proficien\w*)', re.I)
def requirements(text, n=420, k=4):
    out, seen = [], set()
    for s in re.split(r'(?<=[.!?;:])\s+|\s[•·▪–]\s', text):
        s = s.strip()
        if 14 <= len(s) <= 260 and REQ.search(s) and not re.search(r'cookie|privacy|©', s, re.I):
            key = s[:40].lower()
            if key not in seen:
                seen.add(key)
                out.append(s)
        if len(out) >= k:
            break
    return _clip(' '.join(out), n)

DEPT = re.compile(r'(?<![' + L + r'])((?:Department|Faculty|School|Institute|Centre|Center|College|Division|Fachbereich|Fakult[aä]t|Institut|Lehrstuhl|D[eé]partement|Facult[eé]|Laboratoire|Laboratory|Departamento|Facultad|Escuela|Dipartimento|Facolt[aà]|Fak[uü]lte|B[oö]l[uü]m[uü]) (?:of |for |f[uü]r |de |du |des |di |del |d[\'’])?[' + _UP + r'][\w&,\' \-]{3,70}?)(?=[.,;:|()\n]| at | in | and the | - | – |$)')
LABEL = re.compile(r'(?:research (?:areas?|topics?|fields?|interests?|projects?|group)|area of research|field of study|subject areas?|disciplines?|keywords?|forschungsgebiet\w*|forschungsschwerpunkt\w*|fachrichtung|fachgebiet|thema|themen|domaine|discipline|th[eè]me|sujet|axes? de recherche|[aá]rea de (?:investigaci[oó]n|conocimiento)|campo|ricerca|ara[sş]t[ıi]rma alan\w*)\s*[:\-–]\s*([^.\n]{6,160})', re.I)
def research_topics(soup, jl, text, n=320):
    bits = []
    if jl:
        for k in ('skills', 'occupationalCategory', 'industry', 'educationRequirements', 'keywords'):
            v = jl.get(k)
            if isinstance(v, list):
                v = ', '.join(str(x.get('name') if isinstance(x, dict) else x) for x in v)
            if isinstance(v, dict):
                v = v.get('name') or v.get('credentialCategory')
            if v:
                bits.append(re.sub(r'<[^>]+>', ' ', str(v)))
    for m in LABEL.finditer(text[:30000]):
        bits.append(m.group(1))
        if len(bits) > 6:
            break
    seen = set()
    for m in DEPT.finditer(text[:30000]):
        d = m.group(1).strip()
        if d.lower() not in seen and 8 <= len(d) <= 80:
            seen.add(d.lower())
            bits.append(d)
        if len(seen) >= 3:
            break
    return _clip(' | '.join(b.strip() for b in bits if b and b.strip()), n)

def page_keywords(soup, n=200):
    m = soup.find('meta', attrs={'name': re.compile('^keywords$', re.I)})
    return (m.get('content', '') if m else '')[:n]

PROF = W([r'professors?', r'professur\w*', r'lecturers?', r'chair of', r'habilitation', r'assistant professor', r'associate professor', r'tenure[- ]track', r'tenure', r'dozent\w*', r'maître de conférences', r'catedr[aá]tic\w*', r'profesor\w*'])
def is_professor(title):
    """faculty posts belong to the professor directory, not to the PhD/Master/Scholarship feed (unchanged behaviour of the old classifier)"""
    t = str(title or '')
    return bool(PROF.search(t)) and not (_T['postdoc'].search(t) or _T['phd'].search(t) and re.search(r'student|candidate|position|researcher', t, re.I))

APPLY = re.compile(r'apply (?:now|here|by|before|online)|how to apply|application (?:deadline|form|procedure|process|portal|documents?)|submit (?:your|an|the) application|send (?:your|an) application|closing date|deadline|bewerb\w+|bewerbungsfrist|candidature|date limite|postula\w*|convocatoria|plazo|scadenza|domanda di|başvuru', re.I)
def kind_of_page(title, text, jl=None, deadline=None):
    """title verdict, refined with what the page itself says. A page can only move one step: it is never promoted from noise, and
    a title that says nothing is judged by whether the page contains an application path, eligibility rules or a deadline."""
    k = kind_of_title(title, has_jobposting=bool(jl))
    if k == 'noise' or not text:
        return k
    n = len(text)
    ev = sum(1 for r in (APPLY, REQ) if len(r.findall(text[:12000])) >= (1 if r is APPLY else 2))
    if deadline:
        ev += 1
    if k == 'info':
        if n < 350:
            return 'noise'                                  # an almost empty page is not an opportunity
        if ev >= 2:
            return 'opening'
    if k in ('opening', 'programme') and not jl and ev == 0 and n < 500:
        return 'info'
    return k
