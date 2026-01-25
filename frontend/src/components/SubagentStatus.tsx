import { cn } from '@/lib/utils'
import { Loader2 } from 'lucide-react'
import type { SubagentTask } from '@/stores/chat'

interface SubagentStatusProps {
  tasks: SubagentTask[]
  className?: string
}

const agentColors: Record<string, { bg: string; border: string; text: string }> = {
  architect: { bg: 'bg-blue-500/10', border: 'border-blue-500/50', text: 'text-blue-500' },
  reviewer: { bg: 'bg-amber-500/10', border: 'border-amber-500/50', text: 'text-amber-500' },
  coder: { bg: 'bg-emerald-500/10', border: 'border-emerald-500/50', text: 'text-emerald-500' },
  tester: { bg: 'bg-pink-500/10', border: 'border-pink-500/50', text: 'text-pink-500' },
  docs: { bg: 'bg-cyan-500/10', border: 'border-cyan-500/50', text: 'text-cyan-500' },
  devops: { bg: 'bg-orange-500/10', border: 'border-orange-500/50', text: 'text-orange-500' },
  mo: { bg: 'bg-violet-500/10', border: 'border-violet-500/50', text: 'text-violet-500' },
}

const agentIcons: Record<string, string> = {
  architect: '🏗️',
  reviewer: '🔍',
  coder: '💻',
  tester: '🧪',
  docs: '📝',
  devops: '🚀',
  mo: '🤖',
}

export default function SubagentStatus({ tasks, className }: SubagentStatusProps) {
  if (tasks.length === 0) return null

  const colors = (agent: string) => agentColors[agent] || { bg: 'bg-gray-500/10', border: 'border-gray-500/50', text: 'text-gray-500' }
  const barColor = (agent: string) => {
    const map: Record<string, string> = {
      architect: 'bg-blue-500',
      reviewer: 'bg-amber-500',
      coder: 'bg-emerald-500',
      tester: 'bg-pink-500',
      docs: 'bg-cyan-500',
      devops: 'bg-orange-500',
      mo: 'bg-violet-500',
    }
    return map[agent] || 'bg-gray-500'
  }

  return (
    <div className={cn('px-4 py-4 border-t border-border bg-gradient-to-r from-muted/50 to-muted/30', className)}>
      <div className="max-w-4xl mx-auto space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          <span>Running Subagents</span>
          <span className="px-2 py-0.5 rounded-full bg-primary/10 text-primary text-xs">
            {tasks.length} active
          </span>
        </div>
        
        <div className="grid gap-2">
          {tasks.map((task) => {
            const c = colors(task.agent)
            const isActive = task.status === 'running' || task.status === 'spawning'
            
            return (
              <div 
                key={task.id} 
                className={cn(
                  'flex items-center gap-3 px-3 py-2 rounded-lg border',
                  c.bg, c.border,
                  isActive && 'animate-pulse'
                )}
              >
                <span className="text-lg">{agentIcons[task.agent] || '🤖'}</span>
                
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={cn('font-semibold capitalize', c.text)}>
                      {task.agent}
                    </span>
                    <span className="text-xs text-muted-foreground">
                      {task.status === 'spawning' && '• Starting...'}
                      {task.status === 'running' && `• ${Math.round(task.progress * 100)}%`}
                      {task.status === 'completed' && '• ✓ Complete'}
                      {task.status === 'failed' && `• ✗ ${task.error || 'Failed'}`}
                    </span>
                  </div>
                  
                  {(task.status === 'running' || task.status === 'spawning') && (
                    <div className="mt-1.5 h-1.5 bg-black/10 rounded-full overflow-hidden">
                      <div 
                        className={cn('h-full rounded-full transition-all duration-500 ease-out', barColor(task.agent))}
                        style={{ width: `${Math.max(5, task.progress * 100)}%` }}
                      />
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
