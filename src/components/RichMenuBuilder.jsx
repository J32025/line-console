import { useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { useToast, InlineSpinner } from '../lib/ui.jsx'

const SIZES = {
  full: { width: 2500, height: 1686, label: 'เต็ม 2500×1686' },
  half: { width: 2500, height: 843, label: 'ครึ่ง 2500×843' },
}
const DISPLAY_W = 500

const blankArea = () => ({
  bounds: { x: 0, y: 0, width: 0, height: 0 },
  action: { type: 'uri', label: '', uri: 'https://' },
})

export default function RichMenuBuilder({ onDone, onCancel }) {
  const t = useToast()
  const [size, setSize] = useState('full')
  const [name, setName] = useState('เมนูใหม่')
  const [chatBar, setChatBar] = useState('เมนู')
  const [selected, setSelected] = useState(true)
  const [setDefault, setSetDefault] = useState(false)
  const [img, setImg] = useState(null) // dataURL
  const [imgDim, setImgDim] = useState(null)
  const [areas, setAreas] = useState([])
  const [busy, setBusy] = useState(false)
  const boxRef = useRef(null)
  const drag = useRef(null)

  const dim = SIZES[size]
  const scale = DISPLAY_W / dim.width
  const dispH = dim.height * scale

  const pickImage = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const r = new FileReader()
    r.onload = () => {
      const im = new Image()
      im.onload = () => {
        setImgDim({ w: im.width, h: im.height })
        if (im.width !== dim.width || im.height !== dim.height)
          t.info(`รูป ${im.width}×${im.height} — LINE ต้องการ ${dim.width}×${dim.height} พอดี (จะ resize ไม่ได้ ต้องอัปรูปให้ตรง)`, 'error')
      }
      im.src = r.result
      setImg(r.result)
    }
    r.readAsDataURL(f)
  }

  // --- drag เพื่อวาดพื้นที่ ---
  const toImgCoords = (clientX, clientY) => {
    const rect = boxRef.current.getBoundingClientRect()
    return {
      x: Math.round((clientX - rect.left) / scale),
      y: Math.round((clientY - rect.top) / scale),
    }
  }
  const onDown = (e) => {
    if (!img) return
    const p = toImgCoords(e.clientX, e.clientY)
    drag.current = { start: p }
  }
  const onMove = (e) => {
    if (!drag.current) return
    const p = toImgCoords(e.clientX, e.clientY)
    drag.current.cur = p
    setAreas((a) => [...a.filter((x) => !x._draft), draftArea()])
  }
  const draftArea = () => {
    const { start, cur } = drag.current
    if (!cur) return { ...blankArea(), _draft: true }
    return {
      ...blankArea(), _draft: true,
      bounds: {
        x: Math.min(start.x, cur.x), y: Math.min(start.y, cur.y),
        width: Math.abs(cur.x - start.x), height: Math.abs(cur.y - start.y),
      },
    }
  }
  const onUp = () => {
    if (!drag.current?.cur) { drag.current = null; return }
    const d = draftArea()
    drag.current = null
    if (d.bounds.width < 20 || d.bounds.height < 20) {
      setAreas((a) => a.filter((x) => !x._draft))
      return
    }
    delete d._draft
    setAreas((a) => [...a.filter((x) => !x._draft), d])
  }

  const updArea = (i, patch) => setAreas((a) => a.map((x, j) => (j === i ? { ...x, ...patch } : x)))
  const updAction = (i, patch) => setAreas((a) => a.map((x, j) => (j === i ? { ...x, action: { ...x.action, ...patch } } : x)))

  const save = async () => {
    if (!img) return t.err('อัปโหลดรูปก่อน')
    if (imgDim && (imgDim.w !== dim.width || imgDim.h !== dim.height))
      return t.err(`รูปต้องเป็น ${dim.width}×${dim.height} พอดี`)
    const real = areas.filter((a) => !a._draft && a.bounds.width > 0)
    if (!real.length) return t.err('วาดพื้นที่กดอย่างน้อย 1 จุด')
    setBusy(true)
    try {
      const menu = await api.createMenu({
        richMenu: {
          size: { width: dim.width, height: dim.height },
          selected, name: name.slice(0, 300), chatBarText: chatBar.slice(0, 14),
          areas: real.map((a) => ({ bounds: a.bounds, action: cleanAction(a.action) })),
        },
        imageBase64: img,
        setDefault,
      })
      t.ok('สร้างเมนูแล้ว: ' + menu.richMenuId)
      onDone?.()
    } catch (e) { t.err(e.message) } finally { setBusy(false) }
  }

  return (
    <div className="modal-bg" onClick={onCancel}>
      <div className="modal" style={{ maxWidth: 900 }} onClick={(e) => e.stopPropagation()}>
        <div className="row spread">
          <h3>สร้าง Rich Menu</h3>
          <button className="xs" onClick={onCancel}>✕</button>
        </div>

        <div className="rmb-layout">
          <div>
            <div className="row wrap">
              <select value={size} onChange={(e) => { setSize(e.target.value); setAreas([]) }}>
                {Object.entries(SIZES).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
              </select>
              <input type="file" accept="image/png,image/jpeg" onChange={pickImage} />
            </div>

            <div
              ref={boxRef}
              className="rmb-canvas"
              style={{ width: DISPLAY_W, height: dispH, backgroundImage: img ? `url(${img})` : 'none' }}
              onMouseDown={onDown} onMouseMove={onMove} onMouseUp={onUp} onMouseLeave={onUp}
            >
              {!img && <div className="rmb-hint">อัปโหลดรูป แล้วลากเมาส์เพื่อวาดพื้นที่กด</div>}
              {areas.map((a, i) => (
                <div key={i} className={`rmb-area ${a._draft ? 'draft' : ''}`} style={{
                  left: a.bounds.x * scale, top: a.bounds.y * scale,
                  width: a.bounds.width * scale, height: a.bounds.height * scale,
                }}>
                  <span>{i + 1}</span>
                </div>
              ))}
            </div>
            <p className="muted xs">ลากเมาส์บนรูปเพื่อสร้างพื้นที่กด · รูปต้อง {dim.width}×{dim.height}px, ≤1MB</p>
          </div>

          <div className="rmb-side">
            <label className="xs">ชื่อเมนู (ภายใน)</label>
            <input value={name} onChange={(e) => setName(e.target.value)} />
            <label className="xs">ข้อความบนแถบ (≤14 ตัว)</label>
            <input value={chatBar} maxLength={14} onChange={(e) => setChatBar(e.target.value)} />
            <label><input type="checkbox" checked={selected} onChange={(e) => setSelected(e.target.checked)} /> เปิดเมนูค้างไว้</label>
            <label><input type="checkbox" checked={setDefault} onChange={(e) => setSetDefault(e.target.checked)} /> ตั้งเป็น default</label>

            <h4 className="sm">พื้นที่กด ({areas.filter((a) => !a._draft).length})</h4>
            <div className="rmb-areas">
              {areas.filter((a) => !a._draft).map((a, i) => (
                <div key={i} className="rmb-areabox">
                  <div className="row spread">
                    <b className="xs">#{i + 1} ({a.bounds.width}×{a.bounds.height})</b>
                    <button className="xs" onClick={() => setAreas((x) => x.filter((_, j) => j !== i))}>ลบ</button>
                  </div>
                  <select value={a.action.type} onChange={(e) => updAction(i, { type: e.target.value })}>
                    <option value="uri">เปิดลิงก์</option>
                    <option value="message">ส่งข้อความ</option>
                    <option value="postback">postback</option>
                    <option value="richmenuswitch">สลับเมนู</option>
                  </select>
                  {a.action.type === 'uri' && <input placeholder="https://" value={a.action.uri || ''} onChange={(e) => updAction(i, { uri: e.target.value })} />}
                  {a.action.type === 'message' && <input placeholder="ข้อความ" value={a.action.text || ''} onChange={(e) => updAction(i, { text: e.target.value })} />}
                  {a.action.type === 'postback' && <input placeholder="data" value={a.action.data || ''} onChange={(e) => updAction(i, { data: e.target.value })} />}
                  {a.action.type === 'richmenuswitch' && <input placeholder="richMenuAliasId" value={a.action.richMenuAliasId || ''} onChange={(e) => updAction(i, { richMenuAliasId: e.target.value })} />}
                </div>
              ))}
            </div>

            <button className="primary" onClick={save} disabled={busy}>{busy && <InlineSpinner />}สร้างเมนู</button>
          </div>
        </div>
      </div>
    </div>
  )
}

function cleanAction(a) {
  const o = { type: a.type }
  if (a.label) o.label = a.label
  if (a.type === 'uri') o.uri = a.uri
  if (a.type === 'message') o.text = a.text
  if (a.type === 'postback') { o.data = a.data; if (a.displayText) o.displayText = a.displayText }
  if (a.type === 'richmenuswitch') { o.richMenuAliasId = a.richMenuAliasId; o.data = a.data || 'switch' }
  return o
}
