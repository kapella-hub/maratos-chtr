import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Copy, Check } from 'lucide-react'
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

// Strip <thinking> and <analysis> blocks from content
function stripHiddenBlocks(text: string): { content: string; hadThinking: boolean } {
  const thinkingRegex = /<thinking>[\s\S]*?<\/thinking>\s*/gi
  const analysisRegex = /<analysis>[\s\S]*?<\/analysis>\s*/gi
  const hadThinking = thinkingRegex.test(text) || analysisRegex.test(text)
  let content = text.replace(/<thinking>[\s\S]*?<\/thinking>\s*/gi, '')
  content = content.replace(/<analysis>[\s\S]*?<\/analysis>\s*/gi, '').trim()
  return { content, hadThinking }
}

// Convert numbered line formats (• 1: code) to proper markdown code blocks
function convertNumberedLinesToCodeBlocks(text: string): string {
  // Find consecutive numbered lines and wrap them in code blocks
  const lines = text.split('\n')
  const result: string[] = []
  let inCodeBlock = false
  let codeLines: string[] = []
  let prevWasNumbered = false
  
  for (const line of lines) {
    const match = line.match(/^[•\-\*]\s*(\d+):\s*(.*)$/)
    
    if (match) {
      if (!inCodeBlock) {
        inCodeBlock = true
        codeLines = []
      }
      // Extract just the code part (after "• N: ")
      codeLines.push(match[2])
      prevWasNumbered = true
    } else {
      if (inCodeBlock && prevWasNumbered) {
        // End of code block - wrap it
        result.push('```')
        result.push(...codeLines)
        result.push('```')
        inCodeBlock = false
        codeLines = []
      }
      result.push(line)
      prevWasNumbered = false
    }
  }
  
  // Handle trailing code block
  if (inCodeBlock && codeLines.length > 0) {
    result.push('```')
    result.push(...codeLines)
    result.push('```')
  }
  
  return result.join('\n')
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

// Copy button component
function CopyButton({ text, className }: { text: string; className?: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <button
      onClick={handleCopy}
      className={cn(
        'p-1.5 rounded-md transition-colors',
        'hover:bg-muted-foreground/20',
        'text-muted-foreground hover:text-foreground',
        className
      )}
      title={copied ? 'Copied!' : 'Copy'}
    >
      {copied ? (
        <Check className="w-4 h-4 text-green-500" />
      ) : (
        <Copy className="w-4 h-4" />
      )}
    </button>
  )
}

// Code block with copy button, syntax highlighting, and line numbers
function CodeBlock({ children, className }: { children: string; className?: string }) {
  const language = className?.replace('language-', '') || ''
  const lines = children.split('\n')
  // Remove trailing empty line if present
  if (lines[lines.length - 1] === '') lines.pop()
  
  return (
    <div className="relative group my-3">
      <div className="absolute right-2 top-2 opacity-0 group-hover:opacity-100 transition-opacity z-10">
        <CopyButton text={children} />
      </div>
      {language && (
        <div className="absolute left-3 top-2 text-xs text-muted-foreground/60 font-mono">
          {language}
        </div>
      )}
      <pre className={cn(
        'bg-zinc-900 dark:bg-zinc-950 rounded-lg overflow-x-auto text-sm',
        'border border-border',
        language ? 'pt-8 pb-3' : 'py-3'
      )}>
        <code className={cn('font-mono text-zinc-100 block', className)}>
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-white/5">
              <span className="select-none text-zinc-600 text-right pr-4 pl-3 min-w-[3rem] border-r border-zinc-800">
                {i + 1}
              </span>
              <span className="pl-4 pr-4 flex-1">{line || ' '}</span>
            </div>
          ))}
        </code>
      </pre>
    </div>
  )
}

export default function ChatMessage({ message, isThinking }: ChatMessageProps) {
  const [showCopy, setShowCopy] = useState(false)
  const isUser = message.role === 'user'
  const agentId = message.agentId || 'mo'

  return (
    <div
      className={cn(
        'flex gap-3 py-4 px-4 group relative',
        isUser ? 'bg-muted/50' : 'bg-background'
      )}
      onMouseEnter={() => setShowCopy(true)}
      onMouseLeave={() => setShowCopy(false)}
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
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-medium text-muted-foreground">
            {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          </span>
          {!isUser && agentId !== 'mo' && (
            <span className="text-[10px] text-muted-foreground/60 bg-muted px-1.5 py-0.5 rounded">
              {agentId}
            </span>
          )}
          {/* Copy entire message button */}
          {!isUser && message.content && showCopy && (
            <CopyButton text={message.content} className="ml-auto" />
          )}
        </div>
        
        {isThinking ? (
          <ThinkingIndicator />
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-li:text-foreground">
            {(() => {
              const { content: rawContent, hadThinking } = stripHiddenBlocks(message.content)
              const content = convertNumberedLinesToCodeBlocks(rawContent)
              return (
                <>
                  {hadThinking && (
                    <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2 pb-2 border-b border-border">
                      <span className="w-2 h-2 rounded-full bg-violet-500" />
                      <span>Thought through the problem</span>
                    </div>
                  )}
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    components={{
                h1: ({ children }) => (
                  <h1 className="text-xl font-bold mt-6 mb-3 pb-2 border-b border-border">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="text-lg font-semibold mt-5 mb-2 text-foreground">{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 className="text-base font-semibold mt-4 mb-1 text-foreground">{children}</h3>
                ),
                ul: ({ children }) => (
                  <ul className="list-disc list-outside ml-4 my-2 space-y-1">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="list-decimal list-outside ml-4 my-2 space-y-1">{children}</ol>
                ),
                li: ({ children }) => <li className="pl-1">{children}</li>,
                p: ({ children }) => <p className="my-2 leading-relaxed">{children}</p>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-violet-500 pl-4 my-3 italic text-muted-foreground">
                    {children}
                  </blockquote>
                ),
                pre: ({ children }) => {
                  // Extract code content from children
                  const codeElement = children as React.ReactElement
                  const codeProps = codeElement?.props || {}
                  const codeContent = codeProps.children || ''
                  const className = codeProps.className || ''
                  
                  return <CodeBlock className={className}>{String(codeContent)}</CodeBlock>
                },
                code: ({ className, children, ...props }) => {
                  const isInline = !className
                  if (isInline) {
                    return (
                      <code 
                        className="bg-muted px-1.5 py-0.5 rounded text-sm font-mono text-pink-500 dark:text-pink-400" 
                        {...props}
                      >
                        {children}
                      </code>
                    )
                  }
                  // Block code is handled by pre
                  return <code className={cn(className, 'font-mono')} {...props}>{children}</code>
                },
                table: ({ children }) => (
                  <div className="overflow-x-auto my-4 rounded-lg border border-border">
                    <table className="min-w-full">
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="bg-muted/50">{children}</thead>
                ),
                th: ({ children }) => (
                  <th className="px-4 py-2 text-left font-semibold border-b border-border">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-4 py-2 border-b border-border">{children}</td>
                ),
                hr: () => <hr className="my-6 border-border" />,
                a: ({ href, children }) => (
                  <a 
                    href={href} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="text-violet-500 hover:text-violet-400 underline"
                  >
                    {children}
                  </a>
                ),
                // Analysis/thinking blocks get special styling
                strong: ({ children }) => {
                  const text = String(children)
                  // Highlight severity markers
                  if (text.includes('🔴') || text.includes('CRITICAL')) {
                    return <strong className="text-red-500">{children}</strong>
                  }
                  if (text.includes('🟠') || text.includes('HIGH')) {
                    return <strong className="text-orange-500">{children}</strong>
                  }
                  if (text.includes('🟡') || text.includes('MEDIUM')) {
                    return <strong className="text-yellow-500">{children}</strong>
                  }
                  if (text.includes('🟢') || text.includes('LOW')) {
                    return <strong className="text-green-500">{children}</strong>
                  }
                  return <strong className="font-semibold">{children}</strong>
                },
              }}
                  >
                    {stripAnsi(content)}
                  </ReactMarkdown>
                </>
              )
            })()}
          </div>
        )}
      </div>
    </div>
  )
}
