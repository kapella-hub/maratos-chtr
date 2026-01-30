import { ArrowDown } from 'lucide-react'
import { cn } from '@/lib/utils'

interface ScrollToBottomProps {
  visible: boolean
  onClick: () => void
  className?: string
}

export default function ScrollToBottom({ visible, onClick, className }: ScrollToBottomProps) {
  if (!visible) return null

  return (
    <button
      onClick={onClick}
      className={cn(
        'fixed z-30 p-2.5 rounded-full',
        'bg-primary/90 text-primary-foreground',
        'shadow-lg shadow-primary/30',
        'hover:bg-primary hover:shadow-xl hover:shadow-primary/40',
        'transform hover:-translate-y-0.5',
        'transition-all duration-200',
        'animate-in fade-in slide-in-from-bottom-4',
        className
      )}
      title="Scroll to bottom"
    >
      <ArrowDown className="w-4 h-4" />
    </button>
  )
}
