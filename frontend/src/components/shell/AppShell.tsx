import { useState, useEffect, useCallback } from 'react'
import { Outlet } from 'react-router-dom'
import MinimalHeader from './MinimalHeader'
import HistoryDrawer from './HistoryDrawer'
import CommandPalette from '@/components/CommandPalette'
import { CanvasPanel } from '@/components/canvas'
import { useCanvasStore } from '@/stores/canvas'

interface AppShellProps {
  children?: React.ReactNode
  showHeader?: boolean
}

export default function AppShell({ children, showHeader = true }: AppShellProps) {
  const [historyOpen, setHistoryOpen] = useState(false)
  const [commandOpen, setCommandOpen] = useState(false)
  const { panelVisible, panelWidth } = useCanvasStore()

  // Keyboard shortcuts
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Cmd+H for history
    if ((e.metaKey || e.ctrlKey) && e.key === 'h') {
      e.preventDefault()
      setHistoryOpen(prev => !prev)
    }
    // Cmd+K for command palette
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault()
      setCommandOpen(prev => !prev)
    }
    // Escape to close modals
    if (e.key === 'Escape') {
      if (commandOpen) setCommandOpen(false)
      else if (historyOpen) setHistoryOpen(false)
    }
  }, [historyOpen, commandOpen])

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [handleKeyDown])

  const toggleHistory = useCallback(() => {
    setHistoryOpen(prev => !prev)
  }, [])

  const toggleCommand = useCallback(() => {
    setCommandOpen(prev => !prev)
  }, [])

  return (
    <div className="flex h-screen bg-background overflow-hidden">
      {/* Main content area */}
      <div
        className="flex-1 flex flex-col min-w-0 transition-all duration-300"
        style={{
          marginRight: panelVisible ? panelWidth : 0,
        }}
      >
        {/* Header */}
        {showHeader && (
          <MinimalHeader
            onToggleHistory={toggleHistory}
            onToggleCommand={toggleCommand}
          />
        )}

        {/* Page content */}
        <main className="flex-1 overflow-hidden relative">
          {children || <Outlet />}
        </main>
      </div>

      {/* History Drawer */}
      <HistoryDrawer
        isOpen={historyOpen}
        onClose={() => setHistoryOpen(false)}
      />

      {/* Canvas Panel */}
      <CanvasPanel />

      {/* Command Palette */}
      <CommandPalette
        isOpen={commandOpen}
        onClose={() => setCommandOpen(false)}
        onOpenHistory={() => setHistoryOpen(true)}
      />
    </div>
  )
}
