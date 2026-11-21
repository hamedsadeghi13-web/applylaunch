/* ApplyLaunch - topical relevance engine (no server, no AI model: transparent rules that can be tested).
 *
 * Problem it solves: a plain "does the word appear" search shows "Software Architect" for "Architecture".
 * Idea: every opportunity is assigned to the scientific domain(s) its TITLE and (cleaned) TOPIC keywords really talk about,
 * with word-sense guards for ambiguous words. A query is mapped to the domain(s) it names (English / Persian / Turkish).
 * Each result is then judged:
 *    direct      - the opportunity belongs to the queried domain
 *    related     - it belongs to a closely related domain (or to a content-defined interdisciplinary area)
 *    unclassified- the word matches but nothing in the text tells us the domain  (kept, ranked after the others)
 *    irrelevant  - the word matches but the opportunity clearly belongs to another domain (hidden from the main results)
 * Queries that name no known domain (e.g. a city or a rare topic) are left to the normal text search.
 */
(function (root) {
  'use strict';
  const R = (s, f) => new RegExp(s, f || 'i');

  /* ---- domain lexicon: t = words that place a TITLE / topic in the domain ---- */
  const D0 = {
    arch: { t: R('architect(?!ed\\b)(ure|ural|e|es|s|en)?\\b|architektur|architettur|arquitect|mimar|interior (design|architecture)|building design|landscape architect|stadtbaukunst'), q: R('architect|mimar|معمار|mimari') },
    urban: { t: R('urban (design|planning|studies|development|regeneration|morphology|resilience|form)|city planning|town planning|spatial planning|regional planning|urbanis[mt]|stadtplanung|urbanisme|planificaci[oó]n urbana|şehir planlama|kentsel|transport planning'), q: R('urban|city planning|شهرساز|طراحی شهری|kentsel|şehir plan') },
    compdesign: { t: R('(computational|parametric|generative|algorithmic|digital)[ -](design|architecture|fabrication|morphogenesis)|form[- ]?finding|robotic fabrication|digital craft|\\bbim\\b|building information model'),
      ctx: R('building|architectur|construction|built environment|structur|facade|façade|urban|timber|material system'), q: R('computational design|parametric|generative design|طراحی محاسباتی|hesaplamalı tasarım') },
    heritage: { t: R('heritage (conservation|management|studies)|building conservation|historic (preservation|building)|conservation of (monuments|buildings)|restoration of (monuments|buildings)|monument'), q: R('heritage|conservation of|restoration|میراث') },
    construction: { t: R('construction (management|engineering|technology|industry|project|site)|building (physics|science|technology|services|energy|envelope)|quantity surveyor|facade engineering|site engineer|structural design'), q: R('construction|building science|ساخت') },
    civil: { t: R('civil engineer|structural engineer|geotechnic|hydraulic engineer|transportation engineering|bridge|concrete|earthquake|seismic|water resources|coastal engineering|infrastructure engineering'), q: R('civil|عمران|inşaat') },
    mech: { t: R('mechanical|mechatronic|thermodynamic|fluid mechanics|manufacturing|machine design|combustion|tribolog|vibration|automotive|solid mechanics|contact mechanics|m[eé]canique|maschinenbau|makine'), q: R('mechanical|mechatronic|مکانیک|makine') },
    aero: { t: R('aerospace|aeronautic|aircraft|spacecraft|propulsion|avionic|rocket|satellite|astronautic'), q: R('aerospace|aeronautic|هوافضا|havacılık') },
    robotics: { t: R('robot|autonomous (vehicle|system)|exoskeleton'), q: R('robot|ربات') },
    elec: { t: R('electrical engineer|electronic|power (system|electronics|grid)|microelectronic|signal processing|telecommunication|semiconductor|vlsi|antenna|control (systems|engineering)|embedded system|elektrotechnik|[eé]lectrique|elektrik'), q: R('electrical|electronic|برق|الکترونیک|elektrik|elektronik') },
    energy: { t: R('energy (system|storage|transition|efficien|conversion|harvest|technolog|market|policy)|renewable|solar (cell|energy|power|panel)|floating solar|photovoltaic|batter(y|ies)|hydrogen|wind (turbine|energy|power|farm)|nuclear (energy|power|engineering)|fuel cell|smart grid|energie'), q: R('energy|renewable|انرژی|enerji') },
    env: { t: R('environmental (engineering|science|sustainability|studies|management)|climate|ecolog|biodiversity|waste (management|treatment)|pollution|carbon|water quality|sustainab|circular economy'), q: R('environment|sustainab|climate|محیط زیست|çevre|پایدار') },
    chemeng: { t: R('chemical engineering|process engineering|catalysis|reactor|petrochemical|polymer'), q: R('chemical engineering|مهندسی شیمی|kimya mühendisliği') },
    mat: { t: R('materials? (science|engineering|research)|nanomaterial|metallurg|ceramic|composite|alloy|thin film|nanotechnolog'), q: R('materials? (science|engineering)|مواد|malzeme') },
    cs: { t: R('(solutions?|enterprise|technical|technology|data|cloud|security|network|systems?|infrastructure|application|integration|platform|information|digital|software) architect(ure)?s?\\b|software|developer|d[eé]veloppeur|devops|c\\+\\+|\\bjava\\b|python|backend|frontend|full[- ]?stack|\\bcloud\\b|kubernetes|cyber ?security|information (technology|systems|security)|computer (science|engineering|vision|graphics|systems|network|architecture)|programming|algorithm|distributed systems|database|operating system|compiler|\\bit (support|manager|specialist|engineer)|logiciel|informatik|bilgisayar|human-computer|web develop|app develop|blockchain|quantum comput|microarchitecture'), q: R('computer science|software|informatics|computing|programming|کامپیوتر|نرم.?افزار|bilgisayar|yazılım') },
    ai: { t: R('machine learning|deep learning|artificial intelligence|neural network|\\bai\\b|\\bnlp\\b|natural language processing|reinforcement learning|large language|\\bllm|generative ai'), q: R('artificial intelligence|machine learning|deep learning|هوش مصنوعی|yapay zeka|\\bai\\b') },
    data: { t: R('data (science|scientist|analy|engineer)|big data|statistic|bioinformatic|biostatistic|analytics'), q: R('data science|statistic|علم داده|veri bilimi|آمار') },
    math: { t: R('mathematic|applied math|probability|topology|algebra|numerical analysis|optimi[sz]ation|mathematik'), q: R('mathematic|ریاضی|matematik') },
    phys: { t: R('physics|photonic|astrophysic|particle|quantum (physics|field|mechanics)|condensed matter|optics|cosmolog|plasma|physik'), q: R('physics|فیزیک|fizik') },
    chemsci: { t: R('chemistry|biochemistry|organic synthesis|inorganic|analytical chem|spectroscop|chemie|kimya'), q: R('chemistry|شیمی|kimya') },
    bio: { t: R('biolog|genetic|genom|molecular|\\bcell\\b|neuroscien|immunolog|microbiolog|biotech|proteom|biomedical|bioengineering|zoology|botany'), q: R('biolog|genetic|neuroscien|biotech|زیست|biyoloji') },
    med: { t: R('medicine|medical|clinical|surgery|surgeon|oncolog|cardiolog|patient|physician|dentist|radiolog|pathology|epidemiolog|neurolog|paediatric|pediatric|psychiatr|anesthes|(clinical|medical) diagnos|m[eé]decin|medizin|tıp'), q: R('medicine|medical|clinical|پزشک|tıp|tibb') },
    health: { t: R('nurs(e|ing)|public health|physiotherap|health (care|sciences|policy)|midwif|rehabilitation|nutrition|sport science'), q: R('nursing|public health|پرستار|بهداشت|sağlık') },
    pharm: { t: R('pharmac|drug (discovery|development)|toxicolog'), q: R('pharmac|داروسازی|eczacılık') },
    psych: { t: R('psycholog|cognitive|behaviou?ral|neuropsych'), q: R('psycholog|روانشناسی|psikoloji') },
    soc: { t: R('sociolog|anthropolog|political science|international relations|human geography|gender studies|social (science|work|policy)|migration|communication studies|media studies'), q: R('sociolog|anthropolog|political|جامعه|sosyoloji') },
    econ: { t: R('econom|financ|business|management|accounting|marketing|\\bmba\\b|entrepreneur|supply chain|banking|operations research'), q: R('econom|financ|business|management|اقتصاد|مدیریت|ekonomi|işletme') },
    law: { t: R('\\blaw\\b|legal|jurisprud|rechts|\\bdroit\\b|hukuk'), q: R('\\blaw\\b|legal|حقوق|hukuk') },
    edu: { t: R('education|pedagog|teaching and learning|didactic|curriculum|teacher training|language (teaching|learning)'), q: R('education|pedagog|آموزش|eğitim') },
    hum: { t: R('history|philosoph|literature|linguist|classics|archaeolog|theolog|religio|cultural studies|musicolog|philolog|humanities'), q: R('history|philosoph|literature|linguist|archaeolog|تاریخ|فلسفه|tarih') },
    art: { t: R('fine art|visual art|\\bfilm\\b|music|theatre|performing arts|graphic design|industrial design|product design|fashion|photograph|illustration|animation|communication design|interaction design|service design'), q: R('fine art|visual art|film|music|graphic design|industrial design|هنر|sanat') },
    geo: { t: R('geolog|geophysic|geomatic|geodesy|remote sensing|\\bgis\\b|hydrolog|earth science|seismolog|oceanograph|meteorolog|geograph|atmospher'), q: R('geolog|geograph|geophysic|remote sensing|زمین|jeoloji|coğrafya') },
    agri: { t: R('agricultur|agronom|\\bcrop|soil|forestry|horticultur|food science|veterinar|animal science|aquaculture'), q: R('agricultur|agronom|veterinar|food science|کشاورزی|tarım') }
  };
  /* every domain keyword must start at a word boundary (so 'bridge' never matches 'Cambridge') */
  const D = {};
  Object.keys(D0).forEach(k => { D[k] = Object.assign({}, D0[k], { t: new RegExp('(?:^|[^\\p{L}])(?:' + D0[k].t.source + ')', 'iu') }); });
  /* generic words that stand for several domains */
  const GROUPS = { eng: { q: R('\\bengineering\\b|مهندسی|mühendislik'), dom: ['civil', 'mech', 'elec', 'chemeng', 'aero', 'mat', 'energy', 'construction', 'env'] } };

  /* closely related domains (symmetric); a domain is never "related" because it merely shares a word */
  const REL_PAIRS = [
    ['arch', 'urban'], ['arch', 'compdesign'], ['arch', 'heritage'], ['arch', 'construction'],
    ['urban', 'civil'], ['civil', 'construction'],
    ['mech', 'aero'], ['mech', 'mat'], ['mech', 'energy'], ['mech', 'robotics'], ['elec', 'robotics'], ['ai', 'robotics'], ['elec', 'energy'],
    ['cs', 'ai'], ['cs', 'data'], ['ai', 'data'], ['ai', 'math'],
    ['med', 'health'], ['med', 'pharm'], ['bio', 'pharm'], ['bio', 'chemsci'], ['chemsci', 'chemeng'], ['chemeng', 'mat'], ['chemsci', 'mat'],
    ['phys', 'math'], ['soc', 'psych'], ['soc', 'hum'], ['hum', 'art'], ['env', 'energy'], ['env', 'agri']
  ];
  const REL = {};
  REL_PAIRS.forEach(([a, b]) => { (REL[a] = REL[a] || new Set()).add(b); (REL[b] = REL[b] || new Set()).add(a); });

  /* ---- word-sense guards ---- */
  const CS_CTX = R('software|logiciel|c\\+\\+|\\bcloud\\b|devops|developer|d[eé]veloppeur|programm|\\bjava\\b|python|backend|frontend|full[- ]?stack|enterprise|solutions?|\\bdata\\b|systems?|network|security|platform|application|saas|\\baws\\b|azure|\\.net|\\bsap\\b|integration|\\bit\\b|digital transformation|technical architect|technology architect|infrastructure');
  const BUILD_CTX = R('building|urban|landscape|interior|design studio|construction|planning|school of architecture|college of architecture|master of architecture|faculty of architecture|\\bbim\\b|heritage|architectural (design|history|theory|technology|engineering|practice)|zoning|masterplan|housing|retail|residential|project architect|junior architect|architectural designer|\\bregistered architect|licensed architect|\\bRIBA\\b');
  const NOT_ARCH = R('(computer|processor|micro|network|neural|system|systems|software|data|cloud|enterprise|solution|solutions|security|information|memory|chip|hardware|model|application|technical|technology|digital|infrastructure|platform|integration|it) (architecture|architect)|architect(ed)?\\s+(interface|material|structure|metamaterial|lattice)s?|architected|architecture (and|&) (c\\+\\+|software|cloud|devops)|(architecture|architect)\\s+(c\\+\\+|software|logiciel)|software|logiciel');

  /* engineering/IT senses of "architecture" (hardware, devices, networks...) - not buildings */
  const TECH_CTX = R('hardware|exoskeleton|actuat|brain-inspired|cmos|asic|fpga|circuit|processor|\\bgpu\\b|neural|network|software|cloud|memory|rram|\\bchip|sensor|protocol|microservice|pipeline|\\bllm\\b|\\bmodel(l)?ing\\b|robot');
  const JUNK_TOPIC = R('^(jobs?|jobs\\.ac\\.uk|appointments?|vacanc\\w*|positions?|careers?|academic|lecturer|professor|research|staff|employment|hiring|apply|faculty|university|school|college|phd|postdoc\\w*|studentships?|funding|scholarships?|fellowships?|news|events?|admissions?|courses?|programmes?|programs?)$');
  function cleanTopics(t) {
    if (!t) return '';
    return String(t).split(/[,;|]/).map(s => s.trim()).filter(s => s && s.length <= 45 && !JUNK_TOPIC.test(s)).join(' , ');
  }

  /* does a text really belong to domain id?  returns a score (0 = no) */
  function domScore(id, text, weight) {
    const d = D[id];
    if (!d.t.test(text)) return 0;
    if (id === 'arch') {
      if (NOT_ARCH.test(text)) return 0;
      if (CS_CTX.test(text) && !BUILD_CTX.test(text)) return 0;      /* "Solutions Architect", "Cloud Architect" ... */
      if (TECH_CTX.test(text) && !BUILD_CTX.test(text)) return 0;    /* "exoskeleton architecture", "brain-inspired architectures" */
    }
    if (id === 'compdesign' && (!d.ctx.test(text) || (TECH_CTX.test(text) && !BUILD_CTX.test(text)))) return 0;   /* interdisciplinary area: judged by content, not by name */
    return weight;
  }

  /* domain scores of a position: {domain: score}; cached on the object */
  function classify(p) {
    if (p._dom) return p._dom;
    const title = String(p.title || ''), topics = cleanTopics(p.topics);
    const out = {};
    Object.keys(D).forEach(id => {
      let s = domScore(id, title, 3);
      if (!s && topics) s = domScore(id, topics, 2);
      else if (s && topics && domScore(id, topics, 1)) s += 1;
      if (s) out[id] = s;
    });
    /* a title that is clearly software must not also count as architecture etc. (handled by the guards above); keep top 3 */
    const top = Object.entries(out).sort((a, b) => b[1] - a[1]).slice(0, 3);
    p._dom = Object.fromEntries(top);
    return p._dom;
  }

  /* what does the query name?  returns {doms:Set, rest:[tokens]} ; doms empty => plain text search */
  function parseQuery(text) {
    const lower = String(text || '').toLowerCase().trim();
    const doms = new Set();
    let rest = lower;
    Object.keys(D).forEach(id => {
      const m = D[id].q.exec(lower);
      if (m) { doms.add(id); rest = rest.replace(D[id].q, ' '); }
    });
    Object.keys(GROUPS).forEach(g => {
      if (GROUPS[g].q.test(lower) && !doms.size) { GROUPS[g].dom.forEach(x => doms.add(x)); rest = rest.replace(GROUPS[g].q, ' '); }
    });
    /* words like "in", "phd", "position" left over by the domain phrase do not constrain the match */
    const stop = new Set(['in', 'of', 'and', 'the', 'for', 'phd', 'position', 'positions', 'master', 'masters', 'msc', 'degree', 'program', 'programme', 'science', 'studies', 'engineering', 'research', 'جستجو']);
    const toks = rest.split(/[\s,;]+/).filter(t => t && !stop.has(t));
    return { doms, rest: toks, lower };
  }

  /* judge one position for a parsed query: 'direct' | 'related' | 'unclassified' | 'irrelevant' | null (no match at all) */
  function judge(p, q, lexicalHit) {
    if (!q.doms.size) return lexicalHit ? 'direct' : null;
    const c = classify(p), ids = Object.keys(c);
    const own = ids.filter(i => q.doms.has(i));
    if (own.length) return 'direct';
    const relSet = new Set(); q.doms.forEach(d => (REL[d] || []).forEach(x => relSet.add(x)));
    if (ids.some(i => relSet.has(i) && c[i] >= 3)) return 'related';
    if (ids.some(i => relSet.has(i))) return 'related';
    if (!lexicalHit) return null;
    return ids.length ? 'irrelevant' : 'unclassified';
  }

  /* does the raw text contain a word of the queried domain(s)?  (no sense guard: used to find look-alike words) */
  function wordHit(q, text) { for (const d of q.doms) { if (D[d].t.test(text)) return true; } return false; }

  root.Rel = { classify, parseQuery, judge, wordHit, cleanTopics, DOMAINS: Object.keys(D) };
  if (typeof module !== 'undefined') module.exports = root.Rel;
})(typeof window !== 'undefined' ? window : globalThis);
