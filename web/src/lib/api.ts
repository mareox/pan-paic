/** Typed fetch wrapper — raises on non-2xx responses. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body?.detail ?? detail
    } catch {
      // ignore parse error
    }
    throw new ApiError(res.status, detail)
  }
  // 204 No Content
  if (res.status === 204) return undefined as unknown as T
  return res.json()
}

// ---- Tenant types ----
export interface Tenant {
  id: string
  name: string
  base_url: string
  poll_interval_sec: number
  last_fetch_at: string | null
  last_fetch_status: string | null
  created_at: string
}

export interface TenantCreate {
  name: string
  api_key: string
  base_url?: string
  poll_interval_sec?: number
}

export interface TenantUpdate {
  name?: string
  api_key?: string
  base_url?: string
  poll_interval_sec?: number
}

export interface TestConnectionResponse {
  success: boolean
  detail: string
}

// ---- Profile types ----
export type ProfileMode = 'exact' | 'lossless' | 'budget' | 'waste'
export type OutputFormat = 'csv' | 'json' | 'xml' | 'edl' | 'yaml' | 'plain'

export interface Profile {
  id: string
  name: string
  mode: ProfileMode
  budget: number | null
  max_waste: number | null
  format: OutputFormat
  filter_spec_json: string | null
  schedule_cron: string | null
  created_at: string
  updated_at: string
}

export interface ProfileCreate {
  name: string
  mode: ProfileMode
  budget?: number | null
  max_waste?: number | null
  format: OutputFormat
  filter_spec_json?: string | null
  schedule_cron?: string | null
}

export interface ProfileUpdate extends Partial<ProfileCreate> {}

// ---- Diff types ----
export interface Diff {
  id: string
  tenant_id: string
  computed_at: string
  added: Record<string, string[]>
  removed: Record<string, string[]>
  unchanged_count: number
}

// ---- API calls ----
export const api = {
  // Tenants
  listTenants: () => request<Tenant[]>('/api/tenants'),
  createTenant: (body: TenantCreate) =>
    request<Tenant>('/api/tenants', { method: 'POST', body: JSON.stringify(body) }),
  updateTenant: (id: string, body: TenantUpdate) =>
    request<Tenant>(`/api/tenants/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteTenant: (id: string) =>
    request<void>(`/api/tenants/${id}`, { method: 'DELETE' }),
  testConnection: (id: string) =>
    request<TestConnectionResponse>(`/api/tenants/${id}/test-connection`, { method: 'POST' }),

  // Profiles
  listProfiles: () => request<Profile[]>('/api/profiles'),
  createProfile: (body: ProfileCreate) =>
    request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify(body) }),
  updateProfile: (id: string, body: ProfileUpdate) =>
    request<Profile>(`/api/profiles/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteProfile: (id: string) =>
    request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),

  // Reports
  exportUrl: (params: Record<string, string | undefined>) => {
    const q = new URLSearchParams()
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== '') q.set(k, v)
    }
    return `/api/reports/export?${q.toString()}`
  },

  // Diffs
  listDiffs: (tenantId: string, limit = 20, offset = 0) =>
    request<Diff[]>(`/api/tenants/${tenantId}/diffs?limit=${limit}&offset=${offset}`),
}
