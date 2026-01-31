import type { ParsedDiff } from '../types'

interface QualityBadgesProps {
  diff: ParsedDiff;
}

function inferChangeType(diff: ParsedDiff): string {
  const paths = diff.files.map(f => f.path.toLowerCase());
  if (paths.some(p => p.includes('test'))) return 'test';
  if (paths.some(p => p.includes('.md') || p.includes('doc'))) return 'docs';
  if (paths.some(p => p.includes('config') || p.includes('.json') || p.includes('.yml'))) return 'chore';
  if (paths.some(p => p.includes('fix'))) return 'fix';
  return 'feat';
}

function getWarnings(diff: ParsedDiff): string[] {
  const warnings: string[] = [];
  const total = diff.totalAdditions + diff.totalDeletions;
  if (total > 500) warnings.push('Large diff');
  if (diff.files.length > 10) warnings.push('Many files');
  const types = new Set(diff.files.map(f => f.changeType));
  if (types.size > 2) warnings.push('Mixed changes');
  return warnings;
}

export function QualityBadges({ diff }: QualityBadgesProps) {
  if (diff.files.length === 0) return null;

  const changeType = inferChangeType(diff);
  const warnings = getWarnings(diff);

  return (
    <div className="flex flex-wrap gap-2">
      <span className="px-2 py-1 text-xs font-medium rounded bg-blue-600 text-white">
        {changeType}
      </span>
      {warnings.map(w => (
        <span key={w} className="px-2 py-1 text-xs font-medium rounded bg-yellow-600 text-white">
          ⚠ {w}
        </span>
      ))}
    </div>
  );
}
