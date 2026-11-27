"""Logic tests for tools/embed/refresh.py with the STUB embedder (no model, no network): incremental update, text change, pruning, idempotence, abort guards."""
import sys,os,json,shutil,tempfile,numpy as np
ROOT=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..');sys.path.insert(0,os.path.join(ROOT,'tools','embed'))
import refresh
ok=lambda n,c:(print(('ok   ' if c else 'FAIL ')+n),c or sys.exit(1))
d=tempfile.mkdtemp();D=os.path.join(d,'docs','data');os.makedirs(D);S=os.path.join(d,'state')
real=json.load(open(os.path.join(ROOT,'docs','data','affinity.json')))
meta={k:real[k] for k in ('version','nd','domains','relevance_version','model','text_spec','stats','fusion')};meta.update(n=0,revision='stub');json.dump(meta,open(os.path.join(D,'affinity.json'),'w'))
def pos(i,title):return {'id':i,'title':title,'type':'PhD','kind':'opening','topics':'','cc':'DE'}
P=[pos(1000+i,f'PhD in topic {i} architecture') for i in range(60)];T={str(p['id']):['desc %d'%p['id'],'','rt'] for p in P}
def save():json.dump({'positions':P},open(os.path.join(D,'positions.json'),'w'));json.dump({'text':T},open(os.path.join(D,'text.json'),'w'))
def prof():json.dump({'professors':[]},open(os.path.join(D,'professors.json'),'w'))
def rd():
    m=json.load(open(os.path.join(D,'affinity.json')));b=open(os.path.join(D,'affinity.bin'),'rb').read();n=m['n'];assert len(b)==n*4+n*56
    return m,np.frombuffer(b[:n*4],'<u4').tolist(),np.frombuffer(b[n*4:],np.uint8).reshape(n,56)
run=lambda:refresh.main(['--docs',os.path.join(d,'docs'),'--state',S,'--embedder','stub'])
save();prof();r=run();m,ids,U=rd();ok('first run builds a row for every record',r['changed'] and m['n']==60 and ids==[p['id'] for p in P])
r=run();ok('second run with nothing new changes nothing',r['changed'] is False)
U1=U.copy();P+= [pos(2000+i,f'MSc law {i}') for i in range(5)];save();r=run();m,ids,U=rd()
ok('only the 5 new records are computed',r['new']==5 and r['recomputed']==0 and m['n']==65)
ok('existing rows are byte-identical',np.array_equal(U[:60],U1))
T[str(P[3]['id'])][0]='completely different description about robotics';save();r=run();m,ids,U2=rd()
ok('a changed text recomputes exactly that row',r['recomputed']==1 and r['new']==0 and not np.array_equal(U2[3],U[3]) and np.array_equal(np.delete(U2,3,0),np.delete(U,3,0)))
P=P[:62];save();r=run();m,ids,U3=rd();ok('removed records are pruned (rows follow positions order)',m['n']==62 and ids==[p['id'] for p in P] and np.array_equal(U3,U2[:62]))
P=P[:10];save()
try:run();ok('shrink guard aborts',False)
except SystemExit as e:ok('shrink guard aborts (nothing written)',m['n']==62 and rd()[0]['n']==62)
meta2=json.load(open(os.path.join(D,'affinity.json')));meta2['text_spec']='v0';json.dump(meta2,open(os.path.join(D,'affinity.json'),'w'))
try:run();ok('spec mismatch aborts',False)
except AssertionError:ok('text-spec mismatch aborts',True)
print('all passed')
