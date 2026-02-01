import { useState, useEffect, useCallback } from 'react'
import { useQuery } from '@tanstack/react-query'
import { motion, AnimatePresence } from 'framer-motion'
import { fetchSkills, matchSkills, type Skill, type SkillMatch } from '@/lib/api'
import { cn } from '@/lib/utils'
import {
  Sparkles,
  Check,
  ChevronDown,
  ChevronUp,
  Zap,
  X,
  Info,
} from 'lucide-react'

interface SkillSelectorProps {
  prompt: string
  selectedSkill: Skill | null
  onSelect: (skill: Skill | null) => void
  className?: string
}

export default function SkillSelector({
  prompt,
  selectedSkill,
  onSelect,
  className
}: SkillSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [matchedSkills, setMatchedSkills] = useState<SkillMatch[]>([])
  const [autoDetected, setAutoDetected] = useState<Skill | null>(null)

  // Fetch all skills
  const { data: skills = [] } = useQuery({
    queryKey: ['skills'],
    queryFn: fetchSkills,
  })

  // Match skills when prompt changes (debounced)
  const matchPrompt = useCallback(async (text: string) => {
    if (text.length < 5) {
      setMatchedSkills([])
      setAutoDetected(null)
      return
    }

    try {
      const result = await matchSkills(text)
      setMatchedSkills(result.matches)

      // Auto-detect best match but don't force selection
      if (result.best_match && !selectedSkill) {
        setAutoDetected(result.best_match)
      }
    } catch {
      // Ignore errors
    }
  }, [selectedSkill])

  // Debounce prompt matching
  useEffect(() => {
    const timer = setTimeout(() => {
      matchPrompt(prompt)
    }, 300)
    return () => clearTimeout(timer)
  }, [prompt, matchPrompt])

  // Clear auto-detected when skill is manually selected
  useEffect(() => {
    if (selectedSkill) {
      setAutoDetected(null) // eslint-disable-line
    }
  }, [selectedSkill])

  const displayedSkill = selectedSkill || autoDetected

  if (skills.length === 0) {
    return null
  }

  return (
    <div className={cn('relative', className)}>
      {/* Skill indicator button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={cn(
          'flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs',
          'transition-all duration-200',
          displayedSkill
            ? 'bg-violet-500/20 text-violet-400 border border-violet-500/30'
            : 'bg-muted/50 text-muted-foreground hover:bg-muted',
        )}
      >
        {displayedSkill ? (
          <>
            <Zap className="w-3 h-3" />
            <span>{displayedSkill.name}</span>
            {autoDetected && !selectedSkill && (
              <span className="text-[10px] opacity-70">(auto)</span>
            )}
          </>
        ) : (
          <>
            <Sparkles className="w-3 h-3" />
            <span>Skills</span>
          </>
        )}
        {isOpen ? (
          <ChevronUp className="w-3 h-3" />
        ) : (
          <ChevronDown className="w-3 h-3" />
        )}
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            className={cn(
              'absolute bottom-full left-0 mb-2 w-80',
              'bg-background border border-border rounded-xl shadow-xl',
              'overflow-hidden z-50'
            )}
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-border/50 bg-muted/30">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-violet-400" />
                  <span className="font-medium text-sm">Skills</span>
                </div>
                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1 hover:bg-muted rounded"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-1">
                Skills apply quality checklists and workflows to your request
              </p>
            </div>

            {/* Matched skills */}
            {matchedSkills.length > 0 && (
              <div className="p-2 border-b border-border/50">
                <div className="text-xs text-muted-foreground px-2 py-1">
                  Detected for your message:
                </div>
                {matchedSkills.slice(0, 3).map((skill) => (
                  <SkillItem
                    key={skill.id}
                    skill={skill}
                    isSelected={selectedSkill?.id === skill.id}
                    isAutoDetected={autoDetected?.id === skill.id && !selectedSkill}
                    matchedTriggers={skill.matched_triggers}
                    onClick={() => {
                      onSelect(selectedSkill?.id === skill.id ? null : skill)
                      setIsOpen(false)
                    }}
                  />
                ))}
              </div>
            )}

            {/* All skills */}
            <div className="p-2 max-h-60 overflow-y-auto">
              <div className="text-xs text-muted-foreground px-2 py-1">
                All skills:
              </div>
              {skills.map((skill) => (
                <SkillItem
                  key={skill.id}
                  skill={skill}
                  isSelected={selectedSkill?.id === skill.id}
                  onClick={() => {
                    onSelect(selectedSkill?.id === skill.id ? null : skill)
                    setIsOpen(false)
                  }}
                />
              ))}
            </div>

            {/* Clear selection */}
            {selectedSkill && (
              <div className="p-2 border-t border-border/50">
                <button
                  onClick={() => {
                    onSelect(null)
                    setIsOpen(false)
                  }}
                  className="w-full px-3 py-2 text-xs text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors"
                >
                  Clear skill selection (use auto-detect)
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

interface SkillItemProps {
  skill: Skill
  isSelected: boolean
  isAutoDetected?: boolean
  matchedTriggers?: string[]
  onClick: () => void
}

function SkillItem({
  skill,
  isSelected,
  isAutoDetected,
  matchedTriggers,
  onClick
}: SkillItemProps) {
  const [showInfo, setShowInfo] = useState(false)

  return (
    <div
      className={cn(
        'flex items-center gap-3 px-3 py-2 rounded-lg cursor-pointer',
        'transition-all duration-150',
        isSelected
          ? 'bg-violet-500/20 border border-violet-500/30'
          : 'hover:bg-muted/50',
        isAutoDetected && 'ring-1 ring-violet-500/30'
      )}
      onClick={onClick}
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">{skill.name}</span>
          {isSelected && <Check className="w-3 h-3 text-violet-400" />}
          {isAutoDetected && (
            <span className="text-[10px] px-1.5 py-0.5 bg-violet-500/20 text-violet-400 rounded">
              auto
            </span>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {skill.description}
        </p>
        {matchedTriggers && matchedTriggers.length > 0 && (
          <div className="flex gap-1 mt-1 flex-wrap">
            {matchedTriggers.map((trigger) => (
              <span
                key={trigger}
                className="text-[10px] px-1.5 py-0.5 bg-emerald-500/20 text-emerald-400 rounded"
              >
                {trigger}
              </span>
            ))}
          </div>
        )}
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation()
          setShowInfo(!showInfo)
        }}
        className="p-1 hover:bg-muted rounded opacity-50 hover:opacity-100"
      >
        <Info className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}
