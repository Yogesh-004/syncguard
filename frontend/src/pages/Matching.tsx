import { useEffect, useState } from 'react'
import api from '../services/api-client'

function Ticks({ evidence }: any){
  const items:any[]=[]
  const fs = evidence?.field_scores
  if(fs){
    Object.entries(fs).forEach(([k,v]:any)=> items.push({label:`${k} ${(Number(v)*100).toFixed(0)}%`, ok:Number(v)>=0.5}))
  } else {
    const core=['email','phone','name']
    core.forEach(k=>{
      const v=evidence?.[k]
      if(v?.match) items.push({label:`${k} ${(v.score*100).toFixed(0)}%`, ok:true})
      else if(v) items.push({label:k, ok:false, warn:v.reason==='missing_field'})
    })
  }
  if(evidence?.ml_prob!==undefined) items.push({label:`ML ${(evidence.ml_prob*100).toFixed(0)}%`, ok:evidence.ml_prob>=0.6})
  return (
    <div style={{display:'flex', gap:6, flexWrap:'wrap', fontSize:11, marginTop:6}}>
      {items.map((it:any,i:number)=>(<span key={i} style={{color: it.ok?'#22c55e':it.warn?'#f59e0b':'#ef4444'}}>{it.ok?'✓':it.warn?'⚠':'✗'} {it.label}</span>))}
    </div>
  )
}

export default function Matching(){
  const [items, setItems]=useState<any[]>([])
  const [total, setTotal]=useState(0)
  const [counts, setCounts]=useState<any>({})
  const [thresholds, setThresholds]=useState<any>({})
  const [page, setPage]=useState(1)
  const [search, setSearch]=useState('')
  const [decision, setDecision]=useState('')
  const [selected, setSelected]=useState<any>(null)
  const [loading, setLoading]=useState(false)
  const activeJob = typeof window!=='undefined' ? localStorage.getItem('activeJobId') : null
  const activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null

  async function load(p=1){
    setLoading(true)
    try{
      const params:any={ limit:20, page:p }
      if(activeJob) params.job_id=activeJob
      else if(activeLive) params.source_id=activeLive
      if(['MATCH','POSSIBLE_MATCH','NO_MATCH'].includes(decision)) params.decision=decision
      const r=await api.get('/matches', { params })
      let list=r.data.items||[]
      if(decision==='AUTO') list=list.filter((m:any)=> m.auto_resolvable)
      else if(decision==='MANUAL') list=list.filter((m:any)=> !m.auto_resolvable)
      else if(decision==='HIGH_RISK') list=list.filter((m:any)=> (m.risk||m.evidence?.risk)==='HIGH' || (m.risk||m.evidence?.risk)==='CRITICAL')
      if(search){
        const s=search.toLowerCase()
        list=list.filter((m:any)=> String(m.record_a_id).includes(s) || String(m.record_b_id).includes(s) || String(m.id).includes(s) || JSON.stringify(m.evidence||'').toLowerCase().includes(s))
      }
      setItems(list); setTotal(r.data.total ?? list.length)
      setCounts(r.data.counts||{}); setThresholds(r.data.thresholds||{})
    }catch{} finally{ setLoading(false)}
  }
  useEffect(()=>{ load(1); setPage(1) },[decision])
  useEffect(()=>{ load(page) },[page])

  async function openDetail(id:number){
    try{ const r=await api.get(`/matches/${id}`); setSelected(r.data) }catch{}
  }

  return (
    <div>
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', flexWrap:'wrap', gap:8}}>
        <div>
          <h1 style={{fontSize:28, fontWeight:800}}>Matching</h1>
          <p style={{color:'#94a3b8', marginTop:4}}>Mode: <b style={{color:'#22c55e'}}>LIVE</b>{activeJob?` • Job #${activeJob}`:activeLive?` • Source #${activeLive}`:''} • Model v1.0.0 • Persisted DB matches (read-only)</p>
        </div>
        <span style={{background:'#22c55e15', border:'1px solid #22c55e30', color:'#22c55e', padding:'4px 10px', borderRadius:99, fontSize:12, fontWeight:700}}>● Production • ML</span>
      </div>

      <div style={{display:'grid', gridTemplateColumns:'repeat(auto-fit,minmax(130px,1fr))', gap:8, marginTop:12}}>
        {[['MATCH', counts.MATCH, '#22c55e'], ['POSSIBLE', counts.POSSIBLE_MATCH, '#f59e0b'], ['NO MATCH', counts.NO_MATCH, '#64748b'], ['AUTO-RESOLVABLE', items.filter((m:any)=>m.auto_resolvable).length, '#06b6d4'], ['MANUAL REVIEW', items.filter((m:any)=>!m.auto_resolvable).length, '#f59e0b']].map(([label, val, color]:any)=>(
          <div key={label} style={{background:'#1e293b', border:'1px solid #334155', borderRadius:10, padding:10, textAlign:'center'}}>
            <div style={{fontSize:10, color:'#94a3b8'}}>{label}</div>
            <div style={{fontSize:20, fontWeight:800, color}}>{val ?? '?'}</div>
          </div>
        ))}
      </div>
      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:12, marginTop:12, display:'flex', gap:8, flexWrap:'wrap', alignItems:'center'}}>
        <input placeholder="Search match/record id..." value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=> e.key==='Enter' && load(1)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13, minWidth:200}} />
        <select value={decision} onChange={e=>setDecision(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:8, fontSize:13}}>
          <option value="">ALL ({total})</option><option value="MATCH">MATCH ({counts.MATCH ?? '?'})</option><option value="POSSIBLE_MATCH">POSSIBLE ({counts.POSSIBLE_MATCH ?? '?'})</option><option value="NO_MATCH">NO MATCH ({counts.NO_MATCH ?? '?'})</option><option value="AUTO">AUTO-RESOLVABLE</option><option value="MANUAL">MANUAL REVIEW</option><option value="HIGH_RISK">HIGH RISK</option>
        </select>
        <button onClick={()=>load(page)} disabled={loading} style={{background:'#3b82f6', color:'white', border:'none', padding:'6px 12px', borderRadius:8, fontWeight:700, fontSize:13}}>Refresh</button>
        <a href="/live" style={{border:'1px solid #334155', padding:'6px 12px', borderRadius:8, fontSize:13}}>New analysis</a>
        <span style={{color:'#64748b', fontSize:12, marginLeft:'auto'}}>
          {thresholds.MATCH!==undefined ? `MATCH ≥ ${thresholds.MATCH} • POSSIBLE ${thresholds.POSSIBLE_MATCH}–${thresholds.MATCH} • NO MATCH < ${thresholds.POSSIBLE_MATCH} (server config)` : `${total} persisted matches`}
        </span>
      </div>

      {loading ? <div style={{padding:20, color:'#94a3b8'}}>Loading DB matches...</div> : (
        <div style={{display:'grid', gridTemplateColumns: selected ? '1.2fr 0.8fr' : '1fr', gap:16, marginTop:16}}>
          <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, overflow:'hidden'}}>
            <div style={{display:'grid', gridTemplateColumns:'80px 1fr 100px 90px 90px 80px 90px', gap:8, padding:'10px 14px', background:'#0f172a', color:'#94a3b8', fontSize:11, fontWeight:600}}>
              <span>Match</span><span>Entity pair</span><span>Decision</span><span>ML score</span><span>Final conf</span><span>Risk</span><span>Auto</span>
            </div>
            {items.length===0 ? <div style={{padding:32, textAlign:'center', color:'#64748b'}}>No persisted matches — run Live Analysis first</div> :
             items.map((m:any)=>{
               const top = topEvidence(m.evidence)
               return (
               <div key={m.id} onClick={()=>openDetail(m.id)} style={{display:'grid', gridTemplateColumns:'80px 1fr 100px 90px 90px 80px 90px', gap:8, padding:'10px 14px', borderTop:'1px solid #334155', fontSize:12, cursor:'pointer', background: selected?.id===m.id?'#1e293b':'transparent', borderLeft: selected?.id===m.id?'3px solid #22c55e':'3px solid transparent', alignItems:'center'}}>
                 <span style={{fontWeight:700}}>#{m.id}</span>
                 <span>#{m.record_a_id} ↔ #{m.record_b_id} <span style={{color:'#64748b'}}>• job {m.job||'-'}</span><div style={{color:'#64748b', fontSize:11}}>{top}</div></span>
                 <span style={{background: m.decision==='MATCH'?'#22c55e15':m.decision==='NO_MATCH'?'#64748b15':'#f59e0b15', color: m.decision==='MATCH'?'#22c55e':m.decision==='NO_MATCH'?'#94a3b8':'#f59e0b', padding:'2px 8px', borderRadius:99, fontWeight:700, textAlign:'center', fontSize:11}}>{m.decision||'MATCH'}{m.evidence?.sampled?' • sample':''}</span>
                 <span style={{color:'#94a3b8'}}>{((m.model_score ?? m.confidence)*100).toFixed(1)}%</span>
                 <span style={{color: m.confidence>0.8?'#22c55e':'#f59e0b', fontWeight:700}}>{(Math.min(m.confidence, 0.999)*100).toFixed(1)}%</span>
                 <span style={{textTransform:'uppercase', fontSize:11, fontWeight:700, color: (m.risk||m.evidence?.risk)==='LOW'?'#22c55e':((m.risk||m.evidence?.risk)==='CRITICAL'||(m.risk||m.evidence?.risk)==='HIGH')?'#ef4444':'#f59e0b'}}>{m.risk||m.evidence?.risk||'—'}</span>
                 <span style={{color: m.auto_resolvable?'#22c55e':'#64748b', fontWeight:700}}>{m.auto_resolvable?'YES':'NO'}</span>
               </div>
             )})}
            <div style={{display:'flex', justifyContent:'space-between', padding:10, borderTop:'1px solid #334155'}}>
              <button disabled={page<=1} onClick={()=>setPage(p=>p-1)} style={{background:'transparent', border:'1px solid #334155', color:'#e2e8f0', padding:'4px 10px', borderRadius:6}}>Prev</button>
              <span style={{color:'#64748b', fontSize:12}}>Page {page}</span>
              <button onClick={()=>setPage(p=>p+1)} style={{background:'transparent', border:'1px solid #334155', color:'#e2e8f0', padding:'4px 10px', borderRadius:6}}>Next</button>
            </div>
          </div>

          <div style={{background:'#0f172a', border:'1px solid #334155', borderRadius:12, padding:14, height:'fit-content', position:'sticky', top:16}}>
            <h3 style={{fontWeight:700, fontSize:13}}>{selected?`${selected.decision||'MATCH'} #${selected.id}`:'Select a match'}</h3>
            {selected ? (
              <div style={{marginTop:10, fontSize:12}}>
                <div>Source: <b>#{selected.record_a?.id}</b> {selected.record_a?.data?.name||''} <span style={{color:'#64748b'}}>({selected.record_a?.source_record_id})</span></div>
                <div style={{marginTop:4}}>Target: <b>#{selected.record_b?.id}</b> {selected.record_b?.data?.name||''} <span style={{color:'#64748b'}}>({selected.record_b?.source_record_id})</span></div>
                <div style={{marginTop:8}}>Decision: <b style={{color: selected.decision==='MATCH'?'#22c55e':'#f59e0b'}}>{selected.decision}</b> • Confidence <b style={{color:'#22c55e'}}>{(Math.min(selected.confidence, 0.999)*100).toFixed(1)}%</b> • Model score {(selected.model_score*100).toFixed(1)}%</div>
                <div style={{marginTop:4}}>Risk: <b style={{textTransform:'uppercase'}}>{selected.risk||'—'}</b> <span style={{color:'#64748b'}}>{selected.risk_reason||''}</span> • Auto-resolvable: <b style={{color: selected.auto_resolvable?'#22c55e':'#f59e0b'}}>{selected.auto_resolvable?'YES':'NO'}</b> • {selected.recommendation||''}</div>
                {selected.penalties && Object.keys(selected.penalties).length>0 && <div style={{color:'#f59e0b', fontSize:11, marginTop:4}}>Penalties: {Object.entries(selected.penalties).map(([k,v]:any)=>`${k} ${typeof v==='number'?'-'+v:v}`).join(' • ')}</div>}
                <div style={{color:'#64748b', marginTop:4}}>Model: SyncGuard Matcher v{selected.model_version} • Job #{selected.job_id} ({selected.job_status})</div>
                <div style={{color:'#64748b', fontSize:11, marginTop:4}}>Candidate because: {(selected.evidence?.blocking_reasons||['exhaustive']).join(' + ')} (blocking evidence — evaluation only, not a match signal)</div>
                <div style={{fontWeight:600, marginTop:8}}>Field evidence</div>
                <Ticks evidence={selected.evidence} />
                {selected.field_evidence?.fields?.map((f:any)=>(
                  <div key={f.field} style={{display:'flex', justifyContent:'space-between', background:'#1e293b', padding:'4px 8px', borderRadius:6, marginTop:4, fontSize:11}}>
                    <span style={{textTransform:'capitalize'}}>{f.field.replace(/_/g,' ')}</span>
                    <span style={{color: f.status==='EXACT_MATCH'?'#22c55e':f.status==='STRONG_MATCH'?'#22c55e':f.status==='PARTIAL_MATCH'?'#f59e0b':f.status==='MISMATCH'?'#ef4444':'#64748b', fontWeight:600}}>{(f.similarity*100).toFixed(1)}% {f.status.replace(/_/g,' ')}</span>
                  </div>
                ))}
                <div style={{color:'#64748b', fontSize:11, marginTop:8}}>WHY: {whyText(selected.evidence)} • Verification: {(selected.evidence?.verification_status||'NEEDS_REVIEW').replace(/_/g,' ')}</div>
                <button onClick={()=>setSelected(null)} style={{marginTop:10, background:'#334155', color:'white', border:'none', padding:'6px 10px', borderRadius:6, fontSize:12, width:'100%'}}>Close</button>
              </div>
            ) : <div style={{color:'#64748b', fontSize:12, marginTop:8}}>Click a row to see source/target records, field evidence, and why it matched. Source records stay intact — the match is a relationship.</div>}
          </div>
        </div>
      )}
    </div>
  )
}

function topEvidence(ev:any){
  if(!ev) return ''
  const fe = ev.field_evidence?.fields || []
  const pos = fe.filter((f:any)=>['EXACT_MATCH','STRONG_MATCH'].includes(f.status)).map((f:any)=>f.field)
  const neg = fe.filter((f:any)=>f.status==='MISMATCH').map((f:any)=>f.field)
  const parts=[]
  if(pos.length) parts.push('✓ '+pos.slice(0,3).join(','))
  if(neg.length) parts.push('✗ '+neg.slice(0,2).join(','))
  return parts.join(' ') || '—'
}

function whyText(ev:any){
  if(!ev) return ''
  const parts=[]
  if(ev.email?.match) parts.push('Email exact match')
  if(ev.phone?.match) parts.push('phone normalized exact')
  if(ev.name) parts.push(`name ${(ev.name.score*100).toFixed(0)}% similarity`)
  return parts.join(' • ') || 'ML probability above threshold'
}
