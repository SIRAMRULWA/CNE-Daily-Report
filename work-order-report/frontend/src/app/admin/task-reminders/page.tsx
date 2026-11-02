'use client'

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import {
  AlertCircle, BellRing, Check, ChevronLeft, ChevronRight, Clock, Edit3,
  Eye, History, Plus, RefreshCw, Send, ShieldCheck, Trash2, X,
} from 'lucide-react'
import AppShell from '@/components/layout/AppShell'
import { Btn, EmptyState, PageHeader, TableSkeleton, Tag } from '@/components/ui'
import { ApiError, divisionsApi, taskRemindersApi } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations } from '@/lib/permissions'
import { cn, fmtDateTime } from '@/lib/utils'
import type {
  TaskReminderExecution, TaskReminderExecutionStatus,
  TaskReminderSubscription, TaskReminderSubscriptionPayload,
} from '@/types'

type Tab = 'subscriptions' | 'history'
type Editor = 'new' | TaskReminderSubscription
const LIMIT = 50
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const TIME_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const fieldClass = 'h-8 w-full rounded-md border border-[#D0D0D0] bg-white px-2.5 text-[12px] outline-none focus:border-[#E60000] disabled:bg-[#F5F5F5] disabled:text-[#8C8C8C]'
const labelClass = 'mb-1 block text-[10px] font-600 uppercase tracking-[0.45px] text-[#8C8C8C]'

const EMPTY_FORM: TaskReminderSubscriptionPayload = {
  name: '', division: '', assignee_group: null, recipients: [], cc_recipients: [],
  subject: null, frequency: 'DAILY', weekday: null, send_time: '10:00',
  timezone: 'Africa/Johannesburg', max_records: 10000, enabled: false,
}

function message(error: unknown) {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

function managementErrorMessage(error: unknown, missingResource = 'Task Reminder subscription') {
  if (error instanceof ApiError && error.status === 403) {
    return 'Insufficient permissions. Manager, Admin, or Super Admin access is required to manage Task Reminder subscriptions.'
  }
  if (error instanceof ApiError && error.status === 404) {
    return `${missingResource} was not found or has already been deleted.`
  }
  return message(error)
}

function Modal({ title, children, onClose, width = 'max-w-3xl' }: {
  title: string; children: React.ReactNode; onClose: () => void; width?: string
}) {
  return <motion.div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/35 p-4" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onMouseDown={event => event.target === event.currentTarget && onClose()}>
    <motion.div initial={{ scale: .98, y: 8 }} animate={{ scale: 1, y: 0 }} exit={{ scale: .98, y: 8 }} className={cn('max-h-[92vh] w-full overflow-y-auto rounded-lg border border-[#E5E5E5] bg-white shadow-xl', width)}>
      <div className="sticky top-0 z-10 flex items-center border-b border-[#E5E5E5] bg-white px-5 py-3"><h2 className="flex-1 text-[14px] font-600">{title}</h2><button onClick={onClose} className="p-1 text-[#8C8C8C] hover:text-[#1A1A1A]" aria-label="Close"><X size={15} /></button></div>
      {children}
    </motion.div>
  </motion.div>
}

function EmailsInput({ label, required, values, onChange }: {
  label: string; required?: boolean; values: string[]; onChange: (values: string[]) => void
}) {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')
  function add(raw = input) {
    const candidates = raw.split(/[,;\s]+/).map(value => value.trim().toLowerCase()).filter(Boolean)
    if (!candidates.length) return
    const invalid = candidates.find(value => !EMAIL_RE.test(value))
    if (invalid) return setError(`${invalid} is not a valid email address`)
    onChange(Array.from(new Set([...values, ...candidates])))
    setInput(''); setError('')
  }
  return <div><label className={labelClass}>{label}{required ? ' *' : ''}</label><div className={cn('flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border bg-white p-1.5', error ? 'border-[#E60000]' : 'border-[#D0D0D0] focus-within:border-[#E60000]')}>
    {values.map(value => <span key={value} className="inline-flex items-center gap-1 rounded-full bg-[#F5F5F5] px-2 py-1 text-[10px]">{value}<button type="button" onClick={() => onChange(values.filter(item => item !== value))} aria-label={`Remove ${value}`}><X size={10} /></button></span>)}
    <input className="min-w-[180px] flex-1 bg-transparent px-1 text-[11px] outline-none" value={input} placeholder={values.length ? 'Add another…' : 'name@example.com'} onChange={event => setInput(event.target.value)} onBlur={() => input.trim() && add()} onKeyDown={event => { if (['Enter', ',', ';'].includes(event.key)) { event.preventDefault(); add() } }} />
  </div>{error && <p className="mt-1 text-[10px] text-[#CC0000]">{error}</p>}</div>
}

function SubscriptionEditor({ initial, divisions, saving, onCancel, onSave }: {
  initial?: TaskReminderSubscription; divisions: string[]; saving: boolean
  onCancel: () => void; onSave: (payload: TaskReminderSubscriptionPayload) => void
}) {
  const [form, setForm] = useState<TaskReminderSubscriptionPayload>(initial ? {
    name: initial.name, division: initial.division, assignee_group: initial.assignee_group,
    recipients: initial.recipients, cc_recipients: initial.cc_recipients, subject: initial.subject,
    frequency: initial.frequency, weekday: initial.weekday, send_time: initial.send_time.slice(0, 5),
    timezone: initial.timezone, max_records: initial.max_records, enabled: initial.enabled,
  } : EMPTY_FORM)
  const [validation, setValidation] = useState('')
  const [pendingEnable, setPendingEnable] = useState<TaskReminderSubscriptionPayload | null>(null)
  const groups = useQuery({ queryKey: ['division-groups', form.division], queryFn: () => divisionsApi.groups(form.division), enabled: !!form.division })

  function submit() {
    const name = form.name.trim()
    if (!name) return setValidation('Name is required.')
    if (!form.division) return setValidation('Division is required.')
    if (!form.recipients.length) return setValidation('At least one recipient is required.')
    if ([...form.recipients, ...form.cc_recipients].some(email => !EMAIL_RE.test(email))) return setValidation('Every recipient must be a valid email address.')
    if (form.frequency === 'WEEKLY' && form.weekday == null) return setValidation('Select a weekday for weekly Task Reminders.')
    if (!TIME_RE.test(form.send_time.slice(0, 5))) return setValidation('Enter a valid local send time.')
    if (!form.timezone.trim() || (!form.timezone.includes('/') && form.timezone !== 'UTC')) return setValidation('Enter a valid IANA timezone such as Africa/Johannesburg.')
    if (!Number.isInteger(form.max_records) || form.max_records < 1 || form.max_records > 50000) return setValidation('Maximum records must be between 1 and 50,000.')
    setValidation('')
    const payload = { ...form, name, subject: form.subject?.trim() || null, weekday: form.frequency === 'WEEKLY' ? form.weekday : null, send_time: form.send_time.slice(0, 5), timezone: form.timezone.trim() }
    if (payload.enabled && !initial?.enabled) {
      setPendingEnable(payload)
      return
    }
    onSave(payload)
  }

  return <><div className="space-y-4 p-5">
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2"><div><label className={labelClass}>Name *</label><input className={fieldClass} maxLength={200} value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} /></div><div><label className={labelClass}>Division *</label><select className={fieldClass} value={form.division} onChange={event => setForm(current => ({ ...current, division: event.target.value, assignee_group: null }))}><option value="">Select division</option>{divisions.map(division => <option key={division}>{division}</option>)}</select></div></div>
    <div><label className={labelClass}>Assignee group</label><select className={fieldClass} disabled={!form.division || groups.isLoading} value={form.assignee_group ?? ''} onChange={event => setForm(current => ({ ...current, assignee_group: event.target.value || null }))}><option value="">All active groups</option>{groups.data?.groups.filter(group => group.active).map(group => <option key={group.assignee_group}>{group.assignee_group}</option>)}</select><p className="mt-1 text-[10px] text-[#8C8C8C]">All active groups are resolved dynamically by the backend when the Task Reminder runs.</p></div>
    <EmailsInput label="Recipients" required values={form.recipients} onChange={recipients => setForm(current => ({ ...current, recipients }))} />
    <EmailsInput label="CC recipients" values={form.cc_recipients} onChange={cc_recipients => setForm(current => ({ ...current, cc_recipients }))} />
    <div><label className={labelClass}>Subject</label><input className={fieldClass} maxLength={250} value={form.subject ?? ''} placeholder="Backend generates the subject when blank" onChange={event => setForm(current => ({ ...current, subject: event.target.value || null }))} /></div>
    <div className="grid grid-cols-1 gap-4 md:grid-cols-4"><div><label className={labelClass}>Frequency *</label><select className={fieldClass} value={form.frequency} onChange={event => setForm(current => ({ ...current, frequency: event.target.value as 'DAILY' | 'WEEKLY', weekday: event.target.value === 'DAILY' ? null : current.weekday }))}><option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option></select></div><div><label className={labelClass}>Weekday{form.frequency === 'WEEKLY' ? ' *' : ''}</label><select className={fieldClass} disabled={form.frequency !== 'WEEKLY'} value={form.weekday ?? ''} onChange={event => setForm(current => ({ ...current, weekday: event.target.value === '' ? null : Number(event.target.value) }))}><option value="">Select day</option>{WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></div><div><label className={labelClass}>Send time *</label><input className={fieldClass} type="time" value={form.send_time.slice(0, 5)} onChange={event => setForm(current => ({ ...current, send_time: event.target.value }))} /></div><div><label className={labelClass}>Timezone *</label><input className={fieldClass} list="reminder-timezones" value={form.timezone} onChange={event => setForm(current => ({ ...current, timezone: event.target.value }))} /><datalist id="reminder-timezones"><option value="Africa/Johannesburg" /><option value="UTC" /></datalist></div></div>
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2"><div><label className={labelClass}>Maximum records *</label><input className={fieldClass} type="number" min={1} max={50000} value={form.max_records} onChange={event => setForm(current => ({ ...current, max_records: Number(event.target.value) }))} /><p className="mt-1 text-[10px] text-[#8C8C8C]">Execution fails safely if live results exceed this limit.</p></div><div><label className={labelClass}>Scheduled delivery</label><button type="button" role="switch" aria-checked={form.enabled} onClick={() => setForm(current => ({ ...current, enabled: !current.enabled }))} className="flex items-center gap-2 py-1.5 text-[11px]"><span className={cn('relative h-5 w-9 rounded-full transition-colors', form.enabled ? 'bg-[#16A34A]' : 'bg-[#D0D0D0]')}><span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', form.enabled ? 'translate-x-[18px]' : 'translate-x-0.5')} /></span>{form.enabled ? 'Enabled' : 'Disabled'}</button><p className="text-[10px] text-[#8C8C8C]">The backend scheduler owns due execution and duplicate prevention.</p></div></div>
    <div className="rounded-md border border-[#B8CEFF] bg-[#EEF4FF] px-3 py-2 text-[10px] text-[#0057A8]">Weekday-only enforcement is controlled globally by the backend scheduler, not by an individual subscription.</div>
    {validation && <div className="rounded-md border border-[#F5B8B8] bg-[#FFF0F0] px-3 py-2 text-[11px] text-[#CC0000]">{validation}</div>}
  </div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn onClick={onCancel}>Cancel</Btn><Btn variant="primary" loading={saving} onClick={submit}>{initial ? 'Save changes' : 'Create reminder'}</Btn></div>
    <AnimatePresence>{pendingEnable && <Modal title="Enable scheduled reminders?" width="max-w-lg" onClose={() => !saving && setPendingEnable(null)}>
      <div className="space-y-3 p-5 text-[11px]">
        <p>Save <strong>{pendingEnable.name}</strong> with scheduled delivery enabled?</p>
        <div className="rounded-md border border-[#F5D580] bg-[#FFF8E6] p-3 text-[#8A5200]">
          The backend scheduler may retrieve live Helix tickets and send real email at the configured {pendingEnable.frequency === 'WEEKLY' ? `${WEEKDAYS[pendingEnable.weekday ?? 0]} ` : 'daily '}{pendingEnable.send_time.slice(0, 5)} occurrence in {pendingEnable.timezone}.
        </div>
      </div>
      <div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3">
        <Btn disabled={saving} onClick={() => setPendingEnable(null)}>Cancel</Btn>
        <Btn variant="primary" loading={saving} onClick={() => onSave(pendingEnable)}><Check size={12} />Save and enable</Btn>
      </div>
    </Modal>}</AnimatePresence>
  </>
}

function ExecutionStatus({ status }: { status: TaskReminderExecutionStatus }) {
  return <Tag variant={status === 'SENT' ? 'success' : status === 'FAILED' ? 'danger' : 'info'}>{status === 'RUNNING' && <Clock size={10} className="animate-spin" />}{status}</Tag>
}

function ExecutionDetails({ execution }: { execution: TaskReminderExecution }) {
  const rows: [string, React.ReactNode][] = [
    ['Execution ID', execution.id], ['Subscription', `${execution.subscription_name ?? 'Subscription'} (#${execution.subscription_id})`],
    ['Scope', `${execution.division ?? '—'} · ${execution.assignee_group ?? 'All active groups'}`],
    ['Trigger', execution.trigger_source === 'MANUAL' ? 'Sent by administrator' : 'Scheduled automation'],
    ['Idempotency key', execution.idempotency_key], ['Recipients', execution.recipients.join(', ') || '—'],
    ['Open Tasks', execution.record_count ?? '—'], ['Attention items', execution.attention_count ?? '—'],
    ['Provider', execution.provider ?? '—'], ['Provider message ID', execution.provider_message_id ?? '—'],
    ['Requested by', execution.requested_by ?? '—'], ['Started', fmtDateTime(execution.started_at)],
    ['Completed', fmtDateTime(execution.completed_at)], ['Error code', execution.error_code ?? '—'],
    ['Failure details', execution.error_message ?? '—'],
  ]
  return <div className="p-5"><dl className="grid grid-cols-1 gap-x-6 md:grid-cols-2">{rows.map(([label, value]) => <div key={label} className="border-b border-[#F0F0F0] py-2.5"><dt className="text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C]">{label}</dt><dd className={cn('mt-1 break-words text-[11px]', label.includes('Error') || label.includes('Failure') ? 'text-[#CC0000]' : 'text-[#1A1A1A]')}>{value}</dd></div>)}</dl></div>
}

export default function TaskRemindersPage() {
  const { user } = useAuth()
  const canManage = canManageOperations(user)
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('subscriptions')
  const [editor, setEditor] = useState<Editor | null>(null)
  const [toggleTarget, setToggleTarget] = useState<TaskReminderSubscription | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<TaskReminderSubscription | null>(null)
  const [sendTarget, setSendTarget] = useState<TaskReminderSubscription | null>(null)
  const [details, setDetails] = useState<TaskReminderExecution | null>(null)
  const [subscriptionOffset, setSubscriptionOffset] = useState(0)
  const [historyOffset, setHistoryOffset] = useState(0)
  const [historySubscription, setHistorySubscription] = useState('')
  const [historyStatus, setHistoryStatus] = useState<TaskReminderExecutionStatus | ''>('')
  const [subscriptionSearch, setSubscriptionSearch] = useState('')
  const [subscriptionDivision, setSubscriptionDivision] = useState('')
  const [subscriptionState, setSubscriptionState] = useState('')
  const [subscriptionSort, setSubscriptionSort] = useState('updated-desc')
  const [historySearch, setHistorySearch] = useState('')
  const [historyTrigger, setHistoryTrigger] = useState('')
  const [historySort, setHistorySort] = useState('started-desc')

  const divisions = useQuery({ queryKey: ['divisions'], queryFn: divisionsApi.list, enabled: canManage })
  const subscriptions = useQuery({ queryKey: ['task-reminder-subscriptions', subscriptionOffset], queryFn: () => taskRemindersApi.subscriptions(LIMIT, subscriptionOffset), enabled: canManage })
  const history = useQuery({ queryKey: ['task-reminder-executions', historySubscription, historyStatus, historyOffset], queryFn: () => taskRemindersApi.executions({ subscription_id: historySubscription ? Number(historySubscription) : undefined, status: historyStatus, limit: LIMIT, offset: historyOffset }), enabled: canManage, refetchInterval: tab === 'history' ? 30_000 : false })
  const divisionNames = divisions.data?.divisions.map(item => item.division) ?? []
  const visibleSubscriptions = useMemo(() => {
    const search = subscriptionSearch.trim().toLowerCase()
    return [...(subscriptions.data?.subscriptions ?? [])]
      .filter(item => !subscriptionDivision || item.division === subscriptionDivision)
      .filter(item => !subscriptionState || String(item.enabled) === subscriptionState)
      .filter(item => !search || [item.name, item.subject, item.division, item.assignee_group, ...item.recipients, ...item.cc_recipients].some(value => value?.toLowerCase().includes(search)))
      .sort((a, b) => {
        if (subscriptionSort === 'name-asc') return a.name.localeCompare(b.name)
        if (subscriptionSort === 'division-asc') return a.division.localeCompare(b.division) || a.name.localeCompare(b.name)
        if (subscriptionSort === 'schedule-asc') return a.send_time.localeCompare(b.send_time) || a.name.localeCompare(b.name)
        return Date.parse(b.updated_at) - Date.parse(a.updated_at)
      })
  }, [subscriptions.data, subscriptionSearch, subscriptionDivision, subscriptionState, subscriptionSort])
  const visibleHistory = useMemo(() => {
    const search = historySearch.trim().toLowerCase()
    return [...(history.data?.executions ?? [])]
      .filter(item => !historyTrigger || item.trigger_source === historyTrigger)
      .filter(item => !search || [item.subscription_name, item.division, item.assignee_group, item.requested_by, item.provider, item.error_message, ...item.recipients].some(value => value?.toLowerCase().includes(search)))
      .sort((a, b) => {
        if (historySort === 'started-asc') return Date.parse(a.started_at) - Date.parse(b.started_at)
        if (historySort === 'tasks-desc') return (b.record_count ?? -1) - (a.record_count ?? -1)
        if (historySort === 'attention-desc') return (b.attention_count ?? -1) - (a.attention_count ?? -1)
        return Date.parse(b.started_at) - Date.parse(a.started_at)
      })
  }, [history.data, historySearch, historyTrigger, historySort])

  const save = useMutation({
    mutationFn: ({ existing, payload }: { existing?: TaskReminderSubscription; payload: TaskReminderSubscriptionPayload }) => existing ? taskRemindersApi.replaceSubscription(existing.id, payload) : taskRemindersApi.createSubscription(payload),
    onSuccess: (result, variables) => { setEditor(null); qc.invalidateQueries({ queryKey: ['task-reminder-subscriptions'] }); toast.success(variables.existing ? 'Task reminder subscription updated.' : `Task reminder subscription created ${result.enabled ? 'and enabled' : 'disabled for review'}.`) },
    onError: error => toast.error(managementErrorMessage(error)),
  })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => taskRemindersApi.setEnabled(id, enabled),
    onSuccess: result => { setToggleTarget(null); qc.invalidateQueries({ queryKey: ['task-reminder-subscriptions'] }); toast.success(result.enabled ? 'Scheduled task reminders enabled.' : 'Scheduled task reminders disabled.') },
    onError: error => {
      setToggleTarget(null)
      if (error instanceof ApiError && error.status === 404) {
        void qc.invalidateQueries({ queryKey: ['task-reminder-subscriptions'] })
      }
      toast.error(managementErrorMessage(error))
    },
  })
  const remove = useMutation({
    mutationFn: taskRemindersApi.deleteSubscription,
    onSuccess: async result => {
      setDeleteTarget(null)
      await qc.invalidateQueries({ queryKey: ['task-reminder-subscriptions'], refetchType: 'active' })
      toast.success(`Task reminder subscription #${result.id} deleted. Future scheduled executions were stopped and execution history was preserved.`)
    },
    onError: error => {
      setDeleteTarget(null)
      if (error instanceof ApiError && error.status === 404) {
        void qc.invalidateQueries({ queryKey: ['task-reminder-subscriptions'], refetchType: 'active' })
      }
      toast.error(managementErrorMessage(error))
    },
  })
  const send = useMutation({
    mutationFn: (subscription: TaskReminderSubscription) => taskRemindersApi.execute(subscription.id),
    onSuccess: result => { setSendTarget(null); qc.invalidateQueries({ queryKey: ['task-reminder-executions'] }); toast.success(`Task reminder sent successfully. ${result.record_count ?? 0} open tasks were included and ${result.attention_count ?? 0} were highlighted for attention.`); setTab('history'); setDetails(result) },
    onError: error => { setSendTarget(null); qc.invalidateQueries({ queryKey: ['task-reminder-executions'] }); if (error instanceof ApiError && error.status === 502) toast.error(`The task reminder could not be sent. The failed execution was recorded for support. ${error.message}`); else toast.error(message(error)) },
  })

  if (!canManage) return <AppShell><div className="flex flex-1 flex-col"><PageHeader breadcrumb={['Admin', 'Task Reminders']} title="Task Reminders" /><div className="flex flex-1 items-center justify-center"><EmptyState title="Operational admin access required" sub="Manager, Admin, or Super Admin access is required to manage live task reminders." icon={<ShieldCheck size={32} />} /></div></div></AppShell>

  return <AppShell><div className="flex min-h-0 flex-1 flex-col">
    <PageHeader breadcrumb={['Admin', 'Task Reminders']} title="Task Reminders" subtitle="Schedule and monitor Open Tasks from live Helix using the same eligibility rules as Daily Reports." actions={<Btn size="sm" onClick={() => { subscriptions.refetch(); history.refetch() }}><RefreshCw size={11} />Refresh</Btn>} />
    <div className="flex gap-1 border-b border-[#E5E5E5] bg-white px-5">{([{ value: 'subscriptions', label: 'Subscriptions', icon: BellRing }, { value: 'history', label: 'Execution History', icon: History }] as const).map(item => <button key={item.value} onClick={() => setTab(item.value)} className={cn('flex items-center gap-1.5 border-b-2 px-3 py-3 text-[11px] font-500', tab === item.value ? 'border-[#E60000] text-[#E60000]' : 'border-transparent text-[#5C5C5C]')}><item.icon size={13} />{item.label}</button>)}</div>
    <div className="flex-1 overflow-y-auto p-5">
      <div className="mb-4 flex gap-2 rounded-md border border-[#B8CEFF] bg-[#EEF4FF] px-4 py-3 text-[11px] text-[#0057A8]"><AlertCircle size={14} className="mt-0.5 flex-shrink-0" /><span>Each Task Reminder retrieves current Open Tasks from Helix, applies the shared Daily Report transformation, and sends a complete Excel attachment. Work Orders, PBIs, unsupported categories, excluded statuses, and unmapped groups are removed; stored Daily Report snapshots are not used.</span></div>

      {tab === 'subscriptions' && <div className="space-y-4"><div className="flex items-center"><div className="flex-1"><h2 className="text-[13px] font-600">Task Reminder subscriptions</h2><p className="text-[10px] text-[#8C8C8C]">The backend scheduler evaluates enabled subscriptions using their local frequency, weekday, time, and timezone.</p></div>{canManage && <Btn variant="primary" size="sm" onClick={() => setEditor('new')}><Plus size={11} />Create Task Reminder</Btn>}</div>
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[#E5E5E5] bg-white p-3">
          <div className="min-w-[220px] flex-1"><label className={labelClass}>Search</label><input className={fieldClass} value={subscriptionSearch} onChange={event => setSubscriptionSearch(event.target.value)} placeholder="Name, subject, group or recipient" /></div>
          <div><label className={labelClass}>Division</label><select className={cn(fieldClass, 'w-[180px]')} value={subscriptionDivision} onChange={event => setSubscriptionDivision(event.target.value)}><option value="">All divisions</option>{divisionNames.map(division => <option key={division}>{division}</option>)}</select></div>
          <div><label className={labelClass}>Enabled</label><select className={cn(fieldClass, 'w-[130px]')} value={subscriptionState} onChange={event => setSubscriptionState(event.target.value)}><option value="">All states</option><option value="true">Enabled</option><option value="false">Disabled</option></select></div>
          <div><label className={labelClass}>Sort by</label><select className={cn(fieldClass, 'w-[170px]')} value={subscriptionSort} onChange={event => setSubscriptionSort(event.target.value)}><option value="updated-desc">Recently updated</option><option value="name-asc">Name A–Z</option><option value="division-asc">Division A–Z</option><option value="schedule-asc">Reminder time</option></select></div>
          {(subscriptionSearch || subscriptionDivision || subscriptionState) && <Btn size="sm" onClick={() => { setSubscriptionSearch(''); setSubscriptionDivision(''); setSubscriptionState('') }}>Clear</Btn>}
          <span className="pb-1 text-[10px] text-[#8C8C8C]">{visibleSubscriptions.length} on this page</span>
        </div>
        <div className="overflow-x-auto rounded-lg border border-[#E5E5E5] bg-white">
          <table className="min-w-[1100px] w-full">
            <thead><tr className="border-b border-[#E5E5E5] bg-[#FAFAFA]">{['Name', 'Scope', 'Recipients', 'Schedule', 'Maximum', 'Enabled', 'Last updated', 'Actions'].map(label => <th key={label} className="px-3 py-2 text-left text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C]">{label}</th>)}</tr></thead>
            {subscriptions.isLoading ? <TableSkeleton rows={7} cols={8} /> : <tbody>{visibleSubscriptions.map(subscription => (
              <tr key={subscription.id} className="border-b border-[#F0F0F0] align-top last:border-0 hover:bg-[#FAFAFA]">
                <td className="px-3 py-3"><p className="text-[11px] font-600">{subscription.name}</p><p className="max-w-[190px] truncate text-[9px] text-[#8C8C8C]" title={subscription.subject ?? ''}>{subscription.subject ?? 'Automatic subject'}</p></td>
                <td className="px-3 py-3 text-[10px]"><p>{subscription.division}</p><p className="max-w-[210px] truncate text-[#8C8C8C]" title={subscription.assignee_group ?? 'All active groups'}>{subscription.assignee_group ?? 'All active groups'}</p></td>
                <td className="px-3 py-3 text-[10px]"><p>{subscription.recipients.length} To</p><p className="text-[#8C8C8C]">{subscription.cc_recipients.length} CC</p></td>
                <td className="px-3 py-3 text-[10px] text-[#5C5C5C]">{subscription.frequency === 'WEEKLY' ? `${WEEKDAYS[subscription.weekday ?? 0]}s` : 'Daily'} at {subscription.send_time.slice(0, 5)}<p className="text-[9px] text-[#8C8C8C]">{subscription.timezone}</p></td>
                <td className="px-3 py-3 text-[10px]">{subscription.max_records.toLocaleString('en-ZA')}</td>
                <td className="px-3 py-3">
                  {canManage ? <button
                    role="switch"
                    aria-label={`${subscription.enabled ? 'Disable' : 'Enable'} ${subscription.name}`}
                    aria-checked={subscription.enabled}
                    disabled={toggle.isPending}
                    onClick={() => subscription.enabled ? toggle.mutate({ id: subscription.id, enabled: false }) : setToggleTarget(subscription)}
                    className={cn('relative h-5 w-9 rounded-full transition-colors disabled:opacity-50', subscription.enabled ? 'bg-[#16A34A]' : 'bg-[#D0D0D0]')}
                  ><span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', subscription.enabled ? 'translate-x-[18px]' : 'translate-x-0.5')} /></button> : <Tag variant={subscription.enabled ? 'success' : 'info'}>{subscription.enabled ? 'Enabled' : 'Disabled'}</Tag>}
                </td>
                <td className="whitespace-nowrap px-3 py-3 text-[10px]"><p>{fmtDateTime(subscription.updated_at)}</p><p className="text-[9px] text-[#8C8C8C]">{subscription.updated_by}</p></td>
                <td className="whitespace-nowrap px-3 py-3">
                  {canManage ? <>
                    <button onClick={() => setSendTarget(subscription)} className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-600 text-[#0057A8] hover:bg-[#EEF4FF]"><Send size={12} />Send Task Reminder</button>
                    <button onClick={() => setEditor(subscription)} title="Edit Task Reminder subscription" aria-label={`Edit ${subscription.name}`} className="p-1.5 text-[#8C8C8C] hover:text-[#1A1A1A]"><Edit3 size={13} /></button>
                    <button onClick={() => setDeleteTarget(subscription)} title="Delete Task Reminder subscription" aria-label={`Delete ${subscription.name}`} className="p-1.5 text-[#8C8C8C] hover:text-[#CC0000]"><Trash2 size={13} /></button>
                  </> : <span className="text-[10px] text-[#8C8C8C]">View only</span>}
                </td>
              </tr>
            ))}</tbody>}
          </table>
          {!subscriptions.isLoading && !visibleSubscriptions.length && <EmptyState title="No Task Reminder subscriptions found" sub="Create a Task Reminder and enable it after reviewing the Open Tasks scope and schedule." icon={<BellRing size={30} />} />}
        </div>
        <div className="flex justify-end gap-2"><Btn size="sm" disabled={!subscriptionOffset} onClick={() => setSubscriptionOffset(Math.max(0, subscriptionOffset - LIMIT))}><ChevronLeft size={11} />Previous</Btn><span className="px-2 py-1 text-[10px] text-[#8C8C8C]">Offset {subscriptionOffset}</span><Btn size="sm" disabled={(subscriptions.data?.count ?? 0) < LIMIT} onClick={() => setSubscriptionOffset(subscriptionOffset + LIMIT)}>Next<ChevronRight size={11} /></Btn></div>
      </div>}

      {tab === 'history' && <div className="space-y-4"><div className="flex flex-wrap items-end gap-3"><div className="flex-1"><h2 className="text-[13px] font-600">Task Reminder execution history</h2><p className="text-[10px] text-[#8C8C8C]">Manual and scheduled attempts use backend timestamps and recorded outcomes.</p></div><div><label className={labelClass}>Subscription</label><select className={cn(fieldClass, 'w-[230px]')} value={historySubscription} onChange={event => { setHistorySubscription(event.target.value); setHistoryOffset(0) }}><option value="">All subscriptions</option>{subscriptions.data?.subscriptions.map(subscription => <option key={subscription.id} value={subscription.id}>{subscription.name}</option>)}</select></div><div><label className={labelClass}>Status</label><select className={cn(fieldClass, 'w-[140px]')} value={historyStatus} onChange={event => { setHistoryStatus(event.target.value as TaskReminderExecutionStatus | ''); setHistoryOffset(0) }}><option value="">All statuses</option><option>RUNNING</option><option>SENT</option><option>FAILED</option></select></div><div><label className={labelClass}>Trigger</label><select className={cn(fieldClass, 'w-[155px]')} value={historyTrigger} onChange={event => setHistoryTrigger(event.target.value)}><option value="">All triggers</option><option value="AUTOMATION">Scheduled</option><option value="MANUAL">Manual</option></select></div><div><label className={labelClass}>Search</label><input className={cn(fieldClass, 'w-[220px]')} value={historySearch} onChange={event => setHistorySearch(event.target.value)} placeholder="Division, requester or recipient" /></div><div><label className={labelClass}>Sort by</label><select className={cn(fieldClass, 'w-[155px]')} value={historySort} onChange={event => setHistorySort(event.target.value)}><option value="started-desc">Newest first</option><option value="started-asc">Oldest first</option><option value="tasks-desc">Most open tasks</option><option value="attention-desc">Most attention</option></select></div>{(historySubscription || historyStatus || historyTrigger || historySearch) && <Btn size="sm" onClick={() => { setHistorySubscription(''); setHistoryStatus(''); setHistoryTrigger(''); setHistorySearch(''); setHistoryOffset(0) }}>Clear</Btn>}<span className="pb-1 text-[10px] text-[#8C8C8C]">{visibleHistory.length} on this page</span></div>
        <div className="overflow-x-auto rounded-lg border border-[#E5E5E5] bg-white"><table className="min-w-[1150px] w-full"><thead><tr className="border-b border-[#E5E5E5] bg-[#FAFAFA]">{['Started', 'Subscription', 'Scope', 'Trigger', 'Status', 'Open Tasks', 'Attention', 'Requested by', 'Completed', 'Details'].map(label => <th key={label} className="px-3 py-2 text-left text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C]">{label}</th>)}</tr></thead>{history.isLoading ? <TableSkeleton rows={8} cols={10} /> : <tbody>{visibleHistory.map(execution => <tr key={execution.id} className="border-b border-[#F0F0F0] last:border-0"><td className="whitespace-nowrap px-3 py-3 text-[10px]">{fmtDateTime(execution.started_at)}</td><td className="max-w-[190px] px-3 py-3 text-[10px]"><p className="truncate font-600">{execution.subscription_name ?? `#${execution.subscription_id}`}</p></td><td className="px-3 py-3 text-[10px]"><p>{execution.division ?? '—'}</p><p className="max-w-[190px] truncate text-[#8C8C8C]">{execution.assignee_group ?? 'All active groups'}</p></td><td className="px-3 py-3 text-[10px]">{execution.trigger_source === 'MANUAL' ? 'Sent by administrator' : 'Scheduled automation'}</td><td className="px-3 py-3"><ExecutionStatus status={execution.status} /></td><td className="px-3 py-3 text-[10px]">{execution.record_count?.toLocaleString('en-ZA') ?? '—'}</td><td className="px-3 py-3 text-[10px]">{execution.attention_count?.toLocaleString('en-ZA') ?? '—'}</td><td className="max-w-[180px] truncate px-3 py-3 text-[10px]">{execution.requested_by ?? '—'}</td><td className="whitespace-nowrap px-3 py-3 text-[10px]">{fmtDateTime(execution.completed_at)}</td><td className="px-3 py-3"><button onClick={() => setDetails(execution)} className="inline-flex items-center gap-1 text-[10px] font-600 text-[#0057A8]"><Eye size={12} />View</button></td></tr>)}</tbody>}</table>{!history.isLoading && !visibleHistory.length && <EmptyState title="No matching Task Reminder executions" sub="Change the filters or send an enabled Task Reminder." icon={<History size={30} />} />}</div>
        <div className="flex justify-end gap-2"><Btn size="sm" disabled={!historyOffset} onClick={() => setHistoryOffset(Math.max(0, historyOffset - LIMIT))}><ChevronLeft size={11} />Previous</Btn><span className="px-2 py-1 text-[10px] text-[#8C8C8C]">Offset {historyOffset}</span><Btn size="sm" disabled={(history.data?.count ?? 0) < LIMIT} onClick={() => setHistoryOffset(historyOffset + LIMIT)}>Next<ChevronRight size={11} /></Btn></div>
      </div>}
    </div>

    <AnimatePresence>{editor && <Modal title={editor === 'new' ? 'Create Task Reminder subscription' : 'Edit Task Reminder subscription'} onClose={() => setEditor(null)}><SubscriptionEditor initial={editor === 'new' ? undefined : editor} divisions={divisionNames} saving={save.isPending} onCancel={() => setEditor(null)} onSave={payload => save.mutate({ existing: editor === 'new' ? undefined : editor, payload })} /></Modal>}</AnimatePresence>
    <AnimatePresence>{toggleTarget && <Modal title="Enable scheduled reminders?" width="max-w-lg" onClose={() => !toggle.isPending && setToggleTarget(null)}><div className="space-y-3 p-5 text-[11px]"><p>Enable <strong>{toggleTarget.name}</strong>?</p><div className="rounded-md border border-[#F5D580] bg-[#FFF8E6] p-3 text-[#8A5200]">The backend scheduler may retrieve live Helix tickets and send real email at the configured {toggleTarget.frequency === 'WEEKLY' ? `${WEEKDAYS[toggleTarget.weekday ?? 0]} ` : 'daily '}{toggleTarget.send_time.slice(0, 5)} occurrence in {toggleTarget.timezone}.</div></div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn disabled={toggle.isPending} onClick={() => setToggleTarget(null)}>Cancel</Btn><Btn variant="primary" loading={toggle.isPending} onClick={() => toggle.mutate({ id: toggleTarget.id, enabled: true })}><Check size={12} />Enable schedule</Btn></div></Modal>}</AnimatePresence>
    <AnimatePresence>{deleteTarget && <Modal title="Delete this Task Reminder subscription?" width="max-w-lg" onClose={() => !remove.isPending && setDeleteTarget(null)}><div className="space-y-3 p-5 text-[11px]"><p>Delete <strong>{deleteTarget.name}</strong>?</p><p className="text-[#5C5C5C]">Future automated executions will stop. Existing execution history will be preserved.</p></div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn disabled={remove.isPending} onClick={() => setDeleteTarget(null)}>Cancel</Btn><Btn variant="danger" loading={remove.isPending} onClick={() => remove.mutate(deleteTarget.id)}>Delete subscription</Btn></div></Modal>}</AnimatePresence>
    <AnimatePresence>{sendTarget && <Modal title="Send Task Reminder?" width="max-w-lg" onClose={() => !send.isPending && setSendTarget(null)}><div className="space-y-4 p-5 text-[11px]"><p>Retrieve live Open Tasks from Helix and send <strong>{sendTarget.name}</strong> now?</p><div className="rounded-md border border-[#E5E5E5] bg-[#FAFAFA] p-3"><p><span className="text-[#8C8C8C]">Scope:</span> {sendTarget.division} · {sendTarget.assignee_group ?? 'All active groups'}</p><p className="mt-1"><span className="text-[#8C8C8C]">Recipients:</span> {sendTarget.recipients.join(', ')}</p><p className="mt-1"><span className="text-[#8C8C8C]">Open Tasks safety limit:</span> {sendTarget.max_records.toLocaleString('en-ZA')}</p></div>{!sendTarget.enabled && <div className="rounded-md border border-[#F5B8B8] bg-[#FFF0F0] p-3 text-[#CC0000]">This subscription is disabled. Enable it before sending a Task Reminder.</div>}{send.isPending && <div className="flex items-center gap-2 text-[#0057A8]"><Clock size={13} className="animate-spin" />Retrieving live Open Tasks and sending…</div>}</div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn disabled={send.isPending} onClick={() => setSendTarget(null)}>Cancel</Btn><Btn variant="primary" loading={send.isPending} disabled={!sendTarget.enabled} onClick={() => send.mutate(sendTarget)}><Send size={12} />Send Task Reminder</Btn></div></Modal>}</AnimatePresence>
    <AnimatePresence>{details && <Modal title="Task Reminder execution details" width="max-w-2xl" onClose={() => setDetails(null)}><ExecutionDetails execution={details} /><div className="flex justify-end border-t border-[#E5E5E5] px-5 py-3"><Btn onClick={() => setDetails(null)}>Close</Btn></div></Modal>}</AnimatePresence>
  </div></AppShell>
}



