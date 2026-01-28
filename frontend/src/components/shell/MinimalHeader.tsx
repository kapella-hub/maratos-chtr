import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Sparkles, ChevronDown, Menu, Settings, History, Command, Plus, Cpu, Brain, Check, ShieldCheck } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { fetchConfig, updateConfig } from '@/lib/api'
import { useChatStore } from '@/stores/chat'
import { useApprovalsStore } from '@/stores/approvals'

interface MinimalHeaderProps {
  onToggleHistory: () => void
  onToggleCommand: () => void
}

// Kiro CLI available models
const kiroModels = [
  { id: 'Auto', name: 'Auto', credits: '1x' },
  { id: 'claude-sonnet-4.5', name: 'Sonnet 4.5', credits: '1.3x' },
  { id: 'claude-sonnet-4', name: 'Sonnet 4', credits: '1.3x' },
  { id: 'claude-haiku-4.5', name: 'Haiku 4.5', credits: '0.4x' },
  { id: 'claude-opus-4.5', name: 'Opus 4.5', credits: '2.2x' },
]

// Thinking levels
const thinkingLevels = [
  { id: 'off', name: 'Off', color: 'text-gray-400' },
  { id: 'minimal', name: 'Minimal', color: 'text-blue-400' },
  { id: 'low', name: 'Low', color: 'text-cyan-400' },
  { id: 'medium', name: 'Medium', color: 'text-green-400' },
  { id: 'high', name: 'High', color: 'text-yellow-400' },
  { id: 'max', name: 'Max', color: 'text-orange-400' },
]

export default function MinimalHeader({ onToggleHistory, onToggleCommand }: MinimalHeaderProps) {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [showMenu, setShowMenu] = useState(false)
  const [showModelDropdown, setShowModelDropdown] = useState(false)
  const [showThinkingDropdown, setShowThinkingDropdown] = useState(false)
  const modelRef = useRef<HTMLDivElement>(null)
  const thinkingRef = useRef<HTMLDivElement>(null)
  const { clearMessages, setSessionId, isStreaming } = useChatStore()
  const { pendingCount, togglePanel: toggleApprovalsPanel } = useApprovalsStore()

  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const configMutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: (data) => {
      // Directly update the cache with the response
      queryClient.setQueryData(['config'], data)
    },
    onError: (error) => {
      console.error('Config update failed:', error)
    },
  })

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (modelRef.current && !modelRef.current.contains(e.target as Node)) {
        setShowModelDropdown(false)
      }
      if (thinkingRef.current && !thinkingRef.current.contains(e.target as Node)) {
        setShowThinkingDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const selectedModel = config?.default_model || 'Auto'
  const selectedThinking = config?.thinking_level || 'medium'
  const currentModelInfo = kiroModels.find(m => m.id === selectedModel) || kiroModels[0]
  const currentThinkingInfo = thinkingLevels.find(t => t.id === selectedThinking) || thinkingLevels[3]

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

      {/* Center: Model & Thinking selectors */}
      <div className="flex items-center gap-2">
        {/* Model Selector */}
        <div className="relative" ref={modelRef}>
          <button
            onClick={() => {
              if (!isStreaming) {
                setShowModelDropdown(!showModelDropdown)
                setShowThinkingDropdown(false)
              }
            }}
            disabled={isStreaming}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm',
              'hover:bg-muted/50 transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
            <span className="font-medium">{currentModelInfo.name}</span>
            <span className="text-xs text-emerald-400">{currentModelInfo.credits}</span>
            <ChevronDown className={cn(
              'w-3 h-3 text-muted-foreground transition-transform',
              showModelDropdown && 'rotate-180'
            )} />
          </button>

          <AnimatePresence>
            {showModelDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className="absolute top-full left-0 mt-2 w-48 bg-card border border-border rounded-xl shadow-xl z-[100] overflow-hidden"
                style={{ pointerEvents: 'auto' }}
              >
                <div className="p-1">
                  {kiroModels.map((model) => (
                    <button
                      key={model.id}
                      onClick={() => {
                        console.log('Selecting model:', model.id)
                        configMutation.mutate({ default_model: model.id })
                        setShowModelDropdown(false)
                      }}
                      className={cn(
                        'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm',
                        'hover:bg-muted/50 transition-colors',
                        model.id === selectedModel && 'bg-primary/10'
                      )}
                    >
                      <span className="flex-1 font-medium">{model.name}</span>
                      <span className="text-xs text-emerald-400">{model.credits}</span>
                      {model.id === selectedModel && (
                        <Check className="w-3.5 h-3.5 text-primary" />
                      )}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        <span className="text-border">|</span>

        {/* Thinking Level Selector */}
        <div className="relative" ref={thinkingRef}>
          <button
            onClick={() => {
              if (!isStreaming) {
                setShowThinkingDropdown(!showThinkingDropdown)
                setShowModelDropdown(false)
              }
            }}
            disabled={isStreaming}
            className={cn(
              'flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm',
              'hover:bg-muted/50 transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          >
            <Brain className="w-3.5 h-3.5 text-violet-400" />
            <span className={cn('font-medium', currentThinkingInfo.color)}>{currentThinkingInfo.name}</span>
            <ChevronDown className={cn(
              'w-3 h-3 text-muted-foreground transition-transform',
              showThinkingDropdown && 'rotate-180'
            )} />
          </button>

          <AnimatePresence>
            {showThinkingDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -8, scale: 0.95 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.95 }}
                transition={{ duration: 0.15 }}
                className="absolute top-full left-0 mt-2 w-40 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden"
              >
                <div className="p-1">
                  {thinkingLevels.map((level) => (
                    <button
                      key={level.id}
                      onClick={() => {
                        configMutation.mutate({ thinking_level: level.id })
                        setShowThinkingDropdown(false)
                      }}
                      className={cn(
                        'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-left text-sm',
                        'hover:bg-muted/50 transition-colors',
                        level.id === selectedThinking && 'bg-violet-500/10'
                      )}
                    >
                      <span className={cn('flex-1 font-medium', level.color)}>{level.name}</span>
                      {level.id === selectedThinking && (
                        <Check className="w-3.5 h-3.5 text-violet-400" />
                      )}
                    </button>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-1">
        {/* Approvals toggle */}
        <button
          onClick={toggleApprovalsPanel}
          className={cn(
            'relative p-2 rounded-lg',
            pendingCount > 0 ? 'text-amber-400 hover:bg-amber-500/10' : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
            'transition-colors'
          )}
          title="Approvals (Cmd+Shift+A)"
        >
          <ShieldCheck className="w-4 h-4" />
          {pendingCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-4 h-4 bg-amber-500 text-[10px] font-bold text-white rounded-full flex items-center justify-center">
              {pendingCount > 9 ? '9+' : pendingCount}
            </span>
          )}
        </button>

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
