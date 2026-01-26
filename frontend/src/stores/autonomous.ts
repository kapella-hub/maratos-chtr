import { create } from 'zustand'

export type ProjectStatus =
  | 'planning'
  | 'in_progress'
  | 'blocked'
  | 'paused'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type TaskStatus =
  | 'pending'
  | 'blocked'
  | 'ready'
  | 'in_progress'
  | 'testing'
  | 'reviewing'
  | 'fixing'
  | 'completed'
  | 'failed'
  | 'skipped'

export interface QualityGate {
  type: string
  required: boolean
  passed: boolean
  error?: string
  checked_at?: string
}

export interface TaskIteration {
  attempt: number
  started_at: string
  completed_at?: string
  success: boolean
  agent_response: string
  quality_results: Record<string, { passed: boolean; error?: string }>
  feedback?: string
  files_modified: string[]
  commit_sha?: string
}

export interface AutonomousTask {
  id: string
  title: string
  description: string
  agent_type: string
  status: TaskStatus
  depends_on: string[]
  quality_gates: QualityGate[]
  iterations: TaskIteration[]
  current_attempt: number
  max_attempts: number
  priority: number
  target_files: string[]
  final_commit_sha?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface AutonomousProject {
  id: string
  name: string
  original_prompt: string
  workspace_path: string
  status: ProjectStatus
  progress: number
  tasks_completed: number
  tasks_failed: number
  tasks_pending: number
  total_iterations: number
  branch_name?: string
  pr_url?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

export interface AutonomousEvent {
  type: string
  project_id: string
  data: Record<string, unknown>
  timestamp: string
}

interface AutonomousStore {
  // Current project state
  currentProject: AutonomousProject | null
  tasks: AutonomousTask[]
  events: AutonomousEvent[]

  // UI state
  isStreaming: boolean
  isPlanning: boolean
  error: string | null
  abortController: AbortController | null

  // Projects list
  projects: AutonomousProject[]

  // Actions
  setCurrentProject: (project: AutonomousProject | null) => void
  updateProject: (updates: Partial<AutonomousProject>) => void
  setTasks: (tasks: AutonomousTask[]) => void
  updateTask: (taskId: string, updates: Partial<AutonomousTask>) => void
  addTask: (task: AutonomousTask) => void
  addEvent: (event: AutonomousEvent) => void
  clearEvents: () => void

  setStreaming: (streaming: boolean) => void
  setPlanning: (planning: boolean) => void
  setError: (error: string | null) => void
  setAbortController: (controller: AbortController | null) => void

  setProjects: (projects: AutonomousProject[]) => void

  stopProject: () => void
  reset: () => void
}

export const useAutonomousStore = create<AutonomousStore>((set, get) => ({
  currentProject: null,
  tasks: [],
  events: [],
  isStreaming: false,
  isPlanning: false,
  error: null,
  abortController: null,
  projects: [],

  setCurrentProject: (project) => set({ currentProject: project }),

  updateProject: (updates) => set((state) => ({
    currentProject: state.currentProject
      ? { ...state.currentProject, ...updates }
      : null,
  })),

  setTasks: (tasks) => set({ tasks }),

  updateTask: (taskId, updates) => set((state) => ({
    tasks: state.tasks.map((task) =>
      task.id === taskId ? { ...task, ...updates } : task
    ),
  })),

  addTask: (task) => set((state) => ({
    tasks: [...state.tasks, task],
  })),

  addEvent: (event) => set((state) => ({
    events: [...state.events.slice(-100), event], // Keep last 100 events
  })),

  clearEvents: () => set({ events: [] }),

  setStreaming: (streaming) => set({ isStreaming: streaming }),
  setPlanning: (planning) => set({ isPlanning: planning }),
  setError: (error) => set({ error }),
  setAbortController: (controller) => set({ abortController: controller }),

  setProjects: (projects) => set({ projects }),

  stopProject: () => {
    const { abortController } = get()
    if (abortController) {
      abortController.abort()
      set({
        isStreaming: false,
        isPlanning: false,
        abortController: null,
      })
    }
  },

  reset: () => set({
    currentProject: null,
    tasks: [],
    events: [],
    isStreaming: false,
    isPlanning: false,
    error: null,
    abortController: null,
  }),
}))
