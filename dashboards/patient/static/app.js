// Patient Portal Application Logic

let patientTrendsChart = null;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));

// DOM Elements
const loginView = document.getElementById("login-view");
const appView = document.getElementById("app-view");
const loginForm = document.getElementById("portal-login-form");
const loginError = document.getElementById("login-error");
const btnLogout = document.getElementById("btn-logout");

const navPatientName = document.getElementById("nav-patient-name");
const patientWelcomeHeading = document.getElementById("patient-welcome-heading");
const tagPatientCode = document.getElementById("tag-patient-code");
const tagPatientBed = document.getElementById("tag-patient-bed");
const tagPatientBlood = document.getElementById("tag-patient-blood");
const tagPatientAdmission = document.getElementById("tag-patient-admission");

const kpiTotalCheckups = document.getElementById("kpi-total-checkups");
const kpiLatestCheckupDate = document.getElementById("kpi-latest-checkup-date");
const kpiMedCount = document.getElementById("kpi-med-count");

const latestVitalsTime = document.getElementById("latest-vitals-time");
const vitalTemp = document.getElementById("vital-temp");
const vitalTempStatus = document.getElementById("vital-temp-status");
const vitalPulse = document.getElementById("vital-pulse");
const vitalPulseStatus = document.getElementById("vital-pulse-status");
const vitalSpo2 = document.getElementById("vital-spo2");
const vitalSpo2Status = document.getElementById("vital-spo2-status");
const vitalEcg = document.getElementById("vital-ecg");
const vitalEcgStatus = document.getElementById("vital-ecg-status");

const historyStreamContainer = document.getElementById("history-stream-container");
const patientMedicationsTable = document.getElementById("patient-medications-table");

// ---- Authentication Check ----
async function checkAuth() {
  try {
    const res = await fetch("/api/portal/profile");
    if (res.ok) {
      const profile = await res.json();
      loginView.hidden = true;
      appView.hidden = false;
      renderProfile(profile);
      loadPortalData();
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
  const patient_code = document.getElementById("patient_code").value.trim();
  const portal_pin = document.getElementById("portal_pin").value.trim();

  try {
    const res = await fetch("/api/portal/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ patient_code, portal_pin }),
    });

    if (!res.ok) {
      const err = await res.json();
      loginError.textContent = err.detail || "Patient ID or PIN is incorrect.";
      loginError.hidden = false;
      return;
    }

    loginView.hidden = true;
    appView.hidden = false;
    checkAuth();
  } catch (err) {
    loginError.textContent = "Network error during login: " + err;
    loginError.hidden = false;
  }
});

btnLogout.addEventListener("click", async () => {
  await fetch("/api/portal/auth/logout", { method: "POST" });
  loginView.hidden = false;
  appView.hidden = true;
  loginForm.reset();
});

function renderProfile(profile) {
  navPatientName.textContent = profile.full_name;
  patientWelcomeHeading.textContent = window.portalTranslate?.("welcome", profile.full_name) || `Welcome, ${profile.full_name}`;
  window.portalPatientName = profile.full_name;
  tagPatientCode.textContent = `ID: ${profile.patient_code}`;
  tagPatientBed.textContent = profile.bed_number ? `Bed ${profile.bed_number}` : "Discharged";
  tagPatientBlood.textContent = `Blood: ${profile.blood_group}`;
  tagPatientAdmission.textContent = `Admitted: ${profile.admission_date}`;
}

// ---- Load Portal Data ----
async function loadPortalData() {
  loadLatestVitals();
  loadHistory();
  loadMedications();
  loadTrends();
}

async function loadLatestVitals() {
  try {
    const res = await fetch("/api/portal/vitals");
    if (!res.ok) return;
    const v = await res.json();

    if (!v.has_readings) {
      latestVitalsTime.textContent = "No readings taken yet";
      return;
    }

    latestVitalsTime.textContent = `Measured ${v.recorded_at} · ${v.source || "ANNA"} · ${v.freshness_status}`;
    vitalTemp.textContent = v.temperature;
    vitalTempStatus.textContent = v.temperature_status;

    vitalPulse.textContent = v.pulse;
    vitalPulseStatus.textContent = v.pulse_status;

    vitalSpo2.textContent = v.spo2;
    vitalSpo2Status.textContent = v.spo2_status;

    vitalEcg.textContent = v.ecg;
    vitalEcgStatus.textContent = v.ecg === "Not available" ? "No ECG measurement available" : "Recorded during ANNA visit";
  } catch (err) {
    console.error("Error loading vitals:", err);
  }
}

async function loadHistory() {
  try {
    const res = await fetch("/api/portal/history");
    if (!res.ok) return;
    const history = await res.json();

    kpiTotalCheckups.textContent = history.length;
    if (history.length > 0) {
      kpiLatestCheckupDate.textContent = history[0].created_at.split(" at ")[0];
    } else {
      kpiLatestCheckupDate.textContent = "None yet";
    }

    historyStreamContainer.innerHTML = "";
    if (history.length === 0) {
      historyStreamContainer.innerHTML = `<div class="card" style="padding:2rem; text-align:center; color:#64748b;">No completed ANNA checkups on record yet.</div>`;
      return;
    }

    history.forEach((item) => {
      const card = document.createElement("div");
      card.className = "history-card";
      card.innerHTML = `
        <div class="history-header">
          <div class="history-date">${escapeHtml(item.created_at)}</div>
          <div class="history-vitals">
            <span>Temp: <strong>${escapeHtml(item.temperature)}</strong></span>
            <span>Pulse: <strong>${escapeHtml(item.pulse)}</strong></span>
            <span>SpO2: <strong>${escapeHtml(item.spo2)}</strong></span>
          </div>
        </div>
        <p class="history-summary-text">${escapeHtml(item.patient_summary)}</p>
      `;
      historyStreamContainer.appendChild(card);
    });
  } catch (err) {
    console.error("Error loading history:", err);
  }
}

async function loadMedications() {
  try {
    const res = await fetch("/api/portal/medications");
    if (!res.ok) return;
    const meds = await res.json();

    kpiMedCount.textContent = meds.length;

    patientMedicationsTable.innerHTML = "";
    if (meds.length === 0) {
      patientMedicationsTable.innerHTML = `<tr><td colspan="5" style="text-align:center; color:#64748b; padding:1.5rem;">No active prescribed medications.</td></tr>`;
      return;
    }

    meds.forEach((m) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td data-label="Medication"><strong style="font-size:0.95rem; color:var(--text-main);">${escapeHtml(m.medicine_name)}</strong></td>
        <td data-label="Dosage">${escapeHtml(m.dosage)}</td>
        <td data-label="Frequency">${escapeHtml(m.frequency)}</td>
        <td data-label="Scheduled Time"><span style="font-family:'JetBrains Mono',monospace; font-weight:700; color:var(--primary);">${escapeHtml(m.scheduled_time)}</span></td>
        <td data-label="Special Instructions"><small style="color:#64748b;">${escapeHtml(m.instructions || 'Take as instructed by nursing staff.')}</small></td>
      `;
      patientMedicationsTable.appendChild(tr);
    });
  } catch (err) {
    console.error("Error loading medications:", err);
  }
}

async function loadTrends() {
  const summary = document.getElementById("portal-trend-summary");
  try {
    const res = await fetch("/api/portal/trends");
    if (!res.ok) throw new Error("Trend request failed");
    const trends = await res.json();

    if (trends.length === 0) {
      summary.textContent = "No recent reliable measurements are available yet.";
      return;
    }
    const measuredTemps = trends.map(t => t.temperature_c).filter(Number.isFinite);
    const measuredPulses = trends.map(t => t.pulse_bpm).filter(Number.isFinite);
    const changes = [];
    if (measuredTemps.length > 1) {
      const delta = measuredTemps.at(-1) - measuredTemps.at(-2);
      changes.push(`Temperature ${delta > 0 ? "rose" : delta < 0 ? "fell" : "stayed the same"} by ${Math.abs(delta).toFixed(1)} °C since the previous measured visit`);
    }
    if (measuredPulses.length > 1) {
      const delta = measuredPulses.at(-1) - measuredPulses.at(-2);
      changes.push(`Pulse ${delta > 0 ? "rose" : delta < 0 ? "fell" : "stayed the same"} by ${Math.abs(delta).toFixed(0)} BPM`);
    }
    summary.textContent = changes.length ? `${changes.join(". ")}. Your care team will review these readings.` :
      "There is not enough reliable history for a comparison yet. Your care team reviews the readings.";

    if (!window.Chart) {
      summary.textContent += " The chart is temporarily unavailable.";
      return;
    }

    const ctx = document.getElementById("patientTrendsChart").getContext("2d");
    if (patientTrendsChart) patientTrendsChart.destroy();

    const labels = trends.map((t) => t.date);
    const temps = trends.map((t) => t.temperature_c);
    const pulses = trends.map((t) => t.pulse_bpm);

    patientTrendsChart = new Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Temperature (°C)",
            data: temps,
            borderColor: "#7c3aed",
            backgroundColor: "rgba(124, 58, 237, 0.1)",
            tension: 0.3,
            spanGaps: false,
            yAxisID: "yTemp",
          },
          {
            label: "Pulse (BPM)",
            data: pulses,
            borderColor: "#0f766e",
            backgroundColor: "rgba(15, 118, 110, 0.1)",
            tension: 0.3,
            spanGaps: false,
            yAxisID: "yPulse",
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
            title: { display: true, text: "Temperature (°C)" },
          },
          yPulse: {
            type: "linear",
            position: "right",
            grid: { drawOnChartArea: false },
            title: { display: true, text: "Pulse (BPM)" },
          },
        },
      },
    });
  } catch (err) {
    console.error("Error loading trends:", err);
    summary.textContent = "Recent measurements could not be loaded. Please try again later.";
  }
}

// Start
checkAuth();
