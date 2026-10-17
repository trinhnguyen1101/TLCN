import { useEffect, useRef, useState } from 'react'

let context: CanvasRenderingContext2D | null | undefined

export function chartTextWidth(text: string, fontSize = 12) {
  if (context === undefined) context = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d')
  if (!context) return text.length * fontSize * .65
  context.font = `500 ${fontSize}px Arial, sans-serif`
  return context.measureText(text).width + 2
}

export function wrapChartText(text: string, width: number) {
  const lines: string[] = []
  let line = ''
  for (const word of text.split(/\s+/)) {
    const next = line ? `${line} ${word}` : word
    if (chartTextWidth(next) <= width) {
      line = next
      continue
    }
    if (line) lines.push(line)
    line = ''
    for (const character of word) {
      if (line && chartTextWidth(line + character) > width) {
        lines.push(line)
        line = ''
      }
      line += character
    }
  }
  if (line) lines.push(line)
  return lines
}

export function useChartWidth(initialWidth: number) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(initialWidth)
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, entry.contentRect.width)))
    observer.observe(container)
    return () => observer.disconnect()
  }, [])
  return { containerRef, width }
}
