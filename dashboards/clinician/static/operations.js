/* Operational analytics and admin audit views use DOM text nodes for data. */
let auditPage = 1;
let auditPages = 1;

window.loadOperations = async function() {
  const metrics = document.getElementById('operations-metrics');
  const devices = document.getElementById('robot-status-list');
  try {
    const [operationsResponse, devicesResponse] = await Promise.all([
      fetch('/api/analytics/operations?days=7'), fetch('/api/robot/status')
    ]);
    if (!operationsResponse.ok || !devicesResponse.ok) throw new Error('Unavailable');
    const operations = await operationsResponse.json();
    const robots = await devicesResponse.json();
    metrics.replaceChildren();
    for (const [title, value] of [
      ['Completed visits', operations.completed_visits],
      ['Failed visits', operations.failed_visits],
      ['Alerts detected', operations.alerts_detected],
      ['Patients monitored', operations.patients_monitored],
      ['Estimated time saved', `${operations.estimated_time_saved_minutes} minutes`]
    ]) {
      const item = document.createElement('div'); item.className = 'workspace-item';
      const label = document.createElement('span'); label.textContent = title;
      const number = document.createElement('strong'); number.textContent = String(value);
      item.append(label, number); metrics.append(item);
    }
    const formula = document.createElement('small');
    formula.textContent = `Estimate: ${operations.estimate_formula}. This is an operational illustration, not observed staff time.`;
    metrics.append(formula);
    devices.replaceChildren();
    if (!robots.length) {
      devices.textContent = 'No robot heartbeat has been received.';
    } else {
      robots.forEach(robot => {
        const item = document.createElement('div'); item.className = 'workspace-item';
        const name = document.createElement('strong'); name.textContent = robot.robot_id;
        const detail = document.createElement('span');
        detail.textContent = `${robot.status.toUpperCase()} · Last heartbeat ${new Date(robot.last_seen_at).toLocaleString()}${robot.battery_percent == null ? '' : ` · Battery ${robot.battery_percent}%`}`;
        item.append(name, detail); devices.append(item);
      });
    }
  } catch (_) {
    metrics.textContent = 'Operations data is temporarily unavailable.';
    devices.textContent = 'Device status is temporarily unavailable.';
  }
};

window.loadAudit = async function() {
  const tbody = document.getElementById('audit-table-body');
  try {
    const response = await fetch(`/api/admin/audit?limit=25&offset=${(auditPage - 1) * 25}`);
    if (!response.ok) throw new Error('Audit request failed');
    const result = await response.json();
    auditPages = Math.max(1, Math.ceil(result.total / 25));
    if (auditPage > auditPages) { auditPage = auditPages; return window.loadAudit(); }
    document.getElementById('audit-page-label').textContent = `Page ${auditPage} of ${auditPages}`;
    document.getElementById('audit-prev').disabled = auditPage <= 1;
    document.getElementById('audit-next').disabled = auditPage >= auditPages;
    tbody.replaceChildren();
    if (!result.items.length) {
      const row = tbody.insertRow(); const cell = row.insertCell(); cell.colSpan = 5;
      cell.textContent = 'No audit events have been recorded.';
      return;
    }
    result.items.forEach(event => {
      const row = tbody.insertRow();
      [new Date(event.timestamp).toLocaleString(), event.actor_role || 'system',
       event.action, `${event.entity_type || '—'} ${event.entity_id || ''}`, event.details]
        .forEach(value => { row.insertCell().textContent = value; });
    });
  } catch (_) {
    tbody.replaceChildren();
    const row = tbody.insertRow(); const cell = row.insertCell(); cell.colSpan = 5;
    cell.textContent = 'Audit events could not be loaded.';
  }
};
document.getElementById('audit-prev').addEventListener('click', () => { if (auditPage > 1) { auditPage--; window.loadAudit(); } });
document.getElementById('audit-next').addEventListener('click', () => { if (auditPage < auditPages) { auditPage++; window.loadAudit(); } });
