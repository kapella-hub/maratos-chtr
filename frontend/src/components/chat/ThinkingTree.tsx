
import { useState } from 'react'
import { ChevronDown, ChevronRight, Terminal, CheckCircle2, AlertCircle, BrainCircuit } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ThinkingBlock, ThinkingStep } from '@/lib/api'

interface ThinkingTreeProps {
    block: Partial<ThinkingBlock>
    className?: string
}

export default function ThinkingTree({ block, className }: ThinkingTreeProps) {
    const [isExpanded, setIsExpanded] = useState(true)

    if (!block.steps || block.steps.length === 0) return null

    return (
        <div className={cn("border rounded-lg bg-card/50 overflow-hidden", className)}>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full flex items-center gap-2 p-3 text-sm font-medium bg-muted/30 hover:bg-muted/50 transition-colors"
            >
                {isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                <BrainCircuit className="w-4 h-4 text-primary" />
                <span>Thinking Process</span>
                <span className="ml-auto text-xs text-muted-foreground">
                    {block.steps.length} steps • {block.level?.toUpperCase() || 'NORMAL'}
                </span>
            </button>

            {isExpanded && (
                <div className="p-3 space-y-3 bg-background/50">
                    {block.steps.map((step, idx) => (
                        <ThinkingStepNode key={step.id || idx} step={step} />
                    ))}
                </div>
            )}
        </div>
    )
}

function ThinkingStepNode({ step }: { step: ThinkingStep }) {
    const [isOpen, setIsOpen] = useState(false)
    const isTool = step.type === 'tool_call' || step.type === 'tool_result'

    // Icon selection
    const Icon = isTool ? Terminal : (step.type === 'critique' ? AlertCircle : CheckCircle2)
    const color = isTool ? 'text-blue-500' : (step.type === 'critique' ? 'text-amber-500' : 'text-emerald-500')

    return (
        <div className="text-sm">
            <div
                className={cn(
                    "flex items-start gap-2 p-2 rounded-md cursor-pointer transition-colors",
                    "hover:bg-muted/50",
                    isOpen && "bg-muted/30"
                )}
                onClick={() => setIsOpen(!isOpen)}
            >
                <Icon className={cn("w-4 h-4 mt-0.5 shrink-0", color)} />
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                        <span className={cn("font-medium text-xs border px-1.5 rounded uppercase tracking-wider",
                            isTool ? "border-blue-200 text-blue-700 dark:border-blue-900 dark:text-blue-400" :
                                "border-emerald-200 text-emerald-700 dark:border-emerald-900 dark:text-emerald-400"
                        )}>
                            {step.type.replace('_', ' ')}
                        </span>
                        <span className="text-xs text-muted-foreground ml-auto">
                            {step.duration_ms ? `${step.duration_ms}ms` : ''}
                        </span>
                    </div>
                    <div className={cn("text-muted-foreground break-words line-clamp-2 whitespace-pre-wrap", isOpen && "line-clamp-none")}>
                        {step.content}
                    </div>
                </div>
            </div>
        </div>
    )
}
