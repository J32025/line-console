import { useState } from 'react'
import { api } from '../lib/api.js'
import { InlineSpinner, useToast } from '../lib/ui.jsx'

const ACTION = {
  rule: ['ทำกฎคีย์เวิร์ด + ปุ่ม', 'คำตอบเหมือนกันทุกคน'],
  ai: ['ใส่คลังความรู้ให้ AI', 'ถามได้หลายแบบ'],
  status: ['ตอบจากข้อมูลจริง', 'ถามสถานะของตัวเอง'],
  admin: ['ส่งต่อแอดมิน', 'ต้องคนตัดสินใจ'],
}
const n = (v) => (v ?? 0).toLocaleString()
// ข้อความลูกค้าอาจขึ้นต้นเป็นสูตรเมื่อวางลงตารางคำนวณ
const cell = (v) => { const s = String(v ?? '').replace(/[\r\n\t]+/g, ' '); return /^[=+\-@]/.test(s) ? `'${s}` : s }

// วิเคราะห์คำถามขาเข้าทั้งหมด จัดกลุ่มเรื่องเดียวกัน · onArticle = เปิดฟอร์มสร้างบทความจากกลุ่มนั้น
export default function QuestionAnalysis({ onArticle }) {
  const t = useToast()
  const [days, setDays] = useState(30)
  const [d, setD] = useState(null)
  const [busy, setBusy] = useState(false)

  const run = async (refresh) => {
    setBusy(true)
    try { setD(await api.questionAnalysis(days, refresh ? 1 : 0)) }
    catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  const copy = async (text, label) => {
    try { await navigator.clipboard.writeText(text); t.ok(`คัดลอก${label}แล้ว`) }
    catch { t.err('เบราว์เซอร์ไม่อนุญาตให้คัดลอก') }
  }

  const table = () => [
    ['หัวข้อ', 'ครั้ง', 'คน', 'แนวทาง', 'คำสำคัญ', 'ตัวอย่างคำถาม', 'ร่างคำตอบ'],
    ...d.themes.map((th) => [th.title, th.count, th.people, ACTION[th.action]?.[0] || th.action,
      th.keywords.join(', '), th.examples.join(' | '), th.draft]),
  ].map((r) => r.map(cell).join('\t')).join('\n')

  return (
    <section className="card">
      <div className="row spread" style={{ alignItems: 'center' }}>
        <h3>📊 วิเคราะห์คำถามทั้งหมด</h3>
        <div className="row" style={{ gap: 8 }}>
          <select value={days} onChange={(e) => { setDays(Number(e.target.value)); setD(null) }} disabled={busy}>
            <option value={7}>7 วัน</option>
            <option value={30}>30 วัน</option>
            <option value={90}>90 วัน</option>
          </select>
          <button className="sm primary" disabled={busy} onClick={() => run(false)}>
            {busy && <InlineSpinner />}{busy ? 'กำลังวิเคราะห์… (อาจใช้เวลาเกือบ 1 นาที)' : 'วิเคราะห์คำถามทั้งหมด'}
          </button>
          {d && <button className="sm" disabled={busy} onClick={() => run(true)}>วิเคราะห์ใหม่</button>}
        </div>
      </div>
      <p className="muted sm">รวมคำถามที่ลูกค้าพิมพ์เข้ามาในเรื่องเดียวกันเป็นกลุ่ม พร้อมแนวทางตอบ (ตัดข้อความที่มีข้อมูลส่วนตัวออกก่อนส่งให้ AI)</p>

      {d && (
        <>
          <p className="sm">
            ข้อความเข้า {n(d.total_messages)} · เป็นคำถาม <b>{n(d.total_questions)}</b> ครั้ง ({n(d.unique_questions)} แบบ) ·
            ตัดออกเพราะอาจมีข้อมูลส่วนตัว {n(d.skipped_pii)}
            {d.covered_questions < d.total_questions && ` · จัดกลุ่มจากคำถามที่ถี่สุด ครอบคลุม ${n(d.covered_questions)} ครั้ง`}
            {d.cached && ' · (ผลที่เก็บไว้ ไม่เกิน 6 ชม.)'}
          </p>
          {d.method === 'keyword' && d.themes.length > 0 && (
            <p className="err sm">AI จัดกลุ่มไม่สำเร็จ — แสดงผลแบบจัดตามคำสำคัญ (หยาบกว่า ไม่มีร่างคำตอบ) กด “วิเคราะห์ใหม่” เพื่อลองอีกครั้ง</p>
          )}
          {!d.themes.length ? <p className="muted sm">ไม่พบคำถามในช่วงนี้</p> : (
            <button className="xs" onClick={() => copy(table(), 'ตารางสรุป')}>📋 คัดลอกตารางสรุป (วางลง Excel/Sheets)</button>
          )}
          {d.themes.map((th, i) => (
            <div key={i} style={{ borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 10 }}>
              <div className="row spread">
                <b>{i + 1}. {th.title}</b>
                <span className="muted sm">{n(th.count)} ครั้ง · {n(th.people)} คน · {n(th.variants)} แบบ</span>
              </div>
              <div className="sm"><span className="chip ok" title={ACTION[th.action]?.[1]}>{ACTION[th.action]?.[0] || th.action}</span></div>
              <ul className="muted sm" style={{ margin: '4px 0' }}>{th.examples.map((e, j) => <li key={j}>{e}</li>)}</ul>
              {th.keywords.length > 0 && (
                <div className="sm">คำสำคัญ: {th.keywords.join(', ')}{' '}
                  <button className="xs" onClick={() => copy(th.keywords.join(','), 'คำสำคัญ')}>คัดลอก</button>
                </div>
              )}
              {th.draft && (
                <div className="sm" style={{ whiteSpace: 'pre-wrap', marginTop: 4 }}>
                  ร่างคำตอบ (ตรวจและเติมข้อมูลในวงเล็บก่อนใช้): {th.draft}{' '}
                  <button className="xs" onClick={() => copy(th.draft, 'ร่างคำตอบ')}>คัดลอก</button>
                </div>
              )}
              {onArticle && th.action === 'ai' && (
                <button className="xs primary" style={{ marginTop: 4 }} onClick={() => onArticle(th.examples[0])}>สร้างบทความ</button>
              )}
            </div>
          ))}
        </>
      )}
    </section>
  )
}
