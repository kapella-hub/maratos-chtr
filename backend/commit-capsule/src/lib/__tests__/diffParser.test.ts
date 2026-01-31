import { describe, it, expect } from 'vitest';
import { parseDiff, detectCommitType } from '../diffParser';
import { ChangeType } from '../../types';

describe('parseDiff', () => {
  it('parses single modified file', () => {
    const diff = `diff --git a/src/app.ts b/src/app.ts
--- a/src/app.ts
+++ b/src/app.ts
@@ -1,3 +1,4 @@
+import { foo } from 'bar';
 const x = 1;
-const y = 2;
+const y = 3;`;

    const result = parseDiff(diff);
    expect(result.files).toHaveLength(1);
    expect(result.files[0].path).toBe('src/app.ts');
    expect(result.files[0].changeType).toBe(ChangeType.Modified);
    expect(result.files[0].additions).toBe(2);
    expect(result.files[0].deletions).toBe(1);
    expect(result.totalAdditions).toBe(2);
    expect(result.totalDeletions).toBe(1);
  });

  it('parses new file', () => {
    const diff = `diff --git a/new.ts b/new.ts
new file mode 100644
--- /dev/null
+++ b/new.ts
@@ -0,0 +1,2 @@
+const a = 1;
+const b = 2;`;

    const result = parseDiff(diff);
    expect(result.files[0].changeType).toBe(ChangeType.Added);
    expect(result.files[0].additions).toBe(2);
  });

  it('parses deleted file', () => {
    const diff = `diff --git a/old.ts b/old.ts
deleted file mode 100644
--- a/old.ts
+++ /dev/null
@@ -1,2 +0,0 @@
-const a = 1;
-const b = 2;`;

    const result = parseDiff(diff);
    expect(result.files[0].changeType).toBe(ChangeType.Deleted);
    expect(result.files[0].deletions).toBe(2);
  });

  it('parses renamed file', () => {
    const diff = `diff --git a/old.ts b/new.ts
rename from old.ts
rename to new.ts`;

    const result = parseDiff(diff);
    expect(result.files[0].changeType).toBe(ChangeType.Renamed);
    expect(result.files[0].path).toBe('new.ts');
  });

  it('parses multiple files', () => {
    const diff = `diff --git a/a.ts b/a.ts
--- a/a.ts
+++ b/a.ts
+line1
diff --git a/b.ts b/b.ts
new file mode 100644
+line2
+line3`;

    const result = parseDiff(diff);
    expect(result.files).toHaveLength(2);
    expect(result.totalAdditions).toBe(3);
  });

  it('handles empty diff', () => {
    const result = parseDiff('');
    expect(result.files).toHaveLength(0);
    expect(result.totalAdditions).toBe(0);
    expect(result.totalDeletions).toBe(0);
  });

  it('ignores diff header markers (--- and +++)', () => {
    const diff = `diff --git a/x.ts b/x.ts
--- a/x.ts
+++ b/x.ts
+real addition`;

    const result = parseDiff(diff);
    expect(result.files[0].additions).toBe(1);
    expect(result.files[0].deletions).toBe(0);
  });
});

describe('detectCommitType', () => {
  const makeDiff = (files: Array<{ path: string; changeType: ChangeType; additions?: number; deletions?: number }>) => ({
    files: files.map(f => ({ ...f, additions: f.additions ?? 0, deletions: f.deletions ?? 0 })),
    totalAdditions: files.reduce((s, f) => s + (f.additions ?? 0), 0),
    totalDeletions: files.reduce((s, f) => s + (f.deletions ?? 0), 0),
    raw: '',
  });

  it('detects docs for markdown files', () => {
    expect(detectCommitType(makeDiff([{ path: 'README.md', changeType: ChangeType.Modified }]))).toBe('docs');
  });

  it('detects test for test files only', () => {
    expect(detectCommitType(makeDiff([
      { path: 'src/__tests__/foo.test.ts', changeType: ChangeType.Modified },
    ]))).toBe('test');
  });

  it('detects chore for config files', () => {
    expect(detectCommitType(makeDiff([{ path: 'package.json', changeType: ChangeType.Modified }]))).toBe('chore');
    expect(detectCommitType(makeDiff([{ path: '.gitignore', changeType: ChangeType.Modified }]))).toBe('chore');
  });

  it('detects feat for new files with many additions', () => {
    expect(detectCommitType(makeDiff([
      { path: 'src/new.ts', changeType: ChangeType.Added, additions: 50, deletions: 0 },
    ]))).toBe('feat');
  });

  it('detects fix for small modifications', () => {
    expect(detectCommitType(makeDiff([
      { path: 'src/app.ts', changeType: ChangeType.Modified, additions: 5, deletions: 3 },
    ]))).toBe('fix');
  });

  it('detects refactor for balanced changes', () => {
    expect(detectCommitType(makeDiff([
      { path: 'src/app.ts', changeType: ChangeType.Modified, additions: 30, deletions: 25 },
    ]))).toBe('refactor');
  });
});
