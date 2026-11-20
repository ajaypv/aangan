import { Users } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { api } from '@/api'
import { useApp } from '@/state/AppState'
import { Button, Card, inputClass } from '@/ui/primitives'
import { openRoom, saveIdentity } from './roomRoute'

/** Home's "Plan together" card: name a room (like "Goa trip"), create it and open it. Share the link from inside to invite the family. */
export function PlanTogetherCard() {
  const { personaId } = useApp()
  const [open, setOpen] = useState(false)
  const [title, setTitle] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const create = async (e: FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const room = await api.room.create(title.trim() || 'Goa trip', personaId)
      saveIdentity(room.id, { participant_id: room.host_participant_id })
      openRoom(room.id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not start the room')
      setBusy(false)
    }
  }

  return (
    <Card className="p-5 lg:p-6">
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-soft text-brand-text" aria-hidden="true">
          <Users className="size-5" />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="t-section">Plan together</h2>
          <p className="t-secondary">Start a room, send the link to family, and Aangan keeps one plan with flights, places, meals and costs.</p>
        </div>
      </div>
      {open ? (
        <form onSubmit={create} className="mt-4 flex flex-wrap items-center gap-2">
          <label htmlFor="room-title" className="sr-only">
            Room name
          </label>
          <input
            id="room-title"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Goa trip"
            maxLength={60}
            autoComplete="off"
            autoFocus
            enterKeyHint="go"
            className={`${inputClass} min-w-0 flex-1`}
          />
          <Button type="submit" loading={busy}>
            Create room
          </Button>
          <Button variant="tertiary" onClick={() => setOpen(false)} disabled={busy}>
            Cancel
          </Button>
          {error && (
            <p role="alert" className="w-full text-sm font-medium text-[var(--rw-text-danger)]">
              {error}
            </p>
          )}
        </form>
      ) : (
        <Button variant="secondary" className="mt-4" onClick={() => setOpen(true)}>
          Start a room
        </Button>
      )}
    </Card>
  )
}
