import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useMutation } from '@tanstack/react-query'
import UploadZone from '@/components/UploadZone'
import { createProject } from '@/lib/api'
import { ArrowLeft, Mic, Cpu } from 'lucide-react'

type TranscriptionBackend = 'openai' | 'whisper_cpp'

export default function Upload() {
  const [file, setFile] = useState<File | null>(null)
  const [lyrics, setLyrics] = useState('')
  const [transcriptionBackend, setTranscriptionBackend] = useState<TranscriptionBackend>('openai')
  const [error, setError] = useState('')
  const navigate = useNavigate()

  const mutation = useMutation({
    mutationFn: () => createProject(file!, lyrics || undefined, transcriptionBackend),
    onSuccess: (data) => {
      navigate(`/project/${data.project_id}`)
    },
    onError: (err) => {
      setError('Failed to create project. Is the API running?')
      console.error(err)
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!file) {
      setError('Please select an audio file')
      return
    }
    setError('')
    mutation.mutate()
  }

  return (
    <div className="max-w-2xl mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <button
          onClick={() => navigate('/')}
          className="text-gray-400 hover:text-gray-200 transition-colors"
        >
          <ArrowLeft size={20} />
        </button>
        <div>
          <h1 className="text-2xl font-bold">New Project</h1>
          <p className="text-gray-500 text-sm mt-1">
            Upload your song and optionally provide lyrics
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        <UploadZone file={file} onFileSelect={setFile} error={error} />

        {/* Transcription Backend Toggle */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <label className="text-sm text-gray-400 block mb-3">
            Transcription Backend (for auto-transcribing lyrics)
          </label>
          <div className="flex gap-3">
            <button
              type="button"
              onClick={() => setTranscriptionBackend('openai')}
              className={`flex-1 flex items-center gap-3 px-4 py-3 rounded-lg border transition-all ${
                transcriptionBackend === 'openai'
                  ? 'bg-indigo-600/20 border-indigo-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              <Mic size={20} />
              <div className="text-left">
                <div className="text-sm font-medium">OpenAI Whisper</div>
                <div className="text-xs text-gray-500">Best quality, requires API key</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => setTranscriptionBackend('whisper_cpp')}
              className={`flex-1 flex items-center gap-3 px-4 py-3 rounded-lg border transition-all ${
                transcriptionBackend === 'whisper_cpp'
                  ? 'bg-indigo-600/20 border-indigo-500 text-white'
                  : 'bg-gray-800 border-gray-700 text-gray-400 hover:border-gray-600'
              }`}
            >
              <Cpu size={20} />
              <div className="text-left">
                <div className="text-sm font-medium">Whisper.cpp</div>
                <div className="text-xs text-gray-500">Local, no API key needed</div>
              </div>
            </button>
          </div>
        </div>

        <div>
          <label className="text-sm text-gray-400 block mb-2">
            Lyrics (optional)
          </label>
          <textarea
            value={lyrics}
            onChange={(e) => setLyrics(e.target.value)}
            placeholder="Paste lyrics here, one line per verse/chorus..."
            className="w-full h-48 bg-gray-900 border border-gray-800 rounded-xl p-4 text-sm resize-none focus:border-indigo-500 focus:outline-none transition-colors"
          />
          <p className="text-xs text-gray-600 mt-1">
            Leave empty to auto-transcribe from audio using {transcriptionBackend === 'openai' ? 'OpenAI Whisper' : 'Whisper.cpp'}
          </p>
        </div>

        <button
          type="submit"
          disabled={!file || mutation.isPending}
          className="w-full py-3 bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed rounded-xl font-medium transition-colors"
        >
          {mutation.isPending ? 'Processing...' : 'Start Processing'}
        </button>
      </form>
    </div>
  )
}
