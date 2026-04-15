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
    extend: {},
  },
  plugins: [],
};

