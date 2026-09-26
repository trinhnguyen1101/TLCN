import { memo, useEffect, useState } from 'react'
import { GeoJSON, Pane, type GeoJSONProps } from 'react-leaflet'
import type { PolylineOptions } from 'leaflet'

const worldStyle: PolylineOptions = {
  className: 'fill-map-land stroke-map-country-border',
  weight: 1,
  opacity: 1,
  fillOpacity: 1,
  // Shared borders use the same vertices as the province layer; do not simplify them again.
  smoothFactor: 0,
}

// Share the request across remounts (including StrictMode) and retain parsed geometry.
let worldDataRequest: Promise<GeoJSONProps['data']> | undefined

function loadWorldCountries() {
  worldDataRequest ??= fetch(`${import.meta.env.BASE_URL}data/world-countries.geojson`)
    .then(async (response) => {
      if (!response.ok) throw new Error('Cannot load world boundaries')
      return (await response.json()) as GeoJSONProps['data']
    })
    .catch((error: unknown) => {
      worldDataRequest = undefined
      throw error
    })
  return worldDataRequest
}

// This layer is outside the province-selection key; memo skips unrelated dashboard renders.
export const WorldBasemap = memo(function WorldBasemap() {
  const [countries, setCountries] = useState<GeoJSONProps['data'] | null>(null)

  useEffect(() => {
    let active = true
    loadWorldCountries()
      .then((data) => { if (active) setCountries(data) })
      // The decorative background must not block province data or dashboard controls.
      .catch(() => {})
    return () => { active = false }
  }, [])

  if (!countries) return null

  return (
    <Pane name="world-countries" className="pointer-events-none z-[200]">
      <GeoJSON
        data={countries}
        pane="world-countries"
        style={worldStyle}
        interactive={false}
        bubblingMouseEvents={false}
      />
    </Pane>
  )
})
