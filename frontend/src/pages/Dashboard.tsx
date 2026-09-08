import { useEffect, useState } from 'react'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts'
import api from '../services/api-client'

function Stat({ title, value, color }: any) {
  return (
    <div style={{ background: '#1e293b', borderRadius: 12, padding: 16, border: '1px solid #334155' }}>
      <div style={{ color: '#94a3b8', fontSize: 12, textTransform: 'uppercase' }}>{title}</div>
      <div style={{ color, fontSize: 28, fontWeight: 800, marginTop: 6 }}>{value}</div>
    </div>
  )
}

export default function Dashboard() {
  const [demo, setDemo] = useState<any>(null)
  const [live, setLive] = useState<any>({})
  const [recon, setRecon] = useState<any>(null)
  const [health, setHealth] = useState<any>(null)
  useEffect(() => {
    fetch('/demo.json').then(r => r.json()).then(setDemo).catch(()=>{})
    api.get('/health').then(r=>setHealth(r.data)).catch(()=>{})
    ;(async ()=>{
      let activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null
      if(!activeLive){
        try{ const s=await api.get('/sources'); const liveSrc=(s.data as any[]).find((x:any)=> x.config?.live); if(liveSrc){ activeLive=String(liveSrc.id); localStorage.setItem('activeLiveSourceId', activeLive) } }catch{}
      }
      const recQ = activeLive ? `/records?limit=1&source_id=${activeLive}` : '/records?limit=1'
      const confQ = activeLive ? `/conflicts?limit=1&source_id=${activeLive}` : '/conflicts?limit=1'
      const jobsQ = activeLive ? `/jobs?source_id=${activeLive}` : '/jobs'
      const statsQ = activeLive ? `/stats/summary?source_id=${activeLive}` : '/stats/summary'
      const results = await Promise.allSettled([api.get(recQ), api.get(confQ), api.get(jobsQ), api.get('/schemas'), api.get('/sources'), api.get(statsQ)])
      const [rec, conf, jobs, schemas, sources, stats] = results.map((r:any)=> r.status==='fulfilled' ? (r as any).value.data : null)
      setLive({
        records: rec?.total ?? rec?.length ?? 0,
        conflicts: Array.isArray(conf) ? conf.length : conf?.total ?? 0,
        jobs: jobs?.total ?? jobs?.items?.length ?? 0,
        schemas: Array.isArray(schemas) ? schemas.length : schemas?.length ?? 0,
        sources: Array.isArray(sources) ? sources.length : sources?.length ?? 0,
      })
      if(stats) setRecon(stats)
    })()
  }, [])
  const d = demo || { systems_monitored: 3, records_processed: 0, matches: 3, conflicts: 3, auto_resolvable: 1, schema_changes: 2, failed_sync_jobs: 1, reconciliation_health: 94.2, confidence_distribution: [{name:'High',value:1},{name:'Medium',value:2},{name:'Low',value:0}], match_rate: 86.4, conflict_rate: 5.3, resolution_rate: 68.1 }
  const records = live.records ?? d.records_processed
  const conflicts = live.conflicts ?? d.conflicts
  const sourcesCount = live.sources || d.systems_monitored
  const COLORS = ['#22c55e', '#3b82f6', '#f59e0b']
  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800 }}>Overview <span style={{ fontSize:12, color:'#94a3b8', fontWeight:400, marginLeft:8 }}>live API + DEMO DATA fallback</span></h1>
      <p style={{ color: '#94a3b8', marginTop: 6 }}>{health ? `${health.app} ${health.version} • ${health.status}` : 'Loading health...'} — {live.records!==undefined ? 'Live data (DB)' : 'DEMO DATA (demo.json)'}</p>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(150px,1fr))', gap: 12, marginTop: 16 }}>
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
        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16, marginTop: 16 }}>
          <h3 style={{ fontWeight: 700 }}>Reconciliation — persisted backend data ({recon.mode})</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(120px,1fr))', gap: 12, marginTop: 12 }}>
            {[['MATCH', recon.matches, '#22c55e'], ['POSSIBLE', recon.possible, '#f59e0b'], ['NO MATCH', recon.nomatch, '#64748b'], ['Auto-resolvable', recon.auto_resolvable, '#06b6d4'], ['Manual review', recon.manual_review, '#f59e0b'], ['High risk', recon.high_risk, '#ef4444'], ['Conflicts', recon.conflicts, '#f59e0b'], ['Resolved', recon.resolved, '#22c55e'], ['Rejected', recon.rejected, '#ef4444'], ['Deferred', recon.deferred, '#64748b'], ['Sync success', recon.sync_success, '#22c55e'], ['Sync failed', recon.sync_failed, '#ef4444']].map(([label, val, color]: any)=>(
              <div key={label} style={{ background: '#0f172a', borderRadius: 8, padding: 10, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: '#94a3b8', textTransform: 'uppercase' }}>{label}</div>
                <div style={{ fontSize: 22, fontWeight: 800, color, marginTop: 4 }}>{val}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontWeight: 700 }}>Reconciliation</h3>
          <div style={{ display: 'flex', gap: 12, marginTop: 12, fontSize: 13 }}>
            <span>Match <b style={{ color: '#22c55e' }}>{d.match_rate}%</b></span>
            <span>Conflict <b style={{ color: '#f59e0b' }}>{d.conflict_rate}%</b></span>
            <span>Resolved <b style={{ color: '#3b82f6' }}>{d.resolution_rate}%</b></span>
          </div>
          <div style={{ height: 180, marginTop: 12 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={[{ name: 'Match', v: d.match_rate }, { name: 'Conflict', v: d.conflict_rate }, { name: 'Resolved', v: d.resolution_rate }]}>
                <XAxis dataKey="name" stroke="#64748b" fontSize={12} /><YAxis stroke="#64748b" fontSize={12} /><Tooltip />
                <Bar dataKey="v" fill="#3b82f6" radius={[6,6,0,0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontWeight: 700 }}>Confidence</h3>
          <div style={{ height: 180, marginTop: 12 }}>
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={d.confidence_distribution} dataKey="value" nameKey="name" outerRadius={70} label>
                  {d.confidence_distribution.map((_:any,i:number)=><Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginTop: 16 }}>
        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontWeight: 700 }}>Live sources</h3>
          <div style={{ color:'#94a3b8', fontSize:13, marginTop:8 }}>Live sources use the decision engine: MODEL SCORE → FINAL CONFIDENCE → MATCH / POSSIBLE_MATCH / NO_MATCH. Try CSV/JSON/REST connectors via <code>/connectors/*/validate</code>.</div>
        </div>
        <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 16 }}>
          <h3 style={{ fontWeight: 700 }}>Jobs</h3>
          <div style={{ color: '#94a3b8', fontSize: 14, marginTop: 8 }}>Poll <code>GET /jobs</code> — current: {live.jobs ?? 0} jobs. Idempotency via DB UNIQUE, retry 5× backoff.</div>
        </div>
      </div>
    </div>
  )
}
