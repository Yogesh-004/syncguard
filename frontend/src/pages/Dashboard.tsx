import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

function Stat({ title, value, color }: { title: string; value: any; color: string }) {
  return (
    <div className="sg-card p-4 transition-colors duration-300 hover:border-accent">
      <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-fog">{title}</div>
      <div className="tnum mt-1.5 text-[28px] font-extrabold" style={{ color }}>{value}</div>
    </div>
  )
}

export default function Dashboard() {
  const [demo, setDemo] = useState<any>(null)
  const [live, setLive] = useState<any>({})
  const [recon, setRecon] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)

  useEffect(() => {
    fetch('/demo.json').then(r => r.json()).then(setDemo).catch(() => {})
    api.get('/health').then(r => setHealth(r.data)).catch(() => {})
    ;(async () => {
      let activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null
      if (!activeLive) {
        try {
          const s = await api.get('/sources')
          const liveSrc = (s.data as any[]).find((x: any) => x.config?.live)
          if (liveSrc) { activeLive = String(liveSrc.id); localStorage.setItem('activeLiveSourceId', activeLive) }
        } catch {}
      }
      const recQ = activeLive ? `/records?limit=1&source_id=${activeLive}` : '/records?limit=1'
      const confQ = activeLive ? `/conflicts?limit=1&source_id=${activeLive}` : '/conflicts?limit=1'
      const jobsQ = activeLive ? `/jobs?source_id=${activeLive}` : '/jobs'
      const statsQ = activeLive ? `/stats/summary?source_id=${activeLive}` : '/stats/summary'
      const results = await Promise.allSettled([api.get(recQ), api.get(confQ), api.get(jobsQ), api.get('/schemas'), api.get('/sources'), api.get(statsQ)])
      const [rec, conf, jobs, schemas, sources, stats] = results.map((r: any) => r.status === 'fulfilled' ? (r as any).value.data : null)
      setLive({
        records: rec?.total ?? rec?.length ?? 0,
        conflicts: Array.isArray(conf) ? conf.length : conf?.total ?? 0,
        jobs: jobs?.total ?? jobs?.items?.length ?? 0,
        schemas: Array.isArray(schemas) ? schemas.length : schemas?.length ?? 0,
        sources: Array.isArray(sources) ? sources.length : sources?.length ?? 0,
      })
      if (stats) setRecon(stats)
    })()
  }, [])

  const d = demo || { systems_monitored: 3, records_processed: 0, matches: 3, conflicts: 3, auto_resolvable: 1, schema_changes: 2, failed_sync_jobs: 1, reconciliation_health: 94.2, confidence_distribution: [{ name: 'High', value: 1 }, { name: 'Medium', value: 2 }, { name: 'Low', value: 0 }], match_rate: 86.4, conflict_rate: 5.3, resolution_rate: 68.1 }
  const records = live.records ?? d.records_processed
  const conflicts = live.conflicts ?? d.conflicts
  const sourcesCount = live.sources || d.systems_monitored
  const COLORS = ['#22c55e', '#3b82f6', '#f59e0b']

  return (
    <div>
      <GsapReveal>
        <div className="flex items-baseline gap-3">
          <h1 className="text-[28px] font-extrabold tracking-tight">Overview</h1>
          <span className="text-[11px] font-medium text-fog">live API + DEMO DATA fallback</span>
        </div>
        <p className="mt-1.5 text-[14px] text-fog">
          {health ? `${health.app} ${health.version} \u2022 ${health.status}` : 'Loading health...'} - {live.records !== undefined ? 'Live data (DB)' : 'DEMO DATA (demo.json)'}
        </p>
      </GsapReveal>

      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-4">
        <Stat title="Systems" value={sourcesCount} color="#3b82f6" />
        <Stat title="Records (live)" value={records} color="#22c55e" />
        <Stat title="Conflicts (live)" value={conflicts} color="#f59e0b" />
        <Stat title="Jobs (live)" value={live.jobs ?? 1} color="#8b5cf6" />
        <Stat title="Schemas" value={live.schemas ?? 3} color="#06b6d4" />
        <Stat title="Auto-resolvable" value={recon ? recon.auto_resolvable : d.auto_resolvable} color="#06b6d4" />
        <Stat title="Schema changes" value={d.schema_changes} color="#ef4444" />
        <Stat title="Health" value={d.reconciliation_health + '%'} color="#22c55e" />
      </div>

      {recon && (
        <GsapReveal delay={0.06}>
          <div className="sg-card mt-4 p-4">
            <h3 className="text-[14px] font-bold">Reconciliation - persisted backend data ({recon.mode})</h3>
            <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-6">
              {[['MATCH', recon.matches, '#22c55e'], ['POSSIBLE', recon.possible, '#f59e0b'], ['NO MATCH', recon.nomatch, '#64748b'], ['Auto-resolvable', recon.auto_resolvable, '#06b6d4'], ['Manual review', recon.manual_review, '#f59e0b'], ['High risk', recon.high_risk, '#ef4444'], ['Conflicts', recon.conflicts, '#f59e0b'], ['Resolved', recon.resolved, '#22c55e'], ['Rejected', recon.rejected, '#ef4444'], ['Deferred', recon.deferred, '#64748b'], ['Sync success', recon.sync_success, '#22c55e'], ['Sync failed', recon.sync_failed, '#ef4444']].map(([label, val, color]: any) => (
                <div key={label} className="bg-ink-900 p-2.5 text-center">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-fog">{label}</div>
                  <div className="tnum mt-1 text-[20px] font-extrabold" style={{ color }}>{val}</div>
                </div>
              ))}
            </div>
          </div>
        </GsapReveal>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <GsapReveal delay={0.08}>
          <div className="sg-card p-4">
            <h3 className="text-[14px] font-bold">Reconciliation</h3>
            <div className="mt-3 flex gap-4 text-[13px]">
              <span>Match <b className="text-ok">{d.match_rate}%</b></span>
              <span>Conflict <b className="text-warn">{d.conflict_rate}%</b></span>
              <span>Resolved <b className="text-info">{d.resolution_rate}%</b></span>
            </div>
            <div className="mt-3 h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={[{ name: 'Match', v: d.match_rate }, { name: 'Conflict', v: d.conflict_rate }, { name: 'Resolved', v: d.resolution_rate }]}>
                  <XAxis dataKey="name" stroke="#64748b" fontSize={12} />
                  <YAxis stroke="#64748b" fontSize={12} />
                  <Tooltip />
                  <Bar dataKey="v" fill="#3b82f6" radius={0} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </GsapReveal>
        <GsapReveal delay={0.1}>
          <div className="sg-card p-4">
            <h3 className="text-[14px] font-bold">Confidence</h3>
            <div className="mt-3 h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={d.confidence_distribution} dataKey="value" nameKey="name" outerRadius={70} label>
                    {d.confidence_distribution.map((_: any, i: number) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>
        </GsapReveal>
      </div>

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <GsapReveal delay={0.12}>
          <div className="sg-card p-4">
            <h3 className="text-[14px] font-bold">Live sources</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-fog">
              Live sources use the decision engine: MODEL SCORE \u2192 FINAL CONFIDENCE \u2192 MATCH / POSSIBLE_MATCH / NO_MATCH. Try CSV/JSON/REST connectors via <code className="tnum bg-ink-900 px-1.5 py-0.5 text-[12px]">/connectors/*/validate</code>.
            </p>
          </div>
        </GsapReveal>
        <GsapReveal delay={0.14}>
          <div className="sg-card p-4">
            <h3 className="text-[14px] font-bold">Jobs</h3>
            <p className="mt-2 text-[13px] leading-relaxed text-fog">
              Poll <code className="tnum bg-ink-900 px-1.5 py-0.5 text-[12px]">GET /jobs</code> - current: {live.jobs ?? 0} jobs. Idempotency via DB UNIQUE, retry 5\u00d7 backoff.
            </p>
          </div>
        </GsapReveal>
      </div>
    </div>
  )
}
