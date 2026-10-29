import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, ApiError, streamMessage, type Me, type Message } from '../api'
import { Chevron, Copy, LogoMark, Menu, Send, Stop } from '../icons'
import { renderMarkdown } from '../markdown'
import { ago } from '../time'

const SUGGESTIONS = [
  { title: 'Explain a concept', prompt: 'Explain how HTTPS works, step by step, in plain words.' },
  { title: 'Write some code', prompt: 'Write a Python function that deduplicates a list while keeping order.' },
  { title: 'Plan something', prompt: 'Plan a 3-day trip to Rio de Janeiro with a moderate budget.' },
]

type Props = {
  conversationId: string | null
  title?: string
  balance: number
  onOpenSide: () => void
}

export function ChatView({ conversationId, title, balance, onOpenSide }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(conversationId)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [liveTitle, setLiveTitle] = useState<string | undefined>()
  const scroller = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const abort = useRef<AbortController | null>(null)

  if (conversationId !== activeId && streaming === null) {
    setActiveId(conversationId)
    setMessages([])
    setLiveTitle(undefined)
    setError(null)
  }

  const detail = useQuery({
    queryKey: ['conversation', activeId],
    queryFn: () => api.conversation(activeId!),
    enabled: activeId !== null && streaming === null,
  })
  const loaded = detail.data?.messages
  useEffect(() => {
    if (loaded) setMessages(loaded)
  }, [loaded])

  useLayoutEffect(() => {
    const el = scroller.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, streaming])

  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [draft])

  useEffect(() => {
    input.current?.focus()
  }, [activeId])

  const setBalance = (next: number) =>
    queryClient.setQueryData<Me>(['me'], (me) => (me ? { ...me, balance: next } : me))

  const send = async (text?: string, event?: FormEvent) => {
    event?.preventDefault()
    const content = (text ?? draft).trim()
    if (!content || streaming !== null) return
    setDraft('')
    setError(null)
    setStreaming('')
    const controller = new AbortController()
    abort.current = controller
    try {
      let id = activeId
      if (!id) {
        const conversation = await api.createConversation()
        id = conversation.id
        setActiveId(id)
      }
      const target = id
      await streamMessage(
        target,
        content,
        {
          accepted: ({ message, title: newTitle }) => {
            setMessages((current) => [...current, message])
            setLiveTitle(newTitle)
            if (target !== conversationId) navigate(`/c/${target}`, { replace: !conversationId })
            queryClient.invalidateQueries({ queryKey: ['conversations'] })
          },
          delta: ({ text: chunk }) => setStreaming((current) => (current ?? '') + chunk),
          completed: ({ message, balance: next }) => {
            setMessages((current) => [...current, message])
            setBalance(next)
          },
          failed: ({ message, balance: next }) => {
            setMessages((current) => [...current, message])
            setBalance(next)
          },
          error: ({ code }) => setError(code),
        },
        controller.signal,
      )
      queryClient.invalidateQueries({ queryKey: ['conversation', target] })
    } catch (err) {
      if (controller.signal.aborted) {
        setError('Stopped. The partial reply will appear after a refresh.')
      } else {
        setError(describe(err))
        setDraft(content)
      }
    } finally {
      abort.current = null
      setStreaming(null)
    }
  }

  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      void send()
    }
  }

  const onCopy = (event: React.MouseEvent<HTMLDivElement>) => {
    const button = (event.target as HTMLElement).closest('.copy-code')
    const code = button?.parentElement?.querySelector('code')?.textContent
    if (button && code) void navigator.clipboard.writeText(code)
  }

  const heading = liveTitle ?? title ?? detail.data?.conversation.title
  const missing = detail.error instanceof ApiError && detail.error.status === 404
  const empty = !activeId && messages.length === 0 && streaming === null

  return (
    <>
      <header className="top">
        <button className="icon side-btn" onClick={onOpenSide} aria-label="Open sidebar">
          <Menu />
        </button>
        <div className="crumb">
          <span className="p">Chats</span>
          <Chevron />
          <span className="t">{activeId ? heading ?? '…' : 'New chat'}</span>
        </div>
        <div className="right">{balance.toLocaleString()} cr</div>
      </header>
      <div className="convo">
        <div className="msgs" ref={scroller} onClick={onCopy}>
          <div className="pane">
            {missing && <div className="note-err">This conversation does not exist or was deleted.</div>}
            {empty && (
              <div className="empty">
                <span className="logo">
                  <LogoMark />
                </span>
                <h2>What can I help with?</h2>
                <p className="meta">Answers stream in real time. Each reply uses credits.</p>
                <div className="sugg">
                  {SUGGESTIONS.map((s) => (
                    <button key={s.title} onClick={() => void send(s.prompt)}>
                      <b>{s.title}</b>
                      <span>{s.prompt}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m) => (
              <Turn key={m.id} message={m} />
            ))}
            {streaming !== null && (
              <div className="turn assistant">
                {streaming ? (
                  <div
                    className="msg assistant"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(streaming) + '<span class="cursor"></span>' }}
                  />
                ) : (
                  <div className="typing">
                    <i />
                    Thinking…
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="composer-wrap">
          <form className="composer" onSubmit={(e) => void send(undefined, e)}>
            <textarea
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Message Tess…"
              rows={2}
              aria-label="Message"
            />
            <div className="bar">
              <span className="chip">gemini · groq</span>
              <span className={`status ${error ? 'err' : ''}`}>
                {error ?? (streaming !== null ? 'Streaming…' : '')}
              </span>
              {streaming !== null ? (
                <button type="button" className="send" onClick={() => abort.current?.abort()} title="Stop">
                  <Stop />
                </button>
              ) : (
                <button type="submit" className="send" disabled={!draft.trim()} title="Send">
                  <Send />
                </button>
              )}
            </div>
          </form>
          <div className="hint">Enter to send · Shift+Enter for a new line</div>
        </div>
      </div>
    </>
  )
}

function Turn({ message }: { message: Message }) {
  if (message.role === 'user') {
    return (
      <div className="turn user">
        <div className="msg user">{message.content}</div>
        <div className="acts">
          <span className="ago">{ago(message.created_at)}</span>
        </div>
      </div>
    )
  }
  const html = message.content ? withCopyButtons(renderMarkdown(message.content)) : ''
  return (
    <div className="turn assistant">
      {html && <div className="msg assistant" dangerouslySetInnerHTML={{ __html: html }} />}
      {message.status === 'failed' && (
        <div className="note-err">The reply failed ({message.error}). Credits were refunded.</div>
      )}
      <div className="acts">
        <button
          className="icon"
          title="Copy"
          onClick={() => void navigator.clipboard.writeText(message.content)}
        >
          <Copy />
        </button>
        {message.model && (
          <span className="ago">
            {message.provider} · {message.model} · {message.usage.input_tokens}→{message.usage.output_tokens} tok
          </span>
        )}
      </div>
    </div>
  )
}

const COPY_BUTTON =
  '<button class="icon copy-code" title="Copy code" type="button"><svg class="i" viewBox="0 0 24 24"><rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15V5a2 2 0 0 1 2-2h10"/></svg></button>'

function withCopyButtons(html: string): string {
  return html.split('<pre>').join(`<pre>${COPY_BUTTON}`)
}

function describe(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.code === 'insufficient_credits') return 'Out of credits.'
    if (err.status === 401) return 'Session expired. Sign in again.'
    return err.message
  }
  return 'Could not send the message.'
}
