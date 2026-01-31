import { useRef, useEffect, forwardRef, useState, useCallback } from 'react'
import { AnimatePresence } from 'framer-motion'
import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import MessageBubble from './MessageBubble'
import AgentCard from './AgentCard'
import StatusPill from './StatusPill'
import ScrollToBottom from './ScrollToBottom'
import type { ChatMessage, SubagentTask } from '@/stores/chat'

interface ChatStreamProps {
  messages: ChatMessage[]
  activeSubagents: SubagentTask[]
  isThinking: boolean
  isStreaming: boolean
  isOrchestrating: boolean
  onCancelSubagent?: (taskId: string) => void
  onSendQuickPrompt?: (prompt: string) => void
  statusMessage?: string | null
  className?: string
}

const ChatStream = forwardRef<HTMLDivElement, ChatStreamProps>(({
  messages,
  activeSubagents,
  isThinking,
  isStreaming,
  isOrchestrating,
  onCancelSubagent,
  onSendQuickPrompt,
  statusMessage,
  className,
}, ref) => {
  const bottomRef = useRef<HTMLDivElement>(null)
  const internalRef = useRef<HTMLDivElement>(null)
  const [showScrollButton, setShowScrollButton] = useState(false)

  // Check scroll position
  const handleScroll = useCallback(() => {
    const container = internalRef.current
    if (!container) return
    const { scrollTop, scrollHeight, clientHeight } = container
    const isNearBottom = scrollHeight - scrollTop - clientHeight < 100
    setShowScrollButton(!isNearBottom && messages.length > 0)
  }, [messages.length])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeSubagents])

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const status = isOrchestrating ? 'orchestrating' : isThinking ? 'thinking' : isStreaming ? 'streaming' : 'idle'

  // Empty state
  if (messages.length === 0) {
    return (
      <div ref={ref} className={cn('flex items-center justify-center h-full', className)}>
        <div className="text-center max-w-lg px-6">
          {/* Animated Hero */}
          <div className="relative mb-10 inline-block">
            {/* Glow ring */}
            <div className="absolute inset-0 w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500/30 via-violet-500/30 to-purple-500/30 blur-xl animate-pulse" />
            <div className="relative w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500 via-violet-600 to-purple-600 flex items-center justify-center text-white text-3xl font-bold shadow-2xl shadow-violet-500/40 transform hover:scale-105 transition-transform duration-300">
              MO
            </div>
            <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-teal-500 flex items-center justify-center shadow-lg ring-4 ring-background">
              <Sparkles className="w-4 h-4 text-white animate-spin-slow" style={{ animationDuration: '3s' }} />
            </div>
          </div>

          <h2 className="text-3xl font-bold mb-3 bg-gradient-to-r from-foreground via-foreground/90 to-foreground/70 bg-clip-text text-transparent">
            What can I help you build?
          </h2>
          <p className="text-muted-foreground mb-10 leading-relaxed">
            I'm your AI dev partner — ready to code, debug, review, and ship with you.
          </p>

          {/* Quick prompts - 2 column grid */}
          {onSendQuickPrompt && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {[
                { icon: '🔍', text: 'Review my code for issues' },
                { icon: '🏗️', text: 'Explain this codebase' },
                { icon: '🧪', text: 'Write tests for my code' },
                { icon: '🚀', text: 'Help me deploy this app' },
              ].map((item, index) => (
                <button
                  key={index}
                  onClick={() => onSendQuickPrompt(item.text)}
                  className={cn(
                    'group flex items-center gap-3 px-4 py-3.5 rounded-2xl text-left',
                    'bg-muted/30 border border-border/40',
                    'hover:bg-muted/60 hover:border-primary/30',
                    'hover:shadow-lg hover:shadow-primary/5',
                    'transform hover:-translate-y-0.5',
                    'transition-all duration-200'
                  )}
                >
                  <span className="text-lg">{item.icon}</span>
                  <span className="text-sm text-muted-foreground group-hover:text-foreground transition-colors">
                    {item.text}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* Keyboard hint */}
          <p className="mt-8 text-xs text-muted-foreground/60">
            Press <kbd className="px-1.5 py-0.5 rounded bg-muted text-muted-foreground font-mono text-[10px]">⌘K</kbd> for commands
          </p>
        </div>
      </div>
    )
  }

  return (
    <div
      ref={(node) => {
        (internalRef as React.MutableRefObject<HTMLDivElement | null>).current = node
        if (typeof ref === 'function') ref(node)
        else if (ref) (ref as React.MutableRefObject<HTMLDivElement | null>).current = node
      }}
      className={cn('chat-stream overflow-y-auto relative', className)}
      onScroll={handleScroll}
    >
      <div className="max-w-3xl mx-auto py-4">
        {/* Messages */}
        {messages.map((message, index) => (
          <MessageBubble
            key={message.id}
            message={message}
            isThinking={isThinking && index === messages.length - 1 && message.role === 'assistant' && !message.content}
          />
        ))}

        {/* Inline agent cards */}
        <AnimatePresence>
          {activeSubagents.length > 0 && (
            <div className="px-4 space-y-2">
              {activeSubagents.map(task => (
                <AgentCard
                  key={task.id}
                  task={task}
                  onCancel={onCancelSubagent}
                />
              ))}
            </div>
          )}
        </AnimatePresence>

        {/* Status pill when active */}
        <AnimatePresence>
          {status !== 'idle' && messages.length > 0 && messages[messages.length - 1]?.content && (
            <div className="px-4 py-2">
              <StatusPill status={status} message={statusMessage} />
            </div>
          )}
        </AnimatePresence>

        {/* Scroll anchor */}
        <div ref={bottomRef} className="h-8" />
      </div>

      {/* Scroll to bottom button */}
      <ScrollToBottom
        visible={showScrollButton}
        onClick={scrollToBottom}
        className="bottom-4 left-1/2 -translate-x-1/2"
      />
    </div>
  )
})

ChatStream.displayName = 'ChatStream'

export default ChatStream
