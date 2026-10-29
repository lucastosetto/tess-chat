import { store } from './store'

export type Theme = 'system' | 'light' | 'dark'

export function readTheme(): Theme {
  const value = store.get<string>('theme', 'system')
  return value === 'light' || value === 'dark' ? value : 'system'
}

export function applyTheme(theme: Theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
  store.set('theme', theme)
}
