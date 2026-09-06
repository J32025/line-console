import { useState } from 'react'
import { blank, TYPE_LABELS, STICKERS, detectKind } from '../lib/messageTypes.js'

const TYPES = ['text', 'sticker', 'image', 'video', 'audio', 'location', 'buttons', 'confirm', 'carousel', 'flex', 'raw']

export default function MessageEditor({ msg, onChange, onRemove, index }) {
  const kind = detectKind(msg)
  const [raw, setRaw] = useState(kind === 'raw' || kind === 'flex')
  const [rawText, setRawText] = useState(JSON.stringify(msg, null, 2))

  const set = (patch) => onChange({ ...msg, ...patch })
  const setTpl = (patch) => onChange({ ...msg, template: { ...msg.template, ...patch } })

  const changeType = (newKind) => {
    if (newKind === 'raw') { setRaw(true); onChange(blank('text')); setRawText(JSON.stringify(blank('text'), null, 2)); return }
    setRaw(newKind === 'flex')
    const b = blank(newKind)
    onChange(b)
    setRawText(JSON.stringify(b, null, 2))
  }

  const applyRaw = (txt) => {
    setRawText(txt)
    try { onChange(JSON.parse(txt)) } catch { /* ยังพิมพ์ไม่เสร็จ */ }
  }

  return (
    <div className="msg-editor">
      <div className="row spread">
        <div className="row">
          <span className="chip">{index + 1}</span>
          <select value={raw && kind !== 'flex' ? 'raw' : kind}
                  onChange={(e) => changeType(e.target.value)}>
            {TYPES.map((t) => <option key={t} value={t}>{TYPE_LABELS[t]}</option>)}
          </select>
        </div>
        <button className="xs danger" onClick={onRemove}>ลบ</button>
      </div>

      {/* ---- raw / flex JSON ---- */}
      {(raw || kind === 'flex') && (
        <textarea rows={10} value={rawText} onChange={(e) => applyRaw(e.target.value)} spellCheck={false} />
      )}

      {/* ---- structured forms ---- */}
      {!raw && kind === 'text' && (
        <textarea rows={3} placeholder="พิมพ์ข้อความ (สูงสุด 5000 ตัวอักษร)"
                  value={msg.text} onChange={(e) => set({ text: e.target.value })} />
      )}

      {!raw && kind === 'sticker' && (
        <div className="row wrap">
          {STICKERS.map((s) => (
            <button key={s.stickerId}
                    className={msg.stickerId === s.stickerId ? 'sm primary' : 'sm'}
                    onClick={() => set({ packageId: s.packageId, stickerId: s.stickerId })}>
              {s.label}
            </button>
          ))}
          <input style={{ width: 90 }} placeholder="packageId" value={msg.packageId}
                 onChange={(e) => set({ packageId: e.target.value })} />
          <input style={{ width: 90 }} placeholder="stickerId" value={msg.stickerId}
                 onChange={(e) => set({ stickerId: e.target.value })} />
        </div>
      )}

      {!raw && (kind === 'image' || kind === 'video') && (
        <>
          <input placeholder="originalContentUrl (https, ≤ ~10-200MB)" value={msg.originalContentUrl}
                 onChange={(e) => set({ originalContentUrl: e.target.value })} />
          <input placeholder="previewImageUrl (รูปตัวอย่าง https)" value={msg.previewImageUrl}
                 onChange={(e) => set({ previewImageUrl: e.target.value })} />
        </>
      )}

      {!raw && kind === 'audio' && (
        <>
          <input placeholder="originalContentUrl (.m4a https)" value={msg.originalContentUrl}
                 onChange={(e) => set({ originalContentUrl: e.target.value })} />
          <input type="number" placeholder="duration (ms)" value={msg.duration}
                 onChange={(e) => set({ duration: +e.target.value })} />
        </>
      )}

      {!raw && kind === 'location' && (
        <div className="grid" style={{ gridTemplateColumns: '1fr 1fr' }}>
          <input placeholder="ชื่อสถานที่" value={msg.title} onChange={(e) => set({ title: e.target.value })} />
          <input placeholder="ที่อยู่" value={msg.address} onChange={(e) => set({ address: e.target.value })} />
          <input type="number" step="any" placeholder="latitude" value={msg.latitude}
                 onChange={(e) => set({ latitude: +e.target.value })} />
          <input type="number" step="any" placeholder="longitude" value={msg.longitude}
                 onChange={(e) => set({ longitude: +e.target.value })} />
        </div>
      )}

      {!raw && (kind === 'buttons' || kind === 'confirm' || kind === 'carousel') && (
        <>
          <input placeholder="altText (ข้อความสำรองบนแจ้งเตือน)" value={msg.altText}
                 onChange={(e) => set({ altText: e.target.value })} />
          {kind === 'buttons' && (
            <>
              <input placeholder="thumbnailImageUrl (https, ไม่บังคับ)" value={msg.template.thumbnailImageUrl}
                     onChange={(e) => setTpl({ thumbnailImageUrl: e.target.value })} />
              <input placeholder="title" value={msg.template.title}
                     onChange={(e) => setTpl({ title: e.target.value })} />
              <input placeholder="text" value={msg.template.text}
                     onChange={(e) => setTpl({ text: e.target.value })} />
              <ActionsEditor actions={msg.template.actions} max={4}
                             onChange={(actions) => setTpl({ actions })} />
            </>
          )}
          {kind === 'confirm' && (
            <>
              <input placeholder="text" value={msg.template.text}
                     onChange={(e) => setTpl({ text: e.target.value })} />
              <ActionsEditor actions={msg.template.actions} min={2} max={2}
                             onChange={(actions) => setTpl({ actions })} />
            </>
          )}
          {kind === 'carousel' && (
            <CarouselEditor columns={msg.template.columns}
                            onChange={(columns) => setTpl({ columns })} />
          )}
        </>
      )}
    </div>
  )
}

function ActionsEditor({ actions, onChange, min = 1, max = 4 }) {
  const upd = (i, patch) => onChange(actions.map((a, j) => (j === i ? { ...a, ...patch } : a)))
  return (
    <div className="actions-editor">
      {actions.map((a, i) => (
        <div key={i} className="row wrap">
          <select value={a.type} onChange={(e) => upd(i, { type: e.target.value })}>
            <option value="uri">uri</option>
            <option value="message">message</option>
            <option value="postback">postback</option>
          </select>
          <input placeholder="label" value={a.label || ''} onChange={(e) => upd(i, { label: e.target.value })} />
          {a.type === 'uri' && <input placeholder="uri" value={a.uri || ''} onChange={(e) => upd(i, { uri: e.target.value })} />}
          {a.type === 'message' && <input placeholder="text" value={a.text || ''} onChange={(e) => upd(i, { text: e.target.value })} />}
          {a.type === 'postback' && <input placeholder="data" value={a.data || ''} onChange={(e) => upd(i, { data: e.target.value })} />}
          {actions.length > min && <button className="xs" onClick={() => onChange(actions.filter((_, j) => j !== i))}>✕</button>}
        </div>
      ))}
      {actions.length < max && (
        <button className="xs" onClick={() => onChange([...actions, { type: 'uri', label: '', uri: '' }])}>+ ปุ่ม</button>
      )}
    </div>
  )
}

function CarouselEditor({ columns, onChange }) {
  const upd = (i, patch) => onChange(columns.map((c, j) => (j === i ? { ...c, ...patch } : c)))
  return (
    <div>
      {columns.map((c, i) => (
        <div key={i} className="card" style={{ padding: 10, margin: '6px 0' }}>
          <div className="row spread"><b className="sm">การ์ด {i + 1}</b>
            {columns.length > 1 && <button className="xs" onClick={() => onChange(columns.filter((_, j) => j !== i))}>ลบการ์ด</button>}
          </div>
          <input placeholder="thumbnailImageUrl" value={c.thumbnailImageUrl || ''} onChange={(e) => upd(i, { thumbnailImageUrl: e.target.value })} />
          <input placeholder="title" value={c.title || ''} onChange={(e) => upd(i, { title: e.target.value })} />
          <input placeholder="text" value={c.text || ''} onChange={(e) => upd(i, { text: e.target.value })} />
          <ActionsEditor actions={c.actions} max={3} onChange={(actions) => upd(i, { actions })} />
        </div>
      ))}
      {columns.length < 10 && (
        <button className="xs" onClick={() => onChange([...columns, { thumbnailImageUrl: '', title: `การ์ด ${columns.length + 1}`, text: '', actions: [{ type: 'uri', label: 'ดู', uri: 'https://example.com' }] }])}>+ การ์ด</button>
      )}
    </div>
  )
}
