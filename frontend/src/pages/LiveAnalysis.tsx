import { useState } from 'react'
import api from '../services/api-client'

export default function LiveAnalysis() {
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const [status, setStatus] = useState<string>('')
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [liveSource, setLiveSource] = useState<string | null>(localStorage.getItem('activeLiveSourceId'))
  const [busy, setBusy] = useState(false)

  async function poll(job: number, tries = 30) {
    for (let i = 0; i < tries; i++) {
      try {
        const j = await api.get(`/reconciliation/${job}`)
        setStatus(j.data.status)
        if (j.data.status === 'completed' || j.data.status === 'failed') {
          const r = await api.get(`/jobs/${job}/results`)
          setResult({ ...r.data, job: j.data })
          return
        }
      } catch {}
      await new Promise(r => setTimeout(r, 1000))
    }
    setError('Timed out waiting for job — check Jobs page')
  }

  async function submit() {
    setError(''); setResult(null); setStatus('QUEUED'); setBusy(true)
    if (!file) { setError('Choose a CSV or JSON file'); setBusy(false); return }
    try {
      const fd = new FormData()
      fd.append('file', file)
      const up = await api.post('/uploads', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      const sid = String(up.data.source_id)
      localStorage.setItem('activeLiveSourceId', sid)
      localStorage.setItem('activeLiveSourceName', up.data.filename || file.name)
      setLiveSource(sid)
      const r = await api.post('/reconciliation', { source_ids: [sid], config: {} }, { headers: { 'Idempotency-Key': `live-${Date.now()}` } })
      const id = r.data.job_id || r.data.id
      setJobId(id)
      setStatus(r.data.status || 'QUEUED')
      await poll(id)
    } catch (e: any) {
      const msg = e?.response?.data?.detail || 'Upload failed'
      setError(msg)
      setStatus('FAILED')
    } finally { setBusy(false) }
  }

  async function clearLive(){
    if(!liveSource) return
    try{ await api.delete(`/sources/${liveSource}`) }catch{}
    localStorage.removeItem('activeLiveSourceId')
    localStorage.removeItem('activeLiveSourceName')
    setLiveSource(null); setResult(null); setJobId(null); setStatus(''); setError('')
  }

  return (
    <div style={{ maxWidth: 760, margin: '0 auto' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800 }}>Live Analysis</h1>
      <p style={{ color: '#94a3b8', marginTop: 8 }}>Mode: <b style={{color:'#22c55e'}}>LIVE</b> • Trained model inference on your upload — no demo or benchmark data.</p>
      {liveSource && (
        <div style={{background:'#22c55e15', border:'1px solid #22c55e30', borderRadius:8, padding:10, marginTop:12, display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <span style={{color:'#22c55e', fontWeight:600, fontSize:13}}>Live dataset active: Source #{liveSource}</span>
          <button onClick={clearLive} style={{background:'#ef4444', color:'white', border:'none', padding:'6px 12px', borderRadius:6, fontSize:12, fontWeight:700}}>Delete & restore</button>
        </div>
      )}
      <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20, marginTop: 16 }}>
        <input type="file" accept=".csv,.json" onChange={e => setFile(e.target.files?.[0] || null)} style={{ color: '#e2e8f0' }} />
        <div style={{ marginTop: 16, display: 'flex', gap: 12, flexWrap:'wrap' }}>
          <button onClick={submit} disabled={busy} style={{ background: '#3b82f6', color: 'white', border: 'none', padding: '10px 18px', borderRadius: 8, fontWeight: 700, cursor: 'pointer', opacity: busy?0.6:1 }}>{busy?'Processing...':'Upload & Analyze'}</button>
          <a href="/records" style={{ padding: '10px 18px', border: '1px solid #334155', borderRadius: 8, fontSize:13 }}>Records</a>
          <a href="/matching" style={{ padding: '10px 18px', border: '1px solid #334155', borderRadius: 8, fontSize:13 }}>Matching</a>
        </div>
        {error && <div style={{ color: '#f87171', marginTop: 12 }}>{error}</div>}
        {jobId && <div style={{ color: '#94a3b8', fontSize: 13, marginTop: 12 }}>Job #{jobId} • Status: <b>{status}</b> (live backend state, not simulated)</div>}
        {result && (
          <div style={{ background: '#0f172a', padding: 14, borderRadius: 8, marginTop: 16, fontSize: 13 }}>
            <div style={{fontWeight:700}}>Model: SyncGuard Matcher v{result.model_version} • Mode: LIVE • Job #{result.job_id}</div>
            <div style={{display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:8, marginTop:10}}>
              <div style={{background:'#1e293b', borderRadius:8, padding:10, textAlign:'center'}}><div style={{color:'#94a3b8', fontSize:11}}>Records Processed</div><div style={{fontWeight:800, fontSize:20}}>{result.records_processed}</div></div>
              <div style={{background:'#1e293b', borderRadius:8, padding:10, textAlign:'center'}}><div style={{color:'#94a3b8', fontSize:11}}>Matches</div><div style={{fontWeight:800, fontSize:20, color:'#22c55e'}}>{result.matches_found}</div></div>
              <div style={{background:'#1e293b', borderRadius:8, padding:10, textAlign:'center'}}><div style={{color:'#94a3b8', fontSize:11}}>Conflicts</div><div style={{fontWeight:800, fontSize:20, color:'#f59e0b'}}>{result.conflicts}</div></div>
            </div>
            <div style={{color:'#64748b', fontSize:11, marginTop:8}}>Inference timestamp: {result.job?.created_at || ''} • Input source: #{liveSource}</div>
          </div>
        )}
      </div>
    </div>
  )
}
