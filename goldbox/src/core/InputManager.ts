// ============================================================
// InputManager — Global input routing with priority system
// ============================================================

import { ScreenManager } from './Screen';
import type { InputEvent } from './Screen';
import { GameStateStore } from './GameState';

export class InputManager {
  private screenManager: ScreenManager;
  private canvas: HTMLCanvasElement;

  // Track key states for polling
  private keysDown: Set<string> = new Set();
  private mouseButtons: Set<number> = new Set();

  // Pointer lock state
  private pointerLocked: boolean = false;

  // Global shortcuts
  private globalShortcuts: Map<string, () => void> = new Map();

  // Bound event handlers (for proper removal)
  private boundHandlers = {
    mousedown: this.onMouseDown.bind(this),
    mouseup: this.onMouseUp.bind(this),
    mousemove: this.onMouseMove.bind(this),
    wheel: this.onWheel.bind(this),
    click: this.onCanvasClick.bind(this),
    contextmenu: (e: Event) => e.preventDefault(),
  };

  constructor(screenManager: ScreenManager, canvas: HTMLCanvasElement) {
    this.screenManager = screenManager;
    this.canvas = canvas;

    this.setupEventListeners();
    this.setupGlobalShortcuts();
  }

  private setupEventListeners(): void {
    // Keyboard (window-level, don't need to remove)
    window.addEventListener('keydown', this.onKeyDown.bind(this));
    window.addEventListener('keyup', this.onKeyUp.bind(this));

    // Pointer lock change (document-level, don't need to remove)
    document.addEventListener('pointerlockchange', this.onPointerLockChange.bind(this));

    // Canvas-specific events
    this.attachCanvasListeners();
  }

  private attachCanvasListeners(): void {
    this.canvas.addEventListener('mousedown', this.boundHandlers.mousedown);
    this.canvas.addEventListener('mouseup', this.boundHandlers.mouseup);
    this.canvas.addEventListener('mousemove', this.boundHandlers.mousemove);
    this.canvas.addEventListener('wheel', this.boundHandlers.wheel);
    this.canvas.addEventListener('click', this.boundHandlers.click);
    this.canvas.addEventListener('contextmenu', this.boundHandlers.contextmenu);
  }

  private detachCanvasListeners(): void {
    this.canvas.removeEventListener('mousedown', this.boundHandlers.mousedown);
    this.canvas.removeEventListener('mouseup', this.boundHandlers.mouseup);
    this.canvas.removeEventListener('mousemove', this.boundHandlers.mousemove);
    this.canvas.removeEventListener('wheel', this.boundHandlers.wheel);
    this.canvas.removeEventListener('click', this.boundHandlers.click);
    this.canvas.removeEventListener('contextmenu', this.boundHandlers.contextmenu);
  }

  private setupGlobalShortcuts(): void {
    // ESC = back/menu
    this.registerGlobalShortcut('Escape', () => {
      const state = this.screenManager.getActiveScreen();
      if (state && state.id !== 'main-menu') {
        // Try to pop modal first, otherwise go to menu
        const modalStack = this.screenManager.getGameState().getState().ui.modalStack;
        if (modalStack.length > 0) {
          this.screenManager.popModal();
        } else {
          this.screenManager.transition('main-menu');
        }
      }
    });

    // F5 = quicksave (prevent default browser refresh)
    this.registerGlobalShortcut('F5', () => {
      const gameState = this.screenManager.getGameState();
      gameState.saveToLocalStorage('goldbox_quicksave');
      // TODO: Show save confirmation UI
    });

    // F9 = quickload
    this.registerGlobalShortcut('F9', () => {
      const savedState = GameStateStore.loadFromLocalStorage('goldbox_quicksave');
      if (savedState) {
        // TODO: Properly restore game state and reload current screen
        // For now, this is a placeholder
      }
    });
  }

  /**
   * Register a global keyboard shortcut.
   */
  registerGlobalShortcut(key: string, callback: () => void): void {
    this.globalShortcuts.set(key, callback);
  }

  /**
   * Check if a specific key is currently down.
   */
  isKeyDown(key: string): boolean {
    return this.keysDown.has(key.toLowerCase());
  }

  /**
   * Check if a specific mouse button is down.
   */
  isMouseButtonDown(button: number): boolean {
    return this.mouseButtons.has(button);
  }

  /**
   * Request pointer lock (for 3D camera control).
   */
  requestPointerLock(): void {
    this.canvas.requestPointerLock();
  }

  /**
   * Release pointer lock.
   */
  releasePointerLock(): void {
    if (this.pointerLocked) {
      document.exitPointerLock();
    }
  }

  /**
   * Check if pointer is locked.
   */
  isPointerLocked(): boolean {
    return this.pointerLocked;
  }

  // --- Event Handlers ---

  private onKeyDown(e: KeyboardEvent): void {
    this.keysDown.add(e.key.toLowerCase());

    // Check global shortcuts first
    if (this.globalShortcuts.has(e.code)) {
      e.preventDefault();
      this.globalShortcuts.get(e.code)!();
      return;
    }

    // Route to active screen
    const event: InputEvent = {
      type: 'keydown',
      key: e.key.toLowerCase(),
      code: e.code,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onKeyUp(e: KeyboardEvent): void {
    this.keysDown.delete(e.key.toLowerCase());

    const event: InputEvent = {
      type: 'keyup',
      key: e.key.toLowerCase(),
      code: e.code,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onMouseDown(e: MouseEvent): void {
    this.mouseButtons.add(e.button);

    const rect = this.canvas.getBoundingClientRect();
    const event: InputEvent = {
      type: 'mousedown',
      button: e.button,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onMouseUp(e: MouseEvent): void {
    this.mouseButtons.delete(e.button);

    const rect = this.canvas.getBoundingClientRect();
    const event: InputEvent = {
      type: 'mouseup',
      button: e.button,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onMouseMove(e: MouseEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const event: InputEvent = {
      type: 'mousemove',
      movementX: e.movementX,
      movementY: e.movementY,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onWheel(e: WheelEvent): void {
    const rect = this.canvas.getBoundingClientRect();
    const event: InputEvent = {
      type: 'wheel',
      deltaY: e.deltaY,
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    };

    const handled = this.screenManager.handleInput(event);
    if (handled) {
      e.preventDefault();
    }
  }

  private onCanvasClick(): void {
    // Only request pointer lock for screens that need it (dungeon)
    const activeScreen = this.screenManager.getActiveScreen();
    if (activeScreen && activeScreen.id === 'dungeon' && !this.pointerLocked) {
      this.requestPointerLock();
    }
  }

  private onPointerLockChange(): void {
    this.pointerLocked = document.pointerLockElement === this.canvas;
  }

  /**
   * Clear all input state (useful when changing screens).
   */
  clearState(): void {
    this.keysDown.clear();
    this.mouseButtons.clear();
  }

  /**
   * Update canvas reference and re-setup event listeners.
   * Called when canvas is replaced (e.g., switching between WebGPU and Canvas2D).
   */
  updateCanvas(newCanvas: HTMLCanvasElement): void {
    // Remove listeners from old canvas
    this.detachCanvasListeners();

    // Update reference
    this.canvas = newCanvas;

    // Add listeners to new canvas
    this.attachCanvasListeners();
  }
}
