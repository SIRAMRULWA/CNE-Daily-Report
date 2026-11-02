'use client'

import { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { AlertTriangle, ArrowDown, ArrowUp, CalendarDays, ChevronDown, ChevronLeft, ChevronRight, ChevronUp, Columns3, Database, Eye, FileSpreadsheet, FileText, Filter, Gauge, Hash, Layers3, Play, Search, SlidersHorizontal, Sparkles, UserRound, X, Zap } from 'lucide-react'
import { helixRawReportsApi } from '@/lib/api'
import { Btn, EmptyState, PageHeader, TableSkeleton } from '@/components/ui'
import { cn } from '@/lib/utils'
import type { HelixRawReportRequest, HelixRawReportResponse } from '@/types'

function localInputValue(date: Date): string {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000)
  return shifted.toISOString().slice(0, 16)
}

function toOffsetIso(value: string): string {
  const date = new Date(value)
  const offset = -date.getTimezoneOffset()
  const sign = offset >= 0 ? '+' : '-'
  const hours = String(Math.floor(Math.abs(offset) / 60)).padStart(2, '0')
  const minutes = String(Math.abs(offset) % 60).padStart(2, '0')
  return `${value.length === 16 ? `${value}:00` : value}${sign}${hours}:${minutes}`
}

function initialRange() {
  const end = new Date()
  const start = new Date(end.getFullYear(), end.getMonth(), 1, 0, 0, 0)
  return { start: localInputValue(start), end: localInputValue(end) }
}

function displayValue(value: unknown): string {
  if (value === null || value === undefined) return '—'
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function parseExactIds(value: string): string[] {
  return Array.from(new Set(value.split(/[\s,;]+/).map(item => item.trim()).filter(Boolean)))
}

function parseAssignees(value: string): string[] {
  return Array.from(new Set(value.split(/[\n,;]+/).map(item => item.trim()).filter(Boolean)))
}

const PAGE_SIZE = 100

function FilterSection({ title, icon, badge, defaultOpen = true, children }: {
  title: string
  icon: React.ReactNode
  badge?: string | number
  defaultOpen?: boolean
  children: React.ReactNode
}) {
  const [open, setOpen] = useState(defaultOpen)
  return <section className="border-b border-[#E5E5E5]">
    <button type="button" onClick={() => setOpen(current => !current)} className="w-full flex items-center gap-2 px-4 py-3 text-left hover:bg-[#FAFAFA] transition-colors">
      <span className="text-[#8C8C8C]">{icon}</span>
      <span className="flex-1 text-[10px] font-600 uppercase tracking-[0.65px] text-[#5C5C5C]">{title}</span>
      {badge !== undefined && badge !== 0 && badge !== '' && <span className="rounded-full bg-[#FFF0F0] px-2 py-0.5 text-[9px] font-600 text-[#CC0000]">{badge}</span>}
      <ChevronDown size={13} className={cn('text-[#8C8C8C] transition-transform', !open && '-rotate-90')} />
    </button>
    {open && <div className="px-4 pb-4 space-y-3">{children}</div>}
  </section>
}

function RawRecordDetails({ record, fields, labels, onClose }: {
  record: Record<string, unknown>
  fields: string[]
  labels: Map<string, string>
  onClose: () => void
}) {
  return <div className="fixed inset-0 z-[80] flex justify-end bg-black/25" onClick={onClose}>
    <motion.aside initial={{ x: 480 }} animate={{ x: 0 }} exit={{ x: 480 }} transition={{ duration: 0.18, ease: 'easeOut' }} onClick={event => event.stopPropagation()} className="h-full w-[480px] max-w-[94vw] bg-white border-l border-[#D0D0D0] shadow-[0_0_30px_rgba(0,0,0,0.18)] flex flex-col">
      <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-start gap-3">
        <div className="flex-1 min-w-0"><p className="text-[10px] uppercase tracking-[0.5px] text-[#8C8C8C]">Helix raw record</p><h2 className="text-[15px] font-700 text-[#1A1A1A] font-mono truncate">{displayValue(record.task_id ?? record.request_id ?? 'Record details')}</h2></div>
        <button onClick={onClose} className="p-1 text-[#8C8C8C] hover:text-[#1A1A1A] rounded"><X size={16} /></button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 grid grid-cols-1 sm:grid-cols-2 gap-x-5 gap-y-4 content-start">
        {fields.map(field => <div key={field} className={cn('min-w-0', field === 'summary' ? 'sm:col-span-2' : '')}>
          <div className="text-[10px] uppercase tracking-[0.5px] font-600 text-[#8C8C8C] mb-1">{labels.get(field) ?? field}</div>
          <div className="text-[12px] text-[#1A1A1A] break-words">{displayValue(record[field])}</div>
        </div>)}
      </div>
    </motion.aside>
  </div>
}

export default function RawReportsPage() {
  const range = useMemo(initialRange, [])
  const [start, setStart] = useState(range.start)
  const [end, setEnd] = useState(range.end)
  const [dateField, setDateField] = useState('')
  const [selectedFields, setSelectedFields] = useState<string[]>([])
  const [selectedDivisions, setSelectedDivisions] = useState<string[]>([])
  const [selectedGroups, setSelectedGroups] = useState<string[]>([])
  const [assigneesInput, setAssigneesInput] = useState('')
  const [selectedStatuses, setSelectedStatuses] = useState<string[]>([])
  const [calculateSla, setCalculateSla] = useState(false)
  const [includeClosed, setIncludeClosed] = useState(false)
  const [selectedCategories, setSelectedCategories] = useState<string[]>([])
  const [requestIdsInput, setRequestIdsInput] = useState('')
  const [taskIdsInput, setTaskIdsInput] = useState('')
  const [limit, setLimit] = useState('5000')
  const [validationError, setValidationError] = useState('')
  const [report, setReport] = useState<HelixRawReportResponse | null>(null)
  const [tableSearch, setTableSearch] = useState('')
  const [sortField, setSortField] = useState<string | null>(null)
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc')
  const [page, setPage] = useState(0)
  const [selectedRecord, setSelectedRecord] = useState<Record<string, unknown> | null>(null)

  const fieldsQuery = useQuery({
    queryKey: ['helix-raw-report-fields'],
    queryFn: helixRawReportsApi.fields,
    retry: false,
  })

  const filtersQuery = useQuery({
    queryKey: ['helix-raw-report-filters'],
    queryFn: helixRawReportsApi.filters,
    retry: false,
  })

  useEffect(() => {
    if (!fieldsQuery.data) return
    setDateField(current => current || fieldsQuery.data.default_date_field)
    setSelectedFields(current => current.length ? current : fieldsQuery.data.fields.map(field => field.name))
  }, [fieldsQuery.data])

  const generate = useMutation({
    mutationFn: helixRawReportsApi.generate,
    onSuccess: data => {
      setReport(data)
      setTableSearch('')
      setSortField(null)
      setPage(0)
      setSelectedRecord(null)
    },
  })

  const labels = useMemo(() => new Map(
    [...(fieldsQuery.data?.fields ?? []), ...(fieldsQuery.data?.sla_derived_fields ?? [])]
      .map(field => [field.name, field.helix_field]),
  ), [fieldsQuery.data])

  const slaFieldNames = useMemo(() => (
    fieldsQuery.data?.sla_derived_fields?.map(field => field.name)
      ?? ['report_category', 'sla_status', 'hours_open', 'sla_calculated_at']
  ), [fieldsQuery.data])

  const reportFields = useMemo(() => {
    if (!report) return []
    const fields = report.calculate_sla
      ? [...report.fields, ...slaFieldNames.filter(field => report.records.some(record => field in record))]
      : report.fields.filter(field => !slaFieldNames.includes(field))
    return Array.from(new Set(fields))
  }, [report, slaFieldNames])

  const availableGroups = useMemo(() => Array.from(new Set(
    filtersQuery.data?.divisions.flatMap(division => division.assignee_groups) ?? [],
  )).sort((a, b) => a.localeCompare(b)), [filtersQuery.data])

  const groupsIncludedByDivisions = useMemo(() => new Set(
    filtersQuery.data?.divisions
      .filter(division => selectedDivisions.includes(division.name))
      .flatMap(division => division.assignee_groups) ?? [],
  ), [filtersQuery.data, selectedDivisions])

  const visibleRecords = useMemo(() => {
    if (!report) return []
    const needle = tableSearch.trim().toLowerCase()
    const filtered = needle
      ? report.records.filter(record => reportFields.some(field => displayValue(record[field]).toLowerCase().includes(needle)))
      : [...report.records]
    if (!sortField) return filtered
    return filtered.sort((a, b) => {
      const left = displayValue(a[sortField]).toLowerCase()
      const right = displayValue(b[sortField]).toLowerCase()
      return left.localeCompare(right, undefined, { numeric: true }) * (sortDirection === 'asc' ? 1 : -1)
    })
  }, [report, reportFields, tableSearch, sortField, sortDirection])

  const pageCount = Math.max(1, Math.ceil(visibleRecords.length / PAGE_SIZE))
  const pageRecords = visibleRecords.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  useEffect(() => {
    if (page >= pageCount) setPage(pageCount - 1)
  }, [page, pageCount])

  function sortBy(field: string) {
    if (sortField === field) setSortDirection(current => current === 'asc' ? 'desc' : 'asc')
    else {
      setSortField(field)
      setSortDirection('asc')
    }
    setPage(0)
  }

  function toggleSelection(value: string, setter: React.Dispatch<React.SetStateAction<string[]>>) {
    setter(current => current.includes(value)
      ? current.filter(item => item !== value)
      : [...current, value])
  }

  function toggleField(name: string) {
    setSelectedFields(current => current.includes(name)
      ? current.filter(field => field !== name)
      : [...current, name])
  }

  function moveField(index: number, direction: -1 | 1) {
    setSelectedFields(current => {
      const target = index + direction
      if (target < 0 || target >= current.length) return current
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  function submit(event: React.FormEvent) {
    event.preventDefault()
    setValidationError('')
    const requestIds = parseExactIds(requestIdsInput)
    const taskIds = parseExactIds(taskIdsInput)
    if (!!start !== !!end) return setValidationError('Start and end must be supplied together.')
    if (start && end && new Date(end) < new Date(start)) return setValidationError('End must be on or after start.')
    if (!start && !requestIds.length && !taskIds.length) return setValidationError('Supply a date range, Request ID, or Task ID.')
    if (!selectedFields.length) return setValidationError('Select at least one field.')
    const parsedLimit = Number(limit)
    if (!Number.isInteger(parsedLimit) || parsedLimit < 1 || parsedLimit > 100000) {
      return setValidationError('Limit must be a whole number between 1 and 100000.')
    }
    const payload: HelixRawReportRequest = {
      start: start ? toOffsetIso(start) : undefined,
      end: end ? toOffsetIso(end) : undefined,
      date_field: dateField,
      fields: selectedFields,
      divisions: selectedDivisions.length ? selectedDivisions : undefined,
      assignee_groups: selectedGroups.filter(group => !groupsIncludedByDivisions.has(group)).length
        ? selectedGroups.filter(group => !groupsIncludedByDivisions.has(group))
        : undefined,
      assignees: parseAssignees(assigneesInput).length ? parseAssignees(assigneesInput) : undefined,
      statuses: selectedStatuses.length ? selectedStatuses : undefined,
      calculate_sla: calculateSla,
      include_closed: includeClosed,
      categories: selectedCategories.length ? selectedCategories : undefined,
      request_ids: requestIds.length ? requestIds : undefined,
      task_ids: taskIds.length ? taskIds : undefined,
      limit: parsedLimit,
    }
    generate.mutate(payload)
  }

  async function exportPdf() {
    if (!report) return
    const { default: jsPDF } = await import('jspdf')
    const { default: autoTable } = await import('jspdf-autotable')
    const document = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a3' })

    document.setFontSize(15)
    document.setTextColor(26, 26, 26)
    document.text('Helix Raw Report', 32, 30)
    document.setFontSize(8)
    document.setTextColor(92, 92, 92)
    document.text(`${report.count.toLocaleString('en-ZA')} records · ${report.source}${report.start && report.end ? ` · ${report.start} to ${report.end}` : ' · Exact ID lookup'}`, 32, 44)

    autoTable(document, {
      startY: 56,
      margin: { left: 24, right: 24 },
      head: [reportFields.map(field => labels.get(field) ?? field)],
      body: report.records.map(record => reportFields.map(field => record[field] == null ? '—' : displayValue(record[field]))),
      styles: { fontSize: reportFields.length > 12 ? 5 : 6.5, cellPadding: 3, overflow: 'linebreak' },
      headStyles: { fillColor: [230, 0, 0], textColor: 255, fontStyle: 'bold' },
      alternateRowStyles: { fillColor: [250, 250, 250] },
    })

    document.save(`helix-raw-report-${new Date().toISOString().slice(0, 10)}.pdf`)
  }

  async function exportExcel() {
    if (!report) return
    const ExcelJS = (await import('exceljs')).default
    const workbook = new ExcelJS.Workbook()
    const sheet = workbook.addWorksheet('Helix Raw Report')
    sheet.columns = reportFields.map(field => ({ header: labels.get(field) ?? field, key: field, width: 22 }))
    report.records.forEach(record => sheet.addRow(Object.fromEntries(reportFields.map(field => [field, record[field] ?? '']))))
    sheet.getRow(1).eachCell(cell => {
      cell.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFE60000' } }
      cell.font = { color: { argb: 'FFFFFFFF' }, bold: true }
    })
    sheet.views = [{ state: 'frozen', ySplit: 1 }]
    const buffer = await workbook.xlsx.writeBuffer()
    downloadBlob(new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `helix-raw-report-${new Date().toISOString().slice(0, 10)}.xlsx`)
  }

  function applyDatePreset(days?: number) {
    const presetEnd = new Date()
    const presetStart = days
      ? new Date(presetEnd.getTime() - days * 86_400_000)
      : new Date(presetEnd.getFullYear(), presetEnd.getMonth(), 1, 0, 0, 0)
    setStart(localInputValue(presetStart))
    setEnd(localInputValue(presetEnd))
    setRequestIdsInput('')
    setTaskIdsInput('')
    setValidationError('')
  }

  function applyIdLookupPreset() {
    setStart('')
    setEnd('')
    setSelectedDivisions([])
    setSelectedGroups([])
    setAssigneesInput('')
    setSelectedStatuses([])
    setIncludeClosed(false)
    setSelectedCategories([])
    setLimit('100')
    setValidationError('')
  }

  const requestError = generate.error instanceof Error ? generate.error.message : ''
  const fieldsError = fieldsQuery.error instanceof Error ? fieldsQuery.error.message : ''
  const filtersError = filtersQuery.error instanceof Error ? filtersQuery.error.message : ''

  const busy = fieldsQuery.isLoading || filtersQuery.isLoading || generate.isPending
  const errorMessage = validationError || fieldsError || filtersError || requestError

  return <div className="flex flex-col flex-1 min-h-0">
    <PageHeader breadcrumb={['Reports', 'Helix Raw Reports']} title="Helix Raw Report Builder" subtitle="Build and run a live, read-only query against Helix TMS:Task." />

    <div className="flex-1 min-h-0 p-4 lg:p-5">
      <div className="h-full min-h-[680px] bg-white border border-[#DCDCDC] rounded-xl overflow-hidden shadow-[0_2px_12px_rgba(0,0,0,0.04)] grid grid-cols-1 lg:grid-cols-[320px_minmax(0,1fr)] grid-rows-[auto_minmax(0,1fr)]">
        <header className="lg:col-span-2 flex items-center gap-2 px-4 py-2.5 bg-[#FAFAFA] border-b border-[#E5E5E5]">
          <div className="w-7 h-7 rounded-md bg-[#FFF0F0] text-[#E60000] flex items-center justify-center"><Database size={15} /></div>
          <div className="flex-1 min-w-0"><h2 className="text-[14px] font-600 text-[#1A1A1A]">Raw report workspace</h2><p className="text-[10px] text-[#8C8C8C]">Configure filters on the left and inspect results on the right</p></div>
          <Btn type="button" size="sm" onClick={exportPdf} disabled={!report?.records.length}><FileText size={11} /> PDF</Btn>
          <Btn type="button" size="sm" onClick={exportExcel} disabled={!report?.records.length}><FileSpreadsheet size={11} /> Excel</Btn>
          <Btn type="submit" form="raw-report-form" variant="primary" size="sm" loading={generate.isPending} disabled={fieldsQuery.isLoading || filtersQuery.isLoading || !!fieldsError || !!filtersError}><Play size={11} /> Generate report</Btn>
        </header>

        <aside className="min-h-0 overflow-y-auto border-r border-[#E5E5E5] bg-white">
          <form id="raw-report-form" onSubmit={submit}>
            <FilterSection title="Quick presets" icon={<Zap size={14} />}>
              <button type="button" onClick={() => applyDatePreset()} className="w-full flex items-center gap-2.5 p-2.5 rounded-md border border-[#E5E5E5] bg-[#FAFAFA] hover:border-[#F5B8B8] hover:bg-[#FFF8F8] text-left"><span className="w-7 h-7 rounded bg-[#FFF0F0] text-[#E60000] flex items-center justify-center"><CalendarDays size={13} /></span><span><span className="block text-[11px] font-600">Current month</span><span className="block text-[9px] text-[#8C8C8C]">Month start to now</span></span></button>
              <button type="button" onClick={() => applyDatePreset(7)} className="w-full flex items-center gap-2.5 p-2.5 rounded-md border border-[#E5E5E5] bg-[#FAFAFA] hover:border-[#F5B8B8] hover:bg-[#FFF8F8] text-left"><span className="w-7 h-7 rounded bg-[#FFF0F0] text-[#E60000] flex items-center justify-center"><Sparkles size={13} /></span><span><span className="block text-[11px] font-600">Last 7 days</span><span className="block text-[9px] text-[#8C8C8C]">Rolling seven-day range</span></span></button>
              <button type="button" onClick={applyIdLookupPreset} className="w-full flex items-center gap-2.5 p-2.5 rounded-md border border-[#E5E5E5] bg-[#FAFAFA] hover:border-[#F5B8B8] hover:bg-[#FFF8F8] text-left"><span className="w-7 h-7 rounded bg-[#EEF4FF] text-[#0057A8] flex items-center justify-center"><Hash size={13} /></span><span><span className="block text-[11px] font-600">Exact ID lookup</span><span className="block text-[9px] text-[#8C8C8C]">Clear dates and use a 100-row limit</span></span></button>
            </FilterSection>

            <FilterSection title="Date range" icon={<CalendarDays size={14} />} badge={start || end ? 'Set' : ''}>
              <label className="block text-[10px] text-[#8C8C8C]">Date field<select value={dateField} onChange={event => setDateField(event.target.value)} disabled={fieldsQuery.isLoading} className="mt-1 w-full bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[11px]">{fieldsQuery.data?.date_fields.map(field => <option key={field}>{field}</option>)}</select></label>
              <label className="block text-[10px] text-[#8C8C8C]">Start<input type="datetime-local" value={start} onChange={event => setStart(event.target.value)} className="mt-1 w-full bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[11px]" /></label>
              <label className="block text-[10px] text-[#8C8C8C]">End<input type="datetime-local" value={end} onChange={event => setEnd(event.target.value)} className="mt-1 w-full bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[11px]" /></label>
              {(start || end) && <button type="button" onClick={() => { setStart(''); setEnd('') }} className="inline-flex items-center gap-1 text-[10px] text-[#CC0000] hover:underline"><X size={10} /> Clear for exact ID lookup</button>}
            </FilterSection>

            <FilterSection title="Exact IDs" icon={<Hash size={14} />} badge={parseExactIds(requestIdsInput).length + parseExactIds(taskIdsInput).length} defaultOpen={false}>
              <label className="block text-[10px] text-[#8C8C8C]">Request IDs<textarea rows={2} value={requestIdsInput} onChange={event => setRequestIdsInput(event.target.value)} placeholder="CRQ000001, CRQ000002…" className="mt-1 w-full resize-none bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[10px] font-mono" /></label>
              <label className="block text-[10px] text-[#8C8C8C]">Task IDs<textarea rows={2} value={taskIdsInput} onChange={event => setTaskIdsInput(event.target.value)} placeholder="TAS000001, TAS000002…" className="mt-1 w-full resize-none bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[10px] font-mono" /></label>
              <p className="text-[9px] text-[#8C8C8C]">Separate exact IDs with commas, spaces, or new lines.</p>
            </FilterSection>

            <FilterSection title="Divisions" icon={<Layers3 size={14} />} badge={selectedDivisions.length}>
              <div className="max-h-36 overflow-y-auto space-y-0.5">
                {filtersQuery.isLoading && <p className="text-[10px] text-[#8C8C8C]">Loading divisions…</p>}
                {filtersQuery.data?.divisions.map(division => <label key={division.name} className="flex items-center gap-2 px-1.5 py-1.5 rounded hover:bg-[#FAFAFA] cursor-pointer"><input type="checkbox" checked={selectedDivisions.includes(division.name)} onChange={() => toggleSelection(division.name, setSelectedDivisions)} className="accent-[#E60000]" /><span className="flex-1 truncate text-[11px]">{division.name}</span><span className="text-[9px] text-[#0A7A0A] bg-[#EDF7ED] rounded-full px-1.5 py-0.5">{division.assignee_groups.length} groups</span></label>)}
              </div>
              <p className="text-[9px] text-[#8C8C8C]">Leave empty to include all configured groups.</p>
            </FilterSection>

            <FilterSection title="Assignee groups" icon={<SlidersHorizontal size={14} />} badge={new Set([...selectedGroups, ...groupsIncludedByDivisions]).size} defaultOpen={false}>
              <div className="max-h-44 overflow-y-auto space-y-0.5">
                {availableGroups.map(group => { const inherited = groupsIncludedByDivisions.has(group); return <label key={group} className={cn('flex items-center gap-2 px-1.5 py-1.5 rounded', inherited ? 'cursor-default' : 'hover:bg-[#FAFAFA] cursor-pointer')}><input type="checkbox" checked={inherited || selectedGroups.includes(group)} disabled={inherited} onChange={() => toggleSelection(group, setSelectedGroups)} className="accent-[#E60000]" /><span className="flex-1 truncate text-[10px]" title={group}>{group}</span>{inherited && <span className="text-[8px] text-[#0A7A0A]">Division</span>}</label>})}
              </div>
              {selectedGroups.length > 0 && <button type="button" onClick={() => setSelectedGroups([])} className="text-[10px] text-[#CC0000] hover:underline">Clear additional groups</button>}
            </FilterSection>

            <FilterSection title="Assigned to" icon={<UserRound size={14} />} badge={parseAssignees(assigneesInput).length} defaultOpen={false}>
              <label className="block text-[10px] text-[#8C8C8C]">Exact assignee names<textarea rows={3} value={assigneesInput} onChange={event => setAssigneesInput(event.target.value)} placeholder={'Jane Doe\nJohn Smith'} className="mt-1 w-full resize-none bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[10px]" /></label>
              <p className="text-[9px] text-[#8C8C8C]">Separate names with commas or new lines. Names must exactly match Helix.</p>
            </FilterSection>

            <FilterSection title="Status and category" icon={<Filter size={14} />} badge={selectedStatuses.length + selectedCategories.length}>
              <div><div className="flex justify-between"><p className="text-[10px] text-[#8C8C8C]">Statuses</p>{selectedStatuses.length > 0 && <button type="button" onClick={() => setSelectedStatuses([])} className="text-[9px] text-[#CC0000]">Clear</button>}</div><div className="mt-1 grid grid-cols-1 gap-0.5">{fieldsQuery.data?.common_statuses.map(status => <label key={status} className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-[#FAFAFA] cursor-pointer"><input type="checkbox" checked={selectedStatuses.includes(status)} onChange={() => toggleSelection(status, setSelectedStatuses)} className="accent-[#E60000]" /><span className="text-[10px]">{status}</span></label>)}</div></div>
              <p className="text-[9px] text-[#8C8C8C]">{selectedStatuses.length ? 'Only selected statuses will be returned.' : 'No statuses selected: every status, including closed tasks, will be returned.'}</p>
              <label className="flex items-start gap-2 rounded-md border border-[#E5E5E5] bg-[#FAFAFA] p-2 cursor-pointer"><input type="checkbox" checked={includeClosed} onChange={event => setIncludeClosed(event.target.checked)} className="mt-0.5 accent-[#E60000]" /><span><span className="block text-[10px] font-600">Include closed tasks</span><span className="block text-[9px] text-[#8C8C8C]">{selectedStatuses.length ? `Also include ${(fieldsQuery.data?.closed_statuses ?? ['Closed', 'Cancelled', 'Success', 'Bypassed']).join(', ')}.` : 'All statuses are already included when no status filter is selected.'}</span></span></label>
              <div><div className="flex justify-between"><p className="text-[10px] text-[#8C8C8C]">Operational categories</p>{selectedCategories.length > 0 && <button type="button" onClick={() => setSelectedCategories([])} className="text-[9px] text-[#CC0000]">Clear</button>}</div><div className="mt-1 grid grid-cols-2 gap-0.5">{fieldsQuery.data?.derived_categories.map(category => <label key={category} className="flex items-center gap-2 px-1.5 py-1 rounded hover:bg-[#FAFAFA] cursor-pointer"><input type="checkbox" checked={selectedCategories.includes(category)} onChange={() => toggleSelection(category, setSelectedCategories)} className="accent-[#E60000]" /><span className="text-[10px] truncate">{category}</span></label>)}</div></div>
            </FilterSection>

            <FilterSection title="SLA calculation" icon={<Gauge size={14} />} badge={calculateSla ? 'On' : ''}>
              <label className="flex items-start gap-2 rounded-md border border-[#E5E5E5] bg-[#FAFAFA] p-2 cursor-pointer"><input type="checkbox" checked={calculateSla} onChange={event => setCalculateSla(event.target.checked)} className="mt-0.5 accent-[#E60000]" /><span><span className="block text-[10px] font-600">Calculate SLA</span><span className="block text-[9px] text-[#8C8C8C]">Add SLA category, status, hours open, and calculation time to every record.</span></span></label>
            </FilterSection>

            <FilterSection title="Fields" icon={<Columns3 size={14} />} badge={selectedFields.length} defaultOpen={false}>
              <div className="flex justify-between items-center"><p className="text-[9px] text-[#8C8C8C]">Order controls table and exports</p><div className="flex gap-2"><button type="button" onClick={() => setSelectedFields(fieldsQuery.data?.fields.map(field => field.name) ?? [])} className="text-[9px] text-[#CC0000]">All</button><button type="button" onClick={() => setSelectedFields([])} className="text-[9px] text-[#8C8C8C]">Clear</button></div></div>
              <div className="max-h-52 overflow-y-auto space-y-1">{fieldsQuery.data?.fields.map(field => { const index = selectedFields.indexOf(field.name); return <div key={field.name} className={cn('flex items-center gap-1.5 px-2 py-1.5 rounded-md border', index >= 0 ? 'bg-[#FFF8F8] border-[#F5B8B8]' : 'bg-[#FAFAFA] border-transparent')}><input type="checkbox" checked={index >= 0} onChange={() => toggleField(field.name)} className="accent-[#E60000]" /><button type="button" onClick={() => toggleField(field.name)} className={cn('flex-1 text-left text-[10px] truncate', index >= 0 ? 'text-[#CC0000]' : 'text-[#8C8C8C]')} title={field.helix_field}>{field.helix_field}</button>{index >= 0 && <><span className="text-[9px] text-[#8C8C8C]">{index + 1}</span><button type="button" disabled={index === 0} onClick={() => moveField(index, -1)} className="disabled:opacity-20"><ArrowUp size={10} /></button><button type="button" disabled={index === selectedFields.length - 1} onClick={() => moveField(index, 1)} className="disabled:opacity-20"><ArrowDown size={10} /></button></>}</div>})}</div>
            </FilterSection>

            <FilterSection title="Record limit" icon={<Gauge size={14} />} badge={limit} defaultOpen={false}>
              <label className="block text-[10px] text-[#8C8C8C]">Maximum records (1–100,000)<input type="number" min={1} max={100000} step={1} value={limit} onChange={event => setLimit(event.target.value)} className="mt-1 w-full bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2 py-1.5 text-[11px]" /></label>
            </FilterSection>

            <div className="sticky bottom-0 bg-white border-t border-[#E5E5E5] p-3 space-y-2">
              {errorMessage && <div role="alert" className="flex gap-1.5 bg-[#FFF0F0] border border-[#F5B8B8] rounded-md px-2.5 py-2 text-[10px] text-[#CC0000]"><AlertTriangle size={12} className="shrink-0 mt-0.5" />{errorMessage}</div>}
              <Btn type="submit" variant="primary" loading={generate.isPending} disabled={fieldsQuery.isLoading || filtersQuery.isLoading || !!fieldsError || !!filtersError} className="w-full justify-center"><Play size={12} /> Generate report</Btn>
            </div>
          </form>
        </aside>

        <main className="min-w-0 min-h-0 flex flex-col bg-[#FAFAFA]">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-[#E5E5E5] bg-white">
            <div className="flex-1 min-w-0"><p className="text-[11px] text-[#5C5C5C] truncate">{report ? `${report.count.toLocaleString('en-ZA')} records · ${report.source}${report.start && report.end ? ` · ${new Date(report.start).toLocaleDateString('en-ZA')} to ${new Date(report.end).toLocaleDateString('en-ZA')}` : ' · Exact ID lookup'}` : busy ? 'Preparing raw report workspace…' : 'Generate a report to see live Helix results.'}</p></div>
            {report && <div className="flex items-center gap-1.5 bg-[#FAFAFA] border border-[#D0D0D0] rounded-md px-2.5 py-1.5 w-[220px]"><Search size={12} className="text-[#8C8C8C]" /><input value={tableSearch} onChange={event => { setTableSearch(event.target.value); setPage(0) }} placeholder="Search results…" className="bg-transparent outline-none text-[11px] w-full" />{tableSearch && <button type="button" onClick={() => { setTableSearch(''); setPage(0) }}><X size={11} /></button>}</div>}
            <span className="hidden xl:inline text-[9px] text-[#8C8C8C]">Click any row to inspect</span>
          </div>

          {report?.limit_reached && <div className="flex items-center gap-2 px-4 py-2 bg-[#FFF8E6] border-b border-[#F5D580] text-[10px] text-[#8A5200]"><AlertTriangle size={12} />The report reached the selected record limit. Reduce the date range or increase the limit.</div>}

          {report && <div className="px-4 py-2 bg-white border-b border-[#E5E5E5] flex items-center gap-2 overflow-x-auto whitespace-nowrap text-[9px] text-[#8C8C8C]"><span className="rounded-full bg-[#F5F5F5] px-2 py-1">{report.divisions.length ? report.divisions.join(', ') : 'All divisions'}</span><span className="rounded-full bg-[#F5F5F5] px-2 py-1">{report.assignee_groups.length ? `${report.assignee_groups.length} groups` : 'All groups'}</span><span className="rounded-full bg-[#F5F5F5] px-2 py-1">{report.assignees?.length ? report.assignees.join(', ') : 'All assignees'}</span><span className="rounded-full bg-[#F5F5F5] px-2 py-1">{report.all_statuses || !report.statuses.length ? 'All statuses' : report.statuses.join(', ')}</span>{report.include_closed && !report.all_statuses && <span className="rounded-full bg-[#EEF4FF] text-[#0057A8] px-2 py-1">Closed included</span>}<span className="rounded-full bg-[#F5F5F5] px-2 py-1">{report.categories.length ? report.categories.join(', ') : 'All categories'}</span>{report.calculate_sla && <span className="rounded-full bg-[#EDF7ED] text-[#0A7A0A] px-2 py-1">SLA calculated</span>}{(report.request_ids.length > 0 || report.task_ids.length > 0) && <span className="rounded-full bg-[#EEF4FF] text-[#0057A8] px-2 py-1">{report.request_ids.length + report.task_ids.length} exact IDs</span>}<span className="ml-auto">{visibleRecords.length.toLocaleString('en-ZA')} shown</span></div>}

          <div id="raw-report-table-scroll" className="flex-1 min-h-0 overflow-auto bg-white">
            {generate.isPending ? <table className="w-full"><TableSkeleton rows={12} cols={Math.min(selectedFields.length || 5, 10)} /></table> : report ? <table className="min-w-full w-max text-left whitespace-nowrap border-collapse"><thead><tr>{reportFields.map(field => <th key={field} className="sticky top-0 z-10 bg-white border-b border-[#D0D0D0] px-3 py-2"><button type="button" onClick={() => sortBy(field)} className={cn('flex items-center gap-1 text-[9px] font-600 uppercase tracking-[0.4px]', sortField === field ? 'text-[#E60000]' : 'text-[#8C8C8C] hover:text-[#1A1A1A]')}>{labels.get(field) ?? field}{sortField === field ? sortDirection === 'asc' ? <ChevronUp size={10} /> : <ChevronDown size={10} /> : null}</button></th>)}<th className="sticky top-0 z-10 bg-white border-b border-[#D0D0D0] w-9" /></tr></thead><tbody>{pageRecords.length ? pageRecords.map((record, rowIndex) => <motion.tr key={`${page}-${rowIndex}`} initial={{ opacity: 0 }} animate={{ opacity: 1 }} onClick={() => setSelectedRecord(record)} className="border-b border-[#F0F0F0] hover:bg-[#FAFAFA] cursor-pointer">{reportFields.map(field => <td key={field} className={cn('px-3 py-2 text-[10px] text-[#5C5C5C] max-w-[240px] truncate', (field === 'request_id' || field === 'task_id') && 'font-mono text-[#0057A8]', field === 'sla_status' && record[field] === 'BREACHED' && 'font-600 text-[#CC0000]', field === 'sla_status' && record[field] === 'NEARING_SLA' && 'font-600 text-[#8A5200]')} title={displayValue(record[field])}>{displayValue(record[field])}</td>)}<td className="px-2 py-2 text-right"><Eye size={12} className="text-[#8C8C8C]" /></td></motion.tr>) : <tr><td colSpan={reportFields.length + 1}><EmptyState title="No records found" sub={tableSearch ? 'Try a different search term.' : 'The generated report returned no records.'} icon={<Search size={28} />} /></td></tr>}</tbody></table> : <div className="h-full min-h-[420px] flex items-center justify-center"><EmptyState icon={<Database size={34} />} title="No report generated yet" sub="Choose a date range or exact IDs on the left, then generate the report." /></div>}
          </div>

          {report && <footer className="flex items-center gap-2 px-4 py-2 border-t border-[#E5E5E5] bg-white"><span className="flex-1 text-[10px] text-[#8C8C8C]">{visibleRecords.length ? `Showing ${page * PAGE_SIZE + 1}–${Math.min((page + 1) * PAGE_SIZE, visibleRecords.length)} of ${visibleRecords.length.toLocaleString('en-ZA')}` : 'No matching records'}</span><button type="button" onClick={() => document.getElementById('raw-report-table-scroll')?.scrollBy({ left: -420, behavior: 'smooth' })} className="p-1.5 text-[#8C8C8C] hover:text-[#1A1A1A]"><ChevronLeft size={13} /></button><button type="button" onClick={() => document.getElementById('raw-report-table-scroll')?.scrollBy({ left: 420, behavior: 'smooth' })} className="p-1.5 text-[#8C8C8C] hover:text-[#1A1A1A]"><ChevronRight size={13} /></button><Btn type="button" size="sm" disabled={page === 0} onClick={() => setPage(current => Math.max(0, current - 1))}>Prev</Btn><span className="text-[10px] text-[#5C5C5C]">Page {page + 1} of {pageCount}</span><Btn type="button" size="sm" disabled={page >= pageCount - 1} onClick={() => setPage(current => Math.min(pageCount - 1, current + 1))}>Next</Btn></footer>}
        </main>
      </div>
    </div>

    {selectedRecord && report && <RawRecordDetails record={selectedRecord} fields={reportFields} labels={labels} onClose={() => setSelectedRecord(null)} />}
  </div>
}
