import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Save, Loader2 } from 'lucide-react'
import { fetchConfig, updateConfig, type Config } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'

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

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [localConfig, setLocalConfig] = useState<Partial<Config>>({})

  const { data: config, isLoading } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
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

          {/* Workspace */}
          <section>
            <h2 className="text-lg font-semibold mb-4">Workspace</h2>
            <div className="p-4 rounded-lg bg-muted/50 border border-border">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-lg">📁</span>
                <span className="font-mono text-sm">{config?.workspace || '~/maratos-workspace'}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                MO can read files anywhere but only writes to this directory. 
                External code is copied here before modification.
              </p>
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

          {/* Token Limits */}
          <section>
            <h2 className="text-lg font-semibold mb-4">Token Limits</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <label className="block text-sm font-medium mb-2">
                  Max Context
                </label>
                <input
                  type="number"
                  value={localConfig.max_context_tokens || 0}
                  onChange={(e) => setLocalConfig({ ...localConfig, max_context_tokens: parseInt(e.target.value) })}
                  className={cn(
                    'w-full px-4 py-2 rounded-lg',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring'
                  )}
                />
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">
                  Max Response
                </label>
                <input
                  type="number"
                  value={localConfig.max_response_tokens || 0}
                  onChange={(e) => setLocalConfig({ ...localConfig, max_response_tokens: parseInt(e.target.value) })}
                  className={cn(
                    'w-full px-4 py-2 rounded-lg',
                    'bg-muted border border-input',
                    'focus:outline-none focus:ring-2 focus:ring-ring'
                  )}
                />
              </div>
            </div>
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
