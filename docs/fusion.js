/* ApplyLaunch - experimental "fusion" ranking for opportunity search.
   Loaded ONLY when ?engine=fusion (or flags.json says so). Nothing is ever removed: it (a) lets a small, fixed share of list slots follow a
   fusion order (rule tier + kind + embedding affinity) and (b) adds look-alike records the rule engine cannot see, labelled "suggested match".
   Any problem (file missing/corrupt, version mismatch, unvalidated query) silently leaves the current engine in charge. */
(function (G) {
  const F = { ready: false, active: false, spec: null, doms: null, u8: null, row: null, nd: 0, sem: [], elig: null };
  const TIER = r => (r.relRank === 1.5 ? 'loose' : r.rel);
  F.init = async function () {
    F.ready = false;
    try {
      const v = Date.now();
      const [mr, br] = await Promise.all([fetch('data/affinity.json?v=' + v, { cache: 'no-store' }), fetch('data/affinity.bin?v=' + v, { cache: 'no-store' })]);
      if (!mr.ok || !br.ok) throw 0;
      const m = await mr.json(), buf = await br.arrayBuffer();
      if (m.version !== 1 || !m.fusion || m.relevance_version !== (G.Rel && G.Rel.VERSION) || buf.byteLength !== m.n * 4 + m.n * m.nd) throw 0;
      const ids = new Uint32Array(buf.slice(0, m.n * 4)), u8 = new Uint8Array(buf, m.n * 4);
      const row = new Map(); for (let i = 0; i < ids.length; i++) row.set(ids[i], i);
      F.spec = m.fusion; F.doms = m.domains; F.nd = m.nd; F.u8 = u8; F.row = row; F.ready = true;
    } catch (e) { F.ready = false; F.spec = null; }
  };
  F.z = (id, d) => { const i = F.row.get(id); return i === undefined ? NaN : (F.u8[i * F.nd + d] - 128) / 32; };
  F.logit = (r, z) => {
    const s = F.spec, c = s.coef, t = TIER(r), k = r.kind;
    const zc = Math.max(s.z_clip[0], Math.min(s.z_clip[1], z));
    return s.intercept + c[0] * (t === 'direct') + c[1] * (t === 'related') + c[2] * (t === 'loose') + c[3] * (t === 'unclassified') + c[4] * zc + c[5] * (k === 'opening') + c[6] * (k === 'programme') + c[7] * (k === 'info');
  };
  /* called once per search: decides whether fusion applies to this query */
  F.begin = function (pq, toks) {
    F.active = false; F.sem = []; F.elig = null;
    if (!F.ready || !pq || pq.doms.size !== 1 || toks.length || typeof S === 'undefined' || S.sort !== 'match') return false;   /* only the default relevance order; explicit user sorts stay untouched */
    const d = [...pq.doms][0];
    if (!F.spec.validated_domains.includes(d)) return false;
    const j = F.doms.indexOf(d); if (j < 0) return false;
    F.elig = { d, j, rescue: F.spec.rescue.domains.includes(d) };
    return (F.active = true);
  };
  /* a record the rule engine did not show (judge2 -> null) */
  F.cand = function (p) {
    if (!F.active || !F.elig.rescue || p.kind === 'noise' || !F.spec.rescue.kinds.includes(p.kind)) return;
    const z = F.z(p.id, F.elig.j);
    if (z >= F.spec.rescue.z_min) F.sem.push({ p, z });
  };
  /* after the rule list `out` is built: score it, add suggested matches (additive only) */
  F.finish = function (out) {
    if (!F.active) return out;
    out.forEach(r => { const z = F.z(r.id, F.elig.j); r.fs = (r.rel === 'irrelevant' || r.kind === 'noise' || isNaN(z)) ? -Infinity : F.logit(r, z); });
    F.sem.forEach(({ p, z }) => {
      const r = Object.assign({}, p, { score: null, why: [], warn: [], rel: 'sem', rs: 0, relRank: 2.5, kr: 0, sem: true });
      r.fs = F.logit(Object.assign({}, r, { rel: null, relRank: 2.5 }), z); out.push(r);
    });
    F.sem = []; return out;
  };
  /* base = list in the current engine's order (user-chosen sort already applied); returns the merged order. same set of records. */
  F.merge = function (base, list) {
    if (!F.active) return base;
    const L0 = base.filter(r => !r.sem), pool = base.filter(r => r.fs > -Infinity).sort((a, b) => b.fs - a.fs);
    const mix = F.spec.mix, ratio = mix / (1 - mix), seen = new Set(), out = [];
    let a = 0, b = 0, e0 = 0, e1 = 0;
    const nextOf = (L, i) => { while (i < L.length && seen.has(L[i])) i++; return i; };
    while (out.length < base.length) {
      b = nextOf(pool, b); a = nextOf(L0, a);
      if (b < pool.length && (e1 < ratio * e0 || a >= L0.length)) { const r = pool[b++]; seen.add(r); out.push(r); e1++; continue; }
      if (a < L0.length) { const r = L0[a++]; seen.add(r); out.push(r); e0++; continue; }
      base.forEach(r => { if (!seen.has(r)) { seen.add(r); out.push(r); } }); break;     /* safety: everything not yet placed goes last */
    }
    return out;
  };
  G.FUS = F;
})(typeof window !== 'undefined' ? window : globalThis);
