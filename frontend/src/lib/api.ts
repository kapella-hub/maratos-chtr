const API_BASE = '/api'

export interface Agent {
  id: string
  name: string
  description: string
  icon: string
  model: string
  is_default?: boolean
}

export interface Session {
  id: string
  agent_id: string
  title: string | null
  created_at: string
  updated_at: string
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  created_at: string
}

export interface Config {
  app_name: string
  debug: boolean
  default_model: string
  max_context_tokens: number
  max_response_tokens: number
  workspace: string
}

// Agents
export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/agents`)
  if (!res.ok) throw new Error('Failed to fetch agents')
  return res.json()
}

// Sessions
export async function fetchSessions(): Promise<Session[]> {
  const res = await fetch(`${API_BASE}/chat/sessions`)
  if (!res.ok) throw new Error('Failed to fetch sessions')
  return res.json()
}

export async function fetchSession(id: string): Promise<{ session: Session; messages: Message[] }> {
  const res = await fetch(`${API_BASE}/chat/sessions/${id}`)
  if (!res.ok) throw new Error('Failed to fetch session')
  return res.json()
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete session')
}

// Chat event types
export type ChatEventType = 
  | 'session_id' 
  | 'content' 
  | 'done' 
  | 'agent' 
  | 'thinking'
  | 'orchestrating'
  | 'subagent'
  | 'subagent_result'

export interface ChatEvent {
  type: ChatEventType
  data?: string | boolean | number
  subagent?: string
  taskId?: string
  status?: string
  progress?: number
  error?: string
}

// Chat
export async function* streamChat(
  message: string,
  agentId: string = 'mo',
  sessionId?: string,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, agent_id: agentId, session_id: sessionId }),
    signal,
  })

  if (!res.ok) throw new Error('Failed to send message')

  const reader = res.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6)
        if (data === '[DONE]') {
          yield { type: 'done' }
        } else {
          try {
            const parsed = JSON.parse(data)
            if (parsed.session_id) {
              yield { type: 'session_id', data: parsed.session_id }
            }
            if (parsed.agent) {
              yield { type: 'agent', data: parsed.agent }
            }
            if (parsed.thinking !== undefined) {
              yield { type: 'thinking', data: parsed.thinking }
            }
            if (parsed.orchestrating !== undefined) {
              yield { type: 'orchestrating', data: parsed.orchestrating }
            }
            if (parsed.subagent) {
              yield { 
                type: 'subagent', 
                subagent: parsed.subagent,
                taskId: parsed.task_id,
                status: parsed.status,
                progress: parsed.progress,
                error: parsed.error,
              }
            }
            if (parsed.subagent_result) {
              console.log('🎯 subagent_result event:', {
                agent: parsed.subagent_result,
                contentLength: parsed.content?.length,
                contentPreview: parsed.content?.slice(0, 100),
              })
              yield { 
                type: 'subagent_result', 
                subagent: parsed.subagent_result,
                data: parsed.content || '',
              }
            } else if (parsed.content) {
              // Only yield content if NOT part of subagent_result
              yield { type: 'content', data: parsed.content.replace(/\\n/g, '\n') }
            }
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  }
}

// Config
export async function fetchConfig(): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`)
  if (!res.ok) throw new Error('Failed to fetch config')
  return res.json()
}

export async function updateConfig(data: Partial<Config>): Promise<Config> {
  const res = await fetch(`${API_BASE}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error('Failed to update config')
  return res.json()
}
