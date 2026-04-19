import { NavLink } from 'react-router-dom'
import type { ReactNode } from 'react'

interface ShellProps {
  children: ReactNode
  dark: boolean
  onToggleDark: () => void
}

const NAV_ITEMS = [
  { to: '/',         label: 'Query'    },
  { to: '/profiles', label: 'Profiles' },
]

/** EIC geometric wordmark: three stacked bars forming an "E", indigo accent */
function EicMark({ className = '' }: { className?: string }) {
  return (
    <svg
      width="28"
      height="28"
      viewBox="0 0 28 28"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      {/* Top bar */}
      <rect x="4" y="4"  width="20" height="4" rx="1" fill="#4F46E5" />
      {/* Middle bar (shorter) */}
      <rect x="4" y="12" width="14" height="4" rx="1" fill="#4F46E5" />
      {/* Bottom bar */}
      <rect x="4" y="20" width="20" height="4" rx="1" fill="#4F46E5" />
    </svg>
  )
}

export default function Shell({ children, dark, onToggleDark }: ShellProps) {
  return (
    <div className="min-h-screen flex flex-col bg-white dark:bg-[#0a0a0a]">
      <header className="border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-[#0a0a0a] sticky top-0 z-40 shadow-sm dark:shadow-none">
        <div className="max-w-screen-xl mx-auto flex items-center gap-6 px-4 h-14">

          {/* Wordmark lockup */}
          <div className="flex items-center gap-2 shrink-0">
            <EicMark />
            <span className="hidden sm:block text-sm font-semibold tracking-tight text-slate-800 dark:text-slate-100 select-none">
              PAIC
            </span>
          </div>

          {/* Nav */}
          <nav className="flex items-center gap-0.5 flex-1" aria-label="Main navigation">
            {NAV_ITEMS.map(({ to, label }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm font-medium transition-colors ${
                    isActive
                      ? 'text-brand-600 bg-brand-600/10 dark:text-brand-400 dark:bg-brand-600/15'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100 dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-800'
                  }`
                }
              >
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Theme toggle: prominent, ~40x40 hit area */}
          <button
            onClick={onToggleDark}
            aria-label="Toggle theme"
            title={dark ? 'Switch to light mode' : 'Switch to dark mode'}
            className="flex items-center justify-center w-10 h-10 rounded transition-colors
                       text-slate-500 hover:text-slate-900 hover:bg-slate-100
                       dark:text-slate-400 dark:hover:text-slate-100 dark:hover:bg-slate-800
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            {dark ? (
              /* Sun icon: switch to light */
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
                  d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707M17.657 17.657l-.707-.707M6.343 6.343l-.707-.707M12 7a5 5 0 100 10A5 5 0 0012 7z" />
              </svg>
            ) : (
              /* Moon icon: switch to dark */
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round"
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
