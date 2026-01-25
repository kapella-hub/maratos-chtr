import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Square, ListPlus } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ChatInputProps {
  onSend: (message: string) => void
  onQueue?: (message: string) => void
  onStop?: () => void
  isLoading?: boolean
  hasQueue?: boolean
  placeholder?: string
}

export default function ChatInput({ 
  onSend, 
  onQueue, 
  onStop, 
  isLoading, 
  hasQueue,
  placeholder = 'Type a message...' 
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
    }
  }, [input])

  const handleSubmit = () => {
    if (!input.trim()) return
    
    if (isLoading && onQueue) {
      // Queue message if busy
      onQueue(input.trim())
      setInput('')
    } else if (!isLoading) {
      // Send directly if not busy
      onSend(input.trim())
      setInput('')
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div className="border-t border-border p-4">
      <div className="flex items-end gap-2 max-w-4xl mx-auto">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isLoading ? 'Type to queue message...' : placeholder}
            rows={1}
            className={cn(
              'w-full resize-none rounded-lg border border-input bg-background px-4 py-3',
              'focus:outline-none focus:ring-2 focus:ring-ring',
              'placeholder:text-muted-foreground',
              isLoading && 'border-amber-500/50'
            )}
          />
        </div>
        
        {/* Stop button - always visible when loading */}
        {isLoading && (
          <button
            onClick={onStop}
            className={cn(
              'p-3 rounded-lg bg-destructive text-destructive-foreground',
              'hover:bg-destructive/90 transition-colors'
            )}
            title="Stop generation"
          >
            <Square className="w-5 h-5" />
          </button>
        )}
        
        {/* Send/Queue button */}
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className={cn(
            'p-3 rounded-lg transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            isLoading 
              ? 'bg-amber-500 text-white hover:bg-amber-600' 
              : 'bg-primary text-primary-foreground hover:bg-primary/90'
          )}
          title={isLoading ? 'Add to queue' : 'Send message'}
        >
          {isLoading ? (
            <ListPlus className="w-5 h-5" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>
    </div>
  )
}
