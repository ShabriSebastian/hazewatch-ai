/**
 * The map projection, shared by every layer that draws on a map.
 *
 * There is exactly one of these. Institution markers, hotspot cells, the
 * coastline and the labels all come through `project()`, so a point cannot be
 * drawn in one place while the land under it is drawn in another.
 *
 * That used to be untrue. The data was projected and the basemap was two CSS
 * blobs with four labels positioned by eye; Kuching's label sat 37 percentage
 * points from where its own coordinates project to, which is why hotspots
 * appeared to float in the sea. The sea was a rounded div.
 *
 * The bounding box and the coastline path live in `basemap.generated.ts`,
 * written by `scripts/15_build_basemap.py` from Natural Earth. They are emitted
 * together by one run of one script, so the projection here and the geometry
 * there cannot drift apart. Regenerate with `make basemap`.
 */

import { MAP_BBOX } from "./basemap.generated";

export {
  COASTLINE_PATH,
  MAP_ASPECT,
  MAP_BBOX,
  REGION_LABELS,
  CITY_LABELS,
} from "./basemap.generated";

export interface MapPoint {
  x: number;
  y: number;
}

/**
 * Equirectangular, into percentages of the map box.
 *
 * Undistorted only if the container is rendered at `MAP_ASPECT` — a degree of
 * longitude and a degree of latitude are the same distance at this latitude, so
 * the box's own ratio is the one to render at. Both maps set it; see the
 * `aspect-[…]` class on their containers.
 *
 * Deliberately NOT clamped. The old version clamped into [2,98]×[3,97], which
 * silently piled anything off-map onto the edges as phantom hotspots. Callers
 * filter with `withinMapBounds` first, which drops those points instead of
 * lying about where they are.
 */
export function project(lon: number, lat: number): MapPoint {
  return {
    x: ((lon - MAP_BBOX.lonMin) / (MAP_BBOX.lonMax - MAP_BBOX.lonMin)) * 100,
    y: (1 - (lat - MAP_BBOX.latMin) / (MAP_BBOX.latMax - MAP_BBOX.latMin)) * 100,
  };
}

export function withinMapBounds(lon: number, lat: number): boolean {
  return (
    lon >= MAP_BBOX.lonMin
    && lon <= MAP_BBOX.lonMax
    && lat >= MAP_BBOX.latMin
    && lat <= MAP_BBOX.latMax
  );
}

/**
 * A curved arrow between two projected points, as an SVG path.
 *
 * Replaces a hardcoded cubic that pointed wherever it was drawn to point. The
 * control point is offset perpendicular to the line so the curve bows
 * consistently whichever way the transport runs.
 */
export function transportArc(
  from: MapPoint,
  to: MapPoint,
  { bow = 0.18, inset = 0.1 }: { bow?: number; inset?: number } = {},
): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;

  // Both ends are pulled back along the line. The anchors are label points, and
  // an arc that runs the full distance starts and ends underneath the words it
  // is drawn between - the arrowhead in particular landed on top of "SARAWAK".
  const sx = from.x + dx * inset;
  const sy = from.y + dy * inset;
  const ex = to.x - dx * inset;
  const ey = to.y - dy * inset;

  const mx = (sx + ex) / 2;
  const my = (sy + ey) / 2;
  return `M${sx.toFixed(2)},${sy.toFixed(2)} Q${(mx - dy * bow).toFixed(2)},${(my + dx * bow).toFixed(2)} ${ex.toFixed(2)},${ey.toFixed(2)}`;
}
