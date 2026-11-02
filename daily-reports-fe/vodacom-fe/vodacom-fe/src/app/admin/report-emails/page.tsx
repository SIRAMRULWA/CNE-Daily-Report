'use client'

import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { toast } from 'sonner'
import { AlertCircle, CalendarClock, Check, Clock, Edit3, History, Mail, Plus, RefreshCw, Send, ShieldCheck, Trash2, X } from 'lucide-react'
import AppShell from '@/components/layout/AppShell'
import { Btn, EmptyState, PageHeader, TableSkeleton } from '@/components/ui'
import { ApiError, divisionsApi, reportEmailsApi } from '@/lib/api'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations } from '@/lib/permissions'
import { cn, fmtDateTime } from '@/lib/utils'
import type {
  ManualReportEmailPayload, ReportEmailDelivery, ReportEmailFormat,
  ReportEmailFrequency, ReportEmailSubscription, ReportEmailSubscriptionPayload,
} from '@/types'

type Tab = 'subscriptions' | 'send' | 'history'
const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
const fieldClass = 'h-8 w-full rounded-md border border-[#D0D0D0] bg-white px-2.5 text-[12px] outline-none focus:border-[#E60000]'
const labelClass = 'block text-[10px] font-600 uppercase tracking-[0.45px] text-[#8C8C8C] mb-1'

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}

function isApprovalError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}

function EmailsInput({ label, values, onChange, required }: {
  label: string
  values: string[]
  onChange: (values: string[]) => void
  required?: boolean
}) {
  const [input, setInput] = useState('')
  const [error, setError] = useState('')

  function add(raw = input) {
    const candidates = raw.split(/[,;\s]+/).map(value => value.trim().toLowerCase()).filter(Boolean)
    if (!candidates.length) return
    const invalid = candidates.find(value => !EMAIL_RE.test(value))
    if (invalid) {
      setError(`${invalid} is not a valid email address`)
      return
    }
    onChange(Array.from(new Set([...values, ...candidates])))
    setInput('')
    setError('')
  }

  return <div>
    <label className={labelClass}>{label}{required ? ' *' : ''}</label>
    <div className={cn('min-h-9 rounded-md border bg-white p-1.5 flex flex-wrap gap-1.5 items-center', error ? 'border-[#E60000]' : 'border-[#D0D0D0] focus-within:border-[#E60000]')}>
      {values.map(value => <span key={value} className="inline-flex items-center gap-1 rounded-full bg-[#F5F5F5] px-2 py-1 text-[10px] text-[#5C5C5C]">{value}<button type="button" onClick={() => onChange(values.filter(item => item !== value))} aria-label={`Remove ${value}`}><X size={10} /></button></span>)}
      <input value={input} onChange={event => setInput(event.target.value)} onKeyDown={event => {
        if (event.key === 'Enter' || event.key === ',' || event.key === ';') { event.preventDefault(); add() }
        if (event.key === 'Backspace' && !input && values.length) onChange(values.slice(0, -1))
      }} onBlur={() => input.trim() && add()} placeholder={values.length ? 'Add another…' : 'name@vodacom.co.za'} className="min-w-[170px] flex-1 bg-transparent px-1 text-[11px] outline-none" />
    </div>
    {error && <p className="mt-1 text-[10px] text-[#CC0000]">{error}</p>}
  </div>
}

function Modal({ title, children, onClose, width = 'max-w-2xl' }: { title: string; children: React.ReactNode; onClose: () => void; width?: string }) {
  return <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fixed inset-0 z-[90] flex items-center justify-center bg-black/35 p-4" onClick={onClose}>
    <motion.div initial={{ opacity: 0, y: 12, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8 }} onClick={event => event.stopPropagation()} className={cn('w-full rounded-lg border border-[#D0D0D0] bg-white shadow-2xl', width)}>
      <div className="flex items-center gap-3 border-b border-[#E5E5E5] px-5 py-3"><h2 className="flex-1 text-[14px] font-600">{title}</h2><button onClick={onClose} className="text-[#8C8C8C] hover:text-[#1A1A1A]"><X size={16} /></button></div>
      {children}
    </motion.div>
  </motion.div>
}

const emptySubscription = (): ReportEmailSubscriptionPayload => ({
  name: '', division: '', assignee_group: null, recipients: [], cc_recipients: [],
  frequency: 'DAILY', weekday: null, send_time: '08:00:00',
  timezone: 'Africa/Johannesburg', attachment_format: 'XLSX', enabled: false,
})

function SubscriptionEditor({ initial, divisions, onCancel, onSave, saving }: {
  initial?: ReportEmailSubscription
  divisions: string[]
  onCancel: () => void
  onSave: (payload: ReportEmailSubscriptionPayload) => void
  saving: boolean
}) {
  const [form, setForm] = useState<ReportEmailSubscriptionPayload>(() => initial ? {
    name: initial.name, division: initial.division, assignee_group: initial.assignee_group,
    recipients: initial.recipients, cc_recipients: initial.cc_recipients,
    frequency: initial.frequency, weekday: initial.weekday, send_time: initial.send_time,
    timezone: initial.timezone, attachment_format: initial.attachment_format, enabled: initial.enabled,
  } : emptySubscription())
  const [validation, setValidation] = useState('')
  const groupsQuery = useQuery({ queryKey: ['division-groups', form.division], queryFn: () => divisionsApi.groups(form.division), enabled: !!form.division })
  const groups = groupsQuery.data?.groups.filter(group => group.active) ?? []

  function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!form.name.trim()) return setValidation('Subscription name is required.')
    if (!form.division) return setValidation('Division is required.')
    if (!form.recipients.length) return setValidation('At least one primary recipient is required.')
    if (form.frequency === 'WEEKLY' && form.weekday == null) return setValidation('Select a weekday for a weekly subscription.')
    if (!form.send_time) return setValidation('Delivery time is required.')
    setValidation('')
    onSave({ ...form, name: form.name.trim(), send_time: form.send_time.length === 5 ? `${form.send_time}:00` : form.send_time, weekday: form.frequency === 'DAILY' ? null : form.weekday })
  }

  return <form onSubmit={submit}>
    <div className="max-h-[72vh] overflow-y-auto p-5 space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div><label className={labelClass}>Name *</label><input value={form.name} onChange={event => setForm(current => ({ ...current, name: event.target.value }))} className={fieldClass} placeholder="INTSS Daily Report" /></div>
        <div><label className={labelClass}>Division *</label><select value={form.division} onChange={event => setForm(current => ({ ...current, division: event.target.value, assignee_group: null }))} className={fieldClass}><option value="">Select division</option>{divisions.map(division => <option key={division}>{division}</option>)}</select></div>
        <div><label className={labelClass}>Assignee group</label><select value={form.assignee_group ?? ''} disabled={!form.division || groupsQuery.isLoading} onChange={event => setForm(current => ({ ...current, assignee_group: event.target.value || null }))} className={fieldClass}><option value="">All groups</option>{groups.map(group => <option key={group.assignee_group}>{group.assignee_group}</option>)}</select></div>
        <div><label className={labelClass}>Attachment</label><select value={form.attachment_format} onChange={event => setForm(current => ({ ...current, attachment_format: event.target.value as ReportEmailFormat }))} className={fieldClass}><option value="XLSX">Excel (.xlsx)</option><option value="CSV">CSV</option></select></div>
      </div>
      <EmailsInput label="Recipients" values={form.recipients} onChange={recipients => setForm(current => ({ ...current, recipients }))} required />
      <EmailsInput label="CC recipients" values={form.cc_recipients} onChange={cc_recipients => setForm(current => ({ ...current, cc_recipients }))} />
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div><label className={labelClass}>Frequency</label><select value={form.frequency} onChange={event => setForm(current => ({ ...current, frequency: event.target.value as ReportEmailFrequency, weekday: event.target.value === 'DAILY' ? null : current.weekday }))} className={fieldClass}><option value="DAILY">Daily</option><option value="WEEKLY">Weekly</option></select></div>
        <div><label className={labelClass}>Weekday</label><select value={form.weekday ?? ''} disabled={form.frequency !== 'WEEKLY'} onChange={event => setForm(current => ({ ...current, weekday: Number(event.target.value) }))} className={fieldClass}><option value="">Select day</option>{WEEKDAYS.map((day, index) => <option key={day} value={index}>{day}</option>)}</select></div>
        <div><label className={labelClass}>Delivery time</label><input type="time" value={form.send_time.slice(0, 5)} onChange={event => setForm(current => ({ ...current, send_time: event.target.value }))} className={fieldClass} /></div>
        <div><label className={labelClass}>Timezone</label><input value={form.timezone} readOnly className={cn(fieldClass, 'bg-[#F5F5F5]')} /></div>
      </div>
      <div className="rounded-md border border-[#F5D580] bg-[#FFF8E6] px-3 py-2 text-[10px] text-[#8A5200]">Division and group subscriptions are independent. A recipient included in both can receive both reports.</div>
      {!initial && <p className="text-[10px] text-[#8C8C8C]">New subscriptions are saved with automatic delivery off. Enable them after review and server approval.</p>}
      {validation && <div className="rounded-md border border-[#F5B8B8] bg-[#FFF0F0] px-3 py-2 text-[11px] text-[#CC0000]">{validation}</div>}
    </div>
    <div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn type="button" onClick={onCancel}>Cancel</Btn><Btn type="submit" variant="primary" loading={saving}>{initial ? 'Save changes' : 'Create subscription'}</Btn></div>
  </form>
}

function StatusBadge({ status }: { status: ReportEmailDelivery['status'] }) {
  const style = { SENT: 'bg-[#EDF7ED] text-[#0A7A0A] border-[#B8DFB8]', FAILED: 'bg-[#FFF0F0] text-[#CC0000] border-[#F5B8B8]', SKIPPED: 'bg-[#FFF8E6] text-[#8A5200] border-[#F5D580]', SENDING: 'bg-[#EEF4FF] text-[#0057A8] border-[#B8CEFF]' }[status]
  return <span className={cn('inline-flex rounded-full border px-2 py-0.5 text-[9px] font-600', style)}>{status === 'SENDING' ? 'Sending' : status.charAt(0) + status.slice(1).toLowerCase()}</span>
}

export default function ReportEmailsPage() {
  const { user } = useAuth()
  const qc = useQueryClient()
  const allowed = canManageOperations(user)
  const [tab, setTab] = useState<Tab>('subscriptions')
  const [editor, setEditor] = useState<ReportEmailSubscription | 'new' | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ReportEmailSubscription | null>(null)
  const [sendNowTarget, setSendNowTarget] = useState<ReportEmailSubscription | null>(null)
  const [toggleId, setToggleId] = useState<number | null>(null)
  const [approvalWarning, setApprovalWarning] = useState('')
  const [manual, setManual] = useState<ManualReportEmailPayload>({ division: '', assignee_group: null, recipients: [], cc_recipients: [], report_date: null, attachment_format: 'XLSX', subject: null })
  const [latest, setLatest] = useState(true)
  const [manualValidation, setManualValidation] = useState('')
  const [confirmSend, setConfirmSend] = useState(false)
  const [subscriptionSearch, setSubscriptionSearch] = useState('')
  const [subscriptionDivision, setSubscriptionDivision] = useState('')
  const [subscriptionState, setSubscriptionState] = useState('')
  const [subscriptionSort, setSubscriptionSort] = useState('updated-desc')
  const [deliverySearch, setDeliverySearch] = useState('')
  const [deliveryStatus, setDeliveryStatus] = useState('')
  const [deliveryMode, setDeliveryMode] = useState('')
  const [deliverySort, setDeliverySort] = useState('started-desc')

  const divisionsQuery = useQuery({ queryKey: ['divisions'], queryFn: divisionsApi.list, enabled: allowed })
  const subscriptionsQuery = useQuery({ queryKey: ['report-email-subscriptions'], queryFn: reportEmailsApi.subscriptions, enabled: allowed })
  const deliveriesQuery = useQuery({ queryKey: ['report-email-deliveries'], queryFn: () => reportEmailsApi.deliveries(100), enabled: allowed, refetchInterval: tab === 'history' ? 45_000 : false })
  const manualGroupsQuery = useQuery({ queryKey: ['division-groups', manual.division], queryFn: () => divisionsApi.groups(manual.division), enabled: allowed && !!manual.division })
  const divisionNames = divisionsQuery.data?.divisions.map(item => item.division) ?? []
  const visibleSubscriptions = useMemo(() => {
    const search = subscriptionSearch.trim().toLowerCase()
    return [...(subscriptionsQuery.data?.subscriptions ?? [])]
      .filter(item => !subscriptionDivision || item.division === subscriptionDivision)
      .filter(item => !subscriptionState || String(item.enabled) === subscriptionState)
      .filter(item => !search || [item.name, item.division, item.assignee_group, ...item.recipients, ...item.cc_recipients].some(value => value?.toLowerCase().includes(search)))
      .sort((a, b) => {
        if (subscriptionSort === 'name-asc') return a.name.localeCompare(b.name)
        if (subscriptionSort === 'division-asc') return a.division.localeCompare(b.division) || a.name.localeCompare(b.name)
        if (subscriptionSort === 'schedule-asc') return a.send_time.localeCompare(b.send_time) || a.name.localeCompare(b.name)
        return Date.parse(b.updated_at) - Date.parse(a.updated_at)
      })
  }, [subscriptionsQuery.data, subscriptionSearch, subscriptionDivision, subscriptionState, subscriptionSort])
  const visibleDeliveries = useMemo(() => {
    const search = deliverySearch.trim().toLowerCase()
    return [...(deliveriesQuery.data?.deliveries ?? [])]
      .filter(item => !deliveryStatus || item.status === deliveryStatus)
      .filter(item => !deliveryMode || item.delivery_mode === deliveryMode)
      .filter(item => !search || [item.subscription_name, item.requested_by, item.division, item.assignee_group, item.provider, item.report_date, ...item.recipients].some(value => value?.toLowerCase().includes(search)))
      .sort((a, b) => {
        if (deliverySort === 'started-asc') return Date.parse(a.started_at) - Date.parse(b.started_at)
        if (deliverySort === 'records-desc') return (b.record_count ?? -1) - (a.record_count ?? -1)
        if (deliverySort === 'status-asc') return a.status.localeCompare(b.status) || Date.parse(b.started_at) - Date.parse(a.started_at)
        return Date.parse(b.started_at) - Date.parse(a.started_at)
      })
  }, [deliveriesQuery.data, deliverySearch, deliveryStatus, deliveryMode, deliverySort])

  const saveMutation = useMutation({
    mutationFn: ({ existing, payload }: { existing?: ReportEmailSubscription; payload: ReportEmailSubscriptionPayload }) => existing ? reportEmailsApi.updateSubscription(existing.id, payload) : reportEmailsApi.createSubscription({ ...payload, enabled: false }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['report-email-subscriptions'] }); setEditor(null); toast.success(editor === 'new' ? 'Subscription created with automation off' : 'Subscription updated') },
    onError: error => toast.error(errorMessage(error)),
  })
  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) => reportEmailsApi.setEnabled(id, enabled),
    onMutate: ({ id }) => { setToggleId(id); setApprovalWarning('') },
    onSuccess: subscription => { qc.invalidateQueries({ queryKey: ['report-email-subscriptions'] }); qc.invalidateQueries({ queryKey: ['report-email-deliveries'] }); toast.success(`Automatic delivery ${subscription.enabled ? 'enabled' : 'disabled'}`) },
    onError: error => { if (isApprovalError(error)) setApprovalWarning('Automatic email delivery is awaiting server approval. The subscription remains off.'); else toast.error(errorMessage(error)) },
    onSettled: () => setToggleId(null),
  })
  const deleteMutation = useMutation({
    mutationFn: (id: number) => reportEmailsApi.deleteSubscription(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['report-email-subscriptions'] }); setDeleteTarget(null); toast.success('Email subscription deleted') },
    onError: error => toast.error(errorMessage(error)),
  })
  const sendMutation = useMutation({
    mutationFn: reportEmailsApi.send,
    onSuccess: result => { setConfirmSend(false); qc.invalidateQueries({ queryKey: ['report-email-deliveries'] }); toast.success(`Report sent successfully to ${manual.recipients.length} recipient${manual.recipients.length === 1 ? '' : 's'}. The attachment contains ${result.record_count} records.`); setTab('history') },
    onError: error => { setConfirmSend(false); qc.invalidateQueries({ queryKey: ['report-email-deliveries'] }); if (isApprovalError(error)) toast.info('Manual email testing has not yet been enabled by the backend administrator.'); else if (error instanceof ApiError && error.status === 502) toast.error(`The report could not be delivered. Check Delivery History for the provider error. ${error.message}`); else toast.error(errorMessage(error)) },
  })
  const sendSubscriptionNowMutation = useMutation({
    mutationFn: (subscription: ReportEmailSubscription) => reportEmailsApi.send({
      division: subscription.division,
      assignee_group: subscription.assignee_group,
      recipients: subscription.recipients,
      cc_recipients: subscription.cc_recipients,
      report_date: null,
      attachment_format: subscription.attachment_format,
      subject: null,
    }),
    onSuccess: (result, subscription) => {
      setSendNowTarget(null)
      qc.invalidateQueries({ queryKey: ['report-email-deliveries'] })
      toast.success(`${subscription.name} sent to ${subscription.recipients.length} recipient${subscription.recipients.length === 1 ? '' : 's'} with ${result.record_count} records.`)
      setTab('history')
    },
    onError: error => {
      setSendNowTarget(null)
      qc.invalidateQueries({ queryKey: ['report-email-deliveries'] })
      if (isApprovalError(error)) toast.info('Manual email testing has not yet been enabled by the backend administrator.')
      else if (error instanceof ApiError && error.status === 502) toast.error(`The report could not be delivered. Check Delivery History for the provider error. ${error.message}`)
      else toast.error(errorMessage(error))
    },
  })

  function validateManual() {
    if (!manual.division) return setManualValidation('Division is required.')
    if (!manual.recipients.length) return setManualValidation('At least one primary recipient is required.')
    if (!latest && !manual.report_date) return setManualValidation('Select a report date or use Latest Available.')
    setManualValidation(''); setConfirmSend(true)
  }

  if (!allowed) return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Report Emails']} title="Email Management" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Operational admin access required" sub="Manager, Admin, or Super Admin access is required to manage report emails." icon={<ShieldCheck size={32} />} /></div></div></AppShell>

  return <AppShell><div className="flex flex-col flex-1 min-h-0">
    <PageHeader breadcrumb={['Admin', 'Report Emails']} title="Daily Report Email Management" subtitle="Configure automatic delivery, send official snapshots, and review delivery history." actions={<Btn size="sm" onClick={() => { subscriptionsQuery.refetch(); deliveriesQuery.refetch() }}><RefreshCw size={11} /> Refresh</Btn>} />
    <div className="bg-white border-b border-[#E5E5E5] px-5 flex gap-1">{([{ value: 'subscriptions', label: 'Automatic Subscriptions', icon: CalendarClock }, { value: 'send', label: 'Send Report Now', icon: Send }, { value: 'history', label: 'Delivery History', icon: History }] as const).map(item => <button key={item.value} onClick={() => setTab(item.value)} className={cn('flex items-center gap-1.5 px-3 py-3 text-[11px] font-500 border-b-2', tab === item.value ? 'border-[#E60000] text-[#E60000]' : 'border-transparent text-[#5C5C5C] hover:text-[#1A1A1A]')}><item.icon size={13} />{item.label}</button>)}</div>
    <div className="flex-1 overflow-y-auto p-5">
      {approvalWarning && <div className="mb-4 flex gap-2 rounded-md border border-[#F5D580] bg-[#FFF8E6] px-4 py-3 text-[11px] text-[#8A5200]"><AlertCircle size={14} />{approvalWarning}</div>}

      {tab === 'subscriptions' && <div className="space-y-4">
        <div className="flex items-center"><div className="flex-1"><h2 className="text-[13px] font-600">Automatic subscriptions</h2><p className="text-[10px] text-[#8C8C8C]">Schedules continue on the backend even when no user is logged in.</p></div><Btn variant="primary" size="sm" onClick={() => setEditor('new')}><Plus size={11} /> New subscription</Btn></div>
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[#E5E5E5] bg-white p-3">
          <div className="min-w-[220px] flex-1"><label className={labelClass}>Search</label><input className={fieldClass} value={subscriptionSearch} onChange={event => setSubscriptionSearch(event.target.value)} placeholder="Name, group or recipient" /></div>
          <div><label className={labelClass}>Division</label><select className={cn(fieldClass, 'w-[180px]')} value={subscriptionDivision} onChange={event => setSubscriptionDivision(event.target.value)}><option value="">All divisions</option>{divisionNames.map(division => <option key={division}>{division}</option>)}</select></div>
          <div><label className={labelClass}>Automatic</label><select className={cn(fieldClass, 'w-[130px]')} value={subscriptionState} onChange={event => setSubscriptionState(event.target.value)}><option value="">All states</option><option value="true">Enabled</option><option value="false">Disabled</option></select></div>
          <div><label className={labelClass}>Sort by</label><select className={cn(fieldClass, 'w-[170px]')} value={subscriptionSort} onChange={event => setSubscriptionSort(event.target.value)}><option value="updated-desc">Recently updated</option><option value="name-asc">Name A–Z</option><option value="division-asc">Division A–Z</option><option value="schedule-asc">Delivery time</option></select></div>
          {(subscriptionSearch || subscriptionDivision || subscriptionState) && <Btn size="sm" onClick={() => { setSubscriptionSearch(''); setSubscriptionDivision(''); setSubscriptionState('') }}>Clear</Btn>}
          <span className="pb-1 text-[10px] text-[#8C8C8C]">{visibleSubscriptions.length} result{visibleSubscriptions.length === 1 ? '' : 's'}</span>
        </div>
        <div className="rounded-lg border border-[#E5E5E5] bg-white overflow-hidden"><table className="w-full"><thead><tr className="bg-[#FAFAFA] border-b border-[#E5E5E5]">{['Subscription', 'Scope', 'Recipients', 'Schedule', 'Attachment', 'Automatic', ''].map(label => <th key={label} className="px-3 py-2 text-left text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C]">{label}</th>)}</tr></thead>{subscriptionsQuery.isLoading ? <TableSkeleton rows={6} cols={7} /> : <tbody>{visibleSubscriptions.map(subscription => <tr key={subscription.id} className="border-b border-[#F0F0F0] last:border-0 hover:bg-[#FAFAFA]"><td className="px-3 py-3"><p className="text-[11px] font-600">{subscription.name}</p><p className="text-[9px] text-[#8C8C8C]">Updated by {subscription.updated_by}</p></td><td className="px-3 py-3 text-[10px] text-[#5C5C5C]"><p>{subscription.division}</p><p className="max-w-[220px] truncate text-[#8C8C8C]" title={subscription.assignee_group ?? 'All groups'}>{subscription.assignee_group ?? 'All groups'}</p></td><td className="px-3 py-3 text-[10px] text-[#5C5C5C]"><p>{subscription.recipients.length} To</p><p>{subscription.cc_recipients.length} CC</p></td><td className="px-3 py-3 text-[10px] text-[#5C5C5C]">{subscription.frequency === 'WEEKLY' ? `${WEEKDAYS[subscription.weekday ?? 0]}s` : 'Daily'} at {subscription.send_time.slice(0, 5)}<p className="text-[9px] text-[#8C8C8C]">{subscription.timezone}</p></td><td className="px-3 py-3 text-[10px]">{subscription.attachment_format}</td><td className="px-3 py-3"><button disabled={toggleId === subscription.id} onClick={() => toggleMutation.mutate({ id: subscription.id, enabled: !subscription.enabled })} role="switch" aria-checked={subscription.enabled} className={cn('relative h-5 w-9 rounded-full transition-colors disabled:opacity-50', subscription.enabled ? 'bg-[#16A34A]' : 'bg-[#D0D0D0]')}><span className={cn('absolute top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform', subscription.enabled ? 'translate-x-[18px]' : 'translate-x-0.5')}>{toggleId === subscription.id && <span className="absolute inset-1 rounded-full border border-[#8C8C8C] border-t-transparent animate-spin" />}</span></button></td><td className="px-3 py-3 text-right whitespace-nowrap"><button onClick={() => setSendNowTarget(subscription)} title="Send latest available report now" className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-600 text-[#0057A8] hover:bg-[#EEF4FF]"><Send size={12} /> Send now</button><button onClick={() => setEditor(subscription)} title="Edit subscription" className="p-1.5 text-[#8C8C8C] hover:text-[#1A1A1A]"><Edit3 size={13} /></button><button onClick={() => setDeleteTarget(subscription)} title="Delete subscription" className="p-1.5 text-[#8C8C8C] hover:text-[#CC0000]"><Trash2 size={13} /></button></td></tr>)}</tbody>}</table>{!subscriptionsQuery.isLoading && !visibleSubscriptions.length && <EmptyState title="No email subscriptions found" sub="Create a disabled subscription and enable it after review and server approval." icon={<Mail size={30} />} />}</div>
      </div>}

      {tab === 'send' && <div className="max-w-4xl mx-auto rounded-lg border border-[#E5E5E5] bg-white overflow-hidden"><div className="border-b border-[#E5E5E5] px-5 py-4"><h2 className="text-[13px] font-600">Send an official Daily Report now</h2><p className="text-[10px] text-[#8C8C8C]">The backend builds the email and attachment. Manual sending does not create a subscription.</p></div><div className="p-5 space-y-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4"><div><label className={labelClass}>Division *</label><select value={manual.division} onChange={event => setManual(current => ({ ...current, division: event.target.value, assignee_group: null }))} className={fieldClass}><option value="">Select division</option>{divisionNames.map(division => <option key={division}>{division}</option>)}</select></div><div><label className={labelClass}>Assignee group</label><select value={manual.assignee_group ?? ''} disabled={!manual.division || manualGroupsQuery.isLoading} onChange={event => setManual(current => ({ ...current, assignee_group: event.target.value || null }))} className={fieldClass}><option value="">All groups</option>{manualGroupsQuery.data?.groups.filter(group => group.active).map(group => <option key={group.assignee_group}>{group.assignee_group}</option>)}</select></div></div>
        <EmailsInput label="Recipients" values={manual.recipients} onChange={recipients => setManual(current => ({ ...current, recipients }))} required /><EmailsInput label="CC recipients" values={manual.cc_recipients} onChange={cc_recipients => setManual(current => ({ ...current, cc_recipients }))} />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4"><div><label className={labelClass}>Report snapshot</label><select value={latest ? 'latest' : 'date'} onChange={event => { const useLatest = event.target.value === 'latest'; setLatest(useLatest); if (useLatest) setManual(current => ({ ...current, report_date: null })) }} className={fieldClass}><option value="latest">Latest Available</option><option value="date">Choose date</option></select></div><div><label className={labelClass}>Report date</label><input type="date" disabled={latest} value={manual.report_date ?? ''} onChange={event => setManual(current => ({ ...current, report_date: event.target.value || null }))} className={fieldClass} /></div><div><label className={labelClass}>Attachment</label><select value={manual.attachment_format} onChange={event => setManual(current => ({ ...current, attachment_format: event.target.value as ReportEmailFormat }))} className={fieldClass}><option value="XLSX">Excel (.xlsx)</option><option value="CSV">CSV</option></select></div></div>
        <div><label className={labelClass}>Custom subject</label><input value={manual.subject ?? ''} onChange={event => setManual(current => ({ ...current, subject: event.target.value || null }))} maxLength={250} placeholder="Optional — backend generates a subject when blank" className={fieldClass} /></div>
        {manualValidation && <div className="rounded-md border border-[#F5B8B8] bg-[#FFF0F0] px-3 py-2 text-[11px] text-[#CC0000]">{manualValidation}</div>}
      </div><div className="flex justify-end border-t border-[#E5E5E5] px-5 py-3"><Btn variant="primary" onClick={validateManual} disabled={sendMutation.isPending}><Send size={12} /> Send Report Now</Btn></div></div>}

      {tab === 'history' && <div className="space-y-4"><div><h2 className="text-[13px] font-600">Delivery history</h2><p className="text-[10px] text-[#8C8C8C]">Provider acceptance means sent; it does not confirm that a recipient opened the message.</p></div>
        <div className="flex flex-wrap items-end gap-3 rounded-lg border border-[#E5E5E5] bg-white p-3">
          <div className="min-w-[220px] flex-1"><label className={labelClass}>Search</label><input className={fieldClass} value={deliverySearch} onChange={event => setDeliverySearch(event.target.value)} placeholder="Subscription, recipient, provider or division" /></div>
          <div><label className={labelClass}>Status</label><select className={cn(fieldClass, 'w-[130px]')} value={deliveryStatus} onChange={event => setDeliveryStatus(event.target.value)}><option value="">All statuses</option><option>SENT</option><option>FAILED</option><option>SKIPPED</option><option>SENDING</option></select></div>
          <div><label className={labelClass}>Mode</label><select className={cn(fieldClass, 'w-[140px]')} value={deliveryMode} onChange={event => setDeliveryMode(event.target.value)}><option value="">All modes</option><option value="AUTOMATIC">Automatic</option><option value="MANUAL">Manual</option></select></div>
          <div><label className={labelClass}>Sort by</label><select className={cn(fieldClass, 'w-[165px]')} value={deliverySort} onChange={event => setDeliverySort(event.target.value)}><option value="started-desc">Newest first</option><option value="started-asc">Oldest first</option><option value="records-desc">Most records</option><option value="status-asc">Status A–Z</option></select></div>
          {(deliverySearch || deliveryStatus || deliveryMode) && <Btn size="sm" onClick={() => { setDeliverySearch(''); setDeliveryStatus(''); setDeliveryMode('') }}>Clear</Btn>}
          <span className="pb-1 text-[10px] text-[#8C8C8C]">{visibleDeliveries.length} result{visibleDeliveries.length === 1 ? '' : 's'}</span>
        </div>
        <div className="rounded-lg border border-[#E5E5E5] bg-white overflow-x-auto"><table className="min-w-[1050px] w-full"><thead><tr className="bg-[#FAFAFA] border-b border-[#E5E5E5]">{['Status', 'Mode', 'Report', 'Subscription / Requester', 'Recipients', 'Records', 'Provider', 'Started', 'Details'].map(label => <th key={label} className="px-3 py-2 text-left text-[9px] font-600 uppercase tracking-wide text-[#8C8C8C]">{label}</th>)}</tr></thead>{deliveriesQuery.isLoading ? <TableSkeleton rows={8} cols={9} /> : <tbody>{visibleDeliveries.map(delivery => <tr key={delivery.id} className="border-b border-[#F0F0F0] last:border-0 align-top"><td className="px-3 py-3"><StatusBadge status={delivery.status} /></td><td className="px-3 py-3 text-[10px]">{delivery.delivery_mode}</td><td className="px-3 py-3 text-[10px]"><p>{delivery.report_date}</p>{delivery.division && <p className="text-[#8C8C8C]">{delivery.division}{delivery.assignee_group ? ` · ${delivery.assignee_group}` : ''}</p>}</td><td className="px-3 py-3 text-[10px] max-w-[180px]"><p className="truncate">{delivery.subscription_name ?? delivery.requested_by ?? 'Automatic scheduler'}</p></td><td className="px-3 py-3 text-[10px]">{delivery.recipients.length}</td><td className="px-3 py-3 text-[10px]">{delivery.record_count?.toLocaleString('en-ZA') ?? '—'}</td><td className="px-3 py-3 text-[10px]">{delivery.provider ?? '—'}<p className="text-[9px] text-[#8C8C8C]">Attempt {delivery.attempt_count}</p></td><td className="px-3 py-3 text-[10px] whitespace-nowrap">{fmtDateTime(delivery.started_at)}</td><td className="px-3 py-3 text-[10px] text-[#CC0000] max-w-[260px] break-words">{delivery.error_message ?? '—'}</td></tr>)}</tbody>}</table>{!deliveriesQuery.isLoading && !visibleDeliveries.length && <EmptyState title="No delivery history found" sub="Manual and automatic delivery attempts will appear here." icon={<History size={30} />} />}</div></div>}
    </div>

    <AnimatePresence>{editor && <Modal title={editor === 'new' ? 'Create email subscription' : 'Edit email subscription'} onClose={() => setEditor(null)}><SubscriptionEditor initial={editor === 'new' ? undefined : editor} divisions={divisionNames} saving={saveMutation.isPending} onCancel={() => setEditor(null)} onSave={payload => saveMutation.mutate({ existing: editor === 'new' ? undefined : editor, payload })} /></Modal>}</AnimatePresence>
    <AnimatePresence>{deleteTarget && <Modal title="Delete email subscription?" onClose={() => setDeleteTarget(null)} width="max-w-md"><div className="p-5"><p className="text-[12px] text-[#5C5C5C]">Delete <strong>{deleteTarget.name}</strong>? Automatic delivery for this subscription will stop.</p></div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn onClick={() => setDeleteTarget(null)}>Cancel</Btn><Btn variant="danger" loading={deleteMutation.isPending} onClick={() => deleteMutation.mutate(deleteTarget.id)}>Delete subscription</Btn></div></Modal>}</AnimatePresence>
    <AnimatePresence>{sendNowTarget && <Modal title="Send configured subscription now?" onClose={() => !sendSubscriptionNowMutation.isPending && setSendNowTarget(null)} width="max-w-lg"><div className="p-5 space-y-4 text-[11px]"><p>Send <strong>{sendNowTarget.name}</strong> using the latest available report snapshot?</p><div className="rounded-md bg-[#FAFAFA] border border-[#E5E5E5] p-3 space-y-2"><div><span className="text-[#8C8C8C]">Scope:</span><p>{sendNowTarget.division}{sendNowTarget.assignee_group ? ` · ${sendNowTarget.assignee_group}` : ' · All groups'}</p></div><div><span className="text-[#8C8C8C]">To:</span><p>{sendNowTarget.recipients.join(', ')}</p></div><div><span className="text-[#8C8C8C]">CC:</span><p>{sendNowTarget.cc_recipients.length ? sendNowTarget.cc_recipients.join(', ') : 'None'}</p></div><div><span className="text-[#8C8C8C]">Attachment:</span><p>{sendNowTarget.attachment_format === 'XLSX' ? 'Excel (.xlsx)' : 'CSV'}</p></div></div>{sendSubscriptionNowMutation.isPending && <div className="flex items-center gap-2 text-[#0057A8]"><Clock size={13} className="animate-spin" />Generating and sending report…</div>}</div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn disabled={sendSubscriptionNowMutation.isPending} onClick={() => setSendNowTarget(null)}>Cancel</Btn><Btn variant="primary" loading={sendSubscriptionNowMutation.isPending} onClick={() => sendSubscriptionNowMutation.mutate(sendNowTarget)}><Check size={12} /> Confirm and send</Btn></div></Modal>}</AnimatePresence>
    <AnimatePresence>{confirmSend && <Modal title="Confirm manual report delivery" onClose={() => !sendMutation.isPending && setConfirmSend(false)} width="max-w-lg"><div className="p-5 space-y-4 text-[11px]"><p>Send the <strong>{manual.assignee_group ?? manual.division} Daily Report</strong> for <strong>{manual.report_date ? new Date(`${manual.report_date}T00:00:00`).toLocaleDateString('en-ZA', { day: 'numeric', month: 'long', year: 'numeric' }) : 'Latest Available'}</strong>?</p><div className="rounded-md bg-[#FAFAFA] border border-[#E5E5E5] p-3 space-y-2"><div><span className="text-[#8C8C8C]">To:</span><p>{manual.recipients.join(', ')}</p></div><div><span className="text-[#8C8C8C]">CC:</span><p>{manual.cc_recipients.length ? manual.cc_recipients.join(', ') : 'None'}</p></div><div><span className="text-[#8C8C8C]">Attachment:</span><p>{manual.attachment_format === 'XLSX' ? 'Excel (.xlsx)' : 'CSV'}</p></div></div>{sendMutation.isPending && <div className="flex items-center gap-2 text-[#0057A8]"><Clock size={13} className="animate-spin" />Generating and sending report…</div>}</div><div className="flex justify-end gap-2 border-t border-[#E5E5E5] px-5 py-3"><Btn disabled={sendMutation.isPending} onClick={() => setConfirmSend(false)}>Cancel</Btn><Btn variant="primary" loading={sendMutation.isPending} onClick={() => sendMutation.mutate({ ...manual, report_date: latest ? null : manual.report_date })}><Check size={12} /> Confirm and send</Btn></div></Modal>}</AnimatePresence>
  </div></AppShell>
}




