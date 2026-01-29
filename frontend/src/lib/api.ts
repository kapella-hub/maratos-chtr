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
  thinking_level: string
  max_context_tokens: number
  max_response_tokens: number
  workspace: string
  allowed_write_dirs: string
  all_allowed_dirs: string[]
  // Git settings
  git_auto_commit: boolean
  git_push_to_remote: boolean
  git_create_pr: boolean
  git_default_branch: string
  git_commit_prefix: string
  git_remote_name: string
  // GitLab integration
  gitlab_url: string
  gitlab_token: string
  gitlab_namespace: string
  gitlab_skip_ssl: boolean
  gitlab_configured: boolean
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

// Thinking step types
export type ThinkingStepType = 'analysis' | 'evaluation' | 'decision' | 'validation' | 'risk' | 'implementation' | 'critique'

// Thinking step data
export interface ThinkingStep {
  id: string
  type: ThinkingStepType
  content: string
  duration_ms?: number
  tokens?: number
  confidence?: number  // Optional confidence score (0-1)
}

// Thinking block data
export interface ThinkingBlock {
  id: string
  level: string
  template?: string | null
  steps?: ThinkingStep[]
  total_duration_ms?: number
  duration_ms?: number  // Alias for backward compatibility
  total_tokens?: number
  started_at?: string
  completed_at?: string | null
  is_complete?: boolean
}

// Chat event types
export type ChatEventType =
  | 'session_id'
  | 'content'
  | 'done'
  | 'agent'
  | 'model'
  | 'thinking'
  | 'model_thinking'
  | 'thinking_block'      // New: structured thinking block start
  | 'thinking_complete'   // New: structured thinking block complete
  | 'orchestrating'
  | 'subagent'
  | 'subagent_result'
  | 'canvas_create'
  | 'canvas_update'
  | 'canvas_delete'
  // Project context auto-detection
  | 'project_context_active'
  // Inline project events
  | 'project_detected'
  | 'planning_started'
  | 'plan_ready'
  | 'awaiting_approval'
  | 'plan_approved'
  | 'task_started'
  | 'task_progress'
  | 'task_completed'
  | 'task_failed'
  | 'project_paused'
  | 'project_resumed'
  | 'project_completed'
  | 'project_failed'
  | 'project_cancelled'
  | 'git_commit'
  | 'git_pr_created'

export interface SubagentGoal {
  id: number
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
}

export interface SubagentCheckpoint {
  name: string
  description: string
}

export interface SubagentGoalProgress {
  total: number
  completed: number
  current_id: number | null
  items: SubagentGoal[]
}

// Inline project types for events
export interface InlineProjectPlan {
  id: string
  name: string
  original_prompt: string
  workspace_path: string
  status: string
  tasks: Array<{
    id: string
    title: string
    description: string
    agent_type: string
    status: string
    depends_on: string[]
    quality_gates: Array<{ type: string; passed: boolean; error?: string }>
    progress?: number
    current_attempt?: number
    max_attempts?: number
    error?: string
  }>
  progress: number
  tasks_completed: number
  tasks_failed: number
  tasks_pending: number
  branch_name?: string
  pr_url?: string
}

// Project context info (for auto-detection)
export interface ProjectContextInfo {
  name: string
  auto_detected: boolean
}

export interface ChatEvent {
  type: ChatEventType
  data?: string | boolean | number
  subagent?: string
  taskId?: string
  status?: string
  progress?: number
  error?: string
  goals?: SubagentGoalProgress
  checkpoints?: SubagentCheckpoint[]
  // Retry tracking
  attempt?: number
  max_attempts?: number
  is_fallback?: boolean
  original_task_id?: string
  // Project context (auto-detected or explicit)
  projectContext?: ProjectContextInfo
  // Inline project data
  project?: InlineProjectPlan
  projectId?: string
  task?: InlineProjectPlan['tasks'][0]
  reason?: string
  complexity?: number
  estimatedTasks?: number
  commitSha?: string
  commitMessage?: string
  prUrl?: string
}

// Chat
export async function* streamChat(
  message: string,
  agentId: string = 'mo',
  sessionId?: string,
  signal?: AbortSignal,
  projectName?: string | null
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      agent_id: agentId,
      session_id: sessionId,
      project_name: projectName || undefined,
    }),
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
            if (parsed.model) {
              yield { type: 'model', data: parsed.model }
            }
            // Project context auto-detection
            if (parsed.project_context) {
              yield {
                type: 'project_context_active',
                projectContext: parsed.project_context as ProjectContextInfo,
              }
            }
            if (parsed.thinking !== undefined) {
              yield { type: 'thinking', data: parsed.thinking }
            }
            if (parsed.model_thinking !== undefined) {
              yield { type: 'model_thinking', data: parsed.model_thinking }
              // Also yield structured thinking data if present
              if (parsed.thinking_block) {
                yield { type: 'thinking_block', data: parsed.thinking_block }
              }
            }
            if (parsed.thinking_complete) {
              yield { type: 'thinking_complete', data: parsed.thinking_complete }
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
                goals: parsed.goals,
                checkpoints: parsed.checkpoints,
                // Retry tracking
                attempt: parsed.attempt,
                max_attempts: parsed.max_attempts,
                is_fallback: parsed.is_fallback,
                original_task_id: parsed.original_task_id,
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
            } else if (parsed.canvas_create) {
              // Canvas artifact created
              yield { type: 'canvas_create', data: parsed.canvas_create }
            } else if (parsed.canvas_update) {
              yield { type: 'canvas_update', data: parsed.canvas_update }
            } else if (parsed.canvas_delete) {
              yield { type: 'canvas_delete', data: parsed.canvas_delete }
            }
            // Inline project events - backend sends {type: "event_type", ...data}
            else if (parsed.type === 'project_detected') {
              yield {
                type: 'project_detected',
                reason: parsed.reason,
                complexity: parsed.complexity,
                estimatedTasks: parsed.estimated_tasks,
              }
            } else if (parsed.type === 'planning_started') {
              yield { type: 'planning_started', projectId: parsed.project_id }
            } else if (parsed.type === 'plan_ready') {
              yield { type: 'plan_ready', project: parsed.plan }
            } else if (parsed.type === 'awaiting_approval') {
              yield { type: 'awaiting_approval', projectId: parsed.project_id }
            } else if (parsed.type === 'plan_approved') {
              yield { type: 'plan_approved', projectId: parsed.project_id }
            } else if (parsed.type === 'task_started') {
              yield {
                type: 'task_started',
                projectId: parsed.project_id,
                task: parsed.task,
              }
            } else if (parsed.type === 'task_progress') {
              yield {
                type: 'task_progress',
                projectId: parsed.project_id,
                taskId: parsed.task_id,
                progress: parsed.progress,
                status: parsed.status,
              }
            } else if (parsed.type === 'task_completed') {
              yield {
                type: 'task_completed',
                projectId: parsed.project_id,
                taskId: parsed.task_id,
                task: parsed.task,
              }
            } else if (parsed.type === 'task_failed') {
              yield {
                type: 'task_failed',
                projectId: parsed.project_id,
                taskId: parsed.task_id,
                error: parsed.error,
              }
            } else if (parsed.type === 'project_paused') {
              yield { type: 'project_paused', projectId: parsed.project_id }
            } else if (parsed.type === 'project_resumed') {
              yield { type: 'project_resumed', projectId: parsed.project_id }
            } else if (parsed.type === 'project_completed') {
              yield {
                type: 'project_completed',
                projectId: parsed.project_id,
                project: parsed.project,
              }
            } else if (parsed.type === 'project_failed') {
              yield {
                type: 'project_failed',
                projectId: parsed.project_id,
                error: parsed.error,
              }
            } else if (parsed.type === 'project_cancelled') {
              yield { type: 'project_cancelled', projectId: parsed.project_id }
            } else if (parsed.type === 'git_commit') {
              yield {
                type: 'git_commit',
                projectId: parsed.project_id,
                commitSha: parsed.commit_sha,
                commitMessage: parsed.commit_message,
              }
            } else if (parsed.type === 'git_pr_created') {
              yield {
                type: 'git_pr_created',
                projectId: parsed.project_id,
                prUrl: parsed.pr_url,
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

// Inline Project Actions
export interface ProjectActionRequest {
  project_action: 'approve' | 'pause' | 'resume' | 'cancel' | 'adjust'
  project_adjustments?: {
    message?: string
    add_tasks?: string[]
    remove_tasks?: string[]
    modify_tasks?: Record<string, unknown>
  }
}

export async function* streamChatWithProjectAction(
  message: string,
  agentId: string = 'mo',
  sessionId: string,
  action: ProjectActionRequest,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message,
      agent_id: agentId,
      session_id: sessionId,
      ...action,
    }),
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
            // Handle project events - backend sends {type: "event_type", ...data}
            if (parsed.type === 'plan_approved') {
              yield { type: 'plan_approved', projectId: parsed.project_id }
            } else if (parsed.type === 'plan_ready') {
              yield { type: 'plan_ready', project: parsed.plan }
            } else if (parsed.type === 'plan_adjusted') {
              yield { type: 'plan_ready', project: parsed.plan }  // Re-emit as plan_ready
            } else if (parsed.type === 'awaiting_approval') {
              yield { type: 'awaiting_approval', projectId: parsed.project_id }
            } else if (parsed.type === 'project_paused') {
              yield { type: 'project_paused', projectId: parsed.project_id }
            } else if (parsed.type === 'project_resumed') {
              yield { type: 'project_resumed', projectId: parsed.project_id }
            } else if (parsed.type === 'project_cancelled') {
              yield { type: 'project_cancelled', projectId: parsed.project_id }
            } else if (parsed.type === 'task_started') {
              yield { type: 'task_started', projectId: parsed.project_id, task: parsed.task }
            } else if (parsed.type === 'task_progress') {
              yield { type: 'task_progress', projectId: parsed.project_id, taskId: parsed.task_id, progress: parsed.progress }
            } else if (parsed.type === 'task_completed') {
              yield { type: 'task_completed', projectId: parsed.project_id, taskId: parsed.task_id }
            } else if (parsed.type === 'task_failed') {
              yield { type: 'task_failed', projectId: parsed.project_id, taskId: parsed.task_id, error: parsed.error }
            } else if (parsed.type === 'project_completed') {
              yield { type: 'project_completed', projectId: parsed.project_id, project: parsed.project }
            } else if (parsed.type === 'project_failed') {
              yield { type: 'project_failed', projectId: parsed.project_id, error: parsed.error }
            } else if (parsed.content) {
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
  filesystem_access?: boolean
  auto_add_filesystem?: boolean
}

export interface ProjectAnalysis {
  tech_stack: string[]
  conventions: string[]
  patterns: string[]
  dependencies: string[]
  description: string
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

export async function analyzeProject(path: string): Promise<ProjectAnalysis> {
  const res = await fetch(`${API_BASE}/projects/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to analyze project' }))
    throw new Error(error.detail || 'Failed to analyze project')
  }
  return res.json()
}

export async function createProject(project: Project): Promise<Project> {
  const res = await fetch(`${API_BASE}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...project,
      auto_add_filesystem: project.auto_add_filesystem ?? true,
    }),
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
    body: JSON.stringify({
      ...project,
      auto_add_filesystem: project.auto_add_filesystem ?? true,
    }),
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

// Project Documentation
export interface ProjectDoc {
  id: string
  title: string
  content: string
  tags: string[]
  created_at: string
  updated_at: string
}

export interface ProjectDocListItem {
  id: string
  title: string
  tags: string[]
  created_at: string
  updated_at: string
  content_length: number
}

export async function fetchProjectDocs(projectName: string): Promise<ProjectDocListItem[]> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectName)}/docs`)
  if (!res.ok) throw new Error('Failed to fetch project docs')
  return res.json()
}

export async function fetchProjectDoc(projectName: string, docId: string): Promise<ProjectDoc> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectName)}/docs/${docId}`)
  if (!res.ok) throw new Error('Failed to fetch doc')
  return res.json()
}

export async function createProjectDoc(
  projectName: string,
  data: { title: string; content: string; tags?: string[] }
): Promise<ProjectDoc> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectName)}/docs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create doc' }))
    throw new Error(error.detail || 'Failed to create doc')
  }
  return res.json()
}

export async function updateProjectDoc(
  projectName: string,
  docId: string,
  data: { title?: string; content?: string; tags?: string[] }
): Promise<ProjectDoc> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectName)}/docs/${docId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to update doc' }))
    throw new Error(error.detail || 'Failed to update doc')
  }
  return res.json()
}

export async function deleteProjectDoc(projectName: string, docId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/projects/${encodeURIComponent(projectName)}/docs/${docId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to delete doc')
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

// Directory browsing (see Workspace Browse API section below for main browse function)

export async function addAllowedDirectory(path: string): Promise<{ added: string; all_allowed: string[] }> {
  const res = await fetch(`${API_BASE}/config/allowed-dirs/add?path=${encodeURIComponent(path)}`, {
    method: 'POST',
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to add directory' }))
    throw new Error(error.detail || error.error || 'Failed to add directory')
  }
  return res.json()
}

export async function removeAllowedDirectory(path: string): Promise<{ removed?: string; error?: string; all_allowed: string[] }> {
  const res = await fetch(`${API_BASE}/config/allowed-dirs/remove?path=${encodeURIComponent(path)}`, {
    method: 'DELETE',
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to remove directory' }))
    throw new Error(error.detail || 'Failed to remove directory')
  }
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
  // Git repository options
  git_mode?: 'new' | 'existing' | 'none'  // Create new repo, use existing, or no git
  git_remote_url?: string  // Remote URL for push (e.g., git@github.com:user/repo.git)
  git_init_repo?: boolean  // Initialize git repo if not exists
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

// Subagent Failure Stats
export interface FailureStats {
  total: number
  by_agent: Record<string, number>
  by_type: Record<string, number>
  total_retries: number
}

export interface FailureEntry {
  task_id: string
  agent_id: string
  task_description: string
  failure_type: string
  error_message: string
  attempt: number
  max_attempts: number
  duration_seconds: number
  last_checkpoint: string | null
  goals_completed: number
  goals_total: number
  timestamp: string
}

export async function fetchFailureStats(): Promise<{
  stats: FailureStats
  recent_failures: FailureEntry[]
}> {
  const res = await fetch(`${API_BASE}/subagents/failures`)
  if (!res.ok) throw new Error('Failed to fetch failure stats')
  return res.json()
}

export async function fetchAgentFailures(agentId: string, limit: number = 20): Promise<{
  agent_id: string
  count: number
  failures: FailureEntry[]
}> {
  const res = await fetch(`${API_BASE}/subagents/failures/${agentId}?limit=${limit}`)
  if (!res.ok) throw new Error('Failed to fetch agent failures')
  return res.json()
}

export async function retrySubagentTask(taskId: string): Promise<{
  status: string
  original_task_id: string
  new_task: Record<string, unknown>
}> {
  const res = await fetch(`${API_BASE}/subagents/tasks/${taskId}/retry`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to retry task')
  return res.json()
}

export async function spawnFallbackTask(taskId: string, fallbackAgentId: string = 'reviewer'): Promise<{
  status: string
  original_task_id: string
  fallback_task: Record<string, unknown>
}> {
  const res = await fetch(`${API_BASE}/subagents/tasks/${taskId}/fallback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fallback_agent_id: fallbackAgentId }),
  })
  if (!res.ok) throw new Error('Failed to spawn fallback task')
  return res.json()
}

export async function diagnoseFailedTask(taskId: string): Promise<{
  status: string
  original_task_id: string
  diagnostic_task: Record<string, unknown>
}> {
  const res = await fetch(`${API_BASE}/subagents/tasks/${taskId}/diagnose`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to start diagnosis')
  return res.json()
}

// Security Audit Stats
export interface SecurityStats {
  total_operations: number
  failed_operations: number
  denied_operations: number
  total_violations: number
  operations_by_type: Record<string, number>
  violations_by_type: Record<string, number>
}

// Skills
export interface Skill {
  id: string
  name: string
  description: string
  version: string
  triggers: string[]
  tags: string[]
  workflow_steps: number
}

export interface SkillDetail extends Skill {
  system_context: string
  quality_checklist: string[]
  test_requirements: string[]
  workflow: Array<{
    name: string
    action: string
    description: string
  }>
}

export async function fetchSkills(): Promise<Skill[]> {
  const res = await fetch(`${API_BASE}/skills`)
  if (!res.ok) throw new Error('Failed to fetch skills')
  return res.json()
}

export async function fetchSkill(id: string): Promise<SkillDetail> {
  const res = await fetch(`${API_BASE}/skills/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error('Failed to fetch skill')
  return res.json()
}

export interface SkillMatch extends Skill {
  match_score: number
  matched_triggers: string[]
}

export interface SkillMatchResult {
  prompt: string
  matches: SkillMatch[]
  best_match: SkillMatch | null
}

export async function matchSkills(prompt: string): Promise<SkillMatchResult> {
  const res = await fetch(`${API_BASE}/skills/match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt }),
  })
  if (!res.ok) throw new Error('Failed to match skills')
  return res.json()
}

export interface SkillValidationResult {
  path: string
  skill_id: string | null
  valid: boolean
  errors: Array<{ field: string; message: string }>
  warnings: Array<{ field: string; message: string }>
}

export async function validateSkills(): Promise<{
  skills_dir: string
  total: number
  valid: number
  invalid: number
  results: SkillValidationResult[]
}> {
  const res = await fetch(`${API_BASE}/skills/validate`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to validate skills')
  return res.json()
}

// Subagent task management
export async function cancelSubagentTask(taskId: string): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/subagents/tasks/${taskId}/cancel`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to cancel task')
  return res.json()
}

export interface SubagentTaskDetail {
  id: string
  name: string
  description: string
  agent_id: string
  status: string
  progress: number
  logs: string[]
  goals: Array<{
    id: number
    description: string
    status: string
  }>
  checkpoints: Array<{
    name: string
    description: string
  }>
  error?: string
  attempt: number
  max_attempts: number
}

export async function fetchSubagentTask(taskId: string): Promise<SubagentTaskDetail> {
  const res = await fetch(`${API_BASE}/subagents/tasks/${taskId}`)
  if (!res.ok) throw new Error('Failed to fetch task')
  return res.json()
}

// GitLab Integration
export interface GitLabNamespace {
  id: number
  name: string
  path: string
  web_url: string
}

export interface GitLabProject {
  id: number
  name: string
  path: string
  path_with_namespace: string
  ssh_url_to_repo: string
  http_url_to_repo: string
  web_url: string
}

export async function testGitLabConnection(): Promise<{
  status: string
  user: string
  name: string
  gitlab_url: string
}> {
  const res = await fetch(`${API_BASE}/config/gitlab/test`, {
    method: 'POST',
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Connection failed' }))
    throw new Error(error.detail || 'Failed to connect to GitLab')
  }
  return res.json()
}

export async function fetchGitLabNamespaces(): Promise<GitLabNamespace[]> {
  const res = await fetch(`${API_BASE}/config/gitlab/namespaces`)
  if (!res.ok) throw new Error('Failed to fetch namespaces')
  return res.json()
}

export async function createGitLabProject(data: {
  name: string
  description?: string
  namespace?: string
  visibility?: 'private' | 'internal' | 'public'
  initialize_with_readme?: boolean
}): Promise<GitLabProject> {
  const res = await fetch(`${API_BASE}/config/gitlab/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to create project' }))
    throw new Error(error.detail || 'Failed to create GitLab project')
  }
  return res.json()
}

// Agent Metrics
export interface AgentMetrics {
  total_tasks: number
  successful_tasks: number
  failed_tasks: number
  success_rate: number
  avg_duration_seconds: number
  total_goals: number
  completed_goals: number
  goal_completion_rate: number
}

export interface TaskSizingRecommendation {
  agent_id: string
  sample_size: number
  recommended_max_goals: number
  recommended_timeout_seconds: number
  confidence: string
  avg_goals_per_task: number
  avg_duration_seconds: number
  success_rate: number
}

export interface TaskMetric {
  task_id: string
  agent_id: string
  description: string
  status: string
  duration_seconds: number | null
  goals_total: number
  goals_completed: number
  goal_completion_rate: number
  started_at: string
  completed_at: string | null
}

export interface AllMetrics {
  agents: Record<string, AgentMetrics>
  recent_tasks: TaskMetric[]
  failure_patterns: Record<string, number>
}

export async function fetchAllAgentMetrics(): Promise<AllMetrics> {
  const res = await fetch(`${API_BASE}/subagents/metrics`)
  if (!res.ok) throw new Error('Failed to fetch metrics')
  return res.json()
}

export async function fetchAgentMetrics(agentId: string): Promise<{
  metrics: AgentMetrics
  sizing_recommendation: TaskSizingRecommendation
  failure_patterns: Record<string, number>
}> {
  const res = await fetch(`${API_BASE}/subagents/metrics/${agentId}`)
  if (!res.ok) throw new Error('Failed to fetch agent metrics')
  return res.json()
}

// Rate Limiting
export interface RateLimitStatus {
  max_total_concurrent: number
  max_per_agent: number
  current_running: number
  per_agent_running: Record<string, number>
  queue_size: number
  available_slots: number
}

export async function fetchRateLimitStatus(): Promise<RateLimitStatus> {
  const res = await fetch(`${API_BASE}/subagents/rate-limit`)
  if (!res.ok) throw new Error('Failed to fetch rate limit status')
  return res.json()
}

export async function updateRateLimits(config: {
  max_total_concurrent?: number
  max_per_agent?: number
}): Promise<RateLimitStatus> {
  const res = await fetch(`${API_BASE}/subagents/rate-limit`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!res.ok) throw new Error('Failed to update rate limits')
  return res.json()
}

// Workspace Management
export interface WorkspaceStats {
  workspace_path: string
  total_size_mb: number
  total_size_bytes: number
  file_count: number
  dir_count: number
  oldest_file_age_days: number
  newest_file_age_days: number
}

export interface CleanupResult {
  files_deleted: number
  mb_freed: number
  bytes_freed: number
  errors: string[]
}

export interface FullCleanupResult {
  temp_files?: CleanupResult
  old_files?: CleanupResult
  empty_dirs?: CleanupResult
  kiro_temp_files?: { files_deleted: number }
  summary: {
    total_items_deleted: number
    total_mb_freed: number
    total_errors: number
  }
}

export interface LargeFile {
  path: string
  size_mb: number
  size_bytes: number
}

export async function fetchWorkspaceStats(): Promise<WorkspaceStats> {
  const res = await fetch(`${API_BASE}/workspace/stats`)
  if (!res.ok) throw new Error('Failed to fetch workspace stats')
  return res.json()
}

export async function cleanupWorkspace(options: {
  max_age_days?: number
  cleanup_temp?: boolean
  cleanup_old?: boolean
  cleanup_empty?: boolean
  cleanup_kiro_temp?: boolean
}): Promise<FullCleanupResult> {
  const res = await fetch(`${API_BASE}/workspace/cleanup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(options),
  })
  if (!res.ok) throw new Error('Failed to cleanup workspace')
  return res.json()
}

export async function fetchLargeFiles(minSizeMb: number = 10): Promise<LargeFile[]> {
  const res = await fetch(`${API_BASE}/workspace/large-files?min_size_mb=${minSizeMb}`)
  if (!res.ok) throw new Error('Failed to fetch large files')
  return res.json()
}

export async function archiveProject(projectName: string): Promise<{
  project: string
  archive_path: string
  archive_size_mb: number
}> {
  const res = await fetch(`${API_BASE}/workspace/archive/${encodeURIComponent(projectName)}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('Failed to archive project')
  return res.json()
}

// Cross-Session Communication Types
export interface SessionSummary {
  id: string
  title: string | null
  agent_id: string
  message_count: number
  preview: string | null
  updated_at: string
}

export interface SessionContext {
  session_id: string
  title: string | null
  agent_id: string
  message_count: number
  user_message_count: number
  created_at: string
  updated_at: string
  initial_request: string | null
  latest_request: string | null
  mentioned_files: string[]
}

export interface SessionSearchMatch {
  message_id: string
  role: string
  content: string
  created_at: string
}

export interface SessionSearchResult {
  session_id: string
  title: string | null
  agent_id: string
  matches: SessionSearchMatch[]
}

// Cross-Session API Functions
export async function searchSessions(
  query: string,
  limit: number = 10,
  excludeSession?: string
): Promise<SessionSearchResult[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) })
  if (excludeSession) params.set('exclude_session', excludeSession)

  const res = await fetch(`${API_BASE}/sessions/search?${params}`)
  if (!res.ok) throw new Error('Failed to search sessions')
  return res.json()
}

export async function fetchRecentSessions(
  limit: number = 20,
  agentId?: string,
  excludeSession?: string
): Promise<SessionSummary[]> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (agentId) params.set('agent_id', agentId)
  if (excludeSession) params.set('exclude_session', excludeSession)

  const res = await fetch(`${API_BASE}/sessions/recent?${params}`)
  if (!res.ok) throw new Error('Failed to fetch recent sessions')
  return res.json()
}

export async function fetchSessionContext(sessionId: string): Promise<SessionContext> {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}/context`)
  if (!res.ok) throw new Error('Failed to fetch session context')
  return res.json()
}

// Workspace Browse API
export interface DirectoryEntry {
  name: string
  path: string
  is_dir: boolean
  is_git: boolean
  size?: number
  modified?: number
}

export interface BrowseResult {
  current_path: string
  parent_path: string | null
  entries: DirectoryEntry[]
  is_root: boolean
  is_git?: boolean
}

export interface WorkspaceProject {
  name: string
  path: string
  is_git: boolean
  git_info?: {
    branch?: string
  }
  file_count: number | string
  modified: number
}

export async function browseDirectory(
  path: string = '',
  showFiles: boolean = false
): Promise<BrowseResult> {
  const params = new URLSearchParams()
  if (path) params.set('path', path)
  if (showFiles) params.set('show_files', 'true')

  try {
    const res = await fetch(`${API_BASE}/workspace/browse?${params}`)
    if (!res.ok) {
      const errorBody = await res.text()
      let errorMessage = 'Failed to browse directory'
      try {
        const errorJson = JSON.parse(errorBody)
        errorMessage = errorJson.detail || errorJson.error || errorJson.message || errorMessage
      } catch {
        errorMessage = errorBody || errorMessage
      }
      throw new Error(`${errorMessage} (HTTP ${res.status})`)
    }
    return res.json()
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error('Network error: Unable to connect to server')
    }
    throw error
  }
}

export async function fetchWorkspaceProjects(): Promise<WorkspaceProject[]> {
  const res = await fetch(`${API_BASE}/workspace/projects`)
  if (!res.ok) throw new Error('Failed to fetch workspace projects')
  return res.json()
}

// =============================================================================
// Approvals API - Diff-First Approval Workflow
// =============================================================================

export interface Approval {
  id: string
  action_type: 'write' | 'delete' | 'shell'
  session_id: string
  agent_id: string
  task_id: string | null
  file_path: string | null
  diff: string | null
  content_hash: string | null
  command: string | null
  workdir: string | null
  status: 'pending' | 'approved' | 'denied' | 'expired'
  created_at: string
  expires_at: string | null
  approved_by: string | null
  approval_note: string | null
  is_file_operation: boolean
  is_shell_operation: boolean
  affected_paths: string[]
}

export interface ApprovalListResponse {
  approvals: Approval[]
  total: number
  pending_count: number
}

export interface ApprovalActionResponse {
  success: boolean
  approval_id: string
  new_status: string
  message: string
}

export async function fetchApprovals(options?: {
  status?: string
  session_id?: string
  limit?: number
}): Promise<ApprovalListResponse> {
  const params = new URLSearchParams()
  if (options?.status) params.set('status', options.status)
  if (options?.session_id) params.set('session_id', options.session_id)
  if (options?.limit) params.set('limit', String(options.limit))

  const res = await fetch(`${API_BASE}/approvals?${params}`)
  if (!res.ok) throw new Error('Failed to fetch approvals')
  return res.json()
}

export async function fetchPendingApprovals(sessionId?: string): Promise<ApprovalListResponse> {
  const params = new URLSearchParams()
  if (sessionId) params.set('session_id', sessionId)

  const res = await fetch(`${API_BASE}/approvals/pending?${params}`)
  if (!res.ok) throw new Error('Failed to fetch pending approvals')
  return res.json()
}

export async function fetchApproval(id: string): Promise<Approval> {
  const res = await fetch(`${API_BASE}/approvals/${id}`)
  if (!res.ok) throw new Error('Failed to fetch approval')
  return res.json()
}

export async function approveAction(
  id: string,
  options?: { approved_by?: string; note?: string }
): Promise<ApprovalActionResponse> {
  const res = await fetch(`${API_BASE}/approvals/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      approved_by: options?.approved_by || 'user',
      note: options?.note,
    }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to approve action' }))
    throw new Error(error.detail || 'Failed to approve action')
  }
  return res.json()
}

export async function denyAction(
  id: string,
  options?: { denied_by?: string; reason?: string }
): Promise<ApprovalActionResponse> {
  const res = await fetch(`${API_BASE}/approvals/${id}/deny`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      denied_by: options?.denied_by || 'user',
      reason: options?.reason,
    }),
  })
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Failed to deny action' }))
    throw new Error(error.detail || 'Failed to deny action')
  }
  return res.json()
}

export async function cancelApproval(id: string): Promise<{ success: boolean; message: string }> {
  const res = await fetch(`${API_BASE}/approvals/${id}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error('Failed to cancel approval')
  return res.json()
}

// SSE stream for real-time approval updates
export function subscribeToApprovals(
  sessionId?: string,
  onApprovalRequested?: (approval: Approval) => void,
  onApprovalResolved?: (approval: Approval) => void
): () => void {
  const params = new URLSearchParams()
  if (sessionId) params.set('session_id', sessionId)

  const eventSource = new EventSource(`${API_BASE}/approvals/stream/events?${params}`)

  eventSource.addEventListener('approval_requested', (event) => {
    try {
      const approval = JSON.parse(event.data) as Approval
      onApprovalRequested?.(approval)
    } catch (e) {
      console.error('Failed to parse approval_requested event:', e)
    }
  })

  eventSource.addEventListener('approval_resolved', (event) => {
    try {
      const approval = JSON.parse(event.data) as Approval
      onApprovalResolved?.(approval)
    } catch (e) {
      console.error('Failed to parse approval_resolved event:', e)
    }
  })

  eventSource.onerror = () => {
    // Will auto-reconnect
    console.warn('Approval event stream error, reconnecting...')
  }

  // Return cleanup function
  return () => eventSource.close()
}
