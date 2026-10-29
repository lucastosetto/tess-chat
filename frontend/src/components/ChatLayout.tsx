import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Me } from '../api'
import { Chats, LogoMark, Settings, SidebarIcon } from '../icons'
import { store } from '../store'
import { ChatView } from './ChatView'
import { Sessions } from './Sessions'
import { GRANT, SettingsPage } from './Settings'

export function ChatLayout({ me, view = 'chat' }: { me: Me; view?: 'chat' | 'settings' }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })
  const [sideOpen, setSideOpen] = useState(false)
  const [mini, setMini] = useState(() => store.get('sideMini', false))

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
  const toggleMini = () => {
    if (window.matchMedia('(max-width: 760px)').matches) return setSideOpen(false)
    setMini(!mini)
    store.set('sideMini', !mini)
  }
  const list = conversations.data ?? []
  const current = list.find((c) => c.id === conversationId)

  return (
    <div className={`app ${sideOpen ? 'side-open' : ''} ${mini ? 'side-mini' : ''}`}>
      <div className="scrim" onClick={() => setSideOpen(false)} />
      <aside className="side">
        <div className="brand">
          <button className="icon" onClick={toggleMini} data-tip={mini ? 'Expand sidebar' : 'Collapse sidebar'} aria-label={mini ? 'Expand sidebar' : 'Collapse sidebar'}>
            <SidebarIcon />
          </button>
          <span className="lbl wordmark">
            <span className="logo">
              <LogoMark />
            </span>
            Tess
          </span>
        </div>
        <nav className="nav" aria-label="Views">
          <button className={view === 'chat' ? 'on' : ''} title="Chats" onClick={() => open(conversationId ? `/c/${conversationId}` : '/')}>
            <Chats />
            <span className="lbl">Chats</span>
          </button>
          <button className={view === 'settings' ? 'on' : ''} title="Settings" onClick={() => open('/settings')}>
            <Settings />
            <span className="lbl">Settings</span>
          </button>
        </nav>
        <div className="side-chats" hidden={view !== 'chat'}>
          <Sessions
            list={list}
            loaded={conversations.isSuccess}
            currentId={view === 'chat' ? (conversationId ?? null) : null}
            onOpen={(id) => open(`/c/${id}`)}
            onDeleted={(id) => id === conversationId && navigate('/')}
          />
        </div>
        <div className="side-foot">
          <div className="row">
            <span>Credits</span>
            <span>{me.balance.toLocaleString()}</span>
          </div>
          <div className="meter">
            <i style={{ width: `${Math.max(0, Math.min(100, (me.balance / GRANT) * 100))}%` }} />
          </div>
        </div>
      </aside>
      <section className="panel">
        {view === 'settings' ? (
          <>
            <header className="top">
              <button className="icon side-btn" onClick={() => setSideOpen(true)} aria-label="Show sidebar">
                <SidebarIcon />
              </button>
              <div className="crumb">
                <span className="t">Settings</span>
              </div>
            </header>
            <main className="view">
              <SettingsPage me={me} />
            </main>
          </>
        ) : (
          <ChatView
            conversationId={conversationId ?? null}
            title={current?.title}
            onOpenSide={() => setSideOpen(true)}
            onNew={() => open('/')}
          />
        )}
      </section>
    </div>
  )
}
