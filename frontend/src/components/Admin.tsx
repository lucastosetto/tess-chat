import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api'
import { when } from '../time'

const RANGES = [7, 30, 90]

export function AdminPage() {
  const [days, setDays] = useState(30)
  const usage = useQuery({ queryKey: ['admin-usage', days], queryFn: () => api.adminUsage(days) })
  const users = usage.data?.users ?? []

  return (
    <div className="page">
      <div className="page-inner">
        <section className="sec" aria-labelledby="h-usage">
          <div className="sec-hd">
            <div>
              <h2 id="h-usage">Usage by user</h2>
              <p>
                {usage.data
                  ? `${usage.data.total_spent.toLocaleString()} credits spent in the last ${days} days.`
                  : 'Credits, tokens and replies per user.'}
              </p>
            </div>
            <select value={days} onChange={(e) => setDays(Number(e.target.value))} aria-label="Range">
              {RANGES.map((d) => (
                <option key={d} value={d}>
                  Last {d} days
                </option>
              ))}
            </select>
          </div>
          {usage.error && <div className="note-err">Only admins can see this page.</div>}
          <div className="card tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>User</th>
                  <th className="num">Chats</th>
                  <th className="num">Replies</th>
                  <th className="num">Tokens in</th>
                  <th className="num">Tokens out</th>
                  <th className="num">Spent</th>
                  <th className="num">Balance</th>
                  <th>Last active</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.user.id}>
                    <td>
                      {u.user.name || u.user.email}
                      <span className="sub">{u.user.email}</span>
                    </td>
                    <td className="num">{u.conversations.toLocaleString()}</td>
                    <td className="num">{u.replies.toLocaleString()}</td>
                    <td className="num">{u.input_tokens.toLocaleString()}</td>
                    <td className="num">{u.output_tokens.toLocaleString()}</td>
                    <td className="num">{u.spent.toLocaleString()}</td>
                    <td className="num">{u.balance.toLocaleString()}</td>
                    <td>{u.last_active ? when(u.last_active) : '—'}</td>
                  </tr>
                ))}
                {usage.isPending && (
                  <tr>
                    <td colSpan={8}>Loading…</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
        <section className="sec" aria-labelledby="h-tools">
          <div>
            <h2 id="h-tools">Top tools</h2>
            <p>Most used tools in the period, with how many calls failed.</p>
          </div>
          <div className="card tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Tool</th>
                  <th className="num">Calls</th>
                  <th className="num">Failed</th>
                </tr>
              </thead>
              <tbody>
                {usage.data?.tools.map((t) => (
                  <tr key={t.name}>
                    <td>{t.name}</td>
                    <td className="num">{t.calls.toLocaleString()}</td>
                    <td className="num">{t.failures.toLocaleString()}</td>
                  </tr>
                ))}
                {usage.data && usage.data.tools.length === 0 && (
                  <tr>
                    <td colSpan={3}>No tool calls yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
        <section className="sec" aria-labelledby="h-fail">
          <div>
            <h2 id="h-fail">Failed replies</h2>
            <p>Replies that failed, grouped by error. Their credits were refunded.</p>
          </div>
          <div className="card tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Error</th>
                  <th className="num">Count</th>
                </tr>
              </thead>
              <tbody>
                {usage.data?.failures.map((f) => (
                  <tr key={f.error}>
                    <td>{f.error}</td>
                    <td className="num">{f.count.toLocaleString()}</td>
                  </tr>
                ))}
                {usage.data && usage.data.failures.length === 0 && (
                  <tr>
                    <td colSpan={2}>No failures.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  )
}
