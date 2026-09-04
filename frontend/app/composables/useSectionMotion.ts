import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'

interface Options {
  /** ScrollTrigger start position (default: `top 78%`). Ignored with `immediate`. */
  start?: string
  /** Play on mount, once web fonts have settled, instead of on scroll-in. */
  immediate?: boolean
}

/**
 * One gsap.context per landing section. `build` fills a paused timeline whose string
 * selectors are scoped to `root`; it plays once when the section scrolls into view
 * (or on mount with `immediate`). Under prefers-reduced-motion the same timeline is
 * jumped to its end state, so anything that starts hidden (`.m-hide`) never stays hidden.
 */
export function useSectionMotion(
  root: Ref<HTMLElement | null>,
  build: (tl: gsap.core.Timeline) => void,
  options: Options = {}
) {
  let ctx: gsap.Context | undefined
  let tl: gsap.core.Timeline | undefined

  onMounted(() => {
    if (!root.value) return
    gsap.registerPlugin(ScrollTrigger)

    ctx = gsap.context(() => {
      const timeline = gsap.timeline({ paused: true, defaults: { ease: 'power2.out' } })
      tl = timeline
      build(timeline)

      const mm = gsap.matchMedia()
      mm.add('(prefers-reduced-motion: reduce)', () => {
        timeline.progress(1)
      })
      mm.add('(prefers-reduced-motion: no-preference)', () => {
        if (options.immediate) {
          document.fonts.ready.then(() => timeline.play())
          return
        }
        ScrollTrigger.create({
          trigger: root.value,
          start: options.start ?? 'top 78%',
          once: true,
          onEnter: () => timeline.play()
        })
      })
    }, root.value)
  })

  onBeforeUnmount(() => ctx?.revert())

  return { replay: () => tl?.restart() }
}
