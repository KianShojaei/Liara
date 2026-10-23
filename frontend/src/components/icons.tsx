import type { SVGProps } from 'react'

/** Inline line icons (lucide-style: 24px viewBox, 1.5px stroke, currentColor). */
export interface IconProps extends Omit<SVGProps<SVGSVGElement>, 'size'> {
  size?: number
  className?: string
}

function make(name: string, paths: string[]) {
  const Icon = ({ size = 16, className = '', ...rest }: IconProps) => (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      focusable="false"
      className={`inline-block shrink-0 align-[-0.15em] ${className}`}
      data-icon={name}
      {...rest}
    >
      {paths.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  )
  Icon.displayName = `Icon${name}`
  return Icon
}

export const ChatIcon = make('chat', ['M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'])
export const PackageIcon = make('package', ['m7.5 4.27 9 5.15', 'M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z', 'm3.3 7 8.7 5 8.7-5', 'M12 22V12'])
export const AlertIcon = make('alert', ['M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z', 'M12 9v4', 'M12 17h.01'])
export const SirenIcon = make('siren', ['M7 18v-6a5 5 0 1 1 10 0v6', 'M5 21a1 1 0 0 1-1-1v-1a1 1 0 0 1 1-1h14a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1z', 'M21 12h1', 'M18.5 4.5 18 5', 'M2 12h1', 'M12 2v1', 'm4.93 4.93.5.5', 'M12 12v6'])
export const BookIcon = make('book', ['M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20'])
export const HandIcon = make('hand', ['M18 11V6a2 2 0 0 0-4 0v5', 'M14 10V4a2 2 0 0 0-4 0v2', 'M10 10.5V6a2 2 0 0 0-4 0v8', 'M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15'])
export const ShieldIcon = make('shield', ['M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z'])
export const CompassIcon = make('compass', ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'm16.24 7.76-2.12 6.36-6.36 2.12 2.12-6.36z'])
export const RocketIcon = make('rocket', ['M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z', 'm12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z', 'M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0', 'M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5'])
export const LockIcon = make('lock', ['M5 11h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2z', 'M7 11V7a5 5 0 0 1 10 0v4'])
export const ChartIcon = make('chart', ['M3 3v16a2 2 0 0 0 2 2h16', 'm19 9-5 5-4-4-3 3'])
export const BrainIcon = make('brain', ['M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z', 'M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z', 'M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4', 'M17.599 6.5a3 3 0 0 0 .399-1.375', 'M6.003 5.125A3 3 0 0 0 6.401 6.5', 'M3.477 10.896a4 4 0 0 1 .585-.396', 'M19.938 10.5a4 4 0 0 1 .585.396', 'M6 18a4 4 0 0 1-1.967-.516', 'M19.967 17.484A4 4 0 0 1 18 18'])
export const WrenchIcon = make('wrench', ['M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z'])
export const ReceiptIcon = make('receipt', ['M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1z', 'M16 8h-6a2 2 0 1 0 0 4h4a2 2 0 1 1 0 4H8', 'M12 17.5v-11'])
export const FileTextIcon = make('file-text', ['M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7z', 'M14 2v4a2 2 0 0 0 2 2h4', 'M10 9H8', 'M16 13H8', 'M16 17H8'])
export const PuzzleIcon = make('puzzle', ['M19.4 12.8a1 1 0 0 0-.9-.6 2.2 2.2 0 1 1 0-4.4 1 1 0 0 0 .9-.6l.1-.3V4a1 1 0 0 0-1-1h-3.7a.8.8 0 0 1-.7-1 2.2 2.2 0 1 0-4.4 0 .8.8 0 0 1-.7 1H5a1 1 0 0 0-1 1v3.7a.8.8 0 0 0 1 .7 2.2 2.2 0 1 1 0 4.4.8.8 0 0 0-1 .7V20a1 1 0 0 0 1 1h3.7a.8.8 0 0 0 .7-1 2.2 2.2 0 1 1 4.4 0 .8.8 0 0 0 .7 1H19a1 1 0 0 0 1-1v-3.7a1 1 0 0 0-.6-.5z'])
export const RefreshIcon = make('refresh', ['M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8', 'M21 3v5h-5', 'M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16', 'M8 16H3v5'])
export const SearchIcon = make('search', ['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'm21 21-4.3-4.3'])
export const CreditCardIcon = make('credit-card', ['M2 7a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z', 'M2 10h20'])
export const FolderIcon = make('folder', ['M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z'])
export const LinkIcon = make('link', ['M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71', 'M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71'])
export const MonitorIcon = make('monitor', ['M4 3h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z', 'M8 21h8', 'M12 17v4'])
export const UserIcon = make('user', ['M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2', 'M12 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z'])
export const BotIcon = make('bot', ['M12 8V4H8', 'M4 8h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2z', 'M2 14h2', 'M20 14h2', 'M15 13v2', 'M9 13v2'])
export const InfoIcon = make('info', ['M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20z', 'M12 16v-4', 'M12 8h.01'])
export const CheckIcon = make('check', ['M20 6 9 17l-5-5'])
export const CheckCircleIcon = make('check-circle', ['M22 11.08V12a10 10 0 1 1-5.93-9.14', 'M22 4 12 14.01l-3-3'])
export const XIcon = make('x', ['M18 6 6 18', 'm6 6 12 12'])
export const PauseIcon = make('pause', ['M6 4h4v16H6z', 'M14 4h4v16h-4z'])
export const EyeIcon = make('eye', ['M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z', 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z'])
export const ArrowLeftIcon = make('arrow-left', ['m12 19-7-7 7-7', 'M19 12H5'])
export const UndoIcon = make('undo', ['M3 7v6h6', 'M21 17a9 9 0 0 0-9-9 9 9 0 0 0-6 2.3L3 13'])
export const MoonIcon = make('moon', ['M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z'])
export const SunIcon = make('sun', ['M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M12 2v2', 'M12 20v2', 'm4.93 4.93 1.41 1.41', 'm17.66 17.66 1.41 1.41', 'M2 12h2', 'M20 12h2', 'm6.34 17.66-1.41 1.41', 'm19.07 4.93-1.41 1.41'])
export const ListIcon = make('list', ['M8 6h13', 'M8 12h13', 'M8 18h13', 'M3 6h.01', 'M3 12h.01', 'M3 18h.01'])
export const PlusIcon = make('plus', ['M5 12h14', 'M12 5v14'])
export const CopyIcon = make('copy', ['M8 8h12v12H8z', 'M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2'])
