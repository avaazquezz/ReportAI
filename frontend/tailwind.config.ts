import type { Config } from 'tailwindcss'

// Vuetify owns the CSS reset — Tailwind is layout/spacing utilities only,
// so its Preflight reset must stay off or it fights Vuetify's own base styles.
export default <Partial<Config>>{
  corePlugins: {
    preflight: false
  },
  theme: {
    extend: {
      colors: {
        ink: { 900: '#12151C' },
        paper: { 50: '#EEF1F4' },
        surface: { 0: '#FFFFFF' },
        capture: { 500: '#FF6A45' },
        approved: { 600: '#1C8F6A' },
        pending: { 600: '#B8860B' },
        failed: { 600: '#C0392B' },
        slate: { 300: '#C6CCD3' }
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"IBM Plex Sans"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace']
      }
    }
  }
}
