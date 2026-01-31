interface DiffInputProps {
  diff: string;
  context: string;
  onDiffChange: (value: string) => void;
  onContextChange: (value: string) => void;
}

export function DiffInput({ diff, context, onDiffChange, onContextChange }: DiffInputProps) {
  return (
    <div className="space-y-4">
      <div>
        <label className="block text-sm text-gray-400 mb-1">Diff</label>
        <textarea
          value={diff}
          onChange={(e) => onDiffChange(e.target.value)}
          placeholder="Paste your git diff here..."
          className="w-full h-64 bg-gray-800 text-gray-100 border border-gray-700 rounded-lg p-3 font-mono text-sm resize-none focus:outline-none focus:border-blue-500"
        />
      </div>
      <div>
        <label className="block text-sm text-gray-400 mb-1">Context Note</label>
        <input
          type="text"
          value={context}
          onChange={(e) => onContextChange(e.target.value)}
          placeholder="Additional context for the commit..."
          className="w-full bg-gray-800 text-gray-100 border border-gray-700 rounded-lg p-3 text-sm focus:outline-none focus:border-blue-500"
        />
      </div>
    </div>
  );
}
