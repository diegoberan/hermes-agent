import { useEffect, useState } from 'react'

import { Button } from '@/components/ui/button'
import type { LocalServiceDescriptor } from '@/global'
import { useI18n } from '@/i18n'
import { Cpu, Loader2, Play, Square } from '@/lib/icons'
import { notifyError } from '@/store/notifications'

import { EmptyState, ListRow, LoadingState, Pill, SectionHeading, SettingsContent } from './primitives'

type ServiceStatus = { healthy: boolean; running: boolean }
type PendingAction = 'start' | 'stop' | null

// Poll interval for the status dots -- fast enough to feel live while the
// panel is open, cheap enough (one HTTP GET per service) not to matter.
const STATUS_POLL_MS = 4000

export function LocalServicesSettings() {
  const { t } = useI18n()
  const bridge = window.hermesDesktop?.localServices

  const [loading, setLoading] = useState(true)
  const [services, setServices] = useState<LocalServiceDescriptor[]>([])
  const [statuses, setStatuses] = useState<Record<string, ServiceStatus>>({})
  const [pending, setPending] = useState<Record<string, PendingAction>>({})

  useEffect(() => {
    if (!bridge) {
      setLoading(false)

      return
    }

    let cancelled = false

    void bridge.list().then(list => {
      if (!cancelled) {
        setServices(list)
        setLoading(false)
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
    const interval = setInterval(poll, STATUS_POLL_MS)

    return () => {
      cancelled = true
      clearInterval(interval)
    }
  }, [bridge, services])

  const toggle = async (svc: LocalServiceDescriptor) => {
    if (!bridge) {
      return
    }

    const running = statuses[svc.id]?.running
    const action: 'start' | 'stop' = running ? 'stop' : 'start'
    setPending(prev => ({ ...prev, [svc.id]: action }))

    try {
      const result = action === 'start' ? await bridge.start(svc.id) : await bridge.stop(svc.id)

      if (!result.ok) {
        notifyError(
          new Error(result.error || 'unknown error'),
          action === 'start' ? t.settings.localServices.startFailed : t.settings.localServices.stopFailed
        )

        return
      }

      const next = await bridge.status(svc.id)
      setStatuses(prev => ({ ...prev, [svc.id]: next }))
    } finally {
      setPending(prev => ({ ...prev, [svc.id]: null }))
    }
  }

  if (!bridge) {
    return (
      <SettingsContent>
        <EmptyState
          description={t.settings.localServices.unavailableDesc}
          title={t.settings.localServices.unavailableTitle}
        />
      </SettingsContent>
    )
  }

  if (loading) {
    return (
      <SettingsContent>
        <LoadingState label={t.settings.localServices.loading} />
      </SettingsContent>
    )
  }

  return (
    <SettingsContent>
      <SectionHeading icon={Cpu} title={t.settings.localServices.title} />
      <p className="mb-3 text-[length:var(--conversation-caption-font-size)] leading-(--conversation-caption-line-height) text-(--ui-text-tertiary)">
        {t.settings.localServices.intro}
      </p>
      {services.length === 0 ? (
        <EmptyState description={t.settings.localServices.empty} title={t.settings.localServices.title} />
      ) : (
        <div className="divide-y divide-border/30">
          {services.map(svc => {
            const status = statuses[svc.id]
            const busy = pending[svc.id]

            const statusLabel = status?.healthy
              ? t.settings.localServices.statusHealthy
              : status?.running
                ? t.settings.localServices.statusUnhealthy
                : t.settings.localServices.statusStopped

            return (
              <ListRow
                action={
                  <Button
                    disabled={Boolean(busy)}
                    onClick={() => void toggle(svc)}
                    size="sm"
                    variant={status?.running ? 'outline' : 'default'}
                  >
                    {busy ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : status?.running ? (
                      <Square className="size-3.5" />
                    ) : (
                      <Play className="size-3.5" />
                    )}
                    {busy === 'start'
                      ? t.settings.localServices.starting
                      : busy === 'stop'
                        ? t.settings.localServices.stopping
                        : status?.running
                          ? t.settings.localServices.stop
                          : t.settings.localServices.start}
                  </Button>
                }
                description={svc.autoStart ? t.settings.localServices.autoStartHint : undefined}
                hint={svc.healthUrl}
                key={svc.id}
                title={
                  <span className="flex items-center gap-2">
                    {svc.name}
                    <Pill tone={status?.healthy ? 'primary' : 'muted'}>{statusLabel}</Pill>
                  </span>
                }
              />
            )
          })}
        </div>
      )}
    </SettingsContent>
  )
}
