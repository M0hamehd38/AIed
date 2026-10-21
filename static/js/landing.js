'use strict';
const $ = s => document.querySelector(s);
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const smooth = x => x * x * (3 - 2 * x);
const PW = 1670, PH = 941, STOPS = 7;
let FW = 1280, FH = 720, PORT = false;   // stage size; phones in portrait get a tall stage

// ---------- scene ----------
const ICONS = {
  cal:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"><rect x="3" y="5" width="18" height="16" rx="3"/><path d="M3 10h18M8 3v4M16 3v4M7 14h2M11 14h2M15 14h2M7 17h2M11 17h2"/></svg>',
  brain:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5c-1.6-1.8-5.3-1.1-5.3 1.9-2.3.4-3 3.3-1.3 4.8-1.5 1.8-.3 4.7 2.1 4.8.3 2 2.9 3.1 4.5 1.6 1.6 1.5 4.2.4 4.5-1.6 2.4-.1 3.6-3 2.1-4.8 1.7-1.5 1-4.4-1.3-4.8 0-3-3.7-3.7-5.3-1.9zM12 4.5V19M9 9.5c1 .3 2 .3 3-.5M15 13c-1-.3-2-.2-3 .6"/></svg>',
  mic:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>',
  doc:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"><path d="M6 3h9l4 4v14H6z"/><path d="M9 11h7M9 14h7M9 17h5"/></svg>',
  db:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9"><ellipse cx="12" cy="5.5" rx="7" ry="2.5"/><path d="M5 5.5v13c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5v-13M5 12c0 1.4 3.1 2.5 7 2.5s7-1.1 7-2.5"/></svg>',
  chart:'<svg viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round"><path d="M4 20V4M4 20h16M8 16v-4M12 16V9M16 16v-6M7 9l4-3 3 2 5-4"/></svg>',
};
const BLUE = {c1:'rgba(46,92,230,.9)', c2:'rgba(26,48,150,.92)', bd:'rgba(120,175,255,.85)', gl:'rgba(70,140,255,.7)', a1:'#7cc0ff', a2:'#2b63ff'};
const TEAL = {c1:'rgba(20,150,170,.9)', c2:'rgba(18,70,130,.92)', bd:'rgba(110,230,240,.85)', gl:'rgba(40,210,230,.6)', a1:'#7af0f0', a2:'#0ab3c6'};
const PURP = {c1:'rgba(110,70,230,.9)', c2:'rgba(56,40,160,.92)', bd:'rgba(185,155,255,.85)', gl:'rgba(150,100,255,.65)', a1:'#c9a4ff', a2:'#7c3aed'};
const CARDS = [
  ['cal', 'مدیریت کلاس', 'برنامه‌ریزی، حضور و غیاب<br>و مدیریت هوشمند جلسات', BLUE, 1],
  ['brain', 'تحلیل یادگیری', 'شناسایی سطح فهم و<br>الگوهای یادگیری هر دانشجو', BLUE, -1],
  ['mic', 'شنود و تحلیل زنده کلاس', 'درک لحظه‌ای فضای کلاس و<br>کمک به استاد در روند برگزاری', PURP, 1],
  ['doc', 'محتوای آموزشی', 'تولید و ارائه محتوای متناسب<br>با سطح و نیاز دانشجویان', TEAL, -1],
  ['db', 'پایگاه داده', 'ذخیره و تحلیل<br>داده‌های آموزشی', TEAL, 1],
  ['chart', 'گزارش‌ها و داده‌ها', 'تحلیل دقیق عملکرد و پیشرفت<br>دانشجویان و کلاس‌ها', PURP, -1],
];
const stage = $('#stage');
const cards = CARDS.map(([ic, t, d, c, side], i) => {
  const el = document.createElement('div'); el.className = 'o';
  el.innerHTML = `<div class="card" style="--c1:${c.c1};--c2:${c.c2};--bd:${c.bd};--gl:${c.gl};--a1:${c.a1};--a2:${c.a2}"><div class="ic">${ICONS[ic]}</div><div><h3>${t}</h3><p>${d}</p></div></div>`;
  stage.appendChild(el); return {el, side, i};
});
const bokeh = [];
const BK = ['rgba(120,200,255,', 'rgba(150,120,255,', 'rgba(90,150,255,', 'rgba(255,190,120,'];
for (let i = 0; i < 18; i++) {
  const el = document.createElement('div'); el.className = 'o';
  const r = k => Math.abs((Math.sin(i * k) * 43758.5453) % 1), sz = 10 + r(5.17) * 34, col = BK[i % 4];
  el.innerHTML = `<div class="bk" style="width:${sz}px;height:${sz}px;margin:${-sz / 2}px 0 0 ${-sz / 2}px;background:radial-gradient(circle,${col}.85),${col}.25) 45%,${col}0) 70%)"></div>`;
  stage.appendChild(el);
  bokeh.push({el, x:(r(12.9898) - .5) * 2200, y:(r(78.233) - .5) * 1300, z0:r(39.425) * 3200});
}
$('#dots').innerHTML = ['ابتدا', ...CARDS.map(c => c[1]), 'تخته'].map((l, i) => `<button data-go="${i}" aria-label="${l}"><i></i></button>`).join('');

const els = {cls:$('#cls'), scr:$('#scr'), head:$('#headline'), fg:$('#fgroup'), eyeL:$('#eyeL'), eyeR:$('#eyeR'), steam:$('#steam'), stats:$('#stats'), chev:$('#chev'), dots:[...document.querySelectorAll('#dots button')], menu:[...document.querySelectorAll('.menu button')]};
// write a style only when its value changes: most frames touch few properties
const set = (el, prop, v) => { const c = el._s || (el._s = {}); if (c[prop] !== v) { c[prop] = v; el.style[prop] = v; } };
const PLACE = (el, cx, cy, k) => set(el, 'transform', `translate(${(FW / 2 - cx * k).toFixed(2)}px, ${(FH / 2 - cy * k).toFixed(2)}px) scale(${k.toFixed(4)})`);
const farImg = $('#clsFar');

function render(D, t, speed) {
  const pass = clamp(D, 0, 1);
  // classroom: down the middle toward the big screen
  const zc = 1.3 * Math.pow(2.2 / 1.3, clamp(D, 0, 7) / 7) * (1 + 0.006 * Math.sin(t * .9));
  const q = smooth(clamp(D / 7, 0, 1));
  let cx = 835 + 195 * q + Math.sin(t * .5) * 3, cy = 410 - 5 * q + Math.cos(t * .6) * 2;
  const kc = PORT ? FH / PH : (FW / PW) * zc;   // portrait: the photo already fills the height, so the cards carry the motion
  const hw = FW / 2 / kc, hh = FH / 2 / kc; cx = clamp(cx, hw, PW - hw); cy = clamp(cy, hh, Math.max(hh, Math.min(PH - hh, 782 - hh)));
  PLACE(els.cls, cx, cy, kc); PLACE(els.scr, cx, cy, kc);
  const foc = smooth(clamp((D - 0.08) / 0.75, 0, 1));
  set(farImg, 'opacity', (1 - foc).toFixed(3));
  // fly through the gap between the bot (with its desk) and the headline
  const sp = smooth(pass), pr = Math.pow(pass, 1.35), sc = 1 + 1.15 * sp, ho = 1 - clamp((pass - 0.5) / 0.38, 0, 1), hb = (Math.round(clamp(pass - .2, 0, 1) * 10) / 2).toFixed(1);
  const hl = (e, tx, ty, s2) => { set(e, 'transform', `translate(${tx.toFixed(1)}px, ${ty.toFixed(1)}px) scale(${s2.toFixed(4)})`); set(e, 'opacity', ho.toFixed(3)); set(e, 'filter', pass > .2 && hb !== '0.0' ? `blur(${hb}px)` : ''); set(e, 'visibility', ho > 0.001 ? '' : 'hidden'); };
  if (PORT) { hl(els.head, 0, -900 * pr, sc * .95); hl(els.fg, 0, 850 * pr, 1 + .9 * sp); }
  else { hl(els.head, 1350 * pr + 22, -150 * pr + 8, sc * .88); hl(els.fg, -760 * pr, 420 * pr, 1 + .9 * sp); }
  if (pass < 1) {
    const g = (0.5 + 0.5 * Math.sin(t * 1.7)).toFixed(2); set(els.eyeL, 'opacity', g); set(els.eyeR, 'opacity', g);
  }
  // feature cards: the current one is sharp, the next ones wait deeper in the room
  const appear = clamp((D - 0.55) / 0.3, 0, 1);
  for (const c of cards) {
    const n = c.i + 1; let zz, op, blur;
    if (D <= n) { zz = (D - n) * 1300; op = clamp((zz + 3300) / 900, 0, 1); blur = clamp(-zz / 210, 0, 9); }
    else { zz = (D - n) * 1100; op = clamp(1 - zz / 480, 0, 1); blur = clamp(zz / 120, 0, 6); }
    op *= appear;
    const x = c.side * (PORT ? 60 : 300), y = [-70, 30, -40, 20, -60, 30][c.i] + Math.sin(t * 1.4 + c.i) * 5;
    const show = op > 0.005 && zz < 860;
    set(c.el, 'display', show ? '' : 'none');
    if (!show) continue;
    // blur in whole-pixel steps, at most 4px: each new radius costs a new raster
    const bq = Math.min(4, Math.round(blur));
    set(c.el, 'transform', `translate3d(${x}px, ${y.toFixed(1)}px, ${zz.toFixed(1)}px) rotateY(${c.side * 12}deg)`);
    set(c.el, 'opacity', op.toFixed(3)); set(c.el, 'filter', bq ? `blur(${bq}px) brightness(${(1 - bq * .04).toFixed(2)})` : '');
    set(c.el, 'zIndex', String(Math.round(10000 + zz)));
  }
  for (const b of bokeh) {
    const z2 = ((b.z0 + D * 700 + t * 30) % 3200) - 2600;
    const op = clamp((z2 + 2600) / 900, 0, 1) * clamp((700 - z2) / 400, 0, 1) * (0.22 + 0.25 * Math.abs(Math.sin(t * .8 + b.z0))) * appear;
    if (op < 0.004) { set(b.el, 'opacity', '0'); continue; }
    set(b.el, 'transform', `translate3d(${b.x.toFixed(0)}px, ${b.y.toFixed(0)}px, ${z2.toFixed(0)}px)`); set(b.el, 'opacity', op.toFixed(3));
  }
  // opening UI and progress
  const hero = 1 - clamp(D / 0.25, 0, 1);
  set(els.stats, 'opacity', hero.toFixed(3)); set(els.stats, 'transform', `translateY(${((1 - hero) * 40).toFixed(1)}px)`); set(els.stats, 'visibility', hero > 0 ? '' : 'hidden');
  set(els.chev, 'opacity', hero.toFixed(3)); set(els.chev, 'visibility', hero > 0 ? '' : 'hidden');
  if (hero > 0) set(els.chev, 'transform', `translateY(${(Math.abs(Math.sin(t * 2.4)) * 6).toFixed(1)}px)`);
  const at = Math.round(D);
  els.dots.forEach((d, i) => d.classList.toggle('on', i === at));
  els.menu[0].classList.toggle('on', D < 0.5); els.menu[1].classList.toggle('on', D >= 0.5 && D < 6.5);
  const bo = clamp((D - 6.4) / 0.55, 0, 1);
  set(els.scr, 'opacity', bo.toFixed(3)); set(els.scr, 'display', bo > 0 ? '' : 'none');
}

// ---------- scroll drives the camera ----------
const frame = $('#frame');
// where the opening pieces sit on each stage: [left, top, width, height]
const LAYOUT = {
  land:{headline:[666.9, 103.2, 554.6, 339.7], robot:[57.5, 120.6, 466.1, 446.4], desk:[-61, 476.1, 1401.5, 249.9], origin:'400px 560px'},
  port:{headline:[50, 150, 620, 380], robot:[96, 560, 528, 506], desk:[-90, 958, 900, 340], origin:'360px 1060px'},
};
function fit() {
  const vw = innerWidth, vh = innerHeight;
  PORT = vw / vh < 0.9; [FW, FH] = PORT ? [720, 1280] : [1280, 720];
  frame.style.width = FW + 'px'; frame.style.height = FH + 'px';
  const L = LAYOUT[PORT ? 'port' : 'land'];
  // on windows narrower than the stage, its sides are cropped: keep the headline clear of the right edge
  const crop = PORT ? 0 : Math.max(0, (FW - vw / Math.max(vw / FW, vh / FH)) / 2);
  for (const id of ['headline', 'robot', 'desk']) { const [l, t, w, h] = L[id], e = $('#' + id); Object.assign(e.style, {left:l - (id === 'headline' ? crop : 0) + 'px', top:t + 'px', width:w + 'px', height:h + 'px'}); }
  els.fg.style.transformOrigin = L.origin;
  els.head.style.fontSize = (L.headline[2] / 554.6 * 16).toFixed(2) + 'px';
  document.querySelectorAll('#stage .o').forEach(o => { o.style.left = FW / 2 + 'px'; o.style.top = FH * .48 + 'px'; });
  els.stats.style.display = PORT ? 'none' : '';
  frame.style.setProperty('--cs', PORT ? .72 : .8);
  Object.assign(els.chev.style, PORT ? {left:FW / 2 - 25 + 'px', top:FH - 90 + 'px'} : {left:'615px', top:'672px'});
  const s = Math.max(vw / FW, vh / FH);
  frame.style.transform = `translate(-50%, -50%) scale(${s})`;
}
addEventListener('resize', fit); fit();
const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
const target = () => clamp(scrollY / innerHeight, 0, STOPS);
let D = target(), last = -1;
function tick(now) {
  const t = reduce ? 0 : now / 1000, goal = target();
  D += (goal - D) * (reduce ? 1 : 0.11);
  if (Math.abs(goal - D) < 0.0005) D = goal;
  render(D, t, clamp(Math.abs(goal - D) * 1.2, 0, 1));
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);
function go(i) { scrollTo({top:i * innerHeight, behavior:reduce ? 'auto' : 'smooth'}); }
document.addEventListener('click', e => {
  const g = e.target.closest('[data-go]'); if (g) { e.preventDefault(); go(+g.dataset.go); return; }
  const a = e.target.closest('[data-auth]'); if (a) { openAuth(a.dataset.auth); return; }
  const n = e.target.closest('[data-info]'); if (n) { openInfo(n.dataset.info); return; }
  if (e.target.id === 'modalBg' || e.target.closest('.x')) closeModal();
});
addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });

// ---------- sign in / sign up: the forms are rendered by the server (with CSRF) ----------
const bg = $('#modalBg'), modal = $('#modal');
let lastFocus = null;
function show(node) {
  lastFocus = document.activeElement;
  modal.replaceChildren(node); bg.classList.add('open');
  (modal.querySelector('.err:not(:empty)') ? modal.querySelector('input[aria-invalid=true]') || modal.querySelector('input') : modal.querySelector('input') || modal.querySelector('button')).focus();
}
function closeModal() { if (!bg.classList.contains('open')) return; bg.classList.remove('open'); if (lastFocus) lastFocus.focus(); }
const tpl = id => document.getElementById(id).content.cloneNode(true);
function openAuth(mode) { show(tpl(mode === 'signup' ? 'tpl-signup' : 'tpl-login')); }
function openInfo(k) { show(tpl('tpl-' + k)); }
const opened = document.body.dataset.openAuth;
if (opened === 'login' || opened === 'signup') openAuth(opened);

// mouse wheel: rolling the wheel forward (away from you) moves the camera forward into the class
addEventListener('wheel', e => {
  if (e.ctrlKey || document.getElementById('modalBg').classList.contains('open')) return;
  e.preventDefault();
  const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? innerHeight : 1;
  scrollBy(0, -e.deltaY * unit);
}, {passive: false});
