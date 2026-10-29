import { useMutation, useQuery } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { Google, LogoMark } from '../icons'

const ERRORS: Record<string, string> = {
  google: 'Google sign-in failed. Try again.',
  link: 'That magic link is invalid or expired. Ask for a new one.',
}

export function Login() {
  const config = useQuery({ queryKey: ['auth-config'], queryFn: api.authConfig })
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const send = useMutation({ mutationFn: () => api.emailLink(email) })
  const error = ERRORS[params.get('error') ?? '']

  const submit = (event: FormEvent) => {
    event.preventDefault()
    send.mutate()
  }

  return (
    <div className="login">
      <div className="login-card">
        <span className="logo">
          <LogoMark />
        </span>
        <h1>Sign in to Tess</h1>
        <p className="meta">Chat with AI across many conversations.</p>
        {config.data?.google_login && (
          <a className="b google" href="/api/auth/google">
            <Google />
            Continue with Google
          </a>
        )}
        {config.data?.google_login && config.data.email_login && <div className="or">or</div>}
        {config.data?.email_login &&
          (send.isSuccess ? (
            <p className="meta sent">
              Check <b>{email}</b> for a magic link. It expires in 15 minutes.{' '}
              <button className="link" onClick={() => send.reset()}>
                Use another email
              </button>
            </p>
          ) : (
            <form onSubmit={submit}>
              <label>
                Email
                <input
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                />
              </label>
              <button className="b primary" type="submit" disabled={send.isPending}>
                {send.isPending ? 'Sending…' : 'Send me a magic link'}
              </button>
              {send.error && <p className="err">{send.error.message}</p>}
            </form>
          ))}
        {error && <p className="err">{error}</p>}
        {config.isPending && <p className="meta">Loading…</p>}
        {config.data && !config.data.google_login && !config.data.email_login && (
          <p className="meta">No sign-in method is enabled.</p>
        )}
      </div>
    </div>
  )
}
