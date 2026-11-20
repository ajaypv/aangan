import { Confirmation, ConfirmationActions, ConfirmationRequest, ConfirmationTitle } from '@/components/ai-elements/confirmation'
import { useApp } from '@/state/AppState'
import { Button } from '@/ui/primitives'

/** Aangan proposed something and needs a yes or a no. The buttons answer in words, exactly as if the person had typed them. */
export function ProposalCard({ native }: { native: boolean }) {
  const { busy, say } = useApp()
  return (
    <Confirmation state="approval-requested" approval={{ id: 'pending-proposal' }} className="border-[var(--selected-edge)] bg-brand-soft">
      <ConfirmationTitle className="font-semibold text-ink">{native ? 'Aangan aapke jawab ka intezaar kar raha hai.' : 'Aangan is waiting for your answer.'}</ConfirmationTitle>
      <ConfirmationRequest>
        <ConfirmationActions className="self-stretch justify-start gap-2">
          <Button disabled={busy} onClick={() => void say(native ? 'Haan, kar do' : 'Yes, go ahead')}>
            {native ? 'Haan, kar do' : 'Yes, go ahead'}
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void say(native ? 'Nahi' : 'No')}>
            {native ? 'Nahi' : 'No, not that'}
          </Button>
        </ConfirmationActions>
      </ConfirmationRequest>
    </Confirmation>
  )
}
