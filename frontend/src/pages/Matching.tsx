import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

function Ticks({ evidence }: any) {
  const items: any[] = []
  const fs = evidence?.field_scores
  if (fs) {
    Object.entries(fs).forEach(([k, v]: any) => items.push({ label: `${k} ${(Number(v) * 100).toFixed(0)}%`, ok: Number(v) >= 0.5 }))
  } else {
    const core = ['email', 'phone', 'name']
    core.forEach(k => {
      const v = evidence?.[k]
      if (v?.match) items.push({ label: `${k} ${(v.score * 100).toFixed(0)}%`, ok: true })
      else if (v) items.push({ label: k, ok: false, warn: v.reason === 'missing_field' })
    })
  }
  if (evidence?.ml_prob !== undefined) items.push({ label: `ML ${(evidence.ml_prob * 100).toFixed(0)}%`, ok: evidence.ml_prob >= 0.6 })
  return (
    <div className="mt-1.5 flex flex-wrap gap-1.5">
      {items.map((it: any, i: number) => (
        <span key={i} className={`sg-chip ${it.ok ? 'border-ok/40 text-ok' : it.warn ? 'border-warn/40 text-warn' : 'border-danger/40 text-danger'}`}>
          {it.ok ? '\u2713' : it.warn ? '\u26A0' : '\u2717'} {it.label}
        </span>
      ))}
    </div>
  )
}

function topEvidence(ev: any) {
  if (!ev) return ''
  const fe = ev.field_evidence?.fields || []
  const pos = fe.filter((f: any) => ['EXACT_MATCH', 'STRONG_MATCH'].includes(f.status)).map((f: any) => f.field)
  const neg = fe.filter((f: any) => f.status === 'MISMATCH').map((f: any) => f.field)
  const parts: string[] = []
  if (pos.length) parts.push('\u2713 ' + pos.slice(0, 3).join(','))
  if (neg.length) parts.push('\u2717 ' + neg.slice(0, 2).join(','))
  return parts.join(' ') || ' - '
}

function whyText(ev: any) {
  if (!ev) return ''
  const parts: string[] = []
  if (ev.email?.match) parts.push('Email exact match')
  if (ev.phone?.match) parts.push('phone normalized exact')
  if (ev.name) parts.push(`name ${(ev.name.score * 100).toFixed(0)}% similarity`)
  return parts.join(' \u2022 ') || 'ML probability above threshold'
}

export default function Matching() {
  const [items, setItems] = useState<any[]>([])
  const [total, setTotal] = useState(0)
  const [counts, setCounts] = useState<any>({})
  const [thresholds, setThresholds] = useState<any>({})
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [decision, setDecision] = useState('')
  const [selected, setSelected] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const activeJob = typeof window !== 'undefined' ? localStorage.getItem('activeJobId') : null
  const activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null

  async function load(p = 1) {
    setLoading(true)
    try {
      const params: any = { limit: 20, page: p }
      if (activeJob) params.job_id = activeJob
      else if (activeLive) params.source_id = activeLive
      if (['MATCH', 'POSSIBLE_MATCH', 'NO_MATCH'].includes(decision)) params.decision = decision
      const r = await api.get('/matches', { params })
      let list = r.data.items || []
      if (decision === 'AUTO') list = list.filter((m: any) => m.auto_resolvable)
      else if (decision === 'MANUAL') list = list.filter((m: any) => !m.auto_resolvable)
      else if (decision === 'HIGH_RISK') list = list.filter((m: any) => (m.risk || m.evidence?.risk) === 'HIGH' || (m.risk || m.evidence?.risk) === 'CRITICAL')
      if (search) {
        const s = search.toLowerCase()
        list = list.filter((m: any) => String(m.record_a_id).includes(s) || String(m.record_b_id).includes(s) || String(m.id).includes(s) || JSON.stringify(m.evidence || '').toLowerCase().includes(s))
      }
      setItems(list); setTotal(r.data.total ?? list.length)
      setCounts(r.data.counts || {}); setThresholds(r.data.thresholds || {})
    } catch {} finally { setLoading(false) }
  }
  useEffect(() => { load(1); setPage(1) }, [decision])
  useEffect(() => { load(page) }, [page])

  async function openDetail(id: number) {
    try { const r = await api.get(`/matches/${id}`); setSelected(r.data) } catch {}
  }

  return (
    <div>
      <GsapReveal>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-[28px] font-extrabold tracking-tight">Matching</h1>
            <p className="mt-1 text-[14px] text-fog">
              Mode: <b className="text-ok">LIVE</b>{activeJob ? ` \u2022 Job #${activeJob}` : activeLive ? ` \u2022 Source #${activeLive}` : ''} \u2022 Model v1.0.0 \u2022 Persisted DB matches (read-only)
            </p>
          </div>
          <span className="sg-chip border-ok/30 bg-ok/10 text-ok">{'\u25CF'} Production \u2022 ML</span>
        </div>
      </GsapReveal>

      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-5">
        {[['MATCH', counts.MATCH, '#22c55e'], ['POSSIBLE', counts.POSSIBLE_MATCH, '#f59e0b'], ['NO MATCH', counts.NO_MATCH, '#64748b'], ['AUTO-RESOLVABLE', items.filter((m: any) => m.auto_resolvable).length, '#06b6d4'], ['MANUAL REVIEW', items.filter((m: any) => !m.auto_resolvable).length, '#f59e0b']].map(([label, val, color]: any) => (
          <div key={label} className="bg-ink-900 p-2.5 text-center border border-line">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-fog">{label}</div>
            <div className="tnum mt-1 text-[20px] font-extrabold" style={{ color }}>{val ?? '?'}</div>
          </div>
        ))}
      </div>

      <div className="sg-card mt-3 flex flex-wrap items-center gap-2 p-3">
        <input placeholder="Search match/record id..." value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === 'Enter' && load(1)} className="sg-input min-w-[200px]" />
        <select value={decision} onChange={e => setDecision(e.target.value)} className="sg-select">
          <option value="">ALL ({total})</option>
          <option value="MATCH">MATCH ({counts.MATCH ?? '?'})</option>
          <option value="POSSIBLE_MATCH">POSSIBLE ({counts.POSSIBLE_MATCH ?? '?'})</option>
          <option value="NO_MATCH">NO MATCH ({counts.NO_MATCH ?? '?'})</option>
          <option value="AUTO">AUTO-RESOLVABLE</option>
          <option value="MANUAL">MANUAL REVIEW</option>
          <option value="HIGH_RISK">HIGH RISK</option>
        </select>
        <button onClick={() => load(page)} disabled={loading} className="sg-btn bg-info px-3 py-1.5 text-[13px] text-white hover:bg-info/80">
          Refresh
        </button>
        <Link to="/live" className="sg-btn border border-line px-3 py-1.5 text-[13px] text-fog hover:bg-white/5 hover:text-white">
          New analysis
        </Link>
        <span className="ml-auto text-[12px] text-fog/60">
          {thresholds.MATCH !== undefined ? `MATCH \u2265 ${thresholds.MATCH} \u2022 POSSIBLE ${thresholds.POSSIBLE_MATCH}-${thresholds.MATCH} \u2022 NO MATCH < ${thresholds.POSSIBLE_MATCH} (server config)` : `${total} persisted matches`}
        </span>
      </div>

      {loading ? (
        <div className="py-5 text-fog">Loading DB matches...</div>
      ) : (
        <div className="mt-4 grid gap-4" style={{ gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr' }}>
          <div className="sg-card overflow-hidden">
            <div className="sg-table-head grid grid-cols-[70px_1fr_90px_80px_80px_70px_80px] gap-2 px-3.5 py-2.5">
              <span>Match</span><span>Entity pair</span><span>Decision</span><span>ML score</span><span>Final conf</span><span>Risk</span><span>Auto</span>
            </div>
            {items.length === 0 ? (
              <div className="px-4 py-8 text-center text-fog/50">No persisted matches - run Live Analysis first</div>
            ) : items.map((m: any) => {
              const top = topEvidence(m.evidence)
              return (
                <div
                  key={m.id}
                  onClick={() => openDetail(m.id)}
                  className={`grid grid-cols-[70px_1fr_90px_80px_80px_70px_80px] gap-2 border-t border-line px-3.5 py-2.5 text-[12px] transition-colors cursor-pointer items-center ${selected?.id === m.id ? 'bg-panel border-l-[3px] border-l-ok' : 'hover:bg-white/[0.02]'}`}
                >
                  <span className="font-bold">#{m.id}</span>
                  <span>
                    #{m.record_a_id} {'\u2194'} #{m.record_b_id} <span className="text-fog/50">\u2022 job {m.job || '-'}</span>
                    <div className="text-[11px] text-fog/50">{top}</div>
                  </span>
                  <span className={`sg-chip justify-center text-[11px] ${m.decision === 'MATCH' ? 'border-ok/40 text-ok bg-ok/10' : m.decision === 'NO_MATCH' ? 'border-fog/30 text-fog bg-fog/10' : 'border-warn/40 text-warn bg-warn/10'}`}>
                    {m.decision || 'MATCH'}{m.evidence?.sampled ? ' \u2022 sample' : ''}
                  </span>
                  <span className="tnum text-fog">{((m.model_score ?? m.confidence) * 100).toFixed(1)}%</span>
                  <span className={`tnum font-bold ${m.confidence > 0.8 ? 'text-ok' : 'text-warn'}`}>{(Math.min(m.confidence, 0.999) * 100).toFixed(1)}%</span>
                  <span className={`text-[11px] font-bold uppercase ${(m.risk || m.evidence?.risk) === 'LOW' ? 'text-ok' : ((m.risk || m.evidence?.risk) === 'CRITICAL' || (m.risk || m.evidence?.risk) === 'HIGH') ? 'text-danger' : 'text-warn'}`}>
                    {m.risk || m.evidence?.risk || ' - '}
                  </span>
                  <span className={`font-bold ${m.auto_resolvable ? 'text-ok' : 'text-fog/50'}`}>{m.auto_resolvable ? 'YES' : 'NO'}</span>
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
            <h3 className="text-[13px] font-bold">{selected ? `${selected.decision || 'MATCH'} #${selected.id}` : 'Select a match'}</h3>
            {selected ? (
              <div className="mt-2.5 text-[12px]">
                <div>Source: <b>#{selected.record_a?.id}</b> {selected.record_a?.data?.name || ''} <span className="text-fog/50">({selected.record_a?.source_record_id})</span></div>
                <div className="mt-1">Target: <b>#{selected.record_b?.id}</b> {selected.record_b?.data?.name || ''} <span className="text-fog/50">({selected.record_b?.source_record_id})</span></div>
                <div className="mt-2">Decision: <b className={selected.decision === 'MATCH' ? 'text-ok' : 'text-warn'}>{selected.decision}</b> \u2022 Confidence <b className="text-ok">{(Math.min(selected.confidence, 0.999) * 100).toFixed(1)}%</b> \u2022 Model score {(selected.model_score * 100).toFixed(1)}%</div>
                <div className="mt-1">Risk: <b className="uppercase">{selected.risk || ' - '}</b> <span className="text-fog/50">{selected.risk_reason || ''}</span> \u2022 Auto-resolvable: <b className={selected.auto_resolvable ? 'text-ok' : 'text-warn'}>{selected.auto_resolvable ? 'YES' : 'NO'}</b> \u2022 {selected.recommendation || ''}</div>
                {selected.penalties && Object.keys(selected.penalties).length > 0 && (
                  <div className="mt-1 text-[11px] text-warn">Penalties: {Object.entries(selected.penalties).map(([k, v]: any) => `${k} ${typeof v === 'number' ? '-' + v : v}`).join(' \u2022 ')}</div>
                )}
                <div className="mt-1 text-fog/50">Model: SyncGuard Matcher v{selected.model_version} \u2022 Job #{selected.job_id} ({selected.job_status})</div>
                <div className="mt-1 text-[11px] text-fog/50">Candidate because: {(selected.evidence?.blocking_reasons || ['exhaustive']).join(' + ')} (blocking evidence - evaluation only, not a match signal)</div>
                <div className="mt-2 font-semibold">Field evidence</div>
                <Ticks evidence={selected.evidence} />
                {selected.field_evidence?.fields?.map((f: any) => (
                  <div key={f.field} className="mt-1 flex items-center justify-between bg-ink-900 px-2 py-1 text-[11px]">
                    <span className="capitalize">{f.field.replace(/_/g, ' ')}</span>
                    <span className={`font-semibold ${f.status === 'EXACT_MATCH' || f.status === 'STRONG_MATCH' ? 'text-ok' : f.status === 'PARTIAL_MATCH' ? 'text-warn' : f.status === 'MISMATCH' ? 'text-danger' : 'text-fog/50'}`}>
                      {(f.similarity * 100).toFixed(1)}% {f.status.replace(/_/g, ' ')}
                    </span>
                  </div>
                ))}
                <div className="mt-2 text-[11px] text-fog/50">WHY: {whyText(selected.evidence)} \u2022 Verification: {(selected.evidence?.verification_status || 'NEEDS_REVIEW').replace(/_/g, ' ')}</div>
                <button onClick={() => setSelected(null)} className="mt-2.5 w-full bg-line/60 px-2.5 py-1.5 text-[12px] text-white hover:bg-line">Close</button>
              </div>
            ) : (
              <div className="mt-2 text-[12px] text-fog/50 leading-relaxed">Click a row to see source/target records, field evidence, and why it matched. Source records stay intact - the match is a relationship.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
