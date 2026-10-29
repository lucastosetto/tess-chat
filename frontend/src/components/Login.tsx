import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '../api'

export function Login() {
  const queryClient = useQueryClient()
  const config = useQuery({ queryKey: ['auth-config'], queryFn: api.authConfig })
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const login = useMutation({
    mutationFn: () => api.devLogin(email, name),
    onSuccess: (me) => queryClient.setQueryData(['me'], me),
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    login.mutate()
  }

  return (
    <div className="login">
      <div className="login-card">
        <h1>Tess Chat</h1>
        <p className="muted">Multi-conversation AI chat.</p>
        {config.data?.dev_login ? (
          <form onSubmit={submit}>
            <label>
              Email
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" />
            </label>
            <button type="submit" disabled={login.isPending}>
              {login.isPending ? 'Signing in…' : 'Continue (dev login)'}
            </button>
            {login.error && <p className="error">{login.error.message}</p>}
          </form>
        ) : (
          <p className="muted">{config.isPending ? 'Loading…' : 'No sign-in method is enabled.'}</p>
        )}
      </div>
    </div>
  )
}
