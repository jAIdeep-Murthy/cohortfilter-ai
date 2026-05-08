/* ── CohortFilter AI — Frontend Application Logic ── */

const API = '';  // Same origin
const state = {
    currentStep: 'rubric',
    rubric: null,
    uploadId: null,
    rowCount: 0,
    jobId: null,
    results: null,
    duplicates: [],
    allResults: null,  // Unfiltered copy
    sortDir: -1,       // -1 = desc
};

// ── Step Navigation ────────────────────────────────────────

function switchStep(step) {
    // Hide all panels
    document.querySelectorAll('.step-panel').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.step-ind').forEach(s => s.classList.remove('active'));

    // Show target
    const panel = document.getElementById('step-' + step);
    const ind = document.getElementById('ind-' + step);
    if (panel) panel.classList.add('active');
    if (ind) ind.classList.add('active');

    state.currentStep = step;
}

function markStepCompleted(step) {
    const ind = document.getElementById('ind-' + step);
    if (ind) ind.classList.add('completed');
}

// ── Rubric Chat ────────────────────────────────────────────

function addChatMessage(role, content) {
    const container = document.getElementById('chat-messages');
    const div = document.createElement('div');
    div.className = 'chat-msg ' + role;
    const avatar = role === 'assistant' ? 'AI' : 'You';
    div.innerHTML = `
        <div class="msg-avatar">${avatar}</div>
        <div class="msg-body">${content}</div>
    `;
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
}

function fillSuggestion(type) {
    const input = document.getElementById('chat-input');
    if (type === 'ai-india') {
        input.value = "I'm running an AI-focused accelerator for pre-seed startups in India. No solo founders, must have $5K+ MRR. Weight: Traction 40%, Team 30%, Market Fit 20%, Mission Alignment 10%.";
    } else if (type === 'fintech') {
        input.value = "Fintech accelerator for seed-stage startups in Southeast Asia. Must have revenue. Traction 35%, Team 25%, Market Fit 25%, Innovation 15%.";
    }
    input.focus();
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const msg = input.value.trim();
    if (!msg) return;

    input.value = '';
    addChatMessage('user', `<p>${escapeHtml(msg)}</p>`);

    try {
        const res = await fetch(API + '/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: msg }),
        });
        const data = await res.json();

        // Show AI response
        const formatted = data.response.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        addChatMessage('assistant', formatted);

        // Show rubric card
        if (data.rubric) {
            state.rubric = data.rubric;
            showRubricCard(data.rubric);
        }
    } catch (err) {
        addChatMessage('assistant', `<p style="color:var(--danger)">Error: ${err.message}. Is the backend running?</p>`);
    }
}

async function handleDocumentUpload(event) {
    const fileInput = event.target;
    if (!fileInput.files || fileInput.files.length === 0) return;
    
    const file = fileInput.files[0];
    
    // Clear the input so the same file can be uploaded again if needed
    fileInput.value = '';
    
    addChatMessage('user', `<p>📎 <i>Uploaded document: ${escapeHtml(file.name)}</i></p>`);
    addChatMessage('assistant', `<p class="loading-msg">Processing document and extracting rubric criteria...</p>`);
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch(API + '/api/chat/document', {
            method: 'POST',
            body: formData,
        });
        
        const data = await res.json();
        
        // Remove the loading message
        const messages = document.getElementById('chat-messages');
        if (messages.lastElementChild.querySelector('.loading-msg')) {
            messages.removeChild(messages.lastElementChild);
        }
        
        if (!res.ok) {
            throw new Error(data.detail || data.error || 'Failed to process document');
        }
        
        // Show AI response
        const formatted = data.response.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        addChatMessage('assistant', formatted);

        // Show rubric card
        if (data.rubric) {
            state.rubric = data.rubric;
            showRubricCard(data.rubric);
        }
    } catch (err) {
        // Remove the loading message
        const messages = document.getElementById('chat-messages');
        if (messages.lastElementChild.querySelector('.loading-msg')) {
            messages.removeChild(messages.lastElementChild);
        }
        addChatMessage('assistant', `<p style="color:var(--danger)">Error processing document: ${err.message}</p>`);
    }
}

async function loadDemoRubric() {
    const demoMsg = "I'm running an AI-focused accelerator for pre-seed startups in India. No solo founders, must have $5K+ MRR. Weight: Traction 40%, Team 30%, Market Fit 20%, Mission Alignment 10%.";
    document.getElementById('chat-input').value = demoMsg;
    await sendChatMessage();
}

function clearChat() {
    const container = document.getElementById('chat-messages');
    container.innerHTML = `
        <div class="chat-msg assistant">
            <div class="msg-avatar">AI</div>
            <div class="msg-body">
                <p>Welcome to CohortFilter AI. Tell me about your accelerator program:</p>
                <ul>
                    <li>What's the program focus? (e.g., AI startups, pre-seed, India-based)</li>
                    <li>Any dealbreakers? (e.g., no solo founders, must have revenue)</li>
                    <li>How should I weight scoring? (e.g., Traction 40%, Team 30%)</li>
                </ul>
                <p>Or click <strong>Load Demo Rubric</strong> to use a preset configuration.</p>
            </div>
        </div>
    `;
    resetRubric();
}

function showRubricCard(rubric) {
    const card = document.getElementById('rubric-card');
    const body = document.getElementById('rubric-card-body');

    let html = `<p><strong>Program Focus:</strong> ${escapeHtml(rubric.program_focus)}</p>`;

    // Dimensions table
    if (rubric.dimensions && rubric.dimensions.length) {
        html += '<table><thead><tr><th>Dimension</th><th>Weight</th></tr></thead><tbody>';
        for (const d of rubric.dimensions) {
            html += `<tr><td>${escapeHtml(d.name)}</td><td>${(d.weight * 100).toFixed(0)}%</td></tr>`;
        }
        html += '</tbody></table>';
    }

    // Dealbreakers
    if (rubric.dealbreakers && rubric.dealbreakers.length) {
        html += '<p style="margin-top:8px"><strong>Dealbreakers:</strong></p><ul>';
        for (const d of rubric.dealbreakers) {
            html += `<li>${escapeHtml(d.rule)}</li>`;
        }
        html += '</ul>';
    }

    body.innerHTML = html;
    card.classList.remove('hidden');
}

async function confirmRubric() {
    if (!state.rubric) return;

    try {
        await fetch(API + '/api/rubric', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(state.rubric),
        });

        document.getElementById('rubric-status').textContent = '✓ Confirmed';
        document.getElementById('rubric-status').style.color = 'var(--success)';
        document.getElementById('btn-confirm-rubric').disabled = true;
        document.getElementById('btn-confirm-rubric').textContent = '✓ Rubric Confirmed';

        markStepCompleted('rubric');
        switchStep('upload');
    } catch (err) {
        alert('Error saving rubric: ' + err.message);
    }
}

function resetRubric() {
    state.rubric = null;
    document.getElementById('rubric-card').classList.add('hidden');
    document.getElementById('rubric-status').textContent = 'Pending confirmation';
    document.getElementById('rubric-status').style.color = '';
    document.getElementById('btn-confirm-rubric').disabled = false;
    document.getElementById('btn-confirm-rubric').textContent = 'Confirm Rubric & Continue';
}

// ── CSV Upload ─────────────────────────────────────────────

function setupDragDrop() {
    const zone = document.getElementById('upload-zone');
    if (!zone) return;

    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file && file.name.endsWith('.csv')) uploadFile(file);
        else alert('Please drop a .csv file');
    });
    zone.addEventListener('click', () => document.getElementById('file-input').click());
}

function handleFileSelect(event) {
    const file = event.target.files[0];
    if (file) uploadFile(file);
}

async function uploadFile(file) {
    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch(API + '/api/upload', { method: 'POST', body: formData });
        if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
        const data = await res.json();
        state.uploadId = data.upload_id;
        state.rowCount = data.row_count;
        showUploadPreview(data, file.name);
    } catch (err) {
        alert('Upload error: ' + err.message);
    }
}

async function loadDemoCSV() {
    try {
        // Fetch the demo CSV, then upload it
        const csvRes = await fetch(API + '/api/demo/csv');
        if (!csvRes.ok) throw new Error('Demo CSV not found');
        const blob = await csvRes.blob();
        const file = new File([blob], 'demo_applications.csv', { type: 'text/csv' });
        await uploadFile(file);
    } catch (err) {
        alert('Error loading demo CSV: ' + err.message);
    }
}

function showUploadPreview(data, filename) {
    document.getElementById('preview-title').textContent = `Uploaded: ${filename}`;
    document.getElementById('preview-count').textContent = `${data.row_count} applications`;

    // Show sample rows
    const thead = document.getElementById('preview-thead');
    const tbody = document.getElementById('preview-tbody');
    thead.innerHTML = '';
    tbody.innerHTML = '';

    if (data.sample && data.sample.length) {
        const cols = data.columns.slice(0, 6);  // Show first 6 columns
        let headerRow = '<tr>';
        for (const col of cols) headerRow += `<th>${escapeHtml(col)}</th>`;
        headerRow += '</tr>';
        thead.innerHTML = headerRow;

        for (const row of data.sample) {
            let tr = '<tr>';
            for (const col of cols) tr += `<td>${escapeHtml(String(row[col] || '').substring(0, 60))}</td>`;
            tr += '</tr>';
            tbody.innerHTML += tr;
        }
    }

    document.getElementById('upload-preview').classList.remove('hidden');
}

// ── Scoring ────────────────────────────────────────────────

async function startScoring() {
    if (!state.uploadId) { alert('Please upload a CSV first'); return; }

    switchStep('results');
    const progressDiv = document.getElementById('scoring-progress');
    const dashboard = document.getElementById('results-dashboard');
    progressDiv.classList.remove('hidden');
    dashboard.classList.add('hidden');

    try {
        // Start scoring job
        const res = await fetch(API + `/api/score/${state.uploadId}`, { method: 'POST' });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || 'Scoring failed');
        }
        const data = await res.json();
        state.jobId = data.job_id;

        markStepCompleted('upload');

        // Poll for progress
        await pollJobStatus(data.job_id, data.total);
    } catch (err) {
        document.getElementById('progress-detail').textContent = `Error: ${err.message}`;
        document.getElementById('progress-detail').style.color = 'var(--danger)';
    }
}

async function pollJobStatus(jobId, total) {
    const bar = document.getElementById('progress-bar');
    const text = document.getElementById('progress-text');
    const detail = document.getElementById('progress-detail');

    while (true) {
        try {
            const res = await fetch(API + `/api/jobs/${jobId}`);
            const job = await res.json();

            const pct = total > 0 ? (job.progress / total * 100) : 0;
            bar.style.width = pct + '%';
            text.textContent = `${job.progress} / ${total}`;
            detail.textContent = `Scoring application ${job.progress} of ${total}... (${pct.toFixed(0)}%)`;

            if (job.status === 'completed') {
                state.results = job.results;
                state.allResults = [...job.results];
                state.duplicates = job.duplicates || [];
                bar.style.width = '100%';
                text.textContent = `${total} / ${total}`;
                detail.textContent = 'Scoring complete!';
                detail.style.color = 'var(--success)';

                // Brief pause to show 100%, then show dashboard
                await sleep(500);
                document.getElementById('scoring-progress').classList.add('hidden');
                markStepCompleted('results');
                renderDashboard();
                return;
            }

            if (job.status === 'failed') {
                detail.textContent = `Scoring failed: ${job.error}`;
                detail.style.color = 'var(--danger)';
                return;
            }

            await sleep(400);
        } catch (err) {
            detail.textContent = `Polling error: ${err.message}`;
            await sleep(1000);
        }
    }
}

// ── Results Dashboard ──────────────────────────────────────

function renderDashboard() {
    const dashboard = document.getElementById('results-dashboard');
    dashboard.classList.remove('hidden');

    const results = state.results;
    if (!results || !results.length) return;

    // Stats
    const total = results.length;
    const shortlisted = results.filter(r => r.total_score >= 600 && !r.dealbreaker_hit).length;
    const flagged = results.filter(r => r.risk_flags && r.risk_flags.length > 0).length;
    const rejected = results.filter(r => r.dealbreaker_hit).length;

    document.getElementById('stat-total').textContent = total;
    document.getElementById('stat-shortlist').textContent = shortlisted;
    document.getElementById('stat-flagged').textContent = flagged;
    document.getElementById('stat-rejected').textContent = rejected;
    document.getElementById('results-summary').textContent = `${total} applications scored · ${shortlisted} recommended for shortlist · ${rejected} dealbreaker disqualifications`;

    // Duplicate alerts
    if (state.duplicates.length > 0) {
        const alertDiv = document.getElementById('duplicate-alerts');
        alertDiv.classList.remove('hidden');
        let html = '<h4>⚠️ Potential Duplicate/Copycat Applications Detected</h4>';
        for (const pair of state.duplicates) {
            const simPct = (pair.similarity * 100).toFixed(0);
            html += `<div class="dup-pair">
                <span class="dup-sim">${simPct}%</span>
                <span><strong>${escapeHtml(pair.app_a_name)}</strong> ↔ <strong>${escapeHtml(pair.app_b_name)}</strong> — text similarity match</span>
            </div>`;
        }
        alertDiv.innerHTML = html;
    }

    // Table
    renderResultsTable(results);
}

function renderResultsTable(results) {
    const tbody = document.getElementById('results-tbody');
    tbody.innerHTML = '';

    for (const r of results) {
        const scoreClass = r.dealbreaker_hit ? 'score-low' : r.total_score >= 700 ? 'score-high' : r.total_score >= 400 ? 'score-mid' : 'score-low';

        // Dimension mini-bars
        let dimHtml = '<div class="dim-bars">';
        if (r.dimension_scores) {
            for (const [name, data] of Object.entries(r.dimension_scores)) {
                const score = data.score || 0;
                const pct = score / 10;
                const barColor = score >= 700 ? 'var(--success)' : score >= 400 ? 'var(--warning)' : 'var(--danger)';
                dimHtml += `
                    <div class="dim-bar">
                        <span class="dim-bar-label" title="${escapeHtml(name)}">${escapeHtml(name.substring(0, 8))}</span>
                        <div class="dim-bar-track"><div class="dim-bar-fill" style="width:${pct}%;background:${barColor}"></div></div>
                        <span class="dim-bar-val">${score}</span>
                    </div>`;
            }
        }
        dimHtml += '</div>';

        // Flags
        let flagsHtml = '';
        if (r.risk_flags && r.risk_flags.length) {
            for (const f of r.risk_flags) {
                const cls = f.includes('DEALBREAKER') ? 'flag-danger' : f.includes('duplicate') || f.includes('Possible') ? 'flag-warning' : 'flag-info';
                flagsHtml += `<span class="flag-chip ${cls}" title="${escapeHtml(f)}">${escapeHtml(f.substring(0, 30))}</span>`;
            }
        }
        if (r.website_status === 'dead') {
            flagsHtml += '<span class="flag-chip flag-danger">🔴 Dead website</span>';
        }

        const tr = document.createElement('tr');
        tr.id = `row-${r.application_id}`;
        tr.innerHTML = `
            <td class="col-rank" style="text-align:center">${r.rank}</td>
            <td class="col-name"><strong>${escapeHtml(r.startup_name)}</strong></td>
            <td class="col-founder">${escapeHtml(r.founder_name)}</td>
            <td class="col-score"><span class="score-cell ${scoreClass}">${r.total_score}</span></td>
            <td class="col-dims">${dimHtml}</td>
            <td class="col-flags">${flagsHtml || '<span style="color:var(--text-muted)">—</span>'}</td>
            <td class="col-expand"><button class="expand-btn" onclick="toggleExpand('${r.application_id}')">▸</button></td>
        `;
        tbody.appendChild(tr);
    }
}

function toggleExpand(appId) {
    const existingDetail = document.getElementById('detail-' + appId);
    if (existingDetail) {
        existingDetail.remove();
        const btn = document.querySelector(`#row-${appId} .expand-btn`);
        if (btn) btn.textContent = '▸';
        return;
    }

    const r = state.results.find(x => x.application_id === appId);
    if (!r) return;

    // Change button to collapse
    const btn = document.querySelector(`#row-${appId} .expand-btn`);
    if (btn) btn.textContent = '▾';

    // Build detail row
    const tr = document.createElement('tr');
    tr.id = 'detail-' + appId;
    tr.className = 'detail-row';

    let scoresHtml = '<ul class="detail-scores-list">';
    if (r.dimension_scores) {
        for (const [name, data] of Object.entries(r.dimension_scores)) {
            scoresHtml += `<li><span>${escapeHtml(name)}</span><span><strong>${data.score}/1000</strong></span></li>`;
            if (data.reason) {
                scoresHtml += `<li style="padding-left:12px;color:var(--text-secondary);font-size:11px;border:none">${escapeHtml(data.reason)}</li>`;
            }
        }
    }
    scoresHtml += '</ul>';

    let riskHtml = r.risk_flags && r.risk_flags.length
        ? r.risk_flags.map(f => `<li>${escapeHtml(f)}</li>`).join('')
        : '<li style="color:var(--text-muted)">No flags</li>';

    tr.innerHTML = `<td colspan="7">
        <div class="detail-content">
            <div class="detail-section">
                <h4>AI Assessment</h4>
                <p>${escapeHtml(r.summary)}</p>
                <h4 style="margin-top:12px">Risk Flags</h4>
                <ul style="padding-left:16px;font-size:12px">${riskHtml}</ul>
                <p style="margin-top:8px;font-size:11px;color:var(--text-muted)">
                    Confidence: ${(r.confidence * 100).toFixed(0)}% · Website: ${r.website_status}
                    ${r.dealbreaker_hit ? ' · <span style="color:var(--danger);font-weight:600">DEALBREAKER: ' + escapeHtml(r.dealbreaker_reason || '') + '</span>' : ''}
                </p>
            </div>
            <div class="detail-section">
                <h4>Dimension Scores</h4>
                ${scoresHtml}
            </div>
        </div>
    </td>`;

    // Insert after the main row
    const mainRow = document.getElementById('row-' + appId);
    mainRow.parentNode.insertBefore(tr, mainRow.nextSibling);
}

function filterResults() {
    const filter = document.getElementById('filter-select').value;
    let filtered = [...state.allResults];

    switch (filter) {
        case 'shortlist':
            filtered = filtered.filter(r => r.rank <= 10 && !r.dealbreaker_hit);
            break;
        case 'qualified':
            filtered = filtered.filter(r => !r.dealbreaker_hit);
            break;
        case 'flagged':
            filtered = filtered.filter(r => r.dealbreaker_hit || (r.risk_flags && r.risk_flags.length > 0));
            break;
    }

    state.results = filtered;
    renderResultsTable(filtered);
}

function sortResults(field) {
    state.sortDir *= -1;
    state.results.sort((a, b) => (a[field] - b[field]) * state.sortDir);
    // Re-assign ranks for display
    state.results.forEach((r, i) => r.rank = i + 1);
    renderResultsTable(state.results);
}

// ── Export ──────────────────────────────────────────────────

function goToExport() {
    switchStep('export');
}

async function exportPDF() {
    if (!state.jobId) { alert('No results to export'); return; }
    const topN = document.getElementById('pdf-top-n').value;
    const url = API + `/api/export/pdf/${state.jobId}?top_n=${topN}`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('PDF generation failed');
        const blob = await res.blob();
        downloadBlob(blob, `cohortfilter_shortlist_${state.jobId}.pdf`);
    } catch (err) {
        alert('PDF export error: ' + err.message);
    }
}

async function exportCSV() {
    if (!state.jobId) { alert('No results to export'); return; }
    const url = API + `/api/export/csv/${state.jobId}`;

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error('CSV export failed');
        const blob = await res.blob();
        downloadBlob(blob, `cohortfilter_scored_${state.jobId}.csv`);
    } catch (err) {
        alert('CSV export error: ' + err.message);
    }
}

function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ── Utilities ──────────────────────────────────────────────

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str || '';
    return div.innerHTML;
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ── Init ───────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    setupDragDrop();

    // Allow Enter to send chat
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keydown', e => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });
    }

    // Step indicator clicks
    document.querySelectorAll('.step-ind').forEach(btn => {
        btn.addEventListener('click', () => {
            const step = btn.dataset.step;
            if (step) switchStep(step);
        });
    });
});
