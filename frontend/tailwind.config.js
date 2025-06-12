import tailwindcssLineClamp from '@tailwindcss/line-clamp';

/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'dark-bg': '#1a1a1a', // Equivalent to Bootstrap's bg-dark or similar for consistency
        'coral': '#FF6B6B', // Placeholder color, adjust as needed
        'gold': '#FFD700',
        'silver': '#C0C0C0',
        'bronze': '#CD7F32',
      },
      backgroundImage: {
        'gradient-blue': 'linear-gradient(to right, #007bff, #00c6ff)', // Example gradient, adjust as needed
        'gradient-teal': 'linear-gradient(to right, #20c997, #17a2b8)', // Example gradient for Take Quiz
        'gradient-purple': 'linear-gradient(to right, #6f42c1, #8a2be2)', // Example gradient for View Assignment
      },
      textColor: {
        'white-75': 'rgba(255, 255, 255, 0.75)',
        'white-80': 'rgba(255, 255, 255, 0.8)',
        'white-70': 'rgba(255, 255, 255, 0.7)',
        'white-50': 'rgba(255, 255, 255, 0.5)',
      },
    },
  },
  plugins: [
    tailwindcssLineClamp,
  ],
} 