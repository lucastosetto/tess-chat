export type User = { id: string; email: string; name: string; role: string }
export type Me = { user: User; balance: number }
export type Conversation = {
  id: string
  title: string
  pinned: boolean
  archived: boolean
  created_at: string
  updated_at: string
}
export type Usage = { input_tokens: number; output_tokens: number; cached_input_tokens: number }
export type Message = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  status: 'pending' | 'completed' | 'failed'
  model: string | null
  provider: string | null
  usage: Usage
  error: string | null
  created_at: string
}
export type ConversationDetail = { conversation: Conversation; messages: Message[] }
export type AuthConfig = { dev_login: boolean; google_login: boolean }

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
  devLogin: (email: string, name: string) =>
    request<Me>('/api/auth/dev-login', { method: 'POST', body: JSON.stringify({ email, name }) }),
  logout: () => request<void>('/api/auth/logout', { method: 'POST' }),
  conversations: () => request<Conversation[]>('/api/conversations'),
  createConversation: () =>
    request<Conversation>('/api/conversations', { method: 'POST', body: '{}' }),
  conversation: (id: string) => request<ConversationDetail>(`/api/conversations/${id}`),
  update: (id: string, changes: Partial<Pick<Conversation, 'title' | 'pinned' | 'archived'>>) =>
    request<Conversation>(`/api/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(changes),
    }),
  remove: (id: string) => request<void>(`/api/conversations/${id}`, { method: 'DELETE' }),
}

export type StreamHandlers = {
  accepted: (data: { message: Message; title: string }) => void
  delta: (data: { text: string }) => void
  completed: (data: { message: Message; cost: number; balance: number }) => void
  failed: (data: { message: Message; code: string; balance: number }) => void
  error: (data: { code: string }) => void
}

export async function streamMessage(
  conversationId: string,
  content: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
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
