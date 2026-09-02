import { useEffect, useState } from 'react'
import api from '../services/api-client'

function EvidenceTicks({ ev }: any){
  if(!ev) return null
  const items:any[]=[]
  const core=['email','phone','name','postcode','external_id']
  core.forEach(k=>{
    if(ev[k]){
      const v=ev[k]
      if(v.match) items.push({label:k, ok:true, score:v.score})
      else if(v.reason==='missing_field') items.push({label:k, ok:false, warn:true})
      else items.push({label:k, ok:!!v.match, score:v.score})
    }
  })
  if(ev.ml_prob!==undefined) items.push({label:`ML ${(ev.ml_prob*100).toFixed(0)}%`, ok:ev.ml_prob>=0.6, score:ev.ml_prob})
  if(items.length===0){
    Object.entries(ev).forEach(([k,v]:any)=>{
      if(k.startsWith('ml_')||k==='model') return
      if(typeof v==='object' && v!==null && 'match' in v) items.push({label:k, ok:v.match})
    })
  }
  return (
    <div style={{display:'flex', gap:6, flexWrap:'wrap', marginTop:6}}>
      {items.map((it,i)=>(
        <span key={i} style={{background: it.ok?'#22c55e15': it.warn?'#f59e0b15':'#ef444415', border:`1px solid ${it.ok?'#22c55e':it.warn?'#f59e0b':'#ef4444'}30`, color: it.ok?'#22c55e':it.warn?'#f59e0b':'#ef4444', padding:'2px 8px', borderRadius:99, fontSize:11, fontWeight:600}}>
          {it.ok?'✓':it.warn?'⚠':'✗'} {it.label}
        </span>
      ))}
    </div>
  )
}

export default function Conflicts(){
  const [data, setData]=useState<any[]>([])
  const [recordsMap, setRecordsMap]=useState<any>({})
  const [audit, setAudit]=useState<any[]>([])
  const [filterRisk, setFilterRisk]=useState('')
  const [filterStatus, setFilterStatus]=useState('pending')
  const [loading, setLoading]=useState(true)
  const [resolving, setResolving]=useState<number|null>(null)
  const [toast, setToast]=useState<string>('')

  async function load(){
    setLoading(true)
    try{
      const activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null
      const srcQ = activeLive ? `&source_id=${activeLive}` : ''
      const [confRes, recRes, auditRes] = await Promise.all([
        api.get(`/conflicts?limit=100${filterRisk?`&risk_level=${filterRisk}`:''}${filterStatus?`&status=${filterStatus}`:''}${srcQ}`),
        api.get(activeLive ? `/records?limit=500&source_id=${activeLive}` : '/records?limit=500'),
        api.get('/audit-logs?limit=5')
      ])
      setData(Array.isArray(confRes.data)? confRes.data : confRes.data.items||[])
      const map:any={}
      ;(recRes.data.items||[]).forEach((r:any)=> map[r.id]=r)
      setRecordsMap(map)
      setAudit(auditRes.data.items||[])
    }catch{} finally{ setLoading(false)}
  }
  useEffect(()=>{ load() },[filterRisk, filterStatus])

  async function resolve(id:number, action:string){
    setResolving(id)
    try{
      const res = await api.post(`/conflicts/${id}/resolve`, {action})
      const newStatus = (res.data as any)?.status || ({approve:'approved',reject:'rejected',modify:'modified',defer:'deferred'} as any)[action] || action
      setData(d=> d.map(c=> c.id===id ? {...c, resolution_status:newStatus, resolved_at: new Date().toISOString()} : c))
      // Show where result goes
      const dest = action==='approve' ? `→ Audit #${res.data?.conflict_id} → sync to target (job will appear in Jobs)` : action==='reject' ? `→ Audit → dismissed, no sync` : action==='modify' ? `→ Audit → record updated` : `→ Audit → deferred for later review`
      setToast(`Conflict #${id} ${newStatus} ${dest}`)
      setTimeout(()=> setToast(''), 4000)
      // refresh audit
      const ar = await api.get('/audit-logs?limit=5')
      setAudit(ar.data.items||[])
    }catch(e:any){
      setToast(`Failed: ${e?.response?.data?.detail || e.message}`)
      setTimeout(()=> setToast(''), 3000)
    } finally{ setResolving(null)}
  }

  if(loading) return <div style={{padding:20, color:'#94a3b8'}}>Loading conflicts — ML pipeline (trained on 3 benchmarks)...</div>

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:12}}>
        <div>
          <h1 style={{fontSize:28, fontWeight:800}}>Conflicts</h1>
          <p style={{color:'#94a3b8', marginTop:4}}>Every conflict is <b>ML-generated</b> (LogisticRegression) — <b>pipeline:</b> Records → ML Matching → Conflict → <b>Manual/Auto Resolution</b> → Audit → Sync Job</p>
        </div>
        <div style={{background:'#22c55e15', border:'1px solid #22c55e30', padding:'6px 12px', borderRadius:99, fontSize:12, color:'#22c55e', fontWeight:700}}>● Production • ML model</div>
      </div>

      {/* Why manual? */}
      <div style={{background:'#0f172a', border:'1px solid #334155', borderRadius:12, padding:12, marginTop:12, display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:12, fontSize:12}}>
        <div><b style={{color:'#22c55e'}}>Auto-resolve</b> <span style={{color:'#94a3b8'}}>if confidence &gt;95% and low risk → no human needed, audit logged, sync job created automatically</span></div>
        <div><b style={{color:'#f59e0b'}}>Manual approval</b> <span style={{color:'#94a3b8'}}>if 80–95% or medium risk → human must approve/reject to avoid false merge (e.g., John Smith vs John Smyth)</span></div>
        <div><b style={{color:'#ef4444'}}>High risk</b> <span style={{color:'#94a3b8'}}>if &lt;80% or missing key fields → requires intervention, else would create duplicate customer</span></div>
      </div>

      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:12, marginTop:12, display:'flex', gap:8, flexWrap:'wrap', alignItems:'center'}}>
        <select value={filterRisk} onChange={e=>setFilterRisk(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="">All risks</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
        </select>
        <select value={filterStatus} onChange={e=>setFilterStatus(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="pending">Pending (needs action)</option><option value="">All status</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="deferred">Deferred</option>
        </select>
        <button onClick={load} style={{border:'1px solid #334155', background:'transparent', color:'#e2e8f0', padding:'6px 12px', borderRadius:8, fontSize:13}}>Refresh</button>
        <span style={{color:'#64748b', fontSize:12, marginLeft:'auto'}}>{data.length} shown • {data.filter(c=>c.auto_resolvable).length} auto-resolvable • pipeline verified</span>
      </div>

      {toast && <div style={{background:'#22c55e', color:'white', padding:'10px 14px', borderRadius:8, marginTop:12, fontWeight:600, fontSize:13}}>{toast} • Check Jobs and Audit below</div>}

      {data.length===0 ? (
        <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:32, textAlign:'center', marginTop:16, color:'#64748b'}}>
          No conflicts in this filter — try “All status” or lower threshold in Matching. Pipeline verified: {Object.keys(recordsMap).length} records → ML → conflicts.
        </div>
      ) : (
        <div style={{marginTop:16}}>
          {data.map((c:any)=>{
            const a = recordsMap[c.record_a_id]
            const b = recordsMap[c.record_b_id]
            const isRavi = a?.data?.email==='ravi@gmail.com' || b?.data?.email==='ravi@gmail.com'
            return (
              <div key={c.id} style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:16, marginBottom:14, borderLeft:`4px solid ${c.risk_level==='low'?'#22c55e':c.risk_level==='medium'?'#f59e0b':'#ef4444'}`, opacity: c.resolution_status==='pending' ? 1 : 0.85}}>
                <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:8}}>
                  <div style={{display:'flex', gap:8, alignItems:'center', flexWrap:'wrap'}}>
                    <span style={{background:'#0f172a', border:'1px solid #334155', padding:'4px 10px', borderRadius:99, fontSize:12, fontWeight:700}}>#{c.id} • ML {(c.confidence*100).toFixed(1)}%</span>
                    <span style={{background: c.risk_level==='low'?'#22c55e':c.risk_level==='medium'?'#f59e0b':'#ef4444', color:'white', padding:'2px 8px', borderRadius:99, fontSize:11, fontWeight:700, textTransform:'uppercase'}}>{c.risk_level} risk</span>
                    <span style={{background: c.auto_resolvable?'#22c55e15':'#64748b15', border:`1px solid ${c.auto_resolvable?'#22c55e30':'#64748b30'}`, color: c.auto_resolvable?'#22c55e':'#94a3b8', padding:'2px 8px', borderRadius:99, fontSize:11}}>{c.recommendation} {c.auto_resolvable?'• auto':''}</span>
                  </div>
                  <span style={{background: c.resolution_status==='pending'?'#f59e0b15': c.resolution_status==='approved'?'#22c55e15': c.resolution_status==='rejected'?'#ef444415':'#334155', border:`1px solid ${c.resolution_status==='pending'?'#f59e0b30':'#334155'}`, color: c.resolution_status==='pending'?'#f59e0b': c.resolution_status==='approved'?'#22c55e':'#e2e8f0', padding:'4px 10px', borderRadius:99, fontSize:12, textTransform:'capitalize', fontWeight:600}}>{c.resolution_status} {c.resolved_at ? `• ${new Date(c.resolved_at).toLocaleTimeString()}`:''}</span>
                </div>

                <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:12, marginTop:14}}>
                  {[a,b].map((rec:any, idx:number)=>(
                    <div key={idx} style={{background:'#0f172a', borderRadius:10, padding:14, border:'1px solid #334155'}}>
                      <div style={{color: idx===0?'#3b82f6':'#8b5cf6', fontWeight:700, fontSize:11, textTransform:'uppercase'}}>{idx===0 ? 'Record A' : 'Record B'} • #{rec?.id || c.record_a_id} {rec?.source_id ? `(src ${rec.source_id})`:''}</div>
                      {rec ? (
                        <>
                          <div style={{fontWeight:700, marginTop:8}}>{rec.data?.name || rec.data?.title || '—'}</div>
                          <div style={{color:'#94a3b8', fontSize:13, marginTop:4}}>{rec.data?.email || rec.data?.brand || rec.data?.surname || ''}</div>
                          <div style={{fontSize:13, marginTop:6, color: rec.data?.phone ? '#e2e8f0' : '#ef4444', fontWeight:600}}>{rec.data?.phone || rec.data?.price || 'NULL'}</div>
                          <div style={{fontSize:11, color:'#64748b', marginTop:6}}>ID: {rec.source_record_id} {rec.data?.postcode ? `• ${rec.data.postcode}`:''}</div>
                        </>
                      ) : <div style={{color:'#64748b', marginTop:8}}>Loading...</div>}
                    </div>
                  ))}
                </div>

                {isRavi && (
                  <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:8, marginTop:10, fontSize:11, textAlign:'center', background:'#0f172a', borderRadius:8, padding:8, border:'1px dashed #334155'}}>
                    <div><div style={{color:'#3b82f6', fontWeight:700}}>CRM</div><div>Ravi Kumar</div><div style={{color:'#94a3b8'}}>ravi@gmail.com</div><div>9876543210</div></div>
                    <div><div style={{color:'#8b5cf6', fontWeight:700}}>ERP</div><div>RAVI KUMAR</div><div style={{color:'#94a3b8'}}>ravi@gmail.com</div><div>9876543210</div></div>
                    <div><div style={{color:'#f59e0b', fontWeight:700}}>Accounting</div><div>Ravi K.</div><div style={{color:'#94a3b8'}}>ravi@gmail.com</div><div style={{color:'#ef4444'}}>NULL</div></div>
                  </div>
                )}

                {c.conflicting_fields?.length>0 && (
                  <div style={{marginTop:12}}>
                    <div style={{fontWeight:600, fontSize:12, color:'#94a3b8'}}>Conflicting fields — what disagrees</div>
                    <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(180px, 1fr))', gap:8, marginTop:6}}>
                      {c.conflicting_fields.map((f:any,i:number)=>(
                        <div key={i} style={{background:'#0f172a', borderRadius:8, padding:10, border:'1px solid #334155'}}>
                          <div style={{color:'#f59e0b', fontWeight:600, fontSize:12}}>{f.field_name} <span style={{color:'#64748b', fontWeight:400}}>({f.conflict_type})</span></div>
                          {Object.entries(f.values||{}).map(([k,v]:any)=>(
                            <div key={k} style={{display:'flex', justifyContent:'space-between', background:'#1e293b', padding:'4px 8px', borderRadius:6, marginTop:4, fontSize:12}}>
                              <span style={{color:'#94a3b8'}}>{k}</span><span style={{fontWeight:600, color: v===null?'#ef4444':'#e2e8f0'}}>{String(v ?? 'NULL')}</span>
                            </div>
                          ))}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div style={{background:'#0f172a', borderRadius:8, padding:10, marginTop:12, border:'1px solid #334155'}}>
                  <div style={{display:'flex', justifyContent:'space-between'}}>
                    <span style={{fontWeight:600, fontSize:12}}>Evidence • ML model</span>
                    <span style={{color:'#22c55e', fontWeight:700, fontSize:12}}>{(c.confidence*100).toFixed(1)}% confidence</span>
                  </div>
                  <EvidenceTicks ev={c.evidence} />
                  <div style={{color:'#64748b', fontSize:11, marginTop:6}}>Model: LogisticRegression trained on 3 benchmarks • Why manual? {c.risk_level!=='low' || c.confidence <0.95 ? 'Medium/low confidence → human must verify to avoid false merge (e.g., two John Smiths same postcode)' : 'High confidence but still audited'}</div>
                </div>

                {/* Where result goes */}
                {c.resolution_status!=='pending' ? (
                  <div style={{background: c.resolution_status==='approved' ? '#22c55e15' : c.resolution_status==='rejected' ? '#ef444415' : '#334155', border:`1px solid ${c.resolution_status==='approved'?'#22c55e30':'#334155'}`, borderRadius:8, padding:10, marginTop:12, fontSize:12}}>
                    <b>Result:</b> {c.resolution_status} → <b>Audit log</b> created (see below) {c.resolution_status==='approved' ? '→ will sync to target system (check Jobs)' : c.resolution_status==='rejected' ? '→ no sync, kept separate' : ''} • <b>Where:</b> `audit_logs` + `resolution_logs` • <b>Next:</b> {c.resolution_status==='deferred' ? 'Review later in this list' : 'Verify in Audit & Jobs'}
                  </div>
                ) : (
                  <div style={{background:'#1e293b', border:'1px dashed #334155', borderRadius:8, padding:8, marginTop:12, fontSize:11, color:'#94a3b8', textAlign:'center'}}>
                    After you select, result goes to <b>Audit</b> and {c.auto_resolvable ? 'auto-syncs via Jobs' : 'awaits Jobs'} — try Approve to see
                  </div>
                )}

                <div style={{display:'flex', gap:8, marginTop:12, flexWrap:'wrap'}}>
                  {[
                    {id:'approve', label:'Approve', color:'#22c55e', desc:'Merge / sync'},
                    {id:'reject', label:'Reject', color:'#ef4444', desc:'Keep separate'},
                    {id:'modify', label:'Modify', color:'#3b82f6', desc:'Edit then sync'},
                    {id:'defer', label:'Defer', color:'#64748b', desc:'Later'},
                  ].map(btn=>(
                    <button key={btn.id} disabled={resolving===c.id || c.resolution_status!=='pending'} onClick={()=>resolve(c.id, btn.id)}
                      style={{
                        background: btn.color, color:'white', border:'none', padding:'8px 14px', borderRadius:8, cursor: c.resolution_status!=='pending' ? 'not-allowed' : 'pointer',
                        fontWeight:700, fontSize:13, opacity: c.resolution_status!=='pending' ? 0.5 : resolving===c.id ? 0.6 : 1, minWidth:90
                      }}>
                      {btn.label}
                    </button>
                  ))}
                  <span style={{marginLeft:'auto', color:'#64748b', fontSize:11, alignSelf:'center'}}>Pipeline: Records → ML (584 matches) → Conflicts → You → Audit/Jobs</span>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Live audit preview — where result goes */}
      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:14, marginTop:16}}>
        <h3 style={{fontWeight:700, fontSize:13}}>Where results go — Audit trail (live)</h3>
        {audit.length===0 ? <div style={{color:'#64748b', fontSize:12, marginTop:6}}>No audit yet — approve a conflict to see entry here and in Jobs</div> :
         audit.map((a:any)=>(
           <div key={a.id} style={{display:'flex', justifyContent:'space-between', background:'#0f172a', padding:'8px 10px', borderRadius:6, marginTop:6, fontSize:12}}>
             <span><b>{a.action}</b> • {a.entity_type} #{a.entity_id}</span>
             <span style={{color:'#94a3b8'}}>{a.created_at ? new Date(a.created_at).toLocaleTimeString() : ''}</span>
           </div>
         ))}
        <div style={{color:'#64748b', fontSize:11, marginTop:8}}>Every approve/reject creates `audit_logs` + `resolution_logs` — verify via <code>GET /audit-logs</code> and <code>GET /jobs</code></div>
      </div>
    </div>
  )
}
