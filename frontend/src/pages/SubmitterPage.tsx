import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, formatDate, type Document } from '@/api'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const ACCEPTED = ['.pdf', '.docx', '.png', '.jpg', '.jpeg', '.txt']

const schema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200, 'Title must be at most 200 characters'),
  description: z.string().trim(),
  file: z
    .instanceof(FileList)
    .refine((files) => files.length === 1, 'Choose a file')
    .refine((files) => ACCEPTED.some((ext) => files[0]?.name.toLowerCase().endsWith(ext)), 'Accepted types: PDF, DOCX, PNG, JPG, TXT'),
})

const STATUS_STYLES = {
  pending: 'bg-muted text-muted-foreground',
  approved: 'bg-emerald-100 text-emerald-800',
  rejected: 'bg-red-100 text-red-800',
}

export function StatusBadge({ doc }: { doc: Document }) {
  const badge = (
    <motion.span key={doc.status} initial={{ opacity: 0, scale: 0.9 }} animate={{ opacity: 1, scale: 1 }} className="inline-flex">
      <Badge className={`capitalize ${STATUS_STYLES[doc.status]}`}>{doc.status}</Badge>
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

export function FileLink({ doc }: { doc: Document }) {
  if (!doc.file) return <span className="text-muted-foreground">—</span>
  return (
    <Button variant="link" className="h-auto max-w-56 justify-start truncate p-0" onClick={() => api.download(doc).catch((error) => toast.error(error.message))}>
      {doc.file.original_name}
    </Button>
  )
}

export function TableMessage({ columns, loading, message }: { columns: number; loading: boolean; message: string }) {
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

export const rowMotion = {
  initial: { opacity: 0, y: -6 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, x: 12 },
  className: 'border-b transition-colors hover:bg-muted/50',
} as const

export default function SubmitterPage() {
  const queryClient = useQueryClient()
  const documents = useQuery({ queryKey: ['documents', 'mine'], queryFn: () => api.listDocuments() })
  const { register, handleSubmit, reset, setError, formState } = useForm({ resolver: zodResolver(schema), defaultValues: { title: '', description: '' } })
  const { errors } = formState

  const submit = useMutation({
    mutationFn: (values: z.output<typeof schema>) => {
      const body = new FormData()
      body.append('title', values.title)
      if (values.description) body.append('description', values.description)
      body.append('file', values.file[0])
      return api.createDocument(body)
    },
    onSuccess: () => {
      toast.success('Document submitted')
      reset()
      queryClient.invalidateQueries({ queryKey: ['documents'] })
    },
    onError: (error) => {
      toast.error(error.message)
      if (error instanceof ApiError)
        for (const [field, message] of Object.entries(error.fields ?? {}))
          if (field in schema.shape) setError(field as keyof typeof schema.shape, { message: String(message) })
    },
  })

  const items = documents.data?.items ?? []

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Submit a document</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit((values) => submit.mutate(values))} className="grid gap-4" noValidate>
            <div className="grid gap-2">
              <Label htmlFor="title">Title</Label>
              <Input id="title" aria-invalid={!!errors.title} {...register('title')} />
              {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">
                Description <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea id="description" rows={3} {...register('description')} />
            </div>
            <div className="grid gap-2">
              <Label htmlFor="file">File</Label>
              <Input id="file" type="file" accept={ACCEPTED.join(',')} aria-invalid={!!errors.file} {...register('file')} />
              {errors.file && <p className="text-sm text-destructive">{errors.file.message}</p>}
            </div>
            <Button type="submit" className="justify-self-end" disabled={submit.isPending}>
              Submit
            </Button>
          </form>
        </CardContent>
      </Card>

      <section className="grid gap-3">
        <h2 className="text-lg font-medium">My documents</h2>
        <div className="rounded-xl bg-background ring-1 ring-foreground/10">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>File</TableHead>
                <TableHead>Submitted</TableHead>
                <TableHead>Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 && <TableMessage columns={4} loading={documents.isPending} message="No documents yet. Submitted documents will appear here." />}
              <AnimatePresence initial={false}>
                {items.map((doc) => (
                  <motion.tr key={doc.id} {...rowMotion}>
                    <TableCell className="font-medium">{doc.title}</TableCell>
                    <TableCell>
                      <FileLink doc={doc} />
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatDate(doc.created_at)}</TableCell>
                    <TableCell>
                      <StatusBadge doc={doc} />
                    </TableCell>
                  </motion.tr>
                ))}
              </AnimatePresence>
            </TableBody>
          </Table>
        </div>
      </section>
    </>
  )
}
