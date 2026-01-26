import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <motion.div
      className={cn('bg-muted/50 rounded-lg', className)}
      animate={{
        opacity: [0.5, 0.8, 0.5]
      }}
      transition={{
        duration: 1.5,
        repeat: Infinity,
        ease: 'easeInOut'
      }}
    />
  )
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-4 p-6 max-w-4xl mx-auto">
      <Skeleton className="w-10 h-10 rounded-xl flex-shrink-0" />
      <div className="flex-1 space-y-3">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    </div>
  )
}

export function ChatLoadingSkeleton() {
  return (
    <div className="space-y-6">
      <MessageSkeleton />
      <MessageSkeleton />
      <MessageSkeleton />
    </div>
  )
}

export function StatusBarSkeleton() {
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 rounded-xl border border-border/50 bg-muted/20">
      <Skeleton className="w-4 h-4 rounded-full" />
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-1 flex-1" />
      <Skeleton className="w-12 h-4" />
    </div>
  )
}
