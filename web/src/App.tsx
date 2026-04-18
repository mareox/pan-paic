import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Shell from './components/Shell'
import TenantsPage from './pages/TenantsPage'
import ProfilesPage from './pages/ProfilesPage'
import ReportsPage from './pages/ReportsPage'
import DiffsPage from './pages/DiffsPage'

export default function App() {
  const [dark, setDark] = useState(() => {
    const stored = localStorage.getItem('theme')
    if (stored) return stored === 'dark'
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('theme', dark ? 'dark' : 'light')
  }, [dark])

  return (
    <BrowserRouter>
      <Shell dark={dark} onToggleDark={() => setDark(d => !d)}>
        <Routes>
          <Route path="/" element={<Navigate to="/tenants" replace />} />
          <Route path="/tenants" element={<TenantsPage />} />
          <Route path="/profiles" element={<ProfilesPage />} />
          <Route path="/reports" element={<ReportsPage />} />
          <Route path="/diffs" element={<DiffsPage />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
