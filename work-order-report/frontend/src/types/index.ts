// ─── Auth ────────────────────────────────────────────────────────────────────

export type Role = 'SUPER_ADMIN' | 'ADMIN' | 'MANAGER' | 'USER' | 'READ_ONLY'
type UserStatus = 'ACTIVE' | 'DISABLED' | 'LOCKED'

export interface User {
  id: number
  email: string
  full_name?: string | null
  display_name?: string | null
  role: Role
  status: UserStatus
  must_change_password: boolean
  session_id?: string
}

export interface LoginResponse {
  access_token: string
  token_type: 'bearer'
  expires_at: string
  user: User
}

// ─── Workspace ───────────────────────────────────────────────────────────────

export type SlaStatus = 'BREACHED' | 'NEARING_SLA' | 'NO_SCHEDULE' | 'WITHIN_SLA' | 'CLOSED'
export type Category = 'INCIDENT' | 'CHANGE' | 'ACCESS' | 'EVENT'

export interface WorkspaceRecord {
  request_id: string
  task_id: string
  division: string | null
  report_group: string | null
  assignee_group: string | null
  report_category: Category | null
  sla_status: SlaStatus | null
  priority: string | null
  status: string | null
  status_reason: string | null
  assignee: string | null
  summary: string | null
  hours_open: number | null
  assign_time: string | null
  scheduled_start: string | null
  scheduled_end: string | null
  closed_time: string | null
  due_at: string | null
  seconds_to_breach: number | null
  exclude_change: boolean
  exclude_incident: boolean
  source: string
  loaded_at: string
}

export interface RecordsResponse {
  as_of: string
  data_date: string
  data_available: boolean
  timezone: string
  records: WorkspaceRecord[]
  count: number
  total: number
  limit: number
  offset: number
}

export interface SummaryRow {
  division: string | null
  assignee_group: string | null
  sla_status: SlaStatus
  report_category: Category
  record_count: number
  avg_hours_open: number | null
  last_loaded_at: string | null
}

export interface SummaryResponse {
  as_of: string
  data_date: string
  data_available: boolean
  timezone: string
  rows: SummaryRow[]
  count: number
}

// ─── Filters ─────────────────────────────────────────────────────────────────

export interface Filters {
  division?: string
  assignee_group?: string
  sla?: SlaStatus | ''
  category?: Category | ''
  priority?: string
  search?: string
  include_excluded: boolean
  limit: number
  offset: number
}

// ─── Daily Report ─────────────────────────────────────────────────────────────

export interface DailyReportKpis {
  total_incidents: number
  total_changes: number
  total_access: number
  total_events: number
  total_open: number
  total_nearing: number
  total_breached: number
  total_within?: number
  total_closed_success_yesterday: number
  closed_incidents: number
  closed_changes: number
  closed_access: number
  closed_events: number
  successful_closures_by_group: SuccessfulClosureByGroup[]
  report_date: string
  period?: 'day' | 'week'
  date_from?: string
  date_to?: string
  division?: string | null
  assignee_group?: string | null
  divisions?: Array<{
    division?: string | null
    report_group?: string | null
    total_incidents: number
    total_changes: number
    total_access: number
    total_events: number
    total_open: number
    total_nearing: number
    total_breached: number
  }>
}

interface SuccessfulClosureByGroup {
  division: string
  assignee_group: string
  closure_date: string
  total_closed_success: number
}

export interface DailyReportRow {
  report_date: string
  division?: string | null
  assignee_group?: string | null
  report_group: string
  sla_band: 'Total Open Calls' | 'Calls Nearing SLA' | 'Breached Calls' | 'Closed Successfully Yesterday'
  incident_count: number
  change_count: number
  access_count: number
  event_count: number
  total_count: number
}

interface DailyReportAvailableDate {
  report_date: string
  division_count: number
  assignee_group_count: number
  total_open: number
}

interface DailyReportDatesResponse {
  dates: DailyReportAvailableDate[]
  count: number
  limit: number
}

export interface DailyReportLiveRecord {
  report_date?: string
  request_id: string
  task_id: string
  report_group: string | null
  report_category: Category | null
  sla_status: SlaStatus | null
  priority: string | null
  status: string | null
  assignee: string | null
  assignee_group: string | null
  summary: string | null
  hours_open: number | null
  scheduled_end: string | null
  assign_time: string | null
  snapshotted_at?: string | null
}

export interface DailyReportLiveResponse {
  as_of: string
  scope?: 'historical_report_snapshot' | string
  report_date?: string
  period?: 'day' | 'week'
  date_from?: string
  date_to?: string
  records: DailyReportLiveRecord[]
  count: number
  filters: {
    division?: string | null
    group: string | null
    assignee_group?: string | null
    sla: string | null
    category: string | null
  }
}

interface DailyReportGroup {
  report_group: string
  active_records: number
  assignee_group_count?: number
  assignee_groups?: string[]
}

export interface DailyReportViewResponse {
  report_date: string
  current_date: string
  is_historical: boolean
  data_available: boolean
  timezone: string
  period: 'day' | 'week'
  date_from: string
  date_to: string
  filters: {
    division?: string | null
    group?: string | null
    assignee_group?: string | null
  }
  kpis: DailyReportKpis
  summary: {
    rows: DailyReportRow[]
    count: number
  }
  groups: DailyReportGroup[]
  available_dates?: DailyReportDatesResponse
  records?: DailyReportLiveResponse
}

// Standalone Helix raw reports (not part of the Daily Report domain)
interface HelixRawReportField {
  name: string
  helix_field: string
}

export interface HelixRawReportFieldsResponse {
  fields: HelixRawReportField[]
  date_fields: string[]
  default_date_field: string
  common_statuses: string[]
  closed_statuses: string[]
  derived_categories: string[]
  sla_derived_fields: HelixRawReportField[]
}

interface HelixRawReportDivisionFilter {
  name: string
  assignee_groups: string[]
}

export interface HelixRawReportFiltersResponse {
  divisions: HelixRawReportDivisionFilter[]
  count: number
}

export interface HelixRawReportRequest {
  start?: string
  end?: string
  date_field: string
  fields?: string[]
  divisions?: string[]
  assignee_groups?: string[]
  assignees?: string[]
  statuses?: string[]
  calculate_sla?: boolean
  include_closed?: boolean
  categories?: string[]
  request_ids?: string[]
  task_ids?: string[]
  limit: number
}

export interface HelixRawReportResponse {
  source: string
  start: string | null
  end: string | null
  date_field: string
  fields: string[]
  divisions: string[]
  assignee_groups: string[]
  assignees: string[]
  statuses: string[]
  all_statuses: boolean
  include_closed: boolean
  calculate_sla: boolean
  sla_calculated_at: string | null
  categories: string[]
  request_ids: string[]
  task_ids: string[]
  count: number
  limit: number
  limit_reached: boolean
  records: Array<Record<string, unknown>>
}

// ─── Divisions ────────────────────────────────────────────────────────────────

interface Division {
  division: string
  group_count: number
}

interface DivisionGroup {
  division: string
  assignee_group: string
  active: boolean
  created_at: string
  updated_at: string
}

export interface DivisionsResponse {
  divisions: Division[]
  count: number
}

export interface DivisionGroupsResponse {
  division: string
  groups: DivisionGroup[]
  count: number
}

// ─── Activity Log ─────────────────────────────────────────────────────────────

export interface ActivityLogEntry {
  id: number
  action: string
  entity_type: string
  entity_id: string | null
  actor: string | null
  request_id?: string | null
  details: Record<string, unknown> | null
  ip_address?: string | null
  user_agent?: string | null
  browser?: string | null
  operating_system?: string | null
  result?: string | null
  created_at: string
}

export interface ActivityLogResponse {
  logs: ActivityLogEntry[]
  count: number
  limit: number
  offset: number
}

// ─── Health ──────────────────────────────────────────────────────────────────

export interface HealthResponse {
  status: 'ok' | 'error'
  api_time: string
  pipeline: {
    last_run_at: string | null
    last_run_status: string | null
    updated_at: string | null
  }
  records: {
    total: number
    active: number
    breached: number
  }
}

interface RunLogEntry {
  run_id: number
  pipeline_name: string
  source_entity: string
  source_file: string | null
  run_start: string
  run_end: string | null
  status: 'RUNNING' | 'SUCCESS' | 'FAILED' | 'PARTIAL'
  rows_extracted: number
  rows_loaded: number
  rows_rejected: number
  environment: string
  error_message: string | null
  duration_seconds: number | null
}

export interface RunLogResponse {
  runs: RunLogEntry[]
  count: number
}

// ─── Admin ────────────────────────────────────────────────────────────────────

export interface AdminUser {
  id: number
  email: string
  full_name?: string | null
  role: Role
  status: UserStatus
  must_change_password: boolean
  created_at: string
  updated_at?: string
  last_login_at: string | null
}

interface LoginHistoryEntry {
  id: number
  email: string
  full_name?: string | null
  login_time: string
  ip_address: string | null
  browser: string | null
  operating_system: string | null
  status: 'SUCCESS' | 'FAILED'
  failure_reason: string | null
}

export interface LoginHistoryResponse {
  logins: LoginHistoryEntry[]
  count: number
  limit: number
  offset: number
}

interface AdminSession {
  id: string
  email: string
  full_name?: string | null
  issued_at: string
  expires_at: string
  revoked_at: string | null
  ip_address: string | null
  browser: string | null
  operating_system: string | null
  status: 'ACTIVE' | 'REVOKED' | 'EXPIRED'
}

export interface AdminSessionsResponse {
  sessions: AdminSession[]
  count: number
  limit: number
  offset: number
}

// Daily Report email management (ADMIN and SUPER_ADMIN only)
export type ReportEmailFrequency = 'DAILY' | 'WEEKLY'
export type ReportEmailFormat = 'XLSX' | 'CSV'
type ReportEmailDeliveryStatus = 'SENDING' | 'SENT' | 'FAILED' | 'SKIPPED'
type ReportEmailDeliveryMode = 'MANUAL' | 'AUTOMATIC'

export interface ReportEmailSubscriptionPayload {
  name: string
  division: string
  assignee_group: string | null
  recipients: string[]
  cc_recipients: string[]
  frequency: ReportEmailFrequency
  weekday: number | null
  send_time: string
  timezone: string
  attachment_format: ReportEmailFormat
  enabled: boolean
}

export interface ReportEmailSubscription extends ReportEmailSubscriptionPayload {
  id: number
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export interface ReportEmailSubscriptionsResponse {
  subscriptions: ReportEmailSubscription[]
  count: number
}

export interface ManualReportEmailPayload {
  division: string
  assignee_group: string | null
  recipients: string[]
  cc_recipients: string[]
  report_date: string | null
  attachment_format: ReportEmailFormat
  subject: string | null
}

export interface ManualReportEmailResponse {
  delivery_id: number
  status: 'SENT'
  report_date: string
  record_count: number
  provider: string
}

export interface ReportEmailDelivery {
  id: number
  subscription_id: number | null
  subscription_name: string | null
  division?: string | null
  assignee_group?: string | null
  report_date: string
  status: ReportEmailDeliveryStatus
  delivery_mode: ReportEmailDeliveryMode
  recipients: string[]
  record_count: number | null
  provider: string | null
  provider_message_id: string | null
  attempt_count: number
  error_message: string | null
  requested_by: string | null
  started_at: string
  completed_at: string | null
}

export interface ReportEmailDeliveriesResponse {
  deliveries: ReportEmailDelivery[]
  count: number
}

// Outstanding task reminders (live Helix workflow, separate from Daily Reports)
export interface TaskReminderSubscriptionPayload {
  name: string
  division: string
  assignee_group: string | null
  recipients: string[]
  cc_recipients: string[]
  subject: string | null
  frequency: 'DAILY' | 'WEEKLY'
  weekday: number | null
  send_time: string
  timezone: string
  max_records: number
  enabled: boolean
}

export interface TaskReminderSubscription extends TaskReminderSubscriptionPayload {
  id: number
  deleted: boolean
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export interface TaskReminderSubscriptionsResponse {
  subscriptions: TaskReminderSubscription[]
  count: number
  limit: number
  offset: number
}

export type TaskReminderExecutionStatus = 'RUNNING' | 'SENT' | 'FAILED'
type TaskReminderTriggerSource = 'MANUAL' | 'AUTOMATION'

export interface TaskReminderExecution {
  id: number
  subscription_id: number
  subscription_name?: string | null
  division?: string | null
  assignee_group?: string | null
  idempotency_key: string
  trigger_source: TaskReminderTriggerSource
  status: TaskReminderExecutionStatus
  recipients: string[]
  record_count: number | null
  attention_count: number | null
  provider: string | null
  provider_message_id: string | null
  error_code: string | null
  error_message: string | null
  requested_by: string | null
  started_at: string
  completed_at: string | null
}

export interface TaskReminderExecutionsResponse {
  executions: TaskReminderExecution[]
  count: number
  limit: number
  offset: number
}
