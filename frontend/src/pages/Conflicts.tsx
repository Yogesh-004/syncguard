import { useEffect, useState } from 'react'
import api from '../services/api-client'
import ResolutionPanel from '../components/ResolutionPanel'
import Timeline from '../components/Timeline'

function Ticks({ ev }: any){
  if(!ev) return null
  const items:any[]=[]
  ;['email','phone','name'].forEach(k=>{
    const v=ev[k]
    if(v?.match) items.push({label:`${k} ${(v.score*100).toFixed(0)}%`, ok:true})
    else if(v) items.push({label:k, ok:false, warn:v.reason==='missing_field'})
  })
  if(ev.ml_prob!==undefined) items.push({label:`ML ${(ev.ml_prob*100).toFixed(0)}%`, ok:ev.ml_prob>=0.6})
  return (
    <div style={{display:'flex', gap:6, flexWrap:'wrap', marginTop:6}}>
      {items.map((it,i)=>(<span key={i} style={{background: it.ok?'#22c55e15':it.warn?'#f59e0b15':'#ef444415', border:`1px solid ${it.ok?'#22c55e':it.warn?'#f59e0b':'#ef4444'}30`, color: it.ok?'#22c55e':it.warn?'#f59e0b':'#ef4444', padding:'2px 8px', borderRadius:99, fontSize:11, fontWeight:600}}>{it.ok?'✓':it.warn?'⚠':'✗'} {it.label}</span>))}
    </div>
  )
}

function Presence({ presence }: any){
  if(!presence || (!presence.record_a && !presence.record_b)) return null
  const rows=[['A', presence.record_a], ['B', presence.record_b]].filter(([,o])=>o)
  if(!rows.length) return null
  return (
    <div style={{marginTop:8, background:'#1e293b', borderRadius:8, padding:10}}>
      <div style={{fontWeight:600}}>Presence — scope-relative observation (informational only)</div>
      {rows.map(([side,o]:any)=>(
        <div key={side} style={{marginTop:6, fontSize:12}}>
          <div>Record {side} (#{o.record_ref}): <b>{o.record_presence}</b> <span style={{color:'#64748b'}}>({o.basis})</span></div>
          <div style={{color:'#94a3b8', marginTop:2}}>{o.explanation}</div>
          <div style={{color:'#64748b', marginTop:2}}>Scope: {o.scope?.source_a} ↔ {o.scope?.source_b} • {o.scope?.snapshot_a} ↔ {o.scope?.snapshot_b} • completeness {o.scope?.completeness_a}/{o.scope?.completeness_b}</div>
        </div>
      ))}
    </div>
  )
}

export default function Conflicts(){
  const [data, setData]=useState<any[]>([])
  const [total, setTotal]=useState(0)
  const [page, setPage]=useState(1)
  const [search, setSearch]=useState('')
  const [filterRisk, setFilterRisk]=useState('')
  const [filterStatus, setFilterStatus]=useState('pending')
  const [filterField, setFilterField]=useState('')
  const [selected, setSelected]=useState<any>(null)
  const [loading, setLoading]=useState(true)
  const activeJob = typeof window!=='undefined' ? localStorage.getItem('activeJobId') : null
  const activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null

  async function load(p=1){
    setLoading(true)
    try{
      const params:any={ limit:20, page:p }
      if(activeJob) params.job_id=activeJob
      else if(activeLive) params.source_id=activeLive
      if(filterRisk) params.risk_level=filterRisk
      if(filterStatus) params.status=filterStatus
      if(filterField) params.field=filterField
      const r=await api.get('/conflicts', { params })
      let list=Array.isArray(r.data)? r.data : r.data.items||r.data||[]
      if(search){
        const s=search.toLowerCase()
        list=list.filter((c:any)=> String(c.id).includes(s) || (c.conflicting_fields||[]).some((f:any)=> f.field_name?.toLowerCase().includes(s)))
      }
      setData(list); setTotal(list.length)
    }catch{} finally{ setLoading(false)}
  }
  useEffect(()=>{ load(1); setPage(1) },[filterRisk, filterStatus, filterField])
  useEffect(()=>{ load(page) },[page])

  async function openDetail(id:number){
    try{ const r=await api.get(`/conflicts/${id}`); setSelected(r.data) }catch{}
  }

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:8}}>
        <div>
          <h1 style={{fontSize:28, fontWeight:800}}>Conflicts</h1>
          <p style={{color:'#94a3b8', marginTop:4}}>Mode: <b style={{color:'#22c55e'}}>LIVE</b>{activeJob?` • Job #${activeJob}`:activeLive?` • Source #${activeLive}`:''} • Field-level work queue • review only</p>
        </div>
        <span style={{background:'#22c55e15', border:'1px solid #22c55e30', color:'#22c55e', padding:'4px 10px', borderRadius:99, fontSize:12, fontWeight:700}}>● Production • ML</span>
      </div>

      <div style={{background:'#0f172a', border:'1px solid #334155', borderRadius:12, padding:10, marginTop:12, fontSize:12, color:'#94a3b8'}}>
        Policy (backend decision engine): POSSIBLE_MATCH, any HIGH/CRITICAL risk, or missing key fields → MANUAL REVIEW (avoids false merges like John Smith vs John Smyth). Only MATCH + LOW risk + exact trusted ID (or exact email+phone) with zero contradictions is SAFE TO RESOLVE.
      </div>

      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:12, marginTop:12, display:'flex', gap:8, flexWrap:'wrap', alignItems:'center'}}>
        <input placeholder="Search id/field..." value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=> e.key==='Enter' && load(1)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13, minWidth:160}} />
        <select value={filterRisk} onChange={e=>setFilterRisk(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="">All risks</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option>
        </select>
        <select value={filterStatus} onChange={e=>setFilterStatus(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="pending">Pending</option><option value="">All status</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="deferred">Deferred</option>
        </select>
        <select value={filterField} onChange={e=>setFilterField(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="">All fields</option><option value="email">email</option><option value="phone">phone</option><option value="name">name</option><option value="postcode">postcode</option><option value="suburb">suburb</option>
        </select>
        <span style={{color:'#64748b', fontSize:12, marginLeft:'auto'}}>{total} shown • one row per field</span>
      </div>

      {loading ? <div style={{padding:20, color:'#94a3b8'}}>Loading conflicts...</div> : (
        <div style={{display:'grid', gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr', gap:16, marginTop:16}}>
          <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, overflow:'hidden'}}>
            <div style={{display:'grid', gridTemplateColumns:'80px 1fr 90px 90px 90px 90px', gap:8, padding:'10px 14px', background:'#0f172a', color:'#94a3b8', fontSize:11, fontWeight:600}}>
              <span>ID</span><span>Entity • Field</span><span>Source↔Target</span><span>Risk</span><span>Conf</span><span>Status</span>
            </div>
            {data.length===0 ? <div style={{padding:32, textAlign:'center', color:'#64748b'}}>No conflicts — run Live Analysis</div> :
             data.map((c:any)=>{
               const f=(c.conflicting_fields||[])[0]||{}
               return (
                 <div key={c.id} onClick={()=>openDetail(c.id)} style={{display:'grid', gridTemplateColumns:'80px 1fr 90px 90px 90px 90px', gap:8, padding:'10px 14px', borderTop:'1px solid #334155', fontSize:12, cursor:'pointer', background: selected?.id===c.id?'#1e293b':'transparent', borderLeft: selected?.id===c.id?'3px solid #f59e0b':'3px solid transparent', alignItems:'center'}}>
                   <span style={{fontWeight:700}}>#{c.id}</span>
                   <span>#{c.record_a_id}↔#{c.record_b_id} • <b>{f.field_name||'-'}</b></span>
                   <span style={{color:'#94a3b8'}}>{c.record_a_id}↔{c.record_b_id}</span>
                   <span style={{background: c.risk_level==='low'?'#22c55e':c.risk_level==='medium'?'#f59e0b':'#ef4444', color:'white', padding:'2px 6px', borderRadius:99, fontWeight:700, textAlign:'center', fontSize:11, textTransform:'uppercase'}}>{c.risk_level}</span>
                   <span style={{color:'#22c55e', fontWeight:700}}>{(Math.min(c.confidence, 0.999)*100).toFixed(1)}%</span>
                   <span style={{textTransform:'capitalize', color:'#94a3b8'}}>{{pending:'OPEN (pending)', approved:'RESOLVED', modified:'RESOLVED', rejected:'REJECTED', deferred:'DEFERRED'}[(c.resolution_status||c.status)] || c.resolution_status || c.status}</span>
                 </div>
               )
             })}
            <div style={{display:'flex', justifyContent:'space-between', padding:10, borderTop:'1px solid #334155'}}>
              <button disabled={page<=1} onClick={()=>setPage(p=>p-1)} style={{background:'transparent', border:'1px solid #334155', color:'#e2e8f0', padding:'4px 10px', borderRadius:6}}>Prev</button>
              <span style={{color:'#64748b', fontSize:12}}>Page {page}</span>
              <button onClick={()=>setPage(p=>p+1)} style={{background:'transparent', border:'1px solid #334155', color:'#e2e8f0', padding:'4px 10px', borderRadius:6}}>Next</button>
            </div>
          </div>

          <div style={{background:'#0f172a', border:'1px solid #334155', borderRadius:12, padding:14, height:'fit-content', position:'sticky', top:16}}>
            <h3 style={{fontWeight:700, fontSize:13}}>{selected?`CONFLICT #${selected.id}`:'Select a conflict'}</h3>
            {selected ? (
              <div style={{marginTop:10, fontSize:12}}>
                <div>Entity: <b>#{selected.entity?.record_a_id} ↔ #{selected.entity?.record_b_id}</b> • Field: <b style={{color:'#f59e0b'}}>{(selected.field||'').toUpperCase()}</b></div>
                <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:8, marginTop:8}}>
                  <div style={{background:'#1e293b', borderRadius:8, padding:10}}>
                    <div style={{color:'#3b82f6', fontWeight:700, fontSize:11}}>SOURCE A • #{selected.source_record?.id}</div>
                    <div style={{fontWeight:700, marginTop:4}}>{selected.source_record?.data?.name||selected.source_record?.data?.title||'—'}</div>
                    <div style={{color:'#94a3b8'}}>{selected.field_values?.a ?? JSON.stringify(selected.source_record?.data||{}).slice(0,60)}</div>
                  </div>
                  <div style={{background:'#1e293b', borderRadius:8, padding:10}}>
                    <div style={{color:'#8b5cf6', fontWeight:700, fontSize:11}}>SOURCE B • #{selected.target_record?.id}</div>
                    <div style={{fontWeight:700, marginTop:4}}>{selected.target_record?.data?.name||selected.target_record?.data?.title||'—'}</div>
                    <div style={{color:'#94a3b8'}}>{selected.field_values?.b ?? JSON.stringify(selected.target_record?.data||{}).slice(0,60)}</div>
                  </div>
                </div>
                <div style={{marginTop:8, background:'#1e293b', borderRadius:8, padding:10}}>
                  <div>Entity match: <b style={{color:'#22c55e'}}>{(Math.min(selected.match_confidence, 0.999)*100).toFixed(1)}%</b> • Model v{selected.model_version} • Job #{selected.job_id} ({selected.job_status})</div>
                  <Ticks ev={selected.match?.evidence || selected.evidence} />
                </div>
                <div style={{marginTop:8, background:'#1e293b', borderRadius:8, padding:10}}>
                  <div style={{fontWeight:600}}>Conflict — values differ after normalization</div>
                  <div style={{marginTop:4}}>A: <b>{String(selected.field_values?.a ?? 'NULL')}</b> • B: <b>{String(selected.field_values?.b ?? 'NULL')}</b></div>
                  <div style={{marginTop:6}}>Recommendation: <b>{selected.recommendation}</b> <span style={{color:'#64748b'}}>({selected.evidence?.conflict_reason||''})</span></div>
                  <div>Risk: <b style={{textTransform:'uppercase'}}>{selected.risk}</b> <span style={{color:'#64748b'}}>({selected.evidence?.risk_reason||''})</span> • Status: <b style={{textTransform:'capitalize'}}>{selected.status}</b></div>
                </div>
                <ResolutionPanel conflict={selected} onUpdate={(c:any)=>{ setSelected(c); load(1) }} />
                <Presence presence={selected.presence} />
                <Timeline conflictId={selected.id} />
                <button onClick={()=>setSelected(null)} style={{marginTop:10, background:'#334155', color:'white', border:'none', padding:'6px 10px', borderRadius:6, fontSize:12, width:'100%'}}>Close</button>
              </div>
            ) : <div style={{color:'#64748b', fontSize:12, marginTop:8}}>Click a row to review, resolve, dry-run and push. One conflict at a time.</div>}
          </div>
        </div>
      )}
    </div>
  )
}
