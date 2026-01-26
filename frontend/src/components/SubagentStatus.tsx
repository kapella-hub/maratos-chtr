import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Loader2, Check, Circle, AlertCircle, ChevronRight, Zap, X, ChevronDown, ChevronUp, Terminal } from 'lucide-react'
import { cancelSubagentTask } from '@/lib/api'
import type { SubagentTask } from '@/stores/chat'

interface SubagentStatusProps {
  tasks: SubagentTask[]
  className?: string
  onCancel?: (taskId: string) => void
}

const agentConfig: Record<string, {
  icon: string
  gradient: string
  bgGradient: string
  border: string
  text: string
  shadow: string
}> = {
  architect: {
    icon: '🏗️',
    gradient: 'from-blue-500 to-cyan-500',
    bgGradient: 'from-blue-500/10 to-cyan-500/10',
    border: 'border-blue-500/30',
    text: 'text-blue-400',
    shadow: 'shadow-blue-500/20',
  },
  reviewer: {
    icon: '🔍',
    gradient: 'from-amber-500 to-orange-500',
    bgGradient: 'from-amber-500/10 to-orange-500/10',
    border: 'border-amber-500/30',
    text: 'text-amber-400',
    shadow: 'shadow-amber-500/20',
  },
  coder: {
    icon: '💻',
    gradient: 'from-emerald-500 to-green-500',
    bgGradient: 'from-emerald-500/10 to-green-500/10',
    border: 'border-emerald-500/30',
    text: 'text-emerald-400',
    shadow: 'shadow-emerald-500/20',
  },
  tester: {
    icon: '🧪',
    gradient: 'from-pink-500 to-rose-500',
    bgGradient: 'from-pink-500/10 to-rose-500/10',
    border: 'border-pink-500/30',
    text: 'text-pink-400',
    shadow: 'shadow-pink-500/20',
  },
  docs: {
    icon: '📝',
    gradient: 'from-cyan-500 to-sky-500',
    bgGradient: 'from-cyan-500/10 to-sky-500/10',
    border: 'border-cyan-500/30',
    text: 'text-cyan-400',
    shadow: 'shadow-cyan-500/20',
  },
  devops: {
    icon: '🚀',
    gradient: 'from-orange-500 to-red-500',
    bgGradient: 'from-orange-500/10 to-red-500/10',
    border: 'border-orange-500/30',
    text: 'text-orange-400',
    shadow: 'shadow-orange-500/20',
  },
  mo: {
    icon: '🤖',
    gradient: 'from-violet-500 to-purple-500',
    bgGradient: 'from-violet-500/10 to-purple-500/10',
    border: 'border-violet-500/30',
    text: 'text-violet-400',
    shadow: 'shadow-violet-500/20',
  },
}

const defaultConfig = agentConfig.mo

export default function SubagentStatus({ tasks, className, onCancel }: SubagentStatusProps) {
  const [expandedLogs, setExpandedLogs] = useState<Set<string>>(new Set())

  if (tasks.length === 0) return null

  const activeTasks = tasks.filter(t => t.status === 'running' || t.status === 'spawning' || t.status === 'retrying')

  const toggleLogs = (taskId: string) => {
    setExpandedLogs(prev => {
      const next = new Set(prev)
      if (next.has(taskId)) {
        next.delete(taskId)
      } else {
        next.add(taskId)
      }
      return next
    })
  }

  const handleCancel = async (taskId: string) => {
    try {
      await cancelSubagentTask(taskId)
      onCancel?.(taskId)
    } catch (error) {
      console.error('Failed to cancel task:', error)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 20 }}
      className={cn(
        'px-4 py-4 border-t border-border/30',
        'bg-gradient-to-r from-muted/50 via-background to-muted/50',
        className
      )}
    >
      <div className="max-w-4xl mx-auto space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
              className="text-primary"
            >
              <Zap className="w-5 h-5" />
            </motion.div>
            <span className="font-semibold text-foreground">Active Agents</span>
            <span className="badge badge-primary">
              {activeTasks.length} running
            </span>
          </div>
        </div>

        {/* Tasks Grid */}
        <div className="grid gap-3">
          <AnimatePresence mode="popLayout">
            {tasks.map((task, index) => {
              const config = agentConfig[task.agent] || defaultConfig
              const isActive = task.status === 'running' || task.status === 'spawning' || task.status === 'retrying'
              const currentGoal = task.goals?.items?.find(g => g.id === task.goals?.current_id)
              const showLogs = expandedLogs.has(task.id)

              return (
                <motion.div
                  key={task.id}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: 20 }}
                  transition={{ delay: index * 0.05 }}
                  className={cn(
                    'rounded-2xl border overflow-hidden',
                    'bg-gradient-to-r',
                    config.bgGradient,
                    config.border,
                    isActive && 'shadow-lg',
                    isActive && config.shadow
                  )}
                >
                  {/* Main Content */}
                  <div className="p-4">
                    <div className="flex items-center gap-4">
                      {/* Agent Icon */}
                      <motion.div
                        className={cn(
                          'w-12 h-12 rounded-xl flex items-center justify-center',
                          'bg-gradient-to-br shadow-lg',
                          config.gradient,
                          config.shadow
                        )}
                        animate={isActive ? { scale: [1, 1.05, 1] } : {}}
                        transition={{ duration: 2, repeat: Infinity }}
                      >
                        <span className="text-2xl">{config.icon}</span>
                      </motion.div>

                      {/* Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <span className={cn('font-semibold capitalize', config.text)}>
                            {task.agent}
                          </span>
                          <StatusBadge status={task.status} error={task.error} attempt={task.attempt} maxAttempts={task.maxAttempts} />
                          {task.isFallback && (
                            <span className="badge bg-purple-500/20 text-purple-400 text-xs">
                              Fallback
                            </span>
                          )}
                          {task.goals && task.goals.total > 0 && (
                            <span className="text-xs text-muted-foreground ml-auto">
                              {task.goals.completed}/{task.goals.total} goals
                            </span>
                          )}
                        </div>

                        {/* Progress Bar */}
                        {isActive && (
                          <div className="h-2 bg-black/10 rounded-full overflow-hidden">
                            <motion.div
                              className={cn('h-full rounded-full bg-gradient-to-r', config.gradient)}
                              initial={{ width: 0 }}
                              animate={{ width: `${Math.max(5, task.progress * 100)}%` }}
                              transition={{ duration: 0.5, ease: 'easeOut' }}
                            />
                          </div>
                        )}

                        {/* Current Goal */}
                        {currentGoal && isActive && (
                          <motion.div
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            className="flex items-center gap-2 mt-2 text-xs text-muted-foreground"
                          >
                            <ChevronRight className="w-3 h-3" />
                            <span className="truncate">{currentGoal.description}</span>
                          </motion.div>
                        )}
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2">
                        {/* Logs toggle */}
                        <button
                          onClick={() => toggleLogs(task.id)}
                          className={cn(
                            'p-2 rounded-lg transition-colors',
                            showLogs ? 'bg-primary/20 text-primary' : 'hover:bg-muted text-muted-foreground'
                          )}
                          title="Show logs"
                        >
                          <Terminal className="w-4 h-4" />
                          {showLogs ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                        </button>

                        {/* Cancel button */}
                        {isActive && (
                          <button
                            onClick={() => handleCancel(task.id)}
                            className="p-2 rounded-lg hover:bg-red-500/20 text-muted-foreground hover:text-red-400 transition-colors"
                            title="Cancel task"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Goals List (Expandable) */}
                  {task.goals && task.goals.items && task.goals.items.length > 0 && isActive && (
                    <div className="px-4 pb-4">
                      <div className="ml-16 space-y-1.5">
                        {task.goals.items.slice(0, 5).map((goal) => (
                          <motion.div
                            key={goal.id}
                            initial={{ opacity: 0, x: -10 }}
                            animate={{ opacity: 1, x: 0 }}
                            className={cn(
                              'flex items-center gap-2 text-xs py-1 px-2 rounded-lg',
                              goal.status === 'completed' && 'text-emerald-400 bg-emerald-500/10',
                              goal.status === 'in_progress' && 'text-foreground bg-primary/10 font-medium',
                              goal.status === 'pending' && 'text-muted-foreground',
                              goal.status === 'failed' && 'text-red-400 bg-red-500/10'
                            )}
                          >
                            <GoalIcon status={goal.status} />
                            <span className="truncate">{goal.description}</span>
                          </motion.div>
                        ))}
                        {task.goals.items.length > 5 && (
                          <div className="text-xs text-muted-foreground pl-2">
                            +{task.goals.items.length - 5} more goals
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Checkpoints */}
                  {task.checkpoints && task.checkpoints.length > 0 && isActive && (
                    <div className="px-4 pb-4">
                      <div className="ml-16 flex flex-wrap gap-1.5">
                        {task.checkpoints.map((cp, idx) => (
                          <motion.span
                            key={idx}
                            initial={{ scale: 0 }}
                            animate={{ scale: 1 }}
                            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-emerald-500/20 text-emerald-400 rounded-full"
                            title={cp.description}
                          >
                            <Check className="w-3 h-3" />
                            {cp.name}
                          </motion.span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Logs Section (Expandable) */}
                  <AnimatePresence>
                    {showLogs && task.logs && task.logs.length > 0 && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="border-t border-border/30 overflow-hidden"
                      >
                        <div className="px-4 py-3 bg-black/20">
                          <div className="flex items-center gap-2 text-xs text-muted-foreground mb-2">
                            <Terminal className="w-3 h-3" />
                            <span>Agent Logs ({task.logs.length})</span>
                          </div>
                          <div className="font-mono text-[10px] space-y-0.5 max-h-32 overflow-y-auto">
                            {task.logs.slice(-10).map((log, idx) => (
                              <div key={idx} className="text-muted-foreground/80">
                                {log}
                              </div>
                            ))}
                          </div>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              )
            })}
          </AnimatePresence>
        </div>
      </div>
    </motion.div>
  )
}

function StatusBadge({ status, error, attempt, maxAttempts }: { status: string; error?: string; attempt?: number; maxAttempts?: number }) {
  const showAttempt = attempt && maxAttempts && attempt > 1

  switch (status) {
    case 'spawning':
      return (
        <span className="badge bg-violet-500/20 text-violet-400">
          <Loader2 className="w-3 h-3 mr-1 animate-spin" />
          Starting
        </span>
      )
    case 'running':
      return (
        <span className="badge bg-blue-500/20 text-blue-400">
          <motion.span
            className="w-2 h-2 rounded-full bg-blue-400 mr-1"
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 1, repeat: Infinity }}
          />
          Running
          {showAttempt && <span className="ml-1 opacity-70">({attempt}/{maxAttempts})</span>}
        </span>
      )
    case 'retrying':
      return (
        <span className="badge bg-amber-500/20 text-amber-400">
          <motion.div
            animate={{ rotate: 360 }}
            transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
          >
            <Loader2 className="w-3 h-3 mr-1" />
          </motion.div>
          Retrying
          {showAttempt && <span className="ml-1 opacity-70">({attempt}/{maxAttempts})</span>}
        </span>
      )
    case 'completed':
      return (
        <span className="badge bg-emerald-500/20 text-emerald-400">
          <Check className="w-3 h-3 mr-1" />
          Complete
        </span>
      )
    case 'failed':
      return (
        <span className="badge bg-red-500/20 text-red-400" title={error}>
          <AlertCircle className="w-3 h-3 mr-1" />
          Failed
          {showAttempt && <span className="ml-1 opacity-70">(after {attempt} attempts)</span>}
        </span>
      )
    case 'timed_out':
      return (
        <span className="badge bg-orange-500/20 text-orange-400" title={error}>
          <AlertCircle className="w-3 h-3 mr-1" />
          Timed Out
        </span>
      )
    default:
      return null
  }
}

function GoalIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <Check className="w-3 h-3 flex-shrink-0" />
    case 'in_progress':
      return (
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
        >
          <Loader2 className="w-3 h-3 flex-shrink-0" />
        </motion.div>
      )
    case 'pending':
      return <Circle className="w-3 h-3 flex-shrink-0" />
    case 'failed':
      return <AlertCircle className="w-3 h-3 flex-shrink-0" />
    default:
      return <Circle className="w-3 h-3 flex-shrink-0" />
  }
}
