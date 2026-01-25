import ReactMarkdown from 'react-markdown'
import { User } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ChatMessage as ChatMessageType } from '@/stores/chat'

interface ChatMessageProps {
  message: ChatMessageType
}

const agentColors: Record<string, string> = {
  mo: 'from-violet-500 to-purple-600',
  architect: 'from-blue-500 to-cyan-600',
  reviewer: 'from-amber-500 to-orange-600',
}

const agentLabels: Record<string, string> = {
  mo: 'MO',
  architect: 'Architect',
  reviewer: 'Reviewer',
}

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === 'user'
  const agentId = message.agentId || 'mo'

  return (
    <div
      className={cn(
        'flex gap-3 py-4 px-4',
        isUser ? 'bg-muted/50' : 'bg-background'
      )}
    >
      <div
        className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
          isUser 
            ? 'bg-primary text-primary-foreground' 
            : `bg-gradient-to-br ${agentColors[agentId] || agentColors.mo} text-white font-bold text-xs`
        )}
      >
        {isUser ? <User className="w-5 h-5" /> : (
          agentId === 'mo' ? 'MO' : agentId === 'architect' ? '🏗️' : '🔍'
        )}
      </div>
      
      <div className="flex-1 overflow-hidden">
        <div className="text-sm font-medium text-muted-foreground mb-1">
          {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          {!isUser && agentId !== 'mo' && (
            <span className="ml-2 text-[10px] opacity-60">(Opus)</span>
          )}
        </div>
        <div className="prose prose-sm dark:prose-invert max-w-none">
          <ReactMarkdown
            components={{
              pre: ({ children }) => (
                <pre className="bg-muted rounded-lg p-4 overflow-x-auto">
                  {children}
                </pre>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className
                return isInline ? (
                  <code className="bg-muted px-1.5 py-0.5 rounded text-sm" {...props}>
                    {children}
                  </code>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                )
              },
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  )
}
