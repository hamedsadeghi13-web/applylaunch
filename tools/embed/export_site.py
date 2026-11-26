#!/usr/bin/env python3
"""Phase 2.0/2.1 - freeze the Fusion spec (fitted on Dev only) and write the NEW site files:
   docs/data/affinity.bin  = N uint32 ids (LE) + N*56 uint8 affinity (row-major)
   docs/data/affinity.json = manifest + frozen fusion spec
   docs/data/flags.json    = {"engine":"rule", ...}  (only created if missing)
Usage: export_site.py RESULTS_DIR [--docs ../../docs]"""
import sys,os,json,hashlib,struct,numpy as np
R=sys.argv[1];DOCS=os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','docs'))
sys.argv=[sys.argv[0],R,'/dev/null'];exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'analyze_dev.py')).read().split('out={}')[0])
items=D['opp'];use=[i for i in items if i['stratum']!='S6b']
X=np.array([feats(i,'opp') for i in use]);y=np.array([labels(i,'real') for i in use]);w=np.array([i['w'] for i in use])
m=LogisticRegression(C=1.0,max_iter=5000).fit(X,y,sample_weight=w/w.mean())
validated=sorted(set(F2D.values()))
fusion={'label_fitted':'real (relevant D/R and a concrete opportunity)','features':['t_direct','t_related','t_loose','t_unclassified','z','k_opening','k_programme','k_info'],
 'coef':[round(float(c),6) for c in m.coef_[0]],'intercept':round(float(m.intercept_[0]),6),'z_clip':[-3,4],
 'mix':0.1,'mix_note':'share of list slots taken by fusion order; the rest keeps the current order (structural bound on demotion)',
 'validated_domains':validated,'rescue':{'z_min':2.6,'kinds':['opening','programme'],'domains':[d for d in validated if d!='chemeng']},
 'fit':{'n':len(use),'source':'Dev gold only (tools/embed/gold/dev_eval.json); Test never used'}}
fusion['hash']=hashlib.sha256(json.dumps([fusion['coef'],fusion['intercept'],fusion['mix'],fusion['rescue']],sort_keys=True).encode()).hexdigest()[:16]
# BUG GUARD: validated_domains must contain only the 12 evaluated fields (chemeng is evaluated, but rescue is disabled for it)
U=np.load(os.path.join(R,'affinity_opp.npy'));ids=json.load(open(os.path.join(R,'ids_opp.json')));assert U.shape==(len(ids),56)
os.makedirs(os.path.join(DOCS,'data'),exist_ok=True)
with open(os.path.join(DOCS,'data','affinity.bin'),'wb') as f:
    f.write(np.array(ids,dtype='<u4').tobytes());f.write(U.astype(np.uint8).tobytes())
rm=json.load(open(os.path.join(R,'manifest.json')))
meta={'version':1,'n':len(ids),'nd':56,'domains':man['domains'],'relevance_version':2,'model':rm['model'],'revision':rm['revision'],'text_spec':rm['text_spec'],
      'encoding':'uint8 = clip(round(z*32+128),0,255); z = (cos-mean)/std with frozen stats','stats':man['stats'],'fusion':fusion}
json.dump(meta,open(os.path.join(DOCS,'data','affinity.json'),'w'),separators=(',',':'))
fp=os.path.join(DOCS,'data','flags.json')
if not os.path.exists(fp):json.dump({'engine':'rule','allowUrl':True,'note':"engine: 'rule' (current engine) or 'fusion'. allowUrl:false disables ?engine=fusion too."},open(fp,'w'),indent=1)
print('fusion hash',fusion['hash'],'coef',fusion['coef'],fusion['intercept']);print('bytes',os.path.getsize(os.path.join(DOCS,'data','affinity.bin')))
