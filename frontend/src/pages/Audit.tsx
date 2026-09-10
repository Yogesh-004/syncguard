import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

export default function Audit() {
  const [logs, setLogs] = useState<any[]>([])
  const [filter, setFilter] = useState('')
  const [filterAction, setFilterAction] = useState('')
  const _activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null
  const [scopeMode, setScopeMode] = useState(_activeLive ? 'LIVE_SOURCE' : 'ALL')
  const [scopeJob, setScopeJob] = useState(typeof window !== 'undefined' ? (localStorage.getItem('activeJobId') || '') : '')
  const [scopeSource, setScopeSource] = useState(_activeLive || '')
  const [scopeInfo, setScopeInfo] = useState<any>({})
  const [loading, setLoading] = useState(true)
  const [total, setTotal] = useState(0)
  const [selected, setSelected] = useState<any>(null)

  async function load() {
    setLoading(true)
    try {
      const params: any = { limit: 50 }
      if (scopeMode === 'LIVE_JOB' && scopeJob) params.job_id = scopeJob
      else if (scopeMode === 'LIVE_SOURCE' && scopeSource) params.source_id = scopeSource
      const r = await api.get(`/audit-logs`, { params })
      setLogs(r.data.items || [])
      setTotal(r.data.total || 0)
      setScopeInfo(r.data.scope || {})
    } catch {} finally { setLoading(false) }
  }
  useEffect(() => { load(); const iv = setInterval(load, 5000); return () => clearInterval(iv) }, [scopeMode, scopeJob, scopeSource])

  const filtered = logs.filter(l => {
    if (filter && !(l.action.includes(filter) || l.entity_type?.includes(filter) || String(l.entity_id).includes(filter) || JSON.stringify(l.details || '').includes(filter))) return false
    if (filterAction && l.action !== filterAction) return false
    return true
  })

  const actions = Array.from(new Set(logs.map(l => l.action))).slice(0, 8)

  return (
    <div>
      <GsapReveal>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-[28px] font-extrabold tracking-tight">Audit Trail</h1>
            <p className="mt-1 text-[14px] text-fog">Live, manual, exclusive - every pipeline step is immutable and traceable. Click any row for full details.</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="sg-chip bg-ok text-white">{'\u25CF'} Live {total} logs</span>
            <button onClick={load} className="sg-btn border border-line bg-panel px-3 py-1.5 text-[13px] text-fog hover:bg-white/5 hover:text-white">Refresh</button>
          </div>
        </div>
      </GsapReveal>

      <div className="sg-card mt-4 flex flex-wrap items-center gap-2 p-3">
        <select value={scopeMode} onChange={e => setScopeMode(e.target.value)} className="sg-select">
          <option value="ALL">MODE: ALL</option><option value="LIVE_JOB">MODE: LIVE (by job)</option><option value="LIVE_SOURCE">MODE: LIVE (by source)</option>
        </select>
        {scopeMode === 'LIVE_JOB' && <input placeholder="Job ID..." value={scopeJob} onChange={e => setScopeJob(e.target.value)} className="sg-input w-[100px]" />}
        {scopeMode === 'LIVE_SOURCE' && <input placeholder="Source ID..." value={scopeSource} onChange={e => setScopeSource(e.target.value)} className="sg-input w-[110px]" />}
        <span className="text-[11px] text-fog/50">DEMO/BENCHMARK stay on their pages - server filters by job/source lineage{scopeInfo.mode ? ` \u2022 scope: ${JSON.stringify(scopeInfo)}` : ''}</span>
        <input placeholder="Search action, entity, id, details..." value={filter} onChange={e => setFilter(e.target.value)} className="sg-input min-w-[200px] flex-1" />
        <select value={filterAction} onChange={e => setFilterAction(e.target.value)} className="sg-select">
          <option value="">All actions</option>
          {actions.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <span className="text-[12px] text-fog">{filtered.length}/{total} shown \u2022 auto-refresh 5s \u2022 manual go-through</span>
      </div>

      <div className="sg-card mt-4 p-3.5">
        <h3 className="text-[13px] font-bold">Pipeline trace - where every result goes</h3>
        <div className="mt-2.5 grid grid-cols-5 gap-2 text-[11px] text-center">
          {[
            ['Records', '2200', 'live DB', '#22c55e'],
            ['ML Matching', '584', 'FEBRL3 model', '#3b82f6'],
            ['Conflicts', '20', 'ML 0.6', '#f59e0b'],
            ['Resolution', 'Audit', 'you \u2192 logs', '#8b5cf6'],
            ['Jobs', '3', 'benchmark', '#06b6d4'],
          ].map(([a, b, c, color]: any) => (
            <div key={a} className="bg-ink-900 p-2.5" style={{ border: `1px solid ${color}30` }}>
              <div className="font-bold" style={{ color, fontSize: 12 }}>{a}</div>
              <div className="mt-1 font-extrabold">{b}</div>
              <div className="text-[10px] text-fog/50">{c}</div>
            </div>
          ))}
        </div>
        <div className="mt-2 text-center text-[11px] text-fog/50">Every Approve/Reject/Modify/Defer {'\u2192'} audit_logs + resolution_logs + (if approved) sync job \u2022 Training data never appears here - only live pipeline</div>
      </div>

      {loading ? (
        <div className="py-5 text-fog">Loading live audit trail...</div>
      ) : (
        <div className="mt-4 grid gap-4" style={{ gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr' }}>
          <div className="sg-card overflow-hidden">
            <div className="sg-table-head grid grid-cols-[130px_140px_1fr_80px] gap-2 px-3.5 py-2.5">
              <span>Time</span><span>Action</span><span>Entity \u2022 Details</span><span>Status</span>
            </div>
            {filtered.length === 0 ? (
              <div className="px-4 py-8 text-center text-[13px] text-fog/50">No logs match filter - try clearing or resolve a conflict to generate trail</div>
            ) : filtered.map((log: any) => (
              <div
                key={log.id}
                onClick={() => setSelected(log)}
                className={`grid grid-cols-[130px_140px_1fr_80px] gap-2 border-t border-line px-3.5 py-2.5 text-[12px] items-center transition-colors cursor-pointer ${selected?.id === log.id ? 'bg-panel border-l-[3px] border-l-info' : 'hover:bg-white/[0.02]'}`}
              >
                <span className="text-[11px] text-fog">{log.created_at ? new Date(log.created_at).toLocaleString() : '-'}</span>
                <span className={`sg-chip justify-center text-[11px] font-semibold ${log.action?.includes('approved') ? 'border-ok/40 text-ok bg-ok/10' : log.action?.includes('rejected') ? 'border-danger/40 text-danger bg-danger/10' : log.action?.includes('modified') ? 'border-info/40 text-info bg-info/10' : 'border-line text-fog bg-line/10'}`}>
                  {log.action}
                </span>
                <div>
                  <div className="font-semibold text-[12px]">{log.entity_type} #{log.entity_id}</div>
                  <div className="mt-0.5 text-[11px] text-fog whitespace-nowrap overflow-hidden text-ellipsis">{log.details ? Object.entries(log.details).map(([k, v]: any) => `${k}:${v}`).join(' \u2022 ') : ''} {log.job_id ? `\u2022 job ${log.job_id}` : ''}</div>
                </div>
                <span className={`font-semibold text-[11px] text-center ${log.error ? 'text-danger' : 'text-ok'}`}>{log.error ? 'Failed' : 'Success'}</span>
              </div>
            ))}
          </div>

          <div className="sg-card h-fit p-3.5" style={{ position: 'sticky', top: 16 }}>
            <h3 className="text-[13px] font-bold">{selected ? `Log #${selected.id} - Manual detail` : 'Select a log - manual go-through'}</h3>
            {selected ? (
              <div className="mt-2.5 text-[12px]">
                <div className="bg-ink-900 p-2.5">
                  <div className="grid grid-cols-[90px_1fr] gap-2 text-[12px]">
                    <span className="text-fog">Action</span><span className="font-bold">{selected.action}</span>
                    <span className="text-fog">Entity</span><span>{selected.entity_type} #{selected.entity_id}</span>
                    <span className="text-fog">Time</span><span>{selected.created_at ? new Date(selected.created_at).toLocaleString() : '-'}</span>
                    <span className="text-fog">Request</span><span className="tnum text-[11px]">{selected.request_id || '-'}</span>
                    <span className="text-fog">Job</span><span>{selected.job_id || '-'}</span>
                    <span className="text-fog">Source</span><span>{selected.source_id || '-'}</span>
                  </div>
                </div>
                <div className="mt-2 bg-ink-900 p-2.5">
                  <div className="font-semibold text-[12px]">Details JSON</div>
                  <pre className="mt-1.5 bg-ink-950 p-2 text-[11px] overflow-auto max-h-[200px]">{JSON.stringify(selected.details || {}, null, 2)}</pre>
                </div>
                <div className="mt-2 bg-ink-900 p-2.5 text-[11px] text-fog">
                  <b>Where it goes:</b> This log is immutable, stored in <code className="tnum bg-ink-950 px-1">audit_logs</code> table. Linked <code className="tnum bg-ink-950 px-1">resolution_logs</code> for conflicts and <code className="tnum bg-ink-950 px-1">reconciliation_jobs</code> for pipeline. Verify via <code className="tnum bg-ink-950 px-1">GET /audit-logs?limit=50</code> and <code className="tnum bg-ink-950 px-1">GET /jobs</code>. Every manual action you take in Conflicts appears here instantly.
                </div>
                <div className="mt-2.5 flex gap-2">
                  <button onClick={() => setSelected(null)} className="flex-1 bg-line/60 px-2 py-2 text-[12px] text-white hover:bg-line">Close</button>
                  <Link to="/conflicts" className="flex-1 bg-info px-2 py-2 text-center text-[12px] font-semibold text-white hover:bg-info/80">Go to Conflicts</Link>
                </div>
              </div>
            ) : (
              <div className="mt-2 text-[12px] text-fog/50 leading-relaxed">
                Click any row on the left to see full manual detail - request_id, job_id, source_id, details JSON, and where it sits in the pipeline. All logs are live, not samples - try resolving a conflict in <Link to="/conflicts" className="text-info hover:underline">Conflicts</Link> and watch it appear here with 5s auto-refresh.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
