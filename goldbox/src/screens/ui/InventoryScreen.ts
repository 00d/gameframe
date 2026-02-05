// ============================================================
// InventoryScreen — Inventory modal overlay
// ============================================================

import { Screen, ScreenContext, InputEvent } from '../../core/Screen';

export class InventoryScreen implements Screen {
  readonly id = 'inventory';

  private context!: ScreenContext;
  private modalContainer!: HTMLDivElement;

  async init(context: ScreenContext): Promise<void> {
    this.context = context;
    this.createModalUI();
  }

  private createModalUI(): void {
    this.modalContainer = document.createElement('div');
    this.modalContainer.style.cssText = `
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      width: 600px;
      max-height: 80%;
      background: rgba(20, 20, 30, 0.95);
      border: 3px solid #d4af37;
      padding: 20px;
      font-family: 'Courier New', monospace;
      color: #d4af37;
      overflow-y: auto;
      z-index: 200;
      box-shadow: 0 0 30px rgba(0, 0, 0, 0.8);
    `;
  }

  async enter(fromScreen: string | null, params?: any): Promise<void> {
    // Update content with current inventory data
    this.updateContent();
    document.body.appendChild(this.modalContainer);
  }

  async exit(toScreen: string | null): Promise<void> {
    if (this.modalContainer.parentElement) {
      this.modalContainer.parentElement.removeChild(this.modalContainer);
    }
  }

  update(dt: number): void {
    // Static UI
  }

  render(): void {
    // DOM-based, no canvas rendering
  }

  handleInput(event: InputEvent): boolean {
    if (event.type === 'keydown') {
      if (event.key === 'escape' || event.key === 'i') {
        this.context.screenManager.popModal();
        return true;
      }
    }
    return true; // Block all input from underlying screen
  }

  private updateContent(): void {
    const gameState = this.context.gameState.getState();
    const gold = gameState.party.gold;
    const inventory = gameState.party.inventory;

    // Group items by type
    const groupedItems: Record<string, any[]> = {
      weapon: [],
      armor: [],
      consumable: [],
      misc: [],
    };

    inventory.forEach(item => {
      if (groupedItems[item.type]) {
        groupedItems[item.type].push(item);
      } else {
        groupedItems.misc.push(item);
      }
    });

    // Count duplicate items
    const itemCounts = new Map<string, { item: any; count: number }>();
    inventory.forEach(item => {
      const existing = itemCounts.get(item.id);
      if (existing) {
        existing.count++;
      } else {
        itemCounts.set(item.id, { item, count: 1 });
      }
    });

    const renderItemList = (items: any[]) => {
      if (items.length === 0) return '<span style="color: #888;">None</span>';

      const uniqueItems = Array.from(
        new Map(items.map(item => [item.id, item])).values()
      );

      return uniqueItems.map(item => {
        const count = itemCounts.get(item.id)?.count || 1;
        const countStr = count > 1 ? ` x${count}` : '';
        const desc = item.description ? `<br><span style="font-size: 11px; color: #999; margin-left: 15px;">${item.description}</span>` : '';
        const weight = item.weight ? ` (${item.weight * count} lbs)` : '';
        const value = item.value ? ` - ${item.value}gp` : '';
        return `• ${item.name}${countStr}${weight}${value}${desc}`;
      }).join('<br>');
    };

    this.modalContainer.innerHTML = `
      <h2 style="margin: 0 0 20px 0; text-align: center; font-size: 24px; border-bottom: 2px solid #d4af37; padding-bottom: 10px;">
        INVENTORY
      </h2>

      <div style="margin-bottom: 15px;">
        <strong>Gold:</strong> ${gold} gp
      </div>

      ${inventory.length > 0 ? `
        <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
          <strong>WEAPONS</strong><br>
          ${renderItemList(groupedItems.weapon)}
        </div>

        <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
          <strong>ARMOR</strong><br>
          ${renderItemList(groupedItems.armor)}
        </div>

        <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
          <strong>CONSUMABLES</strong><br>
          ${renderItemList(groupedItems.consumable)}
        </div>

        ${groupedItems.misc.length > 0 ? `
          <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
            <strong>MISCELLANEOUS</strong><br>
            ${renderItemList(groupedItems.misc)}
          </div>
        ` : ''}
      ` : `
        <div style="text-align: center; margin: 40px 0; color: #888;">
          Inventory is empty
        </div>
      `}

      <div style="text-align: center; margin-top: 20px; color: #888;">
        Press ESC or I to close
      </div>
    `;
  }
}
