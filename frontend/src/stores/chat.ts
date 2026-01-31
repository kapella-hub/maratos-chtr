import { create } from 'zustand'
import type { ThinkingBlock, ProjectContextInfo } from '@/lib/api'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  agentId?: string
  isSubagentResult?: boolean
  thinkingData?: ThinkingBlock  // Structured thinking data
  statusMessage?: string  // Transient status message for this message generation
}

export interface SubagentGoal {
  id: number
  description: string
  status: 'pending' | 'in_progress' | 'completed' | 'failed'
}

export interface SubagentCheckpoint {
  name: string
  description: string
}

export interface SubagentTask {
  id: string
  agent: string
  status: 'spawning' | 'running' | 'retrying' | 'completed' | 'failed' | 'timed_out' | 'cancelled'
  progress: number
  error?: string
  goals?: {
    total: number
    completed: number
    current_id: number | null
    items: SubagentGoal[]
  }
  checkpoints?: SubagentCheckpoint[]
  logs?: string[]
  currentAction?: string
  // Retry tracking
  attempt?: number
  maxAttempts?: number
  isFallback?: boolean
  originalTaskId?: string
}

export interface QueuedMessage {
  id: string
  content: string
  timestamp: Date
}

// Inline project types
export interface ProjectTask {
  id: string
  title: string
  description: string
  agent_type: string
  status: 'pending' | 'blocked' | 'ready' | 'in_progress' | 'testing' | 'reviewing' | 'fixing' | 'completed' | 'failed' | 'skipped'
  depends_on: string[]
  quality_gates: { type: string; passed: boolean; error?: string }[]
  progress?: number
  current_attempt?: number
  max_attempts?: number
  error?: string
}

export interface ProjectPlan {
  id: string
  name: string
  original_prompt: string
  workspace_path: string
  status: string
  tasks: ProjectTask[]
  progress: number
  tasks_completed: number
  tasks_failed: number
  tasks_pending: number
  branch_name?: string
  pr_url?: string
}

export interface InlineProject {
  id: string | null
  status: 'none' | 'detecting' | 'planning' | 'awaiting_approval' | 'executing' | 'paused' | 'interrupted' | 'completed' | 'failed' | 'cancelled'
  plan: ProjectPlan | null
  currentTaskId: string | null
  events: ProjectEvent[]
  error: string | null
}

export interface ProjectEvent {
  type: string
  data: Record<string, unknown>
  timestamp: string
}

interface ChatStore {
  messages: ChatMessage[]
  messageQueue: QueuedMessage[]
  sessionId: string | null
  agentId: string
  currentModel: string | null  // Model being used for current chat
  isStreaming: boolean
  isThinking: boolean
  isModelThinking: boolean
  statusMessage: string | null // Current transient status message (e.g., "Running tests...")
  isOrchestrating: boolean
  activeSubagents: SubagentTask[]
  abortController: AbortController | null
  currentThinkingBlock: Partial<ThinkingBlock> | null  // Current thinking block being processed

  // Active project context (auto-detected or explicitly set)
  activeProjectContext: ProjectContextInfo | null

  // User-selected project from dropdown (not auto-detected)
  selectedProjectName: string | null

  // Inline project state
  inlineProject: InlineProject

  setSessionId: (id: string | null) => void
  setAgentId: (id: string) => void
  setCurrentModel: (model: string | null) => void
  setActiveProjectContext: (context: ProjectContextInfo | null) => void
  setSelectedProjectName: (name: string | null) => void
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void
  appendToLastMessage: (content: string) => void
  setLastMessageAgent: (agentId: string) => void
  setLastMessageThinking: (thinkingData: ThinkingBlock) => void
  setStreaming: (streaming: boolean) => void
  setThinking: (thinking: boolean) => void
  setModelThinking: (thinking: boolean) => void
  setStatusMessage: (message: string | null) => void
  setCurrentThinkingBlock: (block: Partial<ThinkingBlock> | null) => void
  setOrchestrating: (orchestrating: boolean) => void
  updateSubagent: (task: SubagentTask) => void
  clearSubagents: () => void
  setAbortController: (controller: AbortController | null) => void
  stopGeneration: () => void
  clearMessages: () => void

  // Queue management
  enqueueMessage: (content: string) => void
  dequeueMessage: () => QueuedMessage | undefined
  clearQueue: () => void

  // Inline project actions
  setProjectStatus: (status: InlineProject['status']) => void
  setProjectPlan: (plan: ProjectPlan) => void
  updateProjectTask: (taskId: string, updates: Partial<ProjectTask>) => void
  addProjectEvent: (event: ProjectEvent) => void
  setProjectError: (error: string | null) => void
  clearProject: () => void
}

const initialProject: InlineProject = {
  id: null,
  status: 'none',
  plan: null,
  currentTaskId: null,
  events: [],
  error: null,
}

export const useChatStore = create<ChatStore>((set, get) => ({
  messages: [],
  messageQueue: [],
  sessionId: null,
  agentId: 'mo',
  currentModel: null,
  isStreaming: false,
  isThinking: false,
  isModelThinking: false,
  statusMessage: null,
  isOrchestrating: false,
  activeSubagents: [],
  abortController: null,
  currentThinkingBlock: null,
  activeProjectContext: null,
  selectedProjectName: null,
  inlineProject: { ...initialProject },

  setSessionId: (id) => set({ sessionId: id }),
  setAgentId: (id) => set({ agentId: id }),
  setCurrentModel: (model) => set({ currentModel: model }),
  setActiveProjectContext: (context) => set({ activeProjectContext: context }),
  setSelectedProjectName: (name) => set({ selectedProjectName: name }),
  setAbortController: (controller) => set({ abortController: controller }),

  stopGeneration: () => {
    const { abortController } = get()
    if (abortController) {
      abortController.abort()
      set({ isStreaming: false, isThinking: false, abortController: null })
    }
  },

  // Queue management
  enqueueMessage: (content) => set((state) => ({
    messageQueue: [...state.messageQueue, {
      id: crypto.randomUUID(),
      content,
      timestamp: new Date(),
    }],
  })),

  dequeueMessage: () => {
    const { messageQueue } = get()
    if (messageQueue.length === 0) return undefined
    const [first, ...rest] = messageQueue
    set({ messageQueue: rest })
    return first
  },

  clearQueue: () => set({ messageQueue: [] }),

  addMessage: (message) => set((state) => ({
    messages: [...state.messages, {
      ...message,
      id: crypto.randomUUID(),
      timestamp: new Date(),
    }],
  })),

  appendToLastMessage: (content) => set((state) => {
    const messages = [...state.messages]
    if (messages.length > 0) {
      messages[messages.length - 1] = {
        ...messages[messages.length - 1],
        content: messages[messages.length - 1].content + content,
      }
    }
    return { messages }
  }),

  setLastMessageAgent: (agentId) => set((state) => {
    const messages = [...state.messages]
    if (messages.length > 0) {
      messages[messages.length - 1] = {
        ...messages[messages.length - 1],
        agentId,
      }
    }
    return { messages }
  }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setThinking: (thinking) => set({ isThinking: thinking }),
  setModelThinking: (thinking) => set({ isModelThinking: thinking }),
  setStatusMessage: (message) => set({ statusMessage: message }),
  setCurrentThinkingBlock: (block) => set({ currentThinkingBlock: block }),
  setOrchestrating: (orchestrating) => set({ isOrchestrating: orchestrating }),

  setLastMessageThinking: (thinkingData) => set((state) => {
    const messages = [...state.messages]
    if (messages.length > 0) {
      messages[messages.length - 1] = {
        ...messages[messages.length - 1],
        thinkingData,
      }
    }
    return { messages, currentThinkingBlock: null }
  }),

  updateSubagent: (task) => set((state) => {
    // First try to match by id, then by agent name (for when id changes between spawning/running)
    let existing = state.activeSubagents.findIndex(t => t.id === task.id)
    if (existing < 0) {
      existing = state.activeSubagents.findIndex(t => t.agent === task.agent)
    }
    if (existing >= 0) {
      const updated = [...state.activeSubagents]
      // Merge existing task with updates
      updated[existing] = { ...updated[existing], ...task }
      return { activeSubagents: updated }
    }
    return { activeSubagents: [...state.activeSubagents, task] }
  }),

  clearSubagents: () => set({ activeSubagents: [], isOrchestrating: false }),

  clearMessages: () => set({
    messages: [],
    messageQueue: [],
    sessionId: null,
    currentModel: null,
    isThinking: false,
    isModelThinking: false,
    statusMessage: null,
    isOrchestrating: false,
    activeSubagents: [],
    activeProjectContext: null,
    selectedProjectName: null,
    inlineProject: { ...initialProject },
  }),

  // Inline project actions
  setProjectStatus: (status) => set((state) => ({
    inlineProject: { ...state.inlineProject, status },
  })),

  setProjectPlan: (plan) => set((state) => ({
    inlineProject: {
      ...state.inlineProject,
      id: plan.id,
      plan,
      status: 'awaiting_approval',
    },
  })),

  updateProjectTask: (taskId, updates) => set((state) => {
    if (!state.inlineProject.plan) return state
    const tasks = state.inlineProject.plan.tasks.map(task =>
      task.id === taskId ? { ...task, ...updates } : task
    )
    return {
      inlineProject: {
        ...state.inlineProject,
        currentTaskId: updates.status === 'in_progress' ? taskId : state.inlineProject.currentTaskId,
        plan: { ...state.inlineProject.plan, tasks },
      },
    }
  }),

  addProjectEvent: (event) => set((state) => ({
    inlineProject: {
      ...state.inlineProject,
      events: [...state.inlineProject.events.slice(-99), event],  // Keep last 100
    },
  })),

  setProjectError: (error) => set((state) => ({
    inlineProject: { ...state.inlineProject, error, status: error ? 'failed' : state.inlineProject.status },
  })),

  clearProject: () => set({ inlineProject: { ...initialProject } }),
}))
