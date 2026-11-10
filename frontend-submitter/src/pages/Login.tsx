import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
import { motion } from 'motion/react'
import { useEffect, useState } from 'react'
import { useForm } from 'react-hook-form'
import { Navigate } from 'react-router'
import { toast } from 'sonner'
import { z } from 'zod'
import { ApiError } from '@/api'
import { useAuth } from '@/auth'
import { Brand } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

const schema = z.object({
  email: z.email('Enter a valid email'),
  password: z.string().min(1, 'Enter your password'),
})

const HEADLINE = ['Send it in.', 'See it signed off.']
const WORKSPACE = 'Submitter workspace. Log in with your work email.'

/** Headline lines rise and un-blur in sequence, then the form follows. */
const reveal = (delay: number) => ({
  initial: { opacity: 0, y: '0.35em', filter: 'blur(4px)' },
  animate: { opacity: 1, y: 0, filter: 'blur(0px)' },
  transition: { duration: 0.7, delay, ease: [0.2, 0.7, 0.2, 1] as const },
})

export default function Login() {
  const { user, login } = useAuth()
  const { register, handleSubmit, setError, clearErrors, formState } = useForm({ resolver: zodResolver(schema) })
  const { errors, isSubmitting } = formState
  // Rate limiting: the button stays disabled until Retry-After has passed, with a live countdown.
  const [lock, setLock] = useState<{ seconds: number } | null>(null)
  const [secondsLeft, setSecondsLeft] = useState(0)

  useEffect(() => {
    if (!lock) return
    const deadline = Date.now() + lock.seconds * 1000
    const timer = setInterval(() => {
      const left = Math.max(0, Math.ceil((deadline - Date.now()) / 1000))
      setSecondsLeft(left)
      if (left > 0) return
      clearInterval(timer)
      clearErrors('root')
    }, 250)
    return () => clearInterval(timer)
  }, [lock, clearErrors])

  if (user) return <Navigate to="/" replace />

  const onSubmit = handleSubmit(async ({ email, password }) => {
    try {
      await login(email, password)
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        setError('root', { message: error.message })
        if (error.retryAfter) {
          setSecondsLeft(error.retryAfter)
          setLock({ seconds: error.retryAfter })
        }
      } else if (error instanceof ApiError && error.status === 401) setError('root', { message: 'Invalid email or password' })
      else toast.error(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    }
  })

  return (
    <main className="relative isolate flex min-h-svh flex-col overflow-hidden px-5 py-7 sm:px-[8vw] sm:py-10">
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] mask-[radial-gradient(ellipse_60%_50%_at_45%_50%,black,transparent)] bg-size-[44px_44px]"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[radial-gradient(50%_40%_at_25%_0%,color-mix(in_oklch,var(--primary)_16%,transparent),transparent)]"
      />
      <Brand />
      <div className="mt-16 mb-auto max-w-4xl sm:my-auto">
        <h1 className="text-[clamp(2.75rem,7.2vw,6rem)] leading-[0.98] font-[650] tracking-[-0.045em]">
          {HEADLINE.map((line, i) => (
            <motion.span key={line} className="block" {...reveal(i * 0.12)}>
              {line}
            </motion.span>
          ))}
        </h1>
        <motion.form {...reveal(0.3)} onSubmit={onSubmit} className="mt-9 grid max-w-205 items-start gap-4 sm:mt-14 md:grid-cols-[1fr_1fr_auto] md:gap-3" noValidate>
          <div className="grid gap-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" placeholder="you@company.com" className="h-11 bg-card shadow-sm" aria-invalid={!!errors.email} {...register('email')} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="current-password" className="h-11 bg-card shadow-sm" aria-invalid={!!errors.password} {...register('password')} />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>
          <Button type="submit" className="h-11 px-7 tabular-nums md:mt-5.5" disabled={isSubmitting || secondsLeft > 0}>
            {isSubmitting && <Loader2 className="animate-spin" />}
            {secondsLeft > 0 ? `Try again in ${secondsLeft}s` : 'Log in'}
          </Button>
          {errors.root && (
            <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive md:col-span-3">
              {errors.root.message}
            </p>
          )}
        </motion.form>
        <motion.p {...reveal(0.3)} className="mt-3.5 text-sm text-muted-foreground">
          {WORKSPACE}
        </motion.p>
      </div>
    </main>
  )
}
