import { useRef, useEffect, useCallback, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Sparkles, Layers, Brain, ChevronDown } from 'lucide-react'
import ChatInput, { SessionCommand } from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import SubagentStatus from '@/components/SubagentStatus'
import QueueIndicator from '@/components/QueueIndicator'
import AgentStatusBar from '@/components/AgentStatusBar'
import ToastContainer from '@/components/ToastContainer'
import { CanvasPanel } from '@/components/canvas'
import { useChatStore } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import { useCanvasStore } from '@/stores/canvas'
import { streamChat, fetchConfig, updateConfig } from '@/lib/api'
import { saveChatSession, getChatSession } from '@/lib/chatHistory'

// Format model name for display
function formatModelName(model: string): string {
  if (!model) return 'Claude'
  return model
    .replace(/-\d{8}$/, '')
    .replace('claude-', '')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function ChatPage() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const processingRef = useRef(false)
  const sessionIdRef = useRef<string | null>(null)
  const {
    messages,
    messageQueue,
    sessionId,
    agentId,
    currentModel,
    isStreaming,
    isThinking,
    isModelThinking,
    isOrchestrating,
    activeSubagents,
    setSessionId,
    setAgentId,
    setCurrentModel,
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
    clearQueue,
    clearMessages,
  } = useChatStore()

  // Status dialog state
  const [showStatus, setShowStatus] = useState(false)
  // Thinking level dropdown
  const [showThinkingMenu, setShowThinkingMenu] = useState(false)

  const THINKING_LEVELS = [
    { value: 'off', label: 'Off', description: 'Direct execution' },
    { value: 'minimal', label: 'Minimal', description: 'Quick check' },
    { value: 'low', label: 'Low', description: 'Brief analysis' },
    { value: 'medium', label: 'Medium', description: 'Structured analysis' },
    { value: 'high', label: 'High', description: 'Deep analysis' },
    { value: 'max', label: 'Max', description: 'Exhaustive analysis' },
  ]

  const handleThinkingLevelChange = async (level: string) => {
    try {
      await updateConfig({ thinking_level: level })
      // Invalidate config query to refetch
      await queryClient.invalidateQueries({ queryKey: ['config'] })
      setShowThinkingMenu(false)
      addToast({
        type: 'success',
        title: 'Thinking level updated',
        description: `Now using ${level} analysis depth`
      })
    } catch {
      addToast({
        type: 'error',
        title: 'Error',
        description: 'Failed to update thinking level'
      })
    }
  }

  // Close thinking menu when clicking outside
  useEffect(() => {
    if (!showThinkingMenu) return
    const handleClick = () => setShowThinkingMenu(false)
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [showThinkingMenu])

  const { addToast } = useToastStore()
  const queryClient = useQueryClient()
  const { addArtifact: addCanvasArtifact, artifacts: canvasArtifacts, panelVisible, togglePanel } = useCanvasStore()

  // Fetch config to show current model
  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

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

  // Keep ref in sync when sessionId changes
  useEffect(() => {
    if (sessionId) {
      sessionIdRef.current = sessionId
    }
  }, [sessionId])

  // Save on page unload to prevent data loss during streaming
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

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // Process a single message
  const processMessage = useCallback(async (content: string) => {
    const controller = new AbortController()
    setAbortController(controller)

    addMessage({ role: 'user', content })
    addMessage({ role: 'assistant', content: '', agentId })

    setStreaming(true)
    setThinking(true)

    try {
      for await (const event of streamChat(content, agentId, sessionId || undefined, controller.signal)) {
        if (event.type === 'session_id' && event.data) {
          const newSessionId = event.data as string
          sessionIdRef.current = newSessionId
          setSessionId(newSessionId)
        } else if (event.type === 'agent' && event.data) {
          setLastMessageAgent(event.data as string)
        } else if (event.type === 'model' && event.data) {
          setCurrentModel(event.data as string)
        } else if (event.type === 'thinking') {
          setThinking(event.data as boolean)
        } else if (event.type === 'model_thinking') {
          setModelThinking(event.data as boolean)
        } else if (event.type === 'orchestrating') {
          setOrchestrating(event.data as boolean)
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
          // Handle canvas artifact creation
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
      }
    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        appendToLastMessage('\n\n⏹️ Stopped')
        addToast({
          type: 'info',
          title: 'Task stopped',
          description: 'Generation was cancelled'
        })
      } else {
        console.error('Chat error:', error)
        appendToLastMessage('\n\n❌ Error: Failed to get response')
        addToast({
          type: 'error',
          title: 'Error',
          description: 'Failed to get response from agent'
        })
      }
    } finally {
      // Save before changing streaming state to ensure we capture final messages
      if (sessionIdRef.current) {
        const currentMessages = useChatStore.getState().messages
        saveChatSession(sessionIdRef.current, currentMessages)
      }
      setStreaming(false)
      setThinking(false)
      setModelThinking(false)
      setAbortController(null)
      clearSubagents()
    }
  }, [agentId, sessionId, addMessage, appendToLastMessage, setSessionId, setLastMessageAgent, setCurrentModel, setStreaming, setThinking, setModelThinking, setOrchestrating, updateSubagent, clearSubagents, setAbortController])

  // Process queue after each message
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

  // Handle sending a new message
  const handleSend = async (content: string, skill?: { id: string; name: string } | null) => {
    // If a skill is selected, prefix the content with skill info
    const messageContent = skill
      ? `[Using skill: ${skill.name}]\n\n${content}`
      : content
    await processMessage(messageContent)
    processQueue()
  }

  // Handle queuing a message
  const handleQueue = (content: string) => {
    enqueueMessage(content)
  }

  // Handle session commands
  const handleCommand = (command: SessionCommand) => {
    switch (command) {
      case 'reset':
        clearMessages()
        sessionIdRef.current = null
        addToast({
          type: 'success',
          title: 'Session reset',
          description: 'Started a new conversation'
        })
        break
      case 'status':
        setShowStatus(true)
        break
      case 'help':
        // Insert help message as a system message
        addMessage({
          role: 'assistant',
          content: `## Available Commands

| Command | Description |
|---------|-------------|
| \`/reset\` | Clear the current session and start fresh |
| \`/status\` | Show current session information |
| \`/help\` | Show this help message |

**Keyboard Shortcuts:**
- **Enter** - Send message
- **Shift+Enter** - New line
- **Cmd/Ctrl+Enter** - Send message
- **Esc** - Stop generation`,
          agentId: 'mo'
        })
        break
    }
  }

  // Load session from history when sessionId changes (from sidebar)
  // Only load if messages are empty (fresh session load, not a new chat)
  useEffect(() => {
    if (sessionId && messages.length === 0) {
      const session = getChatSession(sessionId)
      if (session && session.messages.length > 0) {
        session.messages.forEach(msg => {
          addMessage({
            role: msg.role,
            content: msg.content,
            agentId: msg.agentId,
          })
        })
      }
    }
  }, [sessionId, messages.length, addMessage])

  const modelName = formatModelName(config?.default_model || 'claude-sonnet-4')

  return (
    <div className="flex flex-col h-full relative">
      {/* Progress bar */}
      {(isThinking || isModelThinking || isStreaming) && (
        <div className="absolute top-0 left-0 right-0 h-1 bg-muted overflow-hidden z-50">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 via-violet-500 to-purple-500"
            style={{
              animation: 'progress 1.5s ease-in-out infinite',
              width: '100%',
            }}
          />
        </div>
      )}

      {/* Header - only show when active */}
      {(isThinking || isStreaming || isOrchestrating) && (
        <header className="px-6 py-3 border-b border-border/50 bg-background/80 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <AgentStatusBar
              isActive={true}
              status={isOrchestrating ? 'orchestrating' : isStreaming ? 'streaming' : 'thinking'}
              progress={isStreaming ? 50 : 0}
              onCancel={stopGeneration}
            />
            {currentModel && (
              <div className="text-xs text-muted-foreground flex items-center gap-1.5 px-2 py-1 rounded-lg bg-muted/50">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span className="font-mono">{currentModel}</span>
              </div>
            )}
          </div>
        </header>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md px-4 animate-in fade-in-up duration-700">
              {/* Hero */}
              <div className="relative mb-8">
                <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-indigo-500 via-violet-600 to-purple-600 flex items-center justify-center text-white text-3xl font-bold mx-auto shadow-2xl shadow-indigo-500/40 transition-shadow hover:shadow-indigo-500/60">
                  MO
                </div>
                <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center shadow-lg animate-pulse">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
              </div>

              <h2 className="text-2xl font-semibold mb-3 bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
                Hey, I'm MO
              </h2>
              <p className="text-muted-foreground mb-6 leading-relaxed">
                Your capable AI partner for coding, analysis, and creative tasks
              </p>

              {/* Model and thinking badges */}
              <div className="flex items-center justify-center gap-3 flex-wrap">
                <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-zinc-900/50 border border-border/50 text-sm backdrop-blur-sm">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50 animate-pulse" />
                  <span className="text-muted-foreground">Powered by</span>
                  <span className="font-medium">{modelName}</span>
                </div>

                {/* Thinking Level Toggle */}
                <div className="relative">
                  <button
                    onClick={() => setShowThinkingMenu(!showThinkingMenu)}
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-zinc-900/50 border border-border/50 text-sm backdrop-blur-sm hover:border-violet-500/40 transition-colors"
                  >
                    <Brain className="w-4 h-4 text-violet-400" />
                    <span className="text-muted-foreground">Thinking:</span>
                    <span className="font-medium capitalize">{config?.thinking_level || 'medium'}</span>
                    <ChevronDown className="w-3 h-3 text-muted-foreground" />
                  </button>

                  {showThinkingMenu && (
                    <div
                      className="absolute top-full left-1/2 -translate-x-1/2 mt-2 w-56 bg-card border border-border rounded-xl shadow-xl z-20 py-2"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {THINKING_LEVELS.map((level) => (
                        <button
                          key={level.value}
                          onClick={() => handleThinkingLevelChange(level.value)}
                          className={`w-full text-left px-4 py-2.5 hover:bg-muted/50 transition-colors flex items-center justify-between ${
                            config?.thinking_level === level.value ? 'bg-violet-500/10' : ''
                          }`}
                        >
                          <span className="font-medium">{level.label}</span>
                          <span className="text-xs text-muted-foreground">{level.description}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Quick prompts */}
              <div className="mt-10 grid gap-3">
                <button
                  onClick={() => handleSend("Help me review my code for security issues")}
                  className="group text-left px-5 py-4 rounded-xl border border-border/50 hover:border-indigo-500/40 hover:bg-zinc-900/30 transition-all duration-300 text-sm text-muted-foreground hover:text-foreground backdrop-blur-sm hover:shadow-lg hover:shadow-indigo-500/10 hover:-translate-y-0.5"
                >
                  <span className="group-hover:text-indigo-400 transition-colors">Review my code for security issues</span>
                </button>
                <button
                  onClick={() => handleSend("Explain how this codebase is structured")}
                  className="group text-left px-5 py-4 rounded-xl border border-border/50 hover:border-violet-500/40 hover:bg-zinc-900/30 transition-all duration-300 text-sm text-muted-foreground hover:text-foreground backdrop-blur-sm hover:shadow-lg hover:shadow-violet-500/10 hover:-translate-y-0.5"
                >
                  <span className="group-hover:text-violet-400 transition-colors">Explain how this codebase is structured</span>
                </button>
                <button
                  onClick={() => handleSend("Help me write tests for my functions")}
                  className="group text-left px-5 py-4 rounded-xl border border-border/50 hover:border-purple-500/40 hover:bg-zinc-900/30 transition-all duration-300 text-sm text-muted-foreground hover:text-foreground backdrop-blur-sm hover:shadow-lg hover:shadow-purple-500/10 hover:-translate-y-0.5"
                >
                  <span className="group-hover:text-purple-400 transition-colors">Help me write tests for my functions</span>
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {messages.map((message, index) => (
              <ChatMessage
                key={message.id}
                message={message}
                isThinking={isThinking && index === messages.length - 1 && message.role === 'assistant' && !message.content}
              />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {isOrchestrating && activeSubagents.length > 0 && (
        <SubagentStatus
          tasks={activeSubagents}
          onCancel={(taskId) => {
            // Update the local state to reflect cancellation
            updateSubagent({
              id: taskId,
              agent: activeSubagents.find(t => t.id === taskId)?.agent || '',
              status: 'cancelled',
              progress: activeSubagents.find(t => t.id === taskId)?.progress || 0,
            })
          }}
        />
      )}

      <QueueIndicator queue={messageQueue} onClear={clearQueue} />

      <ChatInput
        onSend={handleSend}
        onQueue={handleQueue}
        onStop={stopGeneration}
        onCommand={handleCommand}
        isLoading={isStreaming}
        hasQueue={messageQueue.length > 0}
        placeholder="Message MO..."
      />

      {/* Toast Notifications */}
      <ToastContainer />

      {/* Status Dialog */}
      {showStatus && (
        <div
          className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4"
          onClick={() => setShowStatus(false)}
        >
          <div
            className="bg-card rounded-2xl border border-border shadow-2xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-xl font-semibold mb-4 flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-violet-500" />
              Session Status
            </h2>
            <div className="space-y-3">
              <div className="flex justify-between items-center py-2 border-b border-border/50">
                <span className="text-muted-foreground">Session ID</span>
                <span className="font-mono text-sm">{sessionId ? sessionId.slice(0, 8) + '...' : 'New session'}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-border/50">
                <span className="text-muted-foreground">Agent</span>
                <span className="px-2 py-1 rounded-full bg-violet-500/20 text-violet-400 text-sm font-medium">{agentId.toUpperCase()}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-border/50">
                <span className="text-muted-foreground">Model</span>
                <span className="font-mono text-sm">{currentModel || config?.default_model || 'claude-sonnet-4'}</span>
              </div>
              <div className="flex justify-between items-center py-2 border-b border-border/50">
                <span className="text-muted-foreground">Messages</span>
                <span>{messages.length}</span>
              </div>
              <div className="flex justify-between items-center py-2">
                <span className="text-muted-foreground">Status</span>
                <span className={`flex items-center gap-1.5 text-sm ${isStreaming ? 'text-amber-400' : 'text-emerald-400'}`}>
                  <span className={`w-2 h-2 rounded-full ${isStreaming ? 'bg-amber-400 animate-pulse' : 'bg-emerald-400'}`} />
                  {isStreaming ? 'Streaming' : 'Ready'}
                </span>
              </div>
            </div>
            <button
              onClick={() => setShowStatus(false)}
              className="mt-6 w-full py-2.5 rounded-xl bg-muted hover:bg-muted/80 transition-colors font-medium"
            >
              Close
            </button>
          </div>
        </div>
      )}

      {/* Canvas toggle button - show when artifacts exist */}
      {canvasArtifacts.length > 0 && !panelVisible && (
        <button
          onClick={togglePanel}
          className="fixed right-4 bottom-24 z-30 flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-primary-foreground shadow-lg hover:shadow-xl transition-all"
        >
          <Layers className="w-4 h-4" />
          <span className="text-sm font-medium">Canvas</span>
          <span className="text-xs px-1.5 py-0.5 rounded-full bg-primary-foreground/20">
            {canvasArtifacts.length}
          </span>
        </button>
      )}

      {/* Canvas Panel */}
      <CanvasPanel />
    </div>
  )
}
