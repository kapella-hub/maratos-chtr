import type { Capsule } from '../types';

const STORAGE_KEY = 'commit-capsules';

interface StoredCapsule extends Omit<Capsule, 'timestamp'> {
  id: string;
  timestamp: string;
}

export function save(capsule: Capsule): string {
  const capsules = loadAll();
  const id = crypto.randomUUID();
  const stored: StoredCapsule = {
    ...capsule,
    id,
    timestamp: capsule.timestamp.toISOString(),
  };
  capsules.push(stored);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(capsules));
  return id;
}

export function load(id: string): Capsule | null {
  const stored = loadAll().find((c) => c.id === id);
  if (!stored) return null;
  return toCapule(stored);
}

export function list(): (Capsule & { id: string })[] {
  return loadAll().map((s) => ({ ...toCapule(s), id: s.id }));
}

export function remove(id: string): boolean {
  const capsules = loadAll();
  const idx = capsules.findIndex((c) => c.id === id);
  if (idx === -1) return false;
  capsules.splice(idx, 1);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(capsules));
  return true;
}

function loadAll(): StoredCapsule[] {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return [];
  try {
    return JSON.parse(raw) as StoredCapsule[];
  } catch {
    return [];
  }
}

function toCapule(stored: StoredCapsule): Capsule {
  return {
    message: stored.message,
    diff: stored.diff,
    options: stored.options,
    timestamp: new Date(stored.timestamp),
  };
}
