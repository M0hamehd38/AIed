'use strict';
// Teacher's live session: the server is the source of truth. Buttons POST, the WebSocket pushes the
// new state (answer counts included); if the socket drops, the page polls until it is back.
(function () {
  const root = document.getElementById('live');
  if (!root) return;
  const FA = '۰۱۲۳۴۵۶۷۸۹';
  const fa = v => String(v).replace(/\d/g, d => FA[d]);
  const pct = x => fa(Math.round(x * 100)) + '٪';
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const card = document.getElementById('qCard'), wsTag = document.getElementById('wsState');
  const STATE = {open:['در حال پاسخ', 'green'], paused:['متوقف', 'orange'], closed:['بسته‌شده', 'gray']};

  function render(d) {
    document.getElementById('kTotal').textContent = fa(d.answered_total || 0);
    const q = d.question;
    if (!q) { card.innerHTML = '<div class="card-head"><h2>سؤالی پرسیده نشده</h2></div><p class="muted">از «انتخاب سؤال» در پایین، مبحث و سپس سؤال را انتخاب کنید و «پرسیدن» را بزنید.</p>'; return; }
    const n = q.n || 0, ok = n ? q.counts[q.correct] / n : 0, [st, stc] = STATE[q.state] || ['', 'gray'];
    const ins = q.insight;
    card.innerHTML = `<div class="card-head"><h2>سؤال ${fa(q.number)}</h2><span class="tag ${stc}">${st}</span>${q.late ? '<span class="tag gray">پایان کلاس</span>' : ''}${(q.concepts || []).map(c => `<span class="tag gray">${esc(c)}</span>`).join('')}
        <div class="end">${q.state === 'open' ? '<button class="btn" data-ctl="paused">مکث</button>' : ''}${q.state === 'paused' ? '<button class="btn" data-ctl="open">ادامه</button>' : ''}${q.state !== 'closed' ? '<button class="btn primary" data-ctl="closed">بستن سؤال</button>' : ''}</div></div>
      <p style="font-weight:600;margin-top:0"><bdi>${esc(q.text)}</bdi></p>
      <div class="kpis"><div><b>${fa(n)}</b>پاسخ</div><div><b>${n ? pct(ok) : '—'}</b>درست‌پاسخی</div><div><b>${fa(Math.max(0, (d.class_size || 0) - n))}</b>بدون پاسخ</div></div>
      ${q.options.map((o, i) => { const c = q.counts[i] || 0, good = i === q.correct; return `<div class="opt-bar"><div class="top"><span>${good ? '✓ ' : ''}<bdi>${esc(o)}</bdi>${good ? ' <span class="muted small">(گزینه‌ی درست)</span>' : ''}</span><span>${n ? pct(c / n) : '۰٪'} (${fa(c)} نفر)</span></div><div class="progress"><i style="width:${n ? Math.round(c / n * 100) : 0}%;background:${good ? 'var(--green)' : 'var(--blue)'}"></i></div></div>`; }).join('')}
      ${ins ? `<div class="alert ${ins.kind === 'gray' ? '' : ins.kind} mt"><span class="ic" ${ins.kind === 'gray' ? 'style="background:var(--muted)"' : ''}>${ins.kind === 'green' ? '✓' : ins.kind === 'gray' ? '…' : ins.kind === 'orange' ? '!' : 'i'}</span><div><b>${esc(ins.title)}</b><p>${esc(ins.text)}</p></div></div>` : ''}`;
  }

  async function post(url, body) {
    const r = await fetch(url, {method:'POST', headers:{'X-CSRFToken':csrf, 'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams(body), credentials:'same-origin'});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast(d.error || 'انجام نشد. دوباره امتحان کنید.'); return; }
    render(d);
  }
  function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; document.getElementById('toasts').appendChild(t); setTimeout(() => t.remove(), 3200); }

  document.addEventListener('click', e => {
    const ask = e.target.closest('[data-ask]');
    if (ask) { post(root.dataset.askUrl, {question:ask.dataset.ask, late:document.getElementById('lateFlag').checked ? '1' : '0'}); window.scrollTo({top:0, behavior:'smooth'}); return; }
    const ctl = e.target.closest('[data-ctl]');
    if (ctl) post(root.dataset.controlUrl, {state:ctl.dataset.ctl});
  });

  // live updates
  let poll = null;
  const startPolling = () => { if (!poll) poll = setInterval(() => fetch(root.dataset.stateUrl, {credentials:'same-origin'}).then(r => r.ok && r.json()).then(d => d && render(d)), 3000); };
  const stopPolling = () => { clearInterval(poll); poll = null; };
  function connect(delay) {
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + root.dataset.ws);
    ws.onopen = () => { stopPolling(); wsTag.textContent = 'لحظه‌ای'; wsTag.className = 'tag green'; delay = 1000; };
    ws.onmessage = e => render(JSON.parse(e.data));
    ws.onclose = () => { wsTag.textContent = 'اتصال دوباره…'; wsTag.className = 'tag orange'; startPolling(); setTimeout(() => connect(Math.min(delay * 2, 15000)), delay); };
  }
  render(JSON.parse(document.getElementById('liveState').textContent));
  connect(1000);
})();
