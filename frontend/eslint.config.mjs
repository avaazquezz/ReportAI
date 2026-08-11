// @ts-check
import withNuxt from './.nuxt/eslint.config.mjs'

export default withNuxt(
  {
    rules: {
      // Vuetify's own slot-naming convention for v-data-table (`#item.column_name`,
      // `#header.column_name`) reads as a directive modifier to this rule, which
      // doesn't know about it — a false positive, not a real invalid-slot usage.
      'vue/valid-v-slot': 'off'
    }
  }
)
