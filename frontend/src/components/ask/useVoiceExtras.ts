import { useEffect, useState } from 'react'
import { useApp } from '@/state/AppState'

/**
 * What a voice call shows that the backend transcript cannot yet: the words you are saying right now (interim speech), the turn you just
 * finished until the backend records it, and the greeting Aangan speaks on joining.
 */
export function useVoiceExtras(transcriptLength: number, memberId: string | null) {
  const { voice } = useApp()
  const [greeting, setGreeting] = useState<{ key: string; at: number; text: string; member: string } | null>(null)
  const [seen, setSeen] = useState<{ id: string; len: number; expired: boolean } | null>(null)

  const sessionKey = voice.session?.agent_id
  useEffect(() => {
    if (voice.phase !== 'live' || !voice.session) return
    const session = voice.session
    setGreeting((g) => (g?.key === session.agent_id ? g : { key: session.agent_id, at: transcriptLength, text: session.greeting, member: session.member_id }))
  }, [voice.phase, sessionKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const lastUser = [...voice.turns].reverse().find((t) => t.who === 'user')
  const finishedId = lastUser && lastUser.status !== 'partial' ? lastUser.id : null
  useEffect(() => {
    if (!finishedId) return
    setSeen((s) => (s?.id === finishedId ? s : { id: finishedId, len: transcriptLength, expired: false }))
    const t = window.setTimeout(() => setSeen((s) => (s?.id === finishedId ? { ...s, expired: true } : s)), 8000)
    return () => window.clearTimeout(t)
  }, [finishedId]) // eslint-disable-line react-hooks/exhaustive-deps

  let liveUser: string | null = null
  if (lastUser && voice.session?.member_id === memberId) {
    if (lastUser.status === 'partial') liveUser = lastUser.text
    else if (seen?.id === lastUser.id && !seen.expired && seen.len === transcriptLength) liveUser = lastUser.text
  }
  return { liveUser, listeningNow: lastUser?.status === 'partial', greeting: greeting && greeting.member === memberId ? greeting : null }
}
