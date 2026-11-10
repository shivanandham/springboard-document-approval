import { zodResolver } from '@hookform/resolvers/zod'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, Inbox, Loader2, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState, type ReactNode } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, PAGE_SIZE, type Document, type DocumentStatus } from '@/api'
import { DocumentPanel } from '@/components/DocumentPanel'
import { enter, FileIcon, formatSize, PageHeading, Pagination, RelativeTime, rowMotion, StatusPill, TablePlaceholder, UserAvatar } from '@/components/common'
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
  pending: "You're all caught up. Nothing is waiting for review.",
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

export default function ReviewerPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('pending')
  const [rejecting, setRejecting] = useState<Document | null>(null)
  const [selected, setSelected] = useState<Document | null>(null)
  const [page, setPage] = useState(0)
  const documents = useQuery({
    queryKey: ['documents', tab, page],
    queryFn: () => api.listDocuments(page, tab === 'all' ? undefined : tab),
    placeholderData: keepPreviousData,
  })
  const { register, handleSubmit, reset, formState } = useForm({ resolver: zodResolver(schema), defaultValues: { comment: '' } })

  const decide = useMutation({
    mutationFn: ({ doc, decision, comment }: Decision) => api.decide(doc, decision, comment),
    onSuccess: (doc) => {
      toast.success(`“${doc.title}” ${doc.status}`)
      setRejecting(null)
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
  const items = documents.data?.items ?? []
  const total = documents.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)
  if (page > lastPage) setPage(lastPage)

  return (
    <>
      <PageHeading title="Review queue" subtitle="Documents awaiting your decision">
        <Tabs
          value={tab}
          onValueChange={(value) => {
            setTab(value as Tab)
            setPage(0)
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

      <motion.section {...enter(0.2)} className="overflow-hidden rounded-xl border bg-card shadow-xs">
        <Table>
          <TableHeader className="bg-muted/50">
            <TableRow className="hover:bg-transparent">
              <TableHead className="h-10 px-4 text-xs text-muted-foreground">Document</TableHead>
              <TableHead className="hidden h-10 px-4 text-xs text-muted-foreground sm:table-cell">Submitter</TableHead>
              <TableHead className="hidden h-10 px-4 text-xs text-muted-foreground sm:table-cell">Submitted</TableHead>
              <TableHead className="h-10 px-4 text-right text-xs text-muted-foreground">Decision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 && <TablePlaceholder columns={4} loading={documents.isPending} icon={Inbox} message={EMPTY[tab]} />}
            <AnimatePresence>
              {items.map((doc, index) => (
                <motion.tr
                  key={doc.id}
                  {...rowMotion(index)}
                  tabIndex={0}
                  onClick={() => setSelected(doc)}
                  onKeyDown={(event) => event.key === 'Enter' && event.target === event.currentTarget && setSelected(doc)}
                  className="cursor-pointer border-b transition-colors outline-none hover:bg-muted/50 focus-visible:bg-muted/50"
                >
                  <TableCell className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <FileIcon contentType={doc.file?.content_type} />
                      <div className="grid min-w-0 gap-0.5">
                        <span className="max-w-[18rem] truncate font-medium">{doc.title}</span>
                        {doc.file && (
                          <span className="max-w-[18rem] truncate text-xs text-muted-foreground">
                            {doc.file.original_name} · {formatSize(doc.file.size_bytes)}
                          </span>
                        )}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="hidden px-4 py-3 sm:table-cell">
                    <span className="flex items-center gap-2">
                      <UserAvatar name={doc.submitter.full_name} size="sm" />
                      {doc.submitter.full_name}
                    </span>
                  </TableCell>
                  <TableCell className="hidden px-4 py-3 text-muted-foreground sm:table-cell">
                    <RelativeTime iso={doc.created_at} />
                  </TableCell>
                  <TableCell className="px-4 py-3 text-right">
                    {doc.status === 'pending' ? (
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
                    ) : (
                      <StatusPill status={doc.status} />
                    )}
                  </TableCell>
                </motion.tr>
              ))}
            </AnimatePresence>
          </TableBody>
        </Table>
        <Pagination page={page} total={total} onChange={setPage} />
      </motion.section>

      <DocumentPanel
        doc={selected}
        onClose={() => setSelected(null)}
        footer={(doc) =>
          doc.status === 'pending' && (
            <>
              <Button variant="outline" className="h-9 px-4" disabled={busy(doc)} onClick={() => openReject(doc)}>
                <X />
                Reject
              </Button>
              <Button className="h-9 px-4" disabled={busy(doc)} onClick={() => decide.mutate({ doc, decision: 'approve' })}>
                {busy(doc) ? <Loader2 className="animate-spin" /> : <Check />}
                Approve
              </Button>
            </>
          )
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
