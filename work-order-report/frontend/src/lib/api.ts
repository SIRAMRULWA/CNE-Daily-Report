import type {
  LoginResponse, RecordsResponse, SummaryResponse,
  DivisionsResponse, DivisionGroupsResponse,
  ActivityLogResponse, HealthResponse, RunLogResponse,
  AdminUser, LoginHistoryResponse, AdminSessionsResponse, Filters,
  DailyReportLiveResponse,
  DailyReportViewResponse, SlaStatus, Category,
  HelixRawReportFieldsResponse, HelixRawReportFiltersResponse,
  HelixRawReportRequest, HelixRawReportResponse,
  ManualReportEmailPayload, ManualReportEmailResponse,
  ReportEmailDeliveriesResponse, ReportEmailSubscription,
  ReportEmailSubscriptionPayload, ReportEmailSubscriptionsResponse,
  WorkspaceRecord, SummaryRow, DailyReportLiveRecord,
  TaskReminderExecution, TaskReminderExecutionStatus,
  TaskReminderExecutionsResponse, TaskReminderSubscription,
  TaskReminderSubscriptionPayload, TaskReminderSubscriptionsResponse,
} from '@/types'

const BASE = (process.env.NEXT_PUBLIC_API_URL ?? '').replace(/\/$/, '')
const API_BASE_PATH = '/api/v1'
const BACKEND_RETRY_COUNT = 3
const BACKEND_RETRY_DELAY_MS = 800
const REQUEST_TIMEOUT_MS = 8_000
const BACKEND_UNAVAILABLE_STATUSES = new Set([502, 504])

export const BACKEND_UNAVAILABLE_EVENT = 'backend-unavailable'

interface ApiErrorBody {
  message?: string
  detail?: string | Array<{ field?: string; message?: string; msg?: string }>
  error_code?: string
  request_id?: string
  details?: Array<{ field?: string; message?: string; msg?: string }> | Record<string, unknown>
}

export class ApiError extends Error {
  status: number
  errorCode?: string
  requestId?: string
  details?: ApiErrorBody['details']

  constructor(message: string, status: number, body: ApiErrorBody = {}, requestId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.errorCode = body.error_code
    this.requestId = requestId ?? body.request_id
    this.details = body.details
  }
}

export class BackendUnavailableError extends Error {
  requestId?: string

  constructor(message = 'Backend service is not responding. Please try again later.', requestId?: string) {
    super(message)
    this.name = 'BackendUnavailableError'
    this.requestId = requestId
  }
}

const SESSION_END_ERROR_CODES = new Set([
  'AUTHENTICATION_REQUIRED',
  'SESSION_EXPIRED',
  'SESSION_REVOKED',
  'SESSION_NOT_FOUND',
])

export function isBackendUnavailableError(error: unknown): error is BackendUnavailableError {
  return error instanceof BackendUnavailableError || (
    error instanceof Error && error.name === 'BackendUnavailableError'
  )
}

function wait(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms))
}

function notifyBackendUnavailable(message?: string): void {
  if (typeof window === 'undefined') return
  window.dispatchEvent(new CustomEvent(BACKEND_UNAVAILABLE_EVENT, {
    detail: { message },
  }))
}

function formatValidationDetails(details: ApiErrorBody['details']): string | null {
  if (!Array.isArray(details) || details.length === 0) return null
  return details
    .map((item) => {
      const message = item.message ?? item.msg
      return item.field && message ? `${item.field}: ${message}` : message
    })
    .filter(Boolean)
    .join(', ') || null
}

function validRequestId(value: string | null | undefined): string | undefined {
  const requestId = value?.trim()
  return requestId && requestId.length <= 128 && /^[A-Za-z0-9._:-]+$/.test(requestId)
    ? requestId
    : undefined
}

function createRequestId(): string {
  if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID()
  return `fe-${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
}

function withSupportReference(message: string, errorCode?: string, requestId?: string): string {
  const parts = [message]
  if (errorCode) parts.push(`Error code: ${errorCode}`)
  if (requestId) parts.push(`Reference: ${requestId}`)
  return parts.join(' ')
}

function messageFromApiError(body: ApiErrorBody, requestId?: string): string {
  const detailsMessage = formatValidationDetails(body.details)
  const safeMessage = typeof body.message === 'string' && body.message.trim()
    ? body.message.trim()
    : typeof body.detail === 'string' && body.detail.trim()
      ? body.detail.trim()
      : 'We couldn\u2019t complete this request. Please try again or contact support.'

  let validationMessage = detailsMessage
  if (Array.isArray(body.detail)) {
    validationMessage ||= body.detail
      .map((item) => {
        const message = item.message ?? item.msg
        return item.field && message ? `${item.field}: ${message}` : message
      })
      .filter(Boolean)
      .join(', ')
  }

  const message = validationMessage ? `${safeMessage} ${validationMessage}` : safeMessage
  return withSupportReference(message, body.error_code, requestId)
}

async function fetchWithTimeout(url: string, options: RequestInit): Promise<Response> {
  const controller = new AbortController()
  const timeout = globalThis.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)

  try {
    return await fetch(url, {
      ...options,
      signal: controller.signal,
    })
  } finally {
    globalThis.clearTimeout(timeout)
  }
}

// ─── Token storage ───────────────────────────────────────────────────────────

export function getToken(): string | null {
  if (typeof window === 'undefined') return null
  return localStorage.getItem('itil_token')
}

export function setToken(token: string): void {
  localStorage.setItem('itil_token', token)
}

export function clearToken(): void {
  localStorage.removeItem('itil_token')
  localStorage.removeItem('itil_user')
}

export function setUser(user: LoginResponse['user']): void {
  localStorage.setItem('itil_user', JSON.stringify(user))
}

export function getUser(): LoginResponse['user'] | null {
  if (typeof window === 'undefined') return null
  const raw = localStorage.getItem('itil_user')
  return raw ? JSON.parse(raw) : null
}

// ─── Core fetch ──────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  requireAuth = true,
  treatGatewayErrorsAsUnavailable = true,
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  }
  const requestId = validRequestId(headers['X-Request-ID'] ?? headers['x-request-id']) ?? createRequestId()
  delete headers['x-request-id']
  headers['X-Request-ID'] = requestId

  if (requireAuth) {
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
  }

  let res: Response | null = null

  for (let attempt = 1; attempt <= BACKEND_RETRY_COUNT; attempt += 1) {
    try {
      res = await fetchWithTimeout(`${BASE}${API_BASE_PATH}${path}`, { ...options, headers })
      if (!treatGatewayErrorsAsUnavailable || !BACKEND_UNAVAILABLE_STATUSES.has(res.status)) break
    } catch {
      if (attempt === BACKEND_RETRY_COUNT) {
        const message = withSupportReference('Backend service is not responding. Please try again later.', undefined, requestId)
        notifyBackendUnavailable(message)
        throw new BackendUnavailableError(message, requestId)
      }
    }

    if (attempt < BACKEND_RETRY_COUNT) {
      await wait(BACKEND_RETRY_DELAY_MS * attempt)
    }
  }

  if (!res) {
    const message = withSupportReference('Backend service is not responding. Please try again later.', undefined, requestId)
    notifyBackendUnavailable(message)
    throw new BackendUnavailableError(message, requestId)
  }

  if (treatGatewayErrorsAsUnavailable && BACKEND_UNAVAILABLE_STATUSES.has(res.status)) {
    const responseRequestId = validRequestId(res.headers.get('x-request-id')) ?? requestId
    const message = withSupportReference('Backend service is not responding. Please try again later.', undefined, responseRequestId)
    notifyBackendUnavailable(message)
    throw new BackendUnavailableError(message, responseRequestId)
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as ApiErrorBody
    const responseRequestId = validRequestId(body.request_id)
      ?? validRequestId(res.headers.get('x-request-id'))
      ?? requestId
    const message = messageFromApiError(body, responseRequestId)

    if (body.error_code === 'PASSWORD_CHANGE_REQUIRED') {
      if (typeof window !== 'undefined' && window.location.pathname !== '/admin/change-password') {
        window.location.href = '/admin/change-password'
      }
      throw new ApiError(message, res.status, body, responseRequestId)
    }

    const shouldEndSession = requireAuth && (
      (body.error_code && SESSION_END_ERROR_CODES.has(body.error_code)) ||
      (res.status === 401 && !body.error_code)
    )

    if (shouldEndSession) {
      clearToken()
      if (typeof window !== 'undefined') window.location.href = '/login'
      throw new ApiError(message, res.status, body, responseRequestId)
    }

    if (res.status === 503) {
      notifyBackendUnavailable(message)
      throw new BackendUnavailableError(message, responseRequestId)
    }
    throw new ApiError(message, res.status, body, responseRequestId)
  }

  if (res.status === 204) return undefined as T

  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

function buildQuery(params: Record<string, string | number | boolean | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '' && v !== null) p.set(k, String(v))
  }
  return p.toString() ? `?${p.toString()}` : ''
}

function finiteNumberOrNull(value: unknown): number | null {
  if (value == null || value === '') return null
  const number = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(number) ? number : null
}

function finiteNumberOrZero(value: unknown): number {
  return finiteNumberOrNull(value) ?? 0
}

function normalizeWorkspaceRecord(record: WorkspaceRecord): WorkspaceRecord {
  return {
    ...record,
    hours_open: finiteNumberOrNull(record.hours_open),
  }
}

function normalizeDailyReportRecord(record: DailyReportLiveRecord): DailyReportLiveRecord {
  return {
    ...record,
    hours_open: finiteNumberOrNull(record.hours_open),
  }
}

function normalizeSummaryRow(row: SummaryRow): SummaryRow {
  return {
    ...row,
    avg_hours_open: finiteNumberOrNull(row.avg_hours_open),
  }
}

function normalizeDailyReportRecords(response: DailyReportLiveResponse): DailyReportLiveResponse {
  return {
    ...response,
    count: finiteNumberOrZero(response.count),
    records: response.records.map(normalizeDailyReportRecord),
  }
}

function normalizeDailyReportView(response: DailyReportViewResponse): DailyReportViewResponse {
  const kpis = response.kpis

  return {
    ...response,
    kpis: {
      ...kpis,
      total_incidents: finiteNumberOrZero(kpis.total_incidents),
      total_changes: finiteNumberOrZero(kpis.total_changes),
      total_access: finiteNumberOrZero(kpis.total_access),
      total_events: finiteNumberOrZero(kpis.total_events),
      total_open: finiteNumberOrZero(kpis.total_open),
      total_nearing: finiteNumberOrZero(kpis.total_nearing),
      total_breached: finiteNumberOrZero(kpis.total_breached),
      total_within: kpis.total_within == null
        ? undefined
        : finiteNumberOrZero(kpis.total_within),
      total_closed_success_yesterday: finiteNumberOrZero(
        kpis.total_closed_success_yesterday,
      ),
      closed_incidents: finiteNumberOrZero(kpis.closed_incidents),
      closed_changes: finiteNumberOrZero(kpis.closed_changes),
      closed_access: finiteNumberOrZero(kpis.closed_access),
      closed_events: finiteNumberOrZero(kpis.closed_events),
      successful_closures_by_group: kpis.successful_closures_by_group.map(
        (closure) => ({
          ...closure,
          total_closed_success: finiteNumberOrZero(
            closure.total_closed_success,
          ),
        }),
      ),
      divisions: kpis.divisions?.map((division) => ({
        ...division,
        total_incidents: finiteNumberOrZero(division.total_incidents),
        total_changes: finiteNumberOrZero(division.total_changes),
        total_access: finiteNumberOrZero(division.total_access),
        total_events: finiteNumberOrZero(division.total_events),
        total_open: finiteNumberOrZero(division.total_open),
        total_nearing: finiteNumberOrZero(division.total_nearing),
        total_breached: finiteNumberOrZero(division.total_breached),
      })),
    },
    summary: {
      ...response.summary,
      count: finiteNumberOrZero(response.summary.count),
      rows: response.summary.rows.map((row) => ({
        ...row,
        incident_count: finiteNumberOrZero(row.incident_count),
        change_count: finiteNumberOrZero(row.change_count),
        access_count: finiteNumberOrZero(row.access_count),
        event_count: finiteNumberOrZero(row.event_count),
        total_count: finiteNumberOrZero(row.total_count),
      })),
    },
    groups: response.groups.map((group) => ({
      ...group,
      active_records: finiteNumberOrZero(group.active_records),
      assignee_group_count: group.assignee_group_count == null
        ? undefined
        : finiteNumberOrZero(group.assignee_group_count),
    })),
    available_dates: response.available_dates
      ? {
          ...response.available_dates,
          count: finiteNumberOrZero(response.available_dates.count),
          limit: finiteNumberOrZero(response.available_dates.limit),
          dates: response.available_dates.dates.map((date) => ({
            ...date,
            division_count: finiteNumberOrZero(date.division_count),
            assignee_group_count: finiteNumberOrZero(
              date.assignee_group_count,
            ),
            total_open: finiteNumberOrZero(date.total_open),
          })),
        }
      : undefined,
    records: response.records
      ? normalizeDailyReportRecords(response.records)
      : undefined,
  }
}

// ─── Auth ────────────────────────────────────────────────────────────────────

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<LoginResponse>('/auth/sessions', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }, false),

  logout: () =>
    apiFetch<void>('/auth/sessions/current', { method: 'DELETE' }),

  me: () =>
    apiFetch<LoginResponse['user']>('/users/current'),

  changePassword: (current: string, next: string) =>
    apiFetch<void>('/users/current/password', {
      method: 'PATCH',
      body: JSON.stringify({ current_password: current, new_password: next }),
    }),
}

// ─── Workspace ───────────────────────────────────────────────────────────────

export const workspaceApi = {
  records: (filters: Partial<Filters>) =>
    apiFetch<RecordsResponse>(`/operational-records${buildQuery({
      division: filters.division,
      assignee_group: filters.assignee_group,
      sla: filters.sla,
      category: filters.category,
      priority: filters.priority,
      search: filters.search,
      include_excluded: filters.include_excluded ? 'true' : undefined,
      limit: filters.limit ?? 100,
      offset: filters.offset ?? 0,
    })}`).then(response => response.data_available
      ? { ...response, records: response.records.map(normalizeWorkspaceRecord) }
      : { ...response, records: [], count: 0, total: 0 }),

  summary: (division?: string, assigneeGroup?: string, includeExcluded?: boolean) =>
    apiFetch<SummaryResponse>(`/operational-records/summary${buildQuery({
      division,
      assignee_group: assigneeGroup,
      include_excluded: includeExcluded ? 'true' : undefined,
    })}`).then(response => response.data_available
      ? { ...response, rows: response.rows.map(normalizeSummaryRow) }
      : { ...response, rows: [], count: 0 }),

  activityLog: (
    limit = 50,
    offset = 0,
    entityType?: string | string[],
    actor?: string,
    entityIdPrefix?: string,
  ) =>
    apiFetch<ActivityLogResponse>(`/audit-events${buildQuery({
      entity_type: Array.isArray(entityType) ? undefined : entityType,
      entity_types: Array.isArray(entityType) ? entityType.join(',') : undefined,
      entity_id_prefix: entityIdPrefix,
      actor,
      limit,
      offset,
    })}`),
}

// ─── Daily Report ─────────────────────────────────────────────────────────────

export const dailyReportApi = {
  view: (params: {
    date?: string
    period?: 'day' | 'week'
    division?: string
    assignee_group?: string
    include_dates?: boolean
    date_limit?: number
    include_records?: boolean
    sla?: SlaStatus | ''
    category?: Category | ''
  } = {}) =>
    apiFetch<DailyReportViewResponse>(`/daily-reports${buildQuery({
      report_date: params.date,
      period: params.period,
      division: params.division,
      assignee_group: params.assignee_group,
      include_dates: params.include_dates,
      date_limit: params.date_limit,
      include_records: params.include_records,
      sla: params.sla,
      category: params.category,
    })}`).then(normalizeDailyReportView),

  records: (filters: {
    date?: string
    period?: 'day' | 'week'
    division?: string
    assignee_group?: string
    sla?: SlaStatus | ''
    category?: Category | ''
  } = {}) =>
    apiFetch<DailyReportLiveResponse>(`/daily-reports/records${buildQuery({
      report_date: filters.date,
      period: filters.period,
      division: filters.division,
      assignee_group: filters.assignee_group,
      sla: filters.sla,
      category: filters.category,
    })}`).then(normalizeDailyReportRecords),
}

// Standalone live Helix workflow. It deliberately does not share Daily Report APIs.
export const helixRawReportsApi = {
  fields: () =>
    apiFetch<HelixRawReportFieldsResponse>('/helix-reports/fields'),

  filters: () =>
    apiFetch<HelixRawReportFiltersResponse>('/helix-reports/filters'),

  generate: (payload: HelixRawReportRequest) =>
    apiFetch<HelixRawReportResponse>('/helix-reports', {
      method: 'POST',
      body: JSON.stringify(payload),
    }, true, false),
}

// ─── Divisions ────────────────────────────────────────────────────────────────

export const divisionsApi = {
  list: () =>
    apiFetch<DivisionsResponse>('/divisions'),

  create: (division: string) =>
    apiFetch<{ division: string; active: boolean }>('/divisions', {
      method: 'POST',
      body: JSON.stringify({ division }),
    }),

  groups: (division: string) =>
    apiFetch<DivisionGroupsResponse>(`/divisions/${encodeURIComponent(division)}/groups`),

  addGroups: (division: string, groups: string[]) =>
    apiFetch<DivisionGroupsResponse>(`/divisions/${encodeURIComponent(division)}/groups`, {
      method: 'POST',
      body: JSON.stringify({ groups }),
    }),

  deleteGroup: (division: string, assigneeGroup: string) =>
    apiFetch<{ division: string; assignee_group: string; active: boolean }>(
      `/divisions/${encodeURIComponent(division)}/groups/${encodeURIComponent(assigneeGroup)}`,
      { method: 'DELETE' },
    ),

  seedDefaultGroups: () =>
    apiFetch<DivisionsResponse>('/division-group-seed-jobs', {
      method: 'POST',
    }),
}

// ─── Health ──────────────────────────────────────────────────────────────────

export const healthApi = {
  check: () =>
    apiFetch<HealthResponse>('/health', {}, false),

  runLog: (limit = 20) =>
    apiFetch<RunLogResponse>(`/pipeline-runs${buildQuery({ limit })}`),
}

// ─── Super Admin ─────────────────────────────────────────────────────────────

export const adminApi = {
  users: (params: { status?: string; limit?: number; offset?: number } = {}) =>
    apiFetch<{ users: AdminUser[]; count: number; limit: number; offset: number }>(
      `/users${buildQuery({
        status: params.status,
        limit: params.limit,
        offset: params.offset,
      })}`,
    ),

  createUser: (email: string, role: string, password: string, fullName?: string) =>
    apiFetch<AdminUser>('/users', {
      method: 'POST',
      body: JSON.stringify({ email, role, password, full_name: fullName || undefined }),
    }),

  updateUser: (userId: number, patch: { status?: string; role?: string }) =>
    apiFetch<AdminUser>(`/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  resetPassword: (userId: number, password: string, mustChangePassword = true) =>
    apiFetch<AdminUser>(`/users/${userId}/password-reset`, {
      method: 'POST',
      body: JSON.stringify({ password, must_change_password: mustChangePassword }),
    }),

  deleteUser: (userId: number) =>
    apiFetch<{ id: number; email: string; deleted: boolean }>(`/users/${userId}`, {
      method: 'DELETE',
    }),

  loginHistory: (limit = 100, offset = 0) =>
    apiFetch<LoginHistoryResponse>(`/login-attempts${buildQuery({ limit, offset })}`),

  sessions: (limit = 100, offset = 0) =>
    apiFetch<AdminSessionsResponse>(`/sessions${buildQuery({ limit, offset })}`),

  revokeSession: (sessionId: string) =>
    apiFetch<{ session_id: string; status: 'REVOKED' }>(
      `/sessions/${encodeURIComponent(sessionId)}`,
      { method: 'DELETE' },
    ),
}

export const reportEmailsApi = {
  subscriptions: () =>
    apiFetch<ReportEmailSubscriptionsResponse>('/report-subscriptions'),

  createSubscription: (payload: ReportEmailSubscriptionPayload) =>
    apiFetch<ReportEmailSubscription>('/report-subscriptions', {
      method: 'POST', body: JSON.stringify(payload),
    }),

  updateSubscription: (id: number, payload: ReportEmailSubscriptionPayload) =>
    apiFetch<ReportEmailSubscription>(`/report-subscriptions/${id}`, {
      method: 'PUT', body: JSON.stringify(payload),
    }),

  setEnabled: (id: number, enabled: boolean) =>
    apiFetch<ReportEmailSubscription>(`/report-subscriptions/${id}`, {
      method: 'PATCH', body: JSON.stringify({ enabled }),
    }),

  deleteSubscription: (id: number) =>
    apiFetch<{ id: number; deleted: boolean }>(`/report-subscriptions/${id}`, {
      method: 'DELETE',
    }),

  send: (payload: ManualReportEmailPayload) =>
    apiFetch<ManualReportEmailResponse>('/report-deliveries', {
      method: 'POST', body: JSON.stringify(payload),
    }, true, false),

  deliveries: (limit = 100) =>
    apiFetch<ReportEmailDeliveriesResponse>(`/report-deliveries${buildQuery({ limit })}`),
}

export const taskRemindersApi = {
  subscriptions: (limit = 100, offset = 0) =>
    apiFetch<TaskReminderSubscriptionsResponse>(
      `/task-reminder-subscriptions${buildQuery({ limit, offset })}`,
    ),

  createSubscription: (payload: TaskReminderSubscriptionPayload) =>
    apiFetch<TaskReminderSubscription>('/task-reminder-subscriptions', {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  replaceSubscription: (id: number, payload: TaskReminderSubscriptionPayload) =>
    apiFetch<TaskReminderSubscription>(`/task-reminder-subscriptions/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    }),

  setEnabled: (id: number, enabled: boolean) =>
    apiFetch<TaskReminderSubscription>(`/task-reminder-subscriptions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ enabled }),
    }),

  deleteSubscription: (id: number) =>
    apiFetch<{ id: number; deleted: boolean }>(`/task-reminder-subscriptions/${id}`, {
      method: 'DELETE',
    }),

  executions: (params: {
    subscription_id?: number
    status?: TaskReminderExecutionStatus | ''
    limit?: number
    offset?: number
  } = {}) => apiFetch<TaskReminderExecutionsResponse>(
    `/task-reminder-executions${buildQuery({
      subscription_id: params.subscription_id,
      status: params.status,
      limit: params.limit ?? 100,
      offset: params.offset ?? 0,
    })}`,
  ),

  execute: (subscriptionId: number) =>
    apiFetch<TaskReminderExecution>('/task-reminder-executions', {
      method: 'POST',
      body: JSON.stringify({ subscription_id: subscriptionId }),
    }, true, false),
}
