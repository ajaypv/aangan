import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from '@/api'
import { isVoiceActive, useVoiceState, voice as voiceController, type VoiceState } from '@/lib/voiceSession'
import { clearSetup } from '@/lib/household'
import type { AppConfig, Member, Snapshot, ToolOutcome, ToolSpec } from '@/types'
import { useMe } from './me'

/** Four places: Home, Ask (the assistant), Family, Settings. `view` picks a section inside one (Ask: 'did'; Family: 'schedule'). */
export type Tab = 'home' | 'ask' | 'family' | 'settings'
export const TABS: Tab[] = ['home', 'ask', 'family', 'settings']
/** Old links (?tab=talk) still land somewhere sensible. */
const LEGACY_TABS: Record<string, { tab: Tab; view?: string }> = {
  talk: { tab: 'ask' },
  activity: { tab: 'ask', view: 'did' },
  calendar: { tab: 'family', view: 'schedule' },
}

export interface Household {
  /** False until the first family member exists. */
  exists: boolean
  /** True when the family on screen is the built-in demo family. */
  demo: boolean
}

export interface Toast {
  id: number
  kind: 'info' | 'success' | 'error'
  text: string
}

interface Outbox {
  member_id: string
  text: string
}

interface AppContextValue {
  snap: Snapshot | null
  config: AppConfig | null
  tools: ToolSpec[]
  loading: boolean
  loadError: string | null
  busy: boolean
  online: boolean
  /** The family member using this device (localStorage `aangan.me`), only when they are in the household; otherwise null. */
  me: string | null
  /** Same as `me`. The name earlier code uses. */
  personaId: string | null
  /** The family member using this device, or null until someone has chosen. */
  member: Member | null
  household: Household
  tab: Tab
  view: string | null
  outbox: Outbox | null
  voice: VoiceState
  /** A call is being set up, live, or ending. */
  voiceActive: boolean
  toasts: Toast[]
  setTab: (t: Tab, view?: string | null) => void
  /** Choose who is using this device (ends any voice call first). Returns false, changing nothing, when that person is not in the household. */
  setMe: (id: string) => boolean
  /** Forget who is using this device, which shows the profile picker again. */
  clearMe: () => void
  /** Same as `setMe`. The name earlier code uses. */
  setPersona: (id: string) => void
  reload: () => void
  say: (text: string) => Promise<void>
  trigger: (agent: string, name: string, label: string) => Promise<void>
  callTool: (agent: string, tool: string, args: Record<string, unknown>, doneText: string) => Promise<boolean>
  /** Like `callTool` but shows no toast: forms use it to put the outcome (or the problem) on the form itself. */
  runTool: (agent: string, tool: string, args: Record<string, unknown>) => Promise<ToolOutcome>
  setChaos: (enabled: boolean) => Promise<void>
  /** Back to the starting point of the current mode (the example family while it is loaded). */
  reset: () => Promise<void>
  /** Load the built-in example family. Resolves to the new snapshot, or null when it failed. */
  loadDemo: () => Promise<Snapshot | null>
  /** Empty the household and forget who uses this device. Resolves to whether it worked. */
  resetHousehold: () => Promise<boolean>
  startVoice: () => Promise<void>
  stopVoice: () => Promise<void>
  toggleMute: () => Promise<void>
  interruptVoice: () => Promise<void>
  dismissVoiceError: () => void
  notify: (kind: Toast['kind'], text: string) => void
  dismissToast: (id: number) => void
}

const Ctx = createContext<AppContextValue | null>(null)

export function useApp() {
  const v = useContext(Ctx)
  if (!v) throw new Error('useApp must be used inside <AppProvider>')
  return v
}

const initialRoute = (): { tab: Tab; view: string | null } => {
  const params = new URLSearchParams(location.search)
  const t = params.get('tab') ?? ''
  const view = params.get('view')
  if (TABS.includes(t as Tab)) return { tab: t as Tab, view }
  const legacy = LEGACY_TABS[t]
  // Ask is where the app starts once someone is set up.
  return legacy ? { tab: legacy.tab, view: view ?? legacy.view ?? null } : { tab: 'ask', view: null }
}

const messageOf = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong')

export function AppProvider({ children }: { children: ReactNode }) {
  const [snap, setSnap] = useState<Snapshot | null>(null)
  const [config, setConfig] = useState<AppConfig | null>(null)
  const [tools, setTools] = useState<ToolSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [busyCount, setBusyCount] = useState(0)
  const [online, setOnline] = useState(() => navigator.onLine)
  const { me: storedMe, setMe: storeMe, clearMe: forgetMe, clearOnboarded } = useMe()
  const [route, setRoute] = useState(initialRoute)
  const tab = route.tab
  const [outbox, setOutbox] = useState<Outbox | null>(null)
  const voice = useVoiceState()
  const voiceActive = isVoiceActive(voice)
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextToast = useRef(1)

  // Who is using this device counts only while they are still in the household.
  const member = (snap && storedMe ? snap.members.find((m) => m.id === storedMe) : undefined) ?? null
  const personaId = member?.id ?? null
  const household = useMemo<Household>(() => {
    const h = snap?.household
    return { exists: h?.exists ?? (snap?.members.length ?? 0) > 0, demo: h?.demo ?? false }
  }, [snap])

  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), [])
  const notify = useCallback(
    (kind: Toast['kind'], text: string) => {
      const id = nextToast.current++
      setToasts((t) => [...t.slice(-3), { id, kind, text }])
      window.setTimeout(() => dismissToast(id), kind === 'error' ? 8000 : 4500)
    },
    [dismissToast],
  )

  const load = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const [s, c, t] = await Promise.all([api.state(), api.config(), api.tools()])
      setSnap(s)
      setConfig(c)
      setTools(t)
    } catch (e) {
      setLoadError(messageOf(e))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  // Keep the screen in step with the backend: quickly during a live voice call (the agent acts through the backend), slowly otherwise.
  useEffect(() => {
    if (!snap || !online) return
    const every = voice.phase === 'live' || voice.phase === 'waiting-agent' ? 1500 : 8000
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return
      api.state().then(setSnap).catch(() => {})
    }, every)
    return () => window.clearInterval(id)
  }, [snap !== null, online, voice.phase]) // eslint-disable-line react-hooks/exhaustive-deps

  const guard = useCallback(
    async <T,>(fn: () => Promise<T>): Promise<T | null> => {
      setBusyCount((n) => n + 1)
      try {
        return await fn()
      } catch (e) {
        notify('error', messageOf(e))
        return null
      } finally {
        setBusyCount((n) => n - 1)
      }
    },
    [notify],
  )

  const stopVoice = useCallback(() => voiceController.stop(), [])

  const setMe = useCallback(
    (id: string): boolean => {
      if (!snap?.members.some((m) => m.id === id)) return false
      if (id === personaId) return true
      // The call belongs to one speaker: end it before switching.
      if (voiceController.getState().phase !== 'idle') void voiceController.stop()
      storeMe(id)
      return true
    },
    [snap, personaId, storeMe],
  )

  const clearMe = useCallback(() => {
    if (voiceController.getState().phase !== 'idle') void voiceController.stop()
    forgetMe()
  }, [forgetMe])

  const setTab = useCallback((t: Tab, view: string | null = null) => {
    setRoute({ tab: t, view })
    const url = new URL(location.href)
    url.searchParams.set('tab', t)
    if (view) url.searchParams.set('view', view)
    else url.searchParams.delete('view')
    history.replaceState(null, '', url)
  }, [])

  const say = useCallback(
    async (text: string) => {
      if (!personaId || !text.trim()) return
      setOutbox({ member_id: personaId, text })
      const res = await guard(() => api.converse(personaId, text))
      setOutbox(null)
      if (res) setSnap(res.state)
    },
    [personaId, guard],
  )

  const trigger = useCallback(
    async (agent: string, name: string, label: string) => {
      const res = await guard(() => api.trigger(agent, name))
      if (!res) return
      setSnap(res.state)
      api.config().then(setConfig).catch(() => {})
      notify('success', `${label} ran. See it in Ask.`)
    },
    [guard, notify],
  )

  const callTool = useCallback(
    async (agent: string, tool: string, args: Record<string, unknown>, doneText: string) => {
      const res = await guard(() => api.tool(agent, tool, args))
      if (!res) return false
      setSnap(res.state)
      api.config().then(setConfig).catch(() => {}) // a new member gets a voice assigned
      if (res.status === 'error') {
        notify('error', String(res.result.error ?? 'That did not work'))
        return false
      }
      notify('success', doneText)
      return true
    },
    [guard, notify],
  )

  const runTool = useCallback(async (agent: string, tool: string, args: Record<string, unknown>): Promise<ToolOutcome> => {
    setBusyCount((n) => n + 1)
    try {
      const res = await api.tool(agent, tool, args)
      setSnap(res.state)
      api.config().then(setConfig).catch(() => {}) // a new or edited person changes the voice assigned
      if (res.status === 'error') return { ok: false, result: res.result, error: String(res.result.error ?? 'That did not work.') }
      return { ok: true, result: res.result }
    } catch (e) {
      return { ok: false, result: {}, error: messageOf(e) }
    } finally {
      setBusyCount((n) => n - 1)
    }
  }, [])

  const setChaos = useCallback(
    async (enabled: boolean) => {
      const s = await guard(() => api.chaos(enabled))
      if (s) setSnap(s)
    },
    [guard],
  )

  const reset = useCallback(async () => {
    await voiceController.stop()
    const s = await guard(() => api.reset())
    if (!s) return
    setSnap(s)
    api.config().then(setConfig).catch(() => {})
    notify('success', 'Back to the starting family.')
  }, [guard, notify])

  const loadDemo = useCallback(async (): Promise<Snapshot | null> => {
    await voiceController.stop()
    const s = await guard(() => api.household.demo())
    if (!s) return null
    setSnap(s)
    api.config().then(setConfig).catch(() => {})
    return s
  }, [guard])

  const resetHousehold = useCallback(async (): Promise<boolean> => {
    await voiceController.stop()
    const s = await guard(() => api.household.reset())
    if (!s) return false
    forgetMe()
    clearOnboarded()
    clearSetup()
    setSnap(s)
    api.config().then(setConfig).catch(() => {})
    setTab('ask')
    notify('success', 'The household was reset.')
    return true
  }, [guard, forgetMe, clearOnboarded, notify, setTab])

  const startVoice = useCallback(async () => {
    const phase = voiceController.getState().phase
    if (!personaId || (phase !== 'idle' && phase !== 'error')) return
    await voiceController.start(personaId)
    // A 503 means the server's voice settings changed: refresh what Settings and Talk show.
    if (voiceController.getState().error?.kind === 'not-configured') api.config().then(setConfig).catch(() => {})
  }, [personaId])

  const toggleMute = useCallback(() => voiceController.toggleMute(), [])

  const interruptVoice = useCallback(async () => {
    const problem = await voiceController.interrupt()
    if (problem) notify('error', problem)
  }, [notify])

  const dismissVoiceError = useCallback(() => voiceController.dismissError(), [])

  const value = useMemo<AppContextValue>(
    () => ({
      snap,
      config,
      tools,
      loading,
      loadError,
      busy: busyCount > 0,
      online,
      me: personaId,
      personaId,
      member,
      household,
      tab,
      view: route.view,
      outbox,
      voice,
      voiceActive,
      toasts,
      setTab,
      setMe,
      clearMe,
      setPersona: setMe,
      reload: () => void load(),
      say,
      trigger,
      callTool,
      runTool,
      setChaos,
      reset,
      loadDemo,
      resetHousehold,
      startVoice,
      stopVoice,
      toggleMute,
      interruptVoice,
      dismissVoiceError,
      notify,
      dismissToast,
    }),
    [snap, config, tools, loading, loadError, busyCount, online, personaId, member, household, tab, route.view, outbox, voice, voiceActive, toasts, setTab, setMe, clearMe, load, say, trigger, callTool, runTool, setChaos, reset, loadDemo, resetHousehold, startVoice, stopVoice, toggleMute, interruptVoice, dismissVoiceError, notify, dismissToast],
  )

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}
