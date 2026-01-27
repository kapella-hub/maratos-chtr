import { useRef, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { PanelRightClose, Trash2, Layers } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useCanvasStore } from '@/stores/canvas'
import CanvasArtifact from './CanvasArtifact'

interface CanvasPanelProps {
  className?: string
}

export default function CanvasPanel({ className }: CanvasPanelProps) {
  const {
    artifacts,
    activeArtifactId,
    panelVisible,
    panelWidth,
    setActiveArtifact,
    hidePanel,
    setPanelWidth,
    removeArtifact,
    clearArtifacts,
  } = useCanvasStore()

  const panelRef = useRef<HTMLDivElement>(null)
  const resizeRef = useRef<HTMLDivElement>(null)
  const isDragging = useRef(false)

  // Handle resize drag
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return
      const newWidth = window.innerWidth - e.clientX
      setPanelWidth(newWidth)
    }

    const handleMouseUp = () => {
      isDragging.current = false
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)

    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [setPanelWidth])

  const handleResizeStart = () => {
    isDragging.current = true
    document.body.style.cursor = 'ew-resize'
    document.body.style.userSelect = 'none'
  }

  if (!panelVisible || artifacts.length === 0) {
    return null
  }

  return (
    <AnimatePresence>
      <motion.div
        ref={panelRef}
        initial={{ x: panelWidth, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: panelWidth, opacity: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        style={{ width: panelWidth }}
        className={cn(
          'fixed right-0 top-0 bottom-0 z-40',
          'bg-background/95 backdrop-blur-xl',
          'border-l border-border/50',
          'flex flex-col',
          'shadow-2xl shadow-black/20',
          className
        )}
      >
        {/* Resize handle */}
        <div
          ref={resizeRef}
          onMouseDown={handleResizeStart}
          className="absolute left-0 top-0 bottom-0 w-1 cursor-ew-resize hover:bg-primary/50 transition-colors"
        />

        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border/50 bg-muted/30">
          <Layers className="w-5 h-5 text-primary" />
          <h2 className="font-semibold flex-1">Canvas</h2>
          <span className="text-xs text-muted-foreground px-2 py-1 rounded-full bg-muted">
            {artifacts.length} artifact{artifacts.length !== 1 ? 's' : ''}
          </span>
          {artifacts.length > 0 && (
            <button
              onClick={clearArtifacts}
              className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
              title="Clear all artifacts"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={hidePanel}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Close panel"
          >
            <PanelRightClose className="w-4 h-4" />
          </button>
        </div>

        {/* Artifact tabs */}
        {artifacts.length > 1 && (
          <div className="flex items-center gap-1 px-3 py-2 border-b border-border/30 overflow-x-auto">
            {artifacts.map((artifact) => (
              <button
                key={artifact.id}
                onClick={() => setActiveArtifact(artifact.id)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium transition-colors whitespace-nowrap',
                  activeArtifactId === artifact.id
                    ? 'bg-primary text-primary-foreground'
                    : 'bg-muted/50 text-muted-foreground hover:bg-muted'
                )}
              >
                {artifact.title}
              </button>
            ))}
          </div>
        )}

        {/* Artifact content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {artifacts.map((artifact) => (
            <div
              key={artifact.id}
              className={cn(
                activeArtifactId === artifact.id ? 'block' : 'hidden'
              )}
            >
              <CanvasArtifact
                artifact={artifact}
                isActive={activeArtifactId === artifact.id}
                onSelect={() => setActiveArtifact(artifact.id)}
              />

              {/* Delete button for individual artifact */}
              <div className="flex justify-end mt-2">
                <button
                  onClick={() => removeArtifact(artifact.id)}
                  className="text-xs text-muted-foreground hover:text-destructive flex items-center gap-1 transition-colors"
                >
                  <Trash2 className="w-3 h-3" />
                  Remove
                </button>
              </div>
            </div>
          ))}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
