import gsap from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { CustomEase } from 'gsap/CustomEase'
import { SplitText } from 'gsap/SplitText'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'

/** Motion tokens, in seconds. The brand ease is `ra`: the same curve as --ease-ra in main.css. */
export const MOTION = { micro: 0.2, reveal: 0.7, piece: 1.1 } as const

export interface MotionConditions {
  /** The visitor accepts motion; the full choreography runs. */
  motion: boolean
  /** The visitor asked for less: jump to end states, crossfade, no scrub or pin. */
  reduce: boolean
  /** Wide and tall enough to pin a full-height scene (only when asked for with `desktop: true`). */
  desktop: boolean
  /** A mouse, not a finger: pointer-following effects only run here. */
  finePointer: boolean
}

let registered = false

function register() {
  if (registered) return
  registered = true
  gsap.registerPlugin(ScrollTrigger, CustomEase, SplitText, DrawSVGPlugin)
  CustomEase.create('ra', '0.22,0.8,0.12,1')
  gsap.defaults({ ease: 'ra' })
  ScrollTrigger.config({ ignoreMobileResize: true })
  // A late font changes headline heights, and every trigger below it with them.
  document.fonts.ready.then(() => ScrollTrigger.refresh())
}

/**
 * One gsap.matchMedia per component, scoped to `scope`: everything created inside `setup`
 * (tweens, ScrollTriggers, SplitTexts) is reverted when the component unmounts or when a media
 * condition flips, and `setup` runs again with the new conditions.
 */
export function useMotionScope(
  scope: Ref<HTMLElement | null>,
  setup: (c: MotionConditions, ctx: gsap.Context) => unknown,
  /** Also listen to "a desktop with room to pin a full-height scene" (1024×760 and up): setup
   * re-runs when that is crossed. Off by default, so a resize across it doesn't replay a
   * section that doesn't care. */
  options: { desktop?: boolean } = {}
) {
  let mm: gsap.MatchMedia | undefined

  onMounted(() => {
    if (!scope.value) return
    register()
    mm = gsap.matchMedia(scope.value)
    mm.add(
      {
        motion: '(prefers-reduced-motion: no-preference)',
        reduce: '(prefers-reduced-motion: reduce)',
        finePointer: '(hover: hover) and (pointer: fine)',
        ...(options.desktop ? { desktop: '(min-width: 1024px) and (min-height: 760px)' } : {})
      },
      (ctx) => {
        const cleanup = setup({ desktop: false, ...ctx.conditions } as unknown as MotionConditions, ctx)
        return typeof cleanup === 'function' ? (cleanup as () => void) : undefined
      }
    )
  })

  onBeforeUnmount(() => mm?.revert())
}

/** Line-by-line mask reveal for headings; call inside a `useMotionScope` setup, motion branch only. */
export function revealLines(targets: gsap.DOMTarget, start = 'top 86%') {
  SplitText.create(targets, {
    type: 'lines',
    mask: 'lines',
    autoSplit: true,
    // With autoSplit the tween is created here and returned, so a re-split (a late font, a
    // resize) replaces it instead of animating lines that no longer exist.
    onSplit: (self) =>
      gsap.from(self.lines, {
        yPercent: 110,
        duration: MOTION.reveal + 0.2,
        stagger: 0.09,
        scrollTrigger: { trigger: self.elements[0], start, once: true }
      })
  })
}
