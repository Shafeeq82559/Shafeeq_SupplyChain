import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './pages.css'
import './cases.css'
import './prioritize.css'
import './evaluation.css'
import './evidence.css'
import './deepcheck.css'
import App from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
