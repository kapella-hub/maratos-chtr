import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Search, Pin, Download, Trash2, MessageSquare, Calendar } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { getChatSessions, deleteChatSession, togglePinSession, exportSessionAsMarkdown, type ChatSession } from '@/lib/chatHistory'
import { useChatStore } from '@/stores/chat'

interface HistoryDrawerProps {
  isOpen: boolean
  onClose: () => void
}

function formatRelativeTime(date: Date): string {
  const now = new Date()
  const diff = now.getTime() - date.getTime()
  const minutes = Math.floor(diff / 60000)
  const hours = Math.floor(diff / 3600000)
  const days = Math.floor(diff / 86400000)

  if (minutes < 1) return 'Just now'
  if (minutes < 60) return `${minutes}m ago`
  if (hours < 24) return `${hours}h ago`
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString()
}

function groupSessionsByDate(sessions: ChatSession[]): { title: string; sessions: ChatSession[] }[] {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const yesterday = new Date(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const lastWeek = new Date(today)
  lastWeek.setDate(lastWeek.getDate() - 7)

  const groups: { title: string; sessions: ChatSession[] }[] = [
    { title: 'Pinned', sessions: [] },
    { title: 'Today', sessions: [] },
    { title: 'Yesterday', sessions: [] },
    { title: 'Last 7 Days', sessions: [] },
    { title: 'Older', sessions: [] },
  ]

  sessions.forEach(session => {
    if (session.isPinned) {
      groups[0].sessions.push(session)
    } else {
      const sessionDate = new Date(session.lastUpdated)
      sessionDate.setHours(0, 0, 0, 0)

      if (sessionDate.getTime() === today.getTime()) {
        groups[1].sessions.push(session)
      } else if (sessionDate.getTime() === yesterday.getTime()) {
        groups[2].sessions.push(session)
      } else if (sessionDate >= lastWeek) {
        groups[3].sessions.push(session)
      } else {
        groups[4].sessions.push(session)
      }
    }
  })

  return groups.filter(g => g.sessions.length > 0)
}

export default function HistoryDrawer({ isOpen, onClose }: HistoryDrawerProps) {
  const navigate = useNavigate()
  const [searchQuery, setSearchQuery] = useState('')
  const [sessions, setSessions] = useState<ChatSession[]>(() => getChatSessions())
  const { sessionId: currentSessionId, isStreaming, setSessionId, clearMessages, addMessage } = useChatStore()

  // Refresh sessions when drawer opens or streaming ends
  useEffect(() => {
    if (isOpen) {
      setSessions(getChatSessions())
    }
  }, [isOpen])

  useEffect(() => {
    if (!isStreaming) {
      const timer = setTimeout(() => setSessions(getChatSessions()), 100)
      return () => clearTimeout(timer)
    }
  }, [isStreaming])

  // Listen for custom chatHistoryUpdated events
  useEffect(() => {
    const handleUpdate = () => setSessions(getChatSessions())
    window.addEventListener('chatHistoryUpdated', handleUpdate)
    return () => window.removeEventListener('chatHistoryUpdated', handleUpdate)
  }, [])

  const filteredSessions = useMemo(() => {
    const query = searchQuery.toLowerCase()
    return sessions
      .filter(s =>
        s.title.toLowerCase().includes(query) ||
        s.messages.some(m => m.content.toLowerCase().includes(query))
      )
      .sort((a, b) => {
        if (a.isPinned && !b.isPinned) return -1
        if (!a.isPinned && b.isPinned) return 1
        return new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime()
      })
  }, [sessions, searchQuery])

  const groupedSessions = useMemo(() =>
    groupSessionsByDate(filteredSessions),
    [filteredSessions]
  )

  const handleDelete = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    deleteChatSession(sessionId)
    setSessions(getChatSessions())
  }

  const handlePin = (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    togglePinSession(sessionId)
    setSessions(getChatSessions())
  }

  const handleExport = (session: ChatSession, e: React.MouseEvent) => {
    e.stopPropagation()
    const markdown = exportSessionAsMarkdown(session)
    const blob = new Blob([markdown], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${session.title.replace(/[^a-z0-9]/gi, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleLoadSession = (session: ChatSession) => {
    clearMessages()
    setSessionId(session.id)

    // Load messages into store
    session.messages.forEach(msg => {
      addMessage({
        role: msg.role,
        content: msg.content,
        agentId: msg.agentId,
      })
    })

    navigate('/')
    onClose()
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 bg-black/50 z-40"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            className={cn(
              'fixed left-0 top-0 bottom-0 w-80 z-50',
              'bg-background/95 backdrop-blur-xl',
              'border-r border-border/50',
              'flex flex-col',
              'shadow-2xl shadow-black/30'
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between p-4 border-b border-border/50">
              <h2 className="text-lg font-semibold flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-primary" />
                History
              </h2>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Search */}
            <div className="p-3 border-b border-border/30">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search conversations..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className={cn(
                    'w-full pl-10 pr-3 py-2 text-sm',
                    'bg-muted/50 border border-border/50 rounded-lg',
                    'focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50',
                    'placeholder:text-muted-foreground/60'
                  )}
                  autoFocus
                />
              </div>
            </div>

            {/* Sessions List */}
            <div className="flex-1 overflow-y-auto">
              {groupedSessions.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center p-6">
                  <MessageSquare className="w-12 h-12 text-muted-foreground/30 mb-3" />
                  <p className="text-muted-foreground text-sm">
                    {searchQuery ? 'No matching conversations' : 'No chat history yet'}
                  </p>
                </div>
              ) : (
                <div className="p-2 space-y-4">
                  {groupedSessions.map((group) => (
                    <div key={group.title}>
                      <div className="flex items-center gap-2 px-2 py-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                        {group.title === 'Pinned' ? (
                          <Pin className="w-3 h-3" />
                        ) : (
                          <Calendar className="w-3 h-3" />
                        )}
                        {group.title}
                      </div>
                      <div className="space-y-1">
                        {group.sessions.map((session) => (
                          <motion.div
                            key={session.id}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            className={cn(
                              'group p-3 rounded-lg cursor-pointer transition-all',
                              currentSessionId === session.id
                                ? 'bg-primary/10 border border-primary/30'
                                : 'hover:bg-muted/50 border border-transparent'
                            )}
                            onClick={() => handleLoadSession(session)}
                          >
                            <div className="flex items-start justify-between gap-2 mb-1">
                              <h3 className="text-sm font-medium line-clamp-2 flex-1">
                                {session.title}
                              </h3>
                              <button
                                onClick={(e) => handlePin(session.id, e)}
                                className={cn(
                                  'p-1 rounded transition-colors flex-shrink-0',
                                  session.isPinned
                                    ? 'text-primary'
                                    : 'text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground'
                                )}
                              >
                                <Pin className="w-3.5 h-3.5" />
                              </button>
                            </div>

                            <div className="flex items-center justify-between text-xs text-muted-foreground">
                              <span>{session.messages.length} messages</span>
                              <span>{formatRelativeTime(new Date(session.lastUpdated))}</span>
                            </div>

                            {/* Actions */}
                            <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                              <button
                                onClick={(e) => handleExport(session, e)}
                                className="p-1.5 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                                title="Export as markdown"
                              >
                                <Download className="w-3.5 h-3.5" />
                              </button>
                              <button
                                onClick={(e) => handleDelete(session.id, e)}
                                className="p-1.5 rounded hover:bg-destructive/10 hover:text-destructive transition-colors text-muted-foreground"
                                title="Delete"
                              >
                                <Trash2 className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </motion.div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Footer with keyboard shortcut hint */}
            <div className="p-3 border-t border-border/30 text-center">
              <span className="text-xs text-muted-foreground flex items-center justify-center gap-2">
                <kbd className="kbd">Cmd</kbd>
                <span>+</span>
                <kbd className="kbd">H</kbd>
                <span>to toggle</span>
              </span>
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
