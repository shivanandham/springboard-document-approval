import { zodResolver } from '@hookform/resolvers/zod'
import { Loader2 } from 'lucide-react'
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

export default function Login() {
  const { user, login } = useAuth()
  const { register, handleSubmit, setError, formState } = useForm({ resolver: zodResolver(schema) })
  const { errors, isSubmitting } = formState

  if (user) return <Navigate to="/" replace />

  const onSubmit = handleSubmit(async ({ email, password }) => {
    try {
      await login(email, password)
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) setError('root', { message: 'Invalid email or password' })
      else toast.error(error instanceof Error ? error.message : 'Something went wrong. Please try again.')
    }
  })

  return (
    <main className="relative isolate flex min-h-svh items-center justify-center overflow-hidden p-4">
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[linear-gradient(to_right,var(--border)_1px,transparent_1px),linear-gradient(to_bottom,var(--border)_1px,transparent_1px)] mask-[radial-gradient(ellipse_60%_50%_at_50%_40%,black,transparent)] bg-size-[44px_44px]"
      />
      <div
        aria-hidden
        className="absolute inset-0 -z-10 bg-[radial-gradient(50%_40%_at_50%_0%,color-mix(in_oklch,var(--primary)_16%,transparent),transparent)]"
      />
      <div className="w-full max-w-sm animate-in rounded-2xl duration-500 ease-out fade-in zoom-in-90 border bg-card p-8 shadow-xl shadow-black/[0.04] dark:shadow-black/40">
        <div className="mb-8 grid animate-in justify-items-center delay-100 duration-500 ease-out fill-mode-both fade-in slide-in-from-left-12 gap-5 text-center">
          <Brand />
          <div className="grid gap-1.5">
            <h1 className="text-xl font-semibold tracking-tight">Welcome back</h1>
            <p className="text-sm text-muted-foreground">Log in to your account to continue</p>
          </div>
        </div>
        <form onSubmit={onSubmit} className="grid animate-in gap-4 delay-150 duration-500 ease-out fill-mode-both fade-in slide-in-from-left-12" noValidate>
          <div className="grid gap-2">
            <Label htmlFor="email">Email</Label>
            <Input id="email" type="email" autoComplete="email" className="h-9" aria-invalid={!!errors.email} {...register('email')} />
            {errors.email && <p className="text-sm text-destructive">{errors.email.message}</p>}
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="current-password" className="h-9" aria-invalid={!!errors.password} {...register('password')} />
            {errors.password && <p className="text-sm text-destructive">{errors.password.message}</p>}
          </div>
          {errors.root && (
            <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errors.root.message}
            </p>
          )}
          <Button type="submit" size="lg" className="mt-2 h-9" disabled={isSubmitting}>
            {isSubmitting && <Loader2 className="animate-spin" />}
            Log in
          </Button>
        </form>
      </div>
    </main>
  )
}
