import { useRef, useEffect, useCallback, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Layers, FolderCode } from 'lucide-react'
import ChatInput, { SessionCommand } from '@/components/ChatInput'
import { ChatStream, ProjectCard } from '@/components/chat'
import ToastContainer from '@/components/ToastContainer'
import { useChatStore } from '@/stores/chat'
import type { ProjectPlan, ProjectTask } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import { useCanvasStore } from '@/stores/canvas'
import { streamChat, streamChatWithProjectAction, fetchConfig, fetchProjects, fetchRules, ThinkingBlock } from '@/lib/api'
import { saveChatSession, getChatSession } from '@/lib/chatHistory'
import { playMessageComplete } from '@/lib/sounds'

export default function ChatPage() {
  const processingRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const {
    messages,
    messageQueue,
    sessionId,
    agentId,
    isStreaming,
    isThinking,
    isModelThinking,
    isOrchestrating,
    activeSubagents,
    inlineProject,
    activeProjectContext,
    selectedProjectName,
    setSessionId,
    setAgentId,
    setCurrentModel,
    setActiveProjectContext,
    setSelectedProjectName,
    addMessage,
    appendToLastMessage,
    setLastMessageAgent,
    setStreaming,
    setThinking,
    setModelThinking,
    setOrchestrating,
    updateSubagent,
    clearSubagents,
    setAbortController,
    stopGeneration,
    enqueueMessage,
    dequeueMessage,
    clearMessages,
    setProjectStatus,
    setProjectPlan,
    updateProjectTask,
    addProjectEvent,
    setProjectError,
    clearProject,
    setCurrentThinkingBlock,
    setLastMessageThinking,
    statusMessage,
    setStatusMessage,
    currentThinkingBlock,
  } = useChatStore()

  const { addToast } = useToastStore()
  const { addArtifact: addCanvasArtifact, artifacts: canvasArtifacts, panelVisible, togglePanel } = useCanvasStore()

  // Fetch config (for potential use)
  useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  // Fetch projects for the selector
  const { data: projects = [] } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  // Fetch rules for the selector
  const { data: rules = [] } = useQuery({
    queryKey: ['rules'],
    queryFn: fetchRules,
  })

  // Track selected rules (persisted across messages)
  const [selectedRules, setSelectedRules] = useState<string[]>([])

  // Always use MO agent
  useEffect(() => {
    if (agentId !== 'mo') {
      setAgentId('mo')
    }
  }, [agentId, setAgentId])

  // Save session after messages update
  useEffect(() => {
    if (sessionId && messages.length > 0 && !isStreaming) {
      sessionIdRef.current = sessionId
      saveChatSession(sessionId, messages)
    }
  }, [sessionId, messages, isStreaming])

  // Play sound when streaming completes
  const prevStreamingRef = useRef(isStreaming)
  useEffect(() => {
    if (prevStreamingRef.current && !isStreaming && messages.length > 0) {
      playMessageComplete()
    }
    prevStreamingRef.current = isStreaming
  }, [isStreaming, messages.length])

  // Keep ref in sync
  useEffect(() => {
    if (sessionId) {
      sessionIdRef.current = sessionId
    }
  }, [sessionId])

  // Save on page unload
  useEffect(() => {
    const handleBeforeUnload = () => {
      const currentSessionId = sessionIdRef.current
      const currentMessages = useChatStore.getState().messages
      if (currentSessionId && currentMessages.length > 0) {
        saveChatSession(currentSessionId, currentMessages)
      }
    }
    window.addEventListener('beforeunload', handleBeforeUnload)
    return () => window.removeEventListener('beforeunload', handleBeforeUnload)
  }, [])

  // Process a single message
  const processMessage = useCallback(async (content: string, ruleIds?: string[]) => {
    const controller = new AbortController()
    setAbortController(controller)

    addMessage({ role: 'user', content })
    addMessage({ role: 'assistant', content: '', agentId })

    setStreaming(true)
    setThinking(true)

    try {
      for await (const event of streamChat(content, agentId, sessionId || undefined, controller.signal, selectedProjectName, ruleIds)) {
        if (event.type === 'session_id' && event.data) {
          const newSessionId = event.data as string
          sessionIdRef.current = newSessionId
          setSessionId(newSessionId)
        } else if (event.type === 'agent' && event.data) {
          setLastMessageAgent(event.data as string)
        } else if (event.type === 'model' && event.data) {
          setCurrentModel(event.data as string)
        } else if (event.type === 'project_context_active' && event.projectContext) {
          setActiveProjectContext(event.projectContext)
        } else if (event.type === 'thinking') {
          setThinking(event.data as boolean)
        } else if (event.type === 'model_thinking') {
          setModelThinking(event.data as boolean)
        } else if (event.type === 'thinking_block' && event.data) {
          // Structured thinking block started
          setCurrentThinkingBlock(event.data as unknown as Partial<ThinkingBlock>)
        } else if (event.type === 'thinking_complete' && event.data) {
          // Structured thinking complete - attach to message
          setLastMessageThinking(event.data as unknown as ThinkingBlock)
        } else if (event.type === 'orchestrating') {
          setOrchestrating(event.data as boolean)
        } else if (event.type === 'status_update') {
          // Update transient status message
          setStatusMessage(event.data as string)

          // Notify user on completion
          if (event.status === 'completed') {
            addToast({ type: 'success', description: event.data as string })
          } else if (event.status === 'failed') {
            addToast({ type: 'error', description: event.data as string })
          }
        } else if (event.type === 'subagent' && event.subagent) {
          updateSubagent({
            id: event.taskId || event.subagent,
            agent: event.subagent,
            status: (event.status as 'spawning' | 'running' | 'retrying' | 'completed' | 'failed' | 'timed_out' | 'cancelled') || 'running',
            progress: event.progress || 0,
            error: event.error,
            goals: event.goals,
            checkpoints: event.checkpoints,
            logs: (event as { logs?: string[] }).logs,
            currentAction: (event as { current_action?: string }).current_action,
            attempt: event.attempt,
            maxAttempts: event.max_attempts,
            isFallback: event.is_fallback,
            originalTaskId: event.original_task_id,
          })
        } else if (event.type === 'subagent_result' && event.data) {
          addMessage({
            role: 'assistant',
            content: event.data as string,
            agentId: event.subagent,
          })
        } else if (event.type === 'content' && event.data) {
          appendToLastMessage(event.data as string)
        } else if (event.type === 'canvas_create' && event.data) {
          const artifact = event.data as unknown as {
            id: string
            type: string
            title: string
            content: string
            metadata?: { language?: string; editable?: boolean }
          }
          addCanvasArtifact({
            id: artifact.id,
            type: artifact.type as 'code' | 'preview' | 'form' | 'chart' | 'diagram' | 'table' | 'diff' | 'terminal' | 'markdown',
            title: artifact.title,
            content: artifact.content,
            metadata: artifact.metadata,
          })
        }
        // Inline project events
        else if (event.type === 'project_detected') {
          setProjectStatus('detecting')
          addProjectEvent({ type: 'project_detected', data: { reason: event.reason, complexity: event.complexity }, timestamp: new Date().toISOString() })
        } else if (event.type === 'planning_started') {
          setProjectStatus('planning')
          addProjectEvent({ type: 'planning_started', data: { project_id: event.projectId }, timestamp: new Date().toISOString() })
        } else if (event.type === 'plan_ready' && event.project) {
          setProjectPlan(event.project as ProjectPlan)
          addProjectEvent({ type: 'plan_ready', data: { plan_id: event.project.id }, timestamp: new Date().toISOString() })
        } else if (event.type === 'awaiting_approval') {
          setProjectStatus('awaiting_approval')
        } else if (event.type === 'plan_approved') {
          setProjectStatus('executing')
          addProjectEvent({ type: 'plan_approved', data: {}, timestamp: new Date().toISOString() })
        } else if (event.type === 'task_started' && event.task) {
          updateProjectTask(event.task.id, { status: 'in_progress' })
          addProjectEvent({ type: 'task_started', data: { task_id: event.task.id, task: event.task }, timestamp: new Date().toISOString() })

          // Also show as active subagent card
          updateSubagent({
            id: event.task.id,
            agent: event.task.agent_id || 'mo',
            status: 'running',
            progress: 0,
            currentAction: `Starting: ${event.task.title}`,
            attempt: 1,
            maxAttempts: 3 // Default
          })
        } else if (event.type === 'task_progress') {
          if (event.taskId) {
            updateProjectTask(event.taskId, { progress: event.progress, status: event.status as ProjectTask['status'] })
            // Update agent card progress
            updateSubagent({
              id: event.taskId,
              status: 'running',
              progress: (event.progress || 0) * 100, // Assuming 0-1 float
            })
          }
        } else if (event.type === 'task_completed' && event.taskId) {
          updateProjectTask(event.taskId, { status: 'completed' })
          addProjectEvent({ type: 'task_completed', data: { task_id: event.taskId }, timestamp: new Date().toISOString() })

          updateSubagent({
            id: event.taskId,
            status: 'completed',
            progress: 100
          })
        } else if (event.type === 'task_failed' && event.taskId) {
          updateProjectTask(event.taskId, { status: 'failed', error: event.error })
          addProjectEvent({ type: 'task_failed', data: { task_id: event.taskId, error: event.error }, timestamp: new Date().toISOString() })

          updateSubagent({
            id: event.taskId,
            status: 'failed',
            error: event.error
          })
        } else if (event.type === 'project_paused') {
          setProjectStatus('paused')
        } else if (event.type === 'project_resumed') {
          setProjectStatus('executing')
        } else if (event.type === 'project_completed') {
          setProjectStatus('completed')
          if (event.project) setProjectPlan(event.project as ProjectPlan)
        } else if (event.type === 'project_failed') {
          setProjectError(event.error || 'Project failed')
        } else if (event.type === 'project_cancelled') {
          setProjectStatus('cancelled')
        } else if (event.type === 'git_commit') {
          addProjectEvent({ type: 'git_commit', data: { sha: event.commitSha, message: event.commitMessage }, timestamp: new Date().toISOString() })
        } else if (event.type === 'git_pr_created') {
          addProjectEvent({ type: 'git_pr_created', data: { url: event.prUrl }, timestamp: new Date().toISOString() })
        }
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        appendToLastMessage('\n\n[Stopped]')
        addToast({ type: 'info', title: 'Task stopped', description: 'Generation was cancelled' })
      } else {
        console.error('Chat error:', error)
        appendToLastMessage('\n\n[Error: Failed to get response]')
        addToast({ type: 'error', title: 'Error', description: 'Failed to get response from agent' })
      }
    } finally {
      if (sessionIdRef.current) {
        const currentMessages = useChatStore.getState().messages
        saveChatSession(sessionIdRef.current, currentMessages)
      }
      setStreaming(false)
      setThinking(false)
      setModelThinking(false)
      setAbortController(null)
      setAbortController(null)
      clearSubagents()
      setStatusMessage(null)
    }
  }, [agentId, sessionId, selectedProjectName, addMessage, appendToLastMessage, setSessionId, setLastMessageAgent, setCurrentModel, setActiveProjectContext, setStreaming, setThinking, setModelThinking, setCurrentThinkingBlock, setLastMessageThinking, setOrchestrating, updateSubagent, clearSubagents, setAbortController, setProjectStatus, setProjectPlan, updateProjectTask, addProjectEvent, setProjectError, addCanvasArtifact, addToast, setStatusMessage])

  // Project action handlers
  const handleProjectApprove = useCallback(async () => {
    if (!sessionId) return
    setStreaming(true)
    try {
      for await (const event of streamChatWithProjectAction('Approve and start the project', agentId, sessionId, { project_action: 'approve' })) {
        if (event.type === 'plan_approved') setProjectStatus('executing')
        else if (event.type === 'content' && event.data) appendToLastMessage(event.data as string)
      }
    } catch (error) {
      console.error('Failed to approve project:', error)
      addToast({ type: 'error', title: 'Error', description: 'Failed to approve project' })
    } finally {
      setStreaming(false)
    }
  }, [sessionId, agentId, setStreaming, setProjectStatus, appendToLastMessage, addToast])

  const handleProjectCancel = useCallback(async () => {
    if (!sessionId) return
    setStreaming(true)
    try {
      for await (const event of streamChatWithProjectAction('Cancel the project', agentId, sessionId, { project_action: 'cancel' })) {
        if (event.type === 'project_cancelled') {
          setProjectStatus('cancelled')
          addToast({ type: 'info', title: 'Project cancelled', description: 'The project has been cancelled' })
        }
      }
    } catch (error) {
      console.error('Failed to cancel project:', error)
    } finally {
      setStreaming(false)
    }
  }, [sessionId, agentId, setStreaming, setProjectStatus, addToast])

  const handleProjectPause = useCallback(async () => {
    if (!sessionId) return
    setStreaming(true)
    try {
      for await (const event of streamChatWithProjectAction('Pause the project', agentId, sessionId, { project_action: 'pause' })) {
        if (event.type === 'project_paused') {
          setProjectStatus('paused')
          addToast({ type: 'info', title: 'Project paused', description: 'The project has been paused' })
        }
      }
    } catch (error) {
      console.error('Failed to pause project:', error)
    } finally {
      setStreaming(false)
    }
  }, [sessionId, agentId, setStreaming, setProjectStatus, addToast])

  const handleProjectResume = useCallback(async () => {
    if (!sessionId) return
    setStreaming(true)
    try {
      for await (const event of streamChatWithProjectAction('Resume the project', agentId, sessionId, { project_action: 'resume' })) {
        if (event.type === 'project_resumed') {
          setProjectStatus('executing')
          addToast({ type: 'success', title: 'Project resumed', description: 'The project has been resumed' })
        }
      }
    } catch (error) {
      console.error('Failed to resume project:', error)
    } finally {
      setStreaming(false)
    }
  }, [sessionId, agentId, setStreaming, setProjectStatus, addToast])

  const handleProjectAdjust = useCallback(async (message: string) => {
    if (!sessionId) return
    setStreaming(true)
    addMessage({ role: 'user', content: message })
    addMessage({ role: 'assistant', content: '', agentId: 'mo' })
    try {
      for await (const event of streamChatWithProjectAction(message, agentId, sessionId, { project_action: 'adjust', project_adjustments: { message } })) {
        if (event.type === 'plan_ready' && event.project) setProjectPlan(event.project as ProjectPlan)
        else if (event.type === 'content' && event.data) appendToLastMessage(event.data as string)
      }
    } catch (error) {
      console.error('Failed to adjust project:', error)
      appendToLastMessage('\n\n[Failed to adjust project]')
    } finally {
      setStreaming(false)
    }
  }, [sessionId, agentId, setStreaming, addMessage, setProjectPlan, appendToLastMessage])

  // Process queue
  const processQueue = useCallback(async () => {
    if (processingRef.current) return
    processingRef.current = true
    let next = dequeueMessage()
    while (next) {
      await processMessage(next.content)
      next = dequeueMessage()
    }
    processingRef.current = false
  }, [dequeueMessage, processMessage])

  // Handle sending
  const handleSend = async (content: string, skill?: { id: string; name: string } | null, ruleIds?: string[]) => {
    const messageContent = skill ? `[Using skill: ${skill.name}]\n\n${content}` : content
    await processMessage(messageContent, ruleIds)
    processQueue()
  }

  // Handle commands
  const handleCommand = (command: SessionCommand) => {
    switch (command) {
      case 'reset':
        clearMessages()
        clearProject()
        sessionIdRef.current = null
        addToast({ type: 'success', title: 'Session reset', description: 'Started a new conversation' })
        break
      case 'help':
        addMessage({
          role: 'assistant',
          content: `## Available Commands\n\n| Command | Description |\n|---------|-------------|\n| \`/reset\` | Clear the current session |\n| \`/help\` | Show this help message |\n\n**Keyboard Shortcuts:**\n- **Enter** - Send message\n- **Shift+Enter** - New line\n- **Cmd+H** - Toggle history\n- **Cmd+K** - Command palette\n- **Esc** - Stop generation`,
          agentId: 'mo'
        })
        break
    }
  }

  // Load session from history
  useEffect(() => {
    if (sessionId && messages.length === 0) {
      const session = getChatSession(sessionId)
      if (session && session.messages.length > 0) {
        session.messages.forEach(msg => {
          addMessage({ role: msg.role, content: msg.content, agentId: msg.agentId })
        })
      }
    }
  }, [sessionId, messages.length, addMessage])

  return (
    <div className="flex flex-col h-full relative">
      {/* Progress bar */}
      {(isThinking || isModelThinking || isStreaming) && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-muted/30 overflow-hidden z-50">
          <div
            className="h-full bg-gradient-to-r from-violet-500 via-purple-500 to-indigo-500 rounded-full"
            style={{
              animation: 'progress 2s ease-in-out infinite',
              width: '40%',
              boxShadow: '0 0 20px rgba(139, 92, 246, 0.5)'
            }}
          />
        </div>
      )}

      {/* Active Project Context Indicator */}
      {(activeProjectContext || selectedProjectName) && (
        <div className="max-w-3xl mx-auto w-full px-4 pt-3">
          <div className="flex items-center gap-2.5 px-4 py-2 rounded-xl bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20 text-sm shadow-sm">
            <div className="p-1.5 rounded-lg bg-primary/20">
              <FolderCode className="w-4 h-4 text-primary" />
            </div>
            <div className="flex flex-col">
              <span className="text-xs text-muted-foreground">Working in</span>
              <span className="font-medium text-foreground">{activeProjectContext?.name || selectedProjectName}</span>
            </div>
          </div>
        </div>
      )}

      {/* Chat Stream */}
      <ChatStream
        messages={messages}
        activeSubagents={activeSubagents}
        isThinking={isThinking}
        isStreaming={isStreaming}
        isOrchestrating={isOrchestrating}
        statusMessage={statusMessage}
        onCancelSubagent={(taskId) => {
          updateSubagent({
            id: taskId,
            agent: activeSubagents.find(t => t.id === taskId)?.agent || '',
            status: 'cancelled',
            progress: activeSubagents.find(t => t.id === taskId)?.progress || 0,
          })
        }}
        onSendQuickPrompt={handleSend}
        currentThinkingBlock={currentThinkingBlock}
        className="flex-1"
      />

      {/* Inline Project Card */}
      {inlineProject.plan && inlineProject.status !== 'none' && (
        <div className="max-w-3xl mx-auto w-full px-4 pb-2">
          <ProjectCard
            plan={inlineProject.plan}
            status={inlineProject.status as 'awaiting_approval' | 'executing' | 'paused' | 'completed' | 'failed'}
            onApprove={handleProjectApprove}
            onCancel={handleProjectCancel}
            onPause={handleProjectPause}
            onResume={handleProjectResume}
            onAdjust={handleProjectAdjust}
          />
        </div>
      )}

      {/* Project status indicator for detecting/planning */}
      {(inlineProject.status === 'detecting' || inlineProject.status === 'planning') && (
        <div className="max-w-3xl mx-auto w-full px-4 pb-3">
          <div className="bg-gradient-to-r from-violet-500/10 to-purple-500/10 border border-violet-500/20 rounded-2xl p-4 flex items-center gap-4 shadow-lg shadow-violet-500/5">
            <div className="relative">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center">
                <div className="w-5 h-5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              </div>
              <div className="absolute inset-0 rounded-xl bg-violet-500/30 blur-lg animate-pulse" />
            </div>
            <div>
              <span className="text-sm font-medium text-foreground">
                {inlineProject.status === 'detecting' ? 'Analyzing request...' : 'Creating project plan...'}
              </span>
              <p className="text-xs text-muted-foreground mt-0.5">
                {inlineProject.status === 'detecting'
                  ? 'Determining the best approach for your request'
                  : 'Breaking down tasks and estimating effort'}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Floating Input */}
      <div className="floating-input">
        <ChatInput
          onSend={handleSend}
          onQueue={enqueueMessage}
          onStop={stopGeneration}
          onCommand={handleCommand}
          isLoading={isStreaming}
          hasQueue={messageQueue.length > 0}
          placeholder="Message MO..."
          projects={projects}
          selectedProject={selectedProjectName}
          onProjectSelect={setSelectedProjectName}
          rules={rules}
          selectedRules={selectedRules}
          onRulesChange={setSelectedRules}
        />
      </div>

      {/* Toast Notifications */}
      <ToastContainer />

      {/* Canvas toggle button */}
      {canvasArtifacts.length > 0 && !panelVisible && (
        <button
          onClick={togglePanel}
          className="fixed right-4 bottom-32 z-30 flex items-center gap-2 px-4 py-2.5 rounded-2xl bg-gradient-to-r from-violet-600 to-purple-600 text-white shadow-xl shadow-violet-500/30 hover:shadow-2xl hover:shadow-violet-500/40 hover:-translate-y-0.5 transition-all duration-200"
        >
          <Layers className="w-4 h-4" />
          <span className="text-sm font-medium">Canvas</span>
          <span className="text-xs px-2 py-0.5 rounded-full bg-white/20 font-semibold">
            {canvasArtifacts.length}
          </span>
        </button>
      )}
    </div>
  )
}
