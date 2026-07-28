/**
 * Theme Provider — Manages dark/light theme across the app.
 * Reads theme from UIStore and applies 'dark' class to <html>.
 * Also handles system preference detection on first visit.
 */

import { useEffect, type ReactNode } from 'react'
import { useUIStore } from '@/stores/uiStore'

interface ThemeProviderProps {
  children: ReactNode
}

/**
 * Wrap the app root with this to enable theme switching.
 * Applies theme class to document.documentElement automatically.
 */
export function ThemeProvider({ children }: ThemeProviderProps) {
  const { theme, setTheme } = useUIStore()

  useEffect(() => {
    // On first mount: check system preference if no stored preference
    const stored = localStorage.getItem('aca:theme')
    if (!stored) {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
      setTheme(prefersDark ? 'dark' : 'light')
    } else {
      // Apply stored theme
      document.documentElement.classList.toggle('dark', theme === 'dark')
    }
  }, [])

  useEffect(() => {
    // Apply theme class whenever theme changes
    document.documentElement.classList.toggle('dark', theme === 'dark')
    console.debug('[Theme] Applied theme:', theme)
  }, [theme])

  return <>{children}</>
}
