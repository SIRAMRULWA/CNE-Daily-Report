'use client'

import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { healthApi, ApiError } from '@/lib/api'
import { fmtDateTime, fmtRelative, cn } from '@/lib/utils'
import { PageHeader, KpiCard, Btn, Tag, EmptyState } from '@/components/ui'
import { CheckCircle2, AlertTriangle, Clock, Database, RefreshCw, Activity, ShieldCheck } from 'lucide-react'
import AppShell from '@/components/layout/AppShell'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations } from '@/lib/permissions'

export default function PipelinePage() {
  const { user } = useAuth()
  const canManage = canManageOperations(user)
  const { data: health, isLoading: hLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
    enabled: canManage,
    refetchInterval: 30_000,
  })

  const { data: runLog, isLoading: rlLoading, error: runsError, refetch: refetchRuns } = useQuery({
    queryKey: ['run-log'],
    queryFn: () => healthApi.runLog(25),
    enabled: canManage,
    refetchInterval: 30_000,
  })

  const statusOk = health?.status === 'ok'
  const pipelineOk = health?.pipeline?.last_run_status === 'SUCCESS'

  if (!canManage) {
    return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Pipeline Status']} title="Pipeline Status" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Operational admin access required" sub="Manager, Admin, or Super Admin access is required to view pipeline runs." icon={<ShieldCheck size={32} />} /></div></div></AppShell>
  }

  if (runsError instanceof ApiError && runsError.status === 403) {
    return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Pipeline Status']} title="Pipeline Status" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Access denied" sub="The backend did not authorize this account to view pipeline runs." icon={<ShieldCheck size={32} />} /></div></div></AppShell>
  }

  return (
    <AppShell>
      <div className="flex flex-col flex-1 min-h-0">
        <PageHeader
          breadcrumb={['Admin', 'Pipeline Status']}
          title="Pipeline Status"
          subtitle="Data freshness, pipeline runs, and system health"
          actions={
            <Btn variant="default" size="sm" onClick={() => { refetchHealth(); refetchRuns() }}>
              <RefreshCw size={11} /> Refresh
            </Btn>
          }
        />

        <div className="flex-1 overflow-y-auto p-5 space-y-5">

          {/* Health KPIs */}
          <div className="grid grid-cols-4 gap-3">
            {[
              {
                label: 'API Status',
                value: statusOk ? 'Healthy' : 'Degraded',
                variant: (statusOk ? 'success' : 'danger') as 'success' | 'danger',
                sub: fmtDateTime(health?.api_time),
                icon: <CheckCircle2 size={36} />,
              },
              {
                label: 'Last Pipeline Run',
                value: health?.pipeline?.last_run_status ?? '—',
                variant: (pipelineOk ? 'success' : 'warning') as 'success' | 'warning',
                sub: fmtRelative(health?.pipeline?.last_run_at),
                icon: <Activity size={36} />,
              },
              {
                label: 'Total Records',
                value: health?.records?.total ?? 0,
                variant: 'info' as const,
                sub: 'In staging table',
                icon: <Database size={36} />,
              },
              {
                label: 'Breached Active',
                value: health?.records?.breached ?? 0,
                variant: ((health?.records?.breached ?? 0) > 0 ? 'danger' : 'success') as 'danger' | 'success',
                sub: 'Needs attention',
                icon: <AlertTriangle size={36} />,
              },
            ].map((k, i) => (
              <motion.div key={k.label} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.07 }}>
                <KpiCard {...k} loading={hLoading} />
              </motion.div>
            ))}
          </div>

          {/* Pipeline details card */}
          <div className="bg-white border border-[#E5E5E5] rounded-lg p-4">
            <div className="text-[12px] font-600 text-[#1A1A1A] mb-3">Pipeline Details</div>
            <div className="grid grid-cols-3 gap-4">
              {[
                { label: 'Last run at',     value: fmtDateTime(health?.pipeline?.last_run_at) ?? 'Never' },
                { label: 'Last status',     value: health?.pipeline?.last_run_status ?? '—' },
                { label: 'Heartbeat at',    value: fmtDateTime(health?.pipeline?.updated_at) ?? '—' },
                { label: 'Active records',  value: health?.records?.active?.toLocaleString('en-ZA') ?? '—' },
                { label: 'Breached records',value: health?.records?.breached?.toLocaleString('en-ZA') ?? '—' },
                { label: 'Total records',   value: health?.records?.total?.toLocaleString('en-ZA') ?? '—' },
              ].map(f => (
                <div key={f.label} className="flex flex-col gap-0.5">
                  <div className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px]">{f.label}</div>
                  <div className="text-[13px] font-500 text-[#1A1A1A]">{f.value}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Run log */}
          <div className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-center gap-2">
              <Clock size={13} className="text-[#8C8C8C]" />
              <span className="text-[12px] font-600 text-[#1A1A1A]">Recent Pipeline Runs</span>
              <span className="text-[11px] text-[#8C8C8C] ml-auto">
                {runLog?.runs.length ?? 0} runs shown
              </span>
            </div>

            {rlLoading ? (
              <div className="divide-y divide-[#F0F0F0]">
                {[1, 2, 3, 4, 5].map(i => (
                  <div key={i} className="px-4 py-3 flex items-center gap-3">
                    <div className="w-2 h-6 skeleton rounded" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 skeleton rounded w-48" />
                      <div className="h-3 skeleton rounded w-32" />
                    </div>
                    <div className="h-5 w-16 skeleton rounded-full" />
                  </div>
                ))}
              </div>
            ) : !runLog?.runs.length ? (
              <EmptyState
                title="No pipeline runs yet"
                sub="Run the pipeline using: python pipeline/run.py"
                icon={<Activity size={28} />}
              />
            ) : (
              <div className="divide-y divide-[#F0F0F0]">
                {runLog.runs.map((run, i) => {
                  const statusColor = {
                    SUCCESS: 'bg-[#16A34A]',
                    FAILED:  'bg-[#E60000]',
                    PARTIAL: 'bg-[#F59E0B]',
                    RUNNING: 'bg-[#3B82F6]',
                  }[run.status] ?? 'bg-[#D0D0D0]'

                  const tagVariant = {
                    SUCCESS: 'success',
                    FAILED:  'danger',
                    PARTIAL: 'warning',
                    RUNNING: 'info',
                  }[run.status] as 'success' | 'danger' | 'warning' | 'info'

                  return (
                    <motion.div
                      key={run.run_id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.03 }}
                      className="px-4 py-3 flex items-center gap-3 hover:bg-[#F5F5F5] transition-colors"
                    >
                      <div className={cn('w-1.5 h-8 rounded-full flex-shrink-0', statusColor)} />

                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-[12px] font-600 text-[#1A1A1A]">{run.pipeline_name}</span>
                          <span className="text-[11px] text-[#8C8C8C]">/ {run.source_entity}</span>
                          {run.source_file && (
                            <span className="text-[10px] font-mono text-[#5C5C5C] bg-[#F5F5F5] border border-[#E5E5E5] px-1.5 py-px rounded truncate max-w-[200px]">
                              {run.source_file}
                            </span>
                          )}
                        </div>
                        <div className="flex items-center gap-3 mt-0.5 text-[11px] text-[#8C8C8C]">
                          <span>{fmtDateTime(run.run_start)}</span>
                          {run.duration_seconds != null && <span>· {run.duration_seconds}s</span>}
                          <span>· ↓ {run.rows_loaded?.toLocaleString('en-ZA')} loaded</span>
                          {run.rows_rejected > 0 && (
                            <span className="text-[#CC0000]">✗ {run.rows_rejected} rejected</span>
                          )}
                          {run.error_message && (
                            <span className="text-[#CC0000] truncate max-w-[200px]" title={run.error_message}>
                              {run.error_message}
                            </span>
                          )}
                        </div>
                      </div>

                      <Tag variant={tagVariant}>{run.status}</Tag>
                    </motion.div>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </AppShell>
  )
}
