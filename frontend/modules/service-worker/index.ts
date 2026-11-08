import { createHash } from 'node:crypto'
import { readdir, readFile, writeFile } from 'node:fs/promises'
import { join, relative, sep } from 'node:path'
import { createResolver, defineNuxtModule } from 'nuxt/kit'

// What the phone keeps so the app opens with no coverage: the build's files and the few root files
// the page itself asks for. Not the landing's demo media, source maps, font formats only old
// browsers read (every browser with a service worker reads woff2) or favicon.ico (278 KB, and the
// page offers the SVG first).
const ROOT_FILES = new Set([
  'apple-touch-icon.png',
  'favicon.svg',
  'favicon-16x16.png',
  'favicon-32x32.png',
  'manifest.webmanifest'
])
const SKIPPED = /\.(map|eot|ttf|woff|gz|br)$/
// Nuxt polls it to learn about a newer deployment: always from the network, never a stored copy.
const LATEST_BUILD = '_nuxt/builds/latest.json'
// The texts in each language, written by @nuxtjs/i18n's prerenderMessages (nuxt.config.ts).
const MESSAGES = /^_i18n\/[^/]+\/[a-z]{2}\/messages\.json$/

function isPrecached(file: string): boolean {
  if (ROOT_FILES.has(file) || file.startsWith('icons/') || MESSAGES.test(file)) return true
  return file.startsWith('_nuxt/') && file !== LATEST_BUILD && !SKIPPED.test(file)
}

/** Writes /sw.js (from ./sw.js) into a production build, with the list of files it keeps. */
export default defineNuxtModule({
  meta: { name: 'service-worker' },
  setup(_options, nuxt) {
    if (nuxt.options.dev) return
    const { resolve } = createResolver(import.meta.url)

    // Fired once the build's public files are in place and before Nitro lists the ones it serves,
    // so /sw.js is served like any of them.
    nuxt.hook('nitro:build:public-assets', async (nitro) => {
      const publicDir = nitro.options.output.publicDir
      const files = (await readdir(publicDir, { recursive: true, withFileTypes: true }))
        .filter((entry) => entry.isFile())
        .map((entry) => relative(publicDir, join(entry.parentPath, entry.name)).split(sep).join('/'))
        .filter(isPrecached)
        .sort()
      if (!files.some((file) => MESSAGES.test(file))) {
        throw new Error('No prerendered i18n messages to keep: the app would open offline without its texts')
      }

      // The version is the content itself: a new deployment that changes nothing the phone keeps
      // doesn't make it download anything again.
      const hash = createHash('sha256')
      for (const file of files) hash.update(file).update(await readFile(join(publicDir, file)))
      const version = hash.digest('hex').slice(0, 12)

      const worker = await readFile(resolve('./sw.js'), 'utf8')
      const urls = files.map((file) => `/${file}`)
      await writeFile(
        join(publicDir, 'sw.js'),
        `const VERSION = '${version}'\nconst PRECACHE = ${JSON.stringify(urls)}\n\n${worker}`
      )
      nitro.logger.success(`Service worker ${version}: ${urls.length} files kept on the device`)
    })
  }
})
