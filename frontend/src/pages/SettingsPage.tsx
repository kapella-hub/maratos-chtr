import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Save, Loader2, MessageSquare, Phone, Building2, ToggleLeft, ToggleRight, FolderOpen, Plus, Trash2, Edit3, X, Check, Link, ExternalLink } from 'lucide-react'
import { fetchConfig, updateConfig, type Config, fetchProjects, createProject, updateProject, deleteProject, type Project } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'

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
}

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [localConfig, setLocalConfig] = useState<Partial<Config & ChannelConfig>>({})
  const [editingProject, setEditingProject] = useState<Project | null>(null)
  const [isAddingProject, setIsAddingProject] = useState(false)
  const [projectError, setProjectError] = useState<string | null>(null)
  const [webexWebhookUrl, setWebexWebhookUrl] = useState('')
  const [webexWebhookStatus, setWebexWebhookStatus] = useState<string | null>(null)
  const [webexWebhookLoading, setWebexWebhookLoading] = useState(false)
  const [newAllowedDir, setNewAllowedDir] = useState('')

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const { data: projects = [], isLoading: projectsLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
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

            {/* Default Workspace */}
            <div className="p-3 rounded-lg bg-muted/50 border border-border mb-3">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-5 h-5 text-primary" />
                <span className="font-mono text-sm">{config?.workspace || '~/maratos-workspace'}</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-primary/20 text-primary ml-auto">
                  default
                </span>
              </div>
            </div>

            {/* Custom Allowed Directories */}
            {(config?.all_allowed_dirs || [])
              .filter(dir => dir !== config?.workspace)
              .map((dir) => (
                <div key={dir} className="p-3 rounded-lg bg-muted/50 border border-border mb-2 flex items-center gap-2">
                  <FolderOpen className="w-5 h-5 text-green-500" />
                  <span className="font-mono text-sm flex-1">{dir}</span>
                  <button
                    onClick={() => {
                      const currentDirs = (localConfig.allowed_write_dirs || config?.allowed_write_dirs || '')
                        .split(',')
                        .map(d => d.trim())
                        .filter(d => d && d !== dir)
                      setLocalConfig({
                        ...localConfig,
                        allowed_write_dirs: currentDirs.join(',')
                      })
                    }}
                    className="p-1.5 rounded hover:bg-red-500/10 transition-colors"
                    title="Remove directory"
                  >
                    <Trash2 className="w-4 h-4 text-red-400" />
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
                  if (!newAllowedDir.trim()) return
                  const currentDirs = (localConfig.allowed_write_dirs || config?.allowed_write_dirs || '')
                    .split(',')
                    .map(d => d.trim())
                    .filter(Boolean)
                  if (!currentDirs.includes(newAllowedDir.trim())) {
                    currentDirs.push(newAllowedDir.trim())
                  }
                  setLocalConfig({
                    ...localConfig,
                    allowed_write_dirs: currentDirs.join(',')
                  })
                  setNewAllowedDir('')
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

          {/* Projects */}
          <section>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-lg font-semibold">Projects</h2>
                <p className="text-sm text-muted-foreground">
                  Project profiles provide context to MO about your codebase
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

                <div className="space-y-4">
                  <div className="grid grid-cols-2 gap-4">
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
                    </div>
                    <div>
                      <label className="block text-sm font-medium mb-1">Path</label>
                      <input
                        type="text"
                        placeholder="/path/to/project"
                        value={editingProject.path}
                        onChange={(e) => setEditingProject({ ...editingProject, path: e.target.value })}
                        className={cn(
                          'w-full px-3 py-2 rounded-lg text-sm',
                          'bg-muted border border-input',
                          'focus:outline-none focus:ring-2 focus:ring-ring'
                        )}
                      />
                    </div>
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
                <p className="text-sm text-muted-foreground mt-1">
                  Add a project to help MO understand your codebase
                </p>
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
                            setEditingProject({ ...project })
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
    </div>
  )
}
