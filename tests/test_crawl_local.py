"""python3 tests/test_crawl_local.py - end to end on a local fixture site: analyse() of a posting, enrich_one() of a stored record, news page rejected."""
import sys,os,threading,tempfile,http.server,socketserver,functools,json,datetime as dt
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','crawler'))
import crawl
d=tempfile.mkdtemp()
dl=(dt.date.today()+dt.timedelta(days=60)).strftime('%d %B %Y')
open(os.path.join(d,'phd.html'),'w').write(f'''<html><head><title>x</title><meta name="description" content="Funded doctoral position on timber structures at the Department of Architecture."/></head><body><nav>International Students | Careers</nav>
<main><h1>PhD Position in Timber Structures (m/f/d)</h1><p>The Department of Architecture invites applications for a doctoral researcher. Research areas: structural timber, circular building, digital fabrication.</p>
<p>Applicants must hold a master's degree in architecture or civil engineering. IELTS 6.5 is required. Salary according to TV-L E13. Application deadline: {dl}. Apply now via the portal.</p></main><footer>cookie banner</footer></body></html>''')
open(os.path.join(d,'news.html'),'w').write('<html><body><main><h1>Congratulations to Dr Lee on a successful PhD defence</h1><p>'+'We celebrate. '*30+'</p></main></body></html>')
open(os.path.join(d,'intl.html'),'w').write('<html><body><main><h1>International Students</h1><p>'+'Welcome to our international office. '*20+'</p></main></body></html>')
H=functools.partial(http.server.SimpleHTTPRequestHandler,directory=d)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a):pass
srv=socketserver.TCPServer(('127.0.0.1',0),functools.partial(Q,directory=d));port=srv.server_address[1]
threading.Thread(target=srv.serve_forever,daemon=True).start()
F=crawl.Fetcher(delay=0.0)
src={'id':'t','name':'Test University','type':'university','country':'Germany','cc':'DE'}
fails=[]
def chk(n,c):
    if not c:fails.append(n)
html,_,final=F.get(f'http://127.0.0.1:{port}/phd.html')
rec,why=crawl.analyse(final,html,src,'Test University')
chk('posting accepted: '+why,rec is not None)
if rec:
    chk('type PhD',rec['type']=='PhD');chk('kind opening',rec['kind']=='opening')
    chk('desc from page','timber' in rec['desc'].lower());chk('req has master+IELTS','master' in rec['req'].lower() and 'IELTS' in rec['req'])
    chk('rt has department + areas','Department of Architecture' in rec['rt'] and 'structural timber' in rec['rt'])
    chk('nav text not in description','International Students' not in rec['desc'])
for name in ('news.html','intl.html'):
    html,_,final=F.get(f'http://127.0.0.1:{port}/{name}')
    r,why=crawl.analyse(final,html,src,'Test University');chk(name+' rejected ('+why+')',r is None)
# enrichment of a stored record that has no page text
stored={'title':'PhD Position in Timber Structures (m/f/d)','type':'Other','kind':'info','ks':'t','url':f'http://127.0.0.1:{port}/phd.html','deadline':None}
crawl.enrich_one(stored,F)
chk('enriched desc','timber' in stored['desc'].lower());chk('enriched kind opening',stored['kind']=='opening' and stored['ks']=='p');chk('typed from page title',stored['type']=='PhD')
# retype_stored: no 'intern' for international
pos={'a':{'title':'International Students','type':'Internship'},'b':{'title':'Internship – Data Team','type':'Internship'},'c':{'title':'Researcher (m/f/d) Materials','type':'Research job'},'d':{'title':'Careers and Internships','type':'Research job'}}
crawl.retype_stored(pos)
chk('international is not an internship',pos['a']['type']=='Other' and pos['a']['kind']=='noise')
chk('real internship stays',pos['b']['type']=='Internship' and pos['b']['kind']=='opening')
chk('real research job stays',pos['c']['type']=='Research job')
print('FAILED: '+', '.join(fails) if fails else 'all passed');sys.exit(1 if fails else 0)
