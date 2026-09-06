// แก้ไข quick reply ของ 1 ข้อความ (ปุ่มลอยเหนือแป้นพิมพ์ LINE)

const ACTION_TYPES = [
  ['message', 'ส่งข้อความ'],
  ['uri', 'เปิดลิงก์'],
  ['postback', 'postback'],
  ['camera', 'เปิดกล้อง'],
  ['cameraRoll', 'เลือกรูป'],
  ['location', 'ส่งตำแหน่ง'],
  ['datetimepicker', 'เลือกวันเวลา'],
]

function blankItem() {
  return { type: 'action', action: { type: 'message', label: '', text: '' } }
}

export default function QuickReplyEditor({ value, onChange }) {
  const items = value?.items || []

  const setItems = (next) => onChange(next.length ? { items: next } : undefined)
  const upd = (i, patch) => setItems(items.map((it, j) => (j === i ? { ...it, action: { ...it.action, ...patch } } : it)))

  return (
    <div className="qr-editor">
      <div className="row spread">
        <span className="xs muted">Quick Reply ({items.length}/13)</span>
        {items.length < 13 && <button className="xs" onClick={() => setItems([...items, blankItem()])}>+ ปุ่ม</button>}
      </div>
      {items.map((it, i) => {
        const a = it.action
        return (
          <div key={i} className="row wrap qr-row">
            <select value={a.type} onChange={(e) => upd(i, { type: e.target.value })}>
              {ACTION_TYPES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
            <input placeholder="label (บนปุ่ม)" value={a.label || ''} onChange={(e) => upd(i, { label: e.target.value })} style={{ width: 110 }} />
            {a.type === 'message' && <input placeholder="ข้อความที่ส่ง" value={a.text || ''} onChange={(e) => upd(i, { text: e.target.value })} />}
            {a.type === 'uri' && <input placeholder="https://" value={a.uri || ''} onChange={(e) => upd(i, { uri: e.target.value })} />}
            {a.type === 'postback' && <input placeholder="data" value={a.data || ''} onChange={(e) => upd(i, { data: e.target.value })} />}
            {a.type === 'datetimepicker' && <input placeholder="data" value={a.data || ''} onChange={(e) => upd(i, { data: e.target.value, mode: 'datetime' })} />}
            <button className="xs" onClick={() => setItems(items.filter((_, j) => j !== i))}>✕</button>
          </div>
        )
      })}
    </div>
  )
}
