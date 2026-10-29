import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Me } from '../api'
import { ChevronUp, LogOut, LogoMark, Pencil, Plus, Sun, Trash } from '../icons'
import { applyTheme, readTheme, type Theme } from '../theme'
import { ago } from '../time'
import { ChatView } from './ChatView'

const GRANT = 2_000_000

export function ChatLayout({ me }: { me: Me }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })
  const [sideOpen, setSideOpen] = useState(false)
  const [editing, setEditing] = useState<string | null>(null)

  const remove = useMutation({
    mutationFn: api.remove,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (id === conversationId) navigate('/')
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.rename(id, title),
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      queryClient.invalidateQueries({ queryKey: ['conversation', conversation.id] })
    },
  })

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.shiftKey && event.key.toLowerCase() === 'o') {
        event.preventDefault()
        navigate('/')
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [navigate])

  const open = (path: string) => {
    navigate(path)
    setSideOpen(false)
  }
  const list = conversations.data ?? []
  const current = list.find((c) => c.id === conversationId)

  return (
    <div className={`app ${sideOpen ? 'side-open' : ''}`}>
      <div className="scrim" onClick={() => setSideOpen(false)} />
      <aside className="side">
        <div className="brand">
          <span className="logo">
            <LogoMark />
          </span>
          Tess
        </div>
        <nav className="nav">
          <button onClick={() => open('/')}>
            <Plus />
            New chat
            <kbd>⇧⌘O</kbd>
          </button>
        </nav>
        <div className="group">
          Chats<span className="n">{list.length || ''}</span>
        </div>
        <div className="list-s">
          {list.map((c) =>
            editing === c.id ? (
              <div key={c.id} className="row on">
                <input
                  autoFocus
                  defaultValue={c.title}
                  aria-label="Conversation title"
                  onBlur={() => setEditing(null)}
                  onKeyDown={(e) => {
                    if (e.key === 'Escape') setEditing(null)
                    if (e.key === 'Enter') {
                      const title = e.currentTarget.value.trim()
                      if (title && title !== c.title) rename.mutate({ id: c.id, title })
                      setEditing(null)
                    }
                  }}
                />
              </div>
            ) : (
              <div key={c.id} className={`row ${c.id === conversationId ? 'on' : ''}`}>
                <button className="main" onClick={() => open(`/c/${c.id}`)} onDoubleClick={() => setEditing(c.id)}>
                  <span className="t">{c.title}</span>
                  <span className="w">{ago(c.updated_at)}</span>
                </button>
                <span className="acts">
                  <button className="icon" title="Rename" onClick={() => setEditing(c.id)}>
                    <Pencil />
                  </button>
                  <button
                    className="icon danger"
                    title="Delete"
                    onClick={() => {
                      if (window.confirm(`Delete “${c.title}”?`)) remove.mutate(c.id)
                    }}
                  >
                    <Trash />
                  </button>
                </span>
              </div>
            ),
          )}
          {conversations.isSuccess && list.length === 0 && <div className="none">No chats yet.</div>}
        </div>
        <div className="side-foot">
          <div className="row">
            <span>Credits</span>
            <span>{me.balance.toLocaleString()}</span>
          </div>
          <div className="meter">
            <i style={{ width: `${Math.max(0, Math.min(100, (me.balance / GRANT) * 100))}%` }} />
          </div>
          <Profile me={me} />
        </div>
      </aside>
      <section className="panel">
        <ChatView
          conversationId={conversationId ?? null}
          title={current?.title}
          balance={me.balance}
          onOpenSide={() => setSideOpen(true)}
        />
      </section>
    </div>
  )
}

function Profile({ me }: { me: Me }) {
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const [theme, setTheme] = useState<Theme>(readTheme)
  const ref = useRef<HTMLDivElement>(null)
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      window.location.assign('/login')
    },
  })

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  const pick = (next: Theme) => {
    applyTheme(next)
    setTheme(next)
  }
  const initials = (me.user.name || me.user.email).slice(0, 2).toUpperCase()

  return (
    <div className="pick" ref={ref}>
      <button className="profile-btn" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span className="ava">{initials}</span>
        <span className="name">{me.user.name}</span>
        <ChevronUp />
      </button>
      {open && (
        <div className="menu" role="menu">
          <div className="who">{me.user.email}</div>
          <hr />
          {(['system', 'light', 'dark'] as const).map((value) => (
            <button key={value} role="menuitem" onClick={() => pick(value)}>
              <Sun />
              {value[0].toUpperCase() + value.slice(1)} theme
              {theme === value && <span className="check">✓</span>}
            </button>
          ))}
          <hr />
          <button role="menuitem" className="danger" onClick={() => logout.mutate()}>
            <LogOut />
            Sign out
          </button>
        </div>
      )}
    </div>
  )
}
