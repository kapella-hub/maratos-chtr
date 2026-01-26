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
  allowed_write_dirs: string
  all_allowed_dirs: string[]
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
  | 'model_thinking'
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
            if (parsed.model_thinking !== undefined) {
              yield { type: 'model_thinking', data: parsed.model_thinking }
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

// Projects
export interface Project {
  name: string
  description: string
  path: string
  tech_stack: string[]
  conventions: string[]
  patterns: string[]
  dependencies: string[]
  notes: string
}

export async function fetchProjects(): Promise<Project[]> {
  const res = await fetch(`${API_BASE}/projects`)
  if (!res.ok) throw new Error('Failed to fetch projects')
  return res.json()
}

export async function fetchProject(name: string): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(name)}`)
  if (!res.ok) throw new Error('Failed to fetch project')
  return res.json()
}

export async function createProject(project: Project): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create project' }))
    throw new Error(error.detail || 'Failed to create project')
  }
  return res.json()
}

export async function updateProject(name: string, project: Project): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(project),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to update project' }))
    throw new Error(error.detail || 'Failed to update project')
  }
  return res.json()
}

export async function deleteProject(name: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete project')
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

// Autonomous Types
export interface AutonomousProject {
  id: string
  name: string
  original_prompt: string
  workspace_path: string
  status: string
  progress: number
  tasks_completed: number
  tasks_failed: number
  tasks_pending: number
  total_iterations: number
  branch_name?: string
  pr_url?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface AutonomousTask {
  id: string
  title: string
  description: string
  agent_type: string
  status: string
  depends_on: string[]
  quality_gates: Array<{
    type: string
    required: boolean
    passed: boolean
    error?: string
  }>
  current_attempt: number
  max_attempts: number
  priority: number
  target_files: string[]
  final_commit_sha?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface StartProjectRequest {
  name: string
  prompt: string
  workspace_path?: string
  auto_commit?: boolean
  push_to_remote?: boolean
  create_pr?: boolean
  pr_base_branch?: string
  max_runtime_hours?: number
  max_total_iterations?: number
  parallel_tasks?: number
}

export interface AutonomousEvent {
  type: string
  project_id: string
  data: Record<string, unknown>
  timestamp: string
}

// Autonomous API
export async function fetchAutonomousProjects(): Promise<AutonomousProject[]> {
  const res = await fetch(`${API_BASE}/autonomous/projects`)
  if (!res.ok) throw new Error('Failed to fetch autonomous projects')
  return res.json()
}

export async function fetchAutonomousProject(id: string): Promise<{
  project: AutonomousProject
  tasks: AutonomousTask[]
}> {
  const res = await fetch(`${API_BASE}/autonomous/projects/${id}`)
  if (!res.ok) throw new Error('Failed to fetch autonomous project')
  return res.json()
}

export async function* streamAutonomousProject(
  request: StartProjectRequest,
  signal?: AbortSignal
): AsyncGenerator<AutonomousEvent> {
  const res = await fetch(`${API_BASE}/autonomous/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal,
  })

  if (!res.ok) throw new Error('Failed to start autonomous project')

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
          return
        }
        try {
          const event = JSON.parse(data) as AutonomousEvent
          yield event
        } catch {
          // Ignore parse errors
        }
      }
    }
  }
}

export async function pauseAutonomousProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/autonomous/projects/${id}/pause`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to pause project')
}

export async function resumeAutonomousProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/autonomous/projects/${id}/resume`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to resume project')
}

export async function cancelAutonomousProject(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/autonomous/projects/${id}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to cancel project')
}

export async function retryAutonomousTask(
  projectId: string,
  taskId: string
): Promise<void> {
  const res = await fetch(
    `${API_BASE}/autonomous/projects/${projectId}/tasks/${taskId}/retry`,
    { method: 'POST' }
  )
  if (!res.ok) throw new Error('Failed to retry task')
}

export async function fetchAutonomousStats(): Promise<{
  total_projects: number
  active_projects: number
  running_orchestrators: number
  by_status: Record<string, number>
}> {
  const res = await fetch(`${API_BASE}/autonomous/stats`)
  if (!res.ok) throw new Error('Failed to fetch autonomous stats')
  return res.json()
}
