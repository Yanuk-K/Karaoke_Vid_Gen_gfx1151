export interface StageProgress {
  status: 'pending' | 'running' | 'done' | 'failed' | 'skipped'
  started_at?: string
  finished_at?: string
  message: string
  progress?: number
}

export interface ProjectRead {
  project_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  current_stage: string | null
  progress: number
  created_at: string
  updated_at: string
  transcription_backend?: 'openai' | 'whisper_cpp'
  artifacts: Record<string, string>
  stages: Record<string, StageProgress>
  errors: string[]
  config: {
    countdown_offset: number
    next_line_lead_time: number
    [key: string]: unknown
  }
}

export interface ProjectCreateResponse {
  project_id: string
  status: string
}

export interface WordTiming {
  id: string | null
  text: string
  ruby?: string | null
  start: number
  end: number
  source: 'model' | 'user_edited'
  locked: boolean
}

export interface LineTiming {
  id: string | null
  text: string
  display_start: number
  sing_start: number
  end: number
  source: 'model' | 'user_edited'
  locked: boolean
  lockedIndex?: number
  words: WordTiming[]
}

export interface MelodyExclusionRange {
  id: string
  start: number
  end: number
}

export interface TimingData {
  version: number
  countdown_offset: number
  next_line_lead_time: number
  auto_mute_melody_gaps?: boolean
  melody_gain_db?: number
  lines: LineTiming[]
  melody_exclusion_ranges?: MelodyExclusionRange[]
}

export interface RerunRequest {
  stages: string[]
  unlocked_only?: boolean
  transcription_backend?: 'openai' | 'whisper_cpp'
}

export interface LyricsData {
  lyrics_text: string
  source: 'provided' | 'edited_lyrics' | 'raw_transcript' | 'empty'
}
