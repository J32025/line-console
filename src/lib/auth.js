import liff from '@line/liff'

const LIFF_ID = import.meta.env.VITE_LIFF_ID
let ready = null

export function initAuth() {
  if (ready) return ready
  ready = (async () => {
    if (!LIFF_ID) throw new Error('ยังไม่ได้ตั้ง VITE_LIFF_ID')
    await liff.init({ liffId: LIFF_ID })
    if (!liff.isLoggedIn()) {
      liff.login({ redirectUri: window.location.href })
      await new Promise(() => {})
    }
    const profile = await liff.getProfile()
    return {
      idToken: liff.getIDToken(),
      userId: profile.userId,
      name: profile.displayName,
      picture: profile.pictureUrl || '',
    }
  })()
  return ready
}

export function getIdToken() {
  try { return liff.getIDToken() } catch { return null }
}

export function logout() {
  try { liff.logout() } catch {}
  window.location.reload()
}
