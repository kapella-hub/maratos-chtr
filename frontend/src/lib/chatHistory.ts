import { ChatMessage } from '@/stores/chat'

export interface ChatSession {
  id: string
  title: string
  messages: ChatMessage[]
  timestamp: Date
  lastUpdated: Date
  isPinned?: boolean
}

const STORAGE_KEY = 'maratos_chat_history'
const MAX_SESSIONS = 100

export function saveChatSession(sessionId: string, messages: ChatMessage[], title?: string): void {
  if (!sessionId || messages.length === 0) {
    console.log('[chatHistory] saveChatSession skipped:', { sessionId, messageCount: messages.length })
    return // Nothing to save
  }
  console.log('[chatHistory] saveChatSession:', { sessionId, messageCount: messages.length })

  const sessions = getChatSessions()
  const existing = sessions.find(s => s.id === sessionId)

  const session: ChatSession = {
    id: sessionId,
    title: title || generateTitle(messages),
    messages,
    timestamp: existing?.timestamp || new Date(),
    lastUpdated: new Date(),
    isPinned: existing?.isPinned || false,
  }

  const filtered = sessions.filter(s => s.id !== sessionId)
  const updated = [session, ...filtered].slice(0, MAX_SESSIONS)

  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    // Dispatch custom event for same-tab listeners
    window.dispatchEvent(new CustomEvent('chatHistoryUpdated'))
  } catch (error) {
    // localStorage quota exceeded - try removing older sessions
    console.warn('Failed to save chat session, trying to free space:', error)
    try {
      const reducedSessions = updated.slice(0, Math.floor(MAX_SESSIONS / 2))
      localStorage.setItem(STORAGE_KEY, JSON.stringify(reducedSessions))
    } catch (innerError) {
      console.error('Failed to save chat session even after cleanup:', innerError)
    }
  }
}

export function getChatSessions(): ChatSession[] {
  const data = localStorage.getItem(STORAGE_KEY)
  if (!data) return []
  
  try {
    const sessions = JSON.parse(data)
    return sessions.map((s: any) => ({
      ...s,
      timestamp: new Date(s.timestamp),
      lastUpdated: new Date(s.lastUpdated),
      messages: (s.messages || []).map((m: any) => ({
        ...m,
        timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
      })),
    }))
  } catch (error) {
    console.error('Failed to parse chat history:', error)
    return []
  }
}

export function getChatSession(sessionId: string): ChatSession | null {
  const sessions = getChatSessions()
  return sessions.find(s => s.id === sessionId) || null
}

export function deleteChatSession(sessionId: string): void {
  const sessions = getChatSessions().filter(s => s.id !== sessionId)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
}

export function togglePinSession(sessionId: string): void {
  const sessions = getChatSessions()
  const session = sessions.find(s => s.id === sessionId)
  if (session) {
    session.isPinned = !session.isPinned
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions))
  }
}

export function exportSessionAsMarkdown(session: ChatSession): string {
  const lines = [
    `# ${session.title}`,
    ``,
    `**Created:** ${session.timestamp.toLocaleString()}`,
    `**Last Updated:** ${session.lastUpdated.toLocaleString()}`,
    ``,
    `---`,
    ``,
  ]
  
  session.messages.forEach(msg => {
    lines.push(`## ${msg.role === 'user' ? 'User' : 'Assistant'}`)
    lines.push(`*${msg.timestamp.toLocaleString()}*`)
    lines.push(``)
    lines.push(msg.content)
    lines.push(``)
  })
  
  return lines.join('\n')
}

function generateTitle(messages: ChatMessage[]): string {
  const firstUserMsg = messages.find(m => m.role === 'user')
  if (!firstUserMsg) return 'New Chat'

  let text = firstUserMsg.content

  // Remove code blocks, URLs, and file paths
  text = text.replace(/```[\s\S]*?```/g, '')
  text = text.replace(/`[^`]+`/g, '')
  text = text.replace(/https?:\/\/[^\s]+/g, '')
  text = text.replace(/\/[\w\-./]+/g, ' ')

  // Remove common conversational prefixes
  const prefixes = [
    /^(hey|hi|hello|yo),?\s*/i,
    /^(can you|could you|would you|please|help me|i need|i want|i'd like to|let's|lets)\s*/i,
    /^(show me|tell me|explain|create|make|build|write|fix|add|update|implement|generate)\s*/i,
  ]
  for (const prefix of prefixes) {
    text = text.replace(prefix, '')
  }

  // Clean up whitespace
  text = text.replace(/\s+/g, ' ').trim()

  // Get first meaningful segment (before newline or long pause)
  const firstLine = text.split(/[.\n\r]/)[0]?.trim() || text

  // Truncate to ~35 chars at word boundary
  const maxLen = 35
  if (firstLine.length <= maxLen) {
    return capitalize(firstLine) || 'New Chat'
  }

  // Find last space before maxLen
  const truncated = firstLine.slice(0, maxLen)
  const lastSpace = truncated.lastIndexOf(' ')
  const title = lastSpace > 15 ? truncated.slice(0, lastSpace) : truncated

  return capitalize(title) + '...'
}

function capitalize(str: string): string {
  if (!str) return str
  return str.charAt(0).toUpperCase() + str.slice(1)
}
