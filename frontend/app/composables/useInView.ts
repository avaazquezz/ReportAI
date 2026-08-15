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
    onUnmounted(() => observer.disconnect())
  })

  return inView
}
