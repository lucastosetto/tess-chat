import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { api, type AuditEvent, type DayUsage } from '../api'
import { when } from '../time'

const RANGES = [7, 14, 30]

export function ActivityPage() {
  const [days, setDays] = useState(14)
  const usage = useQuery({ queryKey: ['usage', days], queryFn: () => api.usage(days) })
  const feed = useQuery({ queryKey: ['activity'], queryFn: api.activity })
  const data = usage.data
  const total = (key: keyof Omit<DayUsage, 'day'>) => data?.days.reduce((n, d) => n + d[key], 0) ?? 0
  const replies = total('replies')
  const credits = total('credits')
  const events = (feed.data ?? []).map(describe).filter((e): e is Described => e !== null)

  return (
    <div className="page">
      <div className="page-inner activity">
        <div className="range" role="radiogroup" aria-label="Time range">
          {RANGES.map((r) => (
            <button key={r} role="radio" aria-checked={days === r} className={days === r ? 'on' : ''} onClick={() => setDays(r)}>
              {r} days
            </button>
          ))}
        </div>
        <div className="tiles">
          <Tile label="Credits used" value={credits} hint={`last ${days} days`} />
          <Tile label="Replies" value={replies} hint={total('failed') ? `${total('failed')} failed, refunded` : 'all delivered'} />
          <Tile label="Tools used" value={total('tool_calls')} hint="web searches and page reads" />
          <Tile label="Credits left" value={data?.balance ?? 0} hint={replies ? `≈ ${Math.floor((data?.balance ?? 0) / Math.max(1, credits / replies)).toLocaleString()} more replies` : 'at your current pace'} />
        </div>
        <section className="panel-box">
          <h2>Credits per day</h2>
          {data && <DayChart days={data.days} />}
        </section>
        <section className="panel-box">
          <h2>By model</h2>
          {data && data.models.length === 0 && <p className="meta">No replies in this period.</p>}
          {data?.models.map((m) => (
            <div key={m.model} className="mbar">
              <span className="name">{m.model}</span>
              <span className="track">
                <i style={{ width: `${(m.credits / Math.max(1, data.models[0].credits)) * 100}%` }} />
              </span>
              <span className="val">
                {m.credits.toLocaleString()} cr · {m.replies} {m.replies === 1 ? 'reply' : 'replies'}
              </span>
            </div>
          ))}
        </section>
        <section className="panel-box">
          <h2>Recent activity</h2>
          {feed.isPending && <p className="meta">Loading…</p>}
          <ul className="feed">
            {events.map((e) => (
              <li key={e.id} title={e.trace ? `trace ${e.trace}` : undefined}>
                <span className={`dot ${e.tone}`} />
                <span className="what">
                  {e.text}
                  {e.detail && <span>{e.detail}</span>}
                </span>
                <span className="ago">{when(e.at)}</span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  )
}

function Tile({ label, value, hint }: { label: string; value: number; hint: string }) {
  return (
    <div className="tile">
      <span className="k">{label}</span>
      <b>{value.toLocaleString()}</b>
      <span className="h">{hint}</span>
    </div>
  )
}

function DayChart({ days }: { days: DayUsage[] }) {
  const [hover, setHover] = useState<number | null>(null)
  const W = 720
  const H = 180
  const pad = { l: 44, r: 8, t: 8, b: 22 }
  const max = Math.max(1, ...days.map((d) => d.credits))
  const step = (W - pad.l - pad.r) / days.length
  const bw = Math.max(2, Math.min(28, step - 4))
  const y = (v: number) => pad.t + (H - pad.t - pad.b) * (1 - v / max)
  const label = (d: string) => new Date(`${d}T00:00:00`).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const every = Math.ceil(days.length / 7)
  const h = hover === null ? null : days[hover]
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Credits used per day" onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={pad.l} x2={W - pad.r} y1={y(max * f)} y2={y(max * f)} className="grid" />
            <text x={pad.l - 6} y={y(max * f) + 3} className="axis" textAnchor="end">
              {Math.round(max * f).toLocaleString()}
            </text>
          </g>
        ))}
        {days.map((d, i) => {
          const x = pad.l + i * step + (step - bw) / 2
          const top = y(d.credits)
          const bh = H - pad.b - top
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)}>
              <rect x={pad.l + i * step} y={pad.t} width={step} height={H - pad.t - pad.b} fill="transparent" />
              {d.credits > 0 && (
                <path
                  className={`bar ${hover !== null && hover !== i ? 'dim' : ''}`}
                  d={`M${x},${H - pad.b} V${top + Math.min(4, bh)} q0,-${Math.min(4, bh)} ${Math.min(4, bw / 2)},-${Math.min(4, bh)} H${x + bw - Math.min(4, bw / 2)} q${Math.min(4, bw / 2)},0 ${Math.min(4, bw / 2)},${Math.min(4, bh)} V${H - pad.b} Z`}
                />
              )}
              {i % every === 0 && (
                <text x={x + bw / 2} y={H - 6} className="axis" textAnchor="middle">
                  {label(d.day)}
                </text>
              )}
            </g>
          )
        })}
      </svg>
      {h && hover !== null && (
        <div className="tip" style={{ left: `${((pad.l + hover * step + step / 2) / W) * 100}%` }}>
          <b>{label(h.day)}</b>
          <span>{h.credits.toLocaleString()} credits</span>
          <span>
            {h.replies} {h.replies === 1 ? 'reply' : 'replies'}
            {h.tool_calls > 0 && ` · ${h.tool_calls} tools`}
          </span>
          <span>{(h.input_tokens + h.output_tokens).toLocaleString()} tokens</span>
        </div>
      )}
    </div>
  )
}

type Described = { id: string; at: string; text: string; detail?: string; tone: 'ok' | 'bad' | 'muted'; trace: string | null }

function describe(e: AuditEvent): Described | null {
  const p = e.payload
  const n = (k: string) => Number(p[k] ?? 0).toLocaleString()
  const base = { id: e.id, at: e.at, trace: e.trace_id }
  const make = (text: string, tone: Described['tone'] = 'muted', detail?: string) => ({ ...base, text, tone, detail })
  switch (e.action) {
    case 'user.registered':
      return make('Account created', 'ok')
    case 'user.logged_in':
      return make('Signed in', 'muted', p.method === 'google' ? 'with Google' : 'with a magic link')
    case 'auth.login_link_sent':
      return make('Magic link sent', 'muted', String(p.email ?? ''))
    case 'credits.granted':
      return make(`Received ${n('amount')} credits`, 'ok')
    case 'credits.settled':
      return make(`Charged ${n('amount')} credits`)
    case 'credits.released':
      return make(`Refunded ${n('amount')} credits`, 'ok', 'a reply failed or used less than reserved')
    case 'credits.reserved':
      return null
    case 'conversation.created':
      return make('Started a new chat')
    case 'conversation.titled':
      return make(`Chat named “${String(p.title ?? '')}”`)
    case 'conversation.renamed':
      return make('Renamed a chat')
    case 'conversation.pinned':
      return make('Pinned a chat')
    case 'conversation.unpinned':
      return make('Unpinned a chat')
    case 'conversation.archived':
      return make('Archived a chat')
    case 'conversation.unarchived':
      return make('Restored a chat')
    case 'conversation.deleted':
      return make('Deleted a chat')
    case 'conversation.model_changed':
      return make('Changed model settings', 'muted', [p.model ?? 'Auto', p.effort && `${p.effort} effort`].filter(Boolean).join(' · '))
    case 'conversation.compacted':
      return make('Long chat summarized', 'ok', 'older messages condensed to save context and credits')
    case 'message.sent':
      return make('Sent a message', 'muted', Number(p.attachments) ? `with ${p.attachments} attachment${p.attachments === 1 ? '' : 's'}` : undefined)
    case 'message.completed': {
      const tools = Array.isArray(p.tools) ? p.tools.length : 0
      const tokens = Number(p.input_tokens ?? 0) + Number(p.output_tokens ?? 0)
      return make('Got a reply', 'ok', [p.model, `${tokens.toLocaleString()} tokens`, tools && `${tools} tool${tools === 1 ? '' : 's'}`].filter(Boolean).join(' · '))
    }
    case 'message.failed':
      return make('A reply failed', 'bad', p.error === 'llm_unavailable' ? 'models unavailable, credits refunded' : String(p.error ?? ''))
    case 'attachment.uploaded':
      return make(`Uploaded ${p.mime === 'application/pdf' ? 'a PDF' : 'an image'}`, 'muted', `${Math.max(1, Math.round(Number(p.size ?? 0) / 1024)).toLocaleString()} KB`)
    default:
      return make(e.action)
  }
}
