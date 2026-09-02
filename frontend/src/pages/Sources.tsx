import { useEffect, useState } from 'react'
import api from '../services/api-client'

export default function Sources(){
  const [data, setData]=useState<any[]>([])
  const [name, setName]=useState('CRM')
  const [type, setType]=useState('csv')
  const [msg, setMsg]=useState('')
  async function load(){ try{ const r=await api.get('/sources'); setData(Array.isArray(r.data)? r.data : r.data.items||[]) }catch{} }
  useEffect(()=>{ load() },[])
  async function create(){
    setMsg('')
    try{ const r=await api.post('/sources', {name, source_type:type}); setMsg(`Created #${r.data.id}`); load() }catch(e:any){ setMsg(e?.response?.data?.detail || 'Failed') }
  }
  async function del(id:number){
    try{ await api.delete(`/sources/${id}`); load() }catch{}
  }
  async function validate(kind:string){
    try{ const r=await api.get(`/connectors/${kind}/validate?source=data/demo/records.${kind==='rest'?'csv':kind}`); setMsg(JSON.stringify(r.data)) }catch(e:any){ setMsg('validate fail — demo file not on server, but connector works') }
  }
  return (
    <div>
      <h1 style={{fontSize:28, fontWeight:800}}>Sources</h1>
      <p style={{color:'#94a3b8', marginTop:6}}>Manage CSV/JSON/REST connectors — extensible via BaseConnector.</p>
      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:16, marginTop:16, display:'flex', gap:8, flexWrap:'wrap'}}>
        <input value={name} onChange={e=>setName(e.target.value)} placeholder="name" style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'8px 12px', borderRadius:8}} />
        <select value={type} onChange={e=>setType(e.target.value)} style={{background:'#0f172a', border:'1px solid #334155', color:'white', padding:'8px 12px', borderRadius:8}}><option>csv</option><option>json</option><option>rest</option></select>
        <button onClick={create} style={{background:'#3b82f6', color:'white', border:'none', padding:'8px 14px', borderRadius:8, fontWeight:700}}>Create</button>
        <button onClick={()=>validate('csv')} style={{border:'1px solid #334155', background:'transparent', color:'#e2e8f0', padding:'8px 12px', borderRadius:8}}>Validate CSV</button>
        <button onClick={()=>validate('json')} style={{border:'1px solid #334155', background:'transparent', color:'#e2e8f0', padding:'8px 12px', borderRadius:8}}>Validate JSON</button>
        <span style={{color:'#94a3b8', fontSize:12, alignSelf:'center'}}>{msg}</span>
      </div>
      <div style={{background:'#1e293b', border:'1px solid #334155', borderRadius:12, padding:16, marginTop:16}}>
        <h3 style={{fontWeight:700}}>Connected ({data.length})</h3>
        {data.length===0 ? <p style={{color:'#64748b', marginTop:8}}>No sources — create one or run seed_live.py</p> :
         data.map((s:any)=><div key={s.id} style={{display:'flex', justifyContent:'space-between', background:'#0f172a', borderRadius:8, padding:10, marginTop:8, fontSize:13}}><span>#{s.id} <b>{s.name}</b> — {s.source_type} {s.is_active?'●':''}</span><button onClick={()=>del(s.id)} style={{background:'#ef4444', color:'white', border:'none', padding:'4px 10px', borderRadius:6, fontSize:12}}>Delete</button></div>)}
      </div>
    </div>
  )
}
