import axios from 'axios'
import type {
  LyricsData,
  ProjectRead,
  ProjectCreateResponse,
  TimingData,
  RerunRequest,
} from '@/types/api'

const api = axios.create({
  baseURL: '/api',
})

export async function createProject(
  audioFile: File,
  lyricsText?: string,
  transcriptionBackend?: 'openai' | 'whisper_cpp' | 'qwen_asr',
  language?: string
): Promise<ProjectCreateResponse> {
  const formData = new FormData()
  formData.append('audio_file', audioFile)
  if (lyricsText) {
    formData.append('lyrics_text', lyricsText)
  }
  if (transcriptionBackend) {
    formData.append('transcription_backend', transcriptionBackend)
  }
  if (language) {
    formData.append('language', language)
  }
  const res = await api.post<ProjectCreateResponse>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function getProject(id: string): Promise<ProjectRead> {
  const res = await api.get<ProjectRead>(`/projects/${id}`)
  return res.data
}

export async function rerunProject(
  id: string,
  stages: string[],
  unlockedOnly = true,
  transcriptionBackend?: 'openai' | 'whisper_cpp' | 'qwen_asr',
  language?: string
): Promise<ProjectCreateResponse> {
  const payload: RerunRequest = { stages, unlocked_only: unlockedOnly }
  if (transcriptionBackend) {
    payload.transcription_backend = transcriptionBackend
  }
  if (language) {
    payload.language = language
  }

  const res = await api.post<ProjectCreateResponse>(
    `/projects/${id}/rerun`,
    payload
  )
  return res.data
}

export async function patchLyrics(
  id: string,
  lyricsText: string
): Promise<ProjectCreateResponse> {
  const res = await api.patch<ProjectCreateResponse>(
    `/projects/${id}/lyrics`,
    { lyrics_text: lyricsText }
  )
  return res.data
}

export async function refreshLyrics(id: string): Promise<ProjectCreateResponse> {
  const res = await api.post<ProjectCreateResponse>(`/projects/${id}/lyrics/refresh`)
  return res.data
}

export async function getLyrics(id: string): Promise<LyricsData> {
  const res = await api.get<LyricsData>(`/projects/${id}/lyrics`)
  return res.data
}

export async function patchTiming(
  id: string,
  timing: TimingData
): Promise<ProjectCreateResponse> {
  const res = await api.patch<ProjectCreateResponse>(
    `/projects/${id}/timing`,
    timing
  )
  return res.data
}

export async function getTiming(id: string): Promise<TimingData> {
  const res = await api.get(`/projects/${id}/timing`)
  return res.data
}

export async function getMidiUrl(id: string): Promise<string> {
  return `/api/projects/${id}/midi`
}

export async function getVideoUrl(
  id: string,
  type: 'preview' | 'final'
): Promise<string> {
  return `/api/projects/${id}/video?type=${type}`
}

export function getArtifactUrl(id: string, name: string): string {
  return `/api/projects/${id}/artifacts/${name}`
}

export default api
