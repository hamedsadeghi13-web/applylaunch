// run:  node tests/relevance.test.js      (no dependencies)
const Rel = require('../docs/relevance.js');
const q = Rel.parseQuery('architecture');
const word = t => /architect/i.test(t);
const cases = [
  ['Architecture', 'direct'], ['Architectural Design PhD', 'direct'], ['Sustainable Architecture Master', 'direct'],
  ['Landscape Architecture', 'direct'], ['Interior Architecture', 'direct'], ['Junior Architect - Retail', 'direct'], ['Project Architect', 'direct'],
  ['DIPLÔME D’ÉTAT D\'ARCHITECTE (MASTER)', 'direct'],
  ['Urban Design', 'related'], ['Computational Design in Architecture and Fabrication', 'direct'],
  ['Parametric design and robotic fabrication for timber construction', 'direct'],
  ['Software Architect', 'irrelevant'], ['C++ Software Architecture', 'irrelevant'], ['Software Development Architect', 'irrelevant'],
  ['Solutions Architect', 'irrelevant'], ['Cloud Architect - AWS', 'irrelevant'], ['Enterprise Architect', 'irrelevant'],
  ['PhD in computer architecture and processors', 'irrelevant'], ['Neural network architecture search PhD', 'irrelevant'],
  ['Doctoral Position in contact mechanics of architected interfaces', 'irrelevant'],
  ['Postdoc: exoskeleton architecture and actuation', 'irrelevant'],
  ['Computational Design for mobile UX software', null], ['Postdoc in cell biology', null]
];
let bad = 0;
for (const [t, want] of cases) {
  const got = Rel.judge({ title: t, topics: '' }, q, word(t));
  if (got !== want) { bad++; console.log('FAIL', JSON.stringify(t), 'expected', want, 'got', got); }
}
const eq = (name, a, b) => { if (a !== b) { bad++; console.log('FAIL', name, a, b); } };
eq('cambridge is not a bridge', Rel.judge({ title: 'Postdoc at Cambridge University', topics: '' }, Rel.parseQuery('civil engineering'), false), null);
eq('persian query maps to architecture', [...Rel.parseQuery('معماری').doms][0], 'arch');
console.log(bad ? bad + ' failure(s)' : 'all ' + (cases.length + 2) + ' relevance tests passed');
process.exit(bad ? 1 : 0);
