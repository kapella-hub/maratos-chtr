import { motion, AnimatePresence } from 'framer-motion'
import { CheckCircle, XCircle, Loader2, ChevronRight, AlertCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { SubagentTask } from '@/stores/chat'

interface AgentCardProps {
  task: SubagentTask
  onCancel?: (taskId: string) => void
  compact?: boolean
}

const agentConfig: Record<string, { icon: string; color: string; bgColor: string }> = {
  architect: { icon: '🏗️', color: 'text-blue-400', bgColor: 'bg-blue-500/10' },
  coder: { icon: '💻', color: 'text-emerald-400', bgColor: 'bg-emerald-500/10' },
  reviewer: { icon: '🔍', color: 'text-amber-400', bgColor: 'bg-amber-500/10' },
  tester: { icon: '🧪', color: 'text-pink-400', bgColor: 'bg-pink-500/10' },
  docs: { icon: '📝', color: 'text-cyan-400', bgColor: 'bg-cyan-500/10' },
  devops: { icon: '🚀', color: 'text-orange-400', bgColor: 'bg-orange-500/10' },
  mo: { icon: '🤖', color: 'text-violet-400', bgColor: 'bg-violet-500/10' },
}

export default function AgentCard({ task, onCancel, compact = false }: AgentCardProps) {
  const config = agentConfig[task.agent.toLowerCase()] || agentConfig.mo
  const isActive = task.status === 'running' || task.status === 'spawning' || task.status === 'retrying'
  const isComplete = task.status === 'completed'
  const isFailed = task.status === 'failed' || task.status === 'timed_out' || task.status === 'cancelled'

  const getStatusIcon = () => {
    if (isComplete) return <CheckCircle className="w-4 h-4 text-emerald-500" />
    if (isFailed) return <XCircle className="w-4 h-4 text-red-500" />
    if (task.status === 'retrying') return <AlertCircle className="w-4 h-4 text-amber-500" />
    return <Loader2 className="w-4 h-4 animate-spin text-primary" />
  }

  const getStatusText = () => {
    if (isComplete) return 'Completed'
    if (task.status === 'failed') return 'Failed'
    if (task.status === 'timed_out') return 'Timed out'
    if (task.status === 'cancelled') return 'Cancelled'
    if (task.status === 'retrying') return `Retrying (${task.attempt}/${task.maxAttempts})`
    if (task.status === 'spawning') return 'Starting...'
    return task.currentAction || 'Working...'
  }

  if (compact) {
    return (
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        className={cn(
          'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm',
          'border',
          isActive && 'border-primary/30 bg-primary/5',
          isComplete && 'border-emerald-500/30 bg-emerald-500/5',
          isFailed && 'border-red-500/30 bg-red-500/5'
        )}
      >
        <span>{config.icon}</span>
        <span className={cn('font-medium', config.color)}>
          {task.agent.charAt(0).toUpperCase() + task.agent.slice(1)}
        </span>
        {getStatusIcon()}
      </motion.div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'agent-card-inline',
        isActive && 'border-primary/30',
        isComplete && 'border-emerald-500/30',
        isFailed && 'border-red-500/30'
      )}
    >
      <div className="flex items-start gap-3">
        {/* Agent icon */}
        <div className={cn(
          'w-10 h-10 rounded-xl flex items-center justify-center text-lg flex-shrink-0',
          config.bgColor
        )}>
          {config.icon}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn('font-semibold', config.color)}>
              {task.agent.charAt(0).toUpperCase() + task.agent.slice(1)}
            </span>
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full',
              isActive && 'bg-primary/20 text-primary',
              isComplete && 'bg-emerald-500/20 text-emerald-400',
              isFailed && 'bg-red-500/20 text-red-400'
            )}>
              {getStatusText()}
            </span>
          </div>

          {/* Progress bar */}
          {isActive && (
            <div className="mt-2">
              <div className="h-1.5 bg-muted rounded-full overflow-hidden">
                <motion.div
                  className="h-full bg-gradient-to-r from-primary to-primary/80 rounded-full"
                  initial={{ width: '0%' }}
                  animate={{ width: `${task.progress}%` }}
                  transition={{ duration: 0.3 }}
                />
              </div>
              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-muted-foreground">{task.progress}%</span>
                {task.goals && (
                  <span className="text-xs text-muted-foreground">
                    {task.goals.completed}/{task.goals.total} goals
                  </span>
                )}
              </div>
            </div>
          )}

          {/* Goals list (expandable) */}
          <AnimatePresence>
            {isActive && task.goals && task.goals.items.length > 0 && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="mt-3 space-y-1 overflow-hidden"
              >
                {task.goals.items.slice(0, 3).map((goal) => (
                  <div
                    key={goal.id}
                    className="flex items-center gap-2 text-xs"
                  >
                    {goal.status === 'completed' ? (
                      <CheckCircle className="w-3 h-3 text-emerald-500" />
                    ) : goal.status === 'in_progress' ? (
                      <ChevronRight className="w-3 h-3 text-primary animate-pulse" />
                    ) : (
                      <div className="w-3 h-3 rounded-full border border-muted-foreground/50" />
                    )}
                    <span className={cn(
                      goal.status === 'completed' && 'text-muted-foreground line-through',
                      goal.status === 'in_progress' && 'text-foreground font-medium'
                    )}>
                      {goal.description}
                    </span>
                  </div>
                ))}
                {task.goals.items.length > 3 && (
                  <span className="text-xs text-muted-foreground">
                    +{task.goals.items.length - 3} more
                  </span>
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Error message */}
          {task.error && (
            <div className="mt-2 text-xs text-red-400 flex items-start gap-1">
              <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
              <span>{task.error}</span>
            </div>
          )}
        </div>

        {/* Cancel button */}
        {isActive && onCancel && (
          <button
            onClick={() => onCancel(task.id)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            Cancel
          </button>
        )}
      </div>
    </motion.div>
  )
}
