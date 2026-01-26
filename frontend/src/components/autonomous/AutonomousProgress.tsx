import { AutonomousProject, ProjectStatus } from '../../stores/autonomous'

interface AutonomousProgressProps {
  project: AutonomousProject
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
}

const statusColors: Record<ProjectStatus, string> = {
  planning: 'bg-yellow-500',
  in_progress: 'bg-blue-500',
  blocked: 'bg-orange-500',
  paused: 'bg-gray-500',
  completed: 'bg-green-500',
  failed: 'bg-red-500',
  cancelled: 'bg-gray-400',
}

const statusText: Record<ProjectStatus, string> = {
  planning: 'Planning...',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  paused: 'Paused',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
}

export default function AutonomousProgress({
  project,
  onPause,
  onResume,
  onCancel,
}: AutonomousProgressProps) {
  const progressPercent = Math.round(project.progress * 100)
  const isActive = ['planning', 'in_progress', 'blocked'].includes(project.status)
  const isPaused = project.status === 'paused'

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">{project.name}</h2>
          <p className="text-sm text-gray-400 mt-1">
            {project.workspace_path}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span
            className={`px-3 py-1 rounded-full text-sm font-medium ${statusColors[project.status]} text-white`}
          >
            {statusText[project.status]}
          </span>

          {(isActive || isPaused) && (
            <div className="flex gap-1">
              {isPaused && onResume && (
                <button
                  onClick={onResume}
                  className="p-2 rounded bg-green-600 hover:bg-green-700 transition-colors"
                  title="Resume"
                >
                  ▶️
                </button>
              )}
              {isActive && onPause && (
                <button
                  onClick={onPause}
                  className="p-2 rounded bg-yellow-600 hover:bg-yellow-700 transition-colors"
                  title="Pause"
                >
                  ⏸️
                </button>
              )}
              {(isActive || isPaused) && onCancel && (
                <button
                  onClick={onCancel}
                  className="p-2 rounded bg-red-600 hover:bg-red-700 transition-colors"
                  title="Cancel"
                >
                  ⏹️
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Progress bar */}
      <div className="mb-4">
        <div className="flex justify-between text-sm text-gray-400 mb-1">
          <span>Progress</span>
          <span>{progressPercent}%</span>
        </div>
        <div className="h-3 bg-[#0a0a1a] rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              project.status === 'completed'
                ? 'bg-green-500'
                : project.status === 'failed'
                ? 'bg-red-500'
                : 'bg-blue-500'
            } ${isActive ? 'animate-pulse' : ''}`}
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-4 gap-4 text-center">
        <div className="bg-[#0a0a1a] rounded-lg p-3">
          <div className="text-2xl font-bold text-green-400">
            {project.tasks_completed}
          </div>
          <div className="text-xs text-gray-500">Completed</div>
        </div>
        <div className="bg-[#0a0a1a] rounded-lg p-3">
          <div className="text-2xl font-bold text-red-400">
            {project.tasks_failed}
          </div>
          <div className="text-xs text-gray-500">Failed</div>
        </div>
        <div className="bg-[#0a0a1a] rounded-lg p-3">
          <div className="text-2xl font-bold text-blue-400">
            {project.tasks_pending}
          </div>
          <div className="text-xs text-gray-500">Pending</div>
        </div>
        <div className="bg-[#0a0a1a] rounded-lg p-3">
          <div className="text-2xl font-bold text-purple-400">
            {project.total_iterations}
          </div>
          <div className="text-xs text-gray-500">Iterations</div>
        </div>
      </div>

      {/* Git info */}
      {(project.branch_name || project.pr_url) && (
        <div className="mt-4 pt-4 border-t border-[#2a2a4a]">
          <div className="flex items-center gap-4 text-sm">
            {project.branch_name && (
              <span className="text-gray-400">
                🌿 Branch: <code className="text-green-400">{project.branch_name}</code>
              </span>
            )}
            {project.pr_url && (
              <a
                href={project.pr_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300"
              >
                🔗 View PR
              </a>
            )}
          </div>
        </div>
      )}

      {/* Error */}
      {project.error && (
        <div className="mt-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
          <div className="text-sm text-red-400">{project.error}</div>
        </div>
      )}

      {/* Original prompt (collapsed) */}
      <details className="mt-4">
        <summary className="text-sm text-gray-500 cursor-pointer hover:text-gray-400">
          Original prompt
        </summary>
        <div className="mt-2 p-3 bg-[#0a0a1a] rounded text-sm text-gray-400 whitespace-pre-wrap">
          {project.original_prompt}
        </div>
      </details>
    </div>
  )
}
