import { X } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { QueuedMessage } from '@/stores/chat'

interface QueueIndicatorProps {
  queue: QueuedMessage[]
  onClear: () => void
  className?: string
}

export default function QueueIndicator({ queue, onClear, className }: QueueIndicatorProps) {
  if (queue.length === 0) return null

  return (
    <div className={cn('px-4 py-2 bg-muted/50 border-t border-border', className)}>
      <div className="max-w-4xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm">
          <div className="flex items-center gap-1.5">
            <div className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
            <span className="text-muted-foreground font-medium">
              {queue.length} message{queue.length > 1 ? 's' : ''} queued
            </span>
          </div>
          <span className="text-muted-foreground/60">•</span>
          <span className="text-muted-foreground/80 truncate max-w-xs">
            {queue[0].content.slice(0, 50)}{queue[0].content.length > 50 ? '...' : ''}
          </span>
        </div>
        <button
          onClick={onClear}
          className="p-1 rounded hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
          title="Clear queue"
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
