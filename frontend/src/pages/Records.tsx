import { useState, useEffect } from 'react'
import { GsapReveal } from '../components/Gsap'
import api from '../services/api-client'

export default function Records() {
  const [filter, setFilter] = useState('')
  const [data, setData] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [liveInfo, setLiveInfo] = useState<string>('')

  useEffect(() => {
    async function load() {
      let activeLive = typeof window !== 'undefined' ? localStorage.getItem('activeLiveSourceId') : null
      if (!activeLive) {
        try {
          const s = await api.get('/sources')
          const liveSrc = (s.data as any[]).find((x: any) => x.config?.live)
          if (liveSrc) { activeLive = String(liveSrc.id); localStorage.setItem('activeLiveSourceId', activeLive) }
        } catch {}
      }
      const q = activeLive ? `/records?limit=500&source_id=${activeLive}` : '/records?limit=50'
      if (activeLive) setLiveInfo(`Live dataset #${activeLive} isolated - training data hidden`)
      else setLiveInfo('Training data (benchmark) - upload via Live Analysis to isolate')
      api.get(q).then(r => setData(r.data)).catch(() => {}).finally(() => setLoading(false))
    }
    load()
  }, [])

  const items = (data?.items || []).filter((r: any) => !filter || String(r.source_id).includes(filter) || r.source_record_id.includes(filter) || r.data?.name?.toLowerCase().includes(filter.toLowerCase()))

  return (
    <div>
      <GsapReveal>
        <h1 className="text-[28px] font-extrabold tracking-tight">Records</h1>
        <p className="mt-1 text-[14px] text-fog">{data ? `${data.total} total \u2022 ${liveInfo}` : 'Live from API - fallback to demo.json if offline'}</p>
      </GsapReveal>

      {liveInfo && (
        <div className={`mt-3 border p-2 text-[12px] ${liveInfo.includes('Live dataset') ? 'border-ok/30 bg-ok/10 text-ok' : 'border-line bg-line/10 text-fog'}`}>
          {liveInfo}
        </div>
      )}

      <input placeholder="Filter by source / id / name..." value={filter} onChange={e => setFilter(e.target.value)} className="sg-input mt-4 w-full max-w-[300px]" />

      {loading ? (
        <p className="mt-4 text-fog">Loading...</p>
      ) : (
        <div className="sg-card mt-4 overflow-auto">
          <table className="w-full border-collapse text-[14px]">
            <thead>
              <tr className="sg-table-head">
                <th className="px-3 py-2.5 text-left">ID</th>
                <th className="px-3 py-2.5 text-left">Source</th>
                <th className="px-3 py-2.5 text-left">Record</th>
                <th className="px-3 py-2.5 text-left">Name</th>
                <th className="px-3 py-2.5 text-left">Email</th>
                <th className="px-3 py-2.5 text-left">Phone</th>
                <th className="px-3 py-2.5 text-left">Amount</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 ? (
                <tr><td colSpan={7} className="px-4 py-10 text-center text-fog/50">No records - seed via `python scripts/seed_live.py`</td></tr>
              ) : items.map((r: any) => (
                <tr key={r.id} className="border-t border-line hover:bg-white/[0.02] transition-colors">
                  <td className="px-2.5 py-2">{r.id}</td>
                  <td className="px-2.5 py-2">{r.source_id}</td>
                  <td className="px-2.5 py-2">{r.source_record_id}</td>
                  <td className="px-2.5 py-2">{r.data?.name}</td>
                  <td className="px-2.5 py-2">{r.data?.email}</td>
                  <td className="px-2.5 py-2">{r.data?.phone ?? 'NULL'}</td>
                  <td className="px-2.5 py-2">{r.data?.amount ?? r.data?.transaction_amount}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
