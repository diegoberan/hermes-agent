import { useEffect, useState } from 'react'

import { StatusDot, type StatusTone } from '@/components/status-dot'
import { Button } from '@/components/ui/button'
import type { LocalServiceDescriptor } from '@/global'
import { useI18n } from '@/i18n'
import { Loader2, Play, Square } from '@/lib/icons'

type ServiceStatus = { healthy: boolean; running: boolean }
type PendingAction = 'start' | 'stop' | null

const POLL_MS = 4000

function toneFor(status: ServiceStatus | undefined): StatusTone {
  if (status?.healthy) {
    return 'good'
  }

  return status?.running ? 'warn' : 'muted'
}

// Compact version of Settings > Local Services for the statusbar popover --
// same bridge/data, no navigation required to flip a service on or off.
export function LocalServicesMenuPanel() {
  const { t } = useI18n()
  const copy = t.settings.localServices
  const bridge = window.hermesDesktop?.localServices

  const [services, setServices] = useState<LocalServiceDescriptor[]>([])
  const [statuses, setStatuses] = useState<Record<string, ServiceStatus>>({})
  const [pending, setPending] = useState<Record<string, PendingAction>>({})

  useEffect(() => {
    if (!bridge) {
      return
    }

    let cancelled = false

    void bridge.list().then(list => {
      if (!cancelled) {
        setServices(list)
      }
    })

    return () => {
      cancelled = true
    }
  }, [bridge])

  useEffect(() => {
    if (!bridge || services.length === 0) {
      return
    }

    let cancelled = false

    const poll = () => {
      void Promise.all(services.map(async svc => [svc.id, await bridge.status(svc.id)] as const)).then(entries => {
        if (!cancelled) {
          setStatuses(Object.fromEntries(entries))
        }
      })
    }

    poll()
    const interval = setInterval(poll, POLL_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [bridge, services])

  const toggle = async (svc: LocalServiceDescriptor) => {
    if (!bridge) {
      return
    }

    const action: 'start' | 'stop' = statuses[svc.id]?.running ? 'stop' : 'start'
    setPending(prev => ({ ...prev, [svc.id]: action }))

    try {
      const result = action === 'start' ? await bridge.start(svc.id) : await bridge.stop(svc.id)

      if (result.ok) {
        const next = await bridge.status(svc.id)
        setStatuses(prev => ({ ...prev, [svc.id]: next }))
      }
    } finally {
      setPending(prev => ({ ...prev, [svc.id]: null }))
    }
  }

  if (!bridge || services.length === 0) {
    return null
  }

  return (
    <div className="min-w-56 text-sm">
      <div className="px-3 py-2 text-[0.62rem] font-semibold uppercase tracking-[0.14em] text-muted-foreground/80">
        {copy.title}
      </div>
      <ul className="px-1 pb-1.5">
        {services.map(svc => {
          const status = statuses[svc.id]
          const busy = pending[svc.id]

          return (
            <li className="flex items-center justify-between gap-2 rounded-md px-2 py-1.5" key={svc.id}>
              <span className="flex min-w-0 items-center gap-1.5 truncate text-xs">
                <StatusDot tone={toneFor(status)} />
                <span className="truncate">{svc.name}</span>
              </span>
              <Button
                className="h-6 shrink-0 px-1.5 text-[0.68rem]"
                disabled={Boolean(busy)}
                onClick={() => void toggle(svc)}
                size="xs"
                variant="ghost"
              >
                {busy ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : status?.running ? (
                  <Square className="size-3" />
                ) : (
                  <Play className="size-3" />
                )}
              </Button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
