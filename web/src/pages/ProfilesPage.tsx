import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  type OutputFormat,
  type Profile,
  type ProfileCreate,
  type ProfileMode,
} from '../lib/api'
import Modal from '../components/Modal'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

const MODES: ProfileMode[] = ['exact', 'lossless', 'budget', 'waste']
const FORMATS: OutputFormat[] = ['csv', 'json', 'xml', 'edl', 'yaml', 'plain']

const PROFILE_DRAFT_KEY = 'paic.profileDraft'

interface ProfileFormState {
  name: string
  mode: ProfileMode
  budget: string
  max_waste: string
  format: OutputFormat
  filter_spec_json: string
}

const EMPTY_FORM: ProfileFormState = {
  name: '',
  mode: 'exact',
  budget: '',
  max_waste: '',
  format: 'edl',
  filter_spec_json: '',
}

function toForm(p: Profile): ProfileFormState {
  return {
    name: p.name,
    mode: p.mode,
    budget: p.budget != null ? String(p.budget) : '',
    max_waste: p.max_waste != null ? String(p.max_waste) : '',
    format: p.format as OutputFormat,
    filter_spec_json: p.filter_spec_json ?? '',
  }
}

function ProfileModal({ profile, onClose }: { profile: Profile | null; onClose: () => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<ProfileFormState>(profile ? toForm(profile) : EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)

  const create = useMutation({
    mutationFn: (body: ProfileCreate) => api.createProfile(body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); onClose() },
    onError: (e: Error) => setError(e.message),
  })
  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Partial<ProfileCreate> }) => api.updateProfile(id, body),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); onClose() },
    onError: (e: Error) => setError(e.message),
  })

  const busy = create.isPending || update.isPending

  function buildBody(): ProfileCreate {
    return {
      name: form.name,
      mode: form.mode,
      budget: form.budget ? parseInt(form.budget, 10) : null,
      max_waste: form.max_waste ? parseFloat(form.max_waste) : null,
      format: form.format,
      filter_spec_json: form.filter_spec_json || null,
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!form.name) { setError('Name is required.'); return }
    if (form.mode === 'budget' && !form.budget) { setError('Budget is required for budget mode.'); return }
    if (form.mode === 'waste' && !form.max_waste) { setError('Max waste is required for waste mode.'); return }
    const body = buildBody()
    if (profile) { update.mutate({ id: profile.id, body }) }
    else { create.mutate(body) }
  }

  const f = form
  const set = (k: keyof ProfileFormState) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm(prev => ({ ...prev, [k]: e.target.value }))

  return (
    <Modal title={profile ? `Edit: ${profile.name}` : 'Add Profile'} onClose={onClose} size="lg">
      <form onSubmit={handleSubmit} className="space-y-3">
        {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

        <div className="grid grid-cols-2 gap-3">
          <div className="col-span-2">
            <label className="label" htmlFor="p-name">Name *</label>
            <input id="p-name" className="input" value={f.name} onChange={set('name')} />
          </div>
          <div>
            <label className="label" htmlFor="p-mode">Mode *</label>
            <select id="p-mode" className="input" value={f.mode} onChange={set('mode')}>
              {MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="p-format">Output Format *</label>
            <select id="p-format" className="input" value={f.format} onChange={set('format')}>
              {FORMATS.map(fmt => <option key={fmt} value={fmt}>{fmt}</option>)}
            </select>
          </div>
          {f.mode === 'budget' && (
            <div>
              <label className="label" htmlFor="p-budget">Budget (max prefixes) *</label>
              <input id="p-budget" className="input" type="number" min={1} value={f.budget} onChange={set('budget')} />
            </div>
          )}
          {f.mode === 'waste' && (
            <div>
              <label className="label" htmlFor="p-waste">Max Waste (0-1) *</label>
              <input id="p-waste" className="input" type="number" min={0} max={1} step={0.01}
                value={f.max_waste} onChange={set('max_waste')} />
            </div>
          )}
          <div className="col-span-2">
            <label className="label" htmlFor="p-filter">Filter Spec JSON</label>
            <textarea id="p-filter" className="input font-mono text-xs resize-none h-20"
              placeholder='{"service_types":["remote_network"]}'
              value={f.filter_spec_json} onChange={set('filter_spec_json')} />
          </div>
        </div>

        <div className="flex justify-end gap-2 pt-1">
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy && <Spinner size={3} />}
            {profile ? 'Save' : 'Create'}
          </button>
        </div>
      </form>
    </Modal>
  )
}

function ProfileRow({ profile, onApply }: { profile: Profile; onApply: () => void }) {
  const qc = useQueryClient()
  const [editing, setEditing] = useState(false)
  const [delErr, setDelErr] = useState<string | null>(null)
  const deleteMut = useMutation({
    mutationFn: api.deleteProfile,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
    onError: (e: Error) => setDelErr(e.message),
  })

  return (
    <tr className="tr-hover">
      <td className="td font-medium">{profile.name}</td>
      <td className="td"><span className="badge-blue">{profile.mode}</span></td>
      <td className="td">{profile.format}</td>
      <td className="td text-xs text-gray-500 dark:text-gray-400">
        {profile.budget != null ? `${profile.budget} pfx` : profile.max_waste != null ? `${(profile.max_waste * 100).toFixed(0)}%` : '-'}
      </td>
      <td className="td font-mono text-xs text-gray-500 dark:text-gray-400 truncate max-w-xs">
        {profile.filter_spec_json ?? '-'}
      </td>
      <td className="td">
        <div className="flex items-center gap-1">
          <button className="btn-ghost text-xs" onClick={onApply}>Apply</button>
          <button className="btn-ghost text-xs" onClick={() => setEditing(true)}>Edit</button>
          <button className="btn-ghost text-xs text-red-600 dark:text-red-400"
            onClick={async () => {
              if (!confirm(`Delete "${profile.name}"?`)) return
              try { await deleteMut.mutateAsync(profile.id) }
              catch { /* shown via delErr */ }
            }}>Del</button>
        </div>
        {delErr && <ErrorBanner message={delErr} onDismiss={() => setDelErr(null)} />}
      </td>
      {editing && <ProfileModal profile={profile} onClose={() => setEditing(false)} />}
    </tr>
  )
}

export default function ProfilesPage() {
  const { data: profiles, isLoading, error } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.listProfiles,
  })
  const [adding, setAdding] = useState(false)
  const navigate = useNavigate()

  function applyProfile(p: Profile) {
    sessionStorage.setItem(PROFILE_DRAFT_KEY, JSON.stringify(p))
    navigate('/')
  }

  return (
    <div>
      <div className="section-header">
        <h1 className="page-title">Profiles</h1>
        <button className="btn-primary" onClick={() => setAdding(true)}>
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Profile
        </button>
      </div>

      <div className="card overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-12"><Spinner size={6} /></div>
        ) : error ? (
          <div className="p-4"><ErrorBanner message={(error as Error).message} /></div>
        ) : !profiles?.length ? (
          <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
            No profiles yet. Profiles store query settings only, no credentials.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table-base">
              <thead>
                <tr>
                  <th className="th">Name</th>
                  <th className="th">Mode</th>
                  <th className="th">Format</th>
                  <th className="th">Param</th>
                  <th className="th">Filter</th>
                  <th className="th w-44">Actions</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map(p => <ProfileRow key={p.id} profile={p} onApply={() => applyProfile(p)} />)}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {adding && <ProfileModal profile={null} onClose={() => setAdding(false)} />}
    </div>
  )
}
