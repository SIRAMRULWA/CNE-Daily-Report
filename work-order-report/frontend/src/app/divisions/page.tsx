'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { divisionsApi, workspaceApi } from '@/lib/api'
import { fmtDateTime, cn } from '@/lib/utils'
import { PageHeader, Btn, EmptyState } from '@/components/ui'
import { toast } from 'sonner'
import {
  Plus, Trash2, ChevronRight, Settings, Users, History,
  Shield, X, AlertTriangle,
} from 'lucide-react'
import AppShell from '@/components/layout/AppShell'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations } from '@/lib/permissions'

const DIVISION_ACTIVITY_TYPES = ['division', 'division_group']

export default function DivisionsPage() {
  const { user } = useAuth()
  const canManage = canManageOperations(user)
  const qc = useQueryClient()
  const [selectedDiv, setSelectedDiv] = useState<string | null>(null)
  const [newDivName, setNewDivName] = useState('')
  const [showAddDiv, setShowAddDiv] = useState(false)
  const [newGroupInput, setNewGroupInput] = useState('')
  const [showAddGroup, setShowAddGroup] = useState(false)
  const [activeTab, setActiveTab] = useState<'groups' | 'activity'>('groups')
  const [groupToDelete, setGroupToDelete] = useState<string | null>(null)

  const { data: divData, isLoading: divLoading } = useQuery({
    queryKey: ['divisions'],
    queryFn: divisionsApi.list,
    enabled: canManage,
  })

  const { data: groupData, isLoading: groupLoading } = useQuery({
    queryKey: ['division-groups', selectedDiv],
    queryFn: () => divisionsApi.groups(selectedDiv!),
    enabled: canManage && !!selectedDiv,
  })

  const { data: activityData, isLoading: activityLoading } = useQuery({
    queryKey: ['division-activity-log', selectedDiv],
    queryFn: () => workspaceApi.activityLog(30, 0, DIVISION_ACTIVITY_TYPES, undefined, selectedDiv ?? undefined),
    enabled: canManage && !!selectedDiv,
  })

  const createDivMutation = useMutation({
    mutationFn: (name: string) => divisionsApi.create(name),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['divisions'] })
      qc.invalidateQueries({ queryKey: ['division-activity-log'] })
      qc.invalidateQueries({ queryKey: ['activity-log'] })
      setNewDivName('')
      setShowAddDiv(false)
      toast.success('Division created')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const addGroupsMutation = useMutation({
    mutationFn: ({ division, groups }: { division: string; groups: string[] }) =>
      divisionsApi.addGroups(division, groups),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['division-groups', selectedDiv] })
      qc.invalidateQueries({ queryKey: ['divisions'] })
      qc.invalidateQueries({ queryKey: ['division-activity-log'] })
      qc.invalidateQueries({ queryKey: ['activity-log'] })
      setNewGroupInput('')
      setShowAddGroup(false)
      toast.success('Group(s) added')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const deleteGroupMutation = useMutation({
    mutationFn: ({ division, group }: { division: string; group: string }) =>
      divisionsApi.deleteGroup(division, group),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['division-groups', selectedDiv] })
      qc.invalidateQueries({ queryKey: ['divisions'] })
      qc.invalidateQueries({ queryKey: ['division-activity-log'] })
      qc.invalidateQueries({ queryKey: ['activity-log'] })
      setGroupToDelete(null)
      toast.success('Group removed')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  function handleAddGroups() {
    if (!selectedDiv) return
    const groups = newGroupInput
      .split('\n')
      .map(g => g.trim())
      .filter(Boolean)
    if (!groups.length) return
    addGroupsMutation.mutate({ division: selectedDiv, groups })
  }

  function handleDeleteGroup(group: string) {
    if (!selectedDiv) return
    deleteGroupMutation.mutate({ division: selectedDiv, group })
  }

  const activeGroups = groupData?.groups.filter(g => g.active) ?? []

  if (!canManage) {
    return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Divisions']} title="Division Setup" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Operational admin access required" sub="Manager, Admin, or Super Admin access is required to manage divisions." icon={<Shield size={32} />} /></div></div></AppShell>
  }

  return (
    <AppShell>
      <div className="flex flex-col flex-1 min-h-0">
        <PageHeader
          breadcrumb={['Admin', 'Divisions']}
          title="Division Setup"
          subtitle="Manage divisions and their assignee group mappings"
          actions={
            <Btn variant="primary" size="sm" onClick={() => setShowAddDiv(v => !v)}>
              <Plus size={12} /> New division
            </Btn>
          }
        />

        <div className="flex flex-1 min-h-0 overflow-hidden">

          {/* ── LEFT: Division list ── */}
          <div className="w-[240px] min-w-[240px] bg-white border-r border-[#E5E5E5] flex flex-col overflow-hidden">
            <div className="px-3 pt-3 pb-2">
              <div className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.6px] px-1 mb-2">Divisions</div>

              {/* Add division form */}
              <AnimatePresence>
                {showAddDiv && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="mb-2 overflow-hidden"
                  >
                    <div className="bg-[#F5F5F5] border border-[#E5E5E5] rounded-md p-2 flex flex-col gap-1.5">
                      <input
                        autoFocus
                        value={newDivName}
                        onChange={e => setNewDivName(e.target.value.toUpperCase())}
                        onKeyDown={e => e.key === 'Enter' && newDivName && createDivMutation.mutate(newDivName)}
                        placeholder="DIVISION_NAME"
                        className="h-7 px-2 text-[12px] border border-[#E5E5E5] rounded bg-white outline-none focus:border-[#E60000] font-mono"
                      />
                      <div className="flex gap-1">
                        <Btn
                          variant="primary" size="sm"
                          loading={createDivMutation.isPending}
                          onClick={() => newDivName && createDivMutation.mutate(newDivName)}
                          className="flex-1 justify-center"
                        >
                          Create
                        </Btn>
                        <Btn variant="ghost" size="sm" onClick={() => setShowAddDiv(false)}>Cancel</Btn>
                      </div>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <div className="flex-1 overflow-y-auto px-3 pb-3">
              {divLoading ? (
                <div className="space-y-1">
                  {[1, 2, 3, 4].map(i => (
                    <div key={i} className="h-10 skeleton rounded-md" />
                  ))}
                </div>
              ) : (
                divData?.divisions.map(d => (
                  <button
                    key={d.division}
                    onClick={() => { setSelectedDiv(d.division); setShowAddGroup(false) }}
                    className={cn(
                      'w-full flex items-center gap-2.5 px-2.5 py-2 rounded-md text-left transition-all mb-0.5',
                      selectedDiv === d.division
                        ? 'bg-[#FFF0F0] border border-[#F5B8B8]'
                        : 'hover:bg-[#F5F5F5] border border-transparent',
                    )}
                  >
                    <div className="w-2 h-2 rounded-full bg-[#E60000] flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className={cn(
                        'text-[12px] font-600',
                        selectedDiv === d.division ? 'text-[#CC0000]' : 'text-[#1A1A1A]',
                      )}>
                        {d.division}
                      </div>
                      <div className="text-[10px] text-[#8C8C8C]">{d.group_count} groups</div>
                    </div>
                    {selectedDiv === d.division && <ChevronRight size={13} className="text-[#CC0000]" />}
                  </button>
                ))
              )}
            </div>
          </div>

          {/* ── RIGHT: Groups + Activity ── */}
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">

            {!selectedDiv ? (
              <div className="flex-1 flex items-center justify-center">
                <EmptyState
                  title="Select a division"
                  sub="Choose a division from the left to manage its assignee groups"
                  icon={<Settings size={32} className="text-[#D0D0D0]" />}
                />
              </div>
            ) : (
              <>
                {/* Tab bar */}
                <div className="bg-white border-b border-[#E5E5E5] px-4 flex items-center gap-1 flex-shrink-0">
                  {[
                    { key: 'groups' as const,   label: 'Assignee Groups', icon: <Users size={13} /> },
                    { key: 'activity' as const, label: 'Activity Log',    icon: <History size={13} /> },
                  ].map(t => (
                    <button
                      key={t.key}
                      onClick={() => setActiveTab(t.key)}
                      className={cn(
                        'flex items-center gap-1.5 px-3 py-3 text-[12px] font-500 border-b-2 transition-colors',
                        activeTab === t.key
                          ? 'border-[#E60000] text-[#E60000]'
                          : 'border-transparent text-[#5C5C5C] hover:text-[#1A1A1A]',
                      )}
                    >
                      {t.icon}
                      {t.label}
                    </button>
                  ))}

                  <div className="flex-1" />

                  {activeTab === 'groups' && (
                    <Btn variant="primary" size="sm" onClick={() => setShowAddGroup(v => !v)}>
                      <Plus size={12} /> Add groups
                    </Btn>
                  )}
                </div>

                {/* Groups panel */}
                {activeTab === 'groups' && (
                  <div className="flex-1 overflow-y-auto p-4 space-y-3">

                    {/* Add groups textarea */}
                    <AnimatePresence>
                      {showAddGroup && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          className="overflow-hidden"
                        >
                          <div className="bg-[#F5F5F5] border border-[#E5E5E5] rounded-lg p-3 space-y-2">
                            <div className="text-[11px] font-600 text-[#5C5C5C]">Add assignee groups to {selectedDiv}</div>
                            <div className="text-[10px] text-[#8C8C8C]">One group per line, e.g. Appl:VAS SMS:OSS</div>
                            <textarea
                              autoFocus
                              value={newGroupInput}
                              onChange={e => setNewGroupInput(e.target.value)}
                              placeholder={`Appl:VAS SMS:OSS\nAppl:VAS MMS:OSS`}
                              rows={3}
                              className="w-full text-[12px] font-mono border border-[#E5E5E5] rounded bg-white p-2 outline-none focus:border-[#E60000] resize-none"
                            />
                            <div className="flex gap-2">
                              <Btn
                                variant="primary" size="sm"
                                loading={addGroupsMutation.isPending}
                                onClick={handleAddGroups}
                              >
                                Add groups
                              </Btn>
                              <Btn variant="ghost" size="sm" onClick={() => { setShowAddGroup(false); setNewGroupInput('') }}>
                                Cancel
                              </Btn>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>

                    {/* Groups list */}
                    {groupLoading ? (
                      <div className="space-y-2">
                        {[1, 2, 3].map(i => <div key={i} className="h-12 skeleton rounded-lg" />)}
                      </div>
                    ) : !activeGroups.length ? (
                      <EmptyState
                        title="No groups yet"
                        sub={`Add assignee groups to ${selectedDiv} using the button above`}
                        icon={<Users size={28} />}
                      />
                    ) : (
                      <div className="space-y-1.5">
                        {activeGroups.map(g => (
                          <motion.div
                            key={g.assignee_group}
                            initial={{ opacity: 0, x: -4 }}
                            animate={{ opacity: 1, x: 0 }}
                            className="flex items-center gap-3 bg-white border border-[#E5E5E5] rounded-lg px-3 py-2.5 hover:border-[#D0D0D0] transition-colors group"
                          >
                            <div className="w-1.5 h-1.5 rounded-full bg-[#E60000] flex-shrink-0" />
                            <span className="text-[12px] font-mono text-[#1A1A1A] flex-1">{g.assignee_group}</span>
                            <span className="text-[10px] text-[#8C8C8C]">
                              Added {fmtDateTime(g.created_at)?.split('·')[0]}
                            </span>
                            <button
                              onClick={() => setGroupToDelete(g.assignee_group)}
                              className="opacity-0 group-hover:opacity-100 text-[#8C8C8C] hover:text-[#CC0000] transition-all p-1 rounded"
                              title="Remove group"
                            >
                              <Trash2 size={13} />
                            </button>
                          </motion.div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Activity log panel */}
                {activeTab === 'activity' && (
                  <div className="flex-1 overflow-y-auto p-4">
                    {activityLoading ? (
                      <div className="space-y-2">
                        {[1, 2, 3].map(i => <div key={i} className="h-16 skeleton rounded-lg" />)}
                      </div>
                    ) : !activityData?.logs.length ? (
                      <EmptyState
                        title="No activity for this division"
                        sub={`Changes to ${selectedDiv} and its assignee groups will appear here`}
                        icon={<History size={28} />}
                      />
                    ) : (
                      <div className="space-y-1.5">
                        {activityData.logs.map(log => (
                          <div key={log.id} className="bg-white border border-[#E5E5E5] rounded-lg px-3 py-2.5 flex items-start gap-3">
                            <div className="w-6 h-6 bg-[#F5F5F5] border border-[#E5E5E5] rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                              <Shield size={11} className="text-[#8C8C8C]" />
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <span className="text-[12px] font-600 text-[#1A1A1A]">{log.action}</span>
                                {log.entity_id && (
                                  <span className="text-[10px] bg-[#F5F5F5] border border-[#E5E5E5] px-1.5 py-px rounded font-mono text-[#5C5C5C]">
                                    {log.entity_id}
                                  </span>
                                )}
                              </div>
                              <div className="text-[11px] text-[#8C8C8C] mt-0.5">
                                <span className="text-[#5C5C5C]">{log.actor ?? 'System'}</span>
                                {' · '}
                                {fmtDateTime(log.created_at)}
                              </div>
                              {log.details && (
                                <details className="mt-1">
                                  <summary className="text-[10px] text-[#8C8C8C] cursor-pointer hover:text-[#5C5C5C]">
                                    View details
                                  </summary>
                                  <pre className="text-[10px] bg-[#F5F5F5] border border-[#E5E5E5] rounded p-2 mt-1 overflow-x-auto text-[#5C5C5C] font-mono">
                                    {JSON.stringify(log.details, null, 2)}
                                  </pre>
                                </details>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        <AnimatePresence>
          {selectedDiv && groupToDelete && (
            <motion.div
              className="fixed inset-0 z-[90] flex items-center justify-center bg-black/35 px-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onMouseDown={() => setGroupToDelete(null)}
            >
              <motion.div
                initial={{ opacity: 0, y: 12, scale: 0.98 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: 8, scale: 0.98 }}
                transition={{ duration: 0.16 }}
                className="w-full max-w-[420px] bg-white border border-[#E5E5E5] rounded-lg shadow-xl"
                onMouseDown={event => event.stopPropagation()}
              >
                <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-[#FFF0F0] border border-[#F5B8B8] flex items-center justify-center text-[#CC0000]">
                    <AlertTriangle size={14} />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[13px] font-600 text-[#1A1A1A]">Remove assignee group</div>
                    <div className="text-[11px] text-[#8C8C8C] truncate">{selectedDiv}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setGroupToDelete(null)}
                    className="ml-auto w-7 h-7 rounded-md flex items-center justify-center text-[#8C8C8C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                    title="Close"
                  >
                    <X size={14} />
                  </button>
                </div>

                <div className="p-4 space-y-3">
                  <p className="text-[12px] text-[#3A3A3A]">
                    Remove this assignee group mapping from the selected division?
                  </p>
                  <div className="rounded-md border border-[#E5E5E5] bg-[#FAFAFA] px-3 py-2 text-[11px] font-mono text-[#1A1A1A] break-all">
                    {groupToDelete}
                  </div>
                </div>

                <div className="px-4 py-3 border-t border-[#E5E5E5] flex justify-end gap-2">
                  <Btn variant="ghost" size="sm" onClick={() => setGroupToDelete(null)}>
                    Cancel
                  </Btn>
                  <Btn
                    variant="danger"
                    size="sm"
                    loading={deleteGroupMutation.isPending}
                    disabled={deleteGroupMutation.isPending}
                    onClick={() => handleDeleteGroup(groupToDelete)}
                  >
                    <Trash2 size={11} /> Remove group
                  </Btn>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </AppShell>
  )
}
