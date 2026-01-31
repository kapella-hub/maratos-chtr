import { useState, useEffect } from 'react';
import type { Capsule } from '../types';
import * as storage from '../lib/storage';

interface HistoryPanelProps {
  onSelect: (capsule: Capsule) => void;
}

export function HistoryPanel({ onSelect }: HistoryPanelProps) {
  const [capsules, setCapsules] = useState<(Capsule & { id: string })[]>([]);

  useEffect(() => {
    setCapsules(storage.list());
  }, []);

  const handleDelete = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    storage.remove(id);
    setCapsules(storage.list());
  };

  if (capsules.length === 0) {
    return (
      <div className="p-4 text-gray-500 text-sm">No saved capsules</div>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-2">
      {capsules.map((capsule) => (
        <div
          key={capsule.id}
          onClick={() => onSelect(capsule)}
          className="p-3 bg-gray-800 rounded-lg border border-gray-700 hover:border-gray-600 cursor-pointer"
        >
          <div className="text-sm text-gray-200 truncate">{capsule.message}</div>
          <div className="flex justify-between items-center mt-2">
            <span className="text-xs text-gray-500">
              {capsule.timestamp.toLocaleDateString()}
            </span>
            <button
              onClick={(e) => handleDelete(capsule.id, e)}
              className="text-xs text-red-400 hover:text-red-300"
            >
              Delete
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
