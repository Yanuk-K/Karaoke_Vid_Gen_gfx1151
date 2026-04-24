import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Plus } from 'lucide-react'
import ProjectCard from '@/components/ProjectCard'
import type { ProjectRead } from '@/types/api'
import api from '@/lib/api'

async function fetchProjects(): Promise<ProjectRead[]> {
  const res = await api.get<ProjectRead[]>('/projects')
  return res.data
}

export default function ProjectList() {
  const { data: projects = [], isLoading } = useQuery({
    queryKey: ['projects'],
    queryFn: fetchProjects,
    refetchInterval: 10000,
  })

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Your Projects</h1>
          <p className="text-gray-500 text-sm mt-1">
            Create a new project to start generating karaoke videos
          </p>
        </div>
        <Link
          to="/upload"
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus size={16} /> New Project
        </Link>
      </div>

      {isLoading ? (
        <div className="text-center py-20 text-gray-500">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-gray-600 text-lg mb-2">No projects yet</div>
          <Link
            to="/upload"
            className="text-indigo-400 hover:text-indigo-300 text-sm"
          >
            Create your first project →
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {projects.map((p) => (
            <ProjectCard key={p.project_id} project={p} />
          ))}
        </div>
      )}
    </div>
  )
}
