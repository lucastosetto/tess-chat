import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { LogoMark } from '../icons'

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
        <span className="logo">
          <LogoMark />
        </span>
        <h1>Sign in to Tess</h1>
        <p className="meta">Chat with AI across many conversations.</p>
        {config.data?.dev_login ? (
          <form onSubmit={submit}>
            <label>
              Email
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              Name
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Optional" />
            </label>
            <button className="b primary" type="submit" disabled={login.isPending}>
              {login.isPending ? 'Signing in…' : 'Continue'}
            </button>
            {login.error && <p className="err">{login.error.message}</p>}
          </form>
        ) : (
          <p className="meta">{config.isPending ? 'Loading…' : 'No sign-in method is enabled.'}</p>
        )}
        {config.data?.dev_login && <p className="tag">dev login · no password</p>}
      </div>
    </div>
  )
}
