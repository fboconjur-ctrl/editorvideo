/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#0a0b0d",
          900: "#121317",
          850: "#171920",
          800: "#1d1f27",
          700: "#2a2d38",
          600: "#3a3e4d",
        },
        accent: {
          DEFAULT: "#5b7cff",
          hover: "#7291ff",
          muted: "#28304f",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      boxShadow: {
        panel: "0 1px 2px rgba(0,0,0,0.4), 0 8px 24px -8px rgba(0,0,0,0.5)",
      },
    },
  },
  plugins: [],
};
