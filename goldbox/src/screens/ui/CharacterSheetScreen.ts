// ============================================================
// CharacterSheetScreen — Character sheet modal overlay
// ============================================================

import { Screen, ScreenContext, InputEvent } from '../../core/Screen';

export class CharacterSheetScreen implements Screen {
  readonly id = 'character-sheet';

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
    // Update content with current character data
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
      if (event.key === 'escape' || event.key === 'c') {
        this.context.screenManager.popModal();
        return true;
      }
    }
    return true; // Block all input from underlying screen
  }

  private updateContent(): void {
    const gameState = this.context.gameState.getState();
    const character = gameState.party.characters[0]; // First character for now

    if (!character) {
      this.modalContainer.innerHTML = `
        <h2 style="margin: 0 0 20px 0; text-align: center; font-size: 24px; border-bottom: 2px solid #d4af37; padding-bottom: 10px;">
          CHARACTER SHEET
        </h2>
        <div style="text-align: center; margin: 40px 0;">
          No character data available
        </div>
        <div style="text-align: center; margin-top: 20px; color: #888;">
          Press ESC to close
        </div>
      `;
      return;
    }

    // Calculate ability modifiers
    const getModifier = (score: number) => {
      const mod = Math.floor((score - 10) / 2);
      return mod >= 0 ? `+${mod}` : `${mod}`;
    };

    this.modalContainer.innerHTML = `
      <h2 style="margin: 0 0 20px 0; text-align: center; font-size: 24px; border-bottom: 2px solid #d4af37; padding-bottom: 10px;">
        CHARACTER SHEET
      </h2>

      <div style="margin-bottom: 15px;">
        <strong>Name:</strong> ${character.name}<br>
        <strong>Class:</strong> ${character.class}<br>
        <strong>Level:</strong> ${character.level}<br>
        <strong>Ancestry:</strong> ${character.ancestry}<br>
        <strong>Background:</strong> ${character.background}<br>
      </div>

      <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
        <strong>ATTRIBUTES</strong><br>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin-top: 5px;">
          <div>STR: ${character.attributes.strength} (${getModifier(character.attributes.strength)})</div>
          <div>DEX: ${character.attributes.dexterity} (${getModifier(character.attributes.dexterity)})</div>
          <div>CON: ${character.attributes.constitution} (${getModifier(character.attributes.constitution)})</div>
          <div>INT: ${character.attributes.intelligence} (${getModifier(character.attributes.intelligence)})</div>
          <div>WIS: ${character.attributes.wisdom} (${getModifier(character.attributes.wisdom)})</div>
          <div>CHA: ${character.attributes.charisma} (${getModifier(character.attributes.charisma)})</div>
        </div>
      </div>

      <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
        <strong>COMBAT</strong><br>
        HP: ${character.hitPoints.current} / ${character.hitPoints.max}<br>
        AC: ${character.armorClass}<br>
      </div>

      <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
        <strong>SKILLS</strong><br>
        ${character.skills.length > 0
          ? character.skills.map(s => `${s.name}: +${s.rank}`).join('<br>')
          : 'None'}
      </div>

      <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
        <strong>FEATS</strong><br>
        ${character.feats.length > 0
          ? character.feats.map(f => f.name).join('<br>')
          : 'None'}
      </div>

      <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
        <strong>EQUIPMENT</strong><br>
        <strong>Main Hand:</strong> ${character.equipment.mainHand?.name || 'None'}<br>
        ${character.equipment.mainHand?.description ? `<span style="font-size: 12px; color: #999;">${character.equipment.mainHand.description}</span><br>` : ''}
        <strong>Off Hand:</strong> ${character.equipment.offHand?.name || 'None'}<br>
        <strong>Armor:</strong> ${character.equipment.armor?.name || 'None'}<br>
        ${character.equipment.armor?.description ? `<span style="font-size: 12px; color: #999;">${character.equipment.armor.description}</span><br>` : ''}
      </div>

      ${character.conditions.length > 0 ? `
        <div style="margin-bottom: 15px; border-top: 1px solid #555; padding-top: 10px;">
          <strong>CONDITIONS</strong><br>
          ${character.conditions.map(c => c.name).join(', ')}
        </div>
      ` : ''}

      <div style="text-align: center; margin-top: 20px; color: #888;">
        Press ESC or C to close
      </div>
    `;
  }
}
