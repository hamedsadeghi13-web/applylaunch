import sys,json,collections,os
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','crawler'))
import extract as X
def run(verbose=False):
    res={}
    for f in ('gold_kind','val_kind'):
        g=json.load(open(os.path.join(os.path.dirname(__file__),f+'.json')))
        c=collections.Counter();bad=[]
        for t,i,l in g:
            p=X.kind_of_title(t);c[(l,p)]+=1
            if verbose and ((l=='noise')!=(p=='noise')):bad.append((l,p,t[:80]))
        pn=sum(v for (l,p),v in c.items() if p=='noise');tn=sum(v for (l,p),v in c.items() if l=='noise');ok=c[('noise','noise')]
        hide_wrong=sum(v for (l,p),v in c.items() if p=='noise' and l!='noise')
        op_t=sum(v for (l,p),v in c.items() if l=='opening');op_ok=sum(v for (l,p),v in c.items() if l=='opening' and p in('opening','programme'))
        res[f]=dict(n=len(g),noise_precision=round(ok/max(pn,1),3),noise_recall=round(ok/max(tn,1),3),wrongly_hidden=hide_wrong,opening_found=f'{op_ok}/{op_t}')
        if verbose:
            print(f,res[f]);[print('   ',b) for b in bad]
    return res
if __name__=='__main__':
    r=run('-v' in sys.argv);print(json.dumps(r,indent=1))
    ok=all(v['noise_precision']>=0.95 for v in r.values());sys.exit(0 if ok else 1)
