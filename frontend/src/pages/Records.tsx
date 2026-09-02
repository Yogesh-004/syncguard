import { useState, useEffect } from 'react'
import api from '../services/api-client'

export default function Records() {
  const [filter, setFilter] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [liveInfo, setLiveInfo] = useState<string>('')
  useEffect(() => {
    async function load(){
      let activeLive = typeof window!=='undefined' ? localStorage.getItem('activeLiveSourceId') : null
      if(!activeLive){
        try{ const s=await api.get('/sources'); const liveSrc=(s.data as any[]).find((x:any)=> x.config?.live); if(liveSrc){ activeLive=String(liveSrc.id); localStorage.setItem('activeLiveSourceId', activeLive) } }catch{}
      }
      const q = activeLive ? `/records?limit=500&source_id=${activeLive}` : '/records?limit=50'
      if(activeLive) setLiveInfo(`Live dataset #${activeLive} isolated — training data hidden`)
      else setLiveInfo('Training data (benchmark) — upload via Live Analysis to isolate')
      api.get(q).then(r=>setData(r.data)).catch(()=>{}).finally(()=>setLoading(false))
    }
    load()
  }, [])
  const items = (data?.items || []).filter((r:any)=> !filter || String(r.source_id).includes(filter) || r.source_record_id.includes(filter) || r.data?.name?.toLowerCase().includes(filter.toLowerCase()))
  return (
    <div>
      <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 8 }}>Records</h1>
      <p style={{ color:'#94a3b8', marginBottom: 4 }}>{data ? `${data.total} total • ${liveInfo}` : 'Live from API — fallback to demo.json if offline'}</p>
      {liveInfo && <div style={{background: liveInfo.includes('Live dataset') ? '#22c55e15' : '#334155', border:`1px solid ${liveInfo.includes('Live dataset') ? '#22c55e30' : '#334155'}`, color: liveInfo.includes('Live dataset') ? '#22c55e' : '#94a3b8', padding:'6px 10px', borderRadius:8, fontSize:12, marginBottom:12}}>{liveInfo}</div>}
      <input placeholder="Filter by source / id / name..." value={filter} onChange={e=>setFilter(e.target.value)} style={{ background:'#1e293b', border:'1px solid #334155', color:'#e2e8f0', padding:'8px 16px', borderRadius:8, width:300, marginBottom:16 }} />
      {loading ? <p>Loading...</p> : (
        <div style={{ background:'#1e293b', borderRadius:12, border:'1px solid #334155', overflow:'auto' }}>
          <table style={{ width:'100%', borderCollapse:'collapse', fontSize:14 }}>
            <thead><tr style={{ borderBottom:'1px solid #334155', color:'#94a3b8' }}><th style={{padding:12,textAlign:'left'}}>ID</th><th style={{padding:12,textAlign:'left'}}>Source</th><th style={{padding:12,textAlign:'left'}}>Record</th><th style={{padding:12,textAlign:'left'}}>Name</th><th style={{padding:12,textAlign:'left'}}>Email</th><th style={{padding:12,textAlign:'left'}}>Phone</th><th style={{padding:12,textAlign:'left'}}>Amount</th></tr></thead>
            <tbody>
              {items.length===0 ? <tr><td colSpan={7} style={{padding:40,textAlign:'center',color:'#64748b'}}>No records — seed via `python scripts/seed_live.py`</td></tr> :
               items.map((r:any)=><tr key={r.id} style={{borderBottom:'1px solid #1e293b'}}>
                 <td style={{padding:10}}>{r.id}</td><td style={{padding:10}}>{r.source_id}</td><td style={{padding:10}}>{r.source_record_id}</td>
                 <td style={{padding:10}}>{r.data?.name}</td><td style={{padding:10}}>{r.data?.email}</td><td style={{padding:10}}>{r.data?.phone ?? 'NULL'}</td><td style={{padding:10}}>{r.data?.amount ?? r.data?.transaction_amount}</td>
               </tr>)}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
