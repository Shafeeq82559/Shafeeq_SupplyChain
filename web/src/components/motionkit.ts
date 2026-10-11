// Shared easing and entrance animation.
export const ease = [0.22, 0.8, 0.24, 1] as const
export const rise = (i = 0) => ({ initial: { opacity: 0, y: 16 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay: i * 0.07, ease } })
