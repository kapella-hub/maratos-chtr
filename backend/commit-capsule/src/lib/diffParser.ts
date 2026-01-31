import { ChangeType, FileChange, ParsedDiff } from '../types';

export type CommitType = 'feat' | 'fix' | 'refactor' | 'docs' | 'test' | 'chore';

const FILE_HEADER_REGEX = /^diff --git a\/(.+) b\/(.+)$/;
const NEW_FILE_REGEX = /^new file mode/;
const DELETED_FILE_REGEX = /^deleted file mode/;
const RENAME_FROM_REGEX = /^rename from (.+)$/;
const ADDITION_REGEX = /^\+(?!\+\+)/;
const DELETION_REGEX = /^-(?!--)/;

export function parseDiff(raw: string): ParsedDiff {
  const files: FileChange[] = [];
  const lines = raw.split('\n');
  
  let currentFile: FileChange | null = null;

  for (const line of lines) {
    const headerMatch = line.match(FILE_HEADER_REGEX);
    if (headerMatch) {
      if (currentFile) files.push(currentFile);
      currentFile = { path: headerMatch[2], changeType: ChangeType.Modified, additions: 0, deletions: 0 };
      continue;
    }

    if (!currentFile) continue;

    if (NEW_FILE_REGEX.test(line)) {
      currentFile.changeType = ChangeType.Added;
    } else if (DELETED_FILE_REGEX.test(line)) {
      currentFile.changeType = ChangeType.Deleted;
    } else if (RENAME_FROM_REGEX.test(line)) {
      currentFile.changeType = ChangeType.Renamed;
    } else if (ADDITION_REGEX.test(line)) {
      currentFile.additions++;
    } else if (DELETION_REGEX.test(line)) {
      currentFile.deletions++;
    }
  }

  if (currentFile) files.push(currentFile);

  return {
    files,
    totalAdditions: files.reduce((sum, f) => sum + f.additions, 0),
    totalDeletions: files.reduce((sum, f) => sum + f.deletions, 0),
    raw,
  };
}

export function detectCommitType(diff: ParsedDiff): CommitType {
  const paths = diff.files.map(f => f.path.toLowerCase());
  
  if (paths.some(p => /\.(md|txt|rst)$/.test(p) || p.includes('readme') || p.includes('doc'))) {
    return 'docs';
  }
  if (paths.every(p => /\.(test|spec)\.[jt]sx?$/.test(p) || p.includes('__tests__') || p.includes('test'))) {
    return 'test';
  }
  if (paths.some(p => /^(\..*rc|.*config.*|package\.json|tsconfig|\.gitignore|dockerfile|docker-compose)/i.test(p.split('/').pop() || ''))) {
    return 'chore';
  }
  
  const hasNewFiles = diff.files.some(f => f.changeType === ChangeType.Added);
  const hasOnlyModified = diff.files.every(f => f.changeType === ChangeType.Modified);
  const isSmallChange = diff.totalAdditions + diff.totalDeletions < 20;
  
  if (hasNewFiles && diff.totalAdditions > diff.totalDeletions * 2) {
    return 'feat';
  }
  if (hasOnlyModified && isSmallChange) {
    return 'fix';
  }
  if (hasOnlyModified && diff.totalAdditions > 0 && diff.totalDeletions > 0) {
    return 'refactor';
  }
  
  return 'feat';
}
