const notificationToggle = document.getElementById('notifications-toggle');
const notificationPanel = document.getElementById('notifications-panel');
const notificationCount = document.getElementById('notifications-count');
const notificationList = document.getElementById('notifications-list');

async function loadNotifications() {
  if (document.getElementById('app-view').hidden) return;
  try {
    const response = await fetch('/api/clinician/notifications');
    if (!response.ok) throw new Error('Could not load notifications');
    const data = await response.json();
    notificationCount.hidden = !data.unread_count;
    notificationCount.textContent = String(data.unread_count);
    notificationList.replaceChildren();
    if (!data.items.length) {
      notificationList.textContent = 'You are all caught up.';
      return;
    }
    for (const row of data.items) {
      const item = document.createElement('div');
      item.className = `notification-item${row.read_at ? '' : ' unread'}`;
      item.setAttribute('role', 'listitem');
      const title = document.createElement('strong');
      title.textContent = row.title;
      const time = document.createElement('time');
      time.dateTime = row.created_at;
      time.textContent = new Date(row.created_at).toLocaleString();
      item.append(title, time);
      if (!row.read_at) {
        const button = document.createElement('button');
        button.className = 'btn btn-outline btn-small';
        button.type = 'button';
        button.textContent = 'Mark read';
        button.addEventListener('click', async () => {
          const result = await fetch(`/api/clinician/notifications/${row.id}/read`, {method: 'POST'});
          if (result.ok) loadNotifications();
        });
        item.append(button);
      }
      notificationList.append(item);
    }
  } catch (_) {
    notificationList.textContent = 'Notifications are temporarily unavailable.';
  }
}
notificationToggle.addEventListener('click', () => {
  notificationPanel.hidden = !notificationPanel.hidden;
  notificationToggle.setAttribute('aria-expanded', String(!notificationPanel.hidden));
  if (!notificationPanel.hidden) loadNotifications();
});
document.getElementById('notifications-close').addEventListener('click', () => {
  notificationPanel.hidden = true;
  notificationToggle.setAttribute('aria-expanded', 'false');
  notificationToggle.focus();
});
window.loadNotifications = loadNotifications;
