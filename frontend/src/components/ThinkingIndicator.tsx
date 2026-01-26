import { cn } from '@/lib/utils'

interface ThinkingIndicatorProps {
  className?: string
  label?: string
}

export default function ThinkingIndicator({ className, label = 'Thinking' }: ThinkingIndicatorProps) {
  return (
    <div className={cn(
      'flex items-center gap-3 p-3 rounded-lg',
      'bg-gradient-to-r from-violet-500/10 to-purple-500/10',
      'border border-violet-500/20',
      className
    )}>
      {/* Animated brain/thinking icon */}
      <div className="relative w-8 h-8 flex items-center justify-center">
        <div className="absolute inset-0 bg-violet-500/20 rounded-full animate-ping" />
        <div className="relative w-6 h-6 bg-gradient-to-br from-violet-500 to-purple-600 rounded-full flex items-center justify-center">
          <span className="text-xs">🧠</span>
        </div>
      </div>

      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-violet-400 text-sm font-medium">{label}</span>
          <div className="flex gap-1">
            <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
            <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
            <div className="w-1.5 h-1.5 bg-violet-500 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        </div>
        {/* Progress bar */}
        <div className="mt-2 h-1 bg-violet-500/20 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-violet-500 to-purple-500 rounded-full animate-pulse"
            style={{
              width: '60%',
              animation: 'thinking-progress 2s ease-in-out infinite'
            }}
          />
        </div>
      </div>
    </div>
  )
}
