"""Metric code copied verbatim from gold/phase0_model_bench.py."""
import collections
def curve_recall(scores,rel,w,pstars=(.5,.6,.7)):
    order=sorted(range(len(scores)),key=lambda i:-scores[i]);R=sum(w[i]*rel[i] for i in range(len(w)))
    if R==0:return {p:None for p in pstars},None
    tp=fp=0;best={p:0.0 for p in pstars};ap=0;prev_r=0
    i=0
    while i<len(order):
        j=i
        while j<len(order) and scores[order[j]]==scores[order[i]]:j+=1   # ties together
        for k in order[i:j]:
            tp+=w[k]*rel[k];fp+=w[k]*(1-rel[k])
        pr=tp/(tp+fp);rc=tp/R
        for p in pstars:
            if pr>=p:best[p]=max(best[p],rc)
        ap+=pr*(rc-prev_r);prev_r=rc;i=j
    return best,ap
def evaluate(items,score_fn,label='rel',pstars=(.5,.6,.7)):
    by=collections.defaultdict(list)
    for it in items:
        if it['stratum']=='S6b':continue
        by[it['field']].append(it)
    res={};
    for f,L in by.items():
        rel=[1 if (it['labelA'] in 'DR' and (label=='rel' or it.get('opp')==1)) else 0 for it in L]
        sc=[score_fn(f,it) for it in L];w=[it['w'] for it in L]
        b,ap=curve_recall(sc,rel,w,pstars);res[f]={'recall_at_precision':b,'ap':ap,'n':len(L),'pos':sum(rel)}
    out={}
    for p in pstars:
        v=[r['recall_at_precision'][p] for r in res.values() if r['recall_at_precision'][p] is not None and r['pos']>=3]
        out[f'macro_recall@P{p}']=sum(v)/len(v) if v else None
    v=[r['ap'] for r in res.values() if r['ap'] is not None and r['pos']>=3];out['macro_AP']=sum(v)/len(v) if v else None
    return out,res
