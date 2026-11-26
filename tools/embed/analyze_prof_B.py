import sys,json,numpy as np
R=sys.argv[1];PR=sys.argv[2];sys.argv=[sys.argv[0],R,'/dev/null']
src=open('analyze_dev.py').read().split('out={}')[0];exec(src)
Ep=np.load(PR+'/emb_proto.npy');pidx=json.load(open(PR+'/proto_index.json'));Ee=np.load(PR+'/emb_prof.npy');pid=json.load(open(PR+'/ids_prof.json'));pp={i:k for k,i in enumerate(pid)}
Rr,d2=affinity.domain_sims(Ee,Ep,pidx);assert d2==doms;ZB=affinity.zscore(Rr,man['stats'])   # same frozen stats as opportunities
def aff_prof(it):return float(ZB[pp[it['id']],doms.index(F2D[it['field']])])
items=[i for i in D['prof'] if i['id'] in PQ];out={'n':len(items)}
sr=[rule(i['field'],i) for i in items];sa=[aff_prof(i) for i in items];sf=fusion_scores(items,'prof','rel');su=[TIER[i['rule_tier']]*3+a for i,a in zip(items,sa)]
out.update(rule=macro(items,sr,'rel'),affinity_B=macro(items,sa,'rel'),union=macro(items,su,'rel'),fusion=macro(items,sf,'rel'),d_union_CI=boot(items,sr,su,'rel'),d_fusion_CI=boot(items,sr,sf,'rel'))
# Related-tier precision: among rule 'related' items, relevant share; and top-K precision
rl=[i for i in items if i['rule_tier']=='related' and i['stratum']!='S6b'];w=sum(i['w'] for i in rl);out['rule_related_precision']=sum(i['w']*labels(i,'rel') for i in rl)/w
for nm,sc in (('rule',sr),('affinity_B',sa),('fusion',sf)):
    pr=[]
    for f in {i['field'] for i in items}:
        ks=[k for k,i in enumerate(items) if i['field']==f and i['stratum']!='S6b'];K=sum(items[k]['w'] for k in ks if items[k]['rule_tier'] in('direct','related'))
        o=sorted(ks,key=lambda k:-sc[k]);cw=tp=0
        for k in o:
            cw+=items[k]['w'];tp+=items[k]['w']*labels(items[k],'rel')
            if cw>=K:break
        if cw:pr.append(tp/cw)
    out['topK_prec_'+nm]=float(np.mean(pr))
print(json.dumps(out,indent=1))
