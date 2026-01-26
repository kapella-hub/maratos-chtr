import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate } from 'react-router-dom'
import { MessageSquare, History, Settings, Sparkles, Bot, Plus, Pin, ChevronDown, ChevronRight } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { fetchConfig } from '@/lib/api'
import { getChatSessions, togglePinSession, type ChatSession } from '@/lib/chatHistory'
import { useChatStore } from '@/stores/chat'

const navItems = [
  { to: '/autonomous', icon: Bot, label: 'Autonomous' },
  { to: '/sessions', icon: History, label: 'All History' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

// Format model name for display
function formatModelName(model: string): string {
  if (!model) return 'Claude'
  // Remove version suffixes and clean up
  return model
    .replace(/-\d{8}$/, '') // Remove date suffix
    .replace('claude-', '')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function Layout() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [historyExpanded, setHistoryExpanded] = useState(true)
  const { sessionId, clearMessages, setSessionId } = useChatStore()

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  // Load sessions
  useEffect(() => {
    setSessions(getChatSessions())
  }, [sessionId]) // Refresh when session changes

  const handleNewChat = () => {
    clearMessages()
    setSessionId(null)
    navigate('/')
  }

  const handleLoadSession = (id: string) => {
    // The ChatPage will handle loading via the store
    setSessionId(id)
    navigate('/')
  }

  const handlePin = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    togglePinSession(id)
    setSessions(getChatSessions())
  }

  const modelName = formatModelName(config?.default_model || 'claude-sonnet-4')

  // Get recent sessions (pinned first, then by date)
  const recentSessions = sessions
    .sort((a, b) => {
      if (a.isPinned && !b.isPinned) return -1
      if (!a.isPinned && b.isPinned) return 1
      return new Date(b.lastUpdated).getTime() - new Date(a.lastUpdated).getTime()
    })
    .slice(0, 10)

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-72 border-r border-border/50 flex flex-col bg-zinc-950/50 backdrop-blur-xl">
        {/* Logo */}
        <div className="p-4 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30 transition-shadow hover:shadow-indigo-500/50">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">MaratOS</h1>
              <p className="text-xs text-muted-foreground">
                Powered by {modelName}
              </p>
            </div>
          </div>
        </div>

        {/* New Chat Button */}
        <div className="p-3 border-b border-border/50">
          <button
            onClick={handleNewChat}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-medium text-sm shadow-lg shadow-indigo-500/30 hover:shadow-indigo-500/50 transition-all"
          >
            <Plus className="w-4 h-4" />
            New Chat
          </button>
        </div>

        {/* Chat History */}
        <div className="flex-1 flex flex-col min-h-0">
          <button
            onClick={() => setHistoryExpanded(!historyExpanded)}
            className="flex items-center gap-2 px-4 py-2 text-xs font-medium text-muted-foreground hover:text-foreground transition-colors"
          >
            {historyExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
            <MessageSquare className="w-3 h-3" />
            Recent Chats
          </button>

          {historyExpanded && (
            <div className="flex-1 overflow-y-auto px-2 pb-2 space-y-1">
              {recentSessions.length === 0 ? (
                <div className="text-center text-muted-foreground text-xs py-4">
                  No chat history yet
                </div>
              ) : (
                recentSessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleLoadSession(session.id)}
                    className={cn(
                      'w-full group flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all text-sm',
                      sessionId === session.id
                        ? 'bg-indigo-600/20 text-foreground'
                        : 'text-muted-foreground hover:bg-zinc-900/50 hover:text-foreground'
                    )}
                  >
                    {session.isPinned && (
                      <Pin className="w-3 h-3 text-indigo-400 flex-shrink-0" />
                    )}
                    <span className="flex-1 truncate">{session.title}</span>
                    <button
                      onClick={(e) => handlePin(session.id, e)}
                      className={cn(
                        'p-1 rounded opacity-0 group-hover:opacity-100 transition-opacity',
                        session.isPinned ? 'text-indigo-400' : 'hover:text-foreground'
                      )}
                    >
                      <Pin className="w-3 h-3" />
                    </button>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {/* Navigation */}
        <nav className="p-2 border-t border-border/50">
          <div className="space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-200 text-sm',
                    isActive
                      ? 'bg-zinc-900/80 text-foreground'
                      : 'text-muted-foreground hover:bg-zinc-900/50 hover:text-foreground'
                  )
                }
              >
                <item.icon className="w-4 h-4" />
                <span className="font-medium">{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        {/* Status */}
        <div className="p-3 border-t border-border/50">
          <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500/10 via-violet-500/10 to-purple-500/10 border border-indigo-500/20">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-500 via-violet-600 to-purple-600 flex items-center justify-center text-white text-xs font-bold shadow-lg shadow-indigo-500/30">
              MO
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">MO</div>
              <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Online
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
