import { $gateway } from '@/store/gateway'

// Recomputes this Desktop's speech capability from the Local Services
// registry and sends it to the Gateway. Called once on gateway.ready
// (gateway-event.ts) and again whenever a `kind: "speech"` service is
// toggled from either Local Services surface (Settings panel, statusbar
// popover) -- the Gateway's decision of whether to route a synthesis
// request here should never be more stale than "the last time you flipped
// the switch," not just "whatever was true when the connection opened."
// $gateway.set() happens in setActive() (store/gateway.ts), which is not
// guaranteed to have run yet the instant gateway.ready's handler fires --
// that event is the server's first message after ws.accept(), and the
// primary connection's own bookkeeping (setPrimaryGateway then setActive)
// can still be mid-flight at that exact tick. A few short retries is
// simpler and more robust than chasing the exact ordering.
async function waitForGateway(): Promise<ReturnType<typeof $gateway.get>> {
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const gateway = $gateway.get()

    if (gateway) {
      return gateway
    }

    await new Promise(resolve => setTimeout(resolve, 200))
  }

  return $gateway.get()
}

export async function announceSpeechCapabilities(): Promise<void> {
  const bridge = window.hermesDesktop?.localServices

  if (!bridge) {
    return
  }

  const gateway = await waitForGateway()

  if (!gateway) {
    return
  }

  const services = await bridge.list()
  const speechServices = services.filter(svc => svc.kind === 'speech')

  let available = false
  let localUrl: string | undefined
  let voices: string[] = []

  for (const svc of speechServices) {
    const status = await bridge.status(svc.id)

    if (status.healthy) {
      available = true
      const speechCaps = svc.capabilities?.speech as { localUrl?: string; voices?: string[] } | undefined
      localUrl = speechCaps?.localUrl
      voices = speechCaps?.voices ?? []

      break
    }
  }

  void gateway.request('hermes.capabilities.announce', {
    speech: { available, localUrl, voices }
  })
}
