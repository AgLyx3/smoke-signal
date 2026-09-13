import fs from 'node:fs';

const integrityOnly = process.argv.includes('--integrity-only');

const VALID = ['pending', 'in_progress', 'passing', 'failing', 'blocked', 'deferred'];
const spec = JSON.parse(fs.readFileSync('FEATURES.json', 'utf8'));

const problems = [];
for (const f of spec.features) {
  if (!VALID.includes(f.status)) problems.push(`${f.id}: invalid status "${f.status}"`);
  if (f.status === 'passing' && (!f.verify || f.verify.length === 0)) {
    problems.push(`${f.id}: marked passing with no verify steps`);
  }
  if (f.status === 'blocked' && !f.blocked_by) problems.push(`${f.id}: blocked with no blocked_by`);
  if (f.blocked_by && !spec.blockers?.[f.blocked_by]) {
    problems.push(`${f.id}: blocked_by "${f.blocked_by}" is not in blockers`);
  }
}

const v1 = spec.features.filter((f) => f.status !== 'deferred');
const tally = {};
for (const f of v1) tally[f.status] = (tally[f.status] ?? 0) + 1;

const pct = v1.length ? Math.round(((tally.passing ?? 0) / v1.length) * 100) : 0;
console.log(`\n${spec.project} — v1: ${tally.passing ?? 0}/${v1.length} passing (${pct}%)`);
console.log(Object.entries(tally).map(([k, v]) => `  ${k}: ${v}`).join('\n'));
console.log(`  deferred (not counted): ${spec.features.length - v1.length}`);

const outstanding = v1.filter((f) => f.status !== 'passing');
if (outstanding.length) {
  console.log('\nNot yet passing:');
  for (const f of outstanding) {
    const flag = f.blocked_by ? `  [blocked: ${f.blocked_by}]` : '';
    console.log(`  ${f.status.padEnd(12)} ${f.id.padEnd(32)} ${f.area}${flag}`);
  }
}

const blocked = v1.filter((f) => f.blocked_by);
if (blocked.length) {
  console.log('\nBlockers:');
  for (const [k, v] of Object.entries(spec.blockers ?? {})) {
    if (blocked.some((f) => f.blocked_by === k)) console.log(`  ${k}: ${v}`);
  }
}

if (problems.length) {
  console.log('\nINTEGRITY PROBLEMS:');
  for (const p of problems) console.log(`  ${p}`);
  process.exit(2);
}

// --integrity-only is for CI: outstanding features are project state, not a defect,
// so only integrity problems (exit 2 above) should fail a build.
process.exit(integrityOnly ? 0 : outstanding.length ? 1 : 0);
