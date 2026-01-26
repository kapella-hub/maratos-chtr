import { useState, useCallback, useMemo } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Copy, Check, Terminal, FileCode, FileJson, FileText, Braces, Hash, Database, ListOrdered } from 'lucide-react'
import { cn } from '@/lib/utils'

interface CodeBlockProps {
  code: string
  language?: string
  filePath?: string
  showLineNumbers?: boolean
  className?: string
  maxHeight?: number
  onRunInTerminal?: (code: string) => void
}

// Language icons and colors
const languageConfig: Record<string, { icon: typeof FileCode; color: string; label: string }> = {
  javascript: { icon: FileCode, color: 'text-yellow-400', label: 'JavaScript' },
  typescript: { icon: FileCode, color: 'text-blue-400', label: 'TypeScript' },
  jsx: { icon: FileCode, color: 'text-cyan-400', label: 'JSX' },
  tsx: { icon: FileCode, color: 'text-blue-400', label: 'TSX' },
  python: { icon: FileCode, color: 'text-green-400', label: 'Python' },
  rust: { icon: FileCode, color: 'text-orange-400', label: 'Rust' },
  go: { icon: FileCode, color: 'text-cyan-400', label: 'Go' },
  java: { icon: FileCode, color: 'text-red-400', label: 'Java' },
  cpp: { icon: FileCode, color: 'text-blue-500', label: 'C++' },
  c: { icon: FileCode, color: 'text-blue-400', label: 'C' },
  csharp: { icon: FileCode, color: 'text-green-500', label: 'C#' },
  php: { icon: FileCode, color: 'text-purple-400', label: 'PHP' },
  ruby: { icon: FileCode, color: 'text-red-500', label: 'Ruby' },
  swift: { icon: FileCode, color: 'text-orange-500', label: 'Swift' },
  kotlin: { icon: FileCode, color: 'text-purple-500', label: 'Kotlin' },
  json: { icon: FileJson, color: 'text-yellow-300', label: 'JSON' },
  yaml: { icon: FileText, color: 'text-red-300', label: 'YAML' },
  yml: { icon: FileText, color: 'text-red-300', label: 'YAML' },
  toml: { icon: FileText, color: 'text-orange-300', label: 'TOML' },
  html: { icon: Braces, color: 'text-orange-400', label: 'HTML' },
  css: { icon: Hash, color: 'text-blue-400', label: 'CSS' },
  scss: { icon: Hash, color: 'text-pink-400', label: 'SCSS' },
  sql: { icon: Database, color: 'text-blue-300', label: 'SQL' },
  bash: { icon: Terminal, color: 'text-green-300', label: 'Bash' },
  shell: { icon: Terminal, color: 'text-green-300', label: 'Shell' },
  sh: { icon: Terminal, color: 'text-green-300', label: 'Shell' },
  zsh: { icon: Terminal, color: 'text-green-300', label: 'Zsh' },
  powershell: { icon: Terminal, color: 'text-blue-300', label: 'PowerShell' },
  markdown: { icon: FileText, color: 'text-gray-300', label: 'Markdown' },
  md: { icon: FileText, color: 'text-gray-300', label: 'Markdown' },
  text: { icon: FileText, color: 'text-gray-400', label: 'Text' },
  plaintext: { icon: FileText, color: 'text-gray-400', label: 'Text' },
  dockerfile: { icon: FileCode, color: 'text-blue-400', label: 'Dockerfile' },
  graphql: { icon: Braces, color: 'text-pink-400', label: 'GraphQL' },
  lua: { icon: FileCode, color: 'text-blue-500', label: 'Lua' },
  r: { icon: FileCode, color: 'text-blue-400', label: 'R' },
  scala: { icon: FileCode, color: 'text-red-400', label: 'Scala' },
  haskell: { icon: FileCode, color: 'text-purple-400', label: 'Haskell' },
  elixir: { icon: FileCode, color: 'text-purple-400', label: 'Elixir' },
  erlang: { icon: FileCode, color: 'text-red-400', label: 'Erlang' },
  clojure: { icon: FileCode, color: 'text-green-400', label: 'Clojure' },
  vim: { icon: FileCode, color: 'text-green-500', label: 'Vim' },
  nginx: { icon: FileText, color: 'text-green-400', label: 'Nginx' },
  ini: { icon: FileText, color: 'text-gray-400', label: 'INI' },
  xml: { icon: Braces, color: 'text-orange-300', label: 'XML' },
  diff: { icon: FileCode, color: 'text-green-400', label: 'Diff' },
  makefile: { icon: FileCode, color: 'text-orange-400', label: 'Makefile' },
}

// Custom theme based on GitHub Dark
const customStyle = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: 'transparent',
    margin: 0,
    padding: 0,
    fontSize: '0.875rem',
    lineHeight: '1.7',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontSize: '0.875rem',
    lineHeight: '1.7',
  },
}

export default function CodeBlock({
  code,
  language = 'text',
  filePath,
  showLineNumbers: initialShowLineNumbers = true,
  className,
  maxHeight = 500,
  onRunInTerminal,
}: CodeBlockProps) {
  const [copied, setCopied] = useState(false)
  const [showLineNumbers, setShowLineNumbers] = useState(initialShowLineNumbers)

  const normalizedLang = useMemo(() => {
    const lang = language.toLowerCase().trim()
    // Map common aliases
    const aliases: Record<string, string> = {
      js: 'javascript',
      ts: 'typescript',
      py: 'python',
      rb: 'ruby',
      rs: 'rust',
      'c++': 'cpp',
      'c#': 'csharp',
      ps1: 'powershell',
      psm1: 'powershell',
    }
    return aliases[lang] || lang
  }, [language])

  const config = languageConfig[normalizedLang] || {
    icon: FileCode,
    color: 'text-gray-400',
    label: language || 'Code',
  }

  const Icon = config.icon
  const isShellScript = ['bash', 'shell', 'sh', 'zsh', 'powershell'].includes(normalizedLang)

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }, [code])

  const handleRunInTerminal = useCallback(() => {
    if (onRunInTerminal) {
      onRunInTerminal(code)
    }
  }, [code, onRunInTerminal])

  const lineCount = code.split('\n').length

  // Extract filename and directory from a path
  const fileName = filePath ? filePath.split('/').pop() : null
  const directory = filePath && filePath.includes('/')
    ? filePath.substring(0, filePath.lastIndexOf('/'))
    : null

  return (
    <div className={cn('code-block my-4 group', className)}>
      {/* Header */}
      <div className="code-block-header">
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <Icon className={cn('w-4 h-4 flex-shrink-0', config.color)} />
          {filePath ? (
            <div className="flex items-center gap-1.5 min-w-0" title={filePath}>
              {directory && (
                <>
                  <span className="text-[11px] text-gray-500 truncate max-w-[200px]">
                    {directory}/
                  </span>
                </>
              )}
              <span className="text-[13px] font-semibold text-gray-100 truncate">
                {fileName}
              </span>
            </div>
          ) : (
            <span className="text-xs font-medium text-gray-400">{config.label}</span>
          )}
          <span className="text-[11px] text-gray-600 flex-shrink-0 ml-2">
            {lineCount} {lineCount === 1 ? 'line' : 'lines'}
          </span>
        </div>
        <div className="flex items-center gap-1">
          {/* Line Numbers Toggle */}
          {lineCount > 1 && (
            <button
              onClick={() => setShowLineNumbers(!showLineNumbers)}
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
                'transition-all duration-200',
                showLineNumbers
                  ? 'bg-blue-500/20 text-blue-400'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              )}
              title={showLineNumbers ? 'Hide line numbers' : 'Show line numbers'}
            >
              <ListOrdered className="w-3.5 h-3.5" />
            </button>
          )}
          
          {/* Run in Terminal */}
          {isShellScript && (
            <button
              onClick={handleRunInTerminal}
              className={cn(
                'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
                'transition-all duration-200',
                'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              )}
              title="Run in terminal"
            >
              <Terminal className="w-3.5 h-3.5" />
              <span>Run</span>
            </button>
          )}
          
          {/* Copy Button */}
          <button
            onClick={handleCopy}
            className={cn(
              'flex items-center gap-1.5 px-2 py-1 rounded-md text-xs',
              'transition-all duration-200',
              copied
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            )}
            title={copied ? 'Copied!' : 'Copy code'}
          >
            {copied ? (
              <>
                <Check className="w-3.5 h-3.5" />
                <span>Copied!</span>
              </>
            ) : (
              <>
                <Copy className="w-3.5 h-3.5" />
                <span>Copy</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Code Content */}
      <div
        className="code-block-content overflow-auto"
        style={{ maxHeight }}
      >
        <SyntaxHighlighter
          language={normalizedLang}
          style={customStyle}
          showLineNumbers={showLineNumbers && lineCount > 1}
          lineNumberStyle={{
            minWidth: '2.5em',
            paddingRight: '1em',
            textAlign: 'right',
            color: '#6e7681',
            userSelect: 'none',
          }}
          customStyle={{
            background: 'transparent',
            margin: 0,
            padding: 0,
          }}
          wrapLines
          lineProps={(lineNumber) => ({
            style: {
              display: 'flex',
              flexWrap: 'wrap',
            },
            'data-line': lineNumber,
          })}
        >
          {code}
        </SyntaxHighlighter>
      </div>
    </div>
  )
}

// Inline code component for use in markdown
export function InlineCode({ children }: { children: React.ReactNode }) {
  return (
    <code className="inline-code">
      {children}
    </code>
  )
}
