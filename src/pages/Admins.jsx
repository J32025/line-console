import { useEffect, useState } from 'react'
import { api } from '../lib/api.js'
import { SkeletonRows, InlineSpinner, useToast } from '../lib/ui.jsx'

export default function Admins({ me }) {
  const t = useToast()
  const [rows, setRows] = useState(null)
  const [uid, setUid] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('admin')

  const load = () => api.admins().then((d) => setRows(d.admins)).catch((e) => t.err(e.message))
  useEffect(() => { load() }, [])

  const add = async () => {
    if (!uid.startsWith('U')) return t.err('userId ต้องขึ้นต้น U')
    try {
      await api.addAdmin({ lineUserId: uid.trim(), name, role })
      t.ok('เพิ่มแล้ว'); setUid(''); setName(''); load()
    } catch (e) { t.err(e.message) }
  }

  if (!rows) return <SkeletonRows rows={5} cols={4} />
  const canEdit = ['owner', 'admin'].includes(me.role)

  return (
    <div>
      <h1>ผู้ดูแล</h1>
      <section className="card">
        <table>
          <thead><tr><th>userId</th><th>ชื่อ</th><th>role</th><th>เพิ่มเมื่อ</th><th></th></tr></thead>
          <tbody>
            {rows.map((a) => (
              <tr key={a.line_user_id}>
                <td className="mono xs">{a.line_user_id}</td>
                <td>{a.name}</td>
                <td><span className="chip">{a.role}</span></td>
                <td className="muted xs">{new Date(a.added_at).toLocaleDateString('th-TH')}</td>
                <td>
                  {me.role === 'owner' && a.line_user_id !== me.userId && (
                    <button className="xs danger" onClick={() => confirm('ลบผู้ดูแลนี้?') && api.delAdmin(a.line_user_id).then(() => { t.ok('ลบแล้ว'); load() })}>ลบ</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {canEdit && (
        <section className="card">
          <h3>เพิ่มผู้ดูแล</h3>
          <div className="row wrap">
            <input placeholder="LINE userId (U...)" value={uid} onChange={(e) => setUid(e.target.value)} />
            <input placeholder="ชื่อ" value={name} onChange={(e) => setName(e.target.value)} />
            <select value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="admin">admin</option>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
            </select>
            <button className="primary" onClick={add}>เพิ่ม</button>
          </div>
        </section>
      )}
    </div>
  )
}
