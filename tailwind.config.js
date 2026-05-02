/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./static/**/*.js",
  ],
  safelist: [
    "from-purple-400",
    "from-pink-400",
    "from-orange-400",
    "from-green-400",
    "from-blue-400",
    "to-purple-500",
    "to-pink-500",
    "to-orange-500",
    "to-green-500",
    "to-blue-500",
  ],
  theme: {
    extend: {
      colors: {
        'charity-dark': '#1f0606',
        'charity-gold': '#d58d4b',
        'charity-gold-hover': '#c97835',
      },
      animation: {
        'carousel': 'carousel 40s infinite linear',
        'slide-up': 'slideUp 0.8s ease-out forwards',
        'fade-in-up': 'fadeInUp 0.6s ease-out forwards',
      },
      keyframes: {
        carousel: {
          '0%': { opacity: '0', transform: 'scale(1.05) translateX(50px)' },
          '1%': { opacity: '1', transform: 'scale(1) translateX(0)' },
          '8%': { opacity: '1', transform: 'scale(1) translateX(0)' },
          '10%': { opacity: '0', transform: 'scale(0.95) translateX(-50px)' },
          '100%': { opacity: '0', transform: 'scale(0.95) translateX(-50px)' },
        },
        slideUp: {
          'from': { opacity: '0', transform: 'translateY(30px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        },
        fadeInUp: {
          'from': { opacity: '0', transform: 'translateY(30px)' },
          'to': { opacity: '1', transform: 'translateY(0)' },
        }
      }
    },
  },
  plugins: [],
};

