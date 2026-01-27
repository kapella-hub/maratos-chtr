import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Save, Loader2, MessageSquare, Phone, Building2, ToggleLeft, ToggleRight, FolderOpen, Plus, Trash2, Edit3, X, Check, Link, ExternalLink, Sparkles, Shield, ShieldCheck, FolderSearch, GitBranch, GitCommit, GitPullRequest, Wand2, ChevronRight, Activity, HardDrive, Brain } from 'lucide-react'
import { fetchConfig, updateConfig, type Config, fetchProjects, createProject, updateProject, deleteProject, analyzeProject, removeAllowedDirectory, addAllowedDirectory, testGitLabConnection, fetchSkills, type Project, type Skill } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'
import FolderBrowser from '@/components/FolderBrowser'
import AgentMetrics from '@/components/AgentMetrics'
import WorkspaceManager from '@/components/WorkspaceManager'

// Setup Webex webhook
async function setupWebexWebhook(targetUrl: string): Promise<{ status: string; webhook_id?: string; error?: string }> {
  const res = await fetch('/api/channels/webex/setup', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_url: targetUrl }),
  })
  return res.json()
}

// Kiro CLI available models (AWS-hosted Claude)
const kiroModels = [
  { id: 'Auto', name: 'Auto', credits: '1x', desc: 'Models chosen by task for optimal usage' },
  { id: 'claude-sonnet-4.5', name: 'Claude Sonnet 4.5', credits: '1.3x', desc: 'Latest Claude Sonnet model' },
  { id: 'claude-sonnet-4', name: 'Claude Sonnet 4', credits: '1.3x', desc: 'Hybrid reasoning and coding' },
  { id: 'claude-haiku-4.5', name: 'Claude Haiku 4.5', credits: '0.4x', desc: 'Latest Claude Haiku (fast)' },
  { id: 'claude-opus-4.5', name: 'Claude Opus 4.5', credits: '2.2x', desc: 'Latest Claude Opus (most capable)' },
]

// Direct API models (requires API keys)
const apiModels = [
  { id: 'claude-sonnet-4-20250514', name: 'Claude Sonnet 4 (API)', credits: null, desc: 'Requires Anthropic API key' },
  { id: 'claude-opus-4-20250514', name: 'Claude Opus 4 (API)', credits: null, desc: 'Requires Anthropic API key' },
  { id: 'gpt-4o', name: 'GPT-4o (API)', credits: null, desc: 'Requires OpenAI API key' },
]

// Thinking levels - controls depth of analysis before execution
const thinkingLevels = [
  { id: 'off', name: 'Off', desc: 'Skip analysis, direct execution', color: 'text-gray-400' },
  { id: 'minimal', name: 'Minimal', desc: 'Quick sanity check before execution', color: 'text-blue-400' },
  { id: 'low', name: 'Low', desc: 'Brief problem breakdown', color: 'text-cyan-400' },
  { id: 'medium', name: 'Medium', desc: 'Structured analysis with approach evaluation', color: 'text-green-400' },
  { id: 'high', name: 'High', desc: 'Deep analysis, multiple approaches, risk assessment', color: 'text-yellow-400' },
  { id: 'max', name: 'Maximum', desc: 'Exhaustive analysis with self-critique', color: 'text-orange-400' },
]

interface ChannelConfig {
  imessage_enabled?: boolean
  imessage_allowed_senders?: string
  webex_enabled?: boolean
  webex_token?: string
  webex_webhook_url?: string
  webex_allowed_rooms?: string
  telegram_enabled?: boolean
  telegram_token?: string
  telegram_allowed_users?: string
  allowed_write_dirs?: string
  all_allowed_dirs?: string[]
  // Git settings
  git_auto_commit?: boolean
  git_push_to_remote?: boolean
  git_create_pr?: boolean
  git_default_branch?: string
  git_commit_prefix?: string
  git_remote_name?: string
  // GitLab integration
  gitlab_url?: string
  gitlab_token?: string
  gitlab_namespace?: string
  gitlab_skip_ssl?: boolean
  gitlab_configured?: boolean
}

// Empty project template
const emptyProject: Project = {
  name: '',
  description: '',
  path: '',
  tech_stack: [],
  conventions: [],
  patterns: [],
  dependencies: [],
  notes: '',
  auto_add_filesystem: true,
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [localConfig, setLocalConfig] = useState<Partial<Config & ChannelConfig>>({})
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [isAddingProject, setIsAddingProject] = useState(false)
  const [projectError, setProjectError] = useState<string | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [webexWebhookUrl, setWebexWebhookUrl] = useState('')
  const [webexWebhookStatus, setWebexWebhookStatus] = useState<string | null>(null)
  const [webexWebhookLoading, setWebexWebhookLoading] = useState(false)
  const [newAllowedDir, setNewAllowedDir] = useState('')
  const [showFolderBrowser, setShowFolderBrowser] = useState(false)
  const [folderBrowserTarget, setFolderBrowserTarget] = useState<'project' | 'allowedDir'>('project')
  const [removingDir, setRemovingDir] = useState<string | null>(null)
  const [gitlabTestStatus, setGitlabTestStatus] = useState<{ status: 'idle' | 'testing' | 'success' | 'error'; message?: string }>({ status: 'idle' })

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
  })

  const { data: skills = [] } = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
  })

  const createProjectMutation = useMutation({
    mutationFn: createProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setIsAddingProject(false)
      setEditingProject(null)
      setProjectError(null)
    },
    onError: (error: Error) => {
      setProjectError(error.message)
    },
  })

  const updateProjectMutation = useMutation({
    mutationFn: ({ name, project }: { name: string; project: Project }) => updateProject(name, project),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setEditingProject(null)
      setProjectError(null)
    },
    onError: (error: Error) => {
      setProjectError(error.message)
    },
  })

  const deleteProjectMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
    },
  })

  const mutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['config'] })
    },
  })

  useEffect(() => {
    if (config) {
      setLocalConfig(config)
    }
  }, [config])

  const handleSave = () => {
    mutation.mutate(localConfig)
  }

  const hasChanges = JSON.stringify(config) !== JSON.stringify(localConfig)

  // Handle project analysis
  const handleAnalyzeProject = async () => {
    if (!editingProject?.path) {
      setProjectError('Please enter a project path first')
      return
    }

    setIsAnalyzing(true)
    setProjectError(null)

    try {
      const analysis = await analyzeProject(editingProject.path)

      setEditingProject({
        ...editingProject,
        description: analysis.description || editingProject.description,
        tech_stack: analysis.tech_stack.length > 0 ? analysis.tech_stack : editingProject.tech_stack,
        conventions: analysis.conventions.length > 0 ? analysis.conventions : editingProject.conventions,
        patterns: analysis.patterns.length > 0 ? analysis.patterns : editingProject.patterns,
        dependencies: analysis.dependencies.length > 0 ? analysis.dependencies : editingProject.dependencies,
        notes: analysis.notes || editingProject.notes,
        // Auto-derive name from path if not set
        name: editingProject.name || editingProject.path.split('/').pop()?.toLowerCase().replace(/[^a-z0-9-_]/g, '-') || '',
      })
    } catch (e) {
      console.error('Analyze error:', e)
      setProjectError(e instanceof Error ? e.message : 'Failed to analyze project')
    } finally {
      setIsAnalyzing(false)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin text-4xl">⏳</div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Settings className="w-6 h-6" />
            Settings
          </h1>
          <p className="text-muted-foreground text-sm mt-1">
            Configure MaratOS
          </p>
        </div>
        
        <button
          onClick={handleSave}
          disabled={!hasChanges || mutation.isPending}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg',
            'bg-primary text-primary-foreground',
            'hover:bg-primary/90 transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {mutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Save className="w-4 h-4" />
          )}
          Save
        </button>
      </header>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-2xl space-y-8">
          {/* MO Info */}
          <section className="p-6 rounded-xl bg-gradient-to-br from-violet-500/10 to-purple-600/10 border border-violet-500/20">
            <div className="flex items-center gap-4">
              <div className="w-16 h-16 rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-xl font-bold">
                MO
              </div>
              <div>
                <h2 className="text-lg font-semibold">MO</h2>
                <p className="text-sm text-muted-foreground">
                  Your capable AI partner. Resourceful, opinionated, and genuinely helpful.
                </p>
              </div>
            </div>
          </section>

          {/* Kiro CLI Models */}
          <section>
            <h2 className="text-lg font-semibold mb-2">Kiro CLI Models</h2>
            <p className="text-sm text-muted-foreground mb-4">
              AWS-hosted Claude models via Kiro CLI — no API key needed
            </p>
            <div className="space-y-2">
              {kiroModels.map((model) => (
                <label
                  key={model.id}
                  className={cn(
                    'flex items-center gap-4 p-4 rounded-lg cursor-pointer transition-colors',
                    'border border-border hover:border-primary/50',
                    localConfig.default_model === model.id && 'border-primary bg-primary/5'
                  )}
                >
                  <input
                    type="radio"
                    name="model"
                    value={model.id}
                    checked={localConfig.default_model === model.id}
                    onChange={(e) => setLocalConfig({ ...localConfig, default_model: e.target.value })}
                    className="w-4 h-4"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{model.name}</span>
                      <span className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400">
                        {model.credits} credit
                      </span>
                    </div>
                    <div className="text-sm text-muted-foreground">{model.desc}</div>
                  </div>
                </label>
              ))}
            </div>
          </section>

          {/* API Models (Collapsed) */}
          <section>
            <details className="group">
              <summary className="text-lg font-semibold mb-2 cursor-pointer list-none flex items-center gap-2">
                <span className="text-muted-foreground group-open:rotate-90 transition-transform">▶</span>
                API Models (Advanced)
              </summary>
              <p className="text-sm text-muted-foreground mb-4 ml-5">
                Requires separate API keys configured in .env
              </p>
              <div className="space-y-2 ml-5">
                {apiModels.map((model) => (
                  <label
                    key={model.id}
                    className={cn(
                      'flex items-center gap-4 p-4 rounded-lg cursor-pointer transition-colors',
                      'border border-border hover:border-primary/50 opacity-60',
                      localConfig.default_model === model.id && 'border-primary bg-primary/5 opacity-100'
                    )}
                  >
                    <input
                      type="radio"
                      name="model"
                      value={model.id}
                      checked={localConfig.default_model === model.id}
                      onChange={(e) => setLocalConfig({ ...localConfig, default_model: e.target.value })}
                      className="w-4 h-4"
                    />
                    <div className="flex-1">
                      <div className="font-medium">{model.name}</div>
                      <div className="text-sm text-muted-foreground">{model.desc}</div>
                    </div>
                  </label>
                ))}
              </div>
            </details>
          </section>

          {/* Thinking Level */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <Brain className="w-5 h-5 text-violet-500" />
              Thinking Level
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Controls how deeply the Architect analyzes tasks before spawning coders.
              Higher levels mean more thorough planning but take longer.
            </p>
            <div className="space-y-2">
              {thinkingLevels.map((level) => (
                <label
                  key={level.id}
                  className={cn(
                    'flex items-center gap-4 p-4 rounded-lg cursor-pointer transition-colors',
                    'border border-border hover:border-violet-500/50',
                    localConfig.thinking_level === level.id && 'border-violet-500 bg-violet-500/5'
                  )}
                >
                  <input
                    type="radio"
                    name="thinking_level"
                    value={level.id}
                    checked={localConfig.thinking_level === level.id}
                    onChange={(e) => setLocalConfig({ ...localConfig, thinking_level: e.target.value })}
                    className="w-4 h-4"
                  />
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className={cn('font-medium', level.color)}>{level.name}</span>
                      {level.id === 'medium' && (
                        <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">
                          default
                        </span>
                      )}
                    </div>
                    <div className="text-sm text-muted-foreground">{level.desc}</div>
                  </div>
                </label>
              ))}
            </div>
            <div className="mt-4 p-3 rounded-lg bg-violet-500/10 border border-violet-500/20">
              <p className="text-sm text-violet-200">
                <strong>How it works:</strong> When MO spawns an Architect for complex tasks,
                the thinking level controls how much analysis happens before code is written.
                Higher levels catch more edge cases but use more tokens.
              </p>
            </div>
          </section>

          {/* Messaging Channels */}
          <section>
            <h2 className="text-lg font-semibold mb-2">Messaging Channels</h2>
            <p className="text-sm text-muted-foreground mb-4">
              Connect MO to messaging platforms
            </p>

            <div className="space-y-4">
              {/* iMessage */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
                      <MessageSquare className="w-5 h-5 text-green-500" />
                    </div>
                    <div>
                      <div className="font-medium">iMessage</div>
                      <div className="text-xs text-muted-foreground">macOS only</div>
                    </div>
                  </div>
                  <button
                    onClick={() => setLocalConfig({ ...localConfig, imessage_enabled: !localConfig.imessage_enabled })}
                    className="text-2xl"
                  >
                    {localConfig.imessage_enabled ? (
                      <ToggleRight className="w-10 h-10 text-green-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
                {localConfig.imessage_enabled && (
                  <div>
                    <label className="block text-sm font-medium mb-2">
                      Allowed Senders (comma-separated)
                    </label>
                    <input
                      type="text"
                      placeholder="+1234567890, email@example.com"
                      value={localConfig.imessage_allowed_senders || ''}
                      onChange={(e) => setLocalConfig({ ...localConfig, imessage_allowed_senders: e.target.value })}
                      className={cn(
                        'w-full px-4 py-2 rounded-lg',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring',
                        'text-sm'
                      )}
                    />
                    <p className="text-xs text-muted-foreground mt-2">
                      Leave empty to allow all. Grant Terminal accessibility permissions in System Preferences.
                    </p>
                  </div>
                )}
              </div>

              {/* Webex */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                      <Building2 className="w-5 h-5 text-blue-500" />
                    </div>
                    <div>
                      <div className="font-medium">Webex</div>
                      <div className="text-xs text-muted-foreground">Enterprise messaging</div>
                    </div>
                  </div>
                  <button
                    onClick={() => setLocalConfig({ ...localConfig, webex_enabled: !localConfig.webex_enabled })}
                    className="text-2xl"
                  >
                    {localConfig.webex_enabled ? (
                      <ToggleRight className="w-10 h-10 text-blue-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
                {localConfig.webex_enabled && (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Bot Access Token
                      </label>
                      <input
                        type="password"
                        placeholder="Your Webex bot token"
                        value={localConfig.webex_token || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, webex_token: e.target.value })}
                        className={cn(
                          'w-full px-4 py-2 rounded-lg',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring',
                          'text-sm font-mono'
                        )}
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        Create at <a href="https://developer.webex.com/my-apps" target="_blank" rel="noopener" className="text-primary hover:underline">developer.webex.com/my-apps</a>
                      </p>
                    </div>

                    {/* Webhook Setup */}
                    <div className="p-3 rounded-lg bg-muted/50 border border-border">
                      <label className="block text-sm font-medium mb-2 flex items-center gap-2">
                        <Link className="w-4 h-4" />
                        Webhook URL
                      </label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="https://your-server.com/api/channels/webex/webhook"
                          value={webexWebhookUrl}
                          onChange={(e) => setWebexWebhookUrl(e.target.value)}
                          className={cn(
                            'flex-1 px-3 py-2 rounded-lg',
                            'bg-background border border-input',
                            'focus:outline-none focus:ring-2 focus:ring-ring',
                            'text-sm font-mono'
                          )}
                        />
                        <button
                          onClick={async () => {
                            if (!webexWebhookUrl) return
                            setWebexWebhookLoading(true)
                            setWebexWebhookStatus(null)
                            try {
                              const result = await setupWebexWebhook(webexWebhookUrl)
                              if (result.webhook_id) {
                                setWebexWebhookStatus(`✓ Webhook registered: ${result.webhook_id.slice(0, 8)}...`)
                              } else {
                                setWebexWebhookStatus(`✗ ${result.error || 'Failed to register webhook'}`)
                              }
                            } catch (e) {
                              setWebexWebhookStatus(`✗ Error: ${e}`)
                            } finally {
                              setWebexWebhookLoading(false)
                            }
                          }}
                          disabled={!webexWebhookUrl || !localConfig.webex_token || webexWebhookLoading}
                          className={cn(
                            'px-4 py-2 rounded-lg text-sm font-medium',
                            'bg-blue-500 text-white',
                            'hover:bg-blue-600 transition-colors',
                            'disabled:opacity-50 disabled:cursor-not-allowed',
                            'flex items-center gap-2'
                          )}
                        >
                          {webexWebhookLoading ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <ExternalLink className="w-4 h-4" />
                          )}
                          Register
                        </button>
                      </div>
                      {webexWebhookStatus && (
                        <p className={cn(
                          'text-xs mt-2',
                          webexWebhookStatus.startsWith('✓') ? 'text-green-400' : 'text-red-400'
                        )}>
                          {webexWebhookStatus}
                        </p>
                      )}
                      <p className="text-xs text-muted-foreground mt-2">
                        Your server must be publicly accessible. Use ngrok for local testing:
                        <code className="ml-1 px-1 py-0.5 rounded bg-muted text-xs">ngrok http 8000</code>
                      </p>
                    </div>

                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Allowed Rooms (comma-separated, optional)
                      </label>
                      <input
                        type="text"
                        placeholder="room_id_1, room_id_2"
                        value={localConfig.webex_allowed_rooms || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, webex_allowed_rooms: e.target.value })}
                        className={cn(
                          'w-full px-4 py-2 rounded-lg',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring',
                          'text-sm'
                        )}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Telegram */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-sky-500/20 flex items-center justify-center">
                      <Phone className="w-5 h-5 text-sky-500" />
                    </div>
                    <div>
                      <div className="font-medium">Telegram</div>
                      <div className="text-xs text-muted-foreground">Bot API</div>
                    </div>
                  </div>
                  <button
                    onClick={() => setLocalConfig({ ...localConfig, telegram_enabled: !localConfig.telegram_enabled })}
                    className="text-2xl"
                  >
                    {localConfig.telegram_enabled ? (
                      <ToggleRight className="w-10 h-10 text-sky-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
                {localConfig.telegram_enabled && (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Bot Token
                      </label>
                      <input
                        type="password"
                        placeholder="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
                        value={localConfig.telegram_token || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, telegram_token: e.target.value })}
                        className={cn(
                          'w-full px-4 py-2 rounded-lg',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring',
                          'text-sm font-mono'
                        )}
                      />
                      <p className="text-xs text-muted-foreground mt-1">
                        Get from <a href="https://t.me/botfather" target="_blank" rel="noopener" className="text-primary hover:underline">@BotFather</a>
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-2">
                        Allowed Users (comma-separated, optional)
                      </label>
                      <input
                        type="text"
                        placeholder="user_id_1, user_id_2"
                        value={localConfig.telegram_allowed_users || ''}
                        onChange={(e) => setLocalConfig({ ...localConfig, telegram_allowed_users: e.target.value })}
                        className={cn(
                          'w-full px-4 py-2 rounded-lg',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring',
                          'text-sm'
                        )}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>
          </section>

          {/* Workspace & Allowed Directories */}
          <section>
            <h2 className="text-lg font-semibold mb-2">Filesystem Access</h2>
            <p className="text-sm text-muted-foreground mb-4">
              MO can read files anywhere. Writes are only allowed in these directories.
            </p>

            {/* Default Projects Folder - informational, links to Projects section */}
            <div className="p-4 rounded-lg bg-gradient-to-br from-violet-500/10 to-purple-600/10 border border-violet-500/20 mb-4">
              <div className="flex items-start gap-3">
                <FolderOpen className="w-5 h-5 text-violet-400 mt-0.5" />
                <div className="flex-1">
                  <div className="font-medium text-violet-200">Project Folders</div>
                  <p className="text-sm text-muted-foreground mt-1">
                    When you add a project below, its folder is automatically granted write access.
                    This lets MO modify code directly in your project.
                  </p>
                </div>
              </div>
            </div>

            {/* Default Workspace */}
            <div className="p-3 rounded-lg bg-muted/50 border border-border mb-3">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-5 h-5 text-primary" />
                <span className="font-mono text-sm">{config?.workspace || '~/maratos-workspace'}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary ml-auto">
                  workspace
                </span>
              </div>
              <p className="text-xs text-muted-foreground mt-2 ml-7">
                Default workspace for file operations when no project is specified
              </p>
            </div>

            {/* Custom Allowed Directories */}
            {(config?.all_allowed_dirs || [])
              .filter(dir => dir !== config?.workspace)
              .map((dir) => (
                <div key={dir} className="p-3 rounded-lg bg-muted/50 border border-border mb-2 flex items-center gap-2">
                  <FolderOpen className="w-5 h-5 text-green-500" />
                  <span className="font-mono text-sm flex-1 truncate">{dir}</span>
                  <button
                    onClick={async () => {
                      setRemovingDir(dir)
                      try {
                        await removeAllowedDirectory(dir)
                        queryClient.invalidateQueries({ queryKey: ['config'] })
                      } catch (e) {
                        console.error('Failed to remove directory:', e)
                      } finally {
                        setRemovingDir(null)
                      }
                    }}
                    disabled={removingDir === dir}
                    className="p-1.5 rounded hover:bg-red-500/10 transition-colors disabled:opacity-50"
                    title="Remove directory"
                  >
                    {removingDir === dir ? (
                      <Loader2 className="w-4 h-4 text-red-400 animate-spin" />
                    ) : (
                      <Trash2 className="w-4 h-4 text-red-400" />
                    )}
                  </button>
                </div>
              ))}

            {/* Add New Directory */}
            <div className="flex gap-2 mt-3">
              <input
                type="text"
                placeholder="/path/to/directory"
                value={newAllowedDir}
                onChange={(e) => setNewAllowedDir(e.target.value)}
                className={cn(
                  'flex-1 px-3 py-2 rounded-lg text-sm',
                  'bg-muted border border-input',
                  'focus:outline-none focus:ring-2 focus:ring-ring',
                  'font-mono'
                )}
              />
              <button
                onClick={() => {
                  setFolderBrowserTarget('allowedDir')
                  setShowFolderBrowser(true)
                }}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
                  'bg-muted border border-input',
                  'hover:bg-muted/80 transition-colors'
                )}
                title="Browse folders"
              >
                <FolderSearch className="w-4 h-4" />
              </button>
              <button
                onClick={async () => {
                  if (!newAllowedDir.trim()) return
                  try {
                    await addAllowedDirectory(newAllowedDir.trim())
                    queryClient.invalidateQueries({ queryKey: ['config'] })
                    setNewAllowedDir('')
                  } catch (e) {
                    console.error('Failed to add directory:', e)
                  }
                }}
                disabled={!newAllowedDir.trim()}
                className={cn(
                  'px-4 py-2 rounded-lg text-sm font-medium',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed',
                  'flex items-center gap-2'
                )}
              >
                <Plus className="w-4 h-4" />
                Add
              </button>
            </div>
            <p className="text-xs text-muted-foreground mt-2">
              Add directories where MO can write files directly (e.g., your Projects folder).
            </p>
          </section>

          {/* Git Integration */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <GitBranch className="w-5 h-5" />
              Git Integration
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Default settings for Autonomous Development git operations. These can be overridden per project.
            </p>

            <div className="space-y-4">
              {/* Auto-commit */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-green-500/20 flex items-center justify-center">
                      <GitCommit className="w-5 h-5 text-green-500" />
                    </div>
                    <div>
                      <div className="font-medium">Auto-commit Changes</div>
                      <div className="text-xs text-muted-foreground">Automatically commit after completing tasks</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLocalConfig({ ...localConfig, git_auto_commit: localConfig.git_auto_commit === false ? true : false })}
                    className="text-2xl"
                  >
                    {localConfig.git_auto_commit !== false ? (
                      <ToggleRight className="w-10 h-10 text-green-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
              </div>

              {/* Push to Remote */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                      <GitBranch className="w-5 h-5 text-blue-500" />
                    </div>
                    <div>
                      <div className="font-medium">Push to Remote</div>
                      <div className="text-xs text-muted-foreground">Push commits to remote repository</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLocalConfig({ ...localConfig, git_push_to_remote: !localConfig.git_push_to_remote })}
                    className="text-2xl"
                  >
                    {localConfig.git_push_to_remote ? (
                      <ToggleRight className="w-10 h-10 text-blue-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
              </div>

              {/* Create PR */}
              <div className="p-4 rounded-lg border border-border">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-purple-500/20 flex items-center justify-center">
                      <GitPullRequest className="w-5 h-5 text-purple-500" />
                    </div>
                    <div>
                      <div className="font-medium">Create Pull Request</div>
                      <div className="text-xs text-muted-foreground">Create a PR when project completes</div>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setLocalConfig({ ...localConfig, git_create_pr: !localConfig.git_create_pr })}
                    className="text-2xl"
                  >
                    {localConfig.git_create_pr ? (
                      <ToggleRight className="w-10 h-10 text-purple-500" />
                    ) : (
                      <ToggleLeft className="w-10 h-10 text-muted-foreground" />
                    )}
                  </button>
                </div>
              </div>

              {/* Git Settings Details */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium mb-2">Default Branch</label>
                  <input
                    type="text"
                    placeholder="main"
                    value={localConfig.git_default_branch || ''}
                    onChange={(e) => setLocalConfig({ ...localConfig, git_default_branch: e.target.value })}
                    className={cn(
                      'w-full px-3 py-2 rounded-lg text-sm',
                      'bg-muted border border-input',
                      'focus:outline-none focus:ring-2 focus:ring-ring',
                      'font-mono'
                    )}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Base branch for PRs</p>
                </div>

                <div>
                  <label className="block text-sm font-medium mb-2">Remote Name</label>
                  <input
                    type="text"
                    placeholder="origin"
                    value={localConfig.git_remote_name || ''}
                    onChange={(e) => setLocalConfig({ ...localConfig, git_remote_name: e.target.value })}
                    className={cn(
                      'w-full px-3 py-2 rounded-lg text-sm',
                      'bg-muted border border-input',
                      'focus:outline-none focus:ring-2 focus:ring-ring',
                      'font-mono'
                    )}
                  />
                  <p className="text-xs text-muted-foreground mt-1">Git remote to push to</p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Commit Message Prefix (optional)</label>
                <input
                  type="text"
                  placeholder="[AUTO]"
                  value={localConfig.git_commit_prefix || ''}
                  onChange={(e) => setLocalConfig({ ...localConfig, git_commit_prefix: e.target.value })}
                  className={cn(
                    'w-full px-3 py-2 rounded-lg text-sm',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring'
                  )}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Prefix added to auto-generated commit messages (e.g., "[AUTO]" or "[MO]")
                </p>
              </div>
            </div>
          </section>

          {/* GitLab Integration */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <svg className="w-5 h-5 text-orange-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 0 1-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 0 1 4.82 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0 1 18.6 2a.43.43 0 0 1 .58 0 .42.42 0 0 1 .11.18l2.44 7.51L23 13.45a.84.84 0 0 1-.35.94z"/>
              </svg>
              GitLab Integration
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Connect to GitLab to create new projects directly from Autonomous Development
            </p>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">GitLab URL</label>
                <input
                  type="text"
                  placeholder="https://gitlab.example.com"
                  value={localConfig.gitlab_url || ''}
                  onChange={(e) => setLocalConfig({ ...localConfig, gitlab_url: e.target.value })}
                  className={cn(
                    'w-full px-3 py-2 rounded-lg text-sm',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring',
                    'font-mono'
                  )}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Your GitLab instance URL (e.g., https://gitlab.com or self-hosted)
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Personal Access Token</label>
                <input
                  type="password"
                  placeholder="glpat-xxxxxxxxxxxxxxxxxxxx"
                  value={localConfig.gitlab_token === '***' ? '' : (localConfig.gitlab_token || '')}
                  onChange={(e) => setLocalConfig({ ...localConfig, gitlab_token: e.target.value })}
                  className={cn(
                    'w-full px-3 py-2 rounded-lg text-sm',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring',
                    'font-mono'
                  )}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Create at GitLab → Preferences → Access Tokens. Needs <code className="px-1 bg-muted rounded">api</code> scope.
                  {localConfig.gitlab_token === '***' && (
                    <span className="text-green-400 ml-2">Token configured (hidden)</span>
                  )}
                </p>
              </div>

              <div>
                <label className="block text-sm font-medium mb-2">Default Namespace / Group</label>
                <input
                  type="text"
                  placeholder="group/subgroup"
                  value={localConfig.gitlab_namespace || ''}
                  onChange={(e) => setLocalConfig({ ...localConfig, gitlab_namespace: e.target.value })}
                  className={cn(
                    'w-full px-3 py-2 rounded-lg text-sm',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring',
                    'font-mono'
                  )}
                />
                <p className="text-xs text-muted-foreground mt-1">
                  Default group path for new projects (e.g., <code className="px-1 bg-muted rounded">myteam/projects</code>)
                </p>
              </div>

              {/* Skip SSL Verification */}
              <div className="p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                <label className="flex items-center gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={localConfig.gitlab_skip_ssl || false}
                    onChange={(e) => setLocalConfig({ ...localConfig, gitlab_skip_ssl: e.target.checked })}
                    className="w-4 h-4 rounded border-input"
                  />
                  <div>
                    <div className="font-medium text-yellow-200 text-sm">Skip SSL Verification</div>
                    <p className="text-xs text-muted-foreground">
                      Enable for internal GitLab servers with self-signed certificates.
                      Not recommended for public servers.
                    </p>
                  </div>
                </label>
              </div>

              {/* Test Connection Button */}
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={async () => {
                    // Save current settings first (including skip_ssl)
                    if (localConfig.gitlab_url) {
                      const configToSave: Record<string, unknown> = {
                        gitlab_url: localConfig.gitlab_url,
                        gitlab_namespace: localConfig.gitlab_namespace,
                        gitlab_skip_ssl: localConfig.gitlab_skip_ssl,
                      }
                      if (localConfig.gitlab_token && localConfig.gitlab_token !== '***') {
                        configToSave.gitlab_token = localConfig.gitlab_token
                      }
                      await updateConfig(configToSave)
                    }
                    setGitlabTestStatus({ status: 'testing' })
                    try {
                      const result = await testGitLabConnection()
                      setGitlabTestStatus({
                        status: 'success',
                        message: `Connected as ${result.name} (@${result.user})`,
                      })
                    } catch (e) {
                      setGitlabTestStatus({
                        status: 'error',
                        message: e instanceof Error ? e.message : 'Connection failed',
                      })
                    }
                  }}
                  disabled={!localConfig.gitlab_url || (!localConfig.gitlab_token && !config?.gitlab_configured) || gitlabTestStatus.status === 'testing'}
                  className={cn(
                    'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                    'bg-orange-500 text-white',
                    'hover:bg-orange-600 transition-colors',
                    'disabled:opacity-50 disabled:cursor-not-allowed'
                  )}
                >
                  {gitlabTestStatus.status === 'testing' ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <ExternalLink className="w-4 h-4" />
                  )}
                  Test Connection
                </button>

                {gitlabTestStatus.status === 'success' && (
                  <span className="text-sm text-green-400 flex items-center gap-1">
                    <Check className="w-4 h-4" />
                    {gitlabTestStatus.message}
                  </span>
                )}
                {gitlabTestStatus.status === 'error' && (
                  <span className="text-sm text-red-400">
                    {gitlabTestStatus.message}
                  </span>
                )}
              </div>
            </div>
          </section>

          {/* Projects */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">Projects</h2>
                <p className="text-sm text-muted-foreground">
                  Add your projects so MO knows their tech stack and can work on them directly.
                  Reference by name in chat: "add auth to <span className="text-primary">my-project</span>"
                </p>
              </div>
              <button
                onClick={() => {
                  setIsAddingProject(true)
                  setEditingProject({ ...emptyProject })
                  setProjectError(null)
                }}
                disabled={isAddingProject}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm',
                  'bg-primary text-primary-foreground',
                  'hover:bg-primary/90 transition-colors',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                <Plus className="w-4 h-4" />
                Add Project
              </button>
            </div>

            {projectError && (
              <div className="p-3 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                {projectError}
              </div>
            )}

            {/* Project Editor */}
            {editingProject && (
              <div className="p-4 mb-4 rounded-lg border border-primary/50 bg-primary/5">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="font-medium">
                    {isAddingProject ? 'New Project' : `Edit: ${editingProject.name}`}
                  </h3>
                  <button
                    onClick={() => {
                      setEditingProject(null)
                      setIsAddingProject(false)
                      setProjectError(null)
                    }}
                    className="text-muted-foreground hover:text-foreground"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Error display inside editor */}
                {projectError && (
                  <div className="p-3 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                    {projectError}
                  </div>
                )}

                <div className="space-y-4">
                  {/* Path with Browse and Analyze buttons */}
                  <div>
                    <label className="block text-sm font-medium mb-1">Project Path</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        placeholder="/path/to/project"
                        value={editingProject.path}
                        onChange={(e) => setEditingProject({ ...editingProject, path: e.target.value })}
                        className={cn(
                          'flex-1 px-3 py-2 rounded-lg text-sm',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring',
                          'font-mono'
                        )}
                      />
                      <button
                        onClick={() => {
                          setFolderBrowserTarget('project')
                          setShowFolderBrowser(true)
                        }}
                        className={cn(
                          'flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium',
                          'bg-muted border border-input',
                          'hover:bg-muted/80 transition-colors'
                        )}
                        title="Browse folders"
                      >
                        <FolderSearch className="w-4 h-4" />
                        Browse
                      </button>
                      <button
                        onClick={handleAnalyzeProject}
                        disabled={!editingProject.path || isAnalyzing}
                        className={cn(
                          'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
                          'bg-violet-500 text-white',
                          'hover:bg-violet-600 transition-colors',
                          'disabled:opacity-50 disabled:cursor-not-allowed'
                        )}
                        title="Analyze project to auto-detect tech stack, patterns, etc."
                      >
                        {isAnalyzing ? (
                          <Loader2 className="w-4 h-4 animate-spin" />
                        ) : (
                          <Sparkles className="w-4 h-4" />
                        )}
                        Analyze
                      </button>
                    </div>
                    <p className="text-xs text-muted-foreground mt-1">
                      Browse to select folder, then click Analyze to auto-detect project settings
                    </p>
                  </div>

                  {/* Name field */}
                  <div>
                    <label className="block text-sm font-medium mb-1">Name</label>
                    <input
                      type="text"
                      placeholder="my-project"
                      value={editingProject.name}
                      onChange={(e) => setEditingProject({ ...editingProject, name: e.target.value })}
                      disabled={!isAddingProject}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring',
                        !isAddingProject && 'opacity-60'
                      )}
                    />
                    <p className="text-xs text-muted-foreground mt-1">
                      Use this name to reference the project in chat (e.g., "work on my-project")
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Description</label>
                    <input
                      type="text"
                      placeholder="Brief description of the project"
                      value={editingProject.description}
                      onChange={(e) => setEditingProject({ ...editingProject, description: e.target.value })}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring'
                      )}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Tech Stack (comma-separated)</label>
                    <input
                      type="text"
                      placeholder="Python, FastAPI, React, PostgreSQL"
                      value={editingProject.tech_stack.join(', ')}
                      onChange={(e) => setEditingProject({
                        ...editingProject,
                        tech_stack: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      })}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring'
                      )}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Conventions (comma-separated)</label>
                    <input
                      type="text"
                      placeholder="Type hints required, Use ruff for linting"
                      value={editingProject.conventions.join(', ')}
                      onChange={(e) => setEditingProject({
                        ...editingProject,
                        conventions: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      })}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring'
                      )}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Dependencies (comma-separated)</label>
                    <input
                      type="text"
                      placeholder="fastapi, sqlalchemy, react"
                      value={editingProject.dependencies.join(', ')}
                      onChange={(e) => setEditingProject({
                        ...editingProject,
                        dependencies: e.target.value.split(',').map(s => s.trim()).filter(Boolean)
                      })}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring'
                      )}
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium mb-1">Notes</label>
                    <textarea
                      placeholder="Additional notes about the project structure, patterns, etc."
                      value={editingProject.notes}
                      onChange={(e) => setEditingProject({ ...editingProject, notes: e.target.value })}
                      rows={3}
                      className={cn(
                        'w-full px-3 py-2 rounded-lg text-sm',
                        'bg-muted border border-input',
                        'focus:outline-none focus:ring-2 focus:ring-ring',
                        'resize-none'
                      )}
                    />
                  </div>

                  {/* Filesystem Access Option */}
                  <div className="p-3 rounded-lg bg-muted/50 border border-border">
                    <label className="flex items-start gap-3 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingProject.auto_add_filesystem ?? true}
                        onChange={(e) => setEditingProject({ ...editingProject, auto_add_filesystem: e.target.checked })}
                        className="w-5 h-5 mt-0.5 rounded border-input"
                      />
                      <div>
                        <div className="font-medium flex items-center gap-2">
                          <ShieldCheck className="w-4 h-4 text-green-500" />
                          Grant Write Access
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Allow MO to modify files directly in this project folder.
                          Required for coding tasks.
                        </p>
                      </div>
                    </label>
                  </div>

                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => {
                        setEditingProject(null)
                        setIsAddingProject(false)
                        setProjectError(null)
                      }}
                      className="px-4 py-2 rounded-lg text-sm hover:bg-muted transition-colors"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        if (isAddingProject) {
                          createProjectMutation.mutate(editingProject)
                        } else {
                          updateProjectMutation.mutate({ name: editingProject.name, project: editingProject })
                        }
                      }}
                      disabled={!editingProject.name || !editingProject.path || createProjectMutation.isPending || updateProjectMutation.isPending}
                      className={cn(
                        'flex items-center gap-2 px-4 py-2 rounded-lg text-sm',
                        'bg-primary text-primary-foreground',
                        'hover:bg-primary/90 transition-colors',
                        'disabled:opacity-50 disabled:cursor-not-allowed'
                      )}
                    >
                      {(createProjectMutation.isPending || updateProjectMutation.isPending) ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Check className="w-4 h-4" />
                      )}
                      {isAddingProject ? 'Create' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {/* Projects List */}
            {projectsLoading ? (
              <div className="flex items-center justify-center p-8">
                <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
              </div>
            ) : projects.length === 0 && !editingProject ? (
              <div className="p-8 rounded-lg border border-dashed border-border text-center">
                <FolderOpen className="w-12 h-12 mx-auto text-muted-foreground mb-3" />
                <p className="text-muted-foreground">No projects configured</p>
                <p className="text-sm text-muted-foreground mt-1 mb-4">
                  Add a project to let MO understand and work on your codebase
                </p>
                <button
                  onClick={() => {
                    setIsAddingProject(true)
                    setEditingProject({ ...emptyProject })
                    setProjectError(null)
                  }}
                  className={cn(
                    'inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm',
                    'bg-primary text-primary-foreground',
                    'hover:bg-primary/90 transition-colors'
                  )}
                >
                  <Plus className="w-4 h-4" />
                  Add Your First Project
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                {projects.map((project) => (
                  <div
                    key={project.name}
                    className={cn(
                      'p-4 rounded-lg border border-border',
                      'hover:border-primary/30 transition-colors'
                    )}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <FolderOpen className="w-5 h-5 text-primary" />
                          <span className="font-medium">{project.name}</span>
                          {project.filesystem_access ? (
                            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400">
                              <ShieldCheck className="w-3 h-3" />
                              Write
                            </span>
                          ) : (
                            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-yellow-500/20 text-yellow-400">
                              <Shield className="w-3 h-3" />
                              Read-only
                            </span>
                          )}
                        </div>
                        <p className="text-sm text-muted-foreground mt-1 truncate">
                          {project.description || project.path}
                        </p>
                        {project.tech_stack.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {project.tech_stack.slice(0, 5).map((tech) => (
                              <span
                                key={tech}
                                className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground"
                              >
                                {tech}
                              </span>
                            ))}
                            {project.tech_stack.length > 5 && (
                              <span className="text-xs text-muted-foreground">
                                +{project.tech_stack.length - 5} more
                              </span>
                            )}
                          </div>
                        )}
                      </div>
                      <div className="flex items-center gap-1 ml-4">
                        <button
                          onClick={() => {
                            setEditingProject({ ...project, auto_add_filesystem: true })
                            setIsAddingProject(false)
                            setProjectError(null)
                          }}
                          className="p-2 rounded-lg hover:bg-muted transition-colors"
                          title="Edit project"
                        >
                          <Edit3 className="w-4 h-4 text-muted-foreground" />
                        </button>
                        <button
                          onClick={() => {
                            if (confirm(`Delete project "${project.name}"?`)) {
                              deleteProjectMutation.mutate(project.name)
                            }
                          }}
                          className="p-2 rounded-lg hover:bg-red-500/10 transition-colors"
                          title="Delete project"
                        >
                          <Trash2 className="w-4 h-4 text-red-400" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Skills */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <Wand2 className="w-5 h-5 text-violet-500" />
              Skills
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Skills are automatically selected based on task keywords. They inject quality guidelines and best practices.
            </p>

            {skills.length === 0 ? (
              <div className="p-6 rounded-lg border border-dashed border-border text-center">
                <Wand2 className="w-10 h-10 mx-auto text-muted-foreground mb-3" />
                <p className="text-muted-foreground">No skills loaded</p>
                <p className="text-sm text-muted-foreground mt-1">
                  Add YAML skill files to <code className="px-1 bg-muted rounded">~/.maratos/skills/</code>
                </p>
              </div>
            ) : (
              <div className="space-y-2">
                {skills.map((skill: Skill) => (
                  <details key={skill.id} className="group">
                    <summary className="p-3 rounded-lg border border-border hover:border-violet-500/30 cursor-pointer transition-colors list-none">
                      <div className="flex items-center gap-3">
                        <ChevronRight className="w-4 h-4 text-muted-foreground group-open:rotate-90 transition-transform" />
                        <div className="w-8 h-8 rounded-lg bg-violet-500/20 flex items-center justify-center">
                          <Wand2 className="w-4 h-4 text-violet-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium">{skill.name}</div>
                          <div className="text-xs text-muted-foreground truncate">{skill.description}</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <span className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                            {skill.workflow_steps} steps
                          </span>
                          <span className="text-xs text-muted-foreground">v{skill.version}</span>
                        </div>
                      </div>
                    </summary>
                    <div className="mt-2 ml-7 p-3 rounded-lg bg-muted/50 border border-border">
                      <div className="mb-3">
                        <span className="text-xs font-medium text-muted-foreground">TRIGGERS:</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {skill.triggers.map((trigger) => (
                            <span key={trigger} className="text-xs px-2 py-0.5 rounded-full bg-violet-500/20 text-violet-300">
                              {trigger}
                            </span>
                          ))}
                        </div>
                      </div>
                      {skill.tags.length > 0 && (
                        <div>
                          <span className="text-xs font-medium text-muted-foreground">TAGS:</span>
                          <div className="flex flex-wrap gap-1 mt-1">
                            {skill.tags.map((tag) => (
                              <span key={tag} className="text-xs px-2 py-0.5 rounded-full bg-muted text-muted-foreground">
                                {tag}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  </details>
                ))}
              </div>
            )}

            <div className="mt-4 p-3 rounded-lg bg-violet-500/10 border border-violet-500/20">
              <p className="text-sm text-violet-200">
                <strong>Auto-selection:</strong> When you send a message containing trigger keywords (e.g., "create api endpoint"),
                matching skills are automatically activated. Their quality checklists and best practices are injected into the agent's context.
              </p>
            </div>
          </section>

          {/* Agent Metrics */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <Activity className="w-5 h-5 text-blue-500" />
              Agent Performance
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Monitor agent success rates, task durations, and rate limits
            </p>
            <AgentMetrics />
          </section>

          {/* Workspace Management */}
          <section>
            <h2 className="text-lg font-semibold mb-2 flex items-center gap-2">
              <HardDrive className="w-5 h-5 text-emerald-500" />
              Workspace Management
            </h2>
            <p className="text-sm text-muted-foreground mb-4">
              Monitor and clean up workspace files
            </p>
            <WorkspaceManager />
          </section>

          {/* Debug Mode */}
          <section>
            <h2 className="text-lg font-semibold mb-4">Developer</h2>
            <label className="flex items-center gap-3 cursor-pointer">
              <input
                type="checkbox"
                checked={localConfig.debug || false}
                onChange={(e) => setLocalConfig({ ...localConfig, debug: e.target.checked })}
                className="w-5 h-5 rounded border-input"
              />
              <div>
                <div className="font-medium">Debug Mode</div>
                <div className="text-sm text-muted-foreground">
                  Enable verbose logging
                </div>
              </div>
            </label>
          </section>
        </div>
      </div>

      {/* Folder Browser Modal */}
      <FolderBrowser
        isOpen={showFolderBrowser}
        onClose={() => setShowFolderBrowser(false)}
        onSelect={(path) => {
          if (folderBrowserTarget === 'project' && editingProject) {
            setEditingProject({ ...editingProject, path })
          } else if (folderBrowserTarget === 'allowedDir') {
            setNewAllowedDir(path)
          }
        }}
        initialPath={
          folderBrowserTarget === 'project' && editingProject?.path
            ? editingProject.path
            : '~'
        }
        title={folderBrowserTarget === 'project' ? 'Select Project Folder' : 'Select Directory'}
      />
    </div>
  )
}
