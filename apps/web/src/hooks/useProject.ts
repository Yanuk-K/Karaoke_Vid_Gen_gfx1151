import { useQuery, useQueryClient } from '@tanstack/react-query'
import { getProject, getTiming, patchTiming, getLyrics, patchLyrics } from '@/lib/api'
import type { TimingData } from '@/types/api'

const POLL_INTERVAL = 3000

export function useProject(id: string) {
  return useQuery({
    queryKey: ['project', id],
    queryFn: () => getProject(id),
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && data.status === 'running') return POLL_INTERVAL
      return false
    },
    staleTime: 2000,
  })
}

export function useTiming(id: string) {
  return useQuery({
    queryKey: ['timing', id],
    queryFn: () => getTiming(id),
    retry: 0,
    staleTime: 5000,
    refetchOnWindowFocus: false,
  })
}

export function useTimingUpdate(id: string) {
  const qc = useQueryClient()

  return {
    update: async (timing: TimingData) => {
      await patchTiming(id, timing)
      await qc.invalidateQueries({ queryKey: ['project', id] })
      await qc.invalidateQueries({ queryKey: ['timing', id] })
    },
  }
}

export function useLyrics(id: string) {
  return useQuery({
    queryKey: ['lyrics', id],
    queryFn: () => getLyrics(id),
    retry: 0,
    staleTime: 5000,
    refetchOnWindowFocus: false,
  })
}

export function useLyricsUpdate(id: string) {
  const qc = useQueryClient()

  return {
    update: async (lyricsText: string) => {
      await patchLyrics(id, lyricsText)
      await qc.invalidateQueries({ queryKey: ['project', id] })
      await qc.invalidateQueries({ queryKey: ['lyrics', id] })
      await qc.invalidateQueries({ queryKey: ['timing', id] })
    },
  }
}
