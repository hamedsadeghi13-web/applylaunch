#!/usr/bin/env python3
"""Builds prototypes.json: for each of the 56 relevance.js domains a list of seed phrases (name in en/fa/tr from relevance.js NAMES +
hand-written subfield phrases in en/de/fr/es). Seeds come ONLY from field names and subfield vocabulary - never from records,
rule-engine members or labelled data (no circularity, no Dev leakage). Run: node -e to export NAMES, then python3 make_prototypes.py."""
import json,subprocess,os
HERE=os.path.dirname(os.path.abspath(__file__))
names=json.loads(subprocess.check_output(['node','-e',"const R=require('../../docs/relevance.js');console.log(JSON.stringify({d:R.DOMAINS,n:R.NAMES}))"],cwd=HERE))
SEEDS={
'land':['landscape architecture','landscape design and planning','landscape ecology and urbanism','Landschaftsarchitektur','architecture du paysage','paisajismo'],
'interior':['interior architecture','interior design','spatial design of interiors','Innenarchitektur','architecture d\'intérieur','diseño de interiores'],
'heritage':['heritage conservation','architectural conservation and restoration','cultural heritage management','historic building preservation','Denkmalpflege','patrimoine culturel','restauración del patrimonio'],
'compdesign':['computational design','parametric and generative design','digital fabrication and robotic construction','algorithmic architecture','form finding'],
'bldtech':['building science and technology','building physics and energy performance','building information modelling (BIM)','facade engineering','timber construction','Bauphysik','physique du bâtiment'],
'construction':['construction management','construction engineering and project management','quantity surveying and cost control','construction industry','Baumanagement','gestion de chantier'],
'urban':['urban planning','urban design and city planning','regional and spatial planning','urban studies and urban development','Stadtplanung','urbanisme','planificación urbana'],
'arch':['architecture','architectural design and theory','architectural studies and building design','history and theory of architecture','Architektur','architecture (conception architecturale)','arquitectura'],
'civil':['civil engineering','structural engineering','geotechnical engineering','hydraulic and water resources engineering','infrastructure engineering','Bauingenieurwesen','génie civil','ingeniería civil'],
'transport':['transport engineering and mobility','transportation planning and traffic','railway and road engineering','logistics and mobility systems','Verkehrswesen','ingénierie des transports'],
'mech':['mechanical engineering','thermodynamics and fluid mechanics','machine design and manufacturing','heat transfer and combustion','mechatronics','Maschinenbau','génie mécanique','ingeniería mecánica'],
'aero':['aerospace engineering','aerodynamics and flight dynamics','spacecraft and propulsion','aircraft design','Luft- und Raumfahrttechnik','ingénierie aérospatiale'],
'robotics':['robotics','autonomous robots and manipulation','robot control and perception','mobile robotics','Robotik','robotique'],
'elec':['electrical and electronic engineering','power systems and electrical machines','electronics and microelectronics','signal processing and communications','control systems','Elektrotechnik','génie électrique','ingeniería eléctrica'],
'energy':['energy systems and technology','renewable energy and power generation','energy storage and batteries','smart grids and energy efficiency','Energietechnik','énergies renouvelables'],
'env':['environmental engineering and science','water and wastewater treatment','air pollution and environmental remediation','climate and ecosystem science','waste management','Umweltwissenschaften','sciences de l\'environnement','ingeniería ambiental'],
'sust':['sustainability and sustainable development','circular economy and sustainable design','climate change mitigation and adaptation','sustainability science','Nachhaltigkeit','développement durable'],
'chemeng':['chemical engineering','process engineering and reaction engineering','catalysis and chemical reactors','polymer and petrochemical engineering','bioprocess engineering','Verfahrenstechnik','génie chimique','ingeniería química'],
'mat':['materials science and engineering','nanomaterials and functional materials','metals ceramics and composites','materials characterization','Werkstoffwissenschaft','science des matériaux'],
'mining':['mining engineering','petroleum and reservoir engineering','mineral processing and extraction','oil and gas engineering','Bergbau','génie minier'],
'marine':['naval architecture and ocean engineering','ship design and marine technology','offshore engineering','maritime engineering','Schiffbau','architecture navale'],
'indeng':['industrial engineering','operations research and production systems','supply chain and logistics optimisation','quality and reliability engineering','Wirtschaftsingenieurwesen','génie industriel'],
'biomed':['biomedical engineering','medical devices and biomaterials','biomechanics and medical imaging','tissue engineering','Biomedizinische Technik','génie biomédical'],
'cs':['computer science','software engineering and programming','algorithms and computer systems','cybersecurity and networks','databases and distributed systems','Informatik','informatique','ciencias de la computación'],
'ai':['artificial intelligence','machine learning and deep learning','natural language processing and computer vision','neural networks and reinforcement learning','Künstliche Intelligenz','intelligence artificielle','inteligencia artificial'],
'data':['data science and statistics','statistical modelling and data analytics','biostatistics and econometrics','big data and data mining','Statistik','statistique'],
'math':['mathematics','pure and applied mathematics','algebra geometry and analysis','probability and mathematical modelling','Mathematik','mathématiques','matemáticas'],
'phys':['physics','quantum and condensed matter physics','astrophysics and particle physics','optics and photonics','Physik','physique','física'],
'chemsci':['chemistry','organic and inorganic chemistry','analytical and physical chemistry','chemical synthesis and spectroscopy','Chemie','chimie','química'],
'bio':['biology and life sciences','molecular biology and genetics','ecology and evolution','microbiology and cell biology','biotechnology','Biologie','biologie','biología'],
'neuro':['neuroscience','brain function and cognitive neuroscience','neurobiology and neuroimaging','neurological disease research','Neurowissenschaften','neurosciences'],
'med':['medicine','clinical medicine and surgery','oncology cardiology and internal medicine','medical research and physician training','public health and epidemiology','Medizin','médecine','medicina'],
'dent':['dentistry','oral health and dental surgery','orthodontics and periodontology','Zahnmedizin','médecine dentaire'],
'vet':['veterinary science','animal health and veterinary medicine','livestock and companion animal disease','Veterinärmedizin','médecine vétérinaire'],
'pharm':['pharmacy and pharmacology','drug discovery and pharmaceutical sciences','toxicology and clinical pharmacy','Pharmazie','pharmacie'],
'health':['health sciences and nursing','public health and health policy','nursing and midwifery','rehabilitation and physiotherapy','Gesundheitswissenschaften','sciences infirmières'],
'sport':['sport science','exercise physiology and kinesiology','sports performance and coaching','Sportwissenschaft','sciences du sport'],
'psych':['psychology','clinical and counselling psychology','cognitive and social psychology','developmental and educational psychology','psychotherapy and mental health','Psychologie','psychologie','psicología'],
'soc':['sociology and anthropology','social theory and cultural anthropology','social research and inequality','Soziologie','sociologie','sociología'],
'pol':['political science and international relations','public policy and governance','security studies and diplomacy','comparative politics','Politikwissenschaft','science politique'],
'dev':['development studies','international development and poverty','global development cooperation','humanitarian studies','Entwicklungsstudien','études du développement'],
'econ':['economics','microeconomics and macroeconomics','econometrics and development economics','labour and public economics','Volkswirtschaftslehre','sciences économiques','economía'],
'fin':['finance and accounting','banking and financial markets','corporate finance and auditing','actuarial science and risk management','Finanzwirtschaft','finance et comptabilité'],
'bus':['business and management','business administration and MBA','marketing and entrepreneurship','organisational behaviour and strategy','Betriebswirtschaftslehre','gestion des entreprises','administración de empresas'],
'tour':['tourism and hospitality','hotel and event management','sustainable tourism','Tourismus','tourisme et hôtellerie'],
'law':['law','legal studies and jurisprudence','international and human rights law','commercial and criminal law','Rechtswissenschaft','droit','derecho'],
'edu':['education','teacher training and pedagogy','educational research and curriculum','higher education and learning sciences','Erziehungswissenschaft','sciences de l\'éducation'],
'lang':['languages and linguistics','applied linguistics and translation','literature and language teaching','Sprachwissenschaft','linguistique'],
'hum':['humanities','history and philosophy','archaeology and classical studies','cultural studies and literature','Geschichtswissenschaft','histoire et philosophie'],
'theo':['theology and religious studies','Islamic studies and divinity','biblical studies and philosophy of religion','Theologie','théologie'],
'art':['art and design','fine arts and visual arts','graphic and product design','film and creative practice','Kunst und Design','arts visuels'],
'music':['music','musicology and composition','performance and music theory','Musikwissenschaft','musicologie'],
'comm':['media and communication studies','journalism and public relations','digital media and film studies','Kommunikationswissenschaft','sciences de la communication'],
'geo':['earth sciences and geography','geology and geophysics','geospatial science and GIS','climate and atmospheric sciences','Geowissenschaften','géosciences'],
'agri':['agriculture and forestry','crop science and soil science','agricultural economics and food production','forestry and natural resources','Agrarwissenschaft','sciences agronomiques'],
'food':['food science and technology','food chemistry and nutrition','food safety and processing','Lebensmitteltechnologie','science des aliments'],
}
out={}
miss=[d for d in names['d'] if d not in SEEDS];assert not miss,miss
for d in names['d']:
    out[d]={'names':names['n'][d],'seeds':sorted(set(names['n'][d]+SEEDS[d]))}
json.dump({'version':1,'note':'seeds from field names/subfield vocabulary only','domains':out},open(os.path.join(HERE,'prototypes.json'),'w'),ensure_ascii=False,indent=1)
print(len(out),sum(len(v['seeds']) for v in out.values()),'seeds')
