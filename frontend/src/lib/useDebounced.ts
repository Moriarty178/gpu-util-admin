import { useEffect, useRef, useState } from 'react'

/** Giá trị cục bộ cập nhật ngay (UI mượt), gọi `commit` sau `delay` ms kể từ lần đổi cuối (PLAN §8.2: 300 ms). */
export function useDebouncedValue<T>(external: T, commit: (v: T) => void, delay = 300): [T, (v: T) => void] {
  const [local, setLocal] = useState(external)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const commitRef = useRef(commit)
  commitRef.current = commit

  useEffect(() => {
    setLocal(external)
  }, [external])

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current)
    },
    [],
  )

  const set = (v: T) => {
    setLocal(v)
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => commitRef.current(v), delay)
  }
  return [local, set]
}
