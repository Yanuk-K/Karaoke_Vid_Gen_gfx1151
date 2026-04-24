import {
  CheckCircle,
  Loader2,
  Clock,
  XCircle,
} from 'lucide-react'

interface StageProgressProps {
  name: string
  status: string
  message: string
  progress?: number
}

const stageConfig: Record<string, { icon: typeof CheckCircle; color: string }> = {
  pending: { icon: Clock, color: 'text-gray-500' },
  running: { icon: Loader2, color: 'text-blue-400 animate-spin' },
  done: { icon: CheckCircle, color: 'text-emerald-400' },
  skipped: { icon: CheckCircle, color: 'text-gray-400' },
  failed: { icon: XCircle, color: 'text-red-400' },
}

export default function StageProgress({ name, status, message, progress }: StageProgressProps) {
  const config = stageConfig[status] || stageConfig.pending
  const Icon = config.icon

  return (
    <div className="flex items-center gap-3 py-2 px-3 rounded-lg bg-gray-900/50">
      <Icon size={16} className={config.color} />
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium capitalize">
          {name.replace(/_/g, ' ')}
        </div>
        {message && (
          <div className="text-xs text-gray-500 truncate">{message}</div>
        )}
        {status === 'running' && progress !== undefined && (
          <div className="mt-1">
            <div className="flex justify-between text-xs text-gray-400 mb-0.5">
              <span>Progress</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1">
              <div
                className="bg-blue-500 h-1 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}
      </div>
      <span
        className={`text-xs capitalize px-2 py-0.5 rounded ${
          status === 'done' || status === 'skipped'
            ? 'bg-emerald-500/10 text-emerald-400'
            : status === 'running'
            ? 'bg-blue-500/10 text-blue-400'
            : status === 'failed'
            ? 'bg-red-500/10 text-red-400'
            : 'bg-gray-500/10 text-gray-400'
        }`}
      >
        {status}
      </span>
    </div>
  )
}
