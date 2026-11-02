'use client'

import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { adminApi, ApiError } from '@/lib/api'
import { fmtRelative, cn, ROLE_LABELS } from '@/lib/utils'
import { PageHeader, Btn, EmptyState, Tag } from '@/components/ui'
import { toast } from 'sonner'
import { Users, Plus, KeyRound, ShieldCheck, UserX, UserCheck, AlertCircle, Eye, EyeOff, Trash2, X, AlertTriangle } from 'lucide-react'
import AppShell from '@/components/layout/AppShell'
import { useAuth } from '@/lib/auth-context'
import { canManageOperations, isSuperAdmin } from '@/lib/permissions'
import type { Role } from '@/types'

const ROLES: Role[] = ['ADMIN', 'MANAGER', 'USER', 'READ_ONLY']
const TEMP_PASSWORD_MIN_LENGTH = 12
const ALLOWED_EMAIL_DOMAINS = ['vodacom.co.za', 'vodacom.com', 'vcontractor.co.za']

type UserActionTarget = {
  id: number
  email: string
}

function getEmailDomain(email: string) {
  const parts = email.trim().toLowerCase().split('@')
  return parts.length === 2 ? parts[1] : ''
}

function isAllowedEmail(email: string) {
  return ALLOWED_EMAIL_DOMAINS.includes(getEmailDomain(email))
}

export default function UsersPage() {
  const { user: me } = useAuth()
  const canManage = canManageOperations(me)
  const canDeleteUsers = isSuperAdmin(me)
  const qc = useQueryClient()
  const [showAdd, setShowAdd] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newFullName, setNewFullName] = useState('')
  const [newRole, setNewRole] = useState<Role>('USER')
  const [newPassword, setNewPassword] = useState('')
  const [newPasswordConfirm, setNewPasswordConfirm] = useState('')
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [resetTarget, setResetTarget] = useState<UserActionTarget | null>(null)
  const [resetPassword, setResetPassword] = useState('')
  const [resetPasswordConfirm, setResetPasswordConfirm] = useState('')
  const [showResetPassword, setShowResetPassword] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<UserActionTarget | null>(null)
  const cleanEmail = newEmail.trim().toLowerCase()
  const cleanFullName = newFullName.trim()
  const cleanNewPassword = newPassword.trim()
  const cleanNewPasswordConfirm = newPasswordConfirm.trim()
  const emailIsReady = cleanEmail.length > 0 && isAllowedEmail(cleanEmail)
  const passwordIsReady = cleanNewPassword.length >= TEMP_PASSWORD_MIN_LENGTH
  const passwordsMatch = cleanNewPassword.length > 0 && cleanNewPassword === cleanNewPasswordConfirm
  const canCreateUser = emailIsReady && cleanFullName.length > 0 && passwordIsReady && passwordsMatch
  const cleanResetPassword = resetPassword.trim()
  const cleanResetPasswordConfirm = resetPasswordConfirm.trim()
  const resetPasswordIsReady = cleanResetPassword.length >= TEMP_PASSWORD_MIN_LENGTH
  const resetPasswordsMatch = cleanResetPassword.length > 0 && cleanResetPassword === cleanResetPasswordConfirm
  const canResetPassword = Boolean(resetTarget) && resetPasswordIsReady && resetPasswordsMatch

  const { data, isLoading, error: usersError } = useQuery({
    queryKey: ['admin-users'],
    queryFn: () => adminApi.users(),
    enabled: canManage,
  })

  const createMutation = useMutation({
    mutationFn: ({ email, role, password, fullName }: { email: string; role: string; password: string; fullName?: string }) =>
      adminApi.createUser(email, role, password, fullName),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setNewEmail('')
      setNewFullName('')
      setNewPassword('')
      setNewPasswordConfirm('')
      setShowNewPassword(false)
      setShowAdd(false)
      toast.success('User created')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: string }) =>
      adminApi.updateUser(id, { status }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('User status updated')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const roleMutation = useMutation({
    mutationFn: ({ id, role }: { id: number; role: string }) =>
      adminApi.updateUser(id, { role }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      toast.success('Role updated')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const resetMutation = useMutation({
    mutationFn: ({ id, password }: { id: number; password: string }) => adminApi.resetPassword(id, password),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      closeResetPasswordDialog()
      toast.success('Password reset')
    },
    onError: (err: Error) => toast.error(err.message),
  })

  const deleteMutation = useMutation({
    mutationFn: ({ id }: { id: number }) => adminApi.deleteUser(id),
    onSuccess: deleted => {
      qc.invalidateQueries({ queryKey: ['admin-users'] })
      setDeleteTarget(null)
      toast.success(`${deleted.email} deleted`)
    },
    onError: (err: Error) => toast.error(err.message),
  })

  function cleanTemporaryPassword(password: string) {
    const cleaned = password.trim()
    if (password !== cleaned) {
      toast.warning('Leading or trailing spaces were removed from the temporary password')
    }
    return cleaned
  }

  function handleCreateUser() {
    const password = cleanTemporaryPassword(newPassword)
    const confirmPassword = cleanTemporaryPassword(newPasswordConfirm)
    const email = cleanEmail
    const fullName = cleanFullName

    if (!email || !fullName || !password || !confirmPassword) {
      toast.error('Email, full name, and temporary password are required')
      return
    }
    if (!isAllowedEmail(email)) {
      toast.error(`Email must end with ${ALLOWED_EMAIL_DOMAINS.map(domain => `@${domain}`).join(', ')}`)
      return
    }
    if (password.length < TEMP_PASSWORD_MIN_LENGTH) {
      toast.error(`Temporary password must be at least ${TEMP_PASSWORD_MIN_LENGTH} characters`)
      return
    }
    if (password !== confirmPassword) {
      toast.error('Temporary passwords do not match')
      return
    }

    createMutation.mutate({
      email,
      role: newRole,
      password,
      fullName,
    })
  }

  function openResetPasswordDialog(target: UserActionTarget) {
    setResetTarget(target)
    setResetPassword('')
    setResetPasswordConfirm('')
    setShowResetPassword(false)
  }

  function closeResetPasswordDialog() {
    setResetTarget(null)
    setResetPassword('')
    setResetPasswordConfirm('')
    setShowResetPassword(false)
  }

  function handleResetPassword() {
    if (!resetTarget) return
    const password = cleanTemporaryPassword(resetPassword)
    const confirmPassword = cleanTemporaryPassword(resetPasswordConfirm)
    if (password.length < TEMP_PASSWORD_MIN_LENGTH) {
      toast.error(`Temporary password must be at least ${TEMP_PASSWORD_MIN_LENGTH} characters`)
      return
    }
    if (password !== confirmPassword) {
      toast.error('Temporary passwords do not match')
      return
    }

    resetMutation.mutate({ id: resetTarget.id, password })
  }

  function handleDeleteUser() {
    if (!deleteTarget) return
    deleteMutation.mutate({ id: deleteTarget.id })
  }

  if (!canManage) {
    return (
      <AppShell>
        <div className="flex flex-col flex-1 min-h-0">
          <PageHeader breadcrumb={['Admin', 'Users']} title="User Management" />
          <div className="flex-1 flex items-center justify-center">
            <EmptyState
              title="Operational admin access required"
              sub="Manager, Admin, or Super Admin access is required to manage users"
              icon={<ShieldCheck size={32} />}
            />
          </div>
        </div>
      </AppShell>
    )
  }

  if (usersError instanceof ApiError && usersError.status === 403) {
    return <AppShell><div className="flex flex-col flex-1"><PageHeader breadcrumb={['Admin', 'Users']} title="User Management" /><div className="flex-1 flex items-center justify-center"><EmptyState title="Access denied" sub="The backend did not authorize this account to view users." icon={<ShieldCheck size={32} />} /></div></div></AppShell>
  }

  return (
    <AppShell>
      <div className="flex flex-col flex-1 min-h-0">
        <PageHeader
          breadcrumb={['Admin', 'Users']}
          title="User Management"
          subtitle="Manage access and roles for INTEL Operations users"
          actions={
            <Btn variant="primary" size="sm" onClick={() => setShowAdd(v => !v)}>
              <Plus size={12} /> New user
            </Btn>
          }
        />

        <div className="flex-1 overflow-y-auto p-5 space-y-4">

          {/* Add user form */}
          {showAdd && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-white border border-[#E5E5E5] rounded-lg p-4"
            >
              <div className="text-[12px] font-600 text-[#1A1A1A] mb-3">Create new user</div>
              <div className="flex flex-wrap gap-3 items-end">
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Email</label>
                  <input
                    autoFocus
                    type="email"
                    value={newEmail}
                    onChange={e => setNewEmail(e.target.value)}
                    placeholder="name@vcontractor.co.za"
                    className="h-8 px-2.5 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000] w-56"
                  />
                  {newEmail && !emailIsReady && (
                    <span className="text-[10px] text-[#CC0000]">Use an approved Vodacom or contractor email domain.</span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Full name</label>
                  <input
                    type="text"
                    value={newFullName}
                    onChange={e => setNewFullName(e.target.value)}
                    placeholder="John Smith"
                    className="h-8 px-2.5 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000] w-44"
                  />
                  {newFullName && !cleanFullName && (
                    <span className="text-[10px] text-[#CC0000]">Enter the full name.</span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Temporary password</label>
                  <div className="relative">
                    <input
                      type={showNewPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={e => setNewPassword(e.target.value)}
                      placeholder="Temporary password"
                      className="h-8 pl-2.5 pr-8 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000] w-44"
                    />
                    <button
                      type="button"
                      onClick={() => setShowNewPassword(v => !v)}
                      className="absolute right-2 top-1/2 -translate-y-1/2 text-[#8C8C8C] hover:text-[#1A1A1A]"
                      title={showNewPassword ? 'Hide password' : 'Show password'}
                    >
                      {showNewPassword ? <EyeOff size={13} /> : <Eye size={13} />}
                    </button>
                  </div>
                  {newPassword && !passwordIsReady && (
                    <span className="text-[10px] text-[#CC0000]">Use at least {TEMP_PASSWORD_MIN_LENGTH} characters.</span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Confirm password</label>
                  <input
                    type={showNewPassword ? 'text' : 'password'}
                    value={newPasswordConfirm}
                    onChange={e => setNewPasswordConfirm(e.target.value)}
                    placeholder="Repeat password"
                    className="h-8 px-2.5 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000] w-44"
                  />
                  {newPasswordConfirm && !passwordsMatch && (
                    <span className="text-[10px] text-[#CC0000]">Passwords must match.</span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Role</label>
                  <select
                    value={newRole}
                    onChange={e => setNewRole(e.target.value as Role)}
                    className="h-8 px-2 text-[12px] border border-[#E5E5E5] rounded-md bg-white outline-none focus:border-[#E60000] cursor-pointer"
                  >
                    {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                  </select>
                </div>
                <Btn
                  variant="primary" size="sm"
                  loading={createMutation.isPending}
                  disabled={!canCreateUser || createMutation.isPending}
                  onClick={handleCreateUser}
                >
                  Create user
                </Btn>
                <Btn
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    setShowAdd(false)
                    setNewPassword('')
                    setNewPasswordConfirm('')
                    setShowNewPassword(false)
                  }}
                >
                  Cancel
                </Btn>
              </div>
              <p className="text-[10px] text-[#8C8C8C] mt-2">
                Allowed domains: @vodacom.co.za, @vodacom.com, and @vcontractor.co.za. The user will be asked to change this password after login.
              </p>
            </motion.div>
          )}

          {/* Users table */}
          <div className="bg-white border border-[#E5E5E5] rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-[#E5E5E5] flex items-center gap-2">
              <Users size={13} className="text-[#8C8C8C]" />
              <span className="text-[12px] font-600 text-[#1A1A1A]">Users</span>
              <span className="text-[11px] text-[#8C8C8C] ml-auto">{data?.count ?? 0} accounts</span>
            </div>

            {isLoading ? (
              <div className="divide-y divide-[#F0F0F0]">
                {[1, 2, 3].map(i => (
                  <div key={i} className="px-4 py-3 flex items-center gap-3">
                    <div className="w-8 h-8 skeleton rounded-full" />
                    <div className="flex-1 space-y-1.5">
                      <div className="h-3 skeleton rounded w-40" />
                      <div className="h-3 skeleton rounded w-24" />
                    </div>
                  </div>
                ))}
              </div>
            ) : !data?.users.length ? (
              <EmptyState title="No users found" sub="Create the first user using the button above" icon={<Users size={28} />} />
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr>
                    {['User', 'Role', 'Status', 'Last login', 'Actions'].map(h => (
                      <th key={h} className={cn(
                        'text-[10px] font-600 text-[#8C8C8C] uppercase tracking-[0.5px] py-2 px-4 bg-[#FAFAFA] border-b border-[#E5E5E5]',
                        h === 'Actions' ? 'text-right' : 'text-left',
                      )}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.users.map((u, i) => (
                    <motion.tr
                      key={u.id}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: i * 0.04 }}
                      className={cn(
                        'border-b border-[#F0F0F0] hover:bg-[#F5F5F5] transition-colors',
                        u.status !== 'ACTIVE' ? 'opacity-60' : '',
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2.5">
                          <div className="w-7 h-7 bg-[#FFF0F0] border border-[#F5B8B8] rounded-full flex items-center justify-center text-[10px] font-700 text-[#CC0000] flex-shrink-0">
                            {u.email.split('@')[0].slice(0, 2).toUpperCase()}
                          </div>
                          <div>
                            <div className="text-[12px] font-500 text-[#1A1A1A]">{u.email}</div>
                            {u.full_name && (
                              <div className="text-[10px] text-[#8C8C8C] mt-0.5">{u.full_name}</div>
                            )}
                            {u.must_change_password && (
                              <div className="text-[10px] text-[#C47000] flex items-center gap-0.5 mt-0.5">
                                <AlertCircle size={9} /> Must change password
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {u.role === 'SUPER_ADMIN' ? (
                          <Tag variant="danger">{ROLE_LABELS[u.role]}</Tag>
                        ) : (
                          <select
                            value={u.role}
                            onChange={e => roleMutation.mutate({ id: u.id, role: e.target.value })}
                            className="text-[11px] border border-[#E5E5E5] rounded px-1.5 py-0.5 bg-white cursor-pointer outline-none"
                          >
                            {ROLES.map(r => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                          </select>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Tag variant={u.status === 'ACTIVE' ? 'success' : 'danger'}>{u.status}</Tag>
                      </td>
                      <td className="px-4 py-3 text-[11px] text-[#5C5C5C]">
                        {u.last_login_at ? fmtRelative(u.last_login_at) : 'Never'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-end gap-1">
                          {u.role !== 'SUPER_ADMIN' && (
                            <>
                              <Btn
                                variant="ghost" size="sm"
                                title="Reset password"
                                onClick={() => openResetPasswordDialog({ id: u.id, email: u.email })}
                              >
                                <KeyRound size={11} />
                              </Btn>
                              <Btn
                                variant="ghost" size="sm"
                                title={u.status === 'ACTIVE' ? 'Deactivate' : 'Activate'}
                                onClick={() => statusMutation.mutate({
                                  id: u.id,
                                  status: u.status === 'ACTIVE' ? 'DISABLED' : 'ACTIVE',
                                })}
                              >
                                {u.status === 'ACTIVE'
                                  ? <UserX size={11} className="text-[#CC0000]" />
                                  : <UserCheck size={11} className="text-[#0A7A0A]" />
                                }
                              </Btn>
                              {canDeleteUsers && <Btn
                                variant="ghost" size="sm"
                                title="Delete user"
                                onClick={() => setDeleteTarget({ id: u.id, email: u.email })}
                              >
                                <Trash2 size={11} className="text-[#CC0000]" />
                              </Btn>}
                            </>
                          )}
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        <AnimatePresence>
          {resetTarget && (
            <motion.div
              className="fixed inset-0 z-[90] flex items-center justify-center bg-black/35 px-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onMouseDown={closeResetPasswordDialog}
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
                    <KeyRound size={14} />
                  </div>
                  <div className="min-w-0">
                    <div className="text-[13px] font-600 text-[#1A1A1A]">Reset temporary password</div>
                    <div className="text-[11px] text-[#8C8C8C] truncate">{resetTarget.email}</div>
                  </div>
                  <button
                    type="button"
                    onClick={closeResetPasswordDialog}
                    className="ml-auto w-7 h-7 rounded-md flex items-center justify-center text-[#8C8C8C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                    title="Close"
                  >
                    <X size={14} />
                  </button>
                </div>

                <div className="p-4 space-y-3">
                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">New temporary password</label>
                    <div className="relative">
                      <input
                        autoFocus
                        type={showResetPassword ? 'text' : 'password'}
                        value={resetPassword}
                        onChange={event => setResetPassword(event.target.value)}
                        placeholder="Temporary password"
                        className="h-9 w-full pl-2.5 pr-9 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000]"
                      />
                      <button
                        type="button"
                        onClick={() => setShowResetPassword(value => !value)}
                        className="absolute right-2 top-1/2 -translate-y-1/2 text-[#8C8C8C] hover:text-[#1A1A1A]"
                        title={showResetPassword ? 'Hide password' : 'Show password'}
                      >
                        {showResetPassword ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                    {resetPassword && !resetPasswordIsReady && (
                      <span className="text-[10px] text-[#CC0000]">Use at least {TEMP_PASSWORD_MIN_LENGTH} characters.</span>
                    )}
                  </div>

                  <div className="flex flex-col gap-1">
                    <label className="text-[10px] font-600 text-[#8C8C8C] uppercase tracking-wide">Confirm password</label>
                    <input
                      type={showResetPassword ? 'text' : 'password'}
                      value={resetPasswordConfirm}
                      onChange={event => setResetPasswordConfirm(event.target.value)}
                      placeholder="Repeat password"
                      className="h-9 w-full px-2.5 text-[12px] border border-[#E5E5E5] rounded-md outline-none focus:border-[#E60000]"
                    />
                    {resetPasswordConfirm && !resetPasswordsMatch && (
                      <span className="text-[10px] text-[#CC0000]">Passwords must match.</span>
                    )}
                  </div>

                  <div className="rounded-md border border-[#FFE0A3] bg-[#FFFBF0] px-3 py-2 text-[11px] text-[#8A5A00]">
                    The user will be asked to create their own password after signing in.
                  </div>
                </div>

                <div className="px-4 py-3 border-t border-[#E5E5E5] flex justify-end gap-2">
                  <Btn variant="ghost" size="sm" onClick={closeResetPasswordDialog}>
                    Cancel
                  </Btn>
                  <Btn
                    variant="primary"
                    size="sm"
                    loading={resetMutation.isPending}
                    disabled={!canResetPassword || resetMutation.isPending}
                    onClick={handleResetPassword}
                  >
                    Reset password
                  </Btn>
                </div>
              </motion.div>
            </motion.div>
          )}
        </AnimatePresence>

        <AnimatePresence>
          {canDeleteUsers && deleteTarget && (
            <motion.div
              className="fixed inset-0 z-[90] flex items-center justify-center bg-black/35 px-4"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onMouseDown={() => setDeleteTarget(null)}
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
                    <div className="text-[13px] font-600 text-[#1A1A1A]">Delete user</div>
                    <div className="text-[11px] text-[#8C8C8C] truncate">{deleteTarget.email}</div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(null)}
                    className="ml-auto w-7 h-7 rounded-md flex items-center justify-center text-[#8C8C8C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A]"
                    title="Close"
                  >
                    <X size={14} />
                  </button>
                </div>

                <div className="p-4 space-y-3">
                  <p className="text-[12px] text-[#3A3A3A]">
                    This removes the user from User Management and revokes their active sessions.
                  </p>
                  <div className="rounded-md border border-[#F5B8B8] bg-[#FFF0F0] px-3 py-2 text-[11px] text-[#A00000]">
                    The account can be restored later by creating the same email address again with a new temporary password.
                  </div>
                </div>

                <div className="px-4 py-3 border-t border-[#E5E5E5] flex justify-end gap-2">
                  <Btn variant="ghost" size="sm" onClick={() => setDeleteTarget(null)}>
                    Cancel
                  </Btn>
                  <Btn
                    variant="danger"
                    size="sm"
                    loading={deleteMutation.isPending}
                    disabled={deleteMutation.isPending}
                    onClick={handleDeleteUser}
                  >
                    <Trash2 size={11} /> Delete user
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
