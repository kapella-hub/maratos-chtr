import { useEffect, useRef, useState } from 'react'
import mermaid from 'mermaid'
import DOMPurify from 'dompurify'
import { cn } from '@/lib/utils'
import { AlertCircle, Maximize2, X } from 'lucide-react'

interface MermaidDiagramProps {
  chart: string
  className?: string
}

/**
 * Supported Mermaid diagram types.
 *
 * Agents should output diagrams in these formats for org charts, flowcharts, etc.
 * See docs/DIAGRAMS.md for usage examples.
 */
export const SUPPORTED_DIAGRAM_TYPES = [
  'flowchart',    // Flowcharts and org charts (TB, LR, etc.)
  'graph',        // Same as flowchart (legacy syntax)
  'sequenceDiagram',
  'classDiagram',
  'stateDiagram',
  'stateDiagram-v2',
  'erDiagram',    // Entity-relationship
  'gantt',
  'pie',
  'journey',      // User journey
  'mindmap',      // Mind maps (great for org structures)
  'timeline',
  'quadrantChart',
  'gitGraph',
  'C4Context',    // C4 architecture diagrams
  'C4Container',
  'C4Component',
  'C4Deployment',
  'sankey',       // Sankey diagrams
  'xychart',      // XY charts (beta)
] as const

export type DiagramType = typeof SUPPORTED_DIAGRAM_TYPES[number]

/**
 * Sanitize SVG output from Mermaid.
 * Strips any scripting elements that might have been injected.
 */
function sanitizeSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    // Block scripting in SVG
    FORBID_TAGS: ['script', 'foreignObject', 'animate', 'animateMotion', 'animateTransform', 'set'],
    FORBID_ATTR: [
      'onload', 'onerror', 'onclick', 'onmouseover', 'onmouseout',
      'onfocus', 'onblur', 'onkeydown', 'onkeyup', 'onkeypress',
    ],
  })
}

// Initialize mermaid with dark theme and strict security
mermaid.initialize({
  startOnLoad: false,
  theme: 'dark',
  // Use strict security level to prevent XSS
  // Note: This disables click events in diagrams, which is the safe default
  securityLevel: 'strict',
  themeVariables: {
    primaryColor: '#8b5cf6',
    primaryTextColor: '#e2e8f0',
    primaryBorderColor: '#6366f1',
    lineColor: '#64748b',
    secondaryColor: '#1e293b',
    tertiaryColor: '#0f172a',
    background: '#0f172a',
    mainBkg: '#1e293b',
    nodeBorder: '#475569',
    clusterBkg: '#1e293b',
    clusterBorder: '#334155',
    titleColor: '#e2e8f0',
    edgeLabelBackground: '#1e293b',
    nodeTextColor: '#e2e8f0',
  },
  flowchart: {
    htmlLabels: false, // Disabled for security with strict mode
    curve: 'basis',
    rankSpacing: 50,
    nodeSpacing: 30,
  },
  sequence: {
    diagramMarginX: 20,
    diagramMarginY: 20,
    actorMargin: 50,
    boxTextMargin: 5,
    noteMargin: 10,
    messageMargin: 35,
  },
  mindmap: {
    padding: 16,
    maxNodeWidth: 200,
  },
  // Disable potentially dangerous features
  fontFamily: 'ui-sans-serif, system-ui, sans-serif',
  logLevel: 'error', // Reduce console noise
})

export default function MermaidDiagram({ chart, className }: MermaidDiagramProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [svg, setSvg] = useState<string>('')
  const [error, setError] = useState<string | null>(null)
  const [isFullscreen, setIsFullscreen] = useState(false)
  const idRef = useRef(`mermaid-${Math.random().toString(36).substr(2, 9)}`)

  useEffect(() => {
    const renderDiagram = async () => {
      try {
        setError(null)
        const { svg: rawSvg } = await mermaid.render(idRef.current, chart)
        // Sanitize SVG output to ensure no malicious content
        const sanitizedSvg = sanitizeSvg(rawSvg)
        setSvg(sanitizedSvg)
      } catch (err) {
        console.error('Mermaid render error:', err)
        setError(err instanceof Error ? err.message : 'Failed to render diagram')
      }
    }

    renderDiagram()
  }, [chart])

  if (error) {
    return (
      <div className={cn('my-4 p-4 rounded-xl bg-red-500/10 border border-red-500/20', className)}>
        <div className="flex items-center gap-2 text-red-400 mb-2">
          <AlertCircle className="w-4 h-4" />
          <span className="font-medium">Diagram Error</span>
        </div>
        <pre className="text-xs text-red-300/80 overflow-x-auto">{error}</pre>
        <details className="mt-2">
          <summary className="text-xs text-muted-foreground cursor-pointer hover:text-foreground">
            Show source
          </summary>
          <pre className="mt-2 p-2 rounded bg-muted/50 text-xs overflow-x-auto">{chart}</pre>
        </details>
      </div>
    )
  }

  if (!svg) {
    return (
      <div className={cn('my-4 p-8 rounded-xl bg-muted/30 border border-border/30', className)}>
        <div className="flex items-center justify-center gap-2 text-muted-foreground">
          <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin" />
          <span>Rendering diagram...</span>
        </div>
      </div>
    )
  }

  return (
    <>
      <div
        className={cn(
          'my-4 p-4 rounded-xl bg-[#0f172a] border border-[#1e293b]',
          'overflow-x-auto group relative',
          className
        )}
      >
        <button
          onClick={() => setIsFullscreen(true)}
          className={cn(
            'absolute top-2 right-2 p-1.5 rounded-lg',
            'bg-white/5 hover:bg-white/10 text-gray-400 hover:text-gray-200',
            'opacity-0 group-hover:opacity-100 transition-opacity duration-200',
            'z-10'
          )}
          title="View fullscreen"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
        <div
          ref={containerRef}
          className="mermaid flex justify-center"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>

      {/* Fullscreen Modal */}
      {isFullscreen && (
        <div
          className="fixed inset-0 z-50 bg-black/90 flex items-center justify-center p-8"
          onClick={() => setIsFullscreen(false)}
        >
          <button
            onClick={() => setIsFullscreen(false)}
            className={cn(
              'absolute top-4 right-4 p-2 rounded-lg',
              'bg-white/10 hover:bg-white/20 text-white',
              'transition-colors duration-200'
            )}
          >
            <X className="w-6 h-6" />
          </button>
          <div
            className="max-w-full max-h-full overflow-auto p-4"
            onClick={(e) => e.stopPropagation()}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
        </div>
      )}
    </>
  )
}

/**
 * Check if a language identifier indicates Mermaid code.
 */
export function isMermaidCode(language: string): boolean {
  return language.toLowerCase() === 'mermaid'
}

/**
 * Pattern to detect Mermaid diagram content without explicit language tag.
 * Matches the start of supported diagram types.
 */
export const MERMAID_CONTENT_PATTERN = new RegExp(
  `^\\s*(${SUPPORTED_DIAGRAM_TYPES.join('|')})\\b`,
  'i'
)

/**
 * Check if content looks like a Mermaid diagram (for auto-detection).
 */
export function isMermaidContent(content: string): boolean {
  return MERMAID_CONTENT_PATTERN.test(content.trim())
}
