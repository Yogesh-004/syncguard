import { useEffect, useState } from 'react'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

export default function Jobs() {
  const [data, setData] = useState<any>(null)
  const [filter, setFilter] = useState('')
  const [creating, setCreating] = useState(false)

  async function load() {
    try {
      const activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null
      const srcQ = activeLive ? `&source_id=${activeLive}` : ''
      const r = await api.get(`/jobs?limit=20${filter ? `&status=${filter}` : ''}${srcQ}`)
      setData(r.data)
    } catch {}
  }
  useEffect(() => { load(); const iv = setInterval(load, 3000); return () => clearInterval(iv) }, [filter])

  async function create() {
    setCreating(true)
    try { await api.post('/jobs', { job_type: 'reconciliation', source_id: '1', idempotency_key: `job-${Date.now()}` }); load() } catch {} finally { setCreating(false) }
  }

  const items = data?.items || []

  return (
    <div>
      <GsapReveal>
        <h1 className="text-[28px] font-extrabold tracking-tight">Jobs</h1>
        <p className="mt-1.5 text-[14px] text-fog">Background reconciliation/sync - 202 Accepted {'\u2192'} polling, retries 5\u00d7, idempotency UNIQUE.</p>
      </GsapReveal>

      <div className="sg-card mt-4 flex items-center gap-2 p-4">
        <select value={filter} onChange={e => setFilter(e.target.value)} className="sg-select">
          <option value="">all</option><option>queued</option><option>processing</option><option>completed</option><option>failed</option>
        </select>
        <button onClick={load} className="sg-btn border border-line px-3 py-2 text-[13px] text-fog hover:bg-white/5 hover:text-white">Refresh</button>
        <button onClick={create} disabled={creating} className="sg-btn bg-info px-3.5 py-2 text-[13px] font-bold text-white hover:bg-info/80 disabled:opacity-50">
          {creating ? 'Creating...' : 'New Job'}
        </button>
        <span className="ml-auto text-[12px] text-fog">{data ? `${data.total} total` : ''} - auto-refresh 3s</span>
      </div>

      <div className="mt-4">
        {items.length === 0 ? (
          <div className="sg-card px-6 py-6 text-center text-fog/50">No jobs - create one or POST /reconciliation</div>
        ) : items.map((j: any) => (
          <GsapReveal key={j.id} delay={0.02}>
            <div className="sg-card mb-3 p-4 transition-colors duration-300 hover:border-accent">
              <div className="flex items-center justify-between">
                <b className="text-[14px]">Job #{j.id}</b>
                <span className={`font-bold text-[13px] ${j.status === 'completed' ? 'text-ok' : j.status === 'failed' ? 'text-danger' : 'text-warn'}`}>{j.status}</span>
              </div>
              <div className="mt-1.5 text-[13px] text-fog">{j.job_type} - progress {j.progress}% - {j.created_at ? new Date(j.created_at).toLocaleString() : ''}</div>
              <div className="mt-2 h-2 bg-ink-900 overflow-hidden">
                <div className="h-full transition-all duration-500" style={{ width: `${j.progress}%`, background: j.status === 'failed' ? '#ef4444' : '#3b82f6' }} />
              </div>
            </div>
          </GsapReveal>
        ))}
      </div>
    </div>
  )
}
