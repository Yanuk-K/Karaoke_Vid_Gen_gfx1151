interface SettingsPanelProps {
  countdownOffset: number
  nextLineLeadTime: number
  onCountdownChange: (val: number) => void
  onLeadTimeChange: (val: number) => void
}

export default function SettingsPanel({
  countdownOffset,
  nextLineLeadTime,
  onCountdownChange,
  onLeadTimeChange,
}: SettingsPanelProps) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
      <h3 className="text-sm font-medium text-gray-300">Display Settings</h3>

      <div className="space-y-3">
        <div>
          <label className="text-xs text-gray-500">
            Countdown offset (seconds before first lyric)
          </label>
          <input
            type="range"
            min="0"
            max="5"
            step="0.1"
            value={countdownOffset}
            onChange={(e) => onCountdownChange(parseFloat(e.target.value))}
            className="w-full mt-1 accent-indigo-500"
          />
          <div className="text-right text-xs text-indigo-400 mt-1">
            {countdownOffset.toFixed(1)}s
          </div>
        </div>

        <div>
          <label className="text-xs text-gray-500">
            Next line lead time (seconds early)
          </label>
          <input
            type="range"
            min="0.5"
            max="3"
            step="0.1"
            value={nextLineLeadTime}
            onChange={(e) => onLeadTimeChange(parseFloat(e.target.value))}
            className="w-full mt-1 accent-indigo-500"
          />
          <div className="text-right text-xs text-indigo-400 mt-1">
            {nextLineLeadTime.toFixed(1)}s
          </div>
        </div>
      </div>
    </div>
  )
}
