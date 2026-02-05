// ============================================================
// MainMenuScreen — Main menu with DOM-based UI
// ============================================================

import { Screen, ScreenContext, InputEvent, TransitionType } from '../../core/Screen';
import { GameStateStore } from '../../core/GameState';

export class MainMenuScreen implements Screen {
  readonly id = 'main-menu';

  private context!: ScreenContext;
  private menuContainer!: HTMLDivElement;
  private selectedIndex = 0;
  private menuItems = [
    { label: 'New Game', action: () => this.startNewGame() },
    { label: 'Load Game', action: () => this.loadGame() },
    { label: 'Continue', action: () => this.continueGame() },
  ];

  async init(context: ScreenContext): Promise<void> {
    this.context = context;
    this.createMenuUI();
  }

  private createMenuUI(): void {
    // Create menu container
    this.menuContainer = document.createElement('div');
    this.menuContainer.id = 'main-menu';
    this.menuContainer.style.cssText = `
      position: absolute;
      top: 0;
      left: 0;
      width: 100%;
      height: 100%;
      background: linear-gradient(180deg, #0a0a0a 0%, #1a1a2e 100%);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-family: 'Courier New', monospace;
      color: #d4af37;
      z-index: 100;
    `;

    // Title
    const title = document.createElement('h1');
    title.textContent = 'GOLD BOX CRPG';
    title.style.cssText = `
      font-size: 48px;
      margin-bottom: 60px;
      text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.8);
      letter-spacing: 4px;
    `;
    this.menuContainer.appendChild(title);

    // Menu items container
    const menuList = document.createElement('div');
    menuList.style.cssText = `
      display: flex;
      flex-direction: column;
      gap: 20px;
    `;

    this.menuItems.forEach((item, index) => {
      const menuItem = document.createElement('div');
      menuItem.className = 'menu-item';
      menuItem.dataset.index = index.toString();
      menuItem.textContent = item.label;
      menuItem.style.cssText = `
        font-size: 24px;
        padding: 12px 40px;
        cursor: pointer;
        border: 2px solid transparent;
        transition: all 0.2s;
        text-align: center;
        min-width: 250px;
      `;

      menuItem.addEventListener('mouseenter', () => {
        this.selectedIndex = index;
        this.updateSelection();
      });

      menuItem.addEventListener('click', () => {
        item.action();
      });

      menuList.appendChild(menuItem);
    });

    this.menuContainer.appendChild(menuList);

    // Instructions
    const instructions = document.createElement('div');
    instructions.style.cssText = `
      position: absolute;
      bottom: 30px;
      font-size: 14px;
      color: #888;
    `;
    instructions.textContent = 'Use Arrow Keys or Mouse | Enter to Select';
    this.menuContainer.appendChild(instructions);
  }

  async enter(fromScreen: string | null, params?: any): Promise<void> {
    // Add menu to DOM
    document.body.appendChild(this.menuContainer);
    this.updateSelection();

    // Clear canvas
    const ctx = this.context.canvas.getContext('2d');
    if (ctx) {
      ctx.fillStyle = '#000';
      ctx.fillRect(0, 0, this.context.canvas.width, this.context.canvas.height);
    }
  }

  async exit(toScreen: string | null): Promise<void> {
    // Remove menu from DOM
    if (this.menuContainer.parentElement) {
      this.menuContainer.parentElement.removeChild(this.menuContainer);
    }
  }

  update(dt: number): void {
    // Menu is static, no update needed
  }

  render(): void {
    // Menu is DOM-based, no canvas rendering needed
  }

  handleInput(event: InputEvent): boolean {
    if (event.type === 'keydown') {
      switch (event.key) {
        case 'arrowup':
          this.selectedIndex = (this.selectedIndex - 1 + this.menuItems.length) % this.menuItems.length;
          this.updateSelection();
          return true;

        case 'arrowdown':
          this.selectedIndex = (this.selectedIndex + 1) % this.menuItems.length;
          this.updateSelection();
          return true;

        case 'enter':
          this.menuItems[this.selectedIndex].action();
          return true;
      }
    }

    return false;
  }

  private updateSelection(): void {
    const items = this.menuContainer.querySelectorAll('.menu-item');
    items.forEach((item, index) => {
      const element = item as HTMLDivElement;
      if (index === this.selectedIndex) {
        element.style.border = '2px solid #d4af37';
        element.style.backgroundColor = 'rgba(212, 175, 55, 0.1)';
        element.style.transform = 'scale(1.05)';
      } else {
        element.style.border = '2px solid transparent';
        element.style.backgroundColor = 'transparent';
        element.style.transform = 'scale(1)';
      }
    });
  }

  private startNewGame(): void {
    // Start at overworld
    // TODO: Add character creation screen
    this.context.screenManager.transition('overworld', {
      type: TransitionType.Fade,
      duration: 500,
    });
  }

  private loadGame(): void {
    const savedState = GameStateStore.loadFromLocalStorage('goldbox_save');
    if (savedState) {
      // TODO: Properly restore game state
      this.context.screenManager.transition('overworld', {
        type: TransitionType.Fade,
        duration: 500,
      });
    } else {
      // TODO: Show "No saved game found" message in UI
    }
  }

  private continueGame(): void {
    // Go to overworld with current state
    this.context.screenManager.transition('overworld', {
      type: TransitionType.Fade,
      duration: 500,
    });
  }
}
