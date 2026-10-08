import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react'
import { createPortal } from 'react-dom'

interface Props {
  id: string
  label: string
  anchor: RefObject<HTMLButtonElement | null>
  onClose: () => void
  children: ReactNode
  centered?: boolean
}

/** Calendars use a centered dialog; searchable choices stay beside their trigger. */
export function FilterPopover({ id, label, anchor, onClose, children, centered = false }: Props) {
  const panel = useRef<HTMLDivElement>(null)
  const [position, setPosition] = useState({ top: 0, left: 0 })
  useLayoutEffect(() => {
    if (centered) {
      const viewport = window.visualViewport
      const place = () => {
        if (!panel.current || !viewport) return
        const style = panel.current.style
        style.setProperty('--dialog-viewport-height', `${viewport.height}px`)
        style.setProperty('--dialog-viewport-width', `${viewport.width}px`)
        // A phone keyboard can shrink/pan the visible viewport without changing the page layout.
        const shifted = viewport.height < window.innerHeight - 1 || viewport.width < window.innerWidth - 1 || viewport.offsetTop > 0 || viewport.offsetLeft > 0
        if (shifted) {
          style.setProperty('--dialog-center-x', `${viewport.offsetLeft + viewport.width / 2}px`)
          style.setProperty('--dialog-center-y', `${viewport.offsetTop + viewport.height / 2}px`)
        } else {
          style.removeProperty('--dialog-center-x'); style.removeProperty('--dialog-center-y')
        }
      }
      place()
      viewport?.addEventListener('resize', place)
      viewport?.addEventListener('scroll', place)
      return () => { viewport?.removeEventListener('resize', place); viewport?.removeEventListener('scroll', place) }
    }
    const place = () => {
      const bounds = anchor.current?.getBoundingClientRect()
      if (!bounds || !panel.current) return
      const width = panel.current.offsetWidth
      const height = panel.current.offsetHeight
      setPosition({ left: Math.max(12, Math.min(bounds.left, window.innerWidth - width - 12)),
        top: Math.max(12, Math.min(bounds.bottom + 8, window.innerHeight - height - 12)) })
    }
    place()
    const observer = new ResizeObserver(place)
    if (panel.current) observer.observe(panel.current)
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => { observer.disconnect(); window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true) }
  }, [anchor, centered])
  useEffect(() => {
    const trigger = anchor.current
    const previousOverflow = document.body.style.overflow
    const mobile = window.matchMedia('(max-width: 639px)')
    const syncScrollLock = () => { document.body.style.overflow = centered || mobile.matches ? 'hidden' : previousOverflow }
    syncScrollLock()
    mobile.addEventListener('change', syncScrollLock)
    const frame = requestAnimationFrame(() => (panel.current?.querySelector<HTMLElement>('[data-autofocus]') ?? panel.current?.querySelector<HTMLElement>('button, input'))?.focus())
    const dismiss = (event: PointerEvent) => {
      if (!panel.current?.contains(event.target as Node) && !trigger?.contains(event.target as Node)) onClose()
    }
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); onClose() }
      if (event.key !== 'Tab') return
      const items = [...panel.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]') ?? []]
        .filter((element) => element.tabIndex >= 0 && element.getClientRects().length > 0)
      const first = items[0], last = items.at(-1)
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
    }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', keyboard, true)
    return () => {
      cancelAnimationFrame(frame)
      mobile.removeEventListener('change', syncScrollLock)
      document.body.style.overflow = previousOverflow
      document.removeEventListener('pointerdown', dismiss)
      document.removeEventListener('keydown', keyboard, true)
      const returnTarget = trigger?.getClientRects().length ? trigger
        : trigger?.closest('[data-filter-container]')?.querySelector<HTMLElement>('[data-filter-toggle]')
      returnTarget?.focus({ preventScroll: true })
    }
  }, [anchor, onClose, centered])
  return createPortal(<>
    <div className={`filter-popover-backdrop ${centered ? 'filter-dialog-backdrop' : ''}`} aria-hidden="true" />
    <div ref={panel} id={id} role="dialog" aria-modal="true" aria-label={label}
      className={`filter-popover ${centered ? 'filter-dialog' : ''}`} style={centered ? undefined : position}>
      {children}
    </div>
  </>, document.body)
}
