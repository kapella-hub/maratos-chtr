import { useRef, useEffect } from 'react'
import { Plus } from 'lucide-react'
import ChatInput from '@/components/ChatInput'
import ChatMessage from '@/components/ChatMessage'
import { useChatStore } from '@/stores/chat'
import { streamChat } from '@/lib/api'
import { cn } from '@/lib/utils'

export default function ChatPage() {
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const {
    messages,
    sessionId,
    isStreaming,
    setSessionId,
    addMessage,
    appendToLastMessage,
    setStreaming,
    clearMessages,
  } = useChatStore()

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async (content: string) => {
    // Add user message
    addMessage({ role: 'user', content })

    // Add empty assistant message for streaming
    addMessage({ role: 'assistant', content: '' })

    setStreaming(true)

    try {
      for await (const event of streamChat(content, sessionId || undefined)) {
        if (event.type === 'session_id' && event.data) {
          setSessionId(event.data)
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

  const handleNewChat = () => {
    clearMessages()
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-bold">
            MO
          </div>
          <div>
            <h2 className="font-semibold">MO</h2>
            <p className="text-xs text-muted-foreground">Your AI partner</p>
          </div>
        </div>
        
        <button
          onClick={handleNewChat}
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

      {/* Messages */}
      <div className="flex-1 overflow-y-auto">
        {messages.length === 0 ? (
          <div className="flex items-center justify-center h-full text-muted-foreground">
            <div className="text-center max-w-md">
              <div className="w-20 h-20 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-2xl font-bold mx-auto mb-4">
                MO
              </div>
              <h2 className="text-xl font-semibold text-foreground mb-2">Hey, I'm MO</h2>
              <p className="text-sm">
                Your capable AI partner. I can help with coding, research, file operations, 
                and pretty much anything you throw at me. What's on your mind?
              </p>
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

      {/* Input */}
      <ChatInput
        onSend={handleSend}
        isLoading={isStreaming}
        placeholder="Message MO..."
      />
    </div>
  )
}
