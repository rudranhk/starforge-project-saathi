import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
        devanagari: ["var(--font-devanagari)", "Noto Sans Devanagari", "sans-serif"],
      },
      keyframes: {
        // Mic button "listening" state — an expanding ring communicates
        // "actively capturing audio right now", not just decoration.
        "listen-pulse": {
          "0%": { transform: "scale(1)", opacity: "0.55" },
          "100%": { transform: "scale(1.9)", opacity: "0" },
        },
        // Mic button "speaking" state — bars of varying height read as a
        // waveform at a glance, communicating "audio is playing".
        "waveform-bar": {
          "0%, 100%": { transform: "scaleY(0.3)" },
          "50%": { transform: "scaleY(1)" },
        },
        "fade-slide-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "listen-pulse": "listen-pulse 1.6s ease-out infinite",
        "waveform-bar": "waveform-bar 0.9s ease-in-out infinite",
        "fade-slide-in": "fade-slide-in 0.2s ease-out",
      },
    },
  },
  plugins: [],
};
export default config;
