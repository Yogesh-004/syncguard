import { useEffect, useState } from 'react'
import api from '../services/api-client'

export default function ResolutionPanel({ conflict, onUpdate }: any){
  const [resolutions, setResolutions]=useState<any[]>([])
  const [editVal, setEditVal]=useState('')
  const [reason, setReason]=useState('')
  const [msg, setMsg]=useState('')
  const [dry, setDry]=useState<any>(null)
  const [sync, setSync]=useState<any>(null)
  const [busy, setBusy]=useState(false)

  async function load(){
    try{ const r=await api.get(`/conflicts/${conflict.id}/resolutions`); setResolutions(r.data||[]) }catch{}
  }
  useEffect(()=>{ load(); setDry(null); setSync(null); setMsg('') },[conflict.id])
  const latest = resolutions[resolutions.length-1]

  async function act(action:string, extra:any={}){
    setBusy(true); setMsg('')
    try{
      await api.post(`/conflicts/${conflict.id}/resolve`, { action, reason: reason||undefined, ...extra })
      const c=await api.get(`/conflicts/${conflict.id}`)
      onUpdate(c.data); await load()
      setMsg(`${action} saved — resolution persisted, originals preserved`)
    }catch(e:any){ setMsg(`Failed: ${e?.response?.data?.detail || e.message}`) } finally{ setBusy(false) }
  }

  async function doDry(){
    if(!latest) return
    setBusy(true)
    try{
      const r=await api.post(`/resolutions/${latest.id}/dry-run`)
      setDry(r.data)
      setMsg('Dry run complete — destination NOT modified')
    }catch(e:any){ setMsg(`Dry run failed: ${e?.response?.data?.detail || e.message}`) } finally{ setBusy(false) }
  }

  async function doPush(){
    if(!latest) return
    setBusy(true)
    try{
      const r=await api.post(`/resolutions/${latest.id}/push`, { confirm: true })
      setSync(r.data)
      const s=await api.get(`/sync-jobs/${r.data.sync_job_id}`)
      setSync({ ...r.data, detail: s.data })
      setMsg(r.data.result)
      const c=await api.get(`/conflicts/${conflict.id}`)
      onUpdate(c.data)
    }catch(e:any){ setMsg(`Push failed: ${e?.response?.data?.detail || e.message}`) } finally{ setBusy(false) }
  }

  const resolved = conflict.resolution_status && conflict.resolution_status!=='pending'
  const fv = conflict.field_values || {}

  return (
    <div style={{marginTop:8, background:'#1e293b', borderRadius:8, padding:10}}>
      <div style={{fontWeight:700}}>Resolution</div>
      {!resolved ? (
        <>
          <div style={{display:'flex', gap:6, flexWrap:'wrap', marginTop:8}}>
            <button disabled={busy} onClick={()=>act('USE_SOURCE_A')} style={btn('#22c55e')}>Use Source A</button>
            <button disabled={busy} onClick={()=>act('USE_SOURCE_B')} style={btn('#3b82f6')}>Use Source B</button>
            <button disabled={busy} onClick={()=>act('REJECT')} style={btn('#ef4444')}>Reject</button>
            <button disabled={busy} onClick={()=>act('DEFER')} style={btn('#64748b')}>Defer</button>
          </div>
          <div style={{display:'flex', gap:6, marginTop:8}}>
            <input placeholder={`New value for ${conflict.field||'field'}...`} value={editVal} onChange={e=>setEditVal(e.target.value)} style={{flex:1, background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:6, fontSize:12}} />
            <button disabled={busy || !editVal} onClick={()=>act('MANUAL_EDIT', { modified_values: { [conflict.field||'value']: editVal } })} style={btn('#8b5cf6')}>Save edit</button>
          </div>
          <input placeholder="Reason (optional)..." value={reason} onChange={e=>setReason(e.target.value)} style={{width:'100%', background:'#0f172a', border:'1px solid #334155', color:'white', padding:'6px 10px', borderRadius:6, fontSize:12, marginTop:8}} />
          <div style={{color:'#64748b', fontSize:11, marginTop:6}}>A: {String(fv.a ?? 'NULL')} • B: {String(fv.b ?? 'NULL')} — manual edit is validated by field type (email/phone/date/numeric).</div>
        </>
      ) : (
        <div style={{fontSize:12, marginTop:6}}>
          <div>Action: <b>{latest?.action}</b> • Value: <b style={{color:'#22c55e'}}>{String(latest?.resolved_value ?? '—')}</b> {latest?.selected_source?`(from ${latest.selected_source})`:''}</div>
          {latest && ['approved','modified'].includes(latest.status) && latest.resolved_value!==null && latest.resolved_value!==undefined && (
            <div style={{display:'flex', gap:6, marginTop:8}}>
              <button disabled={busy} onClick={doDry} style={btn('#f59e0b')}>Run Dry Run</button>
              <button disabled={busy || !dry} onClick={doPush} style={btn('#22c55e')}>Confirm Push</button>
            </div>
          )}
          {dry && (
            <div style={{background:'#0f172a', borderRadius:6, padding:8, marginTop:8, fontSize:11}}>
              <div style={{fontWeight:700}}>DRY RUN — {dry.destination} (no write)</div>
              <div>Destination: <b>{dry.destination}</b> • Field: {dry.field} • Op: {dry.operation}</div>
              <div>Current: {String(dry.current_value ?? 'NULL')} → Proposed: <b style={{color:'#22c55e'}}>{String(dry.proposed_value ?? 'NULL')}</b></div>
              <div style={{color:'#22c55e'}}>{dry.result}</div>
            </div>
          )}
          {sync && (
            <div style={{background:'#0f172a', borderRadius:6, padding:8, marginTop:8, fontSize:11}}>
              <div style={{fontWeight:700}}>SYNC — {sync.destination}{sync.destination && String(sync.destination).startsWith('MOCK') ? ' (MOCK)' : ''}</div>
              {sync.detail?.review ? (
                <>
                  <div>Outcome: <b>{sync.detail.review.outcome}</b> • Verification: <b>{sync.detail.review.verification}</b></div>
                  <div style={{color:'#94a3b8', marginTop:2}}>{sync.detail.review.explanation}</div>
                  <div style={{color:'#94a3b8'}}>{sync.detail.review.verification_explanation}</div>
                  {sync.detail.review.requires_human_action && <div style={{color:'#f59e0b', fontWeight:700, marginTop:2}}>Human action required.</div>}
                  {sync.detail.review.retry_allowed && <div style={{color:'#3b82f6', marginTop:2}}>Retry is allowed under the existing policy.</div>}
                </>
              ) : (
                <>
                  <div>Status: <b style={{color: sync.status==='SUCCESS'?'#22c55e':'#ef4444'}}>{sync.status}</b> • Verified: {String(sync.verified)} • Attempts: {sync.attempt_count}</div>
                  <div style={{color: sync.status==='SUCCESS'?'#22c55e':'#ef4444'}}>{sync.result}</div>
                  {sync.error && <div style={{color:'#ef4444'}}>Error: {sync.error}</div>}
                </>
              )}
            </div>
          )}
        </div>
      )}
      {msg && <div style={{color:'#94a3b8', fontSize:11, marginTop:6}}>{msg}</div>}
    </div>
  )
}

function btn(color:string){
  return { background: color, color:'white', border:'none', padding:'6px 10px', borderRadius:6, fontWeight:700, fontSize:12, cursor:'pointer' } as any
}
