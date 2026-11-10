import { renderAsync } from 'docx-preview'
import { CircleAlert, EyeOff, Loader2 } from 'lucide-react'
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Document as PdfDocument, Page, pdfjs } from 'react-pdf'
import { api } from '@/api'
import { EmptyState } from '@/components/common'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
const PREVIEWABLE = ['application/pdf', DOCX, 'text/plain', 'image/png', 'image/jpeg']

type Loaded = { blob: Blob; url?: string; text?: string }

export function ViewerLoading() {
  return (
    <div className="flex h-72 items-center justify-center gap-2 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" />
      Loading preview…
    </div>
  )
}

const ViewerError = () => <EmptyState icon={CircleAlert}>Couldn't load the preview. Try downloading the file instead.</EmptyState>

function Toolbar({ children }: { children?: ReactNode }) {
  return (
    <div className="flex h-10 items-center justify-between border-b bg-card px-4 text-xs text-muted-foreground">
      <span className="font-medium text-foreground">Preview</span>
      {children}
    </div>
  )
}

function useWidth() {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    const observer = new ResizeObserver(([entry]) => setWidth(Math.floor(entry.contentRect.width)))
    observer.observe(ref.current!)
    return () => observer.disconnect()
  }, [])
  return [ref, width] as const
}

function PdfViewer({ blob }: { blob: Blob }) {
  const [ref, width] = useWidth()
  const [pages, setPages] = useState(0)
  return (
    <>
      <Toolbar>{pages > 0 && `${pages} ${pages === 1 ? 'page' : 'pages'}`}</Toolbar>
      <div ref={ref} className="m-4">
        <PdfDocument file={blob} onLoadSuccess={({ numPages }) => setPages(numPages)} loading={<ViewerLoading />} error={<ViewerError />}>
          {width > 0 &&
            Array.from({ length: pages }, (_, i) => (
              <Page
                key={i}
                pageNumber={i + 1}
                width={width}
                renderTextLayer={false}
                renderAnnotationLayer={false}
                loading={<div className="bg-white" style={{ height: width * 1.294 }} />}
                className="mb-4 overflow-hidden rounded-md bg-white shadow-sm ring-1 ring-black/5 last:mb-0"
              />
            ))}
        </PdfDocument>
      </div>
    </>
  )
}

function DocxViewer({ blob }: { blob: Blob }) {
  const ref = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  useEffect(() => {
    let cancelled = false
    // Render off-DOM, then swap in, so a stale render can never land in the panel.
    const target = document.createElement('div')
    renderAsync(blob, target, target, { inWrapper: false, ignoreWidth: true, ignoreHeight: true, breakPages: false }).then(
      () => {
        if (cancelled) return
        // Word bullets use Symbol/Wingdings private-use glyphs that browsers can't draw.
        target.querySelectorAll('style').forEach((style) => (style.textContent = style.textContent!.replace(/[\uF000-\uF0FF]/g, '•')))
        ref.current?.replaceChildren(target)
        setStatus('ready')
      },
      () => !cancelled && setStatus('error'),
    )
    return () => {
      cancelled = true
    }
  }, [blob])
  return (
    <>
      <Toolbar />
      {status === 'loading' && <ViewerLoading />}
      {status === 'error' && <ViewerError />}
      <div
        ref={ref}
        hidden={status !== 'ready'}
        className="m-4 overflow-x-auto rounded-md bg-white text-black shadow-sm ring-1 ring-black/5 [&_section.docx]:min-h-0! [&_section.docx]:px-10! [&_section.docx]:py-10!"
      />
    </>
  )
}

/** Previews a stored document by `id`, or a local `file` that hasn't been uploaded yet. */
export default function FileViewer({ id, file, contentType }: { id?: string; file?: Blob; contentType: string }) {
  const [state, setState] = useState<{ file?: Loaded; error?: boolean }>({})
  const previewable = PREVIEWABLE.includes(contentType)

  useEffect(() => {
    if (!previewable) return
    let cancelled = false
    let url: string | undefined
    const load = file ? Promise.resolve(file) : api.fileBlob(id!)
    load
      .then(async (blob) => {
        const text = contentType === 'text/plain' ? await blob.text() : undefined
        if (cancelled) return
        if (contentType.startsWith('image/')) url = URL.createObjectURL(blob)
        setState({ file: { blob, url, text } })
      })
      .catch(() => !cancelled && setState({ error: true }))
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [id, file, contentType, previewable])

  if (!previewable)
    return (
      <>
        <Toolbar />
        <EmptyState icon={EyeOff}>Preview not available for this file type.</EmptyState>
      </>
    )
  if (state.error)
    return (
      <>
        <Toolbar />
        <ViewerError />
      </>
    )
  if (!state.file)
    return (
      <>
        <Toolbar />
        <ViewerLoading />
      </>
    )

  const { blob, url, text } = state.file
  if (contentType === 'application/pdf') return <PdfViewer blob={blob} />
  if (contentType === DOCX) return <DocxViewer blob={blob} />
  if (url)
    return (
      <>
        <Toolbar />
        <div className="grid place-items-center bg-[repeating-conic-gradient(var(--muted)_0_25%,transparent_0_50%)] bg-size-[16px_16px] p-4">
          <img src={url} alt="" className="max-h-[70vh] max-w-full rounded-md object-contain shadow-sm ring-1 ring-black/5" />
        </div>
      </>
    )
  return (
    <>
      <Toolbar />
      <pre className="max-h-[70vh] overflow-y-auto bg-card p-5 font-mono text-[13px] leading-relaxed break-words whitespace-pre-wrap">{text}</pre>
    </>
  )
}
