import { AlertTriangle, ChevronLeft, ChevronRight, Inbox, X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import type { Severity } from "../api/types";
import { PRIORITY_TONE, SEVERITY_CLASS, STATUS_TONE, toneClass, type Tone } from "../lib/colors";
import { usePrefs } from "../lib/prefs";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="page-title">{title}</h1>
        {subtitle && <p className="muted mt-0.5 text-sm">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const { te } = usePrefs();
  return <span className={cx("pill", SEVERITY_CLASS[severity])}>{te(severity)}</span>;
}

export function Pill({ value, tone }: { value: string | null | undefined; tone?: Tone }) {
  const { te } = usePrefs();
  if (!value) return <span className="muted">—</span>;
  return <span className={cx("pill", toneClass(tone ?? STATUS_TONE[value] ?? "slate"))}>{te(value)}</span>;
}

export function PriorityPill({ value }: { value: string }) {
  return <span className={cx("pill font-mono", toneClass(PRIORITY_TONE[value] ?? "slate"))}>{value}</span>;
}

export function Card({ title, actions, children, className, bodyClass }: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={cx("card", className)}>
      {title && (
        <header className="card-h">
          <span>{title}</span>
          {actions}
        </header>
      )}
      <div className={bodyClass ?? "p-4"}>{children}</div>
    </section>
  );
}

export function Empty({ message, children }: { message?: string; children?: ReactNode }) {
  const { t } = usePrefs();
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-4 py-10 text-center">
      <Inbox className="h-8 w-8 text-slate-300 dark:text-slate-600" />
      <p className="muted text-sm">{message ?? t("c.empty")}</p>
      {children}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const { t } = usePrefs();
  return (
    <div className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
      <div>
        <b>{t("c.error")}</b>
        <div>{error instanceof Error ? error.message : String(error)}</div>
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className ?? "h-4 w-full")} />;
}

export function TableSkeleton({ rows = 6, cols = 5 }: { rows?: number; cols?: number }) {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex gap-3">
          {Array.from({ length: cols }, (_, j) => (
            <Skeleton key={j} className={cx("h-4", j === 1 ? "flex-3" : "flex-1")} />
          ))}
        </div>
      ))}
    </div>
  );
}

function useEscape(onClose: () => void, open: boolean) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, open]);
}

export function Modal({ open, onClose, title, children, footer, wide }: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  useEscape(onClose, open);
  const titleId = useId();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open) ref.current?.querySelector<HTMLElement>("input,select,textarea,button")?.focus();
  }, [open]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-950/50 p-4 pt-[10vh] backdrop-blur-xs" onMouseDown={onClose}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cx("card w-full shadow-2xl", wide ? "max-w-3xl" : "max-w-lg")}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="card-h">
          <span id={titleId}>{title}</span>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        {footer && (
          <footer className="flex justify-end gap-2 border-t border-slate-200 px-4 py-3 dark:border-slate-800">{footer}</footer>
        )}
      </div>
    </div>
  );
}

export function Drawer({ open, onClose, title, children, footer }: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
}) {
  useEscape(onClose, open);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-slate-950/40" onMouseDown={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        className="flex h-full w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-2xl dark:border-slate-800 dark:bg-slate-900"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="flex items-start justify-between gap-3 border-b border-slate-200 px-5 py-3 dark:border-slate-800">
          <div className="min-w-0 flex-1 text-sm font-semibold">{title}</div>
          <button className="btn btn-ghost btn-sm" onClick={onClose} aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </header>
        <div className="flex-1 overflow-y-auto p-5">{children}</div>
        {footer && <footer className="flex flex-wrap gap-2 border-t border-slate-200 px-5 py-3 dark:border-slate-800">{footer}</footer>}
      </aside>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: {
  tabs: { id: T; label: ReactNode }[];
  value: T;
  onChange: (id: T) => void;
}) {
  return (
    <div role="tablist" className="mb-4 flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          role="tab"
          aria-selected={tab.id === value}
          onClick={() => onChange(tab.id)}
          className={cx(
            "-mb-px whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition",
            tab.id === value
              ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function Pagination({ total, limit, offset, onChange }: {
  total: number;
  limit: number;
  offset: number;
  onChange: (offset: number) => void;
}) {
  const { t } = usePrefs();
  if (total <= limit) return null;
  const from = offset + 1;
  const to = Math.min(offset + limit, total);
  return (
    <div className="flex items-center justify-between border-t border-slate-200 px-4 py-2 text-sm dark:border-slate-800">
      <span className="muted tabular-nums">
        {from}–{to} {t("c.of")} {total}
      </span>
      <div className="flex gap-1">
        <button className="btn btn-sm" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>
          <ChevronLeft className="h-3.5 w-3.5" /> {t("c.prev")}
        </button>
        <button className="btn btn-sm" disabled={to >= total} onClick={() => onChange(offset + limit)}>
          {t("c.next")} <ChevronRight className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="muted mt-1 block text-xs">{hint}</span>}
    </label>
  );
}

export function EnumSelect<T extends string>({ value, options, onChange, allLabel, className, ariaLabel }: {
  value: T | "";
  options: readonly T[];
  onChange: (v: T | "") => void;
  allLabel?: string;
  className?: string;
  ariaLabel?: string;
}) {
  const { te } = usePrefs();
  return (
    <select aria-label={ariaLabel} className={cx("input", className)} value={value} onChange={(e) => onChange(e.target.value as T | "")}>
      {allLabel !== undefined && <option value="">{allLabel}</option>}
      {options.map((o) => (
        <option key={o} value={o}>
          {te(o)}
        </option>
      ))}
    </select>
  );
}

/** Toggle chips for multi-select filters (e.g. severities). */
export function ChipToggle<T extends string>({ options, value, onChange, render }: {
  options: readonly T[];
  value: T[];
  onChange: (v: T[]) => void;
  render?: (o: T) => ReactNode;
}) {
  const { te } = usePrefs();
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((o) => {
        const on = value.includes(o);
        return (
          <button
            key={o}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(on ? value.filter((v) => v !== o) : [...value, o])}
            className={cx(
              "rounded-full border px-2.5 py-0.5 text-xs font-medium transition",
              on
                ? "border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300"
                : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800",
            )}
          >
            {render ? render(o) : te(o)}
          </button>
        );
      })}
    </div>
  );
}

export function Kpi({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: "danger" | "warn" | "ok" }) {
  return (
    <div className="card px-4 py-3">
      <div className="muted text-xs font-medium uppercase tracking-wide">{label}</div>
      <div
        className={cx(
          "mt-1 text-2xl font-semibold tabular-nums",
          tone === "danger" && "text-red-600 dark:text-red-400",
          tone === "warn" && "text-amber-600 dark:text-amber-400",
          tone === "ok" && "text-emerald-600 dark:text-emerald-400",
        )}
      >
        {value}
      </div>
      {hint && <div className="muted mt-0.5 text-xs">{hint}</div>}
    </div>
  );
}

/** Small stacked bar showing counts per severity. */
export function SeverityBar({ counts }: { counts: Partial<Record<Severity, number>> }) {
  const order: Severity[] = ["critical", "high", "medium", "low", "info"];
  const total = order.reduce((s, k) => s + (counts[k] ?? 0), 0);
  if (!total) return <span className="muted text-xs">0</span>;
  return (
    <div className="flex items-center gap-2" title={order.map((k) => `${k}: ${counts[k] ?? 0}`).join(" · ")}>
      <div className="flex h-2 w-24 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
        {order.map((k) =>
          counts[k] ? (
            <div key={k} className={SEVERITY_CLASS[k].split(" ")[0]} style={{ width: `${((counts[k] ?? 0) / total) * 100}%` }} />
          ) : null,
        )}
      </div>
      <span className="text-xs tabular-nums">{total}</span>
    </div>
  );
}

/** Tool-provided text: always rendered as plain text, never HTML. */
// Minimal, injection-proof markdown: only ``` blocks, `code` and **bold**, built as React nodes
// (never innerHTML), so tool-provided text can't smuggle markup into the page.
function inlineMd(chunk: string, keyBase: string): ReactNode[] {
  return chunk.split(/(`[^`\n]+`|\*\*[^*]+\*\*)/g).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return <code key={key} className="rounded-sm bg-slate-100 px-1 font-mono text-[0.85em] dark:bg-slate-800">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={key}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

export function MiniMarkdown({ text }: { text: string }) {
  const nodes: ReactNode[] = [];
  const fence = /```[^\n]*\n([\s\S]*?)```/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = fence.exec(text))) {
    nodes.push(...inlineMd(text.slice(last, m.index).replace(/^\n+|\n+$/g, ""), `t${last}`));
    nodes.push(<pre key={`f${m.index}`} className="pre my-2">{m[1].replace(/\n$/, "")}</pre>);
    last = m.index + m[0].length;
  }
  nodes.push(...inlineMd(text.slice(last).replace(/^\n+/, ""), `t${last}`));
  return <div className="whitespace-pre-wrap wrap-break-word text-sm">{nodes}</div>;
}

export function PlainText({ text, mono }: { text: string | null | undefined; mono?: boolean }) {
  if (!text) return <span className="muted">—</span>;
  return mono ? <pre className="pre">{text}</pre> : <MiniMarkdown text={text} />;
}
