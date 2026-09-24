import assert from 'node:assert/strict'
import { mkdir, readdir, readFile, writeFile } from 'node:fs/promises'

const sourceRoot = new URL('../../data/landing/reference/vietnamese-provinces-database/json/', import.meta.url)
const output = new URL('../public/data/vietnam-provinces.geojson', import.meta.url)
const readJson = async (url) => JSON.parse((await readFile(url, 'utf8')).replace(/^\uFEFF/, ''))
const directories = (await readdir(new URL('geojson/', sourceRoot), { withFileTypes: true }))
  .filter((entry) => entry.isDirectory())
  .sort((a, b) => a.name.localeCompare(b.name))
const codes = new Set()
const features = []

for (const { name } of directories) {
  // Only province files are needed; do not bundle ward boundaries.
  const collection = await readJson(new URL(`geojson/${name}/${name}.geojson`, sourceRoot))
  assert.equal(collection.type, 'FeatureCollection', `${name}: expected a FeatureCollection`)
  assert.equal(collection.features.length, 1, `${name}: expected one province`)
  const { id, geometry, properties } = collection.features[0]
  assert.equal(id, name.split('_')[0], `${name}: province code mismatch`)
  assert.equal(properties.code, id, `${name}: property code mismatch`)
  assert(!codes.has(id), `${name}: duplicate province code`)
  codes.add(id)
  assert.equal(geometry.type, 'MultiPolygon', `${name}: expected province polygons`)
  assert(geometry.coordinates.length > 0, `${name}: empty boundary`)
  for (const polygon of geometry.coordinates) {
    assert(polygon.length > 0, `${name}: empty polygon`)
    for (const ring of polygon) {
      assert(ring.length >= 4, `${name}: invalid boundary ring`)
      assert.deepEqual(ring[0], ring.at(-1), `${name}: unclosed boundary ring`)
      for (const [longitude, latitude] of ring) {
        assert(Number.isFinite(longitude) && longitude >= -180 && longitude <= 180, `${name}: invalid longitude`)
        assert(Number.isFinite(latitude) && latitude >= -90 && latitude <= 90, `${name}: invalid latitude`)
      }
    }
  }
  const { code, name: provinceName, nameEn, fullName, fullNameEn, codeName, areaKm2 } = properties
  // Preserve every coordinate, polygon, island, and interior ring unchanged.
  features.push({ type: 'Feature', id, properties: { code, name: provinceName, nameEn, fullName, fullNameEn, codeName, areaKm2 }, geometry })
}

assert(features.length > 0, 'No province boundaries found')
const provinces = await readJson(new URL('simplified_json_generated_data_vn_units.json', sourceRoot))
assert.deepEqual([...codes].sort(), provinces.map((province) => province.Code).sort(), 'Missing province boundaries')
await mkdir(new URL('.', output), { recursive: true })
const content = JSON.stringify({ type: 'FeatureCollection', features }) + '\n'
await writeFile(output, content, 'utf8')
console.log(`Synced ${features.length} province boundaries (${Buffer.byteLength(content)} bytes) to public/data/vietnam-provinces.geojson`)
