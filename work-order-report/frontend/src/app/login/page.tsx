'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { motion } from 'framer-motion'
import { useAuth } from '@/lib/auth-context'
import { ApiError, isBackendUnavailableError } from '@/lib/api'
import { cn } from '@/lib/utils'
import { VodacomLogo } from '@/components/ui/VodacomLogo'

export default function LoginPage() {
  const { login } = useAuth()
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = await login(email, password)
      if (res.user.must_change_password) {
        router.push('/admin/change-password')
      } else {
        router.push('/workspace')
      }
    } catch (err) {
      if (isBackendUnavailableError(err)) {
        setError(err.message)
        return
      }

      const msg = err instanceof Error ? err.message : 'Login failed'
      if (msg.includes('401') || msg.includes('Unauthorized') || msg.toLowerCase().includes('invalid')) {
        const reference = err instanceof ApiError && err.requestId ? ` Reference: ${err.requestId}` : ''
        setError(`Invalid email or password. Contact the system administrator for access.${reference}`)
      } else {
        setError(msg)
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#F5F5F5] flex flex-col">
      {/* Vodacom red header strip */}
      <div className="h-1.5 bg-[#E60000]" />

      <div className="flex-1 flex items-center justify-center p-6">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: 'easeOut' }}
          className="w-full max-w-[380px]"
        >
          {/* Logo */}
          <div className="flex flex-col items-center mb-8 gap-3">
            <VodacomLogo width={160} />
            <div className="text-[12px] text-[#8C8C8C] tracking-wide uppercase font-500">
              INTEL Operations
            </div>
          </div>

          {/* Card */}
          <div className="bg-white border border-[#E5E5E5] rounded-lg shadow-sm overflow-hidden">
            <div className="px-6 pt-6 pb-2 border-b border-[#F0F0F0]">
              <h1 className="text-[17px] font-600 text-[#1A1A1A] tracking-tight">Sign in</h1>
              <p className="text-[12px] text-[#8C8C8C] mt-0.5">Use your Vodacom email address</p>
            </div>

            <form onSubmit={handleSubmit} className="px-6 py-5 flex flex-col gap-4">
              {/* Email */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-500 text-[#5C5C5C] uppercase tracking-wide">
                  Email
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={e => setEmail(e.target.value)}
                  placeholder="name@vodacom.co.za"
                  required
                  autoFocus
                  className={cn(
                    'h-9 px-3 text-[13px] border rounded-md outline-none transition-colors',
                    'border-[#D0D0D0] bg-white text-[#1A1A1A] placeholder:text-[#BCBCBC]',
                    'focus:border-[#E60000] focus:ring-2 focus:ring-[#E60000]/10',
                  )}
                />
              </div>

              {/* Password */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[11px] font-500 text-[#5C5C5C] uppercase tracking-wide">
                  Password
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••"
                  required
                  className={cn(
                    'h-9 px-3 text-[13px] border rounded-md outline-none transition-colors',
                    'border-[#D0D0D0] bg-white text-[#1A1A1A] placeholder:text-[#BCBCBC]',
                    'focus:border-[#E60000] focus:ring-2 focus:ring-[#E60000]/10',
                  )}
                />
              </div>

              {/* Error */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="text-[12px] text-[#CC0000] bg-[#FFF0F0] border border-[#F5B8B8] rounded-md px-3 py-2"
                >
                  {error}
                </motion.div>
              )}

              {/* Submit */}
              <button
                type="submit"
                disabled={loading}
                className={cn(
                  'h-9 rounded-md text-[13px] font-500 text-white transition-all',
                  'bg-[#E60000] hover:bg-[#B30000] active:scale-[0.99]',
                  'disabled:opacity-60 disabled:cursor-not-allowed',
                  'flex items-center justify-center gap-2',
                )}
              >
                {loading ? (
                  <>
                    <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    Signing in…
                  </>
                ) : 'Sign in'}
              </button>
            </form>
          </div>

          <p className="text-center text-[11px] text-[#8C8C8C] mt-5">
            No account? Contact the system administrator for access.
          </p>
        </motion.div>
      </div>
    </div>
  )
}
