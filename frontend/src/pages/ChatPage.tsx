import { useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Sparkles } from 'lucide-react'
import ChatInput from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import SubagentStatus from '@/components/SubagentStatus'
import QueueIndicator from '@/components/QueueIndicator'
import AgentStatusBar from '@/components/AgentStatusBar'
import ToastContainer from '@/components/ToastContainer'
import { useChatStore } from '@/stores/chat'
import { useToastStore } from '@/stores/toast'
import { streamChat, fetchConfig } from '@/lib/api'
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
  } = useChatStore()

  const { addToast } = useToastStore()

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
      saveChatSession(sessionId, messages)
    }
  }, [sessionId, messages, isStreaming])

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
          setSessionId(event.data as string)
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

  // Load session from history when sessionId changes (from sidebar)
  useEffect(() => {
    if (sessionId && messages.length === 0) {
      const session = getChatSession(sessionId)
      if (session) {
        session.messages.forEach(msg => {
          addMessage({
            role: msg.role,
            content: msg.content,
            agentId: msg.agentId,
          })
        })
      }
    }
  }, [sessionId])

  const modelName = formatModelName(config?.default_model || 'claude-sonnet-4')

  return (
    <div className="flex flex-col h-full relative">
      {/* Progress bar */}
      {(isThinking || isModelThinking || isStreaming) && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-muted overflow-hidden z-50">
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

              {/* Model badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-zinc-900/50 border border-border/50 text-sm backdrop-blur-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-500 shadow-sm shadow-emerald-500/50 animate-pulse" />
                <span className="text-muted-foreground">Powered by</span>
                <span className="font-medium">{modelName}</span>
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
        isLoading={isStreaming}
        hasQueue={messageQueue.length > 0}
        placeholder="Message MO..."
      />

      {/* Toast Notifications */}
      <ToastContainer />
    </div>
  )
}
