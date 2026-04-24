import { Link } from 'react-router-dom'
import { ProjectRead } from '@/types/api'
import { Clock, Play, CheckCircle, AlertCircle, Loader2 } from 'lucide-react'

interface ProjectCardProps {
  project: ProjectRead
}

const statusConfig = {
  queued: { color: 'text-yellow-400', icon: Clock, label: 'Queued' },
  running: { color: 'text-blue-400', icon: Loader2, label: 'Processing' },
  completed: { color: 'text-emerald-400', icon: CheckCircle, label: 'Done' },
  failed: { color: 'text-red-400', icon: AlertCircle, label: 'Failed' },
}

export default function ProjectCard({ project }: ProjectCardProps) {
  const config = statusConfig[project.status]
  const Icon = config.icon

  return (
    <Link
      to={`/project/${project.project_id}`}
      className="block bg-gray-900 border border-gray-800 rounded-xl p-5 hover:border-gray-600 transition-colors"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={18} className={config.color} />
          <span className={`text-sm font-medium ${config.color}`}>{config.label}</span>
        </div>
        <span className="text-xs text-gray-500">
          {new Date(project.created_at).toLocaleDateString()}
        </span>
      </div>

      <div className="text-sm text-gray-300 mb-3 truncate">
        {project.artifacts.project_dir?.split('/').pop() || project.project_id.slice(0, 8)}
      </div>

      {project.status === 'running' && (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-gray-400">
            <span>{project.current_stage || 'Starting...'}</span>
            <span>{project.progress}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-1.5">
            <div
              className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500"
              style={{ width: `${project.progress}%` }}
            />
          </div>
        </div>
      )}

      {project.status === 'completed' && (
        <div className="flex items-center gap-4 text-xs text-gray-400">
          <span className="flex items-center gap-1">
            <Play size={12} />
            {Object.keys(project.artifacts).filter(
              (k) => k.includes('video') || k.includes('midi')
            ).length}{' '}
            artifacts
          </span>
        </div>
      )}

      {project.errors.length > 0 && (
        <div className="mt-2 text-xs text-red-400 truncate">
          {project.errors[project.errors.length - 1]}
        </div>
      )}
    </Link>
  )
}
