import { useEffect, useState } from 'react'
import api from '../services/api-client'

export default function Jobs(){
  const [data, setData]=useState<any>(null)
  const [filter, setFilter]=useState('')
  const [creating, setCreating]=useState(false)
  async function load(){
    try{
      const activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null
      const srcQ = activeLive ? `&source_id=${activeLive}` : ''
      const r=await api.get(`/jobs?limit=20${filter?`&status=${filter}`:''}${srcQ}`); setData(r.data)
    }catch{}
  }
  useEffect(()=>{ load(); const iv=setInterval(load,3000); return ()=>clearInterval(iv) },[filter])
  async function create(){
    setCreating(true)
    try{ await api.post('/jobs', {job_type:'reconciliation', source_id:'1', idempotency_key:`job-${Date.now()}`}); load() }catch{} finally{ setCreating(false)}
  }
  const items=data?.items || []
  return (
    <div>
      <h1 style={{fontSize:28, fontWeight:800}}>Jobs</h1>
      <p style={{color:'#94a3b8', marginTop:6}}>Background reconciliation/sync — 202 Accepted → polling, retries 5×, idempotency UNIQUE.</p>
      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:16, marginTop:16, display:'flex', gap:8}}>
        <select value={filter} onChange={e=>setFilter(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'8px 12px', borderRadius:8}}><option value="">all</option><option>queued</option><option>processing</option><option>completed</option><option>failed</option></select>
        <button onClick={load} style={{border:'1px solid #334155', background:'transparent', color:'#e2e8f0', padding:'8px 12px', borderRadius:8}}>Refresh</button>
        <button onClick={create} disabled={creating} style={{background:'#3b82f6', color:'white', border:'none', padding:'8px 14px', borderRadius:8, fontWeight:700}}>{creating?'Creating...':'New Job'}</button>
        <span style={{color:'#94a3b8', fontSize:12, alignSelf:'center'}}>{data ? `${data.total} total` : ''} — auto-refresh 3s</span>
      </div>
      <div style={{marginTop:16}}>
        {items.length===0 ? <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:24, color:'#64748b'}}>No jobs — create one or POST /reconciliation</div> :
         items.map((j:any)=>(
           <div key={j.id} style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:16, marginBottom:12}}>
             <div style={{display:'flex', justifyContent:'space-between'}}><b>Job #{j.id}</b> <span style={{color: j.status==='completed'?'#22c55e': j.status==='failed'?'#ef4444':'#f59e0b'}}>{j.status}</span></div>
             <div style={{fontSize:13, color:'#94a3b8', marginTop:6}}>{j.job_type} — progress {j.progress}% — {j.created_at ? new Date(j.created_at).toLocaleString() : ''}</div>
             <div style={{background:'#0f172a', borderRadius:999, height:8, marginTop:8, overflow:'hidden'}}><div style={{width:`${j.progress}%`, height:'100%', background: j.status==='failed'?'#ef4444':'#3b82f6'}}/></div>
           </div>
         ))}
      </div>
    </div>
  )
}
