/* ApplyLaunch - topical relevance engine v2 (rule based, runs in the browser and in Node; no server, no AI model).
 *
 * What it does
 *  - Every opportunity is placed in one OR SEVERAL scientific domains, from everything we know about it:
 *      title (strongest) > research topics / department names read from the source page > page-specific keywords > description > institution name.
 *    Each domain gets a score; >= MEMBER means "belongs to this domain", lower scores are weak evidence.
 *  - A query is mapped to the domain(s) it names (English / German / French / Spanish / Turkish / Persian aliases). The words of the
 *    domain phrase are consumed completely ("Architecture" no longer leaves "ure" behind as an extra text filter).
 *  - Result classes: direct (member of the queried domain or of one of its sub-domains) | related (member of a closely related domain, or weak evidence)
 *    | unclassified (word matches, nothing says which field) | irrelevant (word matches but the opportunity clearly belongs to another field).
 *  - Domain words are matched as words (prefix boundary), with sense guards: "Solutions Architect" is not architecture, "Financial aid" is not finance,
 *    "Bridge to Success" is not civil engineering, "Water Management" is not business.
 */
(function (root) {
  'use strict';
  const VERSION = 2, MEMBER = 2.5, WEAK = 1.2;
  const R = (s, f) => new RegExp(s, f || 'iu');
  const PRE = '(?:^|[^\\p{L}])';

  /* ---------------- domains: [id, names[en,fa,tr], t (words that place a text in the domain), q (query aliases, consume whole words), options] ---------------- */
  const DEF = [
    ['land', ['Landscape architecture', 'معماری منظر', 'Peyzaj mimarlığı'],
      'landscape (architect\\w*|design|planning|urbanism|ecology)|landschaftsarchitektur|landschaftsplanung|architecture du paysage|paysagiste|paisajismo|arquitectura del paisaje|paesaggio|peyzaj\\w*',
      'landscape architect\\w*|landscape[\\p{L}]*|peyzaj\\w*|منظر\\S*'],
    ['interior', ['Interior architecture', 'معماری داخلی', 'İç mimarlık'],
      'interior (design|architecture)|innenarchitektur|architecture d.int[eé]rieur|dise[nñ]o de interiores|i[cç] mimar\\w*',
      'interior (architecture|design)|interior[\\p{L}]*|innenarch\\w*|معماری داخلی'],
    ['heritage', ['Heritage conservation', 'حفاظت از میراث', 'Kültürel miras'],
      'heritage (conservation|management|studies|science)|(architectural|building|monument|historic) (conservation|preservation)|conservation of (monuments|buildings|heritage)|restoration of (monuments|buildings)|denkmalpflege|patrimoine|patrimonio|restauro|restauraci[oó]n|k[uü]lt[uü]rel miras|koruma ve restorasyon|monument\\w*',
      '(architectural|building) conservation|heritage[\\p{L}]*|denkmal\\w*|patrimo\\w*|restorasyon|restoration|میراث\\S*|مرمت|حفاظت'],
    ['compdesign', ['Computational design', 'طراحی محاسباتی', 'Hesaplamalı tasarım'],
      '(computational|parametric|generative|algorithmic|digital)[ -](design|architecture|fabrication|morphogenesis|craft)|form[- ]?finding|robotic fabrication|digital fabrication|3d[- ]print\\w* (construction|building)',
      'computational design|parametric[\\p{L}]*|generative design|digital fabrication|طراحی محاسباتی|hesaplamalı tasarım',
      { ctx: R('building|architectur|construction|built environment|structur|fa[cç]ade|urban|timber|material system|bauen|b[aâ]ti') }],
    ['bldtech', ['Building science & technology', 'علوم و فناوری ساختمان', 'Yapı bilimi ve teknolojisi'],
      'building (science|physics|technology|technologies|services|energy|envelope|performance|simulation)|architectural (technology|engineering|science)|\\bbim\\b|building information model\\w*|fa[cç]ade (engineering|design)|timber (construction|engineering|building)|bauphysik|bautechnik|geb[aä]udetechnik|bauklimatik|physique du b[aâ]timent|f[ií]sica de la construcci[oó]n|yap[ıi] bilgisi|yap[ıi] fizi[gğ]i',
      'building (science|physics|technology)|architectural technology|\\bbim\\b|bauphysik|فیزیک ساختمان|فناوری ساختمان',
      { ctxFor: { '\\bbim\\b': R('building|construction|architectur|infrastructure|engineer|model|design|digital') } }],
    ['construction', ['Construction management', 'مدیریت ساخت', 'Yapım yönetimi'],
      'construction (management|engineering|technology|industry|project|site|law|economics)|quantity survey\\w*|site engineer|construction manager|baumanagement|baubetrieb|bauwirtschaft|gestion de chantier|gesti[oó]n de obra|yap[ıi] i[sş]letme|in[sş]aat y[oö]netimi',
      'construction[\\p{L}]*|baubetrieb|ساخت'],
    ['urban', ['Urban planning & design', 'شهرسازی', 'Şehir planlama'],
      'urban (design|planning|studies|development|regeneration|morphology|resilience|form|and regional|policy|mobility|geograph\\w+|analytics|science)|city planning|town planning|spatial planning|regional planning|land[- ]use planning|urbanis[mt]\\w*|urbanistic\\w*|stadtplanung|raumplanung|stadtentwicklung|st[aä]dtebau|urbanisme|am[eé]nagement (urbain|du territoire)|planificaci[oó]n (urbana|territorial)|urbanismo|pianificazione (urbana|territoriale)|urbanistica|[sş]ehir (planlama|ve b[oö]lge)|kentsel|kent planlama|housing and urban|mobilit[eé] urbaine',
      'urban (planning|design|studies)|urban[\\p{L}]*|city planning|town planning|spatial planning|stadtplanung|urbanis[\\p{L}]*|[sş]ehir plan\\w*|kentsel|شهرساز\\S*|طراحی شهری|برنامه ?ریزی شهری'],
    ['arch', ['Architecture', 'معماری', 'Mimarlık'],
      'architect(?!ed\\b)(ure|ural|e|es|s|en|in|inn|us)?(?![\\p{L}])|architekt\\w*|architettur\\w*|arquitect\\w*|arquitetur\\w*|architecte\\w*|mimar\\w*|baukunst|building design',
      'architect[\\p{L}]*|architekt[\\p{L}]*|arquitect[\\p{L}]*|arquitetur[\\p{L}]*|mimar[\\p{L}]*|معمار\\S*',
      { kids: ['land', 'interior', 'heritage', 'compdesign', 'bldtech'] }],
    ['civil', ['Civil engineering', 'مهندسی عمران', 'İnşaat mühendisliği'],
      'civil engineer\\w*|civil and (environmental|structural|infrastructure)|structural (engineer\\w*|analysis|design|mechanics|dynamics)|geotechnic\\w*|hydraulic engineer\\w*|hydraulics|transportation engineering|traffic engineering|bridge (engineer\\w*|design|structure\\w*|inspection|maintenance)|concrete (structures?|technology)|earthquake engineering|seismic|water resources? (engineering|management)|coastal engineering|infrastructure|bauingenieur\\w*|g[eé]nie civil|ingenier[ií]a civil|ingegneria civile|engenharia civil|in[sş]aat m[uü]hendis\\w*|bridges?',
      'civil[\\p{L}]*|bauingenieur\\w*|g[eé]nie civil|in[sş]aat\\w*|عمران|مهندسی عمران',
      { ctxFor: { 'bridges?': R('engineer|design|structur|concrete|steel|infrastructure|construction|inspection|civil|span') } }],
    ['transport', ['Transport & mobility', 'حمل‌ونقل', 'Ulaştırma'],
      'transport(ation)? (engineering|planning|systems?|studies|policy|economics)|traffic (engineering|management)|mobility (planning|systems|studies)|railway\\w*|rail (engineering|systems)|verkehrs\\w+|ula[sş]t[ıi]rma|transporte (p[uú]blico|ferroviario)',
      'transport\\w*|verkehr\\w*|حمل ?و ?نقل|ulaştırma'],
    ['mech', ['Mechanical engineering', 'مهندسی مکانیک', 'Makine mühendisliği'],
      'mechanical (engineer\\w*|design|systems?)|mechatronic\\w*|thermodynamic\\w*|fluid (mechanics|dynamics)|manufactur\\w+|machine design|combustion|tribolog\\w*|vibration\\w*|automotive|solid mechanics|contact mechanics|continuum mechanics|heat transfer|m[eé]canique|maschinenbau|ingenier[ií]a mec[aá]nica|ingegneria meccanica|engenharia mec[aâ]nica|makine m[uü]hendis\\w*|production engineering|fertigungs?\\w*|\\bcfd\\b|finite element',
      'mechanical[\\p{L}]*|mechatronic\\w*|maschinenbau|makine\\w*|m[eé]canique|ingenier[ií]a mec[aá]nica|مکانیک\\S*|مهندسی مکانیک',
      { neg: R('systems biology|protein|quantum|\\bcell') }],
    ['aero', ['Aerospace engineering', 'مهندسی هوافضا', 'Havacılık ve uzay'],
      'aerospace|aeronautic\\w*|aircraft|spacecraft|propulsion|avionic\\w*|rocket\\w*|satellite\\w*|astronautic\\w*|luft- und raumfahrt|a[eé]rospatial\\w*|aeron[aá]utic\\w*|havac[ıi]l[ıi]k|aerodynamic\\w*|aeroelastic\\w*',
      'aerospace|aeronautic\\w*|aeroespacial|a[eé]rospatial\\w*|هوافضا|havacılık'],
    ['robotics', ['Robotics', 'رباتیک', 'Robotik'],
      'robot\\w*|autonomous (vehicle|system|driving)|exoskeleton|mechatronics',
      'robot\\w*|ربات\\S*'],
    ['elec', ['Electrical & electronic engineering', 'مهندسی برق و الکترونیک', 'Elektrik-elektronik'],
      'electrical (engineer\\w*|and electronic|systems?|machines?)|electronic (engineer\\w*|systems?|devices?)|power (systems?|electronics|grid|engineering)|microelectronic\\w*|signal processing|telecommunication\\w*|semiconductor\\w*|vlsi|antenna\\w*|control (systems|engineering|theory)|embedded system\\w*|elektrotechnik\\w*|elektronik|nachrichtentechnik|[eé]lectrotechnique|g[eé]nie [eé]lectrique|[eé]lectronique|ingenier[ií]a el[eé]ctric\\w*|electr[oó]nica|ingegneria elettric\\w*|elettronica|elektrik\\w*|optoelectronic\\w*|rf engineer\\w*|wireless',
      'electrical[\\p{L}]*|electronic[\\p{L}]*|elektro\\w*|elektrik\\w*|elektronik|[eé]lectr\\w*|برق|الکترونیک|مخابرات'],
    ['energy', ['Energy', 'انرژی', 'Enerji'],
      'energy (system\\w*|storage|transition|efficien\\w*|conversion|harvest\\w*|technolog\\w*|engineering|management|economics|policy)|renewable\\w*|solar (cell\\w*|energy|power|panel\\w*|thermal)|photovoltaic\\w*|batter(?:y|ies)|hydrogen|wind (turbine\\w*|energy|power|farm)|nuclear (energy|power|engineering|fusion)|fuel cells?|smart grid|energie(?:technik|wende|systeme)?|[eé]nergies? (renouvelable|solaire)|energ[ií]a\\w*|enerji\\w*|bioenergy|geothermal|carbon capture',
      'energy|renewable\\w*|energie\\w*|[eé]nergie\\w*|energ[ií]a|enerji|انرژی'],
    ['env', ['Environmental engineering & science', 'مهندسی و علوم محیط زیست', 'Çevre'],
      'environmental (engineering|science\\w*|technology|chemistry|management|studies|protection|impact|planning|monitoring)|climate (change|science|model\\w*|adaptation|risk|resilience)|ecolog\\w*|biodiversity|waste (management|treatment|water)|wastewater|pollution|air quality|water (quality|treatment|pollution)|carbon (cycle|footprint)|conservation biology|umwelt\\w*|environnement\\w*|medio ?ambient\\w*|meio ambiente|ambientale|[cç]evre\\w*|klima\\w*|climat\\w*|ecosystem\\w*|natural resources?',
      'environment\\w*|ecolog\\w*|climate|umwelt\\w*|environnement\\w*|medio ambiente|[cç]evre\\w*|محیط ?زیست|اقلیم'],
    ['sust', ['Sustainability', 'پایداری', 'Sürdürülebilirlik'],
      'sustainab\\w*|circular economy|nachhaltig\\w*|durabilit\\w+|d[eé]veloppement durable|sostenib\\w*|sustentab\\w*|s[uü]rd[uü]r[uü]lebilir\\w*|\\besg\\b|net[- ]zero|decarboni[sz]\\w*',
      'sustainab\\w*|nachhaltig\\w*|durable|پایدار\\S*|s[uü]rd[uü]r[uü]lebilir\\w*'],
    ['chemeng', ['Chemical engineering', 'مهندسی شیمی', 'Kimya mühendisliği'],
      'chemical engineering|process engineering|process systems|catalysis|catalyst\\w*|reactor\\w*|petrochemical\\w*|polymer (engineering|science|processing)|verfahrenstechnik|g[eé]nie (chimique|des proc[eé]d[eé]s)|ingenier[ií]a qu[ií]mica|ingegneria chimica|engenharia qu[ií]mica|kimya m[uü]hendis\\w*|separation process\\w*|bioprocess\\w*',
      'chemical engineering|verfahrenstechnik|g[eé]nie chimique|ingenier[ií]a qu[ií]mica|kimya m[uü]hendis\\w*|مهندسی شیمی'],
    ['mat', ['Materials science', 'علوم مواد', 'Malzeme bilimi'],
      'materials? (science|engineering|research|chemistry|design)|nanomaterial\\w*|metallurg\\w*|ceramic\\w*|composites?|alloys?|thin films?|nanotechnolog\\w*|werkstoff\\w*|mat[eé]riaux|materiales|malzeme\\w*|polymers?',
      'materials? (science|engineering)|werkstoff\\w*|mat[eé]riaux|malzeme\\w*|metallurg\\w*|مواد|مهندسی مواد'],
    ['mining', ['Mining & petroleum', 'معدن و نفت', 'Maden ve petrol'],
      'mining engineering|petroleum|oil and gas|reservoir engineering|drilling|mineral (processing|engineering)|bergbau|mining|maden m[uü]hendis\\w*',
      'mining|petroleum|bergbau|مهندسی معدن|مهندسی نفت|maden\\w*'],
    ['marine', ['Naval & ocean engineering', 'مهندسی دریا', 'Gemi ve deniz'],
      'naval architecture|marine engineering|ocean engineering|shipbuilding|maritime|offshore (engineering|structures)|schiffbau|gemi in[sş]aat\\w*',
      'naval architecture|marine engineering|ocean engineering|maritime|schiffbau|مهندسی دریا'],
    ['indeng', ['Industrial engineering', 'مهندسی صنایع', 'Endüstri mühendisliği'],
      'industrial engineering|operations research|systems engineering|production (planning|management)|lean manufacturing|six sigma|wirtschaftsingenieur\\w*|g[eé]nie industriel|ingenier[ií]a industrial|end[uü]stri m[uü]hendis\\w*|ergonomi\\w*|human factors',
      'industrial engineering|operations research|wirtschaftsingenieur\\w*|end[uü]stri m[uü]hendis\\w*|مهندسی صنایع'],
    ['biomed', ['Biomedical engineering', 'مهندسی پزشکی', 'Biyomedikal mühendislik'],
      'biomedical engineering|bioengineering|medical (device\\w*|imaging|physics|technology|engineering)|tissue engineering|biomechanic\\w*|biomaterial\\w*|biosensor\\w*|prosthe\\w*|medical image\\w*',
      'biomedical|bioengineering|biomechanic\\w*|مهندسی پزشکی|biyomedikal'],
    ['cs', ['Computer science', 'علوم کامپیوتر', 'Bilgisayar bilimleri'],
      '(solutions?|enterprise|technical|technology|data|cloud|security|network|systems?|infrastructure|application|integration|platform|information|digital|software) architect\\w*|computer (science|engineering|vision|graphics|systems|architecture)|computing|informatik|wirtschaftsinformatik|informatique|ciencias de la computaci[oó]n|inform[aá]tica|ci[eê]ncia da computa[cç][aã]o|informatica|bilgisayar\\w*|yaz[ıi]l[ıi]m|software\\w*|developer\\w*|d[eé]veloppeu\\w*|devops|c\\+\\+|\\bjava\\b|python|backend|frontend|full[- ]?stack|kubernetes|cyber ?security|cybers[eé]curit\\w*|information (technology|systems|security)|algorithms?|programming|databases?|operating systems?|distributed systems?|human[- ]computer|cryptograph\\w*|quantum computing|formal (methods|verification)|compilers?',
      'computer[\\p{L}]*|computing|informatik|informatique|inform[aá]tica|informatica|bilgisayar\\w*|software\\w*|yaz[ıi]l[ıi]m|علوم کامپیوتر|کامپیوتر|رایانه|مهندسی نرم.?افزار'],
    ['ai', ['Artificial intelligence', 'هوش مصنوعی', 'Yapay zeka'],
      'machine learning|deep learning|artificial intelligence|neural networks?|\\bai\\b|\\bnlp\\b|natural language processing|reinforcement learning|large language models?|generative ai|computer vision|intelligence artificielle|k[uü]nstliche intelligenz|\\bki\\b|inteligencia artificial|yapay zeka',
      'artificial intelligence|machine learning|deep learning|\\bai\\b|\\bki\\b|intelligence artificielle|k[uü]nstliche intelligenz|yapay zeka|هوش مصنوعی'],
    ['data', ['Data science & statistics', 'علم داده و آمار', 'Veri bilimi'],
      'data (science|scientist|analy\\w*|engineer\\w*|mining)|big data|statistic\\w*|bioinformatic\\w*|biostatistic\\w*|analytics|datenwissenschaft\\w*|science des donn[eé]es|ciencia de datos|veri bilimi',
      'data science|statistic\\w*|analytics|veri bilimi|علم داده|آمار'],
    ['math', ['Mathematics', 'ریاضیات', 'Matematik'],
      'mathematic\\w*|applied math\\w*|probabilit\\w*|topology|algebra\\w*|numerical (analysis|methods|simulation)|optimi[sz]ation|mathematik|math[eé]matique\\w*|matem[aá]tic\\w*|matematik|geometry|calculus|differential equations|stochastic\\w*|number theory',
      'mathematic\\w*|math[eé]matique\\w*|matem[aá]tic\\w*|matematik|ریاضی\\S*'],
    ['phys', ['Physics', 'فیزیک', 'Fizik'],
      'physics|photonic\\w*|astrophysic\\w*|astronom\\w*|quantum (physics|field|mechanics|optics|materials|technolog\\w*)|condensed matter|optics|cosmolog\\w*|plasma|physik|physique|f[ií]sica|fizik|fisica|laser\\w*|particle physics',
      'physics|physik|physique|f[ií]sica|fizik|astronom\\w*|فیزیک'],
    ['chemsci', ['Chemistry', 'شیمی', 'Kimya'],
      'chemistry|biochemistry|organic synthesis|inorganic|analytical chem\\w*|spectroscop\\w*|chemie|chimie|qu[ií]mica|kimya|chimica|electrochemi\\w*|medicinal chemistry|computational chemistry|chemical (biology|physics|sciences)',
      'chemistry|chemie|chimie|qu[ií]mica|kimya|شیمی'],
    ['bio', ['Biology & life sciences', 'زیست‌شناسی', 'Biyoloji'],
      'biolog\\w*|genetic\\w*|genom\\w*|molecular|\\bcell\\b|immunolog\\w*|microbiolog\\w*|biotechnolog\\w*|proteom\\w*|biomedical|bioengineering|zoolog\\w*|botan\\w*|biochemistr\\w*|evolution\\w*|physiology|biologie|biolog[ií]a|biyoloji|biotech|life sciences|bioinformatic\\w*',
      'biolog\\w*|genetic\\w*|biotech\\w*|life sciences|biyoloji|زیست\\S*'],
    ['neuro', ['Neuroscience', 'علوم اعصاب', 'Nörobilim'],
      'neuroscien\\w*|neurolog\\w*|neurobiolog\\w*|\\bbrain\\b|cognitive (science|neuroscience)|neuroimaging|neuropsych\\w*|neuro\\w+|neurowissenschaft\\w*',
      'neuro\\w*|n[oö]ro\\w*|عصب\\S*'],
    ['med', ['Medicine', 'پزشکی', 'Tıp'],
      'medicine|medical|clinical|surgery|surgeon\\w*|oncolog\\w*|cardiolog\\w*|patients?|physicians?|radiolog\\w*|patholog\\w*|epidemiolog\\w*|paediatric\\w*|pediatric\\w*|psychiatr\\w*|anesthes\\w*|anaesthes\\w*|dermatolog\\w*|ophthalmolog\\w*|orthop\\w*|obstetric\\w*|gynaecolog\\w*|urolog\\w*|[\\p{L}]*medizin\\w*|m[eé]decin\\w*|m[eé]dical\\w*|medicina|medicin\\w*|t[ıi]p\\w*|hekim\\w*|\\bmd\\b|mbbs|residency',
      'medicine|medical|clinical|medizin\\w*|m[eé]decine|medicina|t[ıi]p\\b|پزشک\\S*|طب\\b'],
    ['dent', ['Dentistry', 'دندانپزشکی', 'Diş hekimliği'],
      'dentist\\w*|dental|oral (health|surgery)|zahnmedizin|odontolog\\w*|di[sş] hekim\\w*|chirurgie dentaire',
      'dentist\\w*|dental|zahnmedizin|odontolog\\w*|دندان\\S*|di[sş] hekim\\w*'],
    ['vet', ['Veterinary science', 'دامپزشکی', 'Veterinerlik'],
      'veterinar\\w*|animal (health|science|welfare)|veterin[aä]r\\w*|tiermedizin|v[eé]t[eé]rinaire|veteriner\\w*|aquatic animal',
      'veterinar\\w*|veterin[aä]r\\w*|tiermedizin|v[eé]t[eé]rinaire|veteriner\\w*|دامپزشک\\S*'],
    ['pharm', ['Pharmacy & pharmacology', 'داروسازی', 'Eczacılık'],
      'pharmac\\w*|drug (discovery|development|delivery)|toxicolog\\w*|pharmazie|pharmacie|farmacia|eczac[ıi]l[ıi]k',
      'pharmac\\w*|pharmazie|pharmacie|farmacia|eczac\\w*|داروسازی'],
    ['health', ['Health sciences & nursing', 'علوم بهداشتی و پرستاری', 'Sağlık bilimleri'],
      'nurs(?:e|es|ing)|public health|physiotherap\\w*|health (care|sciences?|policy|informatics|management|promotion|economics|systems?)|midwif\\w*|rehabilitation|nutrition|dietetic\\w*|occupational therap\\w*|global health|epidemiolog\\w*|gesundheit\\w*|pflege\\w*|sant[eé] publique|salud (p[uú]blica|mental)|enfermer[ií]a|hem[sş]irelik|sa[gğ]l[ıi]k|mental health',
      'nursing|public health|health[\\p{L}]*|gesundheit\\w*|sant[eé]|salud|sa[gğ]l[ıi]k|پرستار\\S*|بهداشت|سلامت'],
    ['sport', ['Sport science', 'علوم ورزشی', 'Spor bilimleri'],
      'sports? (science|management|medicine|psychology|coaching|physiology)|exercise (science|physiology)|kinesiolog\\w*|sportwissenschaft\\w*|sciences du sport|ciencias del deporte|spor bilimleri|physical education|human movement',
      'sport\\w*|exercise|kinesiolog\\w*|spor\\b|ورزش\\S*'],
    ['psych', ['Psychology', 'روانشناسی', 'Psikoloji'],
      'psycholog\\w*|cognitive|behaviou?ral (science|economics|insights|neuroscience)|neuropsych\\w*|psychotherap\\w*|psicolog\\w*|psikolog\\w*|psychologie|counsell?ing|mental processes|wellbeing|well-being',
      'psycholog\\w*|psicolog\\w*|psikolog\\w*|psychologie|روان ?شناس\\S*|روانشناسی'],
    ['soc', ['Sociology & anthropology', 'جامعه‌شناسی و انسان‌شناسی', 'Sosyoloji'],
      'sociolog\\w*|anthropolog\\w*|gender studies|social (science\\w*|work|policy|research|theory)|migration|demograph\\w*|ethnolog\\w*|ethnograph\\w*|soziolog\\w*|sociolog[ií]a|sosyoloji|criminolog\\w*|sozialwissenschaft\\w*|sciences sociales|ciencias sociales|sosyal bilim\\w*|sozialarbeit|travail social|trabajo social',
      'sociolog\\w*|anthropolog\\w*|social (science|work)\\w*|soziolog\\w*|sosyoloji|ciencias sociales|sciences sociales|جامعه ?شناس\\S*|انسان ?شناس\\S*'],
    ['pol', ['Political science & international relations', 'علوم سیاسی و روابط بین‌الملل', 'Siyaset bilimi'],
      'political (science|theory|economy|philosophy)|politics|international relations|diplomacy|security studies|public (policy|administration|management|affairs)|policy analysis|governance|politik\\w*|politolog\\w*|relations internationales|relaciones internacionales|uluslararas[ıi] ili[sş]kiler|siyaset\\w*|peace (and conflict|studies)|european studies|area studies|verwaltungswissenschaft\\w*|administration publique|administraci[oó]n p[uú]blica|kamu y[oö]netimi',
      'politic\\w*|political[\\p{L}]*|international relations|diplomacy|public (policy|administration)|governance|siyaset\\w*|علوم سیاسی|روابط بین ?الملل|سیاست'],
    ['dev', ['Development studies', 'مطالعات توسعه', 'Kalkınma çalışmaları'],
      'development (studies|economics|cooperation|policy|aid|practice)|international development|humanitarian\\w*|global south|entwicklungs\\w+|d[eé]veloppement international|desarrollo (internacional|sostenible)|kalk[ıi]nma',
      'development studies|international development|humanitarian\\w*|entwicklungs\\w+|kalk[ıi]nma|مطالعات توسعه'],
    ['econ', ['Economics', 'اقتصاد', 'Ekonomi'],
      'econom(?:ic|ics|ist|ists|y|ies)(?![\\p{L}])|[eé]conom\\w*|[oö]konom\\w*|volkswirtschaft\\w*|wirtschaftswissenschaft\\w*|econom[ií]a\\w*|economia\\w*|ekonomi\\w*|iktisat|econometric\\w*|macroeconom\\w*|microeconom\\w*|game theory|public finance|political economy|ciencias econ[oó]micas|sciences [eé]conomiques',
      'econom\\w*|[eé]conom\\w*|[oö]konom\\w*|volkswirtschaft\\w*|ekonomi\\w*|econom[ií]a|اقتصاد\\S*',
      { x: R('circular economy|green economy|creative economy|economy class|economic aid') }],
    ['fin', ['Finance & accounting', 'مالی و حسابداری', 'Finans ve muhasebe'],
      'financ(?:e|es|ial|ing)(?![\\p{L}])|banking|investment|asset management|actuarial|insurance|accounting|auditing|fintech|corporate finance|risk management|finanz\\w*|finanza\\w*|finanzas|finans\\w*|bankwesen|comptabilit\\w+|contabil\\w+|muhasebe',
      'financ\\w*|banking|accounting|finanz\\w*|finans\\w*|comptabilit\\w+|بانک\\S*|مالی|حسابداری',
      { x: R('financial (aid|support|assistance|help|resources|services? for students|matters)|student finance|finances? (for|of) (students|your|international)|financing (your|for) (studies|study)|funding|scholarship|fees? and finance') }],
    ['bus', ['Business & management', 'کسب‌وکار و مدیریت', 'İşletme'],
      'business|(?<!water |waste |resources? |environmental |energy |forest |coastal |disaster |land |wildlife |soil |data |knowledge |natural )management|marketing|\\bmba\\b|entrepreneur\\w*|supply chain|logistics|human resources?|organi[sz]ational|innovation management|leadership|strategy|consult\\w*|betriebswirtschaft\\w*|gestion|administraci[oó]n de (empresas|negocios)|negocios|[iİ][sş]letme\\w*|y[oö]netim|commerce|digital transformation|e-commerce|project management',
      'business|management|marketing|\\bmba\\b|entrepreneur\\w*|supply chain|logistics|betriebswirtschaft\\w*|administraci[oó]n de empresas|[iİ][sş]letme\\w*|مدیریت|کسب ?و ?کار|بازاریابی'],
    ['tour', ['Tourism & hospitality', 'گردشگری و مهمان‌داری', 'Turizm'],
      'tourism|hospitality|hotel management|travel (and|management)|tourismus|tourisme|turismo|turizm|culinary|events? management|gastronom\\w*',
      'touris\\w*|hospitality|tourismus|tourisme|turismo|turizm|گردشگری'],
    ['law', ['Law', 'حقوق', 'Hukuk'],
      '\\blaws?\\b|\\blegal\\b|jurisprud\\w*|jurist\\w*|juridi\\w*|juristisch\\w*|rechtswissenschaft\\w*|rechts\\w*|\\brecht\\b|\\bdroits?\\b|derecho|direito|diritto|giurisprudenza|hukuk\\w*|rettsvitenskap\\w*|ll\\.m\\.?|\\bllb\\b|master of laws?|advokat\\w*|advogad\\w*|abogac[ií]a|avocat\\w*|arbitration|notar\\w*|juridisk\\w*',
      '\\blaws?\\b|legal|jurid\\w*|jurist\\w*|recht\\w*|\\bdroit\\w*|derecho|direito|diritto|hukuk\\w*|حقوق|قانون'],
    ['edu', ['Education', 'آموزش و پرورش', 'Eğitim'],
      'education\\w*|pedagog\\w*|teaching and learning|didactic\\w*|curriculum|teacher (training|education)|language (teaching|learning)|erziehungswissenschaft\\w*|bildungswissenschaft\\w*|lehramt|sciences de l.[eé]ducation|educaci[oó]n|educa[cç][aã]o|e[gğ]itim\\w*|tesol|p[aä]dagogik',
      'education\\w*|pedagog\\w*|educaci[oó]n|e[gğ]itim\\w*|p[aä]dagogik|آموزش|تعلیم'],
    ['lang', ['Languages & linguistics', 'زبان و زبان‌شناسی', 'Dil bilimi'],
      'languages?|linguistic\\w*|translation|interpreting|applied linguistics|german studies|english studies|romance (languages|studies)|sprach\\w+|langues?|lenguas?|dil bilim\\w*|filolog\\w*|dilbilim',
      'languages?|linguistic\\w*|translation|sprach\\w+|langues?|lenguas?|dilbilim|زبان\\S*'],
    ['hum', ['Humanities (history & philosophy)', 'علوم انسانی', 'Beşeri bilimler'],
      'histor(?:y|ical|ian|ians)(?![\\p{L}])|philosoph\\w*|literatur\\w*|classics|classical (studies|archaeology)|archaeolog\\w*|archeolog\\w*|cultural studies|musicolog\\w*|philolog\\w*|humanities|geschichte|geschichtswissenschaft\\w*|histoire|historia|storia|tarih\\w*|philosophie|filosof[ií]a|literary|arch[aä]ologie|medieval|art history|kunstgeschichte|islamic studies|oriental studies|asian studies|middle eastern studies|african studies',
      'histor\\w*|philosoph\\w*|literatur\\w*|archaeolog\\w*|geschichte|histoire|historia|storia|tarih\\w*|filosof[ií]a|تاریخ|فلسفه|ادبیات|باستان ?شناس\\S*'],
    ['theo', ['Theology & religion', 'الهیات و ادیان', 'İlahiyat'],
      'theolog\\w*|theologie|th[eé]ologie|teolog[ií]a|ilahiyat|religious studies|divinity|biblical|pastoral|religio\\w*',
      'theolog\\w*|religio\\w*|ilahiyat|الهیات|ادیان|دینی'],
    ['art', ['Art & design', 'هنر و طراحی', 'Sanat ve tasarım'],
      'fine arts?|visual arts?|\\bfilm\\b|cinema|theatre|theater|performing arts|graphic design|industrial design|product design|fashion|photograph\\w*|illustration|animation|communication design|interaction design|service design|creative (arts|practice)|bellas artes|beaux-arts|kunst\\w*|sanat\\w*|design (school|studies)|art and design|curatorial|museum studies|dance|sculpture|painting',
      'fine arts?|visual arts?|\\bfilm\\b|cinema|theat\\w+|graphic design|industrial design|product design|fashion|photograph\\w*|animation|kunst\\w*|sanat\\w*|هنر\\S*|طراحی صنعتی|گرافیک'],
    ['music', ['Music', 'موسیقی', 'Müzik'],
      'music\\w*|musik\\w*|musique|m[uú]sica|m[uü]zik\\w*|conservatoire|konservatorium|orchestra|opera|jazz|ethnomusicolog\\w*',
      'music\\w*|musik\\w*|musique|m[uú]sica|m[uü]zik\\w*|موسیقی'],
    ['comm', ['Media & communication', 'رسانه و ارتباطات', 'İletişim'],
      'communication (studies|science\\w*|and media)|media (studies|science\\w*|and communication)|journalis\\w*|publizistik|kommunikationswissenschaft\\w*|medienwissenschaft\\w*|communication sociale|comunicaci[oó]n|comunica[cç][aã]o|ileti[sş]im|public relations|advertising|broadcast\\w*|digital media|film studies',
      'communication\\w*|media|journalis\\w*|publizistik|kommunikation\\w*|medien\\w*|ileti[sş]im|رسانه|ارتباطات|روزنامه ?نگاری'],
    ['geo', ['Earth sciences & geography', 'علوم زمین و جغرافیا', 'Yer bilimleri'],
      'geolog\\w*|geophysic\\w*|geomatic\\w*|geodes\\w*|remote sensing|\\bgis\\b|hydrolog\\w*|earth sciences?|seismolog\\w*|oceanograph\\w*|meteorolog\\w*|geograph\\w*|atmospher\\w*|geowissenschaft\\w*|g[eé]ologie|geolog[ií]a|jeoloji|co[gğ]rafya|cartograph\\w*|geoinformat\\w*|glaciolog\\w*|volcanolog\\w*|marine (science|biology)|earth observation',
      'geolog\\w*|geograph\\w*|geophysic\\w*|remote sensing|geomatic\\w*|geowissenschaft\\w*|jeoloji|co[gğ]rafya|جغرافیا|زمین ?شناس\\S*'],
    ['agri', ['Agriculture & forestry', 'کشاورزی و منابع طبیعی', 'Tarım'],
      'agricultur\\w*|agronom\\w*|\\bcrops?\\b|\\bsoil\\b|forestry|horticultur\\w*|animal science|aquaculture|agrar\\w*|landwirtschaft\\w*|agricole|agricultura|agr[ií]cola|tar[ıi]m\\w*|plant (science|breeding|pathology)|viticultur\\w*|fisheries|livestock|rural development',
      'agricultur\\w*|agronom\\w*|agrar\\w*|landwirtschaft\\w*|tar[ıi]m\\w*|کشاورزی|منابع طبیعی'],
    ['food', ['Food science', 'علوم غذایی', 'Gıda'],
      'food (science|technology|engineering|safety|chemistry)|lebensmittel\\w*|nutrition science|g[ıi]da\\w*|alimentaire|alimentos|enolog\\w*|brewing|dairy',
      'food[\\p{L}]*|lebensmittel\\w*|g[ıi]da\\w*|alimentaire|علوم غذایی|صنایع غذایی']
  ];

  /* strictly limited relations (symmetric). A related domain counts only if the opportunity is a member of it. */
  const REL_PAIRS = [
    ['arch', 'urban'], ['arch', 'construction'], ['urban', 'land'], ['urban', 'civil'], ['urban', 'transport'], ['land', 'env'], ['heritage', 'hum'],
    ['civil', 'construction'], ['civil', 'bldtech'], ['civil', 'env'], ['civil', 'transport'], ['civil', 'mining'], ['construction', 'bldtech'], ['construction', 'bus'],
    ['mech', 'aero'], ['mech', 'mat'], ['mech', 'robotics'], ['mech', 'energy'], ['mech', 'indeng'], ['mech', 'marine'], ['mech', 'biomed'],
    ['elec', 'energy'], ['elec', 'robotics'], ['elec', 'biomed'], ['aero', 'robotics'],
    ['cs', 'ai'], ['cs', 'data'], ['ai', 'data'], ['ai', 'robotics'], ['data', 'math'], ['math', 'phys'], ['cs', 'math'],
    ['chemeng', 'chemsci'], ['chemeng', 'mat'], ['chemeng', 'env'], ['chemeng', 'energy'], ['chemsci', 'mat'], ['chemsci', 'bio'], ['phys', 'mat'],
    ['env', 'sust'], ['env', 'energy'], ['env', 'agri'], ['env', 'geo'], ['sust', 'energy'], ['sust', 'dev'], ['geo', 'civil'],
    ['med', 'health'], ['med', 'pharm'], ['med', 'bio'], ['med', 'dent'], ['med', 'neuro'], ['med', 'biomed'], ['bio', 'neuro'], ['bio', 'agri'], ['bio', 'pharm'], ['bio', 'biomed'], ['vet', 'agri'], ['vet', 'bio'], ['food', 'agri'],
    ['psych', 'neuro'], ['psych', 'health'], ['soc', 'pol'], ['soc', 'dev'], ['soc', 'comm'], ['pol', 'law'], ['pol', 'dev'], ['pol', 'econ'],
    ['econ', 'fin'], ['fin', 'bus'], ['econ', 'dev'], ['bus', 'tour'], ['bus', 'indeng'],
    ['hum', 'theo'], ['hum', 'lang'], ['hum', 'art'], ['hum', 'soc'], ['art', 'music'], ['art', 'comm'], ['sport', 'health'], 
  ];

  /* ---------------- build ---------------- */
  const D = {}, ORDER = [], NAMES = {}, KIDS = {}, REL = {};
  DEF.forEach(([id, names, t, q, o]) => {
    o = o || {};
    D[id] = {
      id, t: R(PRE + '(?:' + t + ')'), tg: new RegExp(PRE + '(?:' + t + ')', 'giu'), q: new RegExp('(?:^|[^\\p{L}])(' + q + ')', 'iu'),
      ctx: o.ctx || null, ctxFor: o.ctxFor || null, neg: o.neg || null, x: o.x || null
    };
    ORDER.push(id); NAMES[id] = names; if (o.kids) KIDS[id] = o.kids;
  });
  REL_PAIRS.forEach(([a, b]) => { (REL[a] = REL[a] || new Set()).add(b); (REL[b] = REL[b] || new Set()).add(a); });
  const GENERIC_ENG = { q: R('(?:^|[^\\p{L}])(engineering|ingenieur\\w*|ingenier[ií]a|m[uü]hendislik|مهندسی)'), dom: ['civil', 'mech', 'elec', 'chemeng', 'aero', 'mat', 'energy', 'env', 'indeng', 'biomed', 'marine', 'mining', 'construction'] };

  /* ---------------- word-sense guards (architecture & friends) ---------------- */
  const CS_CTX = R('software|logiciel|c\\+\\+|\\bcloud\\b|devops|developer|d[eé]veloppeur|programm|\\bjava\\b|python|backend|frontend|full[- ]?stack|enterprise|solutions?|\\bdata\\b|systems?|network|security|platform|application|saas|\\baws\\b|azure|\\.net|\\bsap\\b|\\bit\\b|technical architect');
  const BUILD_CTX = R('building|urban|landscape|interior|design studio|construction|planning|school of architecture|college of architecture|master of architecture|faculty of architecture|\\bbim\\b|heritage|architectural (design|history|theory|technology|engineering)|architekt|arquitect|mimar|housing|city|architect[ei]\\b.*\\b(project|junior|senior|intern)');
  const NOT_ARCH = R('(computer|processor|micro|network|neural|system|systems|software|data|cloud|enterprise|solution|solutions|security|information|memory|chip|hardware|model|application|technical|technology|digital|infrastructure|platform|integration|it) architect|architected\\b|brain[- ]inspired|exoskeleton');
  const TECH_CTX = R('hardware|exoskeleton|actuat|brain-inspired|cmos|asic|fpga|circuit|processor|\\bgpu\\b|neural|network|software|cloud|memory|rram|\\bchip|sensor|protocol|microservice|pipeline|\\bllm\\b|\\bmodel(l)?ing\\b|robot');
  const JUNK_TOPIC = R('^(jobs?|jobs\\.ac\\.uk|appointments?|vacanc\\w*|positions?|careers?|academic|lecturer|professor|research|staff|employment|hiring|apply|faculty|university|school|college|phd|postdoc\\w*|studentships?|funding|scholarships?|fellowships?|news|home|international|students?)$');

  function cleanTopics(t) {
    if (!t) return '';
    return String(t).split(/[,;|]/).map(s => s.trim()).filter(s => s && s.length <= 45 && !JUNK_TOPIC.test(s)).join(' , ');
  }

  /* does text belong to domain id? returns number of hits (0 = no), with sense guards */
  function hits(id, text, count) {
    const d = D[id];
    if (!text) return 0;
    let tx = text;
    if (d.x) tx = tx.replace(new RegExp(d.x.source, 'giu'), ' ');
    if (!d.t.test(tx)) return 0;
    if (d.neg && d.neg.test(tx) && !/mechanical engineer/i.test(tx)) return 0;
    if (id === 'arch') {
      if (NOT_ARCH.test(tx)) return 0;
      if (CS_CTX.test(tx) && !BUILD_CTX.test(tx)) return 0;
      if (TECH_CTX.test(tx) && !BUILD_CTX.test(tx)) return 0;
    }
    if (d.ctx && (!d.ctx.test(tx) || (TECH_CTX.test(tx) && !BUILD_CTX.test(tx)))) return 0;
    if (d.ctxFor) {      /* ambiguous single words that need a context word ("bridge", "BIM") */
      for (const k in d.ctxFor) {
        const amb = new RegExp(PRE + '(?:' + k + ')', 'iu');
        if (amb.test(tx)) {
          const rest = tx.replace(new RegExp(PRE + '(?:' + k + ')', 'giu'), ' ');
          if (!d.t.test(rest) && !d.ctxFor[k].test(tx)) return 0;
        }
      }
    }
    if (!count) return 1;
    const m = tx.match(d.tg);
    return m ? m.length : 1;
  }

  /* ---------------- site-wide keyword lists are not about one opportunity ---------------- */
  function prepare(list) {
    const cnt = new Map();
    list.forEach(p => { const t = String(p.topics || '').trim().toLowerCase(); if (t) { const k = (p.inst || p.uni || '') + '|' + t; cnt.set(k, (cnt.get(k) || 0) + 1); } });
    list.forEach(p => {
      const t = String(p.topics || '').trim().toLowerCase();
      p._tb = !!t && (((cnt.get((p.inst || p.uni || '') + '|' + t)) || 0) >= 3 || t.split(/[,;|]/).length > 9);
    });
    return list;
  }

  const W_TITLE = 3, W_RT = 2.6, W_TOPIC = 1.6, W_INST = 1.4;
  /* scores {domain: number}; >= MEMBER: belongs to the domain; WEAK..MEMBER: weak evidence */
  function score(p) {
    const title = String(p.title || ''), rt = String(p.rt || ''), desc = String(p.desc || ''), inst = String(p.inst || p.uni || '');
    const topics = p._tb ? '' : cleanTopics(p.topics);
    const out = {};
    for (const id of ORDER) {
      let s = 0;
      if (hits(id, title)) s += W_TITLE;
      if (rt && hits(id, rt)) s += W_RT;
      if (topics && hits(id, topics)) s += W_TOPIC;
      if (desc) { const n = hits(id, desc, true); if (n) s += Math.min(3, 0.9 * n); }
      if (s > 0 && s < MEMBER && inst && hits(id, inst)) s += W_INST;      /* the institution name only backs up other evidence (a whole university must not become 'related') */
      if (s >= WEAK) out[id] = Math.round(Math.min(s, 6) * 10) / 10;
    }
    return out;
  }

  /* domain scores of a position (cached). Uses the baked list p.dm when it was produced by this engine version. */
  function classify(p) {
    if (p._dom) return p._dom;
    let out;
    if (p.dv === VERSION) { out = {}; (p.dm || []).forEach(([i, s]) => { out[i] = s; }); }      /* baked (also when empty: nothing found) */
    else out = score(p);
    const top = Object.entries(out).sort((a, b) => b[1] - a[1]).slice(0, 6);
    return (p._dom = Object.fromEntries(top));
  }
  const members = p => Object.keys(classify(p)).filter(i => classify(p)[i] >= MEMBER);
  const bake = p => Object.entries(score(p)).sort((a, b) => b[1] - a[1]).slice(0, 6);

  /* ---------------- query ---------------- */
  const STOP = new Set(['in', 'of', 'and', 'the', 'for', 'at', 'to', 'a', 'phd', 'position', 'positions', 'master', 'masters', 'msc', 'degree', 'program', 'programme', 'science', 'sciences', 'studies', 'study', 'research', 'engineering', 'scholarship', 'fellowship', 'postdoc', 'job', 'jobs', 'internship', 'department', 'school', 'faculty', 'university', 'جستجو', 'و', 'در', 'مهندسی', 'رشته']);
  function parseQuery(text) {
    const lower = String(text || '').toLowerCase().trim();
    let rest = lower;
    const doms = new Set();
    for (const id of ORDER) {
      const m = D[id].q.exec(rest);
      if (m) {                                       /* the whole matched phrase is consumed - no stray letters stay behind as an extra text filter */
        doms.add(id);
        const s = m.index + m[0].length - m[1].length;
        rest = rest.slice(0, s) + ' ' + rest.slice(s + m[1].length);
      }
    }
    if (!doms.size && GENERIC_ENG.q.test(rest)) { GENERIC_ENG.dom.forEach(x => doms.add(x)); rest = rest.replace(GENERIC_ENG.q, ' '); }
    const toks = rest.split(/[\s,;:/]+/).filter(t => t && t.length > 1 && !STOP.has(t));
    return { doms, rest: toks, lower };
  }
  function expandDoms(q) {
    const e = new Set(q.doms);
    q.doms.forEach(d => (KIDS[d] || []).forEach(k => e.add(k)));
    return e;
  }

  /* judge: {k: 'direct'|'related'|'unclassified'|'irrelevant'|null, s: score} */
  function judge2(p, q, lexicalHit) {
    if (!q.doms.size) return { k: lexicalHit ? 'direct' : null, s: 0 };
    const c = classify(p), ids = Object.keys(c);
    const ex = q._ex || (q._ex = expandDoms(q));
    let best = 0, rel = 0, weakOwn = 0;
    const relSet = q._rel || (q._rel = (() => { const s = new Set(); q.doms.forEach(d => (REL[d] || []).forEach(x => { if (!ex.has(x)) s.add(x); })); return s; })());
    ids.forEach(i => {
      if (ex.has(i)) { if (c[i] >= MEMBER) best = Math.max(best, c[i]); else weakOwn = Math.max(weakOwn, c[i]); }
      else if (relSet.has(i) && c[i] >= 3) rel = Math.max(rel, c[i]);
    });
    if (best) return { k: 'direct', s: best };
    if (rel) return { k: 'related', s: rel };
    if (weakOwn) return { k: 'related', s: weakOwn * 0.5 };
    if (!lexicalHit) return { k: null, s: 0 };
    return { k: ids.some(i => c[i] >= MEMBER) ? 'irrelevant' : 'unclassified', s: 0 };
  }
  const judge = (p, q, lex) => judge2(p, q, lex).k;
  /* does the raw text contain a word of the queried domain(s)? (no sense guard: finds look-alike words) */
  function wordHit(q, text) { for (const d of expandDoms(q)) { if (D[d].t.test(text || '')) return true; } return false; }

  root.Rel = { VERSION, MEMBER, classify, members, bake, prepare, parseQuery, judge, judge2, wordHit, cleanTopics, DOMAINS: ORDER, NAMES, KIDS, REL };
  if (typeof module !== 'undefined') module.exports = root.Rel;
})(typeof window !== 'undefined' ? window : globalThis);
