import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import {
  Activity,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  AlertTriangle,
  RefreshCw,
  Settings2,
  Gauge,
  Users
} from 'lucide-react'
import {
  fetchAllAgentMetrics,
  fetchRateLimitStatus,
  updateRateLimits,
  type AllMetrics,
  type RateLimitStatus
} from '@/lib/api'

interface AgentMetricsProps {
  className?: string
}

const agentColors: Record<string, { bg: string; text: string; border: string }> = {
  architect: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  reviewer: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30' },
  coder: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  tester: { bg: 'bg-pink-500/10', text: 'text-pink-400', border: 'border-pink-500/30' },
  docs: { bg: 'bg-cyan-500/10', text: 'text-cyan-400', border: 'border-cyan-500/30' },
  devops: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30' },
  mo: { bg: 'bg-violet-500/10', text: 'text-violet-400', border: 'border-violet-500/30' },
}

const agentIcons: Record<string, string> = {
  architect: '🏗️',
  reviewer: '🔍',
  coder: '💻',
  tester: '🧪',
  docs: '📝',
  devops: '🚀',
  mo: '🤖',
}

export default function AgentMetrics({ className }: AgentMetricsProps) {
  const [metrics, setMetrics] = useState<AllMetrics | null>(null)
  const [rateLimit, setRateLimit] = useState<RateLimitStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [editingRateLimit, setEditingRateLimit] = useState(false)
  const [rateLimitConfig, setRateLimitConfig] = useState({ maxTotal: 10, maxPerAgent: 3 })

  const loadData = async () => {
    try {
      const [metricsData, rateLimitData] = await Promise.all([
        fetchAllAgentMetrics(),
        fetchRateLimitStatus(),
      ])
      setMetrics(metricsData)
      setRateLimit(rateLimitData)
      setRateLimitConfig({
        maxTotal: rateLimitData.max_total_concurrent,
        maxPerAgent: rateLimitData.max_per_agent,
      })
    } catch (error) {
      console.error('Failed to load metrics:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 30000) // Refresh every 30s
    return () => clearInterval(interval)
  }, [])

  const handleSaveRateLimits = async () => {
    try {
      const updated = await updateRateLimits({
        max_total_concurrent: rateLimitConfig.maxTotal,
        max_per_agent: rateLimitConfig.maxPerAgent,
      })
      setRateLimit(updated)
      setEditingRateLimit(false)
    } catch (error) {
      console.error('Failed to update rate limits:', error)
    }
  }

  if (loading) {
    return (
      <div className={cn('flex items-center justify-center p-8', className)}>
        <RefreshCw className="w-6 h-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  if (!metrics) {
    return (
      <div className={cn('p-4 text-center text-muted-foreground', className)}>
        Failed to load metrics
      </div>
    )
  }

  // Calculate totals
  const totalTasks = Object.values(metrics.agents).reduce((sum, m) => sum + m.total_tasks, 0)
  const totalSuccess = Object.values(metrics.agents).reduce((sum, m) => sum + m.successful_tasks, 0)
  const totalFailed = Object.values(metrics.agents).reduce((sum, m) => sum + m.failed_tasks, 0)
  const overallSuccessRate = totalTasks > 0 ? (totalSuccess / totalTasks) * 100 : 0

  return (
    <div className={cn('space-y-6', className)}>
      {/* Summary Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <SummaryCard
          icon={Activity}
          label="Total Tasks"
          value={totalTasks}
          iconColor="text-blue-400"
        />
        <SummaryCard
          icon={CheckCircle}
          label="Successful"
          value={totalSuccess}
          iconColor="text-emerald-400"
        />
        <SummaryCard
          icon={XCircle}
          label="Failed"
          value={totalFailed}
          iconColor="text-red-400"
        />
        <SummaryCard
          icon={TrendingUp}
          label="Success Rate"
          value={`${overallSuccessRate.toFixed(1)}%`}
          iconColor="text-purple-400"
        />
      </div>

      {/* Rate Limit Status */}
      {rateLimit && (
        <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Gauge className="w-5 h-5 text-primary" />
              <h3 className="font-semibold">Rate Limiting</h3>
            </div>
            <button
              onClick={() => setEditingRateLimit(!editingRateLimit)}
              className="p-2 rounded-lg hover:bg-muted transition-colors"
            >
              <Settings2 className="w-4 h-4" />
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="text-center p-3 rounded-xl bg-muted/50">
              <div className="text-2xl font-bold text-foreground">
                {rateLimit.current_running}/{rateLimit.max_total_concurrent}
              </div>
              <div className="text-xs text-muted-foreground">Running Tasks</div>
            </div>
            <div className="text-center p-3 rounded-xl bg-muted/50">
              <div className="text-2xl font-bold text-foreground">{rateLimit.queue_size}</div>
              <div className="text-xs text-muted-foreground">Queued</div>
            </div>
            <div className="text-center p-3 rounded-xl bg-muted/50">
              <div className="text-2xl font-bold text-foreground">{rateLimit.available_slots}</div>
              <div className="text-xs text-muted-foreground">Available Slots</div>
            </div>
            <div className="text-center p-3 rounded-xl bg-muted/50">
              <div className="text-2xl font-bold text-foreground">{rateLimit.max_per_agent}</div>
              <div className="text-xs text-muted-foreground">Max Per Agent</div>
            </div>
          </div>

          {/* Edit Rate Limits */}
          {editingRateLimit && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              className="mt-4 pt-4 border-t border-border/30"
            >
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="text-sm text-muted-foreground block mb-1">Max Total Concurrent</label>
                  <input
                    type="number"
                    min={1}
                    max={50}
                    value={rateLimitConfig.maxTotal}
                    onChange={(e) => setRateLimitConfig(prev => ({ ...prev, maxTotal: parseInt(e.target.value) || 1 }))}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border focus:border-primary outline-none"
                  />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground block mb-1">Max Per Agent</label>
                  <input
                    type="number"
                    min={1}
                    max={20}
                    value={rateLimitConfig.maxPerAgent}
                    onChange={(e) => setRateLimitConfig(prev => ({ ...prev, maxPerAgent: parseInt(e.target.value) || 1 }))}
                    className="w-full px-3 py-2 rounded-lg bg-background border border-border focus:border-primary outline-none"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-4">
                <button
                  onClick={() => setEditingRateLimit(false)}
                  className="px-4 py-2 rounded-lg text-sm hover:bg-muted transition-colors"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSaveRateLimits}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
                >
                  Save
                </button>
              </div>
            </motion.div>
          )}
        </div>
      )}

      {/* Agent-specific Metrics */}
      <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Users className="w-5 h-5 text-primary" />
          <h3 className="font-semibold">Agent Performance</h3>
        </div>

        <div className="grid gap-3">
          {Object.entries(metrics.agents).map(([agentId, agentMetrics]) => {
            const colors = agentColors[agentId] || agentColors.mo
            const icon = agentIcons[agentId] || '🤖'

            return (
              <motion.div
                key={agentId}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className={cn(
                  'rounded-xl border p-4',
                  colors.bg,
                  colors.border
                )}
              >
                <div className="flex items-center gap-3 mb-3">
                  <span className="text-2xl">{icon}</span>
                  <div className="flex-1">
                    <div className={cn('font-semibold capitalize', colors.text)}>
                      {agentId}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {agentMetrics.total_tasks} tasks total
                    </div>
                  </div>
                  <div className="text-right">
                    <div className={cn('text-lg font-bold',
                      agentMetrics.success_rate >= 80 ? 'text-emerald-400' :
                      agentMetrics.success_rate >= 50 ? 'text-amber-400' : 'text-red-400'
                    )}>
                      {(agentMetrics.success_rate * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-muted-foreground">success rate</div>
                  </div>
                </div>

                <div className="grid grid-cols-4 gap-2 text-center text-sm">
                  <div>
                    <div className="font-medium text-emerald-400">{agentMetrics.successful_tasks}</div>
                    <div className="text-xs text-muted-foreground">Success</div>
                  </div>
                  <div>
                    <div className="font-medium text-red-400">{agentMetrics.failed_tasks}</div>
                    <div className="text-xs text-muted-foreground">Failed</div>
                  </div>
                  <div>
                    <div className="font-medium text-foreground">
                      {agentMetrics.avg_duration_seconds.toFixed(1)}s
                    </div>
                    <div className="text-xs text-muted-foreground">Avg Time</div>
                  </div>
                  <div>
                    <div className="font-medium text-foreground">
                      {(agentMetrics.goal_completion_rate * 100).toFixed(0)}%
                    </div>
                    <div className="text-xs text-muted-foreground">Goals</div>
                  </div>
                </div>
              </motion.div>
            )
          })}
        </div>
      </div>

      {/* Failure Patterns */}
      {Object.keys(metrics.failure_patterns).length > 0 && (
        <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
          <div className="flex items-center gap-2 mb-4">
            <AlertTriangle className="w-5 h-5 text-amber-400" />
            <h3 className="font-semibold">Failure Patterns</h3>
          </div>

          <div className="flex flex-wrap gap-2">
            {Object.entries(metrics.failure_patterns).map(([pattern, count]) => (
              <span
                key={pattern}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-sm bg-red-500/10 text-red-400 border border-red-500/20"
              >
                {pattern}
                <span className="px-1.5 py-0.5 rounded-full bg-red-500/20 text-xs">
                  {count}
                </span>
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Recent Tasks */}
      {metrics.recent_tasks.length > 0 && (
        <div className="rounded-2xl border border-border/50 bg-card/50 p-4">
          <div className="flex items-center gap-2 mb-4">
            <Clock className="w-5 h-5 text-primary" />
            <h3 className="font-semibold">Recent Tasks</h3>
          </div>

          <div className="space-y-2">
            {metrics.recent_tasks.slice(0, 5).map((task) => {
              const colors = agentColors[task.agent_id] || agentColors.mo
              const isSuccess = task.status === 'completed'

              return (
                <div
                  key={task.task_id}
                  className="flex items-center gap-3 p-3 rounded-xl bg-muted/30"
                >
                  <div className={cn('p-2 rounded-lg', colors.bg)}>
                    <span>{agentIcons[task.agent_id] || '🤖'}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm truncate">{task.description}</div>
                    <div className="text-xs text-muted-foreground">
                      {task.duration_seconds ? `${task.duration_seconds.toFixed(1)}s` : 'In progress'}
                      {' • '}
                      {task.goals_completed}/{task.goals_total} goals
                    </div>
                  </div>
                  <div className={cn(
                    'px-2 py-1 rounded-full text-xs',
                    isSuccess ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                  )}>
                    {task.status}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {/* Refresh Button */}
      <div className="flex justify-center">
        <button
          onClick={loadData}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh Metrics
        </button>
      </div>
    </div>
  )
}

function SummaryCard({
  icon: Icon,
  label,
  value,
  iconColor
}: {
  icon: React.ComponentType<{ className?: string }>
  label: string
  value: string | number
  iconColor: string
}) {
  return (
    <div className="rounded-xl border border-border/50 bg-card/50 p-4">
      <div className="flex items-center gap-3">
        <div className={cn('p-2 rounded-lg bg-muted/50', iconColor)}>
          <Icon className="w-5 h-5" />
        </div>
        <div>
          <div className="text-2xl font-bold">{value}</div>
          <div className="text-xs text-muted-foreground">{label}</div>
        </div>
      </div>
    </div>
  )
}
