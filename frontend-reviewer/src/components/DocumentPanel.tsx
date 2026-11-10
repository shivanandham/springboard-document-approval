import { useQuery } from '@tanstack/react-query'
import { cn } from 'cn'
import { ArrowRight, Download } from 'lucide-react'
import { lazy, Suspense, useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import { api, type Document, type DocumentEvent } from '@/api'
import { FileIcon, formatSize, RelativeTime, StatusPill, UserAvatar } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Skeleton } from '@/components/ui/skeleton'

const FileViewer = lazy(() => import('@/components/FileViewer'))

const VERB = { submitted: 'submitted the document', approved: 'approved', rejected: 'rejected' }
const DOT = { submitted: 'bg-primary', approved: 'bg-emerald-500', rejected: 'bg-rose-500' }

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="grid gap-2.5">
      <h3 className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  )
}

function Timeline({ events }: { events?: DocumentEvent[] }) {
  if (!events)
    return (
      <div className="grid gap-4">
        {[0, 1].map((i) => (
          <div key={i} className="flex gap-3">
            <Skeleton className="mt-1 size-2.5 rounded-full" />
            <div className="grid flex-1 gap-1.5">
              <Skeleton className="h-3.5 w-1/2" />
              <Skeleton className="h-3 w-24" />
            </div>
          </div>
        ))}
      </div>
    )
  return (
    <ol className="grid">
      {events.map((event, i) => (
        <li key={event.id} className="relative flex gap-3 pb-5 last:pb-0">
          {i < events.length - 1 && <span aria-hidden className="absolute top-4 bottom-0 left-[4.5px] w-px bg-border" />}
          <span className={cn('relative mt-1.5 size-2.5 shrink-0 rounded-full ring-4 ring-card', DOT[event.event])} />
          <div className="grid min-w-0 flex-1 gap-1.5">
            <p className="text-sm">
              <span className="font-medium">{event.actor.full_name}</span> <span className="text-muted-foreground">{VERB[event.event]}</span>
              <span className="text-muted-foreground"> · </span>
              <RelativeTime iso={event.created_at} className="text-muted-foreground" />
            </p>
            <div className="flex items-center gap-1.5">
              {event.from_status && (
                <>
                  <StatusPill status={event.from_status} />
                  <ArrowRight className="size-3.5 text-muted-foreground" />
                </>
              )}
              <StatusPill status={event.to_status} />
            </div>
            {event.comment && <p className="rounded-lg border bg-muted/40 px-3 py-2 text-sm whitespace-pre-wrap">{event.comment}</p>}
          </div>
        </li>
      ))}
    </ol>
  )
}

export function DocumentPanel({ doc, onClose, footer }: { doc: Document | null; onClose: () => void; footer?: (doc: Document) => ReactNode }) {
  // Keep showing the last document while the sheet animates closed.
  const [shown, setShown] = useState(doc)
  if (doc && doc !== shown) setShown(doc)
  const detail = useQuery({ queryKey: ['documents', 'detail', shown?.id], queryFn: () => api.getDocument(shown!.id), enabled: !!shown })
  const current = detail.data ?? shown
  const actions = current && footer?.(current)

  return (
    <Sheet open={!!doc} onOpenChange={(open) => !open && onClose()}>
      <SheetContent className="gap-0 bg-card data-[side=right]:w-full data-[side=right]:sm:max-w-3xl">
        {current && (
          <>
            <SheetHeader className="gap-4 border-b p-5 pr-14">
              <div className="flex items-start gap-3">
                <FileIcon contentType={current.file?.content_type} className="size-10" />
                <div className="grid min-w-0 gap-1">
                  <SheetTitle className="truncate text-base font-semibold">{current.title}</SheetTitle>
                  <SheetDescription className="truncate text-xs">
                    {current.file ? `${current.file.original_name} · ${formatSize(current.file.size_bytes)}` : 'No file attached'}
                  </SheetDescription>
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
                <StatusPill status={current.status} />
                <span className="flex items-center gap-2">
                  <UserAvatar name={current.submitter.full_name} size="sm" />
                  {current.submitter.full_name}
                </span>
                <span className="text-muted-foreground">
                  Submitted <RelativeTime iso={current.created_at} />
                </span>
                {current.file && (
                  <Button variant="outline" size="sm" className="ml-auto" onClick={() => api.download(current).catch((error) => toast.error(error.message))}>
                    <Download />
                    Download
                  </Button>
                )}
              </div>
            </SheetHeader>

            <div className="flex-1 overflow-y-auto">
              <div className="grid gap-7 p-5">
                {current.file && (
                  <div className="overflow-hidden rounded-xl border bg-muted/50">
                    <Suspense fallback={<div className="h-82" />}>
                      <FileViewer key={current.file.id} id={current.id} contentType={current.file.content_type} />
                    </Suspense>
                  </div>
                )}
                {current.description && (
                  <Section title="Description">
                    <p className="text-sm leading-relaxed whitespace-pre-wrap">{current.description}</p>
                  </Section>
                )}
                {current.decision_comment && (
                  <Section title="Decision comment">
                    <p
                      className={cn(
                        'rounded-lg border px-4 py-3 text-sm leading-relaxed whitespace-pre-wrap',
                        current.status === 'rejected'
                          ? 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-400/20 dark:bg-rose-400/10 dark:text-rose-100'
                          : 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-400/20 dark:bg-emerald-400/10 dark:text-emerald-100',
                      )}
                    >
                      {current.decision_comment}
                    </p>
                  </Section>
                )}
                <Section title="Activity">
                  <Timeline events={detail.data?.events} />
                </Section>
              </div>
            </div>

            {actions && <div className="flex justify-end gap-2 border-t bg-card px-5 py-3">{actions}</div>}
          </>
        )}
      </SheetContent>
    </Sheet>
  )
}
