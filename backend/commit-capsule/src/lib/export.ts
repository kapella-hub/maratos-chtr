import type { Capsule } from '../types';

export async function copyToClipboard(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

export function downloadAsMarkdown(capsule: Capsule, filename = 'commit-capsule.md'): void {
  const content = formatAsMarkdown(capsule);
  download(content, filename, 'text/markdown');
}

export function downloadAsJson(capsule: Capsule, filename = 'commit-capsule.json'): void {
  const content = JSON.stringify(capsule, null, 2);
  download(content, filename, 'application/json');
}

function formatAsMarkdown(capsule: Capsule): string {
  const { message, diff, timestamp } = capsule;
  const lines = [
    '# Commit Capsule',
    '',
    `**Date:** ${timestamp.toISOString()}`,
    '',
    '## Message',
    '',
    message,
    '',
    '## Stats',
    '',
    `- Files changed: ${diff.files.length}`,
    `- Additions: ${diff.totalAdditions}`,
    `- Deletions: ${diff.totalDeletions}`,
  ];
  return lines.join('\n');
}

function download(content: string, filename: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}
