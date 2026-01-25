import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User } from 'lucide-react'
import { cn } from '@/lib/utils'
import ThinkingIndicator from '@/components/ThinkingIndicator'
import type { ChatMessage as ChatMessageType } from '@/stores/chat'

interface ChatMessageProps {
  message: ChatMessageType
  isThinking?: boolean
}

// Strip ANSI escape codes from terminal output
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '')
}

const agentColors: Record<string, string> = {
  mo: 'from-violet-500 to-purple-600',
  architect: 'from-blue-500 to-cyan-600',
  reviewer: 'from-amber-500 to-orange-600',
  coder: 'from-emerald-500 to-green-600',
  tester: 'from-pink-500 to-rose-600',
  docs: 'from-cyan-500 to-sky-600',
  devops: 'from-orange-500 to-red-600',
  'kiro-sonnet': 'from-emerald-500 to-teal-600',
  'kiro-opus': 'from-rose-500 to-pink-600',
}

const agentLabels: Record<string, string> = {
  mo: 'MO',
  architect: 'Architect',
  reviewer: 'Reviewer',
  coder: 'Coder',
  tester: 'Tester',
  docs: 'Docs',
  devops: 'DevOps',
  'kiro-sonnet': 'Kiro',
  'kiro-opus': 'Kiro',
}

const agentIcons: Record<string, string> = {
  mo: 'MO',
  architect: '🏗️',
  reviewer: '🔍',
  coder: '💻',
  tester: '🧪',
  docs: '📝',
  devops: '🚀',
  'kiro-sonnet': '🦜',
  'kiro-opus': '🦜',
}

export default function ChatMessage({ message, isThinking }: ChatMessageProps) {
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
        {isUser ? <User className="w-5 h-5" /> : (agentIcons[agentId] || 'MO')}
      </div>
      
      <div className="flex-1 overflow-hidden">
        <div className="text-sm font-medium text-muted-foreground mb-1">
          {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          {!isUser && agentId !== 'mo' && (
            <span className="ml-2 text-[10px] opacity-60">(Opus)</span>
          )}
        </div>
        {isThinking ? (
          <ThinkingIndicator />
        ) : (
        <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-li:text-foreground">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              h1: ({ children }) => <h1 className="text-xl font-bold mt-4 mb-2">{children}</h1>,
              h2: ({ children }) => <h2 className="text-lg font-semibold mt-4 mb-2">{children}</h2>,
              h3: ({ children }) => <h3 className="text-base font-semibold mt-3 mb-1">{children}</h3>,
              ul: ({ children }) => <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>,
              ol: ({ children }) => <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>,
              li: ({ children }) => <li className="ml-2">{children}</li>,
              p: ({ children }) => <p className="my-2">{children}</p>,
              pre: ({ children }) => (
                <pre className="bg-muted rounded-lg p-4 overflow-x-auto my-3 text-sm">
                  {children}
                </pre>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className
                return isInline ? (
                  <code className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                    {children}
                  </code>
                ) : (
                  <code className={cn(className, 'font-mono')} {...props}>
                    {children}
                  </code>
                )
              },
              table: ({ children }) => (
                <div className="overflow-x-auto my-3">
                  <table className="min-w-full border-collapse border border-border">
                    {children}
                  </table>
                </div>
              ),
              th: ({ children }) => (
                <th className="border border-border px-3 py-2 bg-muted text-left font-semibold">
                  {children}
                </th>
              ),
              td: ({ children }) => (
                <td className="border border-border px-3 py-2">{children}</td>
              ),
            }}
          >
            {stripAnsi(message.content)}
          </ReactMarkdown>
        </div>
        )}
      </div>
    </div>
  )
}
