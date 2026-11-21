// run: node tests/relevance2.test.js   - engine v2: multi-domain, multilingual, page text, guards, query parsing
const Rel = require('../docs/relevance.js');
let bad = 0, n = 0;
const ok = (name, cond) => { n++; if (!cond) { bad++; console.log('FAIL', name); } };
const mem = p => Rel.members(Object.assign({ topics: '' }, p));
const has = (p, d) => mem(p).includes(d);
const J = (p, query, lex) => Rel.judge(Object.assign({ topics: '' }, p), Rel.parseQuery(query), lex === undefined ? true : lex);
// ---- the query phrase is consumed completely (the old engine left "ure", "ics", "y", "al" behind as a text filter)
['Architecture', 'Civil Engineering', 'Mechanical Engineering', 'Electrical Engineering', 'Computer Science', 'Medicine', 'Law', 'Psychology', 'Economics', 'Environmental Engineering', 'Chemical Engineering', 'Urban Planning', 'Landscape Architecture', 'Biomedical Engineering']
  .forEach(q => ok('no leftover tokens: ' + q, Rel.parseQuery(q).rest.length === 0));
ok('landscape architecture is one domain', [...Rel.parseQuery('Landscape Architecture').doms].join() === 'land');
// ---- multilingual titles
[['Doctorado en Psicología', 'psych'], ['Doctorado en Derecho', 'law'], ['Bauingenieurwesen (B.Sc.)', 'civil'], ['Master Génie Civil', 'civil'], ['Humanmedizin', 'med'], ['Informatique - Master', 'cs'],
 ['Mimarlık Doktora Programı', 'arch'], ['Architekt:in (m/w/d)', 'arch'], ['Doctorat en sciences économiques', 'econ'], ['Juristische*r Referent*in', 'law'], ['Maschinenbau M.Sc.', 'mech'],
 ['Elektrotechnik und Informationstechnik', 'elec'], ['Ingeniería Química', 'chemeng'], ['Santé publique', 'health'], ['Mobilitate urbană', null], ['Master Urbanisme et aménagement', 'urban'],
 ['Umweltingenieurwesen', 'env'], ['Tiermedizin', 'vet'], ['Zahnmedizin', 'dent'], ['Doktora Hukuk', 'law']].forEach(([t, d]) => { if (d) ok('lexicon ' + t, has({ title: t }, d)); });
// ---- one opportunity, several fields; retrievable from each
const multi = { title: 'PhD in computational design for timber architecture, urban planning and energy systems' };
['arch', 'energy', 'urban'].forEach(d => ok('multi-domain member ' + d, has(multi, d)));
ok('multi: found by architecture query', J(multi, 'architecture') === 'direct');
ok('multi: found by energy query', J(multi, 'energy') === 'direct');
// ---- page text (description / research topics / department) places an opportunity whose headline says nothing
const generic = { title: 'PhD Position (m/f/d)', rt: 'Department of Architecture | Research areas: structural timber, circular building', desc: 'The doctoral candidate will develop digital fabrication workflows for timber construction and architectural design.' };
ok('page text: architecture', has(generic, 'arch'));
ok('page text alone is found by query', J(generic, 'architecture', false) === 'direct');
ok('generic title without text is not classified', mem({ title: 'PhD Position (m/f/d)' }).length === 0);
// ---- sense guards
ok('financial aid is not finance', !has({ title: 'Financial Aid & Scholarships' }, 'fin'));
ok('figurative bridge is not civil engineering', !has({ title: 'A Bridge Between Academia and Industry' }, 'civil'));
ok('bridge engineering is civil', has({ title: 'Bridge Engineering PhD' }, 'civil'));
ok('water management is not business', !has({ title: 'MSc Water Resources Management' }, 'bus'));
ok('energy management is energy', has({ title: 'Postgraduate Energy Management' }, 'energy') && !has({ title: 'Postgraduate Energy Management' }, 'bus'));
ok('MBA is business, not economics', has({ title: 'MBA Program' }, 'bus') && J({ title: 'MBA Program' }, 'economics') !== 'direct');
ok('software architect is not architecture', J({ title: 'Software Architect' }, 'architecture') !== 'direct');
ok('Cambridge is not a bridge', !has({ title: 'Postdoc at Cambridge University' }, 'civil'));
ok('mechanical systems biology is not mechanical engineering', !has({ title: 'Mechanical Systems Biology Group: Postdoc' }, 'mech'));
// ---- strict relations
ok('IR is not related to psychology', J({ title: 'PhD in Politics and International Relations' }, 'psychology') !== 'related' && J({ title: 'PhD in Politics and International Relations' }, 'psychology') !== 'direct');
ok('urban design is related to civil? no - to architecture', J({ title: 'Master in Urban Design' }, 'architecture') === 'related');
ok('energy policy is not mechanical', J({ title: 'PhD Clean Energy Policy and Management' }, 'mechanical engineering') !== 'direct');
// ---- sub-disciplines the user asked about
[['Landscape Architecture MSc', 'direct'], ['BIM Coordinator, Building Construction', 'direct'], ['MSc Architectural Conservation', 'direct'], ['Building Science and Technology', 'direct'], ['Interior Architecture', 'direct'],
 ['Computational Design and Digital Fabrication, Architecture', 'direct'], ['Urban Design', 'related'], ['Architectural Technology BSc', 'direct']].forEach(([t, w]) => ok('architecture subfield ' + t, J({ title: t }, 'architecture') === w));
// ---- baked scores are used when the engine version matches
const p = { title: 'x', dm: [['law', 4]], dv: Rel.VERSION };
ok('baked dm used', Rel.members(p)[0] === 'law');
console.log(bad ? bad + ' of ' + n + ' FAILED' : 'all ' + n + ' passed'); process.exit(bad ? 1 : 0);
