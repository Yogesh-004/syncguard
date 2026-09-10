import { useEffect, useState, useRef } from 'react'
import { Routes, Route, NavLink, Navigate, Link, useLocation } from 'react-router-dom'
import gsap from 'gsap'
import { ShieldCheck, List, X, ArrowRight } from '@phosphor-icons/react'
import Landing from './pages/Landing'
import Dashboard from './pages/Dashboard'
import Records from './pages/Records'
import Matching from './pages/Matching'
import Conflicts from './pages/Conflicts'
import Sources from './pages/Sources'
import Jobs from './pages/Jobs'
import LiveAnalysis from './pages/LiveAnalysis'
import Benchmarks from './pages/Benchmarks'
import Audit from './pages/Audit'

const primaryLinks = [
  { to: '/dashboard', label: 'Overview' },
  { to: '/live', label: 'Live' },
  { to: '/matching', label: 'Matching' },
  { to: '/conflicts', label: 'Conflicts' },
  { to: '/audit', label: 'Audit' },
]

const overflowLinks = [
  { to: '/records', label: 'Records' },
  { to: '/sources', label: 'Sources' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/benchmarks', label: 'Benchmarks' },
]

const allMobileLinks = [{ to: '/', label: 'Home' }, ...primaryLinks, ...overflowLinks]

function linkCls(isActive: boolean) {
  return [
    'whitespace-nowrap px-3 py-2 text-[13px] font-medium transition-all duration-200 border-b-2 -mb-px',
    isActive
      ? 'text-white border-accent'
      : 'text-fog hover:text-white border-transparent hover:border-white/20',
  ].join(' ')
}

export default function App() {
  const [open, setOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const location = useLocation()
  const isLanding = location.pathname === '/'
  const mobileRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const tween = gsap.fromTo(
      '[data-page]',
      { opacity: 0, y: 12 },
      { opacity: 1, y: 0, duration: 0.5, ease: 'power3.out', clearProps: 'all' },
    )
    return () => { tween.kill() }
  }, [location.pathname])

  useEffect(() => {
    if (!open || !mobileRef.current) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const items = mobileRef.current.querySelectorAll('[data-mobile-link]')
    gsap.fromTo(items, { opacity: 0, x: -16 }, { opacity: 1, x: 0, duration: 0.4, stagger: 0.04, ease: 'power3.out' })
  }, [open])

  useEffect(() => {
    setOpen(false)
    setMoreOpen(false)
  }, [location.pathname])

  return (
    <div className="sg-grain min-h-dvh bg-ink-950 text-paper">
      <div className="mx-auto w-full max-w-[88rem] px-4 pt-3 md:px-6">
        <header className="sticky top-3 z-40 border border-line/60 bg-ink-950/80 shadow-[0_24px_80px_rgb(0,0,0,0.5)] backdrop-blur-xl">
          <nav aria-label="Primary" className="flex h-14 items-center gap-3 px-4">
            <Link to="/" className="flex shrink-0 items-center gap-2.5" aria-label="SyncGuard home">
              <span className="grid size-8 place-items-center bg-accent">
                <ShieldCheck size={17} weight="bold" color="#fff" />
              </span>
              <span className="leading-none">
                <span className="block text-[14px] font-extrabold tracking-tight text-white">SyncGuard</span>
                <span className="tnum block text-[9px] font-medium uppercase tracking-[0.2em] text-fog/70">
                  Guarded sync
                </span>
              </span>
            </Link>

            <div className="ml-6 hidden min-w-0 flex-1 items-center gap-0.5 lg:flex">
              <NavLink to="/" end className={({ isActive }) => linkCls(isActive)}>
                Home
              </NavLink>
              {primaryLinks.map((l) => (
                <NavLink key={l.to} to={l.to} className={({ isActive }) => linkCls(isActive)}>
                  {l.label}
                </NavLink>
              ))}
              <div className="relative">
                <button
                  type="button"
                  onClick={() => setMoreOpen((v) => !v)}
                  onBlur={() => window.setTimeout(() => setMoreOpen(false), 150)}
                  aria-expanded={moreOpen}
                  className="whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-[13px] font-medium text-fog transition-all duration-200 hover:text-white hover:border-white/20 -mb-px"
                >
                  More
                </button>
                {moreOpen && (
                  <div className="absolute right-0 top-[calc(100%+4px)] w-44 border border-line bg-ink-950 p-1 shadow-2xl">
                    {overflowLinks.map((l) => (
                      <NavLink
                        key={l.to}
                        to={l.to}
                        onClick={() => setMoreOpen(false)}
                        className={({ isActive }) =>
                          `block px-3 py-2 text-[13px] font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-fog hover:bg-white/5 hover:text-white'}`
                        }
                      >
                        {l.label}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div className="ml-auto hidden shrink-0 items-center gap-2 lg:flex">
              <Link
                to="/live"
                className="sg-btn border border-line bg-transparent px-4 py-2 text-[13px] text-fog hover:bg-white/5 hover:text-white hover:border-white/20"
              >
                New analysis
              </Link>
              <Link
                to="/dashboard"
                className="sg-btn bg-accent px-4 py-2 text-[13px] text-white hover:bg-accent-strong group"
              >
                Open live overview
                <ArrowRight size={14} weight="bold" className="transition-transform duration-300 group-hover:translate-x-0.5" />
              </Link>
            </div>

            <button
              type="button"
              className="ml-auto grid size-9 place-items-center border border-line text-fog transition-colors hover:bg-white/5 hover:text-white lg:hidden"
              aria-label={open ? 'Close menu' : 'Open menu'}
              aria-expanded={open}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? <X size={18} /> : <List size={18} />}
            </button>
          </nav>

          {open && (
            <div ref={mobileRef} className="border-t border-line px-4 py-3 lg:hidden">
              <div className="grid gap-0.5">
                {allMobileLinks.map((l) => (
                  <NavLink
                    key={l.to}
                    to={l.to}
                    end={l.to === '/'}
                    data-mobile-link
                    onClick={() => setOpen(false)}
                    className={({ isActive }) =>
                      `px-3 py-2.5 text-[14px] font-medium transition-colors ${isActive ? 'bg-white/10 text-white' : 'text-fog hover:text-white'}`
                    }
                  >
                    {l.label}
                  </NavLink>
                ))}
                <Link
                  to="/dashboard"
                  onClick={() => setOpen(false)}
                  data-mobile-link
                  className="sg-btn mt-2 bg-accent px-4 py-2.5 text-[13px] text-white"
                >
                  Open live overview
                  <ArrowRight size={14} weight="bold" />
                </Link>
              </div>
            </div>
          )}
        </header>
      </div>

      <main className="w-full max-w-full overflow-x-hidden">
        <div data-page className={isLanding ? '' : 'container pb-20 pt-6'}>
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/live" element={<LiveAnalysis />} />
            <Route path="/benchmarks" element={<Benchmarks />} />
            <Route path="/records" element={<Records />} />
            <Route path="/matching" element={<Matching />} />
            <Route path="/conflicts" element={<Conflicts />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/jobs" element={<Jobs />} />
            <Route path="/audit" element={<Audit />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  )
}
