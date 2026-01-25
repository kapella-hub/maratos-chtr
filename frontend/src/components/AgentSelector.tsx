import { useQuery } from '@tanstack/react-query'
import { ChevronDown } from 'lucide-react'
import { fetchAgents, type Agent } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState, useRef, useEffect } from 'react'

interface AgentSelectorProps {
  value: string
  onChange: (agentId: string) => void
}

const agentColors: Record<string, string> = {
  mo: 'from-violet-500 to-purple-600',
  architect: 'from-blue-500 to-cyan-600',
  reviewer: 'from-amber-500 to-orange-600',
  'kiro-sonnet': 'from-emerald-500 to-teal-600',
  'kiro-opus': 'from-rose-500 to-pink-600',
}

export default function AgentSelector({ value, onChange }: AgentSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  const { data: agents = [] } = useQuery({
    queryKey: ['agents'],
    queryFn: fetchAgents,
  })

  const selectedAgent = agents.find((a) => a.id === value) || agents[0]

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-3 px-3 py-2 rounded-lg',
          'bg-muted hover:bg-muted/80 transition-colors',
          'text-sm font-medium'
        )}
      >
        <div className={cn(
          'w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold',
          `bg-gradient-to-br ${agentColors[selectedAgent?.id] || agentColors.mo}`
        )}>
          {selectedAgent?.icon || '🤖'}
        </div>
        <div className="text-left">
          <div className="font-medium">{selectedAgent?.name || 'MO'}</div>
          <div className="text-xs text-muted-foreground">{selectedAgent?.model?.split('-').slice(0, 2).join(' ')}</div>
        </div>
        <ChevronDown className={cn('w-4 h-4 transition-transform', isOpen && 'rotate-180')} />
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-80 bg-background border border-border rounded-lg shadow-xl z-50 overflow-hidden">
          <div className="p-2 border-b border-border bg-muted/50">
            <span className="text-xs font-medium text-muted-foreground">SELECT AGENT</span>
          </div>
          {agents.map((agent) => (
            <button
              key={agent.id}
              onClick={() => {
                onChange(agent.id)
                setIsOpen(false)
              }}
              className={cn(
                'w-full flex items-start gap-3 px-3 py-3 text-left',
                'hover:bg-muted transition-colors',
                agent.id === value && 'bg-muted'
              )}
            >
              <div className={cn(
                'w-10 h-10 rounded-full flex items-center justify-center text-white font-bold flex-shrink-0',
                `bg-gradient-to-br ${agentColors[agent.id] || agentColors.mo}`
              )}>
                {agent.icon}
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-medium">{agent.name}</span>
                  {agent.is_default && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-primary/20 text-primary">DEFAULT</span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground mt-0.5">{agent.description}</div>
                <div className="text-[10px] text-muted-foreground/70 mt-1 font-mono">{agent.model}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
