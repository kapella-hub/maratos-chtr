import { useState, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
  HardDrive,
  Trash2,
  Archive,
  FileX,
  FolderMinus,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  AlertCircle,
  CheckCircle
} from 'lucide-react'
import {
  fetchWorkspaceStats,
  cleanupWorkspace,
  fetchLargeFiles,
  archiveProject,
  type WorkspaceStats,
  type FullCleanupResult,
  type LargeFile
} from '@/lib/api'

interface WorkspaceManagerProps {
  className?: string
}

export default function WorkspaceManager({ className }: WorkspaceManagerProps) {
  const [stats, setStats] = useState<WorkspaceStats | null>(null)
  const [largeFiles, setLargeFiles] = useState<LargeFile[]>([])
  const [loading, setLoading] = useState(true)
  const [cleaning, setCleaning] = useState(false)
  const [cleanupResult, setCleanupResult] = useState<FullCleanupResult | null>(null)
  const [showLargeFiles, setShowLargeFiles] = useState(false)
  const [archiving, setArchiving] = useState<string | null>(null)

  // Cleanup options
  const [cleanupOptions, setCleanupOptions] = useState({
    cleanup_temp: true,
    cleanup_old: false,
    cleanup_empty: true,
    cleanup_kiro_temp: true,
    max_age_days: 30,
  })

  const loadData = async () => {
    try {
      const [statsData, largeFilesData] = await Promise.all([
        fetchWorkspaceStats(),
        fetchLargeFiles(10),
      ])
      setStats(statsData)
      setLargeFiles(largeFilesData)
    } catch (error) {
      console.error('Failed to load workspace data:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleCleanup = async () => {
    setCleaning(true)
    setCleanupResult(null)
    try {
      const result = await cleanupWorkspace(cleanupOptions)
      setCleanupResult(result)
      // Refresh stats after cleanup
      await loadData()
    } catch (error) {
      console.error('Cleanup failed:', error)
    } finally {
      setCleaning(false)
    }
  }

  const handleArchive = async (projectName: string) => {
    setArchiving(projectName)
    try {
      await archiveProject(projectName)
      // Refresh stats after archival
      await loadData()
    } catch (error) {
      console.error('Archive failed:', error)
    } finally {
      setArchiving(null)
    }
  }

  if (loading) {
    return (
      <div className={cn('flex items-center justify-center p-8', className)}>
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!stats) {
    return (
      <div className={cn('p-4 text-center text-muted-foreground', className)}>
        Failed to load workspace stats
      </div>
    )
  }

  return (
    <div className={cn('space-y-6', className)}>
      {/* Workspace Stats */}
      <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <HardDrive className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Workspace Statistics</h3>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          <StatCard
            label="Total Size"
            value={`${stats.total_size_mb.toFixed(1)} MB`}
            sublabel={`${stats.total_size_bytes.toLocaleString()} bytes`}
          />
          <StatCard
            label="Files"
            value={stats.file_count.toString()}
            sublabel="total files"
          />
          <StatCard
            label="Directories"
            value={stats.dir_count.toString()}
            sublabel="total folders"
          />
          <StatCard
            label="Oldest File"
            value={`${stats.oldest_file_age_days} days`}
            sublabel="since modified"
          />
          <StatCard
            label="Newest File"
            value={`${stats.newest_file_age_days} days`}
            sublabel="since modified"
          />
          <StatCard
            label="Location"
            value={stats.workspace_path.split('/').pop() || 'workspace'}
            sublabel={stats.workspace_path}
          />
        </div>
      </div>

      {/* Cleanup Controls */}
      <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Trash2 className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Cleanup Options</h3>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <label className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors">
              <input
                type="checkbox"
                checked={cleanupOptions.cleanup_temp}
                onChange={(e) => setCleanupOptions(prev => ({ ...prev, cleanup_temp: e.target.checked }))}
                className="rounded"
              />
              <div>
                <div className="font-medium flex items-center gap-2">
                  <FileX className="w-4 h-4 text-amber-400" />
                  Temp Files
                </div>
                <div className="text-xs text-muted-foreground">*.tmp, __pycache__, .DS_Store</div>
              </div>
            </label>

            <label className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors">
              <input
                type="checkbox"
                checked={cleanupOptions.cleanup_empty}
                onChange={(e) => setCleanupOptions(prev => ({ ...prev, cleanup_empty: e.target.checked }))}
                className="rounded"
              />
              <div>
                <div className="font-medium flex items-center gap-2">
                  <FolderMinus className="w-4 h-4 text-blue-400" />
                  Empty Dirs
                </div>
                <div className="text-xs text-muted-foreground">Remove empty directories</div>
              </div>
            </label>

            <label className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors">
              <input
                type="checkbox"
                checked={cleanupOptions.cleanup_kiro_temp}
                onChange={(e) => setCleanupOptions(prev => ({ ...prev, cleanup_kiro_temp: e.target.checked }))}
                className="rounded"
              />
              <div>
                <div className="font-medium flex items-center gap-2">
                  <Trash2 className="w-4 h-4 text-purple-400" />
                  Kiro Temp
                </div>
                <div className="text-xs text-muted-foreground">Clean /tmp/kiro_* files</div>
              </div>
            </label>

            <label className="flex items-center gap-3 p-3 rounded-xl bg-muted/30 cursor-pointer hover:bg-muted/50 transition-colors">
              <input
                type="checkbox"
                checked={cleanupOptions.cleanup_old}
                onChange={(e) => setCleanupOptions(prev => ({ ...prev, cleanup_old: e.target.checked }))}
                className="rounded"
              />
              <div>
                <div className="font-medium flex items-center gap-2">
                  <Archive className="w-4 h-4 text-red-400" />
                  Old Files
                </div>
                <div className="text-xs text-muted-foreground">Files older than specified days</div>
              </div>
            </label>
          </div>

          {cleanupOptions.cleanup_old && (
            <div className="flex items-center gap-3 p-3 rounded-xl bg-muted/30">
              <label className="text-sm">Files older than:</label>
              <input
                type="number"
                min={1}
                max={365}
                value={cleanupOptions.max_age_days}
                onChange={(e) => setCleanupOptions(prev => ({ ...prev, max_age_days: parseInt(e.target.value) || 30 }))}
                className="w-20 px-2 py-1 rounded bg-background border border-border focus:border-primary outline-none text-center"
              />
              <span className="text-sm text-muted-foreground">days</span>
            </div>
          )}

          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className={cn(
              'w-full py-3 rounded-xl font-medium transition-colors flex items-center justify-center gap-2',
              cleaning
                ? 'bg-muted text-muted-foreground cursor-not-allowed'
                : 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/30'
            )}
          >
            {cleaning ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                Cleaning...
              </>
            ) : (
              <>
                <Trash2 className="w-4 h-4" />
                Run Cleanup
              </>
            )}
          </button>
        </div>

        {/* Cleanup Result */}
        <AnimatePresence>
          {cleanupResult && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="mt-4 pt-4 border-t border-border/30"
            >
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle className="w-5 h-5 text-emerald-400" />
                <span className="font-medium">Cleanup Complete</span>
              </div>

              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="p-2 rounded-lg bg-emerald-500/10">
                  <div className="text-lg font-bold text-emerald-400">
                    {cleanupResult.summary.total_items_deleted}
                  </div>
                  <div className="text-xs text-muted-foreground">Items Deleted</div>
                </div>
                <div className="p-2 rounded-lg bg-blue-500/10">
                  <div className="text-lg font-bold text-blue-400">
                    {cleanupResult.summary.total_mb_freed.toFixed(1)} MB
                  </div>
                  <div className="text-xs text-muted-foreground">Space Freed</div>
                </div>
                <div className="p-2 rounded-lg bg-amber-500/10">
                  <div className="text-lg font-bold text-amber-400">
                    {cleanupResult.summary.total_errors}
                  </div>
                  <div className="text-xs text-muted-foreground">Errors</div>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* Large Files */}
      {largeFiles.length > 0 && (
        <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
          <button
            onClick={() => setShowLargeFiles(!showLargeFiles)}
            className="w-full flex items-center justify-between"
          >
            <div className="flex items-center gap-2">
              <AlertCircle className="w-5 h-5 text-amber-400" />
              <h3 className="font-semibold">Large Files ({largeFiles.length})</h3>
            </div>
            {showLargeFiles ? (
              <ChevronUp className="w-5 h-5" />
            ) : (
              <ChevronDown className="w-5 h-5" />
            )}
          </button>

          <AnimatePresence>
            {showLargeFiles && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="mt-4 space-y-2"
              >
                {largeFiles.map((file) => (
                  <div
                    key={file.path}
                    className="flex items-center gap-3 p-3 rounded-xl bg-muted/30"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-mono truncate">{file.path}</div>
                      <div className="text-xs text-muted-foreground">
                        {file.size_mb.toFixed(1)} MB
                      </div>
                    </div>
                    <button
                      onClick={() => handleArchive(file.path.split('/')[0])}
                      disabled={archiving === file.path.split('/')[0]}
                      className="p-2 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground"
                      title="Archive containing project"
                    >
                      {archiving === file.path.split('/')[0] ? (
                        <RefreshCw className="w-4 h-4 animate-spin" />
                      ) : (
                        <Archive className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Refresh Button */}
      <div className="flex justify-center">
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh Stats
        </button>
      </div>
    </div>
  )
}

function StatCard({ label, value, sublabel }: { label: string; value: string; sublabel: string }) {
  return (
    <div className="p-3 rounded-xl bg-muted/30">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="text-lg font-bold">{value}</div>
      <div className="text-xs text-muted-foreground truncate" title={sublabel}>{sublabel}</div>
    </div>
  )
}
