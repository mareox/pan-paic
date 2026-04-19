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
  if (res.status === 204) return undefined as unknown as T
  return res.json()
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
}

export type ProfileUpdate = Partial<ProfileCreate>

// ---- Query types ----
export interface FilterSpec {
  service_types?: string[] | null
  addr_types?: string[] | null
  regions?: string[] | null
  countries?: string[] | null
  location_names?: string[] | null
  ip_version?: 4 | 6 | null
  text?: string | null
}

export interface QueryRequest {
  api_key: string
  prod: string
  base_url_override?: string | null
  service_type?: string
  addr_type?: string
  filter?: FilterSpec
  mode: ProfileMode
  budget?: number | null
  max_waste?: number | null
  format: OutputFormat
}

export interface AggregateResult {
  output_prefixes: string[]
  input_count: number
  output_count: number
  covered_ips: number
  announced_ips: number
  waste_count: number
  waste_ratio: number
  largest_waste_prefix: { prefix: string; covers: number; announces: number; ratio: number } | null
  mode: string
  generated_at: string
}

export interface KnownProds {
  prods: string[]
}

// ---- API calls ----
export const api = {
  // Profiles
  listProfiles: () => request<Profile[]>('/api/profiles'),
  createProfile: (body: ProfileCreate) =>
    request<Profile>('/api/profiles', { method: 'POST', body: JSON.stringify(body) }),
  updateProfile: (id: string, body: ProfileUpdate) =>
    request<Profile>(`/api/profiles/${id}`, { method: 'PUT', body: JSON.stringify(body) }),
  deleteProfile: (id: string) =>
    request<void>(`/api/profiles/${id}`, { method: 'DELETE' }),

  // Stateless query
  query: (body: QueryRequest) =>
    fetch('/api/query', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  queryPreview: (body: QueryRequest) =>
    request<AggregateResult>('/api/query/preview', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  getKnownProds: () => request<KnownProds>('/api/known-prods'),
}
