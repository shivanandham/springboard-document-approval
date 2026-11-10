// Adapted from Magic UI's Animated Theme Toggler (MIT, https://magicui.design/docs/components/animated-theme-toggler):
// trimmed to the circle reveal in controlled mode, with a reduced-motion fallback and an animated icon swap.
import { useCallback, useEffect, useRef } from "react"
import { Moon, Sun } from "lucide-react"
import { AnimatePresence, motion } from "motion/react"
import { flushSync } from "react-dom"

interface AnimatedThemeTogglerProps extends React.ComponentPropsWithoutRef<"button"> {
  duration?: number
  theme: "light" | "dark"
  onThemeChange: (theme: "light" | "dark") => void
}

export const AnimatedThemeToggler = ({ duration = 500, theme, onThemeChange, ...props }: AnimatedThemeTogglerProps) => {
  const isDark = theme === "dark"
  const buttonRef = useRef<HTMLButtonElement>(null)
  const activeAnimRef = useRef<Animation | null>(null)
  const isTransitioningRef = useRef(false)

  useEffect(() => () => activeAnimRef.current?.cancel(), [])

  const toggleTheme = useCallback(() => {
    const button = buttonRef.current
    if (!button || isTransitioningRef.current) return
    const next = isDark ? "light" : "dark"
    const applyTheme = () => {
      // Toggle the class synchronously so the view transition snapshots the new theme.
      document.documentElement.classList.toggle("dark", next === "dark")
      onThemeChange(next)
    }

    if (typeof document.startViewTransition !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      applyTheme()
      return
    }

    // Percentages of the snapshot box, not px: Chrome can misplace px clip-paths on fractional display scales.
    const width = window.innerWidth
    const height = window.innerHeight
    const { top, left, width: w, height: h } = button.getBoundingClientRect()
    const x = left + w / 2
    const y = top + h / 2
    const radius = Math.hypot(Math.max(x, width - x), Math.max(y, height - y))
    const at = `at ${(x / width) * 100}% ${(y / height) * 100}%`
    // circle() percentage radii resolve against hypot(w, h) / sqrt(2) of the reference box.
    const end = `${(radius / (Math.hypot(width, height) / Math.SQRT2)) * 100}%`

    isTransitioningRef.current = true
    const transition = document.startViewTransition(() => flushSync(applyTheme))
    transition.finished.finally(() => (isTransitioningRef.current = false)).catch(() => {})
    transition.ready
      .then(() => {
        activeAnimRef.current = document.documentElement.animate(
          { clipPath: [`circle(0% ${at})`, `circle(${end} ${at})`] },
          { duration, easing: "ease-in-out", fill: "forwards", pseudoElement: "::view-transition-new(root)" }
        )
      })
      .catch(() => {})
  }, [isDark, duration, onThemeChange])

  return (
    <button type="button" ref={buttonRef} onClick={toggleTheme} {...props}>
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={isDark ? "sun" : "moon"}
          initial={{ opacity: 0, scale: 0.5, rotate: -90 }}
          animate={{ opacity: 1, scale: 1, rotate: 0 }}
          exit={{ opacity: 0, scale: 0.5, rotate: 90 }}
          transition={{ duration: 0.2, ease: "easeOut" }}
          className="inline-flex"
        >
          {isDark ? <Sun /> : <Moon />}
        </motion.span>
      </AnimatePresence>
      <span className="sr-only">Toggle theme</span>
    </button>
  )
}
