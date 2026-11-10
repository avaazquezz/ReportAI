import { defineNuxtModule } from 'nuxt/kit'

// vuetify-nuxt-module adds the Material Design Icons stylesheet (~420 KB, three quarters of the
// global CSS) to every page. Only the panel draws icons, so its layouts load it themselves
// (layouts/app.vue and auth.vue) and the public pages stop waiting for it before their first paint.
export default defineNuxtModule({
  meta: { name: 'panel-icons' },
  setup(_options, nuxt) {
    nuxt.hook('modules:done', () => {
      nuxt.options.css = nuxt.options.css.filter((entry) => !entry.includes('materialdesignicons'))
    })
  }
})
