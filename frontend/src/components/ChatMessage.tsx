import { useState, useMemo, Suspense, lazy } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Copy, Check, Image as ImageIcon, ExternalLink, ChevronDown, ChevronRight } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import ThinkingIndicator from '@/components/ThinkingIndicator'
import CodeBlock, { InlineCode } from '@/components/CodeBlock'
import type { ChatMessage as ChatMessageType } from '@/stores/chat'

// Lazy load heavy components
const MermaidDiagram = lazy(() => import('@/components/MermaidDiagram'))
const Chart = lazy(() => import('@/components/Chart'))

interface ChatMessageProps {
  message: ChatMessageType
  isThinking?: boolean
}

// Strip ANSI escape codes from terminal output
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '')
}

// Filter out verbose tool execution log lines and CLI artifacts
function filterToolLogs(text: string): string {
  const toolLogPatterns = [
    /^[✓✔☑✗✘❌]\s*(?:Successfully|Failed).*$/gm,
    /^(?:Successfully|Failed)\s+(?:read|wrote|deleted|copied).*$/gm,
    /^Reading (?:directory|file):.*$/gm,
    /^Searching.*\.\.\..*$/gm,
    /^Found \d+ (?:files?|matches?).*$/gm,
    /^↱ Operation \d+:.*$/gm,
    /^[•\-\s]*Completed in \d+\.?\d*s?.*$/gm,
    /^\[Overview\].*bytes.*tokens.*$/gm,
    /^⋮.*$/gm,
    /^\s*Summary:.*$/gm,
    /^Purpose:.*$/gm,
    /^Updating:.*$/gm,
    /^Creating:.*$/gm,
    /^Deleting:.*$/gm,
    /^\d+ operations? processed.*$/gm,
    /^Now let me analyze.*$/gm,
    /^Let me start by reading.*$/gm,
    // Kiro CLI ASCII art and banners
    /^[⠀\s]*[▀▄█░▒▓⣴⣶⣦⡀⣾⡿⠁⢻⡆⢰⣿⠋⠙⣿]+[⠀\s]*$/gm,
    /^.*╭─+.*─+╮.*$/gm,
    /^.*╰─+.*─+╯.*$/gm,
    /^.*│.*│.*$/gm,
    /^Model:\s*(Auto|claude-[\w\-.]+).*$/gm,
    /^.*Did you know\?.*$/gm,
    /^.*\/changelog.*$/gm,
    /^.*\/model to change.*$/gm,
    /^error: Tool approval required.*$/gm,
    /^.*--trust-all-tools.*$/gm,
    /^.*--no-interactive.*$/gm,
  ]

  let result = text
  for (const pattern of toolLogPatterns) {
    result = result.replace(pattern, '')
  }
  // Clean up lines that are mostly Unicode whitespace/box chars
  result = result.split('\n').filter(line => {
    // Skip lines that are mostly special Unicode chars
    const specialChars = (line.match(/[⠀▀▄█░▒▓│╭╮╯╰─┌┐└┘├┤┬┴┼]/g) || []).length
    return specialChars < line.length * 0.5
  }).join('\n')
  result = result.replace(/\n{3,}/g, '\n\n')
  return result
}

// Fix malformed code blocks
function fixCodeBlocks(text: string): string {
  return text.replace(/```(\w+)\s+([^\n])/g, '```$1\n$2')
}

// Strip hidden blocks
function stripHiddenBlocks(text: string): { content: string; hadThinking: boolean; isThinkingInProgress: boolean } {
  const hasOpenThinking = /<thinking>/i.test(text) && !/<\/thinking>/i.test(text)
  const hasOpenAnalysis = /<analysis>/i.test(text) && !/<\/analysis>/i.test(text)
  const isThinkingInProgress = hasOpenThinking || hasOpenAnalysis

  const thinkingRegex = /<thinking>[\s\S]*?<\/thinking>\s*/gi
  const analysisRegex = /<analysis>[\s\S]*?<\/analysis>\s*/gi
  const hadThinking = thinkingRegex.test(text) || analysisRegex.test(text)

  let content = text.replace(/<thinking>[\s\S]*?<\/thinking>\s*/gi, '')
  content = content.replace(/<analysis>[\s\S]*?<\/analysis>\s*/gi, '')
  content = content.replace(/<thinking>[\s\S]*/gi, '')
  content = content.replace(/<analysis>[\s\S]*/gi, '')

  return { content: content.trim(), hadThinking, isThinkingInProgress }
}

// Agent configs
const spawnAgentConfig: Record<string, { icon: string; color: string; label: string }> = {
  architect: { icon: '🏗️', color: 'border-blue-500 bg-blue-500/10', label: 'Architect' },
  reviewer: { icon: '🔍', color: 'border-amber-500 bg-amber-500/10', label: 'Reviewer' },
  coder: { icon: '💻', color: 'border-emerald-500 bg-emerald-500/10', label: 'Coder' },
  tester: { icon: '🧪', color: 'border-pink-500 bg-pink-500/10', label: 'Tester' },
  docs: { icon: '📝', color: 'border-cyan-500 bg-cyan-500/10', label: 'Docs' },
  devops: { icon: '🚀', color: 'border-orange-500 bg-orange-500/10', label: 'DevOps' },
  mo: { icon: '🤖', color: 'border-violet-500 bg-violet-500/10', label: 'MO' },
}

// Convert spawn markers
function convertSpawnMarkers(text: string): string {
  const spawnRegex = /\[SPAWN:(\w+)\]\s*([^\[]*?)(?=\[SPAWN:|\n\n|$)/gi
  return text.replace(spawnRegex, (_, agent, task) => {
    const config = spawnAgentConfig[agent.toLowerCase()] || spawnAgentConfig.mo
    return `\n\n:::spawn[${agent}|${config.icon}|${config.label}|${task.trim()}]:::\n\n`
  })
}

// Convert numbered lines to code blocks
function convertNumberedLinesToCodeBlocks(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []
  let inCodeBlock = false
  let codeLines: string[] = []
  let prevWasNumbered = false
  let lastLineNum = 0

  const numberedLineRegex = /^\s*(?:[•\-\*]\s*)?(\d+)(?:,\s*\d+)?\s*:\s?(.*)$/

  for (const line of lines) {
    const match = line.match(numberedLineRegex)

    if (match) {
      const lineNum = parseInt(match[1], 10)
      if (!inCodeBlock || (lineNum > lastLineNum && lineNum <= lastLineNum + 10)) {
        if (!inCodeBlock) {
          inCodeBlock = true
          codeLines = []
        }
        codeLines.push(match[2])
        lastLineNum = lineNum
      } else {
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
        'p-1.5 rounded-lg transition-all duration-200',
        'hover:bg-muted text-muted-foreground hover:text-foreground',
        copied && 'text-emerald-500',
        className
      )}
      title={copied ? 'Copied!' : 'Copy'}
    >
      {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
    </button>
  )
}

// Image component with lightbox
function ChatImage({ src, alt }: { src: string; alt?: string }) {
  const [isOpen, setIsOpen] = useState(false)
  const [error, setError] = useState(false)

  if (error) {
    return (
      <div className="my-4 p-4 rounded-xl bg-muted/30 border border-border flex items-center gap-3 text-muted-foreground">
        <ImageIcon className="w-5 h-5" />
        <span className="text-sm">Failed to load image</span>
      </div>
    )
  }

  return (
    <>
      <div className="chat-image my-4 inline-block max-w-lg cursor-pointer" onClick={() => setIsOpen(true)}>
        <img
          src={src}
          alt={alt || 'Image'}
          onError={() => setError(true)}
          className="rounded-lg"
        />
      </div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8 cursor-pointer"
            onClick={() => setIsOpen(false)}
          >
            <motion.img
              initial={{ scale: 0.9 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0.9 }}
              src={src}
              alt={alt || 'Image'}
              className="max-w-full max-h-full object-contain rounded-lg"
            />
          </motion.div>
        )}
      </AnimatePresence>
    </>
  )
}

// Collapsible section for long content
function CollapsibleSection({ title, children, defaultOpen = false }: {
  title: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen)

  return (
    <div className="my-4 rounded-xl border border-border overflow-hidden">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors"
      >
        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        <span className="font-medium text-sm">{title}</span>
      </button>
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="p-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Loading fallback for lazy components
function ComponentLoading() {
  return (
    <div className="my-4 p-8 rounded-xl bg-muted/30 border border-border flex items-center justify-center">
      <div className="flex items-center gap-2 text-muted-foreground">
        <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
        <span>Loading...</span>
      </div>
    </div>
  )
}

export default function ChatMessage({ message, isThinking }: ChatMessageProps) {
  const [showCopy, setShowCopy] = useState(false)
  const isUser = message.role === 'user'
  const agentId = message.agentId || 'mo'

  const processedContent = useMemo(() => {
    const { content: rawContent, hadThinking, isThinkingInProgress } = stripHiddenBlocks(message.content)
    const filtered = filterToolLogs(rawContent)
    const withFixedCodeBlocks = fixCodeBlocks(filtered)
    const withSpawnCards = convertSpawnMarkers(withFixedCodeBlocks)
    const content = convertNumberedLinesToCodeBlocks(withSpawnCards)
    return { content: stripAnsi(content), hadThinking, isThinkingInProgress }
  }, [message.content])

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'flex gap-4 py-6 px-6 group relative',
        isUser ? 'message-user rounded-2xl mx-4 my-2' : 'hover:bg-muted/5 transition-colors duration-200'
      )}
      onMouseEnter={() => setShowCopy(true)}
      onMouseLeave={() => setShowCopy(false)}
    >
      {/* Avatar */}
      <motion.div
        initial={{ scale: 0.8 }}
        animate={{ scale: 1 }}
        className={cn(
          'w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0',
          'shadow-lg transition-shadow duration-300 hover:shadow-xl',
          isUser
            ? 'bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-800 text-gray-600 dark:text-gray-300'
            : `bg-gradient-to-br ${agentColors[agentId] || agentColors.mo} text-white font-bold text-xs`
        )}
      >
        {isUser ? <User className="w-5 h-5" /> : (agentIcons[agentId] || 'MO')}
      </motion.div>

      {/* Content */}
      <div className="flex-1 overflow-hidden min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <span className="font-semibold text-foreground">
            {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          </span>
          {!isUser && agentId !== 'mo' && (
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full font-medium',
              `agent-bg-${agentId} agent-${agentId}`
            )}>
              {agentId}
            </span>
          )}
          <span className="text-xs text-muted-foreground ml-auto">
            {message.timestamp?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
          {!isUser && message.content && showCopy && (
            <CopyButton text={message.content} className="copy-button" />
          )}
        </div>

        {/* Message Body */}
        {isThinking ? (
          <ThinkingIndicator />
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            {/* Thinking Indicators */}
            <AnimatePresence>
              {processedContent.isThinkingInProgress && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-3 text-sm text-violet-400 mb-4 p-3 rounded-xl bg-violet-500/10 border border-violet-500/20"
                >
                  <div className="flex gap-1">
                    <span className="w-2 h-2 bg-violet-500 rounded-full typing-dot" />
                    <span className="w-2 h-2 bg-violet-500 rounded-full typing-dot" />
                    <span className="w-2 h-2 bg-violet-500 rounded-full typing-dot" />
                  </div>
                  <span>Thinking through the problem...</span>
                </motion.div>
              )}
            </AnimatePresence>

            {processedContent.hadThinking && !processedContent.isThinkingInProgress && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3 pb-3 border-b border-border/50">
                <span className="w-2 h-2 rounded-full bg-violet-500" />
                <span>Analyzed the problem</span>
              </div>
            )}

            {/* Markdown Content */}
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h1: ({ children }) => (
                  <h1 className="markdown-h1">{children}</h1>
                ),
                h2: ({ children }) => (
                  <h2 className="markdown-h2">{children}</h2>
                ),
                h3: ({ children }) => (
                  <h3 className="markdown-h3">{children}</h3>
                ),
                ul: ({ children }) => (
                  <ul className="markdown-list list-disc">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="markdown-list list-decimal">{children}</ol>
                ),
                li: ({ children }) => <li className="pl-1">{children}</li>,
                p: ({ children }) => {
                  const text = String(children)

                  // Spawn card markers
                  const spawnMatch = text.match(/:::spawn\[(\w+)\|([^|]+)\|([^|]+)\|([^\]]+)\]:::/)
                  if (spawnMatch) {
                    const [, agent, icon, label, task] = spawnMatch
                    const config = spawnAgentConfig[agent.toLowerCase()] || spawnAgentConfig.mo
                    return (
                      <motion.div
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        className={cn(
                          'my-4 p-4 rounded-xl border-l-4 flex items-start gap-4',
                          'bg-gradient-to-r from-transparent to-muted/30',
                          config.color
                        )}
                      >
                        <span className="text-3xl">{icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-2">
                            <span className="font-semibold">{label}</span>
                            <span className="badge badge-primary text-xs">spawning</span>
                          </div>
                          <p className="text-sm text-muted-foreground leading-relaxed break-words">
                            {task}
                          </p>
                        </div>
                      </motion.div>
                    )
                  }

                  return <p className="my-3 leading-relaxed text-foreground">{children}</p>
                },
                blockquote: ({ children }) => (
                  <blockquote className="blockquote my-4">{children}</blockquote>
                ),
                pre: ({ children }) => {
                  const codeElement = children as React.ReactElement
                  const codeProps = codeElement?.props || {}
                  const codeContent = String(codeProps.children || '').replace(/\n$/, '')
                  const className = codeProps.className || ''
                  const language = className.replace('language-', '')

                  // Handle mermaid diagrams
                  if (language === 'mermaid') {
                    return (
                      <Suspense fallback={<ComponentLoading />}>
                        <MermaidDiagram chart={codeContent} />
                      </Suspense>
                    )
                  }

                  // Handle chart data
                  if (language === 'chart' || language === 'chart-json') {
                    try {
                      const chartData = JSON.parse(codeContent)
                      if (chartData.type && chartData.data) {
                        return (
                          <Suspense fallback={<ComponentLoading />}>
                            <Chart
                              type={chartData.type}
                              data={chartData.data}
                              title={chartData.title}
                            />
                          </Suspense>
                        )
                      }
                    } catch {
                      // Fall through to code block
                    }
                  }

                  return <CodeBlock code={codeContent} language={language} />
                },
                code: ({ className, children }) => {
                  const isInline = !className
                  if (isInline) {
                    return <InlineCode>{children}</InlineCode>
                  }
                  return <code className={cn(className, 'font-mono')}>{children}</code>
                },
                table: ({ children }) => (
                  <div className="overflow-x-auto my-4 rounded-xl border border-border">
                    <table className="markdown-table">{children}</table>
                  </div>
                ),
                thead: ({ children }) => <thead>{children}</thead>,
                th: ({ children }) => (
                  <th className="bg-muted/50 px-4 py-3 text-left font-semibold border-b border-border">
                    {children}
                  </th>
                ),
                td: ({ children }) => (
                  <td className="px-4 py-3 border-b border-border/50">{children}</td>
                ),
                tr: ({ children }) => (
                  <tr className="hover:bg-muted/30 transition-colors">{children}</tr>
                ),
                hr: () => <div className="divider my-8" />,
                a: ({ href, children }) => (
                  <a
                    href={href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="markdown-link inline-flex items-center gap-1"
                  >
                    {children}
                    <ExternalLink className="w-3 h-3" />
                  </a>
                ),
                img: ({ src, alt }) => <ChatImage src={src || ''} alt={alt} />,
                strong: ({ children }) => {
                  const text = String(children)
                  if (text.includes('🔴') || text.includes('CRITICAL')) {
                    return <strong className="text-red-500 font-semibold">{children}</strong>
                  }
                  if (text.includes('🟠') || text.includes('HIGH')) {
                    return <strong className="text-orange-500 font-semibold">{children}</strong>
                  }
                  if (text.includes('🟡') || text.includes('MEDIUM')) {
                    return <strong className="text-yellow-500 font-semibold">{children}</strong>
                  }
                  if (text.includes('🟢') || text.includes('LOW')) {
                    return <strong className="text-emerald-500 font-semibold">{children}</strong>
                  }
                  return <strong className="font-semibold text-foreground">{children}</strong>
                },
                em: ({ children }) => <em className="italic text-muted-foreground">{children}</em>,
              }}
            >
              {processedContent.content}
            </ReactMarkdown>
          </div>
        )}
      </div>
    </motion.div>
  )
}

// Export collapsible for use elsewhere
export { CollapsibleSection }
