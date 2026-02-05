// ============================================================
// TurnManager — Initiative order and turn progression
// ============================================================

export interface Combatant {
  id: string;
  name: string;
  isEnemy: boolean;
  initiative: number;
  currentHP: number;
  maxHP: number;
  gridX: number;
  gridY: number;
  hasActed: boolean;
}

export class TurnManager {
  private combatants: Combatant[] = [];
  private currentTurnIndex = 0;
  private roundNumber = 1;

  constructor(combatants: Combatant[]) {
    this.combatants = [...combatants];
    this.sortByInitiative();
  }

  /**
   * Sort combatants by initiative (highest first).
   */
  private sortByInitiative(): void {
    this.combatants.sort((a, b) => b.initiative - a.initiative);
  }

  /**
   * Get the current active combatant.
   */
  getCurrentCombatant(): Combatant | null {
    if (this.combatants.length === 0) return null;
    return this.combatants[this.currentTurnIndex];
  }

  /**
   * Get all combatants.
   */
  getAllCombatants(): Combatant[] {
    return this.combatants;
  }

  /**
   * Get current round number.
   */
  getRoundNumber(): number {
    return this.roundNumber;
  }

  /**
   * Get current turn index.
   */
  getCurrentTurnIndex(): number {
    return this.currentTurnIndex;
  }

  /**
   * Mark current combatant as having acted and advance to next turn.
   */
  nextTurn(): void {
    const current = this.getCurrentCombatant();
    if (current) {
      current.hasActed = true;
    }

    // Find next living combatant
    let attempts = 0;
    do {
      this.currentTurnIndex = (this.currentTurnIndex + 1) % this.combatants.length;
      attempts++;

      // If we've looped back to start, it's a new round
      if (this.currentTurnIndex === 0) {
        this.roundNumber++;
        this.resetActedFlags();
      }

      // Safety check to prevent infinite loop
      if (attempts > this.combatants.length) {
        break;
      }
    } while (this.getCurrentCombatant()?.currentHP === 0);
  }

  /**
   * Reset acted flags for new round.
   */
  private resetActedFlags(): void {
    this.combatants.forEach(c => c.hasActed = false);
  }

  /**
   * Remove a defeated combatant.
   */
  removeCombatant(id: string): void {
    const index = this.combatants.findIndex(c => c.id === id);
    if (index !== -1) {
      this.combatants.splice(index, 1);

      // Adjust current turn index if needed
      if (this.currentTurnIndex >= this.combatants.length) {
        this.currentTurnIndex = 0;
      }
    }
  }

  /**
   * Update a combatant's data.
   */
  updateCombatant(id: string, updates: Partial<Combatant>): void {
    const combatant = this.combatants.find(c => c.id === id);
    if (combatant) {
      Object.assign(combatant, updates);
    }
  }

  /**
   * Check if combat is over (all enemies or all heroes defeated).
   */
  isCombatOver(): { isOver: boolean; heroesWon: boolean } {
    const livingHeroes = this.combatants.filter(c => !c.isEnemy && c.currentHP > 0);
    const livingEnemies = this.combatants.filter(c => c.isEnemy && c.currentHP > 0);

    if (livingEnemies.length === 0) {
      return { isOver: true, heroesWon: true };
    }

    if (livingHeroes.length === 0) {
      return { isOver: true, heroesWon: false };
    }

    return { isOver: false, heroesWon: false };
  }

  /**
   * Get combatants in initiative order.
   */
  getTurnOrder(): Combatant[] {
    return [...this.combatants];
  }
}
