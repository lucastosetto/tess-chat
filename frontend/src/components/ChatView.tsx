import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Fragment, useEffect, useLayoutEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Picker } from './Picker'
import { api, ApiError, streamMessage, type Conversation, type Me, type Attachment, type Message, type ToolCall } from '../api'
import { ArrowDown, Chevron, ChevronDown, Clip, Copy, FileIcon, LogoMark, NewChat, Send, SidebarIcon, Stop } from '../icons'
import { renderMarkdown } from '../markdown'
import { when } from '../time'

const SUGGESTIONS = [
  { title: 'Explain a concept', prompt: 'Explain how HTTPS works, step by step, in plain words.' },
  { title: 'Write some code', prompt: 'Write a Python function that deduplicates a list while keeping order.' },
  { title: 'Plan something', prompt: 'Plan a 3-day trip to Rio de Janeiro with a moderate budget.' },
]

type Props = {
  conversationId: string | null
  title?: string
  onOpenSide: () => void
  onNew: () => void
}

function contextWindow(model: string | null): number {
  return model && /gemini/i.test(model) ? 1_048_576 : 131_072
}

type Pending = { key: string; name: string; preview: string | null; attachment?: Attachment }

const ACCEPT = 'image/png,image/jpeg,image/webp,image/gif,application/pdf'
const MAX_FILES = 5

const EFFORTS = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Medium' },
  { value: 'high', label: 'High' },
]

export function ChatView({ conversationId, title, onOpenSide, onNew }: Props) {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const [activeId, setActiveId] = useState(conversationId)
  const [messages, setMessages] = useState<Message[]>([])
  const [draft, setDraft] = useState('')
  const [streaming, setStreaming] = useState<string | null>(null)
  const [liveTools, setLiveTools] = useState<ToolCall[]>([])
  const [pending, setPending] = useState<Pending[]>([])
  const [zoom, setZoom] = useState<string | null>(null)
  const picker = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [liveTitle, setLiveTitle] = useState<string | undefined>()
  const [spent, setSpent] = useState<Record<string, number>>({})
  const [atBottom, setAtBottom] = useState(true)
  const [pick, setPick] = useState({ model: '', effort: '' })
  const models = useQuery({ queryKey: ['models'], queryFn: api.models, staleTime: Infinity })
  const me = useQuery({ queryKey: ['me'], queryFn: api.me })
  const [capped, setCapped] = useState(false)
  const broke = capped || (me.data !== undefined && me.data.balance <= 0)
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
    if (el && atBottom) el.scrollTop = el.scrollHeight
  }, [messages, streaming, atBottom])

  const toBottom = () => {
    const el = scroller.current
    el?.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }

  useLayoutEffect(() => {
    const el = input.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  }, [draft])

  useEffect(() => {
    input.current?.focus()
  }, [activeId])

  const saved = detail.data?.conversation
  const choice = activeId && saved ? { model: saved.model ?? '', effort: saved.effort ?? '' } : pick
  const choose = (next: { model: string; effort: string }) => {
    if (!activeId) return setPick(next)
    queryClient.setQueryData<{ conversation: Conversation; messages: Message[] }>(['conversation', activeId], (d) =>
      d ? { ...d, conversation: { ...d.conversation, model: next.model || null, effort: next.effort || null } } : d,
    )
    void api.update(activeId, next).catch((err) => setError(describe(err)))
  }

  const setBalance = (next: number) =>
    queryClient.setQueryData<Me>(['me'], (me) => (me ? { ...me, balance: next } : me))

  const addFiles = (files: File[]) => {
    const room = MAX_FILES - pending.length
    if (files.length > room) setError(`Up to ${MAX_FILES} files per message.`)
    for (const file of files.slice(0, Math.max(room, 0))) {
      const key = crypto.randomUUID()
      const preview = file.type.startsWith('image/') ? URL.createObjectURL(file) : null
      setPending((all) => [...all, { key, name: file.name, preview }])
      api
        .upload(file)
        .then((attachment) =>
          setPending((all) => all.map((p) => (p.key === key ? { ...p, attachment } : p))),
        )
        .catch((err) => {
          setPending((all) => all.filter((p) => p.key !== key))
          setError(describe(err))
        })
    }
  }

  const uploading = pending.some((p) => !p.attachment)

  const send = async (text?: string, event?: FormEvent) => {
    event?.preventDefault()
    const content = (text ?? draft).trim()
    const attached = text === undefined ? pending : []
    if ((!content && !attached.length) || streaming !== null || uploading || broke) return
    setDraft('')
    setPending([])
    setError(null)
    setStreaming('')
    setLiveTools([])
    setAtBottom(true)
    const controller = new AbortController()
    abort.current = controller
    try {
      let id = activeId
      if (!id) {
        const conversation = await api.createConversation()
        id = conversation.id
        if (pick.model || pick.effort) await api.update(id, pick)
        setActiveId(id)
      }
      const target = id
      await streamMessage(
        target,
        content,
        attached.map((p) => p.attachment!.id),
        {
          accepted: ({ message, title: newTitle }) => {
            setMessages((current) => [...current, message])
            setLiveTitle(newTitle)
            if (target !== conversationId) navigate(`/c/${target}`, { replace: !conversationId })
            queryClient.invalidateQueries({ queryKey: ['conversations'] })
          },
          delta: ({ text: chunk }) => setStreaming((current) => (current ?? '') + chunk),
          tool_started: (call) =>
            setLiveTools((current) => [...current, { ...call, output: '', ok: true }]),
          tool_finished: (call) =>
            setLiveTools((current) => current.map((t) => (t.id === call.id ? call : t))),
          compacted: ({ cost, balance: next }) => {
            setBalance(next)
            setSpent((all) => ({ ...all, [target]: (all[target] ?? 0) + cost }))
          },
          completed: ({ message, cost, balance: next }) => {
            setLiveTools([])
            setMessages((current) => [...current, message])
            setSpent((all) => ({ ...all, [target]: (all[target] ?? 0) + cost }))
            setBalance(next)
          },
          title: ({ title: generated, cost, balance: next }) => {
            setLiveTitle(generated)
            setBalance(next)
            setSpent((all) => ({ ...all, [target]: (all[target] ?? 0) + cost }))
            queryClient.invalidateQueries({ queryKey: ['conversations'] })
          },
          failed: ({ message, balance: next }) => {
            setLiveTools([])
            setMessages((current) => [...current, message])
            setBalance(next)
          },
          error: ({ code }) => {
            if (code === 'insufficient_credits') setCapped(true)
            setError(code)
          },
        },
        controller.signal,
      )
      queryClient.invalidateQueries({ queryKey: ['conversation', target] })
    } catch (err) {
      if (controller.signal.aborted) {
        setError('Stopped. The partial reply will appear after a refresh.')
      } else {
        if (err instanceof ApiError && err.status === 402) setCapped(true)
        setError(describe(err))
        setDraft(content)
        setPending(attached)
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

  const until = detail.data?.conversation.summary_until
  const lastSummarized = until ? messages.filter((m) => m.created_at <= until).length - 1 : -1
  const heading = liveTitle ?? title ?? detail.data?.conversation.title
  const missing = detail.error instanceof ApiError && detail.error.status === 404
  const empty = !activeId && messages.length === 0 && streaming === null
  const last = [...messages].reverse().find((m) => m.role === 'assistant' && m.status === 'completed')
  const tokens = last ? last.usage.input_tokens + last.usage.output_tokens : 0
  const window_ = contextWindow(last?.model ?? null)
  const pct = Math.min(100, (tokens / window_) * 100)
  const cost = activeId ? spent[activeId] : undefined

  return (
    <>
      <header className="top">
        <button className="icon side-btn" onClick={onOpenSide} aria-label="Show sidebar">
          <SidebarIcon />
        </button>
        <div className="crumb">
          <span className="p">Chats</span>
          <Chevron />
          <span className="t">{activeId ? heading ?? '…' : 'New chat'}</span>
        </div>
        <div className="right">
          {tokens > 0 && (
            <span className="ring" title={`${Math.round(tokens / 1000)}k of ${Math.round(window_ / 1000)}k tokens in context`}>
              <svg viewBox="0 0 36 36">
                <circle cx="18" cy="18" r="14" fill="none" stroke="var(--track)" strokeWidth="4" />
                <circle cx="18" cy="18" r="14" fill="none" stroke="var(--text-2)" strokeWidth="4" strokeDasharray={`${(pct / 100) * 88} 88`} />
              </svg>
              <span>{pct < 1 && pct > 0 ? '<1' : Math.round(pct)}%</span>
            </span>
          )}
          {cost !== undefined && (
            <span className="cost" title="Credits used by this chat since the page opened">
              {cost.toLocaleString()} cr
            </span>
          )}
          <button className="icon" onClick={onNew} data-tip="New chat (⇧⌘O)" aria-label="New chat">
            <NewChat />
          </button>
        </div>
      </header>
      <div className="convo">
        <div
          className="msgs"
          ref={scroller}
          onClick={onCopy}
          onScroll={(e) => {
            const el = e.currentTarget
            setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 40)
          }}
        >
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
            {messages.map((m, i) => (
              <Fragment key={m.id}>
                <Turn message={m} onZoom={setZoom} />
                {i === lastSummarized && (
                  <div className="summarized" title="Older messages are sent to the model as a summary to save context">
                    Earlier messages summarized
                  </div>
                )}
              </Fragment>
            ))}
            {streaming !== null && (
              <div className="turn assistant">
                {liveTools.length > 0 && <Steps calls={liveTools} running />}
                {streaming ? (
                  <div
                    className="msg assistant"
                    dangerouslySetInnerHTML={{ __html: renderMarkdown(streaming) + '<span class="cursor"></span>' }}
                  />
                ) : liveTools.length > 0 && liveTools.every((t) => t.output) ? null : (
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
          {!atBottom && (
            <button type="button" className="jump" onClick={toBottom}>
              <ArrowDown />
              Latest
            </button>
          )}
          {broke && (
            <div className="note-err capped">
              You are out of credits. Replies are paused until your balance is topped up.
            </div>
          )}
          <form
            className="composer"
            onSubmit={(e) => void send(undefined, e)}
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => {
              e.preventDefault()
              addFiles([...e.dataTransfer.files])
            }}
          >
            {pending.length > 0 && (
              <div className="shots">
                {pending.map((p) => (
                  <div key={p.key} className={`shot ${p.attachment ? '' : 'busy'}`}>
                    {p.preview ? (
                      <img src={p.preview} alt={p.name} onClick={() => setZoom(p.preview)} />
                    ) : (
                      <span className="chip box">
                        <FileIcon />
                        <span>{p.name}</span>
                      </span>
                    )}
                    <button
                      type="button"
                      aria-label={`Remove ${p.name}`}
                      onClick={() => setPending((all) => all.filter((x) => x.key !== p.key))}
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}
            <textarea
              onPaste={(e) => {
                const files = [...e.clipboardData.files]
                if (files.length) {
                  e.preventDefault()
                  addFiles(files)
                }
              }}
              ref={input}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Ask anything"
              rows={2}
              aria-label="Message"
            />
            <div className="bar">
              <input
                ref={picker}
                type="file"
                accept={ACCEPT}
                multiple
                hidden
                onChange={(e) => {
                  addFiles([...(e.target.files ?? [])])
                  e.target.value = ''
                }}
              />
              <button
                type="button"
                className="icon"
                data-tip="Attach images or PDFs"
                aria-label="Attach files"
                disabled={streaming !== null || pending.length >= MAX_FILES}
                onClick={() => picker.current?.click()}
              >
                <Clip />
              </button>
              <Picker
                label="Model"
                value={choice.model}
                disabled={streaming !== null}
                options={[{ value: '', label: 'Auto' }, ...(models.data ?? []).map((m) => ({ value: m.id, label: m.label }))]}
                onChange={(model) => choose({ ...choice, model })}
              />
              <Picker
                label="Effort"
                value={choice.effort}
                fallback="medium"
                disabled={streaming !== null}
                options={EFFORTS}
                onChange={(effort) => choose({ ...choice, effort })}
              />
              <span className={`status ${error ? 'err' : ''}`}>
                {error ?? (streaming !== null ? 'Streaming…' : '')}
              </span>
              {streaming !== null ? (
                <button type="button" className="sendi" onClick={() => abort.current?.abort()} aria-label="Stop" title="Stop">
                  <Stop />
                </button>
              ) : (
                <button type="submit" className="sendi" disabled={(!draft.trim() && !pending.length) || uploading || broke} aria-label="Send" title="Send">
                  <Send />
                </button>
              )}
            </div>
          </form>
          {zoom && (
            <div className="lightbox" onClick={() => setZoom(null)}>
              <img src={zoom} alt="" />
            </div>
          )}
          <p className="hint">↵ send · ⇧↵ newline · ⇧⌘O new chat</p>
        </div>
      </div>
    </>
  )
}

function Turn({ message, onZoom }: { message: Message; onZoom: (url: string) => void }) {
  if (message.role === 'user') {
    return (
      <div className="turn user">
        <div className="msg user">
          {message.attachments.length > 0 && (
            <div className="atts">
              {message.attachments.map((a) => {
                const url = `/api/attachments/${a.id}`
                return a.mime.startsWith('image/') ? (
                  <img key={a.id} className="att" src={url} alt={a.filename} onClick={() => onZoom(url)} />
                ) : (
                  <a key={a.id} className="chip box" href={url} target="_blank" rel="noreferrer">
                    <FileIcon />
                    <span>{a.filename}</span>
                  </a>
                )
              })}
            </div>
          )}
          {message.content}
        </div>
        <div className="acts">
          <span className="ago">{when(message.created_at)}</span>
        </div>
      </div>
    )
  }
  const html = message.content ? withCopyButtons(renderMarkdown(message.content)) : ''
  return (
    <div className="turn assistant">
      {message.tool_calls.length > 0 && <Steps calls={message.tool_calls} />}
      {html && <div className="msg assistant" dangerouslySetInnerHTML={{ __html: html }} />}
      {message.status === 'failed' && (
        <div className="note-err">The reply failed ({message.error}). Credits were refunded.</div>
      )}
      <div className="acts">
        <button
          className="icon"
          data-tip="Copy"
          onClick={() => void navigator.clipboard.writeText(message.content)}
        >
          <Copy />
        </button>
        {message.model && (
          <span className="ago">
            {message.provider} · {message.model} · {message.usage.input_tokens.toLocaleString()}→
            {message.usage.output_tokens.toLocaleString()} tok
            {message.cost > 0 && ` · ${message.cost.toLocaleString()} cr`}
          </span>
        )}
      </div>
    </div>
  )
}

const VERB: Record<string, string> = { web_search: 'Search', fetch_url: 'Fetch' }

function target(raw: string): string {
  try {
    const args = JSON.parse(raw) as Record<string, unknown>
    return String(args.query ?? args.url ?? Object.values(args)[0] ?? '').replace(/\s+/g, ' ')
  } catch {
    return raw
  }
}

function Steps({ calls, running }: { calls: ToolCall[]; running?: boolean }) {
  const n = calls.length
  return (
    <details className="steps" open={running}>
      <summary>
        <ChevronDown />
        <span>
          Used <b>{n} tool{n === 1 ? '' : 's'}</b>
        </span>
      </summary>
      <div className="list">
        {calls.map((call) => (
          <details key={call.id} className={`step ${call.ok ? '' : 'err'}`}>
            <summary>
              <span className="v">{VERB[call.name] ?? call.name}</span>
              <span className="w">{target(call.arguments)}</span>
              <span className="r">{!call.output ? '…' : call.ok ? 'done' : 'failed'}</span>
            </summary>
            <pre>{call.output || call.arguments}</pre>
          </details>
        ))}
      </div>
    </details>
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
