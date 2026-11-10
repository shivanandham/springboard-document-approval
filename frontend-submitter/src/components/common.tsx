import { cn } from 'cn'
import { ChevronsUpDown, FileCheck, FileImage, FileText, FileType, LogOut, RotateCw, TriangleAlert, type LucideIcon } from 'lucide-react'
import { motion } from 'motion/react'
import { useTheme } from 'next-themes'
import type { ReactNode } from 'react'
import { PAGE_SIZE, type DocumentStatus } from '@/api'
import { useAuth } from '@/auth'
import { AnimatedThemeToggler } from '@/components/ui/animated-theme-toggler'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Button, buttonVariants } from '@/components/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Skeleton } from '@/components/ui/skeleton'
import { TableCell, TableRow } from '@/components/ui/table'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

export function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

export function Brand({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-[15px] font-semibold tracking-tight', className)}>
      <span className="grid size-7 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm ring-1 ring-black/5 ring-inset">
        <FileCheck className="size-4" strokeWidth={2.25} />
      </span>
      DocFlow
    </span>
  )
}

const STATUS: Record<DocumentStatus, { label: string; pill: string; dot: string }> = {
  pending: {
    label: 'Pending',
    pill: 'bg-amber-50 text-amber-800 ring-amber-600/20 dark:bg-amber-400/10 dark:text-amber-300 dark:ring-amber-400/20',
    dot: 'bg-amber-500 dark:bg-amber-400',
  },
  approved: {
    label: 'Approved',
    pill: 'bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-400/10 dark:text-emerald-300 dark:ring-emerald-400/20',
    dot: 'bg-emerald-500 dark:bg-emerald-400',
  },
  rejected: {
    label: 'Rejected',
    pill: 'bg-rose-50 text-rose-800 ring-rose-600/20 dark:bg-rose-400/10 dark:text-rose-300 dark:ring-rose-400/20',
    dot: 'bg-rose-500 dark:bg-rose-400',
  },
}

export function StatusPill({ status, className }: { status: DocumentStatus; className?: string }) {
  const { label, pill, dot } = STATUS[status]
  return (
    <motion.span
      key={status}
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      className={cn('inline-flex h-6 items-center gap-1.5 rounded-full px-2.5 text-xs font-medium whitespace-nowrap ring-1 ring-inset', pill, className)}
    >
      <span className={cn('size-1.5 rounded-full', dot)} />
      {label}
    </motion.span>
  )
}

const FILE_TYPES: [match: (type: string) => boolean, Icon: LucideIcon, tint: string][] = [
  [(t) => t === 'application/pdf', FileText, 'bg-rose-50 text-rose-600 dark:bg-rose-400/10 dark:text-rose-300'],
  [(t) => t.includes('wordprocessingml'), FileType, 'bg-sky-50 text-sky-600 dark:bg-sky-400/10 dark:text-sky-300'],
  [(t) => t.startsWith('image/'), FileImage, 'bg-emerald-50 text-emerald-600 dark:bg-emerald-400/10 dark:text-emerald-300'],
]

export function FileIcon({ contentType = '', className }: { contentType?: string; className?: string }) {
  const [, Icon, tint] = FILE_TYPES.find(([match]) => match(contentType)) ?? [null, FileText, 'bg-muted text-muted-foreground']
  return (
    <span className={cn('grid size-9 shrink-0 place-items-center rounded-lg ring-1 ring-foreground/5 ring-inset', tint, className)}>
      <Icon className="size-[18px]" />
    </span>
  )
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')

export function UserAvatar({ name, size = 'default' }: { name: string; size?: 'sm' | 'default' }) {
  return (
    <Avatar size={size}>
      <AvatarFallback className="bg-primary/10 font-medium text-primary group-data-[size=sm]/avatar:text-[10px] dark:bg-primary/20 dark:text-indigo-200">
        {initials(name)}
      </AvatarFallback>
    </Avatar>
  )
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]
const relative = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto', style: 'narrow' })

function timeAgo(iso: string) {
  const seconds = (new Date(iso).getTime() - Date.now()) / 1000
  const unit = UNITS.find(([, size]) => Math.abs(seconds) >= size)
  return unit ? relative.format(Math.round(seconds / unit[1]), unit[0]) : 'just now'
}

export function RelativeTime({ iso, className }: { iso: string; className?: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <time dateTime={iso} className={cn('cursor-default whitespace-nowrap', className)}>
          {timeAgo(iso)}
        </time>
      </TooltipTrigger>
      <TooltipContent>{new Date(iso).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</TooltipContent>
    </Tooltip>
  )
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  return (
    <AnimatedThemeToggler
      theme={resolvedTheme === 'dark' ? 'dark' : 'light'}
      onThemeChange={setTheme}
      className={buttonVariants({ variant: 'ghost', size: 'icon' })}
      aria-label="Toggle theme"
    />
  )
}

function UserMenu() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="h-9 gap-2 pr-2 pl-1">
          <UserAvatar name={user.full_name} size="sm" />
          <span className="hidden sm:inline">{user.full_name}</span>
          <ChevronsUpDown className="text-muted-foreground" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex items-center gap-3 py-2 font-normal">
          <UserAvatar name={user.full_name} />
          <span className="grid min-w-0 gap-0.5">
            <span className="truncate text-sm font-medium text-foreground">{user.full_name}</span>
            <span className="truncate text-xs text-muted-foreground">{user.email}</span>
            <span className="text-xs text-muted-foreground capitalize">{user.roles.join(', ')}</span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={logout}>
          <LogOut />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function Header() {
  return (
    <header className="sticky top-0 z-40 border-b bg-card/80 backdrop-blur supports-backdrop-filter:bg-card/70">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4 sm:px-6">
        <Brand />
        <div className="flex items-center gap-1">
          <ThemeToggle />
          <UserMenu />
        </div>
      </div>
    </header>
  )
}

export function PageHeading({ title, subtitle, children }: { title: string; subtitle: string; children?: ReactNode }) {
  return (
    <motion.div {...enter(0.1)} className="flex flex-wrap items-end justify-between gap-4">
      <div className="grid gap-1">
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        <p className="text-sm text-muted-foreground">{subtitle}</p>
      </div>
      {children}
    </motion.div>
  )
}

export function EmptyState({ icon: Icon, children }: { icon: LucideIcon; children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-3 py-14 text-center">
      <span className="grid size-11 place-items-center rounded-xl bg-muted text-muted-foreground ring-1 ring-foreground/5 ring-inset">
        <Icon className="size-5" />
      </span>
      <p className="text-sm text-muted-foreground">{children}</p>
    </div>
  )
}

export function TablePlaceholder({ columns, loading, icon, message }: { columns: number; loading: boolean; icon: LucideIcon; message: string }) {
  if (!loading)
    return (
      <TableRow className="hover:bg-transparent">
        <TableCell colSpan={columns}>
          <EmptyState icon={icon}>{message}</EmptyState>
        </TableCell>
      </TableRow>
    )
  return Array.from({ length: 4 }, (_, i) => (
    <TableRow key={i} className="hover:bg-transparent">
      <TableCell>
        <div className="flex items-center gap-3">
          <Skeleton className="size-9 rounded-lg" />
          <div className="grid gap-1.5">
            <Skeleton className="h-3.5 w-44" />
            <Skeleton className="h-3 w-28" />
          </div>
        </div>
      </TableCell>
      {Array.from({ length: columns - 1 }, (_, j) => (
        <TableCell key={j} className={cn(j < columns - 2 && 'hidden sm:table-cell')}>
          <Skeleton className={cn('h-3.5 w-20', j === columns - 2 && 'ml-auto w-16 rounded-full')} />
        </TableCell>
      ))}
    </TableRow>
  ))
}

export function Pagination({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  if (total <= PAGE_SIZE) return null
  const start = page * PAGE_SIZE
  return (
    <div className="flex items-center justify-between gap-2 border-t px-4 py-3 text-sm text-muted-foreground">
      <span>
        <span className="font-medium text-foreground tabular-nums">
          {start + 1}–{Math.min(start + PAGE_SIZE, total)}
        </span>{' '}
        of <span className="tabular-nums">{total}</span>
      </span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onChange(page - 1)}>
          Previous
        </Button>
        <Button variant="outline" size="sm" disabled={start + PAGE_SIZE >= total} onClick={() => onChange(page + 1)}>
          Next
        </Button>
      </div>
    </div>
  )
}

/** Page sections slide in from the left. */
export const enter = (delay = 0.1) => ({
  initial: { opacity: 0, x: -20 },
  animate: { opacity: 1, x: 0 },
  transition: { duration: 0.4, delay },
})

/** Table rows stagger in and fade out when removed. */
export const rowMotion = (index: number) => ({
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.4, delay: Math.min(index, 10) * 0.05 } },
  exit: { opacity: 0, transition: { duration: 0.2 } },
})

/** Shown by the app-wide error boundary when rendering crashes. */
export function ErrorFallback() {
  return (
    <main className="flex min-h-svh items-center justify-center p-4">
      <div role="alert" className="grid w-full max-w-sm justify-items-center gap-5 rounded-2xl border bg-card p-8 text-center shadow-sm">
        <span className="grid size-11 place-items-center rounded-xl bg-muted text-muted-foreground ring-1 ring-foreground/5 ring-inset">
          <TriangleAlert className="size-5" />
        </span>
        <div className="grid gap-1.5">
          <h1 className="text-lg font-semibold tracking-tight">Something went wrong</h1>
          <p className="text-sm text-muted-foreground">An unexpected error stopped this page. Reloading usually fixes it.</p>
        </div>
        <Button className="h-9 px-4" onClick={() => window.location.reload()}>
          <RotateCw />
          Reload
        </Button>
      </div>
    </main>
  )
}
