import { create } from 'zustand'
import type { Approval } from '@/lib/api'

interface ApprovalsState {
  approvals: Approval[]
  pendingCount: number
  panelVisible: boolean
  activeApprovalId: string | null
  isLoading: boolean
  error: string | null

  // Actions
  setApprovals: (approvals: Approval[]) => void
  addApproval: (approval: Approval) => void
  updateApproval: (id: string, updates: Partial<Approval>) => void
  removeApproval: (id: string) => void
  setPendingCount: (count: number) => void
  setActiveApproval: (id: string | null) => void
  togglePanel: () => void
  showPanel: () => void
  hidePanel: () => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  clearApprovals: () => void
}

export const useApprovalsStore = create<ApprovalsState>((set) => ({
  approvals: [],
  pendingCount: 0,
  panelVisible: false,
  activeApprovalId: null,
  isLoading: false,
  error: null,

  setApprovals: (approvals) =>
    set({
      approvals,
      pendingCount: approvals.filter((a) => a.status === 'pending').length,
    }),

  addApproval: (approval) =>
    set((state) => {
      // Don't add duplicates
      if (state.approvals.some((a) => a.id === approval.id)) {
        return state
      }
      const newApprovals = [approval, ...state.approvals]
      const shouldShow = approval.status === 'pending'
      return {
        approvals: newApprovals,
        pendingCount: newApprovals.filter((a) => a.status === 'pending').length,
        activeApprovalId: shouldShow ? approval.id : state.activeApprovalId,
        panelVisible: shouldShow || state.panelVisible,
      }
    }),

  updateApproval: (id, updates) =>
    set((state) => {
      const newApprovals = state.approvals.map((a) =>
        a.id === id ? { ...a, ...updates } : a
      )
      return {
        approvals: newApprovals,
        pendingCount: newApprovals.filter((a) => a.status === 'pending').length,
      }
    }),

  removeApproval: (id) =>
    set((state) => {
      const newApprovals = state.approvals.filter((a) => a.id !== id)
      return {
        approvals: newApprovals,
        pendingCount: newApprovals.filter((a) => a.status === 'pending').length,
        activeApprovalId:
          state.activeApprovalId === id
            ? newApprovals[0]?.id || null
            : state.activeApprovalId,
      }
    }),

  setPendingCount: (count) => set({ pendingCount: count }),

  setActiveApproval: (id) => set({ activeApprovalId: id }),

  togglePanel: () => set((state) => ({ panelVisible: !state.panelVisible })),

  showPanel: () => set({ panelVisible: true }),

  hidePanel: () => set({ panelVisible: false }),

  setLoading: (loading) => set({ isLoading: loading }),

  setError: (error) => set({ error }),

  clearApprovals: () =>
    set({
      approvals: [],
      pendingCount: 0,
      activeApprovalId: null,
    }),
}))
