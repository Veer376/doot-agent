import asyncio
import os
from browser_use.browser import BrowserConfig, Browser

simulator_script = """
        (() => {
            // Setup styles and cursor
            if (window.playwrightAnimationsSetup) return;
            const styles = `
                #playwright-cursor { position: absolute; pointer-events: none; z-index: 2147483647; transition: top 0.6s cubic-bezier(0.65, 0, 0.35, 1), left 0.6s cubic-bezier(0.65, 0, 0.35, 1); }
                .playwright-cursor-icon { width: 27px; height: 27px; background-repeat: no-repeat; background-size: contain; transform: translate(-50%, -50%); filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5)); display: none; }
                #playwright-cursor-pointer-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24'%3E%3Cpath fill='black' stroke='white' stroke-width='1.5' d='M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87a.5.5 0 0 0 .35-.85L6.35 2.85a.5.5 0 0 0-.85.35Z'/%3E%3C/svg%3E"); }
                #playwright-cursor-text-icon { width: 2px; height: 22px; background-color: black; animation: blink 1s infinite; filter: none; }
                #playwright-cursor-scroll-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2L9 6h6l-3-4zm0 20l3-4H9l3 4zm8-10l-4 3v-6l4 3zM4 12l4-3v6l-4-3z'/%3E%3C/svg%3E"); }
                #playwright-cursor-key-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M20 5H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm-9 11H5v-2h6v2zm0-3H5V9h6v2zm7 3h-6v-2h6v2zm0-3h-6V9h6v2z'/%3E%3C/svg%3E"); }
                #playwright-cursor-info-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z'/%3E%3C/svg%3E"); }
                #playwright-cursor-processing-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='white' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 1 0 10 10'/%3E%3Cpath fill='black' stroke='black' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 0 0-7.07 2.93'/%3E%3C/svg%3E"); animation: rotate 1s linear infinite; }
                @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
                @keyframes rotate { from { transform: translate(-50%, -50%) rotate(0deg); } to { transform: translate(-50%, -50%) rotate(360deg); } }
                .cursor-click-down #playwright-cursor-pointer-icon, .cursor-key-press #playwright-cursor-key-icon { animation: press-effect 0.4s cubic-bezier(0.250, 0.460, 0.450, 0.940) forwards; }
                @keyframes press-effect { 0% { transform: translate(-50%, -50%) scale(1); } 50% { transform: translate(-50%, -50%) scale(0.5); } 100% { transform: translate(-50%, -50%) scale(1); } }
                .icon-fade-in { animation: fade-in 0.3s ease-out forwards; }
                @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
                #playwright-cursor-textbox { position: absolute; top: 10px; left: 10px; background: rgba(255, 255, 255, 0); border-radius: 16px; box-shadow: 0 4px 30px rgba(0, 0, 0, 0.1); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px); border: 1px solid rgba(255, 255, 255, 0.39); color: black; padding: 6px 12px; font-family: 'Quicksand', sans-serif; font-size: 14px; font-weight: 500; transition: width 0.1s linear, height 0.1s linear; max-width: 375px; word-wrap: break-word; }
                .splash-line { position: absolute; width: 3.5px; pointer-events: none; background-color: #2d3748; border-radius: 9999px; transform-origin: top center; z-index: 2147483646; animation: line-clip-and-retract 0.96s cubic-bezier(0.5, 1, 0.9, 1) forwards; }
                @keyframes line-clip-and-retract { 0% { clip-path: inset(0 0 100% 0); } 30% { clip-path: inset(0 0 0 0); } 100% { clip-path: inset(100% 0 0 0); } }
                .scroll-indicator { position: absolute; z-index: 2147483646; width: 10px; height: 30px; transform: translateX(-50%); }
                @keyframes scroll-down { 0% { transform: translate(-50%, -30px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translate(-50%, 30px); opacity: 0; } }
                @keyframes scroll-up { 0% { transform: translate(-50%, 30px); opacity: 0; } 50% { opacity: 1; } 100% { transform: translate(-50%, -30px); opacity: 0; } }
                #screenshot-flash { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background-color: white; z-index: 2147483647; opacity: 0; pointer-events: none; transition: opacity 0.3s ease-out; }
                #screenshot-flash.active { opacity: 0.8; }
                #screenshot-thumbnail { position: fixed; bottom: 20px; left: 20px; width: 200px; height: 120px; border: 2px solid white; border-radius: 8px; box-shadow: 0 5px 15px rgba(0,0,0,0.3); z-index: 2147483647; opacity: 0; transform: translateY(20px); transition: opacity 0.4s ease-out, transform 0.4s ease-out; pointer-events: none; background-size: cover; background-position: center; }
                #screenshot-thumbnail.visible { opacity: 1; transform: translateY(0); }
                #screenshot-thumbnail.shrink { transform: scale(0); opacity: 0; transition: opacity 0.5s ease-in, transform 0.5s ease-in; }
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
                    window.playwrightTimers.forEach(timer => clearTimeout(timer));
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
                    const chars = fullText.split('');
                    let currentCharIndex = 0;
                    textBox.innerHTML = '';
                    function typeChar() {
                        if (currentCharIndex < chars.length) {
                            textBox.innerHTML += chars[currentCharIndex];
                            currentCharIndex++;
                            const delay = Math.random() * 20 + 10;
                            const timer = setTimeout(typeChar, delay);
                            window.playwrightTimers.add(timer);
                        } else if (callback) callback();
                    }
                    typeChar();
                }

                async function triggerActionAnimations() {
                    if (type === 'click') {
                        cursor.classList.add('cursor-click-down');
                        const timer1 = setTimeout(() => cursor.classList.remove('cursor-click-down'), 400);
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
                                const cleanupTimer = setTimeout(() => line.remove(), 960);
                                window.playwrightTimers.add(cleanupTimer);
                            }
                        }, 50);
                        window.playwrightTimers.add(timer2);
                    } else if (type === 'key') {
                        cursor.classList.add('cursor-key-press');
                        const timer = setTimeout(() => cursor.classList.remove('cursor-key-press'), 400);
                        window.playwrightTimers.add(timer);
                    } else if (type === 'scroll' && direction) {
                        const indicator = document.createElement('div');
                        indicator.className = 'scroll-indicator';
                        indicator.style.left = `${endX}px`;
                        indicator.style.top = `${endY}px`;
                        indicator.style.animation = `scroll-${direction} 0.7s ease-out forwards`;
                        if (direction === 'down') indicator.innerHTML = `<svg width="10" height="30" viewBox="0 0 10 30"><line x1="5" y1="0" x2="5" y2="20" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/><path d="M0 20 L5 30 L10 20 Z" fill="rgba(0,0,0,0.4)"/></svg>`;
                        else if (direction === 'up') indicator.innerHTML = `<svg width="10" height="30" viewBox="0 0 10 30"><path d="M0 10 L5 0 L10 10 Z" fill="rgba(0,0,0,0.4)"/><line x1="5" y1="10" x2="5" y2="30" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/></svg>`;
                        document.body.appendChild(indicator);
                        const timer = setTimeout(() => indicator.remove(), 700);
                        window.playwrightTimers.add(timer);
                    } else if (type === 'screenshot') {
                        document.querySelectorAll('#screenshot-flash, #screenshot-thumbnail').forEach(el => el.remove());

                        const flashElement = document.createElement('div');
                        flashElement.id = 'screenshot-flash';
                        document.body.appendChild(flashElement);

                        const thumbnailElement = document.createElement('div');
                        thumbnailElement.id = 'screenshot-thumbnail';
                        document.body.appendChild(thumbnailElement);

                        const buttonContainer = document.getElementById('button-container');
                        if (buttonContainer) buttonContainer.style.opacity = '0';

                        if (typeof html2canvas !== 'undefined') {
                            const canvas = await html2canvas(document.body, {
                                scale: window.devicePixelRatio,
                                logging: false,
                                useCORS: true,
                                ignoreElements: (element) => ['screenshot-flash', 'screenshot-thumbnail', 'playwright-cursor'].includes(element.id)
                            });

                            if (buttonContainer) buttonContainer.style.opacity = '1';

                            const imageUrl = canvas.toDataURL('image/png');
                            thumbnailElement.style.backgroundImage = `url(${imageUrl})`;
                        }

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
                        const timer2 = setTimeout(() => { thumbnailElement.classList.add('visible'); }, 100);
                        const timer3 = setTimeout(() => {
                            thumbnailElement.classList.add('shrink');
                            const timer4 = setTimeout(() => thumbnailElement.remove(), 500);
                            window.playwrightTimers.add(timer4);
                        }, 2500);

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
                                }, 2000);
                                window.playwrightTimers.add(cleanupTimer);
                            });
                        }
                    }, 100);
                    window.playwrightTimers.add(timer);
                }

                if (type === 'screenshot') {
                    await triggerActionAnimations();
                    return;
                }

                if (!coords || (parseFloat(cursor.style.left) === endX && parseFloat(cursor.style.top) === endY)) {
                    onCursorArrival();
                } else {
                    const movementTimer = setTimeout(onCursorArrival, 600);
                    window.playwrightTimers.add(movementTimer);
                    cursor.style.left = `${endX}px`;
                    cursor.style.top = `${endY}px`;
                }
            };

            // Stop animation function
            window.stop_animation = () => {
                if (window.playwrightTimers) {
                    window.playwrightTimers.forEach(timer => clearTimeout(timer));
                    window.playwrightTimers.clear();
                }

                document.querySelectorAll('#playwright-cursor-textbox, .scroll-indicator, .splash-line, #screenshot-flash, #screenshot-thumbnail').forEach(el => el.remove());

                const cursor = document.getElementById('playwright-cursor');
                if (cursor) {
                    cursor.classList.remove('cursor-click-down', 'cursor-key-press');
                    document.querySelectorAll('.playwright-cursor-icon').forEach(icon => {
                        icon.classList.remove('icon-fade-in');
                    });
                    cursor.style.left = '-100px';
                    cursor.style.top = '-100px';
                }
            };

            console.log('Pointer animation system initialized. Use window.run_animation(params) and window.stop_animation()');
        })();
        """

async def test_pointers():
    """Test both pointer functions with our test HTML page."""
    # Initialize the browser
    chrome_path = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    # wss_url = "ws://localhost:9323/2bbd6505d20815f6797641df75327bc1"
    config = BrowserConfig(browser_binary_path=chrome_path)
    browser = Browser(config=config)
    browser_context = await browser.new_context()
    
    try:
        # Get the absolute path to the test HTML file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        html_path = os.path.join(current_dir, "test_pointer.html")
        file_url = f"file://{html_path}"
        
        
        
        # Navigate to the test page
        await browser_context.navigate_to(file_url)
        
        # Wait for the page to be fully loaded
        await asyncio.sleep(2)
        
        page = await browser_context.get_agent_current_page()
        # await page.evaluate(simulator_script)
        params = {"coords": {"x": 100, "y": 100}, "type": "click", "text": "Click"}

        await page.evaluate("window.run_animation", params)
        await asyncio.sleep(10)
        
    except Exception as e:
        print(f"Error during test: {e}")
    finally:
        # Close the browser
        await browser.close()
        print("Browser closed")

if __name__ == "__main__":
    asyncio.run(test_pointers())
    
