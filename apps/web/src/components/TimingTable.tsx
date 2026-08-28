import { Lock, Unlock, Trash2, Plus, MoveUp, MoveDown, Play, Pause, Music, RotateCcw, Radio, VolumeX } from 'lucide-react'
import { useState, useRef, useEffect, useCallback } from 'react'
import type { TimingData, LineTiming, WordTiming } from '@/types/api'

interface TimingTableProps {
  data: TimingData
  onChange: (data: TimingData) => void
  audioUrl?: string
}

const NUDGE_AMOUNTS = [-500, -100, 100, 500]

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(2)
  return `${m}:${s.padStart(5, '0')}`
}

function parseTimeInput(value: string): number | null {
  const raw = value.trim()
  if (!raw) return null
  if (raw.includes(':')) {
    const [m, s] = raw.split(':')
    const minutes = parseInt(m, 10)
    const seconds = parseFloat(s)
    if (Number.isNaN(minutes) || Number.isNaN(seconds)) return null
    return +(minutes * 60 + seconds).toFixed(3)
  }
  const asFloat = parseFloat(raw)
  if (Number.isNaN(asFloat)) return null
  return +asFloat.toFixed(3)
}

function splitWords(text: string): string[] {
  const trimmed = text.trim()
  if (!trimmed) return []
  return trimmed.split(/\s+/)
}

function parseFuriganaToken(token: string): { base: string; ruby: string | null } {
  const m = token.match(/^\{([^|{}]+)\|([^{}]+)\}$/)
  if (!m) {
    return { base: token, ruby: null }
  }
  return { base: m[1], ruby: m[2] || null }
}

function scaleWords(words: WordTiming[], oldStart: number, oldEnd: number, newStart: number, newEnd: number): WordTiming[] {
  const oldSpan = oldEnd - oldStart
  const newSpan = newEnd - newStart
  if (oldSpan <= 0) return words.map(w => ({ ...w, start: newStart, end: newEnd }))
  
  return words.map(w => {
    const relativeStart = (w.start - oldStart) / oldSpan
    const relativeEnd = (w.end - oldStart) / oldSpan
    return {
      ...w,
      start: +(newStart + relativeStart * newSpan).toFixed(3),
      end: +(newStart + relativeEnd * newSpan).toFixed(3),
      source: 'user_edited' as const,
    }
  })
}

function rebuildWordsForLine(line: LineTiming, text: string): WordTiming[] {
  const tokens = splitWords(text)
  if (tokens.length === 0) {
    return []
  }

  const span = Math.max(line.end - line.sing_start, 0.01)
  const perWord = span / tokens.length
  return tokens.map((token, idx) => {
    const parsed = parseFuriganaToken(token)
    const start = +(line.sing_start + idx * perWord).toFixed(3)
    const end = +(idx === tokens.length - 1 ? line.end : start + perWord).toFixed(3)
    return {
      id: `${line.id || 'line'}_word_${idx + 1}`,
      text: parsed.base,
      ruby: parsed.ruby,
      start,
      end,
      source: 'user_edited',
      locked: false,
    }
  })
}

function updateLine(
  data: TimingData,
  lineId: string | null,
  updater: (line: LineTiming) => LineTiming
): TimingData {
  return {
    ...data,
    lines: data.lines.map((l) => (l.id === lineId ? updater(l) : l)),
  }
}

function updateWord(
  data: TimingData,
  lineId: string | null,
  wordId: string | null,
  updater: (word: WordTiming) => WordTiming
): TimingData {
  return {
    ...data,
    lines: data.lines.map((l) =>
      l.id === lineId
        ? {
            ...l,
            words: l.words
              .map((w) => (w.id === wordId ? updater(w) : w))
              .sort((a, b) => a.start - b.start),
          }
        : l
    ),
  }
}

function nudgeLine(data: TimingData, lineId: string | null, ms: number): TimingData {
  return updateLine(data, lineId, (line) => {
    const shift = ms / 1000
    const newStart = +(line.sing_start + shift).toFixed(3)
    const newEnd = +(line.end + shift).toFixed(3)
    return {
      ...line,
      display_start: +(line.display_start + shift).toFixed(3),
      sing_start: newStart,
      end: newEnd,
      words: scaleWords(line.words, line.sing_start, line.end, newStart, newEnd),
      source: 'user_edited' as const,
    }
  })
}

function nudgeWord(
  data: TimingData,
  lineId: string | null,
  wordId: string | null,
  ms: number
): TimingData {
  return updateWord(data, lineId, wordId, (word) => ({
    ...word,
    start: +(word.start + ms / 1000).toFixed(3),
    end: +(word.end + ms / 1000).toFixed(3),
    source: 'user_edited' as const,
  }))
}

export default function TimingTable({ data, onChange, audioUrl }: TimingTableProps) {
  const [editingLine, setEditingLine] = useState<{
    id: string | null
    field: string
  } | null>(null)
  const [editValue, setEditValue] = useState('')
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [isRecording, setIsRecording] = useState(false)
  const [showWords, setShowWords] = useState(false)
  const [recordingLineIndex, setRecordingLineIndex] = useState(0)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return

    const handleTimeUpdate = () => setCurrentTime(audio.currentTime)
    const handlePlay = () => setIsPlaying(true)
    const handlePause = () => setIsPlaying(false)

    audio.addEventListener('timeupdate', handleTimeUpdate)
    audio.addEventListener('play', handlePlay)
    audio.addEventListener('pause', handlePause)
    return () => {
      audio.removeEventListener('timeupdate', handleTimeUpdate)
      audio.removeEventListener('play', handlePlay)
      audio.removeEventListener('pause', handlePause)
    }
  }, [])

  const handleTap = useCallback(() => {
    if (!isRecording || !audioRef.current) return
    const time = +audioRef.current.currentTime.toFixed(3)
    
    const newLines = data.lines.map((line, idx) => {
      if (idx === recordingLineIndex) {
        // Mark start of current line
        return {
          ...line,
          sing_start: time,
          display_start: +(time - 1.0).toFixed(3), // Default lead
          source: 'user_edited' as const,
          words: rebuildWordsForLine({ ...line, sing_start: time }, line.text)
        }
      }
      if (idx === recordingLineIndex - 1) {
        // Mark end of previous line
        return {
          ...line,
          end: time,
          source: 'user_edited' as const,
          words: rebuildWordsForLine({ ...line, end: time }, line.text)
        }
      }
      return line
    })

    onChange({
      ...data,
      lines: [...newLines].sort((a, b) => {
      if (a.locked && b.locked) return (a.lockedIndex ?? 0) - (b.lockedIndex ?? 0)
      if (a.locked) return -1
      if (b.locked) return 1
      return a.sing_start - b.sing_start
    })
    })

    if (recordingLineIndex < data.lines.length - 1) {
      setRecordingLineIndex(prev => prev + 1)
    } else {
      setIsRecording(false)
    }
  }, [isRecording, recordingLineIndex, data, onChange])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (editingLine) return // Don't tap while typing numbers
      
      if (e.code === 'Space') {
        if (isRecording) {
          e.preventDefault()
          handleTap()
        } else {
          // Standard play/pause if not recording and not typing
          // Only if not in an input
          if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
            e.preventDefault()
            if (audioRef.current?.paused) audioRef.current.play()
            else audioRef.current?.pause()
          }
        }
      }
      if (e.code === 'Escape' && isRecording) {
        setIsRecording(false)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isRecording, handleTap, editingLine])

  const handleEditStart = (
    lineId: string | null,
    field: string,
    currentValue: string | number
  ) => {
    setEditingLine({ id: lineId, field })
    setEditValue(String(currentValue))
  }

  const handleEditSave = () => {
    if (!editingLine) return
    let newData: TimingData = { ...data }
    const line = data.lines.find((l) => l.id === editingLine.id)
    if (!line) {
      setEditingLine(null)
      return
    }

    if (editingLine.field === 'text') {
      const newText = editValue.trim()
      newData = updateLine(data, editingLine.id, (l) => ({
        ...l,
        text: newText,
        words: rebuildWordsForLine(l, newText),
        source: 'user_edited' as const,
      }))
    } else if (editingLine.field === 'display_start') {
      const num = parseTimeInput(editValue)
      if (num === null) {
        setEditingLine(null)
        return
      }
      newData = updateLine(data, editingLine.id, (l) => ({
        ...l,
        display_start: num,
        source: 'user_edited' as const,
      }))
    } else if (editingLine.field === 'sing_start') {
      const num = parseTimeInput(editValue)
      if (num === null) {
        setEditingLine(null)
        return
      }
      newData = updateLine(data, editingLine.id, (l) => ({
        ...l,
        display_start: +(num - data.next_line_lead_time).toFixed(3),
        sing_start: num,
        words: scaleWords(l.words, l.sing_start, l.end, num, l.end),
        source: 'user_edited' as const,
      }))
    } else if (editingLine.field === 'end') {
      const num = parseTimeInput(editValue)
      if (num === null) {
        setEditingLine(null)
        return
      }
      newData = updateLine(data, editingLine.id, (l) => ({
        ...l,
        end: num,
        words: scaleWords(l.words, l.sing_start, l.end, l.sing_start, num),
        source: 'user_edited' as const,
      }))
    } else if (editingLine.field.startsWith('word_')) {
      const parts = editingLine.field.split('_')
      const wordId = parts.slice(1, -1).join('_')
      const fieldType = parts[parts.length - 1]

      if (fieldType === 'text') {
        newData = updateWord(data, editingLine.id, wordId, (w) => ({
          ...w,
          text: editValue.trim(),
          source: 'user_edited' as const,
        }))
      } else if (fieldType === 'ruby') {
        const ruby = editValue.trim()
        newData = updateWord(data, editingLine.id, wordId, (w) => ({
          ...w,
          ruby: ruby || null,
          source: 'user_edited' as const,
        }))
      } else {
        const num = parseTimeInput(editValue)
        if (num === null) {
          setEditingLine(null)
          return
        }
        newData = updateWord(data, editingLine.id, wordId, (w) => ({
          ...w,
          [fieldType]: num,
          source: 'user_edited' as const,
        }))
      }
    }

    onChange({
      ...newData,
      lines: [...newData.lines]
        .map(l => ({ ...l, words: [...l.words].sort((a, b) => a.start - b.start) }))
        .sort((a, b) => {
      if (a.locked && b.locked) return (a.lockedIndex ?? 0) - (b.lockedIndex ?? 0)
      if (a.locked) return -1
      if (b.locked) return 1
      return a.sing_start - b.sing_start
    }),
    })
    setEditingLine(null)
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleEditSave()
    if (e.key === 'Escape') setEditingLine(null)
  }

  const handleNudge = (lineId: string | null, ms: number) => {
    const nudged = nudgeLine(data, lineId, ms)
    onChange({
      ...nudged,
      lines: [...nudged.lines].sort((a, b) => {
      if (a.locked && b.locked) return (a.lockedIndex ?? 0) - (b.lockedIndex ?? 0)
      if (a.locked) return -1
      if (b.locked) return 1
      return a.sing_start - b.sing_start
    }),
    })
  }

  const handleGlobalNudge = (ms: number) => {
    const shift = ms / 1000
    const newLines = data.lines.map(line => ({
      ...line,
      display_start: +(line.display_start + shift).toFixed(3),
      sing_start: +(line.sing_start + shift).toFixed(3),
      end: +(line.end + shift).toFixed(3),
      words: line.words.map(w => ({
        ...w,
        start: +(w.start + shift).toFixed(3),
        end: +(w.end + shift).toFixed(3),
        source: 'user_edited' as const,
      })),
      source: 'user_edited' as const,
    }))
    onChange({ ...data, lines: newLines })
  }

  const handleWordNudge = (
    lineId: string | null,
    wordId: string | null,
    ms: number
  ) => {
    const updated = nudgeWord(data, lineId, wordId, ms)
    onChange({
      ...updated,
      lines: [...updated.lines].sort((a, b) => {
      if (a.locked && b.locked) return (a.lockedIndex ?? 0) - (b.lockedIndex ?? 0)
      if (a.locked) return -1
      if (b.locked) return 1
      return a.sing_start - b.sing_start
    })
    })
  }

  const toggleLock = (lineId: string | null) => {
    const line = data.lines.find((l) => l.id === lineId)
    const shouldBeLocked = !line?.locked
    onChange(
      updateLine(data, lineId, (l) => ({
        ...l,
        locked: shouldBeLocked,
        lockedIndex: shouldBeLocked ? l.sing_start : undefined,
        words: l.words.map((w) => ({ ...w, locked: shouldBeLocked })),
      }))
    )
  }

  const toggleLockAll = (lock: boolean) => {
    const sorted = [...data.lines].sort((a, b) => a.sing_start - b.sing_start)
    const newLines = sorted.map((l) => ({
      ...l,
      locked: lock,
      lockedIndex: lock ? l.sing_start : undefined,
      words: l.words.map((w) => ({ ...w, locked: lock })),
    }))
    onChange({ ...data, lines: newLines })
  }

  const deleteLine = (lineId: string | null) => {
    onChange({
      ...data,
      lines: data.lines.filter((l) => l.id !== lineId),
    })
  }

  const addLine = () => {
    const lastLine = data.lines[data.lines.length - 1]
    const newStart = lastLine ? lastLine.end + 1 : 0
    const newLine: LineTiming = {
      id: `line_${Date.now()}`,
      text: 'New line',
      display_start: +(newStart - data.next_line_lead_time).toFixed(3),
      sing_start: newStart,
      end: newStart + 2,
      source: 'user_edited',
      locked: false,
      words: [{ id: `w_${Date.now()}`, text: 'word', start: newStart, end: newStart + 1, source: 'user_edited', locked: false }],
    }
    const newLines = [...data.lines, newLine].sort((a, b) => {
      if (a.locked && b.locked) return (a.lockedIndex ?? 0) - (b.lockedIndex ?? 0)
      if (a.locked) return -1
      if (b.locked) return 1
      return a.sing_start - b.sing_start
    })
    onChange({ ...data, lines: newLines })
  }

  const moveLine = (index: number, direction: -1 | 1) => {
    const newIndex = index + direction
    if (newIndex < 0 || newIndex >= data.lines.length) return
    const newLines = [...data.lines]
    ;[newLines[index], newLines[newIndex]] = [newLines[newIndex], newLines[index]]
    onChange({ ...data, lines: newLines })
  }

  const handleResetDisplayTiming = () => {
    const lead = data.next_line_lead_time
    onChange({
      ...data,
      lines: data.lines.map(l => ({
        ...l,
        display_start: +(l.sing_start - lead).toFixed(3),
        source: 'user_edited' as const,
      }))
    })
  }

  const addExclusionRange = () => {
    const start = currentTime
    const end = currentTime + 2.0
    const newRange = { id: `range_${Date.now()}`, start, end }
    const ranges = [...(data.melody_exclusion_ranges || []), newRange]
    onChange({ ...data, melody_exclusion_ranges: ranges })
  }

  const deleteExclusionRange = (id: string) => {
    const ranges = (data.melody_exclusion_ranges || []).filter(r => r.id !== id)
    onChange({ ...data, melody_exclusion_ranges: ranges })
  }

  const updateExclusionRange = (id: string, field: 'start' | 'end', value: number) => {
    const ranges = (data.melody_exclusion_ranges || []).map(r => 
      r.id === id ? { ...r, [field]: value } : r
    ).sort((a, b) => a.start - b.start)
    onChange({ ...data, melody_exclusion_ranges: ranges })
  }

  const playAt = (time: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = Math.max(0, time) // Start exactly at time
      audioRef.current.play()
    }
  }

  return (
    <div className="space-y-4">
      {/* Audio Player & Tap Controls */}
      <div className={`sticky top-0 z-10 border rounded-xl p-4 shadow-2xl flex items-center gap-4 transition-all duration-300 ${isRecording ? 'bg-red-950/20 border-red-500' : 'bg-gray-950 border-gray-800'}`}>
        <audio ref={audioRef} src={audioUrl} />
        <button
          onClick={() => isPlaying ? audioRef.current?.pause() : audioRef.current?.play()}
          className={`p-3 rounded-full transition-colors ${isRecording ? 'bg-red-600 hover:bg-red-500' : 'bg-indigo-600 hover:bg-indigo-500'}`}
        >
          {isPlaying ? <Pause size={20} /> : <Play size={20} />}
        </button>
        
        <div className="flex flex-col gap-1">
          <button
            onClick={() => {
              setIsRecording(!isRecording)
              if (!isRecording) {
                setRecordingLineIndex(0)
                if (audioRef.current) audioRef.current.currentTime = 0
                audioRef.current?.play()
              }
            }}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-bold transition-all ${
              isRecording 
                ? 'bg-red-600 text-white animate-pulse' 
                : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
            }`}
          >
            <Radio size={16} />
            {isRecording ? 'TAP SPACE TO TIME' : 'TAP-TO-TIME MODE'}
          </button>
          {isRecording && (
            <div className="text-[10px] text-red-400 font-mono text-center">
              ESC to stop · SPACE for next line
            </div>
          )}
        </div>

        <div className="flex-1">
          <div className="flex justify-between text-xs font-mono text-gray-500 mb-1">
            <span>{formatTime(currentTime)}</span>
            <span>{audioRef.current?.duration ? formatTime(audioRef.current.duration) : '--:--'}</span>
          </div>
          <div 
            className="w-full bg-gray-800 h-1.5 rounded-full cursor-pointer relative"
            onClick={(e) => {
              const rect = e.currentTarget.getBoundingClientRect()
              const pct = (e.clientX - rect.left) / rect.width
              if (audioRef.current) audioRef.current.currentTime = pct * audioRef.current.duration
            }}
          >
            <div 
              className={`h-full rounded-full transition-all ${isRecording ? 'bg-red-500' : 'bg-indigo-500'}`}
              style={{ width: `${(currentTime / (audioRef.current?.duration || 1)) * 100}%` }}
            />
          </div>
        </div>

        <div className="flex items-center gap-2 border-l border-gray-800 pl-4">
          <span className="text-xs text-gray-500 uppercase font-bold tracking-wider">Global Nudge</span>
          <div className="flex gap-1">
            {[-1000, -100, 100, 1000].map(ms => (
              <button
                key={ms}
                onClick={() => handleGlobalNudge(ms)}
                className="text-[10px] px-2 py-1 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 transition-colors"
              >
                {ms > 0 ? '+' : ''}{ms}ms
              </button>
            ))}
          </div>
        </div>
      </div>

      {isRecording && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 text-center">
          <div className="text-sm font-bold text-red-400 mb-1">RECORDING TIMING</div>
          <div className="text-2xl font-black text-white truncate px-8">
            {data.lines[recordingLineIndex]?.text}
          </div>
          <div className="text-xs text-gray-400 mt-2">
            Next: {data.lines[recordingLineIndex + 1]?.text || 'End of song'}
          </div>
        </div>
      )}

      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-4 mb-4">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <label className="text-xs text-gray-500 uppercase font-bold">Song Title</label>
            <input
              type="text"
              value={data.title || ''}
              onChange={(e) => onChange({ ...data, title: e.target.value })}
              placeholder="e.g. Bohemian Rhapsody"
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none"
            />
          </div>
          <div className="space-y-2">
            <label className="text-xs text-gray-500 uppercase font-bold">Artist</label>
            <input
              type="text"
              value={data.artist || ''}
              onChange={(e) => onChange({ ...data, artist: e.target.value })}
              placeholder="e.g. Queen"
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm focus:border-indigo-500 outline-none"
            />
          </div>
        </div>
        <div className="flex items-center gap-4 pt-2 border-t border-gray-800">
           <label className="flex items-center gap-2 cursor-pointer group">
            <input
              type="checkbox"
              checked={data.enable_word_timing !== false}
              onChange={(e) => onChange({ ...data, enable_word_timing: e.target.checked })}
              className="w-4 h-4 rounded border-gray-800 bg-gray-950 text-indigo-600 focus:ring-indigo-500"
            />
            <span className="text-sm text-gray-400 group-hover:text-gray-200 transition-colors">Enable Per-Word Animation</span>
          </label>
        </div>
      </div>

      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-4">
          <label className="text-sm text-gray-400">
            Countdown offset
            <input
              type="number"
              step="0.1"
              min="0"
              value={data.countdown_offset}
              onChange={(e) =>
                onChange({
                  ...data,
                  countdown_offset: parseFloat(e.target.value) || 0,
                })
              }
              className="ml-2 w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
            />
          </label>
          <label className="text-sm text-gray-400">
            Lead time
            <input
              type="number"
              step="0.1"
              min="0"
              value={data.next_line_lead_time}
              onChange={(e) =>
                onChange({
                  ...data,
                  next_line_lead_time: parseFloat(e.target.value) || 0,
                })
              }
              className="ml-2 w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm"
            />
          </label>
          <button
            onClick={handleResetDisplayTiming}
            className="px-3 py-1 bg-gray-800 hover:bg-gray-700 text-gray-400 rounded-lg text-xs font-medium flex items-center gap-1 border border-gray-700"
            title="Recalculate all entry times based on lead time"
          >
            <RotateCcw size={12} /> RESET DISPLAY
          </button>
          <button
            onClick={() => setShowWords(!showWords)}
            className={`px-3 py-1 rounded-lg text-xs font-bold transition-all ${showWords ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'}`}
          >
            {showWords ? 'HIDE WORDS' : 'SHOW WORD TIMING'}
          </button>
        </div>
         <div className="flex items-center gap-2">
            <button
              onClick={() => toggleLockAll(true)}
              className="flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300"
            >
              <Lock size={12} /> Lock All
            </button>
            <button
              onClick={() => toggleLockAll(false)}
              className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-300"
            >
              <Unlock size={12} /> Unlock All
            </button>
          </div>
          <button
            onClick={addLine}
            className="flex items-center gap-1 text-sm text-indigo-400 hover:text-indigo-300"
          >
            <Plus size={14} /> Add line
          </button>
      </div>

      <div className="overflow-x-auto max-h-[60vh] border border-gray-800 rounded-xl">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gray-500 border-b border-gray-800">
              <th className="pb-2 pr-4 font-normal">#</th>
              <th className="pb-2 pr-4 font-normal">Text</th>
              <th className="pb-2 pr-4 font-normal w-24">Display</th>
              <th className="pb-2 pr-4 font-normal w-24">Sing</th>
              <th className="pb-2 pr-4 font-normal w-24">End</th>
              <th className="pb-2 pr-4 font-normal w-16">Locked</th>
              <th className="pb-2 pr-4 font-normal">Nudge (w/ Words)</th>
              <th className="pb-2 font-normal">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.lines.map((line, idx) => {
              const isActive = currentTime >= line.sing_start && currentTime <= line.end
              const isTarget = isRecording && idx === recordingLineIndex
              return (
                <tr 
                  key={line.id || idx} 
                  className={`border-b border-gray-800/50 hover:bg-gray-900/30 transition-colors ${isActive ? 'bg-indigo-500/10' : ''} ${isTarget ? 'bg-red-500/10 ring-1 ring-inset ring-red-500' : ''}`}
                >
                  <td className="py-2 pr-4 text-gray-500">{idx + 1}</td>
                  <td className="py-2 pr-4">
                    {editingLine?.id === line.id && editingLine.field === 'text' ? (
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={handleEditSave}
                        onKeyDown={handleKeyDown}
                        className="w-full bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                        autoFocus
                      />
                    ) : (
                      <div className="flex items-center gap-2 group">
                        <button
                          onClick={() => playAt(line.sing_start)}
                          onMouseEnter={() => { if(!isRecording && !isPlaying) audioRef.current!.currentTime = line.sing_start }}
                          className="p-1.5 text-gray-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-all"
                          title="Preview this line (Hover to seek)"
                        >
                          <Music size={14} />
                        </button>
                        <button
                          onClick={() =>
                            handleEditStart(line.id, 'text', line.text)
                          }
                          className={`text-left transition-colors truncate max-w-xs ${isTarget ? 'text-red-400 font-bold' : 'hover:text-indigo-400'}`}
                        >
                          {line.text}
                        </button>
                      </div>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    {editingLine?.id === line.id && editingLine.field === 'display_start' ? (
                      <input
                        value={editValue}
                        onChange={(e) => setEditValue(e.target.value)}
                        onBlur={handleEditSave}
                        onKeyDown={handleKeyDown}
                        className="w-20 bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                        autoFocus
                      />
                    ) : (
                      <button
                        onClick={() =>
                          handleEditStart(
                            line.id,
                            'display_start',
                            formatTime(line.display_start)
                          )
                        }
                        className="text-indigo-400 hover:text-indigo-300 font-mono"
                      >
                        {formatTime(line.display_start)}
                      </button>
                    )}
                  </td>
                  <td className="py-2 pr-4">
                    <div className="flex flex-col gap-1">
                      {editingLine?.id === line.id && editingLine.field === 'sing_start' ? (
                        <input
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={handleEditSave}
                          onKeyDown={handleKeyDown}
                          className="w-20 bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                          autoFocus
                        />
                      ) : (
                        <button
                          onClick={() =>
                            handleEditStart(
                              line.id,
                              'sing_start',
                              formatTime(line.sing_start)
                            )
                          }
                          className="text-emerald-400 hover:text-emerald-300 font-mono text-left"
                        >
                          {formatTime(line.sing_start)}
                        </button>
                      )}
                      <div className="flex gap-1">
                        <button onClick={() => handleNudge(line.id, -100)} className="text-[9px] px-1 bg-gray-800 hover:bg-gray-700 text-gray-500 rounded">-</button>
                        <button onClick={() => handleNudge(line.id, 100)} className="text-[9px] px-1 bg-gray-800 hover:bg-gray-700 text-gray-500 rounded">+</button>
                      </div>
                    </div>
                  </td>
                  <td className="py-2 pr-4">
                    <div className="flex flex-col gap-1">
                      {editingLine?.id === line.id && editingLine.field === 'end' ? (
                        <input
                          value={editValue}
                          onChange={(e) => setEditValue(e.target.value)}
                          onBlur={handleEditSave}
                          onKeyDown={handleKeyDown}
                          className="w-20 bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                          autoFocus
                        />
                      ) : (
                        <button
                          onClick={() =>
                            handleEditStart(line.id, 'end', formatTime(line.end))
                          }
                          className="text-gray-300 hover:text-gray-100 font-mono text-left"
                        >
                          {formatTime(line.end)}
                        </button>
                      )}
                      <div className="flex gap-1">
                        <button 
                          onClick={() => {
                            onChange(updateLine(data, line.id, (l) => ({ 
                              ...l, 
                              end: +(l.end - 0.1).toFixed(3),
                              words: scaleWords(l.words, l.sing_start, l.end, l.sing_start, l.end - 0.1)
                            })))
                          }} 
                          className="text-[9px] px-1 bg-gray-800 hover:bg-gray-700 text-gray-500 rounded"
                        >-</button>
                        <button 
                           onClick={() => {
                            onChange(updateLine(data, line.id, (l) => ({ 
                              ...l, 
                              end: +(l.end + 0.1).toFixed(3),
                              words: scaleWords(l.words, l.sing_start, l.end, l.sing_start, l.end + 0.1)
                            })))
                          }} 
                          className="text-[9px] px-1 bg-gray-800 hover:bg-gray-700 text-gray-500 rounded"
                        >+</button>
                      </div>
                    </div>
                  </td>
                  <td className="py-2 pr-4">
                    <button
                      onClick={() => toggleLock(line.id)}
                      className={`${
                        line.locked ? 'text-emerald-400' : 'text-gray-600'
                      } hover:text-gray-300 transition-colors`}
                    >
                      {line.locked ? <Lock size={14} /> : <Unlock size={14} />}
                    </button>
                  </td>
                  <td className="py-2 pr-4">
                    <div className="flex flex-col gap-2">
                      <div className="flex gap-1">
                        {NUDGE_AMOUNTS.map((ms) => (
                          <button
                            key={ms}
                            onClick={() => handleNudge(line.id, ms)}
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                              ms < 0
                                ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                                : 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20'
                            } transition-colors`}
                          >
                            {ms > 0 ? '+' : ''}
                            {ms}ms
                          </button>
                        ))}
                      </div>
                      {idx > 0 && line.sing_start < data.lines[idx-1].end && (
                        <div className="text-[10px] text-red-500 font-bold animate-pulse">
                          ⚠️ Overlaps with previous line
                        </div>
                      )}
                    </div>
                  </td>
                  <td className="py-2">
                    <div className="flex gap-1">
                      <button
                        onClick={() => moveLine(idx, -1)}
                        disabled={idx === 0}
                        className="text-gray-500 hover:text-gray-300 disabled:opacity-30"
                      >
                        <MoveUp size={14} />
                      </button>
                      <button
                        onClick={() => moveLine(idx, 1)}
                        disabled={idx === data.lines.length - 1}
                        className="text-gray-500 hover:text-gray-300 disabled:opacity-30"
                      >
                        <MoveDown size={14} />
                      </button>
                      <button
                        onClick={() => deleteLine(line.id)}
                        className="text-gray-500 hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {data.lines.length > 0 && (
        <div className="mt-4 border-t border-gray-800 pt-4">
          <div className="text-sm font-medium text-gray-400 mb-2">
            Word-level timing
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-gray-500 border-b border-gray-800">
                  <th className="pb-2 pr-4 font-normal">Line</th>
                  <th className="pb-2 pr-4 font-normal">Word</th>
                  <th className="pb-2 pr-4 font-normal">Ruby</th>
                  <th className="pb-2 pr-4 font-normal w-24">Start</th>
                  <th className="pb-2 pr-4 font-normal w-24">End</th>
                  <th className="pb-2 pr-4 font-normal">Nudge</th>
                </tr>
              </thead>
              <tbody>
                {data.lines.map((line) =>
                  line.words.map((word) => {
                    const isActive = currentTime >= word.start && currentTime <= word.end
                    return (
                      <tr
                        key={word.id}
                        className={`border-b border-gray-800/30 hover:bg-gray-900/20 transition-colors ${isActive ? 'bg-indigo-500/10' : ''}`}
                      >
                        <td className="py-1.5 pr-4 text-gray-500 text-xs">
                          {line.text.slice(0, 30)}
                          {line.text.length > 30 ? '...' : ''}
                        </td>
                        <td className="py-1.5 pr-4">
                          {editingLine?.id === line.id &&
                          editingLine.field === `word_${word.id}_text` ? (
                            <input
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={handleEditSave}
                              onKeyDown={handleKeyDown}
                              className="bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                              autoFocus
                            />
                          ) : (
                            <div className="flex items-center gap-2 group">
                              <button
                                onClick={() => playAt(word.start)}
                                className="p-1 text-gray-600 hover:text-indigo-400 opacity-0 group-hover:opacity-100 transition-all"
                              >
                                <Music size={10} />
                              </button>
                              <button
                                  onClick={() =>
                                    handleEditStart(
                                      line.id,
                                      `word_${word.id}_text`,
                                      word.text
                                    )
                                  }
                                className="hover:text-indigo-400"
                              >
                                {word.text}
                              </button>
                            </div>
                          )}
                        </td>
                        <td className="py-1.5 pr-4">
                          {editingLine?.id === line.id &&
                          editingLine.field === `word_${word.id}_ruby` ? (
                            <input
                              value={editValue}
                              onChange={(e) => setEditValue(e.target.value)}
                              onBlur={handleEditSave}
                              onKeyDown={handleKeyDown}
                              className="bg-gray-800 border border-indigo-500 rounded px-2 py-1"
                              autoFocus
                            />
                          ) : (
                            <button
                              onClick={() =>
                                handleEditStart(
                                  line.id,
                                  `word_${word.id}_ruby`,
                                  word.ruby || ''
                                )
                              }
                              className="hover:text-indigo-400 text-amber-200"
                            >
                              {word.ruby || '-'}
                            </button>
                          )}
                        </td>
                        <td className="py-1.5 pr-4">
                          <button
                            onClick={() =>
                              handleEditStart(
                                line.id,
                                `word_${word.id}_start`,
                                word.start
                              )
                            }
                            className="text-indigo-400 hover:text-indigo-300 font-mono text-xs"
                          >
                            {formatTime(word.start)}
                          </button>
                        </td>
                        <td className="py-1.5 pr-4">
                          <button
                            onClick={() =>
                              handleEditStart(
                                line.id,
                                `word_${word.id}_end`,
                                word.end
                              )
                            }
                            className="text-gray-300 hover:text-gray-100 font-mono text-xs"
                          >
                            {formatTime(word.end)}
                          </button>
                        </td>
                        <td className="py-1.5 pr-4">
                          <div className="flex gap-1">
                            {NUDGE_AMOUNTS.map((ms) => (
                              <button
                                key={ms}
                                onClick={() =>
                                  handleWordNudge(line.id, word.id, ms)
                                }
                                className={`text-[10px] px-1.5 py-0.5 rounded ${
                                  ms < 0
                                    ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20'
                                    : 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20'
                                } transition-colors`}
                              >
                                {ms > 0 ? '+' : ''}
                                {ms}ms
                              </button>
                            ))}
                          </div>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
      {data.lines.length > 0 && (
        <div className="mt-8 pt-6 border-t border-gray-800">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <div className="p-2 bg-red-500/10 rounded-lg text-red-400">
                <VolumeX size={18} />
              </div>
              <div>
                <h3 className="font-medium text-gray-200">Melody Exclusion Zones</h3>
                <p className="text-xs text-gray-500">Mute the melody guide (audio & dots) during noisy or unwanted parts.</p>
              </div>
            </div>
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2 bg-gray-900/50 px-3 py-1.5 rounded-lg border border-gray-800">
                <Music size={12} className="text-gray-500" />
                <span className="text-[10px] text-gray-500 uppercase font-bold tracking-wider">Volume</span>
                <input
                  type="range"
                  min="-40"
                  max="0"
                  step="1"
                  value={data.melody_gain_db || -14}
                  onChange={(e) => onChange({ ...data, melody_gain_db: parseInt(e.target.value) })}
                  className="w-24 h-1 bg-gray-700 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
                <span className="text-xs font-mono text-indigo-400 w-8 text-right">
                  {data.melody_gain_db || -14}dB
                </span>
              </div>

              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={data.enable_melody_visualizer === true}
                      onChange={(e) => onChange({ ...data, enable_melody_visualizer: e.target.checked })}
                    />
                    <div className="w-8 h-4 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-emerald-600"></div>
                  </div>
                  <span className="text-xs font-medium text-gray-400 group-hover:text-gray-300 transition-colors">
                    Show dots visualizer
                  </span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer group">
                  <div className="relative">
                    <input
                      type="checkbox"
                      className="sr-only peer"
                      checked={data.auto_mute_melody_gaps !== false}
                      onChange={(e) => onChange({ ...data, auto_mute_melody_gaps: e.target.checked })}
                    />
                    <div className="w-8 h-4 bg-gray-700 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-3 after:w-3 after:transition-all peer-checked:bg-indigo-600"></div>
                  </div>
                  <span className="text-xs font-medium text-gray-400 group-hover:text-gray-300 transition-colors">
                    Auto-mute gaps
                  </span>
                </label>
              </div>
              <button
                onClick={addExclusionRange}
                className="flex items-center gap-2 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs font-medium transition-colors border border-gray-700"
              >
                <Plus size={14} /> Add Range at {formatTime(currentTime)}
              </button>
            </div>
          </div>

          <div className="bg-gray-950/50 rounded-xl border border-gray-800 overflow-hidden">
            <table className="w-full text-xs text-left">
              <thead>
                <tr className="bg-gray-900/50 text-gray-500 uppercase tracking-wider font-semibold">
                  <th className="px-4 py-2 font-normal">Start Time</th>
                  <th className="px-4 py-2 font-normal">End Time</th>
                  <th className="px-4 py-2 font-normal">Duration</th>
                  <th className="px-4 py-2 font-normal w-16"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800">
                {(data.melody_exclusion_ranges || []).length === 0 ? (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-gray-600 italic">
                      No exclusion zones defined. The melody guide will play for the entire video.
                    </td>
                  </tr>
                ) : (
                  (data.melody_exclusion_ranges || []).map(range => (
                    <tr key={range.id} className="hover:bg-gray-900/30 transition-colors group">
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            const val = prompt('Enter start time (seconds or M:SS):', range.start.toString())
                            if (val !== null) {
                              const num = parseTimeInput(val)
                              if (num !== null) updateExclusionRange(range.id, 'start', num)
                            }
                          }}
                          className="text-red-400 hover:text-red-300 font-mono"
                        >
                          {formatTime(range.start)}
                        </button>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => {
                            const val = prompt('Enter end time (seconds or M:SS):', range.end.toString())
                            if (val !== null) {
                              const num = parseTimeInput(val)
                              if (num !== null) updateExclusionRange(range.id, 'end', num)
                            }
                          }}
                          className="text-red-400 hover:text-red-300 font-mono"
                        >
                          {formatTime(range.end)}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {(range.end - range.start).toFixed(2)}s
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          onClick={() => deleteExclusionRange(range.id)}
                          className="p-1.5 text-gray-600 hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                        >
                          <Trash2 size={14} />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
