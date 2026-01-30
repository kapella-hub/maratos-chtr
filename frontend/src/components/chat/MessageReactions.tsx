import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { playClick } from '@/lib/sounds'

interface MessageReactionsProps {
  messageId: string
  className?: string
}

type Reaction = 'up' | 'down' | null

export default function MessageReactions({ messageId, className }: MessageReactionsProps) {
  const [reaction, setReaction] = useState<Reaction>(() => {
    const stored = localStorage.getItem(`reaction-${messageId}`)
    return stored as Reaction
  })

  const handleReaction = (type: 'up' | 'down') => {
    playClick()
    const newReaction = reaction === type ? null : type
    setReaction(newReaction)
    if (newReaction) {
      localStorage.setItem(`reaction-${messageId}`, newReaction)
    } else {
      localStorage.removeItem(`reaction-${messageId}`)
    }
    // Could send to backend here for analytics
  }

  return (
    <div className={cn('flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity', className)}>
      <button
        onClick={() => handleReaction('up')}
        className={cn(
          'p-1.5 rounded-lg transition-all',
          reaction === 'up'
            ? 'bg-emerald-500/20 text-emerald-400'
            : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground'
        )}
        title="Helpful"
      >
        <ThumbsUp className="w-3.5 h-3.5" />
      </button>
      <button
        onClick={() => handleReaction('down')}
        className={cn(
          'p-1.5 rounded-lg transition-all',
          reaction === 'down'
            ? 'bg-red-500/20 text-red-400'
            : 'hover:bg-muted/50 text-muted-foreground hover:text-foreground'
        )}
        title="Not helpful"
      >
        <ThumbsDown className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
