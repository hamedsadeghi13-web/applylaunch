#!/usr/bin/env python3
"""Incremental, fully automatic refresh of docs/data/affinity.{bin,json}.
 - rows exist for every record in positions.json (new ones are added, removed ones pruned),
 - a row is recomputed when the record's embedding text changed (crc32 kept in tools/embed/state/affinity.crc, NOT published),
 - model revision, text spec and normalisation statistics are FROZEN (read from affinity.json); a mismatch aborts without writing,
 - sanity checks abort (non-zero exit, nothing written) instead of shipping a bad file; the site falls back to the rule engine for rows it does not have.
Usage: refresh.py [--docs docs] [--state tools/embed/state] [--embedder st|stub]"""
import argparse,json,os,sys,time,zlib
import numpy as np
HERE=os.path.dirname(os.path.abspath(__file__));sys.path.insert(0,HERE)
import spec,affinity,embed
def main(argv=None):
    ap=argparse.ArgumentParser();ap.add_argument('--docs',default=os.path.join(HERE,'..','..','docs'));ap.add_argument('--state',default=os.path.join(HERE,'state'));ap.add_argument('--embedder',default='st');a=ap.parse_args(argv)
    D=os.path.join(a.docs,'data');binp,jsp,crcp=os.path.join(D,'affinity.bin'),os.path.join(D,'affinity.json'),os.path.join(a.state,'affinity.crc')
    meta=json.load(open(jsp));nd=meta['nd'];assert meta['version']==1 and meta['text_spec']==spec.TEXT_SPEC,'text spec / format changed - rebuild with a new freeze'
    P,T,_=embed.load_data(D);ids=[p['id'] for p in P];assert len(set(ids))==len(ids)
    texts=[spec.opp_text(p,T.get(str(p['id']))) for p in P];crc=np.array([zlib.crc32(t.encode())&0xffffffff for t in texts],dtype='<u4')
    old_ids=np.frombuffer(open(binp,'rb').read(meta['n']*4),dtype='<u4').tolist() if os.path.exists(binp) and meta['n'] else []
    oldU=np.frombuffer(open(binp,'rb').read(),dtype=np.uint8,offset=meta['n']*4).reshape(meta['n'],nd) if old_ids else np.zeros((0,nd),np.uint8)
    oldcrc=np.fromfile(crcp,dtype='<u4') if os.path.exists(crcp) else None
    if oldcrc is not None and len(oldcrc)!=len(old_ids):oldcrc=None
    if old_ids and len(ids)<0.9*len(old_ids):sys.exit(f'ABORT: positions shrank {len(old_ids)} -> {len(ids)}; not touching the affinity files')
    rowof={i:k for k,i in enumerate(old_ids)}
    need=[k for k,i in enumerate(ids) if i not in rowof or oldcrc is None or oldcrc[rowof[i]]!=crc[k]]
    if not need and ids==old_ids and oldcrc is not None:print('up to date',len(ids));return {'changed':False,'n':len(ids)}
    st={'new':sum(1 for k in need if ids[k] not in rowof),'recomputed':sum(1 for k in need if ids[k] in rowof),'pruned':len(set(old_ids)-set(ids))}
    t0=time.time();newU=np.zeros((0,nd),np.uint8)
    if need:
        emb=embed.StubEmbedder() if a.embedder=='stub' else embed.STEmbedder(revision=meta['revision'])
        if a.embedder!='stub':assert emb.revision==meta['revision'],f"model revision {emb.revision} != frozen {meta['revision']}"
        else:assert meta['revision']=='stub'
        proto=json.load(open(os.path.join(HERE,'prototypes.json')))['domains'];pidx=[];ptxt=[]
        for d,v in proto.items():
            for s in v['seeds']:pidx.append(d);ptxt.append(s)
        cache={};c={}
        Ep=embed.embed_texts(emb,ptxt,cache,c);E=embed.embed_texts(emb,[texts[k] for k in need],cache,c)
        Rr,doms=affinity.domain_sims(E,Ep,pidx);assert doms==meta['domains'];newU=affinity.to_u8(affinity.zscore(Rr,meta['stats']))
        # --- sanity checks (abort, never ship) ---
        assert newU.shape==(len(need),nd)
        if len(need)>=200:
            Z=affinity.from_u8(newU);mu,sd=Z.mean(axis=0),Z.std(axis=0)
            assert np.all(np.abs(mu)<0.7) and np.all(sd>0.4) and np.all(sd<2.0),f'new-row distribution drifted (mean {mu.min():.2f}..{mu.max():.2f}, std {sd.min():.2f}..{sd.max():.2f})'
        same=[(j,rowof[ids[k]]) for j,k in enumerate(need) if ids[k] in rowof]
        if len(same)>=50:   # reproducibility: re-embedding existing records must give (nearly) the same rows
            d=np.abs(affinity.from_u8(newU[[j for j,_ in same]])-affinity.from_u8(oldU[[r for _,r in same]]));assert np.median(d)<0.15,f'old vs re-embedded rows differ (median |dz|={np.median(d):.3f}) - model/environment changed?'
            st['median_abs_dz_vs_old']=round(float(np.median(d)),4)
    pos_new={ids[k]:j for j,k in enumerate(need)};U=np.zeros((len(ids),nd),np.uint8)
    for k,i in enumerate(ids):U[k]=newU[pos_new[i]] if i in pos_new else oldU[rowof[i]]
    os.makedirs(a.state,exist_ok=True);tmp=binp+'.tmp'
    with open(tmp,'wb') as f:f.write(np.array(ids,dtype='<u4').tobytes());f.write(U.tobytes())
    meta['n']=len(ids);meta['updated']=time.strftime('%Y-%m-%dT%H:%MZ',time.gmtime())
    json.dump(meta,open(jsp+'.tmp','w'),separators=(',',':'));crc.tofile(crcp)
    os.replace(tmp,binp);os.replace(jsp+'.tmp',jsp)
    st.update(changed=True,n=len(ids),seconds=round(time.time()-t0,1));print(json.dumps(st));return st
if __name__=='__main__':main()
