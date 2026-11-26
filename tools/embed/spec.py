"""Frozen text specification (v1) for the Phase-1 embedding layer. Changing anything here MUST bump TEXT_SPEC (cache keys include it)."""
import hashlib,json
TEXT_SPEC='v1'
MODEL='sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
MAX_SEQ=128                      # tokens; most informative content comes first
DESC_CHARS=600
def clean(s): return ' '.join((s or '').split())
def opp_text(p,t=None):
    """title. type. research topics (page) or crawler topics. beginning of description.  NO institution name, NO admission requirements."""
    t=t or ['','','']
    rt=clean(t[2]) or clean(p.get('topics'))
    parts=[clean(p.get('title')),clean(p.get('type')),rt,clean(t[0])[:DESC_CHARS]]
    return '. '.join(x for x in parts if x)
def key(text,model=MODEL,revision=''):
    return hashlib.sha256('\x1f'.join([model,revision,TEXT_SPEC,text]).encode()).hexdigest()[:24]

def prof_text(q):
    """Whole-profile text (variant B, added AFTER seeing Dev results of the per-topic variant): department | first 8 topics."""
    d=clean(q.get('dept'));t='; '.join(clean(x) for x in (q.get('topics') or [])[:8] if x)
    return (d+' | '+t) if d and t else (d or t)
