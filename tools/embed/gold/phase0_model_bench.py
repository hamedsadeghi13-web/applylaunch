#!/usr/bin/env python3
"""ApplyLaunch Phase 0 - embedding model benchmark on the DEV gold (test set is NOT used).
Usage:  pip install sentence-transformers numpy
        python3 phase0_model_bench.py dev_eval.json --models e5 minilm bgem3 --out results.json
        python3 phase0_model_bench.py dev_eval.json --reference     # no model: rule-tier / lexical reference curves only
Metric: per field, weighted precision-recall curve (weights = stratum population / sampled count, S6b excluded),
        recall at fixed precision P* in {0.5,0.6,0.7} (best recall among thresholds with precision >= P*), macro-averaged over fields.
"""
import json,sys,time,re,argparse,collections,os,resource
MODELS={'e5':('intfloat/multilingual-e5-small','query: ','passage: '),
        'minilm':('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2','',''),
        'bgem3':('BAAI/bge-m3','','')}
XL={'Architecture':['معماری','mimarlık','Architektur'],'Civil Engineering':['مهندسی عمران','inşaat mühendisliği','Bauingenieurwesen'],
    'Computer Science':['علوم کامپیوتر','bilgisayar bilimi','Informatik'],'Psychology':['روانشناسی','psikoloji','Psychologie'],
    'Law':['حقوق','hukuk','Rechtswissenschaft'],'Mechanical Engineering':['مهندسی مکانیک','makine mühendisliği','Maschinenbau']}
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
TIER={'direct':4,'related':3,'loose':2,'unclassified':1,None:0}
def rule_score(f,it):return TIER[it['rule_tier']]*1000-(it['rule_rank'] or 0) if it['rule_tier'] else 0
def lex_score(f,it):
    q=set(re.findall(r'\w+',f.lower()));t=re.findall(r'\w+',it['text'].lower());return sum(1 for w in t if w in q)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('data');ap.add_argument('--models',nargs='*',default=[]);ap.add_argument('--out',default='results.json');ap.add_argument('--reference',action='store_true')
    a=ap.parse_args();D=json.load(open(a.data));out={}
    for kind in ['opp','prof']:
        items=D[kind];labels=['rel','real'] if kind=='opp' else ['rel']
        for lab in labels:
            out[f'{kind}_{lab}_rule_tier']=evaluate(items,rule_score,lab)[0]
            out[f'{kind}_{lab}_lexical_overlap']=evaluate(items,lex_score,lab)[0]
    if a.reference:
        print(json.dumps(out,indent=1));json.dump(out,open(a.out,'w'),indent=1);return
    import numpy as np
    from sentence_transformers import SentenceTransformer
    for m in a.models:
        name,qp,pp=MODELS[m];t0=time.time();model=SentenceTransformer(name,device='cpu');load_s=time.time()-t0
        size=sum(os.path.getsize(os.path.join(dp,f)) for dp,_,fs in os.walk(model._first_module().auto_model.config._name_or_path) for f in fs) if os.path.isdir(model._first_module().auto_model.config._name_or_path) else None
        r={'model':name,'load_s':load_s,'model_dir_bytes':size}
        texts=[pp+it['text'] for k in ('opp','prof') for it in D[k]]
        # timing on 1000 records (cycled if fewer), single process, CPU
        sample=(texts*((1000//len(texts))+1))[:1000];t0=time.time();model.encode(sample,batch_size=32,normalize_embeddings=True,show_progress_bar=False);r['sec_per_1000']=time.time()-t0
        r['peak_rss_MB']=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024
        emb={};
        for k in ('opp','prof'):
            E=model.encode([pp+it['text'] for it in D[k]],batch_size=32,normalize_embeddings=True,show_progress_bar=False)
            emb[k]=E
        fields=sorted({it['field'] for k in D for it in D[k]});Qe={f:model.encode([qp+f],normalize_embeddings=True)[0] for f in fields}
        for k in ('opp','prof'):
            idx={id(it):i for i,it in enumerate(D[k])}
            fn=lambda f,it,k=k,idx=idx:float(emb[k][idx[id(it)]]@Qe[f])
            for lab in (['rel','real'] if k=='opp' else ['rel']):
                r[f'{k}_{lab}']=evaluate(D[k],fn,lab)[0]
        # cross-lingual probe: non-English query vs English-dominant dev texts
        probe={}
        for f,qs in XL.items():
            for qq in qs:
                qe=model.encode([qp+qq],normalize_embeddings=True)[0]
                items=[it for it in D['opp'] if it['field']==f and it['stratum']!='S6b']
                idx={id(it):i for i,it in enumerate(D['opp'])}
                fn2=lambda f_,it:float(emb['opp'][idx[id(it)]]@qe)
                o=evaluate(items,fn2,'rel')[0];probe[f'{f}|{qq}']=o.get('macro_recall@P0.5')
        r['crosslingual_recall@P0.5']=probe;out[m]=r;print(m,json.dumps(r,indent=1)[:1500])
    json.dump(out,open(a.out,'w'),indent=1)
if __name__=='__main__':main()
