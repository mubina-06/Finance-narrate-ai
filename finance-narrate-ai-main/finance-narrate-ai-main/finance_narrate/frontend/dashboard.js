// ===== Configuration =====
// In production, set this to your Render backend URL e.g. https://finance-narrate-ai.onrender.com
// In development, use http://localhost:8000
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:8000'
  : 'https://finance-narrate-ai-backend.onrender.com';

// ===== Module-level state =====
let currentFileId = null;
let currentNarrative = null;
let revenueChart = null;
let expenseChart = null;

// ===== DOM references =====
const uploadZone = document.getElementById('upload-zone');
const fileInput = document.getElementById('file-input');
const statusArea = document.getElementById('status-area');
const spinner = document.getElementById('spinner');
const errorBanner = document.getElementById('error-banner');
const errorMessage = document.getElementById('error-message');
const previewSection = document.getElementById('preview-section');
const previewContainer = document.getElementById('preview-table-container');
const chartsSection = document.getElementById('charts-section');
const anomalySection = document.getElementById('anomaly-section');
const anomalyContainer = document.getElementById('anomaly-container');
const narrativeSection = document.getElementById('narrative-section');
const copyBtn = document.getElementById('copy-btn');
const downloadBtn = document.getElementById('download-btn');

// ===== Spinner helpers =====
function showSpinner() {
  spinner.hidden = false;
}

function hideSpinner() {
  spinner.hidden = true;
}

// ===== Error banner =====
function showError(msg) {
  errorMessage.textContent = msg;
  errorBanner.hidden = false;
}

function dismissError() {
  errorBanner.hidden = true;
}

// ===== Status area =====
function setStatus(msg) {
  statusArea.textContent = msg;
}

// ===== Drag-and-drop events =====
uploadZone.addEventListener('dragover', (e) => {
  e.preventDefault();
  uploadZone.classList.add('drag-over');
});

uploadZone.addEventListener('dragleave', () => {
  uploadZone.classList.remove('drag-over');
});

uploadZone.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFile(file);
});

// ===== File input change =====
fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) handleFile(file);
});

// ===== Handle file: upload → analyze → narrative =====
async function handleFile(file) {
  dismissError();
  setStatus(`Uploading "${file.name}"…`);
  showSpinner();

  // --- 8.3: POST /upload ---
  const formData = new FormData();
  formData.append('file', file);

  let uploadData;
  try {
    const res = await fetch(`${API_BASE}/upload`, { method: 'POST', body: formData });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Upload failed (${res.status})`);
    }
    uploadData = await res.json();
  } catch (e) {
    hideSpinner();
    showError(e.message);
    setStatus('');
    return;
  }

  currentFileId = uploadData.file_id;
  setStatus(`Uploaded "${uploadData.filename}" — ${uploadData.row_count} rows. Parsing preview…`);

  // Client-side preview (first 10 rows)
  renderPreview(file);

  hideSpinner();

  // --- 8.4: POST /analyze then POST /generate-narrative ---
  await runAnalysisAndNarrative();
}

// ===== Client-side CSV preview (first 10 rows) =====
function renderPreview(file) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const lines = text.split(/\r?\n/).filter(l => l.trim() !== '');
    const headers = splitCsvLine(lines[0]);
    const rows = lines.slice(1, 11); // first 10 data rows

    let html = '<table><thead><tr>';
    headers.forEach(h => { html += `<th>${escapeHtml(h)}</th>`; });
    html += '</tr></thead><tbody>';

    rows.forEach(line => {
      const cells = splitCsvLine(line);
      html += '<tr>';
      cells.forEach(c => { html += `<td>${escapeHtml(c)}</td>`; });
      html += '</tr>';
    });

    html += '</tbody></table>';
    previewContainer.innerHTML = html;
    previewSection.hidden = false;
  };
  reader.readAsText(file);
}

function splitCsvLine(line) {
  // Simple CSV split respecting quoted fields
  const result = [];
  let current = '';
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      inQuotes = !inQuotes;
    } else if (ch === ',' && !inQuotes) {
      result.push(current.trim());
      current = '';
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ===== 8.4: Analysis + Narrative pipeline =====
async function runAnalysisAndNarrative() {
  if (!currentFileId) return;

  showSpinner();
  setStatus('Running analysis…');

  // POST /analyze/{file_id}
  let metricsData;
  try {
    const res = await fetch(`${API_BASE}/analyze/${currentFileId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Analysis failed (${res.status})`);
    }
    metricsData = await res.json();
  } catch (e) {
    hideSpinner();
    showError(e.message);
    setStatus('Analysis failed.');
    return;
  }

  setStatus('Analysis complete. Generating narrative…');

  // Render charts and anomalies from metrics
  renderRevenueChart(metricsData.monthly_revenue);
  renderExpenseChart(metricsData.top_categories);
  renderAnomalyCards(metricsData.expense_anomalies, metricsData.revenue_dips);
  chartsSection.hidden = false;
  if (metricsData.expense_anomalies.length > 0 || metricsData.revenue_dips.length > 0) {
    anomalySection.hidden = false;
  }

  // POST /generate-narrative/{file_id}
  let narrativeData;
  try {
    const res = await fetch(`${API_BASE}/generate-narrative/${currentFileId}`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || `Narrative generation failed (${res.status})`);
    }
    narrativeData = await res.json();
  } catch (e) {
    hideSpinner();
    showError(e.message);
    setStatus('Narrative generation failed.');
    return;
  }

  hideSpinner();
  currentNarrative = narrativeData;
  setStatus('Report ready.');

  renderNarrativePanel(narrativeData);
  narrativeSection.hidden = false;
  copyBtn.disabled = false;
  downloadBtn.disabled = false;
}

// ===== 8.5: Revenue trend line chart =====
function renderRevenueChart(monthlyRevenue) {
  const labels = monthlyRevenue.map(m => m.month);
  const data = monthlyRevenue.map(m => m.total);

  if (revenueChart) revenueChart.destroy();

  const ctx = document.getElementById('revenue-chart').getContext('2d');
  revenueChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Monthly Revenue',
        data,
        borderColor: '#2b6cb0',
        backgroundColor: 'rgba(43, 108, 176, 0.1)',
        borderWidth: 2,
        pointRadius: 4,
        pointBackgroundColor: '#2b6cb0',
        tension: 0.3,
        fill: true,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: false }
      }
    }
  });
}

// ===== 8.6: Expense breakdown bar chart =====
function renderExpenseChart(topCategories) {
  const labels = topCategories.map(c => c.category);
  const data = topCategories.map(c => c.total_expenses);

  if (expenseChart) expenseChart.destroy();

  const ctx = document.getElementById('expense-chart').getContext('2d');
  expenseChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Total Expenses',
        data,
        backgroundColor: ['#fc8181', '#f6ad55', '#68d391'],
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { beginAtZero: true }
      }
    }
  });
}

// ===== 8.7: Anomaly alert cards =====
function renderAnomalyCards(expenseAnomalies, revenueDips) {
  anomalyContainer.innerHTML = '';

  expenseAnomalies.forEach(a => {
    const card = document.createElement('div');
    card.className = 'anomaly-card';
    card.innerHTML = `
      <div class="anomaly-title">⚠ Expense Anomaly</div>
      <div class="anomaly-detail">
        <span>Date: ${escapeHtml(a.date)}</span>
        <span>Category: ${escapeHtml(a.category)}</span>
        <span>Expenses: $${Number(a.expenses).toLocaleString()}</span>
        <span>Z-Score: ${Number(a.z_score).toFixed(2)}</span>
      </div>
    `;
    anomalyContainer.appendChild(card);
  });

  revenueDips.forEach(d => {
    const card = document.createElement('div');
    card.className = 'anomaly-card';
    card.innerHTML = `
      <div class="anomaly-title">📉 Revenue Dip</div>
      <div class="anomaly-detail">
        <span>Month: ${escapeHtml(d.month)}</span>
        <span>Drop: ${Number(d.drop_pct).toFixed(1)}%</span>
        <span>Revenue: $${Number(d.revenue).toLocaleString()}</span>
      </div>
    `;
    anomalyContainer.appendChild(card);
  });
}

// ===== 8.8: Executive narrative panel =====
function renderNarrativePanel(narrative) {
  document.getElementById('narrative-summary').textContent = narrative.executive_summary;

  const trendsList = document.getElementById('narrative-trends');
  trendsList.innerHTML = '';
  (narrative.revenue_trends || []).forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    trendsList.appendChild(li);
  });

  const anomaliesList = document.getElementById('narrative-anomalies');
  anomaliesList.innerHTML = '';
  (narrative.anomalies || []).forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    anomaliesList.appendChild(li);
  });

  const recsList = document.getElementById('narrative-recommendations');
  recsList.innerHTML = '';
  (narrative.recommendations || []).forEach(item => {
    const li = document.createElement('li');
    li.textContent = item;
    recsList.appendChild(li);
  });
}

// ===== 8.9: Copy Report =====
copyBtn.addEventListener('click', () => {
  if (!currentNarrative) return;
  const text = buildReportText(currentNarrative);
  navigator.clipboard.writeText(text).then(() => {
    const original = copyBtn.textContent;
    copyBtn.textContent = '✓ Copied!';
    setTimeout(() => { copyBtn.textContent = original; }, 2000);
  }).catch(() => {
    showError('Failed to copy to clipboard.');
  });
});

// ===== 8.9: Download as .txt =====
downloadBtn.addEventListener('click', () => {
  if (!currentNarrative || !currentFileId) return;
  const text = buildReportText(currentNarrative);
  const blob = new Blob([text], { type: 'text/plain' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `report_${currentFileId}.txt`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
});

// ===== Build plain-text report from narrative =====
function buildReportText(narrative) {
  const lines = [];

  lines.push('EXECUTIVE SUMMARY');
  lines.push('=================');
  lines.push(narrative.executive_summary || '');
  lines.push('');

  lines.push('REVENUE TRENDS');
  lines.push('==============');
  (narrative.revenue_trends || []).forEach(t => lines.push(`• ${t}`));
  lines.push('');

  lines.push('ANOMALIES');
  lines.push('=========');
  (narrative.anomalies || []).forEach(a => lines.push(`• ${a}`));
  lines.push('');

  lines.push('RECOMMENDATIONS');
  lines.push('===============');
  (narrative.recommendations || []).forEach((r, i) => lines.push(`${i + 1}. ${r}`));

  return lines.join('\n');
}
