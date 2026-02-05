// ============================================================
// DungeonScreen — 3D dungeon exploration mode
// ============================================================

import { Screen, ScreenContext, InputEvent } from '../../core/Screen';
import { DungeonRenderer } from './DungeonRenderer';

const MOVE_SPEED = 3.0;  // units per second
const LOOK_SPEED = 2.0;  // radians per second
const FOV = Math.PI / 3; // 60 degrees

// Sample dungeon map (16x16)
const MAP_WIDTH = 16;
const MAP_HEIGHT = 16;
const MAP_DATA: number[] = [
  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
  1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 0, 2, 0, 0, 0, 0, 1, 0, 0, 3, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 4, 1,
  1, 0, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 2, 2, 0, 0, 0, 3, 3, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 3, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 1, 1, 0, 0, 2, 2, 0, 0, 0, 0, 1,
  1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1,
  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
];

export class DungeonScreen implements Screen {
  readonly id = 'dungeon';

  private context!: ScreenContext;
  private renderer!: DungeonRenderer;

  // Camera state
  private camX = 8.5;
  private camY = 8.5;
  private camAngle = 0.0;

  // Input state
  private keys = new Set<string>();
  private mouseDx = 0;

  // Map data
  private mapData: Uint32Array;
  private mapWidth: number;
  private mapHeight: number;

  constructor() {
    this.mapData = new Uint32Array(MAP_DATA);
    this.mapWidth = MAP_WIDTH;
    this.mapHeight = MAP_HEIGHT;
  }

  async init(context: ScreenContext): Promise<void> {
    this.context = context;
    // Renderer will be created lazily in enter() to avoid canvas context conflicts
  }

  async enter(fromScreen: string | null, params?: any): Promise<void> {
    // Create renderer if not already created (lazy initialization)
    if (!this.renderer) {
      try {
        this.renderer = new DungeonRenderer({
          canvas: this.context.canvas,
          resolution: [960, 720],
        });

        // Load map
        await this.renderer.loadMap(this.mapData, this.mapWidth, this.mapHeight);
      } catch (error) {
        // Show user-friendly error message
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        throw new Error(`Failed to initialize 3D dungeon renderer: ${errorMessage}`);
      }
    }

    // Restore camera from game state if available
    const position = this.context.gameState.getState().party.position;
    if (position.mapId === 'dungeon_1') {
      this.camX = position.x;
      this.camY = position.y;
      this.camAngle = position.facing;
    }

    // Clear input state
    this.keys.clear();
    this.mouseDx = 0;
  }

  async exit(toScreen: string | null): Promise<void> {
    // Release pointer lock when leaving dungeon
    if (document.pointerLockElement) {
      document.exitPointerLock();
    }

    // Save camera position to game state
    this.context.gameState.setState(state => ({
      party: {
        ...state.party,
        position: {
          mapId: 'dungeon_1',
          x: this.camX,
          y: this.camY,
          facing: this.camAngle,
        },
      },
    }));
  }

  update(dt: number): void {
    // Calculate movement
    const forward = [Math.cos(this.camAngle), Math.sin(this.camAngle)];
    const right = [-Math.sin(this.camAngle), Math.cos(this.camAngle)];
    let dx = 0, dy = 0;

    if (this.keys.has('w')) { dx += forward[0]; dy += forward[1]; }
    if (this.keys.has('s')) { dx -= forward[0]; dy -= forward[1]; }
    if (this.keys.has('a')) { dx -= right[0]; dy -= right[1]; }
    if (this.keys.has('d')) { dx += right[0]; dy += right[1]; }

    // Normalize movement vector
    const len = Math.sqrt(dx * dx + dy * dy);
    if (len > 0) { dx /= len; dy /= len; }

    const newX = this.camX + dx * MOVE_SPEED * dt;
    const newY = this.camY + dy * MOVE_SPEED * dt;

    // Wall sliding collision
    if (this.canMoveTo(newX, newY)) {
      this.camX = newX;
      this.camY = newY;
    } else if (this.canMoveTo(newX, this.camY)) {
      this.camX = newX;
    } else if (this.canMoveTo(this.camX, newY)) {
      this.camY = newY;
    }

    // Mouse look
    if (this.mouseDx !== 0) {
      this.camAngle += this.mouseDx * LOOK_SPEED * 0.003;
      this.mouseDx = 0;
    }

    // Keyboard look
    if (this.keys.has('arrowleft')) this.camAngle -= LOOK_SPEED * dt;
    if (this.keys.has('arrowright')) this.camAngle += LOOK_SPEED * dt;

    // Update camera in renderer
    this.renderer.setCamera(this.camX, this.camY, this.camAngle, FOV);
  }

  render(): void {
    this.renderer.frame();
  }

  handleInput(event: InputEvent): boolean {
    switch (event.type) {
      case 'keydown':
        if (event.key) {
          this.keys.add(event.key);

          // Screen transition shortcuts
          if (event.key === 'c') {
            // Open character sheet (modal)
            this.context.screenManager.pushModal('character-sheet');
            return true;
          }
          if (event.key === 'i') {
            // Open inventory (modal)
            this.context.screenManager.pushModal('inventory');
            return true;
          }

          return true;
        }
        break;

      case 'keyup':
        if (event.key) {
          this.keys.delete(event.key);
          return true;
        }
        break;

      case 'mousemove':
        if (event.movementX !== undefined) {
          this.mouseDx += event.movementX;
          return true;
        }
        break;
    }

    return false;
  }

  // --- Collision Helper ---
  private canMoveTo(x: number, y: number): boolean {
    const margin = 0.15;
    const corners = [
      [x - margin, y - margin],
      [x + margin, y - margin],
      [x - margin, y + margin],
      [x + margin, y + margin],
    ];

    for (const [cx, cy] of corners) {
      const gx = Math.floor(cx);
      const gy = Math.floor(cy);
      if (gx < 0 || gy < 0 || gx >= this.mapWidth || gy >= this.mapHeight) {
        return false;
      }
      if (this.mapData[gy * this.mapWidth + gx] !== 0) {
        return false;
      }
    }

    return true;
  }
}
