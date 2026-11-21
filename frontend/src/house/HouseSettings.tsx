import { ExternalLink, House, Link2 } from 'lucide-react'
import { useState } from 'react'
import { api } from '@/api'
import { useApp } from '@/state/AppState'
import { Button, Card, Pill, inputClass } from '@/ui/primitives'
import { houseUrl, validateHouseLink } from './houseLink'

export function HouseSettings() {
  const { snap, reload, notify, online } = useApp()
  const [url, setUrl] = useState(() => houseUrl(location.href))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const linked = snap?.domains.smart_home?.linked ?? false
  const save = async (link: boolean) => {
    setError(null)
    setSaving(true)
    try {
      const id = link ? validateHouseLink(url, location.href) : 'cozy-home'
      await api.house.link(id, link)
      reload()
      notify('success', link ? 'House linked. Ask Aangan to control its lights and doors.' : 'House unlinked. AI controls are disabled.')
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not update the house link. Try again.')
    } finally {
      setSaving(false)
    }
  }
  return (
    <Card className="space-y-4 p-4">
      <div className="flex items-center gap-3">
        <House className="size-6 text-brand-text" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="t-card">Cozy home</p>
          <p className="t-secondary">A furnished 3D house with room lighting, dimmers and doors.</p>
        </div>
        <Pill tone={linked ? 'success' : 'neutral'}>{linked ? 'Linked' : 'Not linked'}</Pill>
      </div>
      <p className="t-secondary">Virtual devices only. Link once for this household, then say or type &ldquo;turn off the kitchen lights&rdquo; on the Ask page. Keep the house open in another window to watch it change.</p>
      <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); void save(true) }}>
        <label className="block text-sm font-semibold">
          House link
          <input className={`${inputClass} mt-1`} type="url" value={url} onChange={(e) => setUrl(e.target.value)} disabled={saving || linked} required aria-describedby="house-link-hint" />
        </label>
        <p id="house-link-hint" className="t-caption">This house shares your Aangan server. No external account or device credentials needed.</p>
        {error && <p role="alert" className="text-sm text-[var(--rw-text-danger)]">{error}</p>}
        <div className="flex flex-wrap items-center gap-3">
          {linked ? (
            <Button type="button" variant="secondary" loading={saving} disabled={!online} onClick={() => void save(false)}>Unlink house</Button>
          ) : (
            <Button type="submit" loading={saving} disabled={!online} icon={<Link2 className="size-4" aria-hidden="true" />}>Link house</Button>
          )}
          <a href={houseUrl(location.href)} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-brand-text underline underline-offset-4">
            Open 3D house <ExternalLink className="size-4" aria-hidden="true" />
          </a>
        </div>
      </form>
    </Card>
  )
}
