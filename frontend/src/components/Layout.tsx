import { Outlet, NavLink } from 'react-router-dom'
import { MessageSquare, History, Settings, Sparkles, Bot } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { cn } from '@/lib/utils'
import { fetchConfig } from '@/lib/api'

const navItems = [
  { to: '/', icon: MessageSquare, label: 'Chat' },
  { to: '/autonomous', icon: Bot, label: 'Autonomous' },
  { to: '/sessions', icon: History, label: 'History' },
  { to: '/settings', icon: Settings, label: 'Settings' },
]

// Format model name for display
function formatModelName(model: string): string {
  if (!model) return 'Claude'
  // Remove version suffixes and clean up
  return model
    .replace(/-\d{8}$/, '') // Remove date suffix
    .replace('claude-', '')
    .replace(/-/g, ' ')
    .split(' ')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function Layout() {
  const { data: config } = useQuery({
    queryKey: ['config'],
    queryFn: fetchConfig,
  })

  const modelName = formatModelName(config?.default_model || 'claude-sonnet-4')

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-64 border-r border-border/50 flex flex-col bg-muted/30">
        {/* Logo */}
        <div className="p-5 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center shadow-lg shadow-violet-500/20">
              <Sparkles className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-semibold tracking-tight">MaratOS</h1>
              <p className="text-xs text-muted-foreground">
                Powered by {modelName}
              </p>
            </div>
          </div>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3">
          <div className="space-y-1">
            {navItems.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-200',
                    isActive
                      ? 'bg-primary text-primary-foreground shadow-md shadow-primary/20'
                      : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  )
                }
              >
                <item.icon className="w-5 h-5" />
                <span className="font-medium text-sm">{item.label}</span>
              </NavLink>
            ))}
          </div>
        </nav>

        {/* Status */}
        <div className="p-3 border-t border-border/50">
          <div className="flex items-center gap-3 px-3 py-3 rounded-xl bg-gradient-to-r from-violet-500/10 to-purple-500/10 border border-violet-500/20">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-violet-500 to-purple-600 flex items-center justify-center text-white text-sm font-bold shadow-md">
              MO
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium">MO</div>
              <div className="text-xs text-muted-foreground flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Online
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
