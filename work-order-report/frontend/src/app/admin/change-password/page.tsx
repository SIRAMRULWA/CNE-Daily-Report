'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { authApi } from '@/lib/api'
import { cn } from '@/lib/utils'
import { KeyRound, CheckCircle2, Eye, EyeOff } from 'lucide-react'
import { Btn } from '@/components/ui'

export default function ChangePasswordPage() {
  const router = useRouter()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showCurrent, setShowCurrent] = useState(false)
  const [showNext, setShowNext] = useState(false)
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')

  const mismatch = next && confirm && next !== confirm
  const weak = next.length > 0 && next.length < 12
  const strength = next.length === 0 ? 0 : next.length < 8 ? 1 : next.length < 12 ? 2 : /[A-Z]/.test(next) && /[0-9]/.test(next) ? 4 : 3

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    const currentPassword = current.trim()
    const nextPassword = next.trim()
    const confirmPassword = confirm.trim()

    if (nextPassword !== confirmPassword) { setError('Passwords do not match'); return }
    if (nextPassword.length < 12) { setError('Password must be at least 12 characters'); return }
    setLoading(true)
    setError('')
    try {
      await authApi.changePassword(currentPassword, nextPassword)
      setDone(true)
      setTimeout(() => router.push('/workspace'), 2000)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to change password')
    } finally {
      setLoading(false)
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-[#F5F5F5] flex items-center justify-center">
        <motion.div
          initial={{ scale: 0.9, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          className="text-center"
        >
          <div className="w-16 h-16 bg-[#EDF7ED] border-2 border-[#B8DFB8] rounded-full flex items-center justify-center mx-auto mb-4">
            <CheckCircle2 size={32} className="text-[#16A34A]" />
          </div>
          <div className="text-[15px] font-600 text-[#1A1A1A]">Password changed</div>
          <div className="text-[12px] text-[#8C8C8C] mt-1">Redirecting to Operations Console...</div>
        </motion.div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-[#F5F5F5] flex flex-col">
      <div className="h-1.5 bg-[#E60000]" />
      <div className="flex-1 flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          className="w-full max-w-[400px]"
        >
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8">
            <div className="w-10 h-10 rounded-full bg-[#E60000] flex items-center justify-center">
              <KeyRound size={18} className="text-white" />
            </div>
            <div>
              <div className="font-bold text-[#1A1A1A] text-[15px]">Change password</div>
              <div className="text-[12px] text-[#5C5C5C]">Required before continuing</div>
            </div>
          </div>

          <div className="bg-[#FFF8E6] border border-[#F5D580] rounded-lg px-4 py-3 mb-5 text-[12px] text-[#C47000]">
            Your account requires a password change before you can access the platform.
          </div>

          <div className="bg-white border border-[#E5E5E5] rounded-lg shadow-sm overflow-hidden">
            <div className="px-6 pt-5 pb-2 border-b border-[#F0F0F0]">
              <h1 className="text-[15px] font-600 text-[#1A1A1A]">Set new password</h1>
              <p className="text-[11px] text-[#8C8C8C] mt-0.5">Minimum 12 characters. Use a mix of letters, numbers, and symbols.</p>
            </div>

            <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4">
              {/* Current password */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-500 text-[#5C5C5C] uppercase tracking-wide">
                  Current (temporary) password
                </label>
                <div className="relative">
                  <input
                    type={showCurrent ? 'text' : 'password'}
                    value={current}
                    onChange={e => setCurrent(e.target.value)}
                    required
                    autoFocus
                    className="h-9 w-full px-3 pr-9 text-[13px] border border-[#D0D0D0] rounded-md outline-none focus:border-[#E60000] focus:ring-2 focus:ring-[#E60000]/10"
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrent(v => !v)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8C8C8C] hover:text-[#5C5C5C]"
                  >
                    {showCurrent ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
              </div>

              {/* New password */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-500 text-[#5C5C5C] uppercase tracking-wide">
                  New password
                </label>
                <div className="relative">
                  <input
                    type={showNext ? 'text' : 'password'}
                    value={next}
                    onChange={e => setNext(e.target.value)}
                    required
                    className={cn(
                      'h-9 w-full px-3 pr-9 text-[13px] border rounded-md outline-none transition-colors',
                      weak ? 'border-[#F59E0B] focus:ring-2 focus:ring-[#F59E0B]/20' : 'border-[#D0D0D0] focus:border-[#E60000] focus:ring-2 focus:ring-[#E60000]/10',
                    )}
                  />
                  <button
                    type="button"
                    onClick={() => setShowNext(v => !v)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[#8C8C8C] hover:text-[#5C5C5C]"
                  >
                    {showNext ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>
                {/* Strength bar */}
                {next.length > 0 && (
                  <div className="flex items-center gap-1.5">
                    <div className="flex gap-1 flex-1">
                      {[1, 2, 3, 4].map(i => (
                        <div
                          key={i}
                          className={cn(
                            'h-1 flex-1 rounded-full transition-colors duration-300',
                            i <= strength
                              ? strength === 1 ? 'bg-[#E60000]'
                              : strength === 2 ? 'bg-[#F59E0B]'
                              : strength === 3 ? 'bg-[#22C55E]'
                              : 'bg-[#16A34A]'
                              : 'bg-[#E5E5E5]',
                          )}
                        />
                      ))}
                    </div>
                    <span className={cn(
                      'text-[10px] font-500',
                      strength === 1 ? 'text-[#E60000]' :
                      strength === 2 ? 'text-[#C47000]' :
                      strength >= 3 ? 'text-[#16A34A]' : 'text-[#8C8C8C]',
                    )}>
                      {strength === 1 ? 'Weak' : strength === 2 ? 'Fair' : strength === 3 ? 'Good' : strength === 4 ? 'Strong' : ''}
                    </span>
                  </div>
                )}
              </div>

              {/* Confirm password */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-500 text-[#5C5C5C] uppercase tracking-wide">
                  Confirm new password
                </label>
                <input
                  type="password"
                  value={confirm}
                  onChange={e => setConfirm(e.target.value)}
                  required
                  className={cn(
                    'h-9 px-3 text-[13px] border rounded-md outline-none transition-colors',
                    mismatch ? 'border-[#E60000] focus:ring-2 focus:ring-[#E60000]/20' : 'border-[#D0D0D0] focus:border-[#E60000] focus:ring-2 focus:ring-[#E60000]/10',
                  )}
                />
                {mismatch && <p className="text-[11px] text-[#CC0000]">Passwords do not match</p>}
              </div>

              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-[12px] text-[#CC0000] bg-[#FFF0F0] border border-[#F5B8B8] rounded-md px-3 py-2"
                >
                  {error}
                </motion.div>
              )}

              <Btn
                variant="primary"
                loading={loading}
                disabled={!!mismatch || !!weak || !current || !next || !confirm}
                className="w-full justify-center h-9 text-[13px]"
              >
                Set new password
              </Btn>
            </form>
          </div>
        </motion.div>
      </div>
    </div>
  )
}
