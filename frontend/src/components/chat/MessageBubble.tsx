import { useState, useMemo, Suspense, lazy } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize'
import { User, Copy, Check, ExternalLink, ChevronDown, ChevronRight, Brain } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import CodeBlock, { InlineCode } from '@/components/CodeBlock'
import type { ChatMessage } from '@/stores/chat'
import type { ThinkingBlock, ThinkingStep } from '@/lib/api'

/**
 * Sanitization schema for HTML rendering.
 *
 * Security Policy:
 * - Whitelist approach: only explicitly allowed tags/attributes pass through
 * - Scripts, iframes, style tags, and event handlers are ALWAYS blocked
 * - Links are forced to open in new tabs with noopener/noreferrer
 *
 * Allowed tags:
 * - Text: p, b, i, strong, em, u, s, mark, small, sub, sup, br, hr
 * - Lists: ul, ol, li, dl, dt, dd
 * - Tables: table, thead, tbody, tfoot, tr, th, td, caption
 * - Code: code, pre, kbd, samp, var
 * - Links: a (with safe href protocols only)
 * - Block: div, span, blockquote, details, summary, figure, figcaption
 * - Headings: h1-h6
 *
 * Explicitly BLOCKED (security):
 * - script, iframe, object, embed, style, link, meta, base, form, input
 * - All on* event handler attributes
 * - javascript:, vbscript:, data: URLs (except safe image data URIs)
 */
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [
    // Text structure
    'p', 'br', 'hr',
    // Text formatting
    'b', 'i', 'strong', 'em', 'u', 's', 'mark', 'small', 'sub', 'sup',
    // Lists
    'ul', 'ol', 'li', 'dl', 'dt', 'dd',
    // Tables
    'table', 'thead', 'tbody', 'tfoot', 'tr', 'th', 'td', 'caption',
    // Code
    'code', 'pre', 'kbd', 'samp', 'var',
    // Links
    'a',
    // Block elements
    'div', 'span', 'blockquote',
    // Headings
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    // Details/summary
    'details', 'summary',
    // Figure
    'figure', 'figcaption',
    // Images (for inline base64 only, URLs validated)
    'img',
  ],
  attributes: {
    ...defaultSchema.attributes,
    '*': ['className', 'id', 'title', 'lang', 'dir'],
    a: ['href', 'target', 'rel'],
    img: ['src', 'alt', 'width', 'height'],
    td: ['colSpan', 'rowSpan'],
    th: ['colSpan', 'rowSpan', 'scope'],
    ol: ['start', 'type', 'reversed'],
    li: ['value'],
    details: ['open'],
    code: ['className'],
    pre: ['className'],
    span: ['className', 'style'],
    div: ['className', 'style'],
  },
  protocols: {
    href: ['http', 'https', 'mailto'],
    src: ['http', 'https', 'data'],
  },
  // Explicitly strip dangerous tags (belt and suspenders)
  strip: ['script', 'style', 'iframe', 'object', 'embed', 'form', 'input', 'textarea', 'button'],
  // Prefix user-provided IDs to prevent DOM clobbering
  clobberPrefix: 'user-content-',
  clobber: ['name', 'id'],
}

// Lazy load heavy components
const MermaidDiagram = lazy(() => import('@/components/MermaidDiagram'))
const Chart = lazy(() => import('@/components/Chart'))

// Import Mermaid helpers
import { isMermaidContent } from '@/components/MermaidDiagram'

interface MessageBubbleProps {
  message: ChatMessage
  isThinking?: boolean
  showTimestamp?: boolean
}

// Agent colors and labels
const agentColors: Record<string, string> = {
  mo: 'from-violet-500 to-purple-600',
  architect: 'from-blue-500 to-cyan-600',
  reviewer: 'from-amber-500 to-orange-600',
  coder: 'from-emerald-500 to-green-600',
  tester: 'from-pink-500 to-rose-600',
  docs: 'from-cyan-500 to-sky-600',
  devops: 'from-orange-500 to-red-600',
}

const agentLabels: Record<string, string> = {
  mo: 'MO',
  architect: 'Architect',
  reviewer: 'Reviewer',
  coder: 'Coder',
  tester: 'Tester',
  docs: 'Docs',
  devops: 'DevOps',
}

const agentIcons: Record<string, string> = {
  mo: 'MO',
  architect: '🏗️',
  coder: '💻',
  reviewer: '🔍',
  tester: '🧪',
  docs: '📝',
  devops: '🚀',
}

// Processing utilities
function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])/g, '')
}

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

function filterToolLogs(text: string): string {
  const toolLogPatterns = [
    // Goal/checkpoint markers
    /^\[GOAL:\d+\]\s*.*/gm,
    /^\[GOAL_DONE:\d+\]\s*$/gm,
    /^\[GOAL_FAILED:\d+\]\s*.*/gm,
    /^\[CHECKPOINT:\w+\]\s*.*/gm,
    /^\[(CODER|ARCHITECT|REVIEWER|TESTER|DOCS|DEVOPS)\]\s*/gm,
    // Kiro-cli tool execution output
    /^Reading (?:file|directory):.*\(using tool:.*\).*$/gm,
    /^↱ Operation \d+:.*$/gm,
    /^[✓✗] Successfully (?:read|wrote|deleted).*$/gm,
    /^Batch \w+ operation with \d+ operations.*$/gm,
    /^⋮$/gm,
    /^Summary: \d+ operations processed.*$/gm,
    /^Completed in [\d.]+s$/gm,
    // Tool result markers
    /^Purpose:.*$/gm,
    /^Code$/gm,
    /^\d+ lines?$/gm,
    /^Copy$/gm,
  ]

  let result = text
  for (const pattern of toolLogPatterns) {
    result = result.replace(pattern, '')
  }
  result = result.replace(/\n{3,}/g, '\n\n')
  return result.trim()
}

function fixCodeBlocks(text: string): string {
  return text.replace(/```(\w+)\s+([^\n])/g, '```$1\n$2')
}

/**
 * Detect and wrap tree-like structures in code blocks.
 * Matches patterns like:
 * ├── folder/
 * │   ├── file.py
 * └── README.md
 */
function wrapTreeStructures(text: string): string {
  // Patterns for tree detection:
  // 1. Lines with tree branch characters (├── or └──)
  // 2. Lines with vertical continuation (│ followed by spaces)
  // 3. Empty tree lines (just │ or spaces)
  const treeChars = '├└│─┬┴┼┤┌┐┘'

  const isTreeLine = (line: string): boolean => {
    // Must contain tree characters
    if (![...treeChars].some(c => line.includes(c))) return false
    // Line with branch: ├── or └──
    if (/[├└]──/.test(line)) return true
    // Continuation line: starts with │ or spaces then │
    if (/^[ \t]*│/.test(line)) return true
    return false
  }

  const lines = text.split('\n')
  const result: string[] = []
  let inTree = false
  let treeLines: string[] = []
  let treeHeader: string | null = null

  // Helper to check if a line looks like a tree header (project-name/ or "structure:")
  const isHeaderLine = (line: string) => {
    if (!line) return false
    const trimmed = line.trim()
    // Project path like "myproject/" or "/path/to/project/"
    if (/^[A-Za-z0-9_\-./~]+\/?$/.test(trimmed)) return true
    // Contains "structure" keyword
    if (trimmed.toLowerCase().includes('structure')) return true
    return false
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const lineIsTree = isTreeLine(line)

    // Also check for blank lines within a tree (they should be included)
    const isBlankInTree = inTree && line.trim() === '' &&
      i + 1 < lines.length && isTreeLine(lines[i + 1])

    if (lineIsTree || isBlankInTree) {
      if (!inTree) {
        // Starting a new tree block
        inTree = true
        // Check if previous non-empty line was a header
        for (let j = result.length - 1; j >= 0; j--) {
          const prevLine = result[j]
          if (prevLine.trim() === '') continue
          if (isHeaderLine(prevLine)) {
            treeHeader = result.splice(j).join('\n').trim()
          }
          break
        }
      }
      treeLines.push(line)
    } else if (inTree) {
      // Check if this is just whitespace before more tree content
      if (line.trim() === '' && i + 1 < lines.length) {
        const nextNonEmpty = lines.slice(i + 1).find(l => l.trim() !== '')
        if (nextNonEmpty && isTreeLine(nextNonEmpty)) {
          treeLines.push(line)
          continue
        }
      }

      // End of tree block - wrap it
      if (treeLines.length > 0) {
        const treeContent = treeHeader
          ? `${treeHeader}\n${treeLines.join('\n')}`
          : treeLines.join('\n')
        result.push('```')
        result.push(treeContent)
        result.push('```')
      }
      inTree = false
      treeLines = []
      treeHeader = null
      result.push(line)
    } else {
      result.push(line)
    }
  }

  // Handle tree at end of text
  if (inTree && treeLines.length > 0) {
    const treeContent = treeHeader
      ? `${treeHeader}\n${treeLines.join('\n')}`
      : treeLines.join('\n')
    result.push('```')
    result.push(treeContent)
    result.push('```')
  }

  return result.join('\n')
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

// Loading fallback
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

// Thinking step type colors
const thinkingStepColors: Record<string, string> = {
  analysis: 'text-blue-400',
  evaluation: 'text-amber-400',
  decision: 'text-emerald-400',
  validation: 'text-cyan-400',
  risk: 'text-red-400',
  implementation: 'text-violet-400',
  critique: 'text-orange-400',
}

// Level display info
const levelInfo: Record<string, { label: string; color: string }> = {
  off: { label: 'Off', color: 'text-gray-400' },
  minimal: { label: 'Minimal', color: 'text-gray-400' },
  low: { label: 'Low', color: 'text-blue-400' },
  medium: { label: 'Medium', color: 'text-amber-400' },
  high: { label: 'High', color: 'text-violet-400' },
  max: { label: 'Maximum', color: 'text-rose-400' },
}

// Thinking Data Display component
function ThinkingDataDisplay({ thinkingData }: { thinkingData: ThinkingBlock }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const levelDisplay = levelInfo[thinkingData.level] || levelInfo.medium
  const hasSteps = thinkingData.steps && thinkingData.steps.length > 0
  const duration = thinkingData.duration_ms ? `${(thinkingData.duration_ms / 1000).toFixed(1)}s` : null

  return (
    <div className="mb-3">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 text-xs text-muted-foreground hover:text-foreground transition-colors"
      >
        <div className="flex items-center gap-1.5">
          <Brain className="w-3.5 h-3.5 text-violet-400" />
          <span className={levelDisplay.color}>{levelDisplay.label} Reasoning</span>
          {thinkingData.template && (
            <span className="px-1.5 py-0.5 rounded bg-muted/50 text-[10px] uppercase tracking-wide">
              {thinkingData.template}
            </span>
          )}
          {duration && (
            <span className="text-muted-foreground/70">• {duration}</span>
          )}
        </div>
        {hasSteps && (
          <span className="text-muted-foreground/50">
            {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          </span>
        )}
      </button>

      <AnimatePresence>
        {isExpanded && hasSteps && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-2 pl-5 border-l-2 border-violet-500/30 space-y-2">
              {thinkingData.steps?.map((step: ThinkingStep, idx: number) => (
                <div key={idx} className="text-xs">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className={cn('font-medium capitalize', thinkingStepColors[step.type] || 'text-muted-foreground')}>
                      {step.type}
                    </span>
                    {step.confidence !== undefined && (
                      <span className="text-muted-foreground/60">
                        {Math.round(step.confidence * 100)}% confidence
                      </span>
                    )}
                  </div>
                  <p className="text-muted-foreground leading-relaxed">{step.content}</p>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// Collapsible section
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

export default function MessageBubble({ message, isThinking, showTimestamp = true }: MessageBubbleProps) {
  const [showCopy, setShowCopy] = useState(false)
  const isUser = message.role === 'user'
  const agentId = message.agentId || 'mo'

  const processedContent = useMemo(() => {
    const { content: rawContent, hadThinking, isThinkingInProgress } = stripHiddenBlocks(message.content)
    const filtered = filterToolLogs(rawContent)
    const withFixedCodeBlocks = fixCodeBlocks(filtered)
    const withWrappedTrees = wrapTreeStructures(withFixedCodeBlocks)
    const content = stripAnsi(withWrappedTrees)
    return { content, hadThinking, isThinkingInProgress }
  }, [message.content])

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className={cn(
        'flex gap-4 py-5 px-4 group relative',
        isUser ? 'message-user rounded-2xl mx-2 my-2' : 'hover:bg-muted/5 transition-colors duration-200'
      )}
      onMouseEnter={() => setShowCopy(true)}
      onMouseLeave={() => setShowCopy(false)}
    >
      {/* Avatar */}
      <motion.div
        initial={{ scale: 0.8 }}
        animate={{ scale: 1 }}
        className={cn(
          'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0',
          'shadow-lg transition-shadow duration-300 hover:shadow-xl',
          isUser
            ? 'bg-gradient-to-br from-gray-100 to-gray-200 dark:from-gray-700 dark:to-gray-800 text-gray-600 dark:text-gray-300'
            : `bg-gradient-to-br ${agentColors[agentId] || agentColors.mo} text-white font-bold text-xs`
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : (agentIcons[agentId] || 'MO')}
      </motion.div>

      {/* Content */}
      <div className="flex-1 overflow-hidden min-w-0">
        {/* Header */}
        <div className="flex items-center gap-2 mb-2">
          <span className="font-semibold text-sm text-foreground">
            {isUser ? 'You' : agentLabels[agentId] || 'MO'}
          </span>
          {showTimestamp && (
            <span className="text-xs text-muted-foreground ml-auto">
              {message.timestamp?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          {!isUser && message.content && (
            <CopyButton
              text={message.content}
              className={cn('copy-button', !showCopy && 'opacity-0 group-hover:opacity-100')}
            />
          )}
        </div>

        {/* Message Body */}
        {isThinking ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-2 py-2"
          >
            <div className="flex gap-1">
              {[0, 1, 2].map((i) => (
                <motion.span
                  key={i}
                  className="w-2 h-2 bg-violet-500 rounded-full"
                  animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
                  transition={{ duration: 0.6, repeat: Infinity, delay: i * 0.15 }}
                />
              ))}
            </div>
          </motion.div>
        ) : (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            {/* Structured Thinking Data Display */}
            {message.thinkingData && (
              <ThinkingDataDisplay thinkingData={message.thinkingData} />
            )}

            {/* Extended Thinking Indicator */}
            <AnimatePresence>
              {processedContent.isThinkingInProgress && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  className="flex items-center gap-2 text-sm text-violet-400 mb-3"
                >
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: 'linear' }}
                  >
                    <Brain className="w-4 h-4" />
                  </motion.div>
                  <span>Analyzing...</span>
                </motion.div>
              )}
            </AnimatePresence>

            {processedContent.hadThinking && !processedContent.isThinkingInProgress && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground mb-3 pb-3 border-b border-border/50">
                <span className="w-2 h-2 rounded-full bg-violet-500" />
                <span>Analyzed the problem</span>
              </div>
            )}

            {/* Markdown Content - with HTML sanitization */}
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[
                rehypeRaw,
                [rehypeSanitize, sanitizeSchema],
              ]}
              components={{
                p: ({ children }) => <p className="my-2 leading-relaxed text-foreground">{children}</p>,
                pre: ({ children }) => {
                  const codeElement = children as React.ReactElement
                  const codeProps = codeElement?.props || {}
                  const codeContent = String(codeProps.children || '').replace(/\n$/, '')
                  const className = codeProps.className || ''

                  let language = className.replace('language-', '').trim().toLowerCase()
                  let filePath: string | undefined

                  if (language.includes(':')) {
                    const [lang, path] = language.split(':')
                    language = lang.trim()
                    filePath = path.trim()
                  }

                  // Handle mermaid diagrams (explicit language or auto-detected)
                  const isMermaid = language === 'mermaid' ||
                    (!language && isMermaidContent(codeContent))

                  if (isMermaid) {
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

                  const codeBlock = <CodeBlock code={codeContent} language={language} filePath={filePath} />

                  // Wrap long outputs in collapsible sections
                  if (codeContent.split('\n').length > 30) {
                    return (
                      <CollapsibleSection title="📄 Details" defaultOpen={false}>
                        {codeBlock}
                      </CollapsibleSection>
                    )
                  }

                  return codeBlock
                },
                code: ({ className, children }) => {
                  const isInline = !className
                  if (isInline) {
                    return <InlineCode>{children}</InlineCode>
                  }
                  return <code className={cn(className, 'font-mono')}>{children}</code>
                },
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
                strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
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
