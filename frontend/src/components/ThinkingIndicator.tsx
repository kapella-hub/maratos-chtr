import { cn } from '@/lib/utils'

interface ThinkingIndicatorProps {
  className?: string
}

export default function ThinkingIndicator({ className }: ThinkingIndicatorProps) {
  return (
    <div className={cn('flex items-center gap-1.5', className)}>
      <span className="text-muted-foreground text-sm">Thinking</span>
      <div className="flex gap-1">
        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
        <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
      </div>
    </div>
  )
}
