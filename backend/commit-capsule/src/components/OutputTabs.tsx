import { useState } from 'react'

type TabType = 'commit' | 'pr' | 'changelog'

const tabs: { id: TabType; label: string }[] = [
  { id: 'commit', label: 'Commit Message' },
  { id: 'pr', label: 'PR Description' },
  { id: 'changelog', label: 'Changelog' },
]

export function OutputTabs() {
  const [activeTab, setActiveTab] = useState<TabType>('commit')

  return (
    <div className="w-full">
      <div className="flex border-b border-gray-700">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors ${
              activeTab === tab.id
                ? 'border-b-2 border-blue-500 text-blue-400'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div className="p-4 bg-gray-800 rounded-b min-h-[200px]">
        {activeTab === 'commit' && <div>Commit message output</div>}
        {activeTab === 'pr' && <div>PR description output</div>}
        {activeTab === 'changelog' && <div>Changelog output</div>}
      </div>
    </div>
  )
}
