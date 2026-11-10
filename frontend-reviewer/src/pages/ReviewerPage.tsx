import { zodResolver } from '@hookform/resolvers/zod'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, formatDate, PAGE_SIZE, type Document, type DocumentStatus } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

type Tab = DocumentStatus | 'all'
type Decision = { doc: Document; decision: 'approve' | 'reject'; comment?: string }

const schema = z.object({ comment: z.string().trim().min(1, 'A comment is required to reject') })

const STATUS = {
  pending: { label: 'Pending', className: 'bg-muted text-muted-foreground' },
  approved: { label: 'Approved', className: 'bg-emerald-100 text-emerald-800' },
  rejected: { label: 'Rejected', className: 'bg-red-100 text-red-800' },
}

function StatusBadge({ doc }: { doc: Document }) {
  const badge = (
    <motion.span key={doc.status} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="inline-flex">
      <Badge className={STATUS[doc.status].className}>{STATUS[doc.status].label}</Badge>
    </motion.span>
  )
  if (doc.status !== 'rejected' || !doc.decision_comment) return badge
  return (
    <Tooltip>
      <TooltipTrigger className="cursor-help">{badge}</TooltipTrigger>
      <TooltipContent className="max-w-xs">{doc.decision_comment}</TooltipContent>
    </Tooltip>
  )
}

function FileLink({ doc }: { doc: Document }) {
  if (!doc.file) return <span className="text-muted-foreground">—</span>
  return (
    <Button variant="link" className="h-auto max-w-56 justify-start truncate p-0" onClick={() => api.download(doc).catch((error) => toast.error(error.message))}>
      {doc.file.original_name}
    </Button>
  )
}

function TableMessage({ columns, loading, message }: { columns: number; loading: boolean; message: string }) {
  if (loading)
    return Array.from({ length: 3 }, (_, i) => (
      <TableRow key={i}>
        <TableCell colSpan={columns}>
          <Skeleton className="h-5 w-full" />
        </TableCell>
      </TableRow>
    ))
  return (
    <TableRow>
      <TableCell colSpan={columns} className="py-10 text-center text-muted-foreground">
        {message}
      </TableCell>
    </TableRow>
  )
}

const rowMotion = {
  initial: { opacity: 0, y: -6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, x: 12 },
  className: 'border-b transition-colors hover:bg-muted/50',
} as const

function Pagination({ page, total, onChange }: { page: number; total: number; onChange: (page: number) => void }) {
  if (total <= PAGE_SIZE) return null
  const start = page * PAGE_SIZE
  return (
    <div className="flex items-center justify-end gap-2 text-sm text-muted-foreground">
      <span className="mr-2">
        {start + 1}–{Math.min(start + PAGE_SIZE, total)} of {total}
      </span>
      <Button variant="outline" size="sm" disabled={page === 0} onClick={() => onChange(page - 1)}>
        Prev
      </Button>
      <Button variant="outline" size="sm" disabled={start + PAGE_SIZE >= total} onClick={() => onChange(page + 1)}>
        Next
      </Button>
    </div>
  )
}

export default function ReviewerPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('pending')
  const [rejecting, setRejecting] = useState<Document | null>(null)
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
    <section className="grid gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-medium">Documents</h1>
        <Tabs
          value={tab}
          onValueChange={(value) => {
            setTab(value as Tab)
            setPage(0)
          }}
        >
          <TabsList>
            <TabsTrigger value="pending">Pending</TabsTrigger>
            <TabsTrigger value="approved">Approved</TabsTrigger>
            <TabsTrigger value="rejected">Rejected</TabsTrigger>
            <TabsTrigger value="all">All</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      <div className="rounded-xl bg-background ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Submitter</TableHead>
              <TableHead>Submitted</TableHead>
              <TableHead>File</TableHead>
              <TableHead className="text-right">Decision</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 && (
              <TableMessage columns={5} loading={documents.isPending} message={tab === 'all' ? 'No documents yet.' : `No ${tab} documents.`} />
            )}
            <AnimatePresence initial={false}>
              {items.map((doc) => (
                <motion.tr key={doc.id} {...rowMotion}>
                  <TableCell className="font-medium">{doc.title}</TableCell>
                  <TableCell>{doc.submitter.full_name}</TableCell>
                  <TableCell className="text-muted-foreground">{formatDate(doc.created_at)}</TableCell>
                  <TableCell>
                    <FileLink doc={doc} />
                  </TableCell>
                  <TableCell className="text-right">
                    {doc.status === 'pending' ? (
                      <div className="inline-flex gap-2">
                        <Button size="sm" disabled={busy(doc)} onClick={() => decide.mutate({ doc, decision: 'approve' })}>
                          <Check />
                          Approve
                        </Button>
                        <Button size="sm" variant="destructive" disabled={busy(doc)} onClick={() => openReject(doc)}>
                          <X />
                          Reject
                        </Button>
                      </div>
                    ) : (
                      <StatusBadge doc={doc} />
                    )}
                  </TableCell>
                </motion.tr>
              ))}
            </AnimatePresence>
          </TableBody>
        </Table>
      </div>
      <Pagination page={page} total={total} onChange={setPage} />

      <Dialog open={!!rejecting} onOpenChange={(open) => !open && !decide.isPending && setRejecting(null)}>
        <DialogContent>
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
              <Textarea id="comment" rows={4} aria-invalid={!!formState.errors.comment} {...register('comment')} />
              {formState.errors.comment && <p className="text-sm text-destructive">{formState.errors.comment.message}</p>}
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" disabled={decide.isPending} onClick={() => setRejecting(null)}>
                Cancel
              </Button>
              <Button type="submit" variant="destructive" disabled={decide.isPending}>
                Reject
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  )
}
