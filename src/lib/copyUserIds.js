import { api } from './api.js'

const PAGE = 1000 // เพดานต่อคำขอของ /api/users

// ดึง userId ทุกคนของเมนูหนึ่ง (ทุกหน้า) — menu = richMenuId หรือ 'none' · q = คำค้นเดียวกับในรายการ
export async function fetchMenuUserIds(menu, q = '') {
  const ids = new Set() // กันซ้ำ: ถ้ามีคนอัปเดตระหว่างไล่หน้า ลำดับอาจเลื่อน
  for (let offset = 0; ; offset += PAGE) {
    const r = await api.users({ menu, q, limit: PAGE, offset })
    r.users.forEach((u) => ids.add(u.line_user_id))
    if (r.users.length < PAGE || offset + PAGE >= r.total) break
  }
  return [...ids]
}

// คัดลอก userId (บรรทัดละคน) — เบราว์เซอร์บล็อก clipboard ได้ จึง fallback เป็นดาวน์โหลดไฟล์ .txt
export async function copyUserIds(ids, t, fileName = 'userids') {
  if (!ids.length) { t.err('ไม่มี userId ให้คัดลอก'); return }
  const text = ids.join('\n')
  try {
    await navigator.clipboard.writeText(text)
    t.ok(`คัดลอก userId แล้ว ${ids.length.toLocaleString()} คน`)
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
