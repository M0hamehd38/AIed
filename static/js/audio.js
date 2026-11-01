'use strict';
// Teacher's listening page. The browser records short chunks; each is sent to the panel, turned into text
// on the university's server and dropped. Only the text lines come back. Nothing is recorded until
// the teacher presses «شروع شنود», and «توقف شنود» stops the microphone at once.
(function () {
  const app = document.getElementById('audioApp');
  if (!app) return;
  const CHUNK_MS = 8000;
  const FA = '۰۱۲۳۴۵۶۷۸۹', fa = v => String(v).replace(/\d/g, d => FA[d]);
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const $ = id => document.getElementById(id);
  const startBtn = $('recStart'), stopBtn = $('recStop'), stateTag = $('recState'), box = $('transcript'), cv = $('wave');
  const LABELS = window.SIG_LABELS || {};
  const tag = k => `<span class="tag ${LABELS[k] ? LABELS[k][1] : 'gray'}">${LABELS[k] ? LABELS[k][0] : k}</span>`;
  document.querySelectorAll('[data-sig]').forEach(el => { el.outerHTML = tag(el.dataset.sig); });
  box.scrollTop = box.scrollHeight;

  const TYPES = ['audio/webm;codecs=opus', 'audio/ogg;codecs=opus', 'audio/webm', 'audio/mp4'];
  let stream = null, recorder = null, timer = null, listening = false, queue = Promise.resolve(), raf = 0, analyser = null;

  function setState(text, cls) { stateTag.textContent = text; stateTag.className = 'tag ' + cls; }
  function toast(msg) { const t = document.createElement('div'); t.className = 'toast'; t.textContent = msg; $('toasts').appendChild(t); setTimeout(() => t.remove(), 4000); }

  function addLine(l) {
    const empty = $('tEmpty'); if (empty) empty.remove();
    const div = document.createElement('div'); div.className = 'tline';
    div.innerHTML = `<time>${fa(l.time)}</time><bdi>${esc(l.text)}</bdi> ${l.signals.map(tag).join(' ')}`;
    box.appendChild(div); box.scrollTop = box.scrollHeight;
  }
  function setCounts(c) { for (const k in c) { const el = $('cnt-' + k); if (el) el.textContent = fa(c[k]); } }

  async function send(blob) {
    if (!blob.size) return;
    const r = await fetch(app.dataset.chunkUrl, {method:'POST', credentials:'same-origin', headers:{'X-CSRFToken':csrf, 'Content-Type':blob.type}, body:blob});
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { toast(d.error || 'ارسال صدا انجام نشد.'); if (r.status === 503 || r.status === 403) stop(); return; }
    if (d.line) addLine(d.line);
    if (d.counts) setCounts(d.counts);
  }

  // one recorder per chunk, so every chunk is a complete, playable file on its own
  function recordChunk(type) {
    if (!listening) return;
    recorder = new MediaRecorder(stream, type ? {mimeType:type, audioBitsPerSecond:32000} : undefined);
    const parts = [];
    recorder.ondataavailable = e => { if (e.data.size) parts.push(e.data); };
    recorder.onstop = () => { const blob = new Blob(parts, {type:(recorder.mimeType || type || 'audio/webm')}); queue = queue.then(() => send(blob)).catch(() => {}); recordChunk(type); };
    recorder.start();
    timer = setTimeout(() => { if (recorder.state !== 'inactive') recorder.stop(); }, CHUNK_MS);
  }

  function drawLevel() {
    const g = cv.getContext('2d'), W = cv.width, H = cv.height, buf = new Uint8Array(analyser ? analyser.frequencyBinCount : 0);
    if (analyser) analyser.getByteFrequencyData(buf);
    g.clearRect(0, 0, W, H);
    const bars = 60, color = getComputedStyle(document.documentElement).getPropertyValue(listening ? '--blue' : '--line') || '#4169f5';
    for (let i = 0; i < bars; i++) {
      const v = analyser ? buf[Math.floor(i * buf.length / bars)] / 255 : 0, h = Math.max(2, v * H);
      g.fillStyle = color.trim(); g.fillRect(W - (i + 1) * 10, (H - h) / 2, 6, h);
    }
    raf = listening ? requestAnimationFrame(drawLevel) : 0;
  }

  async function start() {
    if (!window.MediaRecorder || !navigator.mediaDevices) { toast('این مرورگر ضبط صدا را پشتیبانی نمی‌کند.'); return; }
    try { stream = await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true, noiseSuppression:true, channelCount:1}}); }
    catch (e) { toast('دسترسی به میکروفون داده نشد.'); return; }
    listening = true; startBtn.hidden = true; stopBtn.hidden = false; setState('● در حال شنود', 'red');
    try { const ctx = new AudioContext(); analyser = ctx.createAnalyser(); analyser.fftSize = 256; ctx.createMediaStreamSource(stream).connect(analyser); } catch (e) { analyser = null; }
    drawLevel();
    recordChunk(TYPES.find(t => MediaRecorder.isTypeSupported(t)));
  }
  function stop() {
    if (!listening) return;
    listening = false; clearTimeout(timer);
    if (recorder && recorder.state !== 'inactive') recorder.stop();   // the last chunk is still sent
    if (stream) stream.getTracks().forEach(t => t.stop());             // the microphone light goes off
    startBtn.hidden = false; stopBtn.hidden = true; setState('متوقف', 'gray'); analyser = null;
  }
  startBtn.addEventListener('click', start);
  stopBtn.addEventListener('click', stop);
  addEventListener('pagehide', stop);
  drawLevel();
})();
