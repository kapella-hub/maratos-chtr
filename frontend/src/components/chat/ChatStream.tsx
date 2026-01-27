import { useRef, useEffect, forwardRef } from 'react'
import { AnimatePresence } from 'framer-motion'
import { Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import MessageBubble from './MessageBubble'
import AgentCard from './AgentCard'
import StatusPill from './StatusPill'
import type { ChatMessage, SubagentTask } from '@/stores/chat'

interface ChatStreamProps {
  messages: ChatMessage[]
  activeSubagents: SubagentTask[]
  isThinking: boolean
  isStreaming: boolean
  isOrchestrating: boolean
  onCancelSubagent?: (taskId: string) => void
  onSendQuickPrompt?: (prompt: string) => void
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
  className,
}, ref) => {
  const bottomRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, activeSubagents])

  const status = isOrchestrating ? 'orchestrating' : isThinking ? 'thinking' : isStreaming ? 'streaming' : 'idle'

  // Empty state
  if (messages.length === 0) {
    return (
      <div ref={ref} className={cn('flex items-center justify-center h-full', className)}>
        <div className="text-center max-w-md px-4 animate-in fade-in-up duration-700">
          {/* Hero */}
          <div className="relative mb-8">
            <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500 via-violet-600 to-purple-600 flex items-center justify-center text-white text-2xl font-bold mx-auto shadow-2xl shadow-indigo-500/40 transition-shadow hover:shadow-indigo-500/60">
              MO
            </div>
            <div className="absolute -bottom-1 -right-1 w-7 h-7 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center shadow-lg animate-pulse">
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
          </div>

          <h2 className="text-2xl font-semibold mb-2 bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
            Hey, I'm MO
          </h2>
          <p className="text-muted-foreground mb-8 leading-relaxed text-sm">
            Your capable AI partner for coding, analysis, and creative tasks
          </p>

          {/* Quick prompts */}
          {onSendQuickPrompt && (
            <div className="grid gap-2">
              {[
                'Help me review my code for security issues',
                'Explain how this codebase is structured',
                'Help me write tests for my functions',
              ].map((prompt, index) => (
                <button
                  key={index}
                  onClick={() => onSendQuickPrompt(prompt)}
                  className={cn(
                    'group text-left px-4 py-3 rounded-xl',
                    'border border-border/50 hover:border-primary/40',
                    'hover:bg-muted/30 transition-all duration-300',
                    'text-sm text-muted-foreground hover:text-foreground',
                    'hover:shadow-lg hover:shadow-primary/5 hover:-translate-y-0.5'
                  )}
                >
                  <span className="group-hover:text-primary transition-colors">{prompt}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div ref={ref} className={cn('chat-stream overflow-y-auto', className)}>
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
              <StatusPill status={status} />
            </div>
          )}
        </AnimatePresence>

        {/* Scroll anchor */}
        <div ref={bottomRef} className="h-8" />
      </div>
    </div>
  )
})

ChatStream.displayName = 'ChatStream'

export default ChatStream
