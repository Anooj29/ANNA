async function fetchPatients() {
    const res = await fetch('/api/patients');
    const patients = await res.json();
    const grid = document.getElementById('patient-grid');
    grid.innerHTML = '';

    patients.forEach(p => {
        const card = document.createElement('div');
        card.className = 'patient-card';
        card.innerHTML = `
            <h3>${p.full_name}</h3>
            <div class="meta">Code: ${p.patient_code}</div>
            <div class="meta">Bed: ${p.bed_number || 'N/A'}</div>
        `;
        card.onclick = () => showDetails(p);
        grid.appendChild(card);
    });
}

async function showDetails(patient) {
    document.getElementById('patient-list-section').classList.add('hidden');
    document.getElementById('detail-section').classList.remove('hidden');

    document.getElementById('detail-name').innerText = patient.full_name;
    document.getElementById('detail-code').innerText = patient.patient_code;
    document.getElementById('detail-bed').innerText = patient.bed_number || 'N/A';
    document.getElementById('detail-blood').innerText = patient.blood_group;

    const assignBtn = document.getElementById('assign-robot-btn');
    assignBtn.onclick = async () => {
        const res = await fetch(`/api/assignments?patient_id=${patient.id}`, { method: 'POST' });
        if (res.ok) {
            alert('ANNA has been assigned to this patient!');
        } else {
            alert('Failed to assign robot.');
        }
    };

    const sessionsRes = await fetch(`/api/patients/${encodeURIComponent(patient.full_name)}/sessions`);
    const sessions = await sessionsRes.json();
    const list = document.getElementById('sessions-list');
    list.innerHTML = '';

    if (sessions.length === 0) {
        list.innerHTML = '<p>No health sessions recorded yet.</p>';
        return;
    }

    sessions.forEach(s => {
        const card = document.createElement('div');
        card.className = 'session-card';
        card.innerHTML = `
            <div class="header">
                <strong>Session Date: ${new Date(s.timestamp).toLocaleString()}</strong>
                <span>Emotion: ${s.emotion || 'N/A'}</span>
            </div>
            <div class="vitals">
                <div class="vital-item"><strong>Temp</strong> ${s.temperature || '--'}</div>
                <div class="vital-item"><strong>Pulse</strong> ${s.pulse || '--'}</div>
                <div class="vital-item"><strong>ECG</strong> ${s.ecg || '--'}</div>
            </div>
            <div class="report-text">${s.health_report || 'No report available.'}</div>
        `;
        list.appendChild(card);
    });
}

document.getElementById('back-btn').onclick = () => {
    document.getElementById('patient-list-section').classList.remove('hidden');
    document.getElementById('detail-section').classList.add('hidden');
};

fetchPatients();
