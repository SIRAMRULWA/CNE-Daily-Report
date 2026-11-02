'use client'

import { useState, useEffect, useRef } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { workspaceApi, divisionsApi } from '@/lib/api'
import { RecordsExport } from '@/components/records/RecordsExport'
import {
  fmtDate, fmtHours, fmtCountdown, hoursColor, cn,
} from '@/lib/utils'
import {
  PageHeader, SlaBadge, CategoryChip, PriorityChip,
  TableSkeleton, EmptyState, Btn,
} from '@/components/ui'
import type { WorkspaceRecord, SlaStatus, Category, Filters } from '@/types'
import {
  Search, X, RefreshCw, Filter, ChevronLeft, ChevronRight,
  AlertTriangle, Clock, Info, CheckCircle2, Eye, SlidersHorizontal, Database,
} from 'lucide-react'

// ─── SLA filter chips ─────────────────────────────────────────────────────────

const SLA_CHIPS: { value: SlaStatus | ''; label: string; activeClass: string }[] = [
  { value: 'BREACHED',    label: 'Breached',    activeClass: 'bg-[#FFF0F0] border-[#F5B8B8] text-[#CC0000]' },
  { value: 'NEARING_SLA', label: 'Nearing SLA', activeClass: 'bg-[#FFF8E6] border-[#F5D580] text-[#C47000]' },
  { value: 'NO_SCHEDULE', label: 'No Schedule', activeClass: 'bg-[#EEF4FF] border-[#B8CEFF] text-[#0057A8]' },
  { value: 'WITHIN_SLA',  label: 'Within SLA',  activeClass: 'bg-[#EDF7ED] border-[#B8DFB8] text-[#0A7A0A]' },
  { value: '',             label: 'All',         activeClass: 'bg-[#F5F5F5] border-[#D0D0D0] text-[#1A1A1A]' },
]

const CATEGORY_OPTIONS: Category[] = ['INCIDENT', 'CHANGE', 'ACCESS', 'EVENT']
const PRIORITY_OPTIONS = ['Critical', 'High', 'Medium', 'Low']

interface RecordsFilterState {
  sla: SlaStatus[]
  divisions: string[]
  categories: Category[]
  priorities: string[]
  search?: string
  include_excluded: boolean
  limit: number
  offset: number
}

// ─── Live countdown cell ──────────────────────────────────────────────────────

function CountdownCell({ secondsToBreach }: {
  dueAt: string | null
  secondsToBreach: number | null
  slaStatus: SlaStatus | null
}) {
  const [secs, setSecs] = useState(secondsToBreach)

  useEffect(() => {
    setSecs(secondsToBreach)
    if (secondsToBreach == null) return
    const interval = setInterval(() => {
      setSecs(prev => (prev != null ? prev - 1 : prev))
    }, 1000)
    return () => clearInterval(interval)
  }, [secondsToBreach])

  if (secs == null) return <span className="text-[#8C8C8C] text-[11px]">—</span>

  const color = secs < 0
    ? 'text-[#CC0000] font-600'
    : secs < 14400
    ? 'text-[#C47000] font-500'
    : 'text-[#5C5C5C]'

  return (
    <span className={cn('font-mono text-[11px]', color)}>
      {fmtCountdown(secs)}
    </span>
  )
}

// ─── Summary bar above table ──────────────────────────────────────────────────

function SummaryBar({ records }: { records: WorkspaceRecord[] }) {
  const counts = { BREACHED: 0, NEARING_SLA: 0, NO_SCHEDULE: 0, WITHIN_SLA: 0 }
  records.forEach(r => {
    if (r.sla_status && r.sla_status in counts) {
      counts[r.sla_status as keyof typeof counts]++
    }
  })

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-[#FAFAFA] border-b border-[#E5E5E5] text-[11px]">
      {[
        { key: 'BREACHED',    label: 'Breached',    color: 'text-[#CC0000]', icon: <AlertTriangle size={11} /> },
        { key: 'NEARING_SLA', label: 'Nearing',     color: 'text-[#C47000]', icon: <Clock size={11} /> },
        { key: 'NO_SCHEDULE', label: 'No Schedule', color: 'text-[#0057A8]', icon: <Info size={11} /> },
        { key: 'WITHIN_SLA',  label: 'Within SLA',  color: 'text-[#0A7A0A]', icon: <CheckCircle2 size={11} /> },
      ].map(s => (
        <div key={s.key} className={cn('flex items-center gap-1 font-500', s.color)}>
          {s.icon}
          <span>{counts[s.key as keyof typeof counts]}</span>
          <span className="text-[#8C8C8C] font-400">{s.label}</span>
        </div>
      ))}
      <span className="ml-auto text-[#8C8C8C]">{records.length} shown</span>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

function matchesSearch(record: WorkspaceRecord, term: string): boolean {
  const needle = term.trim().toLowerCase()
  if (!needle) return true

  return [
    record.request_id,
    record.task_id,
    record.division,
    record.assignee_group,
    record.report_category,
    record.priority,
    record.status,
    record.status_reason,
    record.assignee,
    record.summary,
  ].some(value => String(value ?? '').toLowerCase().includes(needle))
}

function recordMatchesFilters(record: WorkspaceRecord, filters: RecordsFilterState): boolean {
  if (filters.sla.length && (!record.sla_status || !filters.sla.includes(record.sla_status))) return false
  if (filters.divisions.length && (!record.division || !filters.divisions.includes(record.division))) return false
  if (filters.categories.length && (!record.report_category || !filters.categories.includes(record.report_category))) return false
  if (filters.priorities.length && (!record.priority || !filters.priorities.includes(record.priority))) return false
  if (filters.search && !matchesSearch(record, filters.search)) return false
  return true
}

function toggleValue<T extends string>(values: T[], value: T): T[] {
  return values.includes(value)
    ? values.filter(item => item !== value)
    : [...values, value]
}

function MultiFilter({
  label,
  values,
  options,
  onToggle,
  onClear,
}: {
  label: string
  values: string[]
  options: { value: string; label: string }[]
  onToggle: (value: string) => void
  onClear: () => void
}) {
  const [open, setOpen] = useState(false)
  const activeLabel = values.length ? `${label}: ${values.length}` : label

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen(value => !value)}
        className={cn(
          'h-7 inline-flex items-center gap-1.5 px-2.5 text-[12px] border rounded-md bg-white outline-none transition-colors',
          values.length
            ? 'border-[#F5B8B8] text-[#CC0000] bg-[#FFF8F8]'
            : 'border-[#E5E5E5] text-[#5C5C5C] hover:border-[#D0D0D0]',
        )}
      >
        <SlidersHorizontal size={12} />
        {activeLabel}
      </button>

      {open && (
        <div className="absolute z-30 mt-1 w-56 max-h-72 overflow-y-auto bg-white border border-[#D0D0D0] rounded-md shadow-[0_8px_24px_rgba(0,0,0,0.12)] p-1.5">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-[10px] uppercase tracking-[0.5px] font-600 text-[#8C8C8C]">{label}</span>
            {values.length > 0 && (
              <button type="button" onClick={onClear} className="text-[10px] text-[#CC0000] hover:underline">
                Clear
              </button>
            )}
          </div>
          {options.map(option => {
            const active = values.includes(option.value)
            return (
              <button
                type="button"
                key={option.value}
                onClick={() => onToggle(option.value)}
                className={cn(
                  'w-full flex items-center gap-2 px-2 py-1.5 rounded text-left text-[12px]',
                  active ? 'bg-[#FFF0F0] text-[#CC0000]' : 'text-[#5C5C5C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]',
                )}
              >
                <span className={cn(
                  'w-3.5 h-3.5 border rounded-[3px] flex items-center justify-center text-[9px]',
                  active ? 'bg-[#E60000] border-[#E60000] text-white' : 'border-[#D0D0D0]',
                )}>
                  {active ? '✓' : ''}
                </span>
                <span className="truncate">{option.label}</span>
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function DetailField({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] uppercase tracking-[0.5px] font-600 text-[#8C8C8C] mb-1">{label}</div>
      <div className={cn('text-[12px] text-[#1A1A1A] break-words', mono ? 'font-mono' : '')}>
        {value || <span className="text-[#8C8C8C]">-</span>}
      </div>
    </div>
  )
}

function RecordDetails({ record, onClose }: { record: WorkspaceRecord; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-[80] flex justify-end bg-black/25" onClick={onClose}>
      <motion.aside
        initial={{ x: 420 }}
        animate={{ x: 0 }}
        exit={{ x: 420 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
        onClick={event => event.stopPropagation()}
        className="h-full w-[420px] max-w-[92vw] bg-white border-l border-[#D0D0D0] shadow-[0_0_30px_rgba(0,0,0,0.18)] flex flex-col"
      >
        <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-start gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <SlaBadge status={record.sla_status} />
              <CategoryChip category={record.report_category} />
              <PriorityChip priority={record.priority} />
            </div>
            <h2 className="text-[15px] font-700 text-[#1A1A1A] font-mono">{record.task_id}</h2>
            <p className="text-[12px] text-[#5C5C5C] truncate">{record.summary ?? 'No summary'}</p>
          </div>
          <button onClick={onClose} className="p-1 text-[#8C8C8C] hover:text-[#1A1A1A] rounded">
            <X size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-5">
          <section className="grid grid-cols-2 gap-4">
            <DetailField label="Request ID" value={record.request_id} mono />
            <DetailField label="Task ID" value={record.task_id} mono />
            <DetailField label="Division" value={record.division} />
            <DetailField label="Group" value={record.assignee_group} />
            <DetailField label="Status" value={record.status} />
            <DetailField label="Reason" value={record.status_reason} />
            <DetailField label="Assignee" value={record.assignee} />
            <DetailField label="Hours Open" value={fmtHours(record.hours_open)} />
          </section>

          <section>
            <DetailField label="Summary" value={record.summary} />
          </section>

          <section className="grid grid-cols-2 gap-4">
            <DetailField label="Assign Time" value={record.assign_time} />
            <DetailField label="Due At" value={record.due_at} />
            <DetailField label="Scheduled Start" value={record.scheduled_start} />
            <DetailField label="Scheduled End" value={record.scheduled_end} />
            <DetailField label="Closed Time" value={record.closed_time} />
            <DetailField label="Loaded At" value={record.loaded_at} />
          </section>

          <section className="grid grid-cols-2 gap-4">
            <DetailField label="Source" value={record.source} />
            <DetailField label="Excluded" value={record.exclude_change || record.exclude_incident ? 'Yes' : 'No'} />
          </section>
        </div>
      </motion.aside>
    </div>
  )
}

const LIMIT = 250

export default function RecordsPage() {
  const qc = useQueryClient()
  const searchRef = useRef<HTMLInputElement>(null)
  const tableScrollRef = useRef<HTMLDivElement>(null)
  const [searchInput, setSearchInput] = useState('')
  const [selectedRecord, setSelectedRecord] = useState<WorkspaceRecord | null>(null)
  const [filters, setFilters] = useState<RecordsFilterState>({
    sla: [],
    divisions: [],
    categories: [],
    priorities: [],
    include_excluded: false,
    limit: LIMIT,
    offset: 0,
  })

  // Debounced search
  useEffect(() => {
    const t = setTimeout(() => {
      setFilters(f => ({ ...f, search: searchInput || undefined, offset: 0 }))
    }, 350)
    return () => clearTimeout(t)
  }, [searchInput])

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['workspace-records', filters],
    queryFn: () => workspaceApi.records({
      sla: filters.sla.length === 1 ? filters.sla[0] : undefined,
      division: filters.divisions.length === 1 ? filters.divisions[0] : undefined,
      category: filters.categories.length === 1 ? filters.categories[0] : undefined,
      priority: filters.priorities.length === 1 ? filters.priorities[0] : undefined,
      include_excluded: filters.include_excluded,
      limit: filters.limit,
      offset: filters.offset,
    } satisfies Partial<Filters>),
    placeholderData: prev => prev,
  })

  const { data: divData } = useQuery({
    queryKey: ['divisions'],
    queryFn: divisionsApi.list,
  })

  function setFilter<K extends keyof RecordsFilterState>(key: K, value: RecordsFilterState[K]) {
    setFilters(f => ({ ...f, [key]: value, offset: 0 }))
  }

  function clearFilters() {
    setSearchInput('')
    setFilters({
      sla: [],
      divisions: [],
      categories: [],
      priorities: [],
      include_excluded: false,
      limit: LIMIT,
      offset: 0,
    })
  }

  const hasActiveFilters = !!(
    filters.divisions.length
    || filters.categories.length
    || filters.priorities.length
    || filters.sla.length
    || filters.search
    || filters.include_excluded
  )

  const visibleRecords = data?.records.filter(record => recordMatchesFilters(record, filters)) ?? []
  const total = hasActiveFilters ? visibleRecords.length : data?.total ?? 0
  const page = Math.floor((filters.offset ?? 0) / LIMIT) + 1
  const totalPages = Math.ceil(total / LIMIT)

  function scrollTable(direction: 'left' | 'right') {
    tableScrollRef.current?.scrollBy({
      left: direction === 'left' ? -420 : 420,
      behavior: 'smooth',
    })
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <PageHeader
        breadcrumb={['Operations Console', 'Records']}
        title="Operations Records"
        subtitle={data?.data_date
          ? `Live view for ${fmtDate(data.data_date, 'dd MMMM yyyy')}`
          : 'Live view of all active change and incident tasks'}
        actions={
          <>
            {hasActiveFilters && (
              <Btn variant="ghost" size="sm" onClick={clearFilters}>
                <X size={11} /> Clear filters
              </Btn>
            )}
            <Btn
              variant="default" size="sm"
              onClick={() => qc.invalidateQueries({ queryKey: ['workspace-records'] })}
            >
              <RefreshCw size={11} className={isFetching ? 'animate-spin' : ''} />
              Refresh
            </Btn>
            <RecordsExport records={visibleRecords} disabled={isLoading} />
          </>
        }
      />

      {/* Toolbar */}
      <div className="bg-white border-b border-[#E5E5E5] px-4 py-2.5 flex items-center gap-2.5 flex-shrink-0 flex-wrap">
        {/* Search */}
        <div className="flex items-center gap-1.5 bg-[#F5F5F5] border border-[#E5E5E5] rounded-md px-2.5 py-[5px] flex-1 max-w-[280px]">
          <Search size={13} className="text-[#8C8C8C] flex-shrink-0" />
          <input
            ref={searchRef}
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            placeholder="Search ID, summary, assignee…"
            className="bg-transparent outline-none text-[12px] text-[#1A1A1A] placeholder:text-[#8C8C8C] w-full"
          />
          {searchInput && (
            <button onClick={() => setSearchInput('')} className="text-[#8C8C8C] hover:text-[#1A1A1A]">
              <X size={12} />
            </button>
          )}
        </div>

        {/* SLA chips */}
        <div className="flex gap-1.5">
          {SLA_CHIPS.map(chip => (
            <button
              key={chip.value}
              onClick={() => setFilter('sla', chip.value ? toggleValue(filters.sla, chip.value) : [])}
              className={cn(
                'px-2.5 py-1 rounded-full text-[11px] font-500 border transition-all cursor-pointer',
                chip.value ? filters.sla.includes(chip.value) : filters.sla.length === 0
                  ? chip.activeClass
                  : 'bg-white border-[#E5E5E5] text-[#5C5C5C] hover:border-[#D0D0D0] hover:text-[#1A1A1A]',
              )}
            >
              {chip.label}
            </button>
          ))}
        </div>

        {/* Division select */}
        <div className="h-px w-px bg-[#E5E5E5] self-stretch" />
        <MultiFilter
          label="Divisions"
          values={filters.divisions}
          options={divData?.divisions.map(d => ({ value: d.division, label: d.division })) ?? []}
          onToggle={value => setFilter('divisions', toggleValue(filters.divisions, value))}
          onClear={() => setFilter('divisions', [])}
        />
        <MultiFilter
          label="Categories"
          values={filters.categories}
          options={CATEGORY_OPTIONS.map(category => ({ value: category, label: category }))}
          onToggle={value => setFilter('categories', toggleValue(filters.categories, value as Category))}
          onClear={() => setFilter('categories', [])}
        />
        <MultiFilter
          label="Priority"
          values={filters.priorities}
          options={PRIORITY_OPTIONS.map(priority => ({ value: priority, label: priority }))}
          onToggle={value => setFilter('priorities', toggleValue(filters.priorities, value))}
          onClear={() => setFilter('priorities', [])}
        />

        <label className="h-7 inline-flex items-center gap-1.5 px-2.5 text-[12px] border border-[#E5E5E5] rounded-md bg-white text-[#5C5C5C] cursor-pointer">
          <input
            type="checkbox"
            checked={filters.include_excluded}
            onChange={event => setFilter('include_excluded', event.target.checked)}
            className="accent-[#E60000]"
          />
          Include excluded
        </label>

        <span className="ml-auto text-[11px] text-[#8C8C8C]">
          {isLoading ? 'Loading…' : `${total.toLocaleString()} records`}
        </span>
      </div>

      {/* Summary bar */}
      {data && <SummaryBar records={visibleRecords} />}

      <div className="bg-white border-b border-[#E5E5E5] px-4 py-1.5 flex items-center gap-2 text-[11px] text-[#8C8C8C]">
        <span className="flex-1">Click a row to view task details. Use the arrows to move across the table.</span>
        <Btn variant="default" size="sm" onClick={() => scrollTable('left')}>
          <ChevronLeft size={13} /> Left
        </Btn>
        <Btn variant="default" size="sm" onClick={() => scrollTable('right')}>
          Right <ChevronRight size={13} />
        </Btn>
      </div>

      {/* Table */}
      <div ref={tableScrollRef} className="flex-1 overflow-auto bg-white">
        <table className="records-table min-w-[1280px] w-full border-collapse">
          <thead>
            <tr>
              {[
                { label: 'SLA',          w: '90px'  },
                { label: 'Request ID',   w: '120px' },
                { label: 'Task ID',      w: '110px' },
                { label: 'Division',     w: '70px'  },
                { label: 'Group',        w: '160px' },
                { label: 'Category',     w: '80px'  },
                { label: 'Priority',     w: '80px'  },
                { label: 'Status',       w: '100px' },
                { label: 'Assignee',     w: '120px' },
                { label: 'Summary',      w: 'auto'  },
                { label: 'Hrs Open',     w: '70px', right: true },
                { label: 'Breach / Due', w: '110px', right: true },
                { label: '',             w: '36px', right: true },
              ].map(col => (
                <th
                  key={col.label}
                  style={{ width: col.w }}
                  className={cn(
                    'text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.4px] py-2 px-3.5 bg-[#FAFAFA] border-b border-[#E5E5E5] whitespace-nowrap sticky top-0 z-10',
                    col.right ? 'text-right' : 'text-left',
                  )}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>

          {isLoading ? (
            <TableSkeleton rows={12} cols={13} />
          ) : data?.data_available === false ? (
            <tbody>
              <tr>
                <td colSpan={13}>
                  <EmptyState
                    title={`No pipeline data has been loaded for ${fmtDate(data.data_date, 'dd MMMM yyyy')}.`}
                    sub={`No records from an earlier day are being shown. Timezone: ${data.timezone}.`}
                    icon={<Database size={32} />}
                  />
                </td>
              </tr>
            </tbody>
          ) : !visibleRecords.length ? (
            <tbody>
              <tr>
                <td colSpan={13}>
                  <EmptyState
                    title="No records found"
                    sub="Try adjusting your filters or refreshing the data"
                    icon={<Filter size={32} />}
                  />
                </td>
              </tr>
            </tbody>
          ) : (
            <tbody>
              {visibleRecords.map((rec, i) => {
                const rowCls = rec.sla_status === 'BREACHED'
                  ? 'row-breach'
                  : rec.sla_status === 'NEARING_SLA'
                  ? 'row-near'
                  : ''
                return (
                  <motion.tr
                    key={rec.task_id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(i * 0.01, 0.3) }}
                    onClick={() => setSelectedRecord(rec)}
                    className={cn('border-b border-[#F0F0F0] hover:bg-[#F5F5F5] cursor-pointer transition-colors', rowCls)}
                  >
                    <td className="px-3.5 py-2.5"><SlaBadge status={rec.sla_status} /></td>
                    <td className="px-3.5 py-2.5">
                      <span className="font-mono text-[11px] text-[#0057A8] font-500">{rec.request_id}</span>
                    </td>
                    <td className="px-3.5 py-2.5">
                      <span className="font-mono text-[11px] text-[#5C5C5C]">{rec.task_id}</span>
                    </td>
                    <td className="px-3.5 py-2.5 text-[12px] text-[#5C5C5C]">{rec.division ?? '—'}</td>
                    <td className="px-3.5 py-2.5">
                      <span className="text-[11px] text-[#5C5C5C] max-w-[150px] truncate block" title={rec.assignee_group ?? ''}>
                        {rec.assignee_group ?? '—'}
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5"><CategoryChip category={rec.report_category} /></td>
                    <td className="px-3.5 py-2.5"><PriorityChip priority={rec.priority} /></td>
                    <td className="px-3.5 py-2.5 text-[11px] text-[#5C5C5C]">{rec.status ?? '—'}</td>
                    <td className="px-3.5 py-2.5 text-[12px] text-[#5C5C5C] max-w-[110px] truncate">{rec.assignee ?? '—'}</td>
                    <td className="px-3.5 py-2.5">
                      <span className="text-[12px] text-[#1A1A1A] max-w-[240px] truncate block summary-cell" title={rec.summary ?? ''}>
                        {rec.summary ?? '—'}
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5 text-right">
                      <span className={cn('text-[12px] font-600', hoursColor(rec.hours_open, rec.sla_status))}>
                        {fmtHours(rec.hours_open)}
                      </span>
                    </td>
                    <td className="px-3.5 py-2.5 text-right">
                      <CountdownCell
                        dueAt={rec.due_at}
                        secondsToBreach={rec.seconds_to_breach}
                        slaStatus={rec.sla_status}
                      />
                    </td>
                    <td className="px-3.5 py-2.5 text-right">
                      <Eye size={13} className="inline text-[#8C8C8C]" />
                    </td>
                  </motion.tr>
                )
              })}
            </tbody>
          )}
        </table>
      </div>

      {/* Pagination */}
      <div className="bg-white border-t border-[#E5E5E5] px-4 py-2.5 flex items-center gap-3 flex-shrink-0">
        <span className="text-[11px] text-[#8C8C8C] flex-1">
          {total > 0
            ? `Showing ${(filters.offset ?? 0) + 1}–${Math.min((filters.offset ?? 0) + LIMIT, total)} of ${total.toLocaleString()} records`
            : 'No records'}
        </span>
        <Btn
          variant="default" size="sm"
          disabled={(filters.offset ?? 0) === 0}
          onClick={() => setFilters(f => ({ ...f, offset: Math.max(0, (f.offset ?? 0) - LIMIT) }))}
        >
          <ChevronLeft size={13} /> Prev
        </Btn>
        <span className="text-[11px] text-[#5C5C5C]">Page {page} of {totalPages || 1}</span>
        <Btn
          variant="default" size="sm"
          disabled={(filters.offset ?? 0) + LIMIT >= total}
          onClick={() => setFilters(f => ({ ...f, offset: (f.offset ?? 0) + LIMIT }))}
        >
          Next <ChevronRight size={13} />
        </Btn>
      </div>

      {selectedRecord && (
        <RecordDetails record={selectedRecord} onClose={() => setSelectedRecord(null)} />
      )}
    </div>
  )
}
