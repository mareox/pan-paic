import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { useState, useEffect } from 'react'
import Shell from './components/Shell'
import QueryPage from './pages/QueryPage'
import ProfilesPage from './pages/ProfilesPage'

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
          <Route path="/" element={<QueryPage />} />
          <Route path="/profiles" element={<ProfilesPage />} />
        </Routes>
      </Shell>
    </BrowserRouter>
  )
}
