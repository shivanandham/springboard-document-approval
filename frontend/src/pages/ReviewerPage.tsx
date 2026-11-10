import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Check, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, formatDate, type Document, type DocumentStatus } from '@/api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { FileLink, rowMotion, StatusBadge, TableMessage } from '@/pages/SubmitterPage'

type Tab = DocumentStatus | 'all'
type Decision = { doc: Document; decision: 'approve' | 'reject'; comment?: string }

const schema = z.object({ comment: z.string().trim().min(1, 'A comment is required to reject') })

export default function ReviewerPage() {
  const queryClient = useQueryClient()
  const [tab, setTab] = useState<Tab>('pending')
  const [rejecting, setRejecting] = useState<Document | null>(null)
  const documents = useQuery({ queryKey: ['documents', tab], queryFn: () => api.listDocuments(tab === 'all' ? undefined : tab) })
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

  return (
    <section className="grid gap-4">
      <div className="flex items-center justify-between gap-4">
        <h1 className="text-lg font-medium">Documents</h1>
        <Tabs value={tab} onValueChange={(value) => setTab(value as Tab)}>
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
