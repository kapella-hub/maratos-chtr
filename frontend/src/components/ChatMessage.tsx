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

// Filter out verbose tool execution log lines
function filterToolLogs(text: string): string {
  const toolLogPatterns = [
    /^[✓✔☑✗✘❌]\s*(?:Successfully|Failed).*$/gm,
    /^(?:Successfully|Failed)\s+(?:read|wrote|deleted|copied).*$/gm,
    /^Reading (?:directory|file):.*$/gm,
    /^Searching.*\.\.\..*$/gm,
    /^Found \d+ (?:files?|matches?).*$/gm,
    /^↱ Operation \d+:.*$/gm,
    /^[•\-\s]*Completed in \d+\.?\d*s?.*$/gm,  // Various formats: "• Completed in", " - Completed in", "Completed in"
    /^\[Overview\].*bytes.*tokens.*$/gm,
    /^⋮.*$/gm,  // Ellipsis lines
    /^\s*Summary:.*$/gm,
    /^Purpose:.*$/gm,
    /^Updating:.*$/gm,
    /^Creating:.*$/gm,
    /^Deleting:.*$/gm,
    /^\d+ operations? processed.*$/gm,
    /^Now let me analyze.*$/gm,  // Kiro transition phrases
    /^Let me start by reading.*$/gm,
  ]

  let result = text
  for (const pattern of toolLogPatterns) {
    result = result.replace(pattern, '')
  }
  // Clean up multiple blank lines
  result = result.replace(/\n{3,}/g, '\n\n')
  return result
}

// Fix malformed code blocks where language is on same line as code
// e.g., "```python code here" → "```python\ncode here"
function fixCodeBlocks(text: string): string {
  // Fix code blocks where language identifier runs into code on same line
  // Match ```language followed by non-whitespace on same line
  return text.replace(/```(\w+)\s+([^\n])/g, '```$1\n$2')
}

// Strip <thinking> and <analysis> blocks from content
function stripHiddenBlocks(text: string): { content: string; hadThinking: boolean; isThinkingInProgress: boolean } {
  // Check if thinking is still in progress (has opening tag but no closing)
  const hasOpenThinking = /<thinking>/i.test(text) && !/<\/thinking>/i.test(text)
  const hasOpenAnalysis = /<analysis>/i.test(text) && !/<\/analysis>/i.test(text)
  const isThinkingInProgress = hasOpenThinking || hasOpenAnalysis

  const thinkingRegex = /<thinking>[\s\S]*?<\/thinking>\s*/gi
  const analysisRegex = /<analysis>[\s\S]*?<\/analysis>\s*/gi
  const hadThinking = thinkingRegex.test(text) || analysisRegex.test(text)

  // Remove complete blocks
  let content = text.replace(/<thinking>[\s\S]*?<\/thinking>\s*/gi, '')
  content = content.replace(/<analysis>[\s\S]*?<\/analysis>\s*/gi, '')

  // Remove incomplete blocks (in progress)
  content = content.replace(/<thinking>[\s\S]*/gi, '')
  content = content.replace(/<analysis>[\s\S]*/gi, '')

  return { content: content.trim(), hadThinking, isThinkingInProgress }
}

// Agent icons and colors for spawn cards
const spawnAgentConfig: Record<string, { icon: string; color: string; label: string }> = {
  architect: { icon: '🏗️', color: 'border-blue-500 bg-blue-500/10', label: 'Architect' },
  reviewer: { icon: '🔍', color: 'border-amber-500 bg-amber-500/10', label: 'Reviewer' },
  coder: { icon: '💻', color: 'border-emerald-500 bg-emerald-500/10', label: 'Coder' },
  tester: { icon: '🧪', color: 'border-pink-500 bg-pink-500/10', label: 'Tester' },
  docs: { icon: '📝', color: 'border-cyan-500 bg-cyan-500/10', label: 'Docs' },
  devops: { icon: '🚀', color: 'border-orange-500 bg-orange-500/10', label: 'DevOps' },
  mo: { icon: '🤖', color: 'border-violet-500 bg-violet-500/10', label: 'MO' },
}

// Convert [SPAWN:agent] markers to styled placeholder
function convertSpawnMarkers(text: string): string {
  // Pattern: [SPAWN:agent] task description (until next [SPAWN: or end)
  const spawnRegex = /\[SPAWN:(\w+)\]\s*([^\[]*?)(?=\[SPAWN:|\n\n|$)/gi

  return text.replace(spawnRegex, (_, agent, task) => {
    const config = spawnAgentConfig[agent.toLowerCase()] || spawnAgentConfig.mo
    const taskText = task.trim()
    // Use a special markdown-safe format that we'll render specially
    return `\n\n:::spawn[${agent}|${config.icon}|${config.label}|${taskText}]:::\n\n`
  })
}

// Convert numbered line formats to proper markdown code blocks
// Handles: "• 1: code", "• 284 : code", "1, 1: code" (diff format), "  220: code" (indented)
function convertNumberedLinesToCodeBlocks(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []
  let inCodeBlock = false
  let codeLines: string[] = []
  let prevWasNumbered = false
  let lastLineNum = 0

  // Patterns for numbered lines:
  // • 1: code  OR  • 284 : code  OR  1, 1: code  OR   220: code (with leading whitespace)
  const numberedLineRegex = /^\s*(?:[•\-\*]\s*)?(\d+)(?:,\s*\d+)?\s*:\s?(.*)$/
  
  for (const line of lines) {
    const match = line.match(numberedLineRegex)
    
    if (match) {
      const lineNum = parseInt(match[1], 10)
      // Check if this continues a sequence (allow gaps up to 10 for diff output)
      if (!inCodeBlock || (lineNum > lastLineNum && lineNum <= lastLineNum + 10)) {
        if (!inCodeBlock) {
          inCodeBlock = true
          codeLines = []
        }
        codeLines.push(match[2])
        lastLineNum = lineNum
      } else {
        // New sequence - flush previous block
        if (codeLines.length > 0) {
          result.push('```')
          result.push(...codeLines)
          result.push('```')
        }
        codeLines = [match[2]]
        lastLineNum = lineNum
        inCodeBlock = true
      }
      prevWasNumbered = true
    } else {
      if (inCodeBlock && prevWasNumbered) {
        // End of code block - wrap it
        result.push('```')
        result.push(...codeLines)
        result.push('```')
        inCodeBlock = false
        codeLines = []
        lastLineNum = 0
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
    <div className="relative group my-4">
      {/* Header bar */}
      <div className="flex items-center justify-between px-4 py-2 bg-zinc-800 dark:bg-zinc-900 rounded-t-xl border border-b-0 border-zinc-700/50">
        <span className="text-xs text-zinc-400 font-mono">{language || 'code'}</span>
        <CopyButton text={children} className="opacity-60 hover:opacity-100" />
      </div>
      <pre className={cn(
        'bg-zinc-900 dark:bg-zinc-950 rounded-b-xl overflow-x-auto text-sm',
        'border border-t-0 border-zinc-700/50'
      )}>
        <code className={cn('font-mono text-zinc-100 block py-3', className)}>
          {lines.map((line, i) => (
            <div key={i} className="flex hover:bg-white/5 transition-colors">
              <span className="select-none text-zinc-600 text-right pr-4 pl-4 min-w-[3.5rem] border-r border-zinc-800/50">
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
        'flex gap-4 py-5 px-6 group relative transition-colors duration-200',
        isUser ? 'bg-muted/30' : 'bg-transparent hover:bg-muted/10'
      )}
      onMouseEnter={() => setShowCopy(true)}
      onMouseLeave={() => setShowCopy(false)}
    >
      <div
        className={cn(
          'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0 shadow-md',
          isUser
            ? 'bg-secondary text-secondary-foreground'
            : `bg-gradient-to-br ${agentColors[agentId] || agentColors.mo} text-white font-bold text-xs`
        )}
      >
        {isUser ? <User className="w-5 h-5" /> : (agentIcons[agentId] || 'MO')}
      </div>

      <div className="flex-1 overflow-hidden min-w-0">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-sm font-medium">
            {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          </span>
          {!isUser && agentId !== 'mo' && (
            <span className="text-[10px] text-muted-foreground bg-muted/50 px-2 py-0.5 rounded-full border border-border/50">
              {agentId}
            </span>
          )}
          {/* Copy entire message button */}
          {!isUser && message.content && showCopy && (
            <CopyButton text={message.content} className="ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
          )}
        </div>
        
        {isThinking ? (
          <ThinkingIndicator />
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-foreground prose-p:text-foreground prose-strong:text-foreground prose-li:text-foreground">
            {(() => {
              const { content: rawContent, hadThinking, isThinkingInProgress } = stripHiddenBlocks(message.content)
              const filtered = filterToolLogs(rawContent)
              const withFixedCodeBlocks = fixCodeBlocks(filtered)
              const withSpawnCards = convertSpawnMarkers(withFixedCodeBlocks)
              const content = convertNumberedLinesToCodeBlocks(withSpawnCards)
              return (
                <>
                  {/* Show thinking in progress indicator */}
                  {isThinkingInProgress && (
                    <div className="flex items-center gap-2 text-xs text-violet-400 mb-3 p-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
                      <div className="flex gap-1">
                        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
                      </div>
                      <span>Thinking through the problem...</span>
                    </div>
                  )}
                  {/* Show completed thinking badge */}
                  {hadThinking && !isThinkingInProgress && (
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
                p: ({ children }) => {
                  // Check for spawn card markers
                  const text = String(children)
                  const spawnMatch = text.match(/:::spawn\[(\w+)\|([^|]+)\|([^|]+)\|([^\]]+)\]:::/)
                  if (spawnMatch) {
                    const [, agent, icon, label, task] = spawnMatch
                    const config = spawnAgentConfig[agent.toLowerCase()] || spawnAgentConfig.mo
                    return (
                      <div className={cn(
                        'my-3 p-3 rounded-lg border-l-4 flex items-start gap-3',
                        config.color
                      )}>
                        <span className="text-2xl">{icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="font-semibold text-sm">{label}</span>
                            <span className="text-xs px-1.5 py-0.5 rounded bg-black/20 text-muted-foreground">
                              spawning
                            </span>
                          </div>
                          <p className="text-sm text-muted-foreground leading-snug break-words">
                            {task}
                          </p>
                        </div>
                      </div>
                    )
                  }
                  return <p className="my-2 leading-relaxed">{children}</p>
                },
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
