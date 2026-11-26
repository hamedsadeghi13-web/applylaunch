#!/usr/bin/env python3
"""Phase 1 - build embeddings (offline / GitHub Actions only; nothing here is loaded by the website).
  python3 tools/embed/embed.py --data docs/data --out OUT [--cache OUT/cache.npz] [--embedder st|stub] [--limit N]
Outputs (in OUT): emb_opp.npy (float16, N x 384), ids_opp.json, emb_topic.npy + topics.json, emb_dept.npy + depts.json,
                  emb_proto.npy + proto_index.json, manifest.json, cache.npz (hash -> vector; for incremental runs)."""
import argparse,json,os,sys,time,resource,platform
import numpy as np
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import spec
def load_data(d,limit=0):
    P=json.load(open(os.path.join(d,'positions.json')))['positions'];T=json.load(open(os.path.join(d,'text.json')))['text']
    Q=json.load(open(os.path.join(d,'professors.json')));Q=Q.get('professors',Q)
    if limit:P=P[:limit];Q=Q[:limit]
    return P,T,Q
class StubEmbedder:
    """Deterministic hashing bag-of-words embedder - ONLY to test plumbing (shapes, cache, quantisation). Carries no quality information."""
    dim=384
    def __init__(self):self.revision='stub'
    def encode(self,texts):
        import re,zlib
        out=np.zeros((len(texts),self.dim),dtype=np.float32)
        for i,t in enumerate(texts):
            for w in re.findall(r'\w+',t.lower()):out[i,zlib.crc32(w.encode())%self.dim]+=1
            n=np.linalg.norm(out[i]);out[i]/=n if n else 1
        return out
class STEmbedder:
    def __init__(self,model=spec.MODEL,revision=None):
        from sentence_transformers import SentenceTransformer
        if not revision:
            try:
                from huggingface_hub import HfApi;revision=HfApi().model_info(model).sha
            except Exception:revision=None
        kw={'revision':revision} if revision else {}
        self.m=SentenceTransformer(model,device='cpu',**kw);self.m.max_seq_length=spec.MAX_SEQ
        self.revision=revision or ''
        self.dim=self.m.get_sentence_embedding_dimension()
    def encode(self,texts):
        return self.m.encode(texts,batch_size=64,normalize_embeddings=True,show_progress_bar=False,convert_to_numpy=True)
def load_cache(path):
    if path and os.path.exists(path):
        z=np.load(path,allow_pickle=False);return dict(zip(z['keys'].tolist(),z['vecs']))
    return {}
def save_cache(path,c):
    if not path:return
    ks=list(c);np.savez(path,keys=np.array(ks),vecs=np.stack([c[k] for k in ks]).astype(np.float16) if ks else np.zeros((0,384),np.float16))
def embed_texts(emb,texts,cache,stats):
    keys=[spec.key(t,spec.MODEL,emb.revision) for t in texts];todo={}
    for k,t in zip(keys,texts):
        if k not in cache and k not in todo:todo[k]=t
    stats['computed']=stats.get('computed',0)+len(todo);stats['reused']=stats.get('reused',0)+len(keys)-len(todo)
    if todo:
        ks=list(todo);V=emb.encode([todo[k] for k in ks])
        for k,v in zip(ks,V):cache[k]=v.astype(np.float16)
    return np.stack([cache[k] for k in keys]).astype(np.float16)
def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--data',default='docs/data');ap.add_argument('--out',required=True);ap.add_argument('--cache',default='')
    ap.add_argument('--embedder',default='st');ap.add_argument('--revision',default='');ap.add_argument('--limit',type=int,default=0);ap.add_argument('--prof-only',action='store_true');a=ap.parse_args(argv)
    os.makedirs(a.out,exist_ok=True);t0=time.time()
    P,T,Q=load_data(a.data,a.limit)
    emb=StubEmbedder() if a.embedder=='stub' else STEmbedder(revision=a.revision or None)
    cache=load_cache(a.cache or None);st={};tm={}
    proto=json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'prototypes.json')))['domains']
    pidx=[];ptxt=[]
    for d,v in proto.items():
        for s in v['seeds']:pidx.append(d);ptxt.append(s)
    def step(name,fn):
        t=time.time();r=fn();tm[name]=round(time.time()-t,1);return r
    E_proto=step('proto',lambda:embed_texts(emb,ptxt,cache,st))
    if a.prof_only:
        E_prof=embed_texts(emb,[spec.prof_text(q) for q in Q],cache,st);np.save(os.path.join(a.out,'emb_prof.npy'),E_prof);json.dump([q['id'] for q in Q],open(os.path.join(a.out,'ids_prof.json'),'w'))
        np.save(os.path.join(a.out,'emb_proto.npy'),E_proto);json.dump(pidx,open(os.path.join(a.out,'proto_index.json'),'w'))
        json.dump({'revision':emb.revision,'n':len(Q),'seconds':round(time.time()-t0,1),'peak_rss_MB':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),'text_spec':spec.TEXT_SPEC},open(os.path.join(a.out,'manifest_prof.json'),'w'));return
    topics=sorted({t for q in Q for t in (q.get('topics') or [])});depts=sorted({spec.clean(q.get('dept')) for q in Q if q.get('dept')})
    E_topic=step('topics',lambda:embed_texts(emb,topics,cache,st));E_dept=step('depts',lambda:embed_texts(emb,depts,cache,st))
    ids=[p['id'] for p in P];texts=[spec.opp_text(p,T.get(str(p['id']))) for p in P]
    E_opp=step('opps',lambda:embed_texts(emb,texts,cache,st))
    np.save(os.path.join(a.out,'emb_opp.npy'),E_opp);json.dump(ids,open(os.path.join(a.out,'ids_opp.json'),'w'))
    np.save(os.path.join(a.out,'emb_topic.npy'),E_topic);json.dump(topics,open(os.path.join(a.out,'topics.json'),'w'),ensure_ascii=False)
    np.save(os.path.join(a.out,'emb_dept.npy'),E_dept);json.dump(depts,open(os.path.join(a.out,'depts.json'),'w'),ensure_ascii=False)
    np.save(os.path.join(a.out,'emb_proto.npy'),E_proto);json.dump(pidx,open(os.path.join(a.out,'proto_index.json'),'w'))
    save_cache(a.cache or None,cache)
    nt=sum(len(t) for t in texts)
    man={'model':spec.MODEL,'revision':emb.revision,'text_spec':spec.TEXT_SPEC,'max_seq':spec.MAX_SEQ,'dim':int(E_opp.shape[1]),'embedder':a.embedder,
         'counts':{'opps':len(ids),'topics':len(topics),'depts':len(depts),'seeds':len(ptxt)},'cache':st,'seconds':tm,'total_seconds':round(time.time()-t0,1),
         'sec_per_1000_opps':round(tm['opps']/max(1,len(ids))*1000,1) if tm.get('opps') else None,'peak_rss_MB':round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024),
         'avg_chars':round(nt/max(1,len(texts))),'python':platform.python_version(),'platform':platform.platform()}
    try:
        import sentence_transformers,torch;man['versions']={'sentence_transformers':sentence_transformers.__version__,'torch':torch.__version__,'numpy':np.__version__}
    except Exception:pass
    json.dump(man,open(os.path.join(a.out,'manifest.json'),'w'),indent=1);print(json.dumps(man,indent=1))
if __name__=='__main__':main()
