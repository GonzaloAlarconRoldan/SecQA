import { ChevronLeft, ChevronRight, Download, ExternalLink, FileText, ImageOff, Trash2, Upload, X } from "lucide-react";
import { useEffect, useRef, useState, type ClipboardEvent, type DragEvent } from "react";
import { useAttachmentBlob, useDeleteAttachment } from "../api/hooks";
import type { Attachment, AttachmentUpload } from "../api/types";
import { fmtBytes, fmtRelative } from "../lib/format";
import { usePrefs } from "../lib/prefs";
import { useToast } from "../lib/toast";
import { cx, Skeleton } from "./ui";

const isImage = (a: Attachment) => a.content_type.startsWith("image/");

/** Object URL for an authenticated blob; revoked when the blob changes or the component unmounts. */
function useObjectUrl(blob: Blob | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!blob) return;
    const u = URL.createObjectURL(blob);
    setUrl(u);
    return () => {
      URL.revokeObjectURL(u);
      setUrl(null);
    };
  }, [blob]);
  return url;
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function AuthImage({ attachment, className }: { attachment: Attachment; className?: string }) {
  const { t } = usePrefs();
  const { data, isLoading, error } = useAttachmentBlob(attachment);
  const url = useObjectUrl(data);
  if (isLoading) return <Skeleton className={cx("h-full w-full", className)} />;
  if (error || !url)
    return (
      <div className={cx("muted flex h-full w-full flex-col items-center justify-center gap-1 text-xs", className)}>
        <ImageOff className="h-5 w-5" />
        {t("ev.loadError")}
      </div>
    );
  return <img src={url} alt={attachment.caption ?? attachment.filename} className={className} />;
}

function Meta({ a }: { a: Attachment }) {
  const { t, lang } = usePrefs();
  return (
    <div className="muted flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px]">
      <span className="rounded bg-slate-100 px-1.5 py-px font-medium uppercase tracking-wide dark:bg-slate-800">
        {t(`ev.kind.${a.kind}` as "ev.kind.file")}
      </span>
      {a.finding_id !== null && a.defect_id === null && <span>{t("ev.fromFinding").replace("{n}", String(a.finding_id))}</span>}
      {a.created_by && <span>{a.created_by.replace(/^human:/, "")}</span>}
      <span>{fmtRelative(a.created_at, lang)}</span>
    </div>
  );
}

function Lightbox({ items, index, onIndex, onClose }: {
  items: Attachment[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const { t } = usePrefs();
  const toast = useToast();
  const a = items[index];
  const { data } = useAttachmentBlob(a);
  const url = useObjectUrl(data);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft" && items.length > 1) onIndex((index - 1 + items.length) % items.length);
      else if (e.key === "ArrowRight" && items.length > 1) onIndex((index + 1) % items.length);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, items.length, onClose, onIndex]);

  if (!a) return null;
  return (
    <div
      className="fixed inset-0 z-[60] flex flex-col bg-slate-950/90 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label={a.caption ?? a.filename}
      onMouseDown={onClose}
    >
      <header className="flex items-center justify-between gap-3 px-4 py-3 text-slate-200" onMouseDown={(e) => e.stopPropagation()}>
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{a.caption ?? a.filename}</div>
          <div className="truncate text-xs text-slate-400">
            {a.filename} · {fmtBytes(a.size)} · {index + 1}/{items.length}
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <button
            className="btn btn-sm"
            disabled={!url}
            onClick={() => url && window.open(url, "_blank", "noopener")}
          >
            <ExternalLink className="h-3.5 w-3.5" /> {t("ev.open")}
          </button>
          <button
            className="btn btn-sm"
            disabled={!data}
            onClick={() => (data ? saveBlob(data, a.filename) : toast.error(t("ev.loadError")))}
          >
            <Download className="h-3.5 w-3.5" /> {t("ev.download")}
          </button>
          <button className="btn btn-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
      </header>
      <div className="relative flex min-h-0 flex-1 items-center justify-center px-14 pb-6">
        {items.length > 1 && (
          <button
            className="absolute left-3 rounded-full bg-slate-800/80 p-2 text-white hover:bg-slate-700"
            aria-label={t("ev.prev")}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onIndex((index - 1 + items.length) % items.length)}
          >
            <ChevronLeft className="h-5 w-5" />
          </button>
        )}
        <div onMouseDown={(e) => e.stopPropagation()} className="flex max-h-full max-w-full items-center justify-center">
          {url ? (
            <img src={url} alt={a.caption ?? a.filename} className="max-h-[calc(100vh-7rem)] max-w-full rounded shadow-2xl" />
          ) : (
            <Skeleton className="h-96 w-[48rem] max-w-full" />
          )}
        </div>
        {items.length > 1 && (
          <button
            className="absolute right-3 rounded-full bg-slate-800/80 p-2 text-white hover:bg-slate-700"
            aria-label={t("ev.next")}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => onIndex((index + 1) % items.length)}
          >
            <ChevronRight className="h-5 w-5" />
          </button>
        )}
      </div>
    </div>
  );
}

function FileRow({ a, onDelete }: { a: Attachment; onDelete: () => void }) {
  const { t } = usePrefs();
  const [want, setWant] = useState(false);
  const { data } = useAttachmentBlob(a, want);
  useEffect(() => {
    if (want && data) {
      saveBlob(data, a.filename);
      setWant(false);
    }
  }, [want, data, a.filename]);
  return (
    <li className="flex items-center gap-2 rounded-md border border-slate-200 px-2.5 py-2 text-sm dark:border-slate-800">
      <FileText className="muted h-4 w-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="truncate" title={a.filename}>{a.caption ?? a.filename}</div>
        <Meta a={a} />
      </div>
      <span className="muted shrink-0 text-xs">{fmtBytes(a.size)}</span>
      <button className="btn btn-ghost btn-sm" aria-label={`${t("ev.download")} ${a.filename}`} onClick={() => setWant(true)}>
        <Download className="h-3.5 w-3.5" />
      </button>
      <button
        className="btn btn-ghost btn-sm"
        aria-label={`${t("c.delete")} ${a.filename}`}
        onClick={() => (window.confirm(t("ev.deleteConfirm")) ? onDelete() : undefined)}
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </li>
  );
}

export function EvidenceGallery({ items, loading, onUpload, uploading, compact }: {
  items: Attachment[];
  loading?: boolean;
  onUpload?: (u: AttachmentUpload) => Promise<unknown>;
  uploading?: boolean;
  compact?: boolean;
}) {
  const { t } = usePrefs();
  const toast = useToast();
  const del = useDeleteAttachment();
  const fileRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<File[]>([]);
  const [caption, setCaption] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  const images = items.filter(isImage);
  const files = items.filter((a) => !isImage(a));

  const remove = (a: Attachment) =>
    del.mutate(a.id, { onSuccess: () => toast.success(t("ev.deleted")), onError: toast.error });

  const addFiles = (list: FileList | File[] | null | undefined) => {
    const arr = Array.from(list ?? []);
    if (arr.length) setPending((p) => [...p, ...arr]);
  };

  const onPaste = (e: ClipboardEvent<HTMLDivElement>) => {
    const pasted = Array.from(e.clipboardData.items)
      .filter((i) => i.kind === "file")
      .map((i) => i.getAsFile())
      .filter((f): f is File => !!f)
      .map((f) =>
        f.name && f.name !== "image.png"
          ? f
          : new File([f], `${t("ev.pasted")}-${new Date().toISOString().replace(/[:.]/g, "-")}.png`, { type: f.type }),
      );
    if (pasted.length) {
      e.preventDefault();
      addFiles(pasted);
    }
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    addFiles(e.dataTransfer.files);
  };

  const submit = async () => {
    if (!onUpload) return;
    try {
      for (const file of pending) {
        await onUpload({ file, caption: caption || undefined, kind: file.type.startsWith("image/") ? "screenshot" : undefined });
      }
      toast.success(t("ev.uploaded"));
      setPending([]);
      setCaption("");
    } catch (err) {
      toast.error(err);
    }
  };

  return (
    <div className="space-y-3">
      {loading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Skeleton className="aspect-video" />
          <Skeleton className="aspect-video" />
        </div>
      ) : items.length === 0 ? (
        <p className="muted text-sm">{t("ev.empty")}</p>
      ) : null}

      {images.length > 0 && (
        <ul className={cx("grid gap-3", compact ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3")}>
          {images.map((a, i) => (
            <li key={a.id} className="group overflow-hidden rounded-md border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
              <div className="relative">
                <button
                  type="button"
                  className="block aspect-video w-full overflow-hidden bg-slate-100 dark:bg-slate-800"
                  onClick={() => setOpen(i)}
                  aria-label={a.caption ?? a.filename}
                >
                  <AuthImage attachment={a} className="h-full w-full object-cover object-top transition group-hover:scale-[1.02]" />
                </button>
                <button
                  type="button"
                  className="absolute right-1.5 top-1.5 rounded bg-slate-900/70 p-1 text-white opacity-0 transition hover:bg-red-600 focus:opacity-100 group-hover:opacity-100"
                  aria-label={`${t("c.delete")} ${a.filename}`}
                  onClick={() => (window.confirm(t("ev.deleteConfirm")) ? remove(a) : undefined)}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
              <div className="space-y-1 p-2">
                <div className="line-clamp-2 text-xs font-medium" title={a.caption ?? a.filename}>
                  {a.caption ?? a.filename}
                </div>
                <Meta a={a} />
              </div>
            </li>
          ))}
        </ul>
      )}

      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((a) => (
            <FileRow key={a.id} a={a} onDelete={() => remove(a)} />
          ))}
        </ul>
      )}

      {onUpload && (
        <div
          tabIndex={0}
          onPaste={onPaste}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={cx(
            "rounded-md border border-dashed p-3 text-sm outline-none transition focus:border-indigo-400",
            dragOver ? "border-indigo-500 bg-indigo-50 dark:bg-indigo-950/30" : "border-slate-300 dark:border-slate-700",
          )}
        >
          <div className="muted flex flex-wrap items-center gap-1 text-xs">
            <Upload className="h-3.5 w-3.5" />
            {t("ev.drop")}
            <button type="button" className="font-medium text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => fileRef.current?.click()}>
              {t("ev.browse")}
            </button>
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              accept="image/*,.txt,.log,.har,.json,.pdf,.zip"
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
          {pending.length > 0 && (
            <div className="mt-2 space-y-2">
              <ul className="flex flex-wrap gap-1.5">
                {pending.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="code flex items-center gap-1">
                    {f.name} <span className="muted">({fmtBytes(f.size)})</span>
                    <button type="button" aria-label={`${t("c.delete")} ${f.name}`} onClick={() => setPending((p) => p.filter((_, j) => j !== i))}>
                      <X className="h-3 w-3" />
                    </button>
                  </li>
                ))}
              </ul>
              <div className="flex gap-2">
                <input
                  className="input flex-1"
                  value={caption}
                  maxLength={2000}
                  placeholder={t("ev.caption")}
                  aria-label={t("ev.caption")}
                  onChange={(e) => setCaption(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !uploading && void submit()}
                />
                <button type="button" className="btn btn-primary btn-sm" disabled={uploading} onClick={() => void submit()}>
                  <Upload className="h-3.5 w-3.5" /> {uploading ? t("ev.uploading") : t("ev.upload")}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {open !== null && images[open] && (
        <Lightbox items={images} index={open} onIndex={setOpen} onClose={() => setOpen(null)} />
      )}
    </div>
  );
}
