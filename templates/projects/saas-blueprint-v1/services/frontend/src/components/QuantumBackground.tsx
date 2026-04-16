import { useRef, useEffect } from 'react'

interface Pt {
  x: number; y: number; vx: number; vy: number
  r: number; color: string
}

function getCSSColor(n: number): string {
  const v = getComputedStyle(document.documentElement)
    .getPropertyValue(`--color-${n}`).trim()
  return v || ['#297BFF', '#0CC02A', '#005F61', '#6F74B8'][n - 1] || '#297BFF'
}

export default function QuantumBackground() {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    // Alias tipado como non-null para uso em closures (TS não propaga narrowing em funções internas)
    const el = canvas as HTMLCanvasElement
    const ctx = canvas.getContext('2d')!

    const resize = () => {
      canvas.width  = window.innerWidth
      canvas.height = window.innerHeight
    }
    resize()
    window.addEventListener('resize', resize)

    // Lê CSS vars ao montar (depois do ThemeContext aplicar as cores do tenant)
    const COLORS = [1, 2, 3, 4, 5].map(getCSSColor)

    const COUNT = 80
    let pts: Pt[] = Array.from({ length: COUNT }, () => ({
      x:     Math.random() * canvas.width,
      y:     Math.random() * canvas.height,
      vx:    (Math.random() - 0.5) * 0.6,
      vy:    (Math.random() - 0.5) * 0.6,
      r:     Math.random() * 2 + 1,
      color: COLORS[Math.floor(Math.random() * COLORS.length)],
    }))

    const MAX_DIST = 150
    let animId: number

    function draw() {
      ctx.clearRect(0, 0, el.width, el.height)

      // Move + bounce
      for (const p of pts) {
        p.x += p.vx; p.y += p.vy
        if (p.x < 0 || p.x > el.width)  p.vx *= -1
        if (p.y < 0 || p.y > el.height) p.vy *= -1
      }

      // Connection lines
      for (let i = 0; i < pts.length; i++) {
        for (let j = i + 1; j < pts.length; j++) {
          const dx = pts[i].x - pts[j].x
          const dy = pts[i].y - pts[j].y
          const d  = Math.sqrt(dx * dx + dy * dy)
          if (d < MAX_DIST) {
            ctx.beginPath()
            ctx.strokeStyle = `rgba(255,255,255,${0.12 * (1 - d / MAX_DIST)})`
            ctx.lineWidth   = 0.8
            ctx.moveTo(pts[i].x, pts[i].y)
            ctx.lineTo(pts[j].x, pts[j].y)
            ctx.stroke()
          }
        }
      }

      // Dots
      for (const p of pts) {
        ctx.beginPath()
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2)
        ctx.fillStyle = p.color
        ctx.shadowColor = p.color
        ctx.shadowBlur  = 6
        ctx.fill()
      }
      ctx.shadowBlur = 0

      animId = requestAnimationFrame(draw)
    }

    draw()

    return () => {
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 0,
        pointerEvents: 'none',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)',
      }}
    />
  )
}
