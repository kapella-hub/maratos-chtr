import { create } from 'zustand'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  agentId?: string
  isSubagentResult?: boolean
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

interface ChatStore {
  messages: ChatMessage[]
  messageQueue: QueuedMessage[]
  sessionId: string | null
  agentId: string
  currentModel: string | null  // Model being used for current chat
  isStreaming: boolean
  isThinking: boolean
  isModelThinking: boolean
  isOrchestrating: boolean
  activeSubagents: SubagentTask[]
  abortController: AbortController | null

  setSessionId: (id: string | null) => void
  setAgentId: (id: string) => void
  setCurrentModel: (model: string | null) => void
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void
  appendToLastMessage: (content: string) => void
  setLastMessageAgent: (agentId: string) => void
  setStreaming: (streaming: boolean) => void
  setThinking: (thinking: boolean) => void
  setModelThinking: (thinking: boolean) => void
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
  isOrchestrating: false,
  activeSubagents: [],
  abortController: null,

  setSessionId: (id) => set({ sessionId: id }),
  setAgentId: (id) => set({ agentId: id }),
  setCurrentModel: (model) => set({ currentModel: model }),
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
  setOrchestrating: (orchestrating) => set({ isOrchestrating: orchestrating }),
  
  updateSubagent: (task) => set((state) => {
    // First try to match by id, then by agent name (for when id changes between spawning/running)
    let existing = state.activeSubagents.findIndex(t => t.id === task.id)
    if (existing < 0) {
      existing = state.activeSubagents.findIndex(t => t.agent === task.agent)
    }
    if (existing >= 0) {
      const updated = [...state.activeSubagents]
      updated[existing] = task
      return { activeSubagents: updated }
    }
    return { activeSubagents: [...state.activeSubagents, task] }
  }),
  
  clearSubagents: () => set({ activeSubagents: [], isOrchestrating: false }),
  
  clearMessages: () => set({ messages: [], messageQueue: [], sessionId: null, currentModel: null, isThinking: false, isModelThinking: false, isOrchestrating: false, activeSubagents: [] }),
}))
