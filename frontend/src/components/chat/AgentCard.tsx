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
  mo: { icon: '/assets/maratos_logo.png', color: 'text-violet-400', bgColor: 'bg-black/20' },
}

export default function AgentCard({ task, onCancel, compact = false }: AgentCardProps) {
  const agentName = task.agent ? task.agent.toLowerCase() : 'mo'
  const config = agentConfig[agentName] || agentConfig.mo
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
          {agentName.charAt(0).toUpperCase() + agentName.slice(1)}
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
        'group relative overflow-hidden rounded-xl border p-4 transition-all duration-300',
        'hover:shadow-lg',
        isActive ? 'border-primary/50 shadow-md bg-gradient-to-br from-background to-primary/5' : 'bg-background/50',
        isComplete && 'border-emerald-500/50 bg-gradient-to-br from-background to-emerald-500/5',
        isFailed && 'border-red-500/50 bg-gradient-to-br from-background to-red-500/5'
      )}
    >
      <div className="flex items-start gap-4">
        {/* Agent Icon with Pulse Effect */}
        <div className="relative">
          <div className={cn(
            'w-12 h-12 rounded-2xl flex items-center justify-center text-2xl shadow-sm transition-transform group-hover:scale-105',
            config.bgColor,
            isActive && 'ring-2 ring-primary/20 ring-offset-2 ring-offset-background'
          )}>
            {config.icon.startsWith('/') ? (
              <img src={config.icon} alt={task.agent} className="w-full h-full object-cover" />
            ) : (
              config.icon
            )}
          </div>
          {isActive && (
            <span className="absolute -bottom-1 -right-1 flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-primary opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-primary"></span>
            </span>
          )}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={cn('text-base font-bold tracking-tight', config.color)}>
                {agentName.charAt(0).toUpperCase() + agentName.slice(1)}
              </span>
              <span className={cn(
                'text-[10px] uppercase tracking-wider font-semibold px-2 py-0.5 rounded-full border',
                isActive && 'border-primary/30 bg-primary/10 text-primary',
                isComplete && 'border-emerald-500/30 bg-emerald-500/10 text-emerald-500',
                isFailed && 'border-red-500/30 bg-red-500/10 text-red-500'
              )}>
                {getStatusText()}
              </span>
            </div>

            {/* Cancel Button */}
            {isActive && onCancel && (
              <button
                onClick={() => onCancel(task.id)}
                className="text-xs font-medium text-muted-foreground hover:text-red-400 transition-colors opacity-0 group-hover:opacity-100"
              >
                Cancel
              </button>
            )}
          </div>

          {/* Progress Bar with Shimmer */}
          {isActive && (
            <div className="space-y-1.5">
              <div className="h-2 bg-muted/50 rounded-full overflow-hidden backdrop-blur-sm relative">
                <motion.div
                  className="h-full bg-gradient-to-r from-primary to-violet-500 rounded-full relative"
                  initial={{ width: '0%' }}
                  animate={{ width: `${task.progress}%` }}
                  transition={{ duration: 0.5, ease: "easeOut" }}
                >
                  <motion.div
                    className="absolute inset-0 bg-white/30"
                    initial={{ x: '-100%' }}
                    animate={{ x: '100%' }}
                    transition={{ repeat: Infinity, duration: 1.5, ease: "linear" }}
                  />
                </motion.div>
              </div>
              <div className="flex justify-between text-xs text-muted-foreground font-medium">
                <span>{task.currentAction || 'Processing...'}</span>
                <span>{Math.round(task.progress)}%</span>
              </div>
            </div>
          )}

          {/* Expanded Goals - Simplified Animation */}
          {isActive && task.goals && task.goals.items.length > 0 && (
            <div className="pt-2">
              <div className="space-y-1.5 bg-muted/30 rounded-lg p-2 border border-border/50">
                {task.goals.items.slice(0, 3).map((goal) => (
                  <div key={goal.id} className="flex items-center gap-2.5">
                    {goal.status === 'completed' ? (
                      <div className="h-4 w-4 rounded-full bg-emerald-500/20 flex items-center justify-center text-emerald-500 ring-1 ring-emerald-500/30">
                        <CheckCircle className="w-2.5 h-2.5" />
                      </div>
                    ) : goal.status === 'in_progress' ? (
                      <div className="h-4 w-4 rounded-full bg-primary/20 flex items-center justify-center text-primary ring-1 ring-primary/30">
                        <Loader2 className="w-2.5 h-2.5 animate-spin" />
                      </div>
                    ) : (
                      <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30 ml-1.5" />
                    )}
                    <span className={cn(
                      'text-xs font-medium transition-colors',
                      goal.status === 'completed' && 'text-muted-foreground line-through decoration-emerald-500/30',
                      goal.status === 'in_progress' && 'text-foreground',
                      goal.status === 'pending' && 'text-muted-foreground'
                    )}>
                      {goal.description}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Error Message */}
          {task.error && (
            <div className="mt-2 p-3 rounded-lg bg-red-500/10 border border-red-500/20 flex items-start gap-2 text-sm text-red-400">
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <span className="font-medium">{task.error}</span>
            </div>
          )}
        </div>
      </div>
    </motion.div>
  )
}
