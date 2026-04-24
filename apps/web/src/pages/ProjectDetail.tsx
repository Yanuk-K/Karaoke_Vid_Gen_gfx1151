import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, Save, RefreshCw, Download, Upload, X } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import StageProgress from '@/components/StageProgress'
import TimingTable from '@/components/TimingTable'
import VideoPreview from '@/components/VideoPreview'
import SettingsPanel from '@/components/SettingsPanel'
import { useLyrics, useLyricsUpdate, useProject, useTiming, useTimingUpdate } from '@/hooks/useProject'
import { refreshLyrics, rerunProject } from '@/lib/api'
import type { TimingData } from '@/types/api'

type Tab = 'status' | 'timing' | 'preview'
type TranscriptionBackend = 'openai' | 'whisper_cpp'

const STAGE_ORDER = [
  'normalize_audio',
  'separate_stems',
  'acquire_lyrics',
  'align_lyrics',
  'extract_melody',
  'render_preview',
] as const

const STAGE_LABELS: Record<string, string> = {
  normalize_audio: 'Normalize Audio',
  separate_stems: 'Separate Stems',
  acquire_lyrics: 'Acquire Lyrics',
  align_lyrics: 'Align Lyrics',
  extract_melody: 'Extract Melody',
  render_preview: 'Render Preview',
}

export default function ProjectDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [activeTab, setActiveTab] = useState<Tab>('status')
  const [timingData, setTimingData] = useState<TimingData | null>(null)
  const [saving, setSaving] = useState(false)
  const [lyricsSaving, setLyricsSaving] = useState(false)
  const [lyricsRefreshing, setLyricsRefreshing] = useState(false)
  const [lyricsText, setLyricsText] = useState('')
  const [rerunFromStage, setRerunFromStage] = useState<(typeof STAGE_ORDER)[number]>('acquire_lyrics')
  const [rerunBackend, setRerunBackend] = useState<TranscriptionBackend>('whisper_cpp')
  const [rerunning, setRerunning] = useState(false)
  const queryClient = useQueryClient()

  const { data: project, isLoading } = useProject(id!)

  const timingQuery = useTiming(id!)
  const { update: updateTiming } = useTimingUpdate(id!)
  const lyricsQuery = useLyrics(id!)
  const { update: updateLyrics } = useLyricsUpdate(id!)

  useEffect(() => {
    if (lyricsQuery.data && !lyricsText.trim()) {
      setLyricsText(lyricsQuery.data.lyrics_text)
    }
  }, [lyricsQuery.data, lyricsText])

  useEffect(() => {
    const backend = project?.transcription_backend
    if (backend === 'openai' || backend === 'whisper_cpp') {
      setRerunBackend(backend)
    }
  }, [project?.transcription_backend])

  if (isLoading) {
    return (
      <div className="max-w-6xl mx-auto py-8 text-center text-gray-500">
        Loading project...
      </div>
    )
  }

  if (!project) {
    return (
      <div className="max-w-6xl mx-auto py-8 text-center">
        <p className="text-gray-400 mb-4">Project not found</p>
        <button
          onClick={() => navigate('/')}
          className="text-indigo-400 hover:text-indigo-300"
        >
          ← Back to projects
        </button>
      </div>
    )
  }

  const handleTimingChange = (newData: TimingData) => {
    setTimingData(newData)
  }

  const handleSaveTiming = async () => {
    const dataToSave = timingData || timingQuery.data
    if (!dataToSave) return
    setSaving(true)
    try {
      await updateTiming(dataToSave)
    } finally {
      setSaving(false)
    }
  }

  const buildStageSuffix = (startStage: string): string[] => {
    const idx = STAGE_ORDER.indexOf(startStage as (typeof STAGE_ORDER)[number])
    if (idx < 0) return []
    return STAGE_ORDER.slice(idx) as unknown as string[]
  }

  const needsBackendSelection = (stages: string[]) => {
    return stages.includes('acquire_lyrics')
  }

  const handleRerun = async (
    stages: string[],
    backend?: TranscriptionBackend
  ) => {
    setRerunning(true)
    try {
      const backendToUse = needsBackendSelection(stages)
        ? backend || rerunBackend
        : undefined
      await rerunProject(id!, stages, true, backendToUse)
      await queryClient.invalidateQueries({ queryKey: ['project', id] })
      await queryClient.invalidateQueries({ queryKey: ['timing', id] })
      await queryClient.invalidateQueries({ queryKey: ['lyrics', id] })
      setTimingData(null) // Clear local state to force reload from fresh server data
    } catch (e) {
      console.error('Rerun failed', e)
    } finally {
      setRerunning(false)
    }
  }

  const handleRerunFromSelectedStage = async () => {
    const stages = buildStageSuffix(rerunFromStage)
    if (!stages.length) return
    await handleRerun(stages, rerunBackend)
  }

  const handleSaveLyrics = async () => {
    setLyricsSaving(true)
    try {
      await updateLyrics(lyricsText)
    } finally {
      setLyricsSaving(false)
    }
  }

  const handleRefreshMatchedLyrics = async () => {
    setLyricsRefreshing(true)
    try {
      await refreshLyrics(id!)
      await queryClient.invalidateQueries({ queryKey: ['project', id] })
      await queryClient.invalidateQueries({ queryKey: ['timing', id] })
      await queryClient.invalidateQueries({ queryKey: ['lyrics', id] })
      setTimingData(null) // Clear local state to force reload from fresh server data
    } finally {
      setLyricsRefreshing(false)
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'status', label: 'Status' },
    { key: 'timing', label: 'Timing Editor' },
    { key: 'preview', label: 'Preview' },
  ]

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/')}
            className="text-gray-400 hover:text-gray-200 transition-colors"
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <h1 className="text-2xl font-bold">Project</h1>
            <p className="text-gray-500 text-sm">
              {project.project_id.slice(0, 12)}...
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() =>
              handleRerun([
                'normalize_audio',
                'separate_stems',
                'acquire_lyrics',
                'align_lyrics',
                'extract_melody',
                'render_preview',
              ])
            }
            disabled={rerunning}
            className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
          >
            <RefreshCw size={14} /> Rerun Full
          </button>
          <button
            onClick={() => handleRerun(['render_preview'])}
            disabled={rerunning}
            className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
          >
            <Download size={14} /> Re-render Video
          </button>
        </div>
      </div>

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium text-gray-200">Transcription & Timing Strategy</div>
          <div className="flex gap-2">
             <button
              onClick={() => {
                setRerunFromStage('acquire_lyrics')
                handleRerunFromSelectedStage()
              }}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-xs font-medium"
            >
              Apply Backend Change & Rerun
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-gray-500 uppercase tracking-wider font-bold">Backend Choice</label>
            <div className="flex gap-2">
              <button
                onClick={() => setRerunBackend('openai')}
                className={`flex-1 py-3 px-4 rounded-xl border transition-all text-left ${
                  rerunBackend === 'openai'
                    ? 'bg-indigo-500/10 border-indigo-500 text-indigo-400'
                    : 'bg-gray-950 border-gray-800 text-gray-500 hover:border-gray-700'
                }`}
              >
                <div className="font-bold text-sm">OpenAI Whisper API</div>
                <div className="text-[10px] mt-1 opacity-70">Guided by official lyrics, best accuracy & timing.</div>
              </button>
              <button
                onClick={() => setRerunBackend('whisper_cpp')}
                className={`flex-1 py-3 px-4 rounded-xl border transition-all text-left ${
                  rerunBackend === 'whisper_cpp'
                    ? 'bg-emerald-500/10 border-emerald-500 text-emerald-400'
                    : 'bg-gray-950 border-gray-800 text-gray-500 hover:border-gray-700'
                }`}
              >
                <div className="font-bold text-sm">Local Whisper.cpp VAD</div>
                <div className="text-[10px] mt-1 opacity-70">Privacy focused, uses Silero VAD for timing.</div>
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label className="text-xs text-gray-500 uppercase tracking-wider font-bold">Rerun From Stage</label>
            <div className="flex gap-2">
              <select
                value={rerunFromStage}
                onChange={(e) =>
                  setRerunFromStage(e.target.value as (typeof STAGE_ORDER)[number])
                }
                className="flex-1 bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none"
              >
                {STAGE_ORDER.map((stage) => (
                  <option key={stage} value={stage}>
                    {STAGE_LABELS[stage]}
                  </option>
                ))}
              </select>
              <button
                onClick={handleRerunFromSelectedStage}
                disabled={rerunning}
                className="px-6 py-2 bg-gray-800 hover:bg-gray-700 disabled:opacity-50 rounded-lg text-sm font-medium"
              >
                {rerunning ? 'Wait...' : 'Go'}
              </button>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-2 border-t border-gray-800/50">
          <button
            onClick={() => handleRerun(buildStageSuffix('acquire_lyrics'), rerunBackend)}
            disabled={rerunning}
            className="px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 rounded-lg text-[11px] text-gray-400"
          >
            Rerun Full Lyrics Path
          </button>
          <button
            onClick={() => handleRerun(buildStageSuffix('align_lyrics'))}
            disabled={rerunning}
            className="px-3 py-1.5 bg-gray-800/50 hover:bg-gray-800 rounded-lg text-[11px] text-gray-400"
          >
            Re-align Existing Transcript
          </button>
          
          <div className="flex-1" />
          
          <div className="flex items-center gap-2 px-3 py-1.5 bg-indigo-500/5 border border-indigo-500/20 rounded-lg">
            <span className="text-[10px] text-indigo-400 font-bold uppercase tracking-wider">Background</span>
            <input
              type="file"
              id="bg-upload"
              className="hidden"
              accept="image/*,video/*"
              onChange={async (e) => {
                const file = e.target.files?.[0]
                if (!file) return
                const formData = new FormData()
                formData.append('file', file)
                await fetch(`/api/projects/${id}/background`, {
                  method: 'POST',
                  body: formData,
                })
                handleRerun(['render_preview'])
              }}
            />
            <label
              htmlFor="bg-upload"
              className="flex items-center gap-1.5 text-[11px] text-indigo-300 hover:text-indigo-200 cursor-pointer transition-colors"
            >
              <Upload size={12} /> {project.artifacts.background ? 'Change Background' : 'Upload BG (Video/Image)'}
            </label>
            {project.artifacts.background && (
              <>
                <span className="text-[9px] text-indigo-500/50 italic truncate max-w-[100px]">
                  {project.artifacts.background.split('/').pop()}
                </span>
                <button
                  onClick={async () => {
                    if (confirm('Remove background?')) {
                      await fetch(`/api/projects/${id}/background`, {
                        method: 'DELETE',
                      })
                      handleRerun(['render_preview'])
                    }
                  }}
                  className="p-1 text-red-500/50 hover:text-red-500 transition-colors"
                >
                  <X size={10} />
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="flex gap-1 bg-gray-900 p-1 rounded-lg w-fit">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-gray-800 text-white'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === 'status' && (
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium">Pipeline Status</span>
              <span
                className={`text-sm capitalize ${
                  project.status === 'completed'
                    ? 'text-emerald-400'
                    : project.status === 'running'
                    ? 'text-blue-400'
                    : project.status === 'failed'
                    ? 'text-red-400'
                    : 'text-yellow-400'
                }`}
              >
                {project.status}
              </span>
            </div>

            {project.status === 'running' && (
              <div className="mb-4">
                <div className="flex justify-between text-xs text-gray-400 mb-1">
                  <span>{project.current_stage?.replace(/_/g, ' ')}</span>
                  <span>{project.progress}%</span>
                </div>
                <div className="w-full bg-gray-800 rounded-full h-2">
                  <div
                    className="bg-indigo-500 h-2 rounded-full transition-all duration-500"
                    style={{ width: `${project.progress}%` }}
                  />
                </div>
              </div>
            )}

            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {Object.entries(project.stages).map(([name, stage]) => (
                <StageProgress
                  key={name}
                  name={name}
                  status={stage.status}
                  message={stage.message}
                  progress={stage.progress}
                />
              ))}
            </div>

            {project.errors.length > 0 && (
              <div className="mt-4 p-3 bg-red-500/5 border border-red-500/20 rounded-lg">
                <div className="text-sm text-red-400 font-medium mb-1">
                  Errors
                </div>
                {project.errors.map((err, i) => (
                  <div key={i} className="text-xs text-red-400/70 font-mono">
                    {err}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'timing' && (
        <div className="space-y-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-medium">Lyrics Editor</h2>
                <p className="text-sm text-gray-500">
                  Edit transcript text directly, then re-align timings automatically.
                </p>
              </div>
              <button
                onClick={handleSaveLyrics}
                disabled={lyricsSaving || lyricsRefreshing}
                className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
              >
                <Save size={14} />
                {lyricsSaving ? 'Saving...' : 'Save Lyrics & Re-align'}
              </button>
            </div>

            <div className="flex items-center justify-between gap-3">
              <div className="text-xs text-gray-500">
                If preview still shows old lines, refresh matched lyrics to overwrite stale timing text.
              </div>
              <button
                onClick={handleRefreshMatchedLyrics}
                disabled={lyricsSaving || lyricsRefreshing}
                className="px-3 py-2 bg-gray-800 hover:bg-gray-700 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg text-xs"
              >
                {lyricsRefreshing ? 'Refreshing...' : 'Refresh Matched Lyrics'}
              </button>
            </div>

            <textarea
              value={lyricsText}
              onChange={(e) => setLyricsText(e.target.value)}
              className="w-full h-40 bg-gray-950 border border-gray-800 rounded-lg p-3 text-sm focus:border-indigo-500 focus:outline-none"
              placeholder="Edit lyrics here, one line per phrase. Furigana format: {漢字|かんじ}"
            />
            <div className="text-xs text-gray-500">
              Source: {lyricsQuery.data?.source || 'loading'} · Furigana syntax: {'{base|ruby}'}
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-medium">Timing Editor</h2>
              <p className="text-sm text-gray-500">
                Edit line and word timings. Changes save to{' '}
                <code className="text-indigo-400">edited_lyrics.json</code>
              </p>
            </div>
            <button
              onClick={handleSaveTiming}
              disabled={saving || !timingData || !timingQuery.data}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
            >
              <Save size={14} />
              {saving ? 'Saving...' : 'Save & Rerender'}
            </button>
          </div>

          <SettingsPanel
            countdownOffset={project.config.countdown_offset}
            nextLineLeadTime={project.config.next_line_lead_time}
            onCountdownChange={(v) =>
              setTimingData(
                timingData
                  ? { ...timingData, countdown_offset: v }
                  : timingQuery.data
                  ? { ...timingQuery.data, countdown_offset: v }
                  : null
              )
            }
            onLeadTimeChange={(v) =>
              setTimingData(
                timingData
                  ? { ...timingData, next_line_lead_time: v }
                  : timingQuery.data
                  ? { ...timingQuery.data, next_line_lead_time: v }
                  : null
              )
            }
          />

          {timingData || (timingQuery.isSuccess && timingQuery.data) ? (
            <TimingTable
              data={timingData || timingQuery.data!}
              onChange={handleTimingChange}
              audioUrl={`/api/projects/${id}/audio?type=vocals`}
            />
          ) : timingQuery.isLoading ? (
            <div className="text-center py-12 text-gray-500">Loading timing data...</div>
          ) : timingQuery.isError ? (
            <div className="text-center py-12">
              <div className="text-gray-500 mb-2">Timing data not available yet</div>
              <div className="text-sm text-gray-600 mb-4">
                {project.status === 'running'
                  ? 'Pipeline still running. Timing will appear when complete.'
                  : 'No timing data found. Try rerunning the pipeline.'}
              </div>
              <button
                onClick={() => timingQuery.refetch()}
                className="px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm"
              >
                Retry
              </button>
            </div>
          ) : (
            <div className="text-center py-12 text-gray-500">
              No timing data available. Complete the pipeline first.
            </div>
          )}
        </div>
      )}

      {activeTab === 'preview' && (
        <div className="space-y-4">
          <h2 className="text-lg font-medium">Video Preview</h2>
          <VideoPreview projectId={project.project_id} videoVersion={project.updated_at} />
        </div>
      )}
    </div>
  )
}
