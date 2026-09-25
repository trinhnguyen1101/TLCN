interface SkeletonProps {
  className?: string
  animated?: boolean
}

export function Skeleton({ className = '', animated = true }: SkeletonProps) {
  return <span aria-hidden="true" className={`block max-w-full rounded-md bg-border/60 ${animated ? 'animate-pulse motion-reduce:animate-none' : ''} ${className}`} />
}
