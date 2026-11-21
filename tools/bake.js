/* node tools/bake.js  - computes the domain scores of every opportunity once (title + page text + topics) and stores them in positions.json
 * as dm:[[domain,score],...] and dv:<engine version>. The browser then does not have to classify 19k records itself.
 * Single source of truth: docs/relevance.js (the same file the site uses). Safe to run repeatedly. */
const fs = require('fs'), path = require('path');
const Rel = require('../docs/relevance.js');
const dir = path.join(__dirname, '..', 'docs', 'data');
const pf = path.join(dir, 'positions.json'), tf = path.join(dir, 'text.json');
const J = JSON.parse(fs.readFileSync(pf, 'utf8'));
const T = fs.existsSync(tf) ? JSON.parse(fs.readFileSync(tf, 'utf8')).text || {} : {};
const P = J.positions;
P.forEach(p => { const t = T[String(p.id)]; if (t) { p.desc = t[0]; p.rt = t[2]; } });
Rel.prepare(P);
let withDom = 0, multi = 0, fromText = 0;
P.forEach(p => {
  const b = Rel.bake(p);
  delete p._dom;
  if (b.length) { p.dm = b.map(([i, s]) => [i, s]); withDom++; if (b.filter(x => x[1] >= Rel.MEMBER).length > 1) multi++; } else delete p.dm;
  p.dv = Rel.VERSION;
  if (t = T[String(p.id)]) { const noText = Rel.bake(Object.assign({}, p, { desc: '', rt: '' })); if (b.length > noText.length) fromText++; }
  delete p.desc; delete p.rt; delete p._tb;
});
var t;
J.baked = { version: Rel.VERSION, at: new Date().toISOString().slice(0, 10) };
fs.writeFileSync(pf, JSON.stringify(J));
console.log(JSON.stringify({ records: P.length, with_domain: withDom, pct: Math.round(1000 * withDom / P.length) / 10, multi_domain: multi, gained_from_page_text: fromText, with_text: Object.keys(T).length }));
