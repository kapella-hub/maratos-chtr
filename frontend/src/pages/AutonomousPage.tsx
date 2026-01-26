import { useState, useCallback, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAutonomousStore, AutonomousTask } from '../stores/autonomous'
import {
  streamAutonomousProject,
  pauseAutonomousProject,
  resumeAutonomousProject,
  cancelAutonomousProject,
  retryAutonomousTask,
  fetchConfig,
  createGitLabProject,
  StartProjectRequest,
} from '../lib/api'
import AutonomousProgress from '../components/autonomous/AutonomousProgress'
import TaskCard from '../components/autonomous/TaskCard'
import EventLog from '../components/autonomous/EventLog'
import { Settings, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { Link } from 'react-router-dom'

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
    git_mode: 'existing',
    git_remote_url: '',
    git_init_repo: true,
  })
  const [gitlabCreateStatus, setGitlabCreateStatus] = useState<{
    status: 'idle' | 'creating' | 'success' | 'error'
    message?: string
    project?: { ssh_url_to_repo: string; web_url: string }
  }>({ status: 'idle' })

  // Fetch config to get git defaults
  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  // Update form defaults when config loads
  useEffect(() => {
    if (config) {
      setFormData((prev) => ({
        ...prev,
        auto_commit: config.git_auto_commit ?? prev.auto_commit,
        push_to_remote: config.git_push_to_remote ?? prev.push_to_remote,
        create_pr: config.git_create_pr ?? prev.create_pr,
        pr_base_branch: config.git_default_branch || prev.pr_base_branch,
      }))
    }
  }, [config])

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
    // Always stop the stream first to immediately stop receiving data
    stopProject()

    // Then try to cancel on the backend (may fail if project not in memory)
    if (currentProject) {
      try {
        await cancelAutonomousProject(currentProject.id)
      } catch (e) {
        console.warn('Failed to cancel project on backend:', e)
        // Stream already stopped, so this is ok
      }
      // Update local status
      updateProject({ status: 'cancelled' })
    }
  }, [currentProject, stopProject, updateProject])

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
            <div className="flex items-center gap-3">
              {/* Stop button - prominent when project is running */}
              {(isStreaming || currentProject.status === 'in_progress' || currentProject.status === 'planning' || currentProject.status === 'paused') && (
                <button
                  onClick={handleCancel}
                  className="flex items-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg transition-colors font-medium"
                >
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                    <rect x="4" y="4" width="12" height="12" rx="1" />
                  </svg>
                  Stop
                </button>
              )}
              <button
                onClick={handleNewProject}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
              >
                New Project
              </button>
            </div>
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

                  {/* Git Integration Section */}
                  <div className="p-4 rounded-lg bg-[#0a0a1a] border border-[#2a2a4a]">
                    <div className="flex items-center justify-between mb-4">
                      <h3 className="text-sm font-medium text-gray-300 flex items-center gap-2">
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <circle cx="12" cy="12" r="3" />
                          <line x1="12" y1="3" x2="12" y2="9" />
                          <line x1="12" y1="15" x2="12" y2="21" />
                        </svg>
                        Git Repository
                      </h3>
                      <Link
                        to="/settings"
                        className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
                      >
                        <Settings className="w-3 h-3" />
                        Configure GitLab
                      </Link>
                    </div>

                    {/* Git Mode Selection */}
                    <div className="grid grid-cols-3 gap-2 mb-4">
                      <button
                        type="button"
                        onClick={() => {
                          setFormData({ ...formData, git_mode: 'new' })
                          setGitlabCreateStatus({ status: 'idle' })
                        }}
                        className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                          formData.git_mode === 'new'
                            ? 'bg-orange-600 text-white'
                            : 'bg-[#1a1a2e] text-gray-400 hover:bg-[#2a2a4a]'
                        }`}
                      >
                        {config?.gitlab_configured ? '+ GitLab' : 'New Repo'}
                      </button>
                      <button
                        type="button"
                        onClick={() => setFormData({ ...formData, git_mode: 'existing' })}
                        className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                          formData.git_mode === 'existing'
                            ? 'bg-blue-600 text-white'
                            : 'bg-[#1a1a2e] text-gray-400 hover:bg-[#2a2a4a]'
                        }`}
                      >
                        Existing Repo
                      </button>
                      <button
                        type="button"
                        onClick={() => setFormData({ ...formData, git_mode: 'none' })}
                        className={`px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                          formData.git_mode === 'none'
                            ? 'bg-gray-600 text-white'
                            : 'bg-[#1a1a2e] text-gray-400 hover:bg-[#2a2a4a]'
                        }`}
                      >
                        No Git
                      </button>
                    </div>

                    {formData.git_mode === 'new' && config?.gitlab_configured && (
                      <>
                        {/* Create GitLab Project */}
                        <div className="mb-4 p-3 rounded-lg bg-[#1a1a2e] border border-orange-500/30">
                          <div className="flex items-center gap-2 mb-3">
                            <svg className="w-4 h-4 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
                              <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51L23 13.45a.84.84 0 0 1-.35.94z"/>
                            </svg>
                            <span className="text-sm font-medium text-orange-400">Create GitLab Project</span>
                          </div>

                          <p className="text-xs text-gray-400 mb-3">
                            Creates a new project in: <code className="px-1 bg-[#0a0a1a] rounded">{config.gitlab_namespace}</code>
                          </p>

                          {!formData.name && (
                            <p className="text-xs text-yellow-400 mb-3">
                              ↑ Enter a Project Name above first
                            </p>
                          )}

                          {gitlabCreateStatus.status === 'success' ? (
                            <div className="flex items-center gap-2 text-green-400 text-sm">
                              <CheckCircle className="w-4 h-4" />
                              <span>Created! </span>
                              <a
                                href={gitlabCreateStatus.project?.web_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="text-blue-400 hover:underline"
                              >
                                View on GitLab
                              </a>
                            </div>
                          ) : gitlabCreateStatus.status === 'error' ? (
                            <div className="flex items-center gap-2 text-red-400 text-sm">
                              <AlertCircle className="w-4 h-4" />
                              <span>{gitlabCreateStatus.message}</span>
                            </div>
                          ) : (
                            <button
                              type="button"
                              onClick={async () => {
                                if (!formData.name) {
                                  setGitlabCreateStatus({ status: 'error', message: 'Enter project name first' })
                                  return
                                }
                                setGitlabCreateStatus({ status: 'creating' })
                                try {
                                  const project = await createGitLabProject({
                                    name: formData.name,
                                    description: formData.prompt.slice(0, 200),
                                    visibility: 'private',
                                    initialize_with_readme: true,
                                  })
                                  setGitlabCreateStatus({
                                    status: 'success',
                                    project: {
                                      ssh_url_to_repo: project.ssh_url_to_repo,
                                      web_url: project.web_url,
                                    },
                                  })
                                  // Auto-fill the remote URL
                                  setFormData({
                                    ...formData,
                                    git_remote_url: project.ssh_url_to_repo,
                                    push_to_remote: true,
                                  })
                                } catch (e) {
                                  setGitlabCreateStatus({
                                    status: 'error',
                                    message: e instanceof Error ? e.message : 'Failed to create project',
                                  })
                                }
                              }}
                              disabled={!formData.name || gitlabCreateStatus.status === 'creating'}
                              className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-gray-600 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
                            >
                              {gitlabCreateStatus.status === 'creating' ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                                  <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51L23 13.45a.84.84 0 0 1-.35.94z"/>
                                </svg>
                              )}
                              Create GitLab Project
                            </button>
                          )}
                        </div>
                      </>
                    )}

                    {formData.git_mode !== 'none' && (
                      <>
                        {/* Remote URL - show for new (non-gitlab) or existing */}
                        {(formData.git_mode === 'existing' || (formData.git_mode === 'new' && !config?.gitlab_configured)) && (
                          <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              Remote URL {formData.git_mode === 'new' ? '(for new repo)' : '(optional)'}
                            </label>
                            <input
                              type="text"
                              value={formData.git_remote_url || ''}
                              onChange={(e) => setFormData({ ...formData, git_remote_url: e.target.value })}
                              className="w-full px-3 py-2 bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500 text-sm font-mono"
                              placeholder="git@github.com:username/repo.git"
                            />
                            <p className="text-xs text-gray-500 mt-1">
                              {formData.git_mode === 'new'
                                ? 'Create this repo on GitHub/GitLab first, then paste the SSH URL'
                                : 'Leave empty to use existing remote'}
                            </p>
                          </div>
                        )}

                        {/* Show remote URL as read-only if GitLab project was created */}
                        {formData.git_mode === 'new' && config?.gitlab_configured && gitlabCreateStatus.status === 'success' && (
                          <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-400 mb-1">Remote URL</label>
                            <input
                              type="text"
                              value={formData.git_remote_url || ''}
                              readOnly
                              className="w-full px-3 py-2 bg-[#1a1a2e] border border-green-500/30 rounded-lg text-sm font-mono text-green-400"
                            />
                          </div>
                        )}

                        {/* Git Options */}
                        <div className="flex flex-wrap gap-4 mb-3">
                          <label className="flex items-center gap-2 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={formData.auto_commit}
                              onChange={(e) => setFormData({ ...formData, auto_commit: e.target.checked })}
                              className="w-4 h-4 rounded border-[#2a2a4a] bg-[#0a0a1a] text-blue-600 focus:ring-blue-500"
                            />
                            <span className="text-sm text-gray-300">Auto-commit</span>
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
                            <span className="text-sm text-gray-300">Create MR</span>
                          </label>
                        </div>

                        {formData.create_pr && (
                          <div>
                            <label className="block text-sm font-medium text-gray-400 mb-1">
                              MR Base Branch
                            </label>
                            <input
                              type="text"
                              value={formData.pr_base_branch}
                              onChange={(e) => setFormData({ ...formData, pr_base_branch: e.target.value })}
                              className="w-full px-3 py-2 bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg focus:outline-none focus:border-blue-500 text-sm"
                            />
                          </div>
                        )}
                      </>
                    )}

                    {formData.git_mode === 'none' && (
                      <p className="text-xs text-gray-500">
                        Code will be generated without git version control. You can initialize git later.
                      </p>
                    )}

                    {formData.git_mode === 'new' && !config?.gitlab_configured && (
                      <p className="text-xs text-gray-500 mt-2">
                        <Link to="/settings" className="text-orange-400 hover:underline">Configure GitLab</Link> to create projects directly from here.
                      </p>
                    )}
                  </div>

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
