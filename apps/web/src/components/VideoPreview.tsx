import { Download, RefreshCw } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'

interface VideoPreviewProps {
  projectId: string
  videoVersion?: string
}

export default function VideoPreview({ projectId, videoVersion }: VideoPreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const [cacheNonce, setCacheNonce] = useState<number>(() => Date.now())

  useEffect(() => {
    setCacheNonce(Date.now())
  }, [videoVersion])

  const bust = useMemo(() => `v=${encodeURIComponent(videoVersion || String(cacheNonce))}`, [videoVersion, cacheNonce])

  const previewUrl = `/api/projects/${projectId}/video?type=preview&${bust}`
  const finalUrl = `/api/projects/${projectId}/video?type=final&${bust}`
  const midiUrl = `/api/projects/${projectId}/midi`

  const downloadLink = (url: string, filename: string) => {
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
  }

  const reloadPreview = () => {
    setCacheNonce(Date.now())
    if (videoRef.current) {
      videoRef.current.pause()
      videoRef.current.load()
    }
  }

  return (
    <div className="space-y-4">
      <div className="relative bg-gray-900 rounded-xl overflow-hidden border border-gray-800">
         <video
          ref={videoRef}
          src={previewUrl}
          className="w-full"
          controls
        />
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          onClick={reloadPreview}
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
        >
          <RefreshCw size={14} /> Refresh Preview
        </button>
        <button
          onClick={() =>
            downloadLink(previewUrl, `karaoke_preview_${projectId.slice(0, 8)}.mp4`)
          }
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
        >
          <Download size={14} /> Preview MP4
        </button>
        <button
          onClick={() =>
            downloadLink(finalUrl, `karaoke_final_${projectId.slice(0, 8)}.mp4`)
          }
          className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded-lg text-sm transition-colors"
        >
          <Download size={14} /> Final MP4
        </button>
        <button
          onClick={() =>
            downloadLink(midiUrl, `melody_${projectId.slice(0, 8)}.mid`)
          }
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
        >
          <Download size={14} /> MIDI
        </button>
        <button
          onClick={() =>
            downloadLink(
              `/api/projects/${projectId}/artifacts/edited_lyrics_json`,
              `timing_${projectId.slice(0, 8)}.json`
            )
          }
          className="flex items-center gap-2 px-4 py-2 bg-gray-800 hover:bg-gray-700 rounded-lg text-sm transition-colors"
        >
          <Download size={14} /> Timing JSON
        </button>
      </div>
    </div>
  )
}
