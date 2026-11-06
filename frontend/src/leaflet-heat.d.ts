declare module 'leaflet.heat' {
  import { Layer } from 'leaflet'
  export class HeatLayer extends Layer {
    constructor(points: [number, number, number][], options?: Record<string, unknown>)
  }
}
