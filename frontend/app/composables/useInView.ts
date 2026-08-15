export function useInView(target: Ref<HTMLElement | null>, threshold = 0.3) {
  const inView = ref(false)

  onMounted(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          inView.value = true
          observer.disconnect()
        }
      },
      { threshold }
    )
    if (target.value) observer.observe(target.value)
    // Targets inside a v-if mount after us — observe them when the ref appears,
    // otherwise the reveal would silently never trigger.
    const stop = watch(target, (el) => {
      if (el) {
        observer.observe(el)
        stop()
      }
    })
    onUnmounted(() => observer.disconnect())
  })

  return inView
}
