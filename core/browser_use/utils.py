import asyncio
import logging
import os
import platform
import signal
import time
from collections.abc import Callable, Coroutine
from functools import wraps
from sys import stderr
from typing import Any, ParamSpec, TypeVar

logger = logging.getLogger(__name__)

# Global flag to prevent duplicate exit messages
_exiting = False

# Define generic type variables for return type and parameters
R = TypeVar('R')
P = ParamSpec('P')


def time_execution_sync(additional_text: str = '') -> Callable[[Callable[P, R]], Callable[P, R]]:
	def decorator(func: Callable[P, R]) -> Callable[P, R]:
		@wraps(func)
		def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
			start_time = time.time()
			result = func(*args, **kwargs)
			execution_time = time.time() - start_time
			logger.debug(f'{additional_text} Execution time: {execution_time:.2f} seconds')
			return result

		return wrapper

	return decorator


def time_execution_async(
	additional_text: str = '',
) -> Callable[[Callable[P, Coroutine[Any, Any, R]]], Callable[P, Coroutine[Any, Any, R]]]:
	def decorator(func: Callable[P, Coroutine[Any, Any, R]]) -> Callable[P, Coroutine[Any, Any, R]]:
		@wraps(func)
		async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
			start_time = time.time()
			result = await func(*args, **kwargs)
			execution_time = time.time() - start_time
			logger.debug(f'{additional_text} Execution time: {execution_time:.2f} seconds')
			return result

		return wrapper

	return decorator


import sys


def get_screen_resolution():
	if sys.platform == 'darwin':  # macOS
		try:
			from AppKit import NSScreen

			screen = NSScreen.mainScreen().frame()
			return {'width': int(screen.size.width), 'height': int(screen.size.height)}
		except ImportError:
			print('AppKit is not available. Make sure you are running this on macOS with pyobjc installed.')
		except Exception as e:
			print(f'Error retrieving macOS screen resolution: {e}')
		return {'width': 2560, 'height': 1664}

	else:  # Windows & Linux
		try:
			from screeninfo import get_monitors

			monitors = get_monitors()
			if not monitors:
				raise Exception('No monitors detected.')
			monitor = monitors[0]
			return {'width': monitor.width, 'height': monitor.height}
		except ImportError:
			print("screeninfo package not found. Install it using 'pip install screeninfo'.")
		except Exception as e:
			print(f'Error retrieving screen resolution: {e}')

		return {'width': 1920, 'height': 1080}


def get_window_adjustments():
	"""Returns recommended x, y offsets for window positioning"""
	if sys.platform == 'darwin':  # macOS
		return -4, 24  # macOS has a small title bar, no border
	elif sys.platform == 'win32':  # Windows
		return -8, 0  # Windows has a border on the left
	else:  # Linux
		return 0, 0
