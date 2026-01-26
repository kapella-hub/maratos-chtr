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
      onQueue(input.trim())
      setInput('')
    } else if (!isLoading) {
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
    <div className="border-t border-border/50 p-4 bg-background/80 backdrop-blur-sm">
      <div className="flex items-end gap-3 max-w-4xl mx-auto">
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isLoading ? 'Type to queue message...' : placeholder}
            rows={1}
            className={cn(
              'w-full resize-none rounded-2xl border bg-muted/50 px-4 py-3',
              'focus:outline-none focus:ring-2 focus:ring-primary/50 focus:border-primary/50 focus:bg-background',
              'placeholder:text-muted-foreground/60',
              'transition-all duration-200',
              isLoading && 'border-amber-500/30 focus:ring-amber-500/50'
            )}
          />
        </div>

        {/* Stop button */}
        {isLoading && (
          <button
            onClick={onStop}
            className={cn(
              'p-3 rounded-xl bg-red-500 text-white',
              'hover:bg-red-600 transition-all duration-200',
              'shadow-lg shadow-red-500/20',
              'flex items-center gap-2'
            )}
            title="Stop generation (Esc)"
          >
            <Square className="w-4 h-4 fill-current" />
            <span className="text-sm font-medium">Stop</span>
          </button>
        )}

        {/* Send/Queue button */}
        <button
          onClick={handleSubmit}
          disabled={!input.trim()}
          className={cn(
            'p-3 rounded-xl transition-all duration-200',
            'disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none',
            isLoading
              ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-lg shadow-amber-500/20'
              : 'bg-gradient-to-r from-violet-600 to-purple-600 text-white hover:from-violet-500 hover:to-purple-500 shadow-lg shadow-violet-500/20 hover:shadow-violet-500/30'
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

      {/* Hint text */}
      <div className="max-w-4xl mx-auto mt-2 text-center">
        <p className="text-xs text-muted-foreground/50">
          Press Enter to send, Shift+Enter for new line
        </p>
      </div>
    </div>
  )
}
