#!/usr/bin/env python3
"""Dev: (3) precision of the top-K where K = weighted number of rule-direct items, rule vs fusion; (4) demotion of rule-direct items by Affinity."""
import sys,json,collections,numpy as np
sys.argv=[sys.argv[0],sys.argv[1],'/dev/null'];exec(open('analyze_dev.py').read().split('out={}')[0])
items=D['opp'];out={}
for lab in('rel','real'):
    sf=fusion_scores(items,'opp',lab);sa=[aff_opp(i) for i in items];by=collections.defaultdict(list)
    for k,i in enumerate(items):
        if i['stratum']!='S6b':by[i['field']].append(k)
    pr={'rule':[],'fusion':[],'affinity':[]}
    for f,ks in by.items():
        K=sum(items[k]['w'] for k in ks if items[k]['rule_tier']=='direct')
        for nm,sc in (('rule',[rule(f,items[k]) for k in ks]),('fusion',[sf[k] for k in ks]),('affinity',[sa[k] for k in ks])):
            o=sorted(range(len(ks)),key=lambda t:-sc[t]);cw=tp=0
            for t in o:
                w=items[ks[t]]['w'];cw+=w;tp+=w*labels(items[ks[t]],lab)
                if cw>=K:break
            pr[nm].append(tp/cw)
    out[f'topK_precision_{lab}']={k:float(np.mean(v)) for k,v in pr.items()}
# demotion: rule-direct items, relevant ones, sorted by Affinity within field: share of relevant direct items in the lowest 30% of Affinity
low=[];tot=0;lw=0
for f in {i['field'] for i in items}:
    d=[i for i in items if i['field']==f and i['rule_tier']=='direct' and i['stratum']!='S6b']
    if len(d)<6:continue
    a=np.array([aff_opp(i) for i in d]);thr=np.quantile(a,.3)
    for i,x in zip(d,a):
        if labels(i,'rel'):tot+=i['w'];lw+=i['w']*(x<=thr)
out['demotion_lowest30pct_affinity']={'share_of_relevant_direct_items_in_it':lw/tot}
d=[i for i in items if i['rule_tier']=='direct' and i['stratum']!='S6b'];w=sum(i['w'] for i in d)
out['direct_tier']={'precision_rel':sum(i['w']*labels(i,'rel') for i in d)/w,'precision_real':sum(i['w']*labels(i,'real') for i in d)/w,'n':len(d)}
print(json.dumps(out,indent=1))
