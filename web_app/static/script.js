/* X Spaces Downloader — frontend logic */

let ws = null;
let totalSegments = 0;

// ── Transcribe checkbox toggle ────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const chk = document.getElementById('transcribe-chk');
  const opts = document.getElementById('transcribe-opts');
  chk.addEventListener('change', () => {
    opts.classList.toggle('hidden', !chk.checked);
  });

  document.getElementById('url-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') startDownload();
  });
});

// ── Entry point ───────────────────────────────────────────────────────────────

function startDownload() {
  const urlInput = document.getElementById('url-input');
  const url = urlInput.value.trim();
  const transcribe = document.getElementById('transcribe-chk').checked;
  const transcribeModel = document.getElementById('model-select').value;

  clearError();

  if (!url) { showError('Please enter a Space URL.'); return; }
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
    body: JSON.stringify({ url, transcribe, transcribe_model: transcribeModel }),
  })
    .then(r => {
      if (!r.ok) return r.json().then(d => { throw new Error(d.detail || 'Server error'); });
      return r.json();
    })
    .then(({ job_id }) => openWebSocket(job_id))
    .catch(err => { showError(err.message); setButtonState(false); });
}

// ── WebSocket ─────────────────────────────────────────────────────────────────

function openWebSocket(jobId) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws/${jobId}`);
  ws.onmessage = e => handleEvent(JSON.parse(e.data));
  ws.onerror   = ()  => showError('WebSocket connection lost.');
}

function handleEvent(msg) {
  switch (msg.type) {

    case 'ping': break;

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
      const isTranscribing = document.getElementById('transcribe-chk').checked;
      const pct = isTranscribing ? 75 : 100;
      setProgress(pct, isTranscribing ? 'Audio ready — transcribing…' : 'Complete', !isTranscribing);

      addLog(`✓ Audio: ${filename} (${size_mb} MB)`, 'ok');
      addFileRow('audio', '🎵 Audio', filename, url, `${size_mb} MB · MP3`);
      document.getElementById('done-section').classList.remove('hidden');

      if (!isTranscribing) setButtonState(false);
      break;
    }

    case 'transcribe_start':
      setProgress(78, 'Transcribing with Whisper…');
      break;

    case 'transcript_done': {
      const { filename, url } = msg.data;
      setProgress(88, 'Transcript ready — cleaning…');
      addLog(`✓ Transcript: ${filename}`, 'ok');
      addFileRow('transcript', '📄 Transcript', filename, url, 'TXT');
      break;
    }

    case 'clean_done': {
      const { filename, url } = msg.data;
      setProgress(94, 'Generating summary…');
      addLog(`✓ Clean transcript: ${filename}`, 'ok');
      addFileRow('clean', '✏️ Clean', filename, url, 'TXT');
      break;
    }

    case 'summary_done': {
      const { filename, url } = msg.data;
      setProgress(100, 'Complete', true);
      addLog(`✓ Summary: ${filename}`, 'ok');
      addFileRow('summary', '📝 Summary', filename, url, 'TXT');
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

function addFileRow(type, label, filename, url, meta) {
  const container = document.getElementById('output-files');
  const row = document.createElement('div');
  row.className = 'file-row';
  row.innerHTML = `
    <span class="file-tag ${type}">${label}</span>
    <a href="${url}" class="btn-success" download="${filename}" style="padding:0.4rem 0.875rem;font-size:0.82rem;">
      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
      Download
    </a>
    <span class="file-meta">${filename} · ${meta}</span>`;
  container.appendChild(row);
}

function addLog(text, cls = '') {
  const log = document.getElementById('log');
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
  document.getElementById('output-files').innerHTML = '';
  document.getElementById('log').innerHTML = '';
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
