"""Plumbing tests for tools/embed with the STUB embedder (no model, no network). They test shapes, cache reuse, quantisation and that the
prototype file is complete - they say nothing about embedding quality."""
import sys,os,json,tempfile,numpy as np
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','tools','embed'))
import embed,affinity,spec
ok=lambda n,c:(print(('ok   ' if c else 'FAIL ')+n),c or sys.exit(1))
proto=json.load(open(os.path.join(os.path.dirname(__file__),'..','tools','embed','prototypes.json')))['domains']
ok('56 domains with seeds',len(proto)==56 and all(len(v['seeds'])>=4 for v in proto.values()))
ok('seeds are plain strings',all(isinstance(s,str) and s for v in proto.values() for s in v['seeds']))
d=tempfile.mkdtemp();out=os.path.join(d,'o');cache=os.path.join(d,'c.npz')
dat=os.path.join(os.path.dirname(__file__),'..','docs','data')
embed.main(['--data',dat,'--out',out,'--cache',cache,'--embedder','stub','--limit','300'])
m=json.load(open(os.path.join(out,'manifest.json')))
E=np.load(os.path.join(out,'emb_opp.npy'));ids=json.load(open(os.path.join(out,'ids_opp.json')))
ok('shape matches ids',E.shape==(len(ids),384) and E.dtype==np.float16 and len(ids)==300)
ok('no university name in text',spec.opp_text({'title':'PhD in X','type':'PhD','inst':'MIT'})=='PhD in X. PhD')
ok('requirements not in text','IELTS' not in spec.opp_text({'title':'T'},['desc','IELTS 6.5 required','rt']))
out2=os.path.join(d,'o2');embed.main(['--data',dat,'--out',out2,'--cache',cache,'--embedder','stub','--limit','300'])
m2=json.load(open(os.path.join(out2,'manifest.json')))
ok('second run reuses cache (nothing recomputed)',m2['cache']['computed']==0 and m2['cache']['reused']>0)
ok('identical embeddings from cache',np.array_equal(E,np.load(os.path.join(out2,'emb_opp.npy'))))
Ep=np.load(os.path.join(out,'emb_proto.npy'));pidx=json.load(open(os.path.join(out,'proto_index.json')))
R,doms=affinity.domain_sims(E,Ep,pidx);ok('affinity shape n x 56',R.shape==(300,56) and len(doms)==56)
st=affinity.fit_stats(R);U=affinity.to_u8(affinity.zscore(R,st))
ok('uint8 quantisation range',U.dtype==np.uint8 and U.shape==R.shape)
Z=affinity.zscore(R,st);ok('dequantised z within 1/64 of z (inside clip range)',np.all(np.abs(np.clip(Z,-3.9,3.9)-affinity.from_u8(U))[np.abs(Z)<3.9]<=1/64+1e-6))
a=spec.key('x','m','r1');b=spec.key('x','m','r2');ok('cache key depends on model revision',a!=b and spec.key('x','m','r1')==a)
print('all passed')
