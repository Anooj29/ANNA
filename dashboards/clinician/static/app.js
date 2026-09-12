const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let stream;

async function api(path, options = {}) {
  const response = await fetch(path, {headers: {'Content-Type':'application/json', ...(options.headers || {})}, ...options});
  if (!response.ok) throw new Error((await response.json().catch(()=>({detail:'Request failed'}))).detail || 'Request failed');
  return response.status === 204 ? null : response.json();
}
function fmt(date) { return new Date(date + (date.endsWith('Z') ? '' : 'Z')).toLocaleString([], {dateStyle:'medium', timeStyle:'short'}); }
function label(type) { return ({health_check:'Health check',rounding:'Safety round',video_call:'Video call',medication_reminder:'Medication reminder'})[type] || type; }

async function load() {
  const [patients, tasks, summaries] = await Promise.all([api('/api/patients'), api('/api/tasks'), api('/api/summaries')]);
  const patient = $('#patient'), filter = $('#summary-filter');
  const current = patient.value, filterValue = filter.value;
  const options = patients.map(p => `<option value="${esc(p.patient_code)}">Bed ${p.bed_number} · ${esc(p.full_name)} (${esc(p.patient_code)})</option>`).join('');
  patient.innerHTML = '<option value="">Choose an admitted patient</option>' + options; patient.value = current;
  filter.innerHTML = '<option value="">All admitted patients</option>' + options; filter.value = filterValue;
  $('#task-list').innerHTML = tasks.length ? tasks.map(t => `<div class="task"><div class="task-top"><span class="pill ${t.priority}">${esc(t.priority)}</span><span class="task-status ${esc(t.status)}">${esc(t.status.replace('_',' '))}</span></div><h3>Bed ${t.bed_number} · ${esc(t.patient_name)}</h3><p>${esc(label(t.task_type))}${t.instructions ? ' — ' + esc(t.instructions) : ''}</p><small>Assigned ${fmt(t.created_at)} by ${esc(t.assigned_by)}</small></div>`).join('') : '<p class="empty">No visits are waiting. ANNA is at home.</p>';
  renderSummaries(summaries, filter.value);
}
function renderSummaries(items, code='') {
  const shown = code ? items.filter(s => s.patient_code === code) : items;
  $('#summary-list').innerHTML = shown.length ? shown.map(s => `<article class="summary"><div><span class="eyebrow">BED ${s.bed_number ?? '—'} · ${esc(s.patient_code)}</span><h3>${esc(s.patient_name)}</h3></div><time>${fmt(s.created_at)}</time><p>${esc(s.summary)}</p><dl>${s.temperature_c ? `<div><dt>Temperature</dt><dd>${esc(s.temperature_c)} °C</dd></div>`:''}${s.pulse_bpm ? `<div><dt>Pulse</dt><dd>${esc(s.pulse_bpm)} bpm</dd></div>`:''}${s.ecg_note ? `<div><dt>ECG note</dt><dd>${esc(s.ecg_note)}</dd></div>`:''}</dl><small>Recorded by ${esc(s.author)}</small></article>`).join('') : '<p class="empty">No ANNA summaries match this view.</p>';
}
async function boot() {
  try { const me = await api('/api/auth/me'); if (!me.email) return; $('#login-view').hidden=true; $('#app-view').hidden=false; await load(); }
  catch (_) { /* unauthenticated remains at login */ }
}
$('#login-form').addEventListener('submit', async e => { e.preventDefault(); const data=Object.fromEntries(new FormData(e.target)); try { await api('/api/auth/login',{method:'POST',body:JSON.stringify(data)}); await boot(); } catch(err) { $('#login-error').hidden=false; $('#login-error').textContent=err.message; }});
$('#task-form').addEventListener('submit', async e => { e.preventDefault(); const msg=$('#task-message'); try { await api('/api/tasks',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(e.target)))}); e.target.reset(); msg.textContent='Visit added to ANNA’s queue.'; await load(); } catch(err) { msg.textContent=err.message; }});
$('#refresh').onclick = load;
$('#summary-filter').onchange = async () => renderSummaries(await api('/api/summaries'), $('#summary-filter').value);
$('#logout').onclick = async () => { await api('/api/auth/logout',{method:'POST'}); location.reload(); };
$('#start-video').onclick = async () => { try { stream=await navigator.mediaDevices.getUserMedia({video:true,audio:true}); $('#preview').srcObject=stream; $('#video-placeholder').hidden=true; } catch(e) { alert('Camera access was not available. Allow camera permission, then try again.'); }};
$('#stop-video').onclick = () => { stream?.getTracks().forEach(t=>t.stop()); stream=null; $('#preview').srcObject=null; $('#video-placeholder').hidden=false; };
boot();
