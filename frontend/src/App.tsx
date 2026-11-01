import { useQuery } from '@tanstack/react-query'
import { Navigate, Route, Routes } from 'react-router-dom'
import { api, ApiError } from './api'
import { ChatLayout } from './components/ChatLayout'
import { Login } from './components/Login'

export default function App() {
  const me = useQuery({ queryKey: ['me'], queryFn: api.me })

  if (me.isPending) return <div className="splash">Loading…</div>
  const signedIn = !me.error
  if (me.error && !(me.error instanceof ApiError && me.error.status === 401)) {
    return <div className="splash">Could not reach the server.</div>
  }

  return (
    <Routes>
      <Route path="/login" element={signedIn ? <Navigate to="/" replace /> : <Login />} />
      <Route
        path="/settings"
        element={signedIn ? <ChatLayout me={me.data!} view="settings" /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/activity"
        element={signedIn ? <ChatLayout me={me.data!} view="activity" /> : <Navigate to="/login" replace />}
      />
      <Route
        path="/c?/:conversationId?"
        element={signedIn ? <ChatLayout me={me.data!} /> : <Navigate to="/login" replace />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
