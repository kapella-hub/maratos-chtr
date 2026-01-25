import { useRef, useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Plus, Settings } from 'lucide-react'
import { Link } from 'react-router-dom'
import ChatInput from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import ThinkingIndicator from '@/components/ThinkingIndicator'
import { useChatStore } from '@/stores/chat'
import { streamChat, fetchConfig } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function ChatPage() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {
    messages,
    sessionId,
    agentId,
    isStreaming,
    isThinking,
    setSessionId,
    setAgentId,
    addMessage,
    appendToLastMessage,
    setLastMessageAgent,
    setStreaming,
    setThinking,
    stopGeneration,
    clearMessages,
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

  const handleSend = async (content: string) => {
    addMessage({ role: 'user', content })
    addMessage({ role: 'assistant', content: '', agentId })

    setStreaming(true)
    setThinking(true)

    try {
      for await (const event of streamChat(content, agentId, sessionId || undefined)) {
        if (event.type === 'session_id' && event.data) {
          setSessionId(event.data as string)
        } else if (event.type === 'agent' && event.data) {
          setLastMessageAgent(event.data as string)
        } else if (event.type === 'thinking') {
          setThinking(event.data as boolean)
        } else if (event.type === 'content' && event.data) {
          appendToLastMessage(event.data as string)
        }
      }
    } catch (error) {
      console.error('Chat error:', error)
      appendToLastMessage('\n\n❌ Error: Failed to get response')
    } finally {
      setStreaming(false)
      setThinking(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <Link
          to="/settings"
          className="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-muted transition-colors"
        >
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
            MO
          </div>
          <div className="text-left">
            <div className="font-medium text-sm">MO</div>
            <div className="text-xs text-muted-foreground">
              {config?.default_model || 'claude-sonnet-4'}
            </div>
          </div>
          <Settings className="w-4 h-4 text-muted-foreground" />
        </Link>
        
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
              <div className="w-20 h-20 rounded-full flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4 bg-gradient-to-br from-violet-500 to-purple-600">
                MO
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">
                Hey, I'm MO
              </h2>
              <p className="text-sm">Your capable AI partner</p>
              <p className="text-xs mt-2 text-muted-foreground/70">
                Powered by {config?.default_model || 'claude-sonnet-4'}
              </p>
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

      <ChatInput
        onSend={handleSend}
        onStop={stopGeneration}
        isLoading={isStreaming}
        placeholder="Message MO..."
      />
    </div>
  )
}
