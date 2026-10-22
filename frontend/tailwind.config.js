/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: { sans: ['Vazirmatn', 'system-ui', 'sans-serif'], mono: ['Vazirmatn', 'system-ui', 'sans-serif'] },
    },
  },
  plugins: [],
}
