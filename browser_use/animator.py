import asyncio
from typing import TYPE_CHECKING, Optional, Dict

if TYPE_CHECKING:
    from playwright.async_api import Page, ElementHandle
    from .dom.types import DOMElementNode


class Animator:
    """
    Manages the injection and execution of browser animators for a specific page.
    This class encapsulates the Python methods to trigger animators and the
    underlying JavaScript code that creates the visual effects.
    """

    def __init__(self, page: Optional["Page"]):
        """
        Initializes the Animator with a Playwright Page object.
        The page object is optional during instantiation but required for execution.
        """
        self.page = page

        # script
        self.animator_script = """
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
                
                .mock-profile {
                    position: absolute;
                    top: 4px;
                    left: 6px;
                    width: 18px;
                    height: 18px;
                    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'%3E%3C/path%3E%3Ccircle cx='12' cy='7' r='4'%3E%3C/circle%3E%3C/svg%3E");
                    background-size: 70%;
                    background-position: center;
                    background-repeat: no-repeat;
                    border: 1.5px solid #6b7280;
                    border-radius: 50%;
                }
                
                .mock-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 24px; height: calc(100% - 32px); }
                
                .mock-card {
                    background: rgba(241, 245, 249, 0.4);
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
                    height: 16px; 
                    background: transparent; 
                    border-radius: 4px; 
                    position: relative; 
                    overflow: hidden; 
                    margin-bottom: 8px;
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
                .mock-line { 
                    height: 4px; 
                    background: #cbd5e1; 
                    border-radius: 2px;
                    position: relative;
                    overflow: hidden;
                    background-color: #e2e8f0;
                }
                .mock-line::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.5), transparent);
                    animation: shimmer 1.5s infinite;
                }
                .mock-line:nth-child(1) { width: 90%; }
                .mock-line:nth-child(2) { width: 70%; animation-delay: 0.2s; }
                .mock-line:nth-child(3) { width: 85%; animation-delay: 0.4s; }

                @keyframes shimmer {
                    0% { transform: translateX(-100%); }
                    100% { transform: translateX(100%); }
                }
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
            window.screenshotTimers = new Set();

            window.stop_all_animations = () => {
                window.playwrightTimers.forEach(timer => clearTimeout(timer));
                window.playwrightTimers.clear();
                window.screenshotTimers.forEach(timer => clearTimeout(timer));
                window.screenshotTimers.clear();

                document.querySelectorAll('#playwright-cursor, #screenshot-flash, #screenshot-thumbnail, .splash-line, .scroll-indicator').forEach(el => el.remove());
                
                // Re-create cursor for next run
                const newCursor = document.createElement('div');
                newCursor.id = 'playwright-cursor';
                ['pointer', 'text', 'scroll', 'key', 'info', 'processing'].forEach(iconType => {
                    const iconEl = document.createElement('div');
                    iconEl.id = `playwright-cursor-${iconType}-icon`;
                    iconEl.className = 'playwright-cursor-icon';
                    newCursor.appendChild(iconEl);
                });
                newCursor.style.left = '-100px';
                newCursor.style.top = '-100px';
                document.body.appendChild(newCursor);
            };
            
            // --- Screenshot Animation Function ---
            window.run_screenshot_animation = async (params = {}) => {
                const { sound_effect = false } = params;

                // Clear only screenshot timers
                window.screenshotTimers.forEach(timer => clearTimeout(timer));
                window.screenshotTimers.clear();
                document.querySelectorAll('#screenshot-flash, #screenshot-thumbnail').forEach(el => el.remove());

                const flashElement = document.createElement('div');
                flashElement.id = 'screenshot-flash';
                document.body.appendChild(flashElement);

                const thumbnailElement = document.createElement('div');
                thumbnailElement.id = 'screenshot-thumbnail';
                
                // Create elements programmatically instead of using innerHTML to avoid TrustedHTML issues
                const mockBrowser = document.createElement('div');
                mockBrowser.className = 'mock-browser';
                
                const mockBrowserHeader = document.createElement('div');
                mockBrowserHeader.className = 'mock-browser-header';
                
                const mockCloseButtons = document.createElement('div');
                mockCloseButtons.className = 'mock-close-buttons';
                
                const mockRedBtn = document.createElement('div');
                mockRedBtn.className = 'mock-close-btn red';
                
                const mockYellowBtn = document.createElement('div');
                mockYellowBtn.className = 'mock-close-btn yellow';
                
                const mockGreenBtn = document.createElement('div');
                mockGreenBtn.className = 'mock-close-btn green';
                
                const mockUrlBar = document.createElement('div');
                mockUrlBar.className = 'mock-url-bar';
                
                // Assemble header
                mockCloseButtons.appendChild(mockRedBtn);
                mockCloseButtons.appendChild(mockYellowBtn);
                mockCloseButtons.appendChild(mockGreenBtn);
                mockBrowserHeader.appendChild(mockCloseButtons);
                mockBrowserHeader.appendChild(mockUrlBar);
                
                // Create content
                const mockContent = document.createElement('div');
                mockContent.className = 'mock-content';
                
                const mockProfile = document.createElement('div');
                mockProfile.className = 'mock-profile';
                
                const mockGrid = document.createElement('div');
                mockGrid.className = 'mock-grid';
                
                // Create first card
                const mockCard1 = document.createElement('div');
                mockCard1.className = 'mock-card';
                
                const mockImage1 = document.createElement('div');
                mockImage1.className = 'mock-image';
                
                const mockCloud1 = document.createElement('div');
                mockCloud1.className = 'mock-cloud';
                
                const mockLines1 = document.createElement('div');
                mockLines1.className = 'mock-lines';
                
                for (let i = 0; i < 3; i++) {
                    const mockLine = document.createElement('div');
                    mockLine.className = 'mock-line';
                    mockLines1.appendChild(mockLine);
                }
                
                // Assemble first card
                mockImage1.appendChild(mockCloud1);
                mockCard1.appendChild(mockImage1);
                mockCard1.appendChild(mockLines1);
                
                // Create second card (duplicate of first)
                const mockCard2 = document.createElement('div');
                mockCard2.className = 'mock-card';
                
                const mockImage2 = document.createElement('div');
                mockImage2.className = 'mock-image';
                
                const mockCloud2 = document.createElement('div');
                mockCloud2.className = 'mock-cloud';
                
                const mockLines2 = document.createElement('div');
                mockLines2.className = 'mock-lines';
                
                for (let i = 0; i < 3; i++) {
                    const mockLine = document.createElement('div');
                    mockLine.className = 'mock-line';
                    mockLines2.appendChild(mockLine);
                }
                
                // Assemble second card
                mockImage2.appendChild(mockCloud2);
                mockCard2.appendChild(mockImage2);
                mockCard2.appendChild(mockLines2);
                
                // Add cards to grid
                mockGrid.appendChild(mockCard1);
                mockGrid.appendChild(mockCard2);
                
                // Create capture button
                const mockCaptureButton = document.createElement('div');
                mockCaptureButton.id = 'mock-capture-button';
                mockCaptureButton.className = 'glass-card';
                mockCaptureButton.textContent = 'Captured';
                
                // Assemble content
                mockContent.appendChild(mockProfile);
                mockContent.appendChild(mockGrid);
                mockContent.appendChild(mockCaptureButton);
                
                // Assemble browser
                mockBrowser.appendChild(mockBrowserHeader);
                mockBrowser.appendChild(mockContent);
                
                // Add to thumbnail
                thumbnailElement.appendChild(mockBrowser);
                
                document.body.appendChild(thumbnailElement);

                if (sound_effect && window.Tone) {
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
                    window.screenshotTimers.add(timer4);
                }, 3500);

                window.screenshotTimers.add(timer1);
                window.screenshotTimers.add(timer2);
                window.screenshotTimers.add(timer3);
            };

            // --- Main Cursor Animation Function ---
            window.run_animation = async (params = {}) => {
                const { coords, action = {}, text } = params;
                const { type, direction } = action;

                // Clear only main cursor timers
                window.playwrightTimers.forEach(timer => clearTimeout(timer));
                window.playwrightTimers.clear();
                document.querySelectorAll('#playwright-cursor-textbox, .splash-line, .scroll-indicator').forEach(el => el.remove());

                const cursor = document.getElementById('playwright-cursor');
                if (!cursor) { console.error("Cursor element not found."); return; }

                document.querySelectorAll('.playwright-cursor-icon').forEach(icon => icon.style.display = 'none');
                const activeIcon = document.getElementById(`playwright-cursor-${type}-icon`) || document.getElementById('playwright-cursor-pointer-icon');
                if (activeIcon) activeIcon.style.display = 'block';

                let endX, endY;

                if (coords) {
                    endX = coords.x;
                    endY = coords.y;
                } else {
                    const currentX = parseFloat(cursor.style.left);
                    // Check if the cursor has a valid, non-initial position
                    if (currentX > 0) {
                        endX = currentX;
                        endY = parseFloat(cursor.style.top);
                    } else {
                        // Default to center if no last position is known
                        endX = window.innerWidth / 2;
                        endY = window.innerHeight / 2;
                    }
                }


                function typeText(textBox, fullText, callback) {
                    // Set text content instead of innerHTML to avoid TrustedHTML issues
                    textBox.textContent = fullText;
                    textBox.classList.add('textbox-appear');
                    if (callback) {
                        const timer = setTimeout(callback, 300);
                        window.playwrightTimers.add(timer);
                    }
                }

                async function triggerActionAnimations() {
                    if (!type) return; // Do nothing if no action type is specified

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
                        // Create SVG programmatically instead of using innerHTML
                        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
                        svg.setAttribute("width", "10");
                        svg.setAttribute("height", "30");
                        svg.setAttribute("viewBox", "0 0 10 30");
                        
                        if (direction === 'down') {
                            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                            line.setAttribute("x1", "5");
                            line.setAttribute("y1", "0");
                            line.setAttribute("x2", "5");
                            line.setAttribute("y2", "20");
                            line.setAttribute("stroke", "rgba(0,0,0,0.4)");
                            line.setAttribute("stroke-width", "4");
                            line.setAttribute("stroke-linecap", "round");
                            
                            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                            path.setAttribute("d", "M0 20 L5 30 L10 20 Z");
                            path.setAttribute("fill", "rgba(0,0,0,0.4)");
                            
                            svg.appendChild(line);
                            svg.appendChild(path);
                        } else if (direction === 'up') {
                            const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
                            path.setAttribute("d", "M0 10 L5 0 L10 10 Z");
                            path.setAttribute("fill", "rgba(0,0,0,0.4)");
                            
                            const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
                            line.setAttribute("x1", "5");
                            line.setAttribute("y1", "10");
                            line.setAttribute("x2", "5");
                            line.setAttribute("y2", "30");
                            line.setAttribute("stroke", "rgba(0,0,0,0.4)");
                            line.setAttribute("stroke-width", "4");
                            line.setAttribute("stroke-linecap", "round");
                            
                            svg.appendChild(path);
                            svg.appendChild(line);
                        }
                        
                        indicator.appendChild(svg);
                        document.body.appendChild(indicator);
                        const timer = setTimeout(() => indicator.remove(), 400);
                        window.playwrightTimers.add(timer);
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
                                    if (window.playwrightTimers.has(cleanupTimer)) {
                                        if (['text', 'scroll', 'key', 'info', 'processing'].includes(type)) {
                                            const pointerIcon = document.getElementById('playwright-cursor-pointer-icon');
                                            document.querySelectorAll('.playwright-cursor-icon').forEach(icon => icon.style.display = 'none');
                                            if (pointerIcon) {
                                                pointerIcon.style.display = 'block';
                                                pointerIcon.classList.add('icon-fade-in');
                                                const fadeTimer = setTimeout(() => pointerIcon.classList.remove('icon-fade-in'), 300);
                                                window.playwrightTimers.add(fadeTimer);
                                            }
                                        }
                                    }
                                }, 1000);
                                window.playwrightTimers.add(cleanupTimer);
                            });
                        }
                    }, 50);
                    window.playwrightTimers.add(timer);
                }

                if (parseFloat(cursor.style.left) === endX && parseFloat(cursor.style.top) === endY) {
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

    async def run_animation(self, params: dict | None = None):
        """A helper to call the injected run_animation function."""
        if not self.page:
            print("Animator Error: Page object not set.")
            return
        try:
            if params:
                await self.page.evaluate("window.run_animation", params)
            else:
                await self.page.evaluate("window.run_animation({})")

        except Exception as e:
            print(f"Animator failed to run: {e}")

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
            print(f"Animator failed to get element handle: {e}")

    async def click(self, element_node: "DOMElementNode"=None, coords: dict|None = None, text: str = "Click!"):
        """
        Gets fresh coordinates for an element and animates a click animator.
        """

        if not self.page:
            return

        try:
            if element_node:
                bbox = element_node.bbox
                if bbox:
                    x = bbox["x"] + bbox["width"] / 2
                    y = bbox["y"] + bbox["height"] / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                return

            params = {
                "coords": coords,
                "text": text,
                "action": {"type": "click"},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during click preparation: {e}")

    async def info(self, text: str):
        """Animates the info message on the browser page"""
        await self.run_animation({"text": text, "action": {"type": "info"}})

    async def type(
        self, element_node: "DOMElementNode", text: Optional[str] = "Typing..."
    ):
        """
        Animates a text input animator.
        """
        if not self.page:
            return

        try:
            coords = await self.get_coords(element_node)
            if not coords:
                return

            params = {"coords": coords, "text": text, "action": {"type": "text"}}
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during type preparation: {e}")

    async def screenshot(self, sound_effect: bool = True):
        """
        Triggers the screenshot animator.
        """
        params = {"action": {"type": "screenshot", "sound_effect": sound_effect}}
        await self.run_animation(params)

    async def scroll(
        self,
        direction: str,
        text: str = None,
        element_node: "DOMElementNode" = None,
        coords: dict = None,
    ):
        """
        Gets fresh coordinates for a target element and animates a scroll animator.
        """
        if not self.page:
            return

        try:
            x = None
            y = None

            if element_node:
                bbox = element_node.bbox
                if bbox:
                    x = bbox["x"] + bbox["width"] / 2
                    y = bbox["y"] + bbox["height"] / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                return

            # Use provided text or a sensible default.
            animator_text = (
                text
                if text is not None
                else f"Scrolling towards element {element_node.highlight_index}"
            )

            params = {
                "coords": coords,
                "text": animator_text,
                "action": {"type": "scroll", "direction": direction},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during scroll preparation: {e}")

    async def stop_all_animations(self):
        """Stops any active animator."""
        if not self.page:
            return
        try:
            await self.page.evaluate("window.stop_all_animations")
        except Exception as e:
            print(f"Failed to stop animator: {e}")

    async def run_screenshot_animation(self):
        """Runs the screenshot animation."""
        if not self.page:
            return
        try:
            await self.page.evaluate(
                "window.run_screenshot_animation", {"sound_effect": True}
            )
        except Exception as e:
            print(f"Failed to stop screenshot animation: {e}")
