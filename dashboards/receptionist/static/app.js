// Receptionist Dashboard Application Logic

let bedsData = [];
let capturedBlob = null;
let photoValidated = false;
let selectedBedNumber = null;
let mediaStream = null;
let activeModalBed = null;
let ws = null;

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
    setTimeout(initWebSocket, 3000);
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

    bedsData.forEach((bed) => {
      const card = document.createElement("div");
      card.className = `bed-card ${bed.is_occupied ? "occupied" : "available"} ${selectedBedNumber === bed.bed_number ? "selected" : ""}`;
      card.innerHTML = `
        <div class="bed-top">
          <span class="bed-num">Bed ${String(bed.bed_number).padStart(2, '0')}</span>
          <span class="bed-badge">${bed.is_occupied ? "Occupied" : "Available"}</span>
        </div>
        <div>
          <div class="bed-occupant">${bed.occupant_name || "Available for admission"}</div>
          <div class="bed-code">${bed.occupant_code || bed.bed_type}</div>
        </div>
      `;

      card.addEventListener("click", () => handleBedClick(bed));

      if (bed.bed_number <= 10) {
        wardAGrid.appendChild(card);
      } else {
        wardBGrid.appendChild(card);
      }

      if (!bed.is_occupied) {
        const opt = document.createElement("option");
        opt.value = bed.bed_number;
        opt.textContent = `Bed ${bed.bed_number} (${bed.ward} - ${bed.bed_type})`;
        bedSelect.appendChild(opt);
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
            <h4>${bed.occupant_name || "Admitted Patient"}</h4>
            <p>Patient ID: <strong class="font-mono text-primary">${bed.occupant_code || "--"}</strong></p>
          </div>
        </div>

        <div class="bed-quick-stats">
          <div class="bed-stat-item">
            <span>Assigned Ward</span>
            <strong>${bed.ward} (${bed.bed_type})</strong>
          </div>
          <div class="bed-stat-item">
            <span>Admission Timestamp</span>
            <strong>${dateStr}</strong>
          </div>
        </div>
      </div>
    `;
    bedModal.hidden = false;
  } else {
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
      
      // Look up patient id via patient code
      const pRes = await fetch(`/api/patients/${activeModalBed.occupant_code}`);
      if (!pRes.ok) throw new Error("Could not retrieve patient details.");
      const pData = await pRes.json();

      const taskRes = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          patient_id: pData.id,
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
    const res = await fetch("/api/patients/admit", {
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
async function loadPatients() {
  const query = patientSearch ? patientSearch.value : "";
  const wardFilter = patientWardFilter ? patientWardFilter.value : "all";
  const statusFilter = patientStatusFilter ? patientStatusFilter.value : "all";

  try {
    const res = await fetch(`/api/patients?query=${encodeURIComponent(query)}`);
    if (!res.ok) return;
    let patients = await res.json();

    if (wardFilter !== "all") {
      patients = patients.filter((p) => {
        if (!p.bed_number) return false;
        return wardFilter === "Ward A" ? p.bed_number <= 10 : p.bed_number > 10;
      });
    }

    if (statusFilter !== "all") {
      patients = patients.filter((p) => p.status === statusFilter);
    }

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
        <td data-label="Patient Code" class="font-mono text-primary" style="font-weight:700;">${p.patient_code}</td>
        <td data-label="Full Name" style="font-weight:700;">${p.full_name}</td>
        <td data-label="Gender / Blood">${p.gender} / <strong>${p.blood_group}</strong></td>
        <td data-label="Bed">${bedDisplay}</td>
        <td data-label="Admission">${admStr}</td>
        <td data-label="Status"><span class="status-pill ${p.status}">${p.status}</span></td>
        <td data-label="Action">
          ${p.status === "admitted" ? `<button class="btn btn-secondary" style="padding:0.35rem 0.75rem; font-size:0.8rem;" onclick="dischargeDirect(${p.bed_number}, '${p.full_name}')">Discharge</button>` : `<span style="color:#94a3b8; font-size:0.82rem;">Released</span>`}
        </td>
      `;
      patientTableBody.appendChild(tr);
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
    searchTimeout = setTimeout(loadPatients, 300);
  });
}
if (patientWardFilter) patientWardFilter.addEventListener("change", loadPatients);
if (patientStatusFilter) patientStatusFilter.addEventListener("change", loadPatients);

// Initial Setup
initWebSocket();
loadStats();
loadBeds();
