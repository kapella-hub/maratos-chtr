import { cn } from '@/lib/utils'

interface SkeletonProps {
  className?: string
}

export function Skeleton({ className }: SkeletonProps) {
  return (
    <div className={cn('animate-pulse rounded-md bg-muted/50', className)} />
  )
}

export function MessageSkeleton() {
  return (
    <div className="flex gap-3 p-4 animate-in fade-in duration-300">
      <Skeleton className="w-8 h-8 rounded-lg shrink-0" />
      <div className="flex-1 space-y-2">
        <Skeleton className="h-4 w-24" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
      </div>
    </div>
  )
}

export function ChatLoadingSkeleton() {
  return (
    <div className="space-y-1">
      {[1, 2, 3].map((i) => (
        <MessageSkeleton key={i} />
      ))}
    </div>
  )
}

export function HeaderSkeleton() {
  return (
    <div className="h-12 flex items-center justify-between px-4 border-b border-border/30">
      <Skeleton className="w-32 h-8" />
      <div className="flex gap-2">
        <Skeleton className="w-24 h-7" />
        <Skeleton className="w-20 h-7" />
      </div>
      <div className="flex gap-1">
        <Skeleton className="w-8 h-8 rounded-lg" />
        <Skeleton className="w-8 h-8 rounded-lg" />
      </div>
    </div>
  )
}
