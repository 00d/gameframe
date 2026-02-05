// ============================================================
// CombatScreen — Tactical turn-based combat
// ============================================================

import { Screen, ScreenContext, InputEvent, TransitionType } from '../../core/Screen';
import { TurnManager, Combatant } from './TurnManager';
import { CombatGrid, GridPosition } from './CombatGrid';

enum CombatState {
  SelectingAction,
  SelectingTarget,
  Animating,
  Victory,
  Defeat,
}

type CombatAction = 'attack' | 'move' | 'defend' | 'end';

export class CombatScreen implements Screen {
  readonly id = 'combat';

  private context!: ScreenContext;
  private turnManager!: TurnManager;
  private grid!: CombatGrid;
  private canvas2dCtx!: CanvasRenderingContext2D;

  // Combat state
  private combatState: CombatState = CombatState.SelectingAction;
  private selectedAction: CombatAction | null = null;
  private selectedPosition: GridPosition | null = null;
  private actionMenuIndex = 0;
  private actions: CombatAction[] = ['attack', 'move', 'defend', 'end'];

  // Animation
  private animationTimer = 0;
  private animationDuration = 1.0;

  async init(context: ScreenContext): Promise<void> {
    this.context = context;

    // Create grid renderer (doesn't need context yet)
    this.grid = new CombatGrid(context.canvas, 12, 10, 48);
  }

  async enter(fromScreen: string | null, params?: any): Promise<void> {
    // Get Canvas2D context (safe to get on enter)
    this.canvas2dCtx = this.context.canvas.getContext('2d')!;

    // Initialize combat
    const combatants = this.createTestCombatants();
    this.turnManager = new TurnManager(combatants);
    this.combatState = CombatState.SelectingAction;
    this.selectedAction = null;
    this.selectedPosition = null;
    this.actionMenuIndex = 0;
  }

  async exit(toScreen: string | null): Promise<void> {
    // Cleanup
  }

  update(dt: number): void {
    // Handle animation timer
    if (this.combatState === CombatState.Animating) {
      this.animationTimer += dt;
      if (this.animationTimer >= this.animationDuration) {
        this.animationTimer = 0;
        this.combatState = CombatState.SelectingAction;
        this.turnManager.nextTurn();

        // Check if combat is over
        const result = this.turnManager.isCombatOver();
        if (result.isOver) {
          this.combatState = result.heroesWon ? CombatState.Victory : CombatState.Defeat;
        }

        // AI turn for enemies
        const current = this.turnManager.getCurrentCombatant();
        if (current?.isEnemy) {
          this.performAITurn();
        }
      }
    }

    // Handle victory/defeat
    if (this.combatState === CombatState.Victory || this.combatState === CombatState.Defeat) {
      this.animationTimer += dt;
      if (this.animationTimer >= 2.0) {
        this.endCombat();
      }
    }
  }

  render(): void {
    // Clear canvas
    this.canvas2dCtx.fillStyle = '#000';
    this.canvas2dCtx.fillRect(0, 0, this.context.canvas.width, this.context.canvas.height);

    // Render grid and combatants
    const combatants = this.turnManager.getAllCombatants();
    const current = this.turnManager.getCurrentCombatant();
    this.grid.render(combatants, current, this.selectedPosition);

    // Render UI
    this.renderUI();

    // Render victory/defeat screen
    if (this.combatState === CombatState.Victory || this.combatState === CombatState.Defeat) {
      this.renderEndScreen();
    }
  }

  private renderUI(): void {
    const ctx = this.canvas2dCtx;

    // Top bar - round and turn info
    ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
    ctx.fillRect(0, 0, this.context.canvas.width, 40);

    ctx.fillStyle = '#d4af37';
    ctx.font = '16px monospace';
    ctx.fillText(`Round ${this.turnManager.getRoundNumber()}`, 10, 25);

    const current = this.turnManager.getCurrentCombatant();
    if (current) {
      ctx.fillText(`Turn: ${current.name}`, this.context.canvas.width / 2 - 60, 25);
    }

    // Action menu (if selecting action)
    if (this.combatState === CombatState.SelectingAction && current && !current.isEnemy) {
      this.renderActionMenu();
    }

    // Turn order sidebar
    this.renderTurnOrder();
  }

  private renderActionMenu(): void {
    const ctx = this.canvas2dCtx;
    const menuX = 20;
    const menuY = this.context.canvas.height - 180;
    const menuWidth = 200;
    const menuHeight = 160;

    // Background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.9)';
    ctx.fillRect(menuX, menuY, menuWidth, menuHeight);
    ctx.strokeStyle = '#d4af37';
    ctx.lineWidth = 2;
    ctx.strokeRect(menuX, menuY, menuWidth, menuHeight);

    // Title
    ctx.fillStyle = '#d4af37';
    ctx.font = 'bold 16px monospace';
    ctx.fillText('ACTIONS', menuX + 10, menuY + 25);

    // Actions
    ctx.font = '14px monospace';
    this.actions.forEach((action, index) => {
      const y = menuY + 50 + index * 25;

      if (index === this.actionMenuIndex) {
        ctx.fillStyle = '#d4af37';
        ctx.fillRect(menuX + 5, y - 15, menuWidth - 10, 20);
        ctx.fillStyle = '#000';
      } else {
        ctx.fillStyle = '#d4af37';
      }

      ctx.fillText(`${action.toUpperCase()}`, menuX + 15, y);
    });
  }

  private renderTurnOrder(): void {
    const ctx = this.canvas2dCtx;
    const x = this.context.canvas.width - 180;
    const y = 50;
    const width = 170;

    // Background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.8)';
    ctx.fillRect(x, y, width, 300);

    // Title
    ctx.fillStyle = '#d4af37';
    ctx.font = 'bold 14px monospace';
    ctx.fillText('TURN ORDER', x + 10, y + 20);

    // List combatants
    ctx.font = '12px monospace';
    const turnOrder = this.turnManager.getTurnOrder();
    turnOrder.forEach((combatant, index) => {
      if (combatant.currentHP <= 0) return;

      const itemY = y + 45 + index * 35;

      // Highlight current turn
      if (index === this.turnManager.getCurrentTurnIndex()) {
        ctx.fillStyle = 'rgba(212, 175, 55, 0.3)';
        ctx.fillRect(x + 5, itemY - 12, width - 10, 30);
      }

      // Name
      ctx.fillStyle = combatant.isEnemy ? '#ff6b6b' : '#4dabf7';
      ctx.fillText(combatant.name, x + 10, itemY);

      // HP
      ctx.fillStyle = '#aaa';
      ctx.font = '10px monospace';
      ctx.fillText(`HP: ${combatant.currentHP}/${combatant.maxHP}`, x + 10, itemY + 12);
      ctx.font = '12px monospace';
    });
  }

  private renderEndScreen(): void {
    const ctx = this.canvas2dCtx;

    // Overlay
    ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    ctx.fillRect(0, 0, this.context.canvas.width, this.context.canvas.height);

    // Message
    const message = this.combatState === CombatState.Victory ? 'VICTORY!' : 'DEFEAT...';
    const color = this.combatState === CombatState.Victory ? '#4ade80' : '#ef4444';

    ctx.fillStyle = color;
    ctx.font = 'bold 48px monospace';
    ctx.textAlign = 'center';
    ctx.fillText(message, this.context.canvas.width / 2, this.context.canvas.height / 2);

    ctx.font = '18px monospace';
    ctx.fillStyle = '#d4af37';
    ctx.fillText('Returning to overworld...', this.context.canvas.width / 2, this.context.canvas.height / 2 + 50);
    ctx.textAlign = 'left';
  }

  handleInput(event: InputEvent): boolean {
    if (this.combatState === CombatState.SelectingAction) {
      return this.handleActionSelection(event);
    } else if (this.combatState === CombatState.SelectingTarget) {
      return this.handleTargetSelection(event);
    }

    return true; // Block input during animations
  }

  private handleActionSelection(event: InputEvent): boolean {
    const current = this.turnManager.getCurrentCombatant();
    if (!current || current.isEnemy) return true;

    if (event.type === 'keydown') {
      switch (event.key) {
        case 'arrowup':
        case 'w':
          this.actionMenuIndex = (this.actionMenuIndex - 1 + this.actions.length) % this.actions.length;
          return true;

        case 'arrowdown':
        case 's':
          this.actionMenuIndex = (this.actionMenuIndex + 1) % this.actions.length;
          return true;

        case 'enter':
        case ' ':
          this.selectedAction = this.actions[this.actionMenuIndex];
          if (this.selectedAction === 'end') {
            this.turnManager.nextTurn();
            const next = this.turnManager.getCurrentCombatant();
            if (next?.isEnemy) {
              this.performAITurn();
            }
          } else if (this.selectedAction === 'defend') {
            // Simple defend - just end turn with bonus
            this.combatState = CombatState.Animating;
            this.animationTimer = 0;
            this.animationDuration = 0.5;
          } else {
            this.combatState = CombatState.SelectingTarget;
          }
          return true;
      }
    }

    return true;
  }

  private handleTargetSelection(event: InputEvent): boolean {
    if (event.type === 'mousedown' && event.x !== undefined && event.y !== undefined) {
      const gridPos = this.grid.screenToGrid(event.x, event.y);
      if (gridPos) {
        this.selectedPosition = gridPos;

        if (this.selectedAction === 'attack') {
          this.performAttack(gridPos);
        } else if (this.selectedAction === 'move') {
          this.performMove(gridPos);
        }

        return true;
      }
    }

    if (event.type === 'keydown' && event.key === 'escape') {
      this.combatState = CombatState.SelectingAction;
      this.selectedPosition = null;
      return true;
    }

    return true;
  }

  // --- Combat Actions ---

  private performAttack(targetPos: GridPosition): void {
    const attacker = this.turnManager.getCurrentCombatant();
    if (!attacker) return;

    const target = this.grid.getCombatantAt(this.turnManager.getAllCombatants(), targetPos);
    if (target && target.isEnemy !== attacker.isEnemy) {
      // Simple damage calculation
      const damage = Math.floor(Math.random() * 6) + 3; // 3-8 damage
      target.currentHP = Math.max(0, target.currentHP - damage);

      this.turnManager.updateCombatant(target.id, { currentHP: target.currentHP });

      // Start animation
      this.combatState = CombatState.Animating;
      this.animationTimer = 0;
      this.animationDuration = 1.0;
    }

    this.selectedPosition = null;
  }

  private performMove(targetPos: GridPosition): void {
    const mover = this.turnManager.getCurrentCombatant();
    if (!mover) return;

    // Check if position is empty
    const occupant = this.grid.getCombatantAt(this.turnManager.getAllCombatants(), targetPos);
    if (!occupant) {
      mover.gridX = targetPos.x;
      mover.gridY = targetPos.y;
      this.turnManager.updateCombatant(mover.id, { gridX: targetPos.x, gridY: targetPos.y });
    }

    this.combatState = CombatState.SelectingAction;
    this.selectedPosition = null;
  }

  private performAITurn(): void {
    const ai = this.turnManager.getCurrentCombatant();
    if (!ai || !ai.isEnemy) return;

    // Simple AI: find nearest hero and attack
    const heroes = this.turnManager.getAllCombatants().filter(c => !c.isEnemy && c.currentHP > 0);
    if (heroes.length > 0) {
      const target = heroes[0];

      // Simple damage
      const damage = Math.floor(Math.random() * 5) + 2;
      target.currentHP = Math.max(0, target.currentHP - damage);
      this.turnManager.updateCombatant(target.id, { currentHP: target.currentHP });
    }

    // Animate AI turn
    this.combatState = CombatState.Animating;
    this.animationTimer = 0;
    this.animationDuration = 0.8;
  }

  private endCombat(): void {
    // Return to overworld
    this.context.screenManager.transition('overworld', {
      type: TransitionType.Fade,
      duration: 500,
    });
  }

  // --- Test Data ---

  private createTestCombatants(): Combatant[] {
    return [
      {
        id: 'hero1',
        name: 'Fighter',
        isEnemy: false,
        initiative: 15,
        currentHP: 20,
        maxHP: 20,
        gridX: 2,
        gridY: 5,
        hasActed: false,
      },
      {
        id: 'hero2',
        name: 'Wizard',
        isEnemy: false,
        initiative: 12,
        currentHP: 12,
        maxHP: 12,
        gridX: 3,
        gridY: 5,
        hasActed: false,
      },
      {
        id: 'enemy1',
        name: 'Goblin',
        isEnemy: true,
        initiative: 14,
        currentHP: 8,
        maxHP: 8,
        gridX: 8,
        gridY: 4,
        hasActed: false,
      },
      {
        id: 'enemy2',
        name: 'Orc',
        isEnemy: true,
        initiative: 10,
        currentHP: 12,
        maxHP: 12,
        gridX: 9,
        gridY: 5,
        hasActed: false,
      },
    ];
  }
}
