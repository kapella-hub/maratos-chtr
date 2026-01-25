import { useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import ChatInput from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import AgentSelector from '@/components/AgentSelector'
import { useChatStore } from '@/stores/chat'
import { streamChat, fetchAgents } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function ChatPage() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {
    messages,
    sessionId,
    agentId,
    isStreaming,
    setSessionId,
    setAgentId,
    addMessage,
    appendToLastMessage,
    setLastMessageAgent,
    setStreaming,
    clearMessages,
  } = useChatStore()

  // Fetch agents and set the default on initial load
  const { data: agents } = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
  })

  useEffect(() => {
    if (agents && agents.length > 0) {
      const defaultAgent = agents.find(a => a.is_default) || agents[0]
      if (defaultAgent && agentId === 'mo' && defaultAgent.id !== 'mo') {
        setAgentId(defaultAgent.id)
      }
    }
  }, [agents, agentId, setAgentId])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (content: string) => {
    addMessage({ role: 'user', content })
    addMessage({ role: 'assistant', content: '', agentId })

    setStreaming(true)

    try {
      for await (const event of streamChat(content, agentId, sessionId || undefined)) {
        if (event.type === 'session_id' && event.data) {
          setSessionId(event.data)
        } else if (event.type === 'agent' && event.data) {
          setLastMessageAgent(event.data)
        } else if (event.type === 'content' && event.data) {
          appendToLastMessage(event.data)
        }
      }
    } catch (error) {
      console.error('Chat error:', error)
      appendToLastMessage('\n\n❌ Error: Failed to get response')
    } finally {
      setStreaming(false)
    }
  }

  const agentInfo: Record<string, { gradient: string; tagline: string }> = {
    mo: { gradient: 'from-violet-500 to-purple-600', tagline: 'Your capable AI partner' },
    architect: { gradient: 'from-blue-500 to-cyan-600', tagline: 'Senior engineer for complex tasks' },
    reviewer: { gradient: 'from-amber-500 to-orange-600', tagline: 'Code quality guardian' },
    'kiro-sonnet': { gradient: 'from-emerald-500 to-teal-600', tagline: 'Claude Sonnet 4 via Kiro CLI' },
    'kiro-opus': { gradient: 'from-rose-500 to-pink-600', tagline: 'Claude Opus 4.5 via Kiro CLI' },
  }

  const current = agentInfo[agentId] || agentInfo.mo

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <AgentSelector value={agentId} onChange={setAgentId} />
        
        <button
          onClick={clearMessages}
          className={cn(
            'flex items-center gap-2 px-3 py-2 rounded-lg',
            'bg-secondary text-secondary-foreground',
            'hover:bg-secondary/80 transition-colors',
            'text-sm font-medium'
          )}
        >
          <Plus className="w-4 h-4" />
          New Chat
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center max-w-md">
              <div className={cn(
                'w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4',
                `bg-gradient-to-br ${current.gradient}`
              )}>
                {agentId === 'mo' ? 'MO' : agentId === 'architect' ? '🏗️' : '🔍'}
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">
                {agentId === 'mo' ? "Hey, I'm MO" : agentId === 'architect' ? "Architect Mode" : "Reviewer Mode"}
              </h2>
              <p className="text-sm">{current.tagline}</p>
              {agentId !== 'mo' && (
                <p className="text-xs mt-2 text-muted-foreground/70">
                  Using Claude Opus for maximum quality
                </p>
              )}
            </div>
          </div>
        ) : (
          <div className="max-w-4xl mx-auto">
            {messages.map((message) => (
              <ChatMessage key={message.id} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      <ChatInput
        onSend={handleSend}
        isLoading={isStreaming}
        placeholder={`Message ${agentId === 'mo' ? 'MO' : agentId === 'architect' ? 'Architect' : 'Reviewer'}...`}
      />
    </div>
  )
}
