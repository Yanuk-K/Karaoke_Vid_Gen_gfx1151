import { Upload, X } from 'lucide-react'
import { useState, useCallback } from 'react'

interface UploadZoneProps {
  file: File | null
  onFileSelect: (file: File | null) => void
  error?: string
}

export default function UploadZone({ file, onFileSelect, error }: UploadZoneProps) {
  const [dragging, setDragging] = useState(false)

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault()
      setDragging(false)
      const dropped = e.dataTransfer.files[0]
      if (dropped) onFileSelect(dropped)
    },
    [onFileSelect]
  )

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0]
    onFileSelect(selected || null)
  }

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-xl p-12 text-center transition-colors ${
          dragging
            ? 'border-indigo-400 bg-indigo-500/10'
            : file
            ? 'border-emerald-500 bg-emerald-500/5'
            : 'border-gray-700 bg-gray-900/50 hover:border-gray-500'
        }`}
      >
        {file ? (
          <div className="flex flex-col items-center gap-3">
            <div className="text-emerald-400 text-4xl font-bold">{file.name}</div>
            <div className="text-gray-400">{(file.size / (1024 * 1024)).toFixed(1)} MB</div>
            <button
              onClick={() => onFileSelect(null)}
              className="mt-2 text-sm text-red-400 hover:text-red-300 flex items-center gap-1"
            >
              <X size={14} /> Remove
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <Upload size={48} className="text-gray-500" />
            <div className="text-gray-300 font-medium">
              Drop audio file here or click to browse
            </div>
            <div className="text-gray-500 text-sm">MP3, WAV, FLAC supported</div>
            <label className="mt-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg cursor-pointer text-sm font-medium transition-colors">
              Browse Files
              <input
                type="file"
                accept="audio/*"
                className="hidden"
                onChange={handleFileInput}
              />
            </label>
          </div>
        )}
      </div>
      {error && <div className="text-red-400 text-sm">{error}</div>}
    </div>
  )
}
