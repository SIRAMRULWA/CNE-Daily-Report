import type { Role, User } from '@/types'

const OPERATIONAL_ADMIN_ROLES: readonly Role[] = ['MANAGER', 'ADMIN', 'SUPER_ADMIN']

export function canManageOperations(user: Pick<User, 'role'> | null | undefined): boolean {
  return Boolean(user && OPERATIONAL_ADMIN_ROLES.includes(user.role))
}

export function isSuperAdmin(user: Pick<User, 'role'> | null | undefined): boolean {
  return user?.role === 'SUPER_ADMIN'
}
