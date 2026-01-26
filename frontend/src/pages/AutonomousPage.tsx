import { useState, useCallback } from 'react'
import { useAutonomousStore, AutonomousTask } from '../stores/autonomous'
import {
  streamAutonomousProject,
  pauseAutonomousProject,
  resumeAutonomousProject,
  cancelAutonomousProject,
  retryAutonomousTask,
  StartProjectRequest,
} from '../lib/api'
import AutonomousProgress from '../components/autonomous/AutonomousProgress'
import TaskCard from '../components/autonomous/TaskCard'
import EventLog from '../components/autonomous/EventLog'

export default function AutonomousPage() {
  const {
    currentProject,
    tasks,
    events,
    isStreaming,
    isPlanning,
    error,
    setCurrentProject,
    updateProject,
    updateTask,
    addTask,
    addEvent,
    clearEvents,
    setStreaming,
    setPlanning,
    setError,
    setAbortController,
    stopProject,
    reset,
  } = useAutonomousStore()

  const [showForm, setShowForm] = useState(!currentProject)
  const [formData, setFormData] = useState<StartProjectRequest>({
    name: '',
    prompt: '',
    auto_commit: true,
    push_to_remote: false,
    create_pr: false,
    pr_base_branch: 'main',
    max_runtime_hours: 8,
    max_total_iterations: 50,
    parallel_tasks: 3,
  })

  // Start a new project
  const startProject = useCallback(async () => {
    if (!formData.name || !formData.prompt) {
      setError('Please provide a name and prompt')
      return
    }

    reset()
    setStreaming(true)
    setPlanning(true)
    setShowForm(false)

    const controller = new AbortController()
    setAbortController(controller)

    try {
      for await (const event of streamAutonomousProject(formData, controller.signal)) {
        addEvent(event)

        // Update state based on event type
        switch (event.type) {
          case 'project_started':
            setCurrentProject({
              id: event.project_id,
              name: formData.name,
              original_prompt: formData.prompt,
              workspace_path: (event.data.workspace_path as string) || '',
              status: 'planning',
              progress: 0,
              tasks_completed: 0,
              tasks_failed: 0,
              tasks_pending: 0,
              total_iterations: 0,
              created_at: event.timestamp,
            })
            break

          case 'planning_completed':
            setPlanning(false)
            updateProject({ status: 'in_progress' })
            break

          case 'task_created':
            addTask(event.data.task as unknown as AutonomousTask)
            break

          case 'task_started':
            updateTask(event.data.task_id as string, {
              status: 'in_progress',
              started_at: event.timestamp,
            })
            break

          case 'task_progress':
            // Progress updates are handled in the event log
            break

          case 'quality_gate_passed':
          case 'quality_gate_failed':
            updateTask(event.data.task_id as string, {
              quality_gates: (event.data.quality_gates as unknown as AutonomousTask['quality_gates']) || [],
            })
            break

          case 'task_fixing':
            updateTask(event.data.task_id as string, {
              status: 'fixing',
            })
            break

          case 'task_completed':
            updateTask(event.data.task_id as string, {
              status: 'completed',
              completed_at: event.timestamp,
              final_commit_sha: event.data.commit_sha as string,
            })
            updateProject({
              tasks_completed: (currentProject?.tasks_completed || 0) + 1,
              tasks_pending: Math.max(0, (currentProject?.tasks_pending || 0) - 1),
              total_iterations: event.data.iterations as number,
            })
            break

          case 'task_failed':
            updateTask(event.data.task_id as string, {
              status: 'failed',
              error: event.data.reason as string,
              completed_at: event.timestamp,
            })
            updateProject({
              tasks_failed: (currentProject?.tasks_failed || 0) + 1,
              tasks_pending: Math.max(0, (currentProject?.tasks_pending || 0) - 1),
            })
            break

          case 'git_commit':
            // Handled in event log
            break

          case 'git_push':
            updateProject({ branch_name: event.data.branch as string })
            break

          case 'git_pr_created':
            updateProject({ pr_url: event.data.url as string })
            break

          case 'paused':
            updateProject({ status: 'paused' })
            break

          case 'resumed':
            updateProject({ status: 'in_progress' })
            break

          case 'project_completed':
            updateProject({
              status: 'completed',
              tasks_completed: event.data.tasks_completed as number,
              tasks_failed: event.data.tasks_failed as number,
              total_iterations: event.data.total_iterations as number,
              branch_name: event.data.branch as string,
              pr_url: event.data.pr_url as string,
            })
            break

          case 'project_failed':
            updateProject({
              status: 'failed',
              error: event.data.error as string,
            })
            break
        }
      }
    } catch (e) {
      if (e instanceof Error && e.name === 'AbortError') {
        // Cancelled
      } else {
        console.error('Stream error:', e)
        setError(e instanceof Error ? e.message : 'Unknown error')
      }
    } finally {
      setStreaming(false)
      setPlanning(false)
      setAbortController(null)
    }
  }, [
    formData,
    reset,
    setStreaming,
    setPlanning,
    setAbortController,
    addEvent,
    setCurrentProject,
    updateProject,
    addTask,
    updateTask,
    setError,
    currentProject,
  ])

  // Control actions
  const handlePause = useCallback(async () => {
    if (currentProject) {
      await pauseAutonomousProject(currentProject.id)
    }
  }, [currentProject])

  const handleResume = useCallback(async () => {
    if (currentProject) {
      await resumeAutonomousProject(currentProject.id)
    }
  }, [currentProject])

  const handleCancel = useCallback(async () => {
    if (currentProject) {
      await cancelAutonomousProject(currentProject.id)
      stopProject()
    }
  }, [currentProject, stopProject])

  const handleRetryTask = useCallback(async (taskId: string) => {
    if (currentProject) {
      await retryAutonomousTask(currentProject.id, taskId)
      updateTask(taskId, { status: 'ready', error: undefined })
    }
  }, [currentProject, updateTask])

  const handleNewProject = useCallback(() => {
    reset()
    clearEvents()
    setShowForm(true)
  }, [reset, clearEvents])

  // Group tasks by status
  const tasksByStatus = tasks.reduce((acc, task) => {
    const status = task.status
    if (!acc[status]) acc[status] = []
    acc[status].push(task)
    return acc
  }, {} as Record<string, AutonomousTask[]>)

  return (
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="shrink-0 border-b border-[#2a2a4a] px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-100">Autonomous Development</h1>
            <p className="text-sm text-gray-400 mt-1">
              AI-powered team that builds, tests, documents, and deploys
            </p>
          </div>
          {currentProject && (
            <button
              onClick={handleNewProject}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
            >
              New Project
            </button>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-hidden">
        {showForm ? (
          /* Project form */
          <div className="h-full overflow-y-auto p-6">
            <div className="max-w-2xl mx-auto space-y-6">
              <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg p-6">
                <h2 className="text-lg font-semibold mb-4">Start New Project</h2>

                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-400 mb-1">
                      Project Name
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      className="w-full px-4 py-2 bg-[#0a0a1a] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500"
                      placeholder="e.g., Todo API Backend"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-400 mb-1">
                      What should the team build?
                    </label>
                    <textarea
                      value={formData.prompt}
                      onChange={(e) => setFormData({ ...formData, prompt: e.target.value })}
                      className="w-full px-4 py-2 bg-[#0a0a1a] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500 min-h-[150px]"
                      placeholder="Describe what you want to build. Be specific about features, technologies, and requirements..."
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-400 mb-1">
                        Workspace Path (optional)
                      </label>
                      <input
                        type="text"
                        value={formData.workspace_path || ''}
                        onChange={(e) => setFormData({ ...formData, workspace_path: e.target.value || undefined })}
                        className="w-full px-4 py-2 bg-[#0a0a1a] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500"
                        placeholder="~/maratos-workspace/project"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-400 mb-1">
                        Max Runtime (hours)
                      </label>
                      <input
                        type="number"
                        value={formData.max_runtime_hours}
                        onChange={(e) => setFormData({ ...formData, max_runtime_hours: Number(e.target.value) })}
                        className="w-full px-4 py-2 bg-[#0a0a1a] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500"
                        min={1}
                        max={24}
                      />
                    </div>
                  </div>

                  <div className="flex flex-wrap gap-4">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.auto_commit}
                        onChange={(e) => setFormData({ ...formData, auto_commit: e.target.checked })}
                        className="w-4 h-4 rounded border-[#2a2a4a] bg-[#0a0a1a] text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-300">Auto-commit changes</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.push_to_remote}
                        onChange={(e) => setFormData({ ...formData, push_to_remote: e.target.checked })}
                        className="w-4 h-4 rounded border-[#2a2a4a] bg-[#0a0a1a] text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-300">Push to remote</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={formData.create_pr}
                        onChange={(e) => setFormData({ ...formData, create_pr: e.target.checked })}
                        className="w-4 h-4 rounded border-[#2a2a4a] bg-[#0a0a1a] text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-300">Create PR</span>
                    </label>
                  </div>

                  {formData.create_pr && (
                    <div>
                      <label className="block text-sm font-medium text-gray-400 mb-1">
                        PR Base Branch
                      </label>
                      <input
                        type="text"
                        value={formData.pr_base_branch}
                        onChange={(e) => setFormData({ ...formData, pr_base_branch: e.target.value })}
                        className="w-full px-4 py-2 bg-[#0a0a1a] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500"
                      />
                    </div>
                  )}

                  <button
                    onClick={startProject}
                    disabled={!formData.name || !formData.prompt || isStreaming}
                    className="w-full py-3 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg font-medium transition-colors"
                  >
                    {isStreaming ? 'Starting...' : 'Start Autonomous Development'}
                  </button>
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400">
                  {error}
                </div>
              )}
            </div>
          </div>
        ) : (
          /* Project view */
          <div className="h-full flex">
            {/* Left panel - Progress and tasks */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {currentProject && (
                <AutonomousProgress
                  project={currentProject}
                  onPause={isStreaming ? handlePause : undefined}
                  onResume={currentProject.status === 'paused' ? handleResume : undefined}
                  onCancel={(isStreaming || currentProject.status === 'paused') ? handleCancel : undefined}
                />
              )}

              {/* Planning indicator */}
              {isPlanning && (
                <div className="flex items-center gap-3 p-4 bg-yellow-500/10 border border-yellow-500/20 rounded-lg">
                  <div className="animate-spin w-5 h-5 border-2 border-yellow-500 border-t-transparent rounded-full" />
                  <span className="text-yellow-400">Architect is planning tasks...</span>
                </div>
              )}

              {/* Tasks */}
              <div className="space-y-4">
                {/* Active tasks */}
                {['in_progress', 'testing', 'reviewing', 'fixing'].some(s => tasksByStatus[s]?.length > 0) && (
                  <div>
                    <h3 className="text-lg font-medium text-gray-200 mb-3">Active Tasks</h3>
                    <div className="space-y-3">
                      {['in_progress', 'testing', 'reviewing', 'fixing'].flatMap(status =>
                        (tasksByStatus[status] || []).map(task => (
                          <TaskCard key={task.id} task={task} />
                        ))
                      )}
                    </div>
                  </div>
                )}

                {/* Ready tasks */}
                {tasksByStatus['ready']?.length > 0 && (
                  <div>
                    <h3 className="text-lg font-medium text-gray-200 mb-3">Ready to Start</h3>
                    <div className="space-y-3">
                      {tasksByStatus['ready'].map(task => (
                        <TaskCard key={task.id} task={task} />
                      ))}
                    </div>
                  </div>
                )}

                {/* Pending/blocked tasks */}
                {(tasksByStatus['pending']?.length > 0 || tasksByStatus['blocked']?.length > 0) && (
                  <div>
                    <h3 className="text-lg font-medium text-gray-200 mb-3">Waiting</h3>
                    <div className="space-y-3">
                      {[...(tasksByStatus['blocked'] || []), ...(tasksByStatus['pending'] || [])].map(task => (
                        <TaskCard key={task.id} task={task} />
                      ))}
                    </div>
                  </div>
                )}

                {/* Completed tasks */}
                {tasksByStatus['completed']?.length > 0 && (
                  <details>
                    <summary className="text-lg font-medium text-gray-200 mb-3 cursor-pointer">
                      Completed ({tasksByStatus['completed'].length})
                    </summary>
                    <div className="space-y-3 mt-3">
                      {tasksByStatus['completed'].map(task => (
                        <TaskCard key={task.id} task={task} />
                      ))}
                    </div>
                  </details>
                )}

                {/* Failed tasks */}
                {tasksByStatus['failed']?.length > 0 && (
                  <div>
                    <h3 className="text-lg font-medium text-red-400 mb-3">Failed</h3>
                    <div className="space-y-3">
                      {tasksByStatus['failed'].map(task => (
                        <TaskCard key={task.id} task={task} onRetry={handleRetryTask} />
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Right panel - Event log */}
            <div className="w-96 shrink-0 border-l border-[#2a2a4a] p-4">
              <EventLog events={events} maxHeight="calc(100vh - 200px)" />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
