// Receptionist Dashboard Application Logic

let bedsData = [];
let capturedBlob = null;
let photoValidated = false;
let selectedBedNumber = null;
let mediaStream = null;
let activeModalBed = null;
let ws = null;
let receptionAuthenticated = false;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
let activeAssignmentCode = null;

function showReceptionApp(allowed) {
  receptionAuthenticated = allowed;
  document.getElementById("reception-auth").hidden = allowed;
  document.querySelector(".topbar").hidden = !allowed;
  document.querySelector(".main-container").hidden = !allowed;
  if (allowed) {
    initWebSocket();
    loadStats();
    loadBeds();
    loadDoctors();
  } else if (ws) {
    ws.close();
  }
}

async function checkReceptionAuth() {
  try {
    const response = await fetch("/api/auth/me");
    const user = await response.json();
    showReceptionApp(Boolean(user.authenticated && ["receptionist", "admin"].includes(user.role)));
  } catch (_) {
    showReceptionApp(false);
  }
}

document.getElementById("reception-login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const error = document.getElementById("reception-login-error");
  error.hidden = true;
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username_or_email: document.getElementById("reception-user").value.trim(),
        password: document.getElementById("reception-password").value
      })
    });
    if (!response.ok) throw new Error("Invalid credentials.");
    const user = await response.json();
    if (!["receptionist", "admin"].includes(user.role)) {
      await fetch("/api/auth/logout", { method: "POST" });
      throw new Error("This account cannot access reception.");
    }
    showReceptionApp(true);
  } catch (failure) {
    error.textContent = failure.message;
    error.hidden = false;
  }
});

document.getElementById("reception-logout").addEventListener("click", async () => {
  await fetch("/api/auth/logout", { method: "POST" });
  showReceptionApp(false);
});

let occupancyChartInstance = null;
let wardDistChartInstance = null;
let admDisChartInstance = null;

// DOM Elements
const wardAGrid = document.getElementById("ward-a-grid");
const wardBGrid = document.getElementById("ward-b-grid");
const bedSelect = document.getElementById("bed_number");
const intakeForm = document.getElementById("intake-form");
const btnRegister = document.getElementById("btn-register");

const webcam = document.getElementById("webcam");
const photoPreview = document.getElementById("photo-preview");
const photoCanvas = document.getElementById("photo-canvas");
const btnStartCamera = document.getElementById("btn-start-camera");
const btnCapture = document.getElementById("btn-capture");
const btnRetake = document.getElementById("btn-retake");
const fileInput = document.getElementById("file-input");
const faceStatus = document.getElementById("face-status");
const faceStatusText = document.getElementById("face-status-text");

const bedModal = document.getElementById("bed-modal");
const modalClose = document.getElementById("modal-close");
const modalDismiss = document.getElementById("modal-dismiss");
const modalDischargeAction = document.getElementById("modal-discharge-action");
const modalAssignAnnaAction = document.getElementById("modal-assign-anna-action");
const modalBody = document.getElementById("modal-body-content");
const modalTitle = document.getElementById("modal-bed-title");

const successModal = document.getElementById("success-modal");
const successClose = document.getElementById("success-close");
const successDone = document.getElementById("success-done");
const successPatientName = document.getElementById("success-patient-name");
const successBedNumber = document.getElementById("success-bed-number");
const successPatientCode = document.getElementById("success-patient-code");
const successPortalPin = document.getElementById("success-portal-pin");

const patientSearch = document.getElementById("patient-search");
const patientWardFilter = document.getElementById("patient-ward-filter");
const patientStatusFilter = document.getElementById("patient-status-filter");
const patientTableBody = document.getElementById("patient-table-body");

async function loadDoctors() {
  const response = await fetch("/api/receptionist/doctors");
  if (!response.ok) return;
  const doctors = await response.json();
  for (const id of ["assigned_doctor_id", "assignment-doctor"]) {
    const select = document.getElementById(id);
    select.querySelectorAll("option:not(:first-child)").forEach((item) => item.remove());
    doctors.forEach((doctor) => {
      const option = document.createElement("option");
      option.value = doctor.id;
      option.textContent = doctor.name;
      select.appendChild(option);
    });
  }
}

window.openAssignment = function(patientCode) {
  activeAssignmentCode = patientCode;
  document.getElementById("assignment-patient").textContent = patientCode;
  document.getElementById("assignment-doctor").value = "";
  document.getElementById("assignment-bed").value = "";
  document.getElementById("assignment-error").hidden = true;
  document.getElementById("assignment-dialog").showModal();
};

document.getElementById("assignment-cancel").addEventListener("click", () => document.getElementById("assignment-dialog").close());
document.getElementById("assignment-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!activeAssignmentCode) return;
  const doctor = document.getElementById("assignment-doctor").value;
  const bed = document.getElementById("assignment-bed").value;
  const error = document.getElementById("assignment-error");
  try {
    const response = await fetch(`/api/receptionist/patients/${encodeURIComponent(activeAssignmentCode)}/assignment`, {
      method: "PATCH", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({doctor_id: doctor ? Number(doctor) : null, bed_number: bed ? Number(bed) : null})
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Assignment could not be saved.");
    document.getElementById("assignment-dialog").close();
    loadBeds(); loadPatients();
  } catch (failure) { error.textContent = failure.message; error.hidden = false; }
});

// ---- Live Clock ----
function updateClock() {
  const now = new Date();
  document.getElementById("live-clock").textContent = now.toLocaleTimeString();
}
setInterval(updateClock, 1000);
updateClock();

// ---- Tab Switching ----
document.querySelectorAll(".tab-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
    btn.classList.add("active");
    const tabId = btn.getAttribute("data-tab");
    document.getElementById(tabId).classList.add("active");
    if (tabId === "patients-tab") {
      loadPatients();
    } else if (tabId === "analytics-tab") {
      loadReceptionAnalytics();
    }
  });
});

function switchTab(tabId) {
  const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
  if (btn) btn.click();
}

// ---- WebSocket Real-Time Sync ----
function initWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/hospital`;
  
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    document.getElementById("ws-status-text").textContent = "Live Sync Active";
    document.getElementById("ws-status").style.background = "#f0fdf4";
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (
        msg.event === "patient_admitted" ||
        msg.event === "patient_discharged" ||
        msg.event === "checkup_completed"
      ) {
        loadStats();
        loadBeds();
        if (document.getElementById("patients-tab").classList.contains("active")) {
          loadPatients();
        }
        if (document.getElementById("analytics-tab").classList.contains("active")) {
          loadReceptionAnalytics();
        }
      }
    } catch (e) {
      console.error("WS Parse error:", e);
    }
  };

  ws.onclose = () => {
    document.getElementById("ws-status-text").textContent = "Reconnecting...";
    document.getElementById("ws-status").style.background = "#fffbeb";
    if (receptionAuthenticated) setTimeout(initWebSocket, 3000);
  };
}

// ---- Load KPI Stats ----
async function loadStats() {
  try {
    const res = await fetch("/api/receptionist/stats");
    if (!res.ok) return;
    const stats = await res.json();
    document.getElementById("kpi-total-beds").textContent = stats.total_beds;
    document.getElementById("kpi-occupied-beds").textContent = stats.occupied_beds;
    document.getElementById("kpi-available-beds").textContent = stats.available_beds;
    document.getElementById("kpi-admissions-today").textContent = stats.admissions_today;
    document.getElementById("kpi-discharges-today").textContent = stats.discharges_today;
    document.getElementById("kpi-active-patients").textContent = stats.active_patients;

    const rate = Math.round((stats.occupied_beds / stats.total_beds) * 100) || 0;
    document.getElementById("kpi-occupancy-rate").textContent = `${rate}% Occupancy rate`;
  } catch (err) {
    console.error("Error loading stats:", err);
  }
}

// ---- Load Beds Map ----
async function loadBeds() {
  try {
    const res = await fetch("/api/beds");
    if (!res.ok) return;
    bedsData = await res.json();

    wardAGrid.innerHTML = "";
    wardBGrid.innerHTML = "";
    bedSelect.innerHTML = '<option value="" disabled selected>Choose an available bed</option>';
    const assignmentBed = document.getElementById("assignment-bed");
    assignmentBed.querySelectorAll("option:not(:first-child)").forEach((item) => item.remove());

    bedsData.forEach((bed) => {
      const card = document.createElement("div");
      card.className = `bed-card ${bed.is_occupied ? "occupied" : "available"} ${selectedBedNumber === bed.bed_number ? "selected" : ""}`;
      card.innerHTML = `
        <div class="bed-top">
          <span class="bed-num">Bed ${String(bed.bed_number).padStart(2, '0')}</span>
          <span class="bed-badge">${escapeHtml(bed.status)}</span>
        </div>
        <div>
          <div class="bed-occupant">${escapeHtml(bed.occupant_name || "Available for admission")}</div>
          <div class="bed-code">${escapeHtml(bed.occupant_code || bed.bed_type)}</div>
        </div>
      `;

      card.addEventListener("click", () => handleBedClick(bed));

      if (bed.bed_number <= 10) {
        wardAGrid.appendChild(card);
      } else {
        wardBGrid.appendChild(card);
      }

      if (!bed.is_occupied && bed.status === "available") {
        const opt = document.createElement("option");
        opt.value = bed.bed_number;
        opt.textContent = `Bed ${bed.bed_number} (${bed.ward} - ${bed.bed_type})`;
        bedSelect.appendChild(opt);
        const assignmentOption = opt.cloneNode(true);
        assignmentBed.appendChild(assignmentOption);
      }
    });

    if (selectedBedNumber) {
      bedSelect.value = selectedBedNumber;
    }
  } catch (err) {
    console.error("Error loading beds:", err);
  }
}

function handleBedClick(bed) {
  if (bed.is_occupied) {
    activeModalBed = bed;
    modalTitle.textContent = `Bed ${bed.bed_number} · ${bed.ward}`;
    const dateStr = bed.admitted_at ? new Date(bed.admitted_at).toLocaleString() : "Recently Admitted";

    modalBody.innerHTML = `
      <div class="bed-patient-profile">
        <div class="bed-profile-banner">
          <div class="bed-profile-avatar">👤</div>
          <div class="bed-profile-info">
            <h4>${escapeHtml(bed.occupant_name || "Admitted Patient")}</h4>
            <p>Patient ID: <strong class="font-mono text-primary">${escapeHtml(bed.occupant_code || "--")}</strong></p>
          </div>
        </div>

        <div class="bed-quick-stats">
          <div class="bed-stat-item">
            <span>Assigned Ward</span>
            <strong>${escapeHtml(bed.ward)} (${escapeHtml(bed.bed_type)})</strong>
          </div>
          <div class="bed-stat-item">
            <span>Admission Timestamp</span>
            <strong>${dateStr}</strong>
          </div>
        </div>
      </div>
    `;
    bedModal.hidden = false;
  } else if (bed.status === "available") {
    selectedBedNumber = bed.bed_number;
    bedSelect.value = bed.bed_number;
    switchTab("intake-tab");
    document.getElementById("full_name").focus();
  }
}

// Assign ANNA visit directly from receptionist bed profile
if (modalAssignAnnaAction) {
  modalAssignAnnaAction.addEventListener("click", async () => {
    if (!activeModalBed || !activeModalBed.occupant_code) return;
    try {
      modalAssignAnnaAction.disabled = true;
      modalAssignAnnaAction.textContent = "Dispatching...";
      
      const taskRes = await fetch("/api/receptionist/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_code: activeModalBed.occupant_code,
          task_type: "ANNA Health Check",
          instructions: "Scheduled routine vitals checkup via Receptionist Ward Map.",
          priority: "normal"
        })
      });

      if (!taskRes.ok) throw new Error("Failed to assign robot task.");
      alert(`✓ ANNA Visit successfully assigned for ${activeModalBed.occupant_name} in Bed ${activeModalBed.bed_number}!`);
      bedModal.hidden = true;
    } catch (e) {
      alert("Error assigning ANNA visit: " + e.message);
    } finally {
      modalAssignAnnaAction.disabled = false;
      modalAssignAnnaAction.innerHTML = `
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>
        <span>Assign ANNA Visit</span>
      `;
    }
  });
}

// ---- Discharge Action ----
modalDischargeAction.addEventListener("click", async () => {
  if (!activeModalBed) return;
  if (!confirm(`Confirm discharge of patient ${activeModalBed.occupant_name} from Bed ${activeModalBed.bed_number}?`)) return;

  modalDischargeAction.disabled = true;
  modalDischargeAction.textContent = "Discharging...";

  try {
    const res = await fetch(`/api/beds/${activeModalBed.bed_number}/discharge`, {
      method: "POST",
    });
    if (!res.ok) {
      const err = await res.json();
      alert("Discharge failed: " + (err.detail || "Server error"));
      return;
    }
    bedModal.hidden = true;
    loadStats();
    loadBeds();
    loadPatients();
  } catch (e) {
    alert("Discharge failed: " + e);
  } finally {
    modalDischargeAction.disabled = false;
    modalDischargeAction.textContent = "Discharge Patient & Free Bed";
  }
});

modalClose.addEventListener("click", () => (bedModal.hidden = true));
modalDismiss.addEventListener("click", () => (bedModal.hidden = true));

// ---- Camera & Photo Validation ----
btnStartCamera.addEventListener("click", async () => {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    webcam.srcObject = mediaStream;
    webcam.hidden = false;
    photoPreview.hidden = true;
    btnCapture.disabled = false;
    btnStartCamera.hidden = true;
  } catch (err) {
    alert("Camera access denied or unavailable. Please use the Upload File button.");
  }
});

btnCapture.addEventListener("click", () => {
  photoCanvas.width = webcam.videoWidth || 640;
  photoCanvas.height = webcam.videoHeight || 480;
  photoCanvas.getContext("2d").drawImage(webcam, 0, 0, photoCanvas.width, photoCanvas.height);

  photoCanvas.toBlob((blob) => {
    capturedBlob = blob;
    photoPreview.src = URL.createObjectURL(blob);
    photoPreview.hidden = false;
    webcam.hidden = true;
    btnCapture.hidden = true;
    btnRetake.hidden = false;
    verifyPhoto(blob);
  }, "image/jpeg", 0.95);
});

btnRetake.addEventListener("click", () => {
  capturedBlob = null;
  photoValidated = false;
  photoPreview.hidden = true;
  webcam.hidden = false;
  btnCapture.hidden = false;
  btnRetake.hidden = true;
  faceStatus.hidden = true;
  updateRegisterButtonState();
});

fileInput.addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (!file) return;
  capturedBlob = file;
  photoPreview.src = URL.createObjectURL(file);
  photoPreview.hidden = false;
  webcam.hidden = true;
  btnCapture.hidden = true;
  btnRetake.hidden = false;
  verifyPhoto(file);
});

async function verifyPhoto(blob) {
  faceStatus.hidden = false;
  faceStatus.className = "status-alert checking";
  faceStatusText.textContent = "Scanning reference image for biometric face enrollment...";

  const formData = new FormData();
  formData.append("photo", blob, "photo.jpg");

  try {
    const res = await fetch("/api/photo-check", {
      method: "POST",
      body: formData,
    });
    const result = await res.json();

    if (result.valid) {
      photoValidated = true;
      faceStatus.className = "status-alert success";
      faceStatusText.textContent = `✓ Biometric enrollment ready: ${result.message}`;
    } else {
      photoValidated = false;
      faceStatus.className = "status-alert error";
      faceStatusText.textContent = `⚠️ Face check failed: ${result.message}. Retake or re-upload.`;
    }
  } catch (err) {
    photoValidated = false;
    faceStatus.className = "status-alert error";
    faceStatusText.textContent = "Could not contact facial verification service.";
  }

  updateRegisterButtonState();
}

function updateRegisterButtonState() {
  btnRegister.disabled = !photoValidated;
}

// ---- Handle Admission Submission ----
intakeForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!photoValidated || !capturedBlob) {
    alert("Please validate a patient reference photo with 1 face detected before admitting.");
    return;
  }

  btnRegister.disabled = true;
  btnRegister.textContent = "Registering & Enrolling Patient...";

  const formData = new FormData(intakeForm);
  formData.set("photo", capturedBlob, "enrollment.jpg");

  try {
    const res = await fetch("/api/patients", {
      method: "POST",
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      alert("Registration failed: " + (err.detail || "Server error"));
      return;
    }

    const patient = await res.json();

    // Show Success Modal
    successPatientName.textContent = patient.full_name;
    successBedNumber.textContent = `Bed ${patient.bed_number}`;
    successPatientCode.textContent = patient.patient_code;
    successPortalPin.textContent = patient.portal_pin;
    successModal.hidden = false;

    // Reset Form
    intakeForm.reset();
    btnRetake.click();
    loadStats();
    loadBeds();
  } catch (err) {
    alert("Network or server error during admission: " + err);
  } finally {
    btnRegister.disabled = false;
    btnRegister.textContent = "Complete Patient Admission";
    updateRegisterButtonState();
  }
});

successClose.addEventListener("click", () => (successModal.hidden = true));
successDone.addEventListener("click", () => {
  successModal.hidden = true;
  switchTab("ward-tab");
});

// ---- Ward Analytics Tab (Chart.js) ----
async function loadReceptionAnalytics() {
  try {
    const [statsRes, analyticsRes] = await Promise.all([
      fetch("/api/receptionist/stats"),
      fetch("/api/receptionist/analytics")
    ]);

    if (!statsRes.ok || !analyticsRes.ok) return;
    const stats = await statsRes.json();
    const analytics = await analyticsRes.json();

    // 1. Occupancy Donut Chart
    const occCtx = document.getElementById("receptionOccupancyChart").getContext("2d");
    if (occupancyChartInstance) occupancyChartInstance.destroy();
    occupancyChartInstance = new Chart(occCtx, {
      type: "doughnut",
      data: {
        labels: ["Occupied Beds", "Available Beds"],
        datasets: [{
          data: [stats.occupied_beds, stats.available_beds],
          backgroundColor: ["#ef4444", "#10b981"],
          hoverOffset: 4,
          borderWidth: 0
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

    // 2. Ward Distribution Bar Chart
    const wardCtx = document.getElementById("wardDistributionChart").getContext("2d");
    if (wardDistChartInstance) wardDistChartInstance.destroy();
    const wa = analytics.ward_occupancy.ward_a;
    const wb = analytics.ward_occupancy.ward_b;
    wardDistChartInstance = new Chart(wardCtx, {
      type: "bar",
      data: {
        labels: ["Ward A (General/ICU)", "Ward B (Step-Down)"],
        datasets: [
          {
            label: "Occupied",
            data: [wa.occupied, wb.occupied],
            backgroundColor: "#ef4444"
          },
          {
            label: "Available",
            data: [wa.available, wb.available],
            backgroundColor: "#10b981"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true },
          y: { stacked: true, beginAtZero: true, max: 10, ticks: { stepSize: 2 } }
        },
        plugins: {
          legend: { position: "bottom" }
        }
      }
    });

    // 3. 7-Day Admission vs Discharge Volume Line Chart
    const admCtx = document.getElementById("admissionDischargeChart").getContext("2d");
    if (admDisChartInstance) admDisChartInstance.destroy();
    admDisChartInstance = new Chart(admCtx, {
      type: "line",
      data: {
        labels: analytics.admissions_vs_discharges.labels,
        datasets: [
          {
            label: "Admissions",
            data: analytics.admissions_vs_discharges.admissions,
            borderColor: "#0284c7",
            backgroundColor: "rgba(2, 132, 199, 0.1)",
            fill: true,
            tension: 0.35,
            borderWidth: 2.5
          },
          {
            label: "Discharges",
            data: analytics.admissions_vs_discharges.discharges,
            borderColor: "#64748b",
            backgroundColor: "rgba(100, 116, 139, 0.05)",
            borderDash: [5, 5],
            tension: 0.35,
            borderWidth: 2
          }
        ]
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
    console.error("Error rendering reception analytics:", err);
  }
}

// ---- Patient Directory Tab ----
let receptionPatientsPage = 1;
let receptionPatientsPages = 1;
async function loadPatients() {
  const query = patientSearch ? patientSearch.value : "";
  const wardFilter = patientWardFilter ? patientWardFilter.value : "all";
  const statusFilter = patientStatusFilter ? patientStatusFilter.value : "all";

  try {
    const res = await fetch(`/api/receptionist/patients?query=${encodeURIComponent(query)}&ward=${encodeURIComponent(wardFilter)}&status=${encodeURIComponent(statusFilter)}&page=${receptionPatientsPage}&page_size=20`);
    if (!res.ok) return;
    const result = await res.json();
    receptionPatientsPages = Math.max(1, result.pages);
    if (receptionPatientsPage > receptionPatientsPages) {
      receptionPatientsPage = receptionPatientsPages;
      return loadPatients();
    }
    const patients = result.items;
    document.getElementById('reception-patients-page').textContent = `Page ${receptionPatientsPage} of ${receptionPatientsPages}`;
    document.getElementById('reception-patients-prev').disabled = receptionPatientsPage <= 1;
    document.getElementById('reception-patients-next').disabled = receptionPatientsPage >= receptionPatientsPages;

    patientTableBody.innerHTML = "";
    if (patients.length === 0) {
      patientTableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:#64748b; padding:2rem;">No matching patient records found.</td></tr>`;
      return;
    }

    patients.forEach((p) => {
      const tr = document.createElement("tr");
      const admStr = p.admission_date ? new Date(p.admission_date).toLocaleDateString() : "--";
      const bedDisplay = p.bed_number ? `Bed ${String(p.bed_number).padStart(2, '0')}` : "--";
      tr.innerHTML = `
        <td data-label="Patient Code" class="font-mono text-primary" style="font-weight:700;">${escapeHtml(p.patient_code)}</td>
        <td data-label="Full Name" style="font-weight:700;">${escapeHtml(p.full_name)}</td>
        <td data-label="Gender / Blood">${escapeHtml(p.gender)} / <strong>${escapeHtml(p.blood_group)}</strong></td>
        <td data-label="Bed">${bedDisplay}</td>
        <td data-label="Admission">${admStr}</td>
        <td data-label="Status"><span class="status-pill ${escapeHtml(p.status)}">${escapeHtml(p.status)}</span></td>
        <td data-label="Action">
          ${p.status === "admitted" ? `<button class="btn btn-secondary assignment-open" type="button">Assign</button> <button class="btn btn-secondary discharge-direct" type="button">Discharge</button>` : `<span style="color:#94a3b8; font-size:0.82rem;">Released</span>`}
        </td>
      `;
      patientTableBody.appendChild(tr);
      tr.querySelector(".assignment-open")?.addEventListener("click", () => openAssignment(p.patient_code));
      tr.querySelector(".discharge-direct")?.addEventListener("click", () => dischargeDirect(p.bed_number, p.full_name));
    });
  } catch (err) {
    console.error("Error loading patients:", err);
  }
}

window.dischargeDirect = async function(bedNumber, name) {
  if (!confirm(`Discharge ${name} from Bed ${bedNumber}?`)) return;
  try {
    const res = await fetch(`/api/beds/${bedNumber}/discharge`, { method: "POST" });
    if (res.ok) {
      loadStats();
      loadBeds();
      loadPatients();
    }
  } catch (e) {
    alert("Discharge failed: " + e);
  }
};

let searchTimeout = null;
if (patientSearch) {
  patientSearch.addEventListener("input", () => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => { receptionPatientsPage = 1; loadPatients(); }, 300);
  });
}
if (patientWardFilter) patientWardFilter.addEventListener("change", () => { receptionPatientsPage = 1; loadPatients(); });
if (patientStatusFilter) patientStatusFilter.addEventListener("change", () => { receptionPatientsPage = 1; loadPatients(); });
document.getElementById('reception-patients-prev').addEventListener('click', () => { if (receptionPatientsPage > 1) { receptionPatientsPage--; loadPatients(); } });
document.getElementById('reception-patients-next').addEventListener('click', () => { if (receptionPatientsPage < receptionPatientsPages) { receptionPatientsPage++; loadPatients(); } });

// Initial Setup
checkReceptionAuth();
