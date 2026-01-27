import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Sparkles, ChevronDown, Menu, Settings, History, Command, Plus } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { fetchConfig } from '@/lib/api'
import { useChatStore } from '@/stores/chat'

interface MinimalHeaderProps {
  onToggleHistory: () => void
  onToggleCommand: () => void
}

// Format model name for display
function formatModelName(model: string): string {
  if (!model) return 'Claude'
  return model
    .replace(/-\d{8}$/, '')
    .replace('claude-', '')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function MinimalHeader({ onToggleHistory, onToggleCommand }: MinimalHeaderProps) {
  const navigate = useNavigate()
  const [showMenu, setShowMenu] = useState(false)
  const { currentModel, clearMessages, setSessionId } = useChatStore()

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const modelName = formatModelName(currentModel || config?.default_model || 'claude-sonnet-4')

  const handleNewChat = () => {
    clearMessages()
    setSessionId(null)
    navigate('/')
    setShowMenu(false)
  }

  return (
    <header className="h-12 flex items-center justify-between px-4 border-b border-border/30 bg-background/80 backdrop-blur-xl z-50">
      {/* Left: Logo */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2.5 hover:opacity-80 transition-opacity"
        >
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-indigo-600 via-violet-600 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/30">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <span className="font-semibold text-base tracking-tight">MaratOS</span>
        </button>
      </div>

      {/* Center: Model selector */}
      <button
        onClick={onToggleCommand}
        className={cn(
          'flex items-center gap-2 px-3 py-1.5 rounded-lg',
          'text-sm text-muted-foreground',
          'hover:bg-muted/50 hover:text-foreground',
          'transition-colors'
        )}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
        <span className="font-medium">{modelName}</span>
        <ChevronDown className="w-3.5 h-3.5" />
      </button>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        {/* Command palette trigger */}
        <button
          onClick={onToggleCommand}
          className={cn(
            'p-2 rounded-lg text-muted-foreground',
            'hover:bg-muted/50 hover:text-foreground',
            'transition-colors'
          )}
          title="Command palette (Cmd+K)"
        >
          <Command className="w-4 h-4" />
        </button>

        {/* History toggle */}
        <button
          onClick={onToggleHistory}
          className={cn(
            'p-2 rounded-lg text-muted-foreground',
            'hover:bg-muted/50 hover:text-foreground',
            'transition-colors'
          )}
          title="Chat history (Cmd+H)"
        >
          <History className="w-4 h-4" />
        </button>

        {/* Menu */}
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className={cn(
              'p-2 rounded-lg text-muted-foreground',
              'hover:bg-muted/50 hover:text-foreground',
              'transition-colors'
            )}
          >
            <Menu className="w-4 h-4" />
          </button>

          <AnimatePresence>
            {showMenu && (
              <>
                {/* Backdrop */}
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowMenu(false)}
                />

                {/* Menu dropdown */}
                <motion.div
                  initial={{ opacity: 0, scale: 0.95, y: -10 }}
                  animate={{ opacity: 1, scale: 1, y: 0 }}
                  exit={{ opacity: 0, scale: 0.95, y: -10 }}
                  transition={{ duration: 0.15 }}
                  className={cn(
                    'absolute right-0 top-full mt-2 w-48 z-50',
                    'bg-card/95 backdrop-blur-xl border border-border/50 rounded-xl',
                    'shadow-xl shadow-black/20 overflow-hidden'
                  )}
                >
                  <div className="py-1">
                    <button
                      onClick={handleNewChat}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-muted/50 transition-colors"
                    >
                      <Plus className="w-4 h-4 text-muted-foreground" />
                      New Chat
                    </button>
                    <button
                      onClick={() => { navigate('/settings'); setShowMenu(false) }}
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-foreground hover:bg-muted/50 transition-colors"
                    >
                      <Settings className="w-4 h-4 text-muted-foreground" />
                      Settings
                    </button>
                  </div>
                </motion.div>
              </>
            )}
          </AnimatePresence>
        </div>
      </div>
    </header>
  )
}
