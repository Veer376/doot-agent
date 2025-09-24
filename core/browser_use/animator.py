import asyncio
from typing import TYPE_CHECKING, Optional, Dict

if TYPE_CHECKING:
    from playwright.async_api import Page, ElementHandle
    from .dom.types import DOMElementNode, BoundingBox


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
        self.animator_script = r"""
        (() => {
            // Setup styles and cursor
            if (window.playwrightAnimationsSetup) return;
            
            const styles = `
                #playwright-cursor { position: absolute; pointer-events: none; z-index: 2147483647; transition: top 0.15s cubic-bezier(0.65, 0, 0.35, 1), left 0.15s cubic-bezier(0.65, 0, 0.35, 1); }
                .playwright-cursor-icon { width: 27px; height: 27px; background-repeat: no-repeat; background-size: contain; transform: translate(-50%, -50%); filter: drop-shadow(0 1px 2px rgba(0, 0, 0, 0.5)); display: none; }
                #playwright-cursor-pointer-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 24 24'%3E%3Cpath fill='black' stroke='black' stroke-width='2' d='M5.5 3.21V20.8c0 .45.54.67.85.35l4.86-4.86a.5.5 0 0 1 .35-.15h6.87a.5.5 0 0 0 .35-.85L6.35 2.85a.5.5 0 0 0-.85.35Z'/%3E%3C/svg%3E"); }
                #playwright-cursor-text-icon { width: 2px; height: 22px; background-color: black; animation: blink 1s infinite; filter: none; }
                #playwright-cursor-scroll-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2L9 6h6l-3-4zm0 20l3-4H9l3 4zm8-10l-4 3v-6l4 3zM4 12l4-3v6l-4-3z'/%3E%3C/svg%3E"); }
                #playwright-cursor-key-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M20 5H4c-1.1 0-2 .9-2 2v10c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2zm-9 11H5v-2h6v2zm0-3H5V9h6v2zm7 3h-6v-2h6v2zm0-3h-6V9h6v2z'/%3E%3C/svg%3E"); }
                .log-icon-info { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z'/%3E%3C/svg%3E"); }
                .log-icon-debug { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M20,8h-2.81c-.45-1.77-2.1-3-4.19-3s-3.74,1.23-4.19,3H6v6h2.09c.05.33.12.65.21,1H6v2h2.3c.2,1.22,1.14,2,2.7,2s2.5-0.78,2.7-2H16v-2h-2.29c.09-.35.16-.67.21-1H16V8z M12,16c-0.83,0-1.5-0.67-1.5-1.5S11.17,13,12,13s1.5,0.67,1.5,1.5S12.83,16,12,16z M13.5,10h-3V8.5C10.5,7.67,11.17,7,12,7s1.5,0.67,1.5,1.5V10z'/%3E%3C/svg%3E"); }
                .log-icon-warning { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z'/%3E%3C/svg%3E"); }
                .log-icon-error { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='black'%3E%3Cpath d='M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm5 13.59L15.59 17 12 13.41 8.41 17 7 15.59 10.59 12 7 8.41 8.41 7 12 10.59 15.59 7 17 8.41 13.41 12 17 15.59z'/%3E%3C/svg%3E"); }
                #playwright-cursor-processing-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='none' stroke='white' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 1 0 10 10'/%3E%3Cpath fill='black' stroke='black' stroke-width='3' stroke-linecap='round' d='M12 2a10 10 0 0 0-7.07 2.93'/%3E%3C/svg%3E"); animation: rotate 1s linear infinite; }
                #playwright-cursor-dropdown-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='black' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E"); transition: transform 0.3s ease-in-out; }
                .cursor-dropdown-open #playwright-cursor-dropdown-icon { transform: translate(-50%, -50%) rotate(180deg); }
                @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
                @keyframes rotate { from { transform: translate(-50%, -50%) rotate(0deg); } to { transform: translate(-50%, -50%) rotate(360deg); } }
                .cursor-click-down #playwright-cursor-pointer-icon, .cursor-key-press #playwright-cursor-key-icon { animation: press-effect 0.2s cubic-bezier(0.250, 0.460, 0.450, 0.940) forwards; }
                @keyframes press-effect { 0% { transform: translate(-50%, -50%) scale(1); } 50% { transform: translate(-50%, -50%) scale(0.5); } 100% { transform: translate(-50%, -50%) scale(1); } }
                .icon-fade-in { animation: fade-in 0.3s ease-out forwards; }
                @keyframes fade-in { from { opacity: 0; } to { opacity: 1; } }
                
                #playwright-cursor-textbox {
                    position: absolute;
                    background: rgba(255, 255, 255, 0.4);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border-radius: 12px;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.5),
                                inset 0 -1px 0 rgba(255, 255, 255, 0.1);
                    color: #333;
                    padding: 6px 12px;
                    font-family: 'Quicksand', sans-serif;
                    font-size: 14px;
                    font-weight: 500;
                    transition: all 0.3s ease-out;
                    max-width: 375px;
                    word-wrap: break-word;
                    opacity: 0;
                    overflow: hidden;
                }
                #playwright-cursor-textbox::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 1px;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.8), transparent);
                }
                #playwright-cursor-textbox::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 1px;
                    height: 100%;
                    background: linear-gradient(180deg, rgba(255, 255, 255, 0.8), transparent, rgba(255, 255, 255, 0.3));
                }

                .textbox-appear { opacity: 1 !important; transform: translateY(0) !important; }
                .playwright-cursor-label { position: absolute; top: 10px; left: 10px; background: rgba(255, 255, 255, 0.2); border-radius: 12px; box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1); backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px); border: 1px solid rgba(255, 255, 255, 0.3); color: #333; padding: 4px 8px; font-family: 'Quicksand', sans-serif; font-size: 12px; font-weight: 500; }
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
                .mock-url-bar::before { content: "🔒 agnet.com/profiles"; font-size: 5px; }
                .mock-close-buttons { display: flex; gap: 2px; }
                .mock-close-btn { width: 6px; height: 6px; border-radius: 50%; }
                .mock-close-btn.red { background: #ef4444; }
                .mock-close-btn.yellow { background: #eab308; }
                .mock-close-btn.green { background: #22c55e; }
                
                .mock-content { padding: 8px; height: calc(100% - 20px); background: transparent; position: relative; }
                
                .mock-profile-container {
                    position: absolute;
                    top: 4px;
                    left: 6px;
                    display: flex;
                    align-items: center;
                    gap: 6px;
                }
                .mock-profile {
                    width: 18px;
                    height: 18px;
                    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%236b7280' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2'%3E%3C/path%3E%3Ccircle cx='12' cy='7' r='4'%3E%3C/circle%3E%3C/svg%3E");
                    background-size: 70%;
                    background-position: center;
                    background-repeat: no-repeat;
                    border: 1.5px solid #6b7280;
                    border-radius: 50%;
                }
                .mock-profile-name {
                    font-size: 10px;
                    font-weight: 500;
                    font-family: 'Quicksand', sans-serif;
                    color: #4a5568;
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
                
                .mock-lines { display: flex; flex-direction: column; gap: 2px; width: 90%;}
                .mock-line { 
                    height: 4px; 
                    border-radius: 2px;
                    position: relative;
                    overflow: hidden;
                    background-color: #cbd5e1;
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

                .glass-card {
                    width: 80px;
                    height: 30px;
                    background: rgba(255, 255, 255, 0.15);
                    backdrop-filter: blur(7px);
                    -webkit-backdrop-filter: blur(7px);
                    border-radius: 10px;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.5),
                                inset 0 -1px 0 rgba(255, 255, 255, 0.1),
                                inset 0 0 20px 10px rgba(255, 255, 255, 1);
                    position: absolute;
                    bottom: 10px;
                    right: 10px;
                    overflow: hidden;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    color: black;
                    font-weight: 500;
                    font-family: 'Quicksand';
                    font-size: 10px;
                    cursor: pointer;
                    transition: all 0.2s ease-in-out;
                }

                .glass-card::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 1px;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.8), transparent);
                }

                .glass-card::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 1px;
                    height: 100%;
                    background: linear-gradient(180deg, rgba(255, 255, 255, 0.8), transparent, rgba(255, 255, 255, 0.3));
                }
                @keyframes shimmer {
                    0% { transform: translateX(-100%); }
                    100% { transform: translateX(100%); }
                }

                /* New Stunning Design CSS */
                .sky { position: absolute; top: 0; left: 0; width: 100%; height: 70%; background: linear-gradient(to bottom, #e8e8e8 0%, #d0d0d0 30%, #c0c0c0 70%, #b0b0b0 100%); }
                .sun { position: absolute; top: 15%; right: 15%; width: 15px; height: 15px; background: radial-gradient(circle, #fffde7 30%, #fff9c4 70%); border-radius: 50%; box-shadow: 0 0 10px rgba(255, 255, 224, 0.6); animation: glow 3s ease-in-out infinite alternate; }
                @keyframes glow { from { box-shadow: 0 0 10px rgba(255, 255, 224, 0.6); } to { box-shadow: 0 0 15px rgba(255, 255, 224, 0.9); } }
                .mountain { position: absolute; bottom: 30%; }
                .mountain-1 { left: 10%; width: 0; height: 0; border-left: 8px solid transparent; border-right: 8px solid transparent; border-bottom: 13px solid #404040; }
                .mountain-1::after { content: ''; position: absolute; top: 0; left: -4px; width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent; border-bottom: 6.5px solid #ffffff; }
                .mountain-2 { left: 35%; width: 0; height: 0; border-left: 10px solid transparent; border-right: 10px solid transparent; border-bottom: 15px solid #505050; }
                .mountain-2::after { content: ''; position: absolute; top: 0; left: -5px; width: 0; height: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 7.5px solid #ffffff; }
                .mountain-3 { right: 10%; width: 0; height: 0; border-left: 7.5px solid transparent; border-right: 7.5px solid transparent; border-bottom: 10px solid #454545; }
                .mountain-3::after { content: ''; position: absolute; top: 0; left: -3.75px; width: 0; height: 0; border-left: 3.75px solid transparent; border-right: 3.75px solid transparent; border-bottom: 5px solid #ffffff; }
                .cloud { position: absolute; background: rgba(255, 255, 255, 0.9); border-radius: 100px; }
                .cloud-1 { top: 10%; left: 20%; width: 20px; height: 7px; animation: float 6s ease-in-out infinite; }
                .cloud-1::before { content: ''; position: absolute; top: -4px; left: 2px; width: 12px; height: 12px; background: rgba(255, 255, 255, 0.9); border-radius: 50%; }
                .cloud-1::after { content: ''; position: absolute; top: -2px; right: 2px; width: 10px; height: 10px; background: rgba(255, 255, 255, 0.9); border-radius: 50%; }
                .cloud-2 { top: 20%; right: 30%; width: 15px; height: 6px; animation: float 8s ease-in-out infinite reverse; }
                .cloud-2::before { content: ''; position: absolute; top: -3px; left: 2px; width: 10px; height: 10px; background: rgba(255, 255, 255, 0.9); border-radius: 50%; }
                .cloud-2::after { content: ''; position: absolute; top: -2px; right: 2px; width: 8px; height: 8px; background: rgba(255, 255, 255, 0.9); border-radius: 50%; }
                @keyframes float { 0%, 100% { transform: translateY(0px); } 50% { transform: translateY(-5.2px); } }
                .bird { position: absolute; top: 25%; left: 50%; width: 5px; height: 1px; background: #000; border-radius: 50%; animation: fly 4s linear infinite; }
                .bird::before { content: ''; position: absolute; left: -2px; top: 0; width: 3px; height: 1px; background: #000; border-radius: 50%; transform: rotate(-20deg); }
                .bird::after { content: ''; position: absolute; right: -2px; top: 0; width: 3px; height: 1px; background: #000; border-radius: 50%; transform: rotate(20deg); }
                .bird-2 { animation-delay: -2s; left: 55%; top: 20%; }
                .bird-3 { animation-delay: -1s; left: 45%; top: 30%; }
                @keyframes fly { 0% { transform: translateX(-15px) translateY(0); } 25% { transform: translateX(0) translateY(-3px); } 50% { transform: translateX(15px) translateY(0); } 75% { transform: translateX(25px) translateY(3px); } 100% { transform: translateX(40px) translateY(0); } }

                /* New Log Container Styles */
                #playwright-log-container {
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 2147483646;
                    display: flex;
                    flex-direction: column-reverse;
                    align-items: flex-end;
                    gap: 10px;
                    pointer-events: none;
                }
                .playwright-log-entry {
                    display: flex;
                    align-items: flex-start;
                    gap: 8px;
                    background: rgba(255, 255, 255, 0.4);
                    backdrop-filter: blur(12px);
                    -webkit-backdrop-filter: blur(12px);
                    border-radius: 12px;
                    border: 1px solid rgba(255, 255, 255, 0.3);
                    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1),
                                inset 0 1px 0 rgba(255, 255, 255, 0.5),
                                inset 0 -1px 0 rgba(255, 255, 255, 0.1);
                    color: #333;
                    padding: 8px 12px;
                    font-family: 'Quicksand', sans-serif;
                    font-size: 14px;
                    font-weight: 500;
                    max-width: 375px;
                    animation: log-fade-in 0.3s ease-out forwards;
                    position: relative;
                    overflow: hidden;
                }
                .playwright-log-entry .log-text-content {
                    word-wrap: break-word;
                    flex-grow: 1;
                }
                .playwright-log-entry pre {
                    background-color: rgba(0,0,0,0.05);
                    border-radius: 6px;
                    padding: 8px;
                    margin: 6px 0;
                    font-family: 'Fira Code', monospace;
                    font-size: 12px;
                    white-space: pre-wrap;
                    word-break: break-all;
                }

                .playwright-log-entry::before {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    height: 1px;
                    background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.8), transparent);
                }
                .playwright-log-entry::after {
                    content: '';
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 1px;
                    height: 100%;
                    background: linear-gradient(180deg, rgba(255, 255, 255, 0.8), transparent, rgba(255, 255, 255, 0.3));
                }

                .playwright-log-entry.fade-out {
                    animation: log-fade-out 0.5s ease-in forwards;
                }
                .log-icon {
                    width: 20px;
                    height: 20px;
                    background-size: contain;
                    background-repeat: no-repeat;
                    flex-shrink: 0;
                    margin-top: 2px;
                }
                @keyframes log-fade-in {
                    from { opacity: 0; transform: translateX(20px); }
                    to { opacity: 1; transform: translateX(0); }
                }
                @keyframes log-fade-out {
                    from { opacity: 1; transform: translateX(0); }
                    to { opacity: 0; transform: translateX(20px); }
                }

            `;
            const styleSheet = document.createElement("style");
            styleSheet.id = 'pointer-animation-styles';
            styleSheet.innerText = styles;
            document.head.appendChild(styleSheet);

            const cursor = document.createElement('div');
            cursor.id = 'playwright-cursor';
            ['pointer', 'text', 'scroll', 'key', 'processing', 'dropdown'].forEach(iconType => {
                const iconEl = document.createElement('div');
                iconEl.id = `playwright-cursor-${iconType}-icon`;
                iconEl.className = 'playwright-cursor-icon';
                cursor.appendChild(iconEl);
            });
            cursor.style.left = '-100px';
            cursor.style.top = '-100px';
            document.body.appendChild(cursor);

            // Create log container if it doesn't exist
            if (!document.getElementById('playwright-log-container')) {
                const newLogContainer = document.createElement('div');
                newLogContainer.id = 'playwright-log-container';
                document.body.appendChild(newLogContainer);
            }

            window.playwrightAnimationsSetup = true;
            window.playwrightTimers = new Set();
            window.screenshotTimers = new Set();
            let textBoxElement = null;

            window.hide_animations = () => {
                document.querySelectorAll('#playwright-cursor, #screenshot-flash, #screenshot-thumbnail, .splash-line, .scroll-indicator, #playwright-log-container').forEach(el => {
                    if (el) el.style.display = 'none';
                });
            };

            window.show_animations = () => {
                document.querySelectorAll('#playwright-cursor, #screenshot-flash, #screenshot-thumbnail, .splash-line, .scroll-indicator, #playwright-log-container').forEach(el => {
                    if (el) el.style.display = ''; // Revert to default display
                });
            };

            function updateDisplay(text, iconType) {
                if (!textBoxElement) {
                    textBoxElement = document.createElement('div');
                    textBoxElement.id = 'playwright-cursor-textbox';
                    cursor.appendChild(textBoxElement);
                }
                
                // --- FIX: Use textContent for safety ---
                textBoxElement.textContent = text;
                textBoxElement.classList.add('textbox-appear');

                document.querySelectorAll('.playwright-cursor-icon').forEach(icon => icon.style.display = 'none');
                const activeIcon = document.getElementById(`playwright-cursor-${iconType}-icon`) || document.getElementById('playwright-cursor-pointer-icon');
                if (activeIcon) activeIcon.style.display = 'block';

                // --- START OF NEW POSITIONING LOGIC ---
                // Reset styles
                textBoxElement.style.top = '';
                textBoxElement.style.left = '';
                textBoxElement.style.bottom = '';
                textBoxElement.style.right = '';
                textBoxElement.style.transform = '';

                // Temporarily make it visible but off-screen to measure
                textBoxElement.style.visibility = 'hidden';
                document.body.appendChild(textBoxElement); // Append to body for accurate measurement
                const boxRect = textBoxElement.getBoundingClientRect();
                cursor.appendChild(textBoxElement); // Move it back
                
                const endX = parseFloat(cursor.style.left);
                const endY = parseFloat(cursor.style.top);
                const viewportWidth = window.innerWidth;
                const viewportHeight = window.innerHeight;
                const margin = 10;

                const canGoRight = endX + margin + boxRect.width < viewportWidth;
                const canGoLeft = endX - margin - boxRect.width > 0;
                const canGoDown = endY + margin + boxRect.height < viewportHeight;
                const canGoUp = endY - margin - boxRect.height > 0;

                // Priority 1: Bottom-Right
                if (canGoDown && canGoRight) {
                    textBoxElement.style.top = `${margin}px`;
                    textBoxElement.style.left = `${margin}px`;
                    textBoxElement.style.transform = 'translateY(-10px)';
                } 
                // Priority 2: Bottom-Left
                else if (canGoDown && canGoLeft) {
                    textBoxElement.style.top = `${margin}px`;
                    textBoxElement.style.left = `-${boxRect.width + margin}px`;
                    textBoxElement.style.transform = 'translateY(-10px)';
                } 
                // Priority 3: Top-Right
                else if (canGoUp && canGoRight) {
                    textBoxElement.style.top = `-${boxRect.height + margin}px`;
                    textBoxElement.style.left = `${margin}px`;
                    textBoxElement.style.transform = 'translateY(10px)';
                } 
                // Priority 4: Top-Left (Default)
                else {
                    textBoxElement.style.top = `-${boxRect.height + margin}px`;
                    textBoxElement.style.left = `-${boxRect.width + margin}px`;
                    textBoxElement.style.transform = 'translateY(10px)';
                }
                
                textBoxElement.style.visibility = 'visible';
                 // --- END OF NEW POSITIONING LOGIC ---
            }
            
            // --- Screenshot Animation Function ---
            window.run_screenshot_animation = async (params = {}) => {
                window.show_animations();
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
                
                const thumbnailHTML = `
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
                             <div class="mock-profile-container">
                                <div class="mock-profile"></div>
                                <div class="mock-profile-name">Veer</div>
                            </div>
                            <div class="mock-grid">
                                <div style="display: flex; flex-direction: column; gap: 4px; justify-content: space-between;">
                                    <div class="mock-card" style="flex-grow: 1; display: flex; align-items: center; justify-content: center;">
                                        <div class="mock-lines">
                                            <div class="mock-line" style="width: 80%"></div>
                                            <div class="mock-line" style="width: 60%"></div>
                                        </div>
                                    </div>
                                    <div class="mock-card" style="flex-grow: 1; display: flex; align-items: center; justify-content: center;">
                                        <div class="mock-lines" style="gap: 3.2px;">
                                            <div class="mock-line" style="width: 75%"></div>
                                            <div class="mock-line" style="width: 90%"></div>
                                            <div class="mock-line" style="width: 60%"></div>
                                            <div class="mock-line" style="width: 80%"></div>
                                        </div>
                                    </div>
                                    <div class="mock-card" style="flex-grow: 0.7; display: flex; align-items: center; justify-content: center;">
                                        <div class="mock-lines">
                                            <div class="mock-line" style="width: 65%"></div>
                                            <div class="mock-line" style="width: 50%"></div>
                                        </div>
                                    </div>
                                </div>
                                <div class="mock-card" style="display: flex; flex-direction: column; justify-content: flex-start; padding: 0;">
                                    <div style="height: 50%; position: relative; overflow: hidden; border-radius: 4px 4px 0 0;">
                                        <div class="sky"></div>
                                        <div class="sun"></div>
                                        <div class="mountain mountain-1"></div>
                                        <div class="mountain mountain-2"></div>
                                        <div class="mountain mountain-3"></div>
                                        <div class="cloud cloud-1"></div>
                                        <div class="cloud cloud-2"></div>
                                        <div class="bird bird-1"></div>
                                        <div class="bird bird-2"></div>
                                        <div class="bird bird-3"></div>
                                    </div>
                                    <div style="height: 50%; display: flex; align-items: center; justify-content: center;">
                                        <div class="mock-lines">
                                            <div class="mock-line"></div>
                                            <div class="mock-line"></div>
                                            <div class="mock-line"></div>
                                        </div>
                                    </div>
                                </div>
                            </div>
                            <div id="mock-capture-button" class="glass-card">snapshot</div>
                        </div>
                    </div>
                `;
                
                const doc = new DOMParser().parseFromString(thumbnailHTML, 'text/html');
                const mockBrowser = doc.body.firstChild;
                if (mockBrowser) {
                    thumbnailElement.appendChild(mockBrowser);
                }
                
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

            // --- New Logging Function ---
            window.createLogEntry = (params) => {
                const {text, level = 'info'} = params
                let logContainer = document.getElementById('playwright-log-container');
                if (!logContainer) {
                    logContainer = document.createElement('div');
                    logContainer.id = 'playwright-log-container';
                    document.body.appendChild(logContainer);
                }

                const logEntry = document.createElement('div');
                logEntry.className = 'playwright-log-entry';
                
                const icon = document.createElement('div');
                icon.className = `log-icon log-icon-${level}`;
                
                const textContent = document.createElement('div');
                textContent.className = 'log-text-content';

                // Regex to find JSON-like structures
                const jsonRegex = /({.*?}|\[.*?\])/g;
                const parts = text.split(jsonRegex);

                parts.forEach(part => {
                    if (part && (part.trim().startsWith('{') || part.trim().startsWith('['))) {
                        try {
                            // Attempt to fix common Python dict string issues before parsing
                            const correctedPart = part.replace(/'/g, '"');
                            const jsonObj = JSON.parse(correctedPart);
                            const pre = document.createElement('pre');
                            pre.textContent = JSON.stringify(jsonObj, null, 2);
                            textContent.appendChild(pre);
                        } catch (e) {
                            // If parsing still fails, treat it as plain text
                            textContent.appendChild(document.createTextNode(part));
                        }
                    } else if (part) {
                        textContent.appendChild(document.createTextNode(part));
                    }
                });
                
                logEntry.appendChild(icon);
                logEntry.appendChild(textContent);
                logContainer.prepend(logEntry);

                setTimeout(() => {
                    logEntry.classList.add('fade-out');
                    logEntry.addEventListener('animationend', () => {
                        logEntry.remove();
                    });
                }, 15000);
            };

            // --- Main Cursor Animation Function ---
            window.run_animation = async (params = {}) => {
                window.show_animations();
                const { coords, action = {}, text } = params;
                const { type, direction } = action;

                // Clear only main cursor timers
                window.playwrightTimers.forEach(timer => clearTimeout(timer));
                window.playwrightTimers.clear();
                document.querySelectorAll('.splash-line, .scroll-indicator').forEach(el => el.remove());

                const cursor = document.getElementById('playwright-cursor');
                if (!cursor) { console.error("Cursor element not found."); return; }
                cursor.style.display = 'block';

                let iconType = type;
                
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
                        
                        let svgString;
                        if (direction === 'down') {
                            svgString = `<svg width="10" height="30" viewBox="0 0 10 30"><line x1="5" y1="0" x2="5" y2="20" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/><path d="M0 20 L5 30 L10 20 Z" fill="rgba(0,0,0,0.4)"/></svg>`;
                        } else if (direction === 'up') {
                            svgString = `<svg width="10" height="30" viewBox="0 0 10 30"><path d="M0 10 L5 0 L10 10 Z" fill="rgba(0,0,0,0.4)"/><line x1="5" y1="10" x2="5" y2="30" stroke="rgba(0,0,0,0.4)" stroke-width="4" stroke-linecap="round"/></svg>`;
                        }
                        
                        if (svgString) {
                            const doc = new DOMParser().parseFromString(svgString, 'text/html');
                            const svgElement = doc.body.firstChild;
                            if(svgElement) {
                                indicator.appendChild(svgElement);
                            }
                        }

                        document.body.appendChild(indicator);
                        const timer = setTimeout(() => indicator.remove(), 400);
                        window.playwrightTimers.add(timer);
                    } else if (type === 'dropdown') {
                        cursor.classList.add('cursor-dropdown-open');
                        const timer = setTimeout(() => cursor.classList.remove('cursor-dropdown-open'), 500);
                        window.playwrightTimers.add(timer);
                    }
                }

                function onCursorArrival() {
                    const timer = setTimeout(() => {
                        triggerActionAnimations();
                        updateDisplay(text, iconType);

                        const cleanupTimer = setTimeout(() => {
                            updateDisplay('Cursor', 'pointer');
                        }, 3000);
                        window.playwrightTimers.add(cleanupTimer);

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

    async def click(
        self,
        element_node: "DOMElementNode" = None,
        coords: dict | None = None,
        text: str = "Click!",
    ):
        """
        Gets fresh coordinates for an element and animates a click animator.
        """

        if not self.page:
            return

        try:
            if element_node:
                bbox: BoundingBox = element_node.bbox
                if bbox:
                    x = bbox.x + bbox.width / 2
                    y = bbox.y + bbox.height / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                print(f"Click animation aborted as no coords found")
                return

            params = {
                "coords": {"x": x, "y": y},
                "text": text,
                "action": {"type": "click"},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during click preparation: {e}")

    async def log(self, text: str, level: str = "info"):
        """
        Animates the log message on the browser page
        """
        if not self.page:
            print("Cannot log: no page instance available")
            return
            
        try:
            params = {"text": text, "level": level}
            await self.page.evaluate("window.createLogEntry", params)
        except Exception as e:
            print(f"Animator failed during log: {e}")
        
    async def type(
        self,
        element_node: "DOMElementNode" = None,
        text: str = "Typing...",
        coords: dict | None = None,
    ):
        """
        Animates a text input animator.
        """
        if not self.page:
            return

        try:
            x = None
            y = None

            if element_node:
                if bbox := element_node.bbox:
                    x = bbox.x + bbox.width / 2
                    y = bbox.y + bbox.height / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                return

            params = {
                "coords": {"x": x, "y": y},
                "text": text,
                "action": {"type": "text"},
            }

            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during type preparation: {e}")

    async def scroll(
        self,
        direction: str,
        text: str = "Scrolling...",
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
                bbox: BoundingBox = element_node.bbox
                if bbox:
                    x = bbox.x + bbox.width / 2
                    y = bbox.y + bbox.height / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                return

            params = {
                "coords": {"x": x, "y": y},
                "text": text,
                "action": {"type": "scroll", "direction": direction},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during scroll preparation: {e}")

    async def dropdown(
        self,
        element_node: "DOMElementNode" = None,
        text: str = "Dropdown!",
        coords: dict | None = None,
    ):
        """
        Animates a dropdown opening action.
        """
        if not self.page:
            return

        try:
            x = None
            y = None

            if element_node and hasattr(element_node, "bbox"):
                bbox = element_node.bbox
                if bbox:
                    x = bbox.x + bbox.width / 2
                    y = bbox.y + bbox.height / 2
            elif coords:
                x = coords.get("x")
                y = coords.get("y")

            if not (x and y):
                print(f"Dropdown animation aborted as no coords found")
                return

            params = {
                "coords": {"x": x, "y": y},
                "text": text,
                "action": {"type": "dropdown"},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during dropdown preparation: {e}")

    async def key(self, text: str = None):
        """
        Animates a key press action.
        """
        if not self.page:
            return

        try:
            # Default coordinates to center of screen if not provided
            params = {
                "text": text,
                "action": {"type": "key"},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during key press animation: {e}")

    async def processing(self, text: str):
        """
        Shows a processing/loading animation to indicate that work is being done.

        Parameters:
        - text: Message to display during the processing animation
        """
        if not self.page:
            return

        try:
            params = {
                "text": text,
                "action": {"type": "processing"},
            }
            await self.run_animation(params)

        except Exception as e:
            print(f"Animator failed during processing animation: {e}")

    async def screenshot(self):
        """Runs the screenshot animation."""
        if not self.page:
            return
        try:
            await self.page.evaluate(
                "window.run_screenshot_animation", {"sound_effect": True}
            )
        except Exception as e:
            print(f"Failed to stop screenshot animation: {e}")

    async def hide_animations(self):
        """Hides any active animations."""
        if not self.page:
            return
        try:
            await self.page.evaluate("window.hide_animations")
        except Exception as e:
            print(f"Failed to stop animator: {e}")

    async def show_animations(self):
        """Shows any active animations."""
        if not self.page:
            return
        try:
            await self.page.evaluate("window.show_animations")
        except Exception as e:
            print(f"Failed to show animations: {e}")

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
