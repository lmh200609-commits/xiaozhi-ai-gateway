// ================= State Management =================
let currentConfig = {};
let allRoles = [];
let activeRoleId = "assistant";
let allDocs = [];
let allZones = [];
let activeZoneId = "default_zone";
let allVideos = [];
let activeZoneSubTab = "docs"; // 'docs' or 'videos'
let currentPlayingVideoKey = null;

// ================= Navigation =================
function switchTab(tabName) {
  try {
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(panel => panel.classList.remove('active'));

    const navBtn = document.getElementById(`nav-${tabName}`);
    if (navBtn) navBtn.classList.add('active');

    const panel = document.getElementById(`tab-${tabName}`);
    if (panel) panel.classList.add('active');

    // Update Page Title
    const titles = {
      devices: { t: "📱 硬件设备看板", s: "实时监控小智 ESP32-S3 连接状态 · MCP 硬件调控 · 毫秒级语音链路" },
      knowledge: { t: "🏛️ 知识区管理 (知识中枢)", s: "私有化专属知识中枢 · 权威文档知识库与展播视频综合管理" },
      roles: { t: "🎭 角色人设与音色", s: "预置场景人设 · 微软自然神经网络音色 · 极速切换" },
      chat: { t: "💬 交互仿真与日志", s: "零硬件快速对话仿真 · 开发板语音交互耗时瀑布流与全链路透视" },
      settings: { t: "⚙️ 网关系统配置", s: "配置 DeepSeek / 兼容大模型中转 · 本地 SenseVoice ASR · Edge-TTS 引擎" }
    };
    if (titles[tabName]) {
      const pt = document.getElementById('page-title');
      const ps = document.getElementById('page-subtitle');
      if (pt) pt.textContent = titles[tabName].t;
      if (ps) ps.textContent = titles[tabName].s;
    }

    if (tabName === 'knowledge') {
      fetchZones();
      fetchKnowledge();
      fetchVideos();
    } else if (tabName === 'roles') {
      fetchRoles();
    } else if (tabName === 'devices') {
      fetchStatus();
    }
  } catch (err) {
    console.error("switchTab error:", err);
  }
}

// ================= Status & Dashboard =================
async function fetchStatus() {
  try {
    const res = await fetch('/api/status');
    if (!res.ok) return;
    const data = await res.json();
    currentConfig = data.config || {};

    // Header Badges
    const modelBadge = document.getElementById('header-model-badge');
    if (modelBadge && data.config) modelBadge.textContent = `模型: ${data.config.model_name || 'deepseek-chat'}`;

    const upBadge = document.getElementById('upload-model-badge');
    if (upBadge && data.config) {
      upBadge.textContent = `✨ 当前解析模型：${data.config.model_name || 'deepseek-chat'} · AI 自动蒸馏 FAQ 与切片`;
    }

    if (data.active_role) {
      activeRoleId = data.active_role.id;
      const roleBadge = document.getElementById('header-role-badge');
      if (roleBadge) roleBadge.textContent = `人设: ${data.active_role.name}`;
    }
    if (data.knowledge_count !== undefined) {
      const ragBadge = document.getElementById('header-rag-badge');
      if (ragBadge) ragBadge.textContent = `知识库: ${data.knowledge_count} 篇`;
    }

    // Devices count
    const statDevCount = document.getElementById('stat-device-count');
    if (statDevCount) statDevCount.textContent = `${data.devices_online || 0} 台`;

    const statLan = document.getElementById('stat-lan-ip');
    if (statLan) statLan.textContent = window.location.host;

    // Sidebar bottom widget
    const dot = document.getElementById('sidebar-dot');
    const statusText = document.getElementById('sidebar-status-text');
    const infoText = document.getElementById('sidebar-device-info');

    if (dot && statusText && infoText) {
      if (data.devices_online > 0) {
        dot.style.background = "#10b981";
        const dev = data.devices[0];
        statusText.textContent = "小智硬件在线";
        infoText.textContent = `IP: ${dev.ip} (${dev.device_id})`;
      } else {
        dot.style.background = "#94a3b8";
        statusText.textContent = "等待小智连接";
        infoText.textContent = `网关: ${window.location.host}`;
      }
    }

    // Device List
    const devList = document.getElementById('device-list');
    if (devList) {
      if (!data.devices_online || data.devices_online === 0) {
        devList.innerHTML = `
          <div class="empty-state">
            <div class="empty-icon">🔌</div>
            <p>暂无小智设备在线</p>
            <span class="empty-hint">请确保 ESP32-S3 连入 WiFi 并指向当前网关地址</span>
          </div>`;
      } else {
        devList.innerHTML = data.devices.map(dev => {
          const isCalling = dev.status === "online" && dev.ws;
          const statusBadge = isCalling
            ? `<span class="badge badge-success"><span class="dot-pulse" style="width:6px; height:6px;"></span> 语音通话中</span>`
            : `<span class="badge" style="background:#e0f2fe; color:#0284c7;"><span class="dot-pulse" style="width:6px; height:6px; background:#0284c7;"></span> 待命就绪 (Standby)</span>`;

          return `
          <div class="device-item">
            <div class="device-item-header">
              <span class="device-name">小智 ESP32-S3</span>
              ${statusBadge}
            </div>
            <div class="device-meta">
              <div><strong>MAC:</strong> ${dev.device_id}</div>
              <div><strong>局域网 IP:</strong> ${dev.ip}</div>
              <div><strong>连入时间:</strong> ${dev.connected_at}</div>
              <div><strong>活跃时间:</strong> ${dev.last_active}</div>
              <div><strong>硬件 MCP 工具:</strong> ${dev.tools ? dev.tools.length : 0} 个已就绪</div>
            </div>
            <div class="device-controls">
              <div class="control-row">
                <span>🔊 喇叭音量:</span>
                <input type="range" min="0" max="100" value="70" onchange="sendDeviceControl('${dev.device_id}', 'volume', this.value)">
              </div>
              <div class="control-row">
                <span>💡 屏幕背光:</span>
                <input type="range" min="0" max="100" value="80" onchange="sendDeviceControl('${dev.device_id}', 'brightness', this.value)">
              </div>
              <div style="display:flex; gap:8px; margin-top:8px;">
                <button class="btn btn-sm btn-secondary" onclick="sendDeviceControl('${dev.device_id}', 'theme', 'dark')">🌙 暗黑模式</button>
                <button class="btn btn-sm btn-secondary" onclick="sendDeviceControl('${dev.device_id}', 'theme', 'light')">☀️ 明亮模式</button>
                <button class="btn btn-sm btn-danger-outline" onclick="sendDeviceControl('${dev.device_id}', 'reboot', '')">🔄 重启硬件</button>
              </div>
              <div id="ctrl-hint-${dev.device_id}" style="font-size:12px; margin-top:6px;"></div>
            </div>
          </div>
        `;}).join('');
      }
    }
  } catch (err) {
    console.error("fetchStatus error:", err);
  }
}

async function sendDeviceControl(deviceId, action, value) {
  try {
    const res = await fetch('/api/device/control', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_id: deviceId, action: action, value: value })
    });
    const data = await res.json();
    const hintEl = document.getElementById(`ctrl-hint-${deviceId}`);
    if (hintEl) {
      if (data.mode === "queued") {
        hintEl.textContent = `ℹ️ ${data.message}`;
        hintEl.style.color = "#0284c7";
      } else {
        hintEl.textContent = `✅ ${data.message || '指令已生效'}`;
        hintEl.style.color = "#10b981";
      }
    }
  } catch (err) {
    console.error("sendDeviceControl error:", err);
  }
}

async function quickTestAgent(userText) {
  const fb = document.getElementById('pc-agent-feedback');
  if (fb) {
    fb.style.display = "block";
    fb.innerHTML = `⏳ 正在让小智思考并执行指令: <strong>${escapeHtml(userText)}</strong> ...`;
  }
  try {
    const res = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: userText, role_id: activeRoleId })
    });
    const data = await res.json();
    let toolsInfo = "";
    if (data.executed_tools && data.executed_tools.length > 0) {
      toolsInfo = data.executed_tools.map(t => `<div style="margin-top:4px;">⚙️ <strong>PC 工具调用:</strong> <code>${escapeHtml(t.tool)}</code> 参数: <code>${JSON.stringify(t.args)}</code> -> <em>${escapeHtml(t.result ? t.result.message : '')}</em></div>`).join('');
    }
    if (fb) {
      fb.innerHTML = `
        <div style="font-weight:600; margin-bottom:4px;">✅ 指令已响应执行：</div>
        <div>👤 游客说话: “${escapeHtml(data.user_text || '')}”</div>
        <div style="margin: 4px 0;">🤖 小智回答: “${escapeHtml(data.assistant_reply || '')}”</div>
        ${toolsInfo}
      `;
    }
    fetchLogs();
  } catch (err) {
    if (fb) fb.innerHTML = `❌ 执行失败: ${err}`;
  }
}

// ================= Conversation Logs =================
async function fetchLogs() {
  try {
    const res = await fetch('/api/logs');
    if (!res.ok) return;
    const logs = await res.json();
    const container = document.getElementById('logs-container');
    if (!container || !Array.isArray(logs) || logs.length === 0) return;

    container.innerHTML = logs.map(log => {
      if (log.type === "conversation") {
        let ragPill = '';
        let ragBox = '';
        if (log.rag_matched && log.rag_matched.length > 0) {
          ragPill = `<span class="pill pill-rag">RAG命中: ${log.rag_matched.length}条 (${log.rag_ms || 0}ms)</span>`;
          ragBox = `
            <div class="rag-reference-box">
              <strong>📖 检索命中的私有知识：</strong>
              ${log.rag_matched.map(m => `<span>《${escapeHtml(m.title)}》${m.question ? `[问: ${escapeHtml(m.question)}]` : ''} (${m.score}分)</span>`).join(' · ')}
            </div>`;
        }

        return `
          <div class="log-card">
            <div class="log-meta">
              <span><strong>来源:</strong> ${escapeHtml(log.device || '')} · ${escapeHtml(log.timestamp || '')} · 人设: ${escapeHtml(log.role_name || '默认')}</span>
              <div class="latency-pills">
                ${log.asr_ms ? `<span class="pill pill-asr">ASR: ${log.asr_ms}ms</span>` : ''}
                ${ragPill}
                <span class="pill pill-ttft">首字: ${log.ttft_ms}ms</span>
                <span class="pill pill-total">全链路: ${log.total_ms}ms</span>
              </div>
            </div>
            <div class="dialog-box">
              <div class="user-bubble"><strong>👤 说话:</strong> ${escapeHtml(log.user_text || '')}</div>
              <div class="assistant-bubble"><strong>🤖 小智:</strong> ${escapeHtml(log.assistant_reply || '')}</div>
              ${ragBox}
            </div>
          </div>`;
      } else if (log.type === "mcp") {
        return `
          <div class="log-card" style="border-left: 3px solid #f59e0b;">
            <div class="log-meta">
              <span><strong>⚙️ 硬件 MCP 工具调用:</strong> ${escapeHtml(log.device || '')} · ${escapeHtml(log.timestamp || '')}</span>
            </div>
            <div style="font-size:12px; color:#b45309; background:#fffbeb; padding:6px 12px; border-radius:6px;">
              调用工具 <code>${escapeHtml(log.tool)}</code> 参数: <code>${JSON.stringify(log.args)}</code>
            </div>
          </div>`;
      } else if (log.type === "pc_tool") {
        return `
          <div class="log-card" style="border-left: 3px solid #10b981; background: #f0fdf4;">
            <div class="log-meta">
              <span><strong>💻 PC Agent 电脑工具执行:</strong> ${escapeHtml(log.tool)} · ${escapeHtml(log.timestamp || '')}</span>
              <span class="pill" style="background:#bbf7d0; color:#15803d;">成功执行</span>
            </div>
            <div style="font-size:12px; color:#166534; padding:6px 12px; border-radius:6px; background:#dcfce7; margin-top:6px;">
              调用指令: <code>${escapeHtml(log.tool)}</code> 参数: <code>${JSON.stringify(log.args)}</code>
              <div style="margin-top:4px;"><strong>执行反馈:</strong> ${escapeHtml(log.result ? (log.result.message || JSON.stringify(log.result)) : '已完成')}</div>
            </div>
          </div>`;
      }
      return '';
    }).join('');
  } catch (err) {
    console.error("fetchLogs error:", err);
  }
}

function clearLogs() {
  const container = document.getElementById('logs-container');
  if (container) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🎧</div>
        <p>日志已清空，等待新对话...</p>
      </div>`;
  }
}

// ================= 🏛️ 知识区 (Knowledge Zone) 管理 =================

async function fetchZones() {
  try {
    const res = await fetch('/api/zones');
    if (!res.ok) return;
    const data = await res.json();
    allZones = data.zones || [];
    const activeZone = data.active_zone || (allZones[0] || {});
    activeZoneId = activeZone.id || "baicheng_railway";

    // Populate zone select dropdown
    const select = document.getElementById('zone-select');
    if (select) {
      select.innerHTML = allZones.map(z => `
        <option value="${z.id}" ${z.id === activeZoneId ? 'selected' : ''}>
          ${z.icon || '🏛️'} ${escapeHtml(z.name)} ${z.is_default ? '(默认)' : ''}
        </option>
      `).join('');
    }

    // Update Zone Info labels
    const uploadZoneName = document.getElementById('video-upload-zone-name');
    if (uploadZoneName) uploadZoneName.textContent = activeZone.name || "白城火车园区知识区";

    // Update stats pills
    const curZone = allZones.find(z => z.id === activeZoneId) || activeZone;
    const docPill = document.getElementById('zone-doc-count-pill');
    const vidPill = document.getElementById('zone-vid-count-pill');
    if (docPill) docPill.textContent = `📄 ${curZone.doc_count || 0} 篇知识文档`;
    if (vidPill) vidPill.textContent = `🎬 ${curZone.video_count || 0} 部展播视频 (${curZone.video_ready_count || 0}部已就绪)`;

  } catch (err) {
    console.error("fetchZones error:", err);
  }
}

async function handleZoneChange(newZoneId) {
  activeZoneId = newZoneId;
  try {
    await fetch('/api/zones/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zone_id: newZoneId })
    });
  } catch (e) {
    console.error("Failed to switch active zone:", e);
  }
  await fetchZones();
  await fetchKnowledge();
  await fetchVideos();
}

function switchZoneSubTab(subTab) {
  activeZoneSubTab = subTab;
  const btnDocs = document.getElementById('btn-subtab-docs');
  const btnVids = document.getElementById('btn-subtab-videos');
  const panelDocs = document.getElementById('subpanel-docs');
  const panelVids = document.getElementById('subpanel-videos');

  if (subTab === 'docs') {
    if (btnDocs) btnDocs.classList.add('active');
    if (btnVids) btnVids.classList.remove('active');
    if (panelDocs) panelDocs.style.display = 'block';
    if (panelVids) panelVids.style.display = 'none';
    fetchKnowledge();
  } else {
    if (btnDocs) btnDocs.classList.remove('active');
    if (btnVids) btnVids.classList.add('active');
    if (panelDocs) panelDocs.style.display = 'none';
    if (panelVids) panelVids.style.display = 'block';
    fetchVideos();
  }
}

function openAddZoneModal() {
  const nameInput = document.getElementById('new-zone-name');
  const descInput = document.getElementById('new-zone-desc');
  const iconInput = document.getElementById('new-zone-icon');
  if (nameInput) nameInput.value = "";
  if (descInput) descInput.value = "";
  if (iconInput) iconInput.value = "🏛️";
  const modal = document.getElementById('zone-modal');
  if (modal) modal.style.display = 'flex';
}

function closeAddZoneModal() {
  const modal = document.getElementById('zone-modal');
  if (modal) modal.style.display = 'none';
}

async function saveNewZone() {
  const nameInput = document.getElementById('new-zone-name');
  const descInput = document.getElementById('new-zone-desc');
  const iconInput = document.getElementById('new-zone-icon');
  const name = nameInput ? nameInput.value.trim() : '';
  const desc = descInput ? descInput.value.trim() : '';
  const icon = iconInput ? iconInput.value.trim() : '🏛️';

  if (!name) {
    alert("请输入知识区名称！");
    return;
  }

  try {
    const res = await fetch('/api/zones', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, description: desc, icon })
    });
    if (res.ok) {
      const data = await res.json();
      closeAddZoneModal();
      await fetchZones();
      if (data.zone && data.zone.id) {
        handleZoneChange(data.zone.id);
      }
      alert(`知识区【${name}】创建成功！`);
    } else {
      const err = await res.json();
      alert("创建知识区失败: " + (err.error || ""));
    }
  } catch (err) {
    alert("请求出错: " + err);
  }
}

// ================= 📄 权威文本知识库与文件档案仓 (RAG) =================

let docViewMode = 'files';
let allZoneChunks = [];

function formatBytes(bytes) {
  if (!bytes || bytes <= 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function getFileIconBadge(fileType, fileName) {
  const ft = (fileType || '').toLowerCase();
  const fn = (fileName || '').toLowerCase();
  if (ft.includes('docx') || fn.endsWith('.docx') || fn.endsWith('.doc')) {
    return `<span class="doc-file-icon icon-docx">🟦 DOCX</span>`;
  }
  if (ft.includes('pdf') || fn.endsWith('.pdf')) {
    return `<span class="doc-file-icon icon-pdf">🟥 PDF</span>`;
  }
  if (ft.includes('md') || fn.endsWith('.md') || fn.endsWith('.markdown')) {
    return `<span class="doc-file-icon icon-md">⬛ Markdown</span>`;
  }
  if (ft.includes('txt') || fn.endsWith('.txt')) {
    return `<span class="doc-file-icon icon-txt">🟩 TXT</span>`;
  }
  if (ft.includes('csv') || fn.endsWith('.csv')) {
    return `<span class="doc-file-icon icon-json">🟨 CSV</span>`;
  }
  if (ft.includes('json') || fn.endsWith('.json')) {
    return `<span class="doc-file-icon icon-json">🟨 JSON</span>`;
  }
  if (ft.includes('manual')) {
    return `<span class="doc-file-icon icon-manual">📝 手动录入</span>`;
  }
  return `<span class="doc-file-icon icon-md">📄 知识档案</span>`;
}

function switchDocViewMode(mode) {
  docViewMode = mode;
  const btnFiles = document.getElementById('btn-view-files');
  const btnChunks = document.getElementById('btn-view-chunks');
  const btnTester = document.getElementById('btn-view-tester');
  const secFiles = document.getElementById('sec-view-files');
  const secChunks = document.getElementById('sec-view-chunks');
  const secTester = document.getElementById('sec-view-tester');

  if (btnFiles) btnFiles.classList.toggle('active', mode === 'files');
  if (btnChunks) btnChunks.classList.toggle('active', mode === 'chunks');
  if (btnTester) btnTester.classList.toggle('active', mode === 'tester');

  if (secFiles) secFiles.style.display = (mode === 'files' ? 'block' : 'none');
  if (secChunks) secChunks.style.display = (mode === 'chunks' ? 'block' : 'none');
  if (secTester) secTester.style.display = (mode === 'tester' ? 'block' : 'none');

  if (mode === 'chunks') {
    fetchKnowledgeChunks();
  }
}

async function fetchKnowledge() {
  try {
    const res = await fetch(`/api/knowledge?zone_id=${activeZoneId}`);
    if (!res.ok) return;
    const data = await res.json();
    allDocs = data.documents || [];

    const totalCountEl = document.getElementById('knowledge-total-count');
    const viewFilesCountEl = document.getElementById('view-files-count');
    const subCountEl = document.getElementById('subtab-doc-count');
    const viewChunksCountEl = document.getElementById('view-chunks-count');

    let totalChunks = 0;
    allDocs.forEach(d => {
      totalChunks += (d.total_chunks || 0);
    });

    if (totalCountEl) totalCountEl.textContent = allDocs.length;
    if (viewFilesCountEl) viewFilesCountEl.textContent = allDocs.length;
    if (subCountEl) subCountEl.textContent = allDocs.length;
    if (viewChunksCountEl) viewChunksCountEl.textContent = totalChunks;

    const container = document.getElementById('docs-container');
    if (!container) return;

    if (allDocs.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">📖</div>
          <p>当前知识区暂无文档档案，请上传 Word、Markdown、PDF 或文本文件</p>
        </div>`;
      return;
    }

    container.innerHTML = allDocs.map(doc => {
      const fileName = doc.file_name || doc.title || '未命名文件';
      const isPhysical = Boolean(doc.has_physical_file);
      const sizeText = formatBytes(doc.file_size);
      const iconBadge = getFileIconBadge(doc.file_type, fileName);
      const statusBadge = isPhysical 
        ? `<span class="archive-status-badge">✅ 物理原件已归档 (${sizeText})</span>`
        : `<span class="archive-status-manual">📝 在线录入/预置档案 (${sizeText})</span>`;

      return `
      <div class="doc-card">
        <div class="doc-header">
          <div class="doc-title" style="flex-wrap:wrap; gap:8px;">
            ${iconBadge}
            <strong style="color:#0f172a; font-size:15px;">《${escapeHtml(fileName)}》</strong>
            <span class="doc-tag">${escapeHtml(doc.category || '通用')}</span>
            ${statusBadge}
          </div>
          <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
            <button class="btn btn-sm btn-download" onclick="downloadDocument('${doc.id}')" title="下载服务器保存的原始物理文件">
              ⬇️ 下载原件
            </button>
            <button class="btn btn-sm btn-secondary" onclick="openDocViewModal('${doc.id}')">
              🔍 查看切片 (${doc.qa_count || 0}问答 / ${doc.fact_count || 0}事实)
            </button>
            <button class="btn btn-sm btn-danger-outline" onclick="deleteKnowledgeDoc('${doc.id}', '${escapeHtml(fileName)}')">
              🗑️ 级联删除
            </button>
          </div>
        </div>
        ${doc.summary ? `<div class="doc-summary"><strong>💡 AI 核心摘要：</strong>${escapeHtml(doc.summary)}</div>` : ''}
        <div class="doc-footer">
          <span style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
            <span>所属知识区: <strong>${escapeHtml(doc.zone_name || '白城火车园区知识区')}</strong></span>
            <span>切片溯源: <strong>${doc.total_chunks || 0}</strong> 块 (${doc.qa_count || 0} FAQ / ${doc.fact_count || 0} 核心事实)</span>
          </span>
          <span>归档时间: ${escapeHtml(doc.created_at || '')}</span>
        </div>
      </div>
      `;
    }).join('');
  } catch (err) {
    console.error("fetchKnowledge error:", err);
  }
}

function downloadDocument(docId) {
  if (!docId) return;
  const downloadUrl = `/api/documents/${docId}/download`;
  window.open(downloadUrl, '_blank');
}

async function fetchKnowledgeChunks() {
  const container = document.getElementById('chunks-container');
  if (container) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="spinner" style="margin: 0 auto 12px;"></div>
        <p>正在读取当前知识区切片与文件溯源数据...</p>
      </div>`;
  }

  try {
    const res = await fetch(`/api/knowledge/chunks?zone_id=${activeZoneId}&limit=500`);
    if (!res.ok) return;
    const data = await res.json();
    allZoneChunks = data.chunks || [];

    // Populate document filter dropdown
    const docSelect = document.getElementById('chunk-filter-doc');
    if (docSelect) {
      const uniqueDocs = [];
      const seenIds = new Set();
      allZoneChunks.forEach(ch => {
        if (!seenIds.has(ch.doc_id)) {
          seenIds.add(ch.doc_id);
          uniqueDocs.push({ id: ch.doc_id, name: ch.source_file_name || ch.doc_title });
        }
      });
      const curVal = docSelect.value;
      docSelect.innerHTML = `<option value="all">📁 全部来源文件 (${uniqueDocs.length}个文件)</option>` +
        uniqueDocs.map(d => `<option value="${d.id}" ${d.id === curVal ? 'selected' : ''}>📄 《${escapeHtml(d.name)}》</option>`).join('');
    }

    const countEl = document.getElementById('all-chunks-count');
    const viewChunksCountEl = document.getElementById('view-chunks-count');
    if (countEl) countEl.textContent = allZoneChunks.length;
    if (viewChunksCountEl) viewChunksCountEl.textContent = allZoneChunks.length;

    filterChunksView();
  } catch (err) {
    console.error("fetchKnowledgeChunks error:", err);
  }
}

function filterChunksView() {
  const docFilter = document.getElementById('chunk-filter-doc') ? document.getElementById('chunk-filter-doc').value : 'all';
  const typeFilter = document.getElementById('chunk-filter-type') ? document.getElementById('chunk-filter-type').value : 'all';
  const kwFilter = document.getElementById('chunk-filter-kw') ? document.getElementById('chunk-filter-kw').value.trim().toLowerCase() : '';

  let filtered = allZoneChunks;

  if (docFilter && docFilter !== 'all') {
    filtered = filtered.filter(ch => ch.doc_id === docFilter);
  }
  if (typeFilter && typeFilter !== 'all') {
    filtered = filtered.filter(ch => ch.chunk_type === typeFilter);
  }
  if (kwFilter) {
    filtered = filtered.filter(ch => {
      const q = (ch.question || '').toLowerCase();
      const c = (ch.content || '').toLowerCase();
      const t = (ch.title || '').toLowerCase();
      const f = (ch.source_file_name || '').toLowerCase();
      return q.includes(kwFilter) || c.includes(kwFilter) || t.includes(kwFilter) || f.includes(kwFilter);
    });
  }

  const container = document.getElementById('chunks-container');
  if (!container) return;

  if (filtered.length === 0) {
    container.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">🔍</div>
        <p>没有找到符合筛选条件的知识切片</p>
      </div>`;
    return;
  }

  container.innerHTML = filtered.map((ch, idx) => {
    const isQa = ch.chunk_type === 'qa';
    const sourceFileName = ch.source_file_name || ch.doc_title || '未知文件';
    return `
      <div class="chunk-card">
        <div class="chunk-header">
          <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
            <span class="source-file-badge" title="来源文件: ${escapeHtml(sourceFileName)}">
              📎 来源文件: 《${escapeHtml(sourceFileName)}》
            </span>
            <span style="font-size:12px; font-weight:700; color:${isQa ? '#2563eb' : '#059669'};">
              ${isQa ? '🧩 FAQ 问答对' : '📄 核心事实切片'} #${idx+1}
            </span>
            ${ch.title ? `<span style="font-size:11px; color:#64748b;">(${escapeHtml(ch.title)})</span>` : ''}
          </div>
          <button class="btn btn-sm btn-outline" style="font-size:11px; padding:2px 8px;" onclick="openDocViewModal('${ch.doc_id}')">
            📖 查看所属文件
          </button>
        </div>
        ${ch.question ? `<div style="font-size:13px; font-weight:700; color:#0f172a; margin-top:2px;">问: ${escapeHtml(ch.question)}</div>` : ''}
        <div style="font-size:13px; color:#334155; line-height:1.5;">${ch.question ? '答: ' : ''}${escapeHtml(ch.content || '')}</div>
      </div>
    `;
  }).join('');
}

// File Drag & Drop Upload for Documents
function setupDocDropZone() {
  const uploadZone = document.getElementById('upload-zone');
  if (!uploadZone) return;

  ['dragenter', 'dragover'].forEach(name => {
    uploadZone.addEventListener(name, (e) => {
      e.preventDefault();
      uploadZone.classList.add('dragover');
    }, false);
  });
  ['dragleave', 'drop'].forEach(name => {
    uploadZone.addEventListener(name, (e) => {
      e.preventDefault();
      uploadZone.classList.remove('dragover');
    }, false);
  });
  uploadZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) uploadFile(files[0]);
  }, false);
}

function handleFileSelected(event) {
  const file = event.target.files[0];
  if (file) uploadFile(file);
}

async function uploadFile(file) {
  const progressBox = document.getElementById('upload-progress');
  const titleText = document.getElementById('upload-status-title');
  const detailText = document.getElementById('upload-status-detail');

  if (progressBox) progressBox.style.display = 'flex';
  if (titleText) titleText.textContent = `正在持久化归档: ${file.name}...`;
  if (detailText) detailText.textContent = "正在保存物理原件至服务器档案仓、提取高频 FAQ 问答与语义切片...";

  const formData = new FormData();
  formData.append('file', file);
  formData.append('zone_id', activeZoneId);

  try {
    const res = await fetch('/api/knowledge/upload', {
      method: 'POST',
      body: formData
    });
    const result = await res.json();
    if (res.ok) {
      const isAi = result.mode === 'ai_distilled';
      const modelName = result.model || currentConfig.model_name || 'DeepSeek';
      const modeDesc = isAi ? `✨ ${modelName} 深度蒸馏` : '本地高精切片';
      if (titleText) titleText.textContent = `🎉 归档入库完成: 《${result.title}》 (${modeDesc})`;
      let detailMsg = `已持久化保存物理原件 (${formatBytes(result.file_size)})，提炼 ${result.qa_count} 个 FAQ 与 ${result.fact_count} 个事实切片入库【${result.zone_name}】`;
      if (result.warning) {
        detailMsg += `\n⚠️ 提示: ${result.warning}`;
      }
      if (detailText) detailText.textContent = detailMsg;
      setTimeout(() => {
        if (progressBox) progressBox.style.display = 'none';
      }, 5000);
      await fetchKnowledge();
      if (docViewMode === 'chunks') {
        await fetchKnowledgeChunks();
      }
      await fetchZones();
      await fetchStatus();
    } else {
      alert("上传失败: " + (result.error || "未知错误"));
      if (progressBox) progressBox.style.display = 'none';
    }
  } catch (err) {
    alert("请求出错: " + err);
    if (progressBox) progressBox.style.display = 'none';
  }
}

async function openDocViewModal(docId) {
  try {
    const res = await fetch(`/api/knowledge/${docId}`);
    const data = await res.json();
    const doc = data.document;

    const fileName = doc.file_name || doc.title || '未命名知识文档';
    const sizeText = formatBytes(doc.file_size);
    const chunks = doc.chunks || [];

    document.getElementById('doc-view-title').textContent = `📖 档案详情与切片溯源: 《${fileName}》`;
    const body = document.getElementById('doc-view-body');

    body.innerHTML = `
      <div style="background:#f1f5f9; border:1px solid #cbd5e1; border-radius:10px; padding:12px 16px; margin-bottom:14px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div style="font-size:13px; color:#334155; line-height:1.6;">
          <div><strong>📁 原始文件名:</strong> 《${escapeHtml(fileName)}》 ${getFileIconBadge(doc.file_type, fileName)}</div>
          <div><strong>📏 文件大小:</strong> <span class="file-size-badge">${sizeText}</span> · <strong>所属分类:</strong> <span class="doc-tag">${escapeHtml(doc.category || '通用')}</span> · <strong>所属知识区:</strong> ${escapeHtml(doc.zone_name || '白城火车园区知识区')}</div>
          <div><strong>🧩 知识切片统计:</strong> 共 ${chunks.length} 块 (${doc.qa_count || 0} 个问答对 / ${doc.fact_count || 0} 个核心事实)</div>
        </div>
        <div>
          <button class="btn btn-sm btn-download" onclick="downloadDocument('${doc.id}')">
            ⬇️ 下载此文档原件
          </button>
        </div>
      </div>
      ${doc.summary ? `<div class="doc-summary" style="margin-bottom:14px;"><strong>💡 AI 核心摘要：</strong>${escapeHtml(doc.summary)}</div>` : ''}
      <h4 style="font-size:14px; margin-bottom:10px; color:#0f172a;">🧩 来源切片列表 (${chunks.length} 块):</h4>
      <div style="display:flex; flex-direction:column; gap:10px; max-height:450px; overflow-y:auto;">
        ${chunks.map((ch, idx) => `
          <div style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:10px; padding:12px 16px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; flex-wrap:wrap; gap:6px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <span class="source-file-badge">📎 来源文件: 《${escapeHtml(fileName)}》</span>
                <span style="font-size:12px; font-weight:700; color:${ch.chunk_type === 'qa' ? '#2563eb' : '#059669'};">
                  ${ch.chunk_type === 'qa' ? '🧩 标准 FAQ 问答对' : '📄 核心事实切片'} #${idx+1}
                </span>
              </div>
              <span style="font-size:11px; color:#94a3b8;">${escapeHtml(ch.title || '')}</span>
            </div>
            ${ch.question ? `<div style="font-size:13px; font-weight:700; color:#1e293b; margin-bottom:4px;">问: ${escapeHtml(ch.question)}</div>` : ''}
            <div style="font-size:13px; color:#475569; line-height:1.5;">${ch.question ? '答: ' : ''}${escapeHtml(ch.content || '')}</div>
          </div>
        `).join('')}
      </div>
    `;

    document.getElementById('doc-view-modal').style.display = 'flex';
  } catch (err) {
    alert("读取切片失败: " + err);
  }
}

function closeDocViewModal() {
  document.getElementById('doc-view-modal').style.display = 'none';
}

async function testSearchKnowledge() {
  const query = document.getElementById('rag-query-input').value.trim();
  if (!query) return;

  const box = document.getElementById('search-results-box');
  box.style.display = 'block';
  box.innerHTML = `<div style="font-size:13px; color:#64748b; padding:10px;">🔍 检索匹配中...</div>`;

  try {
    const res = await fetch('/api/knowledge/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: query, top_k: 4, min_score: 0.01 })
    });
    const data = await res.json();

    if (!data.results || data.results.length === 0) {
      box.innerHTML = `
        <div class="search-match-item" style="border-color:#e2e8f0; color:#64748b;">
          未匹配到相关度高于阈值的知识切片 (极速耗时: ${data.cost_ms}ms)
        </div>`;
      return;
    }

    box.innerHTML = `
      <div style="font-size:13px; color:#16a34a; font-weight:700; margin-top:10px; margin-bottom:8px;">
        🎯 检索完成！匹配到 ${data.results.length} 个高相关知识切片 (极速耗时: ${data.cost_ms}ms)
      </div>
      ${data.results.map((r, i) => {
        const sourceFile = r.source_file_name || r.file_name || r.title || '未知文件';
        const isQa = r.type === 'qa';
        return `
        <div class="search-match-item">
          <div class="search-match-source">
            <span class="source-file-badge">📎 溯源归属文件: 《${escapeHtml(sourceFile)}》</span>
            <span style="font-size:11px; color:#64748b; background:#f1f5f9; padding:2px 6px; border-radius:4px;">知识区: ${escapeHtml(r.zone_name || '')}</span>
          </div>
          <div class="search-match-header">
            <span>[${i+1}] ${isQa ? '🧩 FAQ 问答' : '📄 核心事实'}: 《${escapeHtml(r.title || '')}》</span>
            <span style="font-size:12px; color:#0284c7; background:#e0f2fe; padding:2px 8px; border-radius:4px;">得分: ${r.rrf_score ? r.rrf_score.toFixed(4) : (r.score || '-')}</span>
          </div>
          ${r.question ? `<div style="font-weight:700; color:#0f172a; margin-bottom:4px; font-size:13px;">匹配问题: ${escapeHtml(r.question)}</div>` : ''}
          <div style="color:#334155; line-height:1.5; font-size:13px;">${escapeHtml(r.content || '')}</div>
        </div>
        `;
      }).join('')}
    `;
  } catch (err) {
    box.innerHTML = `<div style="color:#dc2626; font-size:13px; padding:10px;">检索失败: ${err}</div>`;
  }
}

function openAddDocModal() {
  document.getElementById('doc-category').value = "历史机车档案";
  document.getElementById('doc-title').value = "";
  document.getElementById('doc-content').value = "";
  document.getElementById('doc-modal').style.display = 'flex';
}

function closeDocModal() {
  document.getElementById('doc-modal').style.display = 'none';
}

async function saveKnowledgeDoc() {
  const title = document.getElementById('doc-title').value.trim();
  const category = document.getElementById('doc-category').value.trim() || "通用";
  const content = document.getElementById('doc-content').value.trim();

  if (!title || !content) {
    alert("请填写完整的文档标题和知识正文！");
    return;
  }

  try {
    const res = await fetch('/api/knowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, content, zone_id: activeZoneId })
    });
    if (res.ok) {
      closeDocModal();
      await fetchKnowledge();
      if (docViewMode === 'chunks') {
        await fetchKnowledgeChunks();
      }
      await fetchZones();
      await fetchStatus();
      alert("知识文档已成功保存并建立索引！");
    } else {
      const err = await res.json();
      alert("保存失败: " + (err.error || ""));
    }
  } catch (err) {
    alert("请求出错: " + err);
  }
}

async function deleteKnowledgeDoc(docId, fileName) {
  const nameDesc = fileName ? `《${fileName}》` : '该知识文档';
  const msg = `⚠️ 危险操作确认：\n\n确定要彻底删除文件档案 ${nameDesc} 吗？\n\n该操作将执行级联清除：\n1. 从本地磁盘彻底删除保存的原件文件\n2. 从数据库删除此文档记录及其全部知识切片\n3. 同步清理 SQLite FTS5 全文搜索与向量检索索引\n\n此操作不可逆，是否继续删除？`;

  if (!confirm(msg)) return;

  try {
    const res = await fetch(`/api/documents/${docId}`, { method: 'DELETE' });
    if (res.ok) {
      await fetchKnowledge();
      if (docViewMode === 'chunks') {
        await fetchKnowledgeChunks();
      }
      await fetchZones();
      await fetchStatus();
      alert(`文件档案 ${nameDesc} 及全部关联切片已彻底级联删除！`);
    } else {
      const err = await res.json();
      alert("删除失败: " + (err.error || "未知错误"));
    }
  } catch (err) {
    alert("删除请求出错: " + err);
  }
}

// ================= 🎬 展播视频资产库管理 =================

async function fetchVideos() {
  try {
    const res = await fetch(`/api/videos?zone_id=${activeZoneId}`);
    if (!res.ok) return;
    const data = await res.json();
    allVideos = data.videos || [];

    const vidTotalEl = document.getElementById('videos-total-count');
    const subVidCountEl = document.getElementById('subtab-vid-count');
    if (vidTotalEl) vidTotalEl.textContent = allVideos.length;
    if (subVidCountEl) subVidCountEl.textContent = allVideos.length;

    const container = document.getElementById('videos-container');
    if (!container) return;

    if (allVideos.length === 0) {
      container.innerHTML = `
        <div class="empty-state" style="grid-column: 1 / -1;">
          <div class="empty-icon">🎬</div>
          <p>当前知识区暂无视频展项，请在上方传入机车展播视频文件 (.mp4/.mkv)</p>
        </div>`;
      return;
    }

    container.innerHTML = allVideos.map(vid => {
      const isPresent = vid.is_present;
      const statusBadge = isPresent
        ? `<span class="badge badge-success" style="font-size:11px;">✅ 已存入视频库 (${(vid.file_size / 1024 / 1024).toFixed(1)} MB)</span>`
        : `<span class="badge" style="background:#fee2e2; color:#b91c1c; font-size:11px;">⏳ 待上传物理视频文件</span>`;

      const linkBadge = vid.has_knowledge_linked
        ? `<span class="badge" style="background:#dbeafe; color:#1d4ed8; font-size:11px; margin-left:4px;">✨ 已深度联动知识库 (${(vid.linked_qa_count || 0) + (vid.linked_fact_count || 0)}条)</span>`
        : '';

      const aliasesHtml = (vid.aliases && vid.aliases.length > 0)
        ? vid.aliases.map(a => `<span class="alias-pill">${escapeHtml(a)}</span>`).join('')
        : '<span style="color:#94a3b8; font-size:11px;">未设置触发口令</span>';

      return `
        <div class="video-card">
          <div>
            <div class="video-card-top">
              <div>
                <div class="video-card-title">🎬 《${escapeHtml(vid.title || vid.file_name)}》</div>
                <div class="video-card-meta">
                  <span><strong>文件:</strong> <code>${escapeHtml(vid.file_name)}</code></span>
                  <span><strong>展区:</strong> ${escapeHtml(vid.category || vid.zone || '展区大屏')}</span>
                </div>
              </div>
              <div style="display:flex; flex-direction:column; align-items:flex-end; gap:4px;">
                ${statusBadge}
                ${linkBadge}
              </div>
            </div>

            <div style="font-size:13px; color:#475569; margin: 10px 0 8px 0; line-height:1.5;">
              ${escapeHtml(vid.description || '')}
            </div>

            <div class="video-aliases-box">
              <strong style="color:#1e3a8a;">🗣️ 语音口令触发词 (说出即可全屏播放)：</strong><br>
              <div style="margin-top:4px;">${aliasesHtml}</div>
            </div>
          </div>

          <div class="video-actions">
            <div>
              <button class="btn btn-primary btn-sm" onclick="testPlayVideo('${vid.video_id}', '${escapeHtml(vid.file_name)}')">
                ▶️ 全屏试播测试
              </button>
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-primary-outline btn-sm" onclick="openAiLinkModal('${vid.video_id}', '${escapeHtml(vid.title || vid.file_name)}')">
                🤖 AI 知识联动
              </button>
              <button class="btn btn-secondary btn-sm" onclick="openEditVideoModal('${vid.video_id}')">
                ✏️ 编辑口令
              </button>
              <button class="btn btn-danger-outline btn-sm" onclick="deleteVideo('${vid.video_id}', '${escapeHtml(vid.file_name)}')">
                🗑️
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("fetchVideos error:", err);
  }
}

function setupVideoDropZone() {
  const dropZone = document.getElementById('video-drop-zone');
  if (!dropZone) return;

  ['dragenter', 'dragover'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    }, false);
  });
  ['dragleave', 'drop'].forEach(name => {
    dropZone.addEventListener(name, (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
    }, false);
  });
  dropZone.addEventListener('drop', (e) => {
    const dt = e.dataTransfer;
    const files = dt.files;
    if (files.length > 0) uploadVideoFile(files[0]);
  }, false);
}

function handleVideoFileSelected(event) {
  const file = event.target.files[0];
  if (file) uploadVideoFile(file);
}

async function uploadVideoFile(file) {
  const progressBox = document.getElementById('video-upload-progress');
  const titleText = document.getElementById('video-upload-status-title');
  const detailText = document.getElementById('video-upload-status-detail');

  if (progressBox) progressBox.style.display = 'flex';
  if (titleText) titleText.textContent = `正在传输视频: ${file.name}...`;
  if (detailText) detailText.textContent = "正在将视频写入后台专属视频库，并注册语音口令别名...";

  const transcript = document.getElementById('video-upload-transcript')?.value.trim() || '';
  const formData = new FormData();
  formData.append('file', file);
  formData.append('zone_id', activeZoneId);
  if (transcript) {
    formData.append('transcript_text', transcript);
    if (detailText) detailText.textContent = "正在将视频写入后台，并调用 AI 智能识别内容、提炼口令及蒸馏知识切片...";
  }

  try {
    const res = await fetch('/api/videos/upload', {
      method: 'POST',
      body: formData
    });
    const result = await res.json();
    if (res.ok) {
      if (titleText) titleText.textContent = `🎉 视频上传成功: 《${file.name}》`;
      if (detailText) detailText.textContent = result.message || "视频已就绪，可随时呼叫小智或点击试播！";
      const transInput = document.getElementById('video-upload-transcript');
      if (transInput) transInput.value = '';
      setTimeout(() => {
        if (progressBox) progressBox.style.display = 'none';
      }, 4000);
      fetchVideos();
      fetchKnowledge();
      fetchZones();
    } else {
      alert("视频上传失败: " + (result.error || "未知错误"));
      if (progressBox) progressBox.style.display = 'none';
    }
  } catch (err) {
    alert("上传出错: " + err);
    if (progressBox) progressBox.style.display = 'none';
  }
}

function openAiLinkModal(videoId, title) {
  document.getElementById('ai-link-video-id').value = videoId;
  document.getElementById('ai-link-video-title').textContent = title || videoId;
  document.getElementById('ai-link-text-input').value = '';
  document.getElementById('ai-link-result-box').style.display = 'none';
  document.getElementById('ai-link-result-content').innerHTML = '';
  const btn = document.getElementById('btn-submit-ai-link');
  if (btn) {
    btn.disabled = false;
    btn.textContent = '✨ 开始 AI 智能解析与知识库联动';
  }
  document.getElementById('video-ai-link-modal').style.display = 'flex';
}

function closeAiLinkModal() {
  document.getElementById('video-ai-link-modal').style.display = 'none';
}

async function submitAiLink() {
  const videoId = document.getElementById('ai-link-video-id').value;
  const text = document.getElementById('ai-link-text-input').value.trim();
  const btn = document.getElementById('btn-submit-ai-link');
  const resultBox = document.getElementById('ai-link-result-box');
  const resultContent = document.getElementById('ai-link-result-content');

  if (!text) {
    alert("请简短输入视频描述或粘贴字幕/音频文字！");
    return;
  }

  btn.disabled = true;
  btn.textContent = '⏳ AI 正在深度理解内容并生成知识切片...';

  try {
    const res = await fetch('/api/videos/ai-link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ video_id: videoId, text: text, zone_id: activeZoneId })
    });
    const data = await res.json();
    if (res.ok) {
      const r = data.result;
      resultBox.style.display = 'block';
      resultContent.innerHTML = `
        <div style="margin-bottom:8px;"><strong>🎬 规范标题:</strong> 《${escapeHtml(r.title)}》</div>
        <div style="margin-bottom:8px;"><strong>🏷️ 识别分类:</strong> <span class="badge" style="background:#e0f2fe; color:#0369a1;">${escapeHtml(r.category)}</span></div>
        <div style="margin-bottom:8px;"><strong>🗣️ 提炼口令 (${r.aliases ? r.aliases.length : 0}个):</strong> ${(r.aliases || []).slice(0, 10).map(a => `<span class="alias-pill">${escapeHtml(a)}</span>`).join('')}</div>
        <div style="margin-bottom:8px;"><strong>🧩 生成问答:</strong> ${r.qa_pairs ? r.qa_pairs.length : 0} 条标准 FAQ 问答对已入库</div>
        <div><strong>📄 事实切片:</strong> ${r.fact_chunks ? r.fact_chunks.length : 0} 条事实切片已同步建立多媒体双向关联！</div>
      `;
      btn.disabled = false;
      btn.textContent = '✅ 已成功联动知识库';
      fetchVideos();
      fetchKnowledge();
      fetchZones();
    } else {
      alert("AI 联动失败: " + (data.error || ""));
      btn.disabled = false;
      btn.textContent = '重试 AI 联动';
    }
  } catch (err) {
    alert("请求出错: " + err);
    btn.disabled = false;
    btn.textContent = '重试 AI 联动';
  }
}

async function testPlayVideo(videoId, fileName) {
  const keyword = fileName || videoId;
  try {
    const res = await fetch('/api/videos/play_test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: keyword })
    });
    const data = await res.json();
    if (res.ok) {
      alert(`🎬 指令已下达！\n正在您的电脑原生播放器上全屏播放：《${data.result.title || keyword}》！`);
    } else {
      alert("播放失败: " + (data.error || ""));
    }
  } catch (err) {
    alert("请求异常: " + err);
  }
}

function openEditVideoModal(videoId) {
  const vid = allVideos.find(v => v.video_id === videoId || v.file_name === videoId);
  if (!vid) return;

  document.getElementById('edit-video-id').value = vid.video_id;
  document.getElementById('edit-video-title').value = vid.title || "";
  document.getElementById('edit-video-category').value = vid.category || vid.zone || "";
  document.getElementById('edit-video-aliases').value = (vid.aliases || []).join(', ');
  document.getElementById('edit-video-desc').value = vid.description || "";
  document.getElementById('video-edit-modal').style.display = 'flex';
}

function closeVideoEditModal() {
  document.getElementById('video-edit-modal').style.display = 'none';
}

async function saveVideoEdit() {
  const videoId = document.getElementById('edit-video-id').value;
  const title = document.getElementById('edit-video-title').value.trim();
  const category = document.getElementById('edit-video-category').value.trim();
  const aliasesStr = document.getElementById('edit-video-aliases').value.trim();
  const description = document.getElementById('edit-video-desc').value.trim();

  const aliases = aliasesStr.replace(/，/g, ',').split(',').map(s => s.trim()).filter(Boolean);

  try {
    const res = await fetch(`/api/videos/${videoId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category, aliases, description })
    });
    if (res.ok) {
      closeVideoEditModal();
      fetchVideos();
      alert("视频展项与口令已成功更新！");
    } else {
      const err = await res.json();
      alert("修改失败: " + (err.error || ""));
    }
  } catch (err) {
    alert("请求出错: " + err);
  }
}

async function deleteVideo(videoId, fileName) {
  if (!confirm(`确定要从知识区中删除视频《${fileName || videoId}》吗？`)) return;
  try {
    const res = await fetch(`/api/videos/${videoId}`, { method: 'DELETE' });
    if (res.ok) {
      fetchVideos();
      fetchZones();
    } else {
      const err = await res.json();
      alert("删除失败: " + (err.error || ""));
    }
  } catch (err) {
    alert("删除异常: " + err);
  }
}

// ================= Roles & Personas =================
async function fetchRoles() {
  try {
    if (!allZones || allZones.length === 0) {
      await fetchZones();
    }
    const res = await fetch('/api/roles');
    if (!res.ok) return;
    const data = await res.json();
    allRoles = data.roles || [];
    const active = data.active_role || {};
    activeRoleId = active.id;

    // Simulator select options
    const simSelect = document.getElementById('sim-role-select');
    if (simSelect) {
      simSelect.innerHTML = allRoles.map(r => `
        <option value="${r.id}" ${r.id === activeRoleId ? 'selected' : ''}>${r.emoji} ${escapeHtml(r.name)}</option>
      `).join('');
    }

    const container = document.getElementById('roles-container');
    if (!container) return;

    container.innerHTML = allRoles.map(role => {
      const isActive = (role.id === activeRoleId);
      const boundZone = allZones.find(z => z.id === role.zone_id);
      let zoneTagText = '⚪ 未启用知识库';
      if (role.rag_enabled) {
        zoneTagText = boundZone ? `📚 专属: ${boundZone.icon || '🏛️'} ${escapeHtml(boundZone.name)}` : '📚 随全局激活知识区';
      }
      return `
        <div class="role-card ${isActive ? 'active-role' : ''}">
          <div>
            <div class="role-top">
              <div class="role-emoji">${role.emoji || '🤖'}</div>
              <div class="role-title-box">
                <div style="display:flex; align-items:center; gap:8px;">
                  <h3>${escapeHtml(role.name)}</h3>
                  ${isActive ? '<span class="badge badge-success" style="font-size:11px; padding:2px 8px;">活跃中</span>' : ''}
                </div>
                <div class="role-desc">${escapeHtml(role.description || '')}</div>
              </div>
            </div>

            <div class="role-tags">
              <span class="role-tag">🔊 ${role.voice}</span>
              <span class="role-tag">🌡️ Temp: ${role.temperature}</span>
              <span class="role-tag ${role.rag_enabled ? 'highlight' : ''}">
                ${zoneTagText}
              </span>
            </div>

            <div class="role-prompt-preview" title="${escapeHtml(role.system_prompt)}">
              ${escapeHtml(role.system_prompt)}
            </div>
          </div>

          <div class="role-actions">
            <div>
              ${!isActive ? `<button class="btn btn-primary btn-sm" onclick="setActiveRole('${role.id}')">🌟 启用此人设</button>` : '<span style="font-size:12px; color:#10b981; font-weight:700;">✓ 当前正在使用</span>'}
            </div>
            <div style="display:flex; gap:6px;">
              <button class="btn btn-secondary btn-sm" onclick="openEditRoleModal('${role.id}')">✏️ 编辑</button>
              ${!role.is_builtin ? `<button class="btn btn-danger-outline btn-sm" onclick="deleteRole('${role.id}')">🗑️</button>` : ''}
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error("fetchRoles error:", err);
  }
}

function populateRoleZoneSelect(selectedZoneId) {
  const sel = document.getElementById('role-zone-id');
  if (!sel) return;
  let html = '<option value="">⚪ 随全局当前激活知识区</option>';
  if (Array.isArray(allZones)) {
    allZones.forEach(z => {
      const isSel = (z.id === selectedZoneId) ? 'selected' : '';
      html += `<option value="${z.id}" ${isSel}>${z.icon || '🏛️'} ${escapeHtml(z.name)}</option>`;
    });
  }
  sel.innerHTML = html;
}

async function setActiveRole(roleId) {
  try {
    const res = await fetch('/api/roles/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role_id: roleId })
    });
    if (res.ok) {
      fetchRoles();
      fetchStatus();
    }
  } catch (err) {
    alert("切换人设失败: " + err);
  }
}

function openAddRoleModal() {
  document.getElementById('role-modal-title').textContent = "🎭 新建自定义人设";
  document.getElementById('role-edit-id').value = "";
  document.getElementById('role-emoji').value = "🎭";
  document.getElementById('role-name').value = "";
  document.getElementById('role-desc').value = "";
  document.getElementById('role-voice').value = "zh-CN-YunxiNeural";
  document.getElementById('role-temp').value = 0.4;
  document.getElementById('val-temp').textContent = "0.4";
  document.getElementById('role-rag-enabled').value = "true";
  populateRoleZoneSelect("");
  document.getElementById('role-prompt').value = "你是小智专属AI助手，亲切生动地与用户交流。";
  document.getElementById('role-modal').style.display = 'flex';
}

function openEditRoleModal(roleId) {
  const role = allRoles.find(r => r.id === roleId);
  if (!role) return;

  document.getElementById('role-modal-title').textContent = `✏️ 编辑人设: ${role.name}`;
  document.getElementById('role-edit-id').value = role.id;
  document.getElementById('role-emoji').value = role.emoji || "🤖";
  document.getElementById('role-name').value = role.name;
  document.getElementById('role-desc').value = role.description || "";
  document.getElementById('role-voice').value = role.voice;
  document.getElementById('role-temp').value = role.temperature;
  document.getElementById('val-temp').textContent = role.temperature;
  document.getElementById('role-rag-enabled').value = role.rag_enabled ? "true" : "false";
  populateRoleZoneSelect(role.zone_id || "");
  document.getElementById('role-prompt').value = role.system_prompt;
  document.getElementById('role-modal').style.display = 'flex';
}

function closeRoleModal() {
  document.getElementById('role-modal').style.display = 'none';
}

async function saveRoleData() {
  const editId = document.getElementById('role-edit-id').value;
  const roleData = {
    emoji: document.getElementById('role-emoji').value.trim() || "🤖",
    name: document.getElementById('role-name').value.trim(),
    description: document.getElementById('role-desc').value.trim(),
    voice: document.getElementById('role-voice').value,
    temperature: parseFloat(document.getElementById('role-temp').value),
    rag_enabled: document.getElementById('role-rag-enabled').value === "true",
    zone_id: document.getElementById('role-zone-id') ? document.getElementById('role-zone-id').value : "",
    system_prompt: document.getElementById('role-prompt').value.trim(),
  };

  if (editId) roleData.id = editId;

  if (!roleData.name || !roleData.system_prompt) {
    alert("请填写角色名称和人设系统提示词！");
    return;
  }

  try {
    const res = await fetch('/api/roles', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(roleData)
    });
    if (res.ok) {
      closeRoleModal();
      fetchRoles();
      fetchStatus();
    } else {
      const err = await res.json();
      alert("保存人设失败: " + (err.error || ""));
    }
  } catch (err) {
    alert("请求异常: " + err);
  }
}

async function deleteRole(roleId) {
  if (!confirm("确定要删除此自定义人设吗？")) return;
  try {
    const res = await fetch(`/api/roles/${roleId}`, { method: 'DELETE' });
    if (res.ok) {
      fetchRoles();
      fetchStatus();
    } else {
      const err = await res.json();
      alert(err.error || "无法删除");
    }
  } catch (err) {
    alert("删除失败: " + err);
  }
}

// ================= Web Simulator =================
async function sendSimulation() {
  const input = document.getElementById('sim-input');
  const text = input.value.trim();
  if (!text) return;

  const roleSelect = document.getElementById('sim-role-select');
  const selectedRoleId = roleSelect.value;
  const chatView = document.getElementById('sim-chat-view');

  // User bubble
  const userDiv = document.createElement('div');
  userDiv.className = 'sim-msg-user';
  userDiv.textContent = text;
  chatView.appendChild(userDiv);
  input.value = '';
  chatView.scrollTop = chatView.scrollHeight;

  // Pending AI bubble
  const aiDiv = document.createElement('div');
  aiDiv.className = 'sim-msg-ai';
  aiDiv.textContent = "🤔 正在检索知识库并思考回答...";
  chatView.appendChild(aiDiv);
  chatView.scrollTop = chatView.scrollHeight;

  const btn = document.getElementById('btn-sim-send');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch('/api/chat/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, role_id: selectedRoleId })
    });
    const data = await res.json();

    let ragInfo = '';
    if (data.rag_matched && data.rag_matched.length > 0) {
      ragInfo = `<div style="font-size:12px; color:#0284c7; background:#e0f2fe; padding:6px 10px; border-radius:6px; margin-top:8px;">
        📖 命中知识区: ${data.rag_matched.map(m => `《${escapeHtml(m.title)}》${m.question ? `[问: ${escapeHtml(m.question)}]` : ''}`).join(', ')} (${data.metrics ? data.metrics.rag_ms : 0}ms)
      </div>`;
    }

    aiDiv.innerHTML = `
      <div>${escapeHtml(data.assistant_reply || '')}</div>
      ${ragInfo}
      <div class="sim-meta-pill">
        ⚡ 首字: ${data.metrics ? data.metrics.ttft_ms : '-'}ms · 全链路: ${data.metrics ? data.metrics.total_ms : '-'}ms · 音色: ${data.role ? data.role.voice : '-'}
      </div>
    `;
    fetchLogs();
  } catch (err) {
    aiDiv.textContent = "❌ 对话异常: " + err;
  } finally {
    if (btn) btn.disabled = false;
    chatView.scrollTop = chatView.scrollHeight;
  }
}

// ================= System Settings =================
async function loadConfigInputs() {
  try {
    if (!currentConfig || !currentConfig.relay_base_url) {
      const res = await fetch('/api/status');
      if (res.ok) {
        const data = await res.json();
        currentConfig = data.config || {};
      }
    }
    const rUrl = document.getElementById('cfg-relay-url');
    const rKey = document.getElementById('cfg-api-key');
    const rMod = document.getElementById('cfg-model-name');
    const rTts = document.getElementById('cfg-tts-voice');
    const rPrm = document.getElementById('cfg-prompt');

    if (rUrl) rUrl.value = currentConfig.relay_base_url || 'https://api.deepseek.com/v1';
    if (rKey) rKey.value = currentConfig.relay_api_key || '';
    if (rMod) rMod.value = currentConfig.model_name || 'deepseek-chat';
    if (rTts) rTts.value = currentConfig.tts_voice || 'zh-CN-YunxiNeural';
    if (rPrm) rPrm.value = currentConfig.system_prompt || '';
  } catch (e) {
    console.error("loadConfigInputs error:", e);
  }
}

async function saveConfig() {
  const newConfig = {
    relay_base_url: (document.getElementById('cfg-relay-url') ? document.getElementById('cfg-relay-url').value.trim() : ''),
    relay_api_key: (document.getElementById('cfg-api-key') ? document.getElementById('cfg-api-key').value.trim() : ''),
    model_name: (document.getElementById('cfg-model-name') ? document.getElementById('cfg-model-name').value.trim() : ''),
    tts_voice: (document.getElementById('cfg-tts-voice') ? document.getElementById('cfg-tts-voice').value : 'zh-CN-YunxiNeural'),
    system_prompt: (document.getElementById('cfg-prompt') ? document.getElementById('cfg-prompt').value.trim() : ''),
  };

  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(newConfig)
    });
    if (res.ok) {
      fetchStatus();
      alert("全局配置已成功保存！");
    } else {
      alert("保存配置失败");
    }
  } catch (err) {
    alert("保存失败: " + err);
  }
}

// Utility
function escapeHtml(str) {
  if (!str) return '';
  return String(str).replace(/[&<>'"]/g, 
    tag => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[tag] || tag)
  );
}

// ================= Bootstrap Initialization =================

function initApp() {
  setupDocDropZone();
  setupVideoDropZone();

  fetchStatus();
  fetchZones();
  fetchRoles();
  fetchKnowledge();
  fetchVideos();
  fetchLogs();
  loadConfigInputs();

  setInterval(fetchStatus, 2000);
  setInterval(fetchLogs, 1500);
}

if (document.readyState === 'loading') {
  document.addEventListener("DOMContentLoaded", initApp);
} else {
  initApp();
}
