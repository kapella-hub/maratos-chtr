import { useState, useEffect, useRef, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  Command,
  Search,
  MessageSquare,
  Settings,
  History,
  Plus,
  Zap,
  Brain,
  Sparkles,
  ArrowRight,
  X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { fetchConfig } from '@/lib/api'
import { useChatStore } from '@/stores/chat'
import { getChatSessions } from '@/lib/chatHistory'

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
  onOpenHistory: () => void
}

interface CommandItem {
  id: string
  icon: React.ReactNode
  label: string
  description?: string
  shortcut?: string[]
  action: () => void
  category: 'navigation' | 'actions' | 'history' | 'models'
}

const modelOptions = [
  { id: 'claude-sonnet-4-20250514', name: 'Sonnet 4', description: 'Fast and capable', icon: <Zap className="w-4 h-4" /> },
  { id: 'claude-opus-4-20250514', name: 'Opus 4', description: 'Most intelligent', icon: <Brain className="w-4 h-4" /> },
  { id: 'claude-3-5-haiku-20241022', name: 'Haiku 3.5', description: 'Fastest', icon: <Sparkles className="w-4 h-4" /> },
]

export default function CommandPalette({ isOpen, onClose, onOpenHistory }: CommandPaletteProps) {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)
  const { clearMessages, setSessionId, addMessage } = useChatStore()

  useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const recentSessions = useMemo(() => getChatSessions().slice(0, 5), [])

  // Build command list
  const commands = useMemo<CommandItem[]>(() => {
    const items: CommandItem[] = [
      // Navigation
      {
        id: 'new-chat',
        icon: <Plus className="w-4 h-4" />,
        label: 'New Chat',
        description: 'Start a fresh conversation',
        shortcut: ['Cmd', 'N'],
        action: () => {
          clearMessages()
          setSessionId(null)
          navigate('/')
          onClose()
        },
        category: 'navigation',
      },
      {
        id: 'history',
        icon: <History className="w-4 h-4" />,
        label: 'Chat History',
        description: 'Browse previous conversations',
        shortcut: ['Cmd', 'H'],
        action: () => {
          onClose()
          onOpenHistory()
        },
        category: 'navigation',
      },
      {
        id: 'settings',
        icon: <Settings className="w-4 h-4" />,
        label: 'Settings',
        description: 'Configure MaratOS',
        shortcut: ['Cmd', ','],
        action: () => {
          navigate('/settings')
          onClose()
        },
        category: 'navigation',
      },

      // Actions
      {
        id: 'help',
        icon: <Command className="w-4 h-4" />,
        label: 'Show Help',
        description: 'Display available commands',
        action: () => {
          addMessage({
            role: 'assistant',
            content: `## Available Commands\n\n| Command | Description |\n|---------|-------------|\n| \`/reset\` | Clear the current session |\n| \`/help\` | Show this help message |\n\n**Keyboard Shortcuts:**\n- **Cmd+K** - Command palette\n- **Cmd+H** - Toggle history\n- **Cmd+N** - New chat\n- **Enter** - Send message\n- **Esc** - Stop generation`,
            agentId: 'mo'
          })
          onClose()
        },
        category: 'actions',
      },

      // Models
      ...modelOptions.map((model) => ({
        id: `model-${model.id}`,
        icon: model.icon,
        label: `Switch to ${model.name}`,
        description: model.description,
        action: () => {
          // Model switching would need backend support
          onClose()
        },
        category: 'models' as const,
      })),

      // Recent sessions
      ...recentSessions.map((session) => ({
        id: `session-${session.id}`,
        icon: <MessageSquare className="w-4 h-4" />,
        label: session.title,
        description: `${session.messages.length} messages`,
        action: () => {
          clearMessages()
          setSessionId(session.id)
          session.messages.forEach(msg => {
            addMessage({ role: msg.role, content: msg.content, agentId: msg.agentId })
          })
          navigate('/')
          onClose()
        },
        category: 'history' as const,
      })),
    ]

    return items
  }, [recentSessions, clearMessages, setSessionId, addMessage, navigate, onClose, onOpenHistory])

  // Filter commands based on query
  const filteredCommands = useMemo(() => {
    if (!query) return commands
    const lowerQuery = query.toLowerCase()
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(lowerQuery) ||
        cmd.description?.toLowerCase().includes(lowerQuery)
    )
  }, [commands, query])

  // Group commands by category
  const groupedCommands = useMemo(() => {
    const groups: Record<string, CommandItem[]> = {
      navigation: [],
      actions: [],
      models: [],
      history: [],
    }
    filteredCommands.forEach((cmd) => {
      groups[cmd.category].push(cmd)
    })
    return groups
  }, [filteredCommands])

  // Reset selection when query changes
  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      inputRef.current?.focus()
      setQuery('')
    }
  }, [isOpen])

  // Keyboard navigation
  useEffect(() => {
    if (!isOpen) return

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setSelectedIndex((i) => Math.min(i + 1, filteredCommands.length - 1))
      } else if (e.key === 'ArrowUp') {
        e.preventDefault()
        setSelectedIndex((i) => Math.max(i - 1, 0))
      } else if (e.key === 'Enter') {
        e.preventDefault()
        filteredCommands[selectedIndex]?.action()
      } else if (e.key === 'Escape') {
        onClose()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, filteredCommands, selectedIndex, onClose])

  const categoryLabels: Record<string, string> = {
    navigation: 'Navigation',
    actions: 'Actions',
    models: 'Models',
    history: 'Recent Chats',
  }

  let flatIndex = 0

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh]">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Palette */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.15 }}
            className={cn(
              'relative w-full max-w-xl mx-4',
              'bg-card/95 backdrop-blur-xl border border-border/50 rounded-2xl',
              'shadow-2xl shadow-black/30',
              'overflow-hidden'
            )}
          >
            {/* Search input */}
            <div className="flex items-center gap-3 px-4 py-4 border-b border-border/30">
              <Search className="w-5 h-5 text-muted-foreground" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search commands, chats, or type to navigate..."
                className={cn(
                  'flex-1 bg-transparent text-foreground text-lg',
                  'focus:outline-none',
                  'placeholder:text-muted-foreground/50'
                )}
              />
              <button
                onClick={onClose}
                className="p-1 text-muted-foreground hover:text-foreground transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Commands list */}
            <div className="max-h-[50vh] overflow-y-auto">
              {filteredCommands.length === 0 ? (
                <div className="py-12 text-center text-muted-foreground">
                  <Command className="w-8 h-8 mx-auto mb-2 opacity-50" />
                  <p>No commands found</p>
                </div>
              ) : (
                <div className="p-2">
                  {Object.entries(groupedCommands).map(([category, items]) => {
                    if (items.length === 0) return null

                    return (
                      <div key={category} className="mb-2">
                        <div className="px-3 py-2 text-xs font-medium text-muted-foreground uppercase tracking-wider">
                          {categoryLabels[category]}
                        </div>
                        {items.map((cmd) => {
                          const index = flatIndex++
                          const isSelected = index === selectedIndex

                          return (
                            <button
                              key={cmd.id}
                              onClick={cmd.action}
                              onMouseEnter={() => setSelectedIndex(index)}
                              className={cn(
                                'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left',
                                'transition-colors',
                                isSelected
                                  ? 'bg-primary/10 text-foreground'
                                  : 'text-muted-foreground hover:bg-muted/50'
                              )}
                            >
                              <span className={cn(
                                'p-1.5 rounded-lg',
                                isSelected ? 'bg-primary/20 text-primary' : 'bg-muted'
                              )}>
                                {cmd.icon}
                              </span>
                              <div className="flex-1 min-w-0">
                                <div className={cn(
                                  'font-medium text-sm',
                                  isSelected && 'text-foreground'
                                )}>
                                  {cmd.label}
                                </div>
                                {cmd.description && (
                                  <div className="text-xs text-muted-foreground truncate">
                                    {cmd.description}
                                  </div>
                                )}
                              </div>
                              {cmd.shortcut && (
                                <div className="flex items-center gap-1">
                                  {cmd.shortcut.map((key, i) => (
                                    <kbd
                                      key={i}
                                      className="kbd text-[10px]"
                                    >
                                      {key}
                                    </kbd>
                                  ))}
                                </div>
                              )}
                              {isSelected && (
                                <ArrowRight className="w-4 h-4 text-primary" />
                              )}
                            </button>
                          )
                        })}
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="px-4 py-2 border-t border-border/30 flex items-center justify-between text-xs text-muted-foreground bg-muted/20">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <kbd className="kbd">↑↓</kbd>
                  navigate
                </span>
                <span className="flex items-center gap-1">
                  <kbd className="kbd">↵</kbd>
                  select
                </span>
              </div>
              <span className="flex items-center gap-1">
                <kbd className="kbd">Esc</kbd>
                close
              </span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
