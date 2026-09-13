const form = document.getElementById("intake-form");
const errorBanner = document.getElementById("error-banner");
const submitBtn = document.getElementById("submit-btn");

const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const snapshot = document.getElementById("snapshot");
const captureBtn = document.getElementById("capture-btn");
const retakeBtn = document.getElementById("retake-btn");

const wardGrid = document.getElementById("ward-grid");
const wardCount = document.getElementById("ward-count");
const selectedBedEl = document.getElementById("selected-bed");

const confirmation = document.getElementById("confirmation");

let capturedBlob = null;
let selectedBed = null;
let mediaStream = null;

// ---- Live clock ----

function tickClock() {
  const now = new Date();
  document.getElementById("clock").textContent = now.toLocaleString(undefined, {
    weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}
tickClock();
setInterval(tickClock, 1000);

// ---- Camera ----

async function startCamera() {
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
    video.srcObject = mediaStream;
  } catch (err) {
    showError("Could not access the camera. Check permissions and reload the page.");
  }
}

captureBtn.addEventListener("click", () => {
  canvas.width = video.videoWidth || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((blob) => {
    capturedBlob = blob;
    snapshot.src = URL.createObjectURL(blob);
    snapshot.hidden = false;
    video.hidden = true;
    captureBtn.hidden = true;
    retakeBtn.hidden = false;
    refreshSubmitState();
  }, "image/jpeg", 0.92);
});

retakeBtn.addEventListener("click", () => {
  capturedBlob = null;
  snapshot.hidden = true;
  video.hidden = false;
  captureBtn.hidden = false;
  retakeBtn.hidden = true;
  refreshSubmitState();
});

// ---- Ward map ----

async function loadBeds() {
  const res = await fetch("/api/beds");
  const beds = await res.json();

  wardGrid.innerHTML = "";
  const free = beds.filter((b) => !b.is_occupied).length;
  wardCount.textContent = `${free} of ${beds.length} beds free`;

  for (const bed of beds) {
    const tile = document.createElement("div");
    tile.className = "bed-tile" + (bed.is_occupied ? " taken" : "");
    tile.textContent = bed.bed_number;
    tile.setAttribute("role", "option");
    tile.setAttribute("aria-selected", "false");

    if (!bed.is_occupied) {
      tile.addEventListener("click", () => selectBed(bed.bed_number, tile));
    }
    wardGrid.appendChild(tile);
  }
}

function selectBed(bedNumber, tileEl) {
  selectedBed = bedNumber;
  selectedBedEl.textContent = `Bed ${bedNumber}`;
  for (const tile of wardGrid.querySelectorAll(".bed-tile")) {
    tile.classList.remove("selected");
    tile.setAttribute("aria-selected", "false");
  }
  tileEl.classList.add("selected");
  tileEl.setAttribute("aria-selected", "true");
  refreshSubmitState();
}

// ---- Form state / submission ----

function refreshSubmitState() {
  const requiredFieldsFilled = form.checkValidity();
  submitBtn.disabled = !(requiredFieldsFilled && capturedBlob && selectedBed !== null);
}

form.addEventListener("input", refreshSubmitState);

function showError(message) {
  errorBanner.textContent = message;
  errorBanner.hidden = false;
}

function clearError() {
  errorBanner.hidden = true;
  errorBanner.textContent = "";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  clearError();
  submitBtn.disabled = true;
  submitBtn.textContent = "Registering…";

  const data = new FormData(form);
  data.set("bed_number", selectedBed);
  data.set("photo", capturedBlob, "reference.jpg");

  try {
    const res = await fetch("/api/patients", { method: "POST", body: data });
    const body = await res.json();

    if (!res.ok) {
      showError(body.detail || "Registration failed. Please try again.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Register patient";
      return;
    }

    showConfirmation(body);
    await loadBeds();
  } catch (err) {
    showError("Could not reach the server. Check that the dashboard backend is running.");
    submitBtn.disabled = false;
    submitBtn.textContent = "Register patient";
  }
});

function showConfirmation(patient) {
  document.getElementById("confirm-photo").src = snapshot.src;
  document.getElementById("confirm-name").textContent = patient.full_name;
  document.getElementById("confirm-code").textContent = patient.patient_code;
  document.getElementById("confirm-bed").textContent = patient.bed_number;

  form.hidden = true;
  confirmation.hidden = false;
}

document.getElementById("new-patient-btn").addEventListener("click", () => {
  form.reset();
  capturedBlob = null;
  selectedBed = null;
  selectedBedEl.textContent = "None selected — pick one from the ward map";
  snapshot.hidden = true;
  video.hidden = false;
  captureBtn.hidden = false;
  retakeBtn.hidden = true;
  clearError();

  confirmation.hidden = true;
  form.hidden = false;
  submitBtn.textContent = "Register patient";
  refreshSubmitState();
});

// ---- Init ----

startCamera();
loadBeds();
