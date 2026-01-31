import { useState } from 'react'
import { motion } from 'framer-motion'
import { Copy, Check, Download, Code, Eye, FileJson, BarChart3, GitCompare, Terminal, FileText } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { CanvasArtifact as ArtifactType } from '@/stores/canvas'
import CodeBlock from '@/components/CodeBlock'
import MermaidDiagram from '@/components/MermaidDiagram'
import TaskGraph from './TaskGraph'

interface CanvasArtifactProps {
  artifact: ArtifactType
  isActive: boolean
  onSelect: () => void
}

const typeIcons: Record<string, React.ElementType> = {
  code: Code,
  preview: Eye,
  form: FileJson,
  chart: BarChart3,
  diagram: GitCompare,
  table: FileJson,
  diff: GitCompare,
  terminal: Terminal,
  markdown: FileText,
}

const typeColors: Record<string, string> = {
  code: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
  preview: 'text-green-400 bg-green-500/10 border-green-500/20',
  form: 'text-purple-400 bg-purple-500/10 border-purple-500/20',
  chart: 'text-amber-400 bg-amber-500/10 border-amber-500/20',
  diagram: 'text-cyan-400 bg-cyan-500/10 border-cyan-500/20',
  table: 'text-pink-400 bg-pink-500/10 border-pink-500/20',
  diff: 'text-orange-400 bg-orange-500/10 border-orange-500/20',
  terminal: 'text-gray-400 bg-gray-500/10 border-gray-500/20',
  markdown: 'text-violet-400 bg-violet-500/10 border-violet-500/20',
  task_graph: 'text-blue-400 bg-blue-500/10 border-blue-500/20',
}

export default function CanvasArtifact({ artifact, isActive, onSelect }: CanvasArtifactProps) {
  const [copied, setCopied] = useState(false)
  const Icon = typeIcons[artifact.type] || Code
  const colorClass = typeColors[artifact.type] || typeColors.code

  const handleCopy = async () => {
    await navigator.clipboard.writeText(artifact.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDownload = () => {
    const extension = artifact.metadata?.language || 'txt'
    const blob = new Blob([artifact.content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${artifact.title.replace(/\s+/g, '-').toLowerCase()}.${extension}`
    a.click()
    URL.revokeObjectURL(url)
  }

  const renderContent = () => {
    switch (artifact.type) {
      case 'code':
        return (
          <div className="text-sm">
            <CodeBlock
              code={artifact.content}
              language={artifact.metadata?.language || 'plaintext'}
            />
          </div>
        )

      case 'preview':
        return (
          <div className="bg-white rounded-lg overflow-hidden">
            <iframe
              srcDoc={artifact.content}
              className="w-full h-64 border-0"
              sandbox="allow-scripts"
              title={artifact.title}
            />
          </div>
        )

      case 'terminal':
        return (
          <div className="bg-gray-950 rounded-lg p-4 font-mono text-sm text-gray-300 overflow-auto max-h-64">
            <pre className="whitespace-pre-wrap">{artifact.content}</pre>
          </div>
        )

      case 'markdown':
        return (
          <div className="prose prose-sm dark:prose-invert max-w-none p-4 bg-muted/30 rounded-lg">
            {artifact.content}
          </div>
        )

      case 'diagram':
        // Render Mermaid diagrams
        return (
          <MermaidDiagram chart={artifact.content} />
        )

      case 'chart':
        // For now, show the JSON data - could integrate with Chart.js later
        return (
          <div className="p-4 bg-muted/30 rounded-lg">
            <pre className="text-sm overflow-auto">{artifact.content}</pre>
          </div>
        )

      case 'task_graph':
        return (
          <TaskGraph data={artifact.content} />
        )

      default:
        return (
          <div className="p-4 bg-muted/30 rounded-lg">
            <pre className="text-sm overflow-auto whitespace-pre-wrap">{artifact.content}</pre>
          </div>
        )
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'rounded-xl border overflow-hidden cursor-pointer transition-all',
        isActive
          ? 'border-primary ring-2 ring-primary/20'
          : 'border-border hover:border-border/80'
      )}
      onClick={onSelect}
    >
      {/* Header */}
      <div
        className={cn(
          'flex items-center gap-3 px-4 py-3 border-b',
          colorClass
        )}
      >
        <Icon className="w-4 h-4" />
        <span className="font-medium text-sm flex-1 truncate">{artifact.title}</span>
        <div className="flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleCopy()
            }}
            className="p-1.5 rounded-lg hover:bg-background/50 transition-colors"
            title="Copy"
          >
            {copied ? (
              <Check className="w-4 h-4 text-green-400" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation()
              handleDownload()
            }}
            className="p-1.5 rounded-lg hover:bg-background/50 transition-colors"
            title="Download"
          >
            <Download className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="p-3 bg-background/50">
        {renderContent()}
      </div>

      {/* Footer */}
      {artifact.metadata?.language && (
        <div className="px-4 py-2 border-t border-border/50 bg-muted/20">
          <span className="text-xs text-muted-foreground font-mono">
            {artifact.metadata.language}
          </span>
        </div>
      )}
    </motion.div>
  )
}
