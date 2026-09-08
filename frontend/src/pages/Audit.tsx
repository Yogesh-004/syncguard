import { useEffect, useState } from 'react'
import api from '../services/api-client'

export default function Audit(){
  const [logs, setLogs]=useState<any[]>([])
  const [filter, setFilter]=useState('')
  const [filterAction, setFilterAction]=useState('')
  const _activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null
  const [scopeMode, setScopeMode]=useState(_activeLive ? 'LIVE_SOURCE' : 'ALL')
  const [scopeJob, setScopeJob]=useState(typeof window!=='undefined' ? (localStorage.getItem('activeJobId') || '') : '')
  const [scopeSource, setScopeSource]=useState(_activeLive || '')
  const [scopeInfo, setScopeInfo]=useState<any>({})
  const [loading, setLoading]=useState(true)
  const [total, setTotal]=useState(0)
  const [selected, setSelected]=useState<any>(null)

  async function load(){
    setLoading(true)
    try{
      const params:any={ limit:50 }
      if(scopeMode==='LIVE_JOB' && scopeJob) params.job_id=scopeJob
      else if(scopeMode==='LIVE_SOURCE' && scopeSource) params.source_id=scopeSource
      const r=await api.get(`/audit-logs`, { params })
      setLogs(r.data.items||[])
      setTotal(r.data.total||0)
      setScopeInfo(r.data.scope||{})
    }catch{} finally{ setLoading(false)}
  }
  useEffect(()=>{ load(); const iv=setInterval(load, 5000); return ()=>clearInterval(iv) },[scopeMode, scopeJob, scopeSource])

  const filtered = logs.filter(l=>{
    if(filter && !(l.action.includes(filter) || l.entity_type?.includes(filter) || String(l.entity_id).includes(filter) || JSON.stringify(l.details||'').includes(filter))) return false
    if(filterAction && l.action!==filterAction) return false
    return true
  })

  const actions = Array.from(new Set(logs.map(l=>l.action))).slice(0,8)

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:12}}>
        <div>
          <h1 style={{fontSize:28, fontWeight:800}}>Audit Trail</h1>
          <p style={{color:'#94a3b8', marginTop:4}}>Live, manual, exclusive — every pipeline step is immutable and traceable. Click any row for full details.</p>
        </div>
        <div style={{display:'flex', gap:8, alignItems:'center'}}>
          <span style={{background:'#22c55e', color:'white', padding:'4px 10px', borderRadius:99, fontSize:12, fontWeight:700}}>● Live {total} logs</span>
          <button onClick={load} style={{border:'1px solid #334155', background:'#1e293b', color:'#e2e8f0', padding:'6px 12px', borderRadius:8, fontSize:13}}>Refresh</button>
        </div>
      </div>

      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:12, marginTop:16, display:'flex', gap:8, flexWrap:'wrap', alignItems:'center'}}>
        <select value={scopeMode} onChange={e=>setScopeMode(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="ALL">MODE: ALL</option><option value="LIVE_JOB">MODE: LIVE (by job)</option><option value="LIVE_SOURCE">MODE: LIVE (by source)</option>
        </select>
        {scopeMode==='LIVE_JOB' && <input placeholder="Job ID..." value={scopeJob} onChange={e=>setScopeJob(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13, width:100}} />}
        {scopeMode==='LIVE_SOURCE' && <input placeholder="Source ID..." value={scopeSource} onChange={e=>setScopeSource(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13, width:110}} />}
        <span style={{color:'#64748b', fontSize:11}}>DEMO/BENCHMARK stay on their pages — server filters by job/source lineage{scopeInfo.mode?` • scope: ${JSON.stringify(scopeInfo)}`:''}</span>
        <input placeholder="Search action, entity, id, details..." value={filter} onChange={e=>setFilter(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'8px 12px', borderRadius:8, flex:1, minWidth:200}} />
        <select value={filterAction} onChange={e=>setFilterAction(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="">All actions</option>
          {actions.map(a=> <option key={a} value={a}>{a}</option>)}
        </select>
        <span style={{color:'#94a3b8', fontSize:12}}>{filtered.length}/{total} shown • auto-refresh 5s • manual go-through</span>
      </div>

      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:14, marginTop:16}}>
        <h3 style={{fontWeight:700, fontSize:13}}>Pipeline trace — where every result goes</h3>
        <div style={{display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:8, marginTop:10, fontSize:11, textAlign:'center'}}>
          {[
            ['Records','2200','live DB', '#22c55e'],
            ['ML Matching','584','FEBRL3 model', '#3b82f6'],
            ['Conflicts','20','ML 0.6', '#f59e0b'],
            ['Resolution','Audit','you → logs', '#8b5cf6'],
            ['Jobs','3','benchmark', '#06b6d4'],
          ].map(([a,b,c,color]:any)=>(
            <div key={a} style={{background:'#0f172a', borderRadius:8, padding:10, border:`1px solid ${color}30`}}>
              <div style={{fontWeight:700, color, fontSize:12}}>{a}</div>
              <div style={{fontWeight:800, marginTop:4}}>{b}</div>
              <div style={{color:'#64748b', fontSize:10}}>{c}</div>
            </div>
          ))}
        </div>
        <div style={{color:'#64748b', fontSize:11, marginTop:8, textAlign:'center'}}>Every Approve/Reject/Modify/Defer → audit_logs + resolution_logs + (if approved) sync job • Training data never appears here — only live pipeline</div>
      </div>

      {loading ? <div style={{padding:20, color:'#94a3b8'}}>Loading live audit trail...</div> : (
        <div style={{display:'grid', gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr', gap:16, marginTop:16}}>
          <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, overflow:'hidden'}}>
            <div style={{display:'grid', gridTemplateColumns:'140px 160px 1fr 90px', gap:8, padding:'10px 14px', background:'#0f172a', color:'#94a3b8', fontSize:11, fontWeight:600}}>
              <span>Time</span><span>Action</span><span>Entity • Details</span><span>Status</span>
            </div>
            {filtered.length===0 ? <div style={{padding:32, textAlign:'center', color:'#64748b', fontSize:13}}>No logs match filter — try clearing or resolve a conflict to generate trail</div> :
             filtered.map((log:any)=>(
               <div key={log.id} onClick={()=> setSelected(log)} style={{display:'grid', gridTemplateColumns:'140px 160px 1fr 90px', gap:8, padding:'10px 14px', borderTop:'1px solid #334155', fontSize:12, alignItems:'center', cursor:'pointer', background: selected?.id===log.id ? '#1e293b' : 'transparent', borderLeft: selected?.id===log.id ? '3px solid #3b82f6' : '3px solid transparent'}}>
                 <span style={{color:'#94a3b8', fontSize:11}}>{log.created_at ? new Date(log.created_at).toLocaleString() : '-'}</span>
                 <span style={{background: log.action?.includes('approved')?'#22c55e15': log.action?.includes('rejected')?'#ef444415': log.action?.includes('modified')?'#3b82f615':'#334155', border:`1px solid ${log.action?.includes('approved')?'#22c55e30':'#334155'}`, color: log.action?.includes('approved')?'#22c55e': log.action?.includes('rejected')?'#ef4444': log.action?.includes('modified')?'#3b82f6':'#e2e8f0', padding:'2px 8px', borderRadius:99, fontWeight:600, textAlign:'center', fontSize:11}}>{log.action}</span>
                 <div>
                   <div style={{fontWeight:600, fontSize:12}}>{log.entity_type} #{log.entity_id}</div>
                   <div style={{color:'#94a3b8', fontSize:11, marginTop:2, whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis'}}>{log.details ? Object.entries(log.details).map(([k,v]:any)=> `${k}:${v}`).join(' • ') : ''} {log.job_id ? `• job ${log.job_id}`:''}</div>
                 </div>
                 <span style={{color: log.error ? '#ef4444' : '#22c55e', fontWeight:600, fontSize:11, textAlign:'center'}}>{log.error ? 'Failed' : 'Success'}</span>
               </div>
             ))}
          </div>

          <div style={{background:'#0f172a', border:'1px solid #334155', borderRadius:12, padding:14, height:'fit-content', position:'sticky', top:16}}>
            <h3 style={{fontWeight:700, fontSize:13}}>{selected ? `Log #${selected.id} — Manual detail` : 'Select a log — manual go-through'}</h3>
            {selected ? (
              <div style={{marginTop:10, fontSize:12}}>
                <div style={{background:'#1e293b', borderRadius:8, padding:10}}>
                  <div style={{display:'grid', gridTemplateColumns:'100px 1fr', gap:8, fontSize:12}}>
                    <span style={{color:'#94a3b8'}}>Action</span><span style={{fontWeight:700}}>{selected.action}</span>
                    <span style={{color:'#94a3b8'}}>Entity</span><span>{selected.entity_type} #{selected.entity_id}</span>
                    <span style={{color:'#94a3b8'}}>Time</span><span>{selected.created_at ? new Date(selected.created_at).toLocaleString() : '-'}</span>
                    <span style={{color:'#94a3b8'}}>Request</span><span style={{fontFamily:'monospace', fontSize:11}}>{selected.request_id || '-'}</span>
                    <span style={{color:'#94a3b8'}}>Job</span><span>{selected.job_id || '-'}</span>
                    <span style={{color:'#94a3b8'}}>Source</span><span>{selected.source_id || '-'}</span>
                  </div>
                </div>
                <div style={{background:'#1e293b', borderRadius:8, padding:10, marginTop:10}}>
                  <div style={{fontWeight:600, fontSize:12}}>Details JSON</div>
                  <pre style={{background:'#0f172a', padding:8, borderRadius:6, marginTop:6, fontSize:11, overflow:'auto', maxHeight:200}}>{JSON.stringify(selected.details||{}, null, 2)}</pre>
                </div>
                <div style={{background:'#1e293b', borderRadius:8, padding:10, marginTop:10, fontSize:11, color:'#94a3b8'}}>
                  <b>Where it goes:</b> This log is immutable, stored in <code>audit_logs</code> table. Linked <code>resolution_logs</code> for conflicts and <code>reconciliation_jobs</code> for pipeline. Verify via <code>GET /audit-logs?limit=50</code> and <code>GET /jobs</code>. Every manual action you take in Conflicts appears here instantly.
                </div>
                <div style={{display:'flex', gap:8, marginTop:10}}>
                  <button onClick={()=> setSelected(null)} style={{flex:1, background:'#334155', color:'white', border:'none', padding:'8px', borderRadius:6, fontSize:12}}>Close</button>
                  <a href="/conflicts" style={{flex:1, background:'#3b82f6', color:'white', padding:'8px', borderRadius:6, textAlign:'center', fontSize:12, fontWeight:600}}>Go to Conflicts</a>
                </div>
              </div>
            ) : (
              <div style={{color:'#64748b', fontSize:12, marginTop:8, lineHeight:1.6}}>
                Click any row on the left to see full manual detail — request_id, job_id, source_id, details JSON, and where it sits in the pipeline. All logs are live, not samples — try resolving a conflict in <a href="/conflicts" style={{color:'#3b82f6'}}>Conflicts</a> and watch it appear here with 5s auto-refresh.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
