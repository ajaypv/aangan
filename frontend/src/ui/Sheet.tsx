import { X } from 'lucide-react'
import { useEffect, useRef, type ReactNode } from 'react'
import { IconButton } from './primitives'

/** A modal sheet: slides up from the bottom on phones, centres on larger screens. Esc and a tap outside close it. */
export function Sheet({ open, title, onClose, children }: { open: boolean; title: string; onClose: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      aria-labelledby="sheet-title"
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose()
      }}
      className="m-0 mt-auto w-full max-w-none bg-transparent p-0 backdrop:bg-[var(--scrim)] sm:m-auto sm:max-w-md"
    >
      <div className="rise max-h-[88dvh] overflow-y-auto overscroll-contain rounded-t-xl bg-surface p-5 pb-[max(1.25rem,env(safe-area-inset-bottom))] text-ink shadow-lg sm:rounded-xl">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 id="sheet-title" className="t-section">
            {title}
          </h2>
          <IconButton label="Close" tooltip={false} variant="secondary" onClick={onClose}>
            <X className="size-5" />
          </IconButton>
        </div>
        {open && children}
      </div>
    </dialog>
  )
}
