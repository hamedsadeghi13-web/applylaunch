"""Domain affinity from embeddings. similarity(domain) = max over the domain's seed phrases; z-scored with FROZEN corpus statistics (so
values do not drift as the corpus grows); stored as uint8 (z*32+128)."""
import numpy as np
def domain_sims(E,Ep,pidx):
    """E: n x d (L2-normalised). Returns n x D raw sims (max over seeds) and the domain order."""
    doms=[];
    for d in pidx:
        if d not in doms:doms.append(d)
    S=E.astype(np.float32)@Ep.astype(np.float32).T;idx=np.array([doms.index(d) for d in pidx])
    out=np.full((E.shape[0],len(doms)),-1.0,dtype=np.float32)
    for j,d in enumerate(doms):out[:,j]=S[:,idx==j].max(axis=1)
    return out,doms
def fit_stats(R):return {'mean':R.mean(axis=0).tolist(),'std':np.maximum(R.std(axis=0),1e-6).tolist()}
def zscore(R,stats):return (R-np.array(stats['mean'],dtype=np.float32))/np.array(stats['std'],dtype=np.float32)
def to_u8(Z):return np.clip(np.rint(Z*32+128),0,255).astype(np.uint8)
def from_u8(U):return (U.astype(np.float32)-128)/32
