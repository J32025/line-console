import { api } from './api.js'

const PAGE = 1000 // เพดานต่อคำขอของ /api/users

// ดึงผู้ใช้ทุกคนของเมนูหนึ่ง (ทุกหน้า) — menu = richMenuId หรือ 'none' · q = คำค้นเดียวกับในรายการ
export async function fetchMenuUsers(menu, q = '') {
  const users = new Map() // กันซ้ำด้วย userId: ถ้ามีคนอัปเดตระหว่างไล่หน้า ลำดับอาจเลื่อน
  for (let offset = 0; ; offset += PAGE) {
    const r = await api.users({ menu, q, limit: PAGE, offset })
    r.users.forEach((u) => users.set(u.line_user_id, u))
    if (r.users.length < PAGE || offset + PAGE >= r.total) break
  }
  return [...users.values()]
}

export async function fetchMenuUserIds(menu, q = '') {
  return (await fetchMenuUsers(menu, q)).map((u) => u.line_user_id)
}

// ชื่อ LINE บรรทัดละคน — คนไม่มีชื่อใส่ '(ไม่มีชื่อ)' และตัดการขึ้นบรรทัดในชื่อ เพื่อให้ 1 คน = 1 บรรทัดเสมอ
export const lineNames = (users) =>
  users.map((u) => (u.display_name || '').replace(/[\r\n\t\u2028\u2029]+/g, ' ').trim() || '(ไม่มีชื่อ)')

// สองคอลัมน์ "ชื่อ<TAB>userId" — วางลง Excel/Sheets แล้วแยกช่องเอง ชื่อกับ id มาจากแถวเดียวกันเสมอจึงไม่สลับคน
// ชื่อ LINE ผู้ใช้ตั้งเองได้: ถ้าขึ้นต้นด้วย = + - @ โปรแกรมตารางจะตีเป็นสูตร จึงเติม ' นำหน้าให้เป็นข้อความ
export const nameIdRows = (users) =>
  lineNames(users).map((name, i) => `${/^[=+\-@]/.test(name) ? "'" : ''}${name}\t${users[i].line_user_id}`)

// คัดลอก userId (บรรทัดละคน) — เบราว์เซอร์บล็อก clipboard ได้ จึง fallback เป็นดาวน์โหลดไฟล์ .txt
export async function copyUserIds(ids, t, fileName = 'userids', label = 'userId') {
  if (!ids.length) { t.err(`ไม่มี ${label} ให้คัดลอก`); return }
  const text = ids.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    t.ok(`คัดลอก ${label} แล้ว ${ids.length.toLocaleString()} คน`)
  } catch {
    const url = URL.createObjectURL(new Blob([text], { type: 'text/plain' }))
    const a = document.createElement('a')
    a.href = url
    a.download = `${fileName}.txt`
    a.click()
    URL.revokeObjectURL(url)
    t.ok(`คัดลอกอัตโนมัติไม่ได้ — ดาวน์โหลดเป็นไฟล์แทนแล้ว (${ids.length.toLocaleString()} คน)`)
  }
}
