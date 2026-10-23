import { AlertIcon, FolderIcon, LinkIcon, MonitorIcon, PackageIcon, RocketIcon } from './icons'
import { useCallback, useEffect, useRef, useState, type DragEvent, type ReactNode } from 'react'
import { api, uploadProject } from '../api'
import { PLATFORM, bytesLabel } from '../format'
import type { Project } from '../types'
import { Button, Card, Chip, Empty, Expander, Ltr, Progress, Skeleton } from './ui'

const MAX_BYTES = 250 * 1024 * 1024
const slugify = (s: string) => s.toLowerCase().replace(/\.(zip|tar\.gz|tgz|git)$/i, '').replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 30)

type Tab = 'upload' | 'git' | 'local'

/** Intake: archive drop zone, Git URL or local folder. On success hands the project to `onReady`. */
export function IntakePanel({ onReady, compact = false }: { onReady: (p: Project) => void; compact?: boolean }) {
  const [tab, setTab] = useState<Tab>('upload')
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [gitUrl, setGitUrl] = useState('')
  const [branch, setBranch] = useState('')
  const [local, setLocal] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const run = async (fn: () => Promise<Project>) => {
    setBusy(true)
    setError(null)
    try {
      onReady(await fn())
    } catch (e) {
      setError(String((e as Error).message))
    } finally {
      setBusy(false)
      setProgress(null)
    }
  }

  const handleFile = (file: File | undefined) => {
    if (!file) return
    if (!/\.(zip|tar\.gz|tgz)$/i.test(file.name)) return setError('فقط فایل .zip یا .tar.gz')
    if (file.size > MAX_BYTES) return setError('حجم فایل بیشتر از ۲۵۰ مگابایت است')
    setProgress(0)
    run(() => uploadProject(file, slugify(file.name), setProgress))
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault()
    setDrag(false)
    handleFile(e.dataTransfer.files?.[0])
  }

  const tabs: { id: Tab; label: string; icon: ReactNode }[] = [
    { id: 'upload', label: 'آپلود فایل', icon: <FolderIcon size={14} /> },
    { id: 'git', label: 'از Git', icon: <LinkIcon size={14} /> },
    { id: 'local', label: 'پوشه‌ی محلی', icon: <MonitorIcon size={14} /> },
  ]

  return (
    <div className={compact ? '' : 'card'}>
      <div className="mb-3 flex gap-1 rounded-xl bg-raised/60 p-1" role="tablist">
        {tabs.map((t) => (
          <button key={t.id} role="tab" aria-selected={tab === t.id} onClick={() => { setTab(t.id); setError(null) }} className={`flex-1 rounded-lg px-2 py-1.5 text-xs font-medium transition-colors ${tab === t.id ? 'bg-surface text-ink shadow-sm' : 'text-muted hover:text-ink'}`}>
            <span aria-hidden className="ml-1">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'upload' && (
        <div
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
          onClick={() => !busy && fileRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && fileRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center transition-colors ${drag ? 'border-emerald-500 bg-emerald-500/10' : 'border-line hover:border-emerald-500/60 hover:bg-raised/40'}`}
        >
          <input ref={fileRef} type="file" accept=".zip,.tar.gz,.tgz" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} />
          <span className="text-muted/80" aria-hidden><PackageIcon size={36} /></span>
          <div className="text-sm font-medium">فایل پروژه را اینجا رها کنید یا کلیک کنید</div>
          <div className="text-xs text-muted">zip یا tar.gz · تا ۲۵۰ مگابایت · پوشه‌ی node_modules و .env لازم نیست</div>
          {progress != null && (
            <div className="mt-2 w-full max-w-xs">
              <Progress value={progress} tone="info" />
              <div className="mt-1 text-[11px] text-muted">{progress < 1 ? `در حال آپلود… ${Math.round(progress * 100)}٪` : 'در حال بررسی پروژه…'}</div>
            </div>
          )}
        </div>
      )}

      {tab === 'git' && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (gitUrl.trim()) run(() => api.importGit(gitUrl.trim(), branch.trim(), slugify(gitUrl.split('/').pop() ?? ''))) }}>
          <label className="block text-xs text-muted">
            آدرس مخزن (عمومی یا با SSH key)
            <input className="input mono mt-1" dir="ltr" placeholder="https://github.com/user/repo.git" value={gitUrl} onChange={(e) => setGitUrl(e.target.value)} required />
          </label>
          <label className="block text-xs text-muted">
            شاخه (اختیاری)
            <input className="input mono mt-1" dir="ltr" placeholder="main" value={branch} onChange={(e) => setBranch(e.target.value)} />
          </label>
          <Button variant="primary" type="submit" loading={busy} disabled={!gitUrl.trim()}>
            دریافت از Git
          </Button>
        </form>
      )}

      {tab === 'local' && (
        <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (local.trim()) run(() => api.registerLocal(local.trim())) }}>
          <label className="block text-xs text-muted">
            مسیر پوشه‌ی پروژه روی همین دستگاه
            <input className="input mono mt-1" dir="ltr" placeholder="./demo/shop-demo یا C:\projects\my-site" value={local} onChange={(e) => setLocal(e.target.value)} required />
          </label>
          <Button variant="primary" type="submit" loading={busy} disabled={!local.trim()}>
            بررسی پوشه
          </Button>
        </form>
      )}

      {error && <div className="mt-3 rounded-xl border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-300">{error}</div>}
    </div>
  )
}

/** Analysed project + app name + «شروع دیپلوی». */
export function ProjectCard({ project, onDeploy, onDelete }: { project: Project; onDeploy: (path: string, app: string) => Promise<void> | void; onDelete?: () => void }) {
  const a = project.analysis
  const [app, setApp] = useState(slugify(project.name))
  const [busy, setBusy] = useState(false)
  const valid = /^[a-z0-9][a-z0-9-]{1,29}$/.test(app)
  return (
    <Card title={project.name} icon={<PackageIcon size={18} />} tone="accent" meta={a.error ? <Chip tone="danger">خطا در بررسی</Chip> : <Chip tone="success">آماده‌ی دیپلوی</Chip>}>
      {a.error ? (
        <p className="text-sm text-rose-400">{a.error}</p>
      ) : (
        <>
          <div className="flex flex-wrap gap-1.5">
            <Chip tone="info">پلتفرم: {PLATFORM[a.platform] ?? a.platform}</Chip>
            <Chip>پورت: <Ltr>{a.port}</Ltr></Chip>
            <Chip>مسیر سلامت: <Ltr>{a.health_path}</Ltr></Chip>
            {a.databases.map((d) => (
              <Chip key={d} tone="violet">دیتابیس: {d}</Chip>
            ))}
            {a.env_keys.length > 0 && <Chip tone="warning">{a.env_keys.length} متغیر محیطی</Chip>}
            {a.has_dockerfile && <Chip>Dockerfile</Chip>}
          </div>
          {a.env_keys.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {a.env_keys.map((k) => (
                <Ltr key={k} className="rounded-md bg-raised px-1.5 text-[11px]">{k}</Ltr>
              ))}
            </div>
          )}
          {a.warnings.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-xs text-amber-400">
              {a.warnings.map((w) => (
                <li key={w} className="flex items-start gap-1"><AlertIcon size={13} className="mt-1 shrink-0 text-amber-400" /> <span>{w}</span></li>
              ))}
            </ul>
          )}
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <label className="min-w-[12rem] flex-1 text-xs text-muted">
              نام برنامه در لیارا
              <input className={`input mono mt-1 ${!valid ? 'border-rose-500/60' : ''}`} dir="ltr" value={app} onChange={(e) => setApp(e.target.value.toLowerCase())} />
            </label>
            <Button variant="primary" loading={busy} disabled={!valid} onClick={async () => { setBusy(true); try { await onDeploy(project.path, app) } finally { setBusy(false) } }}>
              <RocketIcon size={14} /> شروع دیپلوی
            </Button>
            {onDelete && (
              <Button variant="ghost" onClick={onDelete} title="حذف از لیست پروژه‌ها">
                حذف
              </Button>
            )}
          </div>
          {!valid && <div className="mt-1 text-[11px] text-rose-400">فقط حروف کوچک انگلیسی، عدد و خط تیره؛ ۲ تا ۳۰ کاراکتر.</div>}
          <Expander label="مسیر پروژه">
            <Ltr className="text-xs text-muted">{project.path}</Ltr>
          </Expander>
        </>
      )}
    </Card>
  )
}

export function ProjectsView({ onDeploy }: { onDeploy: (path: string, app: string) => Promise<void> | void }) {
  const [items, setItems] = useState<Project[] | null>(null)
  const [fresh, setFresh] = useState<Project | null>(null)
  const load = useCallback(() => api.projects().then(setItems).catch(() => setItems([])), [])
  useEffect(() => {
    load()
  }, [load])

  const remove = async (name: string) => {
    await api.deleteProject(name)
    if (fresh?.name === name) setFresh(null)
    load()
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h2 className="text-base font-semibold">پروژه‌ها</h2>
        <p className="text-sm text-muted">پروژه را وارد کنید؛ دستیار آن را بررسی می‌کند، پلن پیشنهاد می‌دهد و با تأیید شما دیپلوی می‌کند.</p>
      </div>
      <IntakePanel onReady={(p) => { setFresh(p); load() }} />
      {fresh && <ProjectCard project={fresh} onDeploy={onDeploy} onDelete={() => remove(fresh.name)} />}
      <div>
        <h3 className="mb-2 text-sm font-semibold text-muted">پروژه‌های وارد شده</h3>
        {items == null && <Skeleton className="h-16" />}
        {items && items.length === 0 && <Empty icon={<FolderIcon size={22} />} title="هنوز پروژه‌ای وارد نشده" hint="یک فایل zip رها کنید یا آدرس Git را وارد کنید." />}
        <div className="space-y-3">
          {items?.filter((p) => p.name !== fresh?.name).map((p) => (
            <ProjectCard key={p.name} project={p} onDeploy={onDeploy} onDelete={() => remove(p.name)} />
          ))}
        </div>
      </div>
    </div>
  )
}

export { bytesLabel }
