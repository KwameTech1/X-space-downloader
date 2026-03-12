/* X Spaces Downloader — frontend logic */

let ws = null;
let totalSegments = 0;

// ── Entry point ───────────────────────────────────────────────────────────────

function startDownload() {
  const urlInput = document.getElementById('url-input');
  const url = urlInput.value.trim();

  clearError();

  if (!url) {
    showError('Please enter a Space URL.');
    return;
  }
  if (!/x\.com\/i\/spaces\/|twitter\.com\/i\/spaces\//.test(url)) {
    showError('Please enter a valid X / Twitter Space URL.');
    return;
  }

  setButtonState(true);
  showProgressCard();
  resetProgress();

  fetch('/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
    .then(r => {
      if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Server error'); });
      return r.json();
    })
    .then(({ job_id }) => openWebSocket(job_id))
    .catch(err => {
      showError(err.message);
      setButtonState(false);
    });
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function openWebSocket(jobId) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${jobId}`);

  ws.onmessage = e => handleEvent(JSON.parse(e.data));
  ws.onerror   = ()  => showError('WebSocket connection lost.');
  ws.onclose   = ()  => {};
}

function handleEvent(msg) {
  switch (msg.type) {

    case 'ping':
      break;

    case 'log':
      addLog(msg.data);
      break;

    case 'metadata': {
      const m = msg.data;
      document.getElementById('meta-title').textContent    = m.title    || '—';
      document.getElementById('meta-host').textContent     = m.host     || '—';
      document.getElementById('meta-duration').textContent = m.duration || '—';
      document.getElementById('metadata-section').classList.remove('hidden');
      setProgress(10, 'Metadata fetched');
      break;
    }

    case 'segments_total':
      totalSegments = msg.data;
      setProgress(15, `Found ${totalSegments} segments`);
      break;

    case 'download_done': {
      const { downloaded, total } = msg.data;
      setProgress(65, `Downloaded ${downloaded} / ${total} segments`);
      break;
    }

    case 'done': {
      const { filename, size_mb, url } = msg.data;
      setProgress(100, 'Complete', true);
      addLog(`✓ ${filename} — ${size_mb} MB`, 'ok');

      const link = document.getElementById('file-link');
      link.href = url;
      link.setAttribute('download', filename);
      document.getElementById('file-meta').textContent = `${size_mb} MB · MP3`;
      document.getElementById('done-section').classList.remove('hidden');
      setButtonState(false);
      break;
    }

    case 'error':
      addLog('Error: ' + msg.data, 'error');
      showError(msg.data);
      setButtonState(false);
      setProgress(0, 'Failed');
      break;
  }
}

// ── UI helpers ────────────────────────────────────────────────────────────────

function setProgress(pct, label, done = false) {
  const fill = document.getElementById('progress-fill');
  fill.style.width = pct + '%';
  fill.classList.toggle('done', done);
  document.getElementById('progress-pct').textContent   = pct + '%';
  document.getElementById('progress-label').textContent = label;
}

function addLog(text, cls = '') {
  const log = document.getElementById('log');
  log.classList.remove('hidden');
  const p = document.createElement('p');
  if (cls) p.className = cls;
  p.textContent = '› ' + text;
  log.appendChild(p);
  log.scrollTop = log.scrollHeight;
}

function showProgressCard() {
  document.getElementById('progress-card').classList.remove('hidden');
}

function resetProgress() {
  document.getElementById('metadata-section').classList.add('hidden');
  document.getElementById('done-section').classList.add('hidden');
  document.getElementById('log').innerHTML = '';
  document.getElementById('log').classList.remove('hidden');
  totalSegments = 0;
  setProgress(3, 'Starting…');
}

function showError(msg) {
  const el = document.getElementById('error-msg');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function clearError() {
  document.getElementById('error-msg').classList.add('hidden');
}

function setButtonState(disabled) {
  document.getElementById('download-btn').disabled = disabled;
}

// ── Keyboard shortcut ─────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('url-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') startDownload();
  });
});
