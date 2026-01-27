import { create } from 'zustand'

export interface CanvasArtifact {
  id: string
  type: 'code' | 'preview' | 'form' | 'chart' | 'diagram' | 'table' | 'diff' | 'terminal' | 'markdown'
  title: string
  content: string
  metadata?: {
    language?: string
    editable?: boolean
  }
  createdAt?: string
}

interface CanvasState {
  artifacts: CanvasArtifact[]
  activeArtifactId: string | null
  panelVisible: boolean
  panelWidth: number

  // Actions
  addArtifact: (artifact: CanvasArtifact) => void
  updateArtifact: (id: string, updates: Partial<CanvasArtifact>) => void
  removeArtifact: (id: string) => void
  setActiveArtifact: (id: string | null) => void
  togglePanel: () => void
  showPanel: () => void
  hidePanel: () => void
  setPanelWidth: (width: number) => void
  clearArtifacts: () => void
}

export const useCanvasStore = create<CanvasState>((set) => ({
  artifacts: [],
  activeArtifactId: null,
  panelVisible: false,
  panelWidth: 450,

  addArtifact: (artifact) =>
    set((state) => {
      // Auto-show panel when first artifact is added
      const shouldShow = state.artifacts.length === 0
      return {
        artifacts: [...state.artifacts, artifact],
        activeArtifactId: artifact.id,
        panelVisible: shouldShow || state.panelVisible,
      }
    }),

  updateArtifact: (id, updates) =>
    set((state) => ({
      artifacts: state.artifacts.map((a) =>
        a.id === id ? { ...a, ...updates } : a
      ),
    })),

  removeArtifact: (id) =>
    set((state) => {
      const newArtifacts = state.artifacts.filter((a) => a.id !== id)
      return {
        artifacts: newArtifacts,
        activeArtifactId:
          state.activeArtifactId === id
            ? newArtifacts[0]?.id || null
            : state.activeArtifactId,
        panelVisible: newArtifacts.length > 0 && state.panelVisible,
      }
    }),

  setActiveArtifact: (id) => set({ activeArtifactId: id }),

  togglePanel: () => set((state) => ({ panelVisible: !state.panelVisible })),

  showPanel: () => set({ panelVisible: true }),

  hidePanel: () => set({ panelVisible: false }),

  setPanelWidth: (width) => set({ panelWidth: Math.max(300, Math.min(800, width)) }),

  clearArtifacts: () =>
    set({
      artifacts: [],
      activeArtifactId: null,
      panelVisible: false,
    }),
}))
