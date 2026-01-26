import { useEffect, useRef } from 'react'
import { AutonomousEvent } from '../../stores/autonomous'

interface EventLogProps {
  events: AutonomousEvent[]
  maxHeight?: string
}

const eventColors: Record<string, string> = {
  project_started: 'text-blue-400',
  planning_started: 'text-yellow-400',
  model_selected: 'text-violet-400',
  task_created: 'text-green-400',
  planning_completed: 'text-green-400',
  task_started: 'text-blue-400',
  task_progress: 'text-gray-400',
  task_agent_output: 'text-gray-500',
  quality_gate_check: 'text-purple-400',
  quality_gate_passed: 'text-green-400',
  quality_gate_failed: 'text-red-400',
  task_fixing: 'text-orange-400',
  task_completed: 'text-green-400',
  task_failed: 'text-red-400',
  git_commit: 'text-cyan-400',
  git_push: 'text-cyan-400',
  git_pr_created: 'text-cyan-400',
  paused: 'text-yellow-400',
  resumed: 'text-green-400',
  timeout: 'text-orange-400',
  project_completed: 'text-green-400',
  project_failed: 'text-red-400',
  error: 'text-red-500',
}

const eventIcons: Record<string, string> = {
  project_started: '🚀',
  planning_started: '📋',
  model_selected: '🤖',
  task_created: '📝',
  planning_completed: '✅',
  task_started: '▶️',
  task_progress: '⏳',
  task_agent_output: '💬',
  quality_gate_check: '🔍',
  quality_gate_passed: '✅',
  quality_gate_failed: '❌',
  task_fixing: '🔧',
  task_completed: '✅',
  task_failed: '❌',
  git_commit: '📝',
  git_push: '⬆️',
  git_pr_created: '🔗',
  paused: '⏸️',
  resumed: '▶️',
  timeout: '⏰',
  project_completed: '🎉',
  project_failed: '💥',
  error: '⚠️',
}

function formatEventMessage(event: AutonomousEvent): string {
  const { type, data } = event

  switch (type) {
    case 'project_started':
      return 'Project started'
    case 'planning_started':
      return 'Planning phase started'
    case 'model_selected':
      return `Model: ${data.model} - ${data.reason || data.phase || ''}`
    case 'task_created':
      return `Task created: ${(data.task as Record<string, unknown>)?.title || data.task_id}`
    case 'planning_completed':
      return `Planning completed - ${data.task_count} tasks`
    case 'task_started':
      return `Task started: ${data.title} (${data.agent_type}${data.model ? `, ${data.model}` : ''}, attempt ${data.attempt})`
    case 'task_progress':
      return `Task progress: ${Math.round((data.progress as number || 0) * 100)}% - ${data.stage}`
    case 'task_agent_output':
      return `Agent output: ${(data.output as string)?.slice(0, 100)}...`
    case 'quality_gate_check':
      return `Checking: ${data.gate_type}`
    case 'quality_gate_passed':
      return `Gate passed: ${data.gate_type}`
    case 'quality_gate_failed':
      return `Gate failed: ${data.gate_type} - ${data.error}`
    case 'task_fixing':
      return `Fixing issues (attempt ${data.attempt})`
    case 'task_completed':
      return `Task completed: ${data.task_id} after ${data.iterations} iterations`
    case 'task_failed':
      return `Task failed: ${data.task_id} - ${data.reason}`
    case 'git_commit':
      return `Committed: ${data.sha} - ${data.message}`
    case 'git_push':
      return `Pushed to branch: ${data.branch}`
    case 'git_pr_created':
      return `PR created: ${data.url}`
    case 'paused':
      return 'Project paused'
    case 'resumed':
      return 'Project resumed'
    case 'timeout':
      return 'Project timed out'
    case 'project_completed':
      return `Project completed! ${data.tasks_completed} tasks done`
    case 'project_failed':
      return `Project failed: ${data.error}`
    case 'error':
      return `Error: ${data.error}`
    default:
      return type
  }
}

export default function EventLog({ events, maxHeight = '400px' }: EventLogProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new events
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [events.length])

  return (
    <div className="bg-[#1a1a2e] border border-[#2a2a4a] rounded-lg">
      <div className="px-4 py-2 border-b border-[#2a2a4a]">
        <h3 className="font-medium text-gray-300">Event Log</h3>
      </div>

      <div
        ref={containerRef}
        className="overflow-y-auto font-mono text-xs"
        style={{ maxHeight }}
      >
        {events.length === 0 ? (
          <div className="p-4 text-gray-500 text-center">
            No events yet...
          </div>
        ) : (
          <div className="p-2 space-y-1">
            {events.map((event, index) => {
              const color = eventColors[event.type] || 'text-gray-400'
              const icon = eventIcons[event.type] || '•'
              const time = new Date(event.timestamp).toLocaleTimeString()
              const message = formatEventMessage(event)

              return (
                <div
                  key={index}
                  className={`flex items-start gap-2 ${color} hover:bg-[#2a2a4a] rounded px-2 py-1`}
                >
                  <span className="text-gray-500 shrink-0">{time}</span>
                  <span className="shrink-0">{icon}</span>
                  <span className="break-all">{message}</span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
