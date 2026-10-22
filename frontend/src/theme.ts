const KEY = 'copilot.theme'
export type Theme = 'light' | 'dark'

/** Dark by default (the console look); the choice is stored per browser. */
export function savedTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark')
  document.documentElement.style.colorScheme = theme
  try {
    localStorage.setItem(KEY, theme)
  } catch {
    /* ignore */
  }
}

export function applySavedTheme() {
  applyTheme(savedTheme())
}
