'use client'

import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { workspaceApi, divisionsApi } from '@/lib/api'
import { cn, DIVISION_COLORS } from '@/lib/utils'
import { PageHeader, EmptyState, Btn } from '@/components/ui'
import type { SummaryRow, SlaStatus, Category } from '@/types'
import { useState } from 'react'
import {
  RefreshCw, AlertTriangle, Clock, Info, CheckCircle2,
  ChevronDown, ChevronRight,
} from 'lucide-react'

// ─── Constants ────────────────────────────────────────────────────────────────

const SLA_ORDER: SlaStatus[] = ['BREACHED', 'NEARING_SLA', 'NO_SCHEDULE', 'WITHIN_SLA']
const CATEGORIES: Category[] = ['INCIDENT', 'CHANGE', 'ACCESS', 'EVENT']
const KNOWN_SLA_STATUSES = new Set<SlaStatus>([...SLA_ORDER, 'CLOSED'])
const KNOWN_CATEGORIES = new Set<Category>(CATEGORIES)

const SLA_META: Record<SlaStatus, {
  label: string
  icon: React.ReactNode
  rowBg: string
  textColor: string
  dotColor: string
  pillBg: string
  pillBorder: string
}> = {
  BREACHED:    {
    label: 'Breached',
    icon: <AlertTriangle size={11} />,
    rowBg: 'bg-[#FFF8F8]',
    textColor: 'text-[#CC0000]',
    dotColor: 'bg-[#E60000]',
    pillBg: 'bg-[#FFF0F0]',
    pillBorder: 'border-[#F5B8B8]',
  },
  NEARING_SLA: {
    label: 'Nearing SLA',
    icon: <Clock size={11} />,
    rowBg: 'bg-[#FFFCF0]',
    textColor: 'text-[#C47000]',
    dotColor: 'bg-[#F59E0B]',
    pillBg: 'bg-[#FFF8E6]',
    pillBorder: 'border-[#F5D580]',
  },
  NO_SCHEDULE: {
    label: 'No Schedule',
    icon: <Info size={11} />,
    rowBg: 'bg-[#F8FAFF]',
    textColor: 'text-[#0057A8]',
    dotColor: 'bg-[#3B82F6]',
    pillBg: 'bg-[#EEF4FF]',
    pillBorder: 'border-[#B8CEFF]',
  },
  WITHIN_SLA:  {
    label: 'Within SLA',
    icon: <CheckCircle2 size={11} />,
    rowBg: '',
    textColor: 'text-[#0A7A0A]',
    dotColor: 'bg-[#16A34A]',
    pillBg: 'bg-[#EDF7ED]',
    pillBorder: 'border-[#B8DFB8]',
  },
  CLOSED: {
    label: 'Closed',
    icon: null,
    rowBg: '',
    textColor: 'text-[#8C8C8C]',
    dotColor: 'bg-[#D0D0D0]',
    pillBg: 'bg-[#F5F5F5]',
    pillBorder: 'border-[#E5E5E5]',
  },
}

// ─── Data shape ───────────────────────────────────────────────────────────────

interface DivisionData {
  division: string
  groups: GroupData[]
  totals: Record<SlaStatus, Record<Category, number>>
  grandTotal: number
  breachedTotal: number
}

interface GroupData {
  assigneeGroup: string
  shortLabel: string
  byStatus: Record<SlaStatus, Record<Category, number>>
  rowTotal: number
}

function shortLabel(raw: string): string {
  return raw
    .replace('Appl:', '')
    .replace(':OSS', '')
    .replace(' Operational Support', '')
    .trim()
}

function emptyByCat(): Record<Category, number> {
  return { INCIDENT: 0, CHANGE: 0, ACCESS: 0, EVENT: 0 }
}

function emptyByStatus(): Record<SlaStatus, Record<Category, number>> {
  return {
    BREACHED:    emptyByCat(),
    NEARING_SLA: emptyByCat(),
    NO_SCHEDULE: emptyByCat(),
    WITHIN_SLA:  emptyByCat(),
    CLOSED:      emptyByCat(),
  }
}

function isSlaStatus(value: unknown): value is SlaStatus {
  return typeof value === 'string' && KNOWN_SLA_STATUSES.has(value as SlaStatus)
}

function isCategory(value: unknown): value is Category {
  return typeof value === 'string' && KNOWN_CATEGORIES.has(value as Category)
}

function buildDivisions(rows: SummaryRow[]): DivisionData[] {
  const divMap = new Map<string, Map<string, Record<SlaStatus, Record<Category, number>>>>()

  rows.forEach(r => {
    const div = r.division ?? 'Unknown'
    const grp = r.assignee_group ?? 'Unknown'
    const sla = r.sla_status
    const cat = r.report_category
    if (!isCategory(cat) || !isSlaStatus(sla)) return

    if (!divMap.has(div)) divMap.set(div, new Map())
    const grpMap = divMap.get(div)!
    if (!grpMap.has(grp)) grpMap.set(grp, emptyByStatus())
    grpMap.get(grp)![sla][cat] += Number.isFinite(r.record_count) ? r.record_count : 0
  })

  return Array.from(divMap.entries()).map(([division, grpMap]) => {
    const groups: GroupData[] = Array.from(grpMap.entries()).map(([grp, byStatus]) => {
      const rowTotal = Object.values(byStatus).reduce(
        (s, cats) => s + Object.values(cats).reduce((a, b) => a + b, 0), 0,
      )
      return { assigneeGroup: grp, shortLabel: shortLabel(grp), byStatus, rowTotal }
    }).sort((a, b) => {
      // Sort groups: breached first, then by total
      const aB = Object.values(a.byStatus.BREACHED).reduce((s, v) => s + v, 0)
      const bB = Object.values(b.byStatus.BREACHED).reduce((s, v) => s + v, 0)
      return bB - aB || b.rowTotal - a.rowTotal
    })

    const totals = emptyByStatus()
    groups.forEach(g => {
      SLA_ORDER.forEach(sla => {
        CATEGORIES.forEach(cat => {
          totals[sla][cat] += g.byStatus[sla][cat]
        })
      })
    })

    const breachedTotal = CATEGORIES.reduce((s, c) => s + totals.BREACHED[c], 0)
    const grandTotal = SLA_ORDER.reduce(
      (s, sla) => s + CATEGORIES.reduce((a, c) => a + totals[sla][c], 0), 0,
    )

    return { division, groups, totals, grandTotal, breachedTotal }
  }).sort((a, b) => b.breachedTotal - a.breachedTotal)
}

// ─── Count cell ───────────────────────────────────────────────────────────────

function CountCell({ value, sla, bold }: { value: number; sla: SlaStatus; bold?: boolean }) {
  if (!value) return <span className="text-[#D0D0D0]">—</span>
  return (
    <span className={cn(
      SLA_META[sla].textColor,
      bold ? 'font-700' : 'font-500',
    )}>
      {value}
    </span>
  )
}

// ─── SLA pill ─────────────────────────────────────────────────────────────────

function SlaPill({ sla, count }: { sla: SlaStatus; count: number }) {
  const m = SLA_META[sla]
  return (
    <span className={cn(
      'inline-flex items-center gap-1 px-2 py-[3px] rounded text-[10px] font-600 border whitespace-nowrap',
      m.pillBg, m.pillBorder, m.textColor,
    )}>
      {m.icon}
      {m.label}
      {count > 0 && <span className="ml-0.5 opacity-80">({count})</span>}
    </span>
  )
}

// ─── Division section ─────────────────────────────────────────────────────────

function DivisionSection({
  data,
  defaultOpen,
  activeSlaFilters,
}: {
  data: DivisionData
  defaultOpen: boolean
  activeSlaFilters: Set<SlaStatus>
}) {
  const [open, setOpen] = useState(defaultOpen)
  const color = DIVISION_COLORS[data.division] ?? '#5C5C5C'

  const visibleSlas = SLA_ORDER.filter(sla =>
    activeSlaFilters.size === 0 || activeSlaFilters.has(sla),
  ).filter(sla =>
    CATEGORIES.some(c => data.groups.some(g => g.byStatus[sla][c] > 0)),
  )

  return (
    <div className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden">

      {/* Division header row — always visible */}
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 bg-[#FAFAFA] border-b border-[#E5E5E5] hover:bg-[#F5F5F5] transition-colors text-left"
      >
        {/* Expand/collapse */}
        <span className="text-[#8C8C8C] flex-shrink-0">
          {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        </span>

        {/* Division dot + name */}
        <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: color }} />
        <span className="font-700 text-[13px] text-[#1A1A1A] min-w-[48px]">
          {data.division}
        </span>
        <span className="text-[11px] text-[#8C8C8C]">
          {data.groups.length} group{data.groups.length !== 1 ? 's' : ''}
        </span>

        {/* SLA summary pills */}
        <div className="flex items-center gap-1.5 ml-3 flex-wrap">
          {data.breachedTotal > 0 && (
            <SlaPill sla="BREACHED" count={data.breachedTotal} />
          )}
          {(() => {
            const n = CATEGORIES.reduce((s, c) => s + data.totals.NEARING_SLA[c], 0)
            return n > 0 ? <SlaPill sla="NEARING_SLA" count={n} /> : null
          })()}
          {(() => {
            const n = CATEGORIES.reduce((s, c) => s + data.totals.NO_SCHEDULE[c], 0)
            return n > 0 ? <SlaPill sla="NO_SCHEDULE" count={n} /> : null
          })()}
        </div>

        <span className="ml-auto text-[12px] font-600 text-[#1A1A1A]">
          {data.grandTotal} total
        </span>
      </button>

      {/* Expandable table */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.18, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <table className="w-full border-collapse">
              <thead>
                <tr>
                  <th className="text-left text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-4 bg-white border-b border-[#F0F0F0] w-[200px] sticky left-0">
                    Assignee Group
                  </th>
                  <th className="text-left text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-4 bg-white border-b border-[#F0F0F0] w-[130px]">
                    SLA Status
                  </th>
                  {CATEGORIES.map(c => (
                    <th key={c} className="text-right text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-4 bg-white border-b border-[#F0F0F0] w-[80px]">
                      {c}
                    </th>
                  ))}
                  <th className="text-right text-[10px] font-600 text-[#1A1A1A] uppercase tracking-[0.5px] py-2 px-4 bg-white border-b border-[#F0F0F0] w-[70px]">
                    Total
                  </th>
                </tr>
              </thead>
              <tbody>
                {data.groups.map((grp, gi) => {
                  const slasWithData = visibleSlas.filter(sla =>
                    CATEGORIES.some(c => grp.byStatus[sla][c] > 0),
                  )
                  if (!slasWithData.length) return null

                  return slasWithData.map((sla, si) => {
                    const meta = SLA_META[sla]
                    const rowTotal = CATEGORIES.reduce((s, c) => s + grp.byStatus[sla][c], 0)
                    const isFirst = si === 0
                    const isLastSla = si === slasWithData.length - 1
                    const isLastGroup = gi === data.groups.length - 1

                    return (
                      <tr
                        key={`${grp.assigneeGroup}-${sla}`}
                        className={cn(
                          'transition-colors hover:brightness-[0.97]',
                          meta.rowBg,
                          !isLastSla ? 'border-b border-[#F5F5F5]' : '',
                          isLastSla && !isLastGroup ? 'border-b-2 border-[#E5E5E5]' : '',
                          isLastSla && isLastGroup ? 'border-b border-[#F0F0F0]' : '',
                        )}
                      >
                        {/* Group label — spans all SLA rows for this group */}
                        {isFirst && (
                          <td
                            rowSpan={slasWithData.length}
                            className="px-4 py-2 text-[11px] font-500 text-[#1A1A1A] align-middle border-r border-[#F0F0F0] bg-white sticky left-0"
                            title={grp.assigneeGroup}
                          >
                            {grp.shortLabel}
                          </td>
                        )}

                        {/* SLA status pill */}
                        <td className="px-4 py-1.5">
                          <span className={cn(
                            'inline-flex items-center gap-1 text-[10px] font-600',
                            meta.textColor,
                          )}>
                            {meta.icon}
                            {meta.label}
                          </span>
                        </td>

                        {/* Category counts */}
                        {CATEGORIES.map(cat => (
                          <td key={cat} className="px-4 py-1.5 text-right text-[12px]">
                            <CountCell value={grp.byStatus[sla][cat]} sla={sla} />
                          </td>
                        ))}

                        {/* Row total */}
                        <td className={cn(
                          'px-4 py-1.5 text-right text-[12px] font-700 border-l border-[#F0F0F0]',
                          meta.textColor,
                        )}>
                          {rowTotal || <span className="text-[#D0D0D0]">—</span>}
                        </td>
                      </tr>
                    )
                  })
                })}

                {/* Division subtotal */}
                <tr className="bg-[#FAFAFA] border-t-2 border-[#E5E5E5]">
                  <td colSpan={2} className="px-4 py-2 text-[10px] font-700 text-[#5C5C5C] uppercase tracking-[0.4px]">
                    {data.division} — Total Open
                  </td>
                  {CATEGORIES.map(cat => {
                    const total = visibleSlas.reduce((s, sla) => s + data.totals[sla][cat], 0)
                    return (
                      <td key={cat} className="px-4 py-2 text-right text-[12px] font-700 text-[#1A1A1A]">
                        {total || <span className="text-[#D0D0D0]">—</span>}
                      </td>
                    )
                  })}
                  <td className="px-4 py-2 text-right text-[13px] font-700 text-[#1A1A1A] border-l border-[#E5E5E5]">
                    {visibleSlas.reduce(
                      (s, sla) => s + CATEGORIES.reduce((a, c) => a + data.totals[sla][c], 0), 0,
                    )}
                  </td>
                </tr>
              </tbody>
            </table>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function SlaMonitorPage() {
  const [activeSlaFilters, setActiveSlaFilters] = useState<Set<SlaStatus>>(new Set())
  const [activeDivFilters, setActiveDivFilters] = useState<Set<string>>(new Set())

  const { data, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['workspace-summary-sla'],
    queryFn: () => workspaceApi.summary(),
    refetchInterval: 60_000,
  })

  const { data: divData } = useQuery({
    queryKey: ['divisions'],
    queryFn: divisionsApi.list,
  })

  function toggleSla(sla: SlaStatus) {
    setActiveSlaFilters(prev => {
      const next = new Set(prev)
      if (next.has(sla)) {
        next.delete(sla)
      } else {
        next.add(sla)
      }
      return next
    })
  }

  function toggleDiv(div: string) {
    setActiveDivFilters(prev => {
      const next = new Set(prev)
      if (next.has(div)) {
        next.delete(div)
      } else {
        next.add(div)
      }
      return next
    })
  }

  const allDivisions = buildDivisions(data?.rows ?? [])

  const visibleDivisions = allDivisions.filter(d =>
    activeDivFilters.size === 0 || activeDivFilters.has(d.division),
  )

  const totalBreached = allDivisions.reduce((s, d) => s + d.breachedTotal, 0)
  const totalActive   = allDivisions.reduce((s, d) => s + d.grandTotal, 0)

  const hasFilters = activeSlaFilters.size > 0 || activeDivFilters.size > 0

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <PageHeader
        breadcrumb={['Operations Console', 'SLA Monitor']}
        title="SLA Monitor"
        subtitle="Real-time SLA status by division and assignee group"
        actions={
          <>
            {hasFilters && (
              <Btn
                variant="ghost" size="sm"
                onClick={() => { setActiveSlaFilters(new Set()); setActiveDivFilters(new Set()) }}
              >
                Clear filters
              </Btn>
            )}
            <span className="text-[11px] text-[#8C8C8C]">
              {dataUpdatedAt ? `Updated ${new Date(dataUpdatedAt).toLocaleTimeString('en-ZA')}` : ''}
            </span>
            <Btn variant="default" size="sm" onClick={() => refetch()}>
              <RefreshCw size={11} /> Refresh
            </Btn>
          </>
        }
      />

      {/* ── Breach alert strip ── */}
      <AnimatePresence>
        {totalBreached > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="bg-[#FFF0F0] border-b border-[#F5B8B8] px-5 py-2 flex items-center gap-2 flex-shrink-0"
          >
            <AlertTriangle size={13} className="text-[#CC0000]" />
            <span className="text-[12px] font-600 text-[#CC0000]">
              {totalBreached} breached
            </span>
            <span className="text-[12px] text-[#8C8C8C]">across all divisions — immediate attention required</span>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Filter bar ── */}
      <div className="bg-white border-b border-[#E5E5E5] px-4 py-2.5 flex items-center gap-4 flex-shrink-0 flex-wrap">

        {/* Global stats */}
        <div className="flex items-center gap-3 text-[11px] border-r border-[#E5E5E5] pr-4">
          <span className="text-[#8C8C8C]">{totalActive} active</span>
          <span className="font-600 text-[#CC0000]">{totalBreached} breached</span>
        </div>

        {/* SLA multi-select */}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide mr-1">SLA</span>
          {SLA_ORDER.map(sla => {
            const m = SLA_META[sla]
            const active = activeSlaFilters.has(sla)
            return (
              <button
                key={sla}
                onClick={() => toggleSla(sla)}
                className={cn(
                  'inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-500 border transition-all',
                  active
                    ? cn(m.pillBg, m.pillBorder, m.textColor)
                    : 'bg-white border-[#E5E5E5] text-[#5C5C5C] hover:border-[#D0D0D0] hover:text-[#1A1A1A]',
                )}
              >
                <span className={cn('w-1.5 h-1.5 rounded-full flex-shrink-0', active ? m.dotColor : 'bg-[#D0D0D0]')} />
                {m.label}
              </button>
            )
          })}
        </div>

        <div className="w-px h-4 bg-[#E5E5E5]" />

        {/* Division multi-select */}
        <div className="flex items-center gap-1.5">
          <span className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide mr-1">Division</span>
          {(divData?.divisions ?? []).map(d => {
            const active = activeDivFilters.has(d.division)
            const color = DIVISION_COLORS[d.division] ?? '#5C5C5C'
            return (
              <button
                key={d.division}
                onClick={() => toggleDiv(d.division)}
                className={cn(
                  'px-2.5 py-1 rounded-full text-[11px] font-500 border transition-all',
                  active
                    ? 'text-white border-transparent'
                    : 'bg-white border-[#E5E5E5] text-[#5C5C5C] hover:border-[#D0D0D0]',
                )}
                style={active ? { background: color, borderColor: color } : {}}
              >
                {d.division}
                {active && (
                  <span className="ml-1 opacity-70">✕</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      {/* ── Column header legend ── */}
      <div className="bg-[#FAFAFA] border-b border-[#E5E5E5] px-4 py-1.5 flex items-center flex-shrink-0">
        <div className="w-[200px] text-[10px] text-[#8C8C8C]">Group</div>
        <div className="w-[130px] text-[10px] text-[#8C8C8C]">SLA Status</div>
        <div className="flex gap-0 ml-auto">
          {CATEGORIES.map(c => (
            <div key={c} className="w-[80px] text-[10px] font-600 text-[#8C8C8C] text-right uppercase tracking-[0.5px]">
              {c}
            </div>
          ))}
          <div className="w-[70px] text-[10px] font-600 text-[#1A1A1A] text-right uppercase tracking-[0.5px] pl-4 border-l border-[#E5E5E5] ml-4">
            Total
          </div>
        </div>
      </div>

      {/* ── Division sections ── */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {isLoading ? (
          <div className="space-y-2">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-16 skeleton rounded-lg" />
            ))}
          </div>
        ) : !visibleDivisions.length ? (
          <EmptyState
            title="No data matches your filters"
            sub={hasFilters ? 'Try clearing the filters above' : 'No active records found'}
            icon={<CheckCircle2 size={32} className="text-[#16A34A]" />}
          />
        ) : (
          visibleDivisions.map((div, i) => (
            <motion.div
              key={div.division}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
            >
              <DivisionSection
                data={div}
                defaultOpen={i === 0 || div.breachedTotal > 0}
                activeSlaFilters={activeSlaFilters}
              />
            </motion.div>
          ))
        )}
      </div>
    </div>
  )
}
