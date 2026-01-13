import { BrowserRouter, Routes, Route, NavLink as RouterNavLink, Navigate } from 'react-router-dom'
import { BarChart3, Activity, Briefcase, Settings } from 'lucide-react'
import BacktestPage from './pages/BacktestPage'
import LiveTradingPage from './pages/LiveTradingPage'
import PositionsPage from './pages/PositionsPage'
import SettingsPage from './pages/SettingsPage'
import { cn } from './lib/utils'

function App() {
  return (
    <BrowserRouter>
      <div className="flex min-h-screen bg-background">
        {/* Sidebar */}
        <aside className="w-64 border-r bg-card">
          <div className="p-6">
            <h1 className="text-2xl font-bold">Good Signal</h1>
          </div>
          <nav className="space-y-1 px-3">
            <NavLink to="/backtest" icon={<BarChart3 className="h-5 w-5" />}>
              Backtest
            </NavLink>
            <NavLink to="/live" icon={<Activity className="h-5 w-5" />}>
              Live Trading
            </NavLink>
            <NavLink to="/positions" icon={<Briefcase className="h-5 w-5" />}>
              Positions
            </NavLink>
            <NavLink to="/settings" icon={<Settings className="h-5 w-5" />}>
              Settings
            </NavLink>
          </nav>
        </aside>

        {/* Main Content */}
        <main className="flex-1 overflow-auto">
          <Routes>
            <Route path="/" element={<Navigate to="/backtest" replace />} />
            <Route path="/backtest" element={<BacktestPage />} />
            <Route path="/live" element={<LiveTradingPage />} />
            <Route path="/positions" element={<PositionsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

interface NavLinkProps {
  to: string
  icon: React.ReactNode
  children: React.ReactNode
}

function NavLink({ to, icon, children }: NavLinkProps) {
  return (
    <RouterNavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          isActive
            ? "bg-primary text-primary-foreground"
            : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        )
      }
    >
      {icon}
      {children}
    </RouterNavLink>
  )
}

export default App
