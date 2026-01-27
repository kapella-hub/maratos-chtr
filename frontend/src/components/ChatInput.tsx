import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Square, ListPlus, Sparkles } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import SkillSelector from './SkillSelector'
import type { Skill } from '@/lib/api'

// Session commands
export type SessionCommand = 'reset' | 'status' | 'help'

interface ChatInputProps {
  onSend: (message: string, skill?: Skill | null) => void
  onQueue?: (message: string) => void
  onStop?: () => void
  onCommand?: (command: SessionCommand) => void
  isLoading?: boolean
  hasQueue?: boolean
  placeholder?: string
  showSkills?: boolean
}

export default function ChatInput({
  onSend,
  onQueue,
  onStop,
  onCommand,
  isLoading,
  placeholder = 'Ask MO anything...',
  showSkills = true
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
    }
  }, [input])

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSubmit = () => {
    if (!input.trim()) return

    const trimmed = input.trim()

    // Check for commands
    if (trimmed.startsWith('/') && onCommand) {
      const cmd = trimmed.slice(1).toLowerCase().split(' ')[0]
      if (cmd === 'reset' || cmd === 'status' || cmd === 'help') {
        onCommand(cmd as SessionCommand)
        setInput('')
        return
      }
    }

    if (isLoading && onQueue) {
      onQueue(trimmed)
      setInput('')
    } else if (!isLoading) {
      onSend(trimmed, selectedSkill)
      setInput('')
      setSelectedSkill(null) // Clear skill after sending
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    // Cmd/Ctrl + Enter to send
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
      return
    }
    // Enter without shift to send
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
    // Escape to stop
    if (e.key === 'Escape' && isLoading && onStop) {
      onStop()
    }
  }

  const charCount = input.length
  const showCharCount = charCount > 100
  const isOverLimit = charCount > 2000
  const isCommand = input.trim().startsWith('/')

  return (
    <div className="bg-transparent">
      <div className="pb-4 px-4">
        <div className="max-w-3xl mx-auto">
          {/* Input Container */}
          <motion.div
            className={cn(
              'relative rounded-2xl transition-all duration-300',
              'bg-card border shadow-lg',
              isFocused
                ? 'border-primary/50 shadow-primary/10 ring-4 ring-primary/5'
                : 'border-border/50 shadow-black/5',
              isLoading && 'border-amber-500/30'
            )}
          >
            {/* Decorative gradient line at top when focused */}
            <AnimatePresence>
              {isFocused && (
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  exit={{ scaleX: 0 }}
                  className="absolute top-0 left-4 right-4 h-0.5 bg-gradient-to-r from-violet-500 via-purple-500 to-pink-500 rounded-full"
                />
              )}
            </AnimatePresence>

            {/* Skill Selector */}
            {showSkills && input.length > 0 && !isCommand && (
              <div className="absolute -top-10 left-3">
                <SkillSelector
                  prompt={input}
                  selectedSkill={selectedSkill}
                  onSelect={setSelectedSkill}
                />
              </div>
            )}

            {/* Command hints */}
            <AnimatePresence>
              {isCommand && input.trim() === '/' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute -top-32 left-3 bg-card border border-border rounded-xl p-3 shadow-xl z-10"
                >
                  <div className="text-xs text-muted-foreground mb-2">Commands:</div>
                  <div className="space-y-1">
                    <button
                      onClick={() => setInput('/reset')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/reset</span>
                      <span className="ml-2 text-muted-foreground">Clear session</span>
                    </button>
                    <button
                      onClick={() => setInput('/status')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/status</span>
                      <span className="ml-2 text-muted-foreground">Show session info</span>
                    </button>
                    <button
                      onClick={() => setInput('/help')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/help</span>
                      <span className="ml-2 text-muted-foreground">Show available commands</span>
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Textarea */}
            <div className="flex items-end gap-2 p-3">
              {/* Icon */}
              <div className={cn(
                'flex-shrink-0 p-2 rounded-xl transition-colors duration-200',
                isFocused ? 'text-primary' : 'text-muted-foreground'
              )}>
                <Sparkles className="w-5 h-5" />
              </div>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                placeholder={isLoading ? 'Type to queue next message...' : placeholder}
                rows={1}
                className={cn(
                  'flex-1 resize-none bg-transparent py-2 px-1',
                  'focus:outline-none',
                  'placeholder:text-muted-foreground/50',
                  'text-foreground',
                  'min-h-[40px] max-h-[200px]'
                )}
              />

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Stop button */}
                <AnimatePresence>
                  {isLoading && (
                    <motion.button
                      initial={{ scale: 0, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0, opacity: 0 }}
                      onClick={onStop}
                      className={cn(
                        'p-2.5 rounded-xl bg-red-500 text-white',
                        'hover:bg-red-600 active:scale-95',
                        'transition-all duration-200',
                        'shadow-lg shadow-red-500/25'
                      )}
                      title="Stop generation (Esc)"
                    >
                      <Square className="w-4 h-4 fill-current" />
                    </motion.button>
                  )}
                </AnimatePresence>

                {/* Send/Queue button */}
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSubmit}
                  disabled={!input.trim()}
                  className={cn(
                    'p-2.5 rounded-xl transition-all duration-200',
                    'disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none',
                    'flex items-center gap-2',
                    isLoading
                      ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-lg shadow-amber-500/25'
                      : 'bg-gradient-to-r from-violet-600 to-purple-600 text-white hover:from-violet-500 hover:to-purple-500 shadow-lg shadow-violet-500/25'
                  )}
                  title={isLoading ? 'Add to queue (Enter)' : 'Send message (Enter)'}
                >
                  {isLoading ? (
                    <ListPlus className="w-5 h-5" />
                  ) : (
                    <Send className="w-5 h-5" />
                  )}
                </motion.button>
              </div>
            </div>

            {/* Character count */}
            <AnimatePresence>
              {showCharCount && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className={cn(
                    "absolute right-4 -top-6 text-xs font-medium",
                    isOverLimit ? "text-red-400" : "text-muted-foreground"
                  )}
                >
                  {charCount.toLocaleString()} {isOverLimit && "⚠️"}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* Footer hints */}
          <div className="flex items-center justify-center gap-4 mt-3">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
              <kbd className="kbd">⌘</kbd>
              <span>+</span>
              <kbd className="kbd">Enter</kbd>
              <span>send</span>
            </span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
              <kbd className="kbd">Shift</kbd>
              <span>+</span>
              <kbd className="kbd">Enter</kbd>
              <span>new line</span>
            </span>
            {isLoading && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
                <kbd className="kbd">Esc</kbd>
                <span>stop</span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
