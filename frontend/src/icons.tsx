import type { ReactNode } from 'react'

function Icon({ children, size }: { children: ReactNode; size?: number }) {
  return (
    <svg className="i" viewBox="0 0 24 24" aria-hidden="true" style={size ? { width: size, height: size } : undefined}>
      {children}
    </svg>
  )
}

type P = { size?: number }

export const LogoMark = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 5h14M12 5v15" />
  </svg>
)
export const Fold = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="m6 9 6 6 6-6" />
  </svg>
)
export const SidebarIcon = ({ size }: P) => <Icon size={size}><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></Icon>
export const NewChat = ({ size }: P) => <Icon size={size}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z" /></Icon>
export const Chats = ({ size }: P) => <Icon size={size}><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /></Icon>
export const Settings = ({ size }: P) => <Icon size={size}><path d="M4 7h10M18 7h2M4 17h4M12 17h8" /><circle cx="16" cy="7" r="2" /><circle cx="10" cy="17" r="2" /></Icon>
export const Pin = ({ size }: P) => <Icon size={size}><path d="M12 17v5M9 3h6l-1 6 4 4H6l4-4z" /></Icon>
export const Rename = ({ size }: P) => <Icon size={size}><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z" /></Icon>
export const Archive = ({ size }: P) => <Icon size={size}><rect x="3" y="4" width="18" height="5" rx="1.5" /><path d="M5 9v9a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V9M10 13h4" /></Icon>
export const Trash = ({ size }: P) => <Icon size={size}><path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" /></Icon>
export const Send = () => <Icon><path d="M9 10 4 15l5 5" /><path d="M20 4v7a4 4 0 0 1-4 4H4" /></Icon>
export const Stop = () => (
  <Icon>
    <circle cx="12" cy="12" r="10" />
    <rect x="8.5" y="8.5" width="7" height="7" rx="1.5" fill="currentColor" stroke="none" />
  </Icon>
)
export const Copy = ({ size }: P) => <Icon size={size}><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></Icon>
export const Chevron = () => <Icon><path d="m9 6 6 6-6 6" /></Icon>
export const ArrowDown = () => <Icon size={13}><path d="M12 5v14M5 12l7 7 7-7" /></Icon>
export const LogOut = ({ size }: P) => <Icon size={size}><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></Icon>
