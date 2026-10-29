import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useParams } from 'react-router-dom'
import { api, type Me } from '../api'
import { ChatView } from './ChatView'

export function ChatLayout({ me }: { me: Me }) {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const conversations = useQuery({ queryKey: ['conversations'], queryFn: api.conversations })

  const create = useMutation({
    mutationFn: api.createConversation,
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      navigate(`/c/${conversation.id}`)
    },
  })
  const remove = useMutation({
    mutationFn: api.remove,
    onSuccess: (_, id) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      if (id === conversationId) navigate('/')
    },
  })
  const rename = useMutation({
    mutationFn: ({ id, title }: { id: string; title: string }) => api.rename(id, title),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['conversations'] }),
  })
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      window.location.assign('/login')
    },
  })

  return (
    <div className="layout">
      <aside className="sidebar">
        <button className="new-chat" onClick={() => create.mutate()} disabled={create.isPending}>
          + New chat
        </button>
        <nav className="conversation-list">
          {conversations.data?.map((c) => (
            <div
              key={c.id}
              className={`conversation-item ${c.id === conversationId ? 'active' : ''}`}
              onClick={() => navigate(`/c/${c.id}`)}
            >
              <span className="title">{c.title}</span>
              <span className="actions">
                <button
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation()
                    const title = window.prompt('Rename conversation', c.title)
                    if (title?.trim()) rename.mutate({ id: c.id, title })
                  }}
                >
                  ✎
                </button>
                <button
                  title="Delete"
                  onClick={(e) => {
                    e.stopPropagation()
                    if (window.confirm('Delete this conversation?')) remove.mutate(c.id)
                  }}
                >
                  ×
                </button>
              </span>
            </div>
          ))}
          {conversations.data?.length === 0 && <p className="muted small">No conversations yet.</p>}
        </nav>
        <footer className="sidebar-footer">
          <div className="balance" title="Remaining credits">
            {me.balance.toLocaleString()} credits
          </div>
          <div className="user-row">
            <span className="small">{me.user.email}</span>
            <button className="link" onClick={() => logout.mutate()}>
              Sign out
            </button>
          </div>
        </footer>
      </aside>
      <main className="main">
        {conversationId ? (
          <ChatView key={conversationId} conversationId={conversationId} />
        ) : (
          <div className="empty">
            <h2>Start a conversation</h2>
            <button onClick={() => create.mutate()}>New chat</button>
          </div>
        )}
      </main>
    </div>
  )
}
