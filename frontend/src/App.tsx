import { Routes, Route, NavLink, Navigate } from 'react-router-dom'
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

const navLinks = [
  { to: '/', label: 'Home' },
  { to: '/dashboard', label: 'Dashboard' },
  { to: '/live', label: 'Live Analysis' },
  { to: '/benchmarks', label: 'Benchmarks' },
  { to: '/records', label: 'Records' },
  { to: '/matching', label: 'Matching' },
  { to: '/conflicts', label: 'Conflicts' },
  { to: '/sources', label: 'Sources' },
  { to: '/jobs', label: 'Jobs' },
  { to: '/audit', label: 'Audit' },
]

export default function App() {
  return (
    <div>
      <nav style={{ display: 'flex', gap: 16, padding: '12px 20px', background: '#1e293b', borderBottom: '1px solid #334155', flexWrap: 'wrap' }}>
        <span style={{ fontWeight: 800, color: 'white', marginRight: 8 }}>SyncGuard</span>
        {navLinks.map(link => (
          <NavLink key={link.to} to={link.to} style={({ isActive }) => ({ color: isActive ? '#3b82f6' : '#e2e8f0', fontWeight: isActive ? 700 : 400, padding: '6px 0', borderBottom: isActive ? '2px solid #3b82f6' : '2px solid transparent', fontSize: 14 })}>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <main className="container">
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
      </main>
    </div>
  )
}
