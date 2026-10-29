import type { ReactNode } from 'react'

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg className="i" viewBox="0 0 24 24" aria-hidden="true">
      {children}
    </svg>
  )
}

export const LogoMark = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 5h14M12 5v15" />
  </svg>
)
export const Plus = () => <Icon><path d="M12 5v14M5 12h14" /></Icon>
export const Pencil = () => <Icon><path d="M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></Icon>
export const Trash = () => <Icon><path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6" /></Icon>
export const Send = () => <Icon><path d="M12 19V5M5 12l7-7 7 7" /></Icon>
export const Stop = () => <Icon><rect x="7" y="7" width="10" height="10" rx="1.5" /></Icon>
export const Copy = () => <Icon><rect x="9" y="9" width="12" height="12" rx="2" /><path d="M5 15V5a2 2 0 0 1 2-2h10" /></Icon>
export const Check = () => <Icon><path d="m5 12 5 5L20 7" /></Icon>
export const Chevron = () => <Icon><path d="m9 6 6 6-6 6" /></Icon>
export const ChevronUp = () => <Icon><path d="m6 15 6-6 6 6" /></Icon>
export const Menu = () => <Icon><path d="M4 7h16M4 12h16M4 17h16" /></Icon>
export const Sun = () => <Icon><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></Icon>
export const LogOut = () => <Icon><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" /></Icon>
