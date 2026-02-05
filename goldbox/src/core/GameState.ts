// ============================================================
// GameState — Centralized state store with observable pattern
// ============================================================

// --- ORC Character Model ---
export interface Attributes {
  strength: number;
  dexterity: number;
  constitution: number;
  intelligence: number;
  wisdom: number;
  charisma: number;
}

export interface HitPoints {
  current: number;
  max: number;
}

export interface Skill {
  id: string;
  name: string;
  rank: number;
}

export interface Feat {
  id: string;
  name: string;
}

export interface SpellSlot {
  level: number;
  used: number;
  total: number;
}

export interface Item {
  id: string;
  name: string;
  type: 'weapon' | 'armor' | 'consumable' | 'misc';
  weight: number;
  value: number;
  description?: string;
}

export interface Equipment {
  mainHand: Item | null;
  offHand: Item | null;
  armor: Item | null;
}

export interface Condition {
  id: string;
  name: string;
  duration: number; // -1 = permanent
}

export interface Character {
  id: string;
  name: string;

  // ORC core
  ancestry: string;
  background: string;
  class: string;
  level: number;

  // Attributes
  attributes: Attributes;

  // Derived stats
  hitPoints: HitPoints;
  armorClass: number;

  // Progression
  skills: Skill[];
  feats: Feat[];
  spells: SpellSlot[];

  // Equipment
  equipment: Equipment;

  // Status
  conditions: Condition[];
}

// --- World Position ---
export interface WorldPosition {
  mapId: string;        // e.g., "overworld", "dungeon_1"
  x: number;
  y: number;
  facing: number;       // angle in radians
}

// --- Combat State ---
export interface CombatParticipant {
  characterId: string;
  isEnemy: boolean;
  initiative: number;
  gridX: number;
  gridY: number;
  currentHP: number;
}

export interface CombatState {
  participants: CombatParticipant[];
  currentTurn: number;
  roundNumber: number;
}

// --- Party State ---
export interface PartyState {
  characters: Character[];
  position: WorldPosition;
  gold: number;
  inventory: Item[];
}

// --- World State ---
export interface WorldState {
  currentMap: string;
  questFlags: Record<string, any>;
}

// --- UI State ---
export interface UIState {
  activeScreen: string;
  modalStack: string[];
  history: string[];
}

// --- Root Game State ---
export interface GameState {
  party: PartyState;
  world: WorldState;
  combat: CombatState | null;
  ui: UIState;
}

// --- State Store ---
type StateUpdater = (state: GameState) => Partial<GameState>;
type Subscriber = (state: GameState) => void;

export class GameStateStore {
  private state: GameState;
  private subscribers: Map<string, Set<Subscriber>> = new Map();
  private globalSubscribers: Set<Subscriber> = new Set();

  constructor(initialState?: Partial<GameState>) {
    this.state = this.createDefaultState();
    if (initialState) {
      this.state = { ...this.state, ...initialState };
    }
  }

  private createDefaultState(): GameState {
    // Create a default starting character
    const defaultCharacter: Character = {
      id: 'hero1',
      name: 'Warrior',
      ancestry: 'Human',
      background: 'Soldier',
      class: 'Fighter',
      level: 1,
      attributes: {
        strength: 16,
        dexterity: 14,
        constitution: 15,
        intelligence: 10,
        wisdom: 12,
        charisma: 10,
      },
      hitPoints: {
        current: 12,
        max: 12,
      },
      armorClass: 16,
      skills: [
        { id: 'athletics', name: 'Athletics', rank: 3 },
        { id: 'intimidation', name: 'Intimidation', rank: 2 },
      ],
      feats: [
        { id: 'power_attack', name: 'Power Attack' },
      ],
      spells: [],
      equipment: {
        mainHand: {
          id: 'longsword',
          name: 'Longsword',
          type: 'weapon',
          weight: 3,
          value: 15,
          description: '1d8 slashing damage',
        },
        offHand: null,
        armor: {
          id: 'chain_mail',
          name: 'Chain Mail',
          type: 'armor',
          weight: 40,
          value: 50,
          description: 'AC +6',
        },
      },
      conditions: [],
    };

    return {
      party: {
        characters: [defaultCharacter],
        position: {
          mapId: 'overworld',
          x: 16,
          y: 16,
          facing: 0,
        },
        gold: 100,
        inventory: [
          { id: 'potion_healing', name: 'Healing Potion', type: 'consumable', weight: 0.5, value: 50, description: 'Restores 2d4+2 HP' },
          { id: 'potion_healing', name: 'Healing Potion', type: 'consumable', weight: 0.5, value: 50, description: 'Restores 2d4+2 HP' },
          { id: 'rations', name: 'Rations', type: 'consumable', weight: 1, value: 5, description: 'One day of food' },
        ],
      },
      world: {
        currentMap: 'overworld',
        questFlags: {},
      },
      combat: null,
      ui: {
        activeScreen: 'main-menu',
        modalStack: [],
        history: [],
      },
    };
  }

  /**
   * Get a read-only copy of the current state.
   */
  getState(): Readonly<GameState> {
    return this.state;
  }

  /**
   * Update state using an updater function.
   * Returns the updated state.
   */
  setState(updater: StateUpdater): GameState {
    const partial = updater(this.state);
    const oldState = this.state;
    this.state = this.mergeState(this.state, partial);

    // Notify subscribers
    this.notifySubscribers(oldState, this.state);
    return this.state;
  }

  /**
   * Deep merge helper for nested state updates.
   */
  private mergeState(target: any, source: any): any {
    if (source === null || source === undefined) return target;
    if (typeof source !== 'object') return source;
    if (Array.isArray(source)) return source;

    const result = { ...target };
    for (const key in source) {
      if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
        result[key] = this.mergeState(target[key] || {}, source[key]);
      } else {
        result[key] = source[key];
      }
    }
    return result;
  }

  /**
   * Subscribe to state changes at a specific path (e.g., "party.characters").
   * Returns an unsubscribe function.
   */
  subscribe(path: string | null, callback: Subscriber): () => void {
    if (path === null) {
      this.globalSubscribers.add(callback);
      return () => this.globalSubscribers.delete(callback);
    }

    if (!this.subscribers.has(path)) {
      this.subscribers.set(path, new Set());
    }
    this.subscribers.get(path)!.add(callback);

    return () => {
      const subs = this.subscribers.get(path);
      if (subs) {
        subs.delete(callback);
        if (subs.size === 0) {
          this.subscribers.delete(path);
        }
      }
    };
  }

  /**
   * Notify all relevant subscribers of state changes.
   */
  private notifySubscribers(oldState: GameState, newState: GameState) {
    // Notify global subscribers
    this.globalSubscribers.forEach(sub => sub(newState));

    // Notify path-specific subscribers if their path changed
    this.subscribers.forEach((subs, path) => {
      const oldValue = this.getValueAtPath(oldState, path);
      const newValue = this.getValueAtPath(newState, path);
      if (oldValue !== newValue) {
        subs.forEach(sub => sub(newState));
      }
    });
  }

  /**
   * Get value at a dot-separated path (e.g., "party.gold").
   */
  private getValueAtPath(obj: any, path: string): any {
    const keys = path.split('.');
    let current = obj;
    for (const key of keys) {
      if (current === null || current === undefined) return undefined;
      current = current[key];
    }
    return current;
  }

  /**
   * Serialize state to JSON for saving.
   */
  serialize(): string {
    return JSON.stringify(this.state, null, 2);
  }

  /**
   * Deserialize state from JSON.
   */
  static deserialize(json: string): GameStateStore {
    const state = JSON.parse(json) as GameState;
    return new GameStateStore(state);
  }

  /**
   * Save to localStorage.
   */
  saveToLocalStorage(key: string = 'goldbox_save') {
    try {
      localStorage.setItem(key, this.serialize());
      return true;
    } catch (e) {
      console.error('Failed to save game:', e);
      return false;
    }
  }

  /**
   * Load from localStorage.
   */
  static loadFromLocalStorage(key: string = 'goldbox_save'): GameStateStore | null {
    try {
      const json = localStorage.getItem(key);
      if (!json) return null;
      return GameStateStore.deserialize(json);
    } catch (e) {
      console.error('Failed to load game:', e);
      return null;
    }
  }
}
