#!/usr/bin/env python3
"""Phase 2.3 - evaluate the FROZEN fusion design (affinity.json) on a labelled item list.  items.json: list of
{field,id,stratum,w,rule_tier,rule_rank,labelA,opp,kind}. Usage: eval_final.py items.json RESULTS_DIR OUT.json
No parameter is fitted here. Design = merge(rule order, fusion order, mix=spec.mix) in weighted-rank space (the sample analogue of FUS.merge)."""
import sys,json,random,collections,numpy as np
HERE=__import__('os').path.dirname(__import__('os').path.abspath(__file__));sys.path.insert(0,HERE)
from phase0 import curve_recall
import affinity
items=json.load(open(sys.argv[1]));R=sys.argv[2];M=json.load(open(HERE+'/../../docs/data/affinity.json'));SP=M['fusion']
F2D={'Architecture':'arch','Chemical Engineering':'chemeng','Civil Engineering':'civil','Computer Science':'cs','Economics':'econ','Electrical Engineering':'elec','Environmental Engineering':'env','Law':'law','Mechanical Engineering':'mech','Medicine':'med','Psychology':'psych','Urban Planning':'urban'}
doms=M['domains'];A=affinity.from_u8(np.load(R+'/affinity_opp.npy'));ids=json.load(open(R+'/ids_opp.json'));pos={i:k for k,i in enumerate(ids)}
TIERS=['direct','related','loose','unclassified'];KINDS=['opening','programme','info']
def logit(it):
    k=pos.get(int(it['id']))
    if k is None or it['kind']=='noise':return -np.inf
    z=float(A[k,doms.index(F2D[it['field']])]);z=max(SP['z_clip'][0],min(SP['z_clip'][1],z))
    x=[1.0*(it['rule_tier']==t) for t in TIERS]+[z]+[1.0*(it['kind']==kk) for kk in KINDS]
    return SP['intercept']+sum(c*v for c,v in zip(SP['coef'],x))
for it in items:it['fs']=logit(it)
use=[i for i in items if i['stratum']!='S6b'];TIER={'direct':4,'related':3,'loose':2,'unclassified':1,None:0}
rs=lambda it:TIER[it['rule_tier']]*1000-(it['rule_rank'] or 0) if it['rule_tier'] else 0
lab=lambda it,l:1 if (it['labelA'] in 'DR' and (l=='rel' or it.get('opp')==1)) else 0
def merged(ks,mix):
    ratio=mix/(1-mix);L0=sorted(ks,key=lambda k:-rs(use[k]));L1=[k for k in sorted(ks,key=lambda k:-use[k]['fs']) if use[k]['fs']>-np.inf]
    seen=set();e0=e1=0;a=b=0;order=[]
    while len(order)<len(ks):
        while b<len(L1) and L1[b] in seen:b+=1
        while a<len(L0) and L0[a] in seen:a+=1
        if b<len(L1) and (e1<ratio*e0 or a>=len(L0)):k=L1[b];e1+=use[k]['w'];seen.add(k);order.append(k)
        else:k=L0[a];e0+=use[k]['w'];seen.add(k);order.append(k)
    return order
by=collections.defaultdict(list)
for k,i in enumerate(use):by[i['field']].append(k)
S={'rule':np.zeros(len(use)),'merged':np.zeros(len(use)),'fusion_continuous':np.array([i['fs'] if i['fs']>-np.inf else -1e9 for i in use])}
for f,ks in by.items():
    for k in ks:S['rule'][k]=rs(use[k])
    for pos_,k in enumerate(merged(ks,SP['mix'])):S['merged'][k]=-pos_
def macro(idx,sc,l,p=.5):
    out=[]
    for f,ks in by.items():
        kk=[k for k in ks if k in idx];rel=[lab(use[k],l) for k in kk]
        if sum(rel)<3:continue
        b,_=curve_recall([sc[k] for k in kk],rel,[use[k]['w'] for k in kk],(p,));out.append(b[p] or 0)
    return float(np.mean(out)) if out else None
def wrank(ks,sc):return {k:sum(use[j]['w'] for j in ks if sc[j]>sc[k])+use[k]['w']/2 for k in ks}
def demotion(sc):
    mv=tot=0
    for f,ks in by.items():
        r0=wrank(ks,S['rule']);r1=wrank(ks,sc)
        for k in ks:
            if lab(use[k],'rel') and r0[k]<=100:tot+=use[k]['w'];mv+=use[k]['w']*(r1[k]>100)
    return mv/tot if tot else None
def topk(sc,l):
    out=[]
    for f,ks in by.items():
        K=sum(use[k]['w'] for k in ks if use[k]['rule_tier']=='direct')
        if not K:continue
        cw=tp=0
        for k in sorted(ks,key=lambda k:-sc[k]):
            cw+=use[k]['w'];tp+=use[k]['w']*lab(use[k],l)
            if cw>=K:break
        out.append(tp/cw)
    return float(np.mean(out))
cells=collections.defaultdict(list)
for k,i in enumerate(use):cells[(i['field'],i['stratum'])].append(k)
def boot(a,b,l,n=1000):
    rnd=random.Random(5);d=[]
    for _ in range(n):
        idx=[rnd.choice(v) for v in cells.values() for _ in v];cnt=collections.Counter(idx);w0=[use[k]['w'] for k in range(len(use))]
        # resample by re-weighting: duplicate items = multiple copies; implement through weight multiplication
        for k in range(len(use)):use[k]['w']=w0[k]*cnt.get(k,0)
        sel=set(k for k in cnt);d.append(macro(sel,S[b],l)-macro(sel,S[a],l))
        for k in range(len(use)):use[k]['w']=w0[k]
    d=sorted(x for x in d if x==x);return [d[int(.025*len(d))],d[int(.975*len(d))]]
allk=set(range(len(use)));out={'n_items':len(items),'n_eval':len(use),'missing_affinity':sum(1 for i in items if i['fs']==-np.inf and i['kind']!='noise')}
for l in('rel','real'):
    out[l]={nm:macro(allk,S[nm],l) for nm in S}
    out[l]['delta_merged_vs_rule_CI95']=boot('rule','merged',l);out[l]['delta_cont_vs_rule_CI95']=boot('rule','fusion_continuous',l)
    out[l]['topK_precision']={nm:topk(S[nm],l) for nm in S}
out['demotion_rule_top100_relevant_leaving']={nm:demotion(S[nm]) for nm in ('merged','fusion_continuous')}
d=[i for i in use if i['rule_tier']=='direct'];w=sum(i['w'] for i in d);out['direct_tier_precision']={'rel':sum(i['w']*lab(i,'rel') for i in d)/w,'real':sum(i['w']*lab(i,'real') for i in d)/w,'n':len(d)}
json.dump(out,open(sys.argv[3],'w'),indent=1);print(json.dumps(out,indent=1))
