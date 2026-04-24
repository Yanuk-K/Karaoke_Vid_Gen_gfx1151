import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ProjectList from '@/pages/ProjectList'
import Upload from '@/pages/Upload'
import ProjectDetail from '@/pages/ProjectDetail'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 3000,
    },
  },
})

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <div className="min-h-screen bg-gray-950">
          <header className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-10">
            <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-3">
              <div className="text-indigo-400 font-bold text-lg">
                🎤 Karaoke Generator
              </div>
            </div>
          </header>
          <main className="px-4 py-6">
            <Routes>
              <Route path="/" element={<ProjectList />} />
              <Route path="/upload" element={<Upload />} />
              <Route path="/project/:id" element={<ProjectDetail />} />
            </Routes>
          </main>
        </div>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
