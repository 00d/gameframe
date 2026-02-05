// ============================================================
// OverworldScreen — 2D tile-based world map
// ============================================================

import { Screen, ScreenContext, InputEvent, TransitionType } from '../../core/Screen';
import { TileRenderer, TileMap, Viewport } from './TileRenderer';
import overworldData from '../../data/maps/overworld.json';

const MOVE_SPEED = 4.0; // tiles per second
const TILE_SIZE = 32;
const VIEWPORT_WIDTH = 30;  // tiles (960px / 32px)
const VIEWPORT_HEIGHT = 22; // tiles (720px / 32px)

interface DungeonEntrance {
  id: string;
  x: number;
  y: number;
  name: string;
}

export class OverworldScreen implements Screen {
  readonly id = 'overworld';

  private context!: ScreenContext;
  private renderer!: TileRenderer;
  private map!: TileMap;
  private dungeons: DungeonEntrance[] = [];

  // Party position
  private partyX = 16;
  private partyY = 16;

  // Viewport (camera follows party)
  private viewport: Viewport = {
    x: 0,
    y: 0,
    width: VIEWPORT_WIDTH,
    height: VIEWPORT_HEIGHT,
  };

  // Input state
  private keys = new Set<string>();

  // Canvas2D context
  private canvas2dCtx!: CanvasRenderingContext2D;

  // Random encounter timer
  private encounterTimer = 0;
  private encounterChance = 0.1; // 10% per interval
  private encounterInterval = 3.0; // seconds

  async init(context: ScreenContext): Promise<void> {
    this.context = context;

    // Create renderer (doesn't need context yet)
    this.renderer = new TileRenderer(context.canvas, TILE_SIZE);

    // Load map data
    this.map = {
      width: overworldData.width,
      height: overworldData.height,
      tiles: overworldData.tiles,
      tileSize: overworldData.tileSize,
    };

    // Load dungeon entrances
    this.dungeons = overworldData.dungeons as DungeonEntrance[];

    // Set initial party position
    this.partyX = overworldData.startPosition.x;
    this.partyY = overworldData.startPosition.y;
  }

  async enter(fromScreen: string | null, params?: any): Promise<void> {
    // Get Canvas2D context (safe to get on enter)
    this.canvas2dCtx = this.context.canvas.getContext('2d')!;

    // Restore party position from game state if coming from dungeon
    if (fromScreen === 'dungeon' || fromScreen === 'combat') {
      const position = this.context.gameState.getState().party.position;
      if (position.mapId === 'overworld') {
        this.partyX = position.x;
        this.partyY = position.y;
      }
    }

    // Center viewport on party
    this.centerViewportOnParty();

    // Clear input state
    this.keys.clear();

    // Reset encounter timer
    this.encounterTimer = 0;
  }

  async exit(toScreen: string | null): Promise<void> {
    // Save party position to game state
    this.context.gameState.setState(state => ({
      party: {
        ...state.party,
        position: {
          mapId: 'overworld',
          x: this.partyX,
          y: this.partyY,
          facing: 0,
        },
      },
    }));
  }

  update(dt: number): void {
    // Handle movement
    let dx = 0, dy = 0;

    if (this.keys.has('w') || this.keys.has('arrowup')) dy -= 1;
    if (this.keys.has('s') || this.keys.has('arrowdown')) dy += 1;
    if (this.keys.has('a') || this.keys.has('arrowleft')) dx -= 1;
    if (this.keys.has('d') || this.keys.has('arrowright')) dx += 1;

    // Normalize diagonal movement
    if (dx !== 0 && dy !== 0) {
      dx *= 0.707;
      dy *= 0.707;
    }

    // Calculate new position
    const newX = this.partyX + dx * MOVE_SPEED * dt;
    const newY = this.partyY + dy * MOVE_SPEED * dt;

    // Check if walkable
    const newTile = this.renderer.getTileAt(this.map, newX, newY);
    if (this.renderer.isWalkable(newTile)) {
      this.partyX = newX;
      this.partyY = newY;

      // Update viewport to follow party
      this.centerViewportOnParty();

      // Check for random encounters (only when moving on grass/forest)
      if ((newTile === 0 || newTile === 1) && (dx !== 0 || dy !== 0)) {
        this.encounterTimer += dt;
        if (this.encounterTimer >= this.encounterInterval) {
          this.encounterTimer = 0;
          if (Math.random() < this.encounterChance) {
            this.triggerRandomEncounter();
          }
        }
      }
    }

    // Check for dungeon entrance
    this.checkDungeonEntrance();
  }

  render(): void {
    // Clear canvas
    this.canvas2dCtx.fillStyle = '#000';
    this.canvas2dCtx.fillRect(0, 0, this.context.canvas.width, this.context.canvas.height);

    // Render map
    this.renderer.render(this.map, this.viewport, this.partyX, this.partyY);

    // Render UI overlay
    this.renderUI();
  }

  private renderUI(): void {
    const ctx = this.canvas2dCtx;

    // Top bar with game info
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(0, 0, this.context.canvas.width, 40);

    ctx.fillStyle = '#d4af37';
    ctx.font = '16px monospace';

    const gold = this.context.gameState.getState().party.gold;
    ctx.fillText(`Gold: ${gold}`, this.context.canvas.width - 150, 25);

    // Position debug info (bottom-left corner)
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(0, this.context.canvas.height - 30, 200, 30);
    ctx.fillStyle = '#888';
    ctx.font = '12px monospace';
    ctx.fillText(`Pos: (${Math.floor(this.partyX)}, ${Math.floor(this.partyY)})`, 10, this.context.canvas.height - 10);

    // Check if near dungeon entrance
    const nearDungeon = this.getNearbyDungeon();
    if (nearDungeon) {
      // Show prompt
      const promptY = this.context.canvas.height - 60;
      ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
      ctx.fillRect(0, promptY, this.context.canvas.width, 60);

      ctx.fillStyle = '#d4af37';
      ctx.font = '18px monospace';
      ctx.textAlign = 'center';
      ctx.fillText(`${nearDungeon.name}`, this.context.canvas.width / 2, promptY + 25);
      ctx.font = '14px monospace';
      ctx.fillText('Press ENTER to enter dungeon', this.context.canvas.width / 2, promptY + 45);
      ctx.textAlign = 'left';
    }
  }

  handleInput(event: InputEvent): boolean {
    if (event.type === 'keydown' && event.key) {
      this.keys.add(event.key);

      // Enter dungeon
      if (event.key === 'enter') {
        const nearDungeon = this.getNearbyDungeon();
        if (nearDungeon) {
          this.enterDungeon(nearDungeon);
          return true;
        }
      }

      return true;
    }

    if (event.type === 'keyup' && event.key) {
      this.keys.delete(event.key);
      return true;
    }

    return false;
  }

  // --- Helper Methods ---

  private centerViewportOnParty(): void {
    // Center viewport on party, clamped to map bounds
    this.viewport.x = Math.max(0, Math.min(
      this.partyX - this.viewport.width / 2,
      this.map.width - this.viewport.width
    ));
    this.viewport.y = Math.max(0, Math.min(
      this.partyY - this.viewport.height / 2,
      this.map.height - this.viewport.height
    ));
  }

  private getNearbyDungeon(): DungeonEntrance | null {
    const INTERACTION_DISTANCE = 1.0;

    for (const dungeon of this.dungeons) {
      const dx = this.partyX - dungeon.x;
      const dy = this.partyY - dungeon.y;
      const distance = Math.sqrt(dx * dx + dy * dy);

      if (distance < INTERACTION_DISTANCE) {
        return dungeon;
      }
    }

    return null;
  }

  private checkDungeonEntrance(): void {
    // Auto-enter if standing on dungeon tile
    const currentTile = this.renderer.getTileAt(this.map, this.partyX, this.partyY);
    if (currentTile === 6) { // Dungeon entrance tile
      const dungeon = this.getNearbyDungeon();
      if (dungeon) {
        // Show prompt, don't auto-enter
      }
    }
  }

  private enterDungeon(dungeon: DungeonEntrance): void {
    // Save current position
    this.context.gameState.setState(state => ({
      party: {
        ...state.party,
        position: {
          mapId: 'overworld',
          x: this.partyX,
          y: this.partyY,
          facing: 0,
        },
      },
      world: {
        ...state.world,
        currentMap: dungeon.id,
      },
    }));

    // Transition to dungeon
    this.context.screenManager.transition('dungeon', {
      type: TransitionType.Fade,
      duration: 500,
      params: { dungeonId: dungeon.id },
    });
  }

  private triggerRandomEncounter(): void {
    // Transition to combat
    this.context.screenManager.transition('combat', {
      type: TransitionType.Instant,
      params: { encounterType: 'random' },
    });
  }
}
