import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { api, streamMessage, type ConversationDetail, type Me, type Message } from '../api'
import { renderMarkdown } from '../markdown'

export function ChatView({ conversationId }: { conversationId: string }) {
  const queryClient = useQueryClient()
  const detail = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.conversation(conversationId),
  })
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const bottom = useRef<HTMLDivElement>(null)

  const loaded = detail.data?.messages
  useEffect(() => {
    if (loaded) setMessages(loaded)
  }, [loaded])

  useEffect(() => {
    bottom.current?.scrollIntoView({ block: 'end' })
  }, [messages, streaming])

  const setBalance = (balance: number) =>
    queryClient.setQueryData<Me>(['me'], (me) => (me ? { ...me, balance } : me))

  const send = async (event?: FormEvent) => {
    event?.preventDefault()
    const content = draft.trim()
    if (!content || streaming !== null) return
    setDraft('')
    setError(null)
    setStreaming('')
    try {
      await streamMessage(conversationId, content, {
        accepted: ({ message, title }) => {
          setMessages((current) => [...current, message])
          queryClient.setQueryData<ConversationDetail>(['conversation', conversationId], (d) =>
            d ? { ...d, conversation: { ...d.conversation, title } } : d,
          )
          queryClient.invalidateQueries({ queryKey: ['conversations'] })
        },
        delta: ({ text }) => setStreaming((current) => (current ?? '') + text),
        completed: ({ message, balance }) => {
          setMessages((current) => [...current, message])
          setBalance(balance)
        },
        failed: ({ message, balance }) => {
          setMessages((current) => [...current, message])
          setBalance(balance)
        },
        error: ({ code }) => setError(code),
      })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to send')
      setDraft(content)
    } finally {
      setStreaming(null)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      void send()
    }
  }

  if (detail.isPending) return <div className="splash">Loading…</div>
  if (detail.error) return <div className="splash">Conversation not found.</div>

  return (
    <div className="chat">
      <header className="chat-header">{detail.data.conversation.title}</header>
      <div className="messages">
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {streaming !== null && (
          <div className="message assistant">
            {streaming ? (
              <div className="content" dangerouslySetInnerHTML={{ __html: renderMarkdown(streaming) }} />
            ) : (
              <div className="typing">Thinking…</div>
            )}
          </div>
        )}
        <div ref={bottom} />
      </div>
      <form className="composer" onSubmit={send}>
        {error && <p className="error">{error}</p>}
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Message Tess…"
          rows={3}
          disabled={streaming !== null}
        />
        <button type="submit" disabled={!draft.trim() || streaming !== null}>
          Send
        </button>
      </form>
    </div>
  )
}

function MessageBubble({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="message user">
        <div className="content plain">{message.content}</div>
      </div>
    )
  }
  return (
    <div className={`message assistant ${message.status}`}>
      {message.content && (
        <div className="content" dangerouslySetInnerHTML={{ __html: renderMarkdown(message.content) }} />
      )}
      {message.status === 'failed' && (
        <div className="error small">The reply failed ({message.error}). Credits were refunded.</div>
      )}
      {message.status === 'completed' && message.model && (
        <div className="meta">
          {message.provider} · {message.model} · {message.usage.input_tokens}→
          {message.usage.output_tokens} tokens
        </div>
      )}
    </div>
  )
}
