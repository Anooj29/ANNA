// Clinician Dashboard Application Logic

let activeUser = null;
let patientsData = [];
let tasksData = [];
let alertsData = [];
let activeAnalyticsPatientCode = null;
let currentAnalyticsDays = 7;
let vitalsChartInstance = null;
let emotionChartInstance = null;
let ws = null;
let ackAlertId = null;
let demoSimulationEnabled = false;
let patientsPage = 1;
let patientsPages = 1;
let tasksPage = 1;
let alertsPage = 1;
let tasksPages = 1;
let alertsPages = 1;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

// DOM Elements
const loginView = document.getElementById("login-view");
const appView = document.getElementById("app-view");
const loginForm = document.getElementById("login-form");
const loginError = document.getElementById("login-error");
const btnLogout = document.getElementById("btn-logout");
const clinicianName = document.getElementById("clinician-name");

const patientsTableBody = document.getElementById("patients-table-body");
const patientFilterInput = document.getElementById("patient-filter-input");
const tasksTableBody = document.getElementById("tasks-table-body");
const alertsTableBody = document.getElementById("alerts-table-body");
const alertStatusFilter = document.getElementById("alert-status-filter");
const urgentBadge = document.getElementById("urgent-badge");

const taskModal = document.getElementById("task-modal");
const taskModalClose = document.getElementById("task-modal-close");
const taskModalDismiss = document.getElementById("task-modal-dismiss");
const taskAssignmentForm = document.getElementById("task-assignment-form");
const taskPatientSelect = document.getElementById("task-patient-select");
const btnOpenTaskModal = document.getElementById("btn-open-task-modal");
const btnOpenTaskModal2 = document.getElementById("btn-open-task-modal-2");

const analyticsModal = document.getElementById("analytics-modal");
const analyticsClose = document.getElementById("analytics-close");
const analyticsPatientName = document.getElementById("analytics-patient-name");
const analyticsPatientMeta = document.getElementById("analytics-patient-meta");
const wellnessResponsesList = document.getElementById("wellness-responses-list");
const patientMedsBody = document.getElementById("patient-meds-body");
const btnTogglePrescribe = document.getElementById("btn-toggle-prescribe");
const prescribeForm = document.getElementById("prescribe-form");

const ackModal = document.getElementById("ack-modal");
const ackModalClose = document.getElementById("ack-modal-close");
const ackModalDismiss = document.getElementById("ack-modal-dismiss");
const ackForm = document.getElementById("ack-form");
const ackAlertText = document.getElementById("ack-alert-text");

const summariesContainer = document.getElementById("summaries-container");
const summaryPatientFilter = document.getElementById("summary-patient-filter");

// ---- Tab Switching ----
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const tabId = btn.getAttribute("data-tab");
    document.getElementById(tabId).classList.add("active");

    if (tabId === "overview-tab") loadPatients();
    if (tabId === "overview-tab") window.loadPriority?.();
    if (tabId === "analytics-tab") loadClinicianMacroAnalytics();
    if (tabId === "analytics-tab") window.loadOperations?.();
    if (tabId === "queue-tab") loadTasks();
    if (tabId === "alerts-tab") loadAlerts();
    if (tabId === "reports-tab") loadSummaries();
    if (tabId === "audit-tab") window.loadAudit?.();
  });
});

// ---- Authentication ----
async function checkAuth() {
  try {
    const res = await fetch("/api/auth/me");
    const data = await res.json();
    if (data.authenticated && ["doctor", "nurse", "admin"].includes(data.role)) {
      activeUser = data;
      document.getElementById('audit-tab-button').hidden = data.role !== 'admin';
      clinicianName.textContent = data.full_name || "Clinical user";
      loginView.hidden = true;
      appView.hidden = false;
      initDashboard();
    } else {
      loginView.hidden = false;
      appView.hidden = true;
    }
  } catch (err) {
    loginView.hidden = false;
    appView.hidden = true;
  }
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  loginError.hidden = true;
  const username_or_email = document.getElementById("login-email").value.trim();
  const password = document.getElementById("login-password").value;

  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username_or_email, password }),
    });

    if (!res.ok) {
      const err = await res.json();
      loginError.textContent = err.detail || "Authentication failed.";
      loginError.hidden = false;
      return;
    }

    const user = await res.json();
    if (!["doctor", "nurse", "admin"].includes(user.role)) {
      loginError.textContent = "This account does not have clinical workspace access.";
      loginError.hidden = false;
      return;
    }
    activeUser = user;
    document.getElementById('audit-tab-button').hidden = user.role !== 'admin';
    clinicianName.textContent = user.full_name;
    loginView.hidden = true;
    appView.hidden = false;
    initDashboard();
  } catch (err) {
    loginError.textContent = "Network error during login: " + err;
    loginError.hidden = false;
  }
});

btnLogout.addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  if (ws) ws.close();
  activeUser = null;
  loginView.hidden = false;
  appView.hidden = true;
});

// ---- Real-time WebSocket ----
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/hospital`;
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("ws-status-text").textContent = "Live Sync Active";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      console.log("Clinician WS Event:", msg);
      loadStats();
      window.loadNotifications?.();
      if (msg.event === "task_created" || msg.event === "task_updated" || msg.event === "checkup_completed") {
        loadTasks();
        loadPatients();
        window.loadPriority?.();
        if (activeAnalyticsPatientCode) {
          loadPatientAnalytics(activeAnalyticsPatientCode, currentAnalyticsDays);
        }
      }
      if (msg.event === "patient_admitted" || msg.event === "patient_discharged") {
        loadPatients();
        loadPatientOptions();
        window.loadPriority?.();
      }
      if (msg.event === "alert_created" || msg.event === "alert_acknowledged") {
        loadAlerts();
        window.loadPriority?.();
      }
    } catch (e) {
      console.error("WS error:", e);
    }
  };

  ws.onclose = () => {
    document.getElementById("ws-status-text").textContent = "Reconnecting...";
    if (activeUser) setTimeout(initWebSocket, 3000);
  };
}

// ---- Initialization ----
function initDashboard() {
  initWebSocket();
  fetch("/api/capabilities").then((response) => response.json()).then((capabilities) => {
    demoSimulationEnabled = Boolean(capabilities.demo_simulation);
    loadTasks();
  }).catch(() => {});
  loadStats();
  loadPatients();
  loadPatientOptions();
  loadTasks();
  loadAlerts();
  window.loadNotifications?.();
  window.loadPriority?.();
}

// ---- Stats KPIs ----
async function loadStats() {
  try {
    const res = await fetch("/api/clinician/stats");
    if (!res.ok) return;
    const stats = await res.json();
    document.getElementById("kpi-active-patients").textContent = stats.active_patients;
    document.getElementById("kpi-pending-tasks").textContent = stats.pending_tasks;
    document.getElementById("kpi-completed-today").textContent = stats.completed_today;
    document.getElementById("kpi-urgent-alerts").textContent = stats.urgent_alerts;
    document.getElementById("kpi-attention-count").textContent = stats.attention_count;

    if (stats.urgent_alerts > 0) {
      urgentBadge.textContent = stats.urgent_alerts;
      urgentBadge.hidden = false;
    } else {
      urgentBadge.hidden = true;
    }
  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

// ---- Patients Table ----
async function loadPatientOptions() {
  try {
    const response = await fetch('/api/clinician/patient-options');
    if (!response.ok) return;
    const patients = await response.json();
    const selectedTask = taskPatientSelect.value;
    const selectedReport = summaryPatientFilter.value;
    taskPatientSelect.innerHTML = '<option value="" disabled selected>Select an active patient</option>';
    summaryPatientFilter.innerHTML = '<option value="">All Admitted Patients</option>';
    patients.forEach(p => {
      const option = document.createElement('option');
      option.value = p.patient_code;
      option.textContent = `${p.full_name} (${p.patient_code} - Bed ${p.bed_number ?? '—'})`;
      taskPatientSelect.appendChild(option);
      const reportOption = document.createElement('option');
      reportOption.value = p.patient_code;
      reportOption.textContent = `${p.full_name} (${p.patient_code})`;
      summaryPatientFilter.appendChild(reportOption);
    });
    taskPatientSelect.value = selectedTask || '';
    summaryPatientFilter.value = selectedReport || '';
  } catch (_) { /* Existing options remain available on transient errors. */ }
}

async function loadPatients(query = patientFilterInput.value) {
  try {
    const res = await fetch(`/api/patients?active_only=true&query=${encodeURIComponent(query)}&page=${patientsPage}&page_size=20`);
    if (!res.ok) return;
    const result = await res.json();
    patientsPages = Math.max(result.pages, 1);
    if (patientsPage > patientsPages) { patientsPage = patientsPages; return loadPatients(query); }
    patientsData = result.items;
    document.getElementById('patients-page-label').textContent = `Page ${patientsPage} of ${patientsPages}`;
    document.getElementById('patients-prev').disabled = patientsPage <= 1;
    document.getElementById('patients-next').disabled = patientsPage >= patientsPages;

    patientsTableBody.innerHTML = "";

    if (patientsData.length === 0) {
      patientsTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#64748b; padding:2rem;">No matching admitted patients.</td></tr>`;
      return;
    }

    patientsData.forEach((p) => {
      const tr = document.createElement("tr");
      const v = p.latest_vitals;
      tr.innerHTML = `
        <td data-label="Patient">
          <strong style="color:var(--text-main); font-size:0.95rem;">${escapeHtml(p.full_name)}</strong><br>
          <span class="font-mono" style="font-size:0.78rem; color:var(--primary); font-weight:700;">${escapeHtml(p.patient_code)}</span>
        </td>
        <td data-label="Bed">
          <span class="badge" style="font-size:0.82rem; font-weight:700;">Bed ${p.bed_number ? String(p.bed_number).padStart(2, '0') : '--'}</span>
        </td>
        <td data-label="Temperature">
          ${v ? `<strong style="color:${parseFloat(v.temperature) >= 38.0 ? 'var(--urgent)' : 'inherit'};">${escapeHtml(v.temperature)}</strong>` : '<span style="color:#94a3b8;">--</span>'}
        </td>
        <td data-label="Pulse / SpO2">
          ${v ? `<span>${escapeHtml(v.pulse)} · <strong style="color:${parseFloat(v.spo2) < 95.0 ? 'var(--urgent)' : 'inherit'};">${escapeHtml(v.spo2)}</strong></span>` : '<span style="color:#94a3b8;">--</span>'}
        </td>
        <td data-label="ECG Rhythm">
          ${v ? `<span style="font-size:0.8rem; font-weight:600; color:${v.ecg.includes('Irregular') ? 'var(--urgent)' : '#166534'};">${escapeHtml(v.ecg)}</span>` : '<span style="color:#94a3b8;">--</span>'}
        </td>
        <td data-label="Emotion">
          ${v ? `<span class="badge" style="font-size:0.78rem;">${escapeHtml(v.emotion)}</span>` : '<span style="color:#94a3b8;">--</span>'}
        </td>
        <td data-label="Risk Category">
          <span class="risk-badge ${escapeHtml(p.risk_level)}">${escapeHtml(p.risk_level)}</span>
        </td>
        <td data-label="Actions">
          <button class="btn btn-secondary btn-small patient-analytics-action">Analytics</button>
          <button class="btn btn-primary btn-small patient-open-action">Open</button>
          <button class="btn btn-outline btn-small patient-task-action">Assign</button>
        </td>
      `;
      patientsTableBody.appendChild(tr);
      tr.querySelector(".patient-analytics-action").addEventListener("click", () => openPatientAnalytics(p.patient_code));
      tr.querySelector(".patient-open-action").addEventListener("click", () => openPatientWorkspace(p.patient_code));
      tr.querySelector(".patient-task-action").addEventListener("click", () => openTaskModalFor(p.patient_code));
    });
  } catch (err) {
    console.error("Error loading patients:", err);
  }
}

let patientSearchTimer = null;
patientFilterInput.addEventListener("input", (e) => {
  clearTimeout(patientSearchTimer);
  patientSearchTimer = setTimeout(() => { patientsPage = 1; loadPatients(e.target.value); }, 250);
});
document.getElementById('patients-prev').addEventListener('click', () => { if (patientsPage > 1) { patientsPage--; loadPatients(); } });
document.getElementById('patients-next').addEventListener('click', () => { if (patientsPage < patientsPages) { patientsPage++; loadPatients(); } });

// ---- Tasks Table ----
async function loadTasks() {
  try {
    const res = await fetch(`/api/tasks?page=${tasksPage}&page_size=20`);
    if (!res.ok) return;
    const taskResult = await res.json();
    tasksData = taskResult.items;
    tasksPages = Math.max(taskResult.pages, 1);
    document.getElementById('tasks-page-label').textContent = `Page ${tasksPage} of ${tasksPages}`;
    document.getElementById('tasks-prev').disabled = tasksPage <= 1;
    document.getElementById('tasks-next').disabled = tasksPage >= tasksPages;

    tasksTableBody.innerHTML = "";
    if (tasksData.length === 0) {
      tasksTableBody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:#64748b; padding:2rem;">No active robot tasks scheduled.</td></tr>`;
      return;
    }

    tasksData.forEach((t) => {
      const tr = document.createElement("tr");
      const assignedStr = new Date(t.assigned_at).toLocaleTimeString();
      tr.innerHTML = `
        <td class="font-mono font-bold text-primary">#${t.id}</td>
        <td><strong>${escapeHtml(t.patient_name)}</strong><br><small class="font-mono text-muted">${escapeHtml(t.patient_code)}</small></td>
        <td>Bed ${t.bed_number || '--'}</td>
        <td>
          <strong style="font-size:0.85rem;">${escapeHtml(t.task_type)}</strong><br>
          <span style="font-size:0.78rem; color:#64748b;">${escapeHtml(t.current_stage || t.instructions || 'Routine protocol')}</span>
        </td>
        <td><span class="priority-badge ${escapeHtml(t.priority)}">${escapeHtml(t.priority)}</span></td>
        <td><span class="status-badge-task ${escapeHtml(t.status)}">${escapeHtml(t.status)}</span></td>
        <td style="font-size:0.8rem; color:#64748b;">${assignedStr}</td>
        <td>
          ${t.status === "queued" ? `
            ${demoSimulationEnabled ? `<button class="btn btn-primary btn-small" title="Demo simulation only" onclick="simulateRobotCheckup(${t.id})">Demo simulation</button>` : ""}
            <button class="btn btn-secondary btn-small" onclick="cancelTask(${t.id})">Cancel</button>
          ` : (t.status === "completed" ? `<button class="btn btn-secondary btn-small task-report-action">View Report</button>` : `<span style="font-size:0.75rem; color:#64748b;">${escapeHtml(t.current_stage || t.status)}</span>`)}
        </td>
      `;
      tasksTableBody.appendChild(tr);
      tr.querySelector(".task-report-action")?.addEventListener("click", () => openPatientWorkspace(t.patient_code));
    });
  } catch (err) {
    console.error("Error loading tasks:", err);
  }
}

// Simulate Robot Checkup for SIH Demo
window.simulateRobotCheckup = async function(taskId) {
  if (!confirm(`Trigger live simulated ANNA bedside checkup for Task #${taskId}?`)) return;
  try {
    const res = await fetch(`/api/robot/simulate-checkup/${taskId}`, { method: "POST" });
    if (!res.ok) {
      alert("Simulation failed.");
      return;
    }
    loadTasks();
    loadStats();
    loadPatients();
  } catch (e) {
    alert("Error triggering simulation: " + e);
  }
};

window.cancelTask = async function(taskId) {
  if (!confirm(`Cancel Task #${taskId}?`)) return;
  try {
    await fetch(`/api/tasks/${taskId}/cancel`, { method: "POST" });
    loadTasks();
    loadStats();
  } catch (e) {
    alert("Cancel failed: " + e);
  }
};

// ---- Assign Task Modal ----
function openTaskModalFor(patientCode) {
  taskPatientSelect.value = patientCode;
  taskModal.hidden = false;
}

btnOpenTaskModal.addEventListener("click", () => (taskModal.hidden = false));
btnOpenTaskModal2.addEventListener("click", () => (taskModal.hidden = false));
taskModalClose.addEventListener("click", () => (taskModal.hidden = true));
taskModalDismiss.addEventListener("click", () => (taskModal.hidden = true));

taskAssignmentForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const payload = {
    patient_code: taskPatientSelect.value,
    task_type: document.getElementById("task-type-select").value,
    priority: document.getElementById("task-priority-select").value,
    instructions: document.getElementById("task-instructions").value,
  };

  try {
    const res = await fetch("/api/tasks", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      alert("Failed to assign task.");
      return;
    }
    taskModal.hidden = true;
    taskAssignmentForm.reset();
    loadTasks();
    loadStats();
  } catch (err) {
    alert("Network error: " + err);
  }
});

// ---- Patient Analytics Deep Dive ----
window.openPatientAnalytics = async function(patientCode) {
  activeAnalyticsPatientCode = patientCode;
  analyticsModal.hidden = false;
  loadPatientAnalytics(patientCode, currentAnalyticsDays);
};

analyticsClose.addEventListener("click", () => {
  analyticsModal.hidden = true;
  activeAnalyticsPatientCode = null;
});

document.querySelectorAll(".filter-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".filter-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    currentAnalyticsDays = parseInt(btn.getAttribute("data-days"));
    if (activeAnalyticsPatientCode) {
      loadPatientAnalytics(activeAnalyticsPatientCode, currentAnalyticsDays);
    }
  });
});

async function loadPatientAnalytics(patientCode, days = 7) {
  try {
    const res = await fetch(`/api/patients/${patientCode}/analytics?days=${days}`);
    if (!res.ok) return;
    const data = await res.json();

    analyticsPatientName.textContent = `${data.patient.full_name} (${data.patient.patient_code})`;
    analyticsPatientMeta.textContent = `Bed ${data.patient.bed_number || 'N/A'} · Blood Group ${data.patient.blood_group} · Risk: ${data.patient.risk_level}`;

    // Update Vitals Line Chart
    renderVitalsChart(data.vitals_series);

    // Update Emotion Donut Chart
    renderEmotionChart(data.emotion_distribution);

    // Render Wellness Responses
    wellnessResponsesList.innerHTML = "";
    if (data.wellness_responses.length === 0) {
      wellnessResponsesList.innerHTML = `<div style="color:#64748b; font-size:0.85rem; padding:1rem;">No questionnaire responses recorded yet.</div>`;
    } else {
      data.wellness_responses.forEach((r) => {
        const item = document.createElement("div");
        item.className = "wellness-item";
        item.innerHTML = `
          <div class="wellness-q">${escapeHtml(r.question)} <span style="float:right; font-size:0.7rem; color:#94a3b8;">${escapeHtml(r.date)}</span></div>
          <div class="wellness-a">${escapeHtml(r.answer)}</div>
        `;
        wellnessResponsesList.appendChild(item);
      });
    }

    // Render Medications
    renderPatientMedications(data.medications);
  } catch (err) {
    console.error("Error loading analytics:", err);
  }
}

function renderVitalsChart(series) {
  const ctx = document.getElementById("vitalsChart").getContext("2d");
  if (vitalsChartInstance) vitalsChartInstance.destroy();

  const labels = series.map((s) => s.timestamp);
  const temps = series.map((s) => s.temperature_c);
  const pulses = series.map((s) => s.pulse_bpm);
  const spo2s = series.map((s) => s.spo2_percent);

  vitalsChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Temperature (°C)",
          data: temps,
          borderColor: "#ef4444",
          backgroundColor: "rgba(239, 68, 68, 0.1)",
          yAxisID: "yTemp",
          tension: 0.3,
          borderWidth: 2,
        },
        {
          label: "Pulse (BPM)",
          data: pulses,
          borderColor: "#0284c7",
          backgroundColor: "rgba(2, 132, 199, 0.1)",
          yAxisID: "yPulse",
          tension: 0.3,
          borderWidth: 2,
        },
        {
          label: "SpO2 (%)",
          data: spo2s,
          borderColor: "#10b981",
          backgroundColor: "rgba(16, 185, 129, 0.1)",
          yAxisID: "ySpo2",
          tension: 0.3,
          borderWidth: 2,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      scales: {
        yTemp: {
          type: "linear",
          position: "left",
          min: 35.5,
          max: 39.5,
          title: { display: true, text: "Temp (°C)" },
        },
        yPulse: {
          type: "linear",
          position: "right",
          min: 50,
          max: 130,
          grid: { drawOnChartArea: false },
          title: { display: true, text: "Pulse (BPM)" },
        },
        ySpo2: {
          display: false,
          min: 90,
          max: 100,
        },
      },
    },
  });

  // Evaluate summary indicator
  const latestTemp = temps[temps.length - 1];
  const badge = document.getElementById("trend-summary-badge");
  if (latestTemp >= 38.0) {
    badge.textContent = "⚠ Pyrexia / Elevated Temperature Trend Detected";
    badge.style.color = "var(--urgent)";
  } else {
    badge.textContent = "✓ Vitals Trending Within Baseline Limits";
    badge.style.color = "var(--success)";
  }
}

function renderEmotionChart(distribution) {
  const ctx = document.getElementById("emotionChart").getContext("2d");
  if (emotionChartInstance) emotionChartInstance.destroy();

  const labels = Object.keys(distribution);
  const counts = Object.values(distribution);

  const colors = {
    Happy: "#10b981",
    Neutral: "#64748b",
    Sad: "#3b82f6",
    Surprise: "#f59e0b",
    Fear: "#8b5cf6",
    Angry: "#ef4444",
    Disgust: "#0f766e",
  };

  emotionChartInstance = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [
        {
          data: counts,
          backgroundColor: labels.map((l) => colors[l] || "#94a3b8"),
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "right" },
      },
    },
  });
}

function renderPatientMedications(meds) {
  patientMedsBody.innerHTML = "";
  if (meds.length === 0) {
    patientMedsBody.innerHTML = `<tr><td colspan="6" style="text-align:center; color:#64748b; padding:1.5rem;">No medications actively prescribed.</td></tr>`;
    return;
  }
  meds.forEach((m) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(m.medicine_name)}</strong></td>
      <td>${escapeHtml(m.dosage)}</td>
      <td>${escapeHtml(m.frequency)}</td>
      <td><span class="font-mono">${escapeHtml(m.scheduled_time)}</span></td>
      <td><small style="color:#64748b;">${escapeHtml(m.instructions || '--')}</small></td>
      <td><span class="badge" style="color:#166534; background:#dcfce7;">Active</span></td>
    `;
    patientMedsBody.appendChild(tr);
  });
}

btnTogglePrescribe.addEventListener("click", () => {
  prescribeForm.hidden = !prescribeForm.hidden;
});

prescribeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!activeAnalyticsPatientCode) return;

  const payload = {
    medicine_name: document.getElementById("prescribe-name").value,
    dosage: document.getElementById("prescribe-dose").value,
    frequency: document.getElementById("prescribe-freq").value,
    scheduled_time: document.getElementById("prescribe-time").value,
    instructions: document.getElementById("prescribe-inst").value,
  };

  try {
    const res = await fetch(`/api/patients/${activeAnalyticsPatientCode}/medications`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      prescribeForm.reset();
      prescribeForm.hidden = true;
      loadPatientAnalytics(activeAnalyticsPatientCode, currentAnalyticsDays);
    }
  } catch (err) {
    alert("Prescription error: " + err);
  }
});

// ---- Alert Center ----
async function loadAlerts() {
  const status = alertStatusFilter.value;
  try {
    const res = await fetch(`/api/alerts?status=${encodeURIComponent(status)}&page=${alertsPage}&page_size=20`);
    if (!res.ok) return;
    const alertResult = await res.json();
    alertsData = alertResult.items;
    alertsPages = Math.max(alertResult.pages, 1);
    document.getElementById('alerts-page-label').textContent = `Page ${alertsPage} of ${alertsPages}`;
    document.getElementById('alerts-prev').disabled = alertsPage <= 1;
    document.getElementById('alerts-next').disabled = alertsPage >= alertsPages;

    alertsTableBody.innerHTML = "";
    if (alertsData.length === 0) {
      alertsTableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:2rem;">No alerts matching filter.</td></tr>`;
      return;
    }

    alertsData.forEach((a) => {
      const tr = document.createElement("tr");
      const timeStr = new Date(a.created_at).toLocaleString();
      tr.innerHTML = `
        <td><span class="risk-badge ${escapeHtml(a.severity)}">${escapeHtml(a.severity)}</span></td>
        <td><strong>${escapeHtml(a.patient_name)}</strong><br><small class="font-mono text-muted">${escapeHtml(a.patient_code)}</small></td>
        <td>Bed ${a.bed_number || '--'}</td>
        <td>
          <strong style="font-size:0.85rem;">${escapeHtml(a.alert_type)}</strong><br>
          <span style="font-size:0.8rem; color:#334155;">${escapeHtml(a.message)}</span>
          <small>Value: ${escapeHtml(a.actual_value ?? '—')} · Threshold: ${escapeHtml(a.threshold_value ?? '—')} · Source: ${escapeHtml(a.source || 'Unknown')}</small>
        </td>
        <td style="font-size:0.78rem; color:#64748b;">${timeStr}</td>
        <td><span class="status-pill ${escapeHtml(a.status)}">${escapeHtml(a.status)}</span></td>
        <td>
          ${["active", "new"].includes(a.status) ? `<button class="btn btn-secondary btn-small alert-ack-action">Acknowledge</button>` : ""}
          ${["active", "new", "acknowledged"].includes(a.status) ? `<button class="btn btn-outline btn-small alert-review-action">Review</button>` : ""}
          ${["under_review", "acknowledged"].includes(a.status) ? `<button class="btn btn-outline btn-small alert-resolve-action">Resolve</button>` : ""}
          ${["resolved", "dismissed"].includes(a.status) ? `<small style="color:#64748b;">By ${escapeHtml(a.resolved_by || a.acknowledged_by || 'Care team')}</small>` : ""}
        </td>
      `;
      alertsTableBody.appendChild(tr);
      tr.querySelector(".alert-ack-action")?.addEventListener("click", () => openAckModal(a.id, a.message));
      tr.querySelector(".alert-review-action")?.addEventListener("click", () => changeAlertStatus(a.id, "under_review"));
      tr.querySelector(".alert-resolve-action")?.addEventListener("click", () => changeAlertStatus(a.id, "resolved"));
    });
  } catch (err) {
    console.error("Error loading alerts:", err);
  }
}

async function changeAlertStatus(id, status) {
  const response = await fetch(`/api/alerts/${id}/status`, {
    method: "PATCH", headers: {"Content-Type": "application/json"}, body: JSON.stringify({status})
  });
  if (!response.ok) { alert("Alert status could not be updated. Try again."); return; }
  loadAlerts(); window.loadPriority?.();
}

alertStatusFilter.addEventListener("change", () => { alertsPage = 1; loadAlerts(); });
document.getElementById('tasks-prev').addEventListener('click', () => { if (tasksPage > 1) { tasksPage--; loadTasks(); } });
document.getElementById('tasks-next').addEventListener('click', () => { if (tasksPage < tasksPages) { tasksPage++; loadTasks(); } });
document.getElementById('alerts-prev').addEventListener('click', () => { if (alertsPage > 1) { alertsPage--; loadAlerts(); } });
document.getElementById('alerts-next').addEventListener('click', () => { if (alertsPage < alertsPages) { alertsPage++; loadAlerts(); } });

window.openAckModal = function(alertId, text) {
  ackAlertId = alertId;
  ackAlertText.textContent = text;
  ackModal.hidden = false;
};

ackModalClose.addEventListener("click", () => (ackModal.hidden = true));
ackModalDismiss.addEventListener("click", () => (ackModal.hidden = true));

ackForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!ackAlertId) return;

  const note = document.getElementById("ack-note").value;
  try {
    const res = await fetch(`/api/alerts/${ackAlertId}/acknowledge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    });
    if (res.ok) {
      ackModal.hidden = true;
      ackForm.reset();
      loadAlerts();
      loadStats();
    }
  } catch (err) {
    alert("Acknowledgement failed: " + err);
  }
});

// ---- Summaries Reports ----
async function loadSummaries() {
  const patientCode = summaryPatientFilter.value;
  try {
    const res = await fetch(`/api/summaries?patient_code=${encodeURIComponent(patientCode)}`);
    if (!res.ok) return;
    const summaries = await res.json();

    summariesContainer.innerHTML = "";
    if (summaries.length === 0) {
      summariesContainer.innerHTML = `<div class="card" style="padding:2rem; text-align:center; color:#64748b;">No visit reports recorded.</div>`;
      return;
    }

    summaries.forEach((s) => {
      const card = document.createElement("div");
      card.className = "summary-card";
      card.innerHTML = `
        <div class="summary-meta">
          <div>
            <strong style="font-size:1.1rem;">${escapeHtml(s.patient_name)}</strong>
            <span class="font-mono text-primary font-bold" style="margin-left:0.5rem;">${escapeHtml(s.patient_code)}</span>
            <span class="badge" style="margin-left:0.5rem;">Bed ${s.bed_number || '--'}</span>
          </div>
          <div style="font-size:0.8rem; color:#64748b;">
            Recorded on ${escapeHtml(s.created_at)} · Author: <strong>${escapeHtml(s.author)}</strong>
            ${s.quality_status === 'simulated' ? '<span class="badge">DEMO SIMULATION</span>' : ''}
          </div>
        </div>
        <div style="display:flex; gap:1.5rem; font-size:0.85rem; margin-bottom:1rem; padding:0.5rem 0.75rem; background:#f8fafc; border-radius:8px;">
          <span>Temp: <strong>${escapeHtml(s.temperature_c || '--')}</strong></span>
          <span>Pulse: <strong>${escapeHtml(s.pulse_bpm || '--')}</strong></span>
          <span>SpO2: <strong>${escapeHtml(s.spo2_percent || '--')}</strong></span>
          <span>ECG: <strong>${escapeHtml(s.ecg_note || '--')}</strong></span>
        </div>
        <div class="summary-dual-grid">
          <div class="summary-col clinical">
            <h4>ANNA Assistive Summary — for clinician review</h4>
            <p class="summary-text">${escapeHtml(s.clinical_summary)}</p>
          </div>
          <div class="summary-col patient">
            <h4>📱 Patient-Friendly Summary (Patient Portal View)</h4>
            <p class="summary-text">${escapeHtml(s.patient_summary)}</p>
          </div>
        </div>
        <button type="button" class="btn btn-outline btn-small summary-source-action">View source data</button>
      `;
      summariesContainer.appendChild(card);
      card.querySelector('.summary-source-action').addEventListener('click', () => openPatientWorkspace(s.patient_code));
    });
  } catch (err) {
    console.error("Error loading summaries:", err);
  }
}

// ---- Macro Clinical Analytics Overview ----
let riskChartInstance = null;
let fleetChartInstance = null;
let checkupsTrendChartInstance = null;

async function loadClinicianMacroAnalytics() {
  try {
    const res = await fetch("/api/clinician/analytics/overview");
    if (!res.ok) return;
    const data = await res.json();

    // 1. Patient Risk Distribution Donut
    const riskCtx = document.getElementById("riskDistributionChart").getContext("2d");
    if (riskChartInstance) riskChartInstance.destroy();
    riskChartInstance = new Chart(riskCtx, {
      type: "doughnut",
      data: {
        labels: ["Stable", "Observe", "Review", "Urgent", "Critical"],
        datasets: [{
          data: [
            data.risk_distribution.STABLE || 0,
            data.risk_distribution.OBSERVE || 0,
            data.risk_distribution.REVIEW || 0,
            data.risk_distribution.URGENT || 0,
            data.risk_distribution.CRITICAL || 0,
          ],
          backgroundColor: ["#18804a", "#087e91", "#ad6900", "#d36c18", "#c53636"],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" }
        },
        cutout: "68%"
      }
    });

    // 2. Robot Fleet Tasks Donut
    const fleetCtx = document.getElementById("robotFleetChart").getContext("2d");
    if (fleetChartInstance) fleetChartInstance.destroy();
    fleetChartInstance = new Chart(fleetCtx, {
      type: "doughnut",
      data: {
        labels: ["Completed Rounds", "Queued / In Progress", "Failed / Cancelled"],
        datasets: [{
          data: [
            data.robot_fleet.completed,
            data.robot_fleet.pending,
            data.robot_fleet.failed
          ],
          backgroundColor: ["#0284c7", "#f59e0b", "#ef4444"],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: "bottom" }
        },
        cutout: "68%"
      }
    });

    // 3. 7-Day Checkup Volume
    const trendCtx = document.getElementById("checkupsTrendChart").getContext("2d");
    if (checkupsTrendChartInstance) checkupsTrendChartInstance.destroy();
    checkupsTrendChartInstance = new Chart(trendCtx, {
      type: "bar",
      data: {
        labels: data.checkups_trend.labels,
        datasets: [{
          label: "Completed Bedside Checkups",
          data: data.checkups_trend.counts,
          backgroundColor: "#0f766e",
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, ticks: { stepSize: 1 } }
        },
        plugins: {
          legend: { position: "bottom" }
        }
      }
    });

  } catch (err) {
    console.error("Error loading clinician macro analytics:", err);
  }
}

summaryPatientFilter.addEventListener("change", loadSummaries);

// Start
checkAuth();
