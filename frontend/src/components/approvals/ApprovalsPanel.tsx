import { useRef, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { ShieldCheck, PanelRightClose, Trash2, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useApprovalsStore } from '@/stores/approvals'
import { useChatStore } from '@/stores/chat'
import {
  fetchPendingApprovals,
  approveAction,
  denyAction,
  subscribeToApprovals,
  type Approval,
} from '@/lib/api'
import ApprovalCard from './ApprovalCard'

interface ApprovalsPanelProps {
  className?: string
}

export default function ApprovalsPanel({ className }: ApprovalsPanelProps) {
  const {
    approvals,
    pendingCount,
    panelVisible,
    activeApprovalId,
    isLoading,
    setApprovals,
    addApproval,
    updateApproval,
    setActiveApproval,
    hidePanel,
    setLoading,
    clearApprovals,
  } = useApprovalsStore()

  const { sessionId } = useChatStore()
  const [processingId, setProcessingId] = useState<string | null>(null)
  const panelRef = useRef<HTMLDivElement>(null)

  // Fetch initial approvals and subscribe to updates
  useEffect(() => {
    if (!panelVisible) return

    const loadApprovals = async () => {
      setLoading(true)
      try {
        const response = await fetchPendingApprovals(sessionId || undefined)
        setApprovals(response.approvals)
      } catch (error) {
        console.error('Failed to fetch approvals:', error)
      } finally {
        setLoading(false)
      }
    }

    loadApprovals()

    // Subscribe to real-time updates
    const unsubscribe = subscribeToApprovals(
      sessionId || undefined,
      (approval) => {
        // New approval requested
        addApproval(approval)
      },
      (approval) => {
        // Approval resolved
        updateApproval(approval.id, approval)
      }
    )

    return () => {
      unsubscribe()
    }
  }, [panelVisible, sessionId, setApprovals, addApproval, updateApproval, setLoading])

  // Handle approve action
  const handleApprove = async (approval: Approval, note?: string) => {
    setProcessingId(approval.id)
    try {
      const result = await approveAction(approval.id, { note })
      updateApproval(approval.id, { status: result.new_status as Approval['status'] })
    } catch (error) {
      console.error('Failed to approve:', error)
    } finally {
      setProcessingId(null)
    }
  }

  // Handle deny action
  const handleDeny = async (approval: Approval, reason?: string) => {
    setProcessingId(approval.id)
    try {
      const result = await denyAction(approval.id, { reason })
      updateApproval(approval.id, { status: result.new_status as Approval['status'] })
    } catch (error) {
      console.error('Failed to deny:', error)
    } finally {
      setProcessingId(null)
    }
  }

  // Refresh approvals
  const handleRefresh = async () => {
    setLoading(true)
    try {
      const response = await fetchPendingApprovals(sessionId || undefined)
      setApprovals(response.approvals)
    } catch (error) {
      console.error('Failed to refresh approvals:', error)
    } finally {
      setLoading(false)
    }
  }

  if (!panelVisible) {
    return null
  }

  const pendingApprovals = approvals.filter((a) => a.status === 'pending')
  const resolvedApprovals = approvals.filter((a) => a.status !== 'pending')

  return (
    <AnimatePresence>
      <motion.div
        ref={panelRef}
        initial={{ x: 400, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        exit={{ x: 400, opacity: 0 }}
        transition={{ type: 'spring', damping: 25, stiffness: 300 }}
        className={cn(
          'fixed right-0 top-0 bottom-0 z-40 w-[400px]',
          'bg-background/95 backdrop-blur-xl',
          'border-l border-border/50',
          'flex flex-col',
          'shadow-2xl shadow-black/20',
          className
        )}
      >
        {/* Header */}
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border/50 bg-muted/30">
          <ShieldCheck className="w-5 h-5 text-amber-400" />
          <h2 className="font-semibold flex-1">Approvals</h2>
          {pendingCount > 0 && (
            <span className="text-xs px-2 py-1 rounded-full bg-amber-500/20 text-amber-400 border border-amber-500/30">
              {pendingCount} pending
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={isLoading}
            className={cn(
              'p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors',
              isLoading && 'animate-spin'
            )}
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          {approvals.length > 0 && (
            <button
              onClick={clearApprovals}
              className="p-1.5 rounded-lg hover:bg-destructive/10 text-muted-foreground hover:text-destructive transition-colors"
              title="Clear all"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={hidePanel}
            className="p-1.5 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
            title="Close panel"
          >
            <PanelRightClose className="w-4 h-4" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {isLoading && approvals.length === 0 ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-primary border-t-transparent rounded-full animate-spin" />
            </div>
          ) : approvals.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShieldCheck className="w-12 h-12 mx-auto mb-4 opacity-30" />
              <p className="text-sm">No pending approvals</p>
              <p className="text-xs mt-1">
                High-impact actions will appear here for review
              </p>
            </div>
          ) : (
            <>
              {/* Pending approvals */}
              {pendingApprovals.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Pending Review ({pendingApprovals.length})
                  </h3>
                  <AnimatePresence>
                    {pendingApprovals.map((approval) => (
                      <ApprovalCard
                        key={approval.id}
                        approval={approval}
                        isActive={activeApprovalId === approval.id}
                        onSelect={() => setActiveApproval(approval.id)}
                        onApprove={(note) => handleApprove(approval, note)}
                        onDeny={(reason) => handleDeny(approval, reason)}
                        isProcessing={processingId === approval.id}
                      />
                    ))}
                  </AnimatePresence>
                </div>
              )}

              {/* Resolved approvals */}
              {resolvedApprovals.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
                    Recently Resolved ({resolvedApprovals.length})
                  </h3>
                  <AnimatePresence>
                    {resolvedApprovals.slice(0, 5).map((approval) => (
                      <ApprovalCard
                        key={approval.id}
                        approval={approval}
                        isActive={activeApprovalId === approval.id}
                        onSelect={() => setActiveApproval(approval.id)}
                        onApprove={() => Promise.resolve()}
                        onDeny={() => Promise.resolve()}
                        isProcessing={false}
                      />
                    ))}
                  </AnimatePresence>
                </div>
              )}
            </>
          )}
        </div>
      </motion.div>
    </AnimatePresence>
  )
}
