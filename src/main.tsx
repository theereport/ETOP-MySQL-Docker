import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
// Imported from their own files, not the './features/security-access'
// barrel - that barrel also statically re-exports SecurityAccessWorkspace,
// and this file (the app entry point) is always eagerly loaded, so a
// barrel import here would pull that lazy-loaded workspace back into the
// main bundle.
import AccessProvider from './features/security-access/AccessProvider'
import { installAuthenticatedFetch } from './features/security-access/authenticatedFetch'

installAuthenticatedFetch()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <AccessProvider>
      <App />
    </AccessProvider>
  </StrictMode>,
)
