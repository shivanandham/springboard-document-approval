import { zodResolver } from '@hookform/resolvers/zod'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { cn } from 'cn'
import { FileStack, Loader2, Plus, UploadCloud, X } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { useController, useForm, type Control } from 'react-hook-form'
import { toast } from 'sonner'
import { z } from 'zod'
import { api, ApiError, PAGE_SIZE, type Document } from '@/api'
import { DocumentView, SplitView } from '@/components/DocumentPanel'
import { enter, FileIcon, formatSize, PageHeading, Pagination, RelativeTime, rowMotion, StatusPill, TablePlaceholder, useWide } from '@/components/common'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const ACCEPT = {
  'application/pdf': ['.pdf'],
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
  'image/png': ['.png'],
  'image/jpeg': ['.jpg', '.jpeg'],
  'text/plain': ['.txt'],
}
const ACCEPTED = Object.values(ACCEPT).flat()
const MAX_BYTES = 10 * 1024 * 1024
const REJECTED: Record<string, string> = { 'file-too-large': 'File is larger than 10 MB', 'file-invalid-type': 'Unsupported file type' }

const schema = z.object({
  title: z.string().trim().min(1, 'Title is required').max(200, 'Title must be at most 200 characters'),
  description: z.string().trim(),
  file: z
    .instanceof(File, { message: 'Choose a file' })
    .refine((file) => ACCEPTED.some((ext) => file.name.toLowerCase().endsWith(ext)), 'Accepted types: PDF, DOCX, PNG, JPG, TXT')
    .refine((file) => file.size <= MAX_BYTES, 'The file must be 10 MB or smaller'),
})

type Values = z.input<typeof schema>

type DropZoneProps = {
  control: Control<Values>
  uploading: boolean
  invalid: boolean
  /** Called with a message when a picked file is refused, and with undefined when one is accepted. */
  onReject: (message?: string) => void
}

function DropZone({ control, uploading, invalid, onReject }: DropZoneProps) {
  const { field } = useController({ control, name: 'file' })
  const file = field.value as File | undefined
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPT,
    maxSize: MAX_BYTES,
    multiple: false,
    disabled: uploading,
    onDrop: (accepted, rejected) => {
      field.onChange(accepted[0])
      const code = rejected[0]?.errors[0]?.code
      onReject(code ? (REJECTED[code] ?? 'Choose a single PDF, DOCX, PNG, JPG or TXT file') : undefined)
    },
  })

  return (
    <div className="h-full overflow-hidden">
      <AnimatePresence mode="wait" initial={false}>
        {file ? (
          <motion.div
            key="file"
            initial={{ opacity: 0, x: '100%' }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: '100%' }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className={cn('relative flex h-full min-h-40 items-center gap-3 overflow-hidden rounded-xl border bg-card p-4', invalid && 'border-destructive/60')}
          >
            <FileIcon contentType={file.type} className="size-10" />
            <div className="grid min-w-0 flex-1 gap-0.5">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{uploading ? 'Uploading…' : formatSize(file.size)}</p>
            </div>
            <Button type="button" variant="ghost" size="icon-sm" aria-label="Remove file" disabled={uploading} onClick={() => field.onChange(undefined)}>
              <X />
            </Button>
            {uploading && (
              <div role="progressbar" aria-label="Uploading" className="absolute inset-x-0 bottom-0 h-1 overflow-hidden bg-primary/10">
                <motion.div className="h-full w-2/5 rounded-full bg-primary" animate={{ x: ['-100%', '250%'] }} transition={{ duration: 1.1, ease: 'easeInOut', repeat: Infinity }} />
              </div>
            )}
          </motion.div>
        ) : (
          <motion.div
            key="zone"
            exit={{ opacity: 0, x: '100%' }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            {...(getRootProps() as object)}
            className={cn(
              'flex h-full min-h-40 cursor-pointer flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-input bg-muted/40 p-6 text-center transition-colors outline-none hover:border-primary/50 hover:bg-primary/[0.03] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50',
              isDragActive && 'border-primary bg-primary/5',
              invalid && 'border-destructive/60',
            )}
          >
            <input {...getInputProps({ id: 'file', 'aria-invalid': invalid })} />
            <span className="grid size-10 place-items-center rounded-full bg-card shadow-xs ring-1 ring-foreground/10">
              <UploadCloud className="size-5 text-muted-foreground" />
            </span>
            <div className="grid gap-1">
              <p className="text-sm">
                {isDragActive ? (
                  'Drop to attach'
                ) : (
                  <>
                    Drop a file or <span className="font-medium text-primary underline-offset-4 hover:underline">browse</span>
                  </>
                )}
              </p>
              <p className="text-xs text-muted-foreground">PDF, DOCX, PNG, JPG or TXT · up to 10 MB</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function DocumentRow({ doc, index, selected, onOpen }: { doc: Document; index: number; selected: boolean; onOpen: () => void }) {
  const pill = <StatusPill status={doc.status} />
  return (
    <motion.tr
      {...rowMotion(index)}
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(event) => event.key === 'Enter' && onOpen()}
      data-selected={selected || undefined}
      className="cursor-pointer border-b transition-colors outline-none hover:bg-muted/50 focus-visible:bg-muted/50 data-selected:bg-primary/5 data-selected:shadow-[inset_3px_0_0_var(--primary)]"
    >
      <TableCell className="px-4 py-3">
        <div className="flex items-center gap-3">
          <FileIcon contentType={doc.file?.content_type} />
          <div className="grid min-w-0 gap-0.5">
            <span className="truncate font-medium">{doc.title}</span>
            <span className="truncate text-xs text-muted-foreground">
              {doc.file && `${doc.file.original_name} · ${formatSize(doc.file.size_bytes)} · `}
              <RelativeTime iso={doc.created_at} />
            </span>
          </div>
        </div>
      </TableCell>
      <TableCell className="px-4 py-3 text-right">
        {doc.status === 'rejected' && doc.decision_comment ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="inline-flex cursor-help">{pill}</span>
            </TooltipTrigger>
            <TooltipContent className="max-w-xs">{doc.decision_comment}</TooltipContent>
          </Tooltip>
        ) : (
          pill
        )}
      </TableCell>
    </motion.tr>
  )
}

function NewDocumentForm({ onCreated, onCancel }: { onCreated: (doc: Document) => void; onCancel: () => void }) {
  const queryClient = useQueryClient()
  const [rejectedPick, setRejectedPick] = useState<string>()
  const { register, control, handleSubmit, reset, setError, formState } = useForm<Values, unknown, z.output<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { title: '', description: '' },
  })
  const { errors } = formState

  const submit = useMutation({
    mutationFn: (values: z.output<typeof schema>) => {
      const body = new FormData()
      body.append('title', values.title)
      if (values.description) body.append('description', values.description)
      body.append('file', values.file)
      return api.createDocument(body)
    },
    onSuccess: (doc) => {
      toast.success('Document submitted')
      queryClient.invalidateQueries({ queryKey: ['documents'] })
      onCreated(doc)
    },
    onError: (error) => {
      toast.error(error.message)
      if (!(error instanceof ApiError)) return
      for (const [field, message] of Object.entries(error.fields ?? {}))
        if (field in schema.shape) setError(field as keyof typeof schema.shape, { message: String(message) })
      // The server is the final word on size and type; show its message on the file field.
      if (error.status === 413 || error.status === 415) setError('file', { message: error.message })
    },
  })

  return (
    <form onSubmit={handleSubmit((values) => submit.mutate(values))} className="@container flex h-full min-h-0 flex-col" noValidate>
      <header data-slot="pane-header" className="grid gap-1 border-b p-5">
        <h2 className="text-base font-semibold tracking-tight">New document</h2>
        <p className="text-xs text-muted-foreground">A reviewer sees it as soon as you submit.</p>
      </header>
      <div className="flex-1 overflow-y-auto">
        <div className="grid gap-5 p-5 @xl:grid-cols-2">
          <div className="grid content-start gap-4">
            <div className="grid gap-2">
              <Label htmlFor="title">Title</Label>
              <Input id="title" className="h-9" aria-invalid={!!errors.title} {...register('title')} />
              {errors.title && <p className="text-sm text-destructive">{errors.title.message}</p>}
            </div>
            <div className="grid gap-2">
              <Label htmlFor="description">
                Description <span className="font-normal text-muted-foreground">(optional)</span>
              </Label>
              <Textarea id="description" rows={5} className="min-h-28 resize-none" {...register('description')} />
            </div>
          </div>
          <div className="grid grid-rows-[auto_1fr_auto] gap-2">
            <Label htmlFor="file">File</Label>
            <DropZone control={control} uploading={submit.isPending} invalid={!!(rejectedPick ?? errors.file)} onReject={setRejectedPick} />
            {(rejectedPick ?? errors.file) && <p className="text-sm text-destructive">{rejectedPick ?? errors.file?.message}</p>}
          </div>
        </div>
      </div>
      <div className="flex justify-end gap-2 border-t px-5 py-3">
        <Button
          type="button"
          variant="outline"
          className="h-9 px-4"
          disabled={submit.isPending}
          onClick={() => {
            reset()
            setRejectedPick(undefined)
            onCancel()
          }}
        >
          Cancel
        </Button>
        <Button type="submit" className="h-9 px-4" disabled={submit.isPending}>
          {submit.isPending && <Loader2 className="animate-spin" />}
          Submit
        </Button>
      </div>
    </form>
  )
}

export default function SubmitterPage() {
  const wide = useWide()
  const [page, setPage] = useState(0)
  // No selection means the pane holds the new-document form.
  const [selected, setSelected] = useState<Document | null>(null)
  const [open, setOpen] = useState(false)
  const documents = useQuery({ queryKey: ['documents', 'mine', page], queryFn: () => api.listDocuments(page), placeholderData: keepPreviousData })

  const items = documents.data?.items ?? []
  const total = documents.data?.total ?? 0
  const lastPage = Math.max(0, Math.ceil(total / PAGE_SIZE) - 1)
  if (page > lastPage) setPage(lastPage)

  const show = (doc: Document | null) => {
    setSelected(doc)
    setOpen(true)
  }

  return (
    <>
      <PageHeading title="My documents" subtitle="Submit documents for review and track their status.">
        <Button className="h-9 px-4" onClick={() => show(null)}>
          <Plus />
          New document
        </Button>
      </PageHeading>

      <SplitView
        title={selected?.title ?? 'New document'}
        open={open}
        onClose={() => setOpen(false)}
        detail={
          selected ? (
            <DocumentView key={selected.id} doc={selected} />
          ) : (
            <NewDocumentForm
              onCreated={(doc) => {
                setPage(0)
                show(doc)
              }}
              onCancel={() => {
                setOpen(false)
                if (wide && items[0]) setSelected(items[0])
              }}
            />
          )
        }
        list={
          <motion.section {...enter(0.15)} className="flex flex-col overflow-hidden rounded-xl border bg-card shadow-xs xl:h-full">
            <div className="min-h-0 flex-1 overflow-y-auto">
              <Table className="table-fixed">
                <TableHeader className="bg-muted/50">
                  <TableRow className="hover:bg-transparent">
                    <TableHead className="h-10 px-4 text-xs text-muted-foreground">Document</TableHead>
                    <TableHead className="h-10 w-32 px-4 text-right text-xs text-muted-foreground">Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.length === 0 && <TablePlaceholder columns={2} loading={documents.isPending} icon={FileStack} message="No documents yet. Your submissions will appear here." />}
                  <AnimatePresence>
                    {items.map((doc, index) => (
                      <DocumentRow key={doc.id} doc={doc} index={index} selected={wide && selected?.id === doc.id} onOpen={() => show(doc)} />
                    ))}
                  </AnimatePresence>
                </TableBody>
              </Table>
            </div>
            <Pagination page={page} total={total} onChange={setPage} />
          </motion.section>
        }
      />
    </>
  )
}
