import { NavLink } from 'react-router-dom'
import type { ReactNode } from 'react'

interface ShellProps {
  children: ReactNode
  dark: boolean
  onToggleDark: () => void
}

const NAV_ITEMS = [
  { to: '/tenants', label: 'Tenants' },
  { to: '/profiles', label: 'Profiles' },
  { to: '/reports', label: 'Reports' },
  { to: '/diffs', label: 'Diffs' },
]

export default function Shell({ children, dark, onToggleDark }: ShellProps) {
  return (
    <div className="min-h-screen flex flex-col bg-white dark:bg-gray-950">
      <header className="border-b border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 sticky top-0 z-40">
        <div className="max-w-screen-xl mx-auto flex items-center gap-6 px-4 h-12">
          {/* Logo / Title */}
          <div className="flex items-center gap-2 shrink-0">
            <span className="inline-block w-5 h-5 rounded bg-brand-600 text-white flex items-center justify-center text-[10px] font-bold leading-none">PA</span>
            <span className="text-sm font-semibold tracking-tight text-gray-900 dark:text-gray-100 hidden sm:block">
              Prisma Access IP Console
            </span>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-1 flex-1" aria-label="Main navigation">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `px-3 py-1 rounded text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 dark:bg-brand-900/30 dark:text-brand-300'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100 dark:text-gray-400 dark:hover:text-gray-100 dark:hover:bg-gray-800'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Theme toggle */}
          <button
            onClick={onToggleDark}
            aria-label={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="btn-ghost p-1.5 rounded"
          >
            {dark ? (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 7a5 5 0 100 10A5 5 0 0012 7z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
              </svg>
            )}
          </button>
        </div>
      </header>

      <main className="flex-1 max-w-screen-xl mx-auto w-full px-4 py-6">
        {children}
      </main>
    </div>
  )
}
