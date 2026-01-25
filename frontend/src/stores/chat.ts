import { create } from 'zustand'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: Date
  agentId?: string
}

interface ChatStore {
  messages: ChatMessage[]
  sessionId: string | null
  agentId: string
  isStreaming: boolean
  
  setSessionId: (id: string | null) => void
  setAgentId: (id: string) => void
  addMessage: (message: Omit<ChatMessage, 'id' | 'timestamp'>) => void
  appendToLastMessage: (content: string) => void
  setLastMessageAgent: (agentId: string) => void
  setStreaming: (streaming: boolean) => void
  clearMessages: () => void
}

export const useChatStore = create<ChatStore>((set) => ({
  messages: [],
  sessionId: null,
  agentId: 'mo',
  isStreaming: false,

  setSessionId: (id) => set({ sessionId: id }),
  setAgentId: (id) => set({ agentId: id }),
  
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
  
  clearMessages: () => set({ messages: [], sessionId: null }),
}))
