import { useRef, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Sparkles } from 'lucide-react'
import ChatInput from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import SubagentStatus from '@/components/SubagentStatus'
import QueueIndicator from '@/components/QueueIndicator'
import { useChatStore } from '@/stores/chat'
import { streamChat, fetchConfig } from '@/lib/api'
import { cn } from '@/lib/utils'

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
    isStreaming,
    isThinking,
    isModelThinking,
    isOrchestrating,
    activeSubagents,
    setSessionId,
    setAgentId,
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
    clearMessages,
    enqueueMessage,
    dequeueMessage,
    clearQueue,
  } = useChatStore()

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
      } else {
        console.error('Chat error:', error)
        appendToLastMessage('\n\n❌ Error: Failed to get response')
      }
    } finally {
      setStreaming(false)
      setThinking(false)
      setModelThinking(false)
      setAbortController(null)
      clearSubagents()
    }
  }, [agentId, sessionId, addMessage, appendToLastMessage, setSessionId, setLastMessageAgent, setStreaming, setThinking, setModelThinking, setOrchestrating, updateSubagent, clearSubagents, setAbortController])

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

  const modelName = formatModelName(config?.default_model || 'claude-sonnet-4')

  return (
    <div className="flex flex-col h-full relative">
      {/* Progress bar */}
      {(isThinking || isModelThinking || isStreaming) && (
        <div className="absolute top-0 left-0 right-0 h-0.5 bg-muted overflow-hidden z-50">
          <div
            className="h-full bg-gradient-to-r from-violet-500 via-purple-500 to-violet-500"
            style={{
              animation: 'progress 1.5s ease-in-out infinite',
              width: '100%',
            }}
          />
        </div>
      )}

      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-border/50 bg-background/80 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-sm font-bold shadow-md shadow-violet-500/20">
            MO
          </div>
          <div>
            <div className="font-medium text-sm">MO</div>
            <div className="text-xs text-muted-foreground">
              {modelName}
            </div>
          </div>
        </div>

        <button
          onClick={clearMessages}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-xl',
            'bg-secondary hover:bg-secondary/80',
            'transition-all duration-200',
            'text-sm font-medium'
          )}
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </header>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-md px-4">
              {/* Hero */}
              <div className="relative mb-8">
                <div className="w-24 h-24 rounded-3xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-3xl font-bold mx-auto shadow-2xl shadow-violet-500/30">
                  MO
                </div>
                <div className="absolute -bottom-2 -right-2 w-8 h-8 rounded-full bg-gradient-to-br from-emerald-400 to-emerald-500 flex items-center justify-center shadow-lg">
                  <Sparkles className="w-4 h-4 text-white" />
                </div>
              </div>

              <h2 className="text-2xl font-semibold mb-2">
                Hey, I'm MO
              </h2>
              <p className="text-muted-foreground mb-4">
                Your capable AI partner for coding, analysis, and creative tasks
              </p>

              {/* Model badge */}
              <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-muted/50 border border-border/50 text-sm">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-muted-foreground">Powered by</span>
                <span className="font-medium">{modelName}</span>
              </div>

              {/* Quick prompts */}
              <div className="mt-8 grid gap-2">
                <button
                  onClick={() => handleSend("Help me review my code for security issues")}
                  className="text-left px-4 py-3 rounded-xl border border-border/50 hover:border-primary/30 hover:bg-muted/50 transition-all text-sm text-muted-foreground hover:text-foreground"
                >
                  Review my code for security issues
                </button>
                <button
                  onClick={() => handleSend("Explain how this codebase is structured")}
                  className="text-left px-4 py-3 rounded-xl border border-border/50 hover:border-primary/30 hover:bg-muted/50 transition-all text-sm text-muted-foreground hover:text-foreground"
                >
                  Explain how this codebase is structured
                </button>
                <button
                  onClick={() => handleSend("Help me write tests for my functions")}
                  className="text-left px-4 py-3 rounded-xl border border-border/50 hover:border-primary/30 hover:bg-muted/50 transition-all text-sm text-muted-foreground hover:text-foreground"
                >
                  Help me write tests for my functions
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
    </div>
  )
}
