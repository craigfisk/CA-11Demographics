<template>
  <div class="map-container">
    <div v-if="loading" class="loading">Loading map…</div>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="controls">
      <label :class="{ active: layer === 'district' }" @click="setLayer('district')">
        <span class="swatch district-swatch"></span> District outline
      </label>
      <label :class="{ active: layer === 'hispanic' }" @click="setLayer('hispanic')">
        <span class="swatch hispanic-swatch"></span> Spanish-speaking (% Hispanic/Latino)
      </label>
      <label :class="{ active: layer === 'young' }" @click="setLayer('young')">
        <span class="swatch young-swatch"></span> Young voters (% age 18–34)
      </label>
      <label :class="{ active: layer === 'democrat' }" @click="setLayer('democrat')">
        <span class="swatch democrat-swatch"></span> Registered Democrats (% of voters)
      </label>
      <label :class="{ active: layer === 'npp' }" @click="setLayer('npp')">
        <span class="swatch npp-swatch"></span> No Party Preference (% of voters)
      </label>
      <label :class="{ active: layer === 'republican' }" @click="setLayer('republican')">
        <span class="swatch republican-swatch"></span> Registered Republicans (% of voters)
      </label>
    </div>

    <div id="ca-map" ref="mapEl"></div>

    <div v-if="layer !== 'district'" class="legend">
      <div class="legend-title">
        {{ layer === 'hispanic'   ? '% Hispanic/Latino'
         : layer === 'young'      ? '% age 18–34'
         : layer === 'democrat'   ? '% Registered Democrat'
         : layer === 'republican' ? '% Registered Republican'
         :                          '% No Party Preference' }}
      </div>
      <div class="legend-scale">
        <span v-for="item in activeLegend" :key="item.label" class="legend-item">
          <span class="legend-color" :style="{ background: item.color }"></span>
          {{ item.label }}
        </span>
      </div>
      <div class="legend-note">
        {{ layer === 'hispanic' ? 'Source: ACS 2023 5-yr, Census tracts within CA-11'
         : layer === 'young'    ? 'Source: ACS 2023 5-yr, voting-age pop.'
         :                        'Source: CA Secretary of State Report of Registration' }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

type LayerName = 'district' | 'hispanic' | 'young' | 'democrat' | 'npp' | 'republican'

const mapEl = ref<HTMLElement | null>(null)
const loading = ref(true)
const error = ref('')
const layer = ref<LayerName>('district')

let map: L.Map | null = null
let districtLayer: L.GeoJSON | null = null
let hispanicLayer: L.GeoJSON | null = null
let youngLayer: L.GeoJSON | null = null
let democratLayer: L.GeoJSON | null = null
let nppLayer: L.GeoJSON | null = null
let republicanLayer: L.GeoJSON | null = null
let demoData: any = null
let voterData: any = null

// Color scales
const hispanicBreaks = [0, 5, 10, 20, 35, 100]
const hispanicColors = ['#fff5f0', '#fca082', '#fb5b34', '#cb1a1c', '#67000d']

const youngBreaks = [0, 10, 15, 20, 25, 100]
const youngColors  = ['#f7fbff', '#9ecae1', '#4292c6', '#2171b5', '#084594']

const demBreaks = [0, 40, 50, 55, 65, 100]
const demColors = ['#edf8e9', '#bae4b3', '#74c476', '#31a354', '#006d2c']

const nppBreaks = [0, 20, 25, 30, 35, 100]
const nppColors = ['#feedde', '#fdbe85', '#fd8d3c', '#e6550d', '#a63603']

const repBreaks = [0, 10, 20, 30, 40, 100]
const repColors = ['#fee5d9', '#fcbba1', '#fc9272', '#fb6a4a', '#cb181d']

function colorFor(value: number, breaks: number[], colors: string[]): string {
  for (let i = 0; i < breaks.length - 1; i++) {
    if (value < breaks[i + 1]) return colors[i]
  }
  return colors[colors.length - 1]
}

const activeLegend = computed(() => {
  const [breaks, colors] =
    layer.value === 'hispanic'     ? [hispanicBreaks, hispanicColors]
    : layer.value === 'young'      ? [youngBreaks,    youngColors]
    : layer.value === 'democrat'   ? [demBreaks,      demColors]
    : layer.value === 'republican' ? [repBreaks,      repColors]
    :                                [nppBreaks,      nppColors]
  return colors.map((c, i) => ({
    color: c,
    label: `${breaks[i]}–${breaks[i + 1]}%`,
  }))
})

function buildDemoLayers() {
  if (!map) return

  if (demoData) {
    hispanicLayer = L.geoJSON(demoData, {
      style: (f) => ({
        fillColor: colorFor(f?.properties.pct_hispanic ?? 0, hispanicBreaks, hispanicColors),
        fillOpacity: 0.75,
        color: '#666',
        weight: 0.5,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties
        l.bindTooltip(
          `<strong>Tract ${p.TRACT}</strong><br>` +
          `Hispanic/Latino: <b>${p.pct_hispanic}%</b><br>` +
          `Spanish-speaking: <b>${p.pct_spanish}%</b><br>` +
          `Pop: ${p.total_pop.toLocaleString()}`,
          { sticky: true }
        )
      },
    })

    youngLayer = L.geoJSON(demoData, {
      style: (f) => ({
        fillColor: colorFor(f?.properties.pct_young ?? 0, youngBreaks, youngColors),
        fillOpacity: 0.75,
        color: '#666',
        weight: 0.5,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties
        l.bindTooltip(
          `<strong>Tract ${p.TRACT}</strong><br>` +
          `Age 18–34: <b>${p.pct_young}%</b><br>` +
          `Pop: ${p.total_pop.toLocaleString()}`,
          { sticky: true }
        )
      },
    })
  }

  if (voterData) {
    democratLayer = L.geoJSON(voterData, {
      style: (f) => ({
        fillColor: f?.properties.pct_dem != null
          ? colorFor(f.properties.pct_dem, demBreaks, demColors)
          : '#ccc',
        fillOpacity: 0.75,
        color: '#666',
        weight: 0.5,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties
        l.bindTooltip(
          `<strong>${p.place}</strong><br>` +
          (p.pct_dem != null
            ? `Registered Democrat: <b>${p.pct_dem}%</b>`
            : 'No data'),
          { sticky: true }
        )
      },
    })

    nppLayer = L.geoJSON(voterData, {
      style: (f) => ({
        fillColor: f?.properties.pct_npp != null
          ? colorFor(f.properties.pct_npp, nppBreaks, nppColors)
          : '#ccc',
        fillOpacity: 0.75,
        color: '#666',
        weight: 0.5,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties
        l.bindTooltip(
          `<strong>${p.place}</strong><br>` +
          (p.pct_npp != null
            ? `No Party Preference: <b>${p.pct_npp}%</b>`
            : 'No data'),
          { sticky: true }
        )
      },
    })

    republicanLayer = L.geoJSON(voterData, {
      style: (f) => ({
        fillColor: f?.properties.pct_rep != null
          ? colorFor(f.properties.pct_rep, repBreaks, repColors)
          : '#ccc',
        fillOpacity: 0.75,
        color: '#666',
        weight: 0.5,
      }),
      onEachFeature: (f, l) => {
        const p = f.properties
        l.bindTooltip(
          `<strong>${p.place}</strong><br>` +
          (p.pct_rep != null
            ? `Registered Republican: <b>${p.pct_rep}%</b>`
            : 'No data'),
          { sticky: true }
        )
      },
    })
  }
}

function setLayer(name: LayerName) {
  if (!map) return
  layer.value = name
  hispanicLayer?.remove()
  youngLayer?.remove()
  democratLayer?.remove()
  nppLayer?.remove()
  republicanLayer?.remove()
  districtLayer?.remove()

  if (name === 'district') {
    districtLayer?.addTo(map)
  } else if (name === 'hispanic') {
    hispanicLayer?.addTo(map)
    districtLayer?.addTo(map)
  } else if (name === 'young') {
    youngLayer?.addTo(map)
    districtLayer?.addTo(map)
  } else if (name === 'democrat') {
    democratLayer?.addTo(map)
    districtLayer?.addTo(map)
  } else if (name === 'npp') {
    nppLayer?.addTo(map)
    districtLayer?.addTo(map)
  } else if (name === 'republican') {
    republicanLayer?.addTo(map)
    districtLayer?.addTo(map)
  }
}

watch(layer, setLayer)

onMounted(async () => {
  if (!mapEl.value) return

  map = L.map(mapEl.value).setView([37.76, -122.44], 12)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    maxZoom: 18,
  }).addTo(map)

  try {
    const [districtRes, demoRes] = await Promise.all([
      fetch('/ca11.geojson'),
      fetch('/ca11-demo.geojson'),
    ])
    if (!districtRes.ok) throw new Error(`district HTTP ${districtRes.status}`)
    if (!demoRes.ok)     throw new Error(`demo HTTP ${demoRes.status}`)

    const districtGeojson = await districtRes.json()
    demoData = await demoRes.json()

    // Optional: load voter registration layer (generated by scripts/build_dem_layer.py)
    const voterRes = await fetch('/ca11-voters.geojson').catch(() => null)
    if (voterRes?.ok) voterData = await voterRes.json()

    districtLayer = L.geoJSON(districtGeojson, {
      style: { color: '#c0392b', weight: 3, fillOpacity: 0, interactive: false },
    })

    buildDemoLayers()
    setLayer('district')

    districtLayer!.addTo(map)
    map.fitBounds(districtLayer!.getBounds(), { padding: [30, 30] })

  } catch (e: any) {
    error.value = `Failed to load map data: ${e.message}`
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  map?.remove()
})
</script>

<style scoped>
.map-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  font-family: sans-serif;
}

.controls {
  display: flex;
  gap: 1rem;
  margin-bottom: 0.5rem;
  flex-wrap: wrap;
  justify-content: center;
}

.controls label {
  cursor: pointer;
  padding: 5px 12px;
  border-radius: 4px;
  border: 1px solid #ccc;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: 6px;
  user-select: none;
  background: #f9f9f9;
}

.controls label.active {
  border-color: #333;
  background: #fff;
  font-weight: 600;
}

.swatch {
  display: inline-block;
  width: 14px;
  height: 14px;
  border-radius: 2px;
}

.district-swatch  { background: #c0392b; }
.hispanic-swatch  { background: #fb5b34; }
.young-swatch     { background: #2171b5; }
.democrat-swatch  { background: #31a354; }
.npp-swatch       { background: #fd8d3c; }
.republican-swatch { background: #fb6a4a; }

#ca-map {
  width: 700px;
  height: 550px;
  border: 1px solid #ccc;
  border-radius: 4px;
}

.loading, .error { margin-bottom: 0.5rem; color: #555; }
.error { color: #c0392b; }

.legend {
  margin-top: 0.5rem;
  font-size: 12px;
  text-align: center;
}

.legend-title { font-weight: 600; margin-bottom: 4px; }

.legend-scale {
  display: flex;
  gap: 4px;
  justify-content: center;
  flex-wrap: wrap;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 3px;
}

.legend-color {
  display: inline-block;
  width: 16px;
  height: 12px;
  border: 1px solid #aaa;
}

.legend-note { color: #888; margin-top: 4px; font-size: 11px; }
</style>
