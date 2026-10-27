'use strict';
// Student phone page. Answers go over HTTP (so none is lost on a flaky connection);
// the WebSocket only tells the page when the question changes. Without it, the page polls.
(function () {
  const app = document.getElementById('app'), box = document.getElementById('qBox');
  const conn = document.getElementById('conn'), connText = document.getElementById('connText');
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const FA = '۰۱۲۳۴۵۶۷۸۹', fa = v => String(v).replace(/\d/g, d => FA[d]);
  // letters, not digits: many answers are numbers themselves
  const KEYS = ['الف', 'ب', 'ج', 'د', 'هـ', 'و'];
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  let state = JSON.parse(document.getElementById('initial').textContent), mine = {}, sending = false;
  if (state.question && state.question.mine != null) mine[state.question.id] = state.question.mine;

  function render() {
    if (!state.live) { box.innerHTML = '<div class="wait-box"><p><b>جلسه پایان یافت.</b></p><p class="muted small">ممنون از همراهی شما.</p></div>'; return; }
    const q = state.question;
    if (!q) { box.innerHTML = '<div class="wait-box"><div class="spin" aria-hidden="true"></div><p>منتظر سؤال استاد…</p></div>'; return; }
    const sel = mine[q.id], open = q.state === 'open';
    const note = q.state === 'paused' ? 'سؤال موقتاً متوقف شده است.' : q.state === 'closed' ? (sel != null ? 'سؤال بسته شد. پاسخ شما ثبت شده است.' : 'سؤال بسته شد.') : sel != null ? '✓ پاسخ شما ثبت شد. تا بسته‌شدن سؤال می‌توانید آن را تغییر دهید.' : 'یک گزینه را انتخاب کنید.';
    box.innerHTML = `<p class="muted small">سؤال ${fa(q.number)}</p><div class="q"><bdi>${esc(q.text)}</bdi></div>
      <div class="opts">${q.options.map((o, i) => `<button class="opt ${sel === i ? 'sel' : ''}" data-i="${i}" ${open ? '' : 'disabled'} aria-pressed="${sel === i}"><span class="k">${KEYS[i] || fa(i + 1)}</span><bdi>${esc(o)}</bdi></button>`).join('')}</div>
      <p class="small ${sel != null && open ? '' : 'muted'}" style="margin-top:12px" role="status">${note}</p>`;
  }

  box.addEventListener('click', async e => {
    const b = e.target.closest('.opt'); if (!b || b.disabled || sending) return;
    const q = state.question, i = +b.dataset.i, prev = mine[q.id];
    mine[q.id] = i; render(); sending = true;
    try {
      const r = await fetch(app.dataset.answerUrl, {method:'POST', credentials:'same-origin', headers:{'X-CSRFToken':csrf, 'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({option:i})});
      const d = await r.json().catch(() => ({}));
      if (!r.ok) { mine[q.id] = prev; if (d.question !== undefined) state = d; render(); box.querySelector('[role=status]').textContent = d.error || 'ثبت نشد؛ دوباره بزنید.'; }
    } catch (err) { mine[q.id] = prev; render(); box.querySelector('[role=status]').textContent = 'اتصال برقرار نیست؛ دوباره بزنید.'; }
    sending = false;
  });

  function update(d) { state = d; if (d.question && d.question.mine != null) mine[d.question.id] = d.question.mine; render(); }
  let poll = null;
  const startPolling = () => { if (!poll) poll = setInterval(() => fetch(app.dataset.stateUrl, {credentials:'same-origin'}).then(r => r.ok ? r.json() : null).then(d => d && update(d)).catch(() => {}), 3000); };
  const stopPolling = () => { clearInterval(poll); poll = null; };
  function connect(delay) {
    let ws;
    try { ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + app.dataset.ws); } catch (e) { startPolling(); return; }
    ws.onopen = () => { stopPolling(); conn.className = 'dot on'; connText.textContent = 'متصل'; delay = 1000; };
    ws.onmessage = e => update(JSON.parse(e.data));
    ws.onclose = () => { conn.className = 'dot wait'; connText.textContent = 'اتصال دوباره…'; startPolling(); if (state.live) setTimeout(() => connect(Math.min(delay * 2, 15000)), delay); };
  }
  render(); connect(1000);
})();
