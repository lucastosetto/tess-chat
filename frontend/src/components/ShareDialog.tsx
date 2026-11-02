import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { forwardRef, useState } from 'react'
import { api, ApiError, type ShareLink } from '../api'
import { when } from '../time'

type Props = { conversationId: string; title: string }

export const ShareDialog = forwardRef<HTMLDialogElement, Props>(function ShareDialog({ conversationId, title }, ref) {
  const queryClient = useQueryClient()
  const [fresh, setFresh] = useState<ShareLink | null>(null)
  const [copied, setCopied] = useState(false)
  const links = useQuery({ queryKey: ['shares', conversationId], queryFn: () => api.shares(conversationId) })
  const active = links.data?.[0]
  const current = fresh && fresh.id === active?.id ? fresh : null

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ['shares'] })
  }
  const create = useMutation({
    mutationFn: () => api.share(conversationId),
    onSuccess: (link) => {
      setFresh(link)
      setCopied(false)
      refresh()
    },
  })
  const revoke = useMutation({
    mutationFn: (id: string) => api.revokeShare(id),
    onSuccess: () => {
      setFresh(null)
      refresh()
    },
  })
  const error = create.error ?? revoke.error

  return (
    <dialog ref={ref} aria-labelledby="share-t" onClose={() => setCopied(false)}>
      <h3 id="share-t">Share chat</h3>
      <p className="meta" style={{ margin: '-6px 0 14px' }}>
        Anyone with the link can read “{title}” up to now, without signing in. Messages you send later stay private.
      </p>
      {current?.url ? (
        <div className="link-box">
          <input readOnly value={current.url} aria-label="Share link" onFocus={(e) => e.currentTarget.select()} />
          <button
            className="b primary"
            onClick={() => {
              void navigator.clipboard.writeText(current.url!)
              setCopied(true)
            }}
          >
            {copied ? 'Copied' : 'Copy'}
          </button>
        </div>
      ) : active ? (
        <p className="meta" style={{ margin: 0 }}>
          A link is active since {when(active.created_at)}. For security the full link is only shown once; create a
          new one to copy it again (the old one stops working).
        </p>
      ) : (
        <p className="meta" style={{ margin: 0 }}>No link yet.</p>
      )}
      <h3 style={{ marginTop: 20 }}>Export</h3>
      <div className="link-box">
        <a className="b ghost" href={`/api/conversations/${conversationId}/export?format=markdown`} download>
          Markdown
        </a>
        <a className="b ghost" href={`/api/conversations/${conversationId}/export?format=json`} download>
          JSON
        </a>
      </div>
      <div className="actions">
        {error && <span className="form-err">{error instanceof ApiError ? error.message : 'Something went wrong.'}</span>}
        {active && (
          <button className="b danger-b" disabled={revoke.isPending} onClick={() => revoke.mutate(active.id)}>
            Revoke link
          </button>
        )}
        <button className="b ghost" onClick={(e) => (e.currentTarget.closest('dialog') as HTMLDialogElement).close()}>
          Close
        </button>
        {!current && (
          <button className="b primary" disabled={create.isPending} onClick={() => create.mutate()}>
            {active ? 'Create new link' : 'Create link'}
          </button>
        )}
      </div>
    </dialog>
  )
})
