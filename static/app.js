/* Dungeon Master's Orchestrator, front end */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const sgn = n => (n >= 0 ? '+' + n : String(n));
const store = { get: k => { try { return localStorage.getItem(k); } catch { return null; } }, set: (k, v) => { try { localStorage.setItem(k, v); } catch {} } };
const cid = store.get('cid') || (() => { const v = (crypto.randomUUID && crypto.randomUUID()) || String(Math.random()).slice(2) + Date.now(); store.set('cid', v); return v; })();
const AB = ['str', 'dex', 'con', 'int', 'wis', 'cha'];
const KINDS = [
  { k: 'character', label: 'Heroes', icon: '🧙' }, { k: 'npc', label: 'NPCs', icon: '🍺' },
  { k: 'encounter', label: 'Foes', icon: '⚔️' }, { k: 'note', label: 'Notes', icon: '🪶' }, { k: 'print', label: 'Forge', icon: '🖨️' },
];
const COMBAT_TOOLS = ['start_combat', 'next_turn', 'combat_hp', 'combat_condition', 'end_combat'];
let kind = 'character', agents = {}, advMode = 'none', rollHistory = [];

/* ------------------------------------------------------------ api */
async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { 'Content-Type': 'application/json' }, ...opts });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}
const who = () => ($('#who').value || 'DM').trim().slice(0, 20) || 'DM';
const runTool = async (name, args = {}) => {
  const res = await api('/api/tool/' + name, { method: 'POST', body: JSON.stringify({ args, cid, who: who() }) });
  return res;
};

/* ------------------------------------------------------------ cards */
const pills = a => `<div class="pillrow">${(a || []).map(x => `<span class="pill">${esc(x)}</span>`).join('')}</div>`;

function renderCard(c) {
  switch (c.type) {
    case 'character': return characterCard(c);
    case 'npc': return npcCard(c);
    case 'encounter': return encounterCard(c);
    case 'loot': return lootCard(c);
    case 'roll': return rollCard(c);
    case 'combat': return `<div class="card"><h3>🛡️ ${esc(c.event || 'Combat')}</h3><div class="sub">Round ${c.round ?? '-'} · see the War Table</div></div>`;
    case 'print': return printCard(c);
    case 'note': return `<div class="card"><h3>🪶 ${esc(c.name)}</h3><p>${esc(c.text).replace(/\n/g, '<br>')}</p></div>`;
    case 'state': return stateCard(c);
    case 'error': return `<div class="card errcard"><h3>⚠️ The dice slipped</h3><p>${esc(c.message)}</p></div>`;
    default: return `<div class="card"><pre>${esc(JSON.stringify(c, null, 2))}</pre></div>`;
  }
}

function characterCard(c) {
  const sp = c.spellcasting;
  const slots = sp ? Object.entries(sp.slots).map(([l, n]) => `<span class="pill gold">${sp.pact ? 'Pact' : 'L' + l}: ${n}${sp.pact ? ' × L' + l : ''}</span>`).join('') : '';
  return `<div class="card">
    <h3>${esc(c.name)}</h3><div class="sub">Level ${c.level} ${esc(c.race)} ${esc(c.class)} · ${esc(c.background)}</div>
    <div class="stats"><div class="stat"><b>${c.hp}</b><span>HP</span></div><div class="stat"><b>${c.ac}</b><span>AC</span></div>
      <div class="stat"><b>${sgn(c.initiative)}</b><span>Init</span></div><div class="stat"><b>${c.speed}</b><span>Speed</span></div></div>
    <div class="abils">${AB.map(a => `<div class="ab"><span class="abn">${a.toUpperCase()}</span><b>${c.abilities[a].score}</b><i>${sgn(c.abilities[a].mod)}</i></div>`).join('')}</div>
    <h4>Attacks</h4><table class="tbl"><tr><th>Name</th><th>Hit</th><th>Damage</th></tr>
      ${c.attacks.map(a => `<tr><td>${esc(a.name)}<br><small style="color:var(--mute)">${esc(a.note)}</small></td><td>${sgn(a.to_hit)}</td><td>${esc(a.damage)}</td></tr>`).join('')}</table>
    ${sp ? `<h4>Spellcasting (${sp.ability})</h4><div class="pillrow"><span class="pill gold">Save DC ${sp.save_dc}</span><span class="pill gold">Attack ${sgn(sp.attack)}</span>${slots}</div>` : ''}
    <h4>Saves &amp; Skills</h4>
    <div class="pillrow">${AB.filter(a => c.saves[a].prof).map(a => `<span class="pill gold">${a.toUpperCase()} save ${sgn(c.saves[a].bonus)}</span>`).join('')}
      ${c.skills.filter(s => s.prof).map(s => `<span class="pill">${esc(s.name)} ${sgn(s.bonus)}</span>`).join('')}<span class="pill">Passive Perception ${c.passive_perception}</span></div>
    <h4>Features</h4>${pills([...c.racial_traits, ...c.features])}
    <h4>Gear</h4>${pills(c.equipment)}
    <h4>Backstory</h4><p>${esc(c.backstory.origin)} ${esc(c.backstory.hook)} ${esc(c.backstory.bond)}</p><p><em>${esc(c.backstory.flaw)}</em></p>
    <div class="actions"><button class="btn2" data-act="print" data-name="${esc(c.name)}" data-id="${c.id || ''}" data-type="miniature">🖨️ Queue mini</button></div>
  </div>`;
}

function npcCard(n) {
  return `<div class="card"><h3>${esc(n.name)}</h3><div class="sub">${esc(n.race)} ${esc(n.role)} · ${esc(n.attitude)}</div>
    <div class="two"><div class="kv"><span>Look</span><b style="font-weight:500;text-align:right">${esc(n.appearance)}</b></div><div class="kv"><span>Voice</span><b style="font-weight:500;text-align:right">${esc(n.voice)}</b></div></div>
    <h4>Trait</h4><p>${esc(n.trait)}</p><h4>Wants</h4><p>${esc(n.wants)}</p><h4>Secret</h4><p>🤫 This NPC ${esc(n.secret)}.</p>
    <div class="actions"><button class="btn2" data-act="print" data-name="${esc(n.name)}" data-id="${n.id || ''}" data-type="miniature">🖨️ Queue mini</button></div></div>`;
}

function encounterCard(e) {
  const t = e.thresholds, max = t.deadly * 1.25, pct = v => Math.min(100, (v / max) * 100);
  return `<div class="card"><h3>${esc(e.title)}</h3>
    <div class="sub">Party of ${e.party_size} · level ${e.party_level} · <span class="diff ${esc(e.difficulty)}">${esc(e.difficulty)}</span> (asked for ${esc(e.requested)})</div>
    <div class="meter"><div class="fill" style="width:${pct(e.adjusted_xp)}%"></div>
      ${['easy', 'medium', 'hard', 'deadly'].map(d => `<div class="tick" style="left:${pct(t[d])}%"><em>${d}</em></div>`).join('')}<div class="mark" style="left:calc(${pct(e.adjusted_xp)}% - 2px)"></div></div>
    <div class="pillrow"><span class="pill gold">Adjusted XP ${e.adjusted_xp}</span><span class="pill">Raw XP ${e.total_xp}</span><span class="pill">Theme: ${esc(e.theme)}</span></div>
    <h4>Foes</h4><table class="tbl"><tr><th></th><th>Monster</th><th>CR</th><th>HP</th><th>AC</th></tr>
      ${e.monsters.map(m => `<tr><td><b>${m.count}×</b></td><td>${esc(m.name)}<br><small style="color:var(--mute)">${esc(m.attack)}</small></td><td>${esc(m.cr)}</td><td>${m.hp}</td><td>${m.ac}</td></tr>`).join('')}</table>
    <h4>Tactics</h4><p>${esc(e.tactics)}</p><h4>Twist</h4><p>${esc(e.twist)}</p>
    <div class="actions">${e.id ? `<button class="btn2 hot" data-act="combat" data-id="${e.id}">⚔️ Start combat</button>` : ''}
      <button class="btn2" data-act="loot" data-lvl="${e.party_level}">💰 Roll loot</button>
      <button class="btn2" data-act="print" data-name="${esc(e.monsters.map(m => m.count + '× ' + m.name).join(', '))}" data-id="${e.id || ''}" data-type="miniature">🖨️ Queue minis</button></div></div>`;
}

function lootCard(l) {
  return `<div class="card"><h3>💰 ${l.hoard ? 'Treasure Hoard' : 'Loot'}</h3><div class="sub">Tier ${l.tier} · level ${l.party_level}</div>
    <div class="pillrow"><span class="pill gold">${l.gp.toLocaleString()} gp</span>${l.sp ? `<span class="pill">${l.sp.toLocaleString()} sp</span>` : ''}</div>
    ${l.gems.length ? `<h4>Gems</h4>${pills(l.gems.map(g => `${g.name} (${g.value} gp)`))}` : ''}
    <h4>Magic items</h4>${l.items.length ? l.items.map(i => `<div class="kv"><span>${esc(i.name)}</span><span class="rar ${esc(i.rarity)}">${esc(i.rarity)}</span></div>`).join('') : '<p style="color:var(--mute)">Nothing magical this time.</p>'}</div>`;
}

function rollCard(r) {
  const cls = r.crit ? 'crit' : r.fumble ? 'fumble' : '';
  const pool = [...r.kept];  // match kept dice one-for-one so duplicates (4d6kh3 → 4,4,4,2) drop the right one
  const die = (d, keep) => `<span class="die ${keep ? '' : 'drop'}">${d}</span>`;
  const dice = r.dice.map(d => { const i = pool.indexOf(d); if (i >= 0) pool.splice(i, 1); return die(d, i >= 0); }).join('')
    + (r.discarded || []).map(d => die(d, false)).join('');
  return `<div class="card"><div class="rollcard ${cls}"><div class="big">${r.total}</div><div>
    <div><b>${esc(r.expr)}</b>${r.advantage !== 'none' ? ` · ${r.advantage === 'adv' ? 'advantage' : 'disadvantage'}` : ''}${r.reason ? ' · ' + esc(r.reason) : ''}</div>
    <div>${dice}${r.modifier ? `<span class="die">${sgn(r.modifier)}</span>` : ''}</div>
    ${r.crit ? '<b style="color:var(--gold)">🌟 NATURAL 20!</b>' : ''}${r.fumble ? '<b style="color:var(--red)">💀 Natural 1…</b>' : ''}</div></div></div>`;
}

function printCard(j) {
  const next = { queued: 'printing', printing: 'done', done: null, failed: 'queued' }[j.status];
  return `<div class="card"><h3>🖨️ ${esc(j.name)}</h3><div class="sub">${esc(j.item_type)} · ${j.scale_mm} mm · ×${j.quantity}</div>
    <div class="pillrow"><span class="pill gold">${esc(j.status)}</span><span class="pill">webhook: ${esc(j.webhook)}</span></div>
    ${j.notes ? `<p>${esc(j.notes)}</p>` : ''}<div class="actions">${next ? `<button class="btn2" data-act="pstatus" data-id="${j.id}" data-s="${next}">→ Mark ${next}</button>` : ''}
    ${j.status !== 'failed' && j.status !== 'done' ? `<button class="btn2" data-act="pstatus" data-id="${j.id}" data-s="failed">Mark failed</button>` : ''}</div></div>`;
}

function stateCard(s) {
  const sec = (label, arr) => arr.length ? `<h4>${label}</h4>${arr.map(i => `<div class="kv"><span>${esc(i.name)} <small style="color:var(--mute)">#${i.id}</small></span><span style="color:var(--mute)">${esc(i.summary)}</span></div>`).join('')}` : '';
  return `<div class="card"><h3>📚 Campaign at a glance</h3>${sec('Heroes', s.character)}${sec('NPCs', s.npc)}${sec('Encounters', s.encounter)}${sec('Notes', s.note)}${sec('Print jobs', s.print)}
    ${[s.character, s.npc, s.encounter, s.note, s.print].every(a => !a.length) ? '<p style="color:var(--mute)">The Archive is empty. Ask me to build something!</p>' : ''}</div>`;
}

/* ------------------------------------------------------------ chat */
const msgs = $('#messages');
const mdLite = t => esc(t).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\n/g, '<br>');
function addMsg(role, html, cardsHtml = '') {
  const el = document.createElement('div');
  el.className = 'msg ' + role;
  el.innerHTML = `<div class="who">${role === 'user' ? esc(who()) : '🧠 Orchestrator'}</div><div class="bubble">${html}</div>${cardsHtml ? `<div class="cards">${cardsHtml}</div>` : ''}`;
  msgs.appendChild(el);
  msgs.scrollTop = msgs.scrollHeight;
  return el;
}
function addCards(list) { if (list.length) addMsg('bot', '', list.map(renderCard).join('')).querySelector('.bubble').remove(); }

async function send(text) {
  text = (text ?? $('#input').value).trim();
  if (!text) return;
  $('#input').value = ''; autosize();
  addMsg('user', esc(text));
  const typing = addMsg('bot', '<span class="typing"><i></i><i></i><i></i></span>');
  $('#send').disabled = true;
  try {
    const res = await api('/api/chat', { method: 'POST', body: JSON.stringify({ cid, message: text, who: who() }) });
    typing.remove();
    addMsg('bot', mdLite(res.reply || '…'), (res.cards || []).map(renderCard).join(''));
    loadLibrary(); loadCombat();
  } catch (e) { typing.remove(); addMsg('bot', '⚠️ ' + esc(e.message)); }
  $('#send').disabled = false; $('#input').focus();
}
const autosize = () => { const t = $('#input'); t.style.height = 'auto'; t.style.height = Math.min(140, t.scrollHeight) + 'px'; };
$('#input').addEventListener('input', autosize);
$('#input').addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } });
$('#composer').addEventListener('submit', e => { e.preventDefault(); send(); });

const QUICK = [
  ['⚔️ Medium encounter', 'Build a medium encounter for 4 level 3 heroes'], ['💀 Undead ambush', 'Hard undead encounter, level 5 party of 4'],
  ['🧙 Random hero', 'Create a random level 3 hero'], ['🍺 NPC', 'Make me an NPC innkeeper with a dark secret'],
  ['💰 Loot hoard', 'Roll a treasure hoard for level 5'], ['🗓️ Prep session', "Prep tonight's session: a spooky crypt encounter for 4 level 5 heroes, a cultist NPC, loot, and save a note with the plot hook"],
  ['🛡️ Start combat', 'Start combat'], ['📚 What do we have?', 'What do we have in the archive?'],
];
$('#quick').innerHTML = QUICK.map(([l, p]) => `<button data-p="${esc(p)}">${esc(l)}</button>`).join('');
$('#quick').addEventListener('click', e => { const b = e.target.closest('button'); if (b) send(b.dataset.p); });

/* ------------------------------------------------------------ archive */
const SUB = {
  character: i => `L${i.level} ${i.race} ${i.class}`, npc: i => `${i.race} ${i.role}`,
  encounter: i => `${i.difficulty} · ${i.monsters.reduce((a, m) => a + m.count, 0)} foes`, note: i => (i.text || '').slice(0, 40), print: i => i.status,
};
function renderTabs() {
  $('#libTabs').innerHTML = KINDS.map(k => `<button data-k="${k.k}" class="${k.k === kind ? 'on' : ''}">${k.icon} ${k.label}</button>`).join('');
}
async function loadLibrary() {
  renderTabs();
  const items = await api('/api/items?kind=' + kind).catch(() => []);
  const k = KINDS.find(x => x.k === kind);
  $('#libList').innerHTML = items.length ? items.map(i => `<div class="item" data-id="${i.id}"><span class="ic">${k.icon}</span>
    <div class="tx"><div class="nm">${esc(i.name)}</div><div class="sb">${esc(SUB[kind](i))}</div></div><button class="del" data-del="${i.id}" title="Delete">✕</button></div>`).join('')
    : `<div class="empty">Nothing here yet.<br>Ask the Orchestrator to conjure some ${k.label.toLowerCase()}!</div>`;
  $('#libList')._items = Object.fromEntries(items.map(i => [i.id, i]));
}
$('#libTabs').addEventListener('click', e => { const b = e.target.closest('button'); if (b) { kind = b.dataset.k; loadLibrary(); } });
$('#libList').addEventListener('click', async e => {
  const del = e.target.closest('[data-del]');
  if (del) { e.stopPropagation(); if (confirm('Delete this from the Archive?')) { await api('/api/items/' + del.dataset.del, { method: 'DELETE' }); loadLibrary(); } return; }
  const it = e.target.closest('.item');
  if (it) openModal(renderCard($('#libList')._items[it.dataset.id]));
});
function openModal(html) { $('#modalbody').innerHTML = html; $('#modal').showModal(); }
$('#modalx').onclick = () => $('#modal').close();
$('#modal').addEventListener('click', e => { if (e.target === $('#modal')) $('#modal').close(); });

/* card button actions (works in chat + modal) */
document.addEventListener('click', async e => {
  const b = e.target.closest('[data-act]'); if (!b) return;
  const a = b.dataset.act;
  try {
    if (a === 'combat') { const r = await runTool('start_combat', { encounter_id: +b.dataset.id, include_party: true }); toast(r.type === 'error' ? '⚠️ ' + esc(r.message) : '🛡️ Initiative rolled!'); showView('table'); }
    if (a === 'loot') addCards([await runTool('generate_loot', { party_level: +b.dataset.lvl })]);
    if (a === 'print') { const j = await runTool('queue_print', { item_name: b.dataset.name, item_type: b.dataset.type || 'miniature', source_id: b.dataset.id ? +b.dataset.id : null }); toast('🖨️ Queued: ' + j.name); }
    if (a === 'pstatus') { await runTool('set_print_status', { id: +b.dataset.id, status: b.dataset.s }); $('#modal').close?.(); }
    loadLibrary();
  } catch (err) { toast('⚠️ ' + esc(err.message)); }
});

/* ------------------------------------------------------------ dice */
const DICE = [4, 6, 8, 10, 12, 20, 100];
$('#diceBtns').innerHTML = DICE.map(d => `<button data-d="${d}">d${d}</button>`).join('');
$('#diceBtns').addEventListener('click', e => { const b = e.target.closest('button'); if (b) rollUi(+b.dataset.d); });
$('#advSeg').addEventListener('click', e => { const b = e.target.closest('button'); if (!b) return; advMode = b.dataset.v; $$('#advSeg button').forEach(x => x.classList.toggle('on', x === b)); });
$('#who').value = store.get('who') || '';
$('#who').addEventListener('change', () => store.set('who', $('#who').value));

async function rollUi(sides) {
  const n = Math.max(1, Math.min(100, +$('#dCount').value || 1)), m = +$('#dMod').value || 0;
  const expr = `${n}d${sides}${m ? (m > 0 ? '+' + m : m) : ''}`;
  let adv = advMode;
  if (adv !== 'none' && !(n === 1 && sides === 20)) { adv = 'none'; toast('Advantage only applies to a single d20, so I rolled normally.'); }
  startTumble();
  try {
    const r = await runTool('roll_dice', { advantage: adv, expression: expr });
    if (r.type === 'error') throw new Error(r.message);
    landDie(r, true);
  } catch (e) {
    clearInterval(tumbling); $('#bigDie').classList.remove('rolling');  // don't leave the die tumbling forever
    toast('⚠️ ' + esc(e.message));
  }
}
let tumbling = null;
function startTumble() {
  const die = $('#bigDie'); die.classList.remove('crit', 'fumble'); die.classList.add('rolling');
  clearInterval(tumbling); tumbling = setInterval(() => { $('#dieNum').textContent = 1 + Math.floor(Math.random() * 20); }, 60);
}
function landDie(r, mine) {
  setTimeout(() => {
    clearInterval(tumbling);
    const die = $('#bigDie'); die.classList.remove('rolling');
    $('#dieNum').textContent = r.total; $('#dieNum').setAttribute('font-size', String(r.total).length > 2 ? 18 : 26);
    if (r.crit) die.classList.add('crit'); if (r.fumble) die.classList.add('fumble');
    $('#dieLabel').textContent = r.crit ? '🌟 NATURAL 20!' : r.fumble ? '💀 Critical fumble' : `${r.expr} = ${r.total}`;
    $('#dieSub').textContent = `${r.who || 'DM'} rolled${r.advantage !== 'none' ? ' with ' + (r.advantage === 'adv' ? 'advantage' : 'disadvantage') : ''}`;
  }, mine ? 650 : 0);
  if (!mine) { clearInterval(tumbling); }
}
function logRoll(r) {
  rollHistory.unshift(r); rollHistory = rollHistory.slice(0, 12);
  $('#rollLog').innerHTML = rollHistory.map(x => `<div class="rl ${x.crit ? 'crit' : x.fumble ? 'fumble' : ''}"><span>${esc(x.who || 'DM')} · ${esc(x.expr)} [${x.dice.join(', ')}]</span><b>${x.total}</b></div>`).join('');
}

/* ------------------------------------------------------------ war table */
async function loadCombat() {
  const s = await api('/api/combat').catch(() => ({ active: false }));
  const box = $('#combat');
  $('#roundTag').textContent = s.active ? `Round ${s.round}` : '';
  if (!s.active) {
    box.innerHTML = `<div class="empty">No battle underway.<br><button class="btn2 hot" id="startBtn" style="margin-top:10px">⚔️ Start from latest encounter</button></div>`;
    $('#startBtn').onclick = async () => {
      const encs = await api('/api/items?kind=encounter');
      const r = await runTool('start_combat', { encounter_id: encs[0]?.id || null, include_party: true });
      if (r.type === 'error') toast('⚠️ ' + esc(r.message)); loadCombat();
    };
    return;
  }
  box.innerHTML = s.combatants.map((c, i) => {
    const pct = Math.max(0, Math.round((c.hp / c.max_hp) * 100));
    return `<div class="cb ${c.side} ${i === s.turn ? 'now' : ''} ${c.hp <= 0 ? 'down' : ''}">
      <div class="ini">${c.init}</div>
      <div><div class="nm">${esc(c.name)}${c.conditions.map(x => `<span class="cond">${esc(x)}</span>`).join('')}</div>
        <div class="hpbar"><i class="${pct < 30 ? 'low' : ''}" style="width:${pct}%"></i></div><div class="meta">${c.hp}/${c.max_hp} HP · AC ${c.ac}</div></div>
      <div class="acts"><button data-hp="-" data-n="${esc(c.name)}" title="Damage">💥</button><button data-hp="+" data-n="${esc(c.name)}" title="Heal">💚</button><button data-cond="${esc(c.name)}" title="Condition">🌀</button></div></div>`;
  }).join('') + `<div class="evt">${esc(s.event || '')}</div><div class="cbctl"><button class="btn2 hot" id="nextBtn">⏭ Next turn</button><button class="btn2" id="endBtn">🏳️ End</button></div>`;
  $('#nextBtn').onclick = async () => { await runTool('next_turn'); loadCombat(); };
  $('#endBtn').onclick = async () => { if (confirm('End combat?')) { await runTool('end_combat'); loadCombat(); } };
}
$('#combat').addEventListener('click', async e => {
  const hp = e.target.closest('[data-hp]'), cond = e.target.closest('[data-cond]');
  if (hp) {
    const v = parseInt(prompt(hp.dataset.hp === '-' ? `Damage to ${hp.dataset.n}?` : `Heal ${hp.dataset.n} by?`), 10);
    if (v > 0) { const r = await runTool('combat_hp', { target: hp.dataset.n, delta: hp.dataset.hp === '-' ? -v : v }); if (r.type === 'error') toast('⚠️ ' + esc(r.message)); loadCombat(); }
  }
  if (cond) {
    const c = prompt(`Toggle condition on ${cond.dataset.cond} (e.g. prone, stunned):`); if (!c) return;
    const s = await api('/api/combat'); const has = s.combatants.find(x => x.name === cond.dataset.cond)?.conditions.includes(c.trim());
    await runTool('combat_condition', { target: cond.dataset.cond, condition: c.trim(), active: !has }); loadCombat();
  }
});

/* ------------------------------------------------------------ guild + ws */
function renderAgents() {
  $('#agents').innerHTML = Object.entries(agents).map(([k, a]) => `<div class="agent ${k === 'orchestrator' ? 'orchestrator' : ''}" id="ag-${k}" title="${esc(a.desc)}">
    <span class="ai">${a.icon}</span>${k === 'orchestrator' ? `<div><span class="an">${esc(a.name)}</span><span class="al" id="al-${k}">${esc(a.desc)}</span></div>` : `<span class="an">${esc(a.name)}</span><span class="al" id="al-${k}">${esc(a.desc)}</span>`}</div>`).join('');
}
function pulse(agent, label) {
  const el = $('#ag-' + agent); if (!el) return;
  el.classList.add('active'); $('#al-' + agent).textContent = label;
  setTimeout(() => { el.classList.remove('active'); $('#al-' + agent).textContent = agents[agent].desc; }, 2200);
}
function toast(html, ms = 3200) {
  const t = document.createElement('div'); t.className = 'toast'; t.innerHTML = html; $('#toasts').appendChild(t); setTimeout(() => t.remove(), ms);
}
let ws, retry = 0;
function connect() {
  ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  ws.onopen = () => { retry = 0; };
  ws.onclose = () => setTimeout(connect, Math.min(8000, 800 * ++retry));
  ws.onmessage = m => {
    const ev = JSON.parse(m.data);
    if (ev.event === 'presence') $('#presence').textContent = ev.count;
    if (ev.event === 'thinking') { $('#thinking').classList.toggle('on', ev.on); $('#ag-orchestrator')?.classList.toggle('think', ev.on); }
    if (ev.event === 'tool_start') pulse(ev.agent, 'working…');
    if (ev.event === 'library') loadLibrary();
    if (ev.event === 'tool') {
      pulse(ev.agent, ev.brief || ev.tool); loadLibrary();
      if (COMBAT_TOOLS.includes(ev.tool)) loadCombat();
      if (ev.roll) {
        logRoll(ev.roll);
        if (ev.cid !== cid) { landDie(ev.roll, false); toast(`🎲 <b>${esc(ev.roll.who)}</b> rolled ${esc(ev.roll.expr)} = <b style="color:var(--gold)">${ev.roll.total}</b>${ev.roll.crit ? ' 🌟' : ev.roll.fumble ? ' 💀' : ''}`); }
        else if (!$('#bigDie').classList.contains('rolling')) landDie(ev.roll, true);
      } else if (ev.cid !== cid && ev.ok) toast('✨ ' + esc(ev.brief || ev.tool));
    }
  };
}

/* ------------------------------------------------------------ chrome */
function showView(v) { document.body.dataset.view = v; $$('.tabbar button').forEach(b => b.classList.toggle('on', b.dataset.view === v)); }
$$('.tabbar button').forEach(b => b.onclick = () => showView(b.dataset.view));

async function init() {
  const st = await api('/api/status').catch(() => null);
  if (st) {
    agents = st.agents; renderAgents();
    const chip = $('#modeChip');
    chip.textContent = st.mode === 'claude' ? `🟢 Claude · ${st.model}` : '🟡 Offline Rules Engine';
    chip.classList.add(st.mode === 'claude' ? 'live' : 'off');
    const url = `${location.protocol}//${st.ips[0]}:${st.port}`;
    $('#urlText').textContent = url.replace(/^https?:\/\//, '');
    $('#copyUrl').onclick = async () => { try { await navigator.clipboard.writeText(url); toast('🔗 Copied ' + esc(url)); } catch { prompt('Table link:', url); } };
    addMsg('bot', st.mode === 'claude'
      ? "Welcome, Dungeon Master. 🐉 Tell me what the night needs and I'll command the Guild. Try <code>Prep a spooky crypt session for four level 5 heroes</code>."
      : "Welcome, Dungeon Master. 🐉 I'm in <strong>offline Rules Engine mode</strong>, so use direct commands like <code>encounter level 5 hard undead</code>, <code>character level 3 tiefling warlock</code>, <code>npc innkeeper</code> or <code>roll 4d6kh3</code>. Add an API key to unlock full natural language.");
  }
  await loadLibrary(); await loadCombat(); connect();
}
init();

/* ------------------------------------------------------------ embers */
(function embers() {
  const c = $('#embers'), x = c.getContext('2d'); let w, h, ps = [];
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const resize = () => { w = c.width = innerWidth; h = c.height = innerHeight; }; resize(); addEventListener('resize', resize);
  const spawn = (init) => ({ x: Math.random() * w, y: init ? Math.random() * h : h + 10, r: 0.6 + Math.random() * 2, vy: 0.2 + Math.random() * 0.7, vx: (Math.random() - .5) * .3, a: .2 + Math.random() * .6, hue: 20 + Math.random() * 30, ph: Math.random() * 6.28 });
  for (let i = 0; i < 70; i++) ps.push(spawn(true));
  (function tick(t) {
    if (!document.hidden) {
      x.clearRect(0, 0, w, h);
      for (const p of ps) {
        p.y -= p.vy; p.x += p.vx + Math.sin(t / 900 + p.ph) * .25; if (p.y < -10) Object.assign(p, spawn(false));
        const al = p.a * Math.min(1, p.y / (h * .5));
        x.beginPath(); x.fillStyle = `hsla(${p.hue},100%,60%,${Math.max(0, al)})`; x.shadowColor = `hsl(${p.hue},100%,55%)`; x.shadowBlur = 8; x.arc(p.x, p.y, p.r, 0, 6.28); x.fill();
      }
    }
    requestAnimationFrame(tick);
  })(0);
})();
