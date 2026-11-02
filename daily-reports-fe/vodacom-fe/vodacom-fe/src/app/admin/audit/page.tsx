'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { workspaceApi, ApiError } from '@/lib/api'
import { fmtDateTime, fmtRelative, cn } from '@/lib/utils'
import { PageHeader, Btn, EmptyState, TableSkeleton } from '@/components/ui'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations } from '@/lib/permissions'
import { Shield, ChevronDown, ChevronRight, RefreshCw, History, Search } from 'lucide-react'
import type { ActivityLogEntry } from '@/types'
import AppShell from '@/components/layout/AppShell'

const ACTION_COLORS: Record<string, string> = {
  add_division_groups:    'bg-[#EDF7ED] text-[#0A7A0A] border-[#B8DFB8]',
  delete_group:           'bg-[#FFF0F0] text-[#CC0000] border-[#F5B8B8]',
  create_division:        'bg-[#EEF4FF] text-[#0057A8] border-[#B8CEFF]',
  deactivate_division:    'bg-[#FFF8E6] text-[#C47000] border-[#F5D580]',
  update_role:            'bg-[#F5F0FF] text-[#6B21A8] border-[#D8B8FF]',
  update_status:          'bg-[#FFF8E6] text-[#C47000] border-[#F5D580]',
}

function ActionBadge({ action }: { action: string }) {
  const cls = ACTION_COLORS[action] ?? 'bg-[#F5F5F5] text-[#5C5C5C] border-[#E5E5E5]'
  return (
    <span className={cn('inline-flex items-center px-2 py-px rounded text-[10px] font-600 border', cls)}>
      {action.replace(/_/g, ' ')}
    </span>
  )
}

function LogRow({ log }: { log: ActivityLogEntry }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = Boolean(log.details || log.request_id)

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="border-b border-[#F0F0F0] last:border-b-0 hover:bg-[#FAFAFA] transition-colors"
    >
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => hasDetails && setExpanded(v => !v)}
      >
        {/* Expand icon */}
        <span className="text-[#D0D0D0] w-4 flex-shrink-0">
          {hasDetails
            ? expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />
            : null}
        </span>

        {/* Actor avatar */}
        <div className="w-7 h-7 bg-[#F5F5F5] border border-[#E5E5E5] rounded-full flex items-center justify-center text-[10px] font-700 text-[#5C5C5C] flex-shrink-0">
          {(log.actor ?? 'SY').slice(0, 2).toUpperCase()}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] font-600 text-[#1A1A1A]">{log.actor ?? 'System'}</span>
            <ActionBadge action={log.action} />
            {log.entity_id && (
              <span className="text-[11px] font-mono text-[#5C5C5C] bg-[#F5F5F5] border border-[#E5E5E5] px-1.5 py-px rounded">
                {log.entity_id}
              </span>
            )}
            {log.request_id && (
              <span className="text-[10px] font-mono text-[#0057A8] bg-[#EEF4FF] border border-[#B8CEFF] px-1.5 py-px rounded" title="Support request reference">
                Ref: {log.request_id}
              </span>
            )}
            <span className="text-[11px] text-[#8C8C8C] ml-auto">{fmtRelative(log.created_at)}</span>
          </div>
          <div className="text-[11px] text-[#8C8C8C] mt-0.5">
            {fmtDateTime(log.created_at)} · {log.entity_type}
          </div>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div className="px-4 pb-3 ml-14">
          {log.request_id && <div className="mb-2 text-[10.5px] text-[#5C5C5C]"><span className="font-600">Request ID:</span> <span className="font-mono text-[#0057A8] select-all">{log.request_id}</span></div>}
          {log.details && <pre className="text-[10.5px] bg-[#F5F5F5] border border-[#E5E5E5] rounded-md p-3 overflow-x-auto text-[#5C5C5C] font-mono leading-relaxed">
            {JSON.stringify(log.details, null, 2)}
          </pre>}
        </div>
      )}
    </motion.div>
  )
}

export default function AuditPage() {
  const { user } = useAuth()
  const canManage = canManageOperations(user)
  const [offset, setOffset] = useState(0)
  const [entityFilter, setEntityFilter] = useState('')
  const [search, setSearch] = useState('')
  const LIMIT = 50

  const { data, isLoading, error: auditError, refetch } = useQuery({
    queryKey: ['activity-log', offset, entityFilter],
    queryFn: () => workspaceApi.activityLog(LIMIT, offset, entityFilter || undefined),
    enabled: canManage,
  })

  if (!canManage) {
    return (
      <AppShell>
        <div className="flex flex-col flex-1 min-h-0">
          <PageHeader breadcrumb={['Admin', 'Audit Log']} title="Audit Log" />
          <div className="flex-1 flex items-center justify-center">
            <EmptyState
              title="Operational admin access required"
              sub="Manager, Admin, or Super Admin access is required to view the audit log"
              icon={<Shield size={32} />}
            />
          </div>
        </div>
      </AppShell>
    )
  }

  if (auditError instanceof ApiError && auditError.status === 403) {
    return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Audit Log']} title="Audit Log" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Access denied" sub="The backend did not authorize this account to view audit events." icon={<Shield size={32} />} /></div></div></AppShell>
  }

  const logs = data?.logs ?? []
  const query = search.trim().toLowerCase()
  const visibleLogs = query
    ? logs.filter(log => [log.request_id, log.actor, log.action, log.entity_type, log.entity_id]
      .some(value => value?.toLowerCase().includes(query)))
    : logs
  const total = data?.count ?? 0

  return (
    <AppShell>
      <div className="flex flex-col flex-1 min-h-0">
        <PageHeader
          breadcrumb={['Admin', 'Audit Log']}
          title="Audit Log"
          subtitle="Complete history of configuration changes and administrative actions"
          actions={
            <Btn variant="default" size="sm" onClick={() => refetch()}>
              <RefreshCw size={11} /> Refresh
            </Btn>
          }
        />

        {/* Filters */}
        <div className="bg-white border-b border-[#E5E5E5] px-4 py-2.5 flex items-center gap-3 flex-shrink-0">
          <span className="text-[11px] text-[#8C8C8C]">Filter by type:</span>
          <div className="flex gap-1.5">
            {['', 'division', 'group', 'user'].map(t => (
              <button
                key={t}
                onClick={() => { setEntityFilter(t); setOffset(0) }}
                className={cn(
                  'px-2.5 py-1 rounded-full text-[11px] font-500 border transition-all',
                  entityFilter === t
                    ? 'bg-[#1A1A1A] border-[#1A1A1A] text-white'
                    : 'bg-white border-[#E5E5E5] text-[#5C5C5C] hover:border-[#D0D0D0]',
                )}
              >
                {t === '' ? 'All' : t.charAt(0).toUpperCase() + t.slice(1)}
              </button>
            ))}
          </div>
          <label className="relative ml-2 min-w-[240px]">
            <Search size={12} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#8C8C8C]" />
            <input
              value={search}
              onChange={event => setSearch(event.target.value)}
              placeholder="Search request ID, user or action"
              aria-label="Search audit log"
              className="h-7 w-full rounded-md border border-[#D0D0D0] bg-white pl-7 pr-2 text-[11px] text-[#1A1A1A] outline-none focus:border-[#0057A8]"
            />
          </label>
          <span className="ml-auto text-[11px] text-[#8C8C8C]">{total} entries</span>
        </div>

        {/* Log table */}
        <div className="flex-1 overflow-y-auto bg-white">
          {isLoading ? (
            <table className="w-full"><TableSkeleton rows={10} cols={5} /></table>
          ) : !visibleLogs.length ? (
            <EmptyState
              title={query ? 'No matching activity' : 'No activity recorded'}
              sub={query ? 'Try a different request ID, user, or action.' : 'Division and user changes will appear here'}
              icon={<History size={32} />}
            />
          ) : (
            <div>
              {visibleLogs.map(log => (
                <LogRow key={log.id} log={log} />
              ))}
            </div>
          )}
        </div>

        {/* Pagination */}
        <div className="bg-white border-t border-[#E5E5E5] px-4 py-2.5 flex items-center gap-3 flex-shrink-0">
          <span className="text-[11px] text-[#8C8C8C] flex-1">
            {total > 0
              ? `Showing ${offset + 1}–${Math.min(offset + LIMIT, total)} of ${total}`
              : 'No entries'}
          </span>
          <Btn
            variant="default" size="sm"
            disabled={offset === 0}
            onClick={() => setOffset(v => Math.max(0, v - LIMIT))}
          >
            ← Prev
          </Btn>
          <Btn
            variant="default" size="sm"
            disabled={offset + LIMIT >= total}
            onClick={() => setOffset(v => v + LIMIT)}
          >
            Next →
          </Btn>
        </div>
      </div>
    </AppShell>
  )
}
