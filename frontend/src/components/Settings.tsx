import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type Me } from '../api'
import { LogOut } from '../icons'
import { applyTheme, readTheme, type Theme } from '../theme'

export const GRANT = 2_000_000

const Preview = ({ tone }: { tone: 'lt' | 'dk' }) => (
  <span className={tone}>
    <span className="sb">
      <i />
      <i />
      <i style={{ width: '70%' }} />
    </span>
    <span className="mn" />
  </span>
)

const THEMES: { value: Theme; label: string; preview: React.ReactNode }[] = [
  { value: 'light', label: 'Light', preview: <Preview tone="lt" /> },
  { value: 'dark', label: 'Dark', preview: <Preview tone="dk" /> },
  {
    value: 'system',
    label: 'System',
    preview: (
      <>
        <Preview tone="lt" />
        <span className="dk" style={{ paddingLeft: 0 }}>
          <span className="mn" />
        </span>
      </>
    ),
  },
]

export function SettingsPage({ me }: { me: Me }) {
  const queryClient = useQueryClient()
  const [theme, setTheme] = useState<Theme>(readTheme)
  const logout = useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      queryClient.clear()
      window.location.assign('/login')
    },
  })
  const pct = Math.max(0, Math.min(100, (me.balance / GRANT) * 100))

  return (
    <div className="page">
      <div className="page-inner settings">
        <section className="sec" aria-labelledby="h-app">
          <h2 id="h-app">Appearance</h2>
          <div className="themes" role="radiogroup" aria-labelledby="h-app">
            {THEMES.map((t) => (
              <button
                key={t.value}
                role="radio"
                aria-checked={theme === t.value}
                onClick={() => {
                  applyTheme(t.value)
                  setTheme(t.value)
                }}
              >
                <span className="pv">{t.preview}</span>
                <span className="lbl">
                  <span className="radio" />
                  {t.label}
                </span>
              </button>
            ))}
          </div>
        </section>
        <section className="sec" aria-labelledby="h-acc">
          <div>
            <h2 id="h-acc">Account</h2>
            <p>Signed in with {me.user.role === 'admin' ? 'an admin' : 'a member'} account.</p>
          </div>
          <div className="card">
            <div>
              <span className="ava">{(me.user.name || me.user.email).slice(0, 2).toUpperCase()}</span>
              <div className="grow">
                {me.user.name}
                <span>{me.user.email}</span>
              </div>
            </div>
            <div>
              <div className="grow">
                Credits
                <span>
                  {me.balance.toLocaleString()} of {GRANT.toLocaleString()} left. Each reply is charged by tokens used.
                </span>
                <div className="meter" style={{ marginTop: 8 }}>
                  <i style={{ width: `${pct}%` }} />
                </div>
              </div>
            </div>
            <div>
              <div className="grow">
                Sign out<span>Ends this session on this device.</span>
              </div>
              <button className="icon danger" data-tip="Sign out" aria-label="Sign out" onClick={() => logout.mutate()}>
                <LogOut />
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

