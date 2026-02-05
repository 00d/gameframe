// ============================================================
// Main — Bootstrap and game loop
// ============================================================

import { GameStateStore } from './core/GameState';
import { ScreenManager } from './core/Screen';
import { InputManager } from './core/InputManager';

// Screens
import { MainMenuScreen } from './screens/ui/MainMenuScreen';
import { OverworldScreen } from './screens/overworld/OverworldScreen';
import { DungeonScreen } from './screens/dungeon/DungeonScreen';
import { CombatScreen } from './screens/combat/CombatScreen';
import { CharacterSheetScreen } from './screens/ui/CharacterSheetScreen';
import { InventoryScreen } from './screens/ui/InventoryScreen';

async function main() {
  const canvas = document.getElementById('canvas') as HTMLCanvasElement;

  if (!canvas) {
    throw new Error('Canvas element not found');
  }

  // Set canvas resolution (internal size)
  canvas.width = 960;
  canvas.height = 720;

  // Initialize core systems
  const gameState = new GameStateStore();
  const screenManager = new ScreenManager({ gameState, canvas });
  const inputManager = new InputManager(screenManager, canvas);

  // Set up canvas change callback for context switching
  screenManager.setCanvasChangeCallback((newCanvas) => {
    inputManager.updateCanvas(newCanvas);
  });

  // Register screens
  await screenManager.register(new MainMenuScreen());
  await screenManager.register(new OverworldScreen());
  await screenManager.register(new DungeonScreen());
  await screenManager.register(new CombatScreen());
  await screenManager.register(new CharacterSheetScreen());
  await screenManager.register(new InventoryScreen());

  // Start at main menu
  await screenManager.transition('main-menu');

  // Game loop
  let lastTime = performance.now();

  function loop() {
    const now = performance.now();
    const dt = Math.min((now - lastTime) / 1000, 0.05); // cap at 50ms
    lastTime = now;

    screenManager.update(dt);
    screenManager.render();

    requestAnimationFrame(loop);
  }

  requestAnimationFrame(loop);
}

// Start the game
main().catch(error => {
  console.error('Failed to start game:', error);
  document.body.innerHTML = `
    <div style="color: red; padding: 20px; font-family: monospace;">
      <h1>Error</h1>
      <p>Failed to start game: ${error.message}</p>
      <pre>${error.stack}</pre>
    </div>
  `;
});
