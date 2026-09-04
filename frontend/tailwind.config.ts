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
        ink: { 800: '#1B2029', 900: '#12151C' },
        paper: { 50: '#EEF1F4', 100: '#E3E8EE' },
        surface: { 0: '#FFFFFF' },
        // Warm frame color for header/footer — echoes the capture-orange accent
        // family without its saturation, so the page's neutral bookends feel
        // tied to the brand instead of the cooler blue-grey paper-50.
        cream: { 50: '#FBEEE7' },
        // 600 is a contrast-safe darker step for text/icons/button fills on light
        // backgrounds — white-on-500 and 500-as-text-on-white both fail WCAG (~2.5-2.8:1).
        capture: { 100: '#FFE7DF', 500: '#FF6A45', 600: '#C0432A' },
        approved: { 100: '#DDF3EA', 600: '#1C8F6A' },
        pending: { 600: '#B8860B' },
        failed: { 600: '#C0392B' },
        slate: { 300: '#C6CCD3' },
        // The demo document's own heading color — document mockups wear the *client's*
        // template styling, deliberately not ReportAI's orange.
        doc: { 700: '#1F2D4A' }
      },
      boxShadow: {
        // A sheet of paper on a desk, not a floating SaaS card.
        page: '0 1px 2px rgba(18, 21, 28, 0.08), 0 12px 32px -12px rgba(18, 21, 28, 0.35)',
        float: '0 24px 48px -16px rgba(18, 21, 28, 0.3)'
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'sans-serif'],
        body: ['"IBM Plex Sans"', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace']
      }
    }
  }
}
