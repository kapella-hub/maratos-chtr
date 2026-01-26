import { useState, useMemo } from 'react'
import { ChevronLeft, ChevronRight, Search, Pin, Download, Trash2, MessageSquare } from 'lucide-react'
import { cn } from '@/lib/utils'
import { getChatSessions, deleteChatSession, togglePinSession, exportSessionAsMarkdown, ChatSession } from '@/lib/chatHistory'
import { useChatStore } from '@/stores/chat'

interface ChatHistoryProps {
  onLoadSession?: (sessionId: string) => void
}

export default function ChatHistory({ onLoadSession }: ChatHistoryProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [sessions, setSessions] = useState<ChatSession[]>(() => getChatSessions())
  const currentSessionId = useChatStore(state => state.sessionId)

  const filteredSessions = useMemo(() => {
    const query = searchQuery.toLowerCase()
    const filtered = sessions.filter(s => 
      s.title.toLowerCase().includes(query) ||
      s.messages.some(m => m.content.toLowerCase().includes(query))
    )
    
    const pinned = filtered.filter(s => s.isPinned)
    const unpinned = filtered.filter(s => !s.isPinned)
    
    return [...pinned, ...unpinned]
  }, [sessions, searchQuery])

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

  const handleLoadSession = (sessionId: string) => {
    onLoadSession?.(sessionId)
    setIsOpen(false)
  }

  return (
    <>
      {/* Toggle Button - positioned inside chat area */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'fixed top-20 z-50 p-2 rounded-r-lg bg-zinc-900/90 border border-l-0 border-border/50 hover:bg-zinc-800 transition-all duration-300',
          isOpen ? 'left-80' : 'left-0'
        )}
        aria-label={isOpen ? 'Close history' : 'Open history'}
      >
        {isOpen ? <ChevronLeft className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
      </button>

      {/* Sidebar */}
      <aside
        className={cn(
          'absolute top-0 left-0 h-full w-80 bg-zinc-950/95 backdrop-blur-xl border-r border-border/50 transition-transform duration-300 z-40',
          isOpen ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex flex-col h-full p-4">
          {/* Header */}
          <div className="mb-4">
            <h2 className="text-lg font-semibold mb-3">Chat History</h2>
            
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
              <input
                type="text"
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-3 py-2 bg-zinc-900/50 border border-border/50 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/50"
              />
            </div>
          </div>

          {/* Sessions List */}
          <div className="flex-1 overflow-y-auto space-y-2">
            {filteredSessions.length === 0 ? (
              <div className="text-center text-muted-foreground text-sm py-8">
                <MessageSquare className="w-8 h-8 mx-auto mb-2 opacity-50" />
                {searchQuery ? 'No matching conversations' : 'No chat history yet'}
              </div>
            ) : (
              filteredSessions.map((session) => (
                <div
                  key={session.id}
                  onClick={() => handleLoadSession(session.id)}
                  className={cn(
                    'group p-3 rounded-lg border cursor-pointer transition-all',
                    currentSessionId === session.id
                      ? 'bg-indigo-600/20 border-indigo-500/50'
                      : 'bg-zinc-900/30 border-border/30 hover:bg-zinc-900/50 hover:border-border/50'
                  )}
                >
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <h3 className="text-sm font-medium line-clamp-2 flex-1">
                      {session.title}
                    </h3>
                    <button
                      onClick={(e) => handlePin(session.id, e)}
                      className={cn(
                        'p-1 rounded transition-colors',
                        session.isPinned
                          ? 'text-indigo-400'
                          : 'text-muted-foreground opacity-0 group-hover:opacity-100 hover:text-foreground'
                      )}
                      aria-label={session.isPinned ? 'Unpin' : 'Pin'}
                    >
                      <Pin className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  
                  <div className="flex items-center justify-between text-xs text-muted-foreground">
                    <span>{session.messages.length} messages</span>
                    <span>{formatRelativeTime(session.lastUpdated)}</span>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handleExport(session, e)}
                      className="p-1.5 rounded hover:bg-zinc-800 transition-colors"
                      aria-label="Export as markdown"
                    >
                      <Download className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={(e) => handleDelete(session.id, e)}
                      className="p-1.5 rounded hover:bg-red-500/20 hover:text-red-400 transition-colors"
                      aria-label="Delete"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      </aside>
    </>
  )
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
