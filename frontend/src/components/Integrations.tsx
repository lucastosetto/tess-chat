import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState, type FormEvent } from 'react'
import { api, ApiError, type Agent } from '../api'
import { Drive, Gmail, Google, Refresh, Trash } from '../icons'
import { when } from '../time'

function message(err: unknown): string {
  return err instanceof ApiError ? err.message : 'Something went wrong.'
}

const GOOGLE_RESULT: Record<string, string> = {
  connected: 'Google connected.',
  cancelled: 'Google connection was cancelled.',
  failed: 'Google connection failed. Try again.',
  unavailable: 'Google connections are not configured on this server.',
}

export function ConnectionsSection() {
  const queryClient = useQueryClient()
  const connections = useQuery({ queryKey: ['connections'], queryFn: api.connections })
  const result = new URLSearchParams(window.location.search).get('google')
  const google = connections.data?.connections.find((c) => c.provider === 'google')
  const disconnect = useMutation({
    mutationFn: api.disconnectGoogle,
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ['connections'] }),
  })
  const connect = (products: string) => window.location.assign(`/api/connections/google/start?products=${products}`)

  return (
    <section className="sec" id="connections" aria-labelledby="h-con">
      <div>
        <h2 id="h-con">Connections</h2>
        <p>Let Tess read your Google Drive files and Gmail messages. Access is read-only and you can revoke it anytime.</p>
      </div>
      {result && GOOGLE_RESULT[result] && <p className={result === 'connected' ? 'meta' : 'form-err'}>{GOOGLE_RESULT[result]}</p>}
      <div className="card">
        <div>
          <Google />
          <div className="grow">
            Google
            <span>
              {!connections.data
                ? 'Loading…'
                : !connections.data.google_available
                  ? 'Not configured on this server.'
                  : google
                    ? `${google.account} · ${google.products.join(', ') || 'no products'}`
                    : 'Not connected.'}
            </span>
          </div>
          {connections.data?.google_available &&
            (google ? (
              <button className="b sm danger-b" disabled={disconnect.isPending} onClick={() => disconnect.mutate()}>
                Disconnect
              </button>
            ) : (
              <button className="b sm" onClick={() => connect('drive,gmail')}>
                Connect all
              </button>
            ))}
        </div>
        {connections.data?.google_available &&
          (['drive', 'gmail'] as const).map((product) => (
            <div key={product}>
              {product === 'drive' ? <Drive /> : <Gmail />}
              <div className="grow">
                {product === 'drive' ? 'Google Drive' : 'Gmail'}
                <span>{product === 'drive' ? 'Search and read Docs, Sheets, Slides, PDFs and text files.' : 'Search and read your email.'}</span>
              </div>
              {google?.products.includes(product) ? (
                <span className="meta">Connected</span>
              ) : (
                <button className="b sm" onClick={() => connect(product)}>
                  Connect
                </button>
              )}
            </div>
          ))}
      </div>
    </section>
  )
}

export function McpSection() {
  const queryClient = useQueryClient()
  const servers = useQuery({ queryKey: ['mcp'], queryFn: api.mcpServers })
  const dialog = useRef<HTMLDialogElement>(null)
  const [form, setForm] = useState({ name: '', url: '', headers: '' })
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['mcp'] })
  const add = useMutation({
    mutationFn: () => {
      const headers: Record<string, string> = {}
      for (const line of form.headers.split('\n')) {
        const at = line.indexOf(':')
        if (at > 0) headers[line.slice(0, at).trim()] = line.slice(at + 1).trim()
      }
      return api.addMcpServer({ name: form.name, url: form.url, headers })
    },
    onSuccess: () => {
      setForm({ name: '', url: '', headers: '' })
      dialog.current?.close()
      refresh()
    },
  })
  const reload = useMutation({ mutationFn: api.refreshMcpServer, onSettled: refresh })
  const toggle = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => api.toggleMcpServer(id, enabled),
    onSettled: refresh,
  })
  const remove = useMutation({ mutationFn: api.removeMcpServer, onSettled: refresh })
  const submit = (e: FormEvent) => {
    e.preventDefault()
    add.mutate()
  }
  const list = servers.data ?? []

  return (
    <section className="sec" aria-labelledby="h-mcp">
      <div className="sec-hd">
        <div>
          <h2 id="h-mcp">MCP servers</h2>
          <p>Connect remote MCP servers (streamable HTTP). Their tools become available in every chat.</p>
        </div>
        <button className="b sm" onClick={() => dialog.current?.showModal()}>
          Add server
        </button>
      </div>
      <div className="card">
        {list.length === 0 && <div className="empty-row">{servers.isPending ? 'Loading…' : 'No servers yet.'}</div>}
        {list.map((s) => (
          <div key={s.id}>
            <div className="grow">
              {s.name}
              <span>
                {s.url}
                {s.has_headers && ' · auth headers saved'}
                {s.tools_refreshed_at && ` · tools fetched ${when(s.tools_refreshed_at)}`}
              </span>
              {s.last_error && <span className="err">{s.last_error}</span>}
              {s.tools.length > 0 && (
                <div className="tags">
                  {s.tools.map((t) => (
                    <span key={t.name} className="tag" title={t.description}>
                      {t.name}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <button
              className="icon"
              data-tip="Refresh tools"
              aria-label="Refresh tools"
              disabled={reload.isPending}
              onClick={() => reload.mutate(s.id)}
            >
              <Refresh />
            </button>
            <button
              className="switch"
              role="switch"
              aria-checked={s.enabled}
              aria-label={`Enable ${s.name}`}
              onClick={() => toggle.mutate({ id: s.id, enabled: !s.enabled })}
            />
            <button className="icon danger" data-tip="Remove" aria-label="Remove" onClick={() => remove.mutate(s.id)}>
              <Trash />
            </button>
          </div>
        ))}
      </div>
      <dialog ref={dialog} aria-labelledby="mcp-t">
        <h3 id="mcp-t">Add MCP server</h3>
        <form className="form" onSubmit={submit}>
          <div className="two">
            <label>
              Name
              <input required maxLength={40} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="deepwiki" />
            </label>
            <label>
              URL
              <input required type="url" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} placeholder="https://mcp.deepwiki.com/mcp" />
            </label>
          </div>
          <label>
            Headers (optional)
            <textarea
              style={{ minHeight: 64 }}
              value={form.headers}
              onChange={(e) => setForm({ ...form, headers: e.target.value })}
              placeholder="Authorization: Bearer …"
            />
            <span className="hint">One per line. Stored encrypted and never shown again.</span>
          </label>
          <div className="actions">
            {add.error && <span className="form-err">{message(add.error)}</span>}
            <button type="button" className="b ghost" onClick={() => dialog.current?.close()}>
              Cancel
            </button>
            <button type="submit" className="b primary" disabled={add.isPending}>
              {add.isPending ? 'Connecting…' : 'Add'}
            </button>
          </div>
        </form>
      </dialog>
    </section>
  )
}

const BLANK: { name: string; instructions: string; model: string; tools: string[] | null } = {
  name: '',
  instructions: '',
  model: '',
  tools: null,
}

const BUILT_IN_TOOLS = [
  { value: 'web', label: 'Web search & fetch' },
  { value: 'drive', label: 'Google Drive' },
  { value: 'gmail', label: 'Gmail' },
]

export function AgentsSection() {
  const queryClient = useQueryClient()
  const agents = useQuery({ queryKey: ['agents'], queryFn: api.agents })
  const models = useQuery({ queryKey: ['models'], queryFn: api.models, staleTime: Infinity })
  const servers = useQuery({ queryKey: ['mcp'], queryFn: api.mcpServers })
  const groups = [
    ...BUILT_IN_TOOLS,
    ...(servers.data ?? []).map((s) => ({ value: `mcp:${s.name}`, label: `MCP · ${s.name}` })),
  ]
  const dialog = useRef<HTMLDialogElement>(null)
  const [editing, setEditing] = useState<string | undefined>()
  const [form, setForm] = useState(BLANK)
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ['agents'] })
  const save = useMutation({
    mutationFn: () => api.saveAgent({ ...form, model: form.model || null }, editing),
    onSuccess: () => {
      dialog.current?.close()
      refresh()
    },
  })
  const remove = useMutation({ mutationFn: api.removeAgent, onSettled: refresh })
  const open = (agent?: Agent) => {
    setEditing(agent?.id)
    setForm(
      agent ? { name: agent.name, instructions: agent.instructions, model: agent.model ?? '', tools: agent.tools } : BLANK,
    )
    save.reset()
    dialog.current?.showModal()
  }
  const submit = (e: FormEvent) => {
    e.preventDefault()
    save.mutate()
  }
  const list = agents.data ?? []

  return (
    <section className="sec" aria-labelledby="h-agents">
      <div className="sec-hd">
        <div>
          <h2 id="h-agents">Agents</h2>
          <p>Saved instructions and a default model. Pick an agent in the composer to use it in a chat.</p>
        </div>
        <button className="b sm" onClick={() => open()}>
          New agent
        </button>
      </div>
      <div className="card">
        {list.length === 0 && <div className="empty-row">{agents.isPending ? 'Loading…' : 'No agents yet.'}</div>}
        {list.map((a) => (
          <div key={a.id}>
            <div className="grow">
              {a.name}
              <span>
                {(a.model && models.data?.find((m) => m.id === a.model)?.label) ?? a.model ?? 'Auto model'} ·{' '}
                {a.tools === null ? 'all tools' : a.tools.length ? a.tools.join(', ') : 'no tools'} · edited{' '}
                {when(a.updated_at)}
              </span>
            </div>
            <button className="b sm ghost" onClick={() => open(a)}>
              Edit
            </button>
            <button className="icon danger" data-tip="Delete" aria-label="Delete" onClick={() => remove.mutate(a.id)}>
              <Trash />
            </button>
          </div>
        ))}
      </div>
      <dialog ref={dialog} aria-labelledby="agent-t">
        <h3 id="agent-t">{editing ? 'Edit agent' : 'New agent'}</h3>
        <form className="form" onSubmit={submit}>
          <div className="two">
            <label>
              Name
              <input required maxLength={80} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Code reviewer" />
            </label>
            <label>
              Model
              <select value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })}>
                <option value="">Auto</option>
                {(models.data ?? []).map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label>
            Instructions
            <textarea
              required
              maxLength={8000}
              value={form.instructions}
              onChange={(e) => setForm({ ...form, instructions: e.target.value })}
              placeholder="You review code for bugs and security issues. Answer with a short list."
            />
          </label>
          <fieldset className="tools-pick">
            <legend>Tools</legend>
            <label className="check">
              <input
                type="checkbox"
                checked={form.tools === null}
                onChange={(e) => setForm({ ...form, tools: e.target.checked ? null : [] })}
              />
              All tools, including ones added later
            </label>
            {form.tools !== null &&
              groups.map((g) => (
                <label key={g.value} className="check">
                  <input
                    type="checkbox"
                    checked={form.tools!.includes(g.value)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        tools: e.target.checked
                          ? [...form.tools!, g.value]
                          : form.tools!.filter((t) => t !== g.value),
                      })
                    }
                  />
                  {g.label}
                </label>
              ))}
          </fieldset>
          <div className="actions">
            {save.error && <span className="form-err">{message(save.error)}</span>}
            <button type="button" className="b ghost" onClick={() => dialog.current?.close()}>
              Cancel
            </button>
            <button type="submit" className="b primary" disabled={save.isPending}>
              Save
            </button>
          </div>
        </form>
      </dialog>
    </section>
  )
}

export function SharesSection() {
  const queryClient = useQueryClient()
  const shares = useQuery({ queryKey: ['shares', 'all'], queryFn: () => api.shares() })
  const revoke = useMutation({
    mutationFn: api.revokeShare,
    onSettled: () => void queryClient.invalidateQueries({ queryKey: ['shares'] }),
  })
  const list = shares.data ?? []

  return (
    <section className="sec" aria-labelledby="h-shares">
      <div>
        <h2 id="h-shares">Shared links</h2>
        <p>Public read-only links to your chats. Revoking one stops it working at once.</p>
      </div>
      <div className="card">
        {list.length === 0 && <div className="empty-row">{shares.isPending ? 'Loading…' : 'No active links.'}</div>}
        {list.map((s) => (
          <div key={s.id}>
            <div className="grow">
              {s.title}
              <span>Created {when(s.created_at)}</span>
            </div>
            <a className="b sm ghost" href={`/c/${s.conversation_id}`}>
              Open chat
            </a>
            <button className="b sm danger-b" disabled={revoke.isPending} onClick={() => revoke.mutate(s.id)}>
              Revoke
            </button>
          </div>
        ))}
      </div>
    </section>
  )
}
