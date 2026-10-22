/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: { sans: ['Vazirmatn', 'system-ui', 'sans-serif'], mono: ['Vazirmatn', 'system-ui', 'sans-serif'] },
      fontSize: { base: ['14px', '1.7'], sm: ['13px', '1.6'], xs: ['11.5px', '1.5'] },
      colors: {
        bg: 'rgb(var(--c-bg) / <alpha-value>)',
        surface: 'rgb(var(--c-surface) / <alpha-value>)',
        raised: 'rgb(var(--c-raised) / <alpha-value>)',
        line: 'rgb(var(--c-line) / <alpha-value>)',
        ink: 'rgb(var(--c-ink) / <alpha-value>)',
        muted: 'rgb(var(--c-muted) / <alpha-value>)',
      },
      boxShadow: { card: '0 1px 2px rgb(15 23 42 / 0.06), 0 8px 24px -12px rgb(15 23 42 / 0.12)' },
      keyframes: {
        shimmer: { '0%': { backgroundPosition: '200% 0' }, '100%': { backgroundPosition: '-200% 0' } },
        rise: { '0%': { opacity: '0', transform: 'translateY(6px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
        flow: { '0%': { backgroundPosition: '0 0' }, '100%': { backgroundPosition: '0 -24px' } },
      },
      animation: { shimmer: 'shimmer 1.6s linear infinite', rise: 'rise .25s ease-out both', flow: 'flow 1s linear infinite' },
    },
  },
  plugins: [],
}
