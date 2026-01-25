import { cn } from '@/lib/utils'
import type { SubagentTask } from '@/stores/chat'

interface SubagentStatusProps {
  tasks: SubagentTask[]
  className?: string
}

const agentColors: Record<string, string> = {
  architect: 'bg-blue-500',
  reviewer: 'bg-amber-500',
  coder: 'bg-emerald-500',
  tester: 'bg-pink-500',
  docs: 'bg-cyan-500',
  devops: 'bg-orange-500',
  mo: 'bg-violet-500',
}

const agentLabels: Record<string, string> = {
  architect: '🏗️ Architect',
  reviewer: '🔍 Reviewer',
  coder: '💻 Coder',
  tester: '🧪 Tester',
  docs: '📝 Docs',
  devops: '🚀 DevOps',
  mo: '🤖 MO',
}

export default function SubagentStatus({ tasks, className }: SubagentStatusProps) {
  if (tasks.length === 0) return null

  return (
    <div className={cn('px-4 py-3 border-t border-border bg-muted/30', className)}>
      <div className="max-w-4xl mx-auto space-y-2">
        <div className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
          Running Subagents
        </div>
        {tasks.map((task) => (
          <div key={task.id} className="flex items-center gap-3 text-sm">
            <div className={cn('w-2 h-2 rounded-full', agentColors[task.agent] || 'bg-gray-500', {
              'animate-pulse': task.status === 'running' || task.status === 'spawning',
            })} />
            <span className="font-medium">{agentLabels[task.agent] || task.agent}</span>
            <span className="text-muted-foreground">
              {task.status === 'spawning' && 'Starting...'}
              {task.status === 'running' && `${Math.round(task.progress * 100)}%`}
              {task.status === 'completed' && '✓ Done'}
              {task.status === 'failed' && `✗ ${task.error || 'Failed'}`}
            </span>
            {task.status === 'running' && (
              <div className="flex-1 max-w-32 h-1.5 bg-muted rounded-full overflow-hidden">
                <div 
                  className={cn('h-full rounded-full transition-all duration-300', agentColors[task.agent] || 'bg-gray-500')}
                  style={{ width: `${task.progress * 100}%` }}
                />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
