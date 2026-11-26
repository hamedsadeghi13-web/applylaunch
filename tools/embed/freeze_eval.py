import sys,json,collections,numpy as np
R=sys.argv[1];sys.argv=[sys.argv[0],R,'/dev/null'];exec(open('analyze_dev.py').read().split('out={}')[0])
items=[i for i in D['opp']];X=np.array([feats(i,'opp') for i in items]);w=np.array([i['w'] for i in items]);fl=np.array([i['field'] for i in items]);use=np.array([i['stratum']!='S6b' for i in items])
def lofo(labfit,C=1.0):
    y=np.array([labels(i,labfit) for i in items]);s=np.zeros(len(items))
    for f in set(fl):
        tr=(fl!=f)&use;m=LogisticRegression(C=C,max_iter=3000).fit(X[tr],y[tr],sample_weight=w[tr]/w[tr].mean());s[fl==f]=m.predict_proba(X[fl==f])[:,1]
    return s
def band(p,edges):return sum(p<e for e in edges)    # 0 best
def wrank(ks,sc):
    out={}
    for k in ks:out[k]=sum(items[j]['w'] for j in ks if sc[j]>sc[k])+items[k]['w']/2
    return out
def demotion(sc_rule,sc_new,thr=100):
    mv=tot=0
    for f in set(fl):
        ks=[k for k in range(len(items)) if fl[k]==f and use[k]];r0=wrank(ks,sc_rule);r1=wrank(ks,sc_new)
        for k in ks:
            if labels(items[k],'rel') and r0[k]<=thr:tot+=items[k]['w'];mv+=items[k]['w']*(r1[k]>thr)
    return mv/tot if tot else None
sr=[rule(i['field'],i) for i in items]
for fit in('rel','real'):
    p=lofo(fit)
    for edges in([],[.65,.4,.2,.1]):
        sc=[-band(x,edges)*10+x*0.001 if edges else x for x in p]
        if edges:sc=[-band(x,edges) for x in p]
        print('fit',fit,'bands' if edges else 'continuous','rel',round(macro(items,sc,'rel'),3),'real',round(macro(items,sc,'real'),3),'demotion>100',round(demotion(sr,sc),3))
print('rule rel',round(macro(items,sr,'rel'),3),'real',round(macro(items,sr,'real'),3))
print('--- designs (fit=real) ---')
p=lofo('real');lg=np.log(np.clip(p,1e-6,1-1e-6)/(1-np.clip(p,1e-6,1-1e-6)))
def tierbonus(Bd,Br):return [lg[k]+Bd*(items[k]['rule_tier']=='direct')+Br*(items[k]['rule_tier']=='related') for k in range(len(items))]
for Bd,Br in((0,0),(2,1),(4,2),(6,3),(10,5)):
    sc=tierbonus(Bd,Br);print('tier bonus',Bd,Br,'rel',round(macro(items,sc,'rel'),3),'real',round(macro(items,sc,'real'),3),'demotion',round(demotion(sr,sc),3))
def merged_score(rho):
    sc=np.zeros(len(items))
    for f in set(fl):
        ks=[k for k in range(len(items)) if fl[k]==f and use[k]]
        L0=sorted(ks,key=lambda k:-sr[k]);L1=sorted(ks,key=lambda k:-lg[k]);seen=set();e0=e1=0;a=b=0;order=[]
        while len(order)<len(ks):
            pick1=(e1<rho/(1-rho)*e0) if rho<1 else True
            if pick1:
                while b<len(L1) and L1[b] in seen:b+=1
                if b<len(L1):k=L1[b];e1+=items[k]['w'];seen.add(k);order.append(k);continue
            while a<len(L0) and L0[a] in seen:a+=1
            if a<len(L0):k=L0[a];e0+=items[k]['w'];seen.add(k);order.append(k)
            else:
                while b<len(L1) and L1[b] in seen:b+=1
                k=L1[b];e1+=items[k]['w'];seen.add(k);order.append(k)
        for pos,k in enumerate(order):sc[k]=-pos
    for k in range(len(items)):
        if not use[k]:sc[k]=-1e9
    return list(sc)
for rho in(.1,.2,.3,.5):
    sc=merged_score(rho);print('merge rho',rho,'rel',round(macro(items,sc,'rel'),3),'real',round(macro(items,sc,'real'),3),'demotion',round(demotion(sr,sc),3))
