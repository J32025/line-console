import { getIdToken } from './auth.js'

// --- network activity hook (สำหรับ top loading bar) ---
const netListeners = new Set()
export function onNetActivity(fn) { netListeners.add(fn); return () => netListeners.delete(fn) }
const emitNet = (d) => netListeners.forEach((fn) => fn(d))

async function req(method, path, body) {
  emitNet(1)
  try {
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
  } finally {
    emitNet(-1)
  }
}

export const api = {
  get: (p) => req('GET', p),
  post: (p, b) => req('POST', p, b),
  patch: (p, b) => req('PATCH', p, b),
  del: (p) => req('DELETE', p),

  me: () => req('GET', '/me'),
  dashboard: () => req('GET', '/dashboard'),

  richmenus: () => req('GET', '/richmenus'),
  richmenuUsage: () => req('GET', '/richmenu/usage'),
  createMenu: (payload) => req('POST', '/richmenu/create', payload),
  uploadMenuImage: (rid, imageBase64) => req('POST', `/richmenu/${rid}/image`, { imageBase64 }),
  setDefaultMenu: (richMenuId) => req('POST', '/richmenu/default', { richMenuId }),
  clearDefaultMenu: () => req('DELETE', '/richmenu/default'),
  deleteMenu: (rid) => req('DELETE', `/richmenu/${rid}`),
  assignMenu: (payload) => req('POST', '/richmenu/assign', payload),
  syncMenu: (payload) => req('POST', '/richmenu/sync', payload),

  users: (qs = {}) => req('GET', '/users?' + new URLSearchParams(qs)),
  userDetail: (uid) => req('GET', `/users/${uid}`),
  importUsers: (payload) => req('POST', '/users/import', payload),
  refreshProfiles: (payload) => req('POST', '/users/refresh-profile', payload),
  syncFollowers: () => req('POST', '/users/sync-followers'),
  updateUser: (uid, patch) => req('PATCH', `/users/${uid}`, patch),

  validateMsg: (messages) => req('POST', '/message/validate', { messages }),
  push: (payload) => req('POST', '/message/push', payload),
  bulkSend: (payload) => req('POST', '/message/bulk', payload),
  broadcast: (payload) => req('POST', '/message/broadcast', payload),
  multicastDb: (payload) => req('POST', '/message/multicast-from-db', payload),
  broadcastHistory: () => req('GET', '/broadcasts'),

  quota: () => req('GET', '/stats/quota'),
  insight: (date) => req('GET', '/stats/insight' + (date ? `?date=${date}` : '')),
  statsHistory: (days = 30) => req('GET', `/stats/history?days=${days}`),
  followStats: (days = 14) => req('GET', `/stats/follows?days=${days}`),

  events: (qs = {}) => req('GET', '/events?' + new URLSearchParams(qs)),
  operations: () => req('GET', '/operations'),

  admins: () => req('GET', '/admins'),
  addAdmin: (payload) => req('POST', '/admins', payload),
  delAdmin: (uid) => req('DELETE', `/admins/${uid}`),

  health: () => req('GET', '/health?deep=1'),
  backupNow: () => req('POST', '/backup/now'),
  backupList: () => req('GET', '/backup/list'),
  backupGet: (id) => req('GET', `/backup/${id}`),

  autoReplies: () => req('GET', '/auto-replies'),
  saveAutoReply: (payload) => req('POST', '/auto-replies', payload),
  delAutoReply: (id) => req('DELETE', `/auto-replies/${id}`),

  scheduled: () => req('GET', '/scheduled'),
  schedule: (payload) => req('POST', '/scheduled', payload),
  cancelScheduled: (id) => req('DELETE', `/scheduled/${id}`),

  segments: () => req('GET', '/segments'),
  saveSegment: (payload) => req('POST', '/segments', payload),
  segmentCount: (id) => req('GET', `/segments/${id}/count`),
  delSegment: (id) => req('DELETE', `/segments/${id}`),

  narrowcast: (payload) => req('POST', '/message/narrowcast', payload),
  resolveTarget: (payload) => req('POST', '/target/resolve', payload),

  inbox: (qs = {}) => req('GET', '/inbox?' + new URLSearchParams(qs)),
  thread: (uid, qs = {}) => req('GET', `/inbox/${uid}?` + new URLSearchParams(qs)),
  threadRead: (uid) => req('POST', `/inbox/${uid}/read`),
  threadPause: (uid, paused) => req('POST', `/inbox/${uid}/pause`, { paused }),
  threadSend: (uid, messages) => req('POST', `/inbox/${uid}/send`, { messages }),
}
