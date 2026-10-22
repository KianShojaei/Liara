const fa = new Intl.NumberFormat('fa-IR')

export const toman = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : `${fa.format(Number(n.toFixed(digits)))} تومان`

export const num = (n: number | null | undefined, digits = 1) => (n == null ? '—' : fa.format(Number(n.toFixed(digits))))

export const mb = (bytes: number | null | undefined) => (bytes == null ? '—' : `${fa.format(Math.round(bytes / 1024 / 1024))} MB`)

export const time = (iso: string | number) => {
  const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso)
  return isNaN(d.getTime()) ? String(iso) : d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export const signed = (n: number) => (n > 0 ? '+' : '') + fa.format(Math.round(n))

export const REVERSIBILITY: Record<string, string> = { reversible: 'قابل بازگشت', partial: 'تا حدی قابل بازگشت', irreversible: 'غیرقابل بازگشت' }
export const DOWNTIME: Record<string, string> = { none: 'بدون قطعی', brief: 'قطعی چند ثانیه‌ای', yes: 'قطعی سرویس' }
export const RISK: Record<string, string> = { low: 'ریسک کم', medium: 'ریسک متوسط', high: 'ریسک زیاد' }
export const PROPOSAL_STATUS: Record<string, { label: string; cls: string }> = {
  pending_approval: { label: 'منتظر تأیید شما', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200' },
  approved: { label: 'تأیید شد', cls: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200' },
  running: { label: 'در حال اجرا', cls: 'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200' },
  executed: { label: 'اجرا شد؛ در حال بررسی', cls: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200' },
  verified: { label: 'اجرا و تأیید شد', cls: 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200' },
  verification_failed: { label: 'اجرا شد ولی بررسی ناموفق', cls: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200' },
  failed: { label: 'ناموفق', cls: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200' },
  rejected: { label: 'رد شد', cls: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
  blocked: { label: 'مسدود شد', cls: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200' },
}
export const TIER: Record<string, { label: string; cls: string }> = {
  T0: { label: 'خواندنی', cls: 'bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-200' },
  T1: { label: 'کم‌ریسک', cls: 'bg-sky-100 text-sky-800 dark:bg-sky-900/40 dark:text-sky-200' },
  T2: { label: 'نیازمند تأیید', cls: 'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200' },
  T3: { label: 'محافظت‌شده', cls: 'bg-rose-100 text-rose-800 dark:bg-rose-900/40 dark:text-rose-200' },
}
export const STEP_NAMES: Record<string, string> = {
  create_app: 'ساخت برنامه',
  set_env: 'ثبت متغیرهای محیطی',
  liara_json: 'نوشتن liara.json',
  deploy: 'دیپلوی',
  verify: 'بررسی سلامت',
}
export const CHECK_NAMES: Record<string, string> = {
  release: 'انتشار نسخه',
  container: 'کانتینر',
  http: 'پاسخ HTTP',
  logs: 'لاگ‌ها',
  app_exists: 'وجود برنامه',
  plan: 'پلن',
  scale: 'وضعیت روشن/خاموش',
  dns: 'DNS',
  ssl: 'گواهی SSL',
  https: 'HTTPS',
}
