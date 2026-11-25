#!/usr/bin/env python3
"""Build per-record domain affinity (uint8, 56 per record) from embed.py output. Stats (mean/std) are fitted once on this snapshot and stored in affinity_manifest.json (frozen for later runs via --stats)."""
import argparse,json,os,sys
import numpy as np
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import affinity
ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);ap.add_argument('--stats',default='');a=ap.parse_args()
L=lambda n:np.load(os.path.join(a.out,n))
E=L('emb_opp.npy');Ep=L('emb_proto.npy');pidx=json.load(open(os.path.join(a.out,'proto_index.json')))
R,doms=affinity.domain_sims(E,Ep,pidx)
st=json.load(open(a.stats))['stats'] if a.stats else affinity.fit_stats(R)
np.save(os.path.join(a.out,'affinity_opp.npy'),affinity.to_u8(affinity.zscore(R,st)))
# topics / depts (professor side) use the same frozen stats
for nm in ('topic','dept'):
    Rt,_=affinity.domain_sims(L('emb_%s.npy'%nm),Ep,pidx);np.save(os.path.join(a.out,'affinity_%s.npy'%nm),affinity.to_u8(affinity.zscore(Rt,st)))
json.dump({'domains':doms,'stats':st,'encoding':'uint8 = clip(round(z*32+128),0,255)'},open(os.path.join(a.out,'affinity_manifest.json'),'w'))
print('affinity built',E.shape[0],'records')
