import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import ErrorBoundary from './components/ErrorBoundary.tsx'
import { migrateSoriMemoStorage } from './lib/storageMigration'

window.addEventListener('error', event => {
  const message = event.error instanceof Error ? event.error.message : event.message
  sessionStorage.setItem('sorimemo_last_ui_error', message || 'Unknown UI error')
})

window.addEventListener('unhandledrejection', event => {
  const reason = event.reason
  const message = reason instanceof Error ? reason.message : String(reason || 'Unknown async error')
  sessionStorage.setItem('sorimemo_last_ui_error', message)
})

migrateSoriMemoStorage()

createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
)
