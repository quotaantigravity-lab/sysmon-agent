/* ─── SysMon Agent — Client App ────────────────────────────────────────────── */

// ─── State ────────────────────────────────────────────────────────────────────

let logs = [];
let alerts = [];
let escalations = [];
let chatHistory = [];
let ws = null;
let wsReconnectTimer = null;

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initNav();
  initMetricCards();
  initChatTriggers();
  initWebSocket();
  loadConfig();
  refreshDashboard();
});

// ─── Theme ────────────────────────────────────────────────────────────────────

function initTheme() {
  const saved = localStorage.getItem('sysmon-theme') || 'dark';
  document.documentElement.setAttribute('data-theme', saved);
  document.getElementById('btn-theme').textContent = saved === 'dark' ? '🌙' : '☀️';
}

document.getElementById('btn-theme').addEventListener('click', () => {
  const current = document.documentElement.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('sysmon-theme', next);
  document.getElementById('btn-theme').textContent = next === 'dark' ? '🌙' : '☀️';
});

// ─── Navigation ───────────────────────────────────────────────────────────────

function initNav() {
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      document.getElementById(`tab-${tab}`).classList.add('active');

      // Load data on tab switch
      if (tab === 'logs') loadLogs();
      if (tab === 'alerts') loadAlerts();
      if (tab === 'sops') loadSops();
    });
  });
}

function initMetricCards() {
  const criticalCard = document.querySelector('.metric-critical');
  if (criticalCard) {
    criticalCard.addEventListener('click', () => {
      switchTab('alerts');
      const filter = document.getElementById('alert-filter');
      if (filter) {
        filter.value = 'CRITICAL';
        renderAlerts();
      }
    });
  }

  const warningCard = document.querySelector('.metric-warning');
  if (warningCard) {
    warningCard.addEventListener('click', () => {
      switchTab('alerts');
      const filter = document.getElementById('alert-filter');
      if (filter) {
        filter.value = 'WARNING';
        renderAlerts();
      }
    });
  }

  const okCard = document.querySelector('.metric-ok');
  if (okCard) {
    okCard.addEventListener('click', () => {
      switchTab('alerts');
      const filter = document.getElementById('alert-filter');
      if (filter) {
        filter.value = 'OK';
        renderAlerts();
      }
    });
  }

  const incidentCard = document.querySelector('.metric-incident');
  if (incidentCard) {
    incidentCard.addEventListener('click', () => {
      switchTab('logs');
      const filterType = document.getElementById('filter-type');
      const filterStatus = document.getElementById('filter-status');
      const filterSeverity = document.getElementById('filter-severity');
      if (filterType) filterType.value = 'incident';
      if (filterStatus) filterStatus.value = 'resolving';
      if (filterSeverity) filterSeverity.value = '';
      renderLogs();
    });
  }

  const resolvedCard = document.querySelector('.metric-resolved');
  if (resolvedCard) {
    resolvedCard.addEventListener('click', () => {
      switchTab('logs');
      const filterType = document.getElementById('filter-type');
      const filterStatus = document.getElementById('filter-status');
      const filterSeverity = document.getElementById('filter-severity');
      if (filterType) filterType.value = 'incident';
      if (filterStatus) filterStatus.value = 'resolved';
      if (filterSeverity) filterSeverity.value = '';
      renderLogs();
    });
  }

  const hostsCard = document.querySelector('.metric-hosts');
  if (hostsCard) {
    hostsCard.addEventListener('click', () => {
      switchTab('alerts');
      const filter = document.getElementById('alert-filter');
      if (filter) {
        filter.value = '';
        renderAlerts();
      }
    });
  }
}

function switchTab(tabId) {
  const btn = document.querySelector(`.nav-btn[data-tab="${tabId}"]`);
  if (btn) {
    btn.click();
  }
}

function initChatTriggers() {
  document.querySelectorAll('.btn-trigger').forEach(btn => {
    btn.addEventListener('click', () => {
      const query = btn.dataset.query;
      const input = document.getElementById('chat-input');
      if (input && query) {
        input.value = query;
        sendChat();
      }
    });
  });
}

// ─── WebSocket ────────────────────────────────────────────────────────────────

function initWebSocket() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const url = `${proto}//${location.host}/ws`;

  try {
    ws = new WebSocket(url);

    ws.onopen = () => {
      document.getElementById('ws-status').querySelector('span:last-child').textContent = 'Live';
      document.querySelector('.pulse').style.background = 'var(--ok)';
      if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        handleWSMessage(msg);
      } catch (e) { /* ignore */ }
    };

    ws.onclose = () => {
      document.getElementById('ws-status').querySelector('span:last-child').textContent = 'Offline';
      document.querySelector('.pulse').style.background = 'var(--critical)';
      wsReconnectTimer = setTimeout(initWebSocket, 5000);
    };

    ws.onerror = () => { ws.close(); };
  } catch (e) {
    wsReconnectTimer = setTimeout(initWebSocket, 5000);
  }

  // Keepalive
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping');
  }, 30000);
}

function handleWSMessage(msg) {
  switch (msg.type) {
    case 'pong': break;
    case 'log_created':
      toast('📝 Log mới đã được thêm', 'info');
      loadLogs();
      refreshDashboard();
      break;
    case 'log_updated':
      toast('📝 Log đã được cập nhật', 'info');
      loadLogs();
      refreshDashboard();
      break;
    case 'log_deleted':
      toast('🗑️ Log đã được xóa', 'warning');
      loadLogs();
      refreshDashboard();
      break;
    default:
      if (msg.type === 'alert') {
        toast(`🚨 Alert: ${msg.data?.host || 'Unknown'} — ${msg.data?.message || ''}`, 'warning');
        loadAlerts();
        refreshDashboard();
      }
  }
}

// ─── Toast ────────────────────────────────────────────────────────────────────

function toast(text, type = 'info') {
  const container = document.getElementById('toast-container');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = text;
  container.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 4000);
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

async function refreshDashboard() {
  try {
    const [dashRes, escRes] = await Promise.all([
      fetch('/api/dashboard').then(r => r.json()),
      fetch('/api/escalations').then(r => r.json()),
    ]);

    document.getElementById('m-critical').textContent = dashRes.alerts?.critical ?? '—';
    document.getElementById('m-warning').textContent = dashRes.alerts?.warning ?? '—';
    document.getElementById('m-ok').textContent = dashRes.alerts?.ok ?? '—';
    document.getElementById('m-incidents').textContent = dashRes.logs?.open_incidents ?? '—';
    document.getElementById('m-resolved').textContent = dashRes.logs?.resolved_today ?? '—';
    document.getElementById('m-hosts').textContent = dashRes.affected_hosts ?? '—';

    escalations = escRes;
    renderEscalations();

    // Also load recent alerts for dashboard
    const alertsRes = await fetch('/api/nagios-alerts').then(r => r.json());
    alerts = alertsRes;
    renderRecentAlerts();
  } catch (e) {
    console.error('Dashboard error:', e);
  }
}

function renderEscalations() {
  const container = document.getElementById('escalation-list');
  document.getElementById('esc-count').textContent = escalations.length;

  if (!escalations.length) {
    container.innerHTML = '<div class="empty-state">✅ Không phát hiện leo thang sự cố</div>';
    return;
  }

  container.innerHTML = escalations.map(esc => `
    <div class="esc-item">
      <div class="esc-header">
        <span class="esc-host">${esc.host}</span>
        <span class="esc-badge ${esc.max_severity.toLowerCase()}">${esc.max_severity} · ${esc.alert_count} alerts</span>
      </div>
      ${esc.escalating ? '<div style="color:var(--critical);font-size:0.82rem;font-weight:600;">⚡ ĐANG LEO THANG</div>' : ''}
      <div class="esc-timeline">
        ${esc.timeline.map(t => `
          <div class="esc-event">
            <span class="esc-event-time">${t.time.split(' ')[1]?.slice(0,5) || t.time}</span>
            <span>[${t.state}] ${t.service}: ${t.message.slice(0, 80)}</span>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('');
}

function renderRecentAlerts() {
  const container = document.getElementById('recent-alerts');
  const recent = alerts.slice(0, 6);

  if (!recent.length) {
    container.innerHTML = '<div class="empty-state">Không có cảnh báo</div>';
    return;
  }

  container.innerHTML = recent.map(a => `
    <div class="alert-item">
      <div class="alert-state ${a.state}"></div>
      <div class="alert-info">
        <div class="alert-host">${a.host} / ${a.service}</div>
        <div class="alert-msg">${a.message}</div>
      </div>
      <div class="alert-time">${a.date.split(' ')[1]?.slice(0,8) || a.date}</div>
    </div>
  `).join('');
}

// ─── Logs ─────────────────────────────────────────────────────────────────────

async function loadLogs() {
  try {
    logs = await fetch('/api/logs').then(r => r.json());
    renderLogs();
  } catch (e) {
    console.error('Load logs error:', e);
  }
}

function renderLogs() {
  const typeF = document.getElementById('filter-type').value;
  const statusF = document.getElementById('filter-status').value;
  const sevF = document.getElementById('filter-severity').value;

  let filtered = logs.filter(l =>
    (!typeF || l.type === typeF) &&
    (!statusF || l.status === statusF) &&
    (!sevF || l.severity === sevF)
  );

  const container = document.getElementById('logs-list');
  if (!filtered.length) {
    container.innerHTML = '<div class="empty-state">Không có log nào phù hợp</div>';
    return;
  }

  const icons = { incident: '🔴', maintenance: '🔧', note: '📝' };

  container.innerHTML = filtered.map(l => `
    <div class="log-item">
      <div class="log-type-icon">${icons[l.type] || '📋'}</div>
      <div class="log-body">
        <div class="log-meta">
          <span class="log-component">${l.component}</span>
          <span class="log-tag ${l.severity}">${l.severity}</span>
          <span class="log-tag ${l.status}">${l.status}</span>
        </div>
        <div class="log-content">${l.content}</div>
        <div class="log-time">🕐 ${l.created_at}${l.resolved_at ? ' → ✅ ' + l.resolved_at : ''}</div>
      </div>
      <div class="log-actions">
        <button class="btn btn-sm" onclick="editLog('${l.id}')">✏️</button>
        <button class="btn btn-sm btn-danger" onclick="deleteLog('${l.id}')">🗑️</button>
      </div>
    </div>
  `).join('');
}

function openLogModal(editId = null) {
  document.getElementById('log-edit-id').value = editId || '';
  document.getElementById('log-modal-title').textContent = editId ? '✏️ Chỉnh sửa Log' : '+ Thêm Log Mới';

  if (editId) {
    const l = logs.find(x => x.id === editId);
    if (l) {
      document.getElementById('log-type').value = l.type;
      document.getElementById('log-severity').value = l.severity;
      document.getElementById('log-component').value = l.component;
      document.getElementById('log-status').value = l.status;
      document.getElementById('log-content').value = l.content;
      if (l.created_at) {
        document.getElementById('log-created-at').value = l.created_at.replace(' ', 'T').slice(0, 16);
      } else {
        const now = new Date();
        const offsetMs = now.getTimezoneOffset() * 60000;
        const localISOTime = new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
        document.getElementById('log-created-at').value = localISOTime;
      }
    }
  } else {
    document.getElementById('log-type').value = 'incident';
    document.getElementById('log-severity').value = 'medium';
    document.getElementById('log-component').value = '';
    document.getElementById('log-status').value = 'resolving';
    document.getElementById('log-content').value = '';
    
    const now = new Date();
    const offsetMs = now.getTimezoneOffset() * 60000;
    const localISOTime = new Date(now.getTime() - offsetMs).toISOString().slice(0, 16);
    document.getElementById('log-created-at').value = localISOTime;
  }

  document.getElementById('modal-log').classList.add('show');
}

function editLog(id) { openLogModal(id); }

async function saveLog() {
  const editId = document.getElementById('log-edit-id').value;
  const createdAtVal = document.getElementById('log-created-at').value;
  
  const data = {
    type: document.getElementById('log-type').value,
    severity: document.getElementById('log-severity').value,
    component: document.getElementById('log-component').value,
    status: document.getElementById('log-status').value,
    content: document.getElementById('log-content').value,
  };

  if (!data.component || !data.content) {
    toast('Vui lòng điền đầy đủ thông tin', 'error');
    return;
  }

  if (createdAtVal) {
    data.created_at = createdAtVal.replace('T', ' ') + ':00';
  }

  try {
    const url = editId ? `/api/logs/${editId}` : '/api/logs';
    const method = editId ? 'PUT' : 'POST';
    await fetch(url, {
      method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    closeModal('modal-log');
    toast(editId ? 'Đã cập nhật log' : 'Đã thêm log mới', 'success');
    loadLogs();
    refreshDashboard();
  } catch (e) {
    toast('Lỗi khi lưu log', 'error');
  }
}

async function deleteLog(id) {
  if (!confirm('Xóa log này?')) return;
  try {
    await fetch(`/api/logs/${id}`, { method: 'DELETE' });
    toast('Đã xóa log', 'success');
    loadLogs();
    refreshDashboard();
  } catch (e) {
    toast('Lỗi khi xóa', 'error');
  }
}

// ─── Alerts ───────────────────────────────────────────────────────────────────

async function loadAlerts() {
  try {
    alerts = await fetch('/api/nagios-alerts').then(r => r.json());
    renderAlerts();
  } catch (e) {
    console.error('Load alerts error:', e);
  }
}

function renderAlerts() {
  const filter = document.getElementById('alert-filter').value;
  const limit = parseInt(document.getElementById('alert-limit')?.value || '10');
  
  // Deduplicate alerts: keep only the latest state for each unique host/service
  const uniqueAlerts = [];
  const seen = new Set();
  
  for (const a of alerts) {
    const key = `${a.host}/${a.service}`;
    if (!seen.has(key)) {
      seen.add(key);
      uniqueAlerts.push(a);
    }
  }
  
  let filtered = filter ? uniqueAlerts.filter(a => a.state === filter) : uniqueAlerts;
  filtered = filtered.slice(0, limit);
  
  const container = document.getElementById('alerts-list');

  if (!filtered.length) {
    container.innerHTML = '<div class="empty-state">Không có cảnh báo</div>';
    return;
  }

  container.innerHTML = filtered.map(a => `
    <div class="alert-item">
      <div class="alert-state ${a.state}"></div>
      <div class="alert-info">
        <div class="alert-host">${a.host} / ${a.service}</div>
        <div class="alert-msg">${a.message}</div>
      </div>
      <div class="alert-time">${a.date}</div>
    </div>
  `).join('');
}

// ─── SOPs ─────────────────────────────────────────────────────────────────────

async function loadSops() {
  try {
    const sops = await fetch('/api/sops').then(r => r.json());
    const container = document.getElementById('sops-list');
    if (!sops.length) {
      container.innerHTML = '<div class="empty-state">Chưa có tài liệu nào. Nhấn "Tải lên" để thêm.</div>';
      return;
    }
    container.innerHTML = sops.map(s => `
      <div class="sop-item">
        <div class="sop-info">
          <div class="sop-title">📄 ${s.title}</div>
          <div class="sop-file">${s.filename} · ${Math.round(s.content.length / 1024)}KB text</div>
        </div>
        <button class="btn btn-sm btn-danger" onclick="deleteSop('${s.id}')">🗑️</button>
      </div>
    `).join('');
  } catch (e) {
    console.error('Load SOPs error:', e);
  }
}

function openSopModal() {
  document.getElementById('sop-title').value = '';
  document.getElementById('sop-file').value = '';
  document.getElementById('modal-sop').classList.add('show');
}

async function uploadSop() {
  const title = document.getElementById('sop-title').value;
  const fileInput = document.getElementById('sop-file');
  if (!fileInput.files.length) { toast('Chọn file để tải lên', 'error'); return; }

  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  formData.append('title', title || fileInput.files[0].name);

  try {
    const res = await fetch('/api/sops/upload', { method: 'POST', body: formData });
    if (res.ok) {
      closeModal('modal-sop');
      toast('Tải lên thành công!', 'success');
      loadSops();
    } else {
      const err = await res.json();
      toast(`Lỗi: ${err.detail}`, 'error');
    }
  } catch (e) {
    toast('Lỗi tải lên', 'error');
  }
}

async function deleteSop(id) {
  if (!confirm('Xóa tài liệu này?')) return;
  try {
    await fetch(`/api/sops/${id}`, { method: 'DELETE' });
    toast('Đã xóa tài liệu', 'success');
    loadSops();
  } catch (e) {
    toast('Lỗi khi xóa', 'error');
  }
}

// ─── Chat ─────────────────────────────────────────────────────────────────────

async function sendChat() {
  const input = document.getElementById('chat-input');
  const msg = input.value.trim();
  if (!msg) return;
  input.value = '';

  appendMessage('user', msg);
  chatHistory.push({ role: 'user', content: msg });

  // Show typing indicator
  const typingEl = appendTyping();

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: msg, history: chatHistory.slice(-10) }),
    });
    const data = await res.json();
    typingEl.remove();
    appendMessage('ai', data.response);
    chatHistory.push({ role: 'assistant', content: data.response });
  } catch (e) {
    typingEl.remove();
    appendMessage('ai', '⚠️ Lỗi kết nối. Vui lòng thử lại.');
  }
}

function appendMessage(role, content) {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = `msg msg-${role === 'user' ? 'user' : 'ai'}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? '👤' : '🛡️';

  const body = document.createElement('div');
  body.className = 'msg-content';
  // Simple markdown-ish rendering
  body.innerHTML = content
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>');

  div.appendChild(avatar);
  div.appendChild(body);
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
}

function appendTyping() {
  const container = document.getElementById('chat-messages');
  const div = document.createElement('div');
  div.className = 'msg msg-ai';
  div.innerHTML = `
    <div class="msg-avatar">🛡️</div>
    <div class="msg-content">
      <div class="msg-typing"><span></span><span></span><span></span></div>
    </div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

// ─── Handover ─────────────────────────────────────────────────────────────────

async function generateHandover() {
  const sender = document.getElementById('sender-name').value;
  const receiver = document.getElementById('receiver-name').value;

  try {
    const params = new URLSearchParams();
    if (sender) params.set('sender', sender);
    if (receiver) params.set('receiver', receiver);
    const data = await fetch(`/api/handover?${params}`).then(r => r.json());
    document.getElementById('handover-preview').innerHTML =
      data.markdown.replace(/\n/g, '<br>').replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
    toast('Đã tạo báo cáo bàn giao', 'success');
  } catch (e) {
    toast('Lỗi tạo báo cáo', 'error');
  }
}

// ─── Config ───────────────────────────────────────────────────────────────────

document.getElementById('btn-settings').addEventListener('click', () => {
  loadConfigFields();
  document.getElementById('modal-settings').classList.add('show');
});

document.getElementById('cfg-imap-enabled').addEventListener('change', (e) => {
  document.getElementById('cfg-imap-fields').style.display = e.target.checked ? 'flex' : 'none';
});

async function loadConfig() {
  try {
    const config = await fetch('/api/config').then(r => r.json());
    document.getElementById('chat-model').textContent = config.model_name || 'N/A';
    return config;
  } catch (e) {
    return {};
  }
}

async function loadConfigFields() {
  const config = await loadConfig();
  document.getElementById('cfg-api-key').value = '';
  document.getElementById('cfg-api-key').placeholder = config.has_key ? '•••••••• (đã cấu hình)' : 'Nhập API Key...';
  document.getElementById('cfg-model').value = config.model_name || '';
  const imapEnabled = config.imap_enabled || false;
  document.getElementById('cfg-imap-enabled').checked = imapEnabled;
  document.getElementById('cfg-imap-fields').style.display = imapEnabled ? 'flex' : 'none';
  document.getElementById('cfg-imap-server').value = config.imap_server || '';
  document.getElementById('cfg-imap-user').value = config.imap_user || '';
  document.getElementById('cfg-imap-pass').value = '';
  document.getElementById('cfg-imap-pass').placeholder = config.imap_pass ? '•••••• (đã cấu hình)' : 'App password...';
  document.getElementById('cfg-imap-filter').value = config.imap_filter || '';
  document.getElementById('cfg-esc-window').value = config.alert_escalation_window || 30;
  document.getElementById('cfg-esc-threshold').value = config.alert_escalation_threshold || 3;
}

async function saveConfig() {
  const data = {
    model_name: document.getElementById('cfg-model').value,
    imap_enabled: document.getElementById('cfg-imap-enabled').checked,
    imap_server: document.getElementById('cfg-imap-server').value,
    imap_user: document.getElementById('cfg-imap-user').value,
    imap_filter: document.getElementById('cfg-imap-filter').value,
    alert_escalation_window: parseInt(document.getElementById('cfg-esc-window').value) || 30,
    alert_escalation_threshold: parseInt(document.getElementById('cfg-esc-threshold').value) || 3,
  };

  const apiKey = document.getElementById('cfg-api-key').value;
  if (apiKey) data.api_key = apiKey;

  const imapPass = document.getElementById('cfg-imap-pass').value;
  if (imapPass) data.imap_pass = imapPass;

  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    closeModal('modal-settings');
    toast('Đã lưu cấu hình!', 'success');
    loadConfig();
  } catch (e) {
    toast('Lỗi lưu cấu hình', 'error');
  }
}

// ─── Modals ───────────────────────────────────────────────────────────────────

function closeModal(id) {
  document.getElementById(id).classList.remove('show');
}

// Close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.classList.remove('show');
  });
});

// Close modal on Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.modal-overlay.show').forEach(m => m.classList.remove('show'));
  }
});
