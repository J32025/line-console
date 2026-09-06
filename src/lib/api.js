import { getIdToken } from './auth.js'

async function req(method, path, body) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${getIdToken() || ''}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  })
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : {} } catch { data = { detail: text } }
  if (!res.ok) throw new Error(data.detail || data.message || `HTTP ${res.status}`)
  return data
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  patch: (p, b) => req('PATCH', p, b),
  del: (p) => req('DELETE', p),

  me: () => req('GET', '/me'),
  dashboard: () => req('GET', '/dashboard'),

  richmenus: () => req('GET', '/richmenus'),
  setDefaultMenu: (richMenuId) => req('POST', '/richmenu/default', { richMenuId }),
  clearDefaultMenu: () => req('DELETE', '/richmenu/default'),
  deleteMenu: (rid) => req('DELETE', `/richmenu/${rid}`),
  assignMenu: (payload) => req('POST', '/richmenu/assign', payload),
  syncMenu: (payload) => req('POST', '/richmenu/sync', payload),

  users: (qs = {}) => req('GET', '/users?' + new URLSearchParams(qs)),
  importUsers: (payload) => req('POST', '/users/import', payload),
  refreshProfiles: (payload) => req('POST', '/users/refresh-profile', payload),
  syncFollowers: () => req('POST', '/users/sync-followers'),
  updateUser: (uid, patch) => req('PATCH', `/users/${uid}`, patch),

  validateMsg: (messages) => req('POST', '/message/validate', { messages }),
  push: (payload) => req('POST', '/message/push', payload),
  broadcast: (payload) => req('POST', '/message/broadcast', payload),
  multicastDb: (payload) => req('POST', '/message/multicast-from-db', payload),
  broadcastHistory: () => req('GET', '/broadcasts'),

  quota: () => req('GET', '/stats/quota'),
  insight: (date) => req('GET', '/stats/insight' + (date ? `?date=${date}` : '')),
  statsHistory: (days = 30) => req('GET', `/stats/history?days=${days}`),

  events: (qs = {}) => req('GET', '/events?' + new URLSearchParams(qs)),
  operations: () => req('GET', '/operations'),

  admins: () => req('GET', '/admins'),
  addAdmin: (payload) => req('POST', '/admins', payload),
  delAdmin: (uid) => req('DELETE', `/admins/${uid}`),
}
