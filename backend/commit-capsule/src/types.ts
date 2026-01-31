export enum ChangeType {
  Added = 'added',
  Modified = 'modified',
  Deleted = 'deleted',
  Renamed = 'renamed',
}

export interface FileChange {
  path: string;
  changeType: ChangeType;
  additions: number;
  deletions: number;
}

export interface ParsedDiff {
  files: FileChange[];
  totalAdditions: number;
  totalDeletions: number;
  raw: string;
}

export interface GenerationOptions {
  maxLength?: number;
  includeStats?: boolean;
  style?: 'conventional' | 'simple';
}

export interface Capsule {
  message: string;
  diff: ParsedDiff;
  timestamp: Date;
  options: GenerationOptions;
}
