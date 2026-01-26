import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { Brain, Sparkles } from 'lucide-react'

interface ThinkingIndicatorProps {
  className?: string
  label?: string
  variant?: 'default' | 'minimal' | 'card'
}

export default function ThinkingIndicator({
  className,
  label = 'Thinking',
  variant = 'default'
}: ThinkingIndicatorProps) {

  if (variant === 'minimal') {
    return (
      <div className={cn('flex items-center gap-2', className)}>
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 2, repeat: Infinity, ease: 'linear' }}
          className="text-violet-500"
        >
          <Sparkles className="w-4 h-4" />
        </motion.div>
        <span className="text-sm text-muted-foreground">{label}</span>
        <div className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.div
              key={i}
              className="w-1.5 h-1.5 bg-violet-500 rounded-full"
              animate={{ y: [0, -4, 0] }}
              transition={{
                duration: 0.6,
                repeat: Infinity,
                delay: i * 0.15,
              }}
            />
          ))}
        </div>
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'flex items-center gap-4 p-4 rounded-2xl',
        'bg-gradient-to-r from-violet-500/10 via-purple-500/10 to-pink-500/10',
        'border border-violet-500/20',
        'shadow-lg shadow-violet-500/5',
        className
      )}
    >
      {/* Animated icon */}
      <div className="relative">
        {/* Outer ring */}
        <motion.div
          className="absolute inset-0 rounded-full bg-violet-500/20"
          animate={{ scale: [1, 1.2, 1], opacity: [0.5, 0.2, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        />
        {/* Inner circle */}
        <motion.div
          className="relative w-12 h-12 rounded-xl bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/30"
          animate={{ rotate: [0, 5, -5, 0] }}
          transition={{ duration: 4, repeat: Infinity }}
        >
          <Brain className="w-6 h-6 text-white" />
        </motion.div>
      </div>

      <div className="flex-1 min-w-0">
        {/* Label with dots */}
        <div className="flex items-center gap-2 mb-2">
          <span className="text-violet-400 font-medium">{label}</span>
          <div className="flex gap-1">
            {[0, 1, 2].map((i) => (
              <motion.div
                key={i}
                className="w-2 h-2 bg-violet-500 rounded-full"
                animate={{ y: [0, -5, 0], opacity: [0.5, 1, 0.5] }}
                transition={{
                  duration: 0.8,
                  repeat: Infinity,
                  delay: i * 0.2,
                }}
              />
            ))}
          </div>
        </div>

        {/* Animated progress bar */}
        <div className="h-1.5 bg-violet-500/20 rounded-full overflow-hidden">
          <motion.div
            className="h-full bg-gradient-to-r from-violet-500 via-purple-500 to-pink-500 rounded-full"
            animate={{ x: ['-100%', '100%'] }}
            transition={{
              duration: 1.5,
              repeat: Infinity,
              ease: 'easeInOut',
            }}
            style={{ width: '50%' }}
          />
        </div>

        {/* Status text */}
        <motion.p
          className="text-xs text-muted-foreground mt-2"
          animate={{ opacity: [0.5, 1, 0.5] }}
          transition={{ duration: 2, repeat: Infinity }}
        >
          Processing your request...
        </motion.p>
      </div>
    </motion.div>
  )
}

// Compact thinking dots for inline use
export function ThinkingDots({ className }: { className?: string }) {
  return (
    <div className={cn('inline-flex items-center gap-1', className)}>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-1.5 h-1.5 bg-current rounded-full"
          animate={{ y: [0, -3, 0] }}
          transition={{
            duration: 0.5,
            repeat: Infinity,
            delay: i * 0.1,
          }}
        />
      ))}
    </div>
  )
}
