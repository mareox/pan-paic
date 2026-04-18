import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, type Diff } from '../lib/api'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

function DiffRow({ diff }: { diff: Diff }) {
  const [expanded, setExpanded] = useState(false)

  const addedCount = Object.values(diff.added).reduce((sum, a) => sum + a.length, 0)
  const removedCount = Object.values(diff.removed).reduce((sum, a) => sum + a.length, 0)

  const hasChanges = addedCount > 0 || removedCount > 0

  return (
    <>
      <tr className="tr-hover">
        <td className="td text-xs font-mono text-gray-500 dark:text-gray-400">
          {new Date(diff.computed_at).toLocaleString()}
        </td>
        <td className="td">
          {addedCount > 0 ? (
            <span className="badge-green">+{addedCount}</span>
          ) : (
            <span className="badge-gray">+0</span>
          )}
        </td>
        <td className="td">
          {removedCount > 0 ? (
            <span className="badge-red">−{removedCount}</span>
          ) : (
            <span className="badge-gray">−0</span>
          )}
        </td>
        <td className="td text-gray-500 dark:text-gray-400">{diff.unchanged_count}</td>
        <td className="td">
          <button
            className="btn-ghost text-xs"
            onClick={() => setExpanded(e => !e)}
            disabled={!hasChanges}
            aria-expanded={expanded}
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={5} className="td px-4 py-3 bg-gray-50 dark:bg-gray-900/50">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {/* Added */}
              {addedCount > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-green-700 dark:text-green-400 mb-2 uppercase tracking-wide">
                    Added ({addedCount})
                  </h3>
                  {Object.entries(diff.added).map(([svc, prefixes]) =>
                    prefixes.length > 0 && (
                      <div key={svc} className="mb-2">
                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{svc}</div>
                        <div className="flex flex-wrap gap-1">
                          {prefixes.map(p => (
                            <span key={p} className="inline-block font-mono text-xs bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-300 border border-green-200 dark:border-green-800 rounded px-1.5 py-0.5">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                </div>
              )}
              {/* Removed */}
              {removedCount > 0 && (
                <div>
                  <h3 className="text-xs font-semibold text-red-700 dark:text-red-400 mb-2 uppercase tracking-wide">
                    Removed ({removedCount})
                  </h3>
                  {Object.entries(diff.removed).map(([svc, prefixes]) =>
                    prefixes.length > 0 && (
                      <div key={svc} className="mb-2">
                        <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{svc}</div>
                        <div className="flex flex-wrap gap-1">
                          {prefixes.map(p => (
                            <span key={p} className="inline-block font-mono text-xs bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 border border-red-200 dark:border-red-800 rounded px-1.5 py-0.5">
                              {p}
                            </span>
                          ))}
                        </div>
                      </div>
                    )
                  )}
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function DiffsPage() {
  const [tenantId, setTenantId] = useState('')
  const { data: tenants } = useQuery({ queryKey: ['tenants'], queryFn: api.listTenants })

  const { data: diffs, isLoading, error, refetch } = useQuery({
    queryKey: ['diffs', tenantId],
    queryFn: () => api.listDiffs(tenantId),
    enabled: !!tenantId,
  })

  return (
    <div>
      <div className="section-header">
        <h1 className="page-title">Diffs</h1>
        <div className="flex items-center gap-2">
          <select
            className="input w-52"
            value={tenantId}
            onChange={e => setTenantId(e.target.value)}
            aria-label="Select tenant"
          >
            <option value="">Select tenant…</option>
            {tenants?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
          {tenantId && (
            <button className="btn-secondary" onClick={() => refetch()} aria-label="Refresh diffs">
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {!tenantId ? (
        <div className="card py-16 text-center text-sm text-gray-500 dark:text-gray-400">
          Select a tenant to view its diff history.
        </div>
      ) : (
        <div className="card overflow-hidden">
          {isLoading ? (
            <div className="flex items-center justify-center py-12"><Spinner size={6} /></div>
          ) : error ? (
            <div className="p-4"><ErrorBanner message={(error as Error).message} /></div>
          ) : !diffs?.length ? (
            <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
              No diffs recorded for this tenant yet.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table-base">
                <thead>
                  <tr>
                    <th className="th">Computed At</th>
                    <th className="th">Added</th>
                    <th className="th">Removed</th>
                    <th className="th">Unchanged</th>
                    <th className="th w-24"></th>
                  </tr>
                </thead>
                <tbody>
                  {diffs.map(d => <DiffRow key={d.id} diff={d} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
