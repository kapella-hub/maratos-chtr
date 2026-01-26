import { AutonomousTask, TaskStatus } from '../../stores/autonomous'

interface TaskCardProps {
  task: AutonomousTask
  onRetry?: (taskId: string) => void
}

const statusColors: Record<TaskStatus, string> = {
  pending: 'bg-gray-500',
  blocked: 'bg-yellow-600',
  ready: 'bg-blue-500',
  in_progress: 'bg-blue-600 animate-pulse',
  testing: 'bg-purple-500 animate-pulse',
  reviewing: 'bg-indigo-500 animate-pulse',
  fixing: 'bg-orange-500 animate-pulse',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  skipped: 'bg-gray-400',
}

const statusIcons: Record<TaskStatus, string> = {
  pending: '⏳',
  blocked: '🔒',
  ready: '▶️',
  in_progress: '🔄',
  testing: '🧪',
  reviewing: '👀',
  fixing: '🔧',
  completed: '✅',
  failed: '❌',
  skipped: '⏭️',
}

const agentIcons: Record<string, string> = {
  coder: '💻',
  tester: '🧪',
  reviewer: '👀',
  docs: '📝',
  devops: '🚀',
  architect: '🏗️',
}

export default function TaskCard({ task, onRetry }: TaskCardProps) {
  const statusColor = statusColors[task.status] || 'bg-gray-500'
  const statusIcon = statusIcons[task.status] || '❓'
  const agentIcon = agentIcons[task.agent_type] || '🤖'

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg p-4 hover:border-[#3a3a5a] transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${statusColor} text-white`}>
              {statusIcon} {task.status.replace('_', ' ')}
            </span>
            <span className="text-xs text-gray-500">
              {agentIcon} {task.agent_type}
            </span>
            {task.current_attempt > 0 && (
              <span className="text-xs text-gray-500">
                Attempt {task.current_attempt}/{task.max_attempts}
              </span>
            )}
          </div>

          <h3 className="font-medium text-gray-200 truncate">{task.title}</h3>

          <p className="text-sm text-gray-400 mt-1 line-clamp-2">
            {task.description}
          </p>

          {task.quality_gates.length > 0 && (
            <div className="flex gap-1 mt-2">
              {task.quality_gates.map((gate, i) => (
                <span
                  key={i}
                  className={`text-xs px-1.5 py-0.5 rounded ${
                    gate.passed
                      ? 'bg-green-500/20 text-green-400'
                      : gate.error
                      ? 'bg-red-500/20 text-red-400'
                      : 'bg-gray-500/20 text-gray-400'
                  }`}
                  title={gate.error || gate.type}
                >
                  {gate.type.replace('_', ' ')}
                </span>
              ))}
            </div>
          )}

          {task.target_files.length > 0 && (
            <div className="text-xs text-gray-500 mt-2">
              Files: {task.target_files.slice(0, 3).join(', ')}
              {task.target_files.length > 3 && ` +${task.target_files.length - 3} more`}
            </div>
          )}

          {task.error && (
            <div className="mt-2 p-2 bg-red-500/10 border border-red-500/20 rounded text-xs text-red-400">
              {task.error}
            </div>
          )}

          {task.final_commit_sha && (
            <div className="text-xs text-green-400 mt-2">
              Commit: {task.final_commit_sha}
            </div>
          )}
        </div>

        {task.status === 'failed' && onRetry && (
          <button
            onClick={() => onRetry(task.id)}
            className="px-2 py-1 text-xs bg-blue-600 hover:bg-blue-700 rounded transition-colors"
          >
            Retry
          </button>
        )}
      </div>

      {task.depends_on.length > 0 && (
        <div className="mt-3 pt-3 border-t border-[#2a2a4a]">
          <span className="text-xs text-gray-500">
            Depends on: {task.depends_on.join(', ')}
          </span>
        </div>
      )}
    </div>
  )
}
