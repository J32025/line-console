import { useState } from 'react'
import { GALLERY, CATEGORIES } from '../lib/templateGallery.js'
import MessagePreview from './MessagePreview.jsx'

export default function TemplateGallery({ onPick, onClose }) {
  const [cat, setCat] = useState(CATEGORIES[0])
  const [q, setQ] = useState('')

  const items = GALLERY.filter((g) => {
    if (q) return (g.name + g.desc + g.cat).toLowerCase().includes(q.toLowerCase())
    return g.cat === cat
  })

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 860 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread">
          <h3>คลังเทมเพลต ({GALLERY.length})</h3>
          <button className="xs" onClick={onClose}>✕</button>
        </div>

        <input placeholder="ค้นหาเทมเพลต…" value={q} onChange={(e) => setQ(e.target.value)} style={{ width: '100%', margin: '8px 0' }} />

        {!q && (
          <div className="tg-tabs">
            {CATEGORIES.map((c) => (
              <button key={c} className={c === cat ? 'sm primary' : 'sm'} onClick={() => setCat(c)}>{c}</button>
            ))}
          </div>
        )}

        <div className="tg-grid">
          {items.map((g, i) => {
            const msgs = g.build()
            return (
              <div key={i} className="tg-card">
                <div className="tg-card-head">
                  <div>
                    <b className="sm">{g.name}</b>
                    <div className="muted xs">{g.desc} · {msgs.length} ข้อความ</div>
                  </div>
                  <button className="xs primary" onClick={() => { onPick(msgs); onClose() }}>ใช้</button>
                </div>
                <div className="tg-preview">
                  {msgs.map((m, j) => <MessagePreview key={j} msg={m} />)}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
