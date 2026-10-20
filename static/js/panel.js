'use strict';
// Small progressive enhancements: every page works as plain HTML; this adds the theme switch,
// the mobile menu, evidence dialogs and auto-submitting selects.
const $ = s => document.querySelector(s);
const THEME_ICONS = {
  sun: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  moon: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/></svg>',
};
function paintThemeBtn() {
  const dark = document.documentElement.dataset.theme === 'dark', b = $('#themeBtn');
  if (!b) return;
  b.innerHTML = dark ? THEME_ICONS.sun : THEME_ICONS.moon;
  b.setAttribute('aria-label', dark ? 'حالت روز' : 'حالت شب'); b.title = dark ? 'حالت روز' : 'حالت شب';
}

let lastFocus = null;
function openModal(node) {
  lastFocus = document.activeElement;
  const m = $('#modal'); m.replaceChildren(node);
  $('#modalBg').classList.add('open');
  (m.querySelector('input:not([type=hidden]),textarea') || m.querySelector('.icon-btn')).focus();
}
function closeModal() { $('#modalBg').classList.remove('open'); if (lastFocus) lastFocus.focus(); }
function modalShell(title) {
  const wrap = document.createElement('div');
  wrap.innerHTML = '<div class="modal-head"><h2 id="modalTitle"></h2><button class="icon-btn" data-act="closeModal" aria-label="بستن">×</button></div><div class="modal-body"></div>';
  wrap.querySelector('h2').textContent = title;
  return wrap;
}
function closeMenu() { $('#sidebar').classList.remove('open'); $('#backdrop').classList.remove('open'); }

const ACT = {
  toggleTheme() {
    const t = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('classyar-theme', t); } catch (e) {}
    paintThemeBtn();
  },
  openMenu() { $('#sidebar').classList.add('open'); $('#backdrop').classList.add('open'); $('#nav .nav-btn').focus(); },
  closeMenu,
  closeModal,
  modalBg(el, e) { if (e.target === el) closeModal(); },
  // evidence is rendered by the server; the dialog only shows it
  async evidence(el) {
    const res = await fetch(`${document.body.dataset.evidenceUrl || '/t/evidence/'}?ev=${encodeURIComponent(el.dataset.ev)}`, {credentials: 'same-origin'});
    if (!res.ok) { toast('شواهد بارگذاری نشد.'); return; }
    const box = document.createElement('div'); box.innerHTML = await res.text();
    const title = box.querySelector('[data-title]');
    const shell = modalShell(title ? title.dataset.title : 'شواهد');
    shell.querySelector('.modal-body').append(...box.childNodes);
    openModal(shell);
  },
  // forms kept in <template> elements open in the dialog
  dialog(el) {
    const tpl = document.getElementById(el.dataset.tpl);
    const shell = modalShell(tpl.dataset.title);
    shell.querySelector('.modal-body').append(tpl.content.cloneNode(true));
    openModal(shell);
  },
  copyExport() {
    const pre = $('#exportJson');
    if (navigator.clipboard) navigator.clipboard.writeText(pre.textContent).then(() => toast('کپی شد.'));
  },
};
function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; $('#toasts').appendChild(t); setTimeout(() => t.remove(), 3200); }

document.addEventListener('click', e => {
  const el = e.target.closest('[data-act]');
  if (el && !el.disabled && ACT[el.dataset.act]) { if (el.tagName === 'A' || el.tagName === 'BUTTON' && el.type !== 'submit') e.preventDefault(); e.stopPropagation(); ACT[el.dataset.act](el, e); return; }
  const row = e.target.closest('[data-href]');
  if (row && !e.target.closest('a,button,input,select')) location.href = row.dataset.href;
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { if ($('#modalBg').classList.contains('open')) closeModal(); else closeMenu(); }
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('[data-act]:not(button):not(a),[data-href]')) {
    e.preventDefault();
    if (e.target.dataset.href) location.href = e.target.dataset.href; else ACT[e.target.dataset.act](e.target, e);
  }
});
document.addEventListener('change', e => { if (e.target.matches('[data-autosubmit]')) e.target.form.submit(); });
document.querySelectorAll('#toasts .toast').forEach(t => setTimeout(() => t.remove(), 4200));
document.querySelectorAll('[data-href],tr[data-act]').forEach(el => { el.tabIndex = 0; });
paintThemeBtn();
