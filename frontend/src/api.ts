export type User = { id: string; email: string; name: string; role: string }
export type Me = { user: User; balance: number }
export type Conversation = {
  id: string
  title: string
  model: string | null
  effort: string | null
  pinned: boolean
  archived: boolean
  summary_until: string | null
  agent_id: string | null
  created_at: string
  updated_at: string
}
export type Usage = { input_tokens: number; output_tokens: number; cached_input_tokens: number }
export type ToolCall = { id: string; name: string; arguments: string; output: string; ok: boolean }
export type Attachment = { id: string; filename: string; mime: string; size: number }
export type Message = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  status: 'pending' | 'completed' | 'failed'
  model: string | null
  provider: string | null
  usage: Usage
  error: string | null
  cost: number
  tool_calls: ToolCall[]
  attachments: Attachment[]
  created_at: string
}
export type ConversationDetail = { conversation: Conversation; messages: Message[] }
export type AuditEvent = {
  id: string
  at: string
  action: string
  subject_type: string
  subject_id: string | null
  payload: Record<string, unknown>
  request_id: string | null
  trace_id: string | null
}
export type DayUsage = {
  day: string
  replies: number
  failed: number
  input_tokens: number
  output_tokens: number
  credits: number
  tool_calls: number
}
export type UsageReport = {
  days: DayUsage[]
  models: { model: string; replies: number; credits: number }[]
  balance: number
}
export type ModelOption = { id: string; provider: string; label: string }
export type AuthConfig = { google_login: boolean; email_login: boolean }

export type ConversationChanges = Partial<Pick<Conversation, 'title' | 'pinned' | 'archived'>> & {
  model?: string
  effort?: string
  agent_id?: string
  clear_agent?: boolean
}
export type ShareLink = { id: string; conversation_id: string; title: string; created_at: string; url: string | null }
export type SharedMessage = Pick<Message, 'id' | 'role' | 'content' | 'model' | 'tool_calls' | 'attachments' | 'created_at'>
export type SharedConversation = { title: string; shared_at: string; messages: SharedMessage[] }
export type McpServer = {
  id: string
  name: string
  url: string
  enabled: boolean
  has_headers: boolean
  tools: { name: string; description: string }[]
  tools_refreshed_at: string | null
  last_error: string | null
  created_at: string
}
export type Connection = { provider: string; account: string; products: string[]; updated_at: string }
export type Connections = { google_available: boolean; connections: Connection[] }
export type Agent = {
  id: string
  name: string
  instructions: string
  model: string | null
  tools: string[] | null
  updated_at: string
}
export type AgentInput = { name: string; instructions: string; model: string | null; tools: string[] | null }
export type UserUsage = {
  user: User
  conversations: number
  replies: number
  input_tokens: number
  output_tokens: number
  spent: number
  balance: number
  last_active: string | null
}
export type AdminUsage = {
  days: number
  total_spent: number
  users: UserUsage[]
  tools: { name: string; calls: number; failures: number }[]
  failures: { error: string; count: number }[]
}

export class ApiError extends Error {
  status: number
  code: string
  constructor(status: number, code: string, detail?: string) {
    super(detail ?? code)
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, {
    credentials: 'include',
    ...init,
    headers: { 'Content-Type': 'application/json', ...init.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.error ?? 'error', body.detail)
  }
  return (response.status === 204 ? undefined : await response.json()) as T
}

export const api = {
  authConfig: () => request<AuthConfig>('/api/auth/config'),
  me: () => request<Me>('/api/auth/me'),
  emailLink: (email: string) =>
    request<void>('/api/auth/email', { method: 'POST', body: JSON.stringify({ email }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  conversations: () => request<Conversation[]>('/api/conversations'),
  createConversation: () =>
    request<Conversation>('/api/conversations', { method: 'POST', body: '{}' }),
  conversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  activity: () => request<AuditEvent[]>('/api/activity?limit=100'),
  usage: (days: number) => request<UsageReport>(`/api/usage?days=${days}`),
  models: () => request<ModelOption[]>('/api/models'),
  update: (id: string, changes: ConversationChanges) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  upload: async (file: File): Promise<Attachment> => {
    const form = new FormData()
    form.append('file', file)
    const response = await fetch('/api/attachments', { method: 'POST', credentials: 'include', body: form })
    if (!response.ok) {
      const body = await response.json().catch(() => ({}))
      throw new ApiError(response.status, body.error ?? 'error', body.detail)
    }
    return (await response.json()) as Attachment
  },
  remove: (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
  shares: (conversationId?: string) =>
    request<ShareLink[]>(`/api/shares${conversationId ? `?conversation_id=${conversationId}` : ''}`),
  share: (conversationId: string) =>
    request<ShareLink>(`/api/conversations/${conversationId}/shares`, { method: 'POST' }),
  revokeShare: (id: string) => request<void>(`/api/shares/${id}`, { method: 'DELETE' }),
  shared: (token: string) => request<SharedConversation>(`/api/shared/${encodeURIComponent(token)}`),
  mcpServers: () => request<McpServer[]>('/api/mcp-servers'),
  addMcpServer: (body: { name: string; url: string; headers: Record<string, string> }) =>
    request<McpServer>('/api/mcp-servers', { method: 'POST', body: JSON.stringify(body) }),
  refreshMcpServer: (id: string) => request<McpServer>(`/api/mcp-servers/${id}/refresh`, { method: 'POST' }),
  toggleMcpServer: (id: string, enabled: boolean) =>
    request<McpServer>(`/api/mcp-servers/${id}`, { method: 'PATCH', body: JSON.stringify({ enabled }) }),
  removeMcpServer: (id: string) => request<void>(`/api/mcp-servers/${id}`, { method: 'DELETE' }),
  connections: () => request<Connections>('/api/connections'),
  disconnectGoogle: () => request<void>('/api/connections/google', { method: 'DELETE' }),
  agents: () => request<Agent[]>('/api/agents'),
  saveAgent: (body: AgentInput, id?: string) =>
    request<Agent>(id ? `/api/agents/${id}` : '/api/agents', {
      method: id ? 'PUT' : 'POST',
      body: JSON.stringify(body),
    }),
  removeAgent: (id: string) => request<void>(`/api/agents/${id}`, { method: 'DELETE' }),
  adminUsage: (days: number) => request<AdminUsage>(`/api/admin/usage?days=${days}`),
}

export type StreamHandlers = {
  accepted: (data: { message: Message; title: string }) => void
  delta: (data: { text: string }) => void
  tool_started: (data: { id: string; name: string; arguments: string }) => void
  tool_finished: (data: ToolCall) => void
  compacted: (data: { summarized: number; cost: number; balance: number }) => void
  completed: (data: { message: Message; cost: number; balance: number }) => void
  title: (data: { title: string; cost: number; balance: number }) => void
  failed: (data: { message: Message; code: string; balance: number }) => void
  error: (data: { code: string }) => void
}

export type SendMode = 'send' | 'edit' | 'regenerate'

export async function streamMessage(
  conversationId: string,
  content: string,
  attachmentIds: string[],
  handlers: StreamHandlers,
  signal?: AbortSignal,
  mode: SendMode = 'send',
): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content, attachment_ids: attachmentIds, mode }),
    signal,
  })
  if (!response.ok || !response.body) {
    const body = await response.json().catch(() => ({}))
    throw new ApiError(response.status, body.error ?? 'error', body.detail)
  }
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += value
    let boundary = buffer.indexOf('\n\n')
    while (boundary !== -1) {
      dispatch(buffer.slice(0, boundary), handlers)
      buffer = buffer.slice(boundary + 2)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function dispatch(block: string, handlers: StreamHandlers) {
  let event = 'message'
  const data: string[] = []
  for (const line of block.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data.push(line.slice(5).trim())
  }
  if (!data.length || !(event in handlers)) return
  const handler = handlers[event as keyof StreamHandlers] as (payload: unknown) => void
  handler(JSON.parse(data.join('\n')))
}
