#!/usr/bin/env python3
"""Phase 1 Dev analysis (Test set never touched). Usage: analyze_dev.py RESULTS_DIR OUT.json
Scores: rule tier / Affinity(z of the field's domain) / fusion (logistic regression, leave-one-field-out CV). Paired bootstrap CI on macro Recall@P0.5."""
import json,os,sys,random,collections
import numpy as np
from sklearn.linear_model import LogisticRegression
HERE=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,HERE)
from phase0 import evaluate,curve_recall   # copied metric code (identical to phase0_model_bench.py)
import affinity
F2D={'Architecture':'arch','Chemical Engineering':'chemeng','Civil Engineering':'civil','Computer Science':'cs','Economics':'econ','Electrical Engineering':'elec',
     'Environmental Engineering':'env','Law':'law','Mechanical Engineering':'mech','Medicine':'med','Psychology':'psych','Urban Planning':'urban'}
R=sys.argv[1];D=json.load(open(os.path.join(HERE,'gold','dev_eval.json')))
man=json.load(open(os.path.join(R,'affinity_manifest.json')));doms=man['domains']
A=affinity.from_u8(np.load(os.path.join(R,'affinity_opp.npy')));ids=json.load(open(os.path.join(R,'ids_opp.json')));pos={i:k for k,i in enumerate(ids)}
POS={p['id']:p for p in json.load(open(os.path.join(HERE,'..','..','docs','data','positions.json')))['positions']}
Pj=json.load(open(os.path.join(HERE,'..','..','docs','data','professors.json')));Pj=Pj.get('professors',Pj);PQ={q['id']:q for q in Pj}
AT=affinity.from_u8(np.load(os.path.join(R,'affinity_topic.npy')));topics={t:i for i,t in enumerate(json.load(open(os.path.join(R,'topics.json'))))}
AD=affinity.from_u8(np.load(os.path.join(R,'affinity_dept.npy')));depts={t:i for i,t in enumerate(json.load(open(os.path.join(R,'depts.json'))))}
TIERS=['direct','related','loose','unclassified',None];KINDS=['opening','programme','info','noise']
def aff_opp(it):return float(A[pos[it['id']],doms.index(F2D[it['field']])])
def aff_prof(it):   # pre-specified (not tuned): max over dept and topics, topic i penalised by 0.15*i
    q=PQ[it['id']];j=doms.index(F2D[it['field']]);v=[]
    d=' '.join((q.get('dept') or '').split())
    if d in depts:v.append(float(AD[depts[d],j]))
    for i,t in enumerate((q.get('topics') or [])[:8]):
        if t in topics:v.append(float(AT[topics[t],j])-0.15*i)
    return max(v) if v else -3.0
TIER={'direct':4,'related':3,'loose':2,'unclassified':1,None:0}
def rule(f,it):return TIER[it['rule_tier']]*1000-(it['rule_rank'] or 0) if it['rule_tier'] else 0
def feats(it,kind):
    a=(aff_opp if kind=='opp' else aff_prof)(it);x=[1.0*(it['rule_tier']==t) for t in TIERS[:4]]+[max(-3,min(4,a))]
    if kind=='opp':x+=[1.0*(POS[it['id']].get('kind')==k) for k in KINDS[:3]]
    return x
def labels(it,lab):return 1 if (it['labelA'] in 'DR' and (lab=='rel' or it.get('opp')==1)) else 0
def fusion_scores(items,kind,lab):
    X=np.array([feats(i,kind) for i in items]);y=np.array([labels(i,lab) for i in items]);w=np.array([i['w'] for i in items]);fl=np.array([i['field'] for i in items])
    use=np.array([i['stratum']!='S6b' for i in items]);s=np.zeros(len(items))
    for f in set(fl):
        tr=(fl!=f)&use;m=LogisticRegression(C=1.0,max_iter=2000).fit(X[tr],y[tr],sample_weight=w[tr]/w[tr].mean());te=fl==f;s[te]=m.decision_function(X[te])
    return s
def macro(items,sc,lab,p=.5):
    by=collections.defaultdict(list)
    for it,s in zip(items,sc):
        if it['stratum']!='S6b':by[it['field']].append((it,s))
    out=[]
    for f,L in by.items():
        rel=[labels(i,lab) for i,_ in L]
        if sum(rel)<3:continue
        b,_=curve_recall([s for _,s in L],rel,[i['w'] for i,_ in L],(p,));out.append(b[p] or 0)
    return float(np.mean(out))
def boot(items,sa,sb,lab,n=300,seed=1):
    rnd=random.Random(seed);cells=collections.defaultdict(list)
    for k,i in enumerate(items):cells[(i['field'],i['stratum'])].append(k)
    d=[]
    for _ in range(n):
        idx=[rnd.choice(v) for v in cells.values() for _ in v];sub=[items[k] for k in idx]
        d.append(macro(sub,[sb[k] for k in idx],lab)-macro(sub,[sa[k] for k in idx],lab))
    d=sorted(d);return d[int(.025*n)],d[int(.975*n)]
out={}
for kind,labs in (('opp',('rel','real')),('prof',('rel',))):
    items=[i for i in D[kind] if kind=='opp' or i['id'] in PQ];out[f'{kind}_n']=len(items)
    sr=[rule(i['field'],i) for i in items];sa=[(aff_opp if kind=='opp' else aff_prof)(i) for i in items]
    for lab in labs:
        sf=fusion_scores(items,kind,lab)
        # union: rule-direct/related first, then affinity breaks ties & rescues others (tier bonus 3 z-units per tier step)
        su=[TIER[i['rule_tier']]*3+a for i,a in zip(items,sa)]
        r={'rule':macro(items,sr,lab),'affinity':macro(items,sa,lab),'union_tier_plus_aff':macro(items,su,lab),'fusion_LOFO':macro(items,sf,lab)}
        r['delta_fusion_vs_rule_CI95']=boot(items,sr,sf,lab);r['delta_union_vs_rule_CI95']=boot(items,sr,su,lab);out[f'{kind}_{lab}']=r;print(kind,lab,json.dumps(r))
json.dump(out,open(sys.argv[2],'w'),indent=1)
