import { zodResolver } from '@hookform/resolvers/zod'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, CheckCheck, Inbox, Loader2, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, PAGE_SIZE, type Document, type DocumentStatus } from '@/api'
import { DocumentView, SplitView } from '@/components/DocumentPanel'
import { EmptyState, enter, FileIcon, formatSize, PageHeading, Pagination, RelativeTime, rowMotion, StatusPill, TablePlaceholder, useWide, UserAvatar } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

type Tab = DocumentStatus | 'all'
type Decision = { doc: Document; decision: 'approve' | 'reject'; comment?: string }

const schema = z.object({ comment: z.string().trim().min(1, 'A comment is required to reject') })

const EMPTY: Record<Tab, string> = {
  pending: 'No documents are waiting for review.',
  approved: 'No approved documents yet.',
  rejected: 'No rejected documents yet.',
  all: 'No documents yet.',
}

function RowAction({ label, onClick, disabled, children, className }: { label: string; onClick: () => void; disabled: boolean; children: ReactNode; className: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          disabled={disabled}
          className={className}
          onClick={(event) => {
            event.stopPropagation()
            onClick()
          }}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  )
}

/** The next pending document after `doc` in list order, wrapping around. */
function nextPending(items: Document[], doc: Document) {
  const index = items.findIndex((item) => item.id === doc.id)
  return [...items.slice(index + 1), ...items.slice(0, Math.max(index, 0))].find((item) => item.status === 'pending' && item.id !== doc.id) ?? null
}

export default function ReviewerPage() {
  const queryClient = useQueryClient()
  const wide = useWide()
  const [tab, setTab] = useState<Tab>('pending')
  const [page, setPage] = useState(0)
  const [rejecting, setRejecting] = useState<Document | null>(null)
  const [selected, setSelected] = useState<Document | null>(null)
  // Set when a decision leaves nothing pending, so the docked pane stops auto-selecting.
  const [caughtUp, setCaughtUp] = useState(false)
  const [open, setOpen] = useState(false)
  const documents = useQuery({
    queryKey: ['documents', tab, page],
    queryFn: () => api.listDocuments(page, tab === 'all' ? undefined : tab),
    placeholderData: keepPreviousData,
  })
  const { register, handleSubmit, reset, formState } = useForm({ resolver: zodResolver(schema), defaultValues: { comment: '' } })

  const items = documents.data?.items ?? []
  const total = documents.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)
  if (page > lastPage) setPage(lastPage)
  // Docked, the pane always shows something: the selection, else the first row of the tab.
  const current = selected ?? (wide && !caughtUp && !documents.isPlaceholderData ? (items[0] ?? null) : null)

  const select = (doc: Document | null) => {
    setSelected(doc)
    setCaughtUp(false)
    setOpen(!!doc)
  }

  const decide = useMutation({
    mutationFn: ({ doc, decision, comment }: Decision) => api.decide(doc, decision, comment),
    onSuccess: (doc) => {
      toast.success(`“${doc.title}” ${doc.status}`)
      setRejecting(null)
      const next = nextPending(items, doc)
      setSelected(next)
      setCaughtUp(!next)
      if (!next) setOpen(false)
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast.error('Already decided by someone else')
        setRejecting(null)
      } else toast.error(error.message)
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  })

  const openReject = (doc: Document) => {
    reset()
    setRejecting(doc)
  }

  const busy = (doc: Document) => decide.isPending && decide.variables.doc.id === doc.id

  return (
    <>
      <PageHeading title="Review queue" subtitle="Documents awaiting your decision">
        <Tabs
          value={tab}
          onValueChange={(value) => {
            setTab(value as Tab)
            setPage(0)
            select(null)
          }}
        >
          <TabsList className="h-9 border bg-muted/60 p-0.5">
            {(['pending', 'approved', 'rejected', 'all'] as const).map((value) => (
              <TabsTrigger key={value} value={value} className="px-3 capitalize data-active:bg-card data-active:shadow-xs">
                {value}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </PageHeading>

      <SplitView
        title={current?.title ?? 'Review queue'}
        open={open}
        onClose={() => setOpen(false)}
        detail={
          current ? (
            <DocumentView
              key={current.id}
              doc={current}
              actions={(doc) =>
                doc.status === 'pending' && (
                  <>
                    <Button variant="outline" size="sm" disabled={busy(doc)} onClick={() => openReject(doc)}>
                      <X />
                      Reject
                    </Button>
                    <Button size="sm" disabled={busy(doc)} onClick={() => decide.mutate({ doc, decision: 'approve' })}>
                      {busy(doc) ? <Loader2 className="animate-spin" /> : <Check />}
                      Approve
                    </Button>
                  </>
                )
              }
            />
          ) : (
            wide && (
              <div className="grid h-full place-items-center p-6">
                {caughtUp || tab === 'pending' ? (
                  <EmptyState icon={CheckCheck}>
                    <span className="block font-medium text-foreground">All caught up</span>
                    Nothing is waiting for review.
                  </EmptyState>
                ) : (
                  <EmptyState icon={Inbox}>{EMPTY[tab]}</EmptyState>
                )}
              </div>
            )
          )
        }
        list={
          <motion.section {...enter(0.2)} className="flex flex-col overflow-hidden rounded-xl border bg-card shadow-xs xl:h-full">
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Table className="table-fixed">
                <TableHeader className="bg-muted/50">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-10 px-4 text-xs text-muted-foreground">Document</TableHead>
                    <TableHead className="h-10 w-32 px-4 text-right text-xs text-muted-foreground">Decision</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length === 0 && <TablePlaceholder columns={2} loading={documents.isPending} icon={Inbox} message={EMPTY[tab]} />}
                  <AnimatePresence>
                    {items.map((doc, index) => (
                      <motion.tr
                        key={doc.id}
                        {...rowMotion(index)}
                        tabIndex={0}
                        onClick={() => select(doc)}
                        onKeyDown={(event) => event.key === 'Enter' && event.target === event.currentTarget && select(doc)}
                        data-selected={(wide && current?.id === doc.id) || undefined}
                        className="cursor-pointer border-b transition-colors outline-none hover:bg-muted/50 focus-visible:bg-muted/50 data-selected:bg-primary/5 data-selected:shadow-[inset_3px_0_0_var(--primary)]"
                      >
                        <TableCell className="px-4 py-3">
                          <div className="flex items-center gap-3">
                            <FileIcon contentType={doc.file?.content_type} />
                            <div className="grid min-w-0 gap-1">
                              <span className="truncate font-medium">{doc.title}</span>
                              <span className="flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground">
                                <UserAvatar name={doc.submitter.full_name} size="sm" />
                                <span className="truncate">
                                  {doc.submitter.full_name}
                                  {doc.file && ` · ${formatSize(doc.file.size_bytes)}`} · <RelativeTime iso={doc.created_at} />
                                </span>
                              </span>
                            </div>
                          </div>
                        </TableCell>
                        <TableCell className="px-4 py-3 text-right">
                          {doc.status !== 'pending' ? (
                            <StatusPill status={doc.status} />
                          ) : (
                            !wide && (
                              <div className="inline-flex gap-1">
                                <RowAction
                                  label="Reject"
                                  disabled={busy(doc)}
                                  onClick={() => openReject(doc)}
                                  className="text-muted-foreground hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-400/10 dark:hover:text-rose-300"
                                >
                                  <X />
                                </RowAction>
                                <RowAction
                                  label="Approve"
                                  disabled={busy(doc)}
                                  onClick={() => decide.mutate({ doc, decision: 'approve' })}
                                  className="text-muted-foreground hover:bg-emerald-50 hover:text-emerald-600 dark:hover:bg-emerald-400/10 dark:hover:text-emerald-300"
                                >
                                  {busy(doc) ? <Loader2 className="animate-spin" /> : <Check />}
                                </RowAction>
                              </div>
                            )
                          )}
                        </TableCell>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </TableBody>
              </Table>
            </div>
            <Pagination page={page} total={total} onChange={setPage} />
          </motion.section>
        }
      />

      <Dialog open={!!rejecting} onOpenChange={(open) => !open && !decide.isPending && setRejecting(null)}>
        <DialogContent className="sm:max-w-md">
          <form
            onSubmit={handleSubmit(({ comment }) => rejecting && decide.mutate({ doc: rejecting, decision: 'reject', comment }))}
            className="grid gap-4"
            noValidate
          >
            <DialogHeader>
              <DialogTitle>Reject document</DialogTitle>
              <DialogDescription>“{rejecting?.title}” will be rejected. The submitter will see your comment.</DialogDescription>
            </DialogHeader>
            <div className="grid gap-2">
              <Label htmlFor="comment">Comment</Label>
              <Textarea id="comment" rows={4} className="resize-none" aria-invalid={!!formState.errors.comment} {...register('comment')} />
              {formState.errors.comment && <p className="text-sm text-destructive">{formState.errors.comment.message}</p>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" disabled={decide.isPending} onClick={() => setRejecting(null)}>
                Cancel
              </Button>
              <Button type="submit" className="bg-destructive text-white hover:bg-destructive/90" disabled={decide.isPending}>
                {decide.isPending && <Loader2 className="animate-spin" />}
                Reject
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}
