import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  FolderKanban,
  CheckCircle,
  XCircle,
  Loader2,
  ChevronDown,
  ChevronRight,
  Play,
  Pause,
  X,
  GitBranch,
  ExternalLink,
  Edit2,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ProjectPlan, ProjectTask } from '@/stores/chat'

interface ProjectCardProps {
  plan: ProjectPlan
  status: 'awaiting_approval' | 'executing' | 'paused' | 'completed' | 'failed' | 'cancelled'
  onApprove?: () => void
  onCancel?: () => void
  onPause?: () => void
  onResume?: () => void
  onAdjust?: (message: string) => void
}

const taskStatusConfig: Record<ProjectTask['status'], { icon: React.ReactNode; color: string }> = {
  pending: { icon: <div className="w-3 h-3 rounded-full border-2 border-muted-foreground/40" />, color: 'text-muted-foreground' },
  blocked: { icon: <div className="w-3 h-3 rounded-full border-2 border-amber-500/40" />, color: 'text-amber-500' },
  ready: { icon: <div className="w-3 h-3 rounded-full border-2 border-primary/60" />, color: 'text-primary' },
  in_progress: { icon: <Loader2 className="w-3 h-3 animate-spin" />, color: 'text-primary' },
  testing: { icon: <Loader2 className="w-3 h-3 animate-spin" />, color: 'text-pink-400' },
  reviewing: { icon: <Loader2 className="w-3 h-3 animate-spin" />, color: 'text-amber-400' },
  fixing: { icon: <Loader2 className="w-3 h-3 animate-spin" />, color: 'text-orange-400' },
  completed: { icon: <CheckCircle className="w-3 h-3" />, color: 'text-emerald-500' },
  failed: { icon: <XCircle className="w-3 h-3" />, color: 'text-red-500' },
  skipped: { icon: <div className="w-3 h-3 rounded-full bg-muted-foreground/20" />, color: 'text-muted-foreground' },
}

export default function ProjectCard({
  plan,
  status,
  onApprove,
  onCancel,
  onPause,
  onResume,
  onAdjust,
}: ProjectCardProps) {
  const [expanded, setExpanded] = useState(true)
  const [showAdjustInput, setShowAdjustInput] = useState(false)
  const [adjustMessage, setAdjustMessage] = useState('')

  const completedTasks = plan.tasks.filter(t => t.status === 'completed').length
  const progress = plan.tasks.length > 0 ? Math.round((completedTasks / plan.tasks.length) * 100) : 0

  const isActive = status === 'executing'
  const isPaused = status === 'paused'
  const isComplete = status === 'completed'
  const isFailed = status === 'failed'
  const isWaiting = status === 'awaiting_approval'

  const handleAdjustSubmit = () => {
    if (adjustMessage.trim() && onAdjust) {
      onAdjust(adjustMessage.trim())
      setAdjustMessage('')
      setShowAdjustInput(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="project-card-inline"
    >
      {/* Header */}
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-indigo-500/20 flex items-center justify-center flex-shrink-0">
          <FolderKanban className="w-5 h-5 text-indigo-400" />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-semibold text-foreground truncate">{plan.name}</h3>
            <span className={cn(
              'text-xs px-2 py-0.5 rounded-full capitalize',
              isWaiting && 'bg-amber-500/20 text-amber-400',
              isActive && 'bg-emerald-500/20 text-emerald-400',
              isPaused && 'bg-blue-500/20 text-blue-400',
              isComplete && 'bg-emerald-500/20 text-emerald-400',
              isFailed && 'bg-red-500/20 text-red-400'
            )}>
              {status.replace('_', ' ')}
            </span>
          </div>

          {/* Progress bar */}
          <div className="mt-2">
            <div className="h-1.5 bg-muted/50 rounded-full overflow-hidden">
              <motion.div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500"
                initial={{ width: 0 }}
                animate={{ width: `${progress}%` }}
                transition={{ duration: 0.5 }}
              />
            </div>
            <div className="flex items-center justify-between mt-1 text-xs text-muted-foreground">
              <span>{completedTasks}/{plan.tasks.length} tasks</span>
              <span>{progress}%</span>
            </div>
          </div>

          {/* Git info */}
          {(plan.branch_name || plan.pr_url) && (
            <div className="flex items-center gap-3 mt-2 text-xs">
              {plan.branch_name && (
                <span className="flex items-center gap-1 text-muted-foreground">
                  <GitBranch className="w-3 h-3" />
                  {plan.branch_name}
                </span>
              )}
              {plan.pr_url && (
                <a
                  href={plan.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 text-primary hover:underline"
                >
                  <ExternalLink className="w-3 h-3" />
                  View PR
                </a>
              )}
            </div>
          )}
        </div>

        {/* Expand/collapse */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="p-1 text-muted-foreground hover:text-foreground transition-colors"
        >
          {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
        </button>
      </div>

      {/* Tasks list (expandable) */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="mt-4 space-y-2">
              {plan.tasks.map(task => {
                const config = taskStatusConfig[task.status]
                return (
                  <div
                    key={task.id}
                    className={cn(
                      'flex items-center gap-3 px-3 py-2 rounded-lg',
                      'bg-muted/20',
                      task.status === 'in_progress' && 'bg-primary/10 border border-primary/20'
                    )}
                  >
                    <span className={config.color}>{config.icon}</span>
                    <span className={cn(
                      'flex-1 text-sm',
                      task.status === 'completed' && 'text-muted-foreground line-through',
                      task.status === 'in_progress' && 'font-medium'
                    )}>
                      {task.title}
                    </span>
                    {task.progress !== undefined && task.status === 'in_progress' && (
                      <span className="text-xs text-muted-foreground">{task.progress}%</span>
                    )}
                  </div>
                )
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Actions */}
      {(isWaiting || isActive || isPaused) && (
        <div className="mt-4 pt-3 border-t border-border/30">
          {/* Awaiting approval actions */}
          {isWaiting && (
            <div className="space-y-3">
              {/* Adjust input */}
              {showAdjustInput ? (
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={adjustMessage}
                    onChange={e => setAdjustMessage(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAdjustSubmit()}
                    placeholder="What would you like to change?"
                    className="flex-1 px-3 py-2 text-sm bg-muted/50 border border-border/50 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary/50"
                    autoFocus
                  />
                  <button
                    onClick={handleAdjustSubmit}
                    disabled={!adjustMessage.trim()}
                    className="px-3 py-2 text-sm font-medium bg-muted hover:bg-muted/80 rounded-lg disabled:opacity-50 transition-colors"
                  >
                    Send
                  </button>
                  <button
                    onClick={() => setShowAdjustInput(false)}
                    className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <button
                    onClick={onApprove}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-lg transition-colors"
                  >
                    <Play className="w-4 h-4" />
                    Approve & Start
                  </button>
                  <button
                    onClick={() => setShowAdjustInput(true)}
                    className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium bg-muted hover:bg-muted/80 rounded-lg transition-colors"
                  >
                    <Edit2 className="w-4 h-4" />
                    Adjust
                  </button>
                  <button
                    onClick={onCancel}
                    className="flex items-center justify-center gap-2 px-4 py-2 text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-muted/80 rounded-lg transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          )}

          {/* Executing/Paused actions */}
          {(isActive || isPaused) && (
            <div className="flex items-center gap-2">
              {isActive && (
                <button
                  onClick={onPause}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-muted hover:bg-muted/80 rounded-lg transition-colors"
                >
                  <Pause className="w-4 h-4" />
                  Pause
                </button>
              )}
              {isPaused && (
                <button
                  onClick={onResume}
                  className="flex items-center gap-2 px-4 py-2 text-sm font-medium bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-lg transition-colors"
                >
                  <Play className="w-4 h-4" />
                  Resume
                </button>
              )}
              <button
                onClick={onCancel}
                className="flex items-center gap-2 px-4 py-2 text-sm font-medium text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
                Cancel
              </button>
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}
