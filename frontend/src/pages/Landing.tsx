import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { useGSAP } from '@gsap/react'
import {
  ArrowRight,
  CheckCircle,
  Database,
  FileCsv,
  FlowArrow,
  GitBranch,
  PlugsConnected,
  Scales,
  ShieldCheck,
  WarningCircle,
} from '@phosphor-icons/react'
import api from '../services/api-client'
import { GsapReveal, ScaleFadeImg, ScrubWords } from '../components/Gsap'

gsap.registerPlugin(ScrollTrigger, useGSAP)

type Live = { records: number; sources: number; matches: number; conflicts: number; jobs: number }

const ACCENT = '#2f6bff'

function useLandingData() {
  const [live, setLive] = useState<Live | null>(null)
  const [liveOk, setLiveOk] = useState(false)
  const [specMatch, setSpecMatch] = useState<any>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    Promise.allSettled([
      api.get('/records?limit=1'),
      api.get('/sources'),
      api.get('/matches?decision=MATCH&limit=100'),
      api.get('/conflicts?limit=1'),
      api.get('/jobs'),
    ])
      .then((results) => {
        if (cancelled) return
        const [rec, src, mat, conf, jobs] = results.map((r: any) =>
          r.status === 'fulfilled' ? r.value.data : null,
        )
        if (results.some((r: any) => r.status === 'fulfilled')) setLiveOk(true)
        else setError('Backend is unreachable. Showing sample content.')
        setLive({
          records: rec?.total ?? 0,
          sources: Array.isArray(src) ? src.length : 0,
          matches: mat?.total ?? mat?.items?.length ?? 0,
          conflicts: Array.isArray(conf) ? conf.length : conf?.total ?? 0,
          jobs: jobs?.total ?? 0,
        })
        if (mat?.items?.length) {
          const ravi = mat.items.find((m: any) =>
            m.evidence?.email?.val_a?.includes('ravi@gmail.com'),
          )
          setSpecMatch(ravi ?? mat.items[0])
        }
      })
      .catch(() => {
        if (!cancelled) setError('Backend is unreachable. Showing sample content.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  return { live, liveOk, specMatch, loading, error }
}

function FieldTick({ ok, warn, label }: { ok: boolean; warn?: boolean; label: string }) {
  const color = ok ? '#34d399' : warn ? '#fbbf24' : '#f87171'
  const Icon = ok ? CheckCircle : WarningCircle
  return (
    <span className="inline-flex items-center gap-1.5 text-[13px] font-medium" style={{ color }}>
      <Icon size={15} weight="fill" />
      {label}
    </span>
  )
}

function Hero() {
  const ref = useRef<HTMLElement>(null)
  useGSAP(
    () => {
      if (!ref.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
      const q = gsap.utils.selector(ref.current)
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } })
      tl.fromTo(q('[data-hero]'), { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 1, stagger: 0.12 })
      tl.fromTo(
        q('[data-hero-cta]'),
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.8, stagger: 0.1 },
        '-=0.5',
      )
      gsap.to(q('[data-hero-bg]'), {
        yPercent: 12,
        ease: 'none',
        scrollTrigger: { trigger: ref.current, start: 'top top', end: 'bottom top', scrub: 1 },
      })
      return () => { tl.kill() }
    },
    { scope: ref },
  )

  return (
    <section ref={ref} className="sg-wash relative overflow-hidden border-b border-line">
      <div data-hero-bg className="absolute inset-0" aria-hidden>
        <img
          src="https://picsum.photos/seed/syncguard-ops-floor/2400/1400"
          alt=""
          width={2400}
          height={1400}
          loading="eager"
          className="h-full w-full object-cover opacity-35 grayscale-[40%] contrast-125"
        />
        <div className="absolute inset-0 bg-[radial-gradient(70rem_36rem_at_50%_110%,rgb(9_13_22/0.15),rgb(9_13_22/0.93)_70%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(46rem_24rem_at_50%_0%,rgb(47_107_255/0.2),transparent_65%)]" />
      </div>

      <div className="relative mx-auto flex min-h-[88dvh] w-full max-w-7xl flex-col items-center justify-center px-4 py-32 text-center md:py-48">
        <h1
          data-hero
          className="w-full max-w-6xl text-balance font-extrabold leading-[1.02] tracking-tighter text-white"
          style={{ fontSize: 'clamp(2.75rem, 5vw, 5.25rem)' }}
        >
          Two systems disagree.{' '}
          <span
            className="mx-2 inline-block h-[0.72em] w-[1.9em] bg-cover bg-center align-baseline grayscale contrast-125"
            style={{ backgroundImage: 'url(https://picsum.photos/seed/syncguard-merge/400/160)' }}
            role="img"
            aria-label="Merging records"
          />{' '}
          SyncGuard proves which value wins.
        </h1>
        <p data-hero className="mt-6 max-w-[58ch] text-lg leading-relaxed text-fog">
          Evidence, review, dry run, and verified sync for customer records split across two systems.
        </p>
        <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
          <Link
            data-hero-cta
            to="/dashboard"
            className="sg-btn group bg-accent px-7 py-3.5 text-[15px] text-white hover:bg-accent-strong"
          >
            Open live overview
            <ArrowRight size={16} weight="bold" className="transition-transform duration-300 group-hover:translate-x-1" />
          </Link>
          <Link
            data-hero-cta
            to="/benchmarks"
            className="sg-btn border border-fog/40 bg-white px-7 py-3.5 text-[15px] text-ink-950 hover:bg-slate-200"
          >
            View benchmarks
          </Link>
        </div>
      </div>
    </section>
  )
}

function PartnerMarquee() {
  const row = [
    { icon: Database, word: 'PostgreSQL targets' },
    { icon: FileCsv, word: 'CSV extracts' },
    { icon: PlugsConnected, word: 'REST connectors' },
    { icon: FlowArrow, word: 'Guarded pipelines' },
    { icon: ShieldCheck, word: 'Verified writes' },
    { icon: GitBranch, word: 'Match evidence' },
  ]
  const doubled = [...row, ...row]
  return (
    <section aria-label="Works with" className="overflow-hidden border-b border-line bg-ink-950 py-8">
      <div className="sg-marquee-track items-center gap-12 pr-12">
        {doubled.map((c, i) => (
          <span key={i} className="flex items-center gap-3 whitespace-nowrap" aria-hidden={i >= row.length}>
            <c.icon size={24} weight="duotone" className="text-fog/60" />
            <span className="text-lg font-extrabold uppercase tracking-tight text-fog/50">{c.word}</span>
          </span>
        ))}
      </div>
    </section>
  )
}

function Bento() {
  return (
    <section className="mx-auto w-full max-w-7xl px-4 py-32 md:px-6 md:py-48">
      <GsapReveal>
        <h2 className="max-w-[22ch] text-4xl font-extrabold tracking-tighter text-white md:text-5xl">
          Every step keeps its proof
        </h2>
        <p className="mt-4 max-w-[65ch] text-[15px] leading-relaxed text-fog">
          Raw extracts move to a verified write. Each decision stores the evidence that produced it, so
          review and audit read backend truth instead of frontend guesses.
        </p>
      </GsapReveal>
      <div className="mt-12 grid grid-flow-dense grid-cols-1 gap-4 md:grid-cols-12">
        <GsapReveal className="md:col-span-7" y={32}>
          <article className="group grid h-full overflow-hidden border border-line bg-panel sm:grid-cols-2 transition-colors duration-500 hover:border-accent">
            <div className="p-7">
              <Database size={24} color={ACCENT} weight="duotone" />
              <h3 className="mt-4 text-2xl font-extrabold tracking-tight text-white">Ingest and normalize</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-fog">
                Load CSV, JSON, or REST extracts. Names, phones, emails, and addresses normalize to one
                comparable form before any comparison runs.
              </p>
            </div>
            <div className="overflow-hidden">
              <img
                src="https://picsum.photos/seed/syncguard-ingest/1000/800"
                alt="Normalized source extracts"
                width={1000}
                height={800}
                loading="lazy"
                className="h-56 w-full object-cover opacity-85 grayscale-[30%] contrast-125 transition-transform duration-700 ease-out group-hover:scale-105 sm:h-full"
              />
            </div>
          </article>
        </GsapReveal>
        <GsapReveal className="md:col-span-5" delay={0.08} y={32}>
          <article className="group flex h-full flex-col justify-between border border-line bg-panel-2 p-7 transition-colors duration-500 hover:border-accent">
            <div>
              <GitBranch size={24} color={ACCENT} weight="duotone" />
              <h3 className="mt-4 text-2xl font-extrabold tracking-tight text-white">Match with evidence</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-fog">
                Blocking proposes candidates. A trained matcher scores each pair and stores per field
                reasons, penalties, and risk with the decision.
              </p>
            </div>
            <p className="tnum mt-6 border-t border-white/10 pt-4 text-sm text-paper/80">
              MATCH threshold 0.60, frozen in config
            </p>
          </article>
        </GsapReveal>
        <GsapReveal className="md:col-span-5" delay={0.05} y={32}>
          <article className="group h-full border border-line bg-panel p-7 transition-colors duration-500 hover:border-accent">
            <Scales size={24} color={ACCENT} weight="duotone" />
            <h3 className="mt-4 text-2xl font-extrabold tracking-tight text-white">Review conflicts</h3>
            <p className="mt-3 text-[15px] leading-relaxed text-fog">
              Contradictions route to a reviewer with both values visible. Use A, use B, edit, reject, or
              defer. Originals stay preserved either way.
            </p>
          </article>
        </GsapReveal>
        <GsapReveal className="md:col-span-7" delay={0.1} y={32}>
          <article className="group grid h-full overflow-hidden bg-accent sm:grid-cols-2">
            <div className="p-7">
              <ShieldCheck size={24} color="#fff" weight="duotone" />
              <h3 className="mt-4 text-2xl font-extrabold tracking-tight text-white">Dry run, then guarded sync</h3>
              <p className="mt-3 text-[15px] leading-relaxed text-blue-100">
                Preview the exact mutation first. Writes carry version guards and idempotency keys, then
                read back to verify before the trail closes.
              </p>
            </div>
            <div className="overflow-hidden">
              <img
                src="https://picsum.photos/seed/syncguard-guarded-sync/1000/800"
                alt="Verified write confirmation"
                width={1000}
                height={800}
                loading="lazy"
                className="h-56 w-full object-cover opacity-95 contrast-125 transition-transform duration-700 ease-out group-hover:scale-105 sm:h-full"
              />
            </div>
          </article>
        </GsapReveal>
      </div>
    </section>
  )
}

function PinnedGallery() {
  const ref = useRef<HTMLElement>(null)
  useGSAP(
    () => {
      if (!ref.current || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
      const ctx = gsap.context(() => {
        gsap.to('[data-stack-card]', {
          scale: 0.94,
          opacity: 0.6,
          ease: 'none',
          stagger: 0.15,
          scrollTrigger: { trigger: '[data-stack-track]', start: 'top 70%', end: 'bottom 40%', scrub: 1 },
        })
      }, ref)
      return () => ctx.revert()
    },
    { scope: ref },
  )

  return (
    <section ref={ref} className="border-y border-line bg-ink-950">
      <div className="mx-auto grid w-full max-w-7xl gap-10 px-4 py-32 md:px-6 md:py-48 lg:grid-cols-12">
        <div className="lg:col-span-5">
          <div className="lg:sticky lg:top-32">
            <h2 className="text-4xl font-extrabold tracking-tighter text-white md:text-5xl">
              Watch a conflict close
            </h2>
            <ScrubWords
              className="mt-6 max-w-[48ch] text-xl leading-relaxed text-fog"
              text="Source A and source B disagree on one field. The reviewer picks a value, previews the mutation, pushes once, and the system verifies the write landed."
            />
            <Link to="/conflicts" className="sg-btn mt-8 bg-accent px-6 py-3 text-[15px] text-white hover:bg-accent-strong">
              Review live conflicts
            </Link>
          </div>
        </div>
        <div data-stack-track className="grid gap-6 lg:col-span-7">
          {[
            { seed: 'syncguard-review-both', alt: 'Both conflicting values visible side by side' },
            { seed: 'syncguard-dryrun-preview', alt: 'Dry run preview of the exact mutation' },
            { seed: 'syncguard-verify-trail', alt: 'Verification and audit trail after sync' },
          ].map((g) => (
            <div key={g.seed} data-stack-card className="border border-line bg-panel p-3">
              <ScaleFadeImg seed={g.seed} alt={g.alt} aspect="aspect-[16/10]" />
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function LiveEvidence({
  loading,
  liveOk,
  confidence,
  emailOk,
  phoneMissing,
  nameScore,
  recommendation,
  risk,
  metrics,
  dataNote,
}: any) {
  return (
    <section className="mx-auto w-full max-w-7xl px-4 py-32 md:px-6 md:py-48">
      <div className="grid items-end gap-8 lg:grid-cols-12">
        <GsapReveal className="lg:col-span-7">
          <h2 className="text-4xl font-extrabold tracking-tighter text-white md:text-5xl">
            Live evidence, not mock certainty
          </h2>
        </GsapReveal>
        <GsapReveal className="lg:col-span-5" delay={0.08}>
          <p className="max-w-[52ch] text-[15px] leading-relaxed text-fog">
            This card renders stored backend truth. When the API is unreachable it labels itself as
            sample content instead of inventing precision.
          </p>
        </GsapReveal>
      </div>

      <div className="mt-12 grid gap-4 lg:grid-cols-12">
        <GsapReveal className="lg:col-span-7">
          <div className="border border-line bg-panel">
            {loading ? (
              <div className="p-5">
                <div className="sg-skeleton h-52" />
                <div className="sg-skeleton mt-3 h-5 w-2/3" />
              </div>
            ) : (
              <div className="group overflow-hidden">
                <div className="overflow-hidden">
                  <img
                    src="https://picsum.photos/seed/syncguard-reconciliation/1600/800"
                    alt="Two source extracts merging into one reviewed record"
                    width={1600}
                    height={800}
                    loading="lazy"
                    className="aspect-[2/1] w-full object-cover opacity-85 grayscale-[30%] contrast-125 transition-transform duration-700 ease-out group-hover:scale-105"
                  />
                </div>
                <div className="border-t border-line p-6">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <span className="text-base font-bold text-white">
                      Confidence <span className="tnum text-ok">{confidence} percent</span>
                    </span>
                    <span className="sg-chip border-accent bg-accent text-white">
                      {liveOk ? 'Model scored' : 'Sample scored'}
                    </span>
                  </div>
                  <div className="mt-4 flex flex-wrap gap-x-5 gap-y-2">
                    <FieldTick ok={emailOk} label={emailOk ? 'Email exact' : 'Email differs'} />
                    <FieldTick ok={!phoneMissing} warn={phoneMissing} label={phoneMissing ? 'Phone missing' : 'Phone exact'} />
                    <FieldTick ok label={`Name ${nameScore}`} />
                  </div>
                  <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px]">
                    <span className="sg-chip bg-white/10 text-white">{recommendation}</span>
                    <span className="sg-chip tnum text-fog">{risk} risk</span>
                  </div>
                </div>
                <p className="border-t border-line px-6 py-4 text-[13px] text-fog">
                  Scores never render without stored reasons. Penalties and risk travel with the decision.
                </p>
              </div>
            )}
          </div>
        </GsapReveal>
        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-5">
          {[
            { label: 'Records', value: metrics.records.toLocaleString() },
            { label: 'Matches', value: metrics.matches.toLocaleString() },
            { label: 'Conflicts', value: metrics.conflicts.toLocaleString() },
            { label: 'Sync jobs', value: metrics.jobs.toLocaleString() },
          ].map((m, i) => (
            <GsapReveal key={m.label} delay={i * 0.06}>
              <div className="group border border-line bg-panel p-6 transition-colors duration-500 hover:border-accent">
                <div className="text-[13px] font-semibold uppercase tracking-[0.14em] text-fog">{m.label}</div>
                <div className="tnum mt-2 text-4xl font-extrabold text-white">
                  {loading ? '-' : m.value}
                </div>
                <div className="mt-2 text-xs text-fog/60">{dataNote}</div>
              </div>
            </GsapReveal>
          ))}
        </div>
      </div>
    </section>
  )
}

function Accordions() {
  const items = [
    { title: 'FEBRL3 links, 5K records', stat: 'Recall 0.9947', body: 'Temporal check across two snapshots. Zero incorrect automatic merges in tested sets.', seed: 'syncguard-febrl', active: true },
    { title: 'Walmart Amazon catalog', stat: 'F1 0.649', body: 'Product pairs contributed training signal across noisy titles and attributes.', seed: 'syncguard-walmart' },
    { title: 'Amazon Google catalog', stat: 'F1 0.355', body: 'Person record behavior rests on voter validation, never on catalog claims.', seed: 'syncguard-amazon' },
  ]
  return (
    <section className="border-y border-line bg-ink-950">
      <div className="mx-auto w-full max-w-7xl px-4 py-32 md:px-6 md:py-48">
        <GsapReveal>
          <h2 className="max-w-[24ch] text-4xl font-extrabold tracking-tighter text-white md:text-5xl">
            Trained once, measured in public
          </h2>
          <p className="mt-4 max-w-[65ch] text-[15px] leading-relaxed text-fog">
            One LogisticRegression matcher serves every feature. Thresholds stay frozen. Expand each
            benchmark to see what it actually proves.
          </p>
        </GsapReveal>
        <div className="mt-12 flex min-h-[26rem] flex-col gap-4 md:flex-row">
          {items.map((b) => (
            <article
              key={b.title}
              className={`group relative flex-1 overflow-hidden border border-line transition-all duration-700 ease-out md:hover:flex-[2.2] ${b.active ? 'md:flex-[2.2]' : ''}`}
            >
              <img
                src={`https://picsum.photos/seed/${b.seed}/900/1100`}
                alt=""
                aria-hidden
                width={900}
                height={1100}
                loading="lazy"
                className="absolute inset-0 h-full w-full object-cover opacity-25 grayscale contrast-125 transition-transform duration-700 ease-out group-hover:scale-105"
              />
              <div className="absolute inset-0 bg-gradient-to-t from-ink-950 via-ink-950/70 to-ink-950/20" />
              <div className="relative flex h-full min-h-[22rem] flex-col justify-end p-7">
                <p className="tnum text-3xl font-extrabold text-white">{b.stat}</p>
                <h3 className="mt-2 text-xl font-extrabold text-white">{b.title}</h3>
                <p className="mt-2 max-w-[46ch] text-sm leading-relaxed text-fog md:max-h-0 md:overflow-hidden md:opacity-0 md:transition-all md:duration-500 md:group-hover:max-h-40 md:group-hover:opacity-100">
                  {b.body}
                </p>
                <Link to="/benchmarks" className="sg-btn mt-5 w-fit border border-white/30 bg-white/10 px-4 py-2 text-sm text-white hover:bg-white hover:text-ink-950">
                  View benchmarks
                </Link>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  )
}

function Closing() {
  return (
    <section className="sg-wash mx-auto w-full max-w-7xl px-4 py-32 md:px-6 md:py-48">
      <GsapReveal>
        <div className="grid items-center gap-8 border border-line bg-accent p-8 md:grid-cols-12 md:p-14">
          <div className="md:col-span-8">
            <h2 className="max-w-[20ch] text-4xl font-extrabold leading-[1.05] tracking-tighter text-white md:text-6xl">
              Upload two extracts today
            </h2>
            <p className="mt-4 max-w-[56ch] text-lg leading-relaxed text-blue-100">
              Run the three minute flow from upload to verified write against your own sample.
            </p>
          </div>
          <div className="flex flex-wrap gap-4 md:col-span-4 md:justify-end">
            <Link to="/dashboard" className="sg-btn group bg-white px-7 py-4 text-base text-ink-950 hover:bg-slate-200">
              Open live overview
              <ArrowRight size={18} weight="bold" className="transition-transform duration-300 group-hover:translate-x-1" />
            </Link>
          </div>
        </div>
      </GsapReveal>
      <footer className="flex flex-wrap items-center gap-x-8 gap-y-3 border border-t-0 border-line bg-ink-950 px-6 py-6 text-[13px] text-fog/60">
        <span className="font-bold text-fog">SyncGuard</span>
        <Link to="/dashboard" className="hover:text-fog transition-colors">Overview</Link>
        <Link to="/matching" className="hover:text-fog transition-colors">Matching</Link>
        <Link to="/conflicts" className="hover:text-fog transition-colors">Conflicts</Link>
        <Link to="/audit" className="hover:text-fog transition-colors">Audit</Link>
        <a href="/api/docs" className="ml-auto hover:text-fog transition-colors">
          OpenAPI docs
        </a>
      </footer>
    </section>
  )
}

export default function Landing() {
  const { live, liveOk, specMatch, loading, error } = useLandingData()

  const metrics: Live = live ?? { records: 2200, sources: 4, matches: 23, conflicts: 20, jobs: 1 }
  const dataNote = liveOk ? 'Live DB' : 'Sample'
  const confidence = specMatch ? (Math.min(specMatch.confidence, 0.999) * 100).toFixed(1) : '98.4'
  const evidence = specMatch?.evidence ?? {}
  const emailOk = evidence.email?.match ?? true
  const phoneMissing = evidence.phone?.reason === 'missing_field' || evidence.phone?.match === false
  const nameScore = evidence.name?.score ? `${Math.round(evidence.name.score * 100)} percent` : 'fuzzy'
  const recommendation: string = specMatch?.evidence?.recommendation ?? 'MANUAL REVIEW'
  const risk: string = specMatch?.evidence?.risk ?? specMatch?.risk ?? 'MEDIUM'

  return (
    <div className="w-full">
      <Hero />
      <PartnerMarquee />
      {error && (
        <div className="mx-auto w-full max-w-7xl px-4 md:px-6">
          <div role="status" className="mt-8 border border-warn/40 bg-warn/10 px-5 py-4 text-sm text-warn">
            {error}
          </div>
        </div>
      )}
      <Bento />
      <PinnedGallery />
      <LiveEvidence
        loading={loading}
        liveOk={liveOk}
        confidence={confidence}
        emailOk={emailOk}
        phoneMissing={phoneMissing}
        nameScore={nameScore}
        recommendation={recommendation}
        risk={risk}
        metrics={metrics}
        dataNote={dataNote}
      />
      <Accordions />
      <Closing />
    </div>
  )
}
