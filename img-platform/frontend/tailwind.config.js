/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: '#05070a',
        surface: {
          DEFAULT: '#0d1117',
          2: '#111827',
          3: '#151821',
        },
        border: '#1f2937',
        muted: '#9ca3af',
        subtle: '#6b7280',
        cyan: '#00d2ff',
        green: '#22c55e',
        purple: '#7c3aed',
        amber: '#f59e0b',
      },
    },
  },
  plugins: [],
}
