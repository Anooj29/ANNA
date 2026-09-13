const $ = selector => document.querySelector(selector);
async function api(path, options = {}) {
  const response = await fetch(path, {headers:{'Content-Type':'application/json', ...(options.headers || {})}, ...options});
  if (!response.ok) throw new Error((await response.json().catch(() => ({detail:'Request failed'}))).detail || 'Request failed');
  return response.json();
}
function connect() {
  const feed = $('#feed');
  $('#connection').textContent = 'CONNECTING';
  $('#empty').hidden = false;
  feed.src = '/api/vision/stream?at=' + Date.now();
}
$('#feed').onload = () => { $('#connection').textContent = 'LIVE'; $('#empty').hidden = true; };
$('#feed').onerror = () => { $('#connection').textContent = 'OFFLINE'; $('#empty').hidden = false; };
$('#reconnect').onclick = connect;
$('#login-form').onsubmit = async event => { event.preventDefault(); try { await api('/api/auth/login', {method:'POST', body:JSON.stringify(Object.fromEntries(new FormData(event.target)))}); await boot(); } catch (error) { $('#login-error').hidden=false; $('#login-error').textContent=error.message; } };
$('#logout').onclick = async () => { await api('/api/auth/logout', {method:'POST'}); location.reload(); };
async function boot() { const me = await api('/api/auth/me'); if (!me.email) return; $('#login-view').hidden=true; $('#app-view').hidden=false; connect(); }
boot().catch(() => {});
