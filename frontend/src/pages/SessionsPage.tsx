import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Trash2, MessageSquare, Clock } from 'lucide-react'
import { fetchSessions, deleteSession, fetchSession } from '@/lib/api'
import { useChatStore } from '@/stores/chat'
import { cn } from '@/lib/utils'

export default function SessionsPage() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { setSessionId, addMessage, clearMessages } = useChatStore()

  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ['sessions'],
    queryFn: fetchSessions,
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSession,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })

  const handleResumeSession = async (sessionId: string) => {
    try {
      const data = await fetchSession(sessionId)
      clearMessages()
      setSessionId(sessionId)
      // Load messages into store
      for (const msg of data.messages) {
        addMessage({
          role: msg.role as 'user' | 'assistant',
          content: msg.content,
        })
      }
      navigate('/')
    } catch (error) {
      console.error('Failed to load session:', error)
    }
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin text-4xl">⏳</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-4 border-b border-border">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="w-6 h-6" />
          History
        </h1>
        <p className="text-muted-foreground text-sm mt-1">
          Your conversations with MO
        </p>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        {sessions.length === 0 ? (
          <div className="text-center text-muted-foreground py-12">
            <MessageSquare className="w-12 h-12 mx-auto mb-4 opacity-50" />
            <p>No conversations yet</p>
            <p className="text-sm">Start chatting with MO!</p>
          </div>
        ) : (
          <div className="space-y-2 max-w-3xl">
            {sessions.map((session) => (
              <div
                key={session.id}
                onClick={() => handleResumeSession(session.id)}
                className={cn(
                  'flex items-center gap-4 p-4 rounded-lg cursor-pointer',
                  'bg-muted/50 hover:bg-muted transition-colors'
                )}
              >
                <div className="w-10 h-10 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white font-bold text-xs flex-shrink-0">
                  MO
                </div>
                
                <div className="flex-1 min-w-0">
                  <div className="font-medium truncate">
                    {session.title || 'Untitled conversation'}
                  </div>
                  <div className="flex items-center gap-2 text-sm text-muted-foreground mt-1">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {formatDate(session.updated_at)}
                    </span>
                  </div>
                </div>

                <button
                  onClick={(e) => {
                    e.stopPropagation()
                    deleteMutation.mutate(session.id)
                  }}
                  disabled={deleteMutation.isPending}
                  className={cn(
                    'p-2 rounded-lg text-muted-foreground',
                    'hover:bg-red-500/10 hover:text-red-500',
                    'transition-colors'
                  )}
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
