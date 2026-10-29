import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useLayoutEffect, useRef, useState, type DragEvent, type MouseEvent as ReactMouseEvent } from 'react'
import { api, type Conversation } from '../api'
import { Archive, Fold, Pin, Rename, Trash } from '../icons'
import { store } from '../store'
import { when } from '../time'

type Group = 'pinned' | 'recent' | 'archived'
type Action = 'pin' | 'rename' | 'archive' | 'delete'
type Changes = Partial<Pick<Conversation, 'title' | 'pinned' | 'archived'>>

const RECENT = 12
const KEYS: Record<string, Action> = { F2: 'rename', e: 'archive', E: 'archive', p: 'pin', P: 'pin', Backspace: 'delete', Delete: 'delete' }

type Props = {
  list: Conversation[]
  loaded: boolean
  currentId: string | null
  onOpen: (id: string) => void
  onDeleted: (id: string) => void
}

export function Sessions({ list, loaded, currentId, onOpen, onDeleted }: Props) {
  const queryClient = useQueryClient()
  const [folded, setFolded] = useState<Record<string, boolean>>(() => store.get('chat-fold', {}))
  const [showAll, setShowAll] = useState(false)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [ctx, setCtx] = useState<{ id: string; x: number; y: number } | null>(null)
  const [dragging, setDragging] = useState<string | null>(null)
  const [drop, setDrop] = useState<Group | null>(null)
  const [deleting, setDeleting] = useState<Conversation | null>(null)
  const menu = useRef<HTMLDivElement>(null)
  const dialog = useRef<HTMLDialogElement>(null)
  const press = useRef<number | null>(null)

  const update = useMutation({
    mutationFn: ({ id, changes }: { id: string; changes: Changes }) => api.update(id, changes),
    onMutate: ({ id, changes }) => {
      queryClient.setQueryData<Conversation[]>(['conversations'], (all) =>
        all?.map((c) =>
          c.id === id ? { ...c, ...changes, pinned: changes.archived ? false : (changes.pinned ?? c.pinned) } : c,
        ),
      )
    },
    onSettled: (_, __, { id }) => {
      queryClient.invalidateQueries({ queryKey: ['conversations'] })
      queryClient.invalidateQueries({ queryKey: ['conversation', id] })
    },
  })
  const remove = useMutation({
    mutationFn: api.remove,
    onSuccess: (_, id) => {
      queryClient.setQueryData<Conversation[]>(['conversations'], (all) => all?.filter((c) => c.id !== id))
      onDeleted(id)
    },
  })

  const sections: Record<Group, Conversation[]> = {
    pinned: list.filter((c) => c.pinned && !c.archived),
    recent: list.filter((c) => !c.pinned && !c.archived),
    archived: list.filter((c) => c.archived),
  }
  const recentShown = showAll ? sections.recent : sections.recent.slice(0, RECENT)

  const act = (action: Action, c: Conversation) => {
    setCtx(null)
    if (action === 'rename') setRenaming(c.id)
    else if (action === 'pin') update.mutate({ id: c.id, changes: { pinned: !c.pinned, archived: false } })
    else if (action === 'archive') update.mutate({ id: c.id, changes: { archived: !c.archived } })
    else {
      setDeleting(c)
      dialog.current?.showModal()
    }
  }

  const moveTo = (c: Conversation, group: Group) => {
    const target = { pinned: group === 'pinned', archived: group === 'archived' }
    if (target.pinned !== c.pinned || target.archived !== c.archived) update.mutate({ id: c.id, changes: target })
  }

  const toggleFold = (group: Group) => {
    const next = { ...folded, [group]: !folded[group] }
    setFolded(next)
    store.set('chat-fold', next)
  }

  const openCtx = (event: { preventDefault?: () => void }, id: string, x: number, y: number) => {
    event.preventDefault?.()
    setCtx({ id, x, y })
  }

  useLayoutEffect(() => {
    const m = menu.current
    if (!ctx || !m) return
    m.style.left = `${Math.max(8, Math.min(ctx.x, innerWidth - m.offsetWidth - 8))}px`
    m.style.top = `${Math.max(8, Math.min(ctx.y, innerHeight - m.offsetHeight - 8))}px`
    m.querySelector('button')?.focus()
  }, [ctx])

  useEffect(() => {
    if (!ctx) return
    const close = (event: Event) => {
      if (!menu.current?.contains(event.target as Node)) setCtx(null)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('scroll', close, true)
    window.addEventListener('blur', close)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('scroll', close, true)
      window.removeEventListener('blur', close)
    }
  }, [ctx])

  const target = ctx ? list.find((c) => c.id === ctx.id) : undefined

  const onMenuKey = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const action = KEYS[event.key]
    if (action && target) {
      event.preventDefault()
      act(action, target)
    }
    if (event.key === 'Escape') setCtx(null)
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const buttons = [...(menu.current?.querySelectorAll('button') ?? [])]
      const i = buttons.indexOf(document.activeElement as HTMLButtonElement)
      buttons[(i + (event.key === 'ArrowDown' ? 1 : buttons.length - 1)) % buttons.length]?.focus()
    }
  }

  const dragOver = (group: Group) => (event: DragEvent) => {
    if (!dragging || group === 'archived') return
    event.preventDefault()
    setDrop(group)
  }
  const dropOn = (group: Group) => (event: DragEvent) => {
    event.preventDefault()
    const c = list.find((x) => x.id === dragging)
    if (c && group !== 'archived') moveTo(c, group)
    setDragging(null)
    setDrop(null)
  }

  const commitRename = (c: Conversation, value: string) => {
    const title = value.trim().slice(0, 200)
    setRenaming(null)
    if (title && title !== c.title) update.mutate({ id: c.id, changes: { title } })
  }

  const row = (c: Conversation, group: Group) => {
    if (renaming === c.id) {
      return (
        <div key={c.id} className="it on">
          <input
            autoFocus
            autoComplete="off"
            defaultValue={c.title}
            aria-label="Chat name"
            onFocus={(e) => e.currentTarget.select()}
            onBlur={(e) => commitRename(c, e.currentTarget.value)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') setRenaming(null)
              if (e.key === 'Enter') e.currentTarget.blur()
            }}
          />
        </div>
      )
    }
    const button = (action: Action, label: string, Glyph: typeof Pin, cls = '') => (
      <button
        className={`icon ${cls}`}
        data-tip={label}
        aria-label={label}
        onClick={(e) => {
          e.stopPropagation()
          act(action, c)
        }}
      >
        <Glyph />
      </button>
    )
    return (
      <div
        key={c.id}
        className={`it row ${c.id === currentId ? 'on' : ''} ${ctx?.id === c.id ? 'ctx' : ''} ${dragging === c.id ? 'dragging' : ''}`}
        draggable={group !== 'archived'}
        onDragStart={(e) => {
          e.dataTransfer.effectAllowed = 'move'
          e.dataTransfer.setData('text/plain', c.title)
          setDragging(c.id)
        }}
        onDragEnd={() => {
          setDragging(null)
          setDrop(null)
        }}
        onContextMenu={(e: ReactMouseEvent) => openCtx(e, c.id, e.clientX, e.clientY)}
        onTouchStart={(e) => {
          const t = e.touches[0]
          press.current = window.setTimeout(() => {
            press.current = -1
            openCtx({}, c.id, t.clientX, t.clientY)
          }, 500)
        }}
        onTouchMove={() => press.current !== null && clearTimeout(press.current)}
        onTouchEnd={(e) => {
          if (press.current === -1) e.preventDefault()
          else if (press.current !== null) clearTimeout(press.current)
          press.current = null
        }}
      >
        <button className="main" onClick={() => !ctx && onOpen(c.id)} onDoubleClick={() => setRenaming(c.id)}>
          <span className="t">{c.title}</span>
          <span className="w">{when(c.updated_at)}</span>
        </button>
        <span className="acts">
          {button('pin', c.pinned ? 'Unpin' : 'Pin', Pin)}
          {button('rename', 'Rename', Rename)}
          {button('archive', c.archived ? 'Unarchive' : 'Archive', Archive)}
          {button('delete', 'Delete', Trash, 'danger')}
        </span>
      </div>
    )
  }

  const section = (group: Group, name: string, items: Conversation[], extra?: React.ReactNode) => (
    <div onDragOver={dragOver(group)} onDragLeave={() => setDrop(null)} onDrop={dropOn(group)} className={drop === group ? 'drop-zone' : ''}>
      <div className="group">
        <button className="fold" aria-expanded={!folded[group]} onClick={() => toggleFold(group)}>
          <Fold />
          {name}
        </button>
        <span className="n">{sections[group].length}</span>
      </div>
      {!folded[group] && (
        <div className="list-s">
          {items.map((c) => row(c, group))}
          {extra}
        </div>
      )}
    </div>
  )

  return (
    <div className="sessions">
      {list.length > 0 ? (
        <>
          {section(
            'pinned',
            'Pinned',
            sections.pinned,
            sections.pinned.length === 0 && (
              <div className={`dropend none ${drop === 'pinned' ? 'drop' : ''}`}>Drag a chat here to pin it</div>
            ),
          )}
          {section(
            'recent',
            'Recent',
            recentShown,
            sections.recent.length > RECENT && (
              <button className="it more" onClick={() => setShowAll((v) => !v)}>
                {showAll ? 'Show less' : 'Show all'}
              </button>
            ),
          )}
          {sections.archived.length > 0 && section('archived', 'Archived', sections.archived)}
        </>
      ) : (
        loaded && (
          <>
            <div className="group">Chats</div>
            <p className="meta" style={{ padding: '0 9px', margin: 0 }}>
              No chats yet.
            </p>
          </>
        )
      )}

      {ctx && target && (
        <div className="menu ctxmenu" role="menu" ref={menu} onKeyDown={onMenuKey}>
          <button role="menuitem" onClick={() => act('pin', target)}>
            <Pin size={14} />
            <span>{target.pinned ? 'Unpin' : 'Pin'}</span>
            <kbd>P</kbd>
          </button>
          <button role="menuitem" onClick={() => act('rename', target)}>
            <Rename size={14} />
            Rename<kbd>F2</kbd>
          </button>
          <button role="menuitem" onClick={() => act('archive', target)}>
            <Archive size={14} />
            <span>{target.archived ? 'Unarchive' : 'Archive'}</span>
            <kbd>E</kbd>
          </button>
          <hr />
          <button role="menuitem" className="danger" onClick={() => act('delete', target)}>
            <Trash size={14} />
            Delete…<kbd>⌫</kbd>
          </button>
        </div>
      )}

      <dialog ref={dialog} onClose={() => setDeleting(null)}>
        <h3>Delete chat?</h3>
        <p className="meta" style={{ margin: '-6px 0 0' }}>
          “{deleting?.title}” and its messages are removed. This can't be undone.
        </p>
        <div className="actions">
          <button className="b ghost" onClick={() => dialog.current?.close()}>
            Cancel
          </button>
          <button
            className="b danger-b"
            onClick={() => {
              if (deleting) remove.mutate(deleting.id)
              dialog.current?.close()
            }}
          >
            Delete
          </button>
        </div>
      </dialog>
    </div>
  )
}
