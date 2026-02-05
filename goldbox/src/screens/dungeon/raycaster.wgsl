// ============================================================
// Gold Box Dungeon Raycaster — Compute Shader
// ============================================================
// Renders a raycasted dungeon view entirely in a compute pass.
// Map is a flat u32 grid. 0 = open, >0 = wall (value = texture index).
// Camera state and resolution are uniforms.
// Output is a write-only storage texture consumed by a blit render pass.
// ============================================================

// --- Uniforms ---
struct CameraState {
  position: vec2<f32>,   // world position
  angle:    f32,         // facing angle in radians
  fov:      f32,         // horizontal field of view in radians
  resolution: vec2<f32>, // framebuffer size in pixels (written as f32, cast to u32 where needed)
};

@group(0) @binding(0) var<uniform> camera: CameraState;

// --- Map data (flat buffer, row-major, width * height u32s) ---
struct MapParams {
  width:  u32,
  height: u32,
};

@group(0) @binding(1) var<uniform> mapParams: MapParams;
@group(0) @binding(2) var<storage, read> mapData: array<u32>;

// --- Output texture ---
@group(0) @binding(3) var outputTexture: texture_storage_2d<rgba8unorm, write>;

// --- Palette: wall colors indexed by tile value ---
// Value 0 = open (should never hit), 1..N = wall types
fn wallColor(tileValue: u32, shade: f32) -> vec4<f32> {
  // Base colors per wall type (mod-wrapped for safety)
  let idx = (tileValue - 1u) % 4u;
  var base: vec3<f32>;
  switch(idx) {
    case 0: { base = vec3<f32>(0.55, 0.45, 0.30); } // sandstone
    case 1: { base = vec3<f32>(0.35, 0.35, 0.50); } // dark stone
    case 2: { base = vec3<f32>(0.50, 0.30, 0.20); } // wood
    default: { base = vec3<f32>(0.25, 0.40, 0.25); } // mossy
  }
  // Apply distance shading (shade = 0 far, 1 close)
  return vec4<f32>(base * shade, 1.0);
}

fn floorColor(shade: f32) -> vec4<f32> {
  return vec4<f32>(vec3<f32>(0.18, 0.16, 0.14) * shade, 1.0);
}

fn ceilColor(shade: f32) -> vec4<f32> {
  return vec4<f32>(vec3<f32>(0.22, 0.20, 0.24) * shade, 1.0);
}

// --- Map lookup (bounds-checked) ---
fn getMapTile(x: i32, y: i32) -> u32 {
  if (x < 0 || y < 0 || u32(x) >= mapParams.width || u32(y) >= mapParams.height) {
    return 1u; // out of bounds = wall
  }
  return mapData[u32(y) * mapParams.width + u32(x)];
}

// --- DDA Ray March ---
// Returns: distance to wall hit, tile value of the wall, and which face was hit (0=x, 1=y)
struct RayHit {
  distance:  f32,
  tileValue: u32,
  face:      u32,   // 0 = hit on X axis, 1 = hit on Y axis
}

fn castRay(origin: vec2<f32>, direction: vec2<f32>) -> RayHit {
  // Current grid cell
  var cellX: i32 = i32(floor(origin.x));
  var cellY: i32 = i32(floor(origin.y));

  // How far along the ray to cross one full cell in X or Y
  let deltaDist = vec2<f32>(abs(1.0 / direction.x), abs(1.0 / direction.y));

  // Step direction in grid
  let stepX: i32 = select(-1i, 1i, direction.x > 0.0);
  let stepY: i32 = select(-1i, 1i, direction.y > 0.0);

  // Distance to the first X and Y cell boundary (always positive)
  var tMaxX: f32 = select(
    (origin.x - f32(cellX)) * deltaDist.x,     // dir.x < 0: boundary is at cellX
    (f32(cellX + 1) - origin.x) * deltaDist.x, // dir.x > 0: boundary is at cellX+1
    direction.x > 0.0
  );
  var tMaxY: f32 = select(
    (origin.y - f32(cellY)) * deltaDist.y,     // dir.y < 0: boundary is at cellY
    (f32(cellY + 1) - origin.y) * deltaDist.y, // dir.y > 0: boundary is at cellY+1
    direction.y > 0.0
  );

  var face: u32 = 0u;

  // March — max 64 steps (map won't be larger than this)
  for (var i = 0u; i < 64u; i++) {
    if (tMaxX < tMaxY) {
      cellX += stepX;
      face = 0u;
      let tile = getMapTile(cellX, cellY);
      if (tile != 0u) {
        return RayHit(tMaxX, tile, face);
      }
      tMaxX += deltaDist.x;
    } else {
      cellY += stepY;
      face = 1u;
      let tile = getMapTile(cellX, cellY);
      if (tile != 0u) {
        return RayHit(tMaxY, tile, face);
      }
      tMaxY += deltaDist.y;
    }
  }

  // No hit within step limit — return distant wall
  return RayHit(64.0, 1u, 0u);
}

// --- Main compute entry ---
@compute @workgroup_size(64, 1, 1)
fn main(@builtin(global_invocation_id) id: vec3<u32>) {
  let col = id.x;
  let resX = u32(camera.resolution.x);
  let resY = u32(camera.resolution.y);
  let screenWidth  = camera.resolution.x;
  let screenHeight = camera.resolution.y;

  if (col >= resX) { return; }

  // Angle for this column
  let halfFov = camera.fov * 0.5;
  let colAngle = camera.angle - halfFov + (f32(col) / screenWidth) * camera.fov;

  let dir = vec2<f32>(cos(colAngle), sin(colAngle));

  // Correct for fish-eye: project distance onto the camera's forward plane
  let forward = vec2<f32>(cos(camera.angle), sin(camera.angle));
  let hit = castRay(camera.position, dir);
  let projectedDist = max(hit.distance * dot(dir, forward), 0.001);

  // Wall height in screen pixels
  let wallHeight = screenHeight / projectedDist;

  // Top and bottom of the wall stripe
  let wallTop    = (screenHeight - wallHeight) * 0.5;
  let wallBottom = (screenHeight + wallHeight) * 0.5;

  // Distance shading: 1.0 = right on top of you, 0.0 = max distance
  let shade = clamp(1.0 - projectedDist / 16.0, 0.0, 1.0);

  // Y-face walls are slightly darker for pseudo-lighting
  let faceShade = select(shade, shade * 0.7, hit.face == 1u);

  // --- Draw each pixel in this column ---
  for (var row = 0u; row < resY; row++) {
    let y = f32(row);
    var color: vec4<f32>;

    if (y < wallTop) {
      // Ceiling
      let ceilDist = screenHeight / (2.0 * (screenHeight * 0.5 - y));
      let ceilShade = clamp(1.0 - ceilDist / 16.0, 0.0, 1.0);
      color = ceilColor(ceilShade);
    } else if (y > wallBottom) {
      // Floor
      let floorDist = screenHeight / (2.0 * (y - screenHeight * 0.5));
      let floorShade = clamp(1.0 - floorDist / 16.0, 0.0, 1.0);
      color = floorColor(floorShade);
    } else {
      // Wall
      color = wallColor(hit.tileValue, faceShade);
    }

    textureStore(outputTexture, vec2<u32>(col, row), color);
  }
}
