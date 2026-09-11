import { useState } from 'react'
import { Link } from 'react-router-dom'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

export default function LiveAnalysis() {
  const [file, setFile] = useState<File | null>(null)
  const [jobId, setJobId] = useState<number | null>(null)
  const [status, setStatus] = useState<string>('')
  const [result, setResult] = useState<any>(null)
  const [error, setError] = useState('')
  const [liveSource, setLiveSource] = useState<string | null>(localStorage.getItem('activeLiveSourceId'))
  const [busy, setBusy] = useState(false)

  async function poll(job: number, tries = 150) {
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
      await new Promise(r => setTimeout(r, 5000))
    }
    setError('Timed out waiting for job - check Jobs page')
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

  async function clearLive() {
    if (!liveSource) return
    try { await api.delete(`/sources/${liveSource}`) } catch {}
    localStorage.removeItem('activeLiveSourceId')
    localStorage.removeItem('activeLiveSourceName')
    setLiveSource(null); setResult(null); setJobId(null); setStatus(''); setError('')
  }

  return (
    <div className="mx-auto max-w-[760px]">
      <GsapReveal>
        <h1 className="text-[28px] font-extrabold tracking-tight">Live Analysis</h1>
        <p className="mt-2 text-[14px] text-fog">Mode: <b className="text-ok">LIVE</b> \u2022 Trained model inference on your upload - no demo or benchmark data.</p>
      </GsapReveal>

      {liveSource && (
        <div className="mt-3 flex items-center justify-between border border-ok/30 bg-ok/10 p-2.5">
          <span className="text-[13px] font-semibold text-ok">Live dataset active: Source #{liveSource}</span>
          <button onClick={clearLive} className="sg-btn bg-danger px-3 py-1.5 text-[11px] font-bold text-white hover:bg-danger/80">Delete & restore</button>
        </div>
      )}

      <div className="sg-card mt-4 p-5">
        <input type="file" accept=".csv,.json" onChange={e => setFile(e.target.files?.[0] || null)} className="text-fog" />
        <div className="mt-4 flex flex-wrap gap-3">
          <button onClick={submit} disabled={busy} className="sg-btn bg-info px-4 py-2.5 text-[13px] font-bold text-white hover:bg-info/80 disabled:opacity-50">
            {busy ? 'Processing...' : 'Upload & Analyze'}
          </button>
          <Link to="/records" className="sg-btn border border-line px-4 py-2.5 text-[13px] text-fog hover:bg-white/5 hover:text-white">Records</Link>
          <Link to="/matching" className="sg-btn border border-line px-4 py-2.5 text-[13px] text-fog hover:bg-white/5 hover:text-white">Matching</Link>
        </div>
        {error && <div className="mt-3 text-danger">{error}</div>}
        {jobId && <div className="mt-3 text-[13px] text-fog">Job #{jobId} \u2022 Status: <b>{status}</b> (live backend state, not simulated)</div>}
        {result && (
          <div className="mt-4 bg-ink-900 p-3.5 text-[13px]">
            <div className="font-bold">Model: SyncGuard Matcher v{result.model_version} \u2022 Mode: LIVE \u2022 Job #{result.job_id}</div>
            <div className="mt-2.5 grid grid-cols-3 gap-2">
              <div className="bg-ink-950 p-2.5 text-center"><div className="text-[11px] text-fog">Records Processed</div><div className="mt-1 text-[20px] font-extrabold">{result.records_processed}</div></div>
              <div className="bg-ink-950 p-2.5 text-center"><div className="text-[11px] text-fog">Matches</div><div className="mt-1 text-[20px] font-extrabold text-ok">{result.matches_found}</div></div>
              <div className="bg-ink-950 p-2.5 text-center"><div className="text-[11px] text-fog">Conflicts</div><div className="mt-1 text-[20px] font-extrabold text-warn">{result.conflicts}</div></div>
            </div>
            <div className="mt-2 text-[11px] text-fog/50">Inference timestamp: {result.job?.created_at || ''} \u2022 Input source: #{liveSource}</div>
          </div>
        )}
      </div>
    </div>
  )
}
