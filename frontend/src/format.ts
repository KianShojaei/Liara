const fa = new Intl.NumberFormat('fa-IR')

export const toman = (n: number | null | undefined, digits = 0) =>
  n == null ? '—' : `${fa.format(Number(n.toFixed(digits)))} تومان`

export const num = (n: number | null | undefined, digits = 1) => (n == null ? '—' : fa.format(Number(n.toFixed(digits))))

export const mb = (bytes: number | null | undefined) => (bytes == null ? '—' : `${fa.format(Math.round(bytes / 1024 / 1024))} MB`)

export const bytesLabel = (b: number) => (b < 1024 * 1024 ? `${fa.format(Math.round(b / 1024))} KB` : `${fa.format(Number((b / 1024 / 1024).toFixed(1)))} MB`)

export const pct = (v: number | null | undefined) => (v == null ? '—' : `${fa.format(Math.round(v * 100))}٪`)

export const time = (iso: string | number) => {
  const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso)
  return isNaN(d.getTime()) ? String(iso) : d.toLocaleTimeString('fa-IR', { hour: '2-digit', minute: '2-digit' })
}

export const dateTime = (iso: string | number) => {
  const d = typeof iso === 'number' ? new Date(iso * 1000) : new Date(iso)
  return isNaN(d.getTime()) ? String(iso) : d.toLocaleString('fa-IR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export const signed = (n: number) => (n > 0 ? '+' : '') + fa.format(Math.round(n))

export type Tone = 'neutral' | 'outline' | 'success' | 'warning' | 'danger' | 'info' | 'violet'

export const REVERSIBILITY: Record<string, string> = { reversible: 'قابل بازگشت', partial: 'تا حدی قابل بازگشت', irreversible: 'غیرقابل بازگشت' }
export const DOWNTIME: Record<string, string> = { none: 'بدون قطعی', brief: 'قطعی چند ثانیه‌ای', yes: 'قطعی سرویس' }
export const RISK: Record<string, string> = { low: 'ریسک کم', medium: 'ریسک متوسط', high: 'ریسک زیاد' }
export const RISK_TONE: Record<string, Tone> = { low: 'success', medium: 'warning', high: 'danger' }

export const PROPOSAL_STATUS: Record<string, { label: string; tone: Tone }> = {
  pending_approval: { label: 'منتظر تأیید شما', tone: 'warning' },
  approved: { label: 'تأیید شد', tone: 'info' },
  running: { label: 'در حال اجرا', tone: 'info' },
  executed: { label: 'اجرا شد؛ در حال بررسی', tone: 'violet' },
  verified: { label: 'اجرا و تأیید شد', tone: 'success' },
  verification_failed: { label: 'اجرا شد ولی بررسی ناموفق', tone: 'danger' },
  failed: { label: 'ناموفق', tone: 'danger' },
  rejected: { label: 'رد شد', tone: 'neutral' },
  blocked: { label: 'مسدود شد', tone: 'danger' },
}
export const TIER: Record<string, { label: string; tone: Tone }> = {
  T0: { label: 'خواندنی', tone: 'neutral' },
  T1: { label: 'کم‌ریسک', tone: 'info' },
  T2: { label: 'نیازمند تأیید', tone: 'warning' },
  T3: { label: 'محافظت‌شده', tone: 'danger' },
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
export const PLATFORM: Record<string, string> = { node: 'Node.js', next: 'Next.js', react: 'React (استاتیک)', vue: 'Vue', angular: 'Angular', django: 'Django', flask: 'Flask', python: 'Python', laravel: 'Laravel', php: 'PHP', dotnet: '.NET', go: 'Go', docker: 'Docker', static: 'سایت استاتیک', wordpress: 'WordPress' }
export const ACTOR: Record<string, string> = { agent: 'دستیار', human: 'شما', system: 'سیستم', verifier: 'بررسی‌کننده', investigator: 'تحلیل‌گر', watcher: 'پایشگر', cli: 'خط فرمان' }
export const ACTION: Record<string, string> = { propose: 'پیشنهاد', approve: 'تأیید', reject: 'رد', execute: 'اجرا', verify: 'بررسی', run: 'اجرای خودکار', investigate: 'تحلیل', manual_step_done: 'مرحله‌ی دستی', close_incident: 'بستن رخداد' }

/** Backend check details are terse English; translate the known shapes for the user. */
export function checkDetail(detail: string | undefined | null): string {
  if (!detail) return ''
  const d = String(detail)
  const RELEASE: Record<string, string> = { READY: 'آماده', BUILDING: 'در حال ساخت', DEPLOYING: 'در حال استقرار', FAILED: 'ناموفق', UNHEALTHY: 'ناسالم', PUSHING: 'در حال ارسال', PUSHED: 'ارسال شد' }
  let m: RegExpMatchArray | null
  if ((m = d.match(/^release state (\w+)$/))) return `وضعیت انتشار: ${RELEASE[m[1]] ?? m[1]}`
  if ((m = d.match(/^timed out after (\d+)s in state (\w+)/))) return `بعد از ${fa.format(+m[1])} ثانیه در وضعیت ${RELEASE[m[2]] ?? m[2]} ماند`
  if ((m = d.match(/^(\d+) running(?:, (.+))?$/))) return `${fa.format(+m[1])} نمونه در حال اجرا${m[2] ? ` · ${m[2]}` : ''}`
  if ((m = d.match(/^(\d+)% OK, p50 (\S+) ms$/))) return `${fa.format(+m[1])}٪ پاسخ موفق · میانه ${fa.format(Number(m[2]))} ms`
  if ((m = d.match(/^(\d+) error lines of (\d+) in the last (\d+)s$/))) return `${fa.format(+m[1])} خط خطا از ${fa.format(+m[2])} خط در ${fa.format(+m[3])} ثانیه‌ی اخیر`
  if ((m = d.match(/^scale=(\d+)$/))) return m[1] === '0' ? 'خاموش' : 'روشن'
  if ((m = d.match(/^status (\w+)$/))) return `وضعیت: ${m[1]}`
  if ((m = d.match(/^certificates (\w+)$/))) return `گواهی: ${m[1]}`
  return d
}
