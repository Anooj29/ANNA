async function login() {
    const code = document.getElementById('patient-code').value;
    const res = await fetch(`/api/login?patient_code=${encodeURIComponent(code)}`, { method: 'POST' });
    if (res.ok) {
        const data = await res.json();
        document.getElementById('patient-name').innerText = data.full_name;
        document.getElementById('login-screen').classList.add('hidden');
        document.getElementById('dashboard-screen').classList.remove('hidden');
        fetchSessions();
    } else {
        alert('Invalid patient code. Please try again.');
    }
}

async function fetchSessions() {
    const res = await fetch('/api/my-sessions');
    if (!res.ok) {
        document.getElementById('login-screen').classList.remove('hidden');
        document.getElementById('dashboard-screen').classList.add('hidden');
        return;
    }
    const sessions = await res.json();
    const list = document.getElementById('sessions-list');
    list.innerHTML = '';

    if (sessions.length === 0) {
        list.innerHTML = '<p style="text-align:center">No health records found yet.</p>';
        return;
    }

    sessions.forEach(s => {
        const card = document.createElement('div');
        card.className = 'session-card';
        card.innerHTML = `
            <div class="header">
                <span>📅 ${new Date(s.timestamp).toLocaleString()}</span>
                <span>Mood: ${s.emotion || 'N/A'}</span>
            </div>
            <div class="vitals-grid">
                <div class="vital-item"><strong>Temp</strong> ${s.temperature || '--'}</div>
                <div class="vital-item"><strong>Pulse</strong> ${s.pulse || '--'}</div>
                <div class="vital-item"><strong>ECG</strong> ${s.ecg || '--'}</div>
            </div>
            <div class="report-box">${s.health_report || 'No report available.'}</div>
        `;
        list.appendChild(card);
    });
}

document.getElementById('login-btn').onclick = login;
document.getElementById('logout-btn').onclick = () => {
    document.cookie = "patient_code=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
    location.reload();
};
