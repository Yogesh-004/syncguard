import { useEffect, useState } from 'react'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'
import ResolutionPanel from '../components/ResolutionPanel'
import Timeline from '../components/Timeline'

function Ticks({ ev }: any) {
  if (!ev) return null
  const items: any[] = []
  ;['email', 'phone', 'name'].forEach(k => {
    const v = ev[k]
    if (v?.match) items.push({ label: `${k} ${(v.score * 100).toFixed(0)}%`, ok: true })
    else if (v) items.push({ label: k, ok: false, warn: v.reason === 'missing_field' })
  })
  if (ev.ml_prob !== undefined) items.push({ label: `ML ${(ev.ml_prob * 100).toFixed(0)}%`, ok: ev.ml_prob >= 0.6 })
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span key={i} className={`sg-chip ${it.ok ? 'border-ok/40 text-ok bg-ok/10' : it.warn ? 'border-warn/40 text-warn bg-warn/10' : 'border-danger/40 text-danger bg-danger/10'}`}>
          {it.ok ? '\u2713' : it.warn ? '\u26A0' : '\u2717'} {it.label}
        </span>
      ))}
    </div>
  )
}

function Presence({ presence }: any) {
  if (!presence || (!presence.record_a && !presence.record_b)) return null
  const rows = [['A', presence.record_a], ['B', presence.record_b]].filter(([, o]) => o)
  if (!rows.length) return null
  return (
    <div className="mt-2 bg-ink-900 p-2.5">
      <div className="font-semibold text-[12px]">Presence - scope-relative observation (informational only)</div>
      {rows.map(([side, o]: any) => (
        <div key={side} className="mt-1.5 text-[12px]">
          <div>Record {side} (#{o.record_ref}): <b>{o.record_presence}</b> <span className="text-fog/50">({o.basis})</span></div>
          <div className="mt-0.5 text-fog">{o.explanation}</div>
          <div className="mt-0.5 text-[11px] text-fog/50">Scope: {o.scope?.source_a} {'\u2194'} {o.scope?.source_b} \u2022 {o.scope?.snapshot_a} {'\u2194'} {o.scope?.snapshot_b} \u2022 completeness {o.scope?.completeness_a}/{o.scope?.completeness_b}</div>
        </div>
      ))}
    </div>
  )
}

export default function Conflicts() {
  const [data, setData] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [filterRisk, setFilterRisk] = useState('')
  const [filterStatus, setFilterStatus] = useState('pending')
  const [filterField, setFilterField] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const activeJob = typeof window !== 'undefined' ? localStorage.getItem('activeJobId') : null
  const activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null

  async function load(p = 1) {
    setLoading(true)
    try {
      const params: any = { limit: 20, page: p }
      if (activeJob) params.job_id = activeJob
      else if (activeLive) params.source_id = activeLive
      if (filterRisk) params.risk_level = filterRisk
      if (filterStatus) params.status = filterStatus
      if (filterField) params.field = filterField
      const r = await api.get('/conflicts', { params })
      let list = Array.isArray(r.data) ? r.data : r.data.items || r.data || []
      if (search) {
        const s = search.toLowerCase()
        list = list.filter((c: any) => String(c.id).includes(s) || (c.conflicting_fields || []).some((f: any) => f.field_name?.toLowerCase().includes(s)))
      }
      setData(list); setTotal(list.length)
    } catch {} finally { setLoading(false) }
  }
  useEffect(() => { load(1); setPage(1) }, [filterRisk, filterStatus, filterField])
  useEffect(() => { load(page) }, [page])

  async function openDetail(id: number) {
    try { const r = await api.get(`/conflicts/${id}`); setSelected(r.data) } catch {}
  }

  return (
    <div>
      <GsapReveal>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-[28px] font-extrabold tracking-tight">Conflicts</h1>
            <p className="mt-1 text-[14px] text-fog">
              Mode: <b className="text-ok">LIVE</b>{activeJob ? ` \u2022 Job #${activeJob}` : activeLive ? ` \u2022 Source #${activeLive}` : ''} \u2022 Field-level work queue \u2022 review only
            </p>
          </div>
          <span className="sg-chip border-ok/30 bg-ok/10 text-ok">{'\u25CF'} Production \u2022 ML</span>
        </div>
      </GsapReveal>

      <div className="mt-3 bg-ink-900 border border-line p-2.5 text-[12px] text-fog">
        Policy (backend decision engine): POSSIBLE_MATCH, any HIGH/CRITICAL risk, or missing key fields {'\u2192'} MANUAL REVIEW (avoids false merges like John Smith vs John Smyth). Only MATCH + LOW risk + exact trusted ID (or exact email+phone) with zero contradictions is SAFE TO RESOLVE.
      </div>

      <div className="sg-card mt-3 flex flex-wrap items-center gap-2 p-3">
        <input placeholder="Search id/field..." value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(1)} className="sg-input min-w-[160px]" />
        <select value={filterRisk} onChange={e => setFilterRisk(e.target.value)} className="sg-select">
          <option value="">All risks</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
        </select>
        <select value={filterStatus} onChange={e => setFilterStatus(e.target.value)} className="sg-select">
          <option value="pending">Pending</option><option value="">All status</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="deferred">Deferred</option>
        </select>
        <select value={filterField} onChange={e => setFilterField(e.target.value)} className="sg-select">
          <option value="">All fields</option><option value="email">email</option><option value="phone">phone</option><option value="name">name</option><option value="postcode">postcode</option><option value="suburb">suburb</option>
        </select>
        <span className="ml-auto text-[12px] text-fog/60">{total} shown \u2022 one row per field</span>
      </div>

      {loading ? (
        <div className="py-5 text-fog">Loading conflicts...</div>
      ) : (
        <div className="mt-4 grid gap-4" style={{ gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr' }}>
          <div className="sg-card overflow-hidden">
            <div className="sg-table-head grid grid-cols-[70px_1fr_80px_80px_80px_80px] gap-2 px-3.5 py-2.5">
              <span>ID</span><span>Entity \u2022 Field</span><span>Source{'\u2194'}Target</span><span>Risk</span><span>Conf</span><span>Status</span>
            </div>
            {data.length === 0 ? (
              <div className="px-4 py-8 text-center text-fog/50">No conflicts - run Live Analysis</div>
            ) : data.map((c: any) => {
              const f = (c.conflicting_fields || [])[0] || {}
              return (
                <div
                  key={c.id}
                  onClick={() => openDetail(c.id)}
                  className={`grid grid-cols-[70px_1fr_80px_80px_80px_80px] gap-2 border-t border-line px-3.5 py-2.5 text-[12px] transition-colors cursor-pointer items-center ${selected?.id === c.id ? 'bg-panel border-l-[3px] border-l-warn' : 'hover:bg-white/[0.02]'}`}
                >
                  <span className="font-bold">#{c.id}</span>
                  <span>#{c.record_a_id}{'\u2194'}#{c.record_b_id} \u2022 <b>{f.field_name || '-'}</b></span>
                  <span className="text-fog">{c.record_a_id}{'\u2194'}{c.record_b_id}</span>
                  <span className={`sg-chip justify-center text-[11px] font-bold uppercase ${c.risk_level === 'low' ? 'bg-ok text-white' : c.risk_level === 'medium' ? 'bg-warn text-white' : 'bg-danger text-white'}`}>
                    {c.risk_level}
                  </span>
                  <span className="tnum font-bold text-ok">{(Math.min(c.confidence, 0.999) * 100).toFixed(1)}%</span>
                  <span className="capitalize text-fog">{{ pending: 'OPEN (pending)', approved: 'RESOLVED', modified: 'RESOLVED', rejected: 'REJECTED', deferred: 'DEFERRED' }[(c.resolution_status || c.status)] || c.resolution_status || c.status}</span>
                </div>
              )
            })}
            <div className="flex items-center justify-between border-t border-line px-3 py-2">
              <button disabled={page <= 1} onClick={() => setPage(p => p - 1)} className="sg-btn border border-line px-2.5 py-1 text-[12px] text-fog hover:bg-white/5 disabled:opacity-40">Prev</button>
              <span className="text-[12px] text-fog/60">Page {page}</span>
              <button onClick={() => setPage(p => p + 1)} className="sg-btn border border-line px-2.5 py-1 text-[12px] text-fog hover:bg-white/5">Next</button>
            </div>
          </div>

          <div className="sg-card h-fit p-3.5" style={{ position: 'sticky', top: 16 }}>
            <h3 className="text-[13px] font-bold">{selected ? `CONFLICT #${selected.id}` : 'Select a conflict'}</h3>
            {selected ? (
              <div className="mt-2.5 text-[12px]">
                <div>Entity: <b>#{selected.entity?.record_a_id} {'\u2194'} #{selected.entity?.record_b_id}</b> \u2022 Field: <b className="text-warn">{(selected.field || '').toUpperCase()}</b></div>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <div className="bg-ink-900 p-2.5">
                    <div className="text-[11px] font-bold text-info">SOURCE A \u2022 #{selected.source_record?.id}</div>
                    <div className="mt-1 font-bold">{selected.source_record?.data?.name || selected.source_record?.data?.title || ' - '}</div>
                    <div className="text-fog">{selected.field_values?.a ?? JSON.stringify(selected.source_record?.data || {}).slice(0, 60)}</div>
                  </div>
                  <div className="bg-ink-900 p-2.5">
                    <div className="text-[11px] font-bold text-[#8b5cf6]">SOURCE B \u2022 #{selected.target_record?.id}</div>
                    <div className="mt-1 font-bold">{selected.target_record?.data?.name || selected.target_record?.data?.title || ' - '}</div>
                    <div className="text-fog">{selected.field_values?.b ?? JSON.stringify(selected.target_record?.data || {}).slice(0, 60)}</div>
                  </div>
                </div>
                <div className="mt-2 bg-ink-900 p-2.5">
                  <div>Entity match: <b className="text-ok">{(Math.min(selected.match_confidence, 0.999) * 100).toFixed(1)}%</b> \u2022 Model v{selected.model_version} \u2022 Job #{selected.job_id} ({selected.job_status})</div>
                  <Ticks ev={selected.match?.evidence || selected.evidence} />
                </div>
                <div className="mt-2 bg-ink-900 p-2.5">
                  <div className="font-semibold">Conflict - values differ after normalization</div>
                  <div className="mt-1">A: <b>{String(selected.field_values?.a ?? 'NULL')}</b> \u2022 B: <b>{String(selected.field_values?.b ?? 'NULL')}</b></div>
                  <div className="mt-1.5">Recommendation: <b>{selected.recommendation}</b> <span className="text-fog/50">({selected.evidence?.conflict_reason || ''})</span></div>
                  <div>Risk: <b className="uppercase">{selected.risk}</b> <span className="text-fog/50">({selected.evidence?.risk_reason || ''})</span> \u2022 Status: <b className="capitalize">{selected.status}</b></div>
                </div>
                <ResolutionPanel conflict={selected} onUpdate={(c: any) => { setSelected(c); load(1) }} />
                <Presence presence={selected.presence} />
                <Timeline conflictId={selected.id} />
                <button onClick={() => setSelected(null)} className="mt-2.5 w-full bg-line/60 px-2.5 py-1.5 text-[12px] text-white hover:bg-line">Close</button>
              </div>
            ) : (
              <div className="mt-2 text-[12px] text-fog/50 leading-relaxed">Click a row to review, resolve, dry-run and push. One conflict at a time.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
