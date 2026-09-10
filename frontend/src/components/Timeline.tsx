import { useEffect, useState } from 'react'
import api from '../services/api-client'

export default function Timeline({ conflictId }: any){
 const [items, setItems]=useState<any[]>([])
 useEffect(()=>{
  api.get(`/conflicts/${conflictId}/audit`).then(r=>setItems(r.data||[])).catch(()=>{})
 },[conflictId])
 if(!items.length) return <div style={{color:'#64748b', fontSize:11, marginTop:8}}>No audit events yet.</div>
 return (
  <div style={{marginTop:8, background:'#1e293b', borderRadius: 0, padding:10}}>
   <div style={{fontWeight:700, fontSize:12}}>Timeline - database-backed</div>
   {items.map((a:any)=>(
    <div key={a.id} style={{display:'flex', gap:8, marginTop:6, fontSize:11}}>
     <span style={{color:'#64748b', minWidth:60}}>{a.created_at ? new Date(a.created_at).toLocaleTimeString() : ''}</span>
     <span style={{fontWeight:600}}>{a.action}</span>
     <span style={{color:'#64748b'}}>{a.entity_type} #{a.entity_id}</span>
    </div>
   ))}
  </div>
 )
}
