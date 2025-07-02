"""
Logger module for the browser-use-tool project.
Provides colored logging for different components and log levels.
"""
import sys
from enum import Enum
from datetime import datetime

# ANSI color codes
class Colors:
    # Component colors
    BROWSER = "\033[94m"  # Blue
    AGENT = "\033[95m"    # Purple
    TOOLS = "\033[96m"    # Cyan
    
    # Level colors
    ERROR = "\033[91m"    # Red
    WARNING = "\033[93m"  # Yellow
    INFO = "\033[92m"     # Green
    DEBUG = "\033[90m"    # Dark gray
    
    # Other formatting
    RESET = "\033[0m"     # Reset to default
    BOLD = "\033[1m"      # Bold text
    UNDERLINE = "\033[4m" # Underlined text

class LogLevel(Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"
    DEBUG = "DEBUG"

class Component(Enum):
    BROWSER = "BROWSER"
    AGENT = "AGENT"
    TOOLS = "TOOLS"

class Logger:
    """
    Logger utility for the browser-use-tool project.
    Handles different components and log levels with color formatting.
    """
    
    @staticmethod
    def _get_component_color(component):
        """Get the color code for a component"""
        if component == Component.BROWSER:
            return Colors.BROWSER
        elif component == Component.AGENT:
            return Colors.AGENT
        elif component == Component.TOOLS:
            return Colors.TOOLS
        return ""
    
    @staticmethod
    def _get_level_color(level):
        """Get the color code for a log level"""
        if level == LogLevel.ERROR:
            return Colors.ERROR
        elif level == LogLevel.WARNING:
            return Colors.WARNING
        elif level == LogLevel.INFO:
            return Colors.INFO
        elif level == LogLevel.DEBUG:
            return Colors.DEBUG
        return ""
    
    @classmethod
    def log(cls, level, component, message):
        """
        Log a message with the specified level and component.
        
        Args:
            level (LogLevel): The log level (ERROR, WARNING, INFO, DEBUG)
            component (Component): The component generating the log (BROWSER, AGENT, TOOLS)
            message (str): The log message
            
        Returns:
            None
        """
        timestamp = datetime.now().strftime("%M.%f")[:-3]
        component_color = cls._get_component_color(component)
        level_color = cls._get_level_color(level)
        
        formatted_message = (
            f"{timestamp} "
            f"{component_color}[{component.value}]{Colors.RESET}"
            f"{level_color}[{level.value}]{Colors.RESET}"
            f"[{message}]"
        )
        
        print(formatted_message, file=sys.stderr)
    
    @classmethod
    def error(cls, component, message):
        """Log an error message"""
        cls.log(LogLevel.ERROR, component, message)
    
    @classmethod
    def warning(cls, component, message):
        """Log a warning message"""
        cls.log(LogLevel.WARNING, component, message)
    
    @classmethod
    def info(cls, component, message):
        """Log an info message"""
        cls.log(LogLevel.INFO, component, message)
    
    @classmethod
    def debug(cls, component, message):
        """Log a debug message"""
        cls.log(LogLevel.DEBUG, component, message)

# Convenience functions
def browser_error(message):
    """Log a browser error message"""
    Logger.error(Component.BROWSER, message)

def browser_warning(message):
    """Log a browser warning message"""
    Logger.warning(Component.BROWSER, message)

def browser_info(message):
    """Log a browser info message"""
    Logger.info(Component.BROWSER, message)

def browser_debug(message):
    """Log a browser debug message"""
    Logger.debug(Component.BROWSER, message)

def agent_error(message):
    """Log an agent error message"""
    Logger.error(Component.AGENT, message)

def agent_warning(message):
    """Log an agent warning message"""
    Logger.warning(Component.AGENT, message)

def agent_info(message):
    """Log an agent info message"""
    Logger.info(Component.AGENT, message)

def agent_debug(message):
    """Log an agent debug message"""
    Logger.debug(Component.AGENT, message)

def tools_error(message):
    """Log a tools error message"""
    Logger.error(Component.TOOLS, message)

def tools_warning(message):
    """Log a tools warning message"""
    Logger.warning(Component.TOOLS, message)

def tools_info(message):
    """Log a tools info message"""
    Logger.info(Component.TOOLS, message)

def tools_debug(message):
    """Log a tools debug message"""
    Logger.debug(Component.TOOLS, message)
