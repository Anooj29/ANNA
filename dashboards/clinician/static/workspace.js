/* Clinical workspace: all patient content is rendered with textContent. */
let workspacePatientCode = null;
let workspaceChart = null;

async function workspaceGet(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error("Patient information could not be loaded. Try again.");
  return response.json();
}

function workspaceText(id, value) {
  document.getElementById(id).textContent = value ?? "—";
}

function workspaceItem(container, title, detail, extra) {
  const item = document.createElement("div");
  item.className = "workspace-item";
  const strong = document.createElement("strong");
  strong.textContent = title;
  const meta = document.createElement("span");
  meta.textContent = detail;
  item.append(strong, meta);
  if (extra) {
    const small = document.createElement("small");
    small.textContent = extra;
    item.append(small);
  }
  container.appendChild(item);
  return item;
}

window.loadPriority = async function() {
  const target = document.getElementById("priority-list");
  if (!target) return;
  try {
    const patients = await workspaceGet("/api/clinician/priority");
    target.replaceChildren();
    if (!patients.length) {
      target.textContent = "No active patients to review.";
      return;
    }
    patients.slice(0, 8).forEach((patient) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `priority-row priority-${patient.attention.level.toLowerCase()}`;
      const name = document.createElement("strong");
      name.textContent = patient.full_name;
      const description = document.createElement("span");
      description.textContent = `Bed ${patient.bed_number ?? "—"} · ${patient.attention.level} · ${patient.attention.reasons[0] || "No active alert"}`;
      button.append(name, description);
      button.addEventListener("click", () => window.openPatientWorkspace(patient.patient_code));
      target.appendChild(button);
    });
  } catch (_) {
    target.textContent = "Patient priorities could not be loaded. Try refreshing.";
  }
};

window.openPatientWorkspace = async function(patientCode) {
  workspacePatientCode = patientCode;
  document.querySelector('[data-tab="patient-workspace-tab"]').click();
  workspaceText("workspace-name", "Loading patient workspace…");
  document.getElementById("workspace-empty").hidden = true;
  document.getElementById("workspace-content").hidden = false;
  try {
    const code = encodeURIComponent(patientCode);
    const [profile, attention, latest, changes, timeline, notes] = await Promise.all([
      workspaceGet(`/api/patients/${code}`),
      workspaceGet(`/api/patients/${code}/attention`),
      workspaceGet(`/api/patients/${code}/trends?range=30d`),
      workspaceGet(`/api/patients/${code}/changes`),
      workspaceGet(`/api/patients/${code}/timeline`),
      workspaceGet(`/api/patients/${code}/notes`)
    ]);
    if (workspacePatientCode !== patientCode) return;
    workspaceText("workspace-name", profile.full_name);
    workspaceText("workspace-meta", `${profile.patient_code} · Bed ${profile.bed_number ?? "—"} · ${profile.status}`);
    const reportLink = document.getElementById("workspace-report");
    reportLink.href = `/api/reports/patients/${code}`;
    reportLink.hidden = false;
    workspaceText("workspace-attention-level", attention.level);
    const reasonList = document.getElementById("workspace-attention-reasons");
    reasonList.replaceChildren();
    attention.reasons.forEach((reason) => {
      const li = document.createElement("li"); li.textContent = reason; reasonList.appendChild(li);
    });
    const vitals = document.getElementById("workspace-vitals");
    vitals.replaceChildren();
    Object.entries(latest.metrics).forEach(([name, metric]) => {
      workspaceItem(vitals, name === "spo2" ? "SpO₂" : name === "pulse" ? "Heart rate" : "Temperature",
        metric.current === null ? "No reliable measurement" : `${metric.current} ${metric.unit}`,
        metric.last_measured_at ? `${new Date(metric.last_measured_at).toLocaleString()} · ${metric.source || "Unknown source"}` : "Repeat measurement recommended");
    });
    const changed = document.getElementById("workspace-changes");
    changed.replaceChildren();
    if (!changes.previous_available) changed.textContent = "No previous measurement available.";
    else Object.entries(changes.metrics).forEach(([name, metric]) => {
      workspaceItem(changed, name === "spo2" ? "SpO₂" : name === "pulse" ? "Heart rate" : "Temperature",
        metric.previous === null || metric.current === null ? "Comparable readings unavailable" : `${metric.previous} → ${metric.current} ${metric.unit}`,
        metric.delta === null ? null : `Change ${metric.delta > 0 ? "+" : ""}${metric.delta} ${metric.unit}`);
    });
    const timelineList = document.getElementById("workspace-timeline");
    timelineList.replaceChildren();
    const events = Array.isArray(timeline) ? timeline : (timeline.items || []);
    events.forEach((event) => {
      const li = document.createElement("li");
      workspaceItem(li, event.title, new Date(event.timestamp).toLocaleString(), event.source);
      timelineList.appendChild(li);
    });
    if (!events.length) timelineList.textContent = "No recorded events yet.";
    const noteList = document.getElementById("workspace-notes");
    noteList.replaceChildren();
    notes.forEach((note) => workspaceItem(noteList, "CLINICIAN NOTE", note.content, `${note.author} · ${new Date(note.created_at).toLocaleString()}`));
    if (!notes.length) noteList.textContent = "No clinician notes yet.";
    await window.loadWorkspaceTrends();
  } catch (error) {
    workspaceText("workspace-name", "Patient workspace unavailable");
    workspaceText("workspace-meta", error.message);
  }
};

window.loadWorkspaceTrends = async function() {
  if (!workspacePatientCode) return;
  try {
    const range = document.getElementById("workspace-range").value;
    const data = await workspaceGet(`/api/patients/${encodeURIComponent(workspacePatientCode)}/trends?range=${range}`);
    const summary = document.getElementById("workspace-trend-summary");
    summary.replaceChildren();
    Object.entries(data.metrics).forEach(([name, metric]) => workspaceItem(summary, name.toUpperCase(),
      metric.sample_count ? `Average ${metric.average} ${metric.unit} · Min ${metric.min} · Max ${metric.max}` : "No reliable samples in this range"));
    if (typeof Chart !== "function") return;
    const metrics = data.metrics;
    const timestamps = [...new Set(Object.values(metrics).flatMap((m) => m.series.map((point) => point.measured_at)))].sort();
    if (workspaceChart) workspaceChart.destroy();
    workspaceChart = new Chart(document.getElementById("workspace-chart"), {
      type: "line",
      data: { labels: timestamps.map((time) => new Date(time).toLocaleString()), datasets: [
        {label: "Temperature °C", data: timestamps.map((time) => metrics.temperature.series.find((p) => p.measured_at === time)?.value ?? null), borderColor: "#155eef", spanGaps: false},
        {label: "Heart rate BPM", data: timestamps.map((time) => metrics.pulse.series.find((p) => p.measured_at === time)?.value ?? null), borderColor: "#087e91", spanGaps: false, hidden: true},
        {label: "SpO₂ %", data: timestamps.map((time) => metrics.spo2.series.find((p) => p.measured_at === time)?.value ?? null), borderColor: "#18804a", spanGaps: false, hidden: true}
      ]},
      options: { responsive: true, plugins: {legend: {position: "bottom"}}, scales: {y: {beginAtZero: false}} }
    });
  } catch (_) {
    workspaceText("workspace-trend-summary", "Trends could not be loaded. Try another range.");
  }
};

document.getElementById("workspace-range").addEventListener("change", window.loadWorkspaceTrends);
document.getElementById("workspace-note-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!workspacePatientCode) return;
  const field = document.getElementById("workspace-note");
  const response = await fetch(`/api/patients/${encodeURIComponent(workspacePatientCode)}/notes`, {
    method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({content: field.value})
  });
  if (!response.ok) { alert("Clinical note could not be saved. Try again."); return; }
  field.value = "";
  await window.openPatientWorkspace(workspacePatientCode);
});
