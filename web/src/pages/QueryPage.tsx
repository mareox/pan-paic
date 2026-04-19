import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  api,
  type AggregateResult,
  type FilterSpec,
  type OutputFormat,
  type ProfileMode,
  type QueryRequest,
} from '../lib/api'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

const FORMATS: OutputFormat[] = ['csv', 'json', 'xml', 'edl', 'yaml', 'plain']
const MODES: ProfileMode[] = ['exact', 'lossless', 'budget', 'waste']
const SERVICE_TYPES = ['all', 'remote_network', 'gp_gateway', 'clean_pipe', 'mobile_users']
const ADDR_TYPES = ['all', 'active', 'reserved', 'loopback']

const API_KEY_STORAGE = 'paic.apiKeyDraft'

interface FormState {
  apiKey: string
  prod: string
  baseUrlOverride: string
  serviceType: string
  addrType: string
  region: string
  country: string
  ipVersion: '' | '4' | '6'
  text: string
  mode: ProfileMode
  budget: string
  maxWaste: string
  format: OutputFormat
}

const DEFAULT_FORM: FormState = {
  apiKey: '',
  prod: 'prod',
  baseUrlOverride: '',
  serviceType: 'all',
  addrType: 'all',
  region: '',
  country: '',
  ipVersion: '',
  text: '',
  mode: 'exact',
  budget: '',
  maxWaste: '',
  format: 'edl',
}

function buildFilterSpec(f: FormState): FilterSpec {
  const spec: FilterSpec = {}
  if (f.region) spec.regions = [f.region]
  if (f.country) spec.countries = [f.country]
  if (f.ipVersion) spec.ip_version = (f.ipVersion === '4' ? 4 : 6)
  if (f.text) spec.text = f.text
  return spec
}

function buildRequest(f: FormState): QueryRequest {
  return {
    api_key: f.apiKey,
    prod: f.prod,
    base_url_override: f.baseUrlOverride || null,
    service_type: f.serviceType,
    addr_type: f.addrType,
    filter: buildFilterSpec(f),
    mode: f.mode,
    budget: f.budget ? parseInt(f.budget, 10) : null,
    max_waste: f.maxWaste ? parseFloat(f.maxWaste) : null,
    format: f.format,
  }
}

export default function QueryPage() {
  // Use sessionStorage so the API key never persists across browser tabs/sessions.
  const [form, setForm] = useState<FormState>(() => {
    const stored = sessionStorage.getItem(API_KEY_STORAGE)
    return stored ? { ...DEFAULT_FORM, apiKey: stored } : DEFAULT_FORM
  })
  const [preview, setPreview] = useState<AggregateResult | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  // Pull the prod registry — combobox suggestions, free-text still allowed.
  const { data: prodData } = useQuery({
    queryKey: ['known-prods'],
    queryFn: api.getKnownProds,
    staleTime: 5 * 60_000,
  })

  // Mirror the API key into sessionStorage on change so a refresh keeps it.
  useEffect(() => {
    if (form.apiKey) sessionStorage.setItem(API_KEY_STORAGE, form.apiKey)
    else sessionStorage.removeItem(API_KEY_STORAGE)
  }, [form.apiKey])

  const set = <K extends keyof FormState>(k: K, v: FormState[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  function validate(): string | null {
    if (!form.apiKey) return 'API key is required.'
    if (!form.prod && !form.baseUrlOverride) return 'Either prod or base URL override is required.'
    if (form.mode === 'budget' && !form.budget) return 'Budget is required for budget mode.'
    if (form.mode === 'waste' && !form.maxWaste) return 'Max waste is required for waste mode.'
    return null
  }

  async function runPreview() {
    const v = validate()
    if (v) { setErr(v); return }
    setErr(null); setPreviewBusy(true); setPreview(null)
    try {
      const result = await api.queryPreview(buildRequest(form))
      setPreview(result)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setPreviewBusy(false)
    }
  }

  async function runDownload() {
    const v = validate()
    if (v) { setErr(v); return }
    setErr(null); setDownloadBusy(true)
    try {
      const res = await api.query(buildRequest(form))
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body?.detail ?? res.statusText)
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `prisma-egress.${form.format}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setDownloadBusy(false)
    }
  }

  return (
    <div>
      <div className="section-header">
        <h1 className="page-title">Query</h1>
      </div>

      <div className="card p-5 space-y-5">
        {err && <ErrorBanner message={err} onDismiss={() => setErr(null)} />}

        {/* Auth row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="q-apikey">API Key *</label>
            <input
              id="q-apikey"
              className="input"
              type="password"
              autoComplete="new-password"
              placeholder="header-api-key value"
              value={form.apiKey}
              onChange={e => set('apiKey', e.target.value)}
            />
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
              Stored in browser sessionStorage only. Cleared when you close this tab.
              Never sent anywhere except your PAIC backend.
            </p>
          </div>
          <div>
            <label className="label" htmlFor="q-prod">Prisma Cloud (prod) *</label>
            <input
              id="q-prod"
              className="input"
              list="known-prods-list"
              placeholder="prod, prod6, china-prod, …"
              value={form.prod}
              onChange={e => set('prod', e.target.value)}
            />
            <datalist id="known-prods-list">
              {prodData?.prods.map(p => <option key={p} value={p} />)}
            </datalist>
          </div>
          <div>
            <label className="label" htmlFor="q-base-url">Base URL Override</label>
            <input
              id="q-base-url"
              className="input font-mono text-xs"
              placeholder="(optional, sovereign clouds)"
              value={form.baseUrlOverride}
              onChange={e => set('baseUrlOverride', e.target.value)}
            />
          </div>
        </div>

        {/* Upstream filters (sent to Prisma) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label" htmlFor="q-svc">Service Type</label>
            <select id="q-svc" className="input" value={form.serviceType}
              onChange={e => set('serviceType', e.target.value)}>
              {SERVICE_TYPES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="q-addr">Addr Type</label>
            <select id="q-addr" className="input" value={form.addrType}
              onChange={e => set('addrType', e.target.value)}>
              {ADDR_TYPES.map(a => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
        </div>

        {/* Post-fetch filters */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
          <div>
            <label className="label" htmlFor="q-region">Region</label>
            <input id="q-region" className="input" placeholder="us-east"
              value={form.region} onChange={e => set('region', e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="q-country">Country</label>
            <input id="q-country" className="input" placeholder="US"
              value={form.country} onChange={e => set('country', e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="q-ipv">IP Version</label>
            <select id="q-ipv" className="input" value={form.ipVersion}
              onChange={e => set('ipVersion', e.target.value as FormState['ipVersion'])}>
              <option value="">both</option>
              <option value="4">v4</option>
              <option value="6">v6</option>
            </select>
          </div>
          <div>
            <label className="label" htmlFor="q-text">Free-text Search</label>
            <input id="q-text" className="input" placeholder="Frankfurt"
              value={form.text} onChange={e => set('text', e.target.value)} />
          </div>
        </div>

        {/* Mode + budget/waste */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="q-mode">Aggregation Mode</label>
            <select id="q-mode" className="input" value={form.mode}
              onChange={e => set('mode', e.target.value as ProfileMode)}>
              {MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          {form.mode === 'budget' && (
            <div>
              <label className="label" htmlFor="q-budget">Budget (max prefixes)</label>
              <input id="q-budget" className="input" type="number" min={1}
                value={form.budget} onChange={e => set('budget', e.target.value)} />
            </div>
          )}
          {form.mode === 'waste' && (
            <div>
              <label className="label" htmlFor="q-waste">Max Waste (0-1)</label>
              <input id="q-waste" className="input" type="number" min={0} max={1} step={0.01}
                value={form.maxWaste} onChange={e => set('maxWaste', e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="q-fmt">Output Format</label>
            <select id="q-fmt" className="input" value={form.format}
              onChange={e => set('format', e.target.value as OutputFormat)}>
              {FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
          <button className="btn-secondary" onClick={runPreview} disabled={previewBusy}>
            {previewBusy ? <Spinner size={3} /> : 'Preview'}
          </button>
          <button className="btn-primary" onClick={runDownload} disabled={downloadBusy}>
            {downloadBusy ? <Spinner size={3} /> : `Download ${form.format.toUpperCase()}`}
          </button>
        </div>

        {/* Preview output */}
        {preview && (
          <div className="card p-4 mt-2 bg-slate-50 dark:bg-slate-900/40">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
              <Stat label="Input prefixes" value={preview.input_count} />
              <Stat label="Output prefixes" value={preview.output_count} />
              <Stat label="Announced IPs" value={preview.announced_ips} />
              <Stat label="Waste ratio" value={`${(preview.waste_ratio * 100).toFixed(2)}%`} />
            </div>
            {preview.largest_waste_prefix && (
              <div className="mt-3 text-xs text-slate-500 dark:text-slate-400 font-mono">
                Largest waste: {preview.largest_waste_prefix.prefix}
                {' '}(covers {preview.largest_waste_prefix.covers},
                announces {preview.largest_waste_prefix.announces},
                ratio {(preview.largest_waste_prefix.ratio * 100).toFixed(1)}%)
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className="text-base font-mono font-semibold text-slate-900 dark:text-slate-100">{value}</div>
    </div>
  )
}
