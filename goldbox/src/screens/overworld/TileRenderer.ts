// ============================================================
// TileRenderer — Canvas2D tile rendering with viewport
// ============================================================

export interface TileMap {
  width: number;
  height: number;
  tiles: number[];  // Flat array, row-major
  tileSize: number;
}

export interface Viewport {
  x: number;      // World position (in tiles)
  y: number;
  width: number;  // Viewport size (in tiles)
  height: number;
}

export class TileRenderer {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;
  private tileSize: number;

  // Tile colors (programmer art)
  private tileColors: Map<number, string> = new Map([
    [0, '#2a5f3f'],  // Grass (dark green)
    [1, '#1a3f2f'],  // Forest (darker green)
    [2, '#6b8e23'],  // Road (olive)
    [3, '#8b7355'],  // Mountain (brown)
    [4, '#4682b4'],  // Water (steel blue)
    [5, '#8b4513'],  // Town (saddle brown)
    [6, '#2f2f2f'],  // Dungeon entrance (dark gray)
  ]);

  constructor(canvas: HTMLCanvasElement, tileSize: number = 32) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d')!;
    this.tileSize = tileSize;
  }

  /**
   * Render a tile map to the canvas with the given viewport.
   */
  render(map: TileMap, viewport: Viewport, partyX: number, partyY: number): void {
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    // Calculate which tiles are visible
    const startTileX = Math.floor(viewport.x);
    const startTileY = Math.floor(viewport.y);
    const endTileX = Math.min(Math.ceil(viewport.x + viewport.width), map.width);
    const endTileY = Math.min(Math.ceil(viewport.y + viewport.height), map.height);

    // Pixel offset for smooth scrolling
    const offsetX = -(viewport.x - startTileX) * this.tileSize;
    const offsetY = -(viewport.y - startTileY) * this.tileSize;

    // Draw tiles
    for (let ty = startTileY; ty < endTileY; ty++) {
      for (let tx = startTileX; tx < endTileX; tx++) {
        const tileIndex = ty * map.width + tx;
        const tileType = map.tiles[tileIndex];

        const screenX = (tx - startTileX) * this.tileSize + offsetX;
        const screenY = (ty - startTileY) * this.tileSize + offsetY;

        this.drawTile(tileType, screenX, screenY);
      }
    }

    // Draw party sprite
    const partyScreenX = (partyX - viewport.x) * this.tileSize;
    const partyScreenY = (partyY - viewport.y) * this.tileSize;
    this.drawParty(partyScreenX, partyScreenY);
  }

  /**
   * Draw a single tile (programmer art).
   */
  private drawTile(tileType: number, x: number, y: number): void {
    const color = this.tileColors.get(tileType) || '#ff00ff'; // Magenta for unknown

    this.ctx.fillStyle = color;
    this.ctx.fillRect(x, y, this.tileSize, this.tileSize);

    // Add simple border for clarity
    this.ctx.strokeStyle = 'rgba(0, 0, 0, 0.2)';
    this.ctx.strokeRect(x, y, this.tileSize, this.tileSize);

    // Add tile-specific details
    switch (tileType) {
      case 1: // Forest - add some texture
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.2)';
        this.ctx.fillRect(x + 4, y + 4, 8, 8);
        this.ctx.fillRect(x + 20, y + 20, 8, 8);
        break;

      case 3: // Mountain - add triangle
        this.ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.beginPath();
        this.ctx.moveTo(x + this.tileSize / 2, y + 4);
        this.ctx.lineTo(x + this.tileSize - 4, y + this.tileSize - 4);
        this.ctx.lineTo(x + 4, y + this.tileSize - 4);
        this.ctx.closePath();
        this.ctx.fill();
        break;

      case 4: // Water - add waves
        this.ctx.strokeStyle = 'rgba(255, 255, 255, 0.3)';
        this.ctx.lineWidth = 2;
        this.ctx.beginPath();
        this.ctx.moveTo(x, y + this.tileSize / 2);
        this.ctx.quadraticCurveTo(
          x + this.tileSize / 4, y + this.tileSize / 2 - 4,
          x + this.tileSize / 2, y + this.tileSize / 2
        );
        this.ctx.stroke();
        break;

      case 5: // Town - add house shape
        this.ctx.fillStyle = 'rgba(139, 0, 0, 0.8)';
        this.ctx.fillRect(x + 8, y + 12, 16, 12);
        this.ctx.beginPath();
        this.ctx.moveTo(x + 8, y + 12);
        this.ctx.lineTo(x + 16, y + 4);
        this.ctx.lineTo(x + 24, y + 12);
        this.ctx.closePath();
        this.ctx.fill();
        break;

      case 6: // Dungeon - add stairs icon
        this.ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
        for (let i = 0; i < 4; i++) {
          this.ctx.fillRect(x + 8, y + 8 + i * 5, 16 - i * 3, 3);
        }
        break;
    }
  }

  /**
   * Draw the party sprite (programmer art).
   */
  private drawParty(x: number, y: number): void {
    const centerX = x + this.tileSize / 2;
    const centerY = y + this.tileSize / 2;
    const radius = this.tileSize / 3;

    // Shadow
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.3)';
    this.ctx.beginPath();
    this.ctx.ellipse(centerX, centerY + radius, radius * 0.8, radius * 0.3, 0, 0, Math.PI * 2);
    this.ctx.fill();

    // Main circle (party icon)
    this.ctx.fillStyle = '#d4af37'; // Gold
    this.ctx.beginPath();
    this.ctx.arc(centerX, centerY - 2, radius, 0, Math.PI * 2);
    this.ctx.fill();

    // Border
    this.ctx.strokeStyle = '#8b7355';
    this.ctx.lineWidth = 2;
    this.ctx.stroke();

    // Simple face (two dots for eyes)
    this.ctx.fillStyle = '#000';
    this.ctx.beginPath();
    this.ctx.arc(centerX - 4, centerY - 4, 2, 0, Math.PI * 2);
    this.ctx.arc(centerX + 4, centerY - 4, 2, 0, Math.PI * 2);
    this.ctx.fill();
  }

  /**
   * Get tile type at world position.
   */
  getTileAt(map: TileMap, x: number, y: number): number {
    const tx = Math.floor(x);
    const ty = Math.floor(y);

    if (tx < 0 || ty < 0 || tx >= map.width || ty >= map.height) {
      return -1; // Out of bounds
    }

    return map.tiles[ty * map.width + tx];
  }

  /**
   * Check if a tile is walkable.
   */
  isWalkable(tileType: number): boolean {
    // Water (4) and mountains (3) are not walkable
    return tileType !== 3 && tileType !== 4;
  }
}
