import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner } from '../lib/ui.jsx'

// นำเข้า CSV: parse header -> ให้ผู้ใช้ map คอลัมน์ -> ส่ง rows แบบ map แล้ว
const TARGETS = [
  ['userId', 'LINE userId *'],
  ['displayName', 'ชื่อ'],
  ['tags', 'Tags (คั่น , หรือ |)'],
  ['note', 'Note'],
]

function parseCSV(text) {
  const rows = []
  let row = [], cell = '', q = false
  for (let i = 0; i < text.length; i++) {
    const c = text[i]
    if (q) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++ }
      else if (c === '"') q = false
      else cell += c
    } else if (c === '"') q = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n' || c === '\r') {
      if (c === '\r' && text[i + 1] === '\n') i++
      row.push(cell); rows.push(row); row = []; cell = ''
    } else cell += c
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  return rows.filter((r) => r.some((x) => x.trim()))
}

export default function ImportMapper({ onClose, onDone }) {
  const t = useToast()
  const [raw, setRaw] = useState(null)   // {headers, rows}
  const [map, setMap] = useState({})     // target -> headerIndex
  const [customMap, setCustomMap] = useState([]) // [{key, headerIdx}]
  const [fields, setFields] = useState([])
  const [busy, setBusy] = useState(false)

  useEffect(() => { api.fields().then((d) => setFields(d.fields)).catch(() => {}) }, [])

  const onFile = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => {
      const parsed = parseCSV(String(r.result).replace(/^﻿/, ''))
      const headers = parsed[0] || []
      setRaw({ headers, rows: parsed.slice(1) })
      // auto-map
      const auto = {}
      headers.forEach((h, i) => {
        const l = h.toLowerCase().trim()
        if (['userid', 'uid', 'user_id', 'line_user_id'].includes(l)) auto.userId = i
        else if (['name', 'displayname', 'ชื่อ'].includes(l)) auto.displayName = i
        else if (['tag', 'tags'].includes(l)) auto.tags = i
        else if (['note', 'หมายเหตุ'].includes(l)) auto.note = i
      })
      setMap(auto)
    }
    r.readAsText(f)
  }

  const submit = async () => {
    if (map.userId == null) return t.err('ต้อง map คอลัมน์ userId')
    const rows = raw.rows.map((r) => {
      const o = { userId: r[map.userId]?.trim() }
      if (map.displayName != null) o.displayName = r[map.displayName]?.trim()
      if (map.tags != null) o.tags = r[map.tags]?.trim()
      if (map.note != null) o.note = r[map.note]?.trim()
      const custom = {}
      customMap.forEach(({ key, headerIdx }) => {
        if (headerIdx !== '' && r[headerIdx] != null) custom[key] = r[headerIdx].trim()
      })
      if (Object.keys(custom).length) o.custom = custom
      return o
    })
    setBusy(true)
    try {
      const res = await api.importMapped({ rows })
      t.ok(`นำเข้า ${res.valid}/${res.submitted} แถว`)
      onDone()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 560 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread"><h3>นำเข้าจาก CSV</h3><button className="xs" onClick={onClose}>✕</button></div>

        {!raw ? (
          <>
            <p className="muted sm">เลือกไฟล์ .csv ที่มีแถวหัวคอลัมน์ — คอลัมน์ userId บังคับ</p>
            <input type="file" accept=".csv,text/csv" onChange={onFile} />
          </>
        ) : (
          <>
            <p className="muted sm">{raw.rows.length} แถว · {raw.headers.length} คอลัมน์ — จับคู่คอลัมน์:</p>
            <table className="kv">
              <tbody>
                {TARGETS.map(([key, label]) => (
                  <tr key={key}>
                    <th>{label}</th>
                    <td>
                      <select value={map[key] ?? ''} onChange={(e) => setMap({ ...map, [key]: e.target.value === '' ? undefined : +e.target.value })}>
                        <option value="">— ไม่ใช้ —</option>
                        {raw.headers.map((h, i) => <option key={i} value={i}>{h || `คอลัมน์ ${i + 1}`}</option>)}
                      </select>
                    </td>
                  </tr>
                ))}
                {fields.map((f) => {
                  const cm = customMap.find((c) => c.key === f.key)
                  return (
                    <tr key={f.key}>
                      <th>{f.label} <span className="muted xs">(custom)</span></th>
                      <td>
                        <select value={cm?.headerIdx ?? ''} onChange={(e) => {
                          const v = e.target.value
                          setCustomMap((prev) => [...prev.filter((c) => c.key !== f.key), ...(v === '' ? [] : [{ key: f.key, headerIdx: +v }])])
                        }}>
                          <option value="">— ไม่ใช้ —</option>
                          {raw.headers.map((h, i) => <option key={i} value={i}>{h || `คอลัมน์ ${i + 1}`}</option>)}
                        </select>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            <div className="muted xs" style={{ margin: '8px 0' }}>
              ตัวอย่างแถวแรก: {raw.rows[0]?.slice(0, 4).join(' | ')}
            </div>
            <div className="row">
              <button className="primary" onClick={submit} disabled={busy}>{busy && <InlineSpinner />}นำเข้า</button>
              <button onClick={() => setRaw(null)}>เลือกไฟล์ใหม่</button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
