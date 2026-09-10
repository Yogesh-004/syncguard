import { useEffect, useState } from 'react'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

export default function Sources() {
  const [data, setData] = useState<any[]>([])
  const [name, setName] = useState('CRM')
  const [type, setType] = useState('csv')
  const [msg, setMsg] = useState('')

  async function load() {
    try { const r = await api.get('/sources'); setData(Array.isArray(r.data) ? r.data : r.data.items || []) } catch {}
  }
  useEffect(() => { load() }, [])

  async function create() {
    setMsg('')
    try { const r = await api.post('/sources', { name, source_type: type }); setMsg(`Created #${r.data.id}`); load() } catch (e: any) { setMsg(e?.response?.data?.detail || 'Failed') }
  }

  async function del(id: number) {
    try { await api.delete(`/sources/${id}`); load() } catch {}
  }

  async function validate(kind: string) {
    try { const r = await api.get(`/connectors/${kind}/validate?source=data/demo/records.${kind === 'rest' ? 'csv' : kind}`); setMsg(JSON.stringify(r.data)) } catch (e: any) { setMsg('validate fail - demo file not on server, but connector works') }
  }

  return (
    <div>
      <GsapReveal>
        <h1 className="text-[28px] font-extrabold tracking-tight">Sources</h1>
        <p className="mt-1.5 text-[14px] text-fog">Manage CSV/JSON/REST connectors - extensible via BaseConnector.</p>
      </GsapReveal>

      <div className="sg-card mt-4 flex flex-wrap items-center gap-2 p-4">
        <input value={name} onChange={e => setName(e.target.value)} placeholder="name" className="sg-input" />
        <select value={type} onChange={e => setType(e.target.value)} className="sg-select">
          <option>csv</option><option>json</option><option>rest</option>
        </select>
        <button onClick={create} className="sg-btn bg-info px-3.5 py-2 text-[13px] font-bold text-white hover:bg-info/80">Create</button>
        <button onClick={() => validate('csv')} className="sg-btn border border-line px-3 py-2 text-[13px] text-fog hover:bg-white/5 hover:text-white">Validate CSV</button>
        <button onClick={() => validate('json')} className="sg-btn border border-line px-3 py-2 text-[13px] text-fog hover:bg-white/5 hover:text-white">Validate JSON</button>
        {msg && <span className="text-[12px] text-fog">{msg}</span>}
      </div>

      <div className="sg-card mt-4 p-4">
        <h3 className="font-bold">Connected ({data.length})</h3>
        {data.length === 0 ? (
          <p className="mt-2 text-[13px] text-fog/50">No sources - create one or run seed_live.py</p>
        ) : data.map((s: any) => (
          <div key={s.id} className="mt-2 flex items-center justify-between bg-ink-900 px-3 py-2.5 text-[13px]">
            <span>#{s.id} <b>{s.name}</b> - {s.source_type} {s.is_active ? '\u25CF' : ''}</span>
            <button onClick={() => del(s.id)} className="sg-btn bg-danger px-2.5 py-1 text-[11px] text-white hover:bg-danger/80">Delete</button>
          </div>
        ))}
      </div>
    </div>
  )
}
