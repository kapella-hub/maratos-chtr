import { useState, useMemo, Suspense, lazy } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { User, Copy, Check, Image as ImageIcon, ExternalLink, ChevronDown, ChevronRight, Brain } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
// ThinkingIndicator moved inline for simplicity
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

// Filter out verbose tool execution log lines, CLI artifacts, and GOAL markers
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
    /^Now let me (?:check|examine|look|read|review).*$/gm,
    /^Let me (?:also )?(?:check|examine|look|read|review).*$/gm,
    // Kiro CLI ASCII art and banners - be specific to avoid filtering legitimate flowcharts
    /^[⠀\s]*[▀▄█░▒▓⣴⣶⣦⡀⣾⡿⠁⢻⡆⢰⣿⠋⠙⣿]+[⠀\s]*$/gm,
    // Only filter Kiro-style rounded box banners (╭─╮ style), not regular boxes
    /^\s*╭─+╮\s*$/gm,
    /^\s*╰─+╯\s*$/gm,
    // Only filter Kiro banner content (│ with mostly whitespace or "Did you know" style content)
    /^\s*│\s+(?:Did you know|Type \/|Model:|Auto)\s*.*│\s*$/gm,
    /^Model:\s*(Auto|claude-[\w\-.]+).*$/gm,
    /^.*Did you know\?.*$/gm,
    /^.*\/changelog.*$/gm,
    /^.*\/model to change.*$/gm,
    /^error: Tool approval required.*$/gm,
    /^.*--trust-all-tools.*$/gm,
    /^.*--no-interactive.*$/gm,
    // Filter ALL GOAL markers - these are internal tracking
    /^\[GOAL:\d+\]\s*.*/gm,
    /^\[GOAL_DONE:\d+\]\s*$/gm,
    /^\[GOAL_FAILED:\d+\]\s*.*/gm,
    /^\[CHECKPOINT:\w+\]\s*.*/gm,
    // Filter agent header markers
    /^\[(CODER|ARCHITECT|REVIEWER|TESTER|DOCS|DEVOPS)\]\s*/gm,
    // Filter Summary lines
    /^\s*-?\s*Summary:\s*\d+\s+operations?\s+processed.*$/gm,
  ]

  let result = text
  for (const pattern of toolLogPatterns) {
    result = result.replace(pattern, '')
  }
  // Clean up lines that are mostly Kiro/CLI braille art (⠀▀▄█░▒▓) but preserve box-drawing chars for flowcharts
  result = result.split('\n').filter(line => {
    // Only filter lines with braille/block art chars (CLI banners), not box-drawing chars (flowcharts)
    const cliArtChars = (line.match(/[⠀▀▄█░▒▓⣴⣶⣦⡀⣾⡿⢻⣿]/g) || []).length
    // If line is mostly CLI art chars, filter it out
    return cliArtChars < line.length * 0.3
  }).join('\n')
  result = result.replace(/\n{3,}/g, '\n\n')
  return result.trim()
}

// Fix malformed code blocks
function fixCodeBlocks(text: string): string {
  return text.replace(/```(\w+)\s+([^\n])/g, '```$1\n$2')
}

// Detect orphaned code-like content and wrap in code blocks
function wrapOrphanedCode(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []
  let codeBuffer: string[] = []
  let inFence = false

  // Patterns that indicate code-like content
  const codePatterns = [
    /^\s*(?:const|let|var|function|class|import|export|return|if|else|for|while|switch|try|catch|async|await|throw|new|typeof|instanceof)\b/,
    /^\s*(?:from|import)\s+['"]/, // Python/JS imports
    /^\s*[@#]\w+/, // Decorators
    /^\s*\w+\s*[=:]\s*[{[\('"<]/, // Assignments
    /^\s*[{}[\]();,]\s*$/, // Lone brackets
    /^\s*\.\w+\s*[({]/, // Method chains
    /^\s*(?:public|private|protected|static|readonly)\s/, // Access modifiers
    /^\s*(?:def|fn|pub|impl|struct|enum|trait|type|interface)\s/, // Rust/Python/TS
    /=>\s*[{(]/, // Arrow functions
  ]

  const isCodeLike = (line: string) => codePatterns.some(p => p.test(line))

  for (const line of lines) {
    if (line.startsWith('```')) {
      inFence = !inFence
      if (codeBuffer.length >= 2) {
        result.push('```')
        result.push(...codeBuffer)
        result.push('```')
        codeBuffer = []
      } else if (codeBuffer.length > 0) {
        result.push(...codeBuffer)
        codeBuffer = []
      }
      result.push(line)
      continue
    }

    if (inFence) {
      result.push(line)
      continue
    }

    if (isCodeLike(line)) {
      codeBuffer.push(line)
    } else {
      if (codeBuffer.length >= 2) {
        result.push('```')
        result.push(...codeBuffer)
        result.push('```')
      } else if (codeBuffer.length > 0) {
        result.push(...codeBuffer)
      }
      codeBuffer = []
      result.push(line)
    }
  }

  if (codeBuffer.length >= 2) {
    result.push('```')
    result.push(...codeBuffer)
    result.push('```')
  } else if (codeBuffer.length > 0) {
    result.push(...codeBuffer)
  }

  return result.join('\n')
}

// Inject file paths into code fences from surrounding context
function injectFilePathsIntoCodeFences(text: string): string {
  const lines = text.split('\n')
  const result: string[] = []

  // Multiple patterns to extract file paths from text
  const filePathPatterns = [
    // Backtick quoted paths: `src/components/file.tsx`
    /[`]([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,6})[`]/,
    // Double/single quoted paths
    /["']([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,6})["']/,
    // "File: path/to/file.ts" or "In path/to/file.ts:"
    /(?:file|in|update|create|modify|edit)[:\s]+([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,6})/i,
    // "path/to/file.ts:" at end of line
    /([a-zA-Z0-9_\-./]+\.[a-zA-Z]{1,6}):?\s*$/,
    // Relative or absolute paths
    /((?:\.{0,2}\/)?[a-zA-Z0-9_\-]+(?:\/[a-zA-Z0-9_\-]+)*\.[a-zA-Z]{1,6})/,
  ]

  const extractFilePath = (text: string): string | null => {
    for (const pattern of filePathPatterns) {
      const match = text.match(pattern)
      if (match?.[1]) {
        // Filter out common false positives
        const path = match[1]
        if (path.includes('http') || path.includes('www.') || path === '.md' || path === '.ts') {
          continue
        }
        // Must have a directory separator or be a recognizable filename
        if (path.includes('/') || /^[a-zA-Z0-9_\-]+\.[a-zA-Z]{2,6}$/.test(path)) {
          return path
        }
      }
    }
    return null
  }

  let pendingFilePath: string | null = null
  const lookbackLines = 5 // Check up to 5 lines back for file references

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]

    // Check if this is a code fence
    const fenceMatch = line.match(/^```(\w*)$/)
    if (fenceMatch) {
      const lang = fenceMatch[1] || ''

      // Look back for file path in recent lines
      if (!pendingFilePath) {
        for (let j = Math.max(0, result.length - lookbackLines); j < result.length; j++) {
          const prevLine = result[j]
          const foundPath = extractFilePath(prevLine)
          if (foundPath) {
            pendingFilePath = foundPath
          }
        }
      }

      if (pendingFilePath) {
        result.push(`\`\`\`${lang}:${pendingFilePath}`)
        pendingFilePath = null
        continue
      }
    }

    // Track file paths mentioned in this line for next code block
    const foundPath = extractFilePath(line)
    if (foundPath) {
      pendingFilePath = foundPath
    }

    result.push(line)
  }

  return result.join('\n')
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

// Detect if this is a subagent response (not from MO or user)
const SUBAGENT_IDS = new Set(['architect', 'coder', 'reviewer', 'tester', 'docs', 'devops'])

function isSubagentResponse(agentId: string): boolean {
  return SUBAGENT_IDS.has(agentId.toLowerCase())
}

// Extract a brief summary from agent response content
function extractAgentSummary(content: string, agentId: string): string {
  // Try to find key accomplishments
  const lines = content.split('\n').filter(l => l.trim())

  // Look for summary patterns
  for (const line of lines) {
    if (line.match(/^(completed|implemented|fixed|created|updated|reviewed|tested|added)/i)) {
      return line.slice(0, 100) + (line.length > 100 ? '...' : '')
    }
    if (line.match(/^(summary|result|done):/i)) {
      return line.replace(/^(summary|result|done):\s*/i, '').slice(0, 100)
    }
  }

  // Fallback to first meaningful line
  for (const line of lines) {
    if (line.length > 20 && !line.startsWith('[') && !line.startsWith('#')) {
      return line.slice(0, 80) + (line.length > 80 ? '...' : '')
    }
  }

  // Default summary based on agent type
  const agentActions: Record<string, string> = {
    coder: 'Code implementation completed',
    architect: 'Architecture design completed',
    reviewer: 'Code review completed',
    tester: 'Tests completed',
    docs: 'Documentation completed',
    devops: 'DevOps task completed',
  }
  return agentActions[agentId.toLowerCase()] || 'Task completed'
}

export default function ChatMessage({ message, isThinking }: ChatMessageProps) {
  const [showCopy, setShowCopy] = useState(false)
  const isUser = message.role === 'user'
  const agentId = message.agentId || 'mo'
  const isSubagent = isSubagentResponse(agentId)
  // Subagent responses are collapsed by default
  const [expanded, setExpanded] = useState(!isSubagent)

  // Detect and wrap agent work output sections in collapsible blocks
  function wrapAgentOutput(text: string): string {
    const lines = text.split('\n')
    const result: string[] = []
    let agentOutputLines: string[] = []
    let inAgentOutput = false
    
    const agentOutputPattern = /^[✓✔☑✗✘❌⋮]\s|^\s*(?:Successfully|Failed|Reading|Searching|Found|Completed in|Purpose:|Updating:|Creating:|Deleting:)/
    
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      const isAgentOutput = agentOutputPattern.test(line.trim())
      
      if (isAgentOutput) {
        if (!inAgentOutput) {
          inAgentOutput = true
          agentOutputLines = []
        }
        agentOutputLines.push(line)
      } else {
        if (inAgentOutput && agentOutputLines.length >= 2) {
          // Wrap accumulated agent output in a collapsible code block
          result.push('')
          result.push('<details>')
          result.push('<summary>🔧 Agent Work Details</summary>')
          result.push('')
          result.push('```')
          result.push(...agentOutputLines)
          result.push('```')
          result.push('</details>')
          result.push('')
          agentOutputLines = []
        } else if (inAgentOutput) {
          // Not enough lines, just add them normally
          result.push(...agentOutputLines)
        }
        inAgentOutput = false
        result.push(line)
      }
    }
    
    // Handle remaining agent output at end
    if (inAgentOutput && agentOutputLines.length >= 2) {
      result.push('')
      result.push('<details>')
      result.push('<summary>🔧 Agent Work Details</summary>')
      result.push('')
      result.push('```')
      result.push(...agentOutputLines)
      result.push('```')
      result.push('</details>')
      result.push('')
    } else if (agentOutputLines.length > 0) {
      result.push(...agentOutputLines)
    }
    
    return result.join('\n')
  }

  const processedContent = useMemo(() => {
    const { content: rawContent, hadThinking, isThinkingInProgress } = stripHiddenBlocks(message.content)
    const withAgentWork = wrapAgentOutput(rawContent)
    const filtered = filterToolLogs(withAgentWork)
    const withFixedCodeBlocks = fixCodeBlocks(filtered)
    const withSpawnCards = convertSpawnMarkers(withFixedCodeBlocks)
    const withNumberedLines = convertNumberedLinesToCodeBlocks(withSpawnCards)
    const withOrphanedCode = wrapOrphanedCode(withNumberedLines)
    const withFilePaths = injectFilePathsIntoCodeFences(withOrphanedCode)
    const content = withFilePaths
    const summary = isSubagent ? extractAgentSummary(rawContent, agentId) : ''
    return { content: stripAnsi(content), hadThinking, isThinkingInProgress, summary }
  }, [message.content, agentId, isSubagent])

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
          {!isUser && message.content && (
            <CopyButton text={message.content} className={cn('copy-button', !showCopy && 'opacity-0 group-hover:opacity-100')} />
          )}
        </div>

        {/* Message Body */}
        {isThinking ? (
          /* Simple typing indicator - header shows detailed status */
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
            {/* Extended Thinking Indicator - only show when model reports active thinking */}
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

            {/* Subagent Response - Collapsible by default */}
            {isSubagent && !isUser && (
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className={cn(
                  'rounded-xl border overflow-hidden mb-2',
                  expanded ? 'border-border/50' : `border-${agentId === 'coder' ? 'emerald' : agentId === 'reviewer' ? 'amber' : agentId === 'tester' ? 'pink' : agentId === 'architect' ? 'blue' : 'violet'}-500/30`
                )}
              >
                <button
                  onClick={() => setExpanded(!expanded)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-3 transition-colors text-left',
                    expanded ? 'bg-muted/20 hover:bg-muted/30' : 'bg-muted/40 hover:bg-muted/50'
                  )}
                >
                  <motion.div
                    animate={{ rotate: expanded ? 90 : 0 }}
                    transition={{ duration: 0.2 }}
                  >
                    <ChevronRight className="w-4 h-4 text-muted-foreground" />
                  </motion.div>
                  <span className="text-lg">{agentIcons[agentId] || '🤖'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm">{agentLabels[agentId] || agentId}</span>
                      <span className={cn(
                        'text-xs px-2 py-0.5 rounded-full',
                        expanded ? 'bg-muted text-muted-foreground' : 'bg-emerald-500/20 text-emerald-400'
                      )}>
                        {expanded ? 'expanded' : 'completed'}
                      </span>
                    </div>
                    {!expanded && processedContent.summary && (
                      <p className="text-xs text-muted-foreground mt-1 truncate">
                        {processedContent.summary}
                      </p>
                    )}
                  </div>
                </button>
              </motion.div>
            )}

            {/* Markdown Content - hidden if subagent response and not expanded */}
            {(expanded || isUser || !isSubagent) && (
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                details: ({ children }) => {
                  const [isOpen, setIsOpen] = useState(false)
                  return (
                    <div className="my-4 rounded-xl border border-border overflow-hidden">
                      <button
                        onClick={() => setIsOpen(!isOpen)}
                        className="w-full flex items-center gap-2 px-4 py-3 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
                      >
                        {isOpen ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                        <span className="font-medium text-sm">
                          {/* Extract summary text from children */}
                          {Array.isArray(children) && children.find((child: any) => child?.type === 'summary')?.props?.children || '🔧 Agent Work Details'}
                        </span>
                      </button>
                      <AnimatePresence>
                        {isOpen && (
                          <motion.div
                            initial={{ height: 0 }}
                            animate={{ height: 'auto' }}
                            exit={{ height: 0 }}
                            className="overflow-hidden"
                          >
                            <div className="p-4">
                              {/* Render children except summary */}
                              {Array.isArray(children) && children.filter((child: any) => child?.type !== 'summary')}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )
                },
                summary: () => null, // Handled by details component
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

                    // Agent-specific styling
                    const agentStyles: Record<string, { bg: string; border: string; glow: string; text: string }> = {
                      architect: {
                        bg: 'bg-gradient-to-br from-blue-950/80 to-cyan-950/60',
                        border: 'border-blue-500/40',
                        glow: 'shadow-blue-500/20',
                        text: 'text-blue-300',
                      },
                      coder: {
                        bg: 'bg-gradient-to-br from-emerald-950/80 to-green-950/60',
                        border: 'border-emerald-500/40',
                        glow: 'shadow-emerald-500/20',
                        text: 'text-emerald-300',
                      },
                      reviewer: {
                        bg: 'bg-gradient-to-br from-amber-950/80 to-orange-950/60',
                        border: 'border-amber-500/40',
                        glow: 'shadow-amber-500/20',
                        text: 'text-amber-300',
                      },
                      tester: {
                        bg: 'bg-gradient-to-br from-pink-950/80 to-rose-950/60',
                        border: 'border-pink-500/40',
                        glow: 'shadow-pink-500/20',
                        text: 'text-pink-300',
                      },
                      docs: {
                        bg: 'bg-gradient-to-br from-cyan-950/80 to-sky-950/60',
                        border: 'border-cyan-500/40',
                        glow: 'shadow-cyan-500/20',
                        text: 'text-cyan-300',
                      },
                      devops: {
                        bg: 'bg-gradient-to-br from-orange-950/80 to-red-950/60',
                        border: 'border-orange-500/40',
                        glow: 'shadow-orange-500/20',
                        text: 'text-orange-300',
                      },
                      mo: {
                        bg: 'bg-gradient-to-br from-violet-950/80 to-purple-950/60',
                        border: 'border-violet-500/40',
                        glow: 'shadow-violet-500/20',
                        text: 'text-violet-300',
                      },
                    }

                    const style = agentStyles[agent.toLowerCase()] || agentStyles.mo

                    return (
                      <>
                        <motion.div
                          initial={{ opacity: 0, y: 10, scale: 0.98 }}
                          animate={{ opacity: 1, y: 0, scale: 1 }}
                          transition={{ duration: 0.3, ease: 'easeOut' }}
                          className={cn(
                            'my-4 p-4 rounded-xl border',
                            'shadow-lg backdrop-blur-sm',
                            style.bg,
                            style.border,
                            style.glow
                          )}
                        >
                          <div className="flex items-start gap-4">
                            <div className="flex-shrink-0">
                              <div className={cn(
                                'w-12 h-12 rounded-xl flex items-center justify-center text-2xl',
                                'bg-black/30 border border-white/10'
                              )}>
                                {icon}
                              </div>
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-2">
                                <span className={cn('font-bold text-lg', style.text)}>
                                  {label}
                                </span>
                                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium bg-white/10 text-white/80">
                                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                                  spawning
                                </span>
                              </div>
                              <p className="text-sm text-white/80 leading-relaxed">
                                {task}
                              </p>
                            </div>
                          </div>
                        </motion.div>
                        <div className="h-2" /> {/* Spacing after spawn card */}
                      </>
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

                  // Extract language and file path from className
                  // Supports formats like: language-typescript:path/to/file.ts or language-typescript
                  let language = className.replace('language-', '').trim().toLowerCase()
                  let filePath: string | undefined

                  // Check for file path in language (e.g., typescript:src/file.ts)
                  if (language.includes(':')) {
                    const [lang, path] = language.split(':')
                    language = lang.trim()
                    filePath = path.trim()
                  }

                  // Also try to extract file path from first comment line in code
                  if (!filePath && codeContent) {
                    const firstLine = codeContent.split('\n')[0]
                    // Match patterns like: // src/components/file.tsx or # path/to/file.py
                    const filePathMatch = firstLine.match(/^(?:\/\/|#|\/\*)\s*(?:file:?\s*)?([a-zA-Z0-9_\-./]+\.[a-zA-Z0-9]+)/)
                    if (filePathMatch) {
                      filePath = filePathMatch[1]
                    }
                  }

                  // Handle mermaid diagrams - check for mermaid language or content
                  const isMermaid = language === 'mermaid' ||
                    // Fallback: detect mermaid by content patterns
                    (!language && /^(flowchart|graph|sequenceDiagram|classDiagram|stateDiagram|erDiagram|gantt|pie|journey)\b/i.test(codeContent.trim()))

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

                  // Check if this looks like a file diff or agent output
                  const isDiff = codeContent.includes('---') && codeContent.includes('+++') ||
                                 codeContent.match(/^[-+]\s/m) ||
                                 codeContent.includes('@@') ||
                                 (codeContent.split('\n').length > 20 && !language)

                  const codeBlock = <CodeBlock code={codeContent} language={language} filePath={filePath} />
                  
                  // Wrap diffs and long outputs in collapsible sections
                  if (isDiff || codeContent.split('\n').length > 30) {
                    const title = isDiff ? '📝 File Changes' : '📄 Details'
                    return (
                      <CollapsibleSection title={title} defaultOpen={false}>
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
            )}

            {/* Expand prompt for collapsed subagent responses */}
            {isSubagent && !expanded && !isUser && (
              <button
                onClick={() => setExpanded(true)}
                className="text-xs text-muted-foreground hover:text-foreground transition-colors mt-2"
              >
                Click to see full response...
              </button>
            )}
          </div>
        )}
      </div>
    </motion.div>
  )
}

// Export collapsible for use elsewhere
export { CollapsibleSection }
