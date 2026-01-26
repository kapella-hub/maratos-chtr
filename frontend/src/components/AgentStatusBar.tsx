import { motion, AnimatePresence } from 'framer-motion'
import { X, Clock, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface AgentStatusBarProps {
  isActive: boolean
  status: 'thinking' | 'streaming' | 'orchestrating'
  progress?: number
  estimatedTime?: number
  currentAction?: string
  onCancel?: () => void
  className?: string
}

export default function AgentStatusBar({
  isActive,
  status,
  progress = 0,
  estimatedTime,
  currentAction,
  onCancel,
  className
}: AgentStatusBarProps) {
  if (!isActive) return null

  const statusConfig = {
    thinking: {
      label: 'Thinking',
      color: 'from-violet-500 to-purple-500',
      bgColor: 'bg-violet-500/10',
      borderColor: 'border-violet-500/20'
    },
    streaming: {
      label: 'Responding',
      color: 'from-indigo-500 to-violet-500',
      bgColor: 'bg-indigo-500/10',
      borderColor: 'border-indigo-500/20'
    },
    orchestrating: {
      label: 'Orchestrating',
      color: 'from-purple-500 to-pink-500',
      bgColor: 'bg-purple-500/10',
      borderColor: 'border-purple-500/20'
    }
  }

  const config = statusConfig[status]

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        className={cn(
          'flex items-center gap-3 px-4 py-2.5 rounded-xl border backdrop-blur-sm',
          config.bgColor,
          config.borderColor,
          className
        )}
      >
        {/* Animated spinner */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
        >
          <Loader2 className={cn('w-4 h-4 bg-gradient-to-r bg-clip-text', config.color)} />
        </motion.div>

        {/* Status info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-sm font-medium">{config.label}</span>
            {currentAction && (
              <span className="text-xs text-muted-foreground truncate">
                {currentAction}
              </span>
            )}
          </div>

          {/* Progress bar */}
          {progress > 0 && (
            <div className="h-1 bg-background/50 rounded-full overflow-hidden">
              <motion.div
                className={cn('h-full bg-gradient-to-r rounded-full', config.color)}
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.3 }}
              />
            </div>
          )}
        </div>

        {/* Estimated time */}
        {estimatedTime && estimatedTime > 0 && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="w-3.5 h-3.5" />
            <span>{estimatedTime}s</span>
          </div>
        )}

        {/* Cancel button */}
        {onCancel && (
          <button
            onClick={onCancel}
            className={cn(
              'p-1.5 rounded-lg hover:bg-background/50 transition-colors',
              'text-muted-foreground hover:text-foreground'
            )}
            aria-label="Cancel"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </motion.div>
    </AnimatePresence>
  )
}
