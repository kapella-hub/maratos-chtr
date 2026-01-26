import { useState, useEffect } from 'react'
import { FolderOpen, FolderGit2, ChevronUp, Loader2, X, Check, Home } from 'lucide-react'
import { browseDirectory, type DirectoryEntry } from '@/lib/api'
import { cn } from '@/lib/utils'

interface FolderBrowserProps {
  isOpen: boolean
  onClose: () => void
  onSelect: (path: string) => void
  initialPath?: string
  title?: string
}

export default function FolderBrowser({
  isOpen,
  onClose,
  onSelect,
  initialPath = '~',
  title = 'Select Folder',
}: FolderBrowserProps) {
  const [currentPath, setCurrentPath] = useState(initialPath)
  const [parentPath, setParentPath] = useState<string | null>(null)
  const [entries, setEntries] = useState<DirectoryEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Load directory contents
  const loadDirectory = async (path: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await browseDirectory(path)
      setCurrentPath(response.current_path)
      setParentPath(response.parent_path)
      setEntries(response.entries)
      setSelectedPath(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load directory')
    } finally {
      setIsLoading(false)
    }
  }

  // Load initial directory when opened
  useEffect(() => {
    if (isOpen) {
      loadDirectory(initialPath)
    }
  }, [isOpen, initialPath])

  // Navigate to a directory
  const navigateTo = (path: string) => {
    loadDirectory(path)
  }

  // Go up one level
  const goUp = () => {
    if (parentPath) {
      loadDirectory(parentPath)
    }
  }

  // Go to home
  const goHome = () => {
    loadDirectory('~')
  }

  // Handle folder double-click (navigate into)
  const handleDoubleClick = (entry: DirectoryEntry) => {
    navigateTo(entry.path)
  }

  // Handle folder single-click (select)
  const handleClick = (entry: DirectoryEntry) => {
    setSelectedPath(entry.path)
  }

  // Select current directory
  const selectCurrent = () => {
    onSelect(selectedPath || currentPath)
    onClose()
  }

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-background border border-border rounded-xl shadow-xl w-full max-w-2xl max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-4 py-3 border-b border-border flex items-center justify-between">
          <h2 className="font-semibold">{title}</h2>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-muted transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Path bar */}
        <div className="px-4 py-2 border-b border-border bg-muted/30 flex items-center gap-2">
          <button
            onClick={goHome}
            className="p-1.5 rounded hover:bg-muted transition-colors"
            title="Go to home directory"
          >
            <Home className="w-4 h-4" />
          </button>
          <button
            onClick={goUp}
            disabled={!parentPath}
            className={cn(
              'p-1.5 rounded hover:bg-muted transition-colors',
              !parentPath && 'opacity-50 cursor-not-allowed'
            )}
            title="Go up one level"
          >
            <ChevronUp className="w-4 h-4" />
          </button>
          <div className="flex-1 font-mono text-sm truncate text-muted-foreground">
            {currentPath}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-2 min-h-[300px]">
          {isLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center h-full text-center p-4">
              <p className="text-red-400 mb-2">{error}</p>
              <button
                onClick={() => loadDirectory(currentPath)}
                className="text-sm text-primary hover:underline"
              >
                Try again
              </button>
            </div>
          ) : entries.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
              <FolderOpen className="w-12 h-12 mb-2 opacity-50" />
              <p>No subdirectories</p>
              <p className="text-sm mt-1">You can select this directory</p>
            </div>
          ) : (
            <div className="grid gap-1">
              {entries.map((entry) => (
                <button
                  key={entry.path}
                  onClick={() => handleClick(entry)}
                  onDoubleClick={() => handleDoubleClick(entry)}
                  className={cn(
                    'flex items-center gap-3 px-3 py-2 rounded-lg text-left transition-colors',
                    'hover:bg-muted/50',
                    selectedPath === entry.path && 'bg-primary/20 border border-primary/50'
                  )}
                >
                  {entry.is_project ? (
                    <FolderGit2 className="w-5 h-5 text-green-500 shrink-0" />
                  ) : (
                    <FolderOpen className="w-5 h-5 text-yellow-500 shrink-0" />
                  )}
                  <span className="flex-1 truncate">{entry.name}</span>
                  {entry.is_project && (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 shrink-0">
                      project
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-border flex items-center justify-between bg-muted/30">
          <div className="text-sm text-muted-foreground">
            {selectedPath ? (
              <span className="font-mono">{selectedPath.split('/').pop()}</span>
            ) : (
              <span>Select a folder or use current: <span className="font-mono">{currentPath.split('/').pop()}</span></span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded-lg text-sm hover:bg-muted transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={selectCurrent}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded-lg text-sm',
                'bg-primary text-primary-foreground',
                'hover:bg-primary/90 transition-colors'
              )}
            >
              <Check className="w-4 h-4" />
              Select
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
