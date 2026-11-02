'use client'

import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts'
import { workspaceApi, healthApi, divisionsApi } from '@/lib/api'
import { aggregateSummaryRows, fmtDate, fmtDateTime, cn, DIVISION_COLORS } from '@/lib/utils'
import { KpiCard, PageHeader, TabGroup, Tag, TableSkeleton, Btn, EmptyState } from '@/components/ui'
import { AlertTriangle, Clock, CheckCircle2, Users, Download, RefreshCw, Database } from 'lucide-react'
import type { Category, SummaryRow } from '@/types'

const BANDS = ['Total Open Calls', 'Calls Nearing SLA', 'Breached Calls'] as const
type Band = (typeof BANDS)[number]

type DivisionTableRow = {
  sla_band: Band
  incident_count: number
  change_count: number
  access_count: number
  event_count: number
  total_count: number
}

const CATEGORIES: Category[] = ['INCIDENT', 'CHANGE', 'EVENT', 'ACCESS']
const CATEGORY_META: Record<Category, { name: string; color: string }> = {
  INCIDENT: { name: 'Incident', color: '#E60000' },
  CHANGE: { name: 'Change', color: '#0057A8' },
  EVENT: { name: 'Event', color: '#eda100' },
  ACCESS: { name: 'Access', color: '#6B21A8' },
}

function emptyBandRows(): Record<Band, DivisionTableRow> {
  return {
    'Total Open Calls': { sla_band: 'Total Open Calls', incident_count: 0, change_count: 0, access_count: 0, event_count: 0, total_count: 0 },
    'Calls Nearing SLA': { sla_band: 'Calls Nearing SLA', incident_count: 0, change_count: 0, access_count: 0, event_count: 0, total_count: 0 },
    'Breached Calls': { sla_band: 'Breached Calls', incident_count: 0, change_count: 0, access_count: 0, event_count: 0, total_count: 0 },
  }
}

function addCategoryCount(row: DivisionTableRow, category: Category, count: number) {
  if (category === 'INCIDENT') row.incident_count += count
  if (category === 'CHANGE') row.change_count += count
  if (category === 'ACCESS') row.access_count += count
  if (category === 'EVENT') row.event_count += count
  row.total_count += count
}

function buildDivisionTables(rows: SummaryRow[]) {
  const byDivision: Record<string, Record<Band, DivisionTableRow>> = {}

  rows.forEach(row => {
    const division = row.division ?? 'Unknown'
    if (!byDivision[division]) byDivision[division] = emptyBandRows()

    addCategoryCount(byDivision[division]['Total Open Calls'], row.report_category, row.record_count)
    if (row.sla_status === 'NEARING_SLA') {
      addCategoryCount(byDivision[division]['Calls Nearing SLA'], row.report_category, row.record_count)
    }
    if (row.sla_status === 'BREACHED') {
      addCategoryCount(byDivision[division]['Breached Calls'], row.report_category, row.record_count)
    }
  })

  return Object.entries(byDivision).map(([division, bandRows]) => ({
    division,
    rows: BANDS.map(band => bandRows[band]),
  }))
}

function buildDivisionSlaData(rows: SummaryRow[]) {
  const byDivision: Record<string, { division: string; breached: number; nearing: number; within: number; noSchedule: number }> = {}

  rows.forEach(row => {
    const division = row.division ?? 'Unknown'
    if (!byDivision[division]) {
      byDivision[division] = { division, breached: 0, nearing: 0, within: 0, noSchedule: 0 }
    }
    if (row.sla_status === 'BREACHED') byDivision[division].breached += row.record_count
    if (row.sla_status === 'NEARING_SLA') byDivision[division].nearing += row.record_count
    if (row.sla_status === 'WITHIN_SLA') byDivision[division].within += row.record_count
    if (row.sla_status === 'NO_SCHEDULE') byDivision[division].noSchedule += row.record_count
  })

  return Object.values(byDivision)
}

function DivisionTable({ division, rows }: { division: string; rows: DivisionTableRow[] }) {
  const color = DIVISION_COLORS[division] ?? '#8C8C8C'
  const byBand: Record<string, DivisionTableRow> = {}
  rows.forEach(r => { byBand[r.sla_band] = r })

  return (
    <div className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-center gap-2">
        <div className="w-2 h-2 rounded-full" style={{ background: color }} />
        <span className="text-[12px] font-600 text-[#1A1A1A]">{division}</span>
        {byBand['Breached Calls']?.total_count > 0 && (
          <Tag variant="danger">{byBand['Breached Calls'].total_count} breached</Tag>
        )}
        <span className="ml-auto text-[11px] text-[#8C8C8C]">{byBand['Total Open Calls']?.total_count ?? 0} total</span>
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            {['Status', 'Incident', 'Change', 'Access', 'Event', 'Total'].map(h => (
              <th key={h} className={cn(
                'text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-[7px] px-3 bg-[#FAFAFA] border-b border-[#E5E5E5]',
                h === 'Status' ? 'text-left' : 'text-right',
              )}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {BANDS.map(band => {
            const row = byBand[band]
            const isBreached = band === 'Breached Calls'
            const isNearing = band === 'Calls Nearing SLA'
            const label = band === 'Total Open Calls' ? 'Total Open' : isNearing ? 'Nearing SLA' : 'Breached'
            const cell = (value: number) => {
              if (!value) return <span className="text-[#8C8C8C]">0</span>
              if (isBreached) return <span className="text-[#CC0000] font-600">{value}</span>
              if (isNearing) return <span className="text-[#C47000] font-500">{value}</span>
              return <span>{value}</span>
            }

            return (
              <tr key={band} className="border-b border-[#F0F0F0] last:border-b-0 hover:bg-[#F5F5F5] transition-colors">
                <td className="px-3 py-2 text-[12px] font-500 text-[#1A1A1A]">{label}</td>
                {['incident_count', 'change_count', 'access_count', 'event_count', 'total_count'].map(key => (
                  <td key={key} className="px-3 py-2 text-right text-[12px]">
                    {cell(row[key as keyof DivisionTableRow] as number)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default function DashboardPage() {
  const queryClient = useQueryClient()
  const [divTab, setDivTab] = useState<string>('All Divisions')

  const { data: summary, isLoading: sumLoading, isFetching: sumFetching } = useQuery({
    queryKey: ['workspace-summary'],
    queryFn: () => workspaceApi.summary(),
    refetchInterval: 60_000,
  })

  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
  })

  const { data: divisions } = useQuery({
    queryKey: ['divisions'],
    queryFn: divisionsApi.list,
  })

  const summaryRows = summary?.rows ?? []
  const totals = summary ? aggregateSummaryRows(summary.rows) : null
  const dataDate = summary?.data_date
  const dataDateLabel = dataDate ? fmtDate(dataDate, 'EEEE, dd MMMM yyyy') : 'Loading data date'

  const catData = CATEGORIES.map(category => ({
    ...CATEGORY_META[category],
    value: summaryRows
      .filter(row => row.report_category === category)
      .reduce((total, row) => total + row.record_count, 0),
  }))
  const divisionTables = buildDivisionTables(summaryRows)
  const divisionSlaData = buildDivisionSlaData(summaryRows)
  const divTabs = ['All Divisions', ...(divisions?.divisions.map(d => d.division) ?? [])]

  function refreshDashboard() {
    queryClient.invalidateQueries({ queryKey: ['workspace-summary'] })
    queryClient.invalidateQueries({ queryKey: ['health'] })
    queryClient.invalidateQueries({ queryKey: ['divisions'] })
  }

  return (
    <div className="flex flex-col flex-1">
      <PageHeader
        breadcrumb={['Operations Console', 'Dashboard']}
        title="Operations Overview"
        subtitle={`All divisions - ${dataDateLabel}`}
        actions={
          <>
            <Btn variant="default" size="sm"><Download size={12} />Export</Btn>
            <Btn variant="default" size="sm" onClick={refreshDashboard}>
              <RefreshCw size={12} className={sumFetching ? 'animate-spin' : ''} />Refresh
            </Btn>
          </>
        }
      />

      <div className="p-6 flex-1 overflow-y-auto">
        {!sumLoading && summary?.data_available === false && (
          <div className="mb-5 bg-white border border-[#E5E5E5] rounded-lg">
            <EmptyState
              title={`No pipeline data has been loaded for ${fmtDate(summary.data_date, 'dd MMMM yyyy')}.`}
              sub={`Live dashboard records are isolated to the current ${summary.timezone} date.`}
              icon={<Database size={32} />}
            />
          </div>
        )}
        <div className="grid grid-cols-3 gap-3 mb-5">
          {[
            {
              icon: <CheckCircle2 size={18} className="text-[#0A7A0A]" />,
              iconBg: 'bg-[#EDF7ED]',
              label: 'API Status',
              value: health?.status === 'ok' ? 'All systems operational' : 'Degraded',
              sub: fmtDateTime(health?.api_time),
            },
            {
              icon: <Clock size={18} className="text-[#0A7A0A]" />,
              iconBg: 'bg-[#EDF7ED]',
              label: 'Last Pipeline Run',
              value: fmtDateTime(health?.pipeline?.last_run_at) ?? 'No data',
              sub: health?.pipeline?.last_run_status ?? '-',
            },
            {
              icon: <AlertTriangle size={18} className="text-[#C47000]" />,
              iconBg: 'bg-[#FFF8E6]',
              label: 'Attention Needed',
              value: `${summary?.data_available === false ? 0 : (health?.records?.breached ?? 0)} breached`,
              sub: 'Across all divisions',
            },
          ].map((item, i) => (
            <motion.div
              key={item.label}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.06 }}
              className="bg-white border border-[#E5E5E5] rounded-lg p-3.5 flex items-center gap-3"
            >
              <div className={cn('w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0', item.iconBg)}>
                {item.icon}
              </div>
              <div>
                <div className="text-[11px] text-[#8C8C8C] mb-0.5">{item.label}</div>
                <div className="text-[13px] font-600 text-[#1A1A1A]">{item.value}</div>
                <div className="text-[10px] text-[#8C8C8C] mt-px">{item.sub}</div>
              </div>
            </motion.div>
          ))}
        </div>

        <div className="grid grid-cols-4 gap-3 mb-5">
          {[
            { label: 'Breached Calls', value: totals?.BREACHED ?? health?.records?.breached ?? 0, variant: 'danger', icon: <AlertTriangle size={36} /> },
            { label: 'Nearing SLA', value: totals?.NEARING_SLA ?? 0, variant: 'warning', icon: <Clock size={36} /> },
            { label: 'Within SLA', value: totals?.WITHIN_SLA ?? 0, variant: 'success', icon: <CheckCircle2 size={36} /> },
            { label: 'Total Active', value: totals?.total ?? health?.records?.active ?? 0, variant: 'info', sub: `Across ${divisions?.count ?? 0} divisions`, icon: <Users size={36} /> },
          ].map((kpi, i) => (
            <motion.div key={kpi.label} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.07 }}>
              <KpiCard
                label={kpi.label}
                value={kpi.value}
                variant={kpi.variant as 'danger' | 'warning' | 'success' | 'info'}
                sub={kpi.sub}
                icon={kpi.icon}
                loading={sumLoading}
              />
            </motion.div>
          ))}
        </div>

        <div className="grid grid-cols-[2fr_1fr] gap-4 mb-5">
          <div className="bg-white border border-[#E5E5E5] rounded-lg p-4">
            <div className="text-[12px] font-600 text-[#1A1A1A] mb-0.5">SLA Distribution</div>
            <div className="text-[11px] text-[#8C8C8C] mb-3">Current active calls per division</div>
            <div className="flex gap-4 mb-3 flex-wrap">
              {[
                { label: 'Breached', color: '#E60000' },
                { label: 'Nearing SLA', color: '#F59E0B' },
                { label: 'Within SLA', color: '#16A34A' },
                { label: 'No Schedule', color: '#3B82F6' },
              ].map(item => (
                <div key={item.label} className="flex items-center gap-1.5 text-[11px] text-[#5C5C5C]">
                  <div className="w-2 h-2 rounded-[2px]" style={{ background: item.color }} />
                  {item.label}
                </div>
              ))}
            </div>
            <div className="h-[160px]">
              {sumLoading ? (
                <TableSkeleton rows={4} cols={4} />
              ) : divisionSlaData.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={divisionSlaData} margin={{ top: 2, right: 4, left: -28, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.04)" />
                    <XAxis dataKey="division" tick={{ fontSize: 10, fill: '#8C8C8C' }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fontSize: 10, fill: '#8C8C8C' }} axisLine={false} tickLine={false} />
                    <Tooltip contentStyle={{ fontSize: 11, border: '1px solid #E5E5E5', borderRadius: 6, boxShadow: '0 2px 8px rgba(0,0,0,0.08)' }} />
                    <Bar dataKey="breached" stackId="sla" fill="#E60000" name="Breached" />
                    <Bar dataKey="nearing" stackId="sla" fill="#F59E0B" name="Nearing SLA" />
                    <Bar dataKey="within" stackId="sla" fill="#16A34A" name="Within SLA" />
                    <Bar dataKey="noSchedule" stackId="sla" fill="#3B82F6" name="No Schedule" />
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-[12px] text-[#8C8C8C]">No SLA data available</div>
              )}
            </div>
          </div>

          <div className="bg-white border border-[#E5E5E5] rounded-lg p-4">
            <div className="text-[12px] font-600 text-[#1A1A1A] mb-0.5">By Category</div>
            <div className="text-[11px] text-[#8C8C8C] mb-2">Active records split</div>
            <div className="h-[160px]">
              {catData.some(c => c.value > 0) ? (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={catData} dataKey="value" cx="50%" cy="50%" innerRadius={46} outerRadius={68} strokeWidth={2} stroke="#fff">
                      {catData.map((entry, i) => (
                        <Cell key={i} fill={entry.color} />
                      ))}
                    </Pie>
                    <Tooltip formatter={(v: number, name: string) => [`${v} records`, name]} contentStyle={{ fontSize: 11, border: '1px solid #E5E5E5', borderRadius: 6 }} />
                  </PieChart>
                </ResponsiveContainer>
              ) : (
                <div className="h-full flex items-center justify-center text-[12px] text-[#8C8C8C]">No category data available</div>
              )}
            </div>
            <div className="flex flex-col gap-1 mt-1">
              {catData.map(category => (
                <div key={category.name} className="flex items-center justify-between text-[11px]">
                  <div className="flex items-center gap-1.5">
                    <div className="w-2 h-2 rounded-[2px]" style={{ background: category.color }} />
                    <span className="text-[#5C5C5C]">{category.name}</span>
                  </div>
                  <span className="font-500 text-[#1A1A1A]">{category.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 mb-3">
          <div className="text-[13px] font-600 text-[#1A1A1A]">Division Summary</div>
          <div className="flex-1" />
          <TabGroup
            tabs={divTabs.map(division => ({ value: division, label: division }))}
            value={divTab}
            onChange={setDivTab}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          {divisionTables
            .filter(table => divTab === 'All Divisions' || table.division === divTab)
            .map((table, i) => (
              <motion.div key={table.division} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }}>
                <DivisionTable division={table.division} rows={table.rows} />
              </motion.div>
            ))}
          {!sumLoading && !divisionTables.length && (
            <div className="col-span-2 bg-white border border-[#E5E5E5] rounded-lg py-8 text-center text-[12px] text-[#8C8C8C]">
              No division summary data available
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
