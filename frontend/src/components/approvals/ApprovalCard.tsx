import { useState } from 'react'
import { motion } from 'framer-motion'
import {
  FileEdit,
  Trash2,
  Terminal,
  Check,
  X,
  ChevronDown,
  ChevronRight,
  Clock,
  AlertCircle,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Approval } from '@/lib/api'

interface ApprovalCardProps {
  approval: Approval
  isActive: boolean
  onSelect: () => void
  onApprove: (note?: string) => Promise<void>
  onDeny: (reason?: string) => Promise<void>
  isProcessing?: boolean
}

export default function ApprovalCard({
  approval,
  isActive,
  onSelect,
  onApprove,
  onDeny,
  isProcessing = false,
}: ApprovalCardProps) {
  const [expanded, setExpanded] = useState(true)
  const [denyReason, setDenyReason] = useState('')
  const [showDenyInput, setShowDenyInput] = useState(false)

  const isPending = approval.status === 'pending'
  const isResolved = approval.status !== 'pending'

  const getIcon = () => {
    switch (approval.action_type) {
      case 'write':
        return <FileEdit className="w-4 h-4" />
      case 'delete':
        return <Trash2 className="w-4 h-4" />
      case 'shell':
        return <Terminal className="w-4 h-4" />
      default:
        return <AlertCircle className="w-4 h-4" />
    }
  }

  const getStatusColor = () => {
    switch (approval.status) {
      case 'pending':
        return 'bg-amber-500/10 border-amber-500/30 text-amber-400'
      case 'approved':
        return 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
      case 'denied':
        return 'bg-red-500/10 border-red-500/30 text-red-400'
      case 'expired':
        return 'bg-gray-500/10 border-gray-500/30 text-gray-400'
      default:
        return 'bg-muted border-border text-muted-foreground'
    }
  }

  const getActionLabel = () => {
    switch (approval.action_type) {
      case 'write':
        return `Write to ${approval.file_path?.split('/').pop() || 'file'}`
      case 'delete':
        return `Delete ${approval.file_path?.split('/').pop() || 'file'}`
      case 'shell':
        return 'Run shell command'
      default:
        return 'Unknown action'
    }
  }

  const handleApprove = async () => {
    await onApprove()
  }

  const handleDeny = async () => {
    if (showDenyInput && denyReason.trim()) {
      await onDeny(denyReason.trim())
      setDenyReason('')
      setShowDenyInput(false)
    } else if (!showDenyInput) {
      setShowDenyInput(true)
    } else {
      await onDeny()
      setShowDenyInput(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'rounded-xl border transition-all duration-200',
        isActive ? 'ring-2 ring-primary/50' : '',
        getStatusColor()
      )}
    >
      {/* Header */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => {
          onSelect()
          setExpanded(!expanded)
        }}
      >
        <div className="p-2 rounded-lg bg-background/50">{getIcon()}</div>
        <div className="flex-1 min-w-0">
          <div className="font-medium text-sm truncate">{getActionLabel()}</div>
          <div className="text-xs text-muted-foreground flex items-center gap-2">
            <span className="truncate">Agent: {approval.agent_id}</span>
            {isPending && (
              <span className="flex items-center gap-1 text-amber-400">
                <Clock className="w-3 h-3" />
                Pending
              </span>
            )}
          </div>
        </div>
        <button className="p-1 hover:bg-background/50 rounded">
          {expanded ? (
            <ChevronDown className="w-4 h-4" />
          ) : (
            <ChevronRight className="w-4 h-4" />
          )}
        </button>
      </div>

      {/* Expanded content */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3">
          {/* File path */}
          {approval.file_path && (
            <div className="text-xs">
              <span className="text-muted-foreground">Path: </span>
              <code className="bg-background/50 px-1.5 py-0.5 rounded text-foreground">
                {approval.file_path}
              </code>
            </div>
          )}

          {/* Shell command */}
          {approval.command && (
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Command:</span>
              <pre className="text-xs bg-background/50 p-3 rounded-lg overflow-x-auto">
                <code>{approval.command}</code>
              </pre>
              {approval.workdir && (
                <div className="text-xs text-muted-foreground">
                  Working directory: {approval.workdir}
                </div>
              )}
            </div>
          )}

          {/* Diff preview */}
          {approval.diff && (
            <div className="space-y-1">
              <span className="text-xs text-muted-foreground">Changes:</span>
              <pre className="text-xs bg-background/50 p-3 rounded-lg overflow-x-auto max-h-64 overflow-y-auto font-mono">
                {approval.diff.split('\n').map((line, i) => (
                  <div
                    key={i}
                    className={cn(
                      line.startsWith('+') && !line.startsWith('+++')
                        ? 'text-emerald-400 bg-emerald-500/10'
                        : line.startsWith('-') && !line.startsWith('---')
                        ? 'text-red-400 bg-red-500/10'
                        : line.startsWith('@@')
                        ? 'text-blue-400'
                        : 'text-muted-foreground'
                    )}
                  >
                    {line}
                  </div>
                ))}
              </pre>
            </div>
          )}

          {/* Resolution info */}
          {isResolved && (
            <div className="text-xs text-muted-foreground">
              {approval.status === 'approved' && (
                <span>
                  Approved by {approval.approved_by}
                  {approval.approval_note && `: ${approval.approval_note}`}
                </span>
              )}
              {approval.status === 'denied' && (
                <span>
                  Denied
                  {approval.approval_note && `: ${approval.approval_note}`}
                </span>
              )}
              {approval.status === 'expired' && <span>Request expired</span>}
            </div>
          )}

          {/* Deny reason input */}
          {showDenyInput && isPending && (
            <div className="space-y-2">
              <input
                type="text"
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                placeholder="Reason for denial (optional)"
                className="w-full px-3 py-2 text-sm rounded-lg bg-background/50 border border-border/50 focus:outline-none focus:ring-2 focus:ring-primary/50"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleDeny()
                  if (e.key === 'Escape') setShowDenyInput(false)
                }}
              />
            </div>
          )}

          {/* Action buttons */}
          {isPending && (
            <div className="flex items-center gap-2 pt-2">
              <button
                onClick={handleApprove}
                disabled={isProcessing}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg',
                  'bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400',
                  'border border-emerald-500/30 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <Check className="w-4 h-4" />
                Approve
              </button>
              <button
                onClick={handleDeny}
                disabled={isProcessing}
                className={cn(
                  'flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg',
                  'bg-red-500/20 hover:bg-red-500/30 text-red-400',
                  'border border-red-500/30 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <X className="w-4 h-4" />
                {showDenyInput ? 'Confirm Deny' : 'Deny'}
              </button>
            </div>
          )}
        </div>
      )}
    </motion.div>
  )
}
