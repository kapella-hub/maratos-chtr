import type { GenerationOptions } from '../types'

interface OptionsBarProps {
  options: GenerationOptions;
  onChange: (options: GenerationOptions) => void;
}

export function OptionsBar({ options, onChange }: OptionsBarProps) {
  const update = (partial: Partial<GenerationOptions>) => {
    onChange({ ...options, ...partial })
  }

  return (
    <div className="flex flex-wrap gap-4 p-3 bg-gray-800 rounded-lg border border-gray-700">
      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
        <input
          type="checkbox"
          checked={options.style === 'conventional'}
          onChange={(e) => update({ style: e.target.checked ? 'conventional' : 'simple' })}
          className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
        />
        Verbose
      </label>
      <label className="flex items-center gap-2 text-sm text-gray-300 cursor-pointer">
        <input
          type="checkbox"
          checked={options.includeStats ?? false}
          onChange={(e) => update({ includeStats: e.target.checked })}
          className="w-4 h-4 rounded bg-gray-700 border-gray-600 text-blue-500 focus:ring-blue-500"
        />
        Include Stats
      </label>
    </div>
  )
}
