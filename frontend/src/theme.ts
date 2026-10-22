const KEY = 'copilot.theme'
export type Theme = 'light' | 'dark'

/** Light by default; dark only when the user picks it (stored per browser). */
export function savedTheme(): Theme {
  try {
    return localStorage.getItem(KEY) === 'dark' ? 'dark' : 'light'
  } catch {
    return 'light'
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
