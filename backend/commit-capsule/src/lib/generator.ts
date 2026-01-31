import { ParsedDiff, FileChange, ChangeType, GenerationOptions } from '../types';

export interface GeneratedOutput {
  commitMessage: string;
  prDescription: string;
  changelog: string;
}

function inferCommitType(files: FileChange[]): string {
  const paths = files.map(f => f.path.toLowerCase());
  
  if (paths.some(p => p.includes('test'))) return 'test';
  if (paths.some(p => p.includes('.md') || p.includes('doc'))) return 'docs';
  if (paths.some(p => p.includes('config') || p.includes('.json') || p.includes('.yml'))) return 'chore';
  if (paths.every(f => files.find(x => x.path === f)?.changeType === ChangeType.Added)) return 'feat';
  if (paths.some(p => p.includes('fix'))) return 'fix';
  
  return 'feat';
}

function inferScope(files: FileChange[]): string | null {
  if (files.length === 0) return null;
  
  const dirs = files.map(f => f.path.split('/').slice(0, -1).pop()).filter(Boolean);
  const uniqueDirs = [...new Set(dirs)];
  
  return uniqueDirs.length === 1 ? uniqueDirs[0]! : null;
}

function summarizeChanges(files: FileChange[]): string {
  const byType = {
    added: files.filter(f => f.changeType === ChangeType.Added),
    modified: files.filter(f => f.changeType === ChangeType.Modified),
    deleted: files.filter(f => f.changeType === ChangeType.Deleted),
    renamed: files.filter(f => f.changeType === ChangeType.Renamed),
  };

  const parts: string[] = [];
  if (byType.added.length) parts.push(`add ${byType.added.map(f => f.path.split('/').pop()).join(', ')}`);
  if (byType.modified.length) parts.push(`update ${byType.modified.map(f => f.path.split('/').pop()).join(', ')}`);
  if (byType.deleted.length) parts.push(`remove ${byType.deleted.map(f => f.path.split('/').pop()).join(', ')}`);
  if (byType.renamed.length) parts.push(`rename ${byType.renamed.map(f => f.path.split('/').pop()).join(', ')}`);

  return parts.join(', ') || 'update files';
}

export function generateCommitMessage(diff: ParsedDiff, options: GenerationOptions = {}): string {
  const { maxLength = 72, style = 'conventional' } = options;
  
  if (diff.files.length === 0) return 'chore: empty commit';

  const type = inferCommitType(diff.files);
  const scope = inferScope(diff.files);
  const summary = summarizeChanges(diff.files);

  if (style === 'simple') {
    return summary.slice(0, maxLength);
  }

  const prefix = scope ? `${type}(${scope}): ` : `${type}: `;
  const available = maxLength - prefix.length;
  
  return `${prefix}${summary.slice(0, available)}`;
}

export function generatePRDescription(diff: ParsedDiff, options: GenerationOptions = {}): string {
  const { includeStats = true } = options;
  
  const lines: string[] = ['## Summary', '', summarizeChanges(diff.files), ''];

  lines.push('## Changes', '');
  for (const file of diff.files) {
    const icon = { added: '➕', modified: '📝', deleted: '🗑️', renamed: '📛' }[file.changeType];
    lines.push(`- ${icon} \`${file.path}\``);
  }

  if (includeStats) {
    lines.push('', '## Stats', '', `+${diff.totalAdditions} / -${diff.totalDeletions}`);
  }

  lines.push('', '## Testing Notes', '', '- [ ] Verify changes work as expected', '- [ ] Run existing tests');

  return lines.join('\n');
}

export function generateChangelog(diff: ParsedDiff): string {
  const type = inferCommitType(diff.files);
  const summary = summarizeChanges(diff.files);
  const date = new Date().toISOString().split('T')[0];

  return `## [Unreleased] - ${date}\n\n### ${type.charAt(0).toUpperCase() + type.slice(1)}\n\n- ${summary}`;
}

export function generate(diff: ParsedDiff, options: GenerationOptions = {}): GeneratedOutput {
  return {
    commitMessage: generateCommitMessage(diff, options),
    prDescription: generatePRDescription(diff, options),
    changelog: generateChangelog(diff),
  };
}
