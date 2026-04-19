import { useEffect, type ReactNode } from 'react'

interface ModalProps {
  title: string
  onClose: () => void
  children: ReactNode
  size?: 'sm' | 'md' | 'lg'
}

export default function Modal({ title, onClose, children, size = 'md' }: ModalProps) {
  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const widths = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 dark:bg-black/70 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className={`card w-full ${widths[size]} mx-4 p-6 shadow-2xl
                       bg-white dark:bg-zinc-900 border-slate-200 dark:border-slate-700`}>
        {/* Header */}
        <div className="flex items-center justify-between mb-5">
          <h2
            id="modal-title"
            className="text-base font-semibold text-slate-900 dark:text-slate-100 font-sans"
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close"
            className="flex items-center justify-center w-8 h-8 rounded transition-colors
                       text-slate-400 hover:text-slate-700 hover:bg-slate-100
                       dark:text-slate-500 dark:hover:text-slate-200 dark:hover:bg-slate-800
                       focus:outline-none focus-visible:ring-2 focus-visible:ring-brand-600"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        {children}
      </div>
    </div>
  )
}
