'use client'

import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { RefreshCw, ServerCrash, X } from 'lucide-react'
import { BACKEND_UNAVAILABLE_EVENT } from '@/lib/api'
import { Btn } from '@/components/ui'

const DISMISS_MS = 60_000

export function BackendUnavailableDialog() {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [message, setMessage] = useState('We tried to connect a few times but the backend is not responding. Please try again later.')
  const [retrying, setRetrying] = useState(false)
  const dismissedUntilRef = useRef(0)

  useEffect(() => {
    function handleUnavailable(event: Event) {
      if (Date.now() < dismissedUntilRef.current) return
      const detail = (event as CustomEvent<{ message?: string }>).detail
      setMessage(detail?.message || 'We tried to connect a few times but the backend is not responding. Please try again later.')
      setOpen(true)
    }

    window.addEventListener(BACKEND_UNAVAILABLE_EVENT, handleUnavailable)
    return () => window.removeEventListener(BACKEND_UNAVAILABLE_EVENT, handleUnavailable)
  }, [])

  if (!open) return null

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="backend-unavailable-title"
      className="fixed inset-0 z-[100] flex items-center justify-center bg-black/35 px-4"
    >
      <div className="w-full max-w-[420px] bg-white border border-[#E5E5E5] rounded-lg shadow-[0_18px_50px_rgba(0,0,0,0.22)] overflow-hidden">
        <div className="flex items-start gap-3 p-4 border-b border-[#F0F0F0]">
          <div className="w-9 h-9 rounded-md bg-[#FFF0F0] border border-[#F5B8B8] text-[#CC0000] flex items-center justify-center flex-shrink-0">
            <ServerCrash size={17} />
          </div>
          <div className="min-w-0 flex-1">
            <h2 id="backend-unavailable-title" className="text-[14px] font-600 text-[#1A1A1A] leading-tight">
              Service temporarily unavailable
            </h2>
            <p className="text-[12px] text-[#5C5C5C] mt-1 leading-5">
              {message}
            </p>
          </div>
          <button
            type="button"
            aria-label="Dismiss"
            onClick={() => {
              dismissedUntilRef.current = Date.now() + DISMISS_MS
              setOpen(false)
            }}
            className="w-7 h-7 rounded-md text-[#8C8C8C] hover:bg-[#F5F5F5] hover:text-[#1A1A1A] flex items-center justify-center"
          >
            <X size={14} />
          </button>
        </div>
        <div className="p-4 flex items-center justify-end gap-2">
          <Btn
            variant="default"
            size="sm"
            onClick={() => {
              dismissedUntilRef.current = Date.now() + DISMISS_MS
              setOpen(false)
            }}
          >
            Close
          </Btn>
          <Btn
            variant="primary"
            size="sm"
            loading={retrying}
            onClick={async () => {
              setRetrying(true)
              await queryClient.invalidateQueries()
              setRetrying(false)
              setOpen(false)
            }}
          >
            <RefreshCw size={12} />
            Try again
          </Btn>
        </div>
      </div>
    </div>
  )
}
