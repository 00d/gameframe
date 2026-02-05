// ============================================================
// CombatGrid — Top-down tactical grid renderer
// ============================================================

import { Combatant } from './TurnManager';

export interface GridPosition {
  x: number;
  y: number;
}

export class CombatGrid {
  private canvas: HTMLCanvasElement;
  private ctx: CanvasRenderingContext2D;

  private gridWidth: number;
  private gridHeight: number;
  private cellSize: number;

  // Offset to center grid on canvas
  private offsetX: number = 0;
  private offsetY: number = 0;

  constructor(canvas: HTMLCanvasElement, gridWidth: number = 12, gridHeight: number = 10, cellSize: number = 48) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d')!;
    this.gridWidth = gridWidth;
    this.gridHeight = gridHeight;
    this.cellSize = cellSize;

    // Center grid on canvas
    this.offsetX = (canvas.width - gridWidth * cellSize) / 2;
    this.offsetY = (canvas.height - gridHeight * cellSize) / 2 + 40; // +40 for top UI
  }

  /**
   * Render the combat grid.
   */
  render(combatants: Combatant[], currentCombatant: Combatant | null, selectedPosition: GridPosition | null): void {
    // Clear canvas
    this.ctx.fillStyle = '#1a1a1a';
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    // Draw grid
    this.drawGrid();

    // Draw combatants
    for (const combatant of combatants) {
      if (combatant.currentHP > 0) {
        this.drawCombatant(combatant, combatant === currentCombatant);
      }
    }

    // Draw selected position highlight
    if (selectedPosition) {
      this.drawPositionHighlight(selectedPosition);
    }
  }

  /**
   * Draw the grid lines.
   */
  private drawGrid(): void {
    this.ctx.strokeStyle = '#333';
    this.ctx.lineWidth = 1;

    // Vertical lines
    for (let x = 0; x <= this.gridWidth; x++) {
      const screenX = this.offsetX + x * this.cellSize;
      this.ctx.beginPath();
      this.ctx.moveTo(screenX, this.offsetY);
      this.ctx.lineTo(screenX, this.offsetY + this.gridHeight * this.cellSize);
      this.ctx.stroke();
    }

    // Horizontal lines
    for (let y = 0; y <= this.gridHeight; y++) {
      const screenY = this.offsetY + y * this.cellSize;
      this.ctx.beginPath();
      this.ctx.moveTo(this.offsetX, screenY);
      this.ctx.lineTo(this.offsetX + this.gridWidth * this.cellSize, screenY);
      this.ctx.stroke();
    }
  }

  /**
   * Draw a combatant on the grid (programmer art).
   */
  private drawCombatant(combatant: Combatant, isActive: boolean): void {
    const centerX = this.offsetX + combatant.gridX * this.cellSize + this.cellSize / 2;
    const centerY = this.offsetY + combatant.gridY * this.cellSize + this.cellSize / 2;
    const radius = this.cellSize / 3;

    // Shadow
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.4)';
    this.ctx.beginPath();
    this.ctx.ellipse(centerX, centerY + radius, radius * 0.9, radius * 0.3, 0, 0, Math.PI * 2);
    this.ctx.fill();

    // Active indicator (glow)
    if (isActive) {
      this.ctx.fillStyle = 'rgba(255, 215, 0, 0.3)';
      this.ctx.beginPath();
      this.ctx.arc(centerX, centerY, radius * 1.5, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // Main circle
    const color = combatant.isEnemy ? '#8b0000' : '#4169e1'; // Red for enemies, blue for heroes
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    this.ctx.fill();

    // Border
    this.ctx.strokeStyle = isActive ? '#ffd700' : '#000';
    this.ctx.lineWidth = isActive ? 3 : 2;
    this.ctx.stroke();

    // Simple face/icon
    this.ctx.fillStyle = '#fff';
    if (combatant.isEnemy) {
      // Enemy: X eyes
      this.ctx.lineWidth = 2;
      this.ctx.strokeStyle = '#fff';
      this.ctx.beginPath();
      this.ctx.moveTo(centerX - 6, centerY - 6);
      this.ctx.lineTo(centerX - 2, centerY - 2);
      this.ctx.moveTo(centerX - 2, centerY - 6);
      this.ctx.lineTo(centerX - 6, centerY - 2);
      this.ctx.moveTo(centerX + 2, centerY - 6);
      this.ctx.lineTo(centerX + 6, centerY - 2);
      this.ctx.moveTo(centerX + 6, centerY - 6);
      this.ctx.lineTo(centerX + 2, centerY - 2);
      this.ctx.stroke();
    } else {
      // Hero: dot eyes
      this.ctx.beginPath();
      this.ctx.arc(centerX - 4, centerY - 4, 2, 0, Math.PI * 2);
      this.ctx.arc(centerX + 4, centerY - 4, 2, 0, Math.PI * 2);
      this.ctx.fill();
    }

    // HP bar above combatant
    this.drawHPBar(centerX, centerY - radius - 10, combatant.currentHP, combatant.maxHP);

    // Name below combatant
    this.ctx.fillStyle = '#fff';
    this.ctx.font = '12px monospace';
    this.ctx.textAlign = 'center';
    this.ctx.fillText(combatant.name, centerX, centerY + radius + 15);
    this.ctx.textAlign = 'left';
  }

  /**
   * Draw HP bar (programmer art).
   */
  private drawHPBar(x: number, y: number, current: number, max: number): void {
    const barWidth = 40;
    const barHeight = 6;
    const barX = x - barWidth / 2;

    // Background
    this.ctx.fillStyle = '#333';
    this.ctx.fillRect(barX, y, barWidth, barHeight);

    // HP fill
    const hpPercent = Math.max(0, Math.min(1, current / max));
    const hpColor = hpPercent > 0.5 ? '#4ade80' : hpPercent > 0.25 ? '#fb923c' : '#ef4444';
    this.ctx.fillStyle = hpColor;
    this.ctx.fillRect(barX, y, barWidth * hpPercent, barHeight);

    // Border
    this.ctx.strokeStyle = '#000';
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(barX, y, barWidth, barHeight);
  }

  /**
   * Draw position highlight for movement/targeting.
   */
  private drawPositionHighlight(pos: GridPosition): void {
    const x = this.offsetX + pos.x * this.cellSize;
    const y = this.offsetY + pos.y * this.cellSize;

    this.ctx.fillStyle = 'rgba(255, 215, 0, 0.3)';
    this.ctx.fillRect(x, y, this.cellSize, this.cellSize);

    this.ctx.strokeStyle = '#ffd700';
    this.ctx.lineWidth = 2;
    this.ctx.strokeRect(x, y, this.cellSize, this.cellSize);
  }

  /**
   * Convert screen coordinates to grid position.
   */
  screenToGrid(screenX: number, screenY: number): GridPosition | null {
    const gridX = Math.floor((screenX - this.offsetX) / this.cellSize);
    const gridY = Math.floor((screenY - this.offsetY) / this.cellSize);

    if (gridX >= 0 && gridX < this.gridWidth && gridY >= 0 && gridY < this.gridHeight) {
      return { x: gridX, y: gridY };
    }

    return null;
  }

  /**
   * Check if a grid position is occupied by a combatant.
   */
  getCombatantAt(combatants: Combatant[], pos: GridPosition): Combatant | null {
    return combatants.find(c => c.gridX === pos.x && c.gridY === pos.y && c.currentHP > 0) || null;
  }
}
