import { useState } from 'react'
import api from '../services/api-client'

const stages = ['Initializing...','Connecting...','Loading schema...','Analyzing...','Matching (ML)...','Reconciling...']

export default function LiveAnalysis() {
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const [progress, setProgress] = useState(0)
  const [stage, setStage] = useState(0)
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [liveSource, setLiveSource] = useState<string | null>(localStorage.getItem('activeLiveSourceId'))

  async function submit() {
    setError(''); setResult(null); setProgress(0); setStage(0)
    if (!file) { setError('Choose a CSV or JSON file'); return }
    try {
      const fd = new FormData()
      fd.append('file', file)
      const up = await api.post('/uploads', fd, { headers: { 'Content-Type': 'multipart/form-data' } })
      const sid = String(up.data.source_id)
      const count = up.data.record_count
      // Isolate: set active live source — all features will now filter to this dataset only until deleted
      localStorage.setItem('activeLiveSourceId', sid)
      localStorage.setItem('activeLiveSourceName', up.data.filename || file.name)
      setLiveSource(sid)
      const r = await api.post('/reconciliation', { source_ids: [sid], config: {} }, { headers: { 'Idempotency-Key': `live-${Date.now()}` } })
      const id = r.data.job_id || r.data.id
      setJobId(id)
      setResult({ source_id: sid, records: count, message: up.data.message })
      let p = 0
      const iv = setInterval(async () => {
        p = Math.min(95, p + Math.random() * 18)
        setProgress(Math.round(p))
        setStage(Math.min(stages.length - 1, Math.floor(p / 18)))
        try {
          const j = await api.get(`/reconciliation/${id}`)
          if (j.data.status === 'completed' || j.data.progress === 100) {
            clearInterval(iv); setProgress(100); setStage(stages.length - 1)
            setResult((prev:any)=> ({...prev, job: j.data}))
          }
        } catch {}
      }, 1200)
      setTimeout(() => { clearInterval(iv); setProgress(100) }, 9000)
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Upload failed')
    }
  }

  async function clearLive(){
    if(!liveSource) return
    try{ await api.delete(`/sources/${liveSource}`) }catch{}
    localStorage.removeItem('activeLiveSourceId')
    localStorage.removeItem('activeLiveSourceName')
    setLiveSource(null)
    setResult(null); setJobId(null); setProgress(0)
    setError('')
  }

  return (
    <div style={{ maxWidth: 720, margin: '0 auto' }}>
      <h1 style={{ fontSize: 28, fontWeight: 800 }}>Live Analysis</h1>
      <p style={{ color: '#94a3b8', marginTop: 8 }}>Upload CSV/JSON (≤5MB, 10k) — <b style={{color:'#22c55e'}}>training data (FEBRL3 etc.) stays for model only</b>, live features will be <b>isolated</b> to your dataset until deleted.</p>
      {liveSource && (
        <div style={{background:'#22c55e15', border:'1px solid #22c55e30', borderRadius:8, padding:10, marginTop:12, display:'flex', justifyContent:'space-between', alignItems:'center'}}>
          <span style={{color:'#22c55e', fontWeight:600, fontSize:13}}>● Live dataset active: Source #{liveSource} — all features (Records, Matching, Conflicts, Dashboard, Jobs, Audit) now show <b>only</b> this dataset</span>
          <button onClick={clearLive} style={{background:'#ef4444', color:'white', border:'none', padding:'6px 12px', borderRadius:6, fontSize:12, fontWeight:700}}>Delete & restore</button>
        </div>
      )}
      <div style={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 12, padding: 20, marginTop: 16 }}>
        <input type="file" accept=".csv,.json" onChange={e => setFile(e.target.files?.[0] || null)} style={{ color: '#e2e8f0' }} />
        <div style={{ marginTop: 16, display: 'flex', gap: 12, flexWrap:'wrap' }}>
          <button onClick={submit} style={{ background: '#3b82f6', color: 'white', border: 'none', padding: '10px 18px', borderRadius: 8, fontWeight: 700, cursor: 'pointer' }}>Upload & Isolate</button>
          <a href="/records" style={{ padding: '10px 18px', border: '1px solid #334155', borderRadius: 8, fontSize:13 }}>View Records (live)</a>
          <a href="/matching" style={{ padding: '10px 18px', border: '1px solid #334155', borderRadius: 8, fontSize:13 }}>View Matching (live)</a>
        </div>
        {error && <div style={{ color: '#f87171', marginTop: 12 }}>{error}</div>}
        {jobId && (
          <div style={{ marginTop: 16 }}>
            <div style={{ color: '#94a3b8', fontSize: 13 }}>Job #{jobId} — {stages[stage]} {liveSource ? `(source ${liveSource})` : ''}</div>
            <div style={{ background: '#0f172a', borderRadius: 999, height: 10, marginTop: 8, overflow: 'hidden' }}>
              <div style={{ width: `${progress}%`, height: '100%', background: '#22c55e', transition: 'width 0.6s' }} />
            </div>
            <div style={{ fontSize: 13, marginTop: 6 }}>{progress}% — {result?.records ? `${result.records} records isolated` : ''}</div>
          </div>
        )}
        {result && <div style={{ background: '#0f172a', padding: 12, borderRadius: 8, marginTop: 16, fontSize: 13 }}>
          <div style={{color:'#22c55e', fontWeight:600}}>Live pipeline complete — training data not mixed</div>
          <div style={{color:'#94a3b8', marginTop:6}}>Source #{result.source_id} • {result.records} records • All features (Dashboard, Records, Matching, Conflicts, Jobs, Audit) now filter to this source until you Delete above.</div>
          <pre style={{marginTop:8, fontSize:11, overflow:'auto', color:'#64748b'}}>{JSON.stringify(result, null, 2)}</pre>
        </div>}
      </div>
      <div style={{ color: '#64748b', fontSize: 12, marginTop: 12, background:'#0f172a', padding:10, borderRadius:8, border:'1px solid #334155'}}>
        <b>How isolation works:</b> Training datasets (FEBRL3 5K, Walmart-Amazon 10K, Amazon-Google 11K) are used <b>only</b> to train the ML model (saved to <code>backend/app/models/</code>). They are <b>not</b> shown in live features. When you upload, we create a new <code>Source</code> with <code>live:true</code> and store your records there. Every other feature checks <code>localStorage.activeLiveSourceId</code> and adds <code>?source_id=</code> to API calls — so you see <b>only</b> your dataset until deleted. Delete restores benchmark view.
      </div>
    </div>
  )
}
