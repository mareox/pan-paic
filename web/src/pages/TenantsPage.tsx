import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, type Tenant, type TenantCreate, type TenantUpdate } from '../lib/api'
import Modal from '../components/Modal'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <span className="badge-gray">—</span>
  const lower = status.toLowerCase()
  if (lower === 'ok' || lower === 'success') return <span className="badge-green">{status}</span>
  if (lower === 'error' || lower === 'failed') return <span className="badge-red">{status}</span>
  return <span className="badge-yellow">{status}</span>
}

interface TenantFormState {
  name: string
  api_key: string
  base_url: string
  poll_interval_sec: string
}

const EMPTY_FORM: TenantFormState = {
  name: '',
  api_key: '',
  base_url: 'https://api.prod.datapath.prismaaccess.com',
  poll_interval_sec: '900',
}

function TenantModal({
  tenant,
  onClose,
}: {
  tenant: Tenant | null
  onClose: () => void
}) {
  const qc = useQueryClient()
  const [form, setForm] = useState<TenantFormState>(
    tenant
      ? { name: tenant.name, api_key: '', base_url: tenant.base_url, poll_interval_sec: String(tenant.poll_interval_sec) }
      : EMPTY_FORM,
  )
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (body: TenantCreate) => api.createTenant(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenants'] }); onClose() },
    onError: (e: Error) => setError(e.message),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: TenantUpdate }) => api.updateTenant(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['tenants'] }); onClose() },
    onError: (e: Error) => setError(e.message),
  })

  const busy = create.isPending || update.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    const interval = parseInt(form.poll_interval_sec, 10)
    if (tenant) {
      const body: TenantUpdate = {
        name: form.name || undefined,
        base_url: form.base_url || undefined,
        poll_interval_sec: isNaN(interval) ? undefined : interval,
      }
      if (form.api_key) body.api_key = form.api_key
      update.mutate({ id: tenant.id, body })
    } else {
      if (!form.name || !form.api_key) { setError('Name and API key are required.'); return }
      create.mutate({
        name: form.name,
        api_key: form.api_key,
        base_url: form.base_url || undefined,
        poll_interval_sec: isNaN(interval) ? undefined : interval,
      })
    }
  }

  return (
    <Modal title={tenant ? `Edit — ${tenant.name}` : 'Add Tenant'} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
        <div>
          <label className="label" htmlFor="t-name">Name *</label>
          <input id="t-name" className="input" value={form.name}
            onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
        </div>
        <div>
          <label className="label" htmlFor="t-key">
            API Key {tenant ? '(leave blank to keep current)' : '*'}
          </label>
          <input id="t-key" className="input" type="password" autoComplete="new-password"
            value={form.api_key}
            onChange={e => setForm(f => ({ ...f, api_key: e.target.value }))} />
        </div>
        <div>
          <label className="label" htmlFor="t-url">Base URL</label>
          <input id="t-url" className="input font-mono text-xs" value={form.base_url}
            onChange={e => setForm(f => ({ ...f, base_url: e.target.value }))} />
        </div>
        <div>
          <label className="label" htmlFor="t-poll">Poll Interval (seconds)</label>
          <input id="t-poll" className="input" type="number" min={300} max={86400}
            value={form.poll_interval_sec}
            onChange={e => setForm(f => ({ ...f, poll_interval_sec: e.target.value }))} />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy && <Spinner size={3} />}
            {tenant ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function TestConnectionCell({ tenant }: { tenant: Tenant }) {
  const [result, setResult] = useState<{ success: boolean; detail: string } | null>(null)
  const [busy, setBusy] = useState(false)

  async function run() {
    setBusy(true)
    setResult(null)
    try {
      const r = await api.testConnection(tenant.id)
      setResult(r)
    } catch (e: unknown) {
      setResult({ success: false, detail: e instanceof Error ? e.message : String(e) })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex items-center gap-2">
      <button className="btn-secondary text-xs" onClick={run} disabled={busy}>
        {busy ? <Spinner size={3} /> : 'Test'}
      </button>
      {result && (
        <span className={result.success ? 'badge-green' : 'badge-red'}>
          {result.success ? 'OK' : 'Fail'}
        </span>
      )}
    </div>
  )
}

export default function TenantsPage() {
  const qc = useQueryClient()
  const { data: tenants, isLoading, error } = useQuery({
    queryKey: ['tenants'],
    queryFn: api.listTenants,
  })
  const deleteMut = useMutation({
    mutationFn: api.deleteTenant,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['tenants'] }),
  })

  const [modalTenant, setModalTenant] = useState<Tenant | 'new' | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)

  function fmtDate(s: string | null) {
    if (!s) return '—'
    return new Date(s).toLocaleString()
  }

  return (
    <div>
      <div className="section-header">
        <h1 className="page-title">Tenants</h1>
        <button className="btn-primary" onClick={() => setModalTenant('new')}>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Tenant
        </button>
      </div>

      {deleteError && <div className="mb-3"><ErrorBanner message={deleteError} onDismiss={() => setDeleteError(null)} /></div>}

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12"><Spinner size={6} /></div>
        ) : error ? (
          <div className="p-4"><ErrorBanner message={(error as Error).message} /></div>
        ) : !tenants?.length ? (
          <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
            No tenants yet. Add one to get started.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Base URL</th>
                  <th className="th">Poll (s)</th>
                  <th className="th">Last Fetch</th>
                  <th className="th">Status</th>
                  <th className="th">Connection</th>
                  <th className="th w-24">Actions</th>
                </tr>
              </thead>
              <tbody>
                {tenants.map(t => (
                  <tr key={t.id} className="tr-hover">
                    <td className="td font-medium">{t.name}</td>
                    <td className="td font-mono text-xs text-gray-500 dark:text-gray-400">{t.base_url}</td>
                    <td className="td">{t.poll_interval_sec}</td>
                    <td className="td text-xs text-gray-500 dark:text-gray-400">{fmtDate(t.last_fetch_at)}</td>
                    <td className="td"><StatusBadge status={t.last_fetch_status} /></td>
                    <td className="td"><TestConnectionCell tenant={t} /></td>
                    <td className="td">
                      <div className="flex items-center gap-1">
                        <button className="btn-ghost text-xs" onClick={() => setModalTenant(t)}>Edit</button>
                        <button
                          className="btn-ghost text-xs text-red-600 hover:text-red-700 dark:text-red-400"
                          onClick={async () => {
                            if (!confirm(`Delete "${t.name}"?`)) return
                            try { await deleteMut.mutateAsync(t.id) }
                            catch (e: unknown) { setDeleteError(e instanceof Error ? e.message : String(e)) }
                          }}
                        >
                          Del
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {modalTenant !== null && (
        <TenantModal
          tenant={modalTenant === 'new' ? null : modalTenant}
          onClose={() => setModalTenant(null)}
        />
      )}
    </div>
  )
}
