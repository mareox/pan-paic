import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import ErrorBanner from '../components/ErrorBanner'
import Spinner from '../components/Spinner'

const SERVICE_TYPES = ['remote_network', 'gp_gateway', 'clean_pipe', 'mobile_users']
const ADDR_TYPES = ['active', 'candidate', 'loopback']
const FORMATS = ['csv', 'json', 'xml', 'edl', 'yaml', 'plain'] as const
const MODES = ['exact', 'lossless', 'budget', 'waste'] as const

type Format = typeof FORMATS[number]
type SumMode = typeof MODES[number]

interface ReportForm {
  tenant_id: string
  service_types: string[]
  addr_types: string[]
  region: string
  country: string
  ip_version: 'v4' | 'v6' | 'both'
  search: string
  mode: SumMode
  budget: string
  max_waste: string
  format: Format
}

const DEFAULT_FORM: ReportForm = {
  tenant_id: '',
  service_types: [],
  addr_types: [],
  region: '',
  country: '',
  ip_version: 'both',
  search: '',
  mode: 'exact',
  budget: '',
  max_waste: '',
  format: 'json',
}

function MultiCheck({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: string[]
  value: string[]
  onChange: (v: string[]) => void
}) {
  return (
    <fieldset>
      <legend className="label">{label}</legend>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map(opt => (
          <label key={opt} className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              className="rounded border-gray-300 dark:border-gray-700 text-brand-600 focus:ring-brand-500"
              checked={value.includes(opt)}
              onChange={e => {
                if (e.target.checked) onChange([...value, opt])
                else onChange(value.filter(v => v !== opt))
              }}
            />
            {opt}
          </label>
        ))}
      </div>
    </fieldset>
  )
}

export default function ReportsPage() {
  const [form, setForm] = useState<ReportForm>(DEFAULT_FORM)
  const [downloading, setDownloading] = useState(false)
  const [dlErr, setDlErr] = useState<string | null>(null)

  const { data: tenants } = useQuery({ queryKey: ['tenants'], queryFn: api.listTenants })

  const set = <K extends keyof ReportForm>(k: K, v: ReportForm[K]) =>
    setForm(prev => ({ ...prev, [k]: v }))

  function buildUrl() {
    const params: Record<string, string | undefined> = {
      format: form.format,
      service_type: form.service_types.length ? form.service_types.join(',') : undefined,
      addr_type: form.addr_types.length ? form.addr_types.join(',') : undefined,
      region: form.region || undefined,
      country: form.country || undefined,
    }
    return api.exportUrl(params)
  }

  async function handleDownload() {
    setDownloading(true); setDlErr(null)
    try {
      const url = buildUrl()
      const res = await fetch(url)
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: res.statusText }))
        throw new Error(body?.detail ?? res.statusText)
      }
      const blob = await res.blob()
      const a = document.createElement('a')
      a.href = URL.createObjectURL(blob)
      a.download = `prisma-export.${form.format}`
      a.click()
      URL.revokeObjectURL(a.href)
    } catch (e: unknown) {
      setDlErr(e instanceof Error ? e.message : String(e))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div>
      <div className="section-header">
        <h1 className="page-title">Reports</h1>
      </div>

      <div className="card p-5 space-y-5">
        {dlErr && <ErrorBanner message={dlErr} onDismiss={() => setDlErr(null)} />}

        {/* Tenant + Format row */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="r-tenant">Tenant</label>
            <select id="r-tenant" className="input" value={form.tenant_id}
              onChange={e => set('tenant_id', e.target.value)}>
              <option value="">All tenants</option>
              {tenants?.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="r-format">Output Format</label>
            <select id="r-format" className="input" value={form.format}
              onChange={e => set('format', e.target.value as Format)}>
              {FORMATS.map(f => <option key={f} value={f}>{f}</option>)}
            </select>
          </div>
          <div>
            <label className="label" htmlFor="r-search">Free-text Search</label>
            <input id="r-search" className="input" placeholder="10.0.0.0"
              value={form.search} onChange={e => set('search', e.target.value)} />
          </div>
        </div>

        {/* Checkboxes */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <MultiCheck
            label="Service Type"
            options={SERVICE_TYPES}
            value={form.service_types}
            onChange={v => set('service_types', v)}
          />
          <MultiCheck
            label="Addr Type"
            options={ADDR_TYPES}
            value={form.addr_types}
            onChange={v => set('addr_types', v)}
          />
        </div>

        {/* Region / Country / IP Version */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="r-region">Region</label>
            <input id="r-region" className="input" placeholder="us-west"
              value={form.region} onChange={e => set('region', e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="r-country">Country</label>
            <input id="r-country" className="input" placeholder="US"
              value={form.country} onChange={e => set('country', e.target.value)} />
          </div>
          <fieldset>
            <legend className="label">IP Version</legend>
            <div className="flex items-center gap-4 mt-1">
              {(['v4', 'v6', 'both'] as const).map(v => (
                <label key={v} className="flex items-center gap-1.5 text-sm text-gray-700 dark:text-gray-300 cursor-pointer">
                  <input type="radio" name="ip_version" value={v}
                    className="text-brand-600 focus:ring-brand-500"
                    checked={form.ip_version === v}
                    onChange={() => set('ip_version', v)} />
                  {v}
                </label>
              ))}
            </div>
          </fieldset>
        </div>

        {/* Summarization mode */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div>
            <label className="label" htmlFor="r-mode">Summarization Mode</label>
            <select id="r-mode" className="input" value={form.mode}
              onChange={e => set('mode', e.target.value as SumMode)}>
              {MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
          {form.mode === 'budget' && (
            <div>
              <label className="label" htmlFor="r-budget">Budget (max prefixes)</label>
              <input id="r-budget" className="input" type="number" min={1}
                value={form.budget} onChange={e => set('budget', e.target.value)} />
            </div>
          )}
          {form.mode === 'waste' && (
            <div>
              <label className="label" htmlFor="r-waste">Max Waste %</label>
              <input id="r-waste" className="input" type="number" min={0} max={100} step={1}
                value={form.max_waste} onChange={e => set('max_waste', e.target.value)} />
            </div>
          )}
        </div>

        {/* Download */}
        <div className="flex items-center gap-3 pt-1 border-t border-gray-100 dark:border-gray-800">
          <button className="btn-primary" onClick={handleDownload} disabled={downloading}>
            {downloading ? <Spinner size={3} /> : (
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            )}
            Download {form.format.toUpperCase()}
          </button>
          <span className="text-xs font-mono text-gray-400 dark:text-gray-600 truncate">{buildUrl()}</span>
        </div>
      </div>
    </div>
  )
}
