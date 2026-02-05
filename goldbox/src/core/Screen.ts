// ============================================================
// Screen — Screen interface and ScreenManager for transitions
// ============================================================

import { GameStateStore } from './GameState';

// --- Input Event ---
export interface InputEvent {
  type: 'keydown' | 'keyup' | 'mousemove' | 'mousedown' | 'mouseup' | 'wheel';
  key?: string;
  code?: string;
  movementX?: number;
  movementY?: number;
  button?: number;
  deltaY?: number;
  x?: number;
  y?: number;
}

// --- Screen Context ---
export interface ScreenContext {
  canvas: HTMLCanvasElement;
  gameState: GameStateStore;
  screenManager: ScreenManager;
}

// --- Screen Interface ---
export interface Screen {
  readonly id: string;

  /**
   * Initialize the screen (called once when registered).
   * Load assets, create resources, etc.
   */
  init(context: ScreenContext): Promise<void>;

  /**
   * Called when entering this screen.
   * @param fromScreen - The screen we're transitioning from (null if first screen)
   * @param params - Optional parameters passed from the previous screen
   */
  enter(fromScreen: string | null, params?: any): Promise<void>;

  /**
   * Called when exiting this screen.
   * @param toScreen - The screen we're transitioning to (null if closing)
   */
  exit(toScreen: string | null): Promise<void>;

  /**
   * Update logic (called every frame when active).
   * @param dt - Delta time in seconds
   */
  update(dt: number): void;

  /**
   * Render logic (called every frame when active).
   */
  render(): void;

  /**
   * Handle input events.
   * @returns true if the event was handled (stops propagation)
   */
  handleInput(event: InputEvent): boolean;
}

// --- Transition Types ---
export enum TransitionType {
  Instant = 'instant',
  Fade = 'fade',
  Slide = 'slide',
}

export interface TransitionOptions {
  type: TransitionType;
  duration?: number; // milliseconds
  params?: any;      // parameters to pass to next screen
}

// --- Transition State Machine ---
enum TransitionState {
  Idle,
  ExitingOld,
  TransitionEffect,
  EnteringNew,
}

// --- Screen Manager ---
export class ScreenManager {
  private screens: Map<string, Screen> = new Map();
  private activeScreen: Screen | null = null;
  private modalStack: Screen[] = [];

  private context: ScreenContext;
  private transitionState: TransitionState = TransitionState.Idle;
  private transitionStartTime: number = 0;
  private transitionDuration: number = 0;
  private transitionType: TransitionType = TransitionType.Instant;
  private nextScreen: Screen | null = null;
  private transitionParams: any = null;

  // Overlay canvas for transition effects
  private overlayCanvas: HTMLCanvasElement;
  private overlayCtx: CanvasRenderingContext2D;

  // Canvas change callback (for InputManager)
  private onCanvasChange: ((canvas: HTMLCanvasElement) => void) | null = null;

  constructor(context: Omit<ScreenContext, 'screenManager'>) {
    this.context = { ...context, screenManager: this };

    // Create overlay canvas for transitions
    this.overlayCanvas = document.createElement('canvas');
    this.overlayCanvas.style.position = 'absolute';
    this.overlayCanvas.style.top = '0';
    this.overlayCanvas.style.left = '0';
    this.overlayCanvas.style.pointerEvents = 'none';
    this.overlayCanvas.style.zIndex = '1000';
    this.overlayCanvas.width = context.canvas.width;
    this.overlayCanvas.height = context.canvas.height;
    this.overlayCtx = this.overlayCanvas.getContext('2d')!;

    context.canvas.parentElement?.appendChild(this.overlayCanvas);
  }

  /**
   * Register a screen.
   */
  async register(screen: Screen): Promise<void> {
    await screen.init(this.context);
    this.screens.set(screen.id, screen);
  }

  /**
   * Transition to a new screen.
   */
  async transition(
    toScreenId: string,
    options: TransitionOptions = { type: TransitionType.Instant }
  ): Promise<void> {
    const toScreen = this.screens.get(toScreenId);
    if (!toScreen) {
      throw new Error(`Screen not found: ${toScreenId}`);
    }

    if (this.transitionState !== TransitionState.Idle) {
      console.warn('Transition already in progress');
      return;
    }

    this.nextScreen = toScreen;
    this.transitionParams = options.params;
    this.transitionType = options.type;
    this.transitionDuration = options.duration || 300;
    this.transitionStartTime = performance.now();
    this.transitionState = TransitionState.ExitingOld;

    // Start async transition
    this.performTransition();
  }

  private async performTransition() {
    // Exit old screen
    if (this.activeScreen) {
      await this.activeScreen.exit(this.nextScreen!.id);
    }

    this.transitionState = TransitionState.TransitionEffect;

    // Check if we need to reset canvas for context type switch
    const fromScreenId = this.activeScreen?.id || null;
    const toScreenId = this.nextScreen!.id;

    // Reset canvas when switching between WebGPU (dungeon) and Canvas2D (others)
    const needsWebGPU = toScreenId === 'dungeon';
    const hadWebGPU = fromScreenId === 'dungeon';

    if (needsWebGPU !== hadWebGPU) {
      this.resetCanvas();
    }

    // Wait for transition effect if not instant
    if (this.transitionType !== TransitionType.Instant) {
      await this.waitForTransitionEffect();
    }

    // Enter new screen
    this.activeScreen = this.nextScreen;
    await this.activeScreen!.enter(fromScreenId, this.transitionParams);

    // Update UI state
    this.context.gameState.setState(state => ({
      ui: {
        ...state.ui,
        activeScreen: this.activeScreen!.id,
        history: [...state.ui.history, this.activeScreen!.id],
      },
    }));

    this.transitionState = TransitionState.Idle;
    this.nextScreen = null;
    this.transitionParams = null;
  }

  private waitForTransitionEffect(): Promise<void> {
    return new Promise(resolve => {
      const checkTransition = () => {
        const elapsed = performance.now() - this.transitionStartTime;
        if (elapsed >= this.transitionDuration) {
          this.overlayCtx.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);
          resolve();
        } else {
          requestAnimationFrame(checkTransition);
        }
      };
      requestAnimationFrame(checkTransition);
    });
  }

  /**
   * Push a modal screen on top of the current screen.
   */
  async pushModal(screenId: string, params?: any): Promise<void> {
    const screen = this.screens.get(screenId);
    if (!screen) {
      throw new Error(`Screen not found: ${screenId}`);
    }

    if (this.activeScreen) {
      this.modalStack.push(this.activeScreen);
    }

    const fromScreenId = this.activeScreen?.id || null;
    this.activeScreen = screen;
    await screen.enter(fromScreenId, params);

    this.context.gameState.setState(state => ({
      ui: {
        ...state.ui,
        activeScreen: screen.id,
        modalStack: [...state.ui.modalStack, screen.id],
      },
    }));
  }

  /**
   * Pop the top modal screen.
   */
  async popModal(): Promise<void> {
    if (this.modalStack.length === 0) {
      console.warn('No modal to pop');
      return;
    }

    const toScreenId = this.modalStack[this.modalStack.length - 1].id;
    if (this.activeScreen) {
      await this.activeScreen.exit(toScreenId);
    }

    this.activeScreen = this.modalStack.pop()!;
    await this.activeScreen.enter(null);

    this.context.gameState.setState(state => ({
      ui: {
        ...state.ui,
        activeScreen: this.activeScreen!.id,
        modalStack: state.ui.modalStack.slice(0, -1),
      },
    }));
  }

  /**
   * Update the active screen.
   */
  update(dt: number): void {
    if (this.transitionState !== TransitionState.Idle) {
      this.renderTransitionEffect();
      return;
    }

    if (this.activeScreen) {
      this.activeScreen.update(dt);
    }
  }

  /**
   * Render the active screen.
   */
  render(): void {
    if (this.transitionState !== TransitionState.Idle) {
      return; // Transition rendering handled in update
    }

    if (this.activeScreen) {
      this.activeScreen.render();
    }
  }

  /**
   * Render transition effects.
   */
  private renderTransitionEffect(): void {
    if (this.transitionType === TransitionType.Instant) return;

    const elapsed = performance.now() - this.transitionStartTime;
    const progress = Math.min(elapsed / this.transitionDuration, 1);

    this.overlayCtx.clearRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);

    if (this.transitionType === TransitionType.Fade) {
      // Fade to black
      const alpha = progress < 0.5 ? progress * 2 : (1 - progress) * 2;
      this.overlayCtx.fillStyle = `rgba(0, 0, 0, ${alpha})`;
      this.overlayCtx.fillRect(0, 0, this.overlayCanvas.width, this.overlayCanvas.height);
    } else if (this.transitionType === TransitionType.Slide) {
      // Slide effect (simple left-to-right wipe)
      const x = progress * this.overlayCanvas.width;
      this.overlayCtx.fillStyle = 'black';
      this.overlayCtx.fillRect(0, 0, x, this.overlayCanvas.height);
    }
  }

  /**
   * Dispatch input event to active screen.
   * Returns true if handled.
   */
  handleInput(event: InputEvent): boolean {
    if (this.transitionState !== TransitionState.Idle) {
      return true; // Block input during transitions
    }

    if (this.activeScreen) {
      return this.activeScreen.handleInput(event);
    }
    return false;
  }

  /**
   * Get the currently active screen.
   */
  getActiveScreen(): Screen | null {
    return this.activeScreen;
  }

  /**
   * Check if a screen is registered.
   */
  hasScreen(id: string): boolean {
    return this.screens.has(id);
  }

  /**
   * Get the game state store.
   */
  getGameState(): GameStateStore {
    return this.context.gameState;
  }

  /**
   * Set callback for when canvas is replaced.
   */
  setCanvasChangeCallback(callback: (canvas: HTMLCanvasElement) => void): void {
    this.onCanvasChange = callback;
  }

  /**
   * Reset canvas by replacing it with a fresh one.
   * Necessary when switching between Canvas2D and WebGPU contexts.
   */
  private resetCanvas(): void {
    const oldCanvas = this.context.canvas;
    const parent = oldCanvas.parentElement;

    if (!parent) return;

    // Create new canvas with same properties
    const newCanvas = document.createElement('canvas');
    newCanvas.id = oldCanvas.id;
    newCanvas.width = oldCanvas.width;
    newCanvas.height = oldCanvas.height;
    newCanvas.style.cssText = oldCanvas.style.cssText;

    // Replace old canvas
    parent.replaceChild(newCanvas, oldCanvas);

    // Update context reference
    this.context.canvas = newCanvas;

    // Update overlay canvas dimensions if needed
    if (this.overlayCanvas) {
      this.overlayCanvas.width = newCanvas.width;
      this.overlayCanvas.height = newCanvas.height;
    }

    // Notify callback (for InputManager)
    if (this.onCanvasChange) {
      this.onCanvasChange(newCanvas);
    }
  }
}
