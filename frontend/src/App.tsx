import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { AppShell } from './components/shell'
import ChatPage from './pages/ChatPage'
import SessionsPage from './pages/SessionsPage'
import SettingsPage from './pages/SettingsPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<AppShell />}>
          <Route index element={<ChatPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
