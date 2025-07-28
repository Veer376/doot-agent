import asyncio
from typing import TYPE_CHECKING, Optional, Dict

if TYPE_CHECKING:
    from playwright.async_api import Page, ElementHandle
    from .dom.types import DOMElementNode


class Simulator:
    """
    Manages the injection and execution of browser animations for a specific page.
    This class encapsulates the Python methods to trigger animations and the
    underlying JavaScript code that creates the visual effects.
    """

    def __init__(self, page: Optional["Page"]):
        """
        Initializes the Simulator with a Playwright Page object.
        The page object is optional during instantiation but required for execution.
        """
        self.page = page

        # script
        self.simulator_script = """
        (() => {
            // Setup styles and cursor
            if (window.playwrightAnimationsSetup) return;
            const styles = `
                #playwright-cursor { position: absolute; pointer-events: none; z-index: 2147483647; transition: top 0.15s cubic-bezier(0.65, 0, 0.35, 1), left 0.15s cubic-bezier(0.65, 0, 0.35, 1); }
                .playwright-cursor-icon { width: 27px; height: 27px; background-repeat: no-repeat; background-size: contain; transform: translate(-50%, -50%); filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5)); display: none; }
                #playwright-cursor-pointer-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24'%3E%3Cpath fill='black' stroke='white' stroke-width='1.5' d='M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87a.5.5 0 0 0 .35-.85L6.35 2.85a.5.5 0 0 0-.85.35Z'/%3E%3C/svg%3E"); }
                #playwright-cursor-text-icon { width: 2px; height: 22px; background-color: black; animation: blink 1s infinite; filter: none; }
                #playwright-cursor-scroll-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2L9 6h6l-3-4zm0 20l3-4H9l3 4zm8-10l-4 3v-6l4 3zM4 12l4-3v6l-4-3z'/%3E%3C/svg%3E"); }
                #playwright-cursor-key-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M20 5H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm-9 11H5v-2h6v2zm0-3H5V9h6v2zm7 3h-6v-2h6v2zm0-3h-6V9h6v2z'/%3E%3C/svg%3E"); }
                #playwright-cursor-info-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z'/%3E%3C/svg%3E"); }
                #playwright-cursor-processing-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='white' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 1 0 10 10'/%3E%3Cpath fill='black' stroke='black' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 0 0-7.07 2.93'/%3E%3C/svg%3E"); animation: rotate 1s linear infinite; }
                @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
                @keyframes rotate { from { transform: translate(-50%, -50%) rotate(0deg); } to { transform: translate(-50%, -50%) rotate(360deg); } }
                .cursor-click-down #playwright-cursor-pointer-icon, .cursor-key-press #playwright-cursor-key-icon { animation: press-effect 0.2s cubic-bezier(0.250, 0.460, 0.450, 0.940) forwards; }
                @keyframes press-effect { 0% { transform: translate(-50%, -50%) scale(1); } 50% { transform: translate(-50%, -50%) scale(0.5); } 100% { transform: translate(-50%, -50%) scale(1); } }
                .icon-fade-in { animation: fade-in 0.3s ease-out forwards; }
                @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
                #playwright-cursor-textbox { position: absolute; top: 10px; left: 10px; background: rgba(255, 255, 255, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.39); color: black; padding: 6px 12px; font-family: 'Quicksand', sans-serif; font-size: 14px; font-weight: 500; transition: all 0.3s ease-out; max-width: 375px; word-wrap: break-word; opacity: 0; transform: translateY(-10px); }
                .textbox-appear { opacity: 1 !important; transform: translateY(0) !important; }
                .splash-line { position: absolute; width: 3.5px; pointer-events: none; background-color: #2d3748; border-radius: 9999px; transform-origin: top center; z-index: 2147483646; animation: line-clip-and-retract 0.4s cubic-bezier(0.5, 1, 0.9, 1) forwards; }
                @keyframes line-clip-and-retract { 0% { clip-path: inset(0 0 100% 0); } 30% { clip-path: inset(0 0 0 0); } 100% { clip-path: inset(100% 0 0 0); } }
                .scroll-indicator { position: absolute; z-index: 2147483646; width: 10px; height: 30px; transform: translateX(-50%); }
                @keyframes scroll-down { 0% { transform: translate(-50%, -30px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translate(-50%, 30px); opacity: 0; } }
                @keyframes scroll-up { 0% { transform: translate(-50%, 30px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translate(-50%, -30px); opacity: 0; } }
                #screenshot-flash { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: white; z-index: 2147483647; opacity: 0; pointer-events: none; transition: opacity 0.3s ease-out; }
                #screenshot-flash.active { opacity: 0.8; }
                
                #screenshot-thumbnail {
                    position: fixed;
                    bottom: 20px;
                    left: 20px;
                    z-index: 2147483647;
                    opacity: 0;
                    transform: translateY(20px);
                    transition: opacity 0.4s ease-out, transform 0.4s ease-out;
                    pointer-events: none;
                    width: 300px;
                    height: 180px;
                    background: rgba(255, 255, 255, 0.4);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border-radius: 20px;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.5),
                                inset 0 -1px 0 rgba(255, 255, 255, 0.1),
                                inset 0 0 24px 12px rgba(255, 255, 255, 1.2);
                    overflow: hidden;
                }

                #screenshot-thumbnail::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 1px;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.8), transparent);
                }

                #screenshot-thumbnail::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 1px;
                    height: 100%;
                    background: linear-gradient(180deg, rgba(255, 255, 255, 0.8), transparent, rgba(255, 255, 255, 0.3));
                }

                #screenshot-thumbnail.visible { opacity: 1; transform: translateY(0); }
                #screenshot-thumbnail.shrink { transform: scale(0); opacity: 0; transition: opacity 0.5s ease-in, transform 0.5s ease-in; }
                
                .mock-browser { position: relative; width: 100%; height: 100%; border-radius: 10px; background: transparent; overflow: hidden; }
                .mock-browser-header { height: 20px; background: linear-gradient(180deg, #f1f5f9 0%, #e2e8f0 100%); border-bottom: 1px solid #cbd5e1; display: flex; align-items: center; padding: 0 8px; justify-content: space-between; }
                .mock-url-bar { flex-grow: 1; height: 12px; background: white; border: 1px solid #cbd5e1; border-radius: 6px; margin: 0 4px; position: relative; font-size: 6px; display: flex; align-items: center; padding: 0 4px; color: #64748b; }
                .mock-url-bar::before { content: "🔒 example.com/dashboard"; font-size: 5px; }
                .mock-close-buttons { display: flex; gap: 2px; }
                .mock-close-btn { width: 6px; height: 6px; border-radius: 50%; }
                .mock-close-btn.red { background: #ef4444; }
                .mock-close-btn.yellow { background: #eab308; }
                .mock-close-btn.green { background: #22c55e; }
                
                .mock-content { padding: 8px; height: calc(100% - 20px); background: transparent; position: relative; }
                .mock-profile { position: absolute; top: 6px; left: 8px; width: 16px; height: 16px; background: linear-gradient(135deg, #6b7280 0%, #4b5563 100%); border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-size: 8px; font-weight: bold; border: 1px solid #9ca3af; }
                .mock-profile::before { content: ""; width: 8px; height: 8px; background: #d1d5db; border-radius: 50%; position: relative; }
                .mock-profile::after { content: ""; position: absolute; bottom: 2px; width: 10px; height: 6px; background: #d1d5db; border-radius: 0 0 8px 8px; }
                
                .mock-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 24px; height: calc(100% - 32px); }
                
                .mock-card {
                    background: rgba(255, 255, 255, 0.2);
                    backdrop-filter: blur(5px);
                    -webkit-backdrop-filter: blur(5px);
                    border: 1px solid rgba(255, 255, 255, 0.2);
                    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.05);
                    border-radius: 6px; 
                    padding: 6px; 
                    position: relative;
                }

                .mock-image { 
                    width: 100%; 
                    height: 23px; 
                    background: transparent; 
                    border-radius: 4px; 
                    position: relative; 
                    overflow: hidden; 
                    margin-bottom: 4px;
                    border: none;
                }
                
                /* Sun */
                .mock-image::before { 
                    content: ""; 
                    position: absolute; 
                    top: 3px; 
                    right: 5px; 
                    width: 6px; 
                    height: 6px; 
                    background: #9ca3af; 
                    border-radius: 50%; 
                    border: 1px solid #6b7280;
                }
                
                /* Mountains */
                .mock-image::after { 
                    content: ""; 
                    position: absolute; 
                    bottom: 0; 
                    left: 0; 
                    width: 100%; 
                    height: 10px; 
                    background: linear-gradient(45deg, transparent 30%, #9ca3af 30%, #9ca3af 50%, #6b7280 50%, #6b7280 70%, transparent 70%);
                    clip-path: polygon(0 100%, 20% 30%, 40% 60%, 60% 20%, 80% 50%, 100% 40%, 100% 100%);
                }
                
                /* Clouds */
                .mock-cloud { 
                    position: absolute; 
                    top: 4px; 
                    left: 6px; 
                    width: 10px; 
                    height: 3px; 
                    background: #d1d5db; 
                    border-radius: 6px; 
                    opacity: 0.8;
                }
                .mock-cloud::before { 
                    content: ""; 
                    position: absolute; 
                    top: -1px; 
                    left: 2px; 
                    width: 2px; 
                    height: 2px; 
                    background: #d1d5db; 
                    border-radius: 50%; 
                }
                .mock-cloud::after { 
                    content: ""; 
                    position: absolute; 
                    top: -1px; 
                    right: 1px; 
                    width: 2px; 
                    height: 2px; 
                    background: #d1d5db; 
                    border-radius: 50%; 
                }
                
                .mock-lines { display: flex; flex-direction: column; gap: 2px; }
                .mock-line { height: 2px; background: #cbd5e1; border-radius: 1px; }
                .mock-line:nth-child(1) { width: 90%; }
                .mock-line:nth-child(2) { width: 70%; }
                .mock-line:nth-child(3) { width: 85%; }
                
                .mock-cursor { position: absolute; top: 0; left: 0; width: 15px; height: 15px; pointer-events: none; z-index: 20; }
                .mock-cursor-icon { width: 100%; height: 100%; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24'%3E%3Cpath fill='black' stroke='black' stroke-width='1.5' d='M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87a.5.5 0 0 0 .35-.85L6.35 2.85a.5.5 0 0 0-.85.35Z'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-size: contain; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.3)); transform-origin: top left; }
                
                @keyframes mock-cursor-sequence {
                    0% { transform: translate(var(--start-x), var(--start-y)); opacity: 0; }
                    20% { transform: translate(var(--start-x), var(--start-y)); opacity: 1; }
                    80% { transform: translate(235px, 120px); }
                    90% { transform: translate(235px, 120px) scale(0.7); }
                    100% { transform: translate(235px, 120px) scale(1); opacity: 1; }
                }
                
                .mock-cursor.animated { animation: mock-cursor-sequence 2s ease-in-out forwards; }
            `;
            const styleSheet = document.createElement("style");
            styleSheet.id = 'pointer-animation-styles';
            styleSheet.innerText = styles;
            document.head.appendChild(styleSheet);

            const cursor = document.createElement('div');
            cursor.id = 'playwright-cursor';
            ['pointer', 'text', 'scroll', 'key', 'info', 'processing'].forEach(iconType => {
                const iconEl = document.createElement('div');
                iconEl.id = `playwright-cursor-${iconType}-icon`;
                iconEl.className = 'playwright-cursor-icon';
                cursor.appendChild(iconEl);
            });
            cursor.style.left = '-100px';
            cursor.style.top = '-100px';
            document.body.appendChild(cursor);

            window.playwrightAnimationsSetup = true;
            window.playwrightTimers = new Set();

            // Main animation function
            window.run_animation = async (params) => {
                const { coords, action = { type: 'click' }, text } = params;
                const { type, direction } = action;

                // Comprehensive cleanup & timer fix
                if (window.playwrightTimers) {
                    window.playwrightTimers.forEach(timer => clearTimeout(timer)); // Works for intervals too
                    window.playwrightTimers.clear();
                }

                document.querySelectorAll('#playwright-cursor-textbox, .scroll-indicator, .splash-line').forEach(el => el.remove());

                const cursor = document.getElementById('playwright-cursor');
                if (!cursor) { console.error("Cursor animation setup has not been run."); return; }

                document.querySelectorAll('.playwright-cursor-icon').forEach(icon => icon.style.display = 'none');
                if (type !== 'screenshot') {
                     const activeIcon = document.getElementById(`playwright-cursor-${type}-icon`) || document.getElementById('playwright-cursor-pointer-icon');
                     activeIcon.style.display = 'block';
                }

                const endX = coords ? coords.x : parseFloat(cursor.style.left);
                const endY = coords ? coords.y : parseFloat(cursor.style.top);

                function typeText(textBox, fullText, callback) {
                    textBox.innerHTML = fullText;
                    textBox.classList.add('textbox-appear');
                    if (callback) {
                        const timer = setTimeout(callback, 300);
                        window.playwrightTimers.add(timer);
                    }
                }

                async function triggerActionAnimations() {
                    if (type === 'click') {
                        cursor.classList.add('cursor-click-down');
                        const timer1 = setTimeout(() => cursor.classList.remove('cursor-click-down'), 200);
                        window.playwrightTimers.add(timer1);

                        const timer2 = setTimeout(() => {
                            const splashOriginX = endX - 7;
                            const splashOriginY = endY - 11;
                            for (let i = 0; i < 8; i++) {
                                const line = document.createElement('div');
                                line.className = 'splash-line';
                                const rotation = i * (360 / 8);
                                line.style.height = `${Math.random() * 5 + 18}px`;
                                line.style.left = `${splashOriginX}px`;
                                line.style.top = `${splashOriginY}px`;
                                line.style.transform = `translateX(-50%) rotate(${rotation}deg)`;
                                document.body.appendChild(line);
                                const cleanupTimer = setTimeout(() => line.remove(), 400);
                                window.playwrightTimers.add(cleanupTimer);
                            }
                        }, 50);
                        window.playwrightTimers.add(timer2);
                    } else if (type === 'key') {
                        cursor.classList.add('cursor-key-press');
                        const timer = setTimeout(() => cursor.classList.remove('cursor-key-press'), 200);
                        window.playwrightTimers.add(timer);
                    } else if (type === 'scroll' && direction) {
                        const indicator = document.createElement('div');
                        indicator.className = 'scroll-indicator';
                        indicator.style.left = `${endX}px`;
                        indicator.style.top = `${endY}px`;
                        indicator.style.animation = `scroll-${direction} 0.4s ease-out forwards`;
                        if (direction === 'down') indicator.innerHTML = `<svg width="10" height="30" viewBox="0 0 10 30"><line x1="5" y1="0" x2="5" y2="20" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/><path d="M0 20 L5 30 L10 20 Z" fill="rgba(0,0,0,0.4)"/></svg>`;
                        else if (direction === 'up') indicator.innerHTML = `<svg width="10" height="30" viewBox="0 0 10 30"><path d="M0 10 L5 0 L10 10 Z" fill="rgba(0,0,0,0.4)"/><line x1="5" y1="10" x2="5" y2="30" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/></svg>`;
                        document.body.appendChild(indicator);
                        const timer = setTimeout(() => indicator.remove(), 400);
                        window.playwrightTimers.add(timer);
                    } else if (type === 'screenshot') {
                        document.querySelectorAll('#screenshot-flash, #screenshot-thumbnail').forEach(el => el.remove());

                        const flashElement = document.createElement('div');
                        flashElement.id = 'screenshot-flash';
                        document.body.appendChild(flashElement);

                        const thumbnailElement = document.createElement('div');
                        thumbnailElement.id = 'screenshot-thumbnail';
                        
                        // Create mock browser interface
                        thumbnailElement.innerHTML = `
                            <div class="mock-browser">
                                <div class="mock-browser-header">
                                    <div class="mock-close-buttons">
                                        <div class="mock-close-btn red"></div>
                                        <div class="mock-close-btn yellow"></div>
                                        <div class="mock-close-btn green"></div>
                                    </div>
                                    <div class="mock-url-bar"></div>
                                </div>
                                <div class="mock-content">
                                    <div class="mock-profile"></div>
                                    <div class="mock-grid">
                                        <div class="mock-card">
                                            <div class="mock-image">
                                                <div class="mock-cloud"></div>
                                            </div>
                                            <div class="mock-lines">
                                                <div class="mock-line"></div>
                                                <div class="mock-line"></div>
                                                <div class="mock-line"></div>
                                            </div>
                                        </div>
                                        <div class="mock-card">
                                            <div class="mock-image">
                                                <div class="mock-cloud"></div>
                                            </div>
                                            <div class="mock-lines">
                                                <div class="mock-line"></div>
                                                <div class="mock-line"></div>
                                                <div class="mock-line"></div>
                                            </div>
                                        </div>
                                    </div>
                                    <div id="mock-capture-button" class="glass-card">Capture</div>
                                    <div class="mock-cursor animated">
                                        <div class="mock-cursor-icon"></div>
                                    </div>
                                </div>
                            </div>
                        `;
                        
                        document.body.appendChild(thumbnailElement);

                        const mockCursor = thumbnailElement.querySelector('.mock-cursor');
                        const startX = `${Math.random() * 100}px`;
                        const startY = `${Math.random() * 50 + 20}px`;
                        mockCursor.style.setProperty('--start-x', startX);
                        mockCursor.style.setProperty('--start-y', startY);


                        if (action.sound_effect && window.Tone) {
                            try {
                                const shutterSound = new Tone.NoiseSynth({
                                    noise: { type: 'white' },
                                    envelope: { attack: 0.001, decay: 0.05, sustain: 0, release: 0.1 }
                                }).toDestination();
                                await Tone.start();
                                shutterSound.triggerAttackRelease("0.05");
                            } catch (e) {
                                console.error("Tone.js error:", e);
                            }
                        }

                        flashElement.classList.add('active');
                        const timer1 = setTimeout(() => flashElement.remove(), 300);
                        const timer2 = setTimeout(() => { 
                            thumbnailElement.classList.add('visible'); 
                        }, 100);
                        const timer3 = setTimeout(() => {
                            thumbnailElement.classList.add('shrink');
                            const timer4 = setTimeout(() => thumbnailElement.remove(), 500);
                            window.playwrightTimers.add(timer4);
                        }, 3500);

                        window.playwrightTimers.add(timer1);
                        window.playwrightTimers.add(timer2);
                        window.playwrightTimers.add(timer3);
                    }
                }

                function onCursorArrival() {
                    const timer = setTimeout(() => {
                        triggerActionAnimations();
                        if (text) {
                            const textBox = document.createElement('div');
                            textBox.id = 'playwright-cursor-textbox';
                            cursor.appendChild(textBox);
                            typeText(textBox, text, () => {
                                const cleanupTimer = setTimeout(() => {
                                    textBox.remove();
                                    if (window.playwrightTimers && window.playwrightTimers.has(cleanupTimer)) {
                                        if (['text', 'scroll', 'key', 'info', 'processing'].includes(type)) {
                                            const pointerIcon = document.getElementById('playwright-cursor-pointer-icon');
                                            document.querySelectorAll('.playwright-cursor-icon').forEach(icon => icon.style.display = 'none');
                                            pointerIcon.style.display = 'block';
                                            pointerIcon.classList.add('icon-fade-in');
                                            const fadeTimer = setTimeout(() => pointerIcon.classList.remove('icon-fade-in'), 300);
                                            window.playwrightTimers.add(fadeTimer);
                                        }
                                    }
                                    window.playwrightTimers.delete(cleanupTimer);
                                }, 1000);
                                window.playwrightTimers.add(cleanupTimer);
                            });
                        }
                    }, 50);
                    window.playwrightTimers.add(timer);
                }

                if (type === 'screenshot') {
                    triggerActionAnimations();
                    return;
                }

                if (!coords || (parseFloat(cursor.style.left) === endX && parseFloat(cursor.style.top) === endY)) {
                    onCursorArrival();
                } else {
                    const movementTimer = setTimeout(onCursorArrival, 150);
                    window.playwrightTimers.add(movementTimer);
                    cursor.style.left = `${endX}px`;
                    cursor.style.top = `${endY}px`;
                }
            };
        })();
        """

    async def _run_simulation(self, params: dict):
        """A helper to call the injected run_animation function."""
        if not self.page:
            print("Simulator Error: Page object not set.")
            return
        try:
            await self.page.evaluate("window.run_animation", params)
        except Exception as e:
            print(f"Simulator failed to run: {e}")
            
    async def get_coords(self, element_node: "DOMElementNode"):
        try:
            element_handle = self.page.locator(f"xpath={element_node.xpath}")
            if await element_handle.count() == 0:
                # Use the description from the element_node for a rich error message.
                description = element_node.get_description()
                await self.info(text=f"Could not find element to click: {description}")
                return None
            
            box = await element_handle.bounding_box()
            if not box:
                return None

            # scroll = await self.page.evaluate("() => ({ x: window.scrollX, y: window.scrollY })")

            center_coords = {
                "x": box["x"] + box["width"] / 2,
                "y": box["y"] + box["height"] / 2,
            }
            return center_coords
        
        except Exception as e:
            print(f"Simulator failed to get element handle: {e}")
            
    async def click(self, element_node: 'DOMElementNode', text: str = "Click!"):
        """
        Gets fresh coordinates for an element and simulates a click animation.
        """
        
        if not self.page:
            return

        try:
            coords = await self.get_coords(element_node)
            if not coords:
                return

            params = {"coords": coords, "text": text, "action": {"type": "click"}}
            await self._run_simulation(params)

        except Exception as e:
            print(f"Simulator failed during click preparation: {e}")

    async def info(self, text: str):
        """Simulates the info message on the browser page"""
        await self._run_simulation({"text": text, "action": {"type": "info"}})

    async def type(
        self, element_node: "DOMElementNode", text: Optional[str] = "Typing..."
    ):
        """
        Simulates a text input animation.
        """
        if not self.page:
            return

        try:
            coords = await self.get_coords(element_node)
            if not coords:
                return

            params = {"coords": coords, "text": text, "action": {"type": "text"}}
            await self._run_simulation(params)

        except Exception as e:
            print(f"Simulator failed during type preparation: {e}")

    async def screenshot(self, sound_effect: bool = True):
        """
        Triggers the screenshot animation.
        """
        params = {"action": {"type": "screenshot", "sound_effect": sound_effect}}
        await self._run_simulation(params)

    async def scroll(
        self, element_node: "DOMElementNode", direction: str, text: Optional[str] = None
    ):
        """
        Gets fresh coordinates for a target element and simulates a scroll animation.
        """
        if not self.page:
            return

        try:
            element_handle = await self.page.query_selector(
                f"[data-highlight-id='{element_node.highlight_index}']"
            )
            if not element_handle:
                print(
                    f"Simulator could not find element with index: {element_node.highlight_index}"
                )
                return

            coords = await self._get_page_coordinates(element_handle)
            if not coords:
                return

            # Use provided text or a sensible default.
            animation_text = (
                text
                if text is not None
                else f"Scrolling towards element {element_node.highlight_index}"
            )

            params = {
                "coords": coords,
                "text": animation_text,
                "action": {"type": "scroll", "direction": direction},
            }
            await self._run_simulation(params)

        except Exception as e:
            print(f"Simulator failed during scroll preparation: {e}")

    async def stop_simulation(self):
        """Stops any active animation."""
        if not self.page:
            return
        try:
            await self.page.evaluate("window.stop_animation")
        except Exception as e:
            print(f"Failed to stop animation: {e}")
