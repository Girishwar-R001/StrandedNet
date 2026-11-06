import L from 'leaflet'
import { useEffect, useRef, useState } from 'react'
import { HeatLayer } from 'leaflet.heat'

export { L }

export const CITY_CENTRE: [number, number] = [12.965, 77.635]

/** Creates one Leaflet map for a container. Layers are managed by the caller in effects. */
export function useMap(zoom = 11) {
  const ref = useRef<HTMLDivElement>(null)
  const [map, setMap] = useState<L.Map | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const m = L.map(ref.current, { center: CITY_CENTRE, zoom, zoomSnap: 0.25, zoomControl: true, attributionControl: true })
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(m)
    setMap(m)
    const observer = new ResizeObserver(() => m.invalidateSize())
    observer.observe(ref.current)
    return () => {
      observer.disconnect()
      m.remove()
      setMap(null)
    }
  }, [zoom])

  return { ref, map }
}

export const heatLayer = (points: [number, number, number][], options: Record<string, unknown>): L.Layer =>
  new HeatLayer(points, options)
