import { motion } from 'framer-motion'
import { Brain, Zap, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'

interface StatusPillProps {
  status: 'thinking' | 'streaming' | 'orchestrating' | 'idle'
  message?: string | null
  className?: string
}

export default function StatusPill({ status, message, className }: StatusPillProps) {
  if (status === 'idle') return null

  const statusConfig = {
    thinking: {
      icon: Brain,
      label: 'Thinking',
      className: 'status-pill-thinking',
      animate: true,
    },
    streaming: {
      icon: Zap,
      label: 'Responding',
      className: 'status-pill-streaming',
      animate: false,
    },
    orchestrating: {
      icon: Loader2,
      label: 'Orchestrating',
      className: 'status-pill-thinking',
      animate: true,
    },
  }

  const config = statusConfig[status]
  const Icon = config.icon

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn('status-pill', config.className, className)}
    >
      <Icon
        className={cn(
          'w-4 h-4',
          config.animate && 'animate-spin'
        )}
      />
      <span className="font-medium">{message || config.label}</span>
      <motion.span
        className="flex gap-0.5"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
      >
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="w-1 h-1 rounded-full bg-current"
            animate={{ opacity: [0.3, 1, 0.3] }}
            transition={{
              duration: 1,
              repeat: Infinity,
              delay: i * 0.2,
            }}
          />
        ))}
      </motion.span>
    </motion.div>
  )
}
