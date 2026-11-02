import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { LogoMark } from '../icons'
import { when } from '../time'
import { Turn } from './ChatView'

export function SharedView({ token }: { token: string }) {
  const [zoom, setZoom] = useState<string | null>(null)
  const shared = useQuery({ queryKey: ['shared', token], queryFn: () => api.shared(token), retry: false })
  const files = `/api/shared/${encodeURIComponent(token)}/attachments`

  return (
    <div className="shared-page">
      <header className="top">
        <span className="logo">
          <LogoMark />
        </span>
        <div className="crumb">
          <span className="p">Shared chat</span>
          {shared.data && <span className="t">{shared.data.title}</span>}
        </div>
        <div className="right">
          <a className="b sm ghost" href="/">
            Try Tess
          </a>
        </div>
      </header>
      <div className="msgs">
        <div className="pane">
          {shared.isPending && <p className="meta">Loading…</p>}
          {shared.error && <div className="note-err">This link does not exist or was revoked.</div>}
          {shared.data?.messages.map((m) => <Turn key={m.id} message={m} onZoom={setZoom} files={files} />)}
          {shared.data && (
            <p className="shared-note">Shared {when(shared.data.shared_at)} · read-only snapshot</p>
          )}
        </div>
      </div>
      {zoom && (
        <div className="lightbox" onClick={() => setZoom(null)}>
          <img src={zoom} alt="" />
        </div>
      )}
    </div>
  )
}
