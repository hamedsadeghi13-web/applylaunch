"""python3 tests/test_extract.py  - type/kind/text-extraction rules (offline)."""
import sys,os,json
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','crawler'))
import extract as X
from bs4 import BeautifulSoup
fails=[]
def eq(name,got,want):
    if got!=want:fails.append(f'{name}: got {got!r} want {want!r}')
# ---- the intern / international family: never an internship
for t in ['International Students','Internationale Studierende - TU Dortmund','Internal Affairs','Internet of Things Lab','International Office','Internationales','Interna befordringar','Interni pozivi i rezultati','International Marketing Management maisteriohjelma','Internationalität Bucerius','Internazionalizzazione','Intercultural Bible reading','Internado de Medicina']:
    eq('not-intern '+t,X.type_of(t)=='Internship',False)
for t,w in [('Internship – Data Team','Internship'),('Praktikum beim BUND Naturschutz','Internship'),('Stage H/F niveau Master 2, Modélisation','Internship'),('Summer Intern, Data Science','Internship'),('Erasmus+ Traineeship','Internship'),('Praktikantin (m/w/d)','Internship'),('Becario de investigación','Internship')]:
    eq('intern '+t,X.type_of(t),w)
# ---- other whole-word cases
eq('mastering',X.type_of('Mastering Machine Learning workshop'),None)
eq('promotion news',X.type_of('BBC2 Autumn promotion - Corridor ident'),None)
eq('masterclass',X.type_of('Masterclass in watercolour'),None)
eq('phd',X.type_of('Ph.D. in Computer Science & Engineering'),'PhD')
eq('postdoc',X.type_of('Postdoctoral Researcher (m/f/d) in Topological Data Analysis'),'Postdoc')
eq('grant not in grantham',X.type_of('Grantham Institute news'),None)
eq('bursa',X.type_of('Bursa Technical University campus'),None)
eq('burs',X.type_of('Burs Başvurusu 2026'),'Scholarship')
# ---- kind
for t,w in [('Postdoctoral Researcher (m/f/d) in Topological Data Analysis','opening'),('PhD Position in Soft Robotics','opening'),('Master of Science (M.Sc.) Artificial Intelligence','programme'),('Doctorado en Psicología','programme'),
            ('Rhodes Scholarship 2027','opening'),('Congratulations to Dr Ilaha Abasli on a successful PhD defence','noise'),('International Students','noise'),('Promotie Sybren Slimmen','noise'),('Ing. Matúš Dlugoš, PhD. - Vysoká škola','noise'),
            ('What Does a Civil Engineer Do?','noise'),('Career Opportunities After B.Tech in Mechanical Engineering','noise'),('Scholarships','info'),('Early career researchers: meet Dr Tania','noise')]:
    eq('kind '+t,X.kind_of_title(t),w)
eq('jobposting always opening',X.kind_of_title('Anything',has_jobposting=True),'opening')
# ---- text extraction
html='''<html><head><meta name="description" content="Fully funded PhD in sustainable timber construction at the Department of Architecture."/><meta name="keywords" content="timber, construction"/></head>
<body><nav>Home Menu International Students</nav><main><h1>PhD Position in Timber Construction</h1>
<p>The Department of Architecture at ETH Zurich invites applications for a doctoral position. Research areas: structural timber, circular building, digital fabrication.</p>
<p>Applicants must hold a master's degree in architecture or civil engineering. Good English (IELTS 6.5) is required. Deadline: 30 June 2027.</p></main><footer>cookie</footer></body></html>'''
soup=BeautifulSoup(html,'lxml');txt=X.main_text(soup)
eq('nav removed','International Students' in txt,False)
d=X.describe(soup,None,txt);eq('desc',d.startswith('Fully funded PhD'),True)
eq('req',('master' in X.requirements(txt).lower() and 'IELTS' in X.requirements(txt)),True)
rt=X.research_topics(soup,None,txt);eq('rt',('structural timber' in rt and 'Department of Architecture' in rt),True)
eq('page kind',X.kind_of_page('PhD Position in Timber Construction',txt,None,None),'opening')
eq('thin page',X.kind_of_page('Funding for students','Short text here.',None,None),'noise')
print('FAILED' if fails else 'all passed');[print(' ',f) for f in fails]
sys.exit(1 if fails else 0)
