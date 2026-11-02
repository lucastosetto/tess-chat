import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Me } from '../api'
import { Activity, Chats, Logo, LogOut, Settings, Shield, SidebarIcon } from '../icons'
import { AdminPage } from './Admin'
import { ActivityPage } from './Activity'
import { store } from '../store'
import { ChatView } from './ChatView'
import { Sessions } from './Sessions'
import { GRANT, SettingsPage } from './Settings'

export function ChatLayout({ me, view = 'chat' }: { me: Me; view?: 'chat' | 'settings' | 'activity' | 'admin' }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })
  const [sideOpen, setSideOpen] = useState(false)
  const queryClient = useQueryClient()
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      window.location.assign('/login')
    },
  })
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
            <Logo />
          </span>
        </div>
        <nav className="nav" aria-label="Views">
          <button className={view === 'chat' ? 'on' : ''} title="Chats" onClick={() => open(conversationId ? `/c/${conversationId}` : '/')}>
            <Chats />
            <span className="lbl">Chats</span>
          </button>
          <button className={view === 'activity' ? 'on' : ''} title="Activity" onClick={() => open('/activity')}>
            <Activity />
            <span className="lbl">Activity</span>
          </button>
          {me.user.role === 'admin' && (
            <button className={view === 'admin' ? 'on' : ''} title="Admin" onClick={() => open('/admin')}>
              <Shield />
              <span className="lbl">Admin</span>
            </button>
          )}
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
          <div className="acct">
            <span className="ava">{(me.user.name || me.user.email).slice(0, 2).toUpperCase()}</span>
            <div className="who-txt">
              {me.user.name || me.user.email}
              <span>{me.user.email}</span>
            </div>
            <button className="icon danger" data-tip="Sign out" aria-label="Sign out" disabled={logout.isPending} onClick={() => logout.mutate()}>
              <LogOut />
            </button>
          </div>
        </div>
      </aside>
      <section className="panel">
        {view !== 'chat' ? (
          <>
            <header className="top">
              <button className="icon side-btn" onClick={() => setSideOpen(true)} aria-label="Show sidebar">
                <SidebarIcon />
              </button>
              <div className="crumb">
                <span className="t">{{ settings: 'Settings', activity: 'Activity', admin: 'Admin' }[view]}</span>
              </div>
            </header>
            <main className="view">
              {view === 'settings' ? <SettingsPage me={me} /> : view === 'admin' ? <AdminPage /> : <ActivityPage />}
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
