const form = document.getElementById("intake-form");
const errorBanner = document.getElementById("error-banner");
const submitBtn = document.getElementById("submit-btn");

const video = document.getElementById("video");
const canvas = document.getElementById("canvas");
const snapshot = document.getElementById("snapshot");
const captureBtn = document.getElementById("capture-btn");
const retakeBtn = document.getElementById("retake-btn");
const photoStatus = document.getElementById("photo-status");

const wardGrid = document.getElementById("ward-grid");
const wardCount = document.getElementById("ward-count");
const selectedBedEl = document.getElementById("selected-bed");

const confirmation = document.getElementById("confirmation");

const bedModal = document.getElementById("bed-modal");
const modalClose = document.getElementById("modal-close");
const modalDischargeBtn = document.getElementById("modal-discharge-btn");
const modalError = document.getElementById("modal-error");

let capturedBlob = null;
let photoValidated = false;
let selectedBed = null;
let mediaStream = null;
let modalBedNumber = null;

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
    checkCapturedPhoto(blob);
  }, "image/jpeg", 0.92);
});

retakeBtn.addEventListener("click", () => {
  capturedBlob = null;
  photoValidated = false;
  snapshot.hidden = true;
  video.hidden = false;
  captureBtn.hidden = false;
  retakeBtn.hidden = true;
  photoStatus.hidden = true;
  refreshSubmitState();
});

async function checkCapturedPhoto(blob) {
  photoValidated = false;
  photoStatus.hidden = false;
  photoStatus.textContent = "Checking photo…";
  photoStatus.className = "photo-status checking";
  refreshSubmitState();

  const data = new FormData();
  data.append("photo", blob, "reference.jpg");

  try {
    const res = await fetch("/api/photo-check", { method: "POST", body: data });
    const body = await res.json();
    photoValidated = !!body.ok;
    photoStatus.textContent = body.message;
    photoStatus.className = "photo-status " + (body.ok ? "ok" : "bad");
  } catch (err) {
    photoValidated = false;
    photoStatus.textContent = "Could not reach the server to check the photo.";
    photoStatus.className = "photo-status bad";
  }
  refreshSubmitState();
}

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
    tile.setAttribute("role", "option");
    tile.setAttribute("aria-selected", "false");

    const numberEl = document.createElement("span");
    numberEl.textContent = bed.bed_number;
    tile.appendChild(numberEl);

    if (bed.is_occupied && bed.occupant_name) {
      const nameEl = document.createElement("span");
      nameEl.className = "occupant-name";
      nameEl.textContent = bed.occupant_name.split(" ")[0];
      tile.appendChild(nameEl);
      tile.addEventListener("click", () => openBedModal(bed));
    } else if (!bed.is_occupied) {
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

// ---- Bed detail / discharge modal ----

function openBedModal(bed) {
  modalBedNumber = bed.bed_number;
  document.getElementById("modal-bed-number").textContent = bed.bed_number;
  document.getElementById("modal-patient-name").textContent = bed.occupant_name || "";
  document.getElementById("modal-patient-code").textContent = bed.occupant_code || "";
  const admitted = bed.admitted_at ? new Date(bed.admitted_at).toLocaleString() : "";
  document.getElementById("modal-admitted").textContent = admitted ? `Admitted ${admitted}` : "";
  modalError.hidden = true;
  modalDischargeBtn.disabled = false;
  modalDischargeBtn.textContent = "Discharge & free bed";
  bedModal.hidden = false;
}

function closeBedModal() {
  bedModal.hidden = true;
  modalBedNumber = null;
}

modalClose.addEventListener("click", closeBedModal);
bedModal.addEventListener("click", (event) => {
  if (event.target === bedModal) closeBedModal();
});

modalDischargeBtn.addEventListener("click", async () => {
  if (modalBedNumber === null) return;
  modalDischargeBtn.disabled = true;
  modalDischargeBtn.textContent = "Discharging…";
  modalError.hidden = true;

  try {
    const res = await fetch(`/api/beds/${modalBedNumber}/discharge`, { method: "POST" });
    const body = await res.json();
    if (!res.ok) {
      modalError.textContent = body.detail || "Could not discharge this patient.";
      modalError.hidden = false;
      modalDischargeBtn.disabled = false;
      modalDischargeBtn.textContent = "Discharge & free bed";
      return;
    }
    closeBedModal();
    await loadBeds();
  } catch (err) {
    modalError.textContent = "Could not reach the server.";
    modalError.hidden = false;
    modalDischargeBtn.disabled = false;
    modalDischargeBtn.textContent = "Discharge & free bed";
  }
});

// ---- Form state / submission ----

function refreshSubmitState() {
  const requiredFieldsFilled = form.checkValidity();
  submitBtn.disabled = !(requiredFieldsFilled && photoValidated && selectedBed !== null);
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
  document.getElementById("confirm-pin").textContent = patient.portal_pin || "Ask a clinician to issue access";

  form.hidden = true;
  confirmation.hidden = false;
}

document.getElementById("new-patient-btn").addEventListener("click", () => {
  form.reset();
  capturedBlob = null;
  photoValidated = false;
  selectedBed = null;
  selectedBedEl.textContent = "None selected — pick one from the ward map";
  snapshot.hidden = true;
  video.hidden = false;
  captureBtn.hidden = false;
  retakeBtn.hidden = true;
  photoStatus.hidden = true;
  clearError();

  confirmation.hidden = true;
  form.hidden = false;
  submitBtn.textContent = "Register patient";
  refreshSubmitState();
});

// ---- Init ----

startCamera();
loadBeds();
