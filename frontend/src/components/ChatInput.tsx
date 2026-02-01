import { useState, useRef, useEffect, KeyboardEvent } from 'react'
import { Send, Square, ListPlus, Sparkles, FolderCode, ChevronDown, ChevronRight, X, Loader2, Scale, Check } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { cn } from '@/lib/utils'
import SkillSelector from './SkillSelector'
import type { Skill, RuleListItem } from '@/lib/api'
import { fetchProjectStructure } from '@/lib/api'

// Session commands
export type SessionCommand = 'reset' | 'status' | 'help'

interface Project {
  name: string
  path: string
}

interface ChatInputProps {
  onSend: (message: string, skill?: Skill | null, ruleIds?: string[]) => void
  onQueue?: (message: string) => void
  onStop?: () => void
  onCommand?: (command: SessionCommand) => void
  isLoading?: boolean
  hasQueue?: boolean
  placeholder?: string
  showSkills?: boolean
  projects?: Project[]
  selectedProject?: string | null
  onProjectSelect?: (projectName: string | null) => void
  rules?: RuleListItem[]
  selectedRules?: string[]
  onRulesChange?: (ruleIds: string[]) => void
}

export default function ChatInput({
  onSend,
  onQueue,
  onStop,
  onCommand,
  isLoading,
  placeholder = 'Ask MO anything...',
  showSkills = true,
  projects = [],
  selectedProject,
  onProjectSelect,
  rules = [],
  selectedRules = [],
  onRulesChange,
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [selectedSkill, setSelectedSkill] = useState<Skill | null>(null)
  const [showProjectDropdown, setShowProjectDropdown] = useState(false)
  const [showRulesDropdown, setShowRulesDropdown] = useState(false)
  const [expandedProject, setExpandedProject] = useState<string | null>(null)
  const [projectStructure, setProjectStructure] = useState<string | null>(null)
  const [loadingStructure, setLoadingStructure] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const projectDropdownRef = useRef<HTMLDivElement>(null)
  const rulesDropdownRef = useRef<HTMLDivElement>(null)

  // Fetch project structure when expanded
  useEffect(() => {
    if (expandedProject) {
      setLoadingStructure(true) // eslint-disable-line
      fetchProjectStructure(expandedProject)
        .then((data) => setProjectStructure(data.structure))
        .catch(() => setProjectStructure(null))
        .finally(() => setLoadingStructure(false))
    } else {
      setProjectStructure(null)
    }
  }, [expandedProject])

  // Close dropdowns when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (projectDropdownRef.current && !projectDropdownRef.current.contains(event.target as Node)) {
        setShowProjectDropdown(false)
        setExpandedProject(null)
      }
      if (rulesDropdownRef.current && !rulesDropdownRef.current.contains(event.target as Node)) {
        setShowRulesDropdown(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px'
    }
  }, [input])

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSubmit = () => {
    if (!input.trim()) return

    const trimmed = input.trim()

    // Check for commands
    if (trimmed.startsWith('/') && onCommand) {
      const cmd = trimmed.slice(1).toLowerCase().split(' ')[0]
      if (cmd === 'reset' || cmd === 'status' || cmd === 'help') {
        onCommand(cmd as SessionCommand)
        setInput('')
        return
      }
    }

    if (isLoading && onQueue) {
      onQueue(trimmed)
      setInput('')
    } else if (!isLoading) {
      onSend(trimmed, selectedSkill, selectedRules.length > 0 ? selectedRules : undefined)
      setInput('')
      setSelectedSkill(null) // Clear skill after sending
    }
  }

  const handleKeyDown = (e: KeyboardEvent) => {
    // Cmd/Ctrl + Enter to send
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      handleSubmit()
      return
    }
    // Enter without shift to send
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
    // Escape to stop
    if (e.key === 'Escape' && isLoading && onStop) {
      onStop()
    }
  }

  const charCount = input.length
  const showCharCount = charCount > 100
  const isOverLimit = charCount > 50000
  const isCommand = input.trim().startsWith('/')

  return (
    <div className="bg-transparent">
      <div className="pb-4 px-4">
        <div className="max-w-3xl mx-auto">
          {/* Input Container */}
          <motion.div
            className={cn(
              'relative rounded-2xl transition-all duration-300',
              'bg-card border shadow-lg',
              isFocused
                ? 'border-primary/50 shadow-primary/10 ring-4 ring-primary/5'
                : 'border-border/50 shadow-black/5',
              isLoading && 'border-amber-500/30'
            )}
          >
            {/* Decorative gradient line at top when focused */}
            <AnimatePresence>
              {isFocused && (
                <motion.div
                  initial={{ scaleX: 0 }}
                  animate={{ scaleX: 1 }}
                  exit={{ scaleX: 0 }}
                  className="absolute top-0 left-4 right-4 h-0.5 bg-gradient-to-r from-violet-500 via-purple-500 to-pink-500 rounded-full"
                />
              )}
            </AnimatePresence>

            {/* Skill Selector */}
            {showSkills && input.length > 0 && !isCommand && (
              <div className="absolute -top-10 left-3">
                <SkillSelector
                  prompt={input}
                  selectedSkill={selectedSkill}
                  onSelect={setSelectedSkill}
                />
              </div>
            )}

            {/* Command hints */}
            <AnimatePresence>
              {isCommand && input.trim() === '/' && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 10 }}
                  className="absolute -top-32 left-3 bg-card border border-border rounded-xl p-3 shadow-xl z-10"
                >
                  <div className="text-xs text-muted-foreground mb-2">Commands:</div>
                  <div className="space-y-1">
                    <button
                      onClick={() => setInput('/reset')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/reset</span>
                      <span className="ml-2 text-muted-foreground">Clear session</span>
                    </button>
                    <button
                      onClick={() => setInput('/status')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/status</span>
                      <span className="ml-2 text-muted-foreground">Show session info</span>
                    </button>
                    <button
                      onClick={() => setInput('/help')}
                      className="w-full text-left px-3 py-2 rounded-lg hover:bg-muted/50 text-sm transition-colors"
                    >
                      <span className="font-mono text-violet-400">/help</span>
                      <span className="ml-2 text-muted-foreground">Show available commands</span>
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Textarea */}
            <div className="flex items-end gap-2 p-3">
              {/* Left icons: Sparkles and optional Project selector */}
              <div className="flex items-center gap-1 flex-shrink-0">
                {/* Sparkles icon */}
                <div className={cn(
                  'p-2 rounded-xl transition-colors duration-200',
                  isFocused ? 'text-primary' : 'text-muted-foreground'
                )}>
                  <Sparkles className="w-5 h-5" />
                </div>

                {/* Project selector button */}
                {projects.length > 0 && onProjectSelect && (
                  <div className="relative" ref={projectDropdownRef}>
                    <button
                      type="button"
                      onClick={() => setShowProjectDropdown(!showProjectDropdown)}
                      disabled={isLoading}
                      className={cn(
                        'flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-sm transition-all',
                        'hover:bg-muted/50 disabled:opacity-50',
                        selectedProject
                          ? 'bg-primary/10 text-primary border border-primary/20'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                      title={selectedProject ? `Project: ${selectedProject}` : 'Select project'}
                    >
                      <FolderCode className="w-4 h-4" />
                      {selectedProject ? (
                        <>
                          <span className="max-w-[100px] truncate">{selectedProject}</span>
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={(e) => {
                              e.stopPropagation()
                              onProjectSelect(null)
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.stopPropagation()
                                onProjectSelect(null)
                              }
                            }}
                            className="p-0.5 hover:bg-primary/20 rounded cursor-pointer"
                          >
                            <X className="w-3 h-3" />
                          </span>
                        </>
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {/* Project dropdown */}
                    <AnimatePresence>
                      {showProjectDropdown && (
                        <motion.div
                          initial={{ opacity: 0, y: 5 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: 5 }}
                          className={cn(
                            "absolute bottom-full left-0 mb-2 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden",
                            expandedProject ? "w-[400px]" : "w-56"
                          )}
                        >
                          <div className="p-2 border-b border-border/50">
                            <span className="text-xs text-muted-foreground px-2">Select project</span>
                          </div>
                          <div className="max-h-[400px] overflow-y-auto py-1">
                            {projects.map((project) => (
                              <div key={project.name}>
                                <div className="flex items-center">
                                  {/* Expand/collapse button */}
                                  <button
                                    type="button"
                                    onClick={(e) => {
                                      e.stopPropagation()
                                      setExpandedProject(expandedProject === project.name ? null : project.name)
                                    }}
                                    className="p-2 text-muted-foreground hover:text-foreground transition-colors"
                                  >
                                    {expandedProject === project.name ? (
                                      <ChevronDown className="w-3.5 h-3.5" />
                                    ) : (
                                      <ChevronRight className="w-3.5 h-3.5" />
                                    )}
                                  </button>
                                  {/* Project button */}
                                  <button
                                    type="button"
                                    onClick={() => {
                                      onProjectSelect(project.name)
                                      setShowProjectDropdown(false)
                                      setExpandedProject(null)
                                    }}
                                    className={cn(
                                      'flex-1 text-left px-2 py-2 text-sm transition-colors',
                                      'hover:bg-muted/50 rounded-r-lg',
                                      selectedProject === project.name && 'bg-primary/10 text-primary'
                                    )}
                                  >
                                    <div className="flex items-center gap-2">
                                      <FolderCode className="w-4 h-4 flex-shrink-0" />
                                      <span className="truncate">{project.name}</span>
                                    </div>
                                  </button>
                                </div>
                                {/* Expanded structure */}
                                <AnimatePresence>
                                  {expandedProject === project.name && (
                                    <motion.div
                                      initial={{ height: 0, opacity: 0 }}
                                      animate={{ height: 'auto', opacity: 1 }}
                                      exit={{ height: 0, opacity: 0 }}
                                      className="overflow-hidden"
                                    >
                                      <div className="ml-6 mr-2 mb-2 p-2 bg-muted/30 rounded-lg border border-border/30">
                                        {loadingStructure ? (
                                          <div className="flex items-center gap-2 text-xs text-muted-foreground py-2">
                                            <Loader2 className="w-3 h-3 animate-spin" />
                                            Loading structure...
                                          </div>
                                        ) : projectStructure ? (
                                          <pre className="text-xs text-muted-foreground font-mono whitespace-pre overflow-x-auto max-h-48">
                                            {projectStructure}
                                          </pre>
                                        ) : (
                                          <div className="text-xs text-muted-foreground py-2">
                                            Unable to load structure
                                          </div>
                                        )}
                                      </div>
                                    </motion.div>
                                  )}
                                </AnimatePresence>
                              </div>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}

                {/* Rules selector button */}
                {rules.length > 0 && onRulesChange && (
                  <div className="relative" ref={rulesDropdownRef}>
                    <button
                      type="button"
                      onClick={() => setShowRulesDropdown(!showRulesDropdown)}
                      disabled={isLoading}
                      className={cn(
                        'flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-sm transition-all',
                        'hover:bg-muted/50 disabled:opacity-50',
                        selectedRules.length > 0
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                          : 'text-muted-foreground hover:text-foreground'
                      )}
                      title={selectedRules.length > 0 ? `${selectedRules.length} rules selected` : 'Select rules'}
                    >
                      <Scale className="w-4 h-4" />
                      {selectedRules.length > 0 ? (
                        <>
                          <span className="font-medium">{selectedRules.length}</span>
                          <span
                            role="button"
                            tabIndex={0}
                            onClick={(e) => {
                              e.stopPropagation()
                              onRulesChange([])
                            }}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') {
                                e.stopPropagation()
                                onRulesChange([])
                              }
                            }}
                            className="p-0.5 hover:bg-emerald-500/20 rounded cursor-pointer"
                          >
                            <X className="w-3 h-3" />
                          </span>
                        </>
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5" />
                      )}
                    </button>

                    {/* Rules dropdown */}
                    <AnimatePresence>
                      {showRulesDropdown && (
                        <motion.div
                          initial={{ opacity: 0, y: 5 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: 5 }}
                          className="absolute bottom-full left-0 mb-2 w-72 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden"
                        >
                          <div className="p-2 border-b border-border/50 flex items-center justify-between">
                            <span className="text-xs text-muted-foreground px-2">Select rules to apply</span>
                            {selectedRules.length > 0 && (
                              <button
                                type="button"
                                onClick={() => onRulesChange([])}
                                className="text-xs text-muted-foreground hover:text-foreground px-2"
                              >
                                Clear all
                              </button>
                            )}
                          </div>
                          <div className="max-h-64 overflow-y-auto py-1">
                            {rules.map((rule) => {
                              const isSelected = selectedRules.includes(rule.id)
                              return (
                                <button
                                  key={rule.id}
                                  type="button"
                                  onClick={() => {
                                    if (isSelected) {
                                      onRulesChange(selectedRules.filter(id => id !== rule.id))
                                    } else {
                                      onRulesChange([...selectedRules, rule.id])
                                    }
                                  }}
                                  className={cn(
                                    'w-full text-left px-3 py-2 text-sm transition-colors',
                                    'hover:bg-muted/50 flex items-start gap-2',
                                    isSelected && 'bg-emerald-500/10'
                                  )}
                                >
                                  <div className={cn(
                                    'w-4 h-4 mt-0.5 rounded border flex-shrink-0 flex items-center justify-center',
                                    isSelected
                                      ? 'bg-emerald-500 border-emerald-500 text-white'
                                      : 'border-border'
                                  )}>
                                    {isSelected && <Check className="w-3 h-3" />}
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <div className="font-medium truncate">{rule.name}</div>
                                    {rule.description && (
                                      <div className="text-xs text-muted-foreground truncate">{rule.description}</div>
                                    )}
                                    {rule.tags.length > 0 && (
                                      <div className="flex flex-wrap gap-1 mt-1">
                                        {rule.tags.slice(0, 3).map(tag => (
                                          <span key={tag} className="text-[10px] px-1.5 py-0.5 bg-muted rounded">
                                            {tag}
                                          </span>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                </button>
                              )
                            })}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                )}
              </div>

              <textarea
                ref={textareaRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onFocus={() => setIsFocused(true)}
                onBlur={() => setIsFocused(false)}
                placeholder={isLoading ? 'Type to queue next message...' : placeholder}
                rows={1}
                className={cn(
                  'flex-1 resize-none bg-transparent py-2 px-1',
                  'focus:outline-none',
                  'placeholder:text-muted-foreground/50',
                  'text-foreground',
                  'min-h-[40px] max-h-[200px]'
                )}
              />

              {/* Action Buttons */}
              <div className="flex items-center gap-2 flex-shrink-0">
                {/* Stop button */}
                <AnimatePresence>
                  {isLoading && (
                    <motion.button
                      initial={{ scale: 0, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0, opacity: 0 }}
                      onClick={onStop}
                      className={cn(
                        'p-2.5 rounded-xl bg-red-500 text-white',
                        'hover:bg-red-600 active:scale-95',
                        'transition-all duration-200',
                        'shadow-lg shadow-red-500/25'
                      )}
                      title="Stop generation (Esc)"
                    >
                      <Square className="w-4 h-4 fill-current" />
                    </motion.button>
                  )}
                </AnimatePresence>

                {/* Send/Queue button */}
                <motion.button
                  whileHover={{ scale: 1.02 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={handleSubmit}
                  disabled={!input.trim()}
                  className={cn(
                    'p-2.5 rounded-xl transition-all duration-200',
                    'disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none',
                    'flex items-center gap-2',
                    isLoading
                      ? 'bg-amber-500 text-white hover:bg-amber-600 shadow-lg shadow-amber-500/25'
                      : 'bg-gradient-to-r from-violet-600 to-purple-600 text-white hover:from-violet-500 hover:to-purple-500 shadow-lg shadow-violet-500/25'
                  )}
                  title={isLoading ? 'Add to queue (Enter)' : 'Send message (Enter)'}
                >
                  {isLoading ? (
                    <ListPlus className="w-5 h-5" />
                  ) : (
                    <Send className="w-5 h-5" />
                  )}
                </motion.button>
              </div>
            </div>

            {/* Character count */}
            <AnimatePresence>
              {showCharCount && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className={cn(
                    "absolute right-4 -top-6 text-xs font-medium",
                    isOverLimit ? "text-red-400" : "text-muted-foreground"
                  )}
                >
                  {charCount.toLocaleString()} {isOverLimit && "⚠️"}
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>

          {/* Footer hints */}
          <div className="flex items-center justify-center gap-4 mt-3">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
              <kbd className="kbd">⌘</kbd>
              <span>+</span>
              <kbd className="kbd">Enter</kbd>
              <span>send</span>
            </span>
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
              <kbd className="kbd">Shift</kbd>
              <span>+</span>
              <kbd className="kbd">Enter</kbd>
              <span>new line</span>
            </span>
            {isLoading && (
              <span className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
                <kbd className="kbd">Esc</kbd>
                <span>stop</span>
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
