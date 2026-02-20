/**
 * SplashScreen - Initial loading screen with logo
 * Replaces the old "Connecting to trading server..." text
 */
import { useEffect, useState, useRef } from 'react'

interface SplashScreenProps {
  onComplete: () => void
  minDuration?: number
}

export default function SplashScreen({ onComplete, minDuration = 1500 }: SplashScreenProps) {
  const [progress, setProgress] = useState(0)
  const completedRef = useRef(false)
  const onCompleteRef = useRef(onComplete)

  // Keep ref updated but don't trigger effect
  useEffect(() => {
    onCompleteRef.current = onComplete
  }, [onComplete])

  useEffect(() => {
    const startTime = Date.now()
    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime
      const newProgress = Math.min((elapsed / minDuration) * 100, 100)
      setProgress(newProgress)

      if (elapsed >= minDuration && !completedRef.current) {
        completedRef.current = true
        clearInterval(interval)
        onCompleteRef.current()
      }
    }, 50)

    return () => clearInterval(interval)
  }, [minDuration]) // Only depend on minDuration, not onComplete

  return (
    <div className="fixed inset-0 bg-background flex flex-col items-center justify-center z-50">
      <div className="flex flex-col items-center space-y-6">
        {/* Logo */}
        <img
          src="/static/arena_logo_app_small.png"
          alt="Hyper Alpha Arena"
          className="w-24 h-24 object-contain"
        />

        {/* Title */}
        <h1 className="text-2xl font-bold text-foreground">
          Hyper Alpha Arena
        </h1>

        {/* Progress bar */}
        <div className="w-48 h-1 bg-muted rounded-full overflow-hidden">
          <div
            className="h-full bg-primary transition-all duration-100 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>
    </div>
  )
}
