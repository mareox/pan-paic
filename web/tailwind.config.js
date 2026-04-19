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
        sans:  ['Inter', 'Helvetica Neue', 'system-ui', 'sans-serif'],
        serif: ['Source Serif 4', 'Georgia', 'serif'],
        mono:  ['DM Mono', 'ui-monospace', 'monospace'],
      },
      colors: {
        // Brand — Indigo-based (Tailwind indigo scale aliased for convenience)
        brand: {
          50:  '#EEF2FF',
          100: '#E0E7FF',
          200: '#C7D2FE',
          300: '#A5B4FC',
          400: '#818CF8',
          500: '#6366F1',
          600: '#4F46E5',
          700: '#4338CA',
          800: '#3730A3',
          900: '#312E81',
        },
        // Semantic status palette — replaces GTM names
        status: {
          ok:    '#10B981', // emerald-500
          warn:  '#F59E0B', // amber-500
          error: '#F43F5E', // rose-500
          info:  '#0EA5E9', // sky-500
        },
      },
      backgroundImage: {
        // Indigo → near-black gradient
        'brand-gradient': 'linear-gradient(to bottom, #4338CA, #0F172A)',
        // Diagonal variant
        'brand-gradient-diagonal': 'linear-gradient(135deg, #4338CA, #0F172A)',
      },
    },
  },
  plugins: [],
}
