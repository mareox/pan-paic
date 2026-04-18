/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['DM Sans', 'sans-serif'],
        mono: ['DM Mono', 'monospace'],
      },
      colors: {
        brand: {
          50:  '#f0f4ff',
          100: '#dce6ff',
          200: '#b9ceff',
          300: '#84aaff',
          400: '#4d7fff',
          500: '#1a56ff',
          600: '#0036e6',
          700: '#002ac0',
          800: '#00239c',
          900: '#001f80',
        },
      },
    },
  },
  plugins: [],
}
