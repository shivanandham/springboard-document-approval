export type Me = { id: string; email: string; full_name: string; roles: string[]; permissions: string[] }

export type DocumentStatus = 'pending' | 'approved' | 'rejected'

type UserRef = { id: string; full_name: string; email: string }

export type Document = {
  id: string
  title: string
  description: string | null
  status: DocumentStatus
  version: number
  submitter: UserRef
  decided_by: UserRef | null
  decided_at: string | null
  decision_comment: string | null
  created_at: string
  updated_at: string
  file: { id: string; original_name: string; content_type: string; size_bytes: number; sha256: string; created_at: string } | null
}

export class ApiError extends Error {
  status: number
  code: string
  fields?: Record<string, unknown>

  constructor(status: number, code: string, message: string, fields?: Record<string, unknown>) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields
  }
}

let accessToken: string | null = null
let refreshing: Promise<boolean> | null = null
let onUnauthenticated = () => {}

export function setUnauthenticatedHandler(handler: () => void) {
  onUnauthenticated = handler
}

function refresh() {
  refreshing ??= fetch('/api/auth/refresh', { method: 'POST', credentials: 'include' })
    .then(async (res) => {
      accessToken = res.ok ? (await res.json()).access_token : null
      return res.ok
    })
    .catch(() => false)
    .finally(() => (refreshing = null))
  return refreshing
}

async function send(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  const res = await fetch(`/api${path}`, { ...init, headers, credentials: 'include' })
  if (res.status === 401 && retry) {
    if (await refresh()) return send(path, init, false)
    onUnauthenticated()
  }
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const error = body?.error
    throw new ApiError(res.status, error?.code ?? 'UNKNOWN', error?.message ?? 'Something went wrong. Please try again.', error?.fields)
  }
  return res
}

const json = <T>(path: string, init?: RequestInit) => send(path, init).then((res) => res.json() as Promise<T>)

export const api = {
  async login(email: string, password: string) {
    const res = await send('/auth/login', { method: 'POST', body: new URLSearchParams({ username: email, password }) }, false)
    accessToken = (await res.json()).access_token
  },
  async restoreSession() {
    return (await refresh()) ? api.me() : null
  },
  async logout() {
    await send('/auth/logout', { method: 'POST' }, false).catch(() => {})
    accessToken = null
  },
  me: () => json<Me>('/auth/me'),
  listDocuments: (status?: DocumentStatus) =>
    json<{ items: Document[]; total: number }>(
      `/documents?${new URLSearchParams({ ...(status && { status }), limit: '100', offset: '0', sort: '-created_at' })}`,
    ),
  createDocument: (body: FormData) => json<Document>('/documents', { method: 'POST', body }),
  decide: (doc: Document, decision: 'approve' | 'reject', comment?: string) =>
    json<Document>(`/documents/${doc.id}/decision`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, comment, version: doc.version }),
    }),
  async download(doc: Document) {
    const blob = await (await send(`/documents/${doc.id}/file`)).blob()
    const url = URL.createObjectURL(blob)
    const link = Object.assign(window.document.createElement('a'), { href: url, download: doc.file?.original_name ?? doc.title })
    link.click()
    setTimeout(() => URL.revokeObjectURL(url))
  },
}

export const formatDate = (iso: string) => new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })
