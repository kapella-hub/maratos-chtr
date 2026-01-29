import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Settings, Save, Loader2, FolderOpen, Plus, Trash2, Edit3, X, Check, Sparkles, Shield, ShieldCheck, FolderSearch, GitBranch, FileText, ChevronDown, ChevronRight, RefreshCw, Scale } from 'lucide-react'
import { fetchConfig, updateConfig, type Config, fetchProjects, createProject, updateProject, deleteProject, analyzeProject, removeAllowedDirectory, addAllowedDirectory, type Project, fetchProjectDocs, createProjectDoc, updateProjectDoc, deleteProjectDoc, fetchProjectDoc, fetchRules, fetchRule, createRule, updateRule, deleteRule, createExampleRules } from '@/lib/api'
import { cn } from '@/lib/utils'
import { useState, useEffect } from 'react'
import FolderBrowser from '@/components/FolderBrowser'

interface ChannelConfig {
  allowed_write_dirs?: string
  all_allowed_dirs?: string[]
  git_auto_commit?: boolean
  git_push_to_remote?: boolean
  git_create_pr?: boolean
  git_default_branch?: string
  git_commit_prefix?: string
  git_remote_name?: string
}

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
  const [reanalyzingProject, setReanalyzingProject] = useState<string | null>(null)
  const [newAllowedDir, setNewAllowedDir] = useState('')
  const [showFolderBrowser, setShowFolderBrowser] = useState(false)
  const [folderBrowserTarget, setFolderBrowserTarget] = useState<'project' | 'allowedDir'>('project')
  const [removingDir, setRemovingDir] = useState<string | null>(null)
  // Documentation state
  const [showDocsPanel, setShowDocsPanel] = useState(false)
  const [editingDoc, setEditingDoc] = useState<{ title: string; content: string; tags: string; is_core: boolean; id?: string } | null>(null)
  const [docError, setDocError] = useState<string | null>(null)
  // Rules state
  const [editingRule, setEditingRule] = useState<{ id?: string; name: string; description: string; content: string; tags: string } | null>(null)
  const [ruleError, setRuleError] = useState<string | null>(null)

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
    onError: (error: Error) => setProjectError(error.message),
  })

  const updateProjectMutation = useMutation({
    mutationFn: ({ name, project }: { name: string; project: Project }) => updateProject(name, project),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      setEditingProject(null)
      setProjectError(null)
    },
    onError: (error: Error) => setProjectError(error.message),
  })

  const deleteProjectMutation = useMutation({
    mutationFn: deleteProject,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['projects'] }),
  })

  const mutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['config'] }),
  })

  // Project docs queries and mutations
  const { data: projectDocs = [], isLoading: docsLoading } = useQuery({
    queryKey: ['project-docs', editingProject?.name],
    queryFn: () => editingProject?.name ? fetchProjectDocs(editingProject.name) : Promise.resolve([]),
    enabled: !!editingProject?.name && !isAddingProject,
  })

  const createDocMutation = useMutation({
    mutationFn: ({ projectName, data }: { projectName: string; data: { title: string; content: string; tags?: string[]; is_core?: boolean } }) =>
      createProjectDoc(projectName, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-docs', editingProject?.name] })
      setEditingDoc(null)
      setDocError(null)
    },
    onError: (error: Error) => setDocError(error.message),
  })

  const updateDocMutation = useMutation({
    mutationFn: ({ projectName, docId, data }: { projectName: string; docId: string; data: { title?: string; content?: string; tags?: string[]; is_core?: boolean } }) =>
      updateProjectDoc(projectName, docId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['project-docs', editingProject?.name] })
      setEditingDoc(null)
      setDocError(null)
    },
    onError: (error: Error) => setDocError(error.message),
  })

  const deleteDocMutation = useMutation({
    mutationFn: ({ projectName, docId }: { projectName: string; docId: string }) =>
      deleteProjectDoc(projectName, docId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['project-docs', editingProject?.name] }),
  })

  // Rules queries and mutations
  const { data: rules = [], isLoading: rulesLoading } = useQuery({
    queryKey: ['rules'],
    queryFn: fetchRules,
  })

  const createRuleMutation = useMutation({
    mutationFn: (data: { name: string; description?: string; content: string; tags?: string[] }) => createRule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      setEditingRule(null)
      setRuleError(null)
    },
    onError: (error: Error) => setRuleError(error.message),
  })

  const updateRuleMutation = useMutation({
    mutationFn: ({ id, data }: { id: string; data: { name?: string; description?: string; content?: string; tags?: string[] } }) =>
      updateRule(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['rules'] })
      setEditingRule(null)
      setRuleError(null)
    },
    onError: (error: Error) => setRuleError(error.message),
  })

  const deleteRuleMutation = useMutation({
    mutationFn: deleteRule,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rules'] }),
  })

  const createExamplesMutation = useMutation({
    mutationFn: createExampleRules,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rules'] }),
    onError: (error: Error) => setRuleError(error.message),
  })

  useEffect(() => {
    if (config) setLocalConfig(config)
  }, [config])

  const handleSave = () => mutation.mutate(localConfig)
  const hasChanges = JSON.stringify(config) !== JSON.stringify(localConfig)

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
        name: editingProject.name || editingProject.path.split('/').pop()?.toLowerCase().replace(/[^a-z0-9-_]/g, '-') || '',
      })
    } catch (e) {
      setProjectError(e instanceof Error ? e.message : 'Failed to analyze project')
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleReanalyzeProject = async (project: Project) => {
    setReanalyzingProject(project.name)
    try {
      const analysis = await analyzeProject(project.path)
      // Update the project with new analysis
      await updateProjectMutation.mutateAsync({
        name: project.name,
        project: {
          ...project,
          description: analysis.description || project.description,
          tech_stack: analysis.tech_stack.length > 0 ? analysis.tech_stack : project.tech_stack,
          conventions: analysis.conventions.length > 0 ? analysis.conventions : project.conventions,
          patterns: analysis.patterns.length > 0 ? analysis.patterns : project.patterns,
          dependencies: analysis.dependencies.length > 0 ? analysis.dependencies : project.dependencies,
          notes: analysis.notes || project.notes,
        },
      })
    } catch (e) {
      console.error('Failed to re-analyze project:', e)
    } finally {
      setReanalyzingProject(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="px-6 py-4 border-b border-border flex items-center justify-between bg-background/95 backdrop-blur sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <Settings className="w-5 h-5 text-muted-foreground" />
          <h1 className="text-lg font-semibold">Settings</h1>
        </div>
        <button
          onClick={handleSave}
          disabled={!hasChanges || mutation.isPending}
          className={cn(
            'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium',
            'bg-primary text-primary-foreground',
            'hover:bg-primary/90 transition-colors',
            'disabled:opacity-50 disabled:cursor-not-allowed'
          )}
        >
          {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          Save Changes
        </button>
      </header>

      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl mx-auto p-6 space-y-6">

          {/* Projects Section */}
          <section className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-primary" />
                <h2 className="font-medium">Projects</h2>
                <span className="text-xs text-muted-foreground">({projects.length})</span>
              </div>
              <button
                onClick={() => {
                  setIsAddingProject(true)
                  setEditingProject({ ...emptyProject })
                  setProjectError(null)
                }}
                disabled={isAddingProject}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                  'bg-primary/10 text-primary hover:bg-primary/20',
                  'disabled:opacity-50 transition-colors'
                )}
              >
                <Plus className="w-3.5 h-3.5" />
                Add
              </button>
            </div>

            <div className="p-4">
              {projectError && (
                <div className="p-3 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {projectError}
                </div>
              )}

              {/* Project Editor */}
              {editingProject && (
                <div className="p-4 mb-4 rounded-lg border border-primary/30 bg-primary/5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-medium text-sm">
                      {isAddingProject ? 'Add Project' : `Edit: ${editingProject.name}`}
                    </h3>
                    <button
                      onClick={() => { setEditingProject(null); setIsAddingProject(false); setProjectError(null) }}
                      className="p-1 hover:bg-muted rounded"
                    >
                      <X className="w-4 h-4 text-muted-foreground" />
                    </button>
                  </div>

                  <div className="space-y-3">
                    {/* Path */}
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Path</label>
                      <div className="flex gap-2">
                        <input
                          type="text"
                          placeholder="/path/to/project"
                          value={editingProject.path}
                          onChange={(e) => setEditingProject({ ...editingProject, path: e.target.value })}
                          className="flex-1 px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                        />
                        <button
                          onClick={() => { setFolderBrowserTarget('project'); setShowFolderBrowser(true) }}
                          className="px-3 py-2 rounded-lg text-sm bg-muted border border-input hover:bg-muted/80"
                        >
                          <FolderSearch className="w-4 h-4" />
                        </button>
                        <button
                          onClick={handleAnalyzeProject}
                          disabled={!editingProject.path || isAnalyzing}
                          className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm bg-violet-500 text-white hover:bg-violet-600 disabled:opacity-50"
                        >
                          {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
                          Analyze
                        </button>
                      </div>
                    </div>

                    {/* Name & Description */}
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
                        <input
                          type="text"
                          placeholder="my-project"
                          value={editingProject.name}
                          onChange={(e) => setEditingProject({ ...editingProject, name: e.target.value })}
                          disabled={!isAddingProject}
                          className={cn("w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring", !isAddingProject && "opacity-60")}
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Description</label>
                        <input
                          type="text"
                          placeholder="Brief description"
                          value={editingProject.description}
                          onChange={(e) => setEditingProject({ ...editingProject, description: e.target.value })}
                          className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                      </div>
                    </div>

                    {/* Tech Stack */}
                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Tech Stack</label>
                      <input
                        type="text"
                        placeholder="Python, FastAPI, React"
                        value={editingProject.tech_stack.join(', ')}
                        onChange={(e) => setEditingProject({ ...editingProject, tech_stack: e.target.value.split(',').map(s => s.trim()).filter(Boolean) })}
                        className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    {/* Write Access Toggle */}
                    <label className="flex items-center gap-3 p-3 rounded-lg bg-muted/50 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={editingProject.auto_add_filesystem ?? true}
                        onChange={(e) => setEditingProject({ ...editingProject, auto_add_filesystem: e.target.checked })}
                        className="w-4 h-4 rounded"
                      />
                      <div className="flex-1">
                        <div className="text-sm font-medium flex items-center gap-1.5">
                          <ShieldCheck className="w-3.5 h-3.5 text-green-500" />
                          Grant write access
                        </div>
                        <p className="text-xs text-muted-foreground">Allow MO to modify files in this project</p>
                      </div>
                    </label>

                    {/* Documentation Panel - only for existing projects */}
                    {!isAddingProject && (
                      <div className="border border-border rounded-lg overflow-hidden">
                        <button
                          onClick={() => setShowDocsPanel(!showDocsPanel)}
                          className="w-full flex items-center gap-2 px-3 py-2 bg-muted/30 hover:bg-muted/50 transition-colors"
                        >
                          {showDocsPanel ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
                          <FileText className="w-4 h-4 text-blue-500" />
                          <span className="text-sm font-medium">Documentation</span>
                          <span className="text-xs text-muted-foreground ml-auto">
                            {projectDocs.length} {projectDocs.length === 1 ? 'doc' : 'docs'}
                          </span>
                        </button>

                        {showDocsPanel && (
                          <div className="p-3 space-y-3 border-t border-border">
                            {docError && (
                              <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-red-400 text-xs">
                                {docError}
                              </div>
                            )}

                            {/* Doc Editor */}
                            {editingDoc && (
                              <div className="p-3 rounded-lg border border-blue-500/30 bg-blue-500/5 space-y-2">
                                <input
                                  type="text"
                                  placeholder="Document title"
                                  value={editingDoc.title}
                                  onChange={(e) => setEditingDoc({ ...editingDoc, title: e.target.value })}
                                  className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                                />
                                <textarea
                                  placeholder="Documentation content (markdown supported)"
                                  value={editingDoc.content}
                                  onChange={(e) => setEditingDoc({ ...editingDoc, content: e.target.value })}
                                  rows={6}
                                  className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono resize-y"
                                />
                                <input
                                  type="text"
                                  placeholder="Tags (comma-separated)"
                                  value={editingDoc.tags}
                                  onChange={(e) => setEditingDoc({ ...editingDoc, tags: e.target.value })}
                                  className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                                />
                                <div className="flex items-center justify-between">
                                  <label className="flex items-center gap-2 text-xs cursor-pointer">
                                    <input
                                      type="checkbox"
                                      checked={editingDoc.is_core}
                                      onChange={(e) => setEditingDoc({ ...editingDoc, is_core: e.target.checked })}
                                      className="rounded border-input"
                                    />
                                    <span className="text-muted-foreground">Core doc</span>
                                    <span className="text-[10px] text-muted-foreground/70">(always included in context)</span>
                                  </label>
                                  <div className="flex gap-2">
                                    <button
                                      onClick={() => { setEditingDoc(null); setDocError(null) }}
                                      className="px-3 py-1.5 rounded text-xs hover:bg-muted"
                                    >
                                      Cancel
                                    </button>
                                    <button
                                      onClick={() => {
                                        if (!editingDoc.title.trim() || !editingDoc.content.trim()) {
                                          setDocError('Title and content are required')
                                          return
                                        }
                                        const tags = editingDoc.tags.split(',').map(t => t.trim()).filter(Boolean)
                                        if (editingDoc.id) {
                                          updateDocMutation.mutate({
                                            projectName: editingProject.name,
                                            docId: editingDoc.id,
                                            data: { title: editingDoc.title, content: editingDoc.content, tags, is_core: editingDoc.is_core }
                                          })
                                        } else {
                                          createDocMutation.mutate({
                                            projectName: editingProject.name,
                                            data: { title: editingDoc.title, content: editingDoc.content, tags, is_core: editingDoc.is_core }
                                          })
                                        }
                                      }}
                                      disabled={createDocMutation.isPending || updateDocMutation.isPending}
                                      className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs bg-blue-500 text-white hover:bg-blue-600 disabled:opacity-50"
                                    >
                                      {(createDocMutation.isPending || updateDocMutation.isPending) && <Loader2 className="w-3 h-3 animate-spin" />}
                                      {editingDoc.id ? 'Update' : 'Add'}
                                    </button>
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Add Doc Button */}
                            {!editingDoc && (
                              <button
                                onClick={() => setEditingDoc({ title: '', content: '', tags: '', is_core: false })}
                                className="w-full flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors"
                              >
                                <Plus className="w-3.5 h-3.5" />
                                Add Documentation
                              </button>
                            )}

                            {/* Docs List */}
                            {docsLoading ? (
                              <div className="flex justify-center py-4">
                                <Loader2 className="w-4 h-4 animate-spin text-muted-foreground" />
                              </div>
                            ) : projectDocs.length === 0 && !editingDoc ? (
                              <p className="text-center text-xs text-muted-foreground py-4">
                                No documentation yet. Add notes, API guides, or conventions.
                              </p>
                            ) : (
                              <div className="space-y-1">
                                {projectDocs.map((doc) => (
                                  <div
                                    key={doc.id}
                                    className={cn(
                                      "flex items-center gap-2 p-2 rounded-lg hover:bg-muted/50 group",
                                      doc.is_core && "border-l-2 border-violet-500 pl-3"
                                    )}
                                  >
                                    <FileText className={cn("w-3.5 h-3.5", doc.is_core ? "text-violet-500" : "text-muted-foreground")} />
                                    <div className="flex-1 min-w-0">
                                      <div className="flex items-center gap-2">
                                        <span className="text-sm font-medium truncate">{doc.title}</span>
                                        {doc.is_core && (
                                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-violet-500/20 text-violet-400">core</span>
                                        )}
                                        {doc.has_embedding && (
                                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400" title="Semantic search enabled">RAG</span>
                                        )}
                                      </div>
                                      {doc.tags.length > 0 && (
                                        <div className="flex gap-1 mt-0.5">
                                          {doc.tags.slice(0, 3).map(tag => (
                                            <span key={tag} className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{tag}</span>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                    <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                      <button
                                        onClick={async () => {
                                          try {
                                            const fullDoc = await fetchProjectDoc(editingProject.name, doc.id)
                                            setEditingDoc({ id: doc.id, title: fullDoc.title, content: fullDoc.content, tags: fullDoc.tags.join(', '), is_core: fullDoc.is_core })
                                          } catch (e) {
                                            setDocError('Failed to load doc')
                                          }
                                        }}
                                        className="p-1 rounded hover:bg-muted"
                                      >
                                        <Edit3 className="w-3 h-3 text-muted-foreground" />
                                      </button>
                                      <button
                                        onClick={() => {
                                          if (confirm(`Delete "${doc.title}"?`)) {
                                            deleteDocMutation.mutate({ projectName: editingProject.name, docId: doc.id })
                                          }
                                        }}
                                        className="p-1 rounded hover:bg-red-500/10"
                                      >
                                        <Trash2 className="w-3 h-3 text-red-400" />
                                      </button>
                                    </div>
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        onClick={() => { setEditingProject(null); setIsAddingProject(false); setProjectError(null) }}
                        className="px-4 py-2 rounded-lg text-sm hover:bg-muted"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          if (isAddingProject) createProjectMutation.mutate(editingProject)
                          else updateProjectMutation.mutate({ name: editingProject.name, project: editingProject })
                        }}
                        disabled={!editingProject.name || !editingProject.path || createProjectMutation.isPending || updateProjectMutation.isPending}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        {(createProjectMutation.isPending || updateProjectMutation.isPending) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        {isAddingProject ? 'Create' : 'Save'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Projects List */}
              {projectsLoading ? (
                <div className="flex justify-center p-8">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : projects.length === 0 && !editingProject ? (
                <div className="text-center py-8 text-muted-foreground">
                  <FolderOpen className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No projects yet</p>
                  <p className="text-xs mt-1">Add a project to let MO work on your code</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {projects.map((project) => (
                    <div key={project.name} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-primary/30 transition-colors">
                      <FolderOpen className="w-4 h-4 text-primary flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-sm">{project.name}</span>
                          {project.filesystem_access ? (
                            <ShieldCheck className="w-3.5 h-3.5 text-green-500" />
                          ) : (
                            <Shield className="w-3.5 h-3.5 text-yellow-500" />
                          )}
                        </div>
                        <p className="text-xs text-muted-foreground truncate">{project.path}</p>
                      </div>
                      {project.tech_stack.length > 0 && (
                        <div className="hidden sm:flex gap-1">
                          {project.tech_stack.slice(0, 3).map((tech) => (
                            <span key={tech} className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{tech}</span>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleReanalyzeProject(project)}
                          disabled={reanalyzingProject === project.name}
                          className="p-1.5 rounded hover:bg-violet-500/10 disabled:opacity-50"
                          title="Re-analyze project"
                        >
                          {reanalyzingProject === project.name ? (
                            <Loader2 className="w-3.5 h-3.5 text-violet-400 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3.5 h-3.5 text-violet-400" />
                          )}
                        </button>
                        <button
                          onClick={() => { setEditingProject({ ...project, auto_add_filesystem: true }); setIsAddingProject(false); setProjectError(null) }}
                          className="p-1.5 rounded hover:bg-muted"
                          title="Edit project"
                        >
                          <Edit3 className="w-3.5 h-3.5 text-muted-foreground" />
                        </button>
                        <button
                          onClick={() => { if (confirm(`Delete "${project.name}"?`)) deleteProjectMutation.mutate(project.name) }}
                          className="p-1.5 rounded hover:bg-red-500/10"
                          title="Delete project"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-400" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Rules Section */}
          <section className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Scale className="w-4 h-4 text-emerald-500" />
                <h2 className="font-medium">Development Rules</h2>
                <span className="text-xs text-muted-foreground">({rules.length})</span>
              </div>
              <div className="flex items-center gap-2">
                {rules.length === 0 && (
                  <button
                    onClick={() => createExamplesMutation.mutate()}
                    disabled={createExamplesMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm bg-violet-500/10 text-violet-400 hover:bg-violet-500/20 disabled:opacity-50 transition-colors"
                  >
                    {createExamplesMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                    Add Examples
                  </button>
                )}
                <button
                  onClick={() => setEditingRule({ name: '', description: '', content: '', tags: '' })}
                  disabled={!!editingRule}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
                    'bg-primary/10 text-primary hover:bg-primary/20',
                    'disabled:opacity-50 transition-colors'
                  )}
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add
                </button>
              </div>
            </div>

            <div className="p-4">
              {ruleError && (
                <div className="p-3 mb-4 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-sm">
                  {ruleError}
                </div>
              )}

              {/* Rule Editor */}
              {editingRule && (
                <div className="p-4 mb-4 rounded-lg border border-emerald-500/30 bg-emerald-500/5">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="font-medium text-sm">
                      {editingRule.id ? `Edit: ${editingRule.name}` : 'Add Rule'}
                    </h3>
                    <button
                      onClick={() => { setEditingRule(null); setRuleError(null) }}
                      className="p-1 hover:bg-muted rounded"
                    >
                      <X className="w-4 h-4 text-muted-foreground" />
                    </button>
                  </div>

                  <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Name</label>
                        <input
                          type="text"
                          placeholder="Clean Code Standards"
                          value={editingRule.name}
                          onChange={(e) => setEditingRule({ ...editingRule, name: e.target.value })}
                          className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-medium text-muted-foreground mb-1">Tags</label>
                        <input
                          type="text"
                          placeholder="python, testing, backend"
                          value={editingRule.tags}
                          onChange={(e) => setEditingRule({ ...editingRule, tags: e.target.value })}
                          className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                        />
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Description</label>
                      <input
                        type="text"
                        placeholder="Brief description of this rule"
                        value={editingRule.description}
                        onChange={(e) => setEditingRule({ ...editingRule, description: e.target.value })}
                        className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-muted-foreground mb-1">Content (Markdown)</label>
                      <textarea
                        placeholder="Write the rule content here. This will be injected into the prompt when this rule is selected."
                        value={editingRule.content}
                        onChange={(e) => setEditingRule({ ...editingRule, content: e.target.value })}
                        rows={8}
                        className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono resize-y"
                      />
                    </div>

                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        onClick={() => { setEditingRule(null); setRuleError(null) }}
                        className="px-4 py-2 rounded-lg text-sm hover:bg-muted"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={() => {
                          if (!editingRule.name.trim() || !editingRule.content.trim()) {
                            setRuleError('Name and content are required')
                            return
                          }
                          const tags = editingRule.tags.split(',').map(t => t.trim()).filter(Boolean)
                          if (editingRule.id) {
                            updateRuleMutation.mutate({
                              id: editingRule.id,
                              data: { name: editingRule.name, description: editingRule.description, content: editingRule.content, tags }
                            })
                          } else {
                            createRuleMutation.mutate({
                              name: editingRule.name,
                              description: editingRule.description,
                              content: editingRule.content,
                              tags
                            })
                          }
                        }}
                        disabled={createRuleMutation.isPending || updateRuleMutation.isPending}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                      >
                        {(createRuleMutation.isPending || updateRuleMutation.isPending) ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        {editingRule.id ? 'Save' : 'Create'}
                      </button>
                    </div>
                  </div>
                </div>
              )}

              {/* Rules List */}
              {rulesLoading ? (
                <div className="flex justify-center p-8">
                  <Loader2 className="w-5 h-5 animate-spin text-muted-foreground" />
                </div>
              ) : rules.length === 0 && !editingRule ? (
                <div className="text-center py-8 text-muted-foreground">
                  <Scale className="w-10 h-10 mx-auto mb-2 opacity-50" />
                  <p className="text-sm">No rules yet</p>
                  <p className="text-xs mt-1">Add development standards that can be applied to any chat</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {rules.map((rule) => (
                    <div key={rule.id} className="flex items-center gap-3 p-3 rounded-lg border border-border hover:border-emerald-500/30 transition-colors">
                      <Scale className="w-4 h-4 text-emerald-500 flex-shrink-0" />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm">{rule.name}</div>
                        {rule.description && (
                          <p className="text-xs text-muted-foreground truncate">{rule.description}</p>
                        )}
                      </div>
                      {rule.tags.length > 0 && (
                        <div className="hidden sm:flex gap-1">
                          {rule.tags.slice(0, 3).map((tag) => (
                            <span key={tag} className="text-xs px-2 py-0.5 rounded bg-muted text-muted-foreground">{tag}</span>
                          ))}
                        </div>
                      )}
                      <div className="flex gap-1">
                        <button
                          onClick={async () => {
                            try {
                              const fullRule = await fetchRule(rule.id)
                              setEditingRule({
                                id: fullRule.id,
                                name: fullRule.name,
                                description: fullRule.description,
                                content: fullRule.content,
                                tags: fullRule.tags.join(', ')
                              })
                            } catch (e) {
                              setRuleError('Failed to load rule')
                            }
                          }}
                          className="p-1.5 rounded hover:bg-muted"
                          title="Edit rule"
                        >
                          <Edit3 className="w-3.5 h-3.5 text-muted-foreground" />
                        </button>
                        <button
                          onClick={() => { if (confirm(`Delete "${rule.name}"?`)) deleteRuleMutation.mutate(rule.id) }}
                          className="p-1.5 rounded hover:bg-red-500/10"
                          title="Delete rule"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-400" />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          {/* Filesystem Access */}
          <section className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <FolderOpen className="w-4 h-4 text-emerald-500" />
                <h2 className="font-medium">Filesystem Access</h2>
              </div>
              <p className="text-xs text-muted-foreground mt-1">Directories where MO can write files</p>
            </div>

            <div className="p-4 space-y-2">
              {/* Default Workspace */}
              <div className="flex items-center gap-2 p-2 rounded-lg bg-muted/50">
                <FolderOpen className="w-4 h-4 text-primary" />
                <span className="font-mono text-sm flex-1 truncate">{config?.workspace || '~/maratos-workspace'}</span>
                <span className="text-xs px-2 py-0.5 rounded bg-primary/20 text-primary">default</span>
              </div>

              {/* Custom Directories */}
              {(config?.all_allowed_dirs || []).filter(dir => dir !== config?.workspace).map((dir) => (
                <div key={dir} className="flex items-center gap-2 p-2 rounded-lg bg-muted/50">
                  <FolderOpen className="w-4 h-4 text-emerald-500" />
                  <span className="font-mono text-sm flex-1 truncate">{dir}</span>
                  <button
                    onClick={async () => {
                      setRemovingDir(dir)
                      try { await removeAllowedDirectory(dir); queryClient.invalidateQueries({ queryKey: ['config'] }) }
                      catch (e) { console.error(e) }
                      finally { setRemovingDir(null) }
                    }}
                    disabled={removingDir === dir}
                    className="p-1 rounded hover:bg-red-500/10 disabled:opacity-50"
                  >
                    {removingDir === dir ? <Loader2 className="w-3.5 h-3.5 animate-spin text-red-400" /> : <Trash2 className="w-3.5 h-3.5 text-red-400" />}
                  </button>
                </div>
              ))}

              {/* Add Directory */}
              <div className="flex gap-2 pt-2">
                <input
                  type="text"
                  placeholder="/path/to/directory"
                  value={newAllowedDir}
                  onChange={(e) => setNewAllowedDir(e.target.value)}
                  className="flex-1 px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                />
                <button
                  onClick={() => { setFolderBrowserTarget('allowedDir'); setShowFolderBrowser(true) }}
                  className="px-3 py-2 rounded-lg bg-muted border border-input hover:bg-muted/80"
                >
                  <FolderSearch className="w-4 h-4" />
                </button>
                <button
                  onClick={async () => {
                    if (!newAllowedDir.trim()) return
                    try { await addAllowedDirectory(newAllowedDir.trim()); queryClient.invalidateQueries({ queryKey: ['config'] }); setNewAllowedDir('') }
                    catch (e) { console.error(e) }
                  }}
                  disabled={!newAllowedDir.trim()}
                  className="px-4 py-2 rounded-lg text-sm bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  <Plus className="w-4 h-4" />
                </button>
              </div>
            </div>
          </section>

          {/* Git Settings */}
          <section className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3 border-b border-border">
              <div className="flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-orange-500" />
                <h2 className="font-medium">Git Settings</h2>
              </div>
              <p className="text-xs text-muted-foreground mt-1">Default behavior for autonomous git operations</p>
            </div>

            <div className="p-4 space-y-4">
              {/* Toggle Options */}
              <div className="grid grid-cols-3 gap-3">
                <label className="flex items-center gap-2 p-3 rounded-lg border border-border cursor-pointer hover:border-primary/30">
                  <input
                    type="checkbox"
                    checked={localConfig.git_auto_commit !== false}
                    onChange={() => setLocalConfig({ ...localConfig, git_auto_commit: !localConfig.git_auto_commit })}
                    className="w-4 h-4 rounded"
                  />
                  <span className="text-sm">Auto-commit</span>
                </label>
                <label className="flex items-center gap-2 p-3 rounded-lg border border-border cursor-pointer hover:border-primary/30">
                  <input
                    type="checkbox"
                    checked={localConfig.git_push_to_remote || false}
                    onChange={() => setLocalConfig({ ...localConfig, git_push_to_remote: !localConfig.git_push_to_remote })}
                    className="w-4 h-4 rounded"
                  />
                  <span className="text-sm">Push to remote</span>
                </label>
                <label className="flex items-center gap-2 p-3 rounded-lg border border-border cursor-pointer hover:border-primary/30">
                  <input
                    type="checkbox"
                    checked={localConfig.git_create_pr || false}
                    onChange={() => setLocalConfig({ ...localConfig, git_create_pr: !localConfig.git_create_pr })}
                    className="w-4 h-4 rounded"
                  />
                  <span className="text-sm">Create PR</span>
                </label>
              </div>

              {/* Text Inputs */}
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Default Branch</label>
                  <input
                    type="text"
                    placeholder="main"
                    value={localConfig.git_default_branch || ''}
                    onChange={(e) => setLocalConfig({ ...localConfig, git_default_branch: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Remote</label>
                  <input
                    type="text"
                    placeholder="origin"
                    value={localConfig.git_remote_name || ''}
                    onChange={(e) => setLocalConfig({ ...localConfig, git_remote_name: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-muted-foreground mb-1">Commit Prefix</label>
                  <input
                    type="text"
                    placeholder="[MO]"
                    value={localConfig.git_commit_prefix || ''}
                    onChange={(e) => setLocalConfig({ ...localConfig, git_commit_prefix: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg text-sm bg-muted border border-input focus:outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
              </div>
            </div>
          </section>

          {/* Debug Mode */}
          <section className="bg-card rounded-xl border border-border overflow-hidden">
            <div className="px-4 py-3">
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={localConfig.debug || false}
                  onChange={(e) => setLocalConfig({ ...localConfig, debug: e.target.checked })}
                  className="w-4 h-4 rounded"
                />
                <div>
                  <div className="font-medium text-sm">Debug Mode</div>
                  <p className="text-xs text-muted-foreground">Enable verbose logging for troubleshooting</p>
                </div>
              </label>
            </div>
          </section>

        </div>
      </div>

      {/* Folder Browser Modal */}
      <FolderBrowser
        isOpen={showFolderBrowser}
        onClose={() => setShowFolderBrowser(false)}
        onSelect={(path) => {
          if (folderBrowserTarget === 'project' && editingProject) setEditingProject({ ...editingProject, path })
          else if (folderBrowserTarget === 'allowedDir') setNewAllowedDir(path)
        }}
        initialPath={folderBrowserTarget === 'project' && editingProject?.path ? editingProject.path : '~'}
        title={folderBrowserTarget === 'project' ? 'Select Project Folder' : 'Select Directory'}
      />
    </div>
  )
}
