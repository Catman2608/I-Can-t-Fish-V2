# AI_SYSTEM_MAP: CAST_SYSTEM=_execute_cast* | SHAKE_SYSTEM=_execute_shake* | FISH_SYSTEM=_execute_fish* | CONFIG_SYSTEM=_save_config,_load_config | GUI_VIEWS=*View,*Frame | PERFECT_CAST=find_green*,find_white* | HOTKEYS=HotkeyManager

# === STANDARD LIBRARY IMPORTS ===
import base64
import io
import json
import math
import os
import random
import sys
import threading
import time
import webbrowser
from ctypes import windll
from functools import partial

# === THIRD-PARTY GUI IMPORTS ===
import customtkinter as ctk
from customtkinter import CTkLabel
import tkinter as tk
from tkinter import messagebox

# === THIRD-PARTY UTILITY IMPORTS ===
import keyboard
import requests
import pyautogui

# === COMPUTER VISION AND IMAGING IMPORTS ===
import cv2
import mss
from PIL import Image, ImageTk, ImageGrab, ImageDraw

# === WINDOWS-SPECIFIC IMPORTS ===
import win32api
import win32con
import win32gui

# === OPTIONAL HIGH-PERFORMANCE IMPORTS ===
try:
    import dxcam
    import numpy as np
    DXCAM_AVAILABLE = True
except ImportError:
    DXCAM_AVAILABLE = False
    print("⚠️ dxcam and/or numpy not available. Perfect Cast Release will use fallback method.")
    # Create dummy numpy for type hints and basic functionality
    class np:
        @staticmethod
        def array(*args, **kwargs):
            return []
        
        @staticmethod
        def any(mask):
            return False
            
        @staticmethod
        def max(arr, axis=None):
            return 0
            
        @staticmethod
        def abs(arr):
            return arr

# === WINDOWS MOUSE EVENT CONSTANTS ===
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

# === HELPER FUNCTIONS ===
def _release_left_click():
    """Helper function to release left mouse button - reduces code duplication."""
    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

def _is_roblox_window_active():
    """Check if Roblox window is currently active - for safety during fishing actions only."""
    try:
        import win32gui
        hwnd = win32gui.GetForegroundWindow()
        window_title = win32gui.GetWindowText(hwnd).lower()
        return 'roblox' in window_title or 'fisch' in window_title
    except Exception as e:
        # Don't spam warnings - just return True to allow operation
        return True  # Assume valid if check fails (allows emergency exits)

# === HOTKEY CONSTANTS ===
# Available hotkeys: F1-F12, A-Z (lowercase for consistency)
AVAILABLE_HOTKEYS = [f"F{i}" for i in range(1, 13)] + [chr(i) for i in range(ord('a'), ord('z') + 1)]

# === PERFORMANCE CONSTANTS ===
# Sleep/delay intervals for optimization - tuned for responsiveness vs CPU usage balance
INTERRUPTIBLE_SLEEP_CHECK_INTERVAL = 0.05  # 50ms - check bot state during delays
# REMOVED: PERFECT_CAST_FRAME_DELAY - now uses configurable perfect_cast_scan_fps setting
SCROLL_ZOOM_STEP_DELAY = 0.05  # 50ms - delay between scroll steps for human-like behavior
BOT_CYCLE_CHECK_INTERVAL = 50  # 50ms - faster response than previous 100ms
CAMERA_CLEANUP_DELAY = 0.025  # 25ms - optimized from 50ms for faster cleanup
MOUSE_SMOOTH_DELAY = 0.0005  # 0.5ms - optimized from 1ms for smoother movement
LOOK_ACTION_DELAY = 0.01  # 10ms - delay for mouse movement registration

# === DETECTION TRACKING CONSTANTS ===
# These affect accuracy vs performance tradeoff
TRACKING_LOST_THRESHOLD = 3  # Number of frames before switching from tracking to full scan
WHITE_POSITION_HISTORY_SIZE = 5  # Number of white positions to keep for speed calculation

# === UI CONSTANTS ===
COLOR_LIGHTENING_FACTOR = 1.2  # Factor for making colors lighter on hover (20% increase)

# === HTTP CONSTANTS ===
HTTP_SUCCESS_CODES = [200, 204]  # Successful HTTP response codes

# === PERFECT CAST COLOR CONSTANTS ===
# Pre-compiled constants for maximum speed (BGR format for dxcam)
if DXCAM_AVAILABLE:
    GREEN_BGR = np.array([76, 160, 100], dtype=np.float32)   # #64a04c in BGR format
    WHITE_BGR = np.array([223, 234, 234], dtype=np.float32)  # #eaeadf in BGR format
else:
    # Fallback values for when numpy is not available
    GREEN_BGR = [76, 160, 100]
    WHITE_BGR = [223, 234, 234]

# === APPLICATION INITIALIZATION ===
# Set default appearance mode and color theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# === DPI AWARENESS SETUP ===
# Make the application DPI-aware so ImageGrab captures the full screen on scaled displays
try:
    # Try Windows 10+ method (Per Monitor V2)
    windll.shcore.SetProcessDpiAwareness(2)
except OSError as e:
    # Windows version doesn't support this method
    try:
        # Fallback to older method
        windll.user32.SetProcessDPIAware()
    except OSError as fallback_e:
        print(f"⚠️ Warning: Could not set DPI awareness - Primary: {e}, Fallback: {fallback_e}")
except Exception as e:
    print(f"⚠️ Warning: Unexpected DPI awareness error: {e}")

# === PERFECT CAST RELEASE DETECTION FUNCTIONS ===

def find_vertical_lines_in_frame(frame, expected_count=4, min_sep=10):
    """
    Detect vertical lines spanning top to bottom of frame using edge detection.
    Returns list of X coordinates for detected vertical lines.
    Optimized for detecting target lines and bar boundaries in fishing minigame.
    
    INTEGRATION: This replaces color-based detection with edge-based vertical line detection.
    - Calculates pixel difference between adjacent columns (vertical edge strength)
    - Uses adaptive percentile thresholding (99% down to 85%)
    - Finds local maxima (peaks) representing vertical edges
    - Filters candidates by minimum separation (avoids duplicates)
    - Returns strongest N lines matching expected_count
    - Fallback: if too few candidates, uses lower threshold
    
    BENEFITS over color detection:
    - More reliable for thin lines that span full height
    - Resolution-independent (works with 2560x1440 and 1920x1080)
    - Detects exact X coordinates of line edges
    - Self-correcting: adapts threshold to find exact count
    
    Args:
        frame: BGR numpy array from cv2/dxcam
        expected_count: Expected number of vertical lines (0=disable, 3-4 typical)
        min_sep: Minimum pixel separation between detected lines
    
    Returns:
        List of X coordinates (integers) of detected vertical lines, or empty list
    """
    if frame is None or frame.size == 0:
        return []
    
    height, width = frame.shape[:2]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    # Calculate pixel difference between adjacent columns (vertical edge strength)
    diffs = np.zeros(width, dtype=np.float32)
    for x in range(1, width):
        diffs[x] = np.abs(gray[:, x].astype(np.int16) - gray[:, x-1].astype(np.int16)).sum()
    
    if expected_count == 0:
        return []
    
    best_lines = []
    best_score = -999
    
    # Adaptive threshold search - find peaks that represent vertical edges
    for percentile in range(99, 85, -1):
        threshold = np.percentile(diffs, percentile)
        candidates = []
        
        # Find local maxima (peaks) above threshold
        for x in range(1, width-1):
            if diffs[x] > threshold and diffs[x] >= diffs[x-1] and diffs[x] >= diffs[x+1]:
                candidates.append((x, diffs[x]))
        
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Filter candidates by minimum separation
        lines = []
        for x, d in candidates:
            if not lines or all(abs(x - l[0]) > min_sep for l in lines):
                lines.append((x, d))
                if len(lines) >= expected_count + 3:
                    break
        
        # Perfect match found
        if len(lines) == expected_count:
            return sorted([x for x, d in lines])
        
        # Track best approximation
        score = -abs(len(lines) - expected_count) * 100 + len(lines)
        if score > best_score and len(lines) >= expected_count - 1:
            best_score = score
            best_lines = lines
    
    # Fallback: use lower threshold if no good candidates
    if not best_lines:
        candidates = [(x, diffs[x]) for x in range(1, width-1) if diffs[x] > np.percentile(diffs, 90)]
        candidates.sort(key=lambda x: x[1], reverse=True)
        lines = []
        for x, d in candidates:
            if not lines or all(abs(x - l[0]) > min_sep for l in lines):
                lines.append((x, d))
                if len(lines) >= expected_count + 2:
                    break
        best_lines = lines
    
    # If we have too many lines, keep only the strongest
    if len(best_lines) > expected_count:
        best_lines.sort(key=lambda x: x[1], reverse=True)
        best_lines = best_lines[:expected_count]
    
    return sorted([x for x, d in best_lines])

def find_green_full_scan(frame, target_rgb, tolerance):
    """
    FULL AREA SCAN: Initial detection across entire area
    Returns: (local_midpoint_x, local_green_y, leftmost_x, rightmost_x) - LOCAL coordinates only
    """
    if frame is None:
        return None

    # With region capture, we work in pure local coordinates (0,0) based
    # Pre-convert target to int16 once (avoid repeated conversion)
    target_rgb_int16 = target_rgb.astype(np.int16)

    # Full scan - no skip-scan optimization
    diff = np.abs(frame.astype(np.int16) - target_rgb_int16)
    max_diff = np.max(diff, axis=2)
    mask = max_diff <= tolerance

    if not np.any(mask):
        return None

    # Get all matching coordinates
    y_coords, x_coords = np.where(mask)
    
    # Find leftmost and rightmost x coordinates
    leftmost_local_x = np.min(x_coords)
    rightmost_local_x = np.max(x_coords)
    
    # Find y coordinate of the topmost green pixel (closest to top of screen)
    green_local_y = np.min(y_coords)

    # Calculate midpoint
    midpoint_local_x = (leftmost_local_x + rightmost_local_x) // 2

    # Return LOCAL coordinates: (midpoint_x, y, left_x, right_x)
    return (midpoint_local_x, green_local_y, leftmost_local_x, rightmost_local_x)

def find_green_tracking_box(frame, last_midpoint_x, last_green_y, target_rgb, tolerance, box_size=20, box_width_multiplier=2.0):
    """
    TRACKING BOX SCAN: Ultra-fast scan in small box around last known position
    box_width_multiplier: Makes box wider horizontally (e.g., 2.0 = 2x wider than tall)
    Returns: (local_midpoint_x, local_green_y, leftmost_x, rightmost_x) - LOCAL coordinates only
    """
    if frame is None or last_midpoint_x is None or last_green_y is None:
        return None

    # With region capture, we work in pure local coordinates (0,0) based
    x1, y1, x2, y2 = 0, 0, frame.shape[1], frame.shape[0]

    # Define tracking box boundaries with wider horizontal size
    box_width = int(box_size * box_width_multiplier)
    box_x1 = max(0, last_midpoint_x - box_width)
    box_x2 = min(x2 - x1, last_midpoint_x + box_width)
    box_y1 = max(0, last_green_y - box_size)
    box_y2 = min(y2 - y1, last_green_y + box_size)

    # Extract tracking box area
    if box_x1 >= box_x2 or box_y1 >= box_y2:
        return None

    tracking_box = frame[y1 + box_y1:y1 + box_y2, x1 + box_x1:x1 + box_x2]

    if tracking_box.size == 0:
        return None

    # Pre-convert target to int16 once (avoid repeated conversion)
    target_rgb_int16 = target_rgb.astype(np.int16)

    # Fast scan within tracking box
    diff = np.abs(tracking_box.astype(np.int16) - target_rgb_int16)
    max_diff = np.max(diff, axis=2)
    mask = max_diff <= tolerance

    if not np.any(mask):
        return None  # Lost tracking - need to return to full scan

    # Find green pixels in tracking box
    box_y_coords, box_x_coords = np.where(mask)
    leftmost_box_x = np.min(box_x_coords)
    rightmost_box_x = np.max(box_x_coords)
    
    # Find y coordinate of topmost green pixel
    green_box_y = np.min(box_y_coords)

    # Calculate midpoint
    midpoint_box_x = (leftmost_box_x + rightmost_box_x) // 2

    # Return LOCAL coordinates within the cropped frame: (midpoint_x, y, left_x, right_x)
    final_local_x = box_x1 + midpoint_box_x
    final_local_y = box_y1 + green_box_y
    final_leftmost_x = box_x1 + leftmost_box_x
    final_rightmost_x = box_x1 + rightmost_box_x

    return (final_local_x, final_local_y, final_leftmost_x, final_rightmost_x)

def find_white_below_green(frame, local_green_y, local_left_x, local_right_x, white_tolerance):
    """
    DOWNWARD SCAN ONLY: Search for white pixels BELOW the green line across its full width
    Scans from left_x to right_x horizontally, and from green_y to bottom vertically
    Returns: (local_white_x, local_white_y) or None (closest white pixel to green line)
    """
    if frame is None:
        return None

    # Only scan BELOW green line (green_y to bottom of area)
    scan_start_y = max(0, local_green_y)
    scan_end_y = frame.shape[0]

    if scan_start_y >= scan_end_y:
        return None  # No area below green to scan

    # Bounds check for x coordinates
    scan_left_x = max(0, local_left_x)
    scan_right_x = min(frame.shape[1], local_right_x + 1)
    
    if scan_left_x >= scan_right_x:
        return None

    # Extract rectangular region BELOW green line across full green width
    scan_region = frame[scan_start_y:scan_end_y, scan_left_x:scan_right_x, :]

    if scan_region.size == 0:
        return None

    # Pre-convert WHITE_BGR to int16 once (avoid repeated conversion)
    white_bgr_int16 = WHITE_BGR.astype(np.int16)

    # Work with int16 to avoid float conversion overhead
    diff = np.abs(scan_region.astype(np.int16) - white_bgr_int16)
    max_diff = np.max(diff, axis=2)

    # Find all white matches below green line
    white_mask = max_diff <= white_tolerance

    if np.any(white_mask):
        # Get all matching coordinates
        match_y_coords, match_x_coords = np.where(white_mask)
        
        # Find the closest white pixel to green line (minimum y in scan region)
        closest_idx = np.argmin(match_y_coords)
        relative_y = match_y_coords[closest_idx]
        relative_x = match_x_coords[closest_idx]
        
        # Convert back to frame coordinates
        actual_y = scan_start_y + relative_y
        actual_x = scan_left_x + relative_x
        
        return (actual_x, actual_y)

    return None

def calculate_speed_and_predict(white_positions, timestamps):
    """
    Calculate white pixel movement speed with improved stability
    Uses linear regression on recent positions for smoother velocity estimation
    Returns: speed_pixels_per_second or None
    """
    if len(white_positions) < 2:
        return None

    # Use all available positions (up to 5) for better stability
    # More data points = more accurate velocity estimate
    n = len(white_positions)
    
    # Extract Y positions and time deltas
    y_values = [pos[1] for pos in white_positions]
    time_values = [t - timestamps[0] for t in timestamps]  # Relative to first timestamp
    
    # Simple linear regression: velocity = (sum of (t * y) - n * mean_t * mean_y) / (sum of t^2 - n * mean_t^2)
    mean_t = sum(time_values) / n
    mean_y = sum(y_values) / n
    
    numerator = sum(t * y for t, y in zip(time_values, y_values)) - n * mean_t * mean_y
    denominator = sum(t * t for t in time_values) - n * mean_t * mean_t
    
    if abs(denominator) < 0.0001:  # Avoid division by zero
        return None
    
    # Velocity in pixels per second (positive = moving down, negative = moving up)
    velocity_y = numerator / denominator
    
    return velocity_y


# === RESOURCE MANAGEMENT CLASSES ===

class CameraManager:
    """
    Context manager for DXCam camera resources to ensure proper cleanup.
    Provides automatic resource management with retry logic and error handling.
    """
    def __init__(self, output_idx=0, output_color="BGR", max_retries=3):
        self.output_idx = output_idx
        self.output_color = output_color
        self.max_retries = max_retries
        self.camera = None
        
    def __enter__(self):
        """Initialize camera with retry logic"""
        for attempt in range(self.max_retries):
            try:
                # Clean up any previous camera instance
                if self.camera is not None:
                    try:
                        self.camera.release()
                        time.sleep(CAMERA_CLEANUP_DELAY)  # Optimized cleanup delay
                    except Exception as e:
                        print(f"    ⚠️ Warning: Failed to release previous camera: {e}")
                    finally:
                        self.camera = None
                
                # Create new camera instance
                if DXCAM_AVAILABLE:
                    import dxcam
                    self.camera = dxcam.create(output_idx=self.output_idx, output_color=self.output_color)
                    
                if self.camera:
                    print(f"    ✅ DXCam camera created successfully (attempt {attempt + 1})")
                    return self.camera
                else:
                    print(f"    ❌ DXCam creation failed (attempt {attempt + 1}/{self.max_retries})")
                    time.sleep(0.1)  # Brief delay before retry
                    
            except Exception as e:
                print(f"    ❌ DXCam error (attempt {attempt + 1}/{self.max_retries}): {e}")
                time.sleep(0.1)
        
        # All retries failed
        raise RuntimeError(f"Failed to create DXCam camera after {self.max_retries} attempts")
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up camera resources"""
        if self.camera is not None:
            try:
                self.camera.release()
                print("    ✅ Camera released successfully")
            except Exception as e:
                print(f"    ⚠️ Warning: Error during camera cleanup: {e}")
            finally:
                self.camera = None


class MSSManager:
    """
    Context manager for MSS (screenshot) resources to ensure proper cleanup.
    """
    def __init__(self, monitor_region):
        self.monitor_region = monitor_region
        self.mss_instance = None
        
    def __enter__(self):
        """Initialize MSS instance"""
        try:
            self.mss_instance = mss.mss()
            print("    ✅ MSS instance created successfully")
            return self.mss_instance
        except Exception as e:
            print(f"    ❌ Failed to create MSS instance: {e}")
            raise
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up MSS resources"""
        if self.mss_instance is not None:
            try:
                self.mss_instance.close()
                print("    ✅ MSS instance closed successfully")
            except Exception as e:
                print(f"    ⚠️ Warning: Error during MSS cleanup: {e}")
            finally:
                self.mss_instance = None


# === GUI CLASSES ===

class DiscordView(ctk.CTkFrame):  # AI_TARGET: DISCORD_GUI
    """
    A view (CTkFrame) to contain the Discord settings. Uses a standard tk.Canvas 
    to create custom, scrollable content with Discord theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = master  # Reference to StarryNightApp to access settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#5865F2", # Match the Discord blue background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#7289DA"   # Lighter Discord blue border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="💬 Discord Settings", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n") 
        
        # Enable/Disable Discord Feature Section
        self.enable_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.enable_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.enable_card.grid_columnconfigure(0, weight=1)
        
        # Enable/Disable checkbox - load from settings
        self.discord_enabled = tk.BooleanVar(value=self.app.settings.get("discord_enabled", False))
        enable_checkbox = ctk.CTkCheckBox(
            self.enable_card,
            text="💬 Enable Discord Integration",
            variable=self.discord_enabled,
            command=self._on_discord_enable_change,
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0",
            fg_color="#5865F2",
            hover_color="#7289DA",
            checkmark_color="white"
        )
        enable_checkbox.grid(row=0, column=0, pady=20, padx=30, sticky="w")
        
        # Message Style Selection Section with modern card design
        self.message_style_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.message_style_card.grid(row=2, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.message_style_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the message style section
        subtitle_label = ctk.CTkLabel(
            self.message_style_card, 
            text="⚙️ Discord Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Webhook URL input - load from settings
        webhook_url_label = ctk.CTkLabel(
            self.message_style_card, 
            text="🔗 Webhook URL:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        webhook_url_label.grid(row=1, column=0, padx=(30, 15), pady=12, sticky="ew")

        self.webhook_url_var = self._ensure_gui_var("webhook_url", tk.StringVar, "")
        self.webhook_url_var.trace_add("write", self._on_webhook_url_change)
        webhook_url_entry = ctk.CTkEntry(
            self.message_style_card,
            textvariable=self.webhook_url_var,
            placeholder_text="Enter Discord webhook URL here...",
            font=ctk.CTkFont(size=14),
            fg_color="#383838",
            border_color="#5865F2",
            text_color="#FFFFFF",
            placeholder_text_color="#AAAAAA"
        )
        webhook_url_entry.grid(row=1, column=1, padx=(15, 30), pady=12, sticky="ew")

        # Message Style dropdown - load from settings
        message_style_label = ctk.CTkLabel(
            self.message_style_card, 
            text="📝 Message Style:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        message_style_label.grid(row=2, column=0, padx=(30, 15), pady=12, sticky="ew")

        self.message_style_var = self._ensure_gui_var("discord_message_style", tk.StringVar, "Screenshot")
        self.message_style_var.trace_add("write", lambda *args: self._on_message_style_save())
        message_style_dropdown = ctk.CTkOptionMenu(
            self.message_style_card, 
            values=["Screenshot", "Text"],
            variable=self.message_style_var,
            command=self._on_message_style_change,
            fg_color="#5865F2",      # Discord theme
            button_color="#4752C4",   # Darker Discord blue for button
            button_hover_color="#7289DA",  # Lighter Discord blue on hover
            dropdown_fg_color="#383838",  # Match container
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        message_style_dropdown.grid(row=2, column=1, padx=(15, 30), pady=12, sticky="ew")
        
        # Dynamic options container
        self.options_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.options_card.grid(row=3, column=0, sticky="ew", pady=(0, 25), padx=30)
        self.options_card.grid_columnconfigure(0, weight=1)
        
        # Options title (will update based on selection)
        self.options_title = ctk.CTkLabel(
            self.options_card, 
            text="📷 Screenshot Options", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        self.options_title.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Placeholder for options content
        self.options_content_frame = ctk.CTkFrame(self.options_card, fg_color="transparent")
        self.options_content_frame.grid(row=1, column=0, padx=30, pady=(0, 15), sticky="ew")
        self.options_content_frame.grid_columnconfigure(0, weight=1)
        
        # Initialize with Screenshot options
        self._update_options_display()

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _on_discord_enable_change(self):
        """Called when Discord enable checkbox is changed."""
        enabled = self.discord_enabled.get()
        self.app.settings["discord_enabled"] = enabled

    
    def _on_webhook_url_change(self, *args):
        """Called when webhook URL changes."""
        self.app.settings["webhook_url"] = self.webhook_url_var.get()
    
    def _on_message_style_save(self):
        """Called when message style changes."""
        self.app.settings["discord_message_style"] = self.message_style_var.get()
    
    def _on_message_style_change(self, selected_style):
        """Called when message style dropdown selection changes."""

        self._update_options_display()
    
    def _update_options_display(self):
        """Updates the options display based on selected message style."""
        # Clear existing options content
        for widget in self.options_content_frame.winfo_children():
            widget.destroy()
        
        selected_style = self.message_style_var.get()
        
        # Update title and content based on selection
        if selected_style == "Screenshot":
            self.options_title.configure(text="📷 Screenshot Options")
            
            # Test Screenshot Webhook Button
            test_screenshot_btn = ctk.CTkButton(
                self.options_content_frame,
                text="📷 Test Screenshot Webhook",
                command=self._test_screenshot_webhook,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#5865F2",
                hover_color="#7289DA",
                text_color="white",
                corner_radius=10,
                height=40
            )
            test_screenshot_btn.grid(row=0, column=0, pady=(10, 15), sticky="ew")
            
            # Loops Per Screenshot - load from settings
            loops_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            loops_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
            loops_frame.grid_columnconfigure(1, weight=1)
            
            loops_label = ctk.CTkLabel(
                loops_frame,
                text="🔄 Loops Per Screenshot:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            loops_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.loops_screenshot_var = self._ensure_gui_var("loops_screenshot", tk.StringVar, "10")
            self.loops_screenshot_var.trace_add("write", lambda *args: self.app.settings.update({"loops_screenshot": self.loops_screenshot_var.get()}))
            loops_entry = ctk.CTkEntry(
                loops_frame,
                textvariable=self.loops_screenshot_var,
                font=ctk.CTkFont(size=14),
                fg_color="#383838",
                border_color="#5865F2",
                text_color="#FFFFFF",
                width=100,
                validate="key",
                validatecommand=(self.register(self._validate_number), '%P')
            )
            loops_entry.grid(row=0, column=1, padx=(0, 0), sticky="w")
            
        elif selected_style == "Text":
            self.options_title.configure(text="📝 Text Options")
            
            # Test Text Webhook Button
            test_text_btn = ctk.CTkButton(
                self.options_content_frame,
                text="📝 Test Text Webhook",
                command=self._test_text_webhook,
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#5865F2",
                hover_color="#7289DA",
                text_color="white",
                corner_radius=10,
                height=40
            )
            test_text_btn.grid(row=0, column=0, pady=(10, 15), sticky="ew")
            
            # Loops Per Text
            loops_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            loops_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
            loops_frame.grid_columnconfigure(1, weight=1)
            
            loops_label = ctk.CTkLabel(
                loops_frame,
                text="🔄 Loops Per Text:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            loops_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.loops_text_var = tk.StringVar(value=self.app.settings.get("loops_text", "10"))
            self.loops_text_var.trace_add("write", lambda *args: self.app.settings.update({"loops_text": self.loops_text_var.get()}))
            loops_entry = ctk.CTkEntry(
                loops_frame,
                textvariable=self.loops_text_var,
                font=ctk.CTkFont(size=14),
                fg_color="#383838",
                border_color="#5865F2",
                text_color="#FFFFFF",
                width=100,
                validate="key",
                validatecommand=(self.register(self._validate_number), '%P')
            )
            loops_entry.grid(row=0, column=1, padx=(0, 0), sticky="w")
    
    def _validate_number(self, value):
        """Validates that input is a number."""
        if value == "":
            return True
        try:
            int(value)
            return True
        except ValueError:
            return False
    
    def _test_screenshot_webhook(self):
        """Tests the screenshot webhook functionality in a background thread."""
        webhook_url = self.webhook_url_var.get().strip()
        
        if not webhook_url:
            print("❌ Error: Webhook URL is required for testing")
            return
        
        if not webhook_url.startswith("https://discord.com/api/webhooks/"):
            print("❌ Error: Invalid Discord webhook URL format")
            return
        
        print("📷 Starting screenshot webhook test in background...")
        
        # Run in background thread to prevent GUI freezing
        thread = threading.Thread(target=self._screenshot_webhook_worker, args=(webhook_url,), daemon=True)
        thread.start()
    
    def _screenshot_webhook_worker(self, webhook_url):
        """Worker function for screenshot webhook test that runs in background thread."""
        try:
            print("📸 Taking screenshot for Discord webhook test...")
            
            # Initialize dxcam and capture screenshot
            camera = dxcam.create()
            screenshot = camera.grab()
            
            if screenshot is None:
                print("❌ Error: Failed to capture screenshot")
                return
            
            # Convert numpy array to PIL Image
            img = Image.fromarray(screenshot)
            
            # Convert to bytes
            img_buffer = io.BytesIO()
            img.save(img_buffer, format='PNG')
            img_bytes = img_buffer.getvalue()
            
            # Prepare Discord webhook payload
            files = {
                'file': ('screenshot.png', img_bytes, 'image/png')
            }
            
            payload = {
                'content': '📷 **IRUS COMET SCREENSHOT TEST** 🖼️\n\n📸 This is a test screenshot from IRUS COMET Discord integration!\n✅ Screenshot taken successfully.',
                'username': 'IRUS COMET',
                'avatar_url': 'https://cdn.discordapp.com/emojis/1234567890123456789.png'  # Optional: you can replace with actual avatar
            }
            
            # Send to Discord
            response = requests.post(webhook_url, data=payload, files=files, timeout=10)
            
            if response.status_code in HTTP_SUCCESS_CODES:
                print("✅ Screenshot webhook test successful! Message sent to Discord.")
            else:
                print(f"❌ Webhook test failed. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Error during screenshot webhook test: {str(e)}")
    
    def _test_text_webhook(self):
        """Tests the text webhook functionality in a background thread."""
        webhook_url = self.webhook_url_var.get().strip()
        
        if not webhook_url:
            print("❌ Error: Webhook URL is required for testing")
            return
        
        if not webhook_url.startswith("https://discord.com/api/webhooks/"):
            print("❌ Error: Invalid Discord webhook URL format")
            return
        
        print("📝 Starting text webhook test in background...")
        
        # Run in background thread to prevent GUI freezing
        thread = threading.Thread(target=self._text_webhook_worker, args=(webhook_url,), daemon=True)
        thread.start()
    
    def _text_webhook_worker(self, webhook_url):
        """Worker function for text webhook test that runs in background thread."""
        try:
            print("📨 Sending text message to Discord webhook...")
            
            # Prepare Discord webhook payload for text only
            payload = {
                'content': '📝 **IRUS COMET TEXT TEST** ✉️\n\n📨 This is a test message from IRUS COMET Discord integration!\n✅ Text webhook functionality is working correctly.\n\n🚀 Ready for automation!',
                'username': 'IRUS COMET',
                'avatar_url': 'https://cdn.discordapp.com/emojis/1234567890123456789.png',  # Optional: you can replace with actual avatar
                'embeds': [
                    {
                        'title': '🧪🔗 IRUS COMET Integration Test',
                        'description': 'Text webhook test completed successfully!',
                        'color': 0x5865F2,  # Discord blue color
                        'footer': {
                            'text': 'IRUS COMET by AsphaltCake'
                        }
                    }
                ]
            }
            
            # Send to Discord
            response = requests.post(
                webhook_url, 
                json=payload, 
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            
            if response.status_code in HTTP_SUCCESS_CODES:
                print("✅ Text webhook test successful! Message sent to Discord.")
            else:
                print(f"❌ Webhook test failed. Status code: {response.status_code}")
                print(f"Response: {response.text}")
                
        except Exception as e:
            print(f"❌ Error during text webhook test: {str(e)}")

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")


class FishView(ctk.CTkFrame):  # AI_TARGET: FISH_GUI
    """
    A view (CTkFrame) to contain the Fish settings. Uses a standard tk.Canvas 
    to create custom, scrollable content with green theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = master  # Reference to StarryNightApp to access settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion
        
        # State for screen freeze functionality
        self.screen_frozen = False
        self.frozen_screenshot = None
        self.freeze_overlay = None
        self.current_color_pick_setting = None

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#7ED321", # Match the green background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#9AE84A"   # Lighter green border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="🐟 Fish Settings", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n") 
        
        # Fish Track Style Selection Section with modern card design
        self.fish_track_style_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.fish_track_style_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.fish_track_style_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the fish track style section
        subtitle_label = ctk.CTkLabel(
            self.fish_track_style_card, 
            text="⚙️ Fish Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Fish Track Style dropdown
        fish_track_style_label = ctk.CTkLabel(
            self.fish_track_style_card, 
            text="🎯 Fish Track Style:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        fish_track_style_label.grid(row=1, column=0, padx=(30, 15), pady=12, sticky="ew")

        self.fish_track_style_var = tk.StringVar(value=self.app.settings["fish_track_style"])
        fish_track_style_dropdown = ctk.CTkOptionMenu(
            self.fish_track_style_card, 
            values=["Color", "Line"],
            variable=self.fish_track_style_var,
            command=self._on_fish_track_style_change,
            fg_color="#7ED321",      # Green theme
            button_color="#6BB91A",   # Darker green for button
            button_hover_color="#9AE84A",  # Lighter green on hover
            dropdown_fg_color="#383838",  # Match container
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        fish_track_style_dropdown.grid(row=1, column=1, padx=(15, 30), pady=12, sticky="ew")
        
        # Rod Type dropdown
        rod_type_label = ctk.CTkLabel(
            self.fish_track_style_card, 
            text="🎣 Rod Type:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        rod_type_label.grid(row=2, column=0, padx=(30, 15), pady=12, sticky="ew")

        # Initialize rod types list and get current rod types
        self._initialize_rod_types()
        
        self.rod_type_var = tk.StringVar(value=self.app.settings["fish_rod_type"])
        self.rod_type_dropdown = ctk.CTkOptionMenu(
            self.fish_track_style_card, 
            values=self._get_rod_types_list(),
            variable=self.rod_type_var,
            command=self._on_rod_type_change,
            fg_color="#7ED321",      # Green theme
            button_color="#6BB91A",   # Darker green for button
            button_hover_color="#9AE84A",  # Lighter green on hover
            dropdown_fg_color="#383838",  # Match container
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        self.rod_type_dropdown.grid(row=2, column=1, padx=(15, 30), pady=12, sticky="ew")
        
        # Rod management buttons
        rod_management_frame = ctk.CTkFrame(self.fish_track_style_card, fg_color="transparent")
        rod_management_frame.grid(row=3, column=0, columnspan=2, padx=(30, 30), pady=(5, 15), sticky="ew")
        
        # Add Rod button
        add_rod_button = ctk.CTkButton(
            rod_management_frame,
            text="➕ Add Rod",
            command=self._add_new_rod_type,
            fg_color="#4CAF50",
            hover_color="#45a049",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            height=30,
            width=100
        )
        add_rod_button.grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        # Delete Rod button
        delete_rod_button = ctk.CTkButton(
            rod_management_frame,
            text="🗑️ Delete Rod",
            command=self._delete_rod_type,
            fg_color="#f44336",
            hover_color="#da190b",
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=8,
            height=30,
            width=110
        )
        delete_rod_button.grid(row=0, column=1, sticky="w")
        
        # Dynamic options container
        self.options_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.options_card.grid(row=2, column=0, sticky="ew", pady=(0, 25), padx=30)
        self.options_card.grid_columnconfigure(0, weight=1)
        
        # Options title (will update based on selection)
        self.options_title = ctk.CTkLabel(
            self.options_card, 
            text="🌈 Color Options", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        self.options_title.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Placeholder for options content
        self.options_content_frame = ctk.CTkFrame(self.options_card, fg_color="transparent")
        self.options_content_frame.grid(row=1, column=0, padx=30, pady=(0, 15), sticky="ew")
        self.options_content_frame.grid_columnconfigure(0, weight=1)
        
        # Initialize with Color options
        self._update_options_display()
        
        # Bind cleanup on destroy
        self.bind("<Destroy>", self._on_destroy)

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _on_fish_track_style_change(self, selected_style):
        """Called when fish track style dropdown selection changes."""

        self.app.settings["fish_track_style"] = selected_style
        self._update_options_display()
    
    def _initialize_rod_types(self):
        """Initialize rod types storage if not exists."""
        # Define all preset rod types (undeletable)
        preset_rods = [
            "Default", "Evil Pitch Fork", "Onirifalx", "Polaris Serenade",
            "Sword of Darkness", "Wingripper", "Chrysalis",
            "Luminescent Oath", "Ruinous Oath", "Duskwire", "Sanguine Spire",
            "Rod of Shadow", "Rainbow Cluster"
        ]

        if "rod_types" not in self.app.settings:
            # First time initialization - add preset rods
            self.app.settings["rod_types"] = preset_rods.copy()
            print("  ⚙️ Initialized rod types with presets")
        else:
            # Rod types already exist (loaded from config)
            # Only add missing preset rods if the list is completely empty
            if len(self.app.settings["rod_types"]) == 0:
                self.app.settings["rod_types"] = preset_rods.copy()
                print("  ⚙️ Rod types list was empty, restored presets")
            else:
                # Ensure "Default" rod always exists (required)
                if "Default" not in self.app.settings["rod_types"]:
                    self.app.settings["rod_types"].insert(0, "Default")
                    print("  ✅ Ensured 'Default' rod exists")

        # Initialize all preset rods with their specific colors
        self._initialize_preset_rod_colors()

        # Ensure current rod type exists in the list
        current_rod = self.app.settings.get("fish_rod_type", "Default")
        if current_rod not in self.app.settings["rod_types"]:
            print(f"  🎣 Current rod '{current_rod}' not found, adding it back")
            self.app.settings["rod_types"].append(current_rod)
    
    def _initialize_preset_rod_colors(self):
        """Initialize all preset rods with their specific default colors."""
        # Rod color configurations from v6.7.5.py
        rod_configs = {
            "Default": {
                "fish_target_line_color": "#434b5b",
                "fish_arrow_color": "#848587",
                "fish_left_bar_color": "#f1f1f1",
                "fish_right_bar_color": "#ffffff",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Evil Pitch Fork": {
                "fish_target_line_color": "#671515",
                "fish_arrow_color": "#848587",
                "fish_left_bar_color": "#f1f1f1",
                "fish_right_bar_color": "#ffffff",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 3,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Onirifalx": {
                "fish_target_line_color": "#000000",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#b4def6",
                "fish_right_bar_color": "#6689b5",
                "fish_target_line_tolerance": 0,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Polaris Serenade": {
                "fish_target_line_color": "#29caf5",
                "fish_arrow_color": "#848587",
                "fish_left_bar_color": "#f1f1f1",
                "fish_right_bar_color": "#ffffff",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 3,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Sword of Darkness": {
                "fish_target_line_color": "#000000",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#171716",
                "fish_right_bar_color": None,
                "fish_target_line_tolerance": 0,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 5,
                "fish_right_bar_tolerance": 5
            },
            "Wingripper": {
                "fish_target_line_color": "#707777",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#151515",
                "fish_right_bar_color": None,
                "fish_target_line_tolerance": 15,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Chrysalis": {
                "fish_target_line_color": "#000000",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#ebadf6",
                "fish_right_bar_color": None,
                "fish_target_line_tolerance": 0,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 5,
                "fish_right_bar_tolerance": 5
            },
            "Luminescent Oath": {
                "fish_target_line_color": "#434b5b",
                "fish_arrow_color": "#848587",
                "fish_left_bar_color": "#f1f1f1",
                "fish_right_bar_color": "#0000ff",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 3,
                "fish_left_bar_tolerance": 20,
                "fish_right_bar_tolerance": 20
            },
            "Ruinous Oath": {
                "fish_target_line_color": "#434b5b",
                "fish_arrow_color": "#848587",
                "fish_left_bar_color": "#f1f1f1",
                "fish_right_bar_color": "#ff0000",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 3,
                "fish_left_bar_tolerance": 20,
                "fish_right_bar_tolerance": 20
            },
            "Duskwire": {
                "fish_target_line_color": "#ffffff",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#2f2f2f",
                "fish_right_bar_color": "#000000",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 5,
                "fish_right_bar_tolerance": 5
            },
            "Sanguine Spire": {
                "fish_target_line_color": "#44110f",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#540000",
                "fish_right_bar_color": "#220000",
                "fish_target_line_tolerance": 2,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Rod of Shadow": {
                "fish_target_line_color": "#000000",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#171716",
                "fish_right_bar_color": None,
                "fish_target_line_tolerance": 0,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 3,
                "fish_right_bar_tolerance": 3
            },
            "Rainbow Cluster": {
                "fish_target_line_color": "#eaeaea",
                "fish_arrow_color": None,
                "fish_left_bar_color": "#f48f8a",
                "fish_right_bar_color": "#9470bb",
                "fish_target_line_tolerance": 0,
                "fish_arrow_tolerance": 0,
                "fish_left_bar_tolerance": 5,
                "fish_right_bar_tolerance": 5
            }
        }

        # Initialize each preset rod with its specific colors
        for rod_name, rod_settings in rod_configs.items():
            for key, value in rod_settings.items():
                full_key = f"{key}_{rod_name}"
                if full_key not in self.app.settings:
                    # Keep None as "None" string so arrow fallback is disabled when no arrows exist
                    self.app.settings[full_key] = value if value is not None else "None"


    
    def _get_rod_types_list(self):
        """Get the current list of rod types."""
        return self.app.settings.get("rod_types", ["Default"])
    
    def _add_new_rod_type(self):
        """Add a new custom rod type."""
        import tkinter.simpledialog as simpledialog
        
        # Get new rod name from user
        new_rod_name = simpledialog.askstring(
            "Add New Rod Type",
            "Enter name for new rod type:",
            parent=self.app
        )
        
        if not new_rod_name:
            return  # User cancelled
        
        # Clean and validate name
        new_rod_name = new_rod_name.strip()
        if not new_rod_name:
            print("Rod name cannot be empty")
            return
        
        # Check for duplicates
        existing_rods = self._get_rod_types_list()
        if new_rod_name in existing_rods:
            print(f"Rod type '{new_rod_name}' already exists")
            return
        
        # Add new rod type
        self.app.settings["rod_types"].append(new_rod_name)
        
        # Initialize default settings for new rod
        self._initialize_rod_settings(new_rod_name)
        
        # Update dropdown
        self.rod_type_dropdown.configure(values=self._get_rod_types_list())
        
        # Switch to new rod
        self.rod_type_var.set(new_rod_name)
        self._on_rod_type_change(new_rod_name)
        

    
    def _delete_rod_type(self):
        """Delete the currently selected rod type."""
        current_rod = self.rod_type_var.get()

        # Cannot delete any preset rod
        preset_rods = [
            "Default", "Evil Pitch Fork", "Onirifalx", "Polaris Serenade",
            "Sword of Darkness", "Wingripper", "Chrysalis",
            "Luminescent Oath", "Ruinous Oath", "Duskwire", "Sanguine Spire",
            "Rod of Shadow", "Rainbow Cluster"
        ]

        if current_rod in preset_rods:
            print(f"Cannot delete preset rod type: {current_rod}")
            return
        
        # Must have at least one rod type
        existing_rods = self._get_rod_types_list()
        if len(existing_rods) <= 1:
            print("Cannot delete the only remaining rod type")
            return
        
        # Confirm deletion
        import tkinter.messagebox as messagebox
        confirm = messagebox.askyesno(
            "Delete Rod Type",
            f"Are you sure you want to delete rod type '{current_rod}'?\n\nThis will remove all settings for this rod type.",
            parent=self.app
        )
        
        if not confirm:
            return
        
        # Remove from rod types list
        self.app.settings["rod_types"].remove(current_rod)
        
        # Remove all settings for this rod type
        self._remove_rod_settings(current_rod)
        
        # Switch to Default rod
        self.rod_type_var.set("Default")
        
        # Update dropdown
        self.rod_type_dropdown.configure(values=self._get_rod_types_list())
        
        # Update display
        self._on_rod_type_change("Default")
        

    
    def _initialize_rod_settings(self, rod_name):
        """Initialize default settings for a new rod type."""
        # Default colors (the ones you specified)
        default_colors = {
            f"fish_target_line_color_{rod_name}": "#434b5b",
            f"fish_arrow_color_{rod_name}": "#848587",
            f"fish_left_bar_color_{rod_name}": "#f1f1f1",
            f"fish_right_bar_color_{rod_name}": "#ffffff"
        }
        
        # Default tolerances
        default_tolerances = {
            f"fish_target_line_tolerance_{rod_name}": 0,
            f"fish_arrow_tolerance_{rod_name}": 3,
            f"fish_left_bar_tolerance_{rod_name}": 0,
            f"fish_right_bar_tolerance_{rod_name}": 0
        }
        
        # Set defaults
        for key, value in {**default_colors, **default_tolerances}.items():
            if key not in self.app.settings:
                self.app.settings[key] = value
    
    def _remove_rod_settings(self, rod_name):
        """Remove all settings for a specific rod type."""
        keys_to_remove = []
        for key in self.app.settings.keys():
            if key.endswith(f"_{rod_name}"):
                keys_to_remove.append(key)
        
        for key in keys_to_remove:
            del self.app.settings[key]
    
    def _get_rod_setting_key(self, base_key):
        """Get the rod-specific setting key."""
        current_rod = self.rod_type_var.get()
        if current_rod == "Default":
            return base_key  # Default rod uses original keys
        else:
            return f"{base_key}_{current_rod}"
    
    def _on_rod_type_change(self, selected_type):
        """Called when rod type dropdown selection changes."""

        self.app.settings["fish_rod_type"] = selected_type
        
        # Update color and tolerance displays for the new rod type
        self._update_all_displays_for_rod_type()
    
    def _update_options_display(self):
        """Updates the options display based on selected fish track style."""
        # Clear existing options content
        for widget in self.options_content_frame.winfo_children():
            widget.destroy()
        
        selected_style = self.fish_track_style_var.get()
        
        # Update title and content based on selection
        if selected_style == "Color":
            self.options_title.configure(text="🌈 Color Options")
            self._create_color_options()
            
        elif selected_style == "Line":
            self.options_title.configure(text="📏 Line Options")
            self._create_line_options()
    
    def _create_color_options(self):
        """Creates the color options UI with freeze screen and color pickers."""
        self.options_content_frame.grid_columnconfigure((0, 1), weight=1)
        
        # Freeze Screen button
        freeze_button = ctk.CTkButton(
            self.options_content_frame,
            text="❄️ Freeze Screen" if not self.screen_frozen else "🔥 Unfreeze Screen",
            command=self._toggle_freeze_screen,
            fg_color="#7ED321",
            hover_color="#9AE84A",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10,
            height=35
        )
        freeze_button.grid(row=0, column=0, columnspan=2, pady=(10, 20), padx=20, sticky="ew")
        
        # Store reference to update text later
        self.freeze_button = freeze_button
        
        # Color picker options
        color_options = [
            ("📏 Target Line", "fish_target_line_color"),
            ("➡️ Arrow", "fish_arrow_color"),
            ("◀️ Left Bar", "fish_left_bar_color"),
            ("▶️ Right Bar", "fish_right_bar_color")
        ]
        
        for i, (label_text, setting_key) in enumerate(color_options):
            row = 1 + i
            
            # Color option label
            color_label = ctk.CTkLabel(
                self.options_content_frame,
                text=label_text,
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            color_label.grid(row=row, column=0, padx=(20, 10), pady=8, sticky="w")
            
            # Create frame for color controls
            color_controls_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            color_controls_frame.grid(row=row, column=1, padx=(10, 20), pady=8, sticky="e")
            
            # Color picker button with color preview
            color_value = self._get_rod_specific_setting(setting_key)
            # Handle "None" color - display as gray, not as actual color
            display_color = "#666666" if color_value == "None" else color_value
            color_button = ctk.CTkButton(
                color_controls_frame,
                text="Pick Color",
                command=lambda key=setting_key: self._pick_color(key),
                fg_color=display_color,
                hover_color=self._lighten_color(display_color),
                font=ctk.CTkFont(size=12, weight="bold"),
                corner_radius=8,
                height=30,
                width=80
            )
            color_button.grid(row=0, column=0, padx=(0, 5))
            
            # Color code display (read-only)
            color_code_entry = ctk.CTkEntry(
                color_controls_frame,
                width=80,
                height=30,
                font=ctk.CTkFont(size=11),
                justify="center"
            )
            color_code_entry.insert(0, str(color_value))
            color_code_entry.configure(state="readonly")  # Make it read-only but copyable
            color_code_entry.grid(row=0, column=1, padx=(0, 5))
            
            # None button
            none_button = ctk.CTkButton(
                color_controls_frame,
                text="None",
                command=lambda key=setting_key: self._set_color_none(key),
                fg_color="#FF4444",
                hover_color="#FF6666",
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=6,
                height=30,
                width=50
            )
            none_button.grid(row=0, column=2, padx=(0, 5))
            
            # Default button
            default_button = ctk.CTkButton(
                color_controls_frame,
                text="Default",
                command=lambda key=setting_key: self._set_color_default(key),
                fg_color="#4444FF",
                hover_color="#6666FF",
                font=ctk.CTkFont(size=11, weight="bold"),
                corner_radius=6,
                height=30,
                width=60
            )
            default_button.grid(row=0, column=3, padx=(0, 10))
            
            # Tolerance input box
            tolerance_key = setting_key.replace("color", "tolerance")
            # Get appropriate default based on the tolerance type
            default_tolerance = self._get_default_tolerance_for_key(tolerance_key)
            tolerance_value = self._get_rod_specific_setting(tolerance_key, default_tolerance)
            
            tolerance_entry = ctk.CTkEntry(
                color_controls_frame,
                width=50,
                height=30,
                font=ctk.CTkFont(size=11),
                justify="center",
                placeholder_text="20"
            )
            tolerance_entry.insert(0, str(tolerance_value))
            tolerance_entry.grid(row=0, column=4, padx=(0, 5))
            
            # Bind tolerance entry to update function
            tolerance_entry.bind('<KeyRelease>', lambda event, key=tolerance_key: self._on_tolerance_entry_change(key, event))
            tolerance_entry.bind('<FocusOut>', lambda event, key=tolerance_key: self._on_tolerance_entry_change(key, event))
            
            # Tolerance label
            tolerance_label = ctk.CTkLabel(
                color_controls_frame,
                text="Tol",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color="#CCCCCC",
                width=25
            )
            tolerance_label.grid(row=0, column=5)
            
            # Store references for later updates
            setattr(self, f"{setting_key}_button", color_button)
            setattr(self, f"{setting_key}_entry", color_code_entry)
            setattr(self, f"{tolerance_key}_entry", tolerance_entry)
        
        # Add separator line
        separator = ctk.CTkFrame(
            self.options_content_frame,
            height=2,
            fg_color="#5A5A5A"
        )
        separator.grid(row=5, column=0, columnspan=2, padx=20, pady=(15, 10), sticky="ew")
        
        # Additional Fish Settings Section
        fish_settings_title = ctk.CTkLabel(
            self.options_content_frame,
            text="🐟 Fish Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#E0E0E0"
        )
        fish_settings_title.grid(row=6, column=0, columnspan=2, pady=(10, 15), sticky="n")
        
        # Scan FPS with MS display (like Shake tab)
        scan_fps_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        scan_fps_frame.grid(row=7, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        scan_fps_frame.grid_columnconfigure(1, weight=1)
        
        scan_fps_label = ctk.CTkLabel(
            scan_fps_frame,
            text="📊 Scan FPS:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        scan_fps_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
        
        self.fish_scan_fps_var = tk.IntVar(value=self._get_rod_specific_setting("fish_scan_fps", 150))
        self.fish_scan_fps_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_scan_fps", self.fish_scan_fps_var.get()))
        scan_fps_slider = ctk.CTkSlider(
            scan_fps_frame,
            from_=10,
            to=1000,
            number_of_steps=99,  # (1000-10)/10 = 99 steps
            variable=self.fish_scan_fps_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        scan_fps_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        def update_fish_fps_display(value):
            fps = int(value)
            if fps >= 1000:
                ms_text = "(0ms delay)"
            else:
                ms = round(1000 / fps, 1)
                if ms == int(ms):
                    ms_text = f"({int(ms)}ms)"
                else:
                    ms_text = f"({ms}ms)"
            scan_fps_value.configure(text=f"{fps} {ms_text}")
        
        scan_fps_value = ctk.CTkLabel(
            scan_fps_frame,
            text="30 (33ms)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=100
        )
        scan_fps_value.grid(row=0, column=2, sticky="e")
        
        scan_fps_slider.configure(command=update_fish_fps_display)
        update_fish_fps_display(self.fish_scan_fps_var.get())  # Initialize display
        
        # Fish Lost Timeout
        fish_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        fish_timeout_frame.grid(row=8, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        fish_timeout_frame.grid_columnconfigure(1, weight=1)

        fish_timeout_label = ctk.CTkLabel(
            fish_timeout_frame,
            text="⏱️ Fish Lost Timeout:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        fish_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_lost_timeout_var = tk.IntVar(value=self._get_rod_specific_setting("fish_lost_timeout", 1))
        self.fish_lost_timeout_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_lost_timeout", self.fish_lost_timeout_var.get()))
        fish_timeout_slider = ctk.CTkSlider(
            fish_timeout_frame,
            from_=0,
            to=10,
            number_of_steps=10,
            variable=self.fish_lost_timeout_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        fish_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        fish_timeout_value = ctk.CTkLabel(
            fish_timeout_frame,
            text="3s",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=30
        )
        fish_timeout_value.grid(row=0, column=2, sticky="e")

        fish_timeout_slider.configure(command=lambda value: fish_timeout_value.configure(text=f"{int(value)}s"))
        
        # Bar Ratio From Side
        bar_ratio_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        bar_ratio_frame.grid(row=9, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        bar_ratio_frame.grid_columnconfigure(1, weight=1)

        bar_ratio_label = ctk.CTkLabel(
            bar_ratio_frame,
            text="📏 Bar Ratio From Side:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        bar_ratio_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        # Use a manual variable since we need decimal precision
        current_ratio = self._get_rod_specific_setting("fish_bar_ratio_from_side", 0.6)
        bar_ratio_slider = ctk.CTkSlider(
            bar_ratio_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=10,  # 0.1 increments
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        bar_ratio_slider.set(float(current_ratio))
        bar_ratio_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        bar_ratio_value = ctk.CTkLabel(
            bar_ratio_frame,
            text="0.5",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=30
        )
        bar_ratio_value.grid(row=0, column=2, sticky="e")

        def update_bar_ratio(value):
            ratio = round(float(value), 1)
            bar_ratio_value.configure(text=f"{ratio}")
            self._set_rod_specific_setting("fish_bar_ratio_from_side", ratio)

        bar_ratio_slider.configure(command=update_bar_ratio)
        
        # Control Mode Dropdown
        control_mode_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        control_mode_frame.grid(row=11, column=0, columnspan=2, pady=(15, 10), padx=20, sticky="ew")
        control_mode_frame.grid_columnconfigure(1, weight=1)

        control_mode_label = ctk.CTkLabel(
            control_mode_frame,
            text="🎮 Control Mode:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        control_mode_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_control_mode_var = tk.StringVar(value=self._get_rod_specific_setting("fish_control_mode", "Normal"))
        control_mode_dropdown = ctk.CTkOptionMenu(
            control_mode_frame,
            variable=self.fish_control_mode_var,
            values=["Normal", "Steady", "NigGamble"],
            command=self._on_color_control_mode_change,
            fg_color="#4A4A4A",
            button_color="#7ED321",
            button_hover_color="#6BB91A",
            dropdown_fg_color="#3A3A3A",
            width=150
        )
        control_mode_dropdown.grid(row=0, column=1, sticky="e")
        
        # KP Entry Box
        kp_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        kp_frame.grid(row=12, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        kp_frame.grid_columnconfigure(1, weight=1)

        kp_label = ctk.CTkLabel(
            kp_frame,
            text="🎛️ KP:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        kp_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_kp_entry = ctk.CTkEntry(
            kp_frame,
            width=80,
            height=30,
            font=ctk.CTkFont(size=12),
            justify="center",
            placeholder_text="30"
        )
        current_kp = self._get_rod_specific_setting("fish_kp", 0.9)
        self.fish_kp_entry.insert(0, str(current_kp))
        self.fish_kp_entry.grid(row=0, column=1, padx=(0, 10), sticky="e")
        
        # Bind KP entry events
        self.fish_kp_entry.bind('<KeyRelease>', lambda event: self._on_fish_numeric_entry_change("fish_kp", event))
        self.fish_kp_entry.bind('<FocusOut>', lambda event: self._on_fish_numeric_entry_change("fish_kp", event))
        
        # KD Entry Box
        kd_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        kd_frame.grid(row=13, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        kd_frame.grid_columnconfigure(1, weight=1)

        kd_label = ctk.CTkLabel(
            kd_frame,
            text="🎛️ KD:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        kd_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_kd_entry = ctk.CTkEntry(
            kd_frame,
            width=80,
            height=30,
            font=ctk.CTkFont(size=12),
            justify="center",
            placeholder_text="30"
        )
        current_kd = self._get_rod_specific_setting("fish_kd", 0.2)
        self.fish_kd_entry.insert(0, str(current_kd))
        self.fish_kd_entry.grid(row=0, column=1, padx=(0, 10), sticky="e")
        
        # Bind KD entry events
        self.fish_kd_entry.bind('<KeyRelease>', lambda event: self._on_fish_numeric_entry_change("fish_kd", event))
        self.fish_kd_entry.bind('<FocusOut>', lambda event: self._on_fish_numeric_entry_change("fish_kd", event))
        
        # PD Clamp removed from GUI - using fixed internal value since control is binary (on/off only)

    def _create_line_options(self):
        """Creates the Line options UI for line-based fish tracking."""
        self.options_content_frame.grid_columnconfigure((0, 1), weight=1)

        # Line Settings Section Title
        line_settings_title = ctk.CTkLabel(
            self.options_content_frame,
            text="📏 Line Tracking Settings",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#E0E0E0"
        )
        line_settings_title.grid(row=0, column=0, columnspan=2, pady=(10, 15), sticky="n")

        # Scan FPS with MS display
        scan_fps_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        scan_fps_frame.grid(row=1, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        scan_fps_frame.grid_columnconfigure(1, weight=1)

        scan_fps_label = ctk.CTkLabel(
            scan_fps_frame,
            text="📊 Scan FPS:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        scan_fps_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_scan_fps_var = tk.IntVar(value=self._get_rod_specific_setting("fish_line_scan_fps", 150))
        self.fish_line_scan_fps_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_scan_fps", self.fish_line_scan_fps_var.get()))
        scan_fps_slider = ctk.CTkSlider(
            scan_fps_frame,
            from_=10,
            to=1000,
            number_of_steps=99,
            variable=self.fish_line_scan_fps_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        scan_fps_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        def update_line_fps_display(value):
            fps = int(value)
            if fps >= 1000:
                ms_text = "(0ms delay)"
            else:
                ms = round(1000 / fps, 1)
                if ms == int(ms):
                    ms_text = f"({int(ms)}ms)"
                else:
                    ms_text = f"({ms}ms)"
            scan_fps_value.configure(text=f"{fps} {ms_text}")

        scan_fps_value = ctk.CTkLabel(
            scan_fps_frame,
            text="200 (5ms)",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=100
        )
        scan_fps_value.grid(row=0, column=2, sticky="e")

        scan_fps_slider.configure(command=update_line_fps_display)
        update_line_fps_display(self.fish_line_scan_fps_var.get())

        # Fish Lost Timeout
        fish_lost_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        fish_lost_frame.grid(row=2, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        fish_lost_frame.grid_columnconfigure(1, weight=1)

        fish_lost_label = ctk.CTkLabel(
            fish_lost_frame,
            text="⏱️ Fish Lost Timeout:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        fish_lost_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_lost_timeout_var = tk.DoubleVar(value=self._get_rod_specific_setting("fish_line_lost_timeout", 1.0))
        self.fish_line_lost_timeout_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_lost_timeout", self.fish_line_lost_timeout_var.get()))
        fish_lost_slider = ctk.CTkSlider(
            fish_lost_frame,
            from_=0.5,
            to=10.0,
            number_of_steps=95,
            variable=self.fish_line_lost_timeout_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        fish_lost_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        fish_lost_value = ctk.CTkLabel(
            fish_lost_frame,
            text="3.0s",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=60
        )
        fish_lost_value.grid(row=0, column=2, sticky="e")

        fish_lost_slider.configure(command=lambda value: fish_lost_value.configure(text=f"{float(value):.1f}s"))
        fish_lost_value.configure(text=f"{self.fish_line_lost_timeout_var.get():.1f}s")

        # Bar Ratio From Side
        bar_ratio_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        bar_ratio_frame.grid(row=3, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        bar_ratio_frame.grid_columnconfigure(1, weight=1)

        bar_ratio_label = ctk.CTkLabel(
            bar_ratio_frame,
            text="📏 Bar Ratio From Side:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        bar_ratio_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_bar_ratio_var = tk.DoubleVar(value=self._get_rod_specific_setting("fish_line_bar_ratio", 0.6))
        self.fish_line_bar_ratio_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_bar_ratio", self.fish_line_bar_ratio_var.get()))
        bar_ratio_slider = ctk.CTkSlider(
            bar_ratio_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=100,
            variable=self.fish_line_bar_ratio_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        bar_ratio_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        bar_ratio_value = ctk.CTkLabel(
            bar_ratio_frame,
            text="0.45",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=60
        )
        bar_ratio_value.grid(row=0, column=2, sticky="e")

        bar_ratio_slider.configure(command=lambda value: bar_ratio_value.configure(text=f"{float(value):.2f}"))
        bar_ratio_value.configure(text=f"{self.fish_line_bar_ratio_var.get():.2f}")

        # Min Line Density Slider (Line mode only)
        min_density_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        min_density_frame.grid(row=4, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        min_density_frame.grid_columnconfigure(1, weight=1)

        min_density_label = ctk.CTkLabel(
            min_density_frame,
            text="📊 Min Line Density:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        min_density_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_min_density_var = tk.DoubleVar(value=self._get_rod_specific_setting("fish_line_min_density", 0.8))
        self.fish_line_min_density_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_min_density", self.fish_line_min_density_var.get()))
        min_density_slider = ctk.CTkSlider(
            min_density_frame,
            from_=0.01,
            to=1.0,
            number_of_steps=99,
            variable=self.fish_line_min_density_var,
            progress_color="#7ED321",
            button_color="#9AE84A",
            button_hover_color="#6BB91A"
        )
        min_density_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        min_density_value = ctk.CTkLabel(
            min_density_frame,
            text="80%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#9AE84A",
            width=60
        )
        min_density_value.grid(row=0, column=2, sticky="e")

        min_density_slider.configure(command=lambda value: min_density_value.configure(text=f"{float(value)*100:.0f}%"))
        min_density_value.configure(text=f"{self.fish_line_min_density_var.get()*100:.0f}%")

        # === 🔍 DETECTION SENSITIVITY SECTION ===
        sensitivity_title = ctk.CTkLabel(
            self.options_content_frame,
            text="🔍 Detection Sensitivity",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#FFD700"
        )
        sensitivity_title.grid(row=5, column=0, columnspan=2, pady=(15, 10), sticky="n")

        # Edge Touch Pixels (must touch top OR bottom)
        edge_touch_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        edge_touch_frame.grid(row=6, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        edge_touch_frame.grid_columnconfigure(1, weight=1)

        edge_touch_label = ctk.CTkLabel(
            edge_touch_frame,
            text="📏 Edge Touch (px):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        edge_touch_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_edge_touch_var = tk.IntVar(value=self._get_rod_specific_setting("fish_line_edge_touch_pixels", 1))
        self.fish_line_edge_touch_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_edge_touch_pixels", self.fish_line_edge_touch_var.get()))
        edge_touch_slider = ctk.CTkSlider(
            edge_touch_frame,
            from_=1,
            to=10,
            number_of_steps=9,
            variable=self.fish_line_edge_touch_var,
            progress_color="#00CED1",
            button_color="#00BFFF",
            button_hover_color="#1E90FF"
        )
        edge_touch_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        edge_touch_value = ctk.CTkLabel(
            edge_touch_frame,
            text="1px",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#00BFFF",
            width=60
        )
        edge_touch_value.grid(row=0, column=2, sticky="e")

        edge_touch_slider.configure(command=lambda value: edge_touch_value.configure(text=f"{int(float(value))}px"))
        edge_touch_value.configure(text=f"{self.fish_line_edge_touch_var.get()}px")

        # White Percentage (how much of line is white vs black)
        white_percent_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        white_percent_frame.grid(row=7, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        white_percent_frame.grid_columnconfigure(1, weight=1)

        white_percent_label = ctk.CTkLabel(
            white_percent_frame,
            text="⚪ White % Required:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        white_percent_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_white_percent_var = tk.IntVar(value=self._get_rod_specific_setting("fish_line_white_percentage", 80))
        self.fish_line_white_percent_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_white_percentage", self.fish_line_white_percent_var.get()))
        white_percent_slider = ctk.CTkSlider(
            white_percent_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.fish_line_white_percent_var,
            progress_color="#9370DB",
            button_color="#8A2BE2",
            button_hover_color="#7B68EE"
        )
        white_percent_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        white_percent_value = ctk.CTkLabel(
            white_percent_frame,
            text="80%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#8A2BE2",
            width=60
        )
        white_percent_value.grid(row=0, column=2, sticky="e")

        white_percent_slider.configure(command=lambda value: white_percent_value.configure(text=f"{int(float(value))}%"))
        white_percent_value.configure(text=f"{self.fish_line_white_percent_var.get()}%")

        # Line Merge Distance
        merge_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        merge_frame.grid(row=8, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        merge_frame.grid_columnconfigure(1, weight=1)

        merge_label = ctk.CTkLabel(
            merge_frame,
            text="🔗 Merge Distance:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        merge_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_merge_var = tk.IntVar(value=self._get_rod_specific_setting("fish_line_merge_distance", 2))
        self.fish_line_merge_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_merge_distance", self.fish_line_merge_var.get()))
        merge_slider = ctk.CTkSlider(
            merge_frame,
            from_=1,
            to=5,
            number_of_steps=4,
            variable=self.fish_line_merge_var,
            progress_color="#FFD700",
            button_color="#FFA500",
            button_hover_color="#FF8C00"
        )
        merge_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        merge_value = ctk.CTkLabel(
            merge_frame,
            text="2px",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFA500",
            width=60
        )
        merge_value.grid(row=0, column=2, sticky="e")

        merge_slider.configure(command=lambda value: merge_value.configure(text=f"{int(float(value))}px"))
        merge_value.configure(text=f"{self.fish_line_merge_var.get()}px")

        # Min Lines Required
        min_count_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        min_count_frame.grid(row=9, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        min_count_frame.grid_columnconfigure(1, weight=1)

        min_count_label = ctk.CTkLabel(
            min_count_frame,
            text="📏 Min Lines Required:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        min_count_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_min_count_var = tk.IntVar(value=self._get_rod_specific_setting("fish_line_min_count", 4))
        self.fish_line_min_count_var.trace_add("write", lambda *_: self._set_rod_specific_setting("fish_line_min_count", self.fish_line_min_count_var.get()))
        min_count_slider = ctk.CTkSlider(
            min_count_frame,
            from_=2,
            to=6,
            number_of_steps=4,
            variable=self.fish_line_min_count_var,
            progress_color="#FFD700",
            button_color="#FFA500",
            button_hover_color="#FF8C00"
        )
        min_count_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

        min_count_value = ctk.CTkLabel(
            min_count_frame,
            text="4",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFA500",
            width=60
        )
        min_count_value.grid(row=0, column=2, sticky="e")

        min_count_slider.configure(command=lambda value: min_count_value.configure(text=f"{int(float(value))}"))
        min_count_value.configure(text=f"{self.fish_line_min_count_var.get()}")

        # Control Mode Dropdown
        control_mode_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        control_mode_frame.grid(row=11, column=0, columnspan=2, pady=(15, 10), padx=20, sticky="ew")
        control_mode_frame.grid_columnconfigure(1, weight=1)

        control_mode_label = ctk.CTkLabel(
            control_mode_frame,
            text="🎮 Control Mode:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        control_mode_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_control_mode_var = tk.StringVar(value=self._get_rod_specific_setting("fish_line_control_mode", "Normal"))
        control_mode_dropdown = ctk.CTkOptionMenu(
            control_mode_frame,
            variable=self.fish_line_control_mode_var,
            values=["Normal", "Steady", "NigGamble"],
            command=self._on_line_control_mode_change,
            fg_color="#4A4A4A",
            button_color="#7ED321",
            button_hover_color="#6BB91A",
            dropdown_fg_color="#3A3A3A",
            width=150
        )
        control_mode_dropdown.grid(row=0, column=1, sticky="e")

        # KP Entry Box
        kp_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        kp_frame.grid(row=12, column=0, columnspan=2, pady=(15, 10), padx=20, sticky="ew")
        kp_frame.grid_columnconfigure(1, weight=1)

        kp_label = ctk.CTkLabel(
            kp_frame,
            text="🎛️ KP (Proportional):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        kp_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_kp_entry = ctk.CTkEntry(
            kp_frame,
            width=80,
            height=30,
            font=ctk.CTkFont(size=12),
            justify="center",
            placeholder_text="0.8"
        )
        current_kp = self._get_rod_specific_setting("fish_line_kp", 0.9)
        self.fish_line_kp_entry.insert(0, str(current_kp))
        self.fish_line_kp_entry.grid(row=0, column=1, padx=(0, 10), sticky="e")

        # Bind KP entry events
        self.fish_line_kp_entry.bind('<KeyRelease>', lambda event: self._on_fish_numeric_entry_change("fish_line_kp", event))
        self.fish_line_kp_entry.bind('<FocusOut>', lambda event: self._on_fish_numeric_entry_change("fish_line_kp", event))

        # KD Entry Box
        kd_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
        kd_frame.grid(row=13, column=0, columnspan=2, pady=(0, 10), padx=20, sticky="ew")
        kd_frame.grid_columnconfigure(1, weight=1)

        kd_label = ctk.CTkLabel(
            kd_frame,
            text="🎛️ KD (Derivative):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        kd_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.fish_line_kd_entry = ctk.CTkEntry(
            kd_frame,
            width=80,
            height=30,
            font=ctk.CTkFont(size=12),
            justify="center",
            placeholder_text="0.1"
        )
        current_kd = self._get_rod_specific_setting("fish_line_kd", 0.2)
        self.fish_line_kd_entry.insert(0, str(current_kd))
        self.fish_line_kd_entry.grid(row=0, column=1, padx=(0, 10), sticky="e")

        # Bind KD entry events
        self.fish_line_kd_entry.bind('<KeyRelease>', lambda event: self._on_fish_numeric_entry_change("fish_line_kd", event))
        self.fish_line_kd_entry.bind('<FocusOut>', lambda event: self._on_fish_numeric_entry_change("fish_line_kd", event))

        # PD Clamp Entry Box
        # PD Clamp removed from GUI - using fixed internal value since control is binary (on/off only)

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")
    
    def _toggle_freeze_screen(self):
        """Toggles the screen freeze functionality."""
        if not self.screen_frozen:
            self._freeze_screen()
        else:
            self._unfreeze_screen()
    
    def _freeze_screen(self):
        """Freezes the screen by taking a screenshot and displaying overlay (except GUI)."""
        try:
            from PIL import ImageGrab, ImageTk
            import tkinter as tk
            
            # Take screenshot and store it
            self.frozen_screenshot = ImageGrab.grab()
            
            # Create freeze overlay window that covers everything except this GUI
            self.freeze_overlay = tk.Toplevel()
            self.freeze_overlay.attributes('-fullscreen', True)
            self.freeze_overlay.attributes('-topmost', False)  # GUI stays on top
            self.freeze_overlay.overrideredirect(True)
            
            # Convert screenshot to PhotoImage
            self.frozen_photo = ImageTk.PhotoImage(self.frozen_screenshot)
            
            # Create label with screenshot
            overlay_label = tk.Label(
                self.freeze_overlay, 
                image=self.frozen_photo,
                bg='black'
            )
            overlay_label.pack(fill='both', expand=True)
            
            self.screen_frozen = True
            self.freeze_button.configure(text="🔥 Unfreeze Screen")
            print("Screen frozen - click Pick Color to select colors")
            
        except Exception as e:
            print(f"Error freezing screen: {e}")
    
    def _unfreeze_screen(self):
        """Unfreezes the screen and cleans up."""
        # Clean up freeze overlay
        if hasattr(self, 'freeze_overlay') and self.freeze_overlay:
            self.freeze_overlay.destroy()
            self.freeze_overlay = None
        
        # Clean up any active color picker
        if hasattr(self, 'color_picker_window') and self.color_picker_window:
            self.color_picker_window.destroy()
            self.color_picker_window = None
        
        # Clear frozen screenshot
        self.frozen_screenshot = None
        self.frozen_photo = None
        self.screen_frozen = False
        self.freeze_button.configure(text="❄️ Freeze Screen")
        print("Screen unfrozen")
    
    def _pick_color(self, setting_key):
        """Opens color picker on the already frozen screen."""
        if not self.screen_frozen:
            print("Please freeze the screen first before picking colors")
            # Show messagebox to inform user
            try:
                from tkinter import messagebox
                messagebox.showwarning(
                    "Freeze Required",
                    "Please freeze the screen first before picking colors.\n\n"
                    "Click the '⚡ Freeze Screen' button, then try picking the color again."
                )
            except Exception as e:
                print(f"Error showing messagebox: {e}")
            return
            
        self.current_color_pick_setting = setting_key
        self._start_color_picker_on_frozen_screen()
    
    def _start_color_picker_on_frozen_screen(self):
        """Starts the color picker with zoom overlay on the already frozen screen."""
        import tkinter as tk
        from PIL import ImageTk, Image
        
        try:
            # Hide the freeze overlay temporarily to create picker overlay
            if hasattr(self, 'freeze_overlay') and self.freeze_overlay:
                self.freeze_overlay.withdraw()
            
            # Create color picker window using the frozen screenshot
            self.color_picker_window = tk.Toplevel()
            self.color_picker_window.title("Color Picker - Click to select color")
            self.color_picker_window.overrideredirect(True)
            self.color_picker_window.attributes('-topmost', False)  # Below GUI but above everything else
            
            # Get screen dimensions and position fullscreen
            screen_width = self.frozen_screenshot.width
            screen_height = self.frozen_screenshot.height
            self.color_picker_window.geometry(f"{screen_width}x{screen_height}+0+0")
            
            # Create canvas to display the frozen image
            self.picker_canvas = tk.Canvas(
                self.color_picker_window,
                width=screen_width,
                height=screen_height,
                highlightthickness=0,
                bg="black"
            )
            self.picker_canvas.pack(fill="both", expand=True)
            
            # Display the frozen screenshot
            self.picker_canvas.create_image(
                0, 0,
                image=self.frozen_photo,
                anchor="nw"
            )
            
            # Set up zoom parameters
            self.zoom_size = 150
            self.zoom_factor = 10
            
            # Initialize zoom elements
            self.zoom_window_id = None
            self.zoom_image_id = None
            self.zoom_crosshair_h = None
            self.zoom_crosshair_v = None
            self.zoom_text_id = None
            self.zoom_text_bg_id = None
            
            # Bind events
            self.picker_canvas.bind('<Button-1>', self._on_color_pick_click)
            self.picker_canvas.bind('<Motion>', self._on_color_pick_motion)
            self.color_picker_window.bind('<Escape>', self._cancel_color_picker_restore_freeze)
            self.color_picker_window.focus_set()
            
            # Set crosshair cursor
            self.picker_canvas.config(cursor="crosshair")
            
            print(f"Color picker started for {self.current_color_pick_setting}")
            
        except Exception as e:
            print(f"Error starting color picker: {e}")
            self._cancel_color_picker_restore_freeze()
    
    def _on_color_pick_motion(self, event):
        """Handle mouse motion to show zoom preview like 675.py."""
        if not self.frozen_screenshot:
            return
            
        try:
            from PIL import ImageTk, Image
            
            # Get mouse position
            canvas_x = event.x
            canvas_y = event.y
            
            # Ensure coordinates are within bounds
            img_width = self.frozen_screenshot.width
            img_height = self.frozen_screenshot.height
            
            img_x = max(0, min(canvas_x, img_width - 1))
            img_y = max(0, min(canvas_y, img_height - 1))
            
            # Create zoom area
            zoom_radius = self.zoom_size // (2 * self.zoom_factor)
            
            # Calculate crop area
            crop_left = max(0, img_x - zoom_radius)
            crop_top = max(0, img_y - zoom_radius)
            crop_right = min(img_width, img_x + zoom_radius)
            crop_bottom = min(img_height, img_y + zoom_radius)
            
            # Crop and zoom the image
            crop_box = (crop_left, crop_top, crop_right, crop_bottom)
            cropped = self.frozen_screenshot.crop(crop_box)
            
            # Resize to create zoom effect
            zoomed_width = (crop_right - crop_left) * self.zoom_factor
            zoomed_height = (crop_bottom - crop_top) * self.zoom_factor
            zoomed = cropped.resize((zoomed_width, zoomed_height), Image.NEAREST)
            
            # Position zoom window near cursor but avoid covering it
            zoom_x = canvas_x + 20
            zoom_y = canvas_y - self.zoom_size - 20
            
            # Keep zoom window on screen
            if zoom_x + self.zoom_size > img_width:
                zoom_x = canvas_x - self.zoom_size - 20
            if zoom_y < 0:
                zoom_y = canvas_y + 20
            
            # Delete previous zoom elements
            if self.zoom_window_id:
                self.picker_canvas.delete(self.zoom_window_id)
            if self.zoom_image_id:
                self.picker_canvas.delete(self.zoom_image_id)
            if self.zoom_crosshair_h:
                self.picker_canvas.delete(self.zoom_crosshair_h)
            if self.zoom_crosshair_v:
                self.picker_canvas.delete(self.zoom_crosshair_v)
            if self.zoom_text_id:
                self.picker_canvas.delete(self.zoom_text_id)
            if self.zoom_text_bg_id:
                self.picker_canvas.delete(self.zoom_text_bg_id)
            
            # Create zoom window border
            self.zoom_window_id = self.picker_canvas.create_rectangle(
                zoom_x - 2, zoom_y - 2,
                zoom_x + self.zoom_size + 2, zoom_y + self.zoom_size + 2,
                fill="white", outline="yellow", width=2
            )
            
            # Display zoomed image
            self.zoom_photo = ImageTk.PhotoImage(zoomed)
            self.zoom_image_id = self.picker_canvas.create_image(
                zoom_x, zoom_y,
                image=self.zoom_photo,
                anchor="nw"
            )
            
            # Add crosshair in center of zoom
            center_x = zoom_x + self.zoom_size // 2
            center_y = zoom_y + self.zoom_size // 2
            
            self.zoom_crosshair_h = self.picker_canvas.create_line(
                zoom_x, center_y, zoom_x + self.zoom_size, center_y,
                fill="red", width=1
            )
            self.zoom_crosshair_v = self.picker_canvas.create_line(
                center_x, zoom_y, center_x, zoom_y + self.zoom_size,
                fill="red", width=1
            )
            
            # Get color at cursor position and show hex value
            if 0 <= img_x < img_width and 0 <= img_y < img_height:
                r, g, b = self.frozen_screenshot.getpixel((img_x, img_y))
                hex_color = f"#{r:02x}{g:02x}{b:02x}"
                
                # Create background rectangle with strong contrast
                self.zoom_text_bg_id = self.picker_canvas.create_rectangle(
                    center_x - 40, zoom_y + self.zoom_size + 3,
                    center_x + 40, zoom_y + self.zoom_size + 27,
                    fill="black", outline="yellow", width=2
                )
                
                self.zoom_text_id = self.picker_canvas.create_text(
                    center_x, zoom_y + self.zoom_size + 15,
                    text=hex_color,
                    fill="white",
                    font=("Arial", 11, "bold"),
                    anchor="center"
                )
                
                # Store current color
                self.current_hover_color = hex_color
            
        except Exception as e:
            print(f"Error in zoom preview: {e}")
    
    def _on_color_pick_click(self, event):
        """Handle color selection when user clicks on the freeze frame."""
        if not hasattr(self, 'current_color_pick_setting') or not self.current_color_pick_setting:
            return
            
        try:
            # Get click position
            canvas_x = event.x
            canvas_y = event.y
            
            # Ensure coordinates are within image bounds
            img_width = self.frozen_screenshot.width
            img_height = self.frozen_screenshot.height
            
            img_x = max(0, min(canvas_x, img_width - 1))
            img_y = max(0, min(canvas_y, img_height - 1))
            
            # Get the color at the clicked position
            r, g, b = self.frozen_screenshot.getpixel((img_x, img_y))
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            
            # Update setting for current rod type
            self._set_rod_specific_setting(self.current_color_pick_setting, hex_color)
            
            # Update display using the centralized method
            self._update_color_display(self.current_color_pick_setting)
            
            print(f"Color selected: {hex_color} for {self.current_color_pick_setting}")
            
        except Exception as e:
            print(f"Error picking color: {e}")
            
        # End color picker and restore freeze overlay
        self._cancel_color_picker_restore_freeze()
    
    def _cancel_color_picker_restore_freeze(self, event=None):
        """Cancels color picking and restores the freeze overlay."""
        # Close color picker window
        if hasattr(self, 'color_picker_window') and self.color_picker_window:
            self.color_picker_window.destroy()
            self.color_picker_window = None
        
        # Restore freeze overlay if screen is still frozen
        if self.screen_frozen and hasattr(self, 'freeze_overlay') and self.freeze_overlay:
            self.freeze_overlay.deiconify()  # Show the freeze overlay again
        
        self.current_color_pick_setting = None
        print("Color picker closed - freeze overlay restored")
    
    def _set_color_none(self, setting_key):
        """Sets the color setting to None (disabled)."""
        self._set_rod_specific_setting(setting_key, "None")
        self._update_color_display(setting_key)
        current_rod = self.rod_type_var.get()
        print(f"Color set to None for {setting_key} on rod type {current_rod}")
    
    def _set_color_default(self, setting_key):
        """Sets the color setting to its default value (always uses the specified defaults)."""
        # Always use the specified default colors regardless of rod type
        default_colors = {
            "fish_target_line_color": "#434b5b",  # Dark gray-blue
            "fish_arrow_color": "#848587",        # Medium gray
            "fish_left_bar_color": "#f1f1f1",     # Light gray
            "fish_right_bar_color": "#ffffff"     # White
        }
        
        default_color = default_colors.get(setting_key, "#FFFFFF")
        self._set_rod_specific_setting(setting_key, default_color)
        self._update_color_display(setting_key)
        current_rod = self.rod_type_var.get()
        print(f"Color set to default ({default_color}) for {setting_key} on rod type {current_rod}")
    
    def _update_color_display(self, setting_key):
        """Updates the color display for a specific setting."""
        color_value = self._get_rod_specific_setting(setting_key)
        
        # Update button color and text
        button = getattr(self, f"{setting_key}_button", None)
        if button:
            try:
                if color_value == "None":
                    button.configure(
                        fg_color="#666666",
                        hover_color="#888888",
                        text="Pick Color"
                    )
                else:
                    button.configure(
                        fg_color=color_value,
                        hover_color=self._lighten_color(color_value),
                        text="Pick Color"
                    )
            except tk.TclError:
                # Widget no longer exists (e.g., switched to Line view)
                pass
        
        # Update entry text
        entry = getattr(self, f"{setting_key}_entry", None)
        if entry:
            try:
                entry.configure(state="normal")
                entry.delete(0, "end")
                entry.insert(0, str(color_value))
                entry.configure(state="readonly")
            except tk.TclError:
                # Widget no longer exists (e.g., switched to Line view)
                pass
    
    def _get_rod_specific_setting(self, base_key, default_value=None):
        """Get setting value for current rod type."""
        current_rod = self.rod_type_var.get()
        
        if current_rod == "Default":
            # Default rod uses original keys with specific defaults
            if default_value is None:
                default_value = self._get_default_value_for_key(base_key)
            return self.app.settings.get(base_key, default_value)
        else:
            # Other rods use rod-specific keys
            rod_specific_key = f"{base_key}_{current_rod}"
            if default_value is None:
                default_value = self._get_default_value_for_key(base_key)
            return self.app.settings.get(rod_specific_key, default_value)
    
    def _get_default_value_for_key(self, key):
        """Get the correct default value for a specific setting key."""
        if key == "fish_target_line_color":
            return "#434b5b"
        elif key == "fish_arrow_color":
            return "#848587"
        elif key == "fish_left_bar_color":
            return "#f1f1f1"
        elif key == "fish_right_bar_color":
            return "#ffffff"
        elif key == "fish_target_line_tolerance":
            return 0
        elif key == "fish_arrow_tolerance":
            return 3
        elif key == "fish_left_bar_tolerance":
            return 0
        elif key == "fish_right_bar_tolerance":
            return 0
        else:
            return "#FFFFFF"  # fallback for unknown keys
    
    def _set_rod_specific_setting(self, base_key, value):
        """Set setting value for current rod type."""
        current_rod = self.rod_type_var.get()
        
        if current_rod == "Default":
            # Default rod uses original keys
            self.app.settings[base_key] = value
        else:
            # Other rods use rod-specific keys
            rod_specific_key = f"{base_key}_{current_rod}"
            self.app.settings[rod_specific_key] = value
    
    def _update_all_displays_for_rod_type(self):
        """Update all color and tolerance displays when rod type changes."""
        # Update color displays
        color_keys = ["fish_target_line_color", "fish_arrow_color", "fish_left_bar_color", "fish_right_bar_color"]
        for key in color_keys:
            self._update_color_display(key)
        
        # Update tolerance displays
        tolerance_keys = ["fish_target_line_tolerance", "fish_arrow_tolerance", "fish_left_bar_tolerance", "fish_right_bar_tolerance"]
        for key in tolerance_keys:
            self._update_tolerance_display(key)
        
        # Update numeric settings (KP, KD, etc.) for current rod and mode
        selected_style = self.fish_track_style_var.get()
        
        if selected_style == "Color":
            # Update Color mode entry widgets (only KP and KD have entry widgets)
            self._update_numeric_setting_display("fish_kp", self.fish_kp_entry, 0.9)
            self._update_numeric_setting_display("fish_kd", self.fish_kd_entry, 0.2)
            
            # Update slider variables (they auto-update via trace callbacks)
            self.fish_scan_fps_var.set(self._get_rod_specific_setting("fish_scan_fps", 150))
            self.fish_lost_timeout_var.set(self._get_rod_specific_setting("fish_lost_timeout", 1))
            # bar_ratio_from_side slider doesn't store reference, will be loaded on next use
            
        elif selected_style == "Line":
            # Update Line mode entry widgets (only KP and KD have entry widgets)
            self._update_numeric_setting_display("fish_line_kp", self.fish_line_kp_entry, 0.9)
            self._update_numeric_setting_display("fish_line_kd", self.fish_line_kd_entry, 0.2)
            
            # Update slider variables (they auto-update via trace callbacks)
            self.fish_line_scan_fps_var.set(self._get_rod_specific_setting("fish_line_scan_fps", 150))
            self.fish_line_lost_timeout_var.set(self._get_rod_specific_setting("fish_line_lost_timeout", 1.0))
            self.fish_line_bar_ratio_var.set(self._get_rod_specific_setting("fish_line_bar_ratio", 0.6))
            self.fish_line_min_density_var.set(self._get_rod_specific_setting("fish_line_min_density", 0.8))
    
    def _update_numeric_setting_display(self, setting_key, entry_widget, default_value):
        """Update a numeric entry widget with rod-specific setting value."""
        if entry_widget and hasattr(entry_widget, 'get'):
            try:
                value = self._get_rod_specific_setting(setting_key, default_value)
                entry_widget.delete(0, "end")
                entry_widget.insert(0, str(value))
            except (tk.TclError, AttributeError):
                # Widget no longer exists or not accessible
                pass
    
    def _get_default_tolerance_for_key(self, tolerance_key):
        """Get the appropriate default tolerance value for a specific key."""
        if "target_line" in tolerance_key:
            return 0
        elif "arrow" in tolerance_key:
            return 3
        elif "left_bar" in tolerance_key:
            return 0
        elif "right_bar" in tolerance_key:
            return 0
        else:
            return 0  # fallback default
    
    def _update_tolerance_display(self, tolerance_key):
        """Update tolerance entry for current rod type."""
        default_tolerance = self._get_default_tolerance_for_key(tolerance_key)
        tolerance_value = self._get_rod_specific_setting(tolerance_key, default_tolerance)
        
        # Update entry
        entry = getattr(self, f"{tolerance_key}_entry", None)
        if entry:
            try:
                entry.delete(0, "end")
                entry.insert(0, str(tolerance_value))
            except tk.TclError:
                # Widget no longer exists (e.g., switched to Line view)
                pass
    
    def _on_tolerance_entry_change(self, tolerance_key, event):
        """Handle tolerance entry changes."""
        entry = event.widget
        try:
            value = int(entry.get())
            # Clamp value between 0 and 100
            value = max(0, min(100, value))
            
            # Update the entry if value was clamped
            if str(value) != entry.get():
                entry.delete(0, "end")
                entry.insert(0, str(value))
            
            # Save the tolerance value
            self._set_rod_specific_setting(tolerance_key, value)
            
            current_rod = self.rod_type_var.get()
            print(f"Tolerance updated for {current_rod}: {tolerance_key} = {value}")
            
        except ValueError:
            # Invalid input, revert to current saved value
            default_tolerance = self._get_default_tolerance_for_key(tolerance_key)
            current_value = self._get_rod_specific_setting(tolerance_key, default_tolerance)
            entry.delete(0, "end")
            entry.insert(0, str(current_value))
    
    def _update_tolerance(self, tolerance_key, value):
        """Updates tolerance setting and display (legacy method for compatibility)."""
        self._set_rod_specific_setting(tolerance_key, value)
        current_rod = self.rod_type_var.get()
        print(f"Tolerance updated for {current_rod}: {tolerance_key} = {value}")
    
    def _lighten_color(self, hex_color):
        """Lightens a hex color for hover effects."""
        try:
            # Remove # if present
            hex_color = hex_color.lstrip('#')
            
            # Convert to RGB
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            
            # Lighten by specified factor
            r = min(255, int(r * COLOR_LIGHTENING_FACTOR))
            g = min(255, int(g * COLOR_LIGHTENING_FACTOR))
            b = min(255, int(b * COLOR_LIGHTENING_FACTOR))
            
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception as e:
            print(f"⚠️ Color conversion error: {e}")
            return "#FFFFFF"  # Default to white if error
    
    def _on_destroy(self, event):
        """Cleanup when the view is destroyed."""
        if self.screen_frozen:
            self._unfreeze_screen()
    
    def _on_fish_setting_slider_change(self, setting_key, value, entry, step):
        """Handle fish setting slider changes."""
        try:
            if step == 0.1:  # Decimal setting
                formatted_value = round(float(value), 1)
                entry.delete(0, "end")
                entry.insert(0, f"{formatted_value:.1f}")
            else:  # Integer setting
                formatted_value = int(round(float(value)))
                entry.delete(0, "end")
                entry.insert(0, str(formatted_value))
            
            # Save the setting value
            self._set_rod_specific_setting(setting_key, formatted_value)
            
            current_rod = self.rod_type_var.get()
            print(f"Fish setting updated for {current_rod}: {setting_key} = {formatted_value}")
            
        except (ValueError, TypeError) as e:
            print(f"Error updating fish setting {setting_key}: {e}")
    
    def _on_color_control_mode_change(self, mode):
        """Handle Color mode control mode changes."""
        self._set_rod_specific_setting("fish_control_mode", mode)
        
        # Update KP/KD values based on mode
        if mode == "Normal":
            self._set_rod_specific_setting("fish_kp", 0.9)
            self._set_rod_specific_setting("fish_kd", 0.3)
            self.fish_kp_entry.delete(0, "end")
            self.fish_kp_entry.insert(0, "0.9")
            self.fish_kd_entry.delete(0, "end")
            self.fish_kd_entry.insert(0, "0.3")
        elif mode == "Steady":
            self._set_rod_specific_setting("fish_kp", 0.7)
            self._set_rod_specific_setting("fish_kd", 0.4)
            self.fish_kp_entry.delete(0, "end")
            self.fish_kp_entry.insert(0, "0.7")
            self.fish_kd_entry.delete(0, "end")
            self.fish_kd_entry.insert(0, "0.4")
        # NigGamble mode keeps current values (uses different algorithm)
        

    
    def _on_line_control_mode_change(self, mode):
        """Handle Line mode control mode changes."""
        self._set_rod_specific_setting("fish_line_control_mode", mode)
        
        # Update KP/KD values based on mode
        if mode == "Normal":
            self._set_rod_specific_setting("fish_line_kp", 0.9)
            self._set_rod_specific_setting("fish_line_kd", 0.3)
            self.fish_line_kp_entry.delete(0, "end")
            self.fish_line_kp_entry.insert(0, "0.9")
            self.fish_line_kd_entry.delete(0, "end")
            self.fish_line_kd_entry.insert(0, "0.3")
        elif mode == "Steady":
            self._set_rod_specific_setting("fish_line_kp", 0.7)
            self._set_rod_specific_setting("fish_line_kd", 0.4)
            self.fish_line_kp_entry.delete(0, "end")
            self.fish_line_kp_entry.insert(0, "0.7")
            self.fish_line_kd_entry.delete(0, "end")
            self.fish_line_kd_entry.insert(0, "0.4")
        # NigGamble mode keeps current values (uses different algorithm)
        

    
    def _on_fish_numeric_entry_change(self, setting_key, event):
        """Handle numeric entry changes for KP and KD - allows decimals, no range limits."""
        entry = event.widget
        try:
            value = float(entry.get())
            # No range limits - use whatever value the user inputs
            
            # Save the setting value as-is
            self._set_rod_specific_setting(setting_key, value)
            
            current_rod = self.rod_type_var.get()
            print(f"Fish setting updated for {current_rod}: {setting_key} = {value}")
            
        except (ValueError, TypeError):
            # Invalid input, revert to current saved value
            default_val = 3.0 if setting_key == "fish_kp" else 1.0  # Default values
            current_value = self._get_rod_specific_setting(setting_key, default_val)
            entry.delete(0, "end")
            entry.insert(0, str(current_value))
    
    def _on_fish_pd_clamp_entry_change(self, event):
        """Handle PD Clamp entry changes - allows decimals, no range limits."""
        entry = event.widget
        try:
            value = float(entry.get())
            # No range limits - use whatever value the user inputs
            
            # Save the setting value as-is
            self._set_rod_specific_setting("fish_pd_clamp", value)
            
            current_rod = self.rod_type_var.get()
            print(f"Fish setting updated for {current_rod}: fish_pd_clamp = {value}")
            
        except (ValueError, TypeError):
            # Invalid input, revert to current saved value
            current_value = self._get_rod_specific_setting("fish_pd_clamp", 10.0)
            entry.delete(0, "end")
            entry.insert(0, str(current_value))


class ShakeView(ctk.CTkFrame):  # AI_TARGET: SHAKE_GUI
    """
    A view (CTkFrame) to contain the Shake settings. Uses a standard tk.Canvas
    to create custom, scrollable content with purple theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = master  # Reference to StarryNightApp to access settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#BD10E0", # Match the purple background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#D147FF"   # Lighter purple border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="📳 Shake Settings", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n") 
        
        # Shake Style Selection Section with modern card design
        self.shake_style_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.shake_style_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.shake_style_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the shake style section
        subtitle_label = ctk.CTkLabel(
            self.shake_style_card, 
            text="⚙️ Shake Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Shake Style dropdown
        shake_style_label = ctk.CTkLabel(
            self.shake_style_card, 
            text="🎯 Shake Style:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        shake_style_label.grid(row=1, column=0, padx=(30, 15), pady=12, sticky="ew")

        self.shake_style_var = tk.StringVar(value=self.app.settings["shake_style"])
        self.shake_style_var.trace_add("write", lambda *args: self.app.settings.update({"shake_style": self.shake_style_var.get()}))
        shake_style_dropdown = ctk.CTkOptionMenu(
            self.shake_style_card,
            values=["Pixel", "Navigation", "Circle"],
            variable=self.shake_style_var,
            command=self._on_shake_style_change,
            fg_color="#BD10E0",      # Purple theme
            button_color="#A50ECC",   # Darker purple for button
            button_hover_color="#D147FF",  # Lighter purple on hover
            dropdown_fg_color="#383838",  # Match container
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        shake_style_dropdown.grid(row=1, column=1, padx=(15, 30), pady=12, sticky="ew")
        
        # Dynamic options container
        self.options_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.options_card.grid(row=2, column=0, sticky="ew", pady=(0, 25), padx=30)
        self.options_card.grid_columnconfigure(0, weight=1)
        
        # Options title (will update based on selection)
        self.options_title = ctk.CTkLabel(
            self.options_card, 
            text="⚙️ Pixel Options", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        self.options_title.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Placeholder for options content
        self.options_content_frame = ctk.CTkFrame(self.options_card, fg_color="transparent")
        self.options_content_frame.grid(row=1, column=0, padx=30, pady=(0, 15), sticky="ew")
        self.options_content_frame.grid_columnconfigure(0, weight=1)
        
        # Initialize with Pixel options
        self._update_options_display()

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _on_shake_style_change(self, selected_style):
        """Called when shake style dropdown selection changes."""

        self._update_options_display()
    
    def _update_options_display(self):
        """Updates the options display based on selected shake style."""
        # Clear existing options content
        for widget in self.options_content_frame.winfo_children():
            widget.destroy()
        
        selected_style = self.shake_style_var.get()
        
        # Update title and content based on selection
        if selected_style == "Pixel":
            self.options_title.configure(text="⚙️ Pixel Options")
            
            # Click Count
            click_count_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            click_count_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
            click_count_frame.grid_columnconfigure(1, weight=1)
            
            click_count_label = ctk.CTkLabel(
                click_count_frame,
                text="🖱️ Click Count:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            click_count_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.click_count_var = tk.IntVar(value=self.app.settings["shake_click_count"])
            self.click_count_var.trace_add("write", lambda *_: self.app.settings.update({"shake_click_count": self.click_count_var.get()}))
            click_count_slider = ctk.CTkSlider(
                click_count_frame,
                from_=1,
                to=2,
                number_of_steps=1,
                variable=self.click_count_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            click_count_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            click_count_value = ctk.CTkLabel(
                click_count_frame,
                text="1",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            click_count_value.grid(row=0, column=2, sticky="e")

            click_count_slider.configure(command=lambda value: click_count_value.configure(text=str(int(value))))
            click_count_value.configure(text=str(self.click_count_var.get()))  # Initialize display
            
            # Color Tolerance
            color_tolerance_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            color_tolerance_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
            color_tolerance_frame.grid_columnconfigure(1, weight=1)
            
            color_tolerance_label = ctk.CTkLabel(
                color_tolerance_frame,
                text="🌈 Color Tolerance:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            color_tolerance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.color_tolerance_var = tk.IntVar(value=self.app.settings["shake_color_tolerance"])
            self.color_tolerance_var.trace_add("write", lambda *_: self.app.settings.update({"shake_color_tolerance": self.color_tolerance_var.get()}))
            color_tolerance_slider = ctk.CTkSlider(
                color_tolerance_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.color_tolerance_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            color_tolerance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            color_tolerance_value = ctk.CTkLabel(
                color_tolerance_frame,
                text="0",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            color_tolerance_value.grid(row=0, column=2, sticky="e")

            color_tolerance_slider.configure(command=lambda value: color_tolerance_value.configure(text=str(int(value))))
            color_tolerance_value.configure(text=str(self.color_tolerance_var.get()))  # Initialize display

            # Pixel Distance Tolerance
            pixel_distance_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            pixel_distance_frame.grid(row=2, column=0, pady=(0, 10), sticky="ew")
            pixel_distance_frame.grid_columnconfigure(1, weight=1)

            pixel_distance_label = ctk.CTkLabel(
                pixel_distance_frame,
                text="📏 Pixel Distance Tolerance:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            pixel_distance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.pixel_distance_var = tk.IntVar(value=self.app.settings["shake_pixel_distance_tolerance"])
            self.pixel_distance_var.trace_add("write", lambda *_: self.app.settings.update({"shake_pixel_distance_tolerance": self.pixel_distance_var.get()}))
            pixel_distance_slider = ctk.CTkSlider(
                pixel_distance_frame,
                from_=0,
                to=100,
                number_of_steps=100,
                variable=self.pixel_distance_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            pixel_distance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

            pixel_distance_value = ctk.CTkLabel(
                pixel_distance_frame,
                text="10",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            pixel_distance_value.grid(row=0, column=2, sticky="e")

            pixel_distance_slider.configure(command=lambda value: pixel_distance_value.configure(text=str(int(value))))
            pixel_distance_value.configure(text=str(self.pixel_distance_var.get()))  # Initialize display

            # Scan FPS with MS display
            scan_fps_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            scan_fps_frame.grid(row=3, column=0, pady=(0, 10), sticky="ew")
            scan_fps_frame.grid_columnconfigure(1, weight=1)
            
            scan_fps_label = ctk.CTkLabel(
                scan_fps_frame,
                text="📊 Scan Fps:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            scan_fps_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.scan_fps_var = tk.IntVar(value=self.app.settings["shake_scan_fps"])
            self.scan_fps_var.trace_add("write", lambda *_: self.app.settings.update({"shake_scan_fps": self.scan_fps_var.get()}))
            scan_fps_slider = ctk.CTkSlider(
                scan_fps_frame,
                from_=10,
                to=1000,
                number_of_steps=99,  # (1000-10)/10 = 99 steps
                variable=self.scan_fps_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            scan_fps_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            def update_fps_display(value):
                fps = int(value)
                if fps >= 1000:
                    ms_text = "(no ms delay)"
                else:
                    ms = round(1000 / fps, 1)
                    if ms == int(ms):
                        ms_text = f"({int(ms)}ms)"
                    else:
                        ms_text = f"({ms}ms)"
                scan_fps_value.configure(text=f"{fps} {ms_text}")
            
            scan_fps_value = ctk.CTkLabel(
                scan_fps_frame,
                text="200 (5ms)",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=100
            )
            scan_fps_value.grid(row=0, column=2, sticky="e")

            scan_fps_slider.configure(command=update_fps_display)
            update_fps_display(self.scan_fps_var.get())  # Initialize display with current value
            
            # Duplicate Circle Timeout
            duplicate_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            duplicate_timeout_frame.grid(row=4, column=0, pady=(0, 10), sticky="ew")
            duplicate_timeout_frame.grid_columnconfigure(1, weight=1)

            duplicate_timeout_label = ctk.CTkLabel(
                duplicate_timeout_frame,
                text="⏱️ Duplicate Circle Timeout:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            duplicate_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.duplicate_timeout_var = tk.IntVar(value=self.app.settings["shake_duplicate_timeout"])
            self.duplicate_timeout_var.trace_add("write", lambda *_: self.app.settings.update({"shake_duplicate_timeout": self.duplicate_timeout_var.get()}))
            duplicate_timeout_slider = ctk.CTkSlider(
                duplicate_timeout_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.duplicate_timeout_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            duplicate_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

            duplicate_timeout_value = ctk.CTkLabel(
                duplicate_timeout_frame,
                text="1s",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            duplicate_timeout_value.grid(row=0, column=2, sticky="e")

            duplicate_timeout_slider.configure(command=lambda value: duplicate_timeout_value.configure(text=f"{int(value)}s"))
            duplicate_timeout_value.configure(text=f"{self.duplicate_timeout_var.get()}s")  # Initialize display

            # Fail Cast Timeout
            fail_cast_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            fail_cast_timeout_frame.grid(row=5, column=0, pady=(0, 10), sticky="ew")
            fail_cast_timeout_frame.grid_columnconfigure(1, weight=1)
            
            fail_cast_timeout_label = ctk.CTkLabel(
                fail_cast_timeout_frame,
                text="⏱️ Fail Cast Timeout:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            fail_cast_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            self.fail_cast_timeout_var = tk.IntVar(value=self.app.settings["shake_fail_cast_timeout"])
            self.fail_cast_timeout_var.trace_add("write", lambda *_: self.app.settings.update({"shake_fail_cast_timeout": self.fail_cast_timeout_var.get()}))
            fail_cast_timeout_slider = ctk.CTkSlider(
                fail_cast_timeout_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.fail_cast_timeout_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            fail_cast_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            fail_cast_timeout_value = ctk.CTkLabel(
                fail_cast_timeout_frame,
                text="3s",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            fail_cast_timeout_value.grid(row=0, column=2, sticky="e")

            fail_cast_timeout_slider.configure(command=lambda value: fail_cast_timeout_value.configure(text=f"{int(value)}s"))
            fail_cast_timeout_value.configure(text=f"{self.fail_cast_timeout_var.get()}s")  # Initialize display
            
        elif selected_style == "Navigation":
            self.options_title.configure(text="⚙️ Navigation Options")
            
            # Navigation Key
            nav_key_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            nav_key_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
            nav_key_frame.grid_columnconfigure(1, weight=1)
            
            nav_key_label = ctk.CTkLabel(
                nav_key_frame,
                text="⌨️ Navigation Key:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            nav_key_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.nav_key_var = tk.StringVar(value=self.app.settings["nav_key"])
            self.nav_key_var.trace_add("write", lambda *_: self.app.settings.update({"nav_key": self.nav_key_var.get()}))
            nav_key_entry = ctk.CTkEntry(
                nav_key_frame,
                textvariable=self.nav_key_var,
                font=ctk.CTkFont(size=14),
                width=50,
                height=32,
                fg_color="#383838",
                border_color="#BD10E0",
                text_color="#F0F0F0",
                placeholder_text="Key"
            )
            nav_key_entry.grid(row=0, column=1, padx=(0, 10), sticky="w")
            
            # Bind key validation to only allow single characters
            def validate_nav_key(event=None):
                current_text = self.nav_key_var.get()
                if len(current_text) > 1:
                    self.nav_key_var.set(current_text[-1])  # Keep only the last character
                return True
            
            # Bind focus out event to remove highlight when clicking elsewhere
            def on_nav_key_focus_out(event=None):
                nav_key_entry.configure(border_color="#BD10E0")  # Reset to normal border color
                return True
            
            def on_nav_key_focus_in(event=None):
                nav_key_entry.configure(border_color="#E040FB")  # Highlight border when focused
                return True
            
            nav_key_entry.bind('<KeyRelease>', validate_nav_key)
            nav_key_entry.bind('<FocusOut>', on_nav_key_focus_out)
            nav_key_entry.bind('<FocusIn>', on_nav_key_focus_in)
            
            # Bind click events on the parent frame to remove focus from entry
            def remove_nav_key_focus(event=None):
                nav_key_frame.focus_set()  # Set focus to the parent frame
                return True
            
            nav_key_frame.bind('<Button-1>', remove_nav_key_focus)
            
            # Color Tolerance
            nav_color_tolerance_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            nav_color_tolerance_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
            nav_color_tolerance_frame.grid_columnconfigure(1, weight=1)
            
            nav_color_tolerance_label = ctk.CTkLabel(
                nav_color_tolerance_frame,
                text="🌈 Color Tolerance:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            nav_color_tolerance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.nav_color_tolerance_var = tk.IntVar(value=self.app.settings["nav_color_tolerance"])
            self.nav_color_tolerance_var.trace_add("write", lambda *_: self.app.settings.update({"nav_color_tolerance": self.nav_color_tolerance_var.get()}))
            nav_color_tolerance_slider = ctk.CTkSlider(
                nav_color_tolerance_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.nav_color_tolerance_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            nav_color_tolerance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            nav_color_tolerance_value = ctk.CTkLabel(
                nav_color_tolerance_frame,
                text="0",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            nav_color_tolerance_value.grid(row=0, column=2, sticky="e")

            nav_color_tolerance_slider.configure(command=lambda value: nav_color_tolerance_value.configure(text=str(int(value))))
            nav_color_tolerance_value.configure(text=str(self.nav_color_tolerance_var.get()))  # Initialize display
            
            # Scan FPS with MS display (same as pixel mode)
            nav_scan_fps_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            nav_scan_fps_frame.grid(row=2, column=0, pady=(0, 10), sticky="ew")
            nav_scan_fps_frame.grid_columnconfigure(1, weight=1)
            
            nav_scan_fps_label = ctk.CTkLabel(
                nav_scan_fps_frame,
                text="📊 Scan Fps:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            nav_scan_fps_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.nav_scan_fps_var = tk.IntVar(value=self.app.settings["nav_scan_fps"])
            self.nav_scan_fps_var.trace_add("write", lambda *_: self.app.settings.update({"nav_scan_fps": self.nav_scan_fps_var.get()}))
            nav_scan_fps_slider = ctk.CTkSlider(
                nav_scan_fps_frame,
                from_=10,
                to=1000,
                number_of_steps=99,  # (1000-10)/10 = 99 steps
                variable=self.nav_scan_fps_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            nav_scan_fps_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            def update_nav_fps_display(value):
                fps = int(value)
                if fps >= 1000:
                    ms_text = "(no ms delay)"
                else:
                    ms = round(1000 / fps, 1)
                    if ms == int(ms):
                        ms_text = f"({int(ms)}ms)"
                    else:
                        ms_text = f"({ms}ms)"
                nav_scan_fps_value.configure(text=f"{fps} {ms_text}")
            
            nav_scan_fps_value = ctk.CTkLabel(
                nav_scan_fps_frame,
                text="200 (5ms)",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=100
            )
            nav_scan_fps_value.grid(row=0, column=2, sticky="e")

            nav_scan_fps_slider.configure(command=update_nav_fps_display)
            update_nav_fps_display(self.nav_scan_fps_var.get())  # Initialize display with current value
            
            # Fail Cast Timeout
            nav_fail_cast_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            nav_fail_cast_timeout_frame.grid(row=3, column=0, pady=(0, 10), sticky="ew")
            nav_fail_cast_timeout_frame.grid_columnconfigure(1, weight=1)
            
            nav_fail_cast_timeout_label = ctk.CTkLabel(
                nav_fail_cast_timeout_frame,
                text="⏱️ Fail Cast Timeout:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            nav_fail_cast_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.nav_fail_cast_timeout_var = tk.IntVar(value=self.app.settings["nav_fail_cast_timeout"])
            self.nav_fail_cast_timeout_var.trace_add("write", lambda *_: self.app.settings.update({"nav_fail_cast_timeout": self.nav_fail_cast_timeout_var.get()}))
            nav_fail_cast_timeout_slider = ctk.CTkSlider(
                nav_fail_cast_timeout_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.nav_fail_cast_timeout_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            nav_fail_cast_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            nav_fail_cast_timeout_value = ctk.CTkLabel(
                nav_fail_cast_timeout_frame,
                text="3s",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            nav_fail_cast_timeout_value.grid(row=0, column=2, sticky="e")

            nav_fail_cast_timeout_slider.configure(command=lambda value: nav_fail_cast_timeout_value.configure(text=f"{int(value)}s"))
            nav_fail_cast_timeout_value.configure(text=f"{self.nav_fail_cast_timeout_var.get()}s")  # Initialize display
            
        elif selected_style == "Circle":
            self.options_title.configure(text="⚙️ Circle Options")
            
            # Click Count
            circle_click_count_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            circle_click_count_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
            circle_click_count_frame.grid_columnconfigure(1, weight=1)
            
            circle_click_count_label = ctk.CTkLabel(
                circle_click_count_frame,
                text="🖱️ Click Count:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            circle_click_count_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.circle_click_count_var = tk.IntVar(value=self.app.settings["circle_click_count"])
            self.circle_click_count_var.trace_add("write", lambda *_: self.app.settings.update({"circle_click_count": self.circle_click_count_var.get()}))
            circle_click_count_slider = ctk.CTkSlider(
                circle_click_count_frame,
                from_=1,
                to=2,
                number_of_steps=1,
                variable=self.circle_click_count_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            circle_click_count_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            circle_click_count_value = ctk.CTkLabel(
                circle_click_count_frame,
                text="1",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            circle_click_count_value.grid(row=0, column=2, sticky="e")

            circle_click_count_slider.configure(command=lambda value: circle_click_count_value.configure(text=str(int(value))))
            circle_click_count_value.configure(text=str(self.circle_click_count_var.get()))  # Initialize display
            
            # Pixel Distance Tolerance
            circle_pixel_distance_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            circle_pixel_distance_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
            circle_pixel_distance_frame.grid_columnconfigure(1, weight=1)

            circle_pixel_distance_label = ctk.CTkLabel(
                circle_pixel_distance_frame,
                text="📏 Pixel Distance Tolerance:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            circle_pixel_distance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.circle_pixel_distance_var = tk.IntVar(value=self.app.settings["circle_pixel_distance_tolerance"])
            self.circle_pixel_distance_var.trace_add("write", lambda *_: self.app.settings.update({"circle_pixel_distance_tolerance": self.circle_pixel_distance_var.get()}))
            circle_pixel_distance_slider = ctk.CTkSlider(
                circle_pixel_distance_frame,
                from_=0,
                to=100,
                number_of_steps=100,
                variable=self.circle_pixel_distance_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            circle_pixel_distance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")

            circle_pixel_distance_value = ctk.CTkLabel(
                circle_pixel_distance_frame,
                text="10",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            circle_pixel_distance_value.grid(row=0, column=2, sticky="e")

            circle_pixel_distance_slider.configure(command=lambda value: circle_pixel_distance_value.configure(text=str(int(value))))
            circle_pixel_distance_value.configure(text=str(self.circle_pixel_distance_var.get()))  # Initialize display
            
            # Scan FPS with MS display (same as other modes)
            circle_scan_fps_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            circle_scan_fps_frame.grid(row=2, column=0, pady=(0, 10), sticky="ew")
            circle_scan_fps_frame.grid_columnconfigure(1, weight=1)
            
            circle_scan_fps_label = ctk.CTkLabel(
                circle_scan_fps_frame,
                text="📊 Scan Fps:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            circle_scan_fps_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.circle_scan_fps_var = tk.IntVar(value=self.app.settings["circle_scan_fps"])
            self.circle_scan_fps_var.trace_add("write", lambda *_: self.app.settings.update({"circle_scan_fps": self.circle_scan_fps_var.get()}))
            circle_scan_fps_slider = ctk.CTkSlider(
                circle_scan_fps_frame,
                from_=10,
                to=1000,
                number_of_steps=99,  # (1000-10)/10 = 99 steps
                variable=self.circle_scan_fps_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            circle_scan_fps_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            def update_circle_fps_display(value):
                fps = int(value)
                if fps >= 1000:
                    ms_text = "(no ms delay)"
                else:
                    ms = round(1000 / fps, 1)
                    if ms == int(ms):
                        ms_text = f"({int(ms)}ms)"
                    else:
                        ms_text = f"({ms}ms)"
                circle_scan_fps_value.configure(text=f"{fps} {ms_text}")
            
            circle_scan_fps_value = ctk.CTkLabel(
                circle_scan_fps_frame,
                text="200 (5ms)",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=100
            )
            circle_scan_fps_value.grid(row=0, column=2, sticky="e")

            circle_scan_fps_slider.configure(command=update_circle_fps_display)
            update_circle_fps_display(self.circle_scan_fps_var.get())  # Initialize display with current value
            
            # Duplicate Circle Timeout
            circle_duplicate_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            circle_duplicate_timeout_frame.grid(row=3, column=0, pady=(0, 10), sticky="ew")
            circle_duplicate_timeout_frame.grid_columnconfigure(1, weight=1)
            
            circle_duplicate_timeout_label = ctk.CTkLabel(
                circle_duplicate_timeout_frame,
                text="⏱️ Duplicate Circle Timeout:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            circle_duplicate_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.circle_duplicate_timeout_var = tk.IntVar(value=self.app.settings["circle_duplicate_timeout"])
            self.circle_duplicate_timeout_var.trace_add("write", lambda *_: self.app.settings.update({"circle_duplicate_timeout": self.circle_duplicate_timeout_var.get()}))
            circle_duplicate_timeout_slider = ctk.CTkSlider(
                circle_duplicate_timeout_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.circle_duplicate_timeout_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            circle_duplicate_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            circle_duplicate_timeout_value = ctk.CTkLabel(
                circle_duplicate_timeout_frame,
                text="1s",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            circle_duplicate_timeout_value.grid(row=0, column=2, sticky="e")

            circle_duplicate_timeout_slider.configure(command=lambda value: circle_duplicate_timeout_value.configure(text=f"{int(value)}s"))
            circle_duplicate_timeout_value.configure(text=f"{self.circle_duplicate_timeout_var.get()}s")  # Initialize display
            
            # Fail Cast Timeout
            circle_fail_cast_timeout_frame = ctk.CTkFrame(self.options_content_frame, fg_color="transparent")
            circle_fail_cast_timeout_frame.grid(row=4, column=0, pady=(0, 10), sticky="ew")
            circle_fail_cast_timeout_frame.grid_columnconfigure(1, weight=1)
            
            circle_fail_cast_timeout_label = ctk.CTkLabel(
                circle_fail_cast_timeout_frame,
                text="⏱️ Fail Cast Timeout:",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0"
            )
            circle_fail_cast_timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            self.circle_fail_cast_timeout_var = tk.IntVar(value=self.app.settings["circle_fail_cast_timeout"])
            self.circle_fail_cast_timeout_var.trace_add("write", lambda *_: self.app.settings.update({"circle_fail_cast_timeout": self.circle_fail_cast_timeout_var.get()}))
            circle_fail_cast_timeout_slider = ctk.CTkSlider(
                circle_fail_cast_timeout_frame,
                from_=0,
                to=10,
                number_of_steps=10,
                variable=self.circle_fail_cast_timeout_var,
                progress_color="#BD10E0",
                button_color="#E040FB",
                button_hover_color="#F060FF"
            )
            circle_fail_cast_timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            circle_fail_cast_timeout_value = ctk.CTkLabel(
                circle_fail_cast_timeout_frame,
                text="3s",
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#E040FB",
                width=30
            )
            circle_fail_cast_timeout_value.grid(row=0, column=2, sticky="e")

            circle_fail_cast_timeout_slider.configure(command=lambda value: circle_fail_cast_timeout_value.configure(text=f"{int(value)}s"))
            circle_fail_cast_timeout_value.configure(text=f"{self.circle_fail_cast_timeout_var.get()}s")  # Initialize display

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")


class CastView(ctk.CTkFrame):  # AI_TARGET: CAST_GUI
    """
    A view (CTkFrame) to contain the Cast settings. Uses a standard tk.Canvas
    to create custom, scrollable content with orange theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = master  # Reference to StarryNightApp to access settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#F5A623", # Match the orange background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#FFBD47"   # Lighter orange border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="🎣 Cast Settings", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n") 
        
        # Cast Style Selection Section with modern card design
        self.cast_style_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.cast_style_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.cast_style_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the cast style section
        subtitle_label = ctk.CTkLabel(
            self.cast_style_card, 
            text="⚙️ Cast Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Cast Style dropdown
        cast_style_label = ctk.CTkLabel(
            self.cast_style_card, 
            text="🎯 Cast Style:", 
            anchor="w", 
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F0F0F0"
        )
        cast_style_label.grid(row=1, column=0, padx=(30, 15), pady=12, sticky="ew")

        self.cast_style_var = tk.StringVar(value=self.app.settings.get("cast_mode", "Normal"))
        cast_style_dropdown = ctk.CTkOptionMenu(
            self.cast_style_card, 
            values=["Normal", "Perfect"],
            variable=self.cast_style_var,
            command=self._on_cast_style_change,
            fg_color="#F5A623",      # Orange theme
            button_color="#E0941F",   # Darker orange for button
            button_hover_color="#FFBD47",  # Lighter orange on hover
            dropdown_fg_color="#383838",  # Match container
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10
        )
        cast_style_dropdown.grid(row=1, column=1, padx=(15, 30), pady=12, sticky="ew")
        
        # Dynamic options container
        self.options_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.options_card.grid(row=2, column=0, sticky="ew", pady=(0, 25), padx=30)
        self.options_card.grid_columnconfigure(0, weight=1)
        
        # Options title (will update based on selection)
        self.options_title = ctk.CTkLabel(
            self.options_card, 
            text="🔧 Normal Options", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        self.options_title.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Placeholder for options content
        self.options_content_frame = ctk.CTkFrame(self.options_card, fg_color="transparent")
        self.options_content_frame.grid(row=1, column=0, padx=30, pady=(0, 15), sticky="ew")
        self.options_content_frame.grid_columnconfigure(0, weight=1)
        
        # Initialize with Normal options
        self._update_options_display()

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _on_cast_style_change(self, selected_style):
        """Called when cast style dropdown selection changes."""

        # Save to centralized settings
        self.app.settings["cast_mode"] = selected_style
        self._update_options_display()
    
    def _update_options_display(self):
        """Updates the options display based on selected cast style."""
        # Clear existing options content
        for widget in self.options_content_frame.winfo_children():
            widget.destroy()
        
        selected_style = self.cast_style_var.get()
        
        # Update title
        if selected_style == "Normal":
            self.options_title.configure(text="🔧 Normal Options")
            
            # Create flowchart frame
            flowchart_frame = ctk.CTkFrame(
                self.options_content_frame,
                fg_color="#4A4A4A",
                corner_radius=10,
                border_width=1,
                border_color="#6A6A6A"
            )
            flowchart_frame.grid(row=0, column=0, pady=10, padx=10, sticky="ew")
            flowchart_frame.grid_columnconfigure(1, weight=1)
            
            # Flowchart title
            flowchart_title = ctk.CTkLabel(
                flowchart_frame,
                text="📋 Cast Sequence",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#E0E0E0"
            )
            flowchart_title.grid(row=0, column=0, columnspan=3, pady=(15, 10), sticky="n")
            
            # Initialize delay variables if they don't exist
            if not hasattr(self, 'delay1_var'):
                self.delay1_var = tk.DoubleVar(value=self.app.settings["cast_delay1"])
                self.delay1_var.trace_add("write", lambda *args: self.app.settings.update({"cast_delay1": self.delay1_var.get()}))
            if not hasattr(self, 'delay2_var'):
                self.delay2_var = tk.DoubleVar(value=self.app.settings["cast_delay2"])
                self.delay2_var.trace_add("write", lambda *args: self.app.settings.update({"cast_delay2": self.delay2_var.get()}))
            if not hasattr(self, 'delay3_var'):
                self.delay3_var = tk.DoubleVar(value=self.app.settings["cast_delay3"])
                self.delay3_var.trace_add("write", lambda *args: self.app.settings.update({"cast_delay3": self.delay3_var.get()}))
            
            # Step 1: Delay
            step1_frame = self._create_flowchart_step(
                flowchart_frame, 1, "⏱️", "Delay", self.delay1_var, "#F5A623"
            )
            
            # Arrow 1
            arrow1 = self._create_flowchart_arrow(flowchart_frame, 2)
            
            # Step 2: Hold Left Click
            step2_frame = self._create_flowchart_click_step(
                flowchart_frame, 3, "🖱️", "Hold Left Click", "#4CAF50"
            )
            
            # Arrow 2
            arrow2 = self._create_flowchart_arrow(flowchart_frame, 4)
            
            # Step 3: Delay
            step3_frame = self._create_flowchart_step(
                flowchart_frame, 5, "⏱️", "Delay", self.delay2_var, "#F5A623"
            )
            
            # Arrow 3
            arrow3 = self._create_flowchart_arrow(flowchart_frame, 6)
            
            # Step 4: Release Left Click
            step4_frame = self._create_flowchart_click_step(
                flowchart_frame, 7, "🖱️", "Release Left Click", "#FF6B6B"
            )
            
            # Arrow 4
            arrow4 = self._create_flowchart_arrow(flowchart_frame, 8)
            
            # Step 5: Delay
            step5_frame = self._create_flowchart_step(
                flowchart_frame, 9, "⏱️", "Delay", self.delay3_var, "#F5A623"
            )
            
        elif selected_style == "Perfect":
            self.options_title.configure(text="✨ Perfect Options")
            
            # Create flowchart frame
            flowchart_frame = ctk.CTkFrame(
                self.options_content_frame,
                fg_color="#4A4A4A",
                corner_radius=10,
                border_width=1,
                border_color="#6A6A6A"
            )
            flowchart_frame.grid(row=0, column=0, pady=10, padx=10, sticky="ew")
            flowchart_frame.grid_columnconfigure(1, weight=1)
            
            # Flowchart title
            flowchart_title = ctk.CTkLabel(
                flowchart_frame,
                text="📋 Perfect Cast Sequence",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#E0E0E0"
            )
            flowchart_title.grid(row=0, column=0, columnspan=3, pady=(15, 10), sticky="n")
            
            # Initialize perfect cast variables with settings connection
            if not hasattr(self, 'perfect_delay1_var'):
                self.perfect_delay1_var = tk.DoubleVar(value=self.app.settings["perfect_delay1"])
                self.perfect_delay1_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay1": self.perfect_delay1_var.get()}))
            if not hasattr(self, 'perfect_delay2_var'):
                self.perfect_delay2_var = tk.DoubleVar(value=self.app.settings["perfect_delay2"])
                self.perfect_delay2_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay2": self.perfect_delay2_var.get()}))
            if not hasattr(self, 'perfect_delay3_var'):
                self.perfect_delay3_var = tk.DoubleVar(value=self.app.settings["perfect_delay3"])
                self.perfect_delay3_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay3": self.perfect_delay3_var.get()}))
            if not hasattr(self, 'perfect_delay4_var'):
                self.perfect_delay4_var = tk.DoubleVar(value=self.app.settings["perfect_delay4"])
                self.perfect_delay4_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay4": self.perfect_delay4_var.get()}))
            if not hasattr(self, 'perfect_delay5_var'):
                self.perfect_delay5_var = tk.DoubleVar(value=self.app.settings["perfect_delay5"])
                self.perfect_delay5_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay5": self.perfect_delay5_var.get()}))
            if not hasattr(self, 'perfect_delay6_var'):
                self.perfect_delay6_var = tk.DoubleVar(value=self.app.settings["perfect_delay6"])
                self.perfect_delay6_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay6": self.perfect_delay6_var.get()}))
            if not hasattr(self, 'perfect_delay7_var'):
                self.perfect_delay7_var = tk.DoubleVar(value=self.app.settings["perfect_delay7"])
                self.perfect_delay7_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay7": self.perfect_delay7_var.get()}))
            if not hasattr(self, 'zoom_out_var'):
                self.zoom_out_var = tk.IntVar(value=self.app.settings["zoom_out"])
                self.zoom_out_var.trace_add("write", lambda *args: self.app.settings.update({"zoom_out": self.zoom_out_var.get()}))
            if not hasattr(self, 'zoom_in_var'):
                self.zoom_in_var = tk.IntVar(value=self.app.settings["zoom_in"])
                self.zoom_in_var.trace_add("write", lambda *args: self.app.settings.update({"zoom_in": self.zoom_in_var.get()}))
            if not hasattr(self, 'look_down_var'):
                self.look_down_var = tk.IntVar(value=self.app.settings["look_down"])
                self.look_down_var.trace_add("write", lambda *args: self.app.settings.update({"look_down": self.look_down_var.get()}))
            if not hasattr(self, 'look_up_var'):
                self.look_up_var = tk.IntVar(value=self.app.settings["look_up"])
                self.look_up_var.trace_add("write", lambda *args: self.app.settings.update({"look_up": self.look_up_var.get()}))

            # Final zoom in and look up (after perfect cast release)
            if not hasattr(self, 'perfect_delay8_var'):
                self.perfect_delay8_var = tk.DoubleVar(value=self.app.settings.get("perfect_delay8", 0.0))
                self.perfect_delay8_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay8": self.perfect_delay8_var.get()}))
            if not hasattr(self, 'final_zoom_in_var'):
                self.final_zoom_in_var = tk.IntVar(value=self.app.settings.get("final_zoom_in", 5))
                self.final_zoom_in_var.trace_add("write", lambda *args: self.app.settings.update({"final_zoom_in": self.final_zoom_in_var.get()}))
            if not hasattr(self, 'perfect_delay9_var'):
                self.perfect_delay9_var = tk.DoubleVar(value=self.app.settings.get("perfect_delay9", 0.0))
                self.perfect_delay9_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay9": self.perfect_delay9_var.get()}))
            if not hasattr(self, 'final_look_up_var'):
                self.final_look_up_var = tk.IntVar(value=self.app.settings.get("final_look_up", 2000))
                self.final_look_up_var.trace_add("write", lambda *args: self.app.settings.update({"final_look_up": self.final_look_up_var.get()}))
            if not hasattr(self, 'perfect_delay10_var'):
                self.perfect_delay10_var = tk.DoubleVar(value=self.app.settings.get("perfect_delay10", 0.0))
                self.perfect_delay10_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_delay10": self.perfect_delay10_var.get()}))

            row_count = 1
            
            # Step 1: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay1_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 2: Zoom Out
            self._create_flowchart_zoom_step(flowchart_frame, row_count, "🔍", "Zoom Out", self.zoom_out_var, "#9C27B0", zoom_type="out")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 3: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay2_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 4: Zoom In
            self._create_flowchart_zoom_step(flowchart_frame, row_count, "🔍", "Zoom In", self.zoom_in_var, "#9C27B0", zoom_type="in")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 5: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay3_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 6: Look Down
            self._create_flowchart_look_step(flowchart_frame, row_count, "👁️", "Look Down", self.look_down_var, "#2196F3", look_type="down")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 7: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay4_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 8: Look Up
            self._create_flowchart_look_step(flowchart_frame, row_count, "👁️", "Look Up", self.look_up_var, "#2196F3", look_type="up")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 9: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay5_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 10: Hold Left Click
            self._create_flowchart_click_step(flowchart_frame, row_count, "🖱️", "Hold Left Click", "#4CAF50")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 11: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay6_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1
            
            # Step 12: Perfect Cast Release
            self._create_flowchart_click_step(flowchart_frame, row_count, "⭐", "Perfect Cast Release", "#FFD700")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1

            # Step 13: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay8_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1

            # Step 14: Zoom In
            self._create_flowchart_zoom_step(flowchart_frame, row_count, "🔍", "Zoom In", self.final_zoom_in_var, "#9C27B0", zoom_type="in")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1

            # Step 15: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay9_var, "#F5A623")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1

            # Step 16: Look Up
            self._create_flowchart_look_step(flowchart_frame, row_count, "👁️", "Look Up", self.final_look_up_var, "#2196F3", look_type="up")
            row_count += 1
            self._create_flowchart_arrow(flowchart_frame, row_count)
            row_count += 1

            # Step 17: Delay
            self._create_flowchart_step(flowchart_frame, row_count, "⏱️", "Delay", self.perfect_delay10_var, "#F5A623")

            # Perfect Cast Release Settings Section
            settings_frame = ctk.CTkFrame(
                self.options_content_frame,
                fg_color="#4A4A4A",
                corner_radius=10,
                border_width=1,
                border_color="#6A6A6A"
            )
            settings_frame.grid(row=1, column=0, pady=(20, 10), padx=10, sticky="ew")
            settings_frame.grid_columnconfigure(0, weight=1)
            
            # Settings title
            settings_title = ctk.CTkLabel(
                settings_frame,
                text="⚙️ Perfect Cast Release Settings",
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#E0E0E0"
            )
            settings_title.grid(row=0, column=0, pady=(15, 10), sticky="n")

            # Create settings content frame
            settings_content_frame = ctk.CTkFrame(settings_frame, fg_color="transparent")
            settings_content_frame.grid(row=1, column=0, padx=20, pady=(0, 15), sticky="ew")
            settings_content_frame.grid_columnconfigure(0, weight=1)
            
            # Direct settings container (no dropdown needed)
            self.perfect_cast_options_frame = ctk.CTkFrame(settings_content_frame, fg_color="transparent")
            self.perfect_cast_options_frame.grid(row=0, column=0, sticky="ew")
            self.perfect_cast_options_frame.grid_columnconfigure(0, weight=1)
            
            # Initialize settings display
            self._create_perfect_cast_settings()
    
    def _create_flowchart_step(self, parent, row, icon, label, delay_var, color):
        """Creates a flowchart step with adjustable delay."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label and delay display
        text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="ew", padx=5)
        text_frame.grid_columnconfigure(0, weight=1)
        
        main_label = ctk.CTkLabel(
            text_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=0, sticky="w")
        
        delay_label = ctk.CTkLabel(
            text_frame,
            text=f"({delay_var.get():.1f}s)",
            font=ctk.CTkFont(size=12),
            text_color="white"
        )
        delay_label.grid(row=1, column=0, sticky="w")
        
        # Delay controls
        controls_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=2, padx=(5, 15), sticky="e")
        
        # Direct input entry
        def on_entry_change(*args):
            try:
                value = float(entry_var.get())
                delay_var.set(value)
                delay_label.configure(text=f"({value:.1f}s)")
            except ValueError:
                pass  # Ignore invalid input
            except tk.TclError:
                pass  # Widget was destroyed (cast style changed)
        
        entry_var = tk.StringVar(value=f"{delay_var.get():.1f}")
        entry_var.trace_add("write", on_entry_change)
        
        delay_entry = ctk.CTkEntry(
            controls_frame,
            textvariable=entry_var,
            width=60,
            height=25,
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        delay_entry.grid(row=0, column=0, padx=2)
        
        # Update entry when delay_var changes externally
        def update_entry(*args):
            entry_var.set(f"{delay_var.get():.1f}")
        
        delay_var.trace_add("write", update_entry)
        
        # Store references for updates
        delay_var.delay_label = delay_label
        delay_var.entry_var = entry_var
        
        return step_frame
    
    def _create_flowchart_click_step(self, parent, row, icon, label, color):
        """Creates a flowchart step for click actions (no delay adjustment)."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label
        main_label = ctk.CTkLabel(
            step_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=1, sticky="w", padx=5)
        
        return step_frame
    
    def _create_flowchart_arrow(self, parent, row):
        """Creates a downward arrow between flowchart steps."""
        arrow_label = ctk.CTkLabel(
            parent,
            text="⬇️",
            font=ctk.CTkFont(size=16),
            text_color="#CCCCCC"
        )
        arrow_label.grid(row=row, column=0, columnspan=3, pady=2)
        return arrow_label
    
    def _adjust_delay(self, delay_var, adjustment, delay_label, value_label=None):
        """Adjusts delay value within bounds and updates display."""
        current_value = delay_var.get()
        new_value = max(0.0, min(10.0, current_value + adjustment))
        delay_var.set(new_value)
        
        # Update displays
        delay_label.configure(text=f"({new_value:.1f}s)")
        if value_label:
            value_label.configure(text=f"{new_value:.1f}")
        elif hasattr(delay_var, 'value_label'):
            delay_var.value_label.configure(text=f"{new_value:.1f}")
    
    def _create_flowchart_zoom_step(self, parent, row, icon, label, zoom_var, color, zoom_type):
        """Creates a flowchart step with adjustable zoom (1-20 range, interval of 1)."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label and zoom display
        text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="ew", padx=5)
        text_frame.grid_columnconfigure(0, weight=1)
        
        main_label = ctk.CTkLabel(
            text_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=0, sticky="w")
        
        zoom_label = ctk.CTkLabel(
            text_frame,
            text=f"({zoom_var.get()})",
            font=ctk.CTkFont(size=12),
            text_color="white"
        )
        zoom_label.grid(row=1, column=0, sticky="w")
        
        # Zoom controls
        controls_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=2, padx=(5, 15), sticky="e")
        
        # Decrease button
        decrease_btn = ctk.CTkButton(
            controls_frame,
            text="➕",
            width=30,
            height=25,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2E2E2E",
            hover_color="#3E3E3E",
            command=lambda: self._adjust_zoom(zoom_var, -1, zoom_label)
        )
        decrease_btn.grid(row=0, column=0, padx=2)
        
        # Value display
        value_label = ctk.CTkLabel(
            controls_frame,
            text=f"{zoom_var.get()}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
            width=40
        )
        value_label.grid(row=0, column=1, padx=2)
        
        # Increase button
        increase_btn = ctk.CTkButton(
            controls_frame,
            text="➕",
            width=30,
            height=25,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2E2E2E",
            hover_color="#3E3E3E",
            command=lambda: self._adjust_zoom(zoom_var, 1, zoom_label, value_label)
        )
        increase_btn.grid(row=0, column=2, padx=2)
        
        # Store references for updates
        zoom_var.value_label = value_label
        zoom_var.zoom_label = zoom_label
        
        return step_frame
    
    def _create_flowchart_look_step(self, parent, row, icon, label, look_var, color, look_type):
        """Creates a flowchart step with adjustable look (0-5000 range, interval of 100)."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label and look display
        text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="ew", padx=5)
        text_frame.grid_columnconfigure(0, weight=1)
        
        main_label = ctk.CTkLabel(
            text_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=0, sticky="w")
        
        look_label = ctk.CTkLabel(
            text_frame,
            text=f"({look_var.get()})",
            font=ctk.CTkFont(size=12),
            text_color="white"
        )
        look_label.grid(row=1, column=0, sticky="w")
        
        # Look controls
        controls_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=2, padx=(5, 15), sticky="e")
        
        # Decrease button
        decrease_btn = ctk.CTkButton(
            controls_frame,
            text="➕",
            width=30,
            height=25,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2E2E2E",
            hover_color="#3E3E3E",
            command=lambda: self._adjust_look(look_var, -100, look_label)
        )
        decrease_btn.grid(row=0, column=0, padx=2)
        
        # Value display
        value_label = ctk.CTkLabel(
            controls_frame,
            text=f"{look_var.get()}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="white",
            width=40
        )
        value_label.grid(row=0, column=1, padx=2)
        
        # Increase button
        increase_btn = ctk.CTkButton(
            controls_frame,
            text="➕",
            width=30,
            height=25,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#2E2E2E",
            hover_color="#3E3E3E",
            command=lambda: self._adjust_look(look_var, 100, look_label, value_label)
        )
        increase_btn.grid(row=0, column=2, padx=2)
        
        # Store references for updates
        look_var.value_label = value_label
        look_var.look_label = look_label
        
        return step_frame
    
    def _adjust_zoom(self, zoom_var, adjustment, zoom_label, value_label=None):
        """Adjusts zoom value within bounds (1-20) and updates display."""
        current_value = zoom_var.get()
        new_value = max(1, min(20, current_value + adjustment))
        zoom_var.set(new_value)
        
        # Update displays
        zoom_label.configure(text=f"({new_value})")
        if value_label:
            value_label.configure(text=f"{new_value}")
        elif hasattr(zoom_var, 'value_label'):
            zoom_var.value_label.configure(text=f"{new_value}")
    
    def _adjust_look(self, look_var, adjustment, look_label, value_label=None):
        """Adjusts look value within bounds (0-5000) and updates display."""
        current_value = look_var.get()
        new_value = max(0, min(5000, current_value + adjustment))
        look_var.set(new_value)
        
        # Update displays
        look_label.configure(text=f"({new_value})")
        if value_label:
            value_label.configure(text=f"{new_value}")
        elif hasattr(look_var, 'value_label'):
            look_var.value_label.configure(text=f"{new_value}")

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")


    def _create_perfect_cast_settings(self):
        """Creates the perfect cast release settings."""
        # Clear existing options content
        for widget in self.perfect_cast_options_frame.winfo_children():
            widget.destroy()
        # Green Color Tolerance
        green_tolerance_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        green_tolerance_frame.grid(row=0, column=0, pady=(0, 10), sticky="ew")
        green_tolerance_frame.grid_columnconfigure(1, weight=1)
        
        green_tolerance_label = ctk.CTkLabel(
            green_tolerance_frame,
            text="🟢 Green Color Tolerance:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        green_tolerance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        # Initialize green tolerance variable if it doesn't exist
        if not hasattr(self, 'perfect_cast_green_tolerance_var'):
            self.perfect_cast_green_tolerance_var = tk.IntVar(value=self.app.settings["perfect_cast_green_color_tolerance"])
            self.perfect_cast_green_tolerance_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_green_color_tolerance": self.perfect_cast_green_tolerance_var.get()}))
        
        green_tolerance_slider = ctk.CTkSlider(
            green_tolerance_frame,
            from_=0,
            to=50,
            number_of_steps=50,
            variable=self.perfect_cast_green_tolerance_var,
            progress_color="#F5A623",
            button_color="#E0941F",
            button_hover_color="#FFBD47"
        )
        green_tolerance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        green_tolerance_value = ctk.CTkLabel(
            green_tolerance_frame,
            text="10",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E0941F",
            width=30
        )
        green_tolerance_value.grid(row=0, column=2, sticky="e")

        green_tolerance_slider.configure(command=lambda value: green_tolerance_value.configure(text=str(int(value))))
        green_tolerance_value.configure(text=str(self.perfect_cast_green_tolerance_var.get()))  # Initialize display
        
        # White Color Tolerance
        white_tolerance_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        white_tolerance_frame.grid(row=1, column=0, pady=(0, 10), sticky="ew")
        white_tolerance_frame.grid_columnconfigure(1, weight=1)
        
        white_tolerance_label = ctk.CTkLabel(
            white_tolerance_frame,
            text="⚪ White Color Tolerance:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        white_tolerance_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        # Initialize white tolerance variable if it doesn't exist
        if not hasattr(self, 'perfect_cast_white_tolerance_var'):
            self.perfect_cast_white_tolerance_var = tk.IntVar(value=self.app.settings["perfect_cast_white_color_tolerance"])
            self.perfect_cast_white_tolerance_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_white_color_tolerance": self.perfect_cast_white_tolerance_var.get()}))
        
        white_tolerance_slider = ctk.CTkSlider(
            white_tolerance_frame,
            from_=0,
            to=50,
            number_of_steps=50,
            variable=self.perfect_cast_white_tolerance_var,
            progress_color="#F5A623",
            button_color="#E0941F",
            button_hover_color="#FFBD47"
        )
        white_tolerance_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        white_tolerance_value = ctk.CTkLabel(
            white_tolerance_frame,
            text="10",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E0941F",
            width=30
        )
        white_tolerance_value.grid(row=0, column=2, sticky="e")

        white_tolerance_slider.configure(command=lambda value: white_tolerance_value.configure(text=str(int(value))))
        white_tolerance_value.configure(text=str(self.perfect_cast_white_tolerance_var.get()))  # Initialize display
        
        # Fail Scan Timeout
        timeout_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        timeout_frame.grid(row=2, column=0, pady=(0, 10), sticky="ew")
        timeout_frame.grid_columnconfigure(1, weight=1)
        
        timeout_label = ctk.CTkLabel(
            timeout_frame,
            text="⏱️ Fail Scan Timeout:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        timeout_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        # Initialize timeout variable if it doesn't exist
        if not hasattr(self, 'perfect_cast_timeout_var'):
            self.perfect_cast_timeout_var = tk.IntVar(value=self.app.settings["perfect_cast_fail_scan_timeout"])
            self.perfect_cast_timeout_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_fail_scan_timeout": self.perfect_cast_timeout_var.get()}))
        
        timeout_slider = ctk.CTkSlider(
            timeout_frame,
            from_=0,
            to=10,
            number_of_steps=100,  # 0.1 second steps
            variable=self.perfect_cast_timeout_var,
            progress_color="#F5A623",
            button_color="#E0941F",
            button_hover_color="#FFBD47"
        )
        timeout_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        def update_timeout_display(value):
            timeout_val = float(value)
            display_text = f"{timeout_val:.1f}s"
            timeout_value.configure(text=display_text)
        
        timeout_value = ctk.CTkLabel(
            timeout_frame,
            text="3.0s",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E0941F",
            width=40
        )
        timeout_value.grid(row=0, column=2, sticky="e")

        timeout_slider.configure(command=update_timeout_display)
        update_timeout_display(self.perfect_cast_timeout_var.get())  # Initialize display

        # Release Style Dropdown
        style_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        style_frame.grid(row=3, column=0, pady=(0, 20), sticky="ew")
        style_frame.grid_columnconfigure(1, weight=1)
        
        style_label = ctk.CTkLabel(
            style_frame,
            text="🎯 Release Style:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#F0F0F0"
        )
        style_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        if not hasattr(self, 'perfect_cast_release_style_var'):
            self.perfect_cast_release_style_var = tk.StringVar(value=self.app.settings.get("perfect_cast_release_style", "GigaSigmaUltraMode"))
            self.perfect_cast_release_style_var.trace_add("write", lambda *args: [
                self.app.settings.update({"perfect_cast_release_style": self.perfect_cast_release_style_var.get()}),
                self._update_release_style_display()
            ])
        
        style_dropdown = ctk.CTkOptionMenu(
            style_frame,
            values=["Velocity-Percentage", "Prediction", "GigaSigmaUltraMode"],
            variable=self.perfect_cast_release_style_var,
            fg_color="#F5A623",
            button_color="#E0941F",
            button_hover_color="#FFBD47",
            dropdown_fg_color="#3A3A3A",
            font=ctk.CTkFont(size=14, weight="bold"),
            corner_radius=10,
            width=200
        )
        style_dropdown.grid(row=0, column=1, padx=(0, 10), sticky="w")

        # Tuning Instructions Header
        instructions_frame = ctk.CTkFrame(
            self.perfect_cast_options_frame,
            fg_color="#3A3A3A",
            corner_radius=10,
            border_width=2,
            border_color="#F5A623"
        )
        instructions_frame.grid(row=4, column=0, pady=(15, 15), sticky="ew")
        
        instructions_title = ctk.CTkLabel(
            instructions_frame,
            text="📖 Tutorial Guide",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#F5A623"
        )
        instructions_title.grid(row=0, column=0, pady=(10, 5), padx=15, sticky="w")
        
        instructions_text = ctk.CTkLabel(
            instructions_frame,
            text="💡 If this doesn't work, try other modes",
            font=ctk.CTkFont(size=12),
            text_color="#D0D0D0",
            justify="left"
        )
        instructions_text.grid(row=1, column=0, pady=(0, 10), padx=15, sticky="w")

        # NEW: Velocity-Based Release Percentage Sliders
        
        # Band 1: <400 px/s
        band1_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band1_frame.grid(row=5, column=0, pady=(0, 10), sticky="ew")
        band1_frame.grid_columnconfigure(1, weight=1)
        
        band1_label = ctk.CTkLabel(
            band1_frame,
            text="🐌 <400 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#87CEEB",  # Calm sky blue for slowest speeds
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band1_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.perfect_cast_band1_release_var = self.app._ensure_gui_var(
            self, 'perfect_cast_band1_release_var', tk.IntVar, 
            "perfect_cast_band1_release", 95, 
            lambda *args: self.app.settings.update({"perfect_cast_band1_release": self.perfect_cast_band1_release_var.get()})
        )
        
        band1_slider = ctk.CTkSlider(
            band1_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band1_release_var,
            progress_color="#87CEEB",  # Match label color
            button_color="#5F9EA0",
            button_hover_color="#B0E0E6"
        )
        band1_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band1_value = ctk.CTkLabel(
            band1_frame,
            text="95%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#87CEEB",  # Match label color
            width=50
        )
        band1_value.grid(row=0, column=2, sticky="e")

        def update_band1_display(value):
            band1_value.configure(text=f"{int(float(value))}%")
        band1_slider.configure(command=update_band1_display)
        update_band1_display(self.perfect_cast_band1_release_var.get())
        
        # Band 2: 400-600 px/s
        band2_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band2_frame.grid(row=6, column=0, pady=(0, 10), sticky="ew")
        band2_frame.grid_columnconfigure(1, weight=1)
        
        band2_label = ctk.CTkLabel(
            band2_frame,
            text="🚶 400-600 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#5F9EA0",  # Cadet blue for slow speeds
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band2_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.perfect_cast_band2_release_var = self.app._ensure_gui_var(
            self, 'perfect_cast_band2_release_var', tk.IntVar, 
            "perfect_cast_band2_release", 95, 
            lambda *args: self.app.settings.update({"perfect_cast_band2_release": self.perfect_cast_band2_release_var.get()})
        )
        
        band2_slider = ctk.CTkSlider(
            band2_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band2_release_var,
            progress_color="#5F9EA0",  # Match label color
            button_color="#4A7C7E",
            button_hover_color="#7FB1B3"
        )
        band2_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band2_value = ctk.CTkLabel(
            band2_frame,
            text="94%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#5F9EA0",  # Match label color
            width=50
        )
        band2_value.grid(row=0, column=2, sticky="e")

        def update_band2_display(value):
            band2_value.configure(text=f"{int(float(value))}%")
        band2_slider.configure(command=update_band2_display)
        update_band2_display(self.perfect_cast_band2_release_var.get())

        # Band 3: 600-800 px/s
        band3_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band3_frame.grid(row=7, column=0, pady=(0, 10), sticky="ew")
        band3_frame.grid_columnconfigure(1, weight=1)
        
        band3_label = ctk.CTkLabel(
            band3_frame,
            text="🏃 600-800 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#66B2B2",  # Teal for transitional speeds
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band3_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.perfect_cast_band3_release_var = self.app._ensure_gui_var(
            self, 'perfect_cast_band3_release_var', tk.IntVar, 
            "perfect_cast_band3_release", 95, 
            lambda *args: self.app.settings.update({"perfect_cast_band3_release": self.perfect_cast_band3_release_var.get()})
        )
        
        band3_slider = ctk.CTkSlider(
            band3_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band3_release_var,
            progress_color="#66B2B2",  # Match label color
            button_color="#559999",
            button_hover_color="#7FCCCC"
        )
        band3_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band3_value = ctk.CTkLabel(
            band3_frame,
            text="93%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#66B2B2",  # Match label color
            width=50
        )
        band3_value.grid(row=0, column=2, sticky="e")

        def update_band3_display(value):
            band3_value.configure(text=f"{int(float(value))}%")
        band3_slider.configure(command=update_band3_display)
        update_band3_display(self.perfect_cast_band3_release_var.get())

        # Band 4: 800-1000 px/s
        band4_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band4_frame.grid(row=8, column=0, pady=(0, 10), sticky="ew")
        band4_frame.grid_columnconfigure(1, weight=1)
        
        band4_label = ctk.CTkLabel(
            band4_frame,
            text="🚴 800-1000 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFD700",  # Gold for moderate speeds
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band4_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.perfect_cast_band4_release_var = self.app._ensure_gui_var(
            self, 'perfect_cast_band4_release_var', tk.IntVar, 
            "perfect_cast_band4_release", 92, 
            lambda *args: self.app.settings.update({"perfect_cast_band4_release": self.perfect_cast_band4_release_var.get()})
        )
        
        band4_slider = ctk.CTkSlider(
            band4_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band4_release_var,
            progress_color="#FFD700",  # Match label color
            button_color="#DAA520",
            button_hover_color="#FFEC8B"
        )
        band4_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band4_value = ctk.CTkLabel(
            band4_frame,
            text="92%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFD700",  # Match label color
            width=50
        )
        band4_value.grid(row=0, column=2, sticky="e")

        def update_band4_display(value):
            band4_value.configure(text=f"{int(float(value))}%")
        band4_slider.configure(command=update_band4_display)
        update_band4_display(self.perfect_cast_band4_release_var.get())

        # Band 5: 1000-1200 px/s
        band5_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band5_frame.grid(row=9, column=0, pady=(0, 10), sticky="ew")
        band5_frame.grid_columnconfigure(1, weight=1)
        
        band5_label = ctk.CTkLabel(
            band5_frame,
            text="🏎️ 1000-1200 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFA500",  # Orange for getting intense
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band5_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        if not hasattr(self, 'perfect_cast_band5_release_var'):
            self.perfect_cast_band5_release_var = tk.IntVar(value=self.app.settings.get("perfect_cast_band5_release", 91))
            self.perfect_cast_band5_release_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_band5_release": self.perfect_cast_band5_release_var.get()}))
        
        band5_slider = ctk.CTkSlider(
            band5_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band5_release_var,
            progress_color="#FFA500",  # Match label color
            button_color="#E69400",
            button_hover_color="#FFB733"
        )
        band5_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band5_value = ctk.CTkLabel(
            band5_frame,
            text="90%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FFA500",  # Match label color
            width=50
        )
        band5_value.grid(row=0, column=2, sticky="e")

        def update_band5_display(value):
            band5_value.configure(text=f"{int(float(value))}%")
        band5_slider.configure(command=update_band5_display)
        update_band5_display(self.perfect_cast_band5_release_var.get())

        # Band 6: >1200 px/s
        band6_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        band6_frame.grid(row=10, column=0, pady=(0, 10), sticky="ew")
        band6_frame.grid_columnconfigure(1, weight=1)
        
        band6_label = ctk.CTkLabel(
            band6_frame,
            text="⚡ >1200 px/s:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FF0000",  # Intense red for fastest speeds
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        band6_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        if not hasattr(self, 'perfect_cast_band6_release_var'):
            self.perfect_cast_band6_release_var = tk.IntVar(value=self.app.settings.get("perfect_cast_band6_release", 90))
            self.perfect_cast_band6_release_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_band6_release": self.perfect_cast_band6_release_var.get()}))
        
        band6_slider = ctk.CTkSlider(
            band6_frame,
            from_=70,
            to=95,
            number_of_steps=25,
            variable=self.perfect_cast_band6_release_var,
            progress_color="#FF0000",  # Match label color
            button_color="#CC0000",
            button_hover_color="#FF4444"
        )
        band6_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        band6_value = ctk.CTkLabel(
            band6_frame,
            text="88%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#FF0000",  # Match label color
            width=50
        )
        band6_value.grid(row=0, column=2, sticky="e")

        def update_band6_display(value):
            band6_value.configure(text=f"{int(float(value))}%")
        band6_slider.configure(command=update_band6_display)
        update_band6_display(self.perfect_cast_band6_release_var.get())

        # Fallback slider
        # Fallback slider for velocity mode
        percentage_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        percentage_frame.grid(row=11, column=0, pady=(0, 15), sticky="ew")
        percentage_frame.grid_columnconfigure(1, weight=1)
        
        percentage_label = ctk.CTkLabel(
            percentage_frame,
            text="❓ Fallback (Unknown):",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#888888",
            width=200,  # Fixed width for alignment
            anchor="w"
        )
        percentage_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        # Initialize percentage variable if it doesn't exist
        if not hasattr(self, 'perfect_cast_release_percentage_var'):
            self.perfect_cast_release_percentage_var = tk.IntVar(value=self.app.settings["perfect_cast_release_percentage"])
            self.perfect_cast_release_percentage_var.trace_add("write", lambda *args: self.app.settings.update({"perfect_cast_release_percentage": self.perfect_cast_release_percentage_var.get()}))
        
        percentage_slider = ctk.CTkSlider(
            percentage_frame,
            from_=70,
            to=95,
            number_of_steps=25,  # 1% increments
            variable=self.perfect_cast_release_percentage_var,
            progress_color="#888888",
            button_color="#777777",
            button_hover_color="#999999"
        )
        percentage_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
        
        percentage_value = ctk.CTkLabel(
            percentage_frame,
            text="80%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#888888",
            width=50
        )
        percentage_value.grid(row=0, column=2, sticky="e")

        def update_percentage_display(value):
            percentage_val = int(float(value))
            percentage_value.configure(text=f"{percentage_val}%")
        
        percentage_slider.configure(command=update_percentage_display)
        update_percentage_display(self.perfect_cast_release_percentage_var.get())  # Initialize display
        
        # Initialize release style display (show/hide appropriate sliders)
        self._update_release_style_display()

    def _update_release_style_display(self):
        """Show/hide appropriate settings based on release style selection."""
        release_style = self.perfect_cast_release_style_var.get()
        
        # Store references to velocity-percentage widget rows (5-11)
        velocity_percentage_rows = {5, 6, 7, 8, 9, 10, 11}  # 6 bands + fallback
        
        # Store references to prediction system widget rows (12-22) - 11 bands, offset to avoid conflict
        prediction_rows = {12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22}
        
        # GigaSigma widget rows (23+)
        gigasigma_rows = set(range(23, 40))
        
        # We need to track widgets by their ORIGINAL row position since grid_remove() clears grid_info
        # Store widget-to-row mapping on first call
        if not hasattr(self, '_widget_row_mapping'):
            self._widget_row_mapping = {}
            for widget in self.perfect_cast_options_frame.winfo_children():
                grid_info = widget.grid_info()
                if grid_info and 'row' in grid_info:
                    self._widget_row_mapping[widget] = int(grid_info['row'])
        
        if release_style == "Velocity-Percentage":
            # Create prediction sliders first if they don't exist (so we can hide them)
            if not hasattr(self, '_prediction_sliders_created'):
                self._create_prediction_sliders()
                self._prediction_sliders_created = True
                
                # Update widget mapping with new prediction widgets
                for widget in self.perfect_cast_options_frame.winfo_children():
                    if widget not in self._widget_row_mapping:
                        grid_info = widget.grid_info()
                        if grid_info and 'row' in grid_info:
                            self._widget_row_mapping[widget] = int(grid_info['row'])
            
            # Hide ALL prediction sliders (rows 12-22)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in prediction_rows:
                    widget.grid_remove()
            
            # Hide ALL GigaSigma sliders (rows 23+)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in gigasigma_rows:
                    widget.grid_remove()
            
            # Show velocity-percentage sliders (rows 5-11)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in velocity_percentage_rows:
                    # Re-grid the widget at its original position
                    widget.grid(row=row, column=0, pady=(0, 10), sticky="ew")
            
            # Update instructions frame text
            for widget, row in self._widget_row_mapping.items():
                if row == 4:  # Instructions frame
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("💡"):
                            try:
                                child.configure(
                                    text="💡 Release too LATE? → Increase the % value for your speed band\n"
                                         "💡 Release too EARLY? → Decrease the % value for your speed band\n"
                                         "👁️ Check the overlay to see your px/s velocity (shown in top section)\n"
                                         "🎯 Adjust the slider that matches your bar's speed range",
                                    font=ctk.CTkFont(size=12)
                                )
                            except (tk.TclError, AttributeError) as e:
                                print(f"    ⚠️ Warning: Could not update help text: {e}")
                    break
                    
        elif release_style == "Prediction":
            # Hide velocity-percentage sliders (rows 5-11)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in velocity_percentage_rows:
                    widget.grid_remove()  # Hide but keep in memory
            
            # Hide ALL GigaSigma sliders (rows 23+)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in gigasigma_rows:
                    widget.grid_remove()
            
            # Update instructions frame text
            for widget, row in self._widget_row_mapping.items():
                if row == 4:  # Instructions frame
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("💡"):
                            try:
                                child.configure(
                                    text="💡 Release too LATE? → Increase ms (more positive, e.g., -5 to 0)\n"
                                         "💡 Release too EARLY? → Decrease ms (more negative, e.g., 0 to -5)\n"
                                         "👁️ Check the overlay to see your px/s velocity (shown in top section)\n"
                                         "🎯 Adjust the timing slider that matches your bar's speed range",
                                    font=ctk.CTkFont(size=12)
                                )
                            except (tk.TclError, AttributeError) as e:
                                print(f"    ⚠️ Warning: Could not update prediction help text: {e}")
                    break
            
            # Create prediction sliders if they don't exist
            if not hasattr(self, '_prediction_sliders_created'):
                self._create_prediction_sliders()
                self._prediction_sliders_created = True
                
                # Update widget mapping with new prediction widgets
                for widget in self.perfect_cast_options_frame.winfo_children():
                    if widget not in self._widget_row_mapping:
                        grid_info = widget.grid_info()
                        if grid_info and 'row' in grid_info:
                            self._widget_row_mapping[widget] = int(grid_info['row'])
            
            # Show ALL prediction sliders (rows 12-22)
            for widget, row in list(self._widget_row_mapping.items()):
                if row in prediction_rows:
                    # Re-grid the widget at its original position
                    widget.grid(row=row, column=0, pady=(0, 10), sticky="ew")
        
        elif release_style == "GigaSigmaUltraMode":
            # Hide velocity-percentage sliders
            for widget, row in list(self._widget_row_mapping.items()):
                if row in velocity_percentage_rows:
                    widget.grid_remove()
                if row in prediction_rows:
                    widget.grid_remove()
            
            # Update instructions frame text
            for widget, row in self._widget_row_mapping.items():
                if row == 4:  # Instructions frame
                    for child in widget.winfo_children():
                        if isinstance(child, ctk.CTkLabel) and child.cget("text").startswith("💡"):
                            try:
                                child.configure(
                                    text="💡 If this doesn't work, try other modes",
                                    font=ctk.CTkFont(size=12)
                                )
                            except (tk.TclError, AttributeError) as e:
                                print(f"    ⚠️ Warning: Could not update GigaSigma help text: {e}")
                    break
            
            # Create GigaSigma sliders if they don't exist
            if not hasattr(self, '_gigasigma_sliders_created'):
                self._create_gigasigma_sliders()
                self._gigasigma_sliders_created = True
                
                # Update widget mapping
                for widget in self.perfect_cast_options_frame.winfo_children():
                    if widget not in self._widget_row_mapping:
                        grid_info = widget.grid_info()
                        if grid_info and 'row' in grid_info:
                            self._widget_row_mapping[widget] = int(grid_info['row'])
            
            # Show GigaSigma sliders (rows 23+, after prediction rows which end at 22)
            gigasigma_rows = set(range(23, 40))
            for widget, row in list(self._widget_row_mapping.items()):
                if row in gigasigma_rows:
                    widget.grid(row=row, column=0, pady=(0, 8), sticky="ew")

    def _create_prediction_sliders(self):
        """Creates the 11 velocity band timing sliders for prediction system."""
        # Get resolution scaling factor
        reference_height = self.app.settings.get("perfect_cast_reference_height", 1440)
        current_height = self.app.current_height
        scaling_factor = current_height / reference_height
        
        # Define 11 velocity bands with emojis, ranges, settings keys, and colors
        # Colors: calm blues/greens for slow, transition through yellow/orange, intense reds for fast
        velocity_bands_base = [
            ("🐌", 0, 700, "perfect_cast_timing_700", "#87CEEB"),      # <700 - Light sky blue (calm)
            ("🐢", 700, 800, "perfect_cast_timing_800", "#5F9EA0"),    # 700-800 - Cadet blue (calm)
            ("🚶", 800, 900, "perfect_cast_timing_900", "#66B2B2"),    # 800-900 - Teal (calm)
            ("🏃", 900, 1000, "perfect_cast_timing_1000", "#4682B4"),  # 900-1000 - Steel blue (moderate)
            ("🏃‍♂️", 1000, 1100, "perfect_cast_timing_1100", "#32CD32"), # 1000-1100 - Lime green (transitioning)
            ("🚴", 1100, 1200, "perfect_cast_timing_1200", "#FFD700"), # 1100-1200 - Gold (transitioning)
            ("🏍️", 1200, 1300, "perfect_cast_timing_1300", "#FFA500"), # 1200-1300 - Orange (getting intense)
            ("🚗", 1300, 1400, "perfect_cast_timing_1400", "#FF8C00"), # 1300-1400 - Dark orange (intense)
            ("✈️", 1400, 1500, "perfect_cast_timing_1500", "#FF6347"), # 1400-1500 - Tomato red (intense)
            ("🚀", 1500, 1600, "perfect_cast_timing_1600", "#FF4500"), # 1500-1600 - Orange-red (very intense)
            ("⚡", 1600, 9999, "perfect_cast_timing_1600plus", "#FF0000") # 1600+ - Pure red (maximum intensity)
        ]

        velocity_bands = []
        for emoji, low, high, setting_key, color in velocity_bands_base:
            # Scale velocities to user's resolution
            scaled_low = int(low * scaling_factor)
            scaled_high = int(high * scaling_factor)
            
            # Create label text with scaled values
            if high >= 9999:
                label_text = f"{emoji} {scaled_low}+ px/s"
            else:
                label_text = f"{emoji} {scaled_low}-{scaled_high} px/s"
            
            velocity_bands.append((label_text, setting_key, low, high, color))

        # Create slider for each velocity band (rows 12-22, offset to avoid conflict with velocity-percentage)
        for idx, (label_text, setting_key, base_low, base_high, color) in enumerate(velocity_bands):
            timing_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
            timing_frame.grid(row=12+idx, column=0, pady=(0, 8), sticky="ew")
            timing_frame.grid_columnconfigure(1, weight=1)
            
            timing_label = ctk.CTkLabel(
                timing_frame,
                text=label_text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=color,  # Use the color from velocity_bands
                width=200,  # Fixed width to align all sliders
                anchor="w"
            )
            timing_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

            # Initialize timing variable
            var_name = f'{setting_key}_var'
            if not hasattr(self, var_name):
                var = tk.IntVar(value=self.app.settings.get(setting_key, 0))
                var.trace_add("write", lambda *args, k=setting_key, v=var: self.app.settings.update({k: v.get()}))
                setattr(self, var_name, var)
            else:
                var = getattr(self, var_name)
            
            timing_slider = ctk.CTkSlider(
                timing_frame,
                from_=-200,
                to=200,
                number_of_steps=400,
                variable=var,
                progress_color=color,
                button_color=color,
                button_hover_color=color
            )
            timing_slider.grid(row=0, column=1, padx=(0, 10), sticky="ew")
            
            def make_update_func(val_label, v):
                def update_display(value):
                    val = int(value)
                    if val < 0:
                        display_text = f"{val}ms"
                    elif val > 0:
                        display_text = f"+{val}ms"
                    else:
                        display_text = "0ms"
                    val_label.configure(text=display_text)
                return update_display
            
            timing_value = ctk.CTkLabel(
                timing_frame,
                text="0ms",
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=color,
                width=70
            )
            timing_value.grid(row=0, column=2, sticky="e")

            update_func = make_update_func(timing_value, var)
            timing_slider.configure(command=update_func)
            update_func(var.get())  # Initialize display

    def _create_gigasigma_sliders(self):
        """Creates the ULTIMATE GigaSigmaUltraMode settings panel."""
        row_offset = 23  # Start after prediction rows (which end at 22)
        
        # ===== SECTION 1: BOUNCE STRATEGY =====
        bounce_header = ctk.CTkFrame(
            self.perfect_cast_options_frame,
            fg_color="#2A2A2A",
            corner_radius=10,
            border_width=2,
            border_color="#FF00FF"
        )
        bounce_header.grid(row=row_offset, column=0, pady=(15, 10), sticky="ew")
        
        bounce_title = ctk.CTkLabel(
            bounce_header,
            text="🔄 BOUNCE MODE (ALWAYS 1 BOUNCE)",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#FF00FF"
        )
        bounce_title.grid(row=0, column=0, pady=10, padx=15, sticky="w")
        
        bounce_info = ctk.CTkLabel(
            bounce_header,
            text="Bar automatically bounces once for maximum accuracy",
            font=ctk.CTkFont(size=12),
            text_color="#CCCCCC"
        )
        bounce_info.grid(row=1, column=0, pady=(0, 10), padx=15, sticky="w")
        row_offset += 1
        
        # ===== AUTO-TUNE BUTTONS =====
        tune_frame = ctk.CTkFrame(self.perfect_cast_options_frame, fg_color="transparent")
        tune_frame.grid(row=row_offset, column=0, pady=(0, 15), sticky="ew")
        tune_frame.grid_columnconfigure(0, weight=1)
        tune_frame.grid_columnconfigure(1, weight=1)
        
        # Initialize last cast tracking
        if not hasattr(self.app, '_last_cast_velocity'):
            self.app._last_cast_velocity = None
            self.app._last_cast_band = None
            self.app._tune_used_this_cast = False
            self._last_cast_band = None
            self._tune_used_this_cast = False
        
        # Too Early button
        self.tune_early_button = ctk.CTkButton(
            tune_frame,
            text="⏪ Last Cast Too EARLY",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#FF6B6B",
            hover_color="#FF5252",
            text_color="#FFFFFF",
            command=lambda: self._tune_last_cast("early")
        )
        self.tune_early_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")
        
        # Too Late button
        self.tune_late_button = ctk.CTkButton(
            tune_frame,
            text="⏩ Last Cast Too LATE",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#4ECDC4",
            hover_color="#45B7AF",
            text_color="#FFFFFF",
            command=lambda: self._tune_last_cast("late")
        )
        self.tune_late_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")
        
        # Status label
        self.tune_status_label = ctk.CTkLabel(
            tune_frame,
            text="Cast something first to enable auto-tune",
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        )
        self.tune_status_label.grid(row=1, column=0, columnspan=2, pady=(5, 0))
        
        row_offset += 1

    def _tune_last_cast(self, direction):
        """Auto-tune the velocity band from the last cast."""
        # Check if we have last cast data
        if self.app._last_cast_velocity is None or self.app._last_cast_band is None:
            self.tune_status_label.configure(
                text="❌ No cast data available. Make a cast first!",
                text_color="#FF6B6B"
            )
            return
        
        # Check if already tuned this cast
        if self.app._tune_used_this_cast:
            self.tune_status_label.configure(
                text="❌ Already tuned this cast! Cast again to tune next one.",
                text_color="#FF9B54"
            )
            return
        
        # Map band index to setting key based on perfect cast style
        perfect_cast_style = self.app.settings.get("perfect_cast_release_style", "Velocity-Percentage")
        
        if perfect_cast_style == "Prediction":
            band_settings = [
                "prediction_band1_release",   # 0: <400
                "prediction_band2_release",   # 1: 400-600
                "prediction_band3_release",   # 2: 600-800
                "prediction_band4_release",   # 3: 800-1000
                "prediction_band5_release",   # 4: 1000-1200
                "prediction_band6_release",   # 5: 1200-1400
                "perfect_cast_band7_release", # 6: 1400-1600 (fallback to velocity-percentage for bands 7-11)
                "perfect_cast_band8_release", # 7: 1600-1800
                "perfect_cast_band9_release", # 8: 1800-2000
                "perfect_cast_band10_release",# 9: 2000-2200
                "perfect_cast_band11_release",# 10: >2200
            ]
        elif perfect_cast_style == "GigaSigmaUltraMode":
            band_settings = [
                "gigasigma_band1_release",    # 0: <400
                "gigasigma_band2_release",    # 1: 400-600
                "gigasigma_band3_release",    # 2: 600-800
                "gigasigma_band4_release",    # 3: 800-1000
                "gigasigma_band5_release",    # 4: 1000-1200
                "gigasigma_band6_release",    # 5: 1200-1400
                "perfect_cast_band7_release", # 6: 1400-1600 (fallback to velocity-percentage for bands 7-11)
                "perfect_cast_band8_release", # 7: 1600-1800
                "perfect_cast_band9_release", # 8: 1800-2000
                "perfect_cast_band10_release",# 9: 2000-2200
                "perfect_cast_band11_release",# 10: >2200
            ]
        else:  # Velocity-Percentage (default)
            band_settings = [
                "perfect_cast_band1_release",   # 0: <400
                "perfect_cast_band2_release",   # 1: 400-600
                "perfect_cast_band3_release",   # 2: 600-800
                "perfect_cast_band4_release",   # 3: 800-1000
                "perfect_cast_band5_release",   # 4: 1000-1200
                "perfect_cast_band6_release",   # 5: 1200-1400
                "perfect_cast_band7_release",   # 6: 1400-1600
                "perfect_cast_band8_release",   # 7: 1600-1800
                "perfect_cast_band9_release",   # 8: 1800-2000
                "perfect_cast_band10_release",  # 9: 2000-2200
                "perfect_cast_band11_release",  # 10: >2200
            ]
        
        band_names = [
            "<400 px/s",
            "400-600 px/s",
            "600-800 px/s",
            "800-1000 px/s",
            "1000-1200 px/s",
            "1200-1400 px/s",
            "1400-1600 px/s",
            "1600-1800 px/s",
            "1800-2000 px/s",
            "2000-2200 px/s",
            ">2200 px/s"
        ]
        
        # Get band index from last cast
        band_idx = self.app._last_cast_band
        if band_idx < 0 or band_idx >= len(band_settings):
            self.tune_status_label.configure(
                text="❌ Invalid band data",
                text_color="#FF6B6B"
            )
            return
        
        # Get actual velocity for better display
        velocity = self.app._last_cast_velocity
        
        # Determine detailed velocity range for display (matches bounce adjustment logic)
        if velocity > 2200:
            detailed_range = ">2200 px/s"
        elif velocity > 2000:
            detailed_range = "2000-2200 px/s"
        elif velocity > 1800:
            detailed_range = "1800-2000 px/s"
        elif velocity > 1600:
            detailed_range = "1600-1800 px/s"
        elif velocity > 1400:
            detailed_range = "1400-1600 px/s"
        elif velocity > 1200:
            detailed_range = "1200-1400 px/s"
        elif velocity > 1100:
            detailed_range = "1100-1200 px/s"
        elif velocity > 1000:
            detailed_range = "1000-1100 px/s"
        elif velocity > 900:
            detailed_range = "900-1000 px/s"
        elif velocity > 800:
            detailed_range = "800-900 px/s"
        elif velocity > 700:
            detailed_range = "700-800 px/s"
        elif velocity > 600:
            detailed_range = "600-700 px/s"
        elif velocity > 500:
            detailed_range = "500-600 px/s"
        elif velocity > 400:
            detailed_range = "400-500 px/s"
        else:
            detailed_range = "<400 px/s"
        
        # Get current value
        setting_key = band_settings[band_idx]
        current_value = self.app.settings.get(setting_key, 90)
        
        # Adjust by 1% based on direction
        if direction == "early":
            # Too early means we need to release LATER (increase threshold by 1%)
            new_value = min(98, current_value + 1)
            arrow = "⬆️"
        else:  # late
            # Too late means we need to release EARLIER (decrease threshold by 1%)
            new_value = max(70, current_value - 1)
            arrow = "⬇️"
        
        # Update setting
        self.app.settings[setting_key] = new_value
        
        # Update the corresponding slider if it exists (11 bands)
        slider_vars = [
            getattr(self, 'band1_var', None),
            getattr(self, 'band2_var', None),
            getattr(self, 'band3_var', None),
            getattr(self, 'band4_var', None),
            getattr(self, 'band5_var', None),
            getattr(self, 'band6_var', None),
            getattr(self, 'band7_var', None),
            getattr(self, 'band8_var', None),
            getattr(self, 'band9_var', None),
            getattr(self, 'band10_var', None),
            getattr(self, 'band11_var', None),
        ]
        
        if slider_vars[band_idx] is not None:
            slider_vars[band_idx].set(new_value)
        
        # Mark as used
        self.app._tune_used_this_cast = True
        
        # Update status - show both the base band being adjusted and the detailed velocity range
        self.tune_status_label.configure(
            text=f"✅ {arrow} [{perfect_cast_style}] {band_names[band_idx]}: {current_value}% → {new_value}% | {velocity:.0f} px/s ({detailed_range})",
            text_color="#4ECDC4"
        )
        
        print(f"🎯 Auto-tuned [{perfect_cast_style}] {band_names[band_idx]}: {current_value}% → {new_value}% (Velocity: {velocity:.0f} px/s in {detailed_range}, Direction: {direction})")

    def _reset_gigasigma_learning(self):
        """Reset all GigaSigma learning data."""
        # No longer needed - kept for backward compatibility
        print("🔄 GigaSigma settings reset!")
        
    def _show_gigasigma_stats(self):
        """Show GigaSigma statistics window."""
        # No longer needed - kept for backward compatibility
        print("📊 GigaSigma mode uses velocity-percentage settings")
        
    def _export_gigasigma_data(self):
        """Export GigaSigma learning data."""
        # No longer needed - kept for backward compatibility
        print("💾 GigaSigma mode uses existing velocity-percentage tuning")

    def _create_shake_settings(self):
        """Creates the shake detection settings."""
        pass  # Shake settings removed or implemented elsewhere


class SupportView(ctk.CTkFrame):
    """
    A view (CTkFrame) to contain the Support links. Uses a standard tk.Canvas 
    to create custom, scrollable content with purple theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#9013FE", # Match the purple background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#B347FF"   # Lighter purple border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="💜 Support", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n") 
        
        # Support Links Section with modern card design
        self.support_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.support_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.support_card.grid_columnconfigure(0, weight=1)
        
        # Add a subtitle for the support section
        subtitle_label = ctk.CTkLabel(
            self.support_card, 
            text="🔗 Support Links", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Support links data
        support_links = [
            {"name": "⚡ YouTube Channel", "url": "https://www.youtube.com/@AsphaltCake/?sub_confirmation=1", "desc": "Subscribe for updates and tutorials"},
            {"name": "⚡ Discord Community", "url": "https://discord.gg/vKVBbyfHTD", "desc": "Join our community for support and discussions"},
            {"name": "⚡ PayPal Donation", "url": "https://www.paypal.com/paypalme/JLim862", "desc": "Support the development of this project"}
        ]
        
        for i, link_data in enumerate(support_links):
            # Create container for each link
            link_container = ctk.CTkFrame(self.support_card, fg_color="transparent")
            link_container.grid(row=i+1, column=0, padx=30, pady=12, sticky="ew")
            link_container.grid_columnconfigure(1, weight=1)
            
            # Link button
            link_button = ctk.CTkButton(
                link_container,
                text=link_data["name"],
                command=lambda url=link_data["url"]: self._open_link(url),
                font=ctk.CTkFont(size=14, weight="bold"),
                fg_color="#9013FE",      # Purple theme
                hover_color="#B347FF",   # Lighter purple on hover
                text_color="white",
                corner_radius=10,
                height=40,
                width=250
            )
            link_button.grid(row=0, column=0, padx=(0, 15), sticky="w")
            
            # Description label
            desc_label = ctk.CTkLabel(
                link_container,
                text=link_data["desc"],
                font=ctk.CTkFont(size=12),
                text_color="#CCCCCC",
                anchor="w"
            )
            desc_label.grid(row=0, column=1, sticky="ew")

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _open_link(self, url):
        """Opens a URL in the default web browser."""
        import webbrowser
        webbrowser.open(url)
        print(f"Opening link: {url}")

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")


class MiscView(ctk.CTkFrame):
    """
    A view (CTkFrame) to contain the Misc settings. Uses a standard tk.Canvas
    to create custom, scrollable content with cyan theme.
    """
    def __init__(self, master, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.app = master  # Reference to StarryNightApp to access settings
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#50E3C2", # Match the cyan background theme
            highlightthickness=0, # Remove border
            bd=0
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas,
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#6AEFD6"   # Lighter cyan border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0,
            anchor="nw",
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)

        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure)
        self.content_canvas.bind("<Configure>", self._on_canvas_configure)

        # --- Content Placement (Inside inner_frame) ---

        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame,
            text="⚙️ Misc Settings",
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, pady=(25, 30), sticky="n")

        # Misc Configuration Section with modern card design
        self.misc_config_card = ctk.CTkFrame(
            self.inner_frame,
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.misc_config_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30)
        self.misc_config_card.grid_columnconfigure((0, 1), weight=1, uniform="a")

        # Add a subtitle for the misc configuration section
        subtitle_label = ctk.CTkLabel(
            self.misc_config_card,
            text="⚙️ Misc Configuration",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")

        # Initialize UI components
        self._create_ui()
        self._load_settings()

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))

    # --- Scroll event handling ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120)) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")
    
    def _create_ui(self):
        """Create the main UI components."""
        # Enable/Disable toggle
        self.auto_select_enabled_var = tk.BooleanVar(value=self.app.settings.get("auto_select_rod_enabled", True))
        self.auto_select_enabled_var.trace_add("write", lambda *args: self._save_settings())
        
        # Auto Select Rod dropdown/toggle
        toggle_label = ctk.CTkLabel(
            self.misc_config_card,
            text="Enable Auto Select Rod:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E0E0E0"
        )
        toggle_label.grid(row=1, column=0, sticky="w", padx=(20, 10), pady=(10, 20))
        
        self.toggle_switch = ctk.CTkSwitch(
            self.misc_config_card,
            variable=self.auto_select_enabled_var,
            text="",
            fg_color="#404040",
            progress_color="#6AEFD6",
            button_color="#FFFFFF",
            button_hover_color="#E0E0E0"
        )
        self.toggle_switch.grid(row=1, column=1, sticky="w", padx=(10, 20), pady=(10, 20))
        
        # Options content frame (for flowchart)
        self.options_content_frame = ctk.CTkFrame(
            self.inner_frame,
            fg_color="transparent"
        )
        self.options_content_frame.grid(row=2, column=0, pady=(10, 20), padx=30, sticky="ew")
        self.options_content_frame.grid_columnconfigure(0, weight=1)
        
        # Create flowchart
        self._create_flowchart()
    
    def _create_flowchart(self):
        """Create the Auto Select Rod flowchart."""
        # Clear existing content
        for widget in self.options_content_frame.winfo_children():
            widget.destroy()
        
        # Create flowchart frame
        flowchart_frame = ctk.CTkFrame(
            self.options_content_frame,
            fg_color="#4A4A4A",
            corner_radius=10,
            border_width=1,
            border_color="#6A6A6A"
        )
        flowchart_frame.grid(row=0, column=0, pady=10, padx=10, sticky="ew")
        flowchart_frame.grid_columnconfigure(1, weight=1)
        
        # Flowchart title
        flowchart_title = ctk.CTkLabel(
            flowchart_frame,
            text="🎣 Auto Select Rod Sequence",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#E0E0E0"
        )
        flowchart_title.grid(row=0, column=0, columnspan=3, pady=(15, 10), sticky="n")
        
        # Initialize delay variables if they don't exist
        if not hasattr(self, 'misc_delay1_var'):
            self.misc_delay1_var = tk.DoubleVar(value=self.app.settings.get("auto_select_rod_delay1", 0.0))
            self.misc_delay1_var.trace_add("write", lambda *args: self.app.settings.update({"auto_select_rod_delay1": self.misc_delay1_var.get()}))
        if not hasattr(self, 'misc_delay2_var'):
            self.misc_delay2_var = tk.DoubleVar(value=self.app.settings.get("auto_select_rod_delay2", 1.0))
            self.misc_delay2_var.trace_add("write", lambda *args: self.app.settings.update({"auto_select_rod_delay2": self.misc_delay2_var.get()}))
        if not hasattr(self, 'misc_delay3_var'):
            self.misc_delay3_var = tk.DoubleVar(value=self.app.settings.get("auto_select_rod_delay3", 0.0))
            self.misc_delay3_var.trace_add("write", lambda *args: self.app.settings.update({"auto_select_rod_delay3": self.misc_delay3_var.get()}))
        
        # Step 1: Delay
        step1_frame = self._create_flowchart_step(
            flowchart_frame, 1, "⏱️", "Delay", self.misc_delay1_var, "#50E3C2"
        )
        
        # Arrow 1
        arrow1 = self._create_flowchart_arrow(flowchart_frame, 2)
        
        # Step 2: Equipment Bag
        step2_frame = self._create_flowchart_action_step(
            flowchart_frame, 3, "🎒", "Equipment Bag", "#4CAF50"
        )
        
        # Arrow 2
        arrow2 = self._create_flowchart_arrow(flowchart_frame, 4)
        
        # Step 3: Delay
        step3_frame = self._create_flowchart_step(
            flowchart_frame, 5, "⏱️", "Delay", self.misc_delay2_var, "#50E3C2"
        )
        
        # Arrow 3
        arrow3 = self._create_flowchart_arrow(flowchart_frame, 6)
        
        # Step 4: Fishing Rod
        step4_frame = self._create_flowchart_action_step(
            flowchart_frame, 7, "🎣", "Fishing Rod", "#2196F3"
        )
        
        # Arrow 4
        arrow4 = self._create_flowchart_arrow(flowchart_frame, 8)
        
        # Step 5: Delay
        step5_frame = self._create_flowchart_step(
            flowchart_frame, 9, "⏱️", "Delay", self.misc_delay3_var, "#50E3C2"
        )
    
    def _create_flowchart_step(self, parent, row, icon, label, delay_var, color):
        """Creates a flowchart step with adjustable delay (using entry box like in Cast)."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label and delay display
        text_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        text_frame.grid(row=0, column=1, sticky="ew", padx=5)
        text_frame.grid_columnconfigure(0, weight=1)
        
        main_label = ctk.CTkLabel(
            text_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=0, sticky="w")
        
        delay_label = ctk.CTkLabel(
            text_frame,
            text=f"({delay_var.get():.1f}s)",
            font=ctk.CTkFont(size=12),
            text_color="white"
        )
        delay_label.grid(row=1, column=0, sticky="w")
        
        # Delay controls
        controls_frame = ctk.CTkFrame(step_frame, fg_color="transparent")
        controls_frame.grid(row=0, column=2, padx=(5, 15), sticky="e")
        
        # Direct input entry
        def on_entry_change(*args):
            try:
                value = float(entry_var.get())
                delay_var.set(value)
                delay_label.configure(text=f"({value:.1f}s)")
            except ValueError:
                pass  # Ignore invalid input
            except tk.TclError:
                pass  # Widget was destroyed
        
        entry_var = tk.StringVar(value=f"{delay_var.get():.1f}")
        entry_var.trace_add("write", on_entry_change)
        
        delay_entry = ctk.CTkEntry(
            controls_frame,
            textvariable=entry_var,
            width=60,
            height=25,
            font=ctk.CTkFont(size=12),
            justify="center"
        )
        delay_entry.grid(row=0, column=0, padx=2)
        
        # Update entry when delay_var changes externally
        def update_entry(*args):
            entry_var.set(f"{delay_var.get():.1f}")
        
        delay_var.trace_add("write", update_entry)
        
        # Store references for updates
        delay_var.delay_label = delay_label
        delay_var.entry_var = entry_var
        
        return step_frame
    
    def _create_flowchart_action_step(self, parent, row, icon, label, color):
        """Creates a flowchart step for actions (no delay adjustment)."""
        step_frame = ctk.CTkFrame(
            parent,
            fg_color=color,
            corner_radius=8,
            height=60
        )
        step_frame.grid(row=row, column=0, columnspan=3, pady=5, padx=20, sticky="ew")
        step_frame.grid_columnconfigure(1, weight=1)
        step_frame.grid_propagate(False)
        
        # Icon
        icon_label = ctk.CTkLabel(
            step_frame,
            text=icon,
            font=ctk.CTkFont(size=20),
            text_color="white"
        )
        icon_label.grid(row=0, column=0, padx=(15, 5), sticky="w")
        
        # Label
        main_label = ctk.CTkLabel(
            step_frame,
            text=label,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="white"
        )
        main_label.grid(row=0, column=1, sticky="w", padx=5)
        
        return step_frame
    
    def _create_flowchart_arrow(self, parent, row):
        """Creates a downward arrow between flowchart steps."""
        arrow_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            height=30
        )
        arrow_frame.grid(row=row, column=0, columnspan=3, pady=2, sticky="ew")
        arrow_frame.grid_columnconfigure(0, weight=1)
        arrow_frame.grid_propagate(False)
        
        arrow_label = ctk.CTkLabel(
            arrow_frame,
            text="➕",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#CCCCCC"
        )
        arrow_label.grid(row=0, column=0, sticky="")
        
        return arrow_frame
    
    def _load_settings(self):
        """Load settings from app settings."""
        # Load delay settings
        if hasattr(self, 'misc_delay1_var'):
            self.misc_delay1_var.set(self.app.settings.get("auto_select_rod_delay1", 0.0))
        if hasattr(self, 'misc_delay2_var'):
            self.misc_delay2_var.set(self.app.settings.get("auto_select_rod_delay2", 1.0))
        if hasattr(self, 'misc_delay3_var'):
            self.misc_delay3_var.set(self.app.settings.get("auto_select_rod_delay3", 0.0))
        
        # Load enabled state
        self.auto_select_enabled_var.set(self.app.settings.get("auto_select_rod_enabled", True))
    
    def _save_settings(self):
        """Save settings to app settings."""
        self.app.settings["auto_select_rod_enabled"] = self.auto_select_enabled_var.get()
        if hasattr(self, 'misc_delay1_var'):
            self.app.settings["auto_select_rod_delay1"] = self.misc_delay1_var.get()
        if hasattr(self, 'misc_delay2_var'):
            self.app.settings["auto_select_rod_delay2"] = self.misc_delay2_var.get()
        if hasattr(self, 'misc_delay3_var'):
            self.app.settings["auto_select_rod_delay3"] = self.misc_delay3_var.get()


class BasicSettingsView(ctk.CTkFrame):
    """
    A view (CTkFrame) to contain the Basic Settings. Uses a standard tk.Canvas 
    to create custom, scrollable content.
    """
    def __init__(self, master, hotkey_manager, back_command, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)  # Allow vertical expansion

        self.hotkey_manager = hotkey_manager
        self.scroll_speed = 1 # Scroll 1 unit (line) per mouse wheel tick
        
        # --- 1. Main Content Canvas (The viewport for scrolling) ---
        self.content_canvas = tk.Canvas(
            self,
            bg="#4A90E2", # Match the blue background theme  
            highlightthickness=0, # Remove border
            bd=0 
        )
        self.content_canvas.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        # --- 2. Inner Frame (The actual content that moves) ---
        # Create a modern-looking container with rounded corners and contrasting background
        self.inner_frame = ctk.CTkFrame(
            self.content_canvas, 
            fg_color="#383838",      # Darker background so it's visible with rounded corners
            corner_radius=20,        # Keep the nice rounded corners
            border_width=3,          # Slightly thicker border to make it more visible
            border_color="#5BA3F5"   # Lighter blue border for definition
        )
        self.content_canvas_window = self.content_canvas.create_window(
            0, 0, 
            anchor="nw", 
            window=self.inner_frame
        )

        self.inner_frame.grid_columnconfigure(0, weight=1)
        
        # --- 3. Scroll Indicators Removed ---
        
        # Internal configuration binds
        self.inner_frame.bind("<Configure>", self._on_content_configure) 
        self.content_canvas.bind("<Configure>", self._on_canvas_configure) 
        
        # --- 4. Content Placement (Inside inner_frame) ---
        
        # Title with modern styling
        title_label = ctk.CTkLabel(
            self.inner_frame, 
            text="⚙️ Basic Settings", 
            font=ctk.CTkFont(size=28, weight="bold", family="Segoe UI"),
            text_color="#FFFFFF"
        )
        title_label.grid(row=0, column=0, columnspan=2, pady=(25, 30), sticky="n") 
        
        # Display Capture Configuration Section
        self.display_capture_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.display_capture_card.grid(row=1, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.display_capture_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Display Capture subtitle
        display_subtitle_label = ctk.CTkLabel(
            self.display_capture_card, 
            text="🖥️ Display Capture", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        display_subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Capture Mode dropdown
        capture_mode_label = ctk.CTkLabel(
            self.display_capture_card,
            text="📷 Capture Mode:",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#E0E0E0"
        )
        capture_mode_label.grid(row=1, column=0, sticky="w", padx=(20, 10), pady=(10, 20))
        
        self.capture_mode_dropdown = ctk.CTkOptionMenu(
            self.display_capture_card,
            values=["DXCAM", "MSS"],
            command=self._on_capture_mode_change,
            font=ctk.CTkFont(size=14),
            dropdown_font=ctk.CTkFont(size=14),
            width=120
        )
        # Initialize with current setting from centralized settings
        current_capture_mode = master.settings.get("shake_capture_mode", "DXCAM")
        self.capture_mode_dropdown.set(current_capture_mode)
        self.capture_mode_dropdown.grid(row=1, column=1, sticky="w", padx=(10, 20), pady=(10, 20))
        
        # Hotkey Configuration Section with modern card design
        options = ["Start/Stop", "Change Area", "Exit"]
        self.hotkey_widgets = {}

        # Create a card-like container for the settings
        self.settings_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",  # Lighter than main frame
            corner_radius=15,    # Rounded corners
            border_width=1,
            border_color="#5A5A5A"
        )
        self.settings_card.grid(row=2, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.settings_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the hotkey section
        subtitle_label = ctk.CTkLabel(
            self.settings_card, 
            text="⌨️ Hotkey Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        subtitle_label.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        for i, option_name in enumerate(options):
            # Add icons for each option
            icons = {"Start/Stop": "▶️", "Change Area": "🔄", "Exit": "❌"}
            icon = icons.get(option_name, "⚙️")
            
            label = ctk.CTkLabel(
                self.settings_card, 
                text=f"{icon} {option_name}", 
                anchor="w", 
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#F0F0F0"
            )
            label.grid(row=i+1, column=0, padx=(30, 15), pady=12, sticky="ew")

            dropdown_options = hotkey_manager.get_available_keys_for_option(option_name)
            
            initial_value = hotkey_manager.hotkeys.get(option_name, {}).get('key')
            
            dropdown = ctk.CTkOptionMenu(
                self.settings_card, 
                values=dropdown_options,
                command=partial(self._on_hotkey_select, option_name=option_name),
                fg_color="#4A90E2",      # Blue theme
                button_color="#3A7BD5",   # Darker blue for button
                button_hover_color="#5BA3F5",  # Lighter blue on hover
                dropdown_fg_color="#383838",  # Match container
                font=ctk.CTkFont(size=14, weight="bold"),
                corner_radius=10
            )
            dropdown.set(initial_value or "N/A")
            dropdown.grid(row=i+1, column=1, padx=(15, 30), pady=12, sticky="ew")
            
            self.hotkey_widgets[option_name] = dropdown

        # Hotbar Configuration Section with modern card design
        self.hotbar_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.hotbar_card.grid(row=3, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.hotbar_card.grid_columnconfigure((0, 1), weight=1, uniform="a")
        
        # Add a subtitle for the hotbar section
        hotbar_title = ctk.CTkLabel(
            self.hotbar_card, 
            text="⌨️ Hotbar Configuration", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        hotbar_title.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        # Hotbar options
        hotbar_options = ["Fishing Rod", "Equipment Bag"]
        hotbar_defaults = {"Fishing Rod": "1", "Equipment Bag": "2"}
        hotbar_icons = {"Fishing Rod": "🎣", "Equipment Bag": "🎒"}
        self.hotbar_widgets = {}
        
        # Number options (1-0, where 0 represents slot 10)
        number_options = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"]
        
        for i, option_name in enumerate(hotbar_options):
            icon = hotbar_icons.get(option_name, "⚙️")
            
            label = ctk.CTkLabel(
                self.hotbar_card, 
                text=f"{icon} {option_name}", 
                anchor="w", 
                font=ctk.CTkFont(size=16, weight="bold"),
                text_color="#F0F0F0"
            )
            label.grid(row=i+1, column=0, padx=(30, 15), pady=12, sticky="ew")

            # Load from settings or use default
            if option_name == "Fishing Rod":
                initial_value = self.master.settings.get("hotbar_fishing_rod", "1")
            elif option_name == "Equipment Bag":
                initial_value = self.master.settings.get("hotbar_equipment_bag", "2")
            else:
                initial_value = hotbar_defaults.get(option_name, "1")
            
            dropdown = ctk.CTkOptionMenu(
                self.hotbar_card, 
                values=number_options,
                command=lambda value, opt=option_name: self._on_hotbar_select(value, opt),
                fg_color="#4A90E2",      # Blue theme
                button_color="#3A7BD5",   # Darker blue for button
                button_hover_color="#5BA3F5",  # Lighter blue on hover
                dropdown_fg_color="#383838",  # Match container
                font=ctk.CTkFont(size=14, weight="bold"),
                corner_radius=10
            )
            dropdown.set(initial_value)
            dropdown.grid(row=i+1, column=1, padx=(15, 30), pady=12, sticky="ew")
            
            self.hotbar_widgets[option_name] = dropdown

        # GUI Settings Section with modern card design - use global settings
        self.gui_settings = {
            "Always On Top": tk.BooleanVar(value=master.global_gui_settings["Always On Top"]),
            "Auto Minimize GUI": tk.BooleanVar(value=master.global_gui_settings["Auto Minimize GUI"]),
            "Show Perfect Cast Overlay": tk.BooleanVar(value=master.global_gui_settings["Show Perfect Cast Overlay"]),
            "Show Fishing Overlay": tk.BooleanVar(value=master.global_gui_settings["Show Fishing Overlay"]),
            "Show Status Overlay": tk.BooleanVar(value=master.global_gui_settings["Show Status Overlay"])
        }
        
        # Create GUI settings card
        self.gui_settings_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.gui_settings_card.grid(row=4, column=0, sticky="ew", pady=(0, 25), padx=30) 
        self.gui_settings_card.grid_columnconfigure(0, weight=1)
        
        # GUI settings section title
        gui_settings_title = ctk.CTkLabel(
            self.gui_settings_card, 
            text="🎨 GUI Settings", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        gui_settings_title.grid(row=0, column=0, pady=(15, 10), sticky="n")
        
        # Add GUI setting options
        gui_options = ["Always On Top", "Auto Minimize GUI", "Show Perfect Cast Overlay", "Show Fishing Overlay", "Show Status Overlay"]
        gui_icons = {"Always On Top": "📌", "Auto Minimize GUI": "🔽", "Show Perfect Cast Overlay": "🎯", "Show Fishing Overlay": "🐟", "Show Status Overlay": "📊"}
        
        for i, option_name in enumerate(gui_options):
            icon = gui_icons.get(option_name, "⚙️")
            
            # Create container for each setting
            setting_container = ctk.CTkFrame(self.gui_settings_card, fg_color="transparent")
            setting_container.grid(row=i+1, column=0, padx=30, pady=8, sticky="ew")
            setting_container.grid_columnconfigure(0, weight=1)
            
            # Create checkbox and label
            checkbox = ctk.CTkCheckBox(
                setting_container,
                text=f"{icon} {option_name}",
                variable=self.gui_settings[option_name],
                command=lambda opt=option_name: self._on_gui_setting_change(opt),
                font=ctk.CTkFont(size=14, weight="bold"),
                text_color="#F0F0F0",
                fg_color="#4A90E2",
                hover_color="#5BA3F5",
                checkmark_color="white"
            )
            checkbox.grid(row=0, column=0, sticky="w")

        # Status Labels for Toggle Keys with modern card design - use global states
        self.toggle_statuses = {
            "Start/Stop": tk.BooleanVar(value=master.global_hotkey_states["Start/Stop"]),
            "Change Area": tk.BooleanVar(value=master.global_hotkey_states["Change Area"])
        }
        
        # Create status card
        self.status_card = ctk.CTkFrame(
            self.inner_frame, 
            fg_color="#454545",
            corner_radius=15,
            border_width=1,
            border_color="#5A5A5A"
        )
        self.status_card.grid(row=5, column=0, pady=(15, 25), padx=30, sticky="ew")
        
        # Status section title
        status_title = ctk.CTkLabel(
            self.status_card, 
            text="📊 Current Status", 
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#E0E0E0"
        )
        status_title.grid(row=0, column=0, columnspan=2, pady=(15, 10), sticky="n")
        
        for i, (key, var) in enumerate(self.toggle_statuses.items()):
            # Create a status indicator with modern styling
            status_container = ctk.CTkFrame(self.status_card, fg_color="transparent")
            status_container.grid(row=i+1, column=0, padx=30, pady=8, sticky="ew")
            status_container.grid_columnconfigure(1, weight=1)
            
            # Status icon
            status_icon = ctk.CTkLabel(
                status_container,
                text="➕" if key == "Start/Stop" else "⌨️",
                font=ctk.CTkFont(size=16)
            )
            status_icon.grid(row=0, column=0, padx=(0, 10), sticky="w")
            
            # Status label
            status_label = ctk.CTkLabel(
                status_container, 
                text=f"{key} is: OFF",
                font=ctk.CTkFont(size=14, weight="bold"),
                anchor="w"
            )
            status_label.grid(row=0, column=1, sticky="ew")
            
            var.trace_add("write", lambda name, index, mode, label=status_label, key=key: self._update_status_label(label, key))
            self._update_status_label(status_label, key)

        # Scroll indicators removed


    # --- Custom Scrolling and Indicator Logic ---
    
    # --- New public method for external scroll events ---
    def handle_scroll_event(self, event):
        """Called externally from the main app window binding."""
        self._on_scroll_event(event)

    def _on_content_configure(self, event):
        """Called when the size of the inner content frame changes."""
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
        c_w = self.content_canvas.winfo_width()
        self.content_canvas.itemconfigure(self.content_canvas_window, width=c_w)

    def _on_canvas_configure(self, event):
        """Called when the size of the canvas (viewport) changes."""
        self.content_canvas.itemconfigure(self.content_canvas_window, width=event.width)
        self.content_canvas.configure(scrollregion=self.content_canvas.bbox("all"))
    
    def _on_scroll_event(self, event):
        """
        Handles mouse wheel scrolling (Windows/macOS/Linux).
        """
        scroll_units = 0
        
        if event.delta:
            # Windows/macOS: delta is typically +/- 120. Normalize to +/- 1 unit.
            scroll_units = int(-1 * (event.delta / 120) * self.scroll_speed) 
        
        elif event.num in (4, 5):
            # Linux event: num is 4 (up) or 5 (down)
            scroll_direction = 1 if event.num == 4 else -1
            # yview_scroll expects negative for up, positive for down (Tkinter convention)
            scroll_units = -1 * scroll_direction * self.scroll_speed 
        
        if scroll_units != 0:
            self.content_canvas.yview_scroll(scroll_units, "units")

    # Scroll functions removed

    # --- Other Helper Methods (Unchanged) ---
    
    def _on_hotkey_select(self, new_key, option_name):
        """Called when a hotkey is selected from a dropdown."""
        self.hotkey_manager.update_hotkey(option_name, new_key)
        
        for name, dropdown in self.hotkey_widgets.items():
            if name in self.hotkey_manager.hotkeys:
                self_values = self.hotkey_manager.get_available_keys_for_option(name)
                dropdown.configure(values=self_values)
                if name == option_name:
                    dropdown.set(new_key)


    def _update_status_label(self, label, key):
        """Updates the text of a status label based on the toggle state with modern styling."""
        is_on = self.toggle_statuses[key].get()
        status_text = "⚡ ACTIVE" if is_on else "⚡ INACTIVE"
        color = "#00FF7F" if is_on else "#FF6B6B"  # Modern green/red colors
        label.configure(text=f"{key}: {status_text}", text_color=color)


    def _on_hotbar_select(self, selected_slot, option_name):
        """Called when a hotbar slot is selected from a dropdown."""
        print(f"Hotbar: {option_name} set to slot {selected_slot}")
        
        # Save the hotbar configuration to settings
        if option_name == "Fishing Rod":
            self.master.settings["hotbar_fishing_rod"] = selected_slot
        elif option_name == "Equipment Bag":
            self.master.settings["hotbar_equipment_bag"] = selected_slot

    def _on_gui_setting_change(self, setting_name):
        """Called when a GUI setting checkbox is changed."""
        setting_value = self.gui_settings[setting_name].get()
        print(f"GUI Setting: {setting_name} changed to {'ON' if setting_value else 'OFF'}")
        
        # Update global setting
        self.master.global_gui_settings[setting_name] = setting_value
        
        if setting_name == "Always On Top":
            # Apply always on top setting to the main window
            self.master.wm_attributes("-topmost", setting_value)
        elif setting_name == "Auto Minimize GUI":
            # Auto minimize setting will be checked in main app hotkey handler
            pass
        elif setting_name == "Show Perfect Cast Overlay":
            # Perfect cast overlay setting will be checked when creating cast visualizations
            pass
        elif setting_name == "Show Fishing Overlay":
            # Fishing overlay setting will be checked when creating fish visualizations
            pass
        elif setting_name == "Show Status Overlay":
            # Toggle status overlay visibility
            if self.master.global_gui_settings["Show Status Overlay"]:
                # Re-show overlay with current status and last used color
                if hasattr(self.master, 'current_status'):
                    last_color = getattr(self.master, 'status_color', 'white')
                    self.master._show_status_overlay(last_color)
            else:
                self.master._hide_status_overlay()

    def _on_capture_mode_change(self, selected_mode):
        """Called when the capture mode dropdown is changed."""
        print(f"Display Capture: Mode changed to {selected_mode}")
        
        # Update the centralized settings
        self.master.settings["shake_capture_mode"] = selected_mode
        
        # Log the change
        print(f"Shake capture mode updated to: {selected_mode}")

    def toggle_hotkey_state(self, option_name):
        """Legacy method - hotkey state is now managed globally by the main app."""
        # This method is now handled by the main app's _handle_hotkey_action
        # Just sync the display with global state
        if option_name in self.toggle_statuses:
            global_state = self.master.global_hotkey_states.get(option_name, False)
            self.toggle_statuses[option_name].set(global_state)


class HotkeyManager:
    """Manages the hotkey assignments and global keyboard binding."""
    
    def __init__(self, key_trigger_callback, app_quit_callback):
        self.all_keys = AVAILABLE_HOTKEYS
        self.key_trigger_callback = key_trigger_callback
        self.app_quit_callback = app_quit_callback 

        self.hotkeys = {
            "Start/Stop": {'key': 'F3', 'binding': None},
            "Change Area": {'key': 'F1', 'binding': None},
            "Exit": {'key': 'F4', 'binding': None} 
        }
        
        self.initialize_bindings()

    def initialize_bindings(self):
        """Binds all initial hotkeys using the keyboard library."""
        self._unhook_all()
        for option_name, data in self.hotkeys.items():
            self._bind_key(option_name, data['key'])

    def _unhook_all(self):
        """Unhooks all current keyboard bindings."""
        for option_name, data in self.hotkeys.items():
            if data['binding']:
                try:
                    keyboard.unhook(data['binding'])
                except (ValueError, KeyError) as e:
                    # Binding might already be unhooked or invalid - this is expected
                    print(f"    ⚡ Note: Hotkey already unhooked for {option_name}: {e}")
                except Exception as e:
                    print(f"    ⚠️ Warning: Unexpected error unhooking hotkey for {option_name}: {e}")
                data['binding'] = None

    def _bind_key(self, option_name, key):
        """Internal method to bind a single hotkey."""
        if self.hotkeys[option_name]['binding']:
            keyboard.unhook(self.hotkeys[option_name]['binding'])
            
        key_to_bind = key.lower() 

        if option_name == "Exit":
            def exit_callback(event):
                # Only trigger on key press, not release
                # Run in thread to avoid blocking keyboard hook
                if event.event_type == keyboard.KEY_DOWN:
                    import threading
                    threading.Thread(target=self.app_quit_callback, daemon=True).start()

            # keyboard.hook_key passes a single event object
            binding = keyboard.hook_key(key_to_bind, exit_callback, suppress=False)
        else:
            def general_callback(event):
                # Only trigger on key press, not release
                # Run in thread to avoid blocking keyboard hook
                if event.event_type == keyboard.KEY_DOWN:
                    import threading
                    threading.Thread(target=lambda: self.key_trigger_callback(option_name), daemon=True).start()

            try:
                # keyboard.hook_key passes a single event object
                binding = keyboard.hook_key(key_to_bind, general_callback, suppress=False)
            except Exception:
                binding = None

        self.hotkeys[option_name]['binding'] = binding


    def update_hotkey(self, option_name, new_key):
        """Changes the hotkey for a specific option and rebinds it."""
        if option_name in self.hotkeys:
            self.hotkeys[option_name]['key'] = new_key
            self._bind_key(option_name, new_key)

    def get_used_keys(self):
        """Returns a list of all currently assigned hotkeys."""
        return [data['key'] for data in self.hotkeys.values()]

    def get_available_keys_for_option(self, option_name):
        """Returns all keys not currently used by other options, sorted."""
        used_keys = self.get_used_keys()
        current_key = self.hotkeys.get(option_name, {}).get('key')
        
        available = [key for key in self.all_keys if key not in used_keys or key == current_key]
        
        return sorted(available)


class DualAreaSelector:
    """Full-screen overlay for selecting both Fish Box and Shake Box simultaneously"""

    def __init__(self, parent, screenshot, fish_box, shake_box, callback):
        self.callback = callback
        self.screenshot = screenshot

        # Create fullscreen window
        self.window = tk.Toplevel(parent)
        self.window.attributes('-fullscreen', True)
        self.window.attributes('-topmost', True)
        self.window.configure(cursor='cross')

        # Get screen dimensions
        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()

        # Convert PIL image to PhotoImage
        self.photo = ImageTk.PhotoImage(screenshot)

        # Create canvas with screenshot
        self.canvas = tk.Canvas(self.window, width=self.screen_width, height=self.screen_height, highlightthickness=0)
        self.canvas.pack()

        # Display frozen screenshot
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

        # Initialize Fish Box
        self.fish_box = fish_box.copy()
        self.fish_x1, self.fish_y1 = self.fish_box["x1"], self.fish_box["y1"]
        self.fish_x2, self.fish_y2 = self.fish_box["x2"], self.fish_box["y2"]

        # Initialize Shake Box
        self.shake_box = shake_box.copy()
        self.shake_x1, self.shake_y1 = self.shake_box["x1"], self.shake_box["y1"]
        self.shake_x2, self.shake_y2 = self.shake_box["x2"], self.shake_box["y2"]

        # Drawing state
        self.dragging = False
        self.active_box = None  # 'fish' or 'shake'
        self.drag_corner = None
        self.resize_threshold = 10

        # Create Fish Box (Blue)
        self.fish_rect = self.canvas.create_rectangle(
            self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2,
            outline='#2196F3',
            width=2,
            fill='#2196F3',
            stipple='gray50',
            tags='fish_box'
        )

        # Fish Box label
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        fish_label_y = self.fish_y1 - 20
        self.fish_label = self.canvas.create_text(
            fish_label_x, fish_label_y,
            text="Fish Box",
            font=("Arial", 12, "bold"),
            fill='#2196F3',
            tags='fish_label'
        )

        # Create Shake Box (Red)
        self.shake_rect = self.canvas.create_rectangle(
            self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2,
            outline='#f44336',
            width=2,
            fill='#f44336',
            stipple='gray50',
            tags='shake_box'
        )

        # Shake Box label
        shake_label_x = self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2
        shake_label_y = self.shake_y1 - 20
        self.shake_label = self.canvas.create_text(
            shake_label_x, shake_label_y,
            text="Shake Box",
            font=("Arial", 12, "bold"),
            fill='#f44336',
            tags='shake_label'
        )

        # Create corner handles for both boxes
        self.fish_handles = []
        self.shake_handles = []
        self.create_all_handles()

        # Zoom window
        self.zoom_window_size = 150
        self.zoom_factor = 4
        self.zoom_rect = None
        self.zoom_image_id = None

        # Bind events
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<Motion>', self.on_mouse_move)
        self.window.bind('<Escape>', lambda e: self.finish_selection())
        self.window.bind('<Return>', lambda e: self.finish_selection())

    def create_all_handles(self):
        """Create corner handles for both boxes"""
        self.create_handles_for_box('fish')
        self.create_handles_for_box('shake')

    def create_handles_for_box(self, box_type):
        """Create corner handles for a specific box"""
        handle_size = 12
        corner_marker_size = 3

        if box_type == 'fish':
            x1, y1, x2, y2 = self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2
            color = '#2196F3'
            handles_list = self.fish_handles
        else:  # shake
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2
            color = '#f44336'
            handles_list = self.shake_handles

        corners = [
            (x1, y1, 'nw'),
            (x2, y1, 'ne'),
            (x1, y2, 'sw'),
            (x2, y2, 'se')
        ]

        # Delete old handles
        for handle in handles_list:
            self.canvas.delete(handle)
        handles_list.clear()

        # Create new handles
        for x, y, corner in corners:
            # Outer handle
            handle = self.canvas.create_rectangle(
                x - handle_size, y - handle_size,
                x + handle_size, y + handle_size,
                fill='',
                outline=color,
                width=2,
                tags=f'{box_type}_handle_{corner}'
            )
            handles_list.append(handle)

            # Corner marker
            corner_marker = self.canvas.create_rectangle(
                x - corner_marker_size, y - corner_marker_size,
                x + corner_marker_size, y + corner_marker_size,
                fill='red',
                outline='white',
                width=1,
                tags=f'{box_type}_corner_{corner}'
            )
            handles_list.append(corner_marker)

            # Crosshair
            line1 = self.canvas.create_line(
                x - handle_size, y, x + handle_size, y,
                fill='yellow',
                width=1,
                tags=f'{box_type}_cross_{corner}'
            )
            line2 = self.canvas.create_line(
                x, y - handle_size, x, y + handle_size,
                fill='yellow',
                width=1,
                tags=f'{box_type}_cross_{corner}'
            )
            handles_list.append(line1)
            handles_list.append(line2)

    def get_corner_at_position(self, x, y, box_type):
        """Determine which corner is near the cursor for a specific box"""
        if box_type == 'fish':
            x1, y1, x2, y2 = self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2
        else:  # shake
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2

        corners = {
            'nw': (x1, y1),
            'ne': (x2, y1),
            'sw': (x1, y2),
            'se': (x2, y2)
        }

        for corner, (cx, cy) in corners.items():
            if abs(x - cx) < self.resize_threshold and abs(y - cy) < self.resize_threshold:
                return corner

        return None

    def is_inside_box(self, x, y, box_type):
        """Check if point is inside a specific box"""
        if box_type == 'fish':
            return self.fish_x1 < x < self.fish_x2 and self.fish_y1 < y < self.fish_y2
        else:  # shake
            return self.shake_x1 < x < self.shake_x2 and self.shake_y1 < y < self.shake_y2

    def on_mouse_down(self, event):
        """Handle mouse button press"""
        self.drag_start_x = event.x
        self.drag_start_y = event.y

        # Check Fish Box first
        corner = self.get_corner_at_position(event.x, event.y, 'fish')
        if corner:
            self.dragging = True
            self.active_box = 'fish'
            self.drag_corner = corner
            return

        if self.is_inside_box(event.x, event.y, 'fish'):
            self.dragging = True
            self.active_box = 'fish'
            self.drag_corner = 'move'
            return

        # Check Shake Box
        corner = self.get_corner_at_position(event.x, event.y, 'shake')
        if corner:
            self.dragging = True
            self.active_box = 'shake'
            self.drag_corner = corner
            return

        if self.is_inside_box(event.x, event.y, 'shake'):
            self.dragging = True
            self.active_box = 'shake'
            self.drag_corner = 'move'
            return

    def on_mouse_drag(self, event):
        """Handle mouse drag"""
        if not self.dragging or not self.active_box:
            return

        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y

        if self.active_box == 'fish':
            if self.drag_corner == 'move':
                self.fish_x1 += dx
                self.fish_y1 += dy
                self.fish_x2 += dx
                self.fish_y2 += dy
            elif self.drag_corner == 'nw':
                self.fish_x1 = event.x
                self.fish_y1 = event.y
            elif self.drag_corner == 'ne':
                self.fish_x2 = event.x
                self.fish_y1 = event.y
            elif self.drag_corner == 'sw':
                self.fish_x1 = event.x
                self.fish_y2 = event.y
            elif self.drag_corner == 'se':
                self.fish_x2 = event.x
                self.fish_y2 = event.y

            if self.fish_x1 > self.fish_x2:
                self.fish_x1, self.fish_x2 = self.fish_x2, self.fish_x1
            if self.fish_y1 > self.fish_y2:
                self.fish_y1, self.fish_y2 = self.fish_y2, self.fish_y1

        else:  # shake
            if self.drag_corner == 'move':
                self.shake_x1 += dx
                self.shake_y1 += dy
                self.shake_x2 += dx
                self.shake_y2 += dy
            elif self.drag_corner == 'nw':
                self.shake_x1 = event.x
                self.shake_y1 = event.y
            elif self.drag_corner == 'ne':
                self.shake_x2 = event.x
                self.shake_y1 = event.y
            elif self.drag_corner == 'sw':
                self.shake_x1 = event.x
                self.shake_y2 = event.y
            elif self.drag_corner == 'se':
                self.shake_x2 = event.x
                self.shake_y2 = event.y

            if self.shake_x1 > self.shake_x2:
                self.shake_x1, self.shake_x2 = self.shake_x2, self.shake_x1
            if self.shake_y1 > self.shake_y2:
                self.shake_y1, self.shake_y2 = self.shake_y2, self.shake_y1

        self.update_boxes()
        self.show_zoom(event.x, event.y)

        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_up(self, event):
        """Handle mouse button release"""
        self.dragging = False
        self.active_box = None
        self.drag_corner = None

    def on_mouse_move(self, event):
        """Handle mouse movement"""
        # Check which box cursor is over
        fish_corner = self.get_corner_at_position(event.x, event.y, 'fish')
        shake_corner = self.get_corner_at_position(event.x, event.y, 'shake')

        if fish_corner or shake_corner:
            corner = fish_corner or shake_corner
            cursors = {'nw': 'top_left_corner', 'ne': 'top_right_corner',
                      'sw': 'bottom_left_corner', 'se': 'bottom_right_corner'}
            self.window.configure(cursor=cursors.get(corner, 'cross'))
        elif self.is_inside_box(event.x, event.y, 'fish') or self.is_inside_box(event.x, event.y, 'shake'):
            self.window.configure(cursor='fleur')
        else:
            self.window.configure(cursor='cross')

        self.show_zoom(event.x, event.y)

    def show_zoom(self, x, y):
        """Display mini zoom window"""
        if self.zoom_rect:
            self.canvas.delete(self.zoom_rect)
        if self.zoom_image_id:
            self.canvas.delete(self.zoom_image_id)

        zoom_src_size = self.zoom_window_size // self.zoom_factor
        x1_src = max(0, x - zoom_src_size // 2)
        y1_src = max(0, y - zoom_src_size // 2)
        x2_src = min(self.screen_width, x1_src + zoom_src_size)
        y2_src = min(self.screen_height, y1_src + zoom_src_size)

        cropped = self.screenshot.crop((x1_src, y1_src, x2_src, y2_src))
        zoomed = cropped.resize((self.zoom_window_size, self.zoom_window_size), Image.NEAREST)

        draw = ImageDraw.Draw(zoomed)
        center = self.zoom_window_size // 2
        crosshair_size = 10
        draw.line([(center - crosshair_size, center), (center + crosshair_size, center)], fill='red', width=2)
        draw.line([(center, center - crosshair_size), (center, center + crosshair_size)], fill='red', width=2)

        self.zoom_photo = ImageTk.PhotoImage(zoomed)

        zoom_x = x + 30
        zoom_y = y + 30

        if zoom_x + self.zoom_window_size > self.screen_width:
            zoom_x = x - self.zoom_window_size - 30
        if zoom_y + self.zoom_window_size > self.screen_height:
            zoom_y = y - self.zoom_window_size - 30

        self.zoom_rect = self.canvas.create_rectangle(
            zoom_x, zoom_y,
            zoom_x + self.zoom_window_size, zoom_y + self.zoom_window_size,
            fill='black',
            outline='white',
            width=2
        )

        self.zoom_image_id = self.canvas.create_image(
            zoom_x, zoom_y,
            image=self.zoom_photo,
            anchor='nw'
        )

    def update_boxes(self):
        """Update both boxes and their labels"""
        # Update Fish Box
        self.canvas.coords(self.fish_rect, self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2)
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        fish_label_y = self.fish_y1 - 20
        self.canvas.coords(self.fish_label, fish_label_x, fish_label_y)

        # Update Shake Box
        self.canvas.coords(self.shake_rect, self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2)
        shake_label_x = self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2
        shake_label_y = self.shake_y1 - 20
        self.canvas.coords(self.shake_label, shake_label_x, shake_label_y)

        # Update handles
        self.create_all_handles()

    def finish_selection(self):
        """Close and return both box coordinates"""
        fish_coords = {
            "x1": int(self.fish_x1),
            "y1": int(self.fish_y1),
            "x2": int(self.fish_x2),
            "y2": int(self.fish_y2)
        }
        shake_coords = {
            "x1": int(self.shake_x1),
            "y1": int(self.shake_y1),
            "x2": int(self.shake_x2),
            "y2": int(self.shake_y2)
        }
        self.window.destroy()
        self.callback(fish_coords, shake_coords)


# ===== AUTO-SUBSCRIBE TO YOUTUBE FUNCTIONS =====
YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@AsphaltCake?sub_confirmation=1"
input_blocked = False

def block_all_inputs():
    """Block all keyboard inputs during automation"""
    global input_blocked
    input_blocked = True
    
    def suppress_key(event):
        if input_blocked:
            return False
        return True
    
    keyboard.hook(suppress_key)

def unblock_all_inputs():
    """Unblock all keyboard inputs after automation"""
    global input_blocked
    input_blocked = False
    keyboard.unhook_all()

def wait_for_browser_load(timeout=10):
    """Wait for browser window to appear and be ready"""
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        def window_enum_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd):
                window_text = win32gui.GetWindowText(hwnd)
                browser_keywords = ['Chrome', 'Firefox', 'Edge', 'Opera', 'Brave', 'YouTube']
                if any(keyword.lower() in window_text.lower() for keyword in browser_keywords):
                    windows.append((hwnd, window_text))
            return True
        
        windows = []
        win32gui.EnumWindows(window_enum_callback, windows)
        
        if windows:
            return True
        
        time.sleep(0.1)
    
    return False

def focus_browser_window():
    """Find and focus the browser window"""
    def window_enum_callback(hwnd, windows):
        if win32gui.IsWindowVisible(hwnd):
            window_text = win32gui.GetWindowText(hwnd)
            browser_keywords = ['Chrome', 'Firefox', 'Edge', 'Opera', 'Brave', 'YouTube']
            if any(keyword.lower() in window_text.lower() for keyword in browser_keywords):
                windows.append((hwnd, window_text))
        return True
    
    windows = []
    win32gui.EnumWindows(window_enum_callback, windows)
    
    if windows:
        hwnd = windows[0][0]
        try:
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.SetForegroundWindow(hwnd)
            return True
        except Exception as e:
            print(f"⚠️ Window focus error: {e}")
            return False
    return False

def auto_subscribe_to_youtube():
    """Execute auto-subscribe sequence to YouTube channel"""
    print("\n=== AUTO-SUBSCRIBE TO YOUTUBE ===")
    
    try:
        # Open YouTube channel
        print(f"🌐 Opening YouTube channel...")
        webbrowser.open(YOUTUBE_CHANNEL_URL)
        
        # Wait for browser to load
        if not wait_for_browser_load(timeout=10):
            print("⚠️ Browser didn't load, skipping auto-subscribe")
            return False
        
        # Wait for subscribe dialog
        print("⏳ Waiting for subscribe confirmation dialog...")
        time.sleep(3.5)
        
        # Try to focus browser
        print("🖱️ Focusing browser window...")
        focus_start = time.time()
        focused = False
        
        while time.time() - focus_start < 5:
            if focus_browser_window():
                focused = True
                break
            time.sleep(0.5)
        
        if not focused:
            print("⚠️ Could not focus browser, skipping auto-subscribe")
            return False
        
        time.sleep(0.3)
        
        # Block user input
        print("🔒 Blocking user input...")
        block_all_inputs()
        time.sleep(0.5)
        
        # Navigate and subscribe
        print("🧭 Navigating to Subscribe button...")
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.press('tab')
        time.sleep(0.2)
        pyautogui.press('enter')
        time.sleep(0.5)
        
        # Close tab
        print("❌ Closing YouTube tab...")
        pyautogui.hotkey('ctrl', 'w')
        time.sleep(0.3)
        
        print("✅ Auto-subscribe completed!")
        return True
        
    except Exception as e:
        print(f"❌ Auto-subscribe error: {e}")
        return False
    finally:
        unblock_all_inputs()


class TermsOfUseDialog(ctk.CTkToplevel):
    """
    Animated Terms of Use dialog with starry space background and comet theme.
    Shown on first launch - user must accept before the main app can be used.
    """
    # Animation constants for easy tuning
    MAX_COMETS = 20  # Maximum comets on screen at once
    COMET_SPAWN_CHANCE = 0.15  # 15% chance per frame to spawn a comet
    COMET_BURST_CHANCE = 0.05  # 5% chance per frame for comet burst
    COMET_BURST_MIN = 3  # Minimum comets in a burst
    COMET_BURST_MAX = 6  # Maximum comets in a burst
    FADE_IN_DURATION = 15  # Frames for comet fade-in
    STARS_PER_PIXEL_AREA = 25000  # One star per this many pixels (reduced star count for better performance)
    MIN_STARS = 50  # Minimum star count
    MAX_STARS = 200  # Maximum star count
    
    def __init__(self, parent):
        super().__init__(parent)
        
        self.title("IRUS COMET - Terms of Use")
        self.geometry("900x700")
        self.resizable(True, True)
        self.minsize(600, 500)  # Set minimum window size to prevent content from being cut off
        
        # Make it modal and center it
        self.transient(parent)
        self.grab_set()
        
        # Result flag
        self.accepted = False
        self.is_closing = False
        
        # Animation state
        self.stars = []
        self.animation_comets = []  # Renamed from self.comets to avoid conflict with currency
        self.nebula_particles = []  # Add nebula dust particles
        self.animation_running = True
        
        # Create main canvas for animated background
        self.canvas = tk.Canvas(self, bg="#0a0e27", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        
        # Create stars with varied colors and sizes
        star_colors = [
            (180, 220, 255),  # Blue-white
            (200, 180, 255),  # Purple-white
            (255, 250, 240),  # Warm white
            (150, 200, 255),  # Cool blue
        ]
        
        for _ in range(80):
            x = random.randint(0, 900)
            y = random.randint(0, 700)
            size = random.choice([1, 1, 2, 2, 3, 4])  # Varied sizes, smaller more common
            brightness = random.uniform(0.3, 1.0)
            base_color = random.choice(star_colors)
            
            star = {
                'id': self.canvas.create_oval(x, y, x+size, y+size, 
                                              fill=f"#{int(base_color[0]*brightness):02x}{int(base_color[1]*brightness):02x}{int(base_color[2]*brightness):02x}",
                                              outline=""),
                'x': x, 'y': y, 'size': size,
                'twinkle_phase': random.uniform(0, 6.28),
                'twinkle_speed': random.uniform(0.02, 0.1),
                'base_brightness': brightness,
                'base_color': base_color,
                'pulse_offset': random.uniform(0, 3.14)  # For varied pulsing
            }
            self.stars.append(star)
        
        # Create comets (shooting stars)
        for _ in range(3):
            self._spawn_comet()
        
        # Header with animated glow effect
        self.header_bg = self.canvas.create_rectangle(0, 0, 900, 100, fill="#0f1535", outline="")
        
        # Animated title with glow
        self.title_text = self.canvas.create_text(
            450, 50,
            text="✨ IRUS COMET ✨",
            font=("Arial", 32, "bold"),
            fill="#00d4ff"
        )
        self.title_glow = self.canvas.create_text(
            450, 50,
            text="✨ IRUS COMET ✨",
            font=("Arial", 33, "bold"),
            fill="#00d4ff",
            state="hidden"
        )
        self.glow_phase = 0
        
        # Draw border rectangle directly on canvas (no fill, just outline)
        content_y = 120
        self.content_border = self.canvas.create_rectangle(
            30, content_y, 870, content_y + 440,
            fill="",  # No fill - completely transparent!
            outline="#00d4ff", 
            width=3
        )
        
        # Create a clipping rectangle for the scrollable content area
        # This prevents text from showing outside the content box
        self.content_clip_y1 = content_y + 60  # Below the title
        self.content_clip_y2 = content_y + 440  # Bottom of content area
        
        # Draw terms title directly on canvas
        self.terms_title_text = self.canvas.create_text(
            450, content_y + 30,
            text="📜 TERMS OF USE 📜",
            font=("Arial", 20, "bold"),
            fill="#00d4ff"
        )
        
        # Load the full Terms of Use content from file
        terms_content = """        +-----------------------------------------------------------------------+
        │                    IRUS COMET - TERMS OF USE                          │
        │                         by AsphaltCake                                │
        +-----------------------------------------------------------------------+

By using IRUS COMET, you agree to the following terms and conditions:

══════════════════════════════════════════════════
⚡ 1. USAGE
══════════════════════════════════════════════════

✅ YOU ARE ALLOWED TO:
   ✓ Use IRUS COMET for personal purposes
   ✓ Study and reverse engineer the code for educational purposes
   ✓ Modify the code for your own personal use
   ✓ Share your modifications with proper attribution

❌ YOU ARE NOT ALLOWED TO:
   ✗ Repackage or redistribute this software as your own
   ✗ Remove or modify credits to the original author (AsphaltCake)
   ✗ Sell or monetize this software or its derivatives
   ✗ Claim ownership of the original codebase

⚡ IF YOU SHARE MODIFICATIONS:
   ⚠️ You MUST credit AsphaltCake as the original author
   ⚠️ You MUST link to the original source (YOUTUBE CHANNEL)
   ⚠️ You MUST clearly indicate what changes you made
   ⚠️ You may NOT claim the entire work as your own creation

══════════════════════════════════════════════════
⚡ 2. INTENDED USE & GAME COMPLIANCE
══════════════════════════════════════════════════

⚠️ This software is designed for ROBLOX FISCH
⚠️ You are responsible for ensuring your use complies with the game's
  Terms of Service and any applicable rules
⚠️ The author is NOT responsible for any account actions (bans, suspensions)
  resulting from your use of this software
⚠️ Use at your own risk - (automation allowed by the game rules)

══════════════════════════════════════════════════
⚡ 3. YOUTUBE CHANNEL SUBSCRIPTION
══════════════════════════════════════════════════

By using IRUS COMET, you agree that:
• This software will automatically subscribe to my YouTube channel
• This is a form of support for the free software you're receiving
• You are encouraged (but not required) to subscribe and support the channel
• YouTube Channel: https://www.youtube.com/@AsphaltCake

══════════════════════════════════════════════════
⚡ 4. LIABILITY DISCLAIMER
══════════════════════════════════════════════════

• The author is NOT liable for any damages, or account issues
• No guarantee of functionality, compatibility, or performance
• Use of this software is entirely at your own risk

══════════════════════════════════════════════════
⚡ 5. PRIVACY & DATA COLLECTION
══════════════════════════════════════════════════

• This software stores configuration data locally on your device
• No personal data is collected or transmitted to external servers
• Your settings and preferences are stored in a local config file only

══════════════════════════════════════════════════
⚡ 6. CREDITS & ATTRIBUTION
══════════════════════════════════════════════════

Original Author: AsphaltCake
YouTube: https://www.youtube.com/@AsphaltCake
Discord: https://discord.gg/vKVBbyfHTD

If you share, modify, or redistribute this software:
📋 REQUIRED: Credit "AsphaltCake" as the original creator
📋 REQUIRED: Link to the original source
📋 REQUIRED: Indicate any changes you made
🚫 FORBIDDEN: Claim the entire work as your own

══════════════════════════════════════════════════
⚡ 7. TERMS UPDATES
══════════════════════════════════════════════════

• These terms may be updated at any time
• Continued use of the software constitutes acceptance of updated terms

══════════════════════════════════════════════════
✅ 8. ACCEPTANCE
══════════════════════════════════════════════════

By clicking "I Accept" below, you acknowledge that you have read,
understood, and agree to these Terms of Use.

If you do not agree to these terms, click "Decline" and do not use this
software.

══════════════════════════════════════════════════

🎣 Thank you for using IRUS COMET! 🎣"""
        
        # Draw text content directly on canvas with scrolling support
        self.scroll_offset = 0  # Track vertical scroll position
        self.content_y_start = content_y + 70  # Starting Y position for text
        
        self.terms_content_text = self.canvas.create_text(
            450, self.content_y_start,
            text=terms_content,
            font=("Consolas", 9),
            fill="#b8d4f1",
            width=780,
            anchor="n",  # Anchor to top (north) for scrolling
            justify="left"
        )
        
        # Bind mouse wheel and arrow keys for scrolling
        self.canvas.bind("<MouseWheel>", self._on_scroll)
        self.canvas.bind("<Button-4>", self._on_scroll)  # Linux scroll up
        self.canvas.bind("<Button-5>", self._on_scroll)  # Linux scroll down
        self.bind("<Up>", self._on_key_scroll)
        self.bind("<Down>", self._on_key_scroll)
        self.bind("<Prior>", self._on_key_scroll)  # Page Up
        self.bind("<Next>", self._on_key_scroll)   # Page Down
        
        # Add scroll indicator at bottom of content area
        self.scroll_hint = self.canvas.create_text(
            450, content_y + 510,
            text="💡 Scroll with mouse wheel or arrow keys 💡",
            font=("Arial", 9, "italic"),
            fill="#00d4ff"
        )
        
        # Create masking rectangles to hide scrolled text outside content area
        # Top mask - covers area between header and content top
        self.top_mask = self.canvas.create_rectangle(
            0, 0, 900, content_y + 60,
            fill="#0a0e27", outline=""
        )
        # Bottom mask - covers area between content bottom and buttons
        self.bottom_mask = self.canvas.create_rectangle(
            0, content_y + 440, 900, 700,
            fill="#0a0e27", outline=""
        )
        
        # Raise UI elements above masks
        self.canvas.tag_raise(self.header_bg)
        self.canvas.tag_raise(self.title_text)
        self.canvas.tag_raise(self.title_glow)
        self.canvas.tag_raise(self.content_border)
        self.canvas.tag_raise(self.terms_title_text)
        self.canvas.tag_raise(self.scroll_hint)
        
        # Bottom control panel (always visible, pinned to bottom)
        self.bottom_panel = ctk.CTkFrame(
            self.canvas,
            fg_color=("#0f1535", "#0a0e27"),
            corner_radius=0
        )
        # Initial position - place lower to ensure visibility
        # The _update_layout calls will properly position it once window is fully rendered
        # Increased height to 100px to fit checkbox + buttons comfortably
        self.bottom_window = self.canvas.create_window(450, 600, window=self.bottom_panel, width=900, height=100)
        
        # Checkbox with glow effect
        self.accept_var = tk.BooleanVar(value=False)
        checkbox_container = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        checkbox_container.pack(pady=(10, 5))
        
        self.accept_checkbox = ctk.CTkCheckBox(
            checkbox_container,
            text="I have read and accept the Terms of Use",
            variable=self.accept_var,
            font=("Arial", 13, "bold"),
            command=self._on_checkbox_toggle,
            fg_color=("#00d4ff", "#00d4ff"),
            hover_color=("#0099cc", "#0099cc"),
            border_color=("#00d4ff", "#00d4ff"),
            text_color=("#b8d4f1", "#88b4e3")
        )
        self.accept_checkbox.pack()
        
        # Buttons with glowing effect
        button_container = ctk.CTkFrame(self.bottom_panel, fg_color="transparent")
        button_container.pack(fill="x", padx=150, pady=(0, 10))
        button_container.grid_columnconfigure(0, weight=1)
        button_container.grid_columnconfigure(1, weight=1)
        
        self.accept_button = ctk.CTkButton(
            button_container,
            text="✅ Accept & Launch",
            font=("Arial", 14, "bold"),
            command=self._on_accept,
            state="disabled",
            fg_color=("#00d4ff", "#0099cc"),
            hover_color=("#0099cc", "#007799"),
            text_color=("#ffffff", "#ffffff"),
            height=40,
            corner_radius=10,
            border_width=2,
            border_color=("#00d4ff", "#0099cc")
        )
        self.accept_button.grid(row=0, column=0, padx=(0, 10), sticky="ew")
        
        self.decline_button = ctk.CTkButton(
            button_container,
            text="❌ Decline & Exit",
            font=("Arial", 14, "bold"),
            command=self._on_decline,
            fg_color=("#cc0000", "#990000"),
            hover_color=("#990000", "#660000"),
            text_color=("#ffffff", "#ffffff"),
            height=40,
            corner_radius=10,
            border_width=2,
            border_color=("#ff4444", "#cc0000")
        )
        self.decline_button.grid(row=0, column=1, padx=(10, 0), sticky="ew")
        
        # Center the dialog on screen
        self.update_idletasks()
        width = 900
        height = 700
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Force an immediate layout update with known dimensions
        self._update_layout(width, height)
        
        # Handle window close (treat as decline)
        self.protocol("WM_DELETE_WINDOW", self._on_decline)
        
        # Handle resize
        self.bind("<Configure>", self._on_resize)
        
        # Trigger initial layout updates to ensure proper positioning
        # Optimized: Use progressive layout updates with cleanup
        self._layout_update_count = 0
        
        # Start animations
        self._animate()
        
        # Start layout updates after methods are defined
        self._schedule_layout_update()
    
    def _schedule_layout_update(self):
        """Optimized layout update scheduler to replace multiple .after() calls."""
        if self._layout_update_count >= 5:
            return  # Stop after 5 attempts
        
        delays = [1, 50, 150, 300, 500]
        delay = delays[self._layout_update_count]
        
        def update_and_schedule():
            try:
                width = self.winfo_width()
                height = self.winfo_height()
                print(f"🔧 Layout update #{self._layout_update_count + 1}: {width}x{height}")
                self._update_layout(width, height)
                self._layout_update_count += 1
                if self._layout_update_count < 5:
                    self._schedule_layout_update()
                else:
                    print("✅ Layout updates complete")
            except Exception as e:
                print(f"⚠️ Layout update error: {e}")
                import traceback
                traceback.print_exc()
        
        self.after(delay, update_and_schedule)
    
    def _on_scroll(self, event):
        """Handle mouse wheel scrolling"""
        # Determine scroll direction
        if event.num == 5 or event.delta < 0:  # Scroll down
            delta = 20
        elif event.num == 4 or event.delta > 0:  # Scroll up
            delta = -20
        else:
            return
        
        # Update scroll offset with bounds checking
        self.scroll_offset += delta
        
        # Get text bounds to limit scrolling
        bbox = self.canvas.bbox(self.terms_content_text)
        if bbox:
            text_height = bbox[3] - bbox[1]
            # Calculate visible area from clip bounds
            content_area_height = self.content_clip_y2 - self.content_clip_y1
            max_scroll = max(0, text_height - content_area_height + 20)  # +20 for padding
            
            # Clamp scroll offset
            self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
        
        # Move the text (use dynamic center X)
        center_x = self.winfo_width() / 2
        new_y = self.content_y_start - self.scroll_offset
        self.canvas.coords(self.terms_content_text, center_x, new_y)
    
    def _on_key_scroll(self, event):
        """Handle keyboard scrolling (arrow keys, page up/down)"""
        if event.keysym == "Up":
            delta = -20
        elif event.keysym == "Down":
            delta = 20
        elif event.keysym == "Prior":  # Page Up
            delta = -100
        elif event.keysym == "Next":   # Page Down
            delta = 100
        else:
            return
        
        # Update scroll offset with bounds checking
        self.scroll_offset += delta
        
        # Get text bounds to limit scrolling
        bbox = self.canvas.bbox(self.terms_content_text)
        if bbox:
            text_height = bbox[3] - bbox[1]
            # Calculate visible area from clip bounds
            content_area_height = self.content_clip_y2 - self.content_clip_y1
            max_scroll = max(0, text_height - content_area_height + 20)
            
            # Clamp scroll offset
            self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))
        
        # Move the text (use dynamic center X)
        center_x = self.winfo_width() / 2
        new_y = self.content_y_start - self.scroll_offset
        self.canvas.coords(self.terms_content_text, center_x, new_y)
    
    def _spawn_comet(self):
        """Spawn a new comet (shooting star) with varied colors and speeds"""
        if len(self.animation_comets) >= self.MAX_COMETS:
            return
        
        # Get current canvas dimensions
        canvas_width = self.canvas.winfo_width() or 900
        canvas_height = self.canvas.winfo_height() or 700
        
        # Ensure minimum canvas size for calculations
        canvas_width = max(canvas_width, 900)
        canvas_height = max(canvas_height, 700)
        
        # Varied comet types with more options for visual variety
        comet_type = random.choice(['fast', 'fast', 'medium', 'medium', 'slow', 'arc', 'diagonal', 'streak'])
        
        if comet_type == 'fast':
            x = random.randint(-80, canvas_width // 2)
            y = random.randint(80, max(120, canvas_height // 3))
            vx = random.uniform(8, 14)
            vy = random.uniform(2, 5)
            trail_length = 15
            colors = [(100, 200, 255), (150, 220, 255), (200, 240, 255)]  # Blue streak
        elif comet_type == 'medium':
            x = random.randint(-50, int(canvas_width * 0.8))
            y = random.randint(100, max(150, canvas_height // 2))
            vx = random.uniform(4, 7)
            vy = random.uniform(1.5, 3)
            trail_length = 10
            colors = [(180, 150, 255), (200, 180, 255), (220, 200, 255)]  # Purple streak
        elif comet_type == 'arc':
            x = random.randint(-50, canvas_width // 3)
            y = random.randint(40, max(80, canvas_height // 5))
            vx = random.uniform(3, 6)
            vy = random.uniform(3, 6)  # More vertical for arc
            trail_length = 9
            colors = [(255, 250, 200), (255, 240, 180), (255, 230, 160)]  # Golden streak
        elif comet_type == 'diagonal':
            x = random.randint(-100, canvas_width // 4)
            y = random.randint(50, max(100, canvas_height // 3))
            vx = random.uniform(6, 10)
            vy = random.uniform(4, 7)  # Steep diagonal
            trail_length = 12
            colors = [(255, 200, 200), (255, 180, 200), (255, 160, 200)]  # Pink streak
        elif comet_type == 'streak':
            x = random.randint(-120, canvas_width // 3)
            y = random.randint(120, max(180, canvas_height // 2))
            vx = random.uniform(10, 16)  # Super fast
            vy = random.uniform(1, 2)  # Almost horizontal
            trail_length = 18
            colors = [(220, 255, 255), (200, 240, 255), (180, 220, 255)]  # Bright cyan
        else:  # slow
            x = random.randint(-50, int(canvas_width * 0.7))
            y = random.randint(150, max(200, min(canvas_height // 2, canvas_height - 100)))
            vx = random.uniform(2, 4)
            vy = random.uniform(0.5, 2)
            trail_length = 6
            colors = [(200, 255, 255), (180, 240, 255), (160, 220, 255)]  # Cyan streak
        
        # Create comet trail with gradient colors
        trail_ids = []
        base_color = random.choice(colors)
        for i in range(trail_length):
            size = max(0.5, 4 - (i * 0.35))
            alpha = max(0.1, 1.0 - (i * (0.9 / trail_length)))
            
            # Color gradient effect (start invisible for fade-in)
            r = int(base_color[0] * alpha)
            g = int(base_color[1] * alpha)
            b = int(base_color[2] * alpha)
            
            trail_id = self.canvas.create_oval(
                x - i*5, y - i*2, x - i*5 + size, y - i*2 + size,
                fill=f"#{r:02x}{g:02x}{b:02x}",
                outline="",
                state='hidden'  # Start hidden for fade-in
            )
            trail_ids.append(trail_id)
        
        self.animation_comets.append({
            'trail_ids': trail_ids,
            'base_color': base_color,  # Store base color for fade effects
            'trail_length': trail_length,
            'x': x, 'y': y,
            'vx': vx, 'vy': vy,
            'lifetime': 0,
            'type': comet_type,
            'fade_in_duration': self.FADE_IN_DURATION,
            'fade_out_start': None  # Will be set when approaching edge
        })
    
    def _animate(self):
        """Animate stars and comets with enhanced effects"""
        if not self.animation_running or self.is_closing:
            return
        
        # Animate star twinkling with color variations and occasional flashes
        for star in self.stars:
            star['twinkle_phase'] += star['twinkle_speed']
            
            # Enhanced pulsing effect with sine wave
            pulse = 0.6 + 0.4 * abs(math.sin(star['twinkle_phase'] + star['pulse_offset']))
            brightness = star['base_brightness'] * pulse
            
            # Occasional bright flash
            if random.random() < 0.001:  # 0.1% chance per frame
                brightness = min(1.0, brightness * 1.8)
            
            # Apply brightness to base color
            r = int(star['base_color'][0] * brightness)
            g = int(star['base_color'][1] * brightness)
            b = int(star['base_color'][2] * brightness)
            
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.itemconfig(star['id'], fill=color)
            # Raise stars above text widget so they're visible
            self.canvas.tag_raise(star['id'])
        
        # Animate title glow
        self.glow_phase += 0.1
        glow_intensity = abs(math.sin(self.glow_phase))
        if glow_intensity > 0.8:
            self.canvas.itemconfig(self.title_glow, state="normal")
        else:
            self.canvas.itemconfig(self.title_glow, state="hidden")
        
        # Animate comets with enhanced movement and fading
        canvas_width = self.canvas.winfo_width() or 900
        canvas_height = self.canvas.winfo_height() or 700
        
        # Define fade zones (margins from edges and UI elements)
        fade_out_margin = 150  # Start fading out 150px from edge/UI
        fade_in_margin = 100   # Fade in distance below top UI
        top_ui_zone = 120      # Header + "Terms of Use" title area
        bottom_ui_zone = canvas_height - (canvas_height - 600)  # Approximate bottom panel area
        
        for comet in self.animation_comets[:]:
            comet['x'] += comet['vx']
            comet['y'] += comet['vy']
            comet['lifetime'] += 1
            
            # Calculate fade-in ratio based on position relative to top UI
            # Comets fade IN as they emerge from the top UI zone
            distance_below_top_ui = comet['y'] - top_ui_zone
            if distance_below_top_ui < fade_in_margin:
                position_fade_in = max(0, distance_below_top_ui / fade_in_margin)
            else:
                position_fade_in = 1.0
            
            # Also consider lifetime fade-in (first 15 frames)
            if comet['lifetime'] < comet['fade_in_duration']:
                time_fade_in = comet['lifetime'] / comet['fade_in_duration']
            else:
                time_fade_in = 1.0
            
            # Use the most restrictive fade-in
            fade_in_ratio = min(position_fade_in, time_fade_in)
            
            # Calculate fade-out ratio when approaching RIGHT edge or BOTTOM areas
            distance_to_right = canvas_width - comet['x']
            distance_to_bottom = canvas_height - comet['y']
            distance_from_bottom_ui = bottom_ui_zone - comet['y']  # Distance to bottom UI
            
            # Find minimum distance to fade-out boundaries (exclude top since we fade IN there)
            distance_to_edge = min(distance_to_right, distance_to_bottom,
                                  distance_from_bottom_ui if distance_from_bottom_ui > 0 else fade_out_margin)
            
            if distance_to_edge < fade_out_margin:
                fade_out_ratio = distance_to_edge / fade_out_margin
            else:
                fade_out_ratio = 1.0
            
            # Combined fade effect (both fade-in and fade-out)
            combined_fade = fade_in_ratio * fade_out_ratio
            
            # Calculate trail direction based on velocity (opposite to movement)
            # Normalize the velocity to get direction
            speed = math.sqrt(comet['vx']**2 + comet['vy']**2)
            if speed > 0:
                trail_dx = -(comet['vx'] / speed) * 5  # Trail points opposite to movement
                trail_dy = -(comet['vy'] / speed) * 5
            else:
                trail_dx = -5
                trail_dy = -2
            
            # Update trail positions with dynamic sizing and fading
            for i, trail_id in enumerate(comet['trail_ids']):
                # Calculate base alpha for this trail segment
                base_alpha = max(0.1, 1.0 - (i * (0.9 / comet['trail_length'])))
                
                # Apply combined fade
                final_alpha = base_alpha * combined_fade
                
                # Size adjustments
                base_size = 4 - (i * 0.35)
                size = max(0.5, base_size * combined_fade)
                
                # Position trail segments along velocity direction
                x = comet['x'] + i * trail_dx
                y = comet['y'] + i * trail_dy
                self.canvas.coords(trail_id, x, y, x + size, y + size)
                
                # Update color with fade
                if combined_fade > 0.01:  # Only show if visible
                    r = int(comet['base_color'][0] * final_alpha)
                    g = int(comet['base_color'][1] * final_alpha)
                    b = int(comet['base_color'][2] * final_alpha)
                    self.canvas.itemconfig(trail_id, 
                                          fill=f"#{r:02x}{g:02x}{b:02x}",
                                          state='normal')
                else:
                    self.canvas.itemconfig(trail_id, state='hidden')
                
                # Raise comet trails above text widget
                self.canvas.tag_raise(trail_id)
            
            # Remove if completely faded out or way off screen
            fully_faded = combined_fade < 0.01
            way_off_screen = (comet['x'] > canvas_width + 200 or 
                            comet['y'] > canvas_height + 200 or
                            comet['lifetime'] > 300)
            
            if fully_faded or way_off_screen:
                for trail_id in comet['trail_ids']:
                    self.canvas.delete(trail_id)
                self.animation_comets.remove(comet)
        
        # Spawn LOTS of comets for continuous comet shower effect
        if random.random() < self.COMET_SPAWN_CHANCE:
            self._spawn_comet()
        
        # Sometimes spawn multiple comets at once for bursts
        if random.random() < self.COMET_BURST_CHANCE:
            for _ in range(random.randint(self.COMET_BURST_MIN, self.COMET_BURST_MAX)):
                self._spawn_comet()
        
        # Periodic cleanup and performance monitoring (every ~1 second at 30fps)
        if not hasattr(self, '_cleanup_frame_count'):
            self._cleanup_frame_count = 0
        self._cleanup_frame_count += 1
        if self._cleanup_frame_count >= 30:  # Every ~1 second
            # Only call these methods if they exist (they might not exist in TermsOfUseDialog)
            if hasattr(self, '_cleanup_excessive_particles'):
                self._cleanup_excessive_particles()
            if hasattr(self, '_monitor_performance'):
                self._monitor_performance()
            self._cleanup_frame_count = 0
        
        # Schedule next frame
        self.after(33, self._animate)  # ~30 FPS
    
    def _update_layout(self, width, height):
        """Update layout positioning based on window dimensions"""
        # Don't update if dimensions are too small (window not ready)
        if width < 100 or height < 100:
            return
            
        # Update canvas size
        self.canvas.config(width=width, height=height)
        
        # Update header background to span full width
        self.canvas.coords(self.header_bg, 0, 0, width, 100)
        
        # Center title horizontally
        center_x = width / 2
        self.canvas.coords(self.title_text, center_x, 50)
        self.canvas.coords(self.title_glow, center_x, 50)
        
        # Reposition and resize content area
        content_y = 120
        content_height = max(height - 230, 200)  # Leave space for header (100px) and bottom panel (100px + 30px margin)
        content_width = min(width - 60, 840)  # Max 840px or window width - 60px margin
        
        # Update the border rectangle
        rect_x1 = (width - content_width) / 2
        rect_y1 = content_y
        rect_x2 = rect_x1 + content_width
        rect_y2 = rect_y1 + content_height
        self.canvas.coords(self.content_border, rect_x1, rect_y1, rect_x2, rect_y2)
        
        # Update title position
        self.canvas.coords(self.terms_title_text, center_x, content_y + 30)
        
        # Update the text content position and width, preserving scroll offset
        self.content_y_start = content_y + 70  # Update starting position for scrolling
        self.canvas.coords(self.terms_content_text, center_x, self.content_y_start - self.scroll_offset)
        self.canvas.itemconfig(self.terms_content_text, width=content_width - 40)
        
        # Update clipping bounds for scrollable content
        self.content_clip_y1 = content_y + 60
        self.content_clip_y2 = rect_y2
        
        # Update scroll hint position (just above bottom panel)
        self.canvas.coords(self.scroll_hint, center_x, rect_y2 + 15)
        
        # Update masking rectangles to match new window size
        self.canvas.coords(self.top_mask, 0, 0, width, content_y + 60)
        self.canvas.coords(self.bottom_mask, 0, rect_y2, width, height)
        
        # Raise UI elements above masks (so they're visible)
        self.canvas.tag_raise(self.header_bg)
        self.canvas.tag_raise(self.title_text)
        self.canvas.tag_raise(self.title_glow)
        self.canvas.tag_raise(self.content_border)
        self.canvas.tag_raise(self.terms_title_text)
        self.canvas.tag_raise(self.scroll_hint)
        
        # Adjust star count based on canvas area
        target_star_count = int((width * height) / self.STARS_PER_PIXEL_AREA)
        target_star_count = max(self.MIN_STARS, min(target_star_count, self.MAX_STARS))
        
        # Star colors for variety
        star_colors = [
            (180, 220, 255),  # Blue-white
            (200, 180, 255),  # Purple-white
            (255, 250, 240),  # Warm white
            (150, 200, 255),  # Cool blue
        ]
        
        # Add more stars if window grew
        while len(self.stars) < target_star_count:
            x = random.randint(0, width)
            y = random.randint(0, height)
            star_size = random.choice([1, 1, 2, 2, 3, 4])
            brightness = random.uniform(0.3, 1.0)
            base_color = random.choice(star_colors)
            
            star_id = self.canvas.create_oval(
                x, y, x + star_size, y + star_size,
                fill=f"#{int(base_color[0]*brightness):02x}{int(base_color[1]*brightness):02x}{int(base_color[2]*brightness):02x}",
                outline=""
            )
            self.stars.append({
                'id': star_id,
                'x': x, 'y': y, 'size': star_size,
                'base_brightness': brightness,
                'base_color': base_color,
                'twinkle_phase': random.uniform(0, math.pi * 2),
                'twinkle_speed': random.uniform(0.02, 0.1),
                'pulse_offset': random.uniform(0, 3.14)
            })
        
        # Remove excess stars if window shrunk
        while len(self.stars) > target_star_count:
            star = self.stars.pop()
            self.canvas.delete(star['id'])
        
        # OPTIMIZATION: Only raise tags when needed, not every frame
        # Stars and comets are created with correct layering initially
        
        # Reposition bottom panel at the bottom with margin
        # Panel is 100px tall, position its center so the bottom edge has 10px margin from window bottom
        # bottom_y = height - (panel_height/2) - bottom_margin
        bottom_y = height - 50 - 10  # Position: window_height - half_panel_height(50) - margin(10)
        self.canvas.coords(self.bottom_window, center_x, bottom_y)
        self.canvas.itemconfig(self.bottom_window, width=width, height=100)
    
    def _on_resize(self, event):
        """Handle window resize to reposition canvas elements"""
        if event.widget == self:
            self._update_layout(event.width, event.height)
    
    def _on_checkbox_toggle(self):
        """Enable/disable accept button based on checkbox state"""
        if self.accept_var.get():
            self.accept_button.configure(state="normal")
        else:
            self.accept_button.configure(state="disabled")
    
    def _on_accept(self):
        """User accepted the terms"""
        self.accepted = True
        self.is_closing = True
        self.animation_running = False
        self.grab_release()
        self.destroy()
    
    def _on_decline(self):
        """User declined the terms - exit app"""
        self.accepted = False
        self.is_closing = True
        self.animation_running = False
        self.grab_release()
        self.destroy()


class StarryNightApp(ctk.CTk):  # AI_TARGET: MAIN_APPLICATION_CLASS
    
    # Config file path (in same directory as script/exe, with fallback to AppData)
    if getattr(sys, 'frozen', False) or '__compiled__' in globals():
        # Running as compiled executable - try exe directory first
        exe_dir = os.path.dirname(sys.executable)
        CONFIG_FILE = os.path.join(exe_dir, "Config.txt")
        
        # Test write permissions - if fails, use AppData silently
        try:
            test_file = os.path.join(exe_dir, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
        except (PermissionError, OSError):
            # No write permission - use AppData instead
            appdata = os.path.join(os.getenv('APPDATA'), 'IRUS_COMET')
            os.makedirs(appdata, exist_ok=True)
            CONFIG_FILE = os.path.join(appdata, "Config.txt")
    else:
        # Running as script
        CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Config.txt")
    
    def __init__(self):  # AI_TARGET: APP_INITIALIZATION
        print("🚀 StarryNightApp __init__ starting...")
        super().__init__()
        print("🏗️ CustomTkinter super().__init__() completed")

        # AI_SECTION_START: GUI_SETUP
        self.title("IRUS COMET by AsphaltCake")
        self.geometry("800x600")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.is_quitting = False
        # AI_SECTION_END: GUI_SETUP

        # AI_SECTION_START: THREAD_SYSTEM
        print("🧵 Setting up thread system...")
        from queue import Queue
        self.gui_update_queue = Queue()
        self._process_gui_updates()
        print("🧵 Thread system initialized")
        # AI_SECTION_END: THREAD_SYSTEM

        # --- Screen Resolution Tracking for Resize Detection ---
        self._last_screen_width = self.winfo_screenwidth()
        self._last_screen_height = self.winfo_screenheight()

        # --- Hotkey Manager and State ---
        print("🔥 Initializing HotkeyManager...")
        self.hotkey_manager = HotkeyManager(self._on_hotkey_trigger, self.quit_app)
        print("🔥 HotkeyManager initialized")
        self.basic_settings_view = None
        self.support_view = None
        self.cast_view = None
        self.shake_view = None
        self.fish_view = None
        self.discord_view = None
        self.misc_view = None

        # Global hotkey states (independent of settings view)
        self.global_hotkey_states = {
            "Start/Stop": False,
            "Change Area": False
        }

        # Area selection state
        self.area_selector = None
        self.is_modifying_area = False

        # Reference resolution (2560x1440) - coordinates are designed for this resolution
        self.reference_width = 2560
        self.reference_height = 1440
        
        # Get current screen resolution
        self.current_width = self.winfo_screenwidth()
        self.current_height = self.winfo_screenheight()
        
        # Calculate scaling factors
        self.scale_x = self.current_width / self.reference_width
        self.scale_y = self.current_height / self.reference_height
        
        print(f"🖥️  Screen Resolution: {self.current_width}x{self.current_height}")
        print(f"📏 Reference Resolution: {self.reference_width}x{self.reference_height}")
        print(f"📐 Scale Factors: X={self.scale_x:.3f}, Y={self.scale_y:.3f}")

        # Default area coordinates (at 2560x1440 reference resolution, will be scaled)
        fish_box_default = {"x1": 765, "y1": 1217, "x2": 1797, "y2": 1255}
        shake_box_default = {"x1": 530, "y1": 235, "x2": 2030, "y2": 900}
        
        # Scale coordinates to current resolution
        self.fish_box = self._scale_coordinates(fish_box_default)
        self.shake_box = self._scale_coordinates(shake_box_default)
        
        print(f"🐟 Scaled Fish Box: {self.fish_box}")
        print(f"📦 Scaled Shake Box: {self.shake_box}")
        
        print("✅ Coordinate scaling completed")
        # Validate coordinates are within screen bounds
        if self.fish_box["x2"] > self.current_width or self.fish_box["y2"] > self.current_height:
            print(f"⚠️  Warning: Fish box coordinates exceed screen bounds!")
        if self.shake_box["x2"] > self.current_width or self.shake_box["y2"] > self.current_height:
            print(f"⚠️  Warning: Shake box coordinates exceed screen bounds!")

        # ===== CENTRALIZED SETTINGS STORAGE =====
        # Bot reads from here, GUI writes to here
        self.settings = {
            # Cast settings
            "cast_mode": "Normal",  # "Normal" or "Perfect"
            "cast_delay1": 0.0,
            "cast_delay2": 0.5,
            "cast_delay3": 1.0,
            "perfect_delay1": 0.0,
            "perfect_delay2": 0.0,
            "perfect_delay3": 0.0,
            "perfect_delay4": 0.2,
            "perfect_delay5": 0.2,
            "perfect_delay6": 0.0,
            "perfect_delay7": 0.0,
            "perfect_delay8": 0.0,
            "perfect_delay9": 0.0,
            "perfect_delay10": 0.2,
            "zoom_out": 13,
            "zoom_in": 6,
            "look_down": 2000,
            "look_up": 900,
            "final_zoom_in": 5,
            "final_look_up": 2000,
            
            # Perfect Cast Release settings
            "perfect_cast_green_color_tolerance": 15,
            "perfect_cast_white_color_tolerance": 15,
            "perfect_cast_fail_scan_timeout": 3,
            "perfect_cast_scan_fps": 1000,  # Maximum speed for precision (0ms delay)
            "perfect_cast_release_style": "GigaSigmaUltraMode",  # "Velocity-Percentage", "Prediction", or "GigaSigmaUltraMode"

            # Perfect Cast Release - Velocity-Percentage system
            "perfect_cast_release_percentage": 85,     # Fallback when velocity not detected (70-95%)
            "perfect_cast_band1_release": 95,          # <400 px/s
            "perfect_cast_band2_release": 94,          # 400-600 px/s
            "perfect_cast_band3_release": 92,          # 600-800 px/s
            "perfect_cast_band4_release": 91,          # 800-1000 px/s
            "perfect_cast_band5_release": 89,          # 1000-1200 px/s
            "perfect_cast_band6_release": 88,          # >1200 px/s
            "perfect_cast_minimum_distance": 25,       # Minimum distance for immediate release (pixels at 1440p)
            "perfect_cast_reference_height": 1440,     # Reference resolution for distance scaling

            # Perfect Cast Release - Prediction system auto-tune bands
            "prediction_band1_release": 95,            # <400 px/s
            "prediction_band2_release": 94,            # 400-600 px/s
            "prediction_band3_release": 92,            # 600-800 px/s
            "prediction_band4_release": 91,            # 800-1000 px/s
            "prediction_band5_release": 89,            # 1000-1200 px/s
            "prediction_band6_release": 88,            # >1200 px/s

            # Perfect Cast Release - GigaSigmaUltraMode auto-tune bands
            "gigasigma_band1_release": 95,             # <400 px/s
            "gigasigma_band2_release": 94,             # 400-600 px/s
            "gigasigma_band3_release": 92,             # 600-800 px/s
            "gigasigma_band4_release": 91,             # 800-1000 px/s
            "gigasigma_band5_release": 89,             # 1000-1200 px/s
            "gigasigma_band6_release": 88,             # >1200 px/s

            # Perfect Cast Release - Prediction system (OLD)
            "perfect_cast_timing_700": 0,
            "perfect_cast_timing_800": 0,
            "perfect_cast_timing_900": 0,
            "perfect_cast_timing_1000": 0,
            "perfect_cast_timing_1100": 0,
            "perfect_cast_timing_1200": 0,
            "perfect_cast_timing_1300": 0,
            "perfect_cast_timing_1400": 0,
            "perfect_cast_timing_1500": 0,
            "perfect_cast_timing_1600": 0,
            "perfect_cast_timing_1600plus": 0,
            "perfect_cast_speed_threshold": 1000,      # Speed threshold for slow/fast timing adjustment
            "perfect_cast_slow_speed_time": 150,       # Distance-based fallback for slow speeds
            "perfect_cast_fast_speed_time": 100,       # Distance-based fallback for fast speeds

            # Hotbar settings
            "hotbar_fishing_rod": "1",  # Hotbar key for Fishing Rod
            "hotbar_equipment_bag": "2",  # Hotbar key for Equipment Bag

            # Misc settings - Auto Select Rod
            "auto_select_rod_enabled": True,
            "auto_select_rod_delay1": 0.0,  # Before Equipment Bag (0-10s range)
            "auto_select_rod_delay2": 0.5,  # After Equipment Bag, before Fishing Rod (0-10s range)
            "auto_select_rod_delay3": 0.0,  # After Fishing Rod (0-10s range)

            # Shake settings
            "shake_style": "Pixel",  # "Pixel", "Navigation", "Circle"
            "shake_capture_mode": "MSS",  # "DXCAM" or "MSS"
            "shake_click_count": 1,
            "shake_color_tolerance": 0,
            "shake_pixel_distance_tolerance": 10,
            "shake_scan_fps": 1000,
            "shake_duplicate_timeout": 1,
            "shake_fail_cast_timeout": 3,
            "nav_key": "\\",
            "nav_color_tolerance": 0,
            "nav_scan_fps": 1000,
            "nav_fail_cast_timeout": 3,
            "circle_click_count": 1,
            "circle_pixel_distance_tolerance": 10,
            "circle_scan_fps": 1000,
            "circle_duplicate_timeout": 1,
            "circle_fail_cast_timeout": 3,

            # Fish settings
            "fish_track_style": "Line",  # "Color" or "Line"
            "fish_rod_type": "Default",
            "fish_target_line_color": "#434b5b",  # Grayish blue target line
            "fish_arrow_color": "#848587",        # White default
            "fish_left_bar_color": "#f1f1f1",     # Light gray left bar
            "fish_right_bar_color": "#ffffff",    # White right bar
            "fish_target_line_tolerance": 0,      # Default tolerance values
            "fish_left_bar_tolerance": 0,         # Tolerance 0 as per GUI
            "fish_right_bar_tolerance": 0,        # Tolerance 0 as per GUI
            "fish_scan_fps": 1000,                # Scan FPS for color mode (10-1000, 1000=1ms delay)
            "fish_lost_timeout": 1,               # Fish lost timeout in seconds (0-10s)
            "fish_bar_ratio_from_side": 0.6,      # Bar ratio from side (0.0-1.0) - edge detection threshold
            "fish_control_mode": "Steady",        # Control mode: Normal, Steady, or NigGamble
            "fish_kp": 0.9,                       # KP parameter
            "fish_kd": 0.3,                       # KD parameter
            "fish_pd_clamp": 1.0,                 # PD Clamp (fixed at 1.0, not user-configurable - only sign matters for binary control)

            # Fish Line mode settings
            "fish_line_scan_fps": 1000,           # Scan FPS for line mode (10-1000)
            "fish_line_lost_timeout": 1.0,        # Fish lost timeout for line mode (0.5-10.0s)
            "fish_line_bar_ratio": 0.6,          # Bar ratio from side for line mode (0.0-1.0) - edge detection threshold
            "fish_line_mi2n_density": 0.8,         # Minimum line density for line detection (0.01-1.0, 80% default)
            "fish_line_control_mode": "Steady",   # Control mode: Normal, Steady, or NigGamble
            "fish_line_kp": 0.9,                  # KP parameter for line mode
            "fish_line_kd": 0.3,                  # KD parameter for line mode
            "fish_line_pd_clamp": 1.0,            # PD Clamp for line mode (fixed at 1.0 - only sign matters)

            # Discord settings
            "discord_enabled": False,
            "webhook_url": "",
            "discord_message_style": "Screenshot",  # "Screenshot" or "Text"
            "loops_screenshot": "10",
            "loops_text": "10",
        }

        print("📊 Settings dictionary initialized")
        # GUI Settings (global to the app)
        self.global_gui_settings = {
            "Always On Top": True,
            "Auto Minimize GUI": True,
            "Show Perfect Cast Overlay": True,
            "Show Fishing Overlay": True,
            "Show Status Overlay": False
        }
        
        # GigaSigma auto-tune tracking (initialize early so it's always available)
        self._last_cast_velocity = None
        self._last_cast_band = None
        self._tune_used_this_cast = False
        
        # Status tracking for overlay
        self.current_status = "Idle"
        self.previous_status = "None"
        self.status_details = ""
        self.status_color = "white"  # Track last color used
        self.status_overlay = None
        self.status_label = None
        
        print("✅ Status tracking initialized")
        
        # Apply initial "Always On Top" setting
        self.wm_attributes("-topmost", self.global_gui_settings["Always On Top"])
        
        # Rock slashing mini-game
        self.fisch_gui_enabled_var = tk.BooleanVar(value=True)  # Fisch GUI toggle (default ON)
        self.fisch_gui_toggle_checkbox = None
        self.minigame_enabled_var = tk.BooleanVar(value=False)  # Minigame toggle
        self.minigame_toggle_checkbox = None
        self.rocks_slashed = 500000.0  # TESTING: Start with 500K comets after maxing T1&T2
        self.rocks_slashed_label_id = None  # Canvas text ID for counter
        self.auto_slash_var = tk.BooleanVar(value=False)
        self.auto_slash_checkbox = None
        self.active_rocks = []  # Changed to list to support multiple rocks
        self.rock_spawn_timer = 0
        self.rock_spawn_interval = 1000  # 1 second in milliseconds
        self.auto_trail_elements = []  # For auto collect trail
        self.auto_trail_head_x = 400  # Starting position for auto trail
        self.auto_trail_head_y = 300
        self.auto_trail_speed = 5  # Pixels per frame movement speed
        
        # Rebirth system
        self.rebirth_count = 0
        self.rebirth_multiplier = 1.0

        # Shop upgrades - 10-Tier system (5+ upgrades per tier!)
        # TESTING CONFIG: Tier 1 and 2 maxed out for balanced testing
        self.upgrade_levels = {
            # Tier 1 - Foundation (5 upgrades) - MAXED FOR TESTING
            'tier1_production': 50, 'tier1_multiplier': 50, 'tier1_luck': 40, 'tier1_bonus': 50, 'tier1_power': 40,
            # Tier 2 - Automation (5 upgrades) - MAXED FOR TESTING  
            'tier2_speed': 40, 'tier2_spawn': 25, 'tier2_rocks': 30, 'tier2_fire': 50, 'tier2_collection': 50,
            # Tier 3 - Luck Bonuses (5 upgrades)
            'tier3_fortune': 0, 'tier3_jackpot': 0, 'tier3_burst': 0, 'tier3_double': 0, 'tier3_triple': 0,
            # Tier 4 - Power (5 upgrades)
            'tier4_super_prod': 0, 'tier4_strength': 0, 'tier4_critical': 0, 'tier4_mega': 0, 'tier4_thunder': 0,
            # Tier 5 - Passive (5 upgrades)
            'tier5_passive': 0, 'tier5_efficiency': 0, 'tier5_energy': 0, 'tier5_growth': 0, 'tier5_recycler': 0,
            # Tier 6 - Multiplicative (5 upgrades)
            'tier6_true_multi': 0, 'tier6_income': 0, 'tier6_amplifier': 0, 'tier6_compound': 0, 'tier6_synergy': 0,
            # Tier 7 - Exponential (5 upgrades)
            'tier7_exponential': 0, 'tier7_supernova': 0, 'tier7_storm': 0, 'tier7_inferno': 0, 'tier7_lightning': 0,
            # Tier 8 - Ultimate (5 upgrades)
            'tier8_ultimate': 0, 'tier8_cosmic': 0, 'tier8_overdrive': 0, 'tier8_transcendent': 0, 'tier8_absolute': 0,
            # Tier 9 - God Tier (5 upgrades)
            'tier9_godmode': 0, 'tier9_infinity': 0, 'tier9_omnipotent': 0, 'tier9_eternal': 0, 'tier9_omniscient': 0
        }
        self.comet_multiplier = 1.0  # Base multiplier for comets earned
        self.base_comets_per_rock = 1.0  # Base comets per rock for balanced progression
        self.auto_collect_speed_bonus = 0  # Percentage speed bonus for auto collect
        self.max_rocks_count = 1  # Max rocks on screen
        self.luck_amplifier = 1.0  # Luck proc amplifier
        self.passive_income_rate = 0  # Passive income per second
        self.collision_check_counter = 0  # Counter to throttle collision checks

        # === STATISTICS TRACKING (Enhanced for New Systems) ===
        self.stats = {
            # === COLLECTION STATISTICS ===
            'total_rocks_collected': 0,
            'total_comets_earned': 0.0,
            'current_balance': 0.0,  # Track for historical analysis
            'highest_single_collection': 0.0,
            'highest_balance_reached': 0.0,
            'lifetime_earnings': 0.0,  # Total earned across all rebirths
            
            # === LUCK STATISTICS (Independent System) ===
            'double_procs': 0,        # 2x multiplier hits
            'triple_procs': 0,        # 3x multiplier hits
            'jackpot_procs': 0,       # 5x multiplier hits
            'burst_procs': 0,         # Burst bonus hits
            'mega_procs': 0,          # Future: 10x hits
            'ultra_procs': 0,         # Future: 25x hits
            'luck_combos_hit': 0,     # Times multiple luck procs triggered simultaneously
            
            # === UPGRADE STATISTICS ===
            'total_upgrades_purchased': 0,
            'total_comets_spent': 0.0,
            'highest_tier_reached': 2,     # Highest tier with any upgrade - UPDATED FOR TESTING
            'tier1_upgrades': 230, 'tier2_upgrades': 195, 'tier3_upgrades': 0,  # UPDATED: T1=50+50+40+50+40=230, T2=40+25+30+50+50=195
            'tier4_upgrades': 0, 'tier5_upgrades': 0, 'tier6_upgrades': 0,
            'tier7_upgrades': 0, 'tier8_upgrades': 0, 'tier9_upgrades': 0,
            'most_expensive_purchase': 0.0,
            'energy_savings_total': 0.0,  # Total saved from tier 5 energy upgrade
            
            # === PROGRESSION STATISTICS ===
            'rebirths_completed': 0,
            'passive_income_earned': 0.0,
            'auto_collect_time_seconds': 0,
            'manual_collect_time_seconds': 0,
            
            # === SESSION STATISTICS ===
            'session_start_time': None,
            'total_playtime_seconds': 0,
            'current_session_earnings': 0.0,
            'current_session_upgrades': 0,
        }
        
        # === SHOP SYSTEM VARIABLES ===
        self.comets = 0.0  # Current comet currency
        self.total_comets_earned = 0.0  # Lifetime comets earned
        self.rebirths = 0  # Number of rebirths
        self.max_upgrade_levels = {}  # Max levels reached for each upgrade
        self.playtime_tracking = {
            'total_seconds': 0,
            'last_session_start': None
        }

        # Comet trail configuration (optimized for performance)
        self.comet_trail_particles = []  # List of particle dictionaries
        self.comet_trail_max_particles = 10  # Reduced from 25 to 10 for better performance
        self.comet_particle_lifetime = 8   # Reduced from 15 to 8 for faster cleanup
        self.comet_trail_colors = ["#18191A", "#B8D4F1", "#88B4E3", "#5894D5", "#3074C7"]  # Ice blue gradient
        self.comet_trail_update_counter = 0  # Counter to throttle trail updates
        
        # Discord integration loop counter
        self.discord_loop_count = 0  # Tracks completed bot cycles for Discord webhooks
        
        # Resize debounce
        self._resize_after_id = None
        self._pending_width = 0
        self._pending_height = 0

        # --- Bindings for Scroll Wheel (Global and delegated) ---
        self.bind("<MouseWheel>", self._on_app_scroll)
        self.bind("<Button-4>", self._on_app_scroll)
        self.bind("<Button-5>", self._on_app_scroll)
        
        print("🎮 Shop and stats initialized")
        
        # --- State Control ---
        self.app_state = 'menu' 
        self.is_rotating = True 
        self.zoomed_tab_data = {} 

        # --- Star/Trail Configuration ---
        self.stars = []
        self.base_max_stars = 100
        self.max_stars = self.base_max_stars
        self.star_density_factor = 0.0002
        self.star_size = 3
        self.fade_steps = 60
        self.trail_elements = [] 
        self.trail_size = 6
        self.trail_lifetime = 12
        self.auto_trail_lifetime = 45  # Auto trail lasts much longer (3x longer for visibility)
        print("🌟 Animation variables initialized") 
        self.trail_max_elements = 50 
        self.base_animation_delay_ms = 30  # Faster base speed (33 FPS instead of 20 FPS)
        self.animation_delay_ms = self.base_animation_delay_ms  # Will be dynamically calculated
        self.performance_mode_active = False  # Tracks if performance mode is enabled (>3 comets)
        
        # Shop optimization variables
        self.shop_batch_size = 5  # Create upgrades in batches
        self.shop_creation_index = 0  # Track creation progress 

        # Create a standard Tkinter Canvas
        self.canvas = tk.Canvas(
            self,
            bg="black",
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        print(f"🖼️ Canvas created and gridded")

        # --- Menu Configuration ---
        print("📋 Setting up menu configuration...")
        self.menu_tabs = ["Basic", "Misc", "Cast", "Shake", "Fish", "Discord", "Support"]
        self.tab_colors = { 
            "Basic": "#4A90E2", 
            "Misc": "#50E3C2",
            "Cast": "#F5A623",
            "Shake": "#BD10E0",
            "Fish": "#7ED321",
            "Discord": "#5865F2",
            "Support": "#9013FE"
        }
        self.menu_radius = 150 
        self.tab_base_size = 60 
        self.tab_hover_size = 80 
        self.current_angle = 0 
        self.rotation_speed = 0.005 
        self.tab_items = [] 
        self.hovered_tab_index = -1 
        
        # Central label
        self.central_label_id = None
        self.central_label_text = "IRUS COMET"
        self.central_font = ctk.CTkFont(size=32, weight="bold", family="Inter")
        self.central_label_offset_y = 250 

        # Bottom toggle buttons
        self.bottom_buttons = []
        self.bottom_button_names = ["Start", "Misc", "Cast", "Shake", "Fish"]
        self.bottom_button_states = {name: True for name in self.bottom_button_names if name != "Start"}  # True = active, False = toggled off, Start is not toggleable
        self.bottom_button_offset_y = 250  # Same distance as central label but below
        self.flow_arrows = []  # Store arrow elements for the flow

        # Tab View Elements
        self.back_button_id = None
        self.back_text_id = None
        self.current_tab_title_id = None
        print("📑 Tab view elements configured")

        # Initial drawing and animation start
        print("🎨 Creating UI elements...")
        self._create_central_label()
        self._create_menu_tabs()
        self._create_bottom_buttons()
        self._create_flow_arrows()
        self._create_fisch_gui_toggle()
        self._create_minigame_toggle()
        
        # Create minigame elements (will be hidden initially)
        self._create_rocks_slashed_label()
        print("🎨 All UI elements created")
        self._create_auto_slash_checkbox()
        self._create_shop_button()
        
        # Initially hide minigame elements since toggle is off by default
        # Set initial state before calling toggle to ensure proper hiding
        # Counter starts hidden (already created with state='hidden')
        if self.auto_slash_checkbox:
            self.auto_slash_checkbox.place_forget()
        if self.shop_button:
            self.shop_button.place_forget()

        # Initialize camera tracking list for resource cleanup
        self._active_cameras = []

        # ===== LOAD CONFIG (Terms of Use already handled at startup) =====
        if os.path.exists(self.CONFIG_FILE):
            self._load_config()
        else:
            self._save_config()
        
        # === INITIALIZE SESSION TRACKING ===
        import time
        current_time = time.time()
        
        # Initialize session start time if not set
        if self.stats.get('session_start_time') is None:
            self.stats['session_start_time'] = current_time
            print("📊 Starting new statistics session...")
        
        # Reset session-specific stats for new run
        self.stats['current_session_earnings'] = 0.0
        self.stats['current_session_upgrades'] = 0
        
        # Update current balance in stats for tracking
        self.stats['current_balance'] = self.rocks_slashed
        
        # Start playtime tracking
        self._start_playtime_tracking()
        
        # Show main window and bring to front
        self.deiconify()
        self.update_idletasks()
        self.lift()
        self.focus_force()
        self.attributes('-topmost', True)
        self.update()
        self.after(100, lambda: self.attributes('-topmost', self.global_gui_settings["Always On Top"]))
        
        # Debug canvas info
        canvas_items = self.canvas.find_all()
        canvas_width = self.canvas.winfo_width()
        canvas_height = self.canvas.winfo_height()
        print(f"👁️ Main GUI is now visible")
        print(f"🖼️ Canvas size: {canvas_width}x{canvas_height}")
        print(f"🎯 Canvas has {len(canvas_items)} elements: {canvas_items[:10] if len(canvas_items) > 10 else canvas_items}")
        
        # Track animation state
        self.animations_running = True

        # Start animations
        self.animate_stars()
        self.animate_menu()
        self.animate_trail()
        self.animate_rocks()
    
    # === HELPER METHODS ===
    def _get_capture_mode_settings(self):  # AI_TARGET: CAPTURE_HELPER
        """Get capture mode settings to avoid duplicate code across functions."""
        capture_mode = self.settings.get("shake_capture_mode", "DXCAM")
        use_mss = capture_mode == "MSS"
        return capture_mode, use_mss
    
    def _ensure_gui_var(self, obj, var_name, var_type, setting_key, default_value, trace_callback=None):  # AI_TARGET: GUI_PERSISTENCE_FIX
        """Ensure GUI variable exists and is updated to current config value. Fixes restart persistence issues."""
        if not hasattr(obj, var_name):
            var = var_type(value=self.settings.get(setting_key, default_value))
            setattr(obj, var_name, var)
            if trace_callback:
                var.trace_add("write", trace_callback)
        else:
            # Always update to current config value - fixes GUI persistence on restart
            getattr(obj, var_name).set(self.settings.get(setting_key, default_value))
        return getattr(obj, var_name)

    # --- Scroll Delegation (Optimized) ---
    def _on_app_scroll(self, event):
        """Delegates scroll event to the active view with throttling for performance."""
        # Throttle scroll events to reduce lag during rapid scrolling
        import time
        current_time = time.time()
        
        if not hasattr(self, '_last_scroll_time'):
            self._last_scroll_time = 0
        
        # Only process scroll events every 16ms (60 FPS limit)
        if current_time - self._last_scroll_time < 0.016:
            return
        
        self._last_scroll_time = current_time
        
        if self.app_state == 'tab_view':
            if self.basic_settings_view:
                self.basic_settings_view.handle_scroll_event(event)
            elif self.support_view:
                self.support_view.handle_scroll_event(event)
            elif self.cast_view:
                self.cast_view.handle_scroll_event(event)
            elif self.shake_view:
                self.shake_view.handle_scroll_event(event)
            elif self.fish_view:
                self.fish_view.handle_scroll_event(event)
            elif self.misc_view:
                self.misc_view.handle_scroll_event(event)
            elif self.discord_view:
                self.discord_view.handle_scroll_event(event)
            
    # ===== THREAD-SAFE GUI UPDATE SYSTEM =====
    
    def _process_gui_updates(self):
        """Process queued GUI updates in a thread-safe manner"""
        try:
            # Process all pending updates without blocking
            while not self.gui_update_queue.empty():
                try:
                    update_func, args, kwargs = self.gui_update_queue.get_nowait()
                    update_func(*args, **kwargs)
                except Exception as e:
                    print(f"    ⚠️ Warning: Error processing GUI update: {e}")
        except Exception as e:
            # Queue might be empty or application shutting down
            pass
        
        # Schedule next check (runs continuously while app is alive)
        if not self.is_quitting:
            self.after(10, self._process_gui_updates)  # Check every 10ms for responsiveness
    
    def _queue_gui_update(self, update_func, *args, **kwargs):
        """Thread-safe method to queue GUI updates from background threads"""
        try:
            self.gui_update_queue.put((update_func, args, kwargs))
        except Exception as e:
            print(f"    ⚠️ Warning: Could not queue GUI update: {e}")

    def _create_transparent_overlay(self, title, transparent_color='#00FF00', topmost=True, hide_initially=False):
        """Helper function to create a transparent overlay with consistent settings"""
        overlay = tk.Toplevel(self)
        overlay.title(title)
        overlay.attributes('-topmost', topmost)
        overlay.overrideredirect(True)
        overlay.attributes('-transparentcolor', transparent_color)
        
        # Create canvas with transparent background
        canvas = tk.Canvas(overlay, bg=transparent_color, highlightthickness=0)
        canvas.pack(fill='both', expand=True)
        
        if hide_initially:
            overlay.withdraw()
        
        return overlay, canvas

    # ===== HOTKEY ACTION METHODS =====
    
    def _on_hotkey_trigger(self, option_name):
        """
        Callback executed by the HotkeyManager (in a separate thread).
        For Start/Stop, update state immediately for responsiveness.
        For GUI updates, schedule on main thread.
        IMPORTANT: Return immediately to avoid blocking keyboard hook.
        """
        try:
            if option_name == "Start/Stop":
                # Update state immediately in hotkey thread for instant responsiveness
                current_state = self.global_hotkey_states["Start/Stop"]
                new_state = not current_state
                self.global_hotkey_states["Start/Stop"] = new_state
                print(f"Global HotKey: Start/Stop toggled to {'ON' if new_state else 'OFF'}")

                # Schedule GUI updates and bot cycle start on main thread
                try:
                    self.after(0, lambda: self._handle_start_stop_gui(new_state))
                except tk.TclError:
                    # This is expected if the application is shutting down
                    print("    ⚡ Note: Could not schedule GUI update - application may be shutting down")
                except Exception as e:
                    print(f"    ⚠️ Warning: Unexpected error scheduling start/stop GUI update: {e}")
            elif option_name != "Exit":
                try:
                    self.after(0, lambda: self._handle_hotkey_action(option_name))
                except tk.TclError:
                    # This is expected if the application is shutting down
                    print("    ⚡ Note: Could not schedule hotkey action - application may be shutting down")
                except Exception as e:
                    print(f"    ⚠️ Warning: Unexpected error scheduling hotkey action: {e}")
        except Exception as e:
            print(f"❌ Hotkey callback error: {e}")
        # ALWAYS return immediately to not block keyboard hook

    def _handle_start_stop_gui(self, new_state):
        """Handle GUI updates for Start/Stop toggle (runs in main thread)"""
        # Update BasicSettingsView if it exists and is active
        if self.basic_settings_view and hasattr(self.basic_settings_view, 'toggle_statuses'):
            self.basic_settings_view.toggle_statuses["Start/Stop"].set(new_state)

        if new_state:
            # Bot is starting - pause animations, minimize if enabled, then begin the main cycle
            self.animations_running = False
            print("Bot cycle starting, pausing animations...")

            # Auto minimize GUI if enabled
            if self.global_gui_settings.get("Auto Minimize GUI", False):
                self.iconify()
                print("Auto-minimized GUI due to bot starting")

            # Initialize bot state variables
            self._initialize_bot_state()

            # Show status overlay when bot starts
            self._update_status("Bot Starting", "white", "Press F3 to stop")

            self.run_bot_cycle()
        else:
            # Bot is stopping - cleanup resources and resume animations
            print("Bot cycle stopping, cleaning up resources...")
            self._cleanup_bot_resources()
            
            # Hide status overlay when bot stops
            self._hide_status_overlay()
            
            self.animations_running = True
            print("Bot cycle stopping, resuming animations...")

            # Auto restore GUI if enabled
            if self.global_gui_settings.get("Auto Minimize GUI", False):
                self.deiconify()
                self.lift()
                print("Auto-restored GUI due to bot stopping")

    def _handle_hotkey_action(self, option_name):
        """Performs the action associated with the hotkey in the main thread."""
        if option_name in ["Change Area"]:
            # Toggle global state
            current_state = self.global_hotkey_states[option_name]
            new_state = not current_state
            self.global_hotkey_states[option_name] = new_state

            print(f"Global HotKey: {option_name} toggled to {'ON' if new_state else 'OFF'}")

            # Update BasicSettingsView if it exists and is active
            if self.basic_settings_view and hasattr(self.basic_settings_view, 'toggle_statuses'):
                self.basic_settings_view.toggle_statuses[option_name].set(new_state)

            # Special handling for Change Area toggle
            if option_name == "Change Area":
                self.toggle_modify_area()
                return  # Skip the auto minimize logic for Change Area

            # Handle auto minimize GUI functionality
            if self.global_gui_settings["Auto Minimize GUI"]:
                if new_state:  # Toggled ON - minimize
                    self.iconify()
                    print(f"Auto-minimized GUI due to {option_name} activation")
                else:  # Toggled OFF - restore
                    self.deiconify()
                    self.lift()
                    print(f"Auto-restored GUI due to {option_name} deactivation")

    def toggle_modify_area(self):
        """Toggle the modify area mode - shows both boxes"""
        if not self.is_modifying_area:
            # Start area modification
            self.is_modifying_area = True

            # Auto minimize if enabled
            if self.global_gui_settings.get("Auto Minimize GUI", False):
                self.iconify()

            self.open_area_selector_both_boxes()
        else:
            # Stop area modification - save and close the selector if it exists
            if self.area_selector:
                self.area_selector.finish_selection()

    def open_area_selector_both_boxes(self):
        """Open area selector showing both Fish Box and Shake Box"""
        # Safety check: Don't allow area changes while bot is running
        if self.global_hotkey_states.get("Start/Stop", False):
            print("⚠️ Cannot change areas while bot is running! Stop the bot first.")
            return

        screenshot = ImageGrab.grab()
        self.area_selector = DualAreaSelector(self, screenshot, self.fish_box, self.shake_box, self.on_both_areas_selected)

    def on_both_areas_selected(self, fish_coords, shake_coords):
        """Called when both area selections are complete"""
        self.is_modifying_area = False
        self.area_selector = None
        self.fish_box = fish_coords
        self.shake_box = shake_coords
        print(f"Fish Box updated: {fish_coords}")
        print(f"Shake Box updated: {shake_coords}")

        # Auto restore if enabled and minimized
        if self.global_gui_settings.get("Auto Minimize GUI", False):
            self.deiconify()

    # ===== DISCORD WEBHOOK FUNCTIONS =====
    def _send_discord_screenshot(self, message_prefix=""):
        """Send a screenshot to Discord webhook in background thread."""
        if not self.settings.get("discord_enabled", False):
            return
        
        webhook_url = self.settings.get("webhook_url", "").strip()
        if not webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
            return
        
        # Send in background thread to not block bot
        thread = threading.Thread(
            target=self._discord_screenshot_worker, 
            args=(webhook_url, message_prefix), 
            daemon=True
        )
        thread.start()
    
    def _discord_screenshot_worker(self, webhook_url, message_prefix):
        """Worker function to send screenshot webhook."""
        try:
            screenshot = ImageGrab.grab()
            img_byte_arr = io.BytesIO()
            screenshot.save(img_byte_arr, format='PNG')
            img_byte_arr.seek(0)
            
            files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
            payload = {
                'content': f'{message_prefix}🎣 **IRUS COMET BOT** 🤖\n🔄 Loop #{self.discord_loop_count}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': 'IRUS COMET'
            }
            
            response = requests.post(webhook_url, data=payload, files=files, timeout=10)
            if response.status_code == 200 or response.status_code == 204:
                print(f"📤 Discord screenshot sent (Loop #{self.discord_loop_count})")
            else:
                print(f"❌ Discord screenshot failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Error sending Discord screenshot: {e}")
    
    def _send_discord_text(self, message_prefix=""):
        """Send a text message to Discord webhook in background thread."""
        if not self.settings.get("discord_enabled", False):
            return
        
        webhook_url = self.settings.get("webhook_url", "").strip()
        if not webhook_url or not webhook_url.startswith("https://discord.com/api/webhooks/"):
            return
        
        # Send in background thread to not block bot
        thread = threading.Thread(
            target=self._discord_text_worker, 
            args=(webhook_url, message_prefix), 
            daemon=True
        )
        thread.start()
    
    def _discord_text_worker(self, webhook_url, message_prefix):
        """Worker function to send text webhook."""
        try:
            payload = {
                'content': f'{message_prefix}🎣 **IRUS COMET BOT** 🤖\n🔄 Loop #{self.discord_loop_count}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': 'IRUS COMET',
                'embeds': [{
                    'title': '⚡ Bot Status Update',
                    'description': f'Completed loop #{self.discord_loop_count}',
                    'color': 0x5865F2,
                    'timestamp': time.strftime("%Y-%m-%dT%H:%M:%S")
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200 or response.status_code == 204:
                print(f"📤 Discord text sent (Loop #{self.discord_loop_count})")
            else:
                print(f"❌ Discord text failed: {response.status_code}")
        except Exception as e:
            print(f"❌ Error sending Discord text: {e}")

    # ===== RESOLUTION SCALING METHODS =====
    def _scale_coordinates(self, coords_dict):
        """Scale coordinates from reference resolution to current resolution"""
        return {
            "x1": int(coords_dict["x1"] * self.scale_x),
            "y1": int(coords_dict["y1"] * self.scale_y), 
            "x2": int(coords_dict["x2"] * self.scale_x),
            "y2": int(coords_dict["y2"] * self.scale_y)
        }
    
    def _unscale_coordinates(self, coords_dict):
        """Convert coordinates from current resolution back to reference resolution"""
        return {
            "x1": int(coords_dict["x1"] / self.scale_x),
            "y1": int(coords_dict["y1"] / self.scale_y),
            "x2": int(coords_dict["x2"] / self.scale_x),
            "y2": int(coords_dict["y2"] / self.scale_y)
        }
    
    def _check_resolution_change(self):
        """Check if screen resolution changed and rescale boxes if needed - CRITICAL for Roblox resize handling"""
        current_width = self.winfo_screenwidth()
        current_height = self.winfo_screenheight()
        
        if (current_width != self._last_screen_width or 
            current_height != self._last_screen_height):
            print(f"🖥️ Resolution change detected: {self._last_screen_width}x{self._last_screen_height} → {current_width}x{current_height}")
            
            # Update resolution tracking
            self._last_screen_width = current_width
            self._last_screen_height = current_height
            
            # Recalculate scaling factors and boxes
            self._setup_scaling()
            print("📐 Detection boxes rescaled for new resolution")
            return True
        return False
    
    def get_scaled_fish_box(self):
        """Get fish box coordinates scaled for current resolution"""
        return self.fish_box.copy()
    
    def get_scaled_shake_box(self):
        """Get shake box coordinates scaled for current resolution"""
        return self.shake_box.copy()

    # ===== MAIN BOT LOOP =====
    def run_bot_cycle(self):
        """
        Main bot loop that cycles through: Start > Misc > Cast > Shake > Fish
        Respects toggle states and loads appropriate settings for each block.
        """
        # Debug entrance
        print(f"🔄 run_bot_cycle called - _cycle_running={getattr(self, '_cycle_running', False)}, Start/Stop={self.global_hotkey_states['Start/Stop']}, is_quitting={self.is_quitting}")
        
        # Prevent multiple cycles from running simultaneously
        if hasattr(self, '_cycle_running') and self._cycle_running:
            print("⚠️ WARNING: Bot cycle already running, ignoring duplicate call")
            return
        
        if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
            # Bot is not running or app is quitting, schedule next check or exit
            if not self.is_quitting:
                print(f"⏸️ Bot stopped, scheduling next check in {BOT_CYCLE_CHECK_INTERVAL}ms...")
                self.after(BOT_CYCLE_CHECK_INTERVAL, self.run_bot_cycle)
            else:
                print("🛑 Bot quitting, not scheduling next check")
            return

        try:
            # Mark cycle as running
            self._cycle_running = True
            
            # SAFETY: Only check Roblox window for fishing actions, not for emergency exits
            # Skip window check - user needs to be able to exit if Roblox crashes
            
            # Check for resolution changes that could break detection
            self._check_resolution_change()
            
            # Live feed overlay should already be created when bot started
            # No need to create it here as it's created immediately on start

            # ===== DISCORD: Send initial message on first cycle =====
            if self.discord_loop_count == 0 and self.settings.get("discord_enabled", False):
                print("📤 Discord: Sending initial bot start message...")
                message_style = self.settings.get("discord_message_style", "Screenshot")
                if message_style == "Screenshot":
                    self._send_discord_screenshot("⚡ **BOT STARTED** 🚀\n")
                else:  # Text mode
                    self._send_discord_text("⚡ **BOT STARTED** 🚀\n")

            # Start block (always runs if bot is active)
            print("\n=== CYCLE START ===")
            self._execute_start_block()

            # Check if still running after Start block
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                print("\n--- Bot stopped after START block ---")
                return

            # Misc block (check if enabled)
            if self.bottom_button_states.get("Misc", True):
                print("\n--- Executing MISC Block ---")
                self._update_status("Misc Block", "white")
                self._execute_misc_block()
            else:
                print("\n--- MISC Block DISABLED, skipping ---")

            # Check if still running after Misc block
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                print("\n--- Bot stopped after MISC block ---")
                return

            # Cast block (check if enabled)
            if self.bottom_button_states.get("Cast", True):
                print("\n--- Executing CAST Block ---")
                self._update_status("Cast Block", "white")
                # Close cast visualization overlays at start of cast block (cleanup from previous cycle)
                self._cleanup_cast_overlays()
                self._execute_cast_block()
            else:
                print("\n--- CAST Block DISABLED, skipping ---")

            # Check if still running after Cast block
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                print("\n--- Bot stopped after CAST block ---")
                return

            # Shake block (check if enabled)
            shake_result = None
            if self.bottom_button_states.get("Shake", True):
                print("\n--- Executing SHAKE Block ---")
                self._update_status("Shake Block", "white")
                # Move cast visualization overlays to the right side of shake area
                self._move_cast_overlays_to_side()
                shake_result = self._execute_shake_block()
            else:
                print("\n--- SHAKE Block DISABLED, skipping ---")
                # Move cast visualization overlays even if shake is disabled
                self._move_cast_overlays_to_side()

            # Check if still running after Shake block
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                print("\n--- Bot stopped after SHAKE block ---")
                # Close cast visualization overlays when user stops
                self._cleanup_cast_overlays()
                return

            # Check shake result - if "restart", go back to Misc block
            if shake_result == "restart":
                print("\n--- SHAKE Block returned RESTART, going back to MISC ---")
                # Will schedule next cycle at the end (in finally block)
                return
            elif shake_result == "fish_stage":
                print("\n--- 🐟 SHAKE Block detected FISH, entering FISH STAGE ---")
                self._update_status("Fish Stage", "white")
                # Execute fish stage
                try:
                    fish_result = self._execute_fish_stage()
                    print(f"🐟 Fish stage returned: {fish_result}")
                except Exception as e:
                    print(f"❌ CRITICAL ERROR in fish stage: {e}")
                    import traceback
                    traceback.print_exc()

                print("✅ === FISH STAGE ENDED ===")

                # ===== DISCORD: Increment loop counter and send periodic message =====
                self.discord_loop_count += 1
                print(f"🔄 Discord Loop Count: {self.discord_loop_count}")
                
                if self.settings.get("discord_enabled", False):
                    message_style = self.settings.get("discord_message_style", "Screenshot")
                    
                    # Determine loop threshold based on message style
                    if message_style == "Screenshot":
                        loops_threshold = int(self.settings.get("loops_screenshot", 10))
                    else:  # Text mode
                        loops_threshold = int(self.settings.get("loops_text", 10))
                    
                    # Send periodic message if threshold reached
                    if self.discord_loop_count % loops_threshold == 0:
                        print(f"📤 Discord: Sending periodic update (every {loops_threshold} loops)...")
                        if message_style == "Screenshot":
                            self._send_discord_screenshot()
                        else:
                            self._send_discord_text()

                # Will schedule next cycle at the end (in finally block)
                return

            # Fish block - ALWAYS executes (even if disabled) to wait for fish stage to complete
            # If enabled: Automatically detects and controls fish
            # If disabled: Still waits for fish to appear and end (user controls manually)
            fish_enabled = self.bottom_button_states.get("Fish", True)
            
            if fish_enabled:
                print("\n--- Executing FISH Block (AUTO MODE) ---")
            else:
                print("\n--- FISH Block DISABLED (MANUAL MODE - waiting for fish stage to complete) ---")
            
            # Scan for fish detection continuously (like shake block does)
            # Get timeout and scan settings from shake settings
            shake_style = self.settings.get("shake_style", "Pixel")
            if shake_style == "Navigation":
                fail_cast_timeout = self.settings.get("nav_fail_cast_timeout", 20)
            else:
                fail_cast_timeout = self.settings.get("shake_fail_cast_timeout", 20)
            
            # Get scan FPS based on shake style
            if shake_style == "Pixel":
                scan_fps = self.settings.get("pixel_scan_fps", 60)
            elif shake_style == "Circle":
                scan_fps = self.settings.get("circle_scan_fps", 60)
            elif shake_style == "Navigation":
                scan_fps = self.settings.get("nav_scan_fps", 60)
            else:
                scan_fps = 60
            
            scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.005
            
            capture_mode, use_mss = self._get_capture_mode_settings()
            
            if fish_enabled:
                print(f"  Scanning for fish (timeout: {fail_cast_timeout}s, FPS: {scan_fps})")
            else:
                print(f"  Waiting for fish to appear and end (manual catch) - timeout: {fail_cast_timeout}s")
            
            # Scan loop (similar to shake block's no_pixel_timer loop)
            timeout_start = time.time()
            last_scan_time = time.time()
            fish_was_detected = False
            
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()
                elapsed_time = current_time - timeout_start
                
                # Check if timeout exceeded
                if elapsed_time >= fail_cast_timeout:
                    if fish_enabled:
                        print(f"  Fish detection timeout ({fail_cast_timeout}s) - no fish found")
                    else:
                        print(f"  Fish wait timeout ({fail_cast_timeout}s) - no fish appeared")
                    break
                
                # Check for fish detection
                exit_result = self._check_shake_exit_condition(None, use_mss)
                if exit_result == "fish_stage":
                    if not fish_was_detected:
                        fish_was_detected = True
                        
                        if fish_enabled:
                            # AUTO MODE: Execute fish stage automatically
                            print("\n--- 🐟 FISH Block detected FISH, entering FISH STAGE (AUTO) ---")
                            try:
                                fish_result = self._execute_fish_stage()
                                print(f"🐟 Fish stage returned: {fish_result}")
                            except Exception as e:
                                print(f"❌ CRITICAL ERROR in fish stage: {e}")
                                import traceback
                                traceback.print_exc()

                            print("✅ === FISH STAGE ENDED ===")
                            
                            # ===== DISCORD: Increment loop counter and send periodic message =====
                            self.discord_loop_count += 1
                            print(f"🔄 Discord Loop Count: {self.discord_loop_count}")
                            
                            if self.settings.get("discord_enabled", False):
                                message_style = self.settings.get("discord_message_style", "Screenshot")
                                
                                # Determine loop threshold based on message style
                                if message_style == "Screenshot":
                                    loops_threshold = int(self.settings.get("loops_screenshot", 10))
                                else:  # Text mode
                                    loops_threshold = int(self.settings.get("loops_text", 10))
                                
                                # Send periodic message if threshold reached
                                if self.discord_loop_count % loops_threshold == 0:
                                    print(f"📤 Discord: Sending periodic update (every {loops_threshold} loops)...")
                                    if message_style == "Screenshot":
                                        self._send_discord_screenshot()
                                    else:
                                        self._send_discord_text()
                            
                            # Will schedule next cycle at the end (in finally block)
                            return
                        else:
                            # MANUAL MODE: Fish detected, now wait for it to disappear (user is catching)
                            print("\n--- 🐟 FISH detected - User is manually catching (waiting for fish to end) ---")
                            # Reset timeout so we wait for fish to END, not for initial detection
                            timeout_start = current_time
                
                elif fish_was_detected and exit_result != "fish_stage":
                    # Fish was present but now gone - fish stage ended
                    if not fish_enabled:
                        print("\n--- ✅ FISH STAGE ENDED (manual catch complete) ---")
                        
                        # ===== DISCORD: Increment loop counter and send periodic message =====
                        self.discord_loop_count += 1
                        print(f"🔄 Discord Loop Count: {self.discord_loop_count}")
                        
                        if self.settings.get("discord_enabled", False):
                            message_style = self.settings.get("discord_message_style", "Screenshot")
                            
                            # Determine loop threshold based on message style
                            if message_style == "Screenshot":
                                loops_threshold = int(self.settings.get("loops_screenshot", 10))
                            else:  # Text mode
                                loops_threshold = int(self.settings.get("loops_text", 10))
                            
                            # Send periodic message if threshold reached
                            if self.discord_loop_count % loops_threshold == 0:
                                print(f"📤 Discord: Sending periodic update (every {loops_threshold} loops)...")
                                if message_style == "Screenshot":
                                    self._send_discord_screenshot()
                                else:
                                    self._send_discord_text()
                    
                    # Exit the loop - fish stage is done
                    break
                
                # Sleep until next scan
                last_scan_time = current_time
                time.sleep(scan_delay)
            
            if fish_enabled:
                print("  Fish block completed (no fish detected within timeout)")
            else:
                print("  Fish wait completed")

            print("\n=== CYCLE END ===\n")

        except Exception as e:
            print(f"ERROR in bot cycle: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Always clear the running flag
            self._cycle_running = False
            
            # Schedule next cycle immediately in finally block to ensure it happens
            # Debug: Show why cycle is or isn't restarting
            if self.is_quitting:
                print("🛑 Cycle NOT restarting - Application is quitting")
            elif not self.global_hotkey_states["Start/Stop"]:
                print("⏸️ Cycle NOT restarting - Start/Stop is OFF")
            else:
                print(f"⏱️ Scheduling next cycle in {BOT_CYCLE_CHECK_INTERVAL}ms... (Start/Stop={self.global_hotkey_states['Start/Stop']}, is_quitting={self.is_quitting})")
                self.after(BOT_CYCLE_CHECK_INTERVAL, self.run_bot_cycle)
                print(f"✅ Next cycle scheduled successfully")

    def _execute_start_block(self):
        """
        Start block - initialization and setup before main blocks.
        This always runs when bot is active.
        """
        print("Starting bot cycle...")
        # Start block - currently handles basic initialization

    def _execute_misc_block(self):
        """
        Misc block - miscellaneous settings and configurations.
        Executes Auto Select Rod if enabled.
        """
        print("  Misc block executed")
        
        # Check if Auto Select Rod is enabled
        if self.settings.get("auto_select_rod_enabled", True):
            print("    Auto Select Rod enabled - executing sequence")
            
            # Get hotbar keys
            equipment_bag_key = self.settings.get("hotbar_equipment_bag", "2")
            fishing_rod_key = self.settings.get("hotbar_fishing_rod", "1")
            
            # Get delays
            delay1 = self.settings.get("auto_select_rod_delay1", 0.0)
            delay2 = self.settings.get("auto_select_rod_delay2", 1.0)
            delay3 = self.settings.get("auto_select_rod_delay3", 0.0)
            
            # Delay 1: Before Equipment Bag
            if delay1 > 0:
                print(f"    Delay before Equipment Bag: {delay1}s")
                if not self._interruptible_sleep(delay1):
                    return False
            
            # Press Equipment Bag key
            print(f"    Pressing Equipment Bag key: {equipment_bag_key}")
            self._send_key_press(equipment_bag_key)
            
            # Delay 2: Before Fishing Rod
            if delay2 > 0:
                print(f"    Delay before Fishing Rod: {delay2}s")
                if not self._interruptible_sleep(delay2):
                    return False
            
            # Press Fishing Rod key  
            print(f"    Pressing Fishing Rod key: {fishing_rod_key}")
            self._send_key_press(fishing_rod_key)
            
            # Delay 3: After Fishing Rod
            if delay3 > 0:
                print(f"    Delay after Fishing Rod: {delay3}s")
                if not self._interruptible_sleep(delay3):
                    return False
            
            print("    Auto Select Rod sequence completed")
        else:
            print("    Auto Select Rod disabled")

    def _interruptible_sleep(self, duration):
        """
        Sleep for duration seconds, but check hotkey state and exit condition every 50ms.
        Returns True if completed, False if interrupted.
        """
        if duration <= 0:
            return True

        # Pre-calculate end time to avoid repeated time.time() calls
        end_time = time.time() + duration

        while time.time() < end_time:
            # Check both bot state and exit condition
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                return False  # Interrupted

            sleep_time = min(INTERRUPTIBLE_SLEEP_CHECK_INTERVAL, end_time - time.time())
            if sleep_time > 0:
                time.sleep(sleep_time)

        return True  # Completed

    # AI_SYSTEM_START: CAST_SYSTEM

    def _execute_cast_block(self):  # AI_TARGET: CAST_MODE_SELECTOR
        cast_mode = self.settings["cast_mode"]  # AI_SETTING: CAST_MODE_SELECTOR

        if cast_mode == "Normal":
            self._execute_cast_normal_flow()
        elif cast_mode == "Perfect":
            self._execute_cast_perfect_flow()
        else:
            print(f"  Unknown cast mode: {cast_mode}")

    def _execute_cast_normal_flow(self):  # AI_TARGET: CAST_NORMAL_MODE
        print("  -> Running CAST Normal Mode")
        
        # Optional warning: Check if Roblox window is active (but don't block - user might need emergency control)
        if not _is_roblox_window_active():
            print("⚠️ INFO: Roblox window may not be active - continuing anyway for emergency control")

        try:
            delay1 = self.settings["cast_delay1"]  # AI_SETTING: CAST_DELAY_1
            delay2 = self.settings["cast_delay2"]  # AI_SETTING: CAST_DELAY_2  
            delay3 = self.settings["cast_delay3"]  # AI_SETTING: CAST_DELAY_3

            # Step 1: Initial delay
            if delay1 > 0:
                print(f"    Delay 1: {delay1}s")
                if not self._interruptible_sleep(delay1):
                    print("    Cast interrupted during delay 1")
                    return

            # Step 2: Hold left click
            print(f"    Holding left click for {delay2}s")
            windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

            if not self._interruptible_sleep(delay2):
                print("    Cast interrupted during hold")
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)  # Release before exit
                return

            # Step 3: Release left click
            print(f"    Releasing left click")
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            # Step 4: Final delay
            if delay3 > 0:
                print(f"    Delay 3: {delay3}s")
                if not self._interruptible_sleep(delay3):
                    print("    Cast interrupted during delay 3")
                    return

            print("    Normal cast completed")

        except Exception as e:
            print(f"    Error in Normal cast flow: {e}")
            import traceback
            traceback.print_exc()

    def _execute_cast_perfect_flow(self):  # AI_TARGET: CAST_PERFECT_MODE
        print("  -> Running CAST Perfect Mode")

        try:
            # Get settings from dictionary
            delay1 = self.settings["perfect_delay1"]
            zoom_out_amount = self.settings["zoom_out"]
            delay2 = self.settings["perfect_delay2"]
            zoom_in_amount = self.settings["zoom_in"]
            delay3 = self.settings["perfect_delay3"]
            look_down_amount = self.settings["look_down"]
            delay4 = self.settings["perfect_delay4"]
            look_up_amount = self.settings["look_up"]
            delay5 = self.settings["perfect_delay5"]
            delay6 = self.settings["perfect_delay6"]

            # Get shake area center for cursor positioning
            shake_center_x = (self.shake_box["x1"] + self.shake_box["x2"]) // 2
            shake_center_y = (self.shake_box["y1"] + self.shake_box["y2"]) // 2

            # Step 1: Initial delay
            if delay1 > 0:
                print(f"    Delay 1: {delay1}s")
                if not self._interruptible_sleep(delay1):
                    print("    Perfect cast interrupted during delay 1")
                    return

            # Step 2: Zoom out (scroll down)
            if zoom_out_amount > 0:
                print(f"    Zooming out: scrolling down {zoom_out_amount} times")
                self._perform_scroll_zoom(zoom_out_amount, "down")

            # Step 3: Delay after zoom out
            if delay2 > 0:
                print(f"    Delay 2: {delay2}s")
                if not self._interruptible_sleep(delay2):
                    print("    Perfect cast interrupted during delay 2")
                    return

            # Step 4: Zoom in (scroll up)
            if zoom_in_amount > 0:
                print(f"    Zooming in: scrolling up {zoom_in_amount} times")
                self._perform_scroll_zoom(zoom_in_amount, "up")

            # Step 5: Delay after zoom in
            if delay3 > 0:
                print(f"    Delay 3: {delay3}s")
                if not self._interruptible_sleep(delay3):
                    print("    Perfect cast interrupted during delay 3")
                    return

            # Step 6: Look down
            if look_down_amount > 0:
                print(f"    Looking down: moving cursor down {look_down_amount} pixels")
                self._perform_look_action(shake_center_x, shake_center_y, look_down_amount, "down")

            # Step 7: Delay after look down
            if delay4 > 0:
                print(f"    Delay 4: {delay4}s")
                if not self._interruptible_sleep(delay4):
                    print("    Perfect cast interrupted during delay 4")
                    return

            # Step 8: Look up
            if look_up_amount > 0:
                print(f"    Looking up: moving cursor up {look_up_amount} pixels")
                self._perform_look_action(shake_center_x, shake_center_y, look_up_amount, "up")

            # Step 9: Delay after look up
            if delay5 > 0:
                print(f"    Delay 5: {delay5}s")
                if not self._interruptible_sleep(delay5):
                    print("    Perfect cast interrupted during delay 5")
                    return

            # Step 10: Hold left click
            print(f"    Holding left click")
            windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)

            # Step 11: Delay while holding click
            if delay6 > 0:
                print(f"    Delay 6 (holding): {delay6}s")
                if not self._interruptible_sleep(delay6):
                    print("    Perfect cast interrupted during delay 6")
                    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)  # Release before exit
                    return

            # Step 12: Perfect cast release - Advanced detection system
            print(f"    Starting perfect cast release detection...")
            self._perform_perfect_cast_release()

            # Step 13: Delay (after perfect cast)
            delay8 = self.settings.get("perfect_delay8", 0.0)
            if delay8 > 0:
                print(f"    Delay 8: {delay8}s")
                if not self._interruptible_sleep(delay8):
                    print("    Perfect cast interrupted during delay 8")
                    return

            # Step 15: Zoom in after perfect cast
            final_zoom_in_amount = self.settings.get("final_zoom_in", 5)
            if final_zoom_in_amount > 0:
                print(f"    Post-cast zoom in: scrolling up {final_zoom_in_amount} times")
                self._perform_scroll_zoom(final_zoom_in_amount, "up")

            # Step 16: Delay 9 (after zoom in)
            delay9 = self.settings.get("perfect_delay9", 0.0)
            if delay9 > 0:
                print(f"    Delay 9: {delay9}s")
                if not self._interruptible_sleep(delay9):
                    print("    Perfect cast interrupted during delay 9")
                    return

            # Step 17: Look up
            final_look_up_amount = self.settings.get("final_look_up", 2000)
            if final_look_up_amount > 0:
                print(f"    Post-cast look up: moving cursor up {final_look_up_amount} pixels")
                self._perform_look_action(shake_center_x, shake_center_y, final_look_up_amount, "up")

            # Step 18: Delay 10 (after look up)
            delay10 = self.settings.get("perfect_delay10", 0.0)
            if delay10 > 0:
                print(f"    Delay 10: {delay10}s")
                if not self._interruptible_sleep(delay10):
                    print("    Perfect cast interrupted during delay 10")
                    return

            print("    Perfect cast completed")

        except Exception as e:
            print(f"    Error in Perfect cast flow: {e}")
            import traceback
            traceback.print_exc()
            # Ensure left click is released on error
            try:
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            except Exception as e:
                print(f"    ⚠️ Warning: Failed to release left click: {e}")

    def _perform_perfect_cast_release(self):
        """
        Performs the perfect cast release detection and timing.
        Scans for green bobber and white splash, releases when white reaches green.
        """
        print("    🎯 Perfect Cast Release: Starting advanced detection...")
        
        # Check which release system to use
        release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
        
        if release_style == "Prediction":
            # Route to old prediction system
            print("    ⏱️ Using Prediction (Time-Based) system")
            return self._perform_perfect_cast_release_prediction()
        elif release_style == "GigaSigmaUltraMode":
            # Route to GigaSigma Ultra system
            print("    🧠 Using GigaSigmaUltraMode system")
            return self._perform_perfect_cast_release_gigasigma()
        else:
            # Route to velocity-percentage system (default)
            print("    📊 Using Velocity-Percentage system")
            return self._perform_perfect_cast_release_velocity_percentage()
    
    def _perform_perfect_cast_release_velocity_percentage(self):
        """
        NEW SYSTEM: Velocity-adaptive percentage-based release.
        Releases when white has traveled X% of distance to green (X varies by velocity).
        """
        # Check if we're being called by GigaSigmaUltraMode
        if hasattr(self, '_gigasigma_state'):
            print("    ⚡ GigaSigma Enhanced Velocity Detection: Starting bounce-aware tracking...")
        else:
            print("    ⚡ Velocity-Percentage Release: Starting detection...")
        
        # Check if advanced detection is available
        if not DXCAM_AVAILABLE:
            print("    ⚠️ Advanced detection not available (dxcam/numpy missing)")
            print("    ⏱️ Using fallback timing method...")
            fail_timeout = self.settings.get("perfect_cast_fail_scan_timeout", 3.0)
            time.sleep(fail_timeout)  # Simple timeout-based release
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            print(f"    ⏱️ Released after {fail_timeout}s timeout")
            return
        
        # Get settings from GUI
        green_tolerance = self.settings.get("perfect_cast_green_color_tolerance", 10)
        white_tolerance = self.settings.get("perfect_cast_white_color_tolerance", 10)
        
        # Calculate proper frame delay based on FPS setting
        scan_fps = self.settings.get("perfect_cast_scan_fps", 200)
        if scan_fps >= 1000:
            frame_delay = 0.0  # 0ms delay for 1000+ FPS (maximum performance)
        else:
            frame_delay = 1.0 / scan_fps  # Standard formula: delay = 1.0/fps
        print(f"    ⚡ Perfect Cast FPS: {scan_fps} (frame delay: {frame_delay*1000:.1f}ms)")
        
        # Check if GigaSigmaUltraMode - use longer timeout for bounce mode
        release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
        if release_style == "GigaSigmaUltraMode":
            fail_timeout = 10.0  # Fixed 10 seconds for GigaSigma
        else:
            fail_timeout = self.settings.get("perfect_cast_fail_scan_timeout", 3.0)

        # Get NEW percentage-based release setting
        release_percentage = self.settings.get("perfect_cast_release_percentage", 80)  # 70-95%
        minimum_distance_base = self.settings.get("perfect_cast_minimum_distance", 25)

        # Calculate scaling factor based on current resolution vs reference (1440p)
        reference_height = self.settings.get("perfect_cast_reference_height", 1440)
        current_height = self.current_height
        scaling_factor = current_height / reference_height

        # Scale distance threshold (we measure in current resolution)
        minimum_distance = int(minimum_distance_base * scaling_factor)

        # Velocity band system uses NORMALIZED 1440p equivalent thresholds for consistent behavior
        # Fixed bands: <400, 400-600, 600-800, 800-1000, 1000-1200, >1200 px/s (1440p equivalent)
        
        print(f"    📏 Resolution scaling: {current_height}p / {reference_height}p = {scaling_factor:.2f}x")
        print(f"    📐 Minimum release distance: {minimum_distance}px (base: {minimum_distance_base}px)")
        print(f"    📊 Release percentage: {release_percentage}% of total distance")
        
        # Check if GigaSigma is active to show enhanced velocity bands
        if hasattr(self, '_gigasigma_state'):
            print(f"    🚴 GigaSigma Velocity bands (1440p equiv): <400 | 400-500 | 500-600 | 600-700 | 700-800 | 800-900 | 900-1000")
            print(f"    🚴                                      | 1000-1100 | 1100-1200 | 1200-1400 | 1400-1600 | 1600-1800 | 1800-2000 | 2000-2200 | >2200 px/s")
        else:
            print(f"    🚴 Velocity bands (1440p equiv): <400 | 400-600 | 600-800 | 800-1000 | 1000-1200 | >1200 px/s")

        # Get shake area coordinates (region to scan) - use same as regular shake detection
        shake_area = self.shake_box.copy()
        
        # EXTEND DOWNWARD: Increase scan area below to catch white bar further down
        # Add 50% more height below the shake area to catch distant white bars
        original_height = shake_area["y2"] - shake_area["y1"]
        extension = int(original_height * 0.5)  # Add 50% more height
        shake_area["y2"] = min(shake_area["y2"] + extension, self.current_height)  # Don't exceed screen height
        
        extended_height = shake_area["y2"] - shake_area["y1"]
        print(f"    📏 Scan area extended: {original_height}px → {extended_height}px (+{extension}px downward)")
        
        # Calculate scaled tracking box size based on shake area dimensions
        # Reference: 60px box at 1500px width (2560x1440 shake box)
        # Increased from 20px to 60px to give more padding as bobber expands in-game
        shake_width = shake_area["x2"] - shake_area["x1"]
        tracking_box_size = int(60 * (shake_width / 1500))
        print(f"    📦 Tracking box size: {tracking_box_size}px (scaled from 60px reference)")
        
        try:
            # Use same capture mode setting as shake detection, but keep d.py's optimization methods
            capture_mode, use_mss = self._get_capture_mode_settings()
            
            # Setup region coordinates
            x1, y1 = shake_area["x1"], shake_area["y1"] 
            x2, y2 = shake_area["x2"], shake_area["y2"]
            region = (x1, y1, x2, y2)
            
            # Initialize capture method
            camera = None
            
            if use_mss:
                # MSS mode - compatible with d.py methods but uses MSS capture
                print(f"    📷 Using MSS capture mode for perfect cast release")
                mss_monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            else:
                # DXCam mode - same as d.py (preferred for performance)
                print(f"    🎥 Using DXCAM capture mode for perfect cast release")
                
                # CRITICAL: Clear device cache before creating new camera
                try:
                    if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                        dxcam._device_info.clear()
                    elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                        dxcam.device_info.clear()
                except (AttributeError, TypeError) as e:
                    # Expected when DXCAM attributes don't exist or have different types
                    print(f"⚠️ DXCAM device cache clear warning (harmless): {e}")
                except Exception as e:
                    print(f"⚠️ DXCAM device cache clear unexpected error: {e}")
                
                camera = dxcam.create(output_idx=0, output_color="BGR")
                if camera is None:
                    print("    ❌ Failed to initialize DXCam")
                    print("    ⏱️ Using fallback timing method...")
                    time.sleep(fail_timeout)
                    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    return
                
                # Track camera for cleanup
                if not hasattr(self, '_active_cameras'):
                    self._active_cameras = []
                self._active_cameras.append(camera)
                print(f"    ✅ DXCam camera created successfully")
            
            # Tracking state variables
            is_tracking = False
            last_midpoint_x = None
            last_green_y = None
            frames_since_lost = 0
            
            # White position tracking for speed calculation
            white_positions = []
            timestamps = []
            last_time_to_impact = None  # Track previous time-to-impact to detect bounce
            
            # NEW: Track initial white position for percentage calculation
            initial_white_y = None  # Y position when white first detected
            initial_distance = None  # Initial distance between white and green
            
            # Timing variables
            scan_time_start = time.time()
            frame_count = 0
            should_print = True  # Print every frame initially, then every 10th
            
            print(f"    🔍 Scanning area: ({shake_area['x1']}, {shake_area['y1']}) to ({shake_area['x2']}, {shake_area['y2']})")
            print(f"    ⚙️ Settings: Green tolerance={green_tolerance}, White tolerance={white_tolerance}, Timeout={fail_timeout}s")
            
            # Pre-initialize overlay windows to avoid lag on first display
            if self.global_gui_settings.get("Show Perfect Cast Overlay", True):
                print(f"    🖼️ Pre-initializing overlay windows...")
                self._preinitialize_cast_overlays()
            
            print(f"    🎯 Starting Perfect Cast Release detection...")
            print(f"    📋 Output format: F#frame | time_ms | MODE | Distance | Progress%")
            
            while True:
                frame_start_time = time.time()
                current_time = time.time()
                elapsed_time = current_time - scan_time_start
                
                # Check for timeout
                if elapsed_time >= fail_timeout:
                    print(f"    ⏱️ TIMEOUT REACHED ({fail_timeout}s) - Releasing left click")
                    self._update_status("Perfect Cast: TIMEOUT", "red")
                    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    break
                
                # Check if bot has been stopped
                if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                    print("    ⏸️ Bot stopped during perfect cast release")
                    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    break
                
                frame_count += 1
                
                # Capture frame - support both MSS and DXCam modes
                frame = None
                
                if use_mss:
                    # MSS capture - works with d.py detection methods
                    try:
                        with mss.mss() as sct:
                            screenshot = sct.grab(mss_monitor)
                            frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
                    except Exception as e:
                        print(f"    ❌ MSS capture error: {e}")
                        continue
                else:
                    # DXCam capture - same as d.py (optimal performance)
                    frame = camera.grab(region=region)
                
                if frame is None:
                    continue
                
                # STEP 1: GREEN DETECTION - Adaptive scanning (tracking vs full)
                green_midpoint_result = None
                
                # If tracking mode, try tracking box first
                if is_tracking and last_midpoint_x is not None and last_green_y is not None:
                    green_midpoint_result = find_green_tracking_box(
                        frame, last_midpoint_x, last_green_y, GREEN_BGR, green_tolerance, tracking_box_size
                    )
                    
                    if green_midpoint_result is not None:
                        frames_since_lost = 0  # Success - continue tracking
                    else:
                        frames_since_lost += 1
                        if frames_since_lost >= 3:  # Lost tracking - switch modes
                            is_tracking = False
                            frames_since_lost = 0
                
                # If not tracking OR tracking failed, do full scan
                if not is_tracking or green_midpoint_result is None:
                    green_midpoint_result = find_green_full_scan(frame, GREEN_BGR, green_tolerance)
                    if green_midpoint_result is not None:
                        is_tracking = True  # Found green - switch to tracking
                        frames_since_lost = 0
                
                # STEP 2: WHITE DETECTION - Only if green found
                white_result = None
                green_left_x = None
                green_right_x = None
                green_width = None
                if green_midpoint_result is not None:
                    local_midpoint_x, local_green_y, green_left_x, green_right_x = green_midpoint_result
                    
                    # Calculate green width
                    green_width = green_right_x - green_left_x
                    
                    # Convert to screen coordinates for position tracking
                    midpoint_x = shake_area['x1'] + local_midpoint_x
                    green_y = shake_area['y1'] + local_green_y
                    
                    # Update tracking state (store local coordinates for tracking)
                    last_midpoint_x = local_midpoint_x
                    last_green_y = local_green_y
                    
                    # White detection ONLY BELOW green line, across full green width
                    local_white_x = None
                    local_white_y = None
                    white_result = find_white_below_green(frame, local_green_y, green_left_x, green_right_x, white_tolerance)
                    if white_result is not None:
                        local_white_x, local_white_y = white_result
                        white_x = shake_area['x1'] + local_white_x
                        white_y = shake_area['y1'] + local_white_y
                        white_result = (white_x, white_y)
                
                # STEP 3: CALCULATE - Timing and decision logic
                scan_duration = (current_time - scan_time_start) * 1000
                
                # Prepare prediction info for visualization
                prediction_info = None
                
                # STEP 4: DECISION LOGIC
                if green_midpoint_result is not None and white_result is not None and local_white_y is not None:
                    white_x, white_y = white_result
                    mode_text = "TRACK" if is_tracking else "FULL"
                    local_distance = abs(local_white_y - local_green_y)
                    
                    # NEW: Track initial white position when first detected
                    if initial_white_y is None:
                        initial_white_y = local_white_y
                        initial_distance = local_distance
                        print(f"    👁️ Initial white detected: Y={local_white_y}px, Distance={local_distance}px")
                    
                    # Calculate progress percentage (how far white has traveled toward green)
                    if initial_distance is not None and initial_distance > 0:
                        distance_traveled = initial_distance - local_distance
                        progress_percentage = (distance_traveled / initial_distance) * 100
                    else:
                        progress_percentage = 0
                    
                    # Create prediction info with distance and progress
                    prediction_info = {
                        'distance': local_distance,
                        'progress': progress_percentage,
                        'initial_distance': initial_distance
                    }

                    # Print frame status (every 10th frame to reduce overhead)
                    if frame_count % 10 == 0:
                        print(f"    📊 F#{frame_count} | {scan_duration:.1f}ms | {mode_text} | Dist:{local_distance}px | {progress_percentage:.1f}%")
                    
                    # Store white position and timestamp for velocity tracking
                    white_positions.append((white_x, white_y))
                    timestamps.append(current_time)
                    
                    # Keep last 5 positions for velocity calculation (more points = smoother tracking)
                    if len(white_positions) > 5:
                        white_positions.pop(0)
                        timestamps.pop(0)
                    
                    # NEW: VELOCITY-BASED PERCENTAGE RELEASE SYSTEM
                    # Calculate velocity to determine appropriate release percentage
                    velocity_y = None
                    if len(white_positions) >= 3:
                        velocity_y = calculate_speed_and_predict(white_positions, timestamps)
                        
                        # DISABLED: Extrapolation can be inaccurate, use raw detection for more conservative progress
                        # Using raw first detection makes progress calculation more reliable
                    
                    # Determine release percentage based on NORMALIZED velocity bands (6 bands)
                    # Use 1440p equivalent thresholds: <400, 400-600, 600-800, 800-1000, 1000-1200, >1200
                    # Initialize velocity_band with fallback value
                    velocity_band = "UNKNOWN (calculating...)"
                    
                    if velocity_y is not None:
                        # Normalize velocity to 1440p equivalent for consistent band selection
                        normalized_velocity = abs(velocity_y) / scaling_factor
                        
                        if normalized_velocity < 400:
                            # Band 1: <400 px/s (95%)
                            active_release_percentage = self.settings.get("perfect_cast_band1_release", 95)
                            velocity_band = f"<400 px/s"
                        elif normalized_velocity < 600:
                            # Band 2: 400-600 px/s (94%)
                            active_release_percentage = self.settings.get("perfect_cast_band2_release", 94)
                            velocity_band = f"400-600 px/s"
                        elif normalized_velocity < 800:
                            # Band 3: 600-800 px/s (93%)
                            active_release_percentage = self.settings.get("perfect_cast_band3_release", 93)
                            velocity_band = f"600-800 px/s"
                        elif normalized_velocity < 1000:
                            # Band 4: 800-1000 px/s (92%)
                            active_release_percentage = self.settings.get("perfect_cast_band4_release", 92)
                            velocity_band = f"800-1000 px/s"
                        elif normalized_velocity < 1200:
                            # Band 5: 1000-1200 px/s (90%)
                            active_release_percentage = self.settings.get("perfect_cast_band5_release", 90)
                            velocity_band = f"1000-1200 px/s"
                        else:
                            # Band 6: >1200 px/s (88%)
                            active_release_percentage = self.settings.get("perfect_cast_band6_release", 88)
                            velocity_band = f">1200 px/s"
                    else:
                        # Fallback to default if velocity not available yet (get from GUI settings)
                        active_release_percentage = release_percentage
                    
                    # GIGASIGMA: Track velocity direction for bounce detection (do this ALWAYS, not just at threshold)
                    gigasigma_state = getattr(self, '_gigasigma_state', None)
                    if gigasigma_state and gigasigma_state['allow_bounce'] and velocity_y is not None:
                        # Store velocity during initial phase (before first bounce) for accurate tracking
                        # IMPORTANT: Only store ONCE when first good velocity is available (don't overwrite)
                        if gigasigma_state['stored_velocity'] is None and abs(velocity_y) > 100:
                            # Store if we're in initial_up phase OR if detection started late and we have no phase yet
                            current_phase = gigasigma_state.get('bounce_phase', 'initial_up')
                            if current_phase in ['initial_up', 'unknown'] or gigasigma_state['bounce_count'] == 0:
                                # Store NORMALIZED velocity (1440p equivalent) for consistent comparisons
                                normalized_velocity = velocity_y / scaling_factor
                                gigasigma_state['stored_velocity'] = normalized_velocity
                                gigasigma_state['stored_abs_velocity'] = abs(normalized_velocity)
                                phase_info = f" (phase: {current_phase})" if current_phase != 'initial_up' else ""
                                print(f"    💾 Stored velocity (LOCKED): {velocity_y:.1f}px/s raw → {normalized_velocity:.1f}px/s (1440p){phase_info} - will use this for entire cast")
                        
                        # Detect velocity direction based on Y position change
                        # In screen coords: white starts BELOW green (higher Y), moves UP (decreasing Y) toward green
                        # So negative velocity_y = moving up/toward green, positive = moving down/away from green
                        current_direction = 1 if velocity_y < 0 else -1  # 1 = UP toward green, -1 = DOWN away from green
                        
                        # Safeguard: If velocity is too small, ignore direction changes (noise/jitter)
                        if abs(velocity_y) < 50:  # Ignore very small movements
                            current_direction = gigasigma_state.get('last_stable_direction', current_direction)
                        else:
                            gigasigma_state['last_stable_direction'] = current_direction
                        
                        # Debug: Print velocity and direction
                        if frame_count % 5 == 0:  # Every 5 frames
                            direction_str = "↑UP" if current_direction == 1 else "↓DOWN"
                            phase = "unknown"
                            if 'bounce_phase' in gigasigma_state:
                                phase = gigasigma_state['bounce_phase']
                            stored_vel = gigasigma_state.get('stored_abs_velocity')
                            stored_vel_str = f"{stored_vel:.1f}px/s" if stored_vel is not None else "not yet stored"
                            current_vel_str = f"{velocity_y:.1f}px/s" if velocity_y is not None else "calculating..."
                            print(f"    🎯 Current: {current_vel_str} | Stored: {stored_vel_str} (1440p) | {direction_str} | Phase: {phase} | Bounces: {gigasigma_state['bounce_count']}/{gigasigma_state['max_bounces']}")
                        
                        # Track bounce phases: "initial_up" → "bounced_down" → "returning_up" (= 1 complete bounce)
                        if 'bounce_phase' not in gigasigma_state:
                            gigasigma_state['bounce_phase'] = 'initial_up'
                        
                        phase = gigasigma_state['bounce_phase']
                        
                        # State machine for bounce detection
                        if phase == 'initial_up' and current_direction == -1:
                            # Hit green and now going DOWN - entering bounce phase
                            gigasigma_state['bounce_phase'] = 'bounced_down'
                            print(f"    ⬇️ Hit green! Now bouncing away...")
                        
                        elif phase == 'bounced_down' and current_direction == 1:
                            # Was going down, now going UP again - completed a full bounce!
                            gigasigma_state['bounce_count'] += 1
                            gigasigma_state['bounce_phase'] = 'returning_up'
                            print(f"    🔄 FULL BOUNCE COMPLETE! (up→hit→down→UP) Count: {gigasigma_state['bounce_count']}/{gigasigma_state['max_bounces']}")
                        
                        elif phase == 'returning_up' and current_direction == -1:
                            # White is now going DOWN during return journey
                            # But only release if we're actually close to green again (within cast threshold)
                            if abs(distance_from_target) <= cast_threshold_1440p:
                                # CRITICAL: White hit green again during return - THIS IS WHEN WE RELEASE!
                                print(f"    🎯 WHITE HIT GREEN ON RETURN! RELEASING NOW!")
                                gigasigma_state['should_release_now'] = True  # Flag for immediate release
                            else:
                                print(f"    ⬇️ Returning down but not at green yet (distance: {abs(distance_from_target):.1f}px > {cast_threshold_1440p}px)")
                        
                        elif phase == 'returning_up' and current_direction == 1:
                            # Still going UP during return - waiting for peak
                            pass  # Keep waiting
                        
                        # Note: We don't update last_velocity_direction anymore, using phase tracking instead
                    
                    # GIGASIGMA: Decide when to release
                    should_release = False
                    
                    if gigasigma_state and gigasigma_state['allow_bounce']:
                        # PRIMARY RELEASE CONDITION: White hit green on return journey
                        if gigasigma_state.get('should_release_now', False):
                            should_release = True
                            print(f"    🚀 GIGASIGMA RELEASE: White hit green on return bounce!")
                            bounce_adjustment = 0  # No adjustment needed, releasing at exact moment
                        
                        elif gigasigma_state['bounce_count'] >= gigasigma_state['max_bounces']:
                            # FALLBACK: If somehow we miss the exact moment, release at adjusted threshold after bounce
                            # This applies user's auto-tune adjustments for "too early/too late" feedback
                            bounce_adjustment = 0
                            # Use STORED velocity for bounce adjustment (current velocity is near-zero after bounce)
                            stored_abs_velocity = gigasigma_state.get('stored_abs_velocity')
                            if stored_abs_velocity is not None:
                                abs_velocity = stored_abs_velocity
                                # Finer-grained adjustments with more velocity bands
                                # Ultra-fast range split for precision
                                if abs_velocity > 2200:
                                    # Extreme (>2200): -10% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 10
                                elif abs_velocity > 2000:
                                    # Ultra+ (2000-2200): -9% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 9
                                elif abs_velocity > 1800:
                                    # Ultra (1800-2000): -8% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 8
                                elif abs_velocity > 1600:
                                    # Very very fast+ (1600-1800): -7% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 7
                                elif abs_velocity > 1400:
                                    # Very very fast (1400-1600): -5% per bounce (1558 late, 1592 early - split difference)
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 5
                                elif abs_velocity > 1200:
                                    # Very fast (1200-1400): -4% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 4
                                elif abs_velocity > 1100:
                                    # Fast+ (1100-1200): -5% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 5
                                elif abs_velocity > 1000:
                                    # Fast (1000-1100): -3% per bounce (was -7%, too early at 1024px/s)
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 3
                                elif abs_velocity > 900:
                                    # Medium-fast+ (900-1000): -3% per bounce (was -6%, too early at 927px/s)
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 3
                                elif abs_velocity > 800:
                                    # Medium-fast (800-900): -2% per bounce (was -5%, too early at 864px/s)
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 2
                                elif abs_velocity > 700:
                                    # Medium (700-800): -4% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 4
                                elif abs_velocity > 600:
                                    # Medium- (600-700): -3% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 3
                                elif abs_velocity > 500:
                                    # Slow-medium (500-600): -2% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 2
                                elif abs_velocity > 400:
                                    # Slow (400-500): -1% per bounce
                                    bounce_adjustment = gigasigma_state['bounce_count'] * 1
                                else:
                                    # Very slow (<400): 0% per bounce
                                    bounce_adjustment = 0
                        else:
                            # Not ready to release yet
                            bounce_adjustment = 0
                        
                        adjusted_release_percentage = active_release_percentage - bounce_adjustment
                        
                        # Release after enough bounces AND adjusted progress threshold met
                        if gigasigma_state['bounce_count'] >= gigasigma_state['max_bounces']:
                            if progress_percentage >= adjusted_release_percentage:
                                should_release = True
                                if bounce_adjustment > 0:
                                    print(f"    ✅ Bounce quota met ({gigasigma_state['bounce_count']} bounces), adjusted release from {active_release_percentage}% to {adjusted_release_percentage}%")
                                else:
                                    print(f"    ✅ Bounce quota met ({gigasigma_state['bounce_count']} bounces), releasing!")
                        else:
                            # Still waiting for more bounces
                            if progress_percentage >= active_release_percentage and frame_count % 10 == 0:
                                print(f"    ⏳ At release threshold but waiting for bounce {gigasigma_state['bounce_count']+1}/{gigasigma_state['max_bounces']}...")
                    else:
                        # No bounce mode, release normally
                        should_release = progress_percentage >= active_release_percentage
                    
                    # Release when conditions met
                    if should_release:
                        # Ensure all variables are defined with fallback values
                        if 'active_release_percentage' not in locals():
                            active_release_percentage = release_percentage
                        if 'velocity_band' not in locals():
                            velocity_band = "UNKNOWN"
                        
                        # For GigaSigma mode, use stored velocity from initial_up phase (before bounce)
                        release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
                        
                        # Determine which velocity to use and whether it needs normalization
                        if release_style == "GigaSigmaUltraMode":
                            gigasigma_state = getattr(self, '_gigasigma_state', None)
                            if gigasigma_state and gigasigma_state.get('stored_velocity') is not None:
                                # Stored velocity is already normalized to 1440p
                                display_velocity = abs(gigasigma_state['stored_velocity'])
                                print(f"    📊 Using stored velocity: {display_velocity:.1f}px/s (1440p equiv, measured during initial approach)")
                            else:
                                # Fallback to current velocity if stored not available
                                display_velocity = abs(velocity_y) / scaling_factor if velocity_y else 0
                        else:
                            # Non-GigaSigma modes: normalize current velocity
                            display_velocity = abs(velocity_y) / scaling_factor if velocity_y else 0
                        
                        # Determine which threshold to display (adjusted or original)
                        display_threshold = active_release_percentage
                        gigasigma_state = getattr(self, '_gigasigma_state', None)
                        if gigasigma_state and gigasigma_state['allow_bounce'] and gigasigma_state['bounce_count'] > 0:
                            # Show adjusted threshold if GigaSigma with bounces
                            # Use stored abs_velocity for accurate calculation (fallback to display_velocity if not available)
                            abs_velocity = gigasigma_state.get('stored_abs_velocity', display_velocity)
                            if abs_velocity > 1200:
                                bounce_adjustment = gigasigma_state['bounce_count'] * 20
                            elif abs_velocity > 1000:
                                bounce_adjustment = gigasigma_state['bounce_count'] * 18
                            elif abs_velocity > 800:
                                bounce_adjustment = gigasigma_state['bounce_count'] * 16
                            elif abs_velocity > 600:
                                bounce_adjustment = gigasigma_state['bounce_count'] * 14
                            else:
                                bounce_adjustment = gigasigma_state['bounce_count'] * 12
                            display_threshold = active_release_percentage - bounce_adjustment
                        
                        # Show appropriate message based on release style
                        release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
                        if release_style == "GigaSigmaUltraMode":
                            print(f"    🧠 GIGASIGMA ULTRA RELEASE!")
                        else:
                            print(f"    🚀 VELOCITY-BASED RELEASE!")
                        print(f"       Velocity: {display_velocity:.1f}px/s (1440p equiv) | Band: {velocity_band}")
                        print(f"       Progress: {progress_percentage:.1f}% (threshold: {display_threshold}%)")
                        print(f"       Distance remaining: {local_distance}px")
                        
                        # Update prediction info (store normalized velocity for display)
                        prediction_info['release_type'] = "VELOCITY-PERCENTAGE"
                        prediction_info['release_percentage'] = active_release_percentage
                        prediction_info['velocity'] = display_velocity  # Normalized to 1440p for consistent display
                        prediction_info['velocity_band'] = velocity_band
                        
                        # Show final info overlay
                        self._show_release_info(prediction_info)
                        
                        # Store last cast data for GigaSigma auto-tune
                        release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
                        if release_style == "GigaSigmaUltraMode":
                            # Safety check: Ensure display_velocity is valid before storing
                            if display_velocity is None or display_velocity == 0:
                                print(f"    ⚠️ Skipping auto-tune storage - velocity not yet calculated")
                            else:
                                self._last_cast_velocity = display_velocity  # Store normalized velocity
                                # Use stored velocity for accurate band determination
                                gigasigma_state = getattr(self, '_gigasigma_state', None)
                                abs_velocity = gigasigma_state.get('stored_abs_velocity', display_velocity) if gigasigma_state else display_velocity
                                
                                # Safety check: Ensure abs_velocity is valid
                                if abs_velocity is None or abs_velocity == 0:
                                    print(f"    ⚠️ Skipping auto-tune storage - abs_velocity invalid")
                                else:
                                    # Determine band index based on stored velocity (not current zero velocity)
                                    # Use NORMALIZED 1440p thresholds since abs_velocity is already normalized
                                    if abs_velocity < 400:
                                        self._last_cast_band = 0  # <400
                                        display_band_name = f"<400 px/s"
                                    elif abs_velocity < 600:
                                        self._last_cast_band = 1  # 400-600
                                        display_band_name = f"400-600 px/s"
                                    elif abs_velocity < 800:
                                        self._last_cast_band = 2  # 600-800
                                        display_band_name = f"600-800 px/s"
                                    elif abs_velocity < 1000:
                                        self._last_cast_band = 3  # 800-1000
                                        display_band_name = f"800-1000 px/s"
                                    elif abs_velocity < 1200:
                                        self._last_cast_band = 4  # 1000-1200
                                        display_band_name = f"1000-1200 px/s"
                                    elif abs_velocity < 1400:
                                        self._last_cast_band = 5  # 1200-1400
                                        display_band_name = f"1200-1400 px/s"
                                    elif abs_velocity < 1600:
                                        self._last_cast_band = 6  # 1400-1600
                                        display_band_name = f"1400-1600 px/s"
                                    elif abs_velocity < 1800:
                                        self._last_cast_band = 7  # 1600-1800
                                        display_band_name = f"1600-1800 px/s"
                                    elif abs_velocity < 2000:
                                        self._last_cast_band = 8  # 1800-2000
                                        display_band_name = f"1800-2000 px/s"
                                    elif abs_velocity < 2200:
                                        self._last_cast_band = 9  # 2000-2200
                                        display_band_name = f"2000-2200 px/s"
                                    else:
                                        self._last_cast_band = 10  # >2200
                                        display_band_name = f">2200 px/s"
                                    
                                    # Reset tune usage flag for new cast
                                    self._tune_used_this_cast = False
                                    
                                    # Debug: Confirm storage (safe - values guaranteed valid at this point)
                                    print(f"    💾 Auto-tune data stored: velocity={display_velocity:.1f} px/s, band={display_band_name}")
                                    
                                    # Capture values for GUI update to avoid scope issues
                                    final_display_velocity = display_velocity
                                    final_display_band_name = display_band_name
                                    
                                    # Update button status (schedule on main thread to avoid GUI update issues)
                                    def update_tune_status():
                                        if hasattr(self, 'cast_view') and self.cast_view and hasattr(self.cast_view, 'tune_status_label'):
                                            try:
                                                self.cast_view.tune_status_label.configure(
                                                    text=f"Ready to tune: {final_display_band_name} at {final_display_velocity:.0f} px/s",
                                                    text_color="#4ECDC4"
                                                )
                                                print(f"    ✅ Auto-tune button status updated")
                                            except Exception as e:
                                                print(f"    ⚠️ Failed to update tune button: {e}")
                                    
                                    # Schedule GUI update on main thread
                                    try:
                                        self.after(0, update_tune_status)
                                    except Exception as e:
                                        print(f"    ⚠️ Failed to schedule tune button update: {e}")
                        
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        print("    ✅ PERFECT CAST COMPLETE")
                        self._update_status("Perfect Cast: SUCCESS", "green")
                        break
                                
                # STEP 3.5: VISUALIZATION - Show green and white positions
                if green_midpoint_result is not None and green_width is not None and local_white_y is not None:
                    # Only show visualization if Show Perfect Cast Overlay is enabled
                    if self.global_gui_settings.get("Show Perfect Cast Overlay", True):
                        self._show_cast_visualization(
                            shake_area, local_midpoint_x, local_green_y, 
                            local_white_y,  # Updated every scan when white detected
                            y2 - y1,  # Frame height
                            green_width,  # Width of detected green
                            None  # Don't show prediction info during detection
                    )
                
                # EMERGENCY DISTANCE FALLBACK
                # If white gets very close (within minimum distance), release immediately
                # BUT: Skip in GigaSigma bounce mode - we want to let it bounce!
                gigasigma_state = getattr(self, '_gigasigma_state', None)
                skip_emergency = (gigasigma_state and 
                                 gigasigma_state['allow_bounce'] and 
                                 gigasigma_state['bounce_count'] < gigasigma_state['max_bounces'])
                
                # GigaSigma timeout fallback - if waiting too long for bounce, release anyway
                if skip_emergency and frame_count > 200:  # ~10 seconds at 20fps
                    print(f"    ⏰ GigaSigma timeout after {frame_count} frames - releasing anyway")
                    skip_emergency = False
                
                if green_midpoint_result is not None and white_result is not None and local_white_y is not None:
                    if local_distance <= minimum_distance and not skip_emergency:
                        print(f"    🚨 EMERGENCY RELEASE! Distance: {local_distance}px (threshold: {minimum_distance}px)")
                        if prediction_info is not None:
                            prediction_info['release_type'] = "EMERGENCY"
                            prediction_info['threshold'] = minimum_distance
                        self._show_release_info(prediction_info)
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        print("    ✅ PERFECT CAST COMPLETE")
                        break
                    elif local_distance <= minimum_distance and skip_emergency:
                        print(f"    🔄 Very close ({local_distance}px) but waiting for bounce {gigasigma_state['bounce_count']+1}/{gigasigma_state['max_bounces']}...")
                
                # Frame delay based on configured FPS
                if frame_delay > 0:
                    time.sleep(frame_delay)
            
        except Exception as e:
            import traceback
            print(f"    ❌ Perfect Cast Release Error: {e}")
            print(f"    📍 Full traceback:")
            traceback.print_exc()
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        finally:
            # Cleanup
            if camera is not None:
                try:
                    camera.release()
                    # Remove from active cameras list
                    if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                        self._active_cameras.remove(camera)
                except Exception as cleanup_error:
                    print(f"    ❌ Error during camera cleanup: {cleanup_error}")
            
            # Close cast visualization overlays (keep them visible, cleanup happens at shake/fish/stop)
            
            print("    ✅ Perfect Cast Release detection ended")
            return True  # Successful completion
    
    def _cleanup_all_cameras(self):
        """Cleanup all active cameras to prevent resource leaks."""
        if hasattr(self, '_active_cameras'):
            for camera in self._active_cameras[:]:  # Use slice to safely iterate
                try:
                    if camera:
                        camera.release()
                except Exception as e:
                    print(f"⚠️ Camera cleanup error: {e}")
            self._active_cameras.clear()
    
    def _monitor_performance(self):
        """Monitor application performance and log potential issues."""
        try:
            # Count active GUI elements
            canvas_items = len(self.canvas.find_all()) if hasattr(self, 'canvas') else 0
            particles = len(getattr(self, 'comet_trail_particles', []))
            nebula_particles = len(getattr(self, 'nebula_particles', []))
            animation_comets = len(getattr(self, 'animation_comets', []))
            active_cameras = len(getattr(self, '_active_cameras', []))
            
            # Log performance warnings if thresholds exceeded
            if canvas_items > 1000:
                print(f"⚠️ Performance Warning: {canvas_items} canvas items (high)")
            if particles + nebula_particles + animation_comets > 200:
                print(f"⚠️ Performance Warning: {particles + nebula_particles + animation_comets} total particles (high)")
            if active_cameras > 2:
                print(f"⚠️ Resource Warning: {active_cameras} active cameras (cleanup recommended)")
                
        except Exception as e:
            # Don't let performance monitoring crash the app
            pass

    def _perform_perfect_cast_release_gigasigma(self):
        """
        GigaSigmaUltraMode: Advanced precision system with velocity detection and automatic bounce.
        
        Uses velocity-percentage logic with enhanced features:
        - Multi-sample velocity detection with outlier removal
        - Automatic 1-bounce mode for maximum accuracy (always enabled)
        - Confidence scoring based on sample consistency
        """
        print("    🧠 GigaSigmaUltraMode: Starting detection...")
        
        # GigaSigma ALWAYS uses 1 bounce for maximum accuracy (hardcoded)
        allow_bounce = True
        max_bounces = 1
        
        print(f"    🔄 Bounce Mode: ACTIVE (always 1 bounce)")
        
        # Track bounce state
        bounce_count = 0
        last_velocity_direction = None  # 1 = moving up (toward green), -1 = moving down (away from green)
        velocity_samples = []
        
        # Store these in settings so the detection loop can access them
        self._gigasigma_state = {
            'allow_bounce': allow_bounce,
            'max_bounces': max_bounces,
            'bounce_count': 0,
            'last_velocity_direction': None,
            'velocity_samples': [],
            'waiting_for_bounce': allow_bounce,  # Wait for bounce before releasing
            'stored_velocity': None,  # Store velocity before bounce for accurate tracking
            'stored_abs_velocity': None,  # Store absolute velocity for band selection
            'bounce_phase': 'initial_up'  # Initialize phase tracking
        }
        
        # Use the standard velocity-percentage logic with bounce detection
        try:
            result = self._perform_perfect_cast_release_velocity_percentage()
            return result if result is not None else True
        finally:
            # Always cleanup GigaSigma state after cast completion
            if hasattr(self, '_gigasigma_state'):
                print("    🧹 Cleaning up GigaSigma state for next cast")
                delattr(self, '_gigasigma_state')

    def _perform_perfect_cast_release_prediction(self):
        """
        Time-based prediction with 11 velocity bands.
        Releases when time_to_impact <= reaction_delay (varies by velocity band).
        
        This uses velocity tracking to predict when the white marker will reach green,
        and releases with adaptive timing based on velocity bands (11 speed ranges).
        """
        print("    ⚡ Prediction (Time-Based) Release: Starting detection...")
        
        # Get settings
        green_tolerance = self.settings.get("perfect_cast_green_color_tolerance", 10)
        white_tolerance = self.settings.get("perfect_cast_white_color_tolerance", 10)
        fail_timeout = self.settings.get("perfect_cast_fail_scan_timeout", 3.0)
        
        # Get timing adjustments for each velocity band
        timing_very_slow = self.settings.get("perfect_cast_very_slow_timing", 0)
        timing_slow = self.settings.get("perfect_cast_slow_timing", 0)
        timing_walking = self.settings.get("perfect_cast_walking_timing", 0)
        timing_jogging = self.settings.get("perfect_cast_jogging_timing", 0)
        timing_running = self.settings.get("perfect_cast_running_timing", 0)
        timing_cycling = self.settings.get("perfect_cast_cycling_timing", 0)
        timing_motorcycle = self.settings.get("perfect_cast_motorcycle_timing", 0)
        timing_driving = self.settings.get("perfect_cast_driving_timing", 0)
        timing_flying = self.settings.get("perfect_cast_flying_timing", 0)
        timing_rocket = self.settings.get("perfect_cast_rocket_timing", 0)
        timing_lightning = self.settings.get("perfect_cast_lightning_timing", 0)
        
        # Setup capture region - use same as regular shake detection
        shake_area = self.shake_box
        if shake_area is None:
            print("    ❌ Failed to get shake detection area")
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            return
        
        y1, x1, y2, x2 = shake_area['y1'], shake_area['x1'], shake_area['y2'], shake_area['x2']
        region = (x1, y1, x2, y2)
        
        # Initialize camera
        use_dxcam = DXCAM_AVAILABLE and self.settings.get("capture_mode", "MSS") == "DXCam"
        camera = None
        if use_dxcam:
            try:
                import dxcam
                camera = dxcam.create(output_color="BGR")
                if camera is None:
                    use_dxcam = False
            except Exception as e:
                print(f"⚠️ DXCAM initialization failed: {e}")
                use_dxcam = False
        
        # Tracking state
        white_positions = []
        timestamps = []
        last_time_to_impact = None
        is_tracking = False
        last_midpoint_x = None
        last_green_y = None
        frames_since_lost = 0
        tracking_box_size = 100
        
        # Calculate scaling factor based on resolution
        reference_height = 1440
        actual_height = y2 - y1
        scaling_factor = actual_height / reference_height
        
        # Minimum distance threshold (scaled)
        minimum_distance = 30 * scaling_factor
        
        frame_count = 0
        scan_time_start = time.time()
        
        print(f"    📊 Output format: F#frame | time_ms | MODE | Distance_pixels")
        
        while True:
            frame_start_time = time.time()
            current_time = time.time()
            elapsed_time = current_time - scan_time_start
            
            # Check for timeout
            if elapsed_time >= fail_timeout:
                print(f"    ⏰ TIMEOUT REACHED ({fail_timeout}s) - Releasing left click")
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                break
            
            # Check if bot has been stopped
            if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                print("    🛑 Bot stopped during perfect cast release")
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                break
            
            frame_count += 1
            
            # Capture frame
            frame = None
            if use_dxcam and camera:
                frame = camera.grab(region=region)
            else:
                try:
                    with mss.mss() as sct:
                        mss_monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
                        screenshot = sct.grab(mss_monitor)
                        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_BGRA2BGR)
                except Exception as e:
                    continue
            
            if frame is None:
                continue
            
            # STEP 1: GREEN DETECTION
            green_midpoint_result = None
            
            if is_tracking and last_midpoint_x is not None and last_green_y is not None:
                green_midpoint_result = find_green_tracking_box(
                    frame, last_midpoint_x, last_green_y, GREEN_BGR, green_tolerance, tracking_box_size
                )
                if green_midpoint_result is not None:
                    frames_since_lost = 0
                else:
                    frames_since_lost += 1
                    if frames_since_lost >= 3:
                        is_tracking = False
                        frames_since_lost = 0
            
            if not is_tracking or green_midpoint_result is None:
                green_midpoint_result = find_green_full_scan(frame, GREEN_BGR, green_tolerance)
                if green_midpoint_result is not None:
                    is_tracking = True
                    frames_since_lost = 0
            
            # STEP 2: WHITE DETECTION
            white_result = None
            green_left_x = None
            green_right_x = None
            green_width = None
            local_distance = 0
            
            if green_midpoint_result is not None:
                local_midpoint_x, local_green_y, green_left_x, green_right_x = green_midpoint_result
                
                # Calculate green width
                green_width = green_right_x - green_left_x
                
                last_midpoint_x = local_midpoint_x
                last_green_y = local_green_y
                
                white_result = find_white_below_green(frame, local_green_y, green_left_x, green_right_x, white_tolerance)
                if white_result is not None:
                    local_white_x, local_white_y = white_result
                    white_x = x1 + local_white_x
                    white_y = y1 + local_white_y
                    
                    local_distance = abs(local_white_y - local_green_y)
                    
                    # Print status
                    if frame_count % 10 == 0:
                        mode_text = "TRACK" if is_tracking else "FULL"
                        scan_duration = (current_time - scan_time_start) * 1000
                        print(f"    ✅ F#{frame_count} | {scan_duration:.1f}ms | {mode_text} | Dist:{local_distance}")
                    
                    # Store position for velocity tracking
                    white_positions.append((white_x, white_y))
                    timestamps.append(current_time)
                    
                    if len(white_positions) > 5:
                        white_positions.pop(0)
                        timestamps.pop(0)
                    
                    # Initialize prediction_info for visualization
                    prediction_info = None
                    
                    # VELOCITY-BASED PREDICTION
                    if len(white_positions) >= 3:
                        velocity_y = calculate_speed_and_predict(white_positions, timestamps)
                        
                        min_speed_threshold = 5 * scaling_factor
                        if velocity_y is not None:
                            velocity_magnitude = abs(velocity_y)
                            if velocity_magnitude > min_speed_threshold:
                                white_above_green = local_white_y < local_green_y
                                moving_toward_green = (white_above_green and velocity_y > 0) or (not white_above_green and velocity_y < 0)
                                
                                if moving_toward_green:
                                    time_to_impact = local_distance / velocity_magnitude
                                
                                # Define velocity bands (scaled to resolution)
                                v700 = 700 * scaling_factor
                                v800 = 800 * scaling_factor
                                v900 = 900 * scaling_factor
                                v1000 = 1000 * scaling_factor
                                v1100 = 1100 * scaling_factor
                                v1200 = 1200 * scaling_factor
                                v1300 = 1300 * scaling_factor
                                v1400 = 1400 * scaling_factor
                                v1500 = 1500 * scaling_factor
                                v1600 = 1600 * scaling_factor
                                
                                # Determine reaction delay based on velocity band
                                if velocity_magnitude < v700:
                                    reaction_delay = 0.060
                                    user_adjustment = timing_very_slow * 0.001
                                elif velocity_magnitude < v800:
                                    reaction_delay = 0.058
                                    user_adjustment = timing_slow * 0.001
                                elif velocity_magnitude < v900:
                                    reaction_delay = 0.057
                                    user_adjustment = timing_walking * 0.001
                                elif velocity_magnitude < v1000:
                                    reaction_delay = 0.056
                                    user_adjustment = timing_jogging * 0.001
                                elif velocity_magnitude < v1100:
                                    reaction_delay = 0.055
                                    user_adjustment = timing_running * 0.001
                                elif velocity_magnitude < v1200:
                                    reaction_delay = 0.050
                                    user_adjustment = timing_cycling * 0.001
                                elif velocity_magnitude < v1300:
                                    reaction_delay = 0.048
                                    user_adjustment = timing_motorcycle * 0.001
                                elif velocity_magnitude < v1400:
                                    reaction_delay = 0.047
                                    user_adjustment = timing_driving * 0.001
                                elif velocity_magnitude < v1500:
                                    reaction_delay = 0.046
                                    user_adjustment = timing_flying * 0.001
                                elif velocity_magnitude < v1600:
                                    reaction_delay = 0.050
                                    user_adjustment = timing_rocket * 0.001
                                else:
                                    reaction_delay = 0.049
                                    user_adjustment = timing_lightning * 0.001
                                
                                adjusted_reaction_delay = reaction_delay + user_adjustment
                                
                                # Build prediction info for visualization
                                prediction_info = {
                                    'distance': local_distance,
                                    'velocity': velocity_magnitude,
                                    'time_to_impact': time_to_impact * 1000,  # Convert to ms
                                    'release_timing': adjusted_reaction_delay * 1000  # Convert to ms
                                }
                    
                    # VISUALIZATION - Show green and white positions (without prediction info during loop)
                    if self.global_gui_settings.get("Show Perfect Cast Overlay", True):
                        self._show_cast_visualization(
                            shake_area, local_midpoint_x, local_green_y,
                            local_white_y,  # Updated every scan when white detected
                            y2 - y1,  # Frame height
                            green_width,  # Width of detected green
                            None  # Don't show prediction info during loop (only at release)
                        )
                    
                    # Continue with velocity-based prediction logic
                    if prediction_info is not None:
                                
                                # RELEASE CONDITION
                                if time_to_impact <= adjusted_reaction_delay:
                                    print(f"    🎯 PREDICTIVE RELEASE!")
                                    print(f"       Distance: {local_distance}px")
                                    print(f"       Velocity: {velocity_magnitude:.1f}px/s")
                                    print(f"       Time to impact: {time_to_impact*1000:.1f}ms")
                                    print(f"       Release timing: {adjusted_reaction_delay*1000:.1f}ms")
                                    
                                    # Show final prediction info overlay at release
                                    if self.global_gui_settings.get("Show Perfect Cast Overlay", True):
                                        self._show_cast_visualization(
                                            shake_area, local_midpoint_x, local_green_y,
                                            local_white_y,
                                            y2 - y1,
                                            green_width,
                                            prediction_info  # Show prediction info at release
                                        )
                                    
                                    windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    print("    ✅ PERFECT CAST COMPLETE")
                                    break
                                
                                last_time_to_impact = time_to_impact
                    
                    # SLOW SPEED FALLBACK
                    if len(white_positions) >= 3:
                        slow_speed_threshold = minimum_distance * 0.8
                        if local_distance <= slow_speed_threshold:
                            recent_distances = []
                            for i in range(-3, 0):
                                pos, _ = white_positions[i]
                                dist = abs(pos[1] - (y1 + local_green_y))
                                recent_distances.append(dist)
                            
                            if recent_distances[-1] < recent_distances[0]:
                                print(f"    🎯 SLOW SPEED RELEASE! Distance: {local_distance}px")
                                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                print("    ✅ PERFECT CAST COMPLETE (slow speed)")
                                break
                    
                    # EMERGENCY RELEASE
                    emergency_distance = minimum_distance * 0.5
                    if local_distance <= emergency_distance:
                        print(f"    🚨 EMERGENCY RELEASE! Distance: {local_distance}px")
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        print("    ✅ PERFECT CAST COMPLETE (emergency)")
                        break

    def _perform_scroll_zoom(self, amount, direction):
        """
        Perform zoom by scrolling like a human would.
        
        Args:
            amount: Number of scroll steps
            direction: "up" for zoom in, "down" for zoom out
        """
        try:
            # Mouse wheel constants
            WHEEL_DELTA = 120  # Standard wheel delta
            
            if direction == "down":
                # Scroll down (zoom out)
                wheel_data = -WHEEL_DELTA
            else:
                # Scroll up (zoom in)
                wheel_data = WHEEL_DELTA
            
            for i in range(amount):
                # Send mouse wheel event
                windll.user32.mouse_event(0x0800, 0, 0, wheel_data, 0)  # 0x0800 = MOUSEEVENTF_WHEEL
                
                # Small delay between scroll steps - optimized for responsiveness
                time.sleep(0.025)  # 25ms instead of 100ms for much faster scrolling
                
                # Check for interruption
                if not self.global_hotkey_states["Start/Stop"] or self.is_quitting:
                    print(f"    Scroll zoom interrupted at step {i+1}/{amount}")
                    return False
                    
        except Exception as e:
            print(f"    Error in scroll zoom: {e}")
            return False
            
        return True

    def _perform_look_action(self, center_x, center_y, pixels, direction):
        """
        Perform look action using right click drag method with small steps.
        
        Args:
            center_x, center_y: Center coordinates of shake area
            pixels: Number of pixels to move
            direction: "up" or "down"
        """
        try:
            # Step 1: Set cursor to middle of shake area
            windll.user32.SetCursorPos(center_x, center_y)
            
            # Step 2: Move cursor down by 1 pixel (anti-roblox method)
            windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            
            # Step 3: Hold down right click
            windll.user32.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            
            # Small delay to ensure right click registers
            time.sleep(0.025)
            
            # Step 4: Move cursor by specified pixels using small steps method
            steps = 100
            pixels_per_step = pixels // steps
            remainder = pixels % steps
            
            if direction == "down":
                # Move down in small steps
                for _ in range(steps):
                    windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, pixels_per_step, 0, 0)
                    time.sleep(MOUSE_SMOOTH_DELAY)  # Optimized smoothness delay
                # Handle any remainder pixels
                if remainder > 0:
                    windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, remainder, 0, 0)
            else:
                # Move up in small steps (negative pixels)
                for _ in range(steps):
                    windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, -pixels_per_step, 0, 0)
                    time.sleep(MOUSE_SMOOTH_DELAY)  # Optimized smoothness delay
                # Handle any remainder pixels
                if remainder > 0:
                    windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, -remainder, 0, 0)
            
            # Step 5: Release right click
            windll.user32.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            
            # Step 6: Set cursor back to middle of shake area
            windll.user32.SetCursorPos(center_x, center_y)
            
            # Step 7: Move cursor down by 1 pixel (final anti-roblox method)
            windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            
        except Exception as e:
            print(f"    Error in look action: {e}")
            # Ensure right click is released on error
            try:
                windll.user32.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            except Exception as e:
                print(f"    ⚠️ Warning: Failed to release right click: {e}")
    # AI_SYSTEM_END: CAST_SYSTEM

    # AI_SYSTEM_START: SHAKE_SYSTEM

    def _execute_shake_block(self):  # AI_TARGET: SHAKE_MODE_SELECTOR
        shake_style = self.settings["shake_style"]  # AI_SETTING: SHAKE_MODE_SELECTOR

        if shake_style == "Pixel":
            return self._execute_shake_pixel_mode()
        elif shake_style == "Navigation":
            return self._execute_shake_navigation_mode()
        elif shake_style == "Circle":
            return self._execute_shake_circle_mode()

    def _execute_shake_pixel_mode(self):  # AI_TARGET: SHAKE_PIXEL_DETECTION
        print("  -> Running SHAKE Pixel Mode")

        try:
            click_count = self.settings["shake_click_count"]  # AI_SETTING: SHAKE_CLICK_COUNT
            color_tolerance = self.settings["shake_color_tolerance"]  # AI_SETTING: SHAKE_COLOR_TOLERANCE
            pixel_distance_tolerance_base = self.settings["shake_pixel_distance_tolerance"]  # AI_SETTING: SHAKE_PIXEL_TOLERANCE
            scan_fps = self.settings["shake_scan_fps"]
            duplicate_timeout = self.settings["shake_duplicate_timeout"]
            fail_cast_timeout = self.settings["shake_fail_cast_timeout"]
            # Calculate scan delay from FPS with adaptive adjustment for Discord
            base_scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.005
            scan_delay = base_scan_delay
            consecutive_errors = 0  # Track consecutive capture errors

            # Initialize capture method based on settings
            x1, y1 = self.shake_box["x1"], self.shake_box["y1"]
            x2, y2 = self.shake_box["x2"], self.shake_box["y2"]
            region = (x1, y1, x2, y2)
            
            # Scale pixel distance tolerance to current resolution
            # Reference: 10px at 1500px width (2560x1440 shake box ~1500px wide)
            shake_width = x2 - x1
            pixel_distance_tolerance = pixel_distance_tolerance_base * (shake_width / 1500)

            # Initialize capture method
            camera = None
            capture_mode, use_mss = self._get_capture_mode_settings()
            
            if use_mss:
                # Use MSS for capture
                print(f"    Using MSS capture mode for shake detection")
                mss_monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            else:
                # Try to create DXCam with fallback handling for Discord conflicts
                print(f"    Using DXCAM capture mode for shake detection")
                
                # CRITICAL: Clear device cache before creating new camera
                try:
                    if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                        dxcam._device_info.clear()
                    elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                        dxcam.device_info.clear()
                except:
                    pass
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Release any previous camera instance before retry
                        if camera is not None:
                            try:
                                camera.release()
                                time.sleep(0.05)  # Brief delay for cleanup
                            except:
                                pass
                            camera = None
                        
                        camera = dxcam.create(output_idx=0, output_color="BGR")
                        if camera:
                            # Track camera for cleanup
                            if not hasattr(self, '_active_cameras'):
                                self._active_cameras = []
                            self._active_cameras.append(camera)
                            print(f"    ✅ DXCam camera created successfully")
                            break
                        else:
                            print(f"    DXCam creation failed (attempt {attempt + 1}/{max_retries})")
                            time.sleep(0.1)  # Brief delay before retry
                    except Exception as e:
                        print(f"    DXCam error (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(0.1)
                
                if not camera:
                    print("    ❌ ERROR: Failed to create dxcam camera after retries")
                    print("    💡 TIP: Try restarting the macro or switch to MSS mode in settings")
                    return "restart"

            # Tracking variables
            last_pixel_pos = None
            duplicate_timer = 0.0
            no_pixel_timer = 0.0
            last_scan_time = time.time()

            print(f"    Scanning shake area ({x1},{y1}) to ({x2},{y2})")
            print(f"    Settings: Mode={capture_mode}, FPS={scan_fps}, Clicks={click_count}, ColorTol={color_tolerance}")
            print(f"    Pixel Distance Tolerance: {pixel_distance_tolerance_base}px (base) → {pixel_distance_tolerance:.1f}px (scaled for {shake_width}px width)")

            # Main shake loop
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()

                # Capture screen region with adaptive error handling
                frame = None
                try:
                    if use_mss:
                        # Use MSS capture
                        with mss.mss() as sct:
                            screenshot = sct.grab(mss_monitor)
                            frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
                    else:
                        # Use DXCam capture
                        frame = camera.grab(region=region)
                    
                    if frame is None:
                        # Frame capture failed - could be Discord interference
                        consecutive_errors += 1
                        if consecutive_errors > 10:
                            # Too many failures - reduce scan rate temporarily
                            scan_delay = min(base_scan_delay * 3, 0.05)  # Max 50ms delay
                            print(f"    Reducing scan rate due to capture failures (delay: {scan_delay:.3f}s)")
                        time.sleep(scan_delay)
                        continue
                    else:
                        # Successful capture - reset error counter and scan delay
                        if consecutive_errors > 0:
                            consecutive_errors = 0
                            scan_delay = base_scan_delay  # Restore original speed
                except Exception as capture_error:
                    # Capture failed - likely Discord conflict
                    consecutive_errors += 1
                    if consecutive_errors % 5 == 0:  # Log every 5th error to avoid spam
                        print(f"    Frame capture error #{consecutive_errors} ({capture_mode} - Discord interference?): {capture_error}")
                    
                    # Adaptive delay based on error count
                    error_delay = min(base_scan_delay * (1 + consecutive_errors * 0.1), 0.1)  # Max 100ms
                    time.sleep(error_delay)
                    continue

                # Find white pixel (255, 255, 255) with color tolerance
                white_pixel = self._find_white_pixel(frame, color_tolerance)

                if white_pixel:
                    # Found a white pixel
                    pixel_x, pixel_y = white_pixel
                    # Convert to screen coordinates
                    screen_x = x1 + pixel_x
                    screen_y = y1 + pixel_y

                    # Check if it's a duplicate (within distance tolerance)
                    is_duplicate = False
                    if last_pixel_pos:
                        distance = ((screen_x - last_pixel_pos[0]) ** 2 + (screen_y - last_pixel_pos[1]) ** 2) ** 0.5
                        is_duplicate = distance <= pixel_distance_tolerance

                    if is_duplicate:
                        # Same pixel detected - increment duplicate timer
                        duplicate_timer += (current_time - last_scan_time)

                        if duplicate_timer >= duplicate_timeout:
                            # Timer ended - click the pixel and reset timer
                            print(f"    ⏱️ Duplicate timer ended ({duplicate_timeout}s) - clicking same pixel at ({screen_x}, {screen_y})")
                            self._click_at_position(screen_x, screen_y, click_count)
                            duplicate_timer = 0.0
                            # Clear tracking so next detection of same pixel is treated as new
                            last_pixel_pos = None
                    else:
                        # New pixel at different location
                        if duplicate_timer > 0:
                            # We were timing a duplicate but found new pixel - reset timer and click new pixel
                            print(f"    🔄 New pixel found during duplicate timer - resetting timer and clicking at ({screen_x}, {screen_y})")
                            duplicate_timer = 0.0
                        else:
                            # First pixel or completely new pixel after no duplicates
                            print(f"    🎯 New pixel detected - clicking at ({screen_x}, {screen_y})")
                        
                        # Click new pixel and start tracking it
                        self._click_at_position(screen_x, screen_y, click_count)
                        last_pixel_pos = (screen_x, screen_y)
                        duplicate_timer = 0.0

                    # Reset no-pixel timer since we found something
                    no_pixel_timer = 0.0

                else:
                    # No white pixel found
                    no_pixel_timer += (current_time - last_scan_time)
                    
                    # Reset duplicate tracking when no pixels are found
                    if duplicate_timer > 0 or last_pixel_pos:
                        duplicate_timer = 0.0
                        last_pixel_pos = None

                    # Check exit condition (fish detection based on track style)
                    exit_result = self._check_shake_exit_condition(camera, use_mss)
                    if exit_result == "fish_stage":
                        if camera and not use_mss:
                            try:
                                camera.release()
                                if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                                    self._active_cameras.remove(camera)
                            except:
                                pass
                        return "fish_stage"  # Proceed to fish stage

                    if no_pixel_timer >= fail_cast_timeout:
                        # Fail cast timeout - return to Misc block
                        print(f"    ⚠️ No white pixels found for {fail_cast_timeout}s - returning to Misc block")
                        if camera and not use_mss:
                            try:
                                camera.release()
                                if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                                    self._active_cameras.remove(camera)
                            except:
                                pass
                        return "restart"  # Go back to start of loop (Misc)

                last_scan_time = current_time
                time.sleep(scan_delay)

            # Bot stopped - clean up camera
            try:
                if camera and not use_mss:
                    camera.release()
                    if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                        self._active_cameras.remove(camera)
                    print("    DXCam camera released successfully")
                elif use_mss:
                    print("    MSS capture completed successfully")
            except Exception as cleanup_error:
                print(f"    Camera cleanup error: {cleanup_error}")
            return "continue"

        except Exception as e:
            print(f"    Error in Shake Pixel mode: {e}")
            import traceback
            traceback.print_exc()
            # Ensure camera is released even on error
            try:
                if camera and not use_mss:
                    camera.release()
                    if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                        self._active_cameras.remove(camera)
            except Exception as e:
                print(f"⚠️ Camera cleanup warning: {e}")
                pass
            return "restart"

    def _execute_shake_circle_mode(self):
        """
        Shake Circle mode: Scan for circles using Hough Circle Transform in shake_box area.
        - Scans at specified FPS rate using circle detection from a.py
        - Clicks on circle when found (with click_count clicks)
        - Tracks duplicate circles with distance tolerance
        - Duplicate timeout prevents spam clicking same circle
        - Fail cast timeout returns to Misc block if no circles found
        - Uses dxcam or MSS for capture, windll for clicks
        """
        print("  -> Running SHAKE Circle Mode")

        try:
            # Load settings
            click_count = self.settings["circle_click_count"]
            pixel_distance_tolerance_base = self.settings["circle_pixel_distance_tolerance"]
            scan_fps = self.settings["circle_scan_fps"]
            duplicate_timeout = self.settings["circle_duplicate_timeout"]
            fail_cast_timeout = self.settings["circle_fail_cast_timeout"]
            # Calculate scan delay from FPS
            base_scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.005
            scan_delay = base_scan_delay
            consecutive_errors = 0

            # Initialize capture method based on settings
            x1, y1 = self.shake_box["x1"], self.shake_box["y1"]
            x2, y2 = self.shake_box["x2"], self.shake_box["y2"]
            region = (x1, y1, x2, y2)
            
            # Scale pixel distance tolerance to current resolution
            # Reference: 10px at 1500px width (2560x1440 shake box ~1500px wide)
            shake_width = x2 - x1
            pixel_distance_tolerance = pixel_distance_tolerance_base * (shake_width / 1500)

            # Initialize capture method
            camera = None
            capture_mode, use_mss = self._get_capture_mode_settings()
            
            if use_mss:
                # Use MSS for capture
                print(f"    Using MSS capture mode for circle detection")
                mss_monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            else:
                # Try to create DXCam with fallback handling
                print(f"    Using DXCAM capture mode for circle detection")
                
                # CRITICAL: Clear device cache before creating new camera
                try:
                    if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                        dxcam._device_info.clear()
                    elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                        dxcam.device_info.clear()
                except:
                    pass
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Release any previous camera instance before retry
                        if camera is not None:
                            try:
                                camera.release()
                                time.sleep(0.05)  # Brief delay for cleanup
                            except:
                                pass
                            camera = None
                        
                        camera = dxcam.create(output_idx=0, output_color="BGR")
                        if camera:
                            # Track camera for cleanup
                            if not hasattr(self, '_active_cameras'):
                                self._active_cameras = []
                            self._active_cameras.append(camera)
                            print(f"    ✅ DXCam camera created successfully")
                            break
                        else:
                            print(f"    DXCam creation failed (attempt {attempt + 1}/{max_retries})")
                            time.sleep(0.1)
                    except Exception as e:
                        print(f"    DXCam error (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(0.1)
                
                if not camera:
                    print("    ❌ ERROR: Failed to create dxcam camera after retries")
                    return "restart"

            # Tracking variables
            last_circle_pos = None
            duplicate_timer = 0.0
            no_circle_timer = 0.0
            last_scan_time = time.time()

            print(f"    Scanning shake area ({x1},{y1}) to ({x2},{y2}) for circles")
            print(f"    Settings: Mode={capture_mode}, FPS={scan_fps}, Clicks={click_count}")
            print(f"    Pixel Distance Tolerance: {pixel_distance_tolerance_base}px (base) → {pixel_distance_tolerance:.1f}px (scaled for {shake_width}px width)")

            # Main circle detection loop
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()

                # Capture screen region
                frame = None
                try:
                    if use_mss:
                        # Use MSS capture
                        with mss.mss() as sct:
                            screenshot = sct.grab(mss_monitor)
                            frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
                    else:
                        # Use DXCam capture
                        frame = camera.grab(region=region)
                    
                    if frame is None:
                        consecutive_errors += 1
                        if consecutive_errors > 10:
                            scan_delay = min(base_scan_delay * 3, 0.05)
                            print(f"    Reducing scan rate due to capture failures (delay: {scan_delay:.3f}s)")
                        time.sleep(scan_delay)
                        continue
                    else:
                        if consecutive_errors > 0:
                            consecutive_errors = 0
                            scan_delay = base_scan_delay
                except Exception as capture_error:
                    consecutive_errors += 1
                    if consecutive_errors % 5 == 0:
                        print(f"    Frame capture error #{consecutive_errors} ({capture_mode}): {capture_error}")
                    
                    error_delay = min(base_scan_delay * (1 + consecutive_errors * 0.1), 0.1)
                    time.sleep(error_delay)
                    continue

                # Detect circles using the same method as a.py
                circle_center = self._detect_circle_in_frame(frame)

                if circle_center:
                    # Found a circle
                    circle_x, circle_y = circle_center
                    # Convert to screen coordinates
                    screen_x = x1 + circle_x
                    screen_y = y1 + circle_y

                    # Check if it's a duplicate (within distance tolerance)
                    is_duplicate = False
                    if last_circle_pos:
                        distance = ((screen_x - last_circle_pos[0]) ** 2 + (screen_y - last_circle_pos[1]) ** 2) ** 0.5
                        is_duplicate = distance <= pixel_distance_tolerance

                    if is_duplicate:
                        # Same circle detected - increment duplicate timer
                        duplicate_timer += (current_time - last_scan_time)

                        if duplicate_timer >= duplicate_timeout:
                            # Timer ended - click the circle and reset timer
                            print(f"    ⏱️ Duplicate timer ended ({duplicate_timeout}s) - clicking same circle at ({screen_x}, {screen_y})")
                            self._click_at_position(screen_x, screen_y, click_count)
                            duplicate_timer = 0.0
                            # Clear tracking so next detection of same circle is treated as new
                            last_circle_pos = None
                    else:
                        # New circle at different location
                        if duplicate_timer > 0:
                            # We were timing a duplicate but found new circle - reset timer and click new circle
                            print(f"    🔄 New circle found during duplicate timer - resetting timer and clicking at ({screen_x}, {screen_y})")
                            duplicate_timer = 0.0
                        else:
                            # First circle or completely new circle after no duplicates
                            print(f"    🎯 New circle detected - clicking at ({screen_x}, {screen_y})")
                        
                        # Click new circle and start tracking it
                        self._click_at_position(screen_x, screen_y, click_count)
                        last_circle_pos = (screen_x, screen_y)
                        duplicate_timer = 0.0

                    # Reset no-circle timer since we found something
                    no_circle_timer = 0.0

                else:
                    # No circle found
                    no_circle_timer += (current_time - last_scan_time)
                    
                    # Reset duplicate tracking when no circles are found
                    if duplicate_timer > 0 or last_circle_pos:
                        duplicate_timer = 0.0
                        last_circle_pos = None

                    # Check exit condition (fish detection based on track style)
                    exit_result = self._check_shake_exit_condition(camera, use_mss)
                    if exit_result == "fish_stage":
                        if camera and not use_mss:
                            try:
                                camera.release()
                                if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                                    self._active_cameras.remove(camera)
                            except:
                                pass
                        return "fish_stage"  # Proceed to fish stage

                    if no_circle_timer >= fail_cast_timeout:
                        # Fail cast timeout - return to Misc block
                        print(f"    ⚠️ No circles found for {fail_cast_timeout}s - returning to Misc block")
                        if camera and not use_mss:
                            try:
                                camera.release()
                                if hasattr(self, '_active_cameras') and camera in self._active_cameras:
                                    self._active_cameras.remove(camera)
                            except:
                                pass
                        return "restart"  # Go back to start of loop (Misc)

                last_scan_time = current_time
                time.sleep(scan_delay)

            # Bot stopped - clean up camera
            try:
                if camera and not use_mss:
                    camera.release()
                    print("    DXCam camera released successfully")
                elif use_mss:
                    print("    MSS capture completed successfully")
            except Exception as cleanup_error:
                print(f"    Camera cleanup error: {cleanup_error}")
            return "continue"

        except Exception as e:
            print(f"    Error in Shake Circle mode: {e}")
            import traceback
            traceback.print_exc()
            # Ensure camera is released even on error
            try:
                if camera and not use_mss:
                    camera.release()
            except:
                pass
            return "restart"

    def _execute_shake_navigation_mode(self):
        """
        Shake Navigation mode: Press navigation key once, then scan for white pixels.
        - Presses navigation key ONCE at the start (never again)
        - Scans shake_box area for white pixels at specified FPS
        - Sends Enter key when white pixel found
        - Fail cast timeout checks for fish exit condition
        - If white pixels reappear during timeout, reset timeout timer
        - Uses centralized exit condition based on fish track style
        """
        print("  -> Running SHAKE Navigation Mode")

        try:
            # Load settings
            nav_key = self.settings.get("nav_key", "\\")
            color_tolerance = self.settings.get("nav_color_tolerance", 0)
            scan_fps = self.settings.get("nav_scan_fps", 200)
            fail_cast_timeout = self.settings.get("nav_fail_cast_timeout", 3)
            # Calculate scan delay
            base_scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.005
            scan_delay = base_scan_delay
            consecutive_errors = 0

            # Get shake area coordinates
            x1, y1 = self.shake_box["x1"], self.shake_box["y1"]
            x2, y2 = self.shake_box["x2"], self.shake_box["y2"]
            region = (x1, y1, x2, y2)

            # Initialize capture method
            camera = None
            capture_mode, use_mss = self._get_capture_mode_settings()

            if use_mss:
                # Use MSS for capture
                print(f"    Using MSS capture mode for shake detection")
                mss_monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
            else:
                # Try to create DXCam
                print(f"    Using DXCAM capture mode for shake detection")
                
                # CRITICAL: Clear device cache before creating new camera
                try:
                    if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                        dxcam._device_info.clear()
                    elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                        dxcam.device_info.clear()
                except:
                    pass
                
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Release any previous camera instance before retry
                        if camera is not None:
                            try:
                                camera.release()
                                time.sleep(0.05)  # Brief delay for cleanup
                            except:
                                pass
                            camera = None
                        
                        camera = dxcam.create(output_idx=0, output_color="BGR")
                        if camera:
                            # Track camera for cleanup
                            if not hasattr(self, '_active_cameras'):
                                self._active_cameras = []
                            self._active_cameras.append(camera)
                            print(f"    ✅ DXCam camera created successfully")
                            break
                        else:
                            print(f"    DXCam creation failed (attempt {attempt + 1}/{max_retries})")
                            time.sleep(0.1)
                    except Exception as e:
                        print(f"    DXCam error (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(0.1)

                if not camera:
                    print("    ERROR: Failed to create dxcam camera after retries")
                    return "restart"

            # ONE-TIME NAVIGATION KEY PRESS (only happens once)
            print(f"    ⌨️ Pressing navigation key '{nav_key}' (ONE TIME ONLY)")
            self._send_key_press(nav_key)
            time.sleep(0.1)  # Brief delay after key press

            # Tracking variables
            no_pixel_timer = 0.0
            last_scan_time = time.time()

            print(f"    Scanning shake area ({x1},{y1}) to ({x2},{y2})")
            print(f"    Settings: Mode={capture_mode}, FPS={scan_fps}, ColorTol={color_tolerance}, NavKey={nav_key}")

            # Main shake loop
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()

                # Capture screen region with error handling
                frame = None
                try:
                    if use_mss:
                        with mss.mss() as sct:
                            screenshot = sct.grab(mss_monitor)
                            frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
                    else:
                        frame = camera.grab(region=region)

                    if frame is None:
                        consecutive_errors += 1
                        if consecutive_errors > 10:
                            scan_delay = min(base_scan_delay * 3, 0.05)
                            print(f"    Reducing scan rate due to capture failures (delay: {scan_delay:.3f}s)")
                        time.sleep(scan_delay)
                        continue
                    else:
                        if consecutive_errors > 0:
                            consecutive_errors = 0
                            scan_delay = base_scan_delay
                except Exception as capture_error:
                    consecutive_errors += 1
                    if consecutive_errors % 5 == 0:
                        print(f"    Frame capture error #{consecutive_errors}: {capture_error}")
                    error_delay = min(base_scan_delay * (1 + consecutive_errors * 0.1), 0.1)
                    time.sleep(error_delay)
                    continue

                # Find white pixel (255, 255, 255) with color tolerance
                white_pixel = self._find_white_pixel(frame, color_tolerance)

                if white_pixel:
                    # Found white pixel - send Enter key
                    pixel_x, pixel_y = white_pixel
                    screen_x = x1 + pixel_x
                    screen_y = y1 + pixel_y
                    print(f"    🎯 White pixel detected at ({screen_x}, {screen_y}) - sending Enter key")
                    self._send_key_press("enter")

                    # Reset no-pixel timer since we found something
                    no_pixel_timer = 0.0

                else:
                    # No white pixel found - increment timer
                    no_pixel_timer += (current_time - last_scan_time)

                    # Check exit condition during timeout
                    exit_result = self._check_shake_exit_condition(camera, use_mss)
                    if exit_result == "fish_stage":
                        if camera and not use_mss:
                            camera.release()
                        return "fish_stage"

                    if no_pixel_timer >= fail_cast_timeout:
                        # Fail cast timeout - return to Misc block
                        print(f"    ⚠️ No white pixels found for {fail_cast_timeout}s - returning to Misc block")
                        if camera and not use_mss:
                            camera.release()
                        return "restart"

                last_scan_time = current_time
                time.sleep(scan_delay)

            # Bot stopped - clean up camera
            try:
                if camera and not use_mss:
                    camera.release()
                    print("    DXCam camera released successfully")
                elif use_mss:
                    print("    MSS capture completed successfully")
            except Exception as cleanup_error:
                print(f"    Camera cleanup error: {cleanup_error}")
            return "continue"

        except Exception as e:
            print(f"    Error in Shake Navigation mode: {e}")
            import traceback
            traceback.print_exc()
            # Ensure camera is released even on error
            try:
                if camera and not use_mss:
                    camera.release()
            except:
                pass
            return "restart"

    def _hex_to_bgr(self, hex_color):
        """
        Convert hex color to BGR tuple for OpenCV.
        Returns None if color is invalid or disabled.
        """
        if hex_color is None or hex_color.lower() in ["none", "#none", ""]:
            return None
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (b, g, r)  # BGR format for OpenCV
        return None

    def _detect_fish_colors_in_frame(self, frame, target_line_color, left_bar_color, right_bar_color,
                                   arrow_color, target_line_tolerance, left_bar_tolerance,
                                   right_bar_tolerance, arrow_tolerance, skip_arrow_scan=False):
        """
        Detect fish colors in frame and return pixel positions.
        Returns dict with: target_line_x, bar_left_x, bar_right_x, arrow_left_x, arrow_right_x
        Optimized: Uses vectorized numpy operations + vertical line detection.

        Args:
            skip_arrow_scan: If True, skip arrow detection entirely (optimization when bars found)
        """

        result = {
            "target_line_x": None,  # Kept for backwards compatibility (will be middle)
            "target_left_x": None,
            "target_right_x": None,
            "target_middle_x": None,
            "bar_left_x": None,
            "bar_right_x": None,
            "arrow_center_x": None
        }

        height, width = frame.shape[:2]
        
        # Try vertical line detection first (more reliable for clear lines)
        use_line_detection = self.settings.get("use_vertical_line_detection", True)
        
        if use_line_detection:
            # Detect 3-4 vertical lines: target_left, target_right, bar_left, bar_right
            expected_lines = 4 if (left_bar_color is not None and right_bar_color is not None) else 3
            vertical_lines = find_vertical_lines_in_frame(frame, expected_count=expected_lines, min_sep=10)
            
            if len(vertical_lines) >= 2:
                # Assign detected lines to target and bar positions
                if len(vertical_lines) == 4:
                    # 4 lines: assign as left_target, right_target, left_bar, right_bar
                    result["target_left_x"] = vertical_lines[0]
                    result["target_right_x"] = vertical_lines[1]
                    result["target_middle_x"] = (vertical_lines[0] + vertical_lines[1]) // 2
                    result["target_line_x"] = result["target_middle_x"]
                    result["bar_left_x"] = vertical_lines[2]
                    result["bar_right_x"] = vertical_lines[3]
                    return result  # Perfect detection, return immediately
                    
                elif len(vertical_lines) == 3:
                    # 3 lines: left_target, right_target, and one bar edge
                    result["target_left_x"] = vertical_lines[0]
                    result["target_right_x"] = vertical_lines[1]
                    result["target_middle_x"] = (vertical_lines[0] + vertical_lines[1]) // 2
                    result["target_line_x"] = result["target_middle_x"]
                    # Third line could be left or right bar - use middle distance heuristic
                    bar_x = vertical_lines[2]
                    if bar_x < result["target_middle_x"]:
                        result["bar_left_x"] = bar_x
                    else:
                        result["bar_right_x"] = bar_x
                    return result
                    
                elif len(vertical_lines) == 2:
                    # 2 lines: assume target boundaries
                    result["target_left_x"] = vertical_lines[0]
                    result["target_right_x"] = vertical_lines[1]
                    result["target_middle_x"] = (vertical_lines[0] + vertical_lines[1]) // 2
                    result["target_line_x"] = result["target_middle_x"]
                    # Fall through to color detection for bars

        # Fallback to color-based detection (original method)
        # Helper function to create mask for a color (returns x_coords or None)
        def find_color_x_coords(bgr_color, tolerance):
            if bgr_color is None:
                return None

            # Create mask for color with tolerance
            lower_bound = np.array([max(0, bgr_color[0] - tolerance),
                                  max(0, bgr_color[1] - tolerance),
                                  max(0, bgr_color[2] - tolerance)])
            upper_bound = np.array([min(255, bgr_color[0] + tolerance),
                                  min(255, bgr_color[1] + tolerance),
                                  min(255, bgr_color[2] + tolerance)])

            mask = cv2.inRange(frame, lower_bound, upper_bound)
            y_coords, x_coords = np.where(mask > 0)

            # Return x_coords array directly (vectorized)
            if len(x_coords) > 0:
                return x_coords
            return None

        # Find target line pixels if not already found by line detection
        if result["target_line_x"] is None:
            target_x_coords = find_color_x_coords(target_line_color, target_line_tolerance)
            if target_x_coords is not None:
                result["target_left_x"] = int(np.min(target_x_coords))
                result["target_right_x"] = int(np.max(target_x_coords))
                result["target_middle_x"] = int((result["target_left_x"] + result["target_right_x"]) / 2)
                result["target_line_x"] = result["target_middle_x"]

        # Find bar pixels if not already found by line detection
        if result["bar_left_x"] is None and result["bar_right_x"] is None:
            bar_x_coords = None

            if left_bar_color is not None:
                left_x_coords = find_color_x_coords(left_bar_color, left_bar_tolerance)
                if left_x_coords is not None:
                    bar_x_coords = left_x_coords

            if right_bar_color is not None:
                right_x_coords = find_color_x_coords(right_bar_color, right_bar_tolerance)
                if right_x_coords is not None:
                    if bar_x_coords is not None:
                        # Concatenate both bar color arrays
                        bar_x_coords = np.concatenate([bar_x_coords, right_x_coords])
                    else:
                        bar_x_coords = right_x_coords

            # If ANY bar pixels found, assign leftmost and rightmost
            if bar_x_coords is not None:
                result["bar_left_x"] = int(np.min(bar_x_coords))
                result["bar_right_x"] = int(np.max(bar_x_coords))

        # Find single arrow point if enabled (fallback only)
        # Skip arrow scan if bars were found (optimization)
        if not skip_arrow_scan and arrow_color is not None:
            arrow_x_coords = find_color_x_coords(arrow_color, arrow_tolerance)
            if arrow_x_coords is not None:
                # Just find the center/average position of arrow pixels (vectorized mean)
                result["arrow_center_x"] = float(np.mean(arrow_x_coords))

        return result

    def _find_white_pixel(self, frame, tolerance):
        """
        Find first white pixel (255,255,255) in frame with color tolerance.
        Returns (x, y) tuple of first match, or None if not found.
        """
        # Define white color range with tolerance
        lower_white = np.array([255 - tolerance, 255 - tolerance, 255 - tolerance])
        upper_white = np.array([255, 255, 255])

        # Create mask for white pixels
        mask = np.all((frame >= lower_white) & (frame <= upper_white), axis=-1)

        # Find first white pixel
        white_pixels = np.argwhere(mask)
        if len(white_pixels) > 0:
            y, x = white_pixels[0]  # numpy returns (row, col) = (y, x)
            return (int(x), int(y))

        return None

    def _detect_circle_in_frame(self, frame):
        """
        Detect circles in frame using strict Hough Circle Transform for perfect circles only.
        Specifically optimized for SHAKE button detection with strict filtering.
        Returns (center_x, center_y) of the best circle found, or None if no circles.

        Args:
            frame: BGR image from dxcam/mss
        """
        try:
            # Convert BGR to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Scale circle detection parameters based on resolution
            # Reference values are for 2560x1440 resolution
            # Use average of scale_x and scale_y for uniform circle scaling
            scale_factor = (self.scale_x + self.scale_y) / 2

            # Scale parameters proportionally to resolution
            scaled_min_dist = int(150 * scale_factor)
            scaled_min_radius = int(50 * scale_factor)
            scaled_max_radius = int(300 * scale_factor)
            scaled_good_min_radius = int(50 * scale_factor)
            scaled_good_max_radius = int(120 * scale_factor)

            # Hough Circle Transform with strict parameters for perfect circles only
            circles = cv2.HoughCircles(
                gray,
                cv2.HOUGH_GRADIENT,
                dp=1,           # Inverse ratio of accumulator resolution
                minDist=scaled_min_dist,    # Increased distance between circles to avoid overlapping detections
                param1=100,     # Higher Canny threshold for edge detection
                param2=100,     # Much higher accumulator threshold - only perfect circles
                minRadius=scaled_min_radius,   # Larger minimum radius to ignore small false positives
                maxRadius=scaled_max_radius   # Maximum circle radius
            )

            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")

                # Additional filtering: Only accept circles with good radius range for SHAKE buttons
                good_circles = []
                for (x, y, r) in circles:
                    # SHAKE buttons are typically 50-120 pixels radius (scaled)
                    if scaled_good_min_radius <= r <= scaled_good_max_radius:
                        good_circles.append((x, y, r))

                if good_circles:
                    # Return the largest good circle (most likely to be SHAKE button)
                    largest_circle = max(good_circles, key=lambda c: c[2])
                    x, y, r = largest_circle
                    print(f"    ⚡ Circle detected at local ({x}, {y}) with radius {r} (scale: {scale_factor:.3f})")
                    return (int(x), int(y))

            # Only use strict HoughCircles detection - no backup methods to avoid false positives
            return None

        except Exception as e:
            print(f"    Error in circle detection: {e}")
            return None

    def _detect_lines_in_frame(self, frame, original_width=None, filter_noise=False):
        """
        Detect vertical lines in frame using Canny + Sobel edge detection.
        Returns list of x-coordinates of detected vertical lines.
        """
        try:
            original_height, original_frame_width = frame.shape[:2]
            if original_width is None:
                original_width = original_frame_width
            
            height, width = frame.shape[:2]
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Detect edges
            edges = cv2.Canny(gray, 50, 150)
            sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
            sobelx_abs = np.abs(sobelx)
            
            # Find full-height vertical lines
            vertical_lines = []
            line_strengths = []
            
            for col in range(width):
                column_edges = edges[:, col]
                edge_coverage = np.sum(column_edges > 0) / height
                
                column_gradient = sobelx_abs[:, col]
                strong_gradient_count = np.sum(column_gradient > 40)
                gradient_coverage = strong_gradient_count / height
                
                if edge_coverage >= 0.50 or gradient_coverage >= 0.50:
                    vertical_lines.append(col)
                    line_strengths.append((col, edge_coverage, gradient_coverage))
            
            if len(vertical_lines) == 0:
                return []
            
            # Merge adjacent pixels
            cluster_tolerance = max(2, int(width / 512))
            distinct_lines = []
            distinct_strengths = []
            current_cluster_start = 0
            current_cluster_end = 0
            
            for i in range(1, len(vertical_lines)):
                if vertical_lines[i] - vertical_lines[current_cluster_end] <= cluster_tolerance:
                    current_cluster_end = i
                else:
                    cluster = line_strengths[current_cluster_start:current_cluster_end+1]
                    best = max(cluster, key=lambda x: (x[1], x[2]))
                    distinct_lines.append(best[0])
                    distinct_strengths.append((best[1], best[2]))
                    current_cluster_start = i
                    current_cluster_end = i
            
            cluster = line_strengths[current_cluster_start:current_cluster_end+1]
            best = max(cluster, key=lambda x: (x[1], x[2]))
            distinct_lines.append(best[0])
            distinct_strengths.append((best[1], best[2]))
            
            # Filter weak lines in 4-line cases
            if len(distinct_lines) == 4:
                combined_strengths = [(i, canny + sobel) for i, (canny, sobel) in enumerate(distinct_strengths)]
                combined_strengths.sort(key=lambda x: x[1])
                weakest_idx = combined_strengths[0][0]
                weakest_strength = combined_strengths[0][1]
                median_strength = combined_strengths[2][1]
                
                if weakest_strength < 0.5 * median_strength:
                    distinct_lines.pop(weakest_idx)
            
            # Smart filtering for 5 lines
            if len(distinct_lines) == 5:
                combined_strengths = [(i, canny + sobel) for i, (canny, sobel) in enumerate(distinct_strengths)]
                combined_strengths.sort(key=lambda x: x[1])
                weakest_idx = combined_strengths[0][0]
                second_weakest_idx = combined_strengths[1][0]
                weakest_strength = combined_strengths[0][1]
                second_weakest_strength = combined_strengths[1][1]
                
                # If weakest is <60% of second-weakest, remove it
                if weakest_strength < 0.6 * second_weakest_strength:
                    distinct_lines.pop(weakest_idx)
                    distinct_strengths.pop(weakest_idx)
                # Check if two weakest lines are close together (same bar split)
                elif abs(distinct_lines[weakest_idx] - distinct_lines[second_weakest_idx]) < 30:
                    distinct_lines.pop(weakest_idx)
                    distinct_strengths.pop(weakest_idx)
                else:
                    # Check if all 5 lines are relatively weak (likely noise)
                    avg_strength = sum(s for _, s in combined_strengths) / 5
                    if avg_strength < 1.2:  # Average strength threshold
                        if filter_noise:
                            return []
                    
                    # All 5 lines are strong - check for suspicious patterns
                    # Pattern: 3 lines close together within 100px - remove middle one
                    for i in range(3):  # Check positions 0-1-2, 1-2-3, 2-3-4
                        if i + 2 < 5:
                            dist1 = distinct_lines[i+1] - distinct_lines[i]
                            dist2 = distinct_lines[i+2] - distinct_lines[i+1]
                            # If three consecutive lines are all within 100px spacing
                            if dist1 < 100 and dist2 < 100:
                                # Remove the middle one (i+1)
                                distinct_lines.pop(i+1)
                                distinct_strengths.pop(i+1)
                                return distinct_lines
                    
                    # Fallback: Check if second-weakest is <90% of median
                    median_strength = combined_strengths[2][1]
                    if second_weakest_strength < 0.9 * median_strength:
                        distinct_lines.pop(second_weakest_idx)
                        distinct_strengths.pop(second_weakest_idx)
                    else:
                        if filter_noise:
                            return []
            
            # Filter noise: >5 lines
            if len(distinct_lines) > 5:
                if filter_noise:
                    return []
            
            return distinct_lines

        except Exception as e:
            print(f"    Error in line detection: {e}")
            return []

    def _check_shake_exit_condition(self, camera=None, use_mss=False):
        """
        Centralized exit condition checker for shake modes.
        Checks bottom left corner for specific color #9bff9b to exit shake stage.

        Returns:
            "fish_stage" - Exit condition met, proceed to fish stage (color is GONE)
            None - Exit condition not met, continue shake loop (color is present)
        """
        try:
            # Get screen dimensions using MSS
            with mss.mss() as sct:
                # Get primary monitor info
                monitor = sct.monitors[1]  # Index 1 is primary monitor
                screen_width = monitor["width"]
                screen_height = monitor["height"]
                
                # Scale bottom left corner area (based on 2560x1440 reference)
                # Reference: x:0-500, y:1200-1440 at 2560x1440
                x1 = 0
                y1 = int(screen_height * (1200 / 1440))
                x2 = int(screen_width * (500 / 2560))
                y2 = screen_height
                
                # Capture bottom left corner
                capture_region = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
                screenshot = sct.grab(capture_region)
                frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
            
            if frame is None:
                return None
            
            # Target color #9bff9b (RGB: 155, 255, 155)
            target_color_bgr = np.array([155, 255, 155])  # BGR format
            tolerance = 15  # Reasonable tolerance for color matching
            
            # Create color mask
            lower_bound = np.clip(target_color_bgr - tolerance, 0, 255)
            upper_bound = np.clip(target_color_bgr + tolerance, 0, 255)
            mask = cv2.inRange(frame, lower_bound, upper_bound)
            
            # Count matching pixels
            matching_pixels = cv2.countNonZero(mask)
            
            # Exit when color is NOT present (0 pixels) - we're in fish stage
            if matching_pixels == 0:
                print(f"    🐟 Bottom left color GONE! (0 pixels) Proceeding to fish stage...")
                self._update_status("Shake: Fish Found", "green")
                return "fish_stage"
            
            # Color is present - stay in shake mode
            return None
            
        except Exception as e:
            print(f"    Error checking shake exit condition: {e}")
            return None
    
    def _check_fish_exit_condition(self):
        """
        Check if fish stage should exit by detecting green color in bottom left.
        Used during fish stage to detect when minigame has ended.

        Returns:
            "fish_stage" - Green color found, fish stage ended
            None - Green color not found, continue fishing
        """
        try:
            # Get screen dimensions using MSS
            with mss.mss() as sct:
                # Get primary monitor info
                monitor = sct.monitors[1]  # Index 1 is primary monitor
                screen_width = monitor["width"]
                screen_height = monitor["height"]
                
                # Scale bottom left corner area (based on 2560x1440 reference)
                x1 = 0
                y1 = int(screen_height * (1200 / 1440))
                x2 = int(screen_width * (500 / 2560))
                y2 = screen_height
                
                # Capture bottom left corner
                capture_region = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
                screenshot = sct.grab(capture_region)
                frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
            
            if frame is None:
                return None
            
            # Target color #9bff9b (RGB: 155, 255, 155)
            target_color_bgr = np.array([155, 255, 155])  # BGR format
            tolerance = 15
            
            # Create color mask
            lower_bound = np.clip(target_color_bgr - tolerance, 0, 255)
            upper_bound = np.clip(target_color_bgr + tolerance, 0, 255)
            mask = cv2.inRange(frame, lower_bound, upper_bound)
            
            # Count matching pixels
            matching_pixels = cv2.countNonZero(mask)
            
            # Exit fish stage when color IS present (reappeared)
            if matching_pixels > 0:
                return "fish_stage"
            
            # Color still gone - continue fishing
            return None
            
        except Exception as e:
            print(f"    Error checking fish exit condition: {e}")
            return None

    def _should_check_fish_colors(self):
        """Check if fish detection should be active during shake timeout."""
        # Check if Fish Settings is on Color or Line style
        fish_track_style = self.settings.get("fish_track_style", "Color")
        return fish_track_style in ["Color", "Line"]

    def _check_fish_colors_in_area(self, camera=None, use_mss=False):
        """
        Check for fish colors (target line + either left or right bar) in the fish area.
        Returns True if both target line and at least one bar color are detected.
        Uses MSS for fish area capture to avoid DXCam instance conflicts.
        """
        try:
            
            # Get fish area coordinates
            fish_area = self.fish_box
            if not fish_area:
                print("    No fish area set, cannot check fish colors")
                return False
            
            x1, y1, x2, y2 = fish_area["x1"], fish_area["y1"], fish_area["x2"], fish_area["y2"]
            
            # Use MSS for fish area capture (avoids DXCam conflicts)
            with mss.mss() as sct:
                # MSS monitor format: {"top": y1, "left": x1, "width": w, "height": h}
                monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
                screenshot = sct.grab(monitor)
                
                # Convert to BGR format for OpenCV
                fish_frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
            if fish_frame is None:
                return False
            
            # Get current rod type and fish colors
            current_rod = self.settings.get("fish_rod_type", "Default")
            
            # Get colors for current rod type
            target_line_color = self._get_fish_color_for_rod("fish_target_line_color", current_rod)
            left_bar_color = self._get_fish_color_for_rod("fish_left_bar_color", current_rod)
            right_bar_color = self._get_fish_color_for_rod("fish_right_bar_color", current_rod)
            arrow_color = self._get_fish_color_for_rod("fish_arrow_color", current_rod)
            
            # Get tolerances for current rod type
            target_line_tolerance = self._get_fish_tolerance_for_rod("fish_target_line_tolerance", current_rod)
            left_bar_tolerance = self._get_fish_tolerance_for_rod("fish_left_bar_tolerance", current_rod)
            right_bar_tolerance = self._get_fish_tolerance_for_rod("fish_right_bar_tolerance", current_rod)
            arrow_tolerance = self._get_fish_tolerance_for_rod("fish_arrow_tolerance", current_rod)
            
            # Skip if target line is disabled
            if target_line_color == "None":
                return False
            
            # Check for target line color
            target_line_detected = self._detect_color_in_frame(fish_frame, target_line_color, target_line_tolerance)
            
            if not target_line_detected:
                return False
            
            # Check for either left or right bar color (if they're not disabled)
            left_bar_detected = False
            right_bar_detected = False
            
            if left_bar_color != "None":
                left_bar_detected = self._detect_color_in_frame(fish_frame, left_bar_color, left_bar_tolerance)
            
            if right_bar_color != "None":
                right_bar_detected = self._detect_color_in_frame(fish_frame, right_bar_color, right_bar_tolerance)
            
            # Check if at least one bar is detected
            bar_detected = left_bar_detected or right_bar_detected
            
            # If target line detected + bar detected, success!
            if target_line_detected and bar_detected:
                colors_found = []
                if target_line_detected:
                    colors_found.append("target_line")
                if left_bar_detected:
                    colors_found.append("left_bar")
                if right_bar_detected:
                    colors_found.append("right_bar")
                
                print(f"    🐟 Fish colors detected: {', '.join(colors_found)} (rod: {current_rod})")
                return True
            
            # FALLBACK: If bar not found, check for arrow (target line + arrow)
            if target_line_detected and not bar_detected:
                arrow_detected = False
                if arrow_color and arrow_color.lower() not in ["none", "#none", ""]:
                    arrow_detected = self._detect_color_in_frame(fish_frame, arrow_color, arrow_tolerance)
                    
                    if arrow_detected:
                        print(f"    🐟 Fish colors detected (arrow fallback): target_line + arrow (rod: {current_rod})")
                        return True
            
            return False
            
        except Exception as e:
            print(f"    Error checking fish colors: {e}")
            return False

    def _check_lines_in_area(self, camera=None, use_mss=False):
        """
        Check for vertical lines in the fish area (Line mode exit condition).
        Returns True if minimum number of lines are detected (configurable).
        Uses MSS for fish area capture to avoid DXCam instance conflicts.
        """
        try:
            # Get minimum line count from settings (configurable via GUI)
            min_line_count = self._get_rod_specific_setting("fish_line_min_count", 4)

            # Get fish area coordinates
            fish_area = self.fish_box
            if not fish_area:
                print("    No fish area set, cannot check lines")
                return False

            x1, y1, x2, y2 = fish_area["x1"], fish_area["y1"], fish_area["x2"], fish_area["y2"]

            # Use MSS for fish area capture
            with mss.mss() as sct:
                monitor = {"top": y1, "left": x1, "width": x2 - x1, "height": y2 - y1}
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            # Detect lines in frame (with noise filtering for exit condition)
            line_coordinates = self._detect_lines_in_frame(frame, filter_noise=True)

            # Check if minimum lines detected
            if len(line_coordinates) >= min_line_count:
                print(f"    📏 Line detection: Found {len(line_coordinates)} lines (min: {min_line_count})")
                return True

            return False

        except Exception as e:
            print(f"    Error checking lines: {e}")
            return False

    def _get_fish_color_for_rod(self, base_key, rod_name):
        """Get fish color setting for specific rod type."""
        if rod_name == "Default":
            return self.settings.get(base_key, "#FFFFFF")
        else:
            rod_specific_key = f"{base_key}_{rod_name}"
            return self.settings.get(rod_specific_key, "#FFFFFF")
    
    def _get_fish_tolerance_for_rod(self, base_key, rod_name):
        """Get fish tolerance setting for specific rod type."""
        if rod_name == "Default":
            return self.settings.get(base_key, 0)
        else:
            rod_specific_key = f"{base_key}_{rod_name}"
            return self.settings.get(rod_specific_key, 0)
    
    def _get_rod_specific_setting(self, base_key, default_value=None):
        """Get setting value for current rod type."""
        current_rod = self.settings.get("fish_rod_type", "Default")
        
        if current_rod == "Default":
            # Default rod uses original keys
            return self.settings.get(base_key, default_value)
        else:
            # Other rods use rod-specific keys
            rod_specific_key = f"{base_key}_{current_rod}"
            return self.settings.get(rod_specific_key, default_value)
    
    def _detect_color_in_frame(self, frame, hex_color, tolerance):
        """
        Detect if a specific color exists in the frame within tolerance.
        Returns True if color is found, False otherwise.
        """
        try:
            
            if frame is None or frame.size == 0 or hex_color == "None":
                return False
            
            # Convert hex color to BGR
            hex_color = hex_color.lstrip('#')
            if len(hex_color) != 6:
                return False
            
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16) 
            b = int(hex_color[4:6], 16)
            target_bgr = np.array([b, g, r])  # OpenCV uses BGR
            
            # Create color range with tolerance
            lower_bound = np.clip(target_bgr - tolerance, 0, 255)
            upper_bound = np.clip(target_bgr + tolerance, 0, 255)
            
            # Create mask for the color
            mask = cv2.inRange(frame, lower_bound, upper_bound)
            
            # Check if any pixels match
            return np.any(mask > 0)
            
        except Exception as e:
            print(f"    Error detecting color {hex_color}: {e}")
            return False

    def _cleanup_cast_overlays(self):
        """Clean up cast visualization overlays (green and white boxes, info text)."""
        try:
            if hasattr(self, '_cast_overlay') and self._cast_overlay is not None:
                try:
                    self._cast_overlay.destroy()
                    self._cast_overlay = None
                except:
                    pass
            
            if hasattr(self, '_white_overlay') and self._white_overlay is not None:
                try:
                    self._white_overlay.destroy()
                    self._white_overlay = None
                except:
                    pass
            
            if hasattr(self, '_info_overlay') and self._info_overlay is not None:
                try:
                    self._info_overlay.destroy()
                    self._info_overlay = None
                except:
                    pass
        except:
            pass

    def _preinitialize_cast_overlays(self):
        """Pre-create overlay windows to avoid lag on first display during release."""
        try:
            # Pre-create green box overlay (hidden)
            if not hasattr(self, '_cast_overlay') or self._cast_overlay is None:
                self._cast_overlay, self._cast_canvas = self._create_transparent_overlay("Green Detection", hide_initially=True)
            
            # Pre-create white box overlay (hidden)
            if not hasattr(self, '_white_overlay') or self._white_overlay is None:
                self._white_overlay, self._white_canvas = self._create_transparent_overlay("White Detection", hide_initially=True)
            
            # Pre-create info box overlay (hidden)
            if not hasattr(self, '_info_overlay') or self._info_overlay is None:
                self._info_overlay = tk.Toplevel(self)
                self._info_overlay.title("Release Info")
                self._info_overlay.attributes('-topmost', True)
                self._info_overlay.overrideredirect(True)
                self._info_overlay.attributes('-alpha', 0.90)
                self._info_label = tk.Label(
                    self._info_overlay,
                    text="",
                    font=("Consolas", 11, "bold"),
                    fg="#00FF00",
                    bg="#1a1a1a",
                    justify="left",
                    padx=12,
                    pady=10
                )
                self._info_label.pack()
                self._info_overlay.withdraw()  # Keep hidden until needed
            
            # Force all overlays to initialize
            self._cast_overlay.update_idletasks()
            self._white_overlay.update_idletasks()
            self._info_overlay.update_idletasks()
            
        except Exception as e:
            print(f"    ❌ Error pre-initializing overlays: {e}")

    def _update_status(self, new_status, color="white", details=""):
        """
        Thread-safe status update method.
        
        Args:
            new_status: Status text to display
            color: Color for the status ("white", "green", "yellow", "red")
            details: Additional details/help text to show user
        """
        # Check if we're on the main thread
        if threading.current_thread() == threading.main_thread():
            # Direct update on main thread
            self._update_status_direct(new_status, color, details)
        else:
            # Queue update for main thread
            self._queue_gui_update(self._update_status_direct, new_status, color, details)
    
    def _update_status_direct(self, new_status, color="white", details=""):
        """Direct status update (main thread only)"""
        # Store previous status
        self.previous_status = self.current_status
        self.current_status = new_status
        self.status_details = details
        self.status_color = color  # Track the color
        
        # Update overlay if it should be shown
        if self.global_gui_settings.get("Show Status Overlay", True):
            self._show_status_overlay(color)
    
    def _show_status_overlay(self, current_color="white"):
        """Create or update the status overlay at top-left of screen."""
        try:
            # Create overlay window if it doesn't exist
            if not hasattr(self, 'status_overlay') or self.status_overlay is None:
                self.status_overlay = tk.Toplevel(self)
                self.status_overlay.title("Bot Status")
                self.status_overlay.attributes('-topmost', True)
                self.status_overlay.overrideredirect(True)
                # Make it fully opaque (no transparency)
                self.status_overlay.attributes('-alpha', 1.0)
                
                # Create label for status text
                self.status_label = tk.Label(
                    self.status_overlay,
                    text="",
                    font=("Consolas", 9, "bold"),
                    fg="#FFFFFF",
                    bg="#000000",  # Pure black background
                    justify="left",
                    padx=20,
                    pady=15,
                    anchor="nw"
                )
                self.status_label.pack(fill="both", expand=True)
                
                # Position at top-left corner
                self.status_overlay.geometry("+10+10")
            
            # Color mapping
            color_map = {
                "white": "#FFFFFF",
                "green": "#00FF00",
                "yellow": "#FFFF00",
                "red": "#FF0000"
            }
            current_fg = color_map.get(current_color, "#FFFFFF")
            
            # Build comprehensive status text with help information
            status_lines = [
                "=" * 50,
                "🎣 IRUS COMET BOT - STATUS MONITOR",
                "=" * 50,
                "",
                f"📍 CURRENT: {self.current_status}",
                f"📝 PREVIOUS: {self.previous_status}",
            ]
            
            # Add details if provided
            if hasattr(self, 'status_details') and self.status_details:
                status_lines.append("")
                status_lines.append("⚡ DETAILS:")
                status_lines.append(self.status_details)
            
            # Add helpful troubleshooting info based on status
            status_lines.append("")
            status_lines.append("=" * 50)
            
            if "TIMEOUT" in self.current_status:
                status_lines.extend([
                    "⚠️ ISSUE: Timeout reached",
                    "",
                    "⚡ POSSIBLE SOLUTIONS:",
                    "  • Check if bobber is visible in game",
                    "  • Verify Cast Area box is correct",
                    "  • Adjust color tolerances in settings",
                    "  • Increase timeout duration",
                    "  • Check if game window is active/visible"
                ])
            elif "SUCCESS" in self.current_status or "Complete" in self.current_status:
                status_lines.extend([
                    "✅ STATUS: Operation successful",
                    "",
                    "⚡ Bot will continue to next stage..."
                ])
            elif "Fish Found" in self.current_status:
                status_lines.extend([
                    "🐟 STATUS: Fish detected!",
                    "",
                    "⚡ Entering fish catching mode..."
                ])
            elif "Fish Stage" in self.current_status:
                if "Timeout" in self.current_status:
                    status_lines.extend([
                        "⚡ ISSUE: Fish stage timeout",
                        "",
                        "⚡ POSSIBLE SOLUTIONS:",
                        "  • Check Fish Area box positioning",
                        "  • Verify target/bar colors are correct",
                        "  • Adjust color tolerances",
                        "  • Increase Fish Lost Timeout",
                        "  • Check if lines are visible (Line mode)"
                    ])
                else:
                    status_lines.extend([
                        "⚡ STATUS: Actively catching fish",
                        "",
                        "⚡ Mode: " + ("Color" if "Color" in self.current_status else "Line")
                    ])
            elif "Shake Block" in self.current_status:
                status_lines.extend([
                    "⚡ STATUS: Scanning for shake circles",
                    "",
                    "⚡ Waiting for white circles to appear...",
                    "  • Check Shake Area box is correct",
                    "  • Verify shake circles are visible"
                ])
            elif "Cast Block" in self.current_status:
                status_lines.extend([
                    "⚡ STATUS: Performing cast action",
                    "",
                    "⚡ Waiting for perfect cast indicator..."
                ])
            elif "Misc Block" in self.current_status:
                status_lines.extend([
                    "⚡ STATUS: Executing miscellaneous actions",
                    "",
                    "⚡ Preparing for next fishing cycle..."
                ])
            else:
                status_lines.extend([
                    "⚡ Bot is running...",
                    "",
                    "Press F3 to stop bot"
                ])
            
            status_lines.append("=" * 50)
            
            status_text = "\n".join(status_lines)
            
            # Update label - only color the CURRENT status line
            self.status_label.config(text=status_text, fg=current_fg)
            
            # Show overlay
            self.status_overlay.deiconify()
            self.status_overlay.update_idletasks()
            
        except Exception as e:
            print(f"    ❌ Error showing status overlay: {e}")
    
    def _hide_status_overlay(self):
        """Hide the status overlay."""
        try:
            if hasattr(self, 'status_overlay') and self.status_overlay is not None:
                self.status_overlay.withdraw()
        except:
            pass
    
    def _cleanup_status_overlay(self):
        """Destroy the status overlay."""
        try:
            if hasattr(self, 'status_overlay') and self.status_overlay is not None:
                self.status_overlay.destroy()
                self.status_overlay = None
                self.status_label = None
        except:
            pass

    def _show_release_info(self, prediction_info):
        """Show final release information overlay after perfect cast release."""
        try:
            if not self.global_gui_settings.get("Show Perfect Cast Overlay", True):
                print("    💬 Info overlay disabled by settings")
                return
            
            if prediction_info is None:
                print("    💬 No prediction info to display")
                return
            
            print("    🖼️ Creating/updating release info overlay...")
            
            # Create overlay window for INFO box if it doesn't exist
            if not hasattr(self, '_info_overlay') or self._info_overlay is None:
                self._info_overlay = tk.Toplevel(self)
                self._info_overlay.title("Release Info")
                self._info_overlay.attributes('-topmost', True)
                self._info_overlay.overrideredirect(True)
                
                # Semi-transparent dark background
                self._info_overlay.attributes('-alpha', 0.90)
                
                # Create label for text
                self._info_label = tk.Label(
                    self._info_overlay,
                    text="",
                    font=("Consolas", 11, "bold"),
                    fg="#00FF00",  # Bright green text
                    bg="#1a1a1a",  # Dark background
                    justify="left",
                    padx=12,
                    pady=10
                )
                self._info_label.pack()
            
            # Build info text - check actual release style from settings
            release_style = self.settings.get("perfect_cast_release_style", "Velocity-Percentage")
            
            if release_style == "GigaSigmaUltraMode":
                display_mode = "GIGASIGMA ULTRA"
            elif release_style == "Prediction":
                display_mode = "PREDICTION"
            else:
                display_mode = "VELOCITY-PERCENTAGE"
            
            info_lines = [f"⚡ {display_mode} RELEASE"]
            
            if 'distance' in prediction_info:
                info_lines.append(f"   Distance: {prediction_info['distance']:.0f}px")
            
            if 'velocity' in prediction_info:
                info_lines.append(f"   Velocity: {prediction_info['velocity']:.1f}px/s")
            
            if 'time_to_impact' in prediction_info:
                info_lines.append(f"   Time to impact: {prediction_info['time_to_impact']:.1f}ms")
            
            if 'release_timing' in prediction_info:
                info_lines.append(f"   Release timing: {prediction_info['release_timing']:.1f}ms")
            
            if 'threshold' in prediction_info:
                info_lines.append(f"   Threshold: {prediction_info['threshold']:.1f}px")
            
            info_text = "\n".join(info_lines)
            self._info_label.config(text=info_text)
            
            # Update label to get actual size
            self._info_overlay.update_idletasks()
            info_height = self._info_label.winfo_reqheight()
            info_width = self._info_label.winfo_reqwidth()
            
            # Position beside the red boxes (to the right of them)
            # Try to position relative to the green/white boxes
            positioned = False
            if hasattr(self, '_cast_overlay') and self._cast_overlay is not None:
                try:
                    # Get green box position
                    green_geometry = self._cast_overlay.geometry()
                    print(f"    📦 Green box geometry: {green_geometry}")
                    parts = green_geometry.split('+')
                    if len(parts) >= 3:
                        green_x = int(parts[1])
                        green_y = int(parts[2])
                        
                        # Get white box position if available for vertical centering
                        white_y = green_y
                        if hasattr(self, '_white_overlay') and self._white_overlay is not None:
                            try:
                                white_geometry = self._white_overlay.geometry()
                                print(f"    📦 White box geometry: {white_geometry}")
                                white_parts = white_geometry.split('+')
                                if len(white_parts) >= 3:
                                    white_y = int(white_parts[2])
                            except:
                                pass
                        
                        # Calculate vertical midpoint between green and white boxes
                        vertical_midpoint = (green_y + white_y) // 2
                        
                        # Position to the right of the boxes
                        # Get box width from geometry (format: WIDTHxHEIGHT+X+Y)
                        size_part = parts[0]
                        box_width = int(size_part.split('x')[0])
                        
                        info_x = green_x + box_width + 15  # 15px spacing from box edge
                        info_y = vertical_midpoint - (info_height // 2)
                        
                        self._info_overlay.geometry(f"+{info_x}+{info_y}")
                        print(f"    📌 Info box positioned at: {info_x}, {info_y}")
                        positioned = True
                except Exception as e:
                    print(f"    ❌ Error positioning info box beside boxes: {e}")
            
            # Fallback: position relative to shake area if boxes don't exist
            if not positioned and self.shake_box:
                try:
                    shake_right = self.shake_box["x2"]
                    shake_center_y = (self.shake_box["y1"] + self.shake_box["y2"]) // 2
                    info_x = shake_right + 30
                    info_y = shake_center_y - (info_height // 2)
                    self._info_overlay.geometry(f"+{info_x}+{info_y}")
                    print(f"    ⚡ Info box positioned at shake area: {info_x}, {info_y}")
                    positioned = True
                except Exception as e:
                    print(f"    ❌ Error positioning info box at shake area: {e}")
            
            if positioned:
                self._info_overlay.deiconify()
                self._info_overlay.update_idletasks()
                self._info_overlay.update()  # Force immediate render
                print("    ✅ Info overlay displayed")
            else:
                print("    ⚠️ Could not position info overlay - no reference boxes found")
        except Exception as e:
            print(f"Error showing release info: {e}")
            pass

    def _move_cast_overlays_to_side(self):
        """Move cast visualization overlays to the right side of shake area."""
        try:
            if not self.shake_box:
                print("    ⚠️ Cannot move overlays - shake_box not defined")
                return
            
            print("    ↗️ Moving cast overlays to right side of shake area...")
            
            # Calculate right side position (outside shake area on the right)
            shake_right = self.shake_box["x2"]
            move_offset = 20  # 20px spacing from shake area edge
            new_x = shake_right + move_offset
            
            print(f"    🎯 Target X position: {new_x} (shake_right: {shake_right} + offset: {move_offset})")
            
            # Move green box
            if hasattr(self, '_cast_overlay') and self._cast_overlay is not None:
                try:
                    # Get current geometry
                    geometry = self._cast_overlay.geometry()
                    print(f"    📦 Green box current geometry: {geometry}")
                    # Parse: "WIDTHxHEIGHT+X+Y"
                    parts = geometry.split('+')
                    if len(parts) >= 3:
                        size_part = parts[0]  # WIDTHxHEIGHT
                        current_y = int(parts[2])
                        # Update position
                        new_geometry = f"{size_part}+{new_x}+{current_y}"
                        self._cast_overlay.geometry(new_geometry)
                        # Ensure it's visible
                        self._cast_overlay.deiconify()
                        print(f"    ✅ Green box moved to: {new_geometry}")
                except Exception as e:
                    print(f"    ❌ Error moving green box: {e}")
            else:
                print("    ⚠️ Green box overlay doesn't exist")
            
            # Move white box
            if hasattr(self, '_white_overlay') and self._white_overlay is not None:
                try:
                    geometry = self._white_overlay.geometry()
                    print(f"    📍 White box current geometry: {geometry}")
                    parts = geometry.split('+')
                    if len(parts) >= 3:
                        size_part = parts[0]
                        current_y = int(parts[2])
                        new_geometry = f"{size_part}+{new_x}+{current_y}"
                        self._white_overlay.geometry(new_geometry)
                        # Ensure it's visible
                        self._white_overlay.deiconify()
                        print(f"    ✅ White box moved to: {new_geometry}")
                except Exception as e:
                    print(f"    ❌ Error moving white box: {e}")
            else:
                print("    ⚠️ White box overlay doesn't exist")
            
            # Move info box
            if hasattr(self, '_info_overlay') and self._info_overlay is not None:
                try:
                    geometry = self._info_overlay.geometry()
                    print(f"    📦 Info box current geometry: {geometry}")
                    parts = geometry.split('+')
                    if len(parts) >= 2:
                        size_part = parts[0]
                        current_y = int(parts[2]) if len(parts) >= 3 else 0
                        # Info box goes even further right
                        info_x = new_x + 100  # Additional offset for info box
                        new_geometry = f"{size_part}+{info_x}+{current_y}"
                        self._info_overlay.geometry(new_geometry)
                        # Ensure it's visible
                        self._info_overlay.deiconify()
                        print(f"    ✅ Info box moved to: {new_geometry}")
                except Exception as e:
                    print(f"    ❌ Error moving info box: {e}")
            else:
                print("    ⚠️ Info box overlay doesn't exist")
        except Exception as e:
            print(f"    ❌ Error in _move_cast_overlays_to_side: {e}")

    def _show_cast_visualization(self, shake_area, green_x_local, green_y_local, white_y_local, frame_height, green_width, prediction_info=None):
        """
        Display red outline boxes around detected green bobber and white pixel detection area.
        Green box: top, left, right sides (no bottom) - U-shape
        White box: bottom, left, right sides (no top) - inverted U-shape
        Prediction info box: shows velocity, distance, timing info to the right of the boxes
        
        Args:
            prediction_info: dict with keys 'distance', 'velocity', 'time_to_impact', 'release_timing' (all optional)
        """
        try:
            # Estimate green height (bobbers are roughly square)
            green_height = green_width
            
            # Calculate box dimensions with extra padding to ensure NO overlap with green
            # Use 20% padding on each side (minimum 6px) to guarantee clearance at all resolutions
            padding = max(int(green_width * 0.2), 6)
            current_width = green_width + (padding * 2)  # Padding on both sides
            current_height = green_height + (padding * 2)  # Padding on top and bottom
            
            # Create overlay window for GREEN box if it doesn't exist
            if not hasattr(self, '_cast_overlay') or self._cast_overlay is None:
                self._cast_overlay = tk.Toplevel(self)
                self._cast_overlay.title("Green Detection")
                self._cast_overlay.attributes('-topmost', True)
                self._cast_overlay.overrideredirect(True)
                
                # Use a specific color (lime green) as transparency key
                self._cast_overlay.attributes('-transparentcolor', '#00FF00')
                
                # Create canvas with lime green background (will be transparent)
                self._cast_canvas = tk.Canvas(self._cast_overlay, width=current_width, height=current_height, 
                                              bg='#00FF00', highlightthickness=0)
                self._cast_canvas.pack()
            
            # Clear canvas
            self._cast_canvas.delete('all')
            
            # Position overlay around where green is detected
            x1 = shake_area['x1']
            y1 = shake_area['y1']
            
            # Calculate screen position: center the box around the green bobber
            green_screen_x = x1 + green_x_local
            green_screen_y = y1 + green_y_local
            
            # Position box centered on green detection point
            box_x = green_screen_x - (current_width // 2)
            box_y = green_screen_y - (current_height // 2)
            
            # Update canvas size if green size changed
            if self._cast_canvas.winfo_width() != current_width or self._cast_canvas.winfo_height() != current_height:
                self._cast_canvas.config(width=current_width, height=current_height)
            
            # Move window to position (centered on green)
            self._cast_overlay.geometry(f"{current_width}x{current_height}+{box_x}+{box_y}")
            
            # Draw THICK RED OUTLINE box with only LEFT and RIGHT sides
            # Top and bottom omitted to avoid interfering with color detection
            line_width = 4
            line_offset = line_width // 2  # Offset to keep line within canvas bounds
            
            # Left side
            self._cast_canvas.create_line(
                line_offset, line_offset,
                line_offset, current_height - line_offset,
                fill='#FF0000', width=line_width
            )
            
            # Right side
            self._cast_canvas.create_line(
                current_width - line_offset, line_offset,
                current_width - line_offset, current_height - line_offset,
                fill='#FF0000', width=line_width
            )
            
            # Top and bottom sides intentionally omitted to avoid color interference
            
            # Force immediate visual update
            self._cast_overlay.deiconify()
            self._cast_canvas.update_idletasks()
            self._cast_overlay.update()
            
            # ===== WHITE PIXEL DETECTION BOX =====
            # Only show white box if white pixel was detected
            if white_y_local is not None:
                # Create overlay window for WHITE box if it doesn't exist
                if not hasattr(self, '_white_overlay') or self._white_overlay is None:
                    self._white_overlay = tk.Toplevel(self)
                    self._white_overlay.title("White Detection")
                    self._white_overlay.attributes('-topmost', True)
                    self._white_overlay.overrideredirect(True)
                    
                    # Use lime green as transparency key
                    self._white_overlay.attributes('-transparentcolor', '#00FF00')
                    
                    # Create canvas
                    self._white_canvas = tk.Canvas(self._white_overlay, width=current_width, height=current_height, 
                                                   bg='#00FF00', highlightthickness=0)
                    self._white_canvas.pack()
                
                # Clear canvas
                self._white_canvas.delete('all')
                
                # Calculate white pixel screen position (use green_x for horizontal alignment)
                white_screen_x = x1 + green_x_local
                white_screen_y = y1 + white_y_local
                
                # Position box centered on white detection point
                white_box_x = white_screen_x - (current_width // 2)
                white_box_y = white_screen_y - (current_height // 2)
                
                # Update canvas size if needed
                if self._white_canvas.winfo_width() != current_width or self._white_canvas.winfo_height() != current_height:
                    self._white_canvas.config(width=current_width, height=current_height)
                
                # Move window to position (centered on white)
                self._white_overlay.geometry(f"{current_width}x{current_height}+{white_box_x}+{white_box_y}")
                
                # Draw THICK RED OUTLINE box with only LEFT and RIGHT sides
                # Top and bottom omitted to avoid interfering with color detection
                
                # Left side
                self._white_canvas.create_line(
                    line_offset, line_offset,
                    line_offset, current_height - line_offset,
                    fill='#FF0000', width=line_width
                )
                
                # Right side
                self._white_canvas.create_line(
                    current_width - line_offset, line_offset,
                    current_width - line_offset, current_height - line_offset,
                    fill='#FF0000', width=line_width
                )
                
                # Top and bottom sides intentionally omitted to avoid color interference
                
                # Force immediate visual update
                self._white_overlay.deiconify()
                self._white_canvas.update_idletasks()
                self._white_overlay.update()
            else:
                # Hide white overlay if white pixel not detected
                if hasattr(self, '_white_overlay') and self._white_overlay is not None:
                    self._white_overlay.withdraw()
            
            # ===== PREDICTION INFO OVERLAY =====
            # Show prediction info if provided (for prediction/time-based mode)
            if prediction_info is not None:
                # Create info overlay if it doesn't exist
                if not hasattr(self, '_info_overlay') or self._info_overlay is None:
                    self._info_overlay = tk.Toplevel(self)
                    self._info_overlay.title("Release Info")
                    self._info_overlay.attributes('-topmost', True)
                    self._info_overlay.overrideredirect(True)
                    self._info_overlay.attributes('-alpha', 0.90)
                    self._info_label = tk.Label(
                        self._info_overlay,
                        text="",
                        font=("Consolas", 11, "bold"),
                        fg="#00FF00",
                        bg="#1a1a1a",
                        justify="left",
                        padx=12,
                        pady=10
                    )
                    self._info_label.pack()
                
                # Build info text in same format as velocity mode
                info_lines = ["⚡ PREDICTION RELEASE"]
                if 'distance' in prediction_info and prediction_info['distance'] is not None:
                    info_lines.append(f"   Distance: {prediction_info['distance']:.0f}px")
                if 'velocity' in prediction_info and prediction_info['velocity'] is not None:
                    info_lines.append(f"   Velocity: {prediction_info['velocity']:.1f}px/s")
                
                if len(info_lines) > 1:  # Has more than just the title
                    info_text = "\n".join(info_lines)
                    self._info_label.config(text=info_text)
                    
                    # Position info overlay to the right of the boxes
                    # Use the green box position as reference
                    self._info_overlay.update_idletasks()
                    info_width = self._info_overlay.winfo_reqwidth()
                    info_height = self._info_overlay.winfo_reqheight()
                    
                    # Position to the right of green box
                    info_x = box_x + current_width + 10  # 10px gap
                    info_y = box_y
                    
                    self._info_overlay.geometry(f"+{info_x}+{info_y}")
                    self._info_overlay.deiconify()
                    self._info_overlay.update()
                else:
                    # Hide if no info to display
                    self._info_overlay.withdraw()
            else:
                # Hide info overlay if no prediction info provided
                if hasattr(self, '_info_overlay') and self._info_overlay is not None:
                    self._info_overlay.withdraw()
            
        except Exception as e:
            # Silently fail - visualization is non-critical
            pass
    # AI_SYSTEM_END: SHAKE_SYSTEM

    # AI_SYSTEM_START: FISH_SYSTEM

    def _execute_fish_stage(self):  # AI_TARGET: FISH_MODE_SELECTOR
        print("🐟 === FISH STAGE STARTED ===")

        # Check fish track style and route to appropriate handler
        fish_track_style = self.settings.get("fish_track_style", "Color")

        if fish_track_style == "Color":
            print("🐟 Fish colors detected during shake timeout!")
            print("🐟 Entering fish catching mode (Color)...")
            self._update_status("Fish Stage: Color Mode", "white")
            return self._execute_fish_stage_color()
        elif fish_track_style == "Line":
            print("📏 Fish lines detected during shake timeout!")
            print("📏 Entering fish catching mode (Line)...")
            self._update_status("Fish Stage: Line Mode", "white")
            return self._execute_fish_stage_line()
        else:
            print(f"❌ Unknown fish track style: {fish_track_style}")
            return "restart"

    def _show_fish_visualization(self, frame, target_line_x, bar_left_x, bar_right_x, bar_center_x, arrow_center_x,
                                  width, height, x1, y1, target_left_x=None, target_right_x=None, target_middle_x=None):
        """
        Display visual overlay of detected fish elements on screen using PIL to draw directly on screen.
        Shows target line (left, right, middle), left bar, right bar, center, and arrow positions.
        Draws lines ABOVE the fish area to avoid interfering with scanning.
        """
        try:
            # Skip visualization if Show Fishing Overlay is disabled
            if not self.global_gui_settings.get("Show Fishing Overlay", True):
                return
            
            # Create transparent overlay window if it doesn't exist
            if not hasattr(self, '_debug_overlay') or self._debug_overlay is None:
                # Create a toplevel window for the overlay
                self._debug_overlay = tk.Toplevel(self)
                self._debug_overlay.title("Fish Debug")
                
                # Make it transparent and always on top
                self._debug_overlay.attributes('-topmost', True)
                self._debug_overlay.attributes('-alpha', 0.7)  # Semi-transparent
                self._debug_overlay.overrideredirect(True)  # No window decorations
                
                # Position above fish area
                overlay_y = y1 - height - height
                self._debug_overlay.geometry(f"{width}x{height}+{x1}+{overlay_y}")
                
                # Create canvas to draw on
                self._debug_canvas = tk.Canvas(self._debug_overlay, width=width, height=height, 
                                               bg='black', highlightthickness=0)
                self._debug_canvas.pack()
            
            # Clear previous drawings
            self._debug_canvas.delete('all')
            
            # Draw vertical lines for detected elements
            # Draw left bar (green)
            if bar_left_x is not None:
                x_pos = int(bar_left_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#00FF00', width=2)
                self._debug_canvas.create_text(x_pos + 10, 20, text='L', fill='#00FF00', font=('Arial', 10, 'bold'))
            
            # Draw right bar (blue)
            if bar_right_x is not None:
                x_pos = int(bar_right_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#0000FF', width=2)
                self._debug_canvas.create_text(x_pos + 10, 40, text='R', fill='#0000FF', font=('Arial', 10, 'bold'))
            
            # Draw center bar (cyan)
            if bar_center_x is not None:
                x_pos = int(bar_center_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#00FFFF', width=2)
                self._debug_canvas.create_text(x_pos + 10, 60, text='C', fill='#00FFFF', font=('Arial', 10, 'bold'))
            
            # Draw target line left (red)
            if target_left_x is not None:
                x_pos = int(target_left_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF0000', width=2)
                self._debug_canvas.create_text(x_pos + 10, 80, text='TL', fill='#FF0000', font=('Arial', 10, 'bold'))

            # Draw target line right (red)
            if target_right_x is not None:
                x_pos = int(target_right_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF0000', width=2)
                self._debug_canvas.create_text(x_pos + 10, 100, text='TR', fill='#FF0000', font=('Arial', 10, 'bold'))

            # Draw target line middle (orange)
            if target_middle_x is not None:
                x_pos = int(target_middle_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FFA500', width=2)
                self._debug_canvas.create_text(x_pos + 10, 120, text='TM', fill='#FFA500', font=('Arial', 10, 'bold'))
            elif target_line_x is not None:
                # Fallback: if new values not provided, use old target_line_x
                x_pos = int(target_line_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF0000', width=2)
                self._debug_canvas.create_text(x_pos + 10, 80, text='T', fill='#FF0000', font=('Arial', 10, 'bold'))

            # Draw arrow (magenta)
            if arrow_center_x is not None:
                x_pos = int(arrow_center_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF00FF', width=2)
                self._debug_canvas.create_text(x_pos + 10, 140, text='A', fill='#FF00FF', font=('Arial', 10, 'bold'))

            # Add legend at the bottom
            self._debug_canvas.create_text(10, height - 10, text='BL=BarLeft BR=BarRight C=BarCenter TL=TargetLeft TR=TargetRight TM=TargetMiddle A=Arrow',
                                          fill='white', anchor='w', font=('Arial', 8))
            
            # Update the display
            self._debug_overlay.update()
            
        except Exception as e:
            # Silently fail if visualization fails - don't interrupt fishing
            pass

    def _show_line_visualization(self, frame, target_left_x, target_right_x, bar_left_x, bar_right_x, target_middle_x, bar_middle_x, width, height, x1, y1):
        """
        Display visual overlay of detected line elements on screen using tkinter canvas.
        Shows target left/right lines, bar left/right lines, and middles.
        Draws lines ABOVE the fish area to avoid interfering with scanning.
        """
        try:
            # Skip visualization if Show Fishing Overlay is disabled
            if not self.global_gui_settings.get("Show Fishing Overlay", True):
                return
            
            # Create transparent overlay window if it doesn't exist
            if not hasattr(self, '_debug_overlay') or self._debug_overlay is None:
                # Create a toplevel window for the overlay
                self._debug_overlay = tk.Toplevel(self)
                self._debug_overlay.title("Fish Debug")
                
                # Make it transparent and always on top
                self._debug_overlay.attributes('-topmost', True)
                self._debug_overlay.attributes('-alpha', 0.7)  # Semi-transparent
                self._debug_overlay.overrideredirect(True)  # No window decorations
                
                # Position above fish area
                overlay_y = y1 - height - height
                self._debug_overlay.geometry(f"{width}x{height}+{x1}+{overlay_y}")
                
                # Create canvas to draw on
                self._debug_canvas = tk.Canvas(self._debug_overlay, width=width, height=height, 
                                               bg='black', highlightthickness=0)
                self._debug_canvas.pack()
            
            # Clear previous drawings
            self._debug_canvas.delete('all')
            
            # Draw vertical lines for detected elements
            # Draw target left line (red)
            if target_left_x is not None:
                x_pos = int(target_left_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF0000', width=2)
                self._debug_canvas.create_text(x_pos + 10, 20, text='TL', fill='#FF0000', font=('Arial', 10, 'bold'))
            
            # Draw target right line (red)
            if target_right_x is not None:
                x_pos = int(target_right_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FF0000', width=2)
                self._debug_canvas.create_text(x_pos + 10, 40, text='TR', fill='#FF0000', font=('Arial', 10, 'bold'))
            
            # Draw target middle (orange)
            if target_middle_x is not None:
                x_pos = int(target_middle_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#FFA500', width=2)
                self._debug_canvas.create_text(x_pos + 10, 60, text='TM', fill='#FFA500', font=('Arial', 10, 'bold'))
            
            # Draw bar left line (green)
            if bar_left_x is not None:
                x_pos = int(bar_left_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#00FF00', width=2)
                self._debug_canvas.create_text(x_pos + 10, 80, text='BL', fill='#00FF00', font=('Arial', 10, 'bold'))
            
            # Draw bar right line (blue)
            if bar_right_x is not None:
                x_pos = int(bar_right_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#0000FF', width=2)
                self._debug_canvas.create_text(x_pos + 10, 100, text='BR', fill='#0000FF', font=('Arial', 10, 'bold'))
            
            # Draw bar middle (cyan)
            if bar_middle_x is not None:
                x_pos = int(bar_middle_x)
                self._debug_canvas.create_line(x_pos, 0, x_pos, height, fill='#00FFFF', width=2)
                self._debug_canvas.create_text(x_pos + 10, 120, text='BM', fill='#00FFFF', font=('Arial', 10, 'bold'))
            
            # Add legend at the bottom
            self._debug_canvas.create_text(10, height - 10, text='TL/TR=Target  TM=Target Mid  BL/BR=Bars  BM=Bar Mid',
                                          fill='white', anchor='w', font=('Arial', 8))
            
            # Update the display
            self._debug_overlay.update()
            
        except Exception as e:
            # Silently fail if visualization fails - don't interrupt fishing
            pass

    def _execute_fish_stage_color(self):  # AI_TARGET: FISH_COLOR_DETECTION
        
        try:
            # Load fish settings for current rod
            current_rod = self.settings.get("fish_rod_type", "Default")
            
            # Get colors and tolerances for current rod
            target_line_color = self._get_fish_color_for_rod("fish_target_line_color", current_rod)
            left_bar_color = self._get_fish_color_for_rod("fish_left_bar_color", current_rod)
            right_bar_color = self._get_fish_color_for_rod("fish_right_bar_color", current_rod)
            arrow_color = self._get_fish_color_for_rod("fish_arrow_color", current_rod)
            
            target_line_tolerance = self._get_fish_tolerance_for_rod("fish_target_line_tolerance", current_rod)
            left_bar_tolerance = self._get_fish_tolerance_for_rod("fish_left_bar_tolerance", current_rod)
            right_bar_tolerance = self._get_fish_tolerance_for_rod("fish_right_bar_tolerance", current_rod)
            arrow_tolerance = self._get_fish_tolerance_for_rod("fish_arrow_tolerance", current_rod)
            
            # Get fish-specific settings
            scan_fps = self._get_rod_specific_setting("fish_scan_fps", 150)
            fish_lost_timeout = self._get_rod_specific_setting("fish_lost_timeout", 1)
            bar_ratio_from_side = self._get_rod_specific_setting("fish_bar_ratio_from_side", 0.5)
            control_mode = self._get_rod_specific_setting("fish_control_mode", "Normal")
            kp = self._get_rod_specific_setting("fish_kp", 0.9)
            kd = self._get_rod_specific_setting("fish_kd", 0.3)
            pd_clamp = self._get_rod_specific_setting("fish_pd_clamp", 1.0)
            
            # Get capture mode from settings  
            capture_mode, use_mss = self._get_capture_mode_settings()
            
            # Fish area coordinates
            if not self.fish_box:
                print("⚠️ No fish area set - cannot proceed")
                return "restart"
                
            x1, y1, x2, y2 = self.fish_box["x1"], self.fish_box["y1"], self.fish_box["x2"], self.fish_box["y2"]
            region = (x1, y1, x2, y2)
            width = x2 - x1
            height = y2 - y1
            
            print(f"🐟 Fish area: ({x1},{y1}) to ({x2},{y2}) - {width}x{height}")
            print(f"🎣 Rod: {current_rod} | Capture: {capture_mode} | FPS: {scan_fps}")
            print(f"🎨 Colors - Target: {target_line_color}, Left: {left_bar_color}, Right: {right_bar_color}, Arrow: {arrow_color}")

            # Move cursor to top middle of shake area (anti-Roblox detection)
            if self.shake_box:
                shake_center_x = (self.shake_box["x1"] + self.shake_box["x2"]) // 2
                shake_top_y = self.shake_box["y1"]
                print(f"🖱️ Moving cursor to shake area top-middle: ({shake_center_x}, {shake_top_y})")
                windll.user32.SetCursorPos(shake_center_x, shake_top_y)
                # Move 1 pixel down relatively (anti-Roblox detection)
                windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
                print(f"🖱️ Moved cursor 1px down relatively")

            # Arrow disabled check
            arrow_enabled = arrow_color is not None and arrow_color.lower() not in ["none", "#none", ""]
            if not arrow_enabled:
                print("⚙️ Arrow color disabled - using bar-only mode")

            # Pre-compute BGR colors once before loop (optimization)
            target_line_bgr = self._hex_to_bgr(target_line_color)
            left_bar_bgr = self._hex_to_bgr(left_bar_color)
            right_bar_bgr = self._hex_to_bgr(right_bar_color)
            arrow_bgr = self._hex_to_bgr(arrow_color) if arrow_enabled else None

            # Initialize capture method
            camera = None
            mss_instance = None

            if use_mss:
                print("📷 Using MSS capture for fish detection")
                mss_monitor = {"top": y1, "left": x1, "width": width, "height": height}
                mss_instance = mss.mss()  # Create once, reuse in loop
            else:
                print("🎥 Using DXCAM capture for fish detection")
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        # Release any previous camera instance before retry
                        if camera is not None:
                            try:
                                camera.release()
                            except:
                                pass
                            camera = None
                        
                        camera = dxcam.create(output_idx=0, output_color="BGR")
                        if camera:
                            break
                        print(f"❌ DXCam creation failed (attempt {attempt + 1}/{max_retries})")
                        time.sleep(0.1)
                    except Exception as e:
                        print(f"❌ DXCam error (attempt {attempt + 1}/{max_retries}): {e}")
                        time.sleep(0.1)

                if not camera:
                    print("⚠️ Failed to create DXCam - falling back to MSS")
                    use_mss = True
                    mss_monitor = {"top": y1, "left": x1, "width": width, "height": height}
                    mss_instance = mss.mss()  # Create once, reuse in loop
            
            # Calculate scan delay
            scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.001
            if scan_fps >= 1000:
                scan_delay = 0.001  # 0ms delay special case
            
            # Initialize tracking variables
            target_line_last_x = None
            bar_center_x = None
            target_line_lost_timer = 0.0
            last_scan_time = time.time()
            
            # Exit condition checking variables
            last_exit_check_time = time.time()
            exit_check_interval = 0.5  # Check every 500ms during valid detection
            
            # Stability detection variables
            stability_state = True  # Start in stability mode
            stability_initial_target_x = None
            stability_initial_bar_x = None
            stability_scan_count = 0
            stability_alternate_state = False  # Alternates between hold/release
            
            # PD control variables
            last_error = None
            last_target_x = None
            is_holding_click = False
            frame_counter = 0  # For periodic logging

            # Arrow fallback variables (based on v5.py logic)
            estimated_box_length = None
            has_calculated_length_once = False
            last_left_x = None
            last_right_x = None
            last_indicator_x = None
            last_holding_state = False

            # Track if bars were found to skip arrow scanning (optimization)
            bars_found_previously = False

            print("🔄 Starting fish detection loop...")

            # Main fish detection loop
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()
                frame_counter += 1  # Increment frame counter
                
                # Capture frame with retry loop - keep trying until we get a frame
                frame = None
                capture_attempts = 0
                max_capture_attempts = 10

                while frame is None and capture_attempts < max_capture_attempts:
                    try:
                        if use_mss:
                            # Reuse mss_instance instead of creating new one each frame
                            screenshot = mss_instance.grab(mss_monitor)
                            frame = np.array(screenshot)
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                        else:
                            # Use linear grab() method
                            frame = camera.grab(region=region)

                        if frame is None:
                            capture_attempts += 1
                            if capture_attempts == 1:
                                print(f"⚠️ Frame capture returned None, retrying... (attempt {capture_attempts}/{max_capture_attempts})")
                            time.sleep(0.001)  # 1ms delay between retries

                    except Exception as e:
                        capture_attempts += 1
                        print(f"❌ Capture error on attempt {capture_attempts}: {e}")
                        time.sleep(0.001)

                # If we exhausted all retries, skip this cycle
                if frame is None:
                    print(f"❌ Failed to capture frame after {max_capture_attempts} attempts, skipping cycle")
                    time.sleep(scan_delay)
                    continue

                # Detect colors in frame (using pre-computed BGR colors)
                # Skip bar detection entirely when in edge lock state (optimization)
                in_edge_lock = hasattr(self, '_locked_edge_threshold') and self._locked_edge_threshold is not None
                
                if in_edge_lock:
                    # Edge lock active - only scan for target line, skip all bar detection
                    detection_result = self._detect_fish_colors_in_frame(
                        frame, target_line_bgr, left_bar_bgr, right_bar_bgr,
                        arrow_bgr,
                        target_line_tolerance, 0, 0,  # Set bar tolerances to 0 to skip detection
                        0,  # Skip arrow
                        skip_arrow_scan=True
                    )
                    # Use locked bar positions from memory
                    target_line_x = detection_result.get("target_line_x")
                    target_left_x = detection_result.get("target_left_x")
                    target_right_x = detection_result.get("target_right_x")
                    target_middle_x = detection_result.get("target_middle_x")
                    bar_left_x = self._last_bar_left_x
                    bar_right_x = self._last_bar_right_x
                    arrow_center_x = None
                    if frame_counter % 10 == 0:
                        print("🔒 EDGE LOCK: Skipping bar detection, using locked positions")
                else:
                    # Normal detection - scan for everything
                    skip_arrow = bars_found_previously and arrow_enabled
                    if skip_arrow and frame_counter % 10 == 0:  # Log every 10th frame
                        print("⚡ Optimization: Skipping arrow scan (bars found)")
                    detection_result = self._detect_fish_colors_in_frame(
                        frame, target_line_bgr, left_bar_bgr, right_bar_bgr,
                        arrow_bgr,
                        target_line_tolerance, left_bar_tolerance, right_bar_tolerance,
                        arrow_tolerance if arrow_enabled else 0,
                        skip_arrow_scan=skip_arrow
                    )
                    
                    target_line_x = detection_result.get("target_line_x")
                    target_left_x = detection_result.get("target_left_x")
                    target_right_x = detection_result.get("target_right_x")
                    target_middle_x = detection_result.get("target_middle_x")
                    bar_left_x = detection_result.get("bar_left_x")
                    bar_right_x = detection_result.get("bar_right_x")
                    arrow_center_x = detection_result.get("arrow_center_x")
                
                # Debug logging - show detected color coordinates
                debug_colors = []
                if target_left_x is not None and target_right_x is not None and target_middle_x is not None:
                    debug_colors.append(f"Target=L{target_left_x:.0f}/M{target_middle_x:.0f}/R{target_right_x:.0f}")
                elif target_line_x is not None:
                    debug_colors.append(f"Target={target_line_x:.0f}")
                if bar_left_x is not None:
                    debug_colors.append(f"BarL={bar_left_x:.0f}")
                if bar_right_x is not None:
                    debug_colors.append(f"BarR={bar_right_x:.0f}")
                if arrow_center_x is not None:
                    debug_colors.append(f"Arrow={arrow_center_x:.0f}")

                if debug_colors:
                    print(f"🔍 DEBUG: Detected X coords: {', '.join(debug_colors)}")
                
                # Check exit condition (every 500ms when valid detection found)
                if (target_line_x is not None or target_left_x is not None) and (bar_left_x is not None or bar_right_x is not None or arrow_center_x is not None):
                    # Valid detection - check exit condition periodically
                    if current_time - last_exit_check_time >= exit_check_interval:
                        exit_result = self._check_fish_exit_condition()
                        if exit_result == "fish_stage":
                            print(f"🐟 Fish stage exit condition met - green color detected in bottom left")
                            break
                        last_exit_check_time = current_time
                
                # NOTE: Live feed overlay update moved to after bar calculations
                # so it can show arrow-estimated positions too
                
                # Update target line position and reset timer if found
                if target_line_x is not None:
                    target_line_last_x = target_line_x  # Use most right pixel as requested
                    target_line_lost_timer = 0.0  # Reset timer
                else:
                    # Target line lost - increment timer
                    target_line_lost_timer += (current_time - last_scan_time)
                    
                    # Check if target line lost too long
                    if target_line_lost_timer >= fish_lost_timeout:
                        print(f"⚠️ Target line lost for {fish_lost_timeout}s - exiting fish stage")
                        break
                
                # Initialize last known bar positions
                if not hasattr(self, '_last_bar_left_x'):
                    self._last_bar_left_x = None
                if not hasattr(self, '_last_bar_right_x'):
                    self._last_bar_right_x = None
                if not hasattr(self, '_last_bar_box_size'):
                    self._last_bar_box_size = None  # Track box size (right - left)
                if not hasattr(self, '_last_bar_center_x'):
                    self._last_bar_center_x = None  # Track last known center for arrow side detection
                
                # Calculate bar center and remember positions
                # Track if ANY bar color was detected in current frame
                any_bar_detected_this_frame = (bar_left_x is not None or bar_right_x is not None)
                bar_center_found = False
                if bar_left_x is not None and bar_right_x is not None:
                    # Both bars detected - validate and save positions
                    # Ensure left is never greater than right (swap if needed)
                    if bar_left_x > bar_right_x:
                        bar_left_x, bar_right_x = bar_right_x, bar_left_x
                        print(f"🔄 Color mode: Swapped bars (L was > R)")

                    # Calculate current frame values (don't update memory yet - edge detection does that)
                    bar_center_x = (bar_left_x + bar_right_x) / 2.0
                    bar_center_found = True
                    bar_box_size = bar_right_x - bar_left_x
                    print(f"📊 Color mode: Bars at L={bar_left_x:.0f}, R={bar_right_x:.0f}, Size={bar_box_size:.0f}px")
                elif bar_left_x is not None:
                    # Only left bar found - use last known right position
                    bar_right_x = self._last_bar_right_x  # Use last known right position
                    if bar_right_x is not None:
                        # Validate: left must be less than right
                        if bar_left_x < bar_right_x:
                            bar_center_x = (bar_left_x + bar_right_x) / 2.0
                            bar_center_found = True
                        else:
                            # Invalid: left >= right, use old positions
                            print(f"⚠️ Color mode: Rejected left bar {bar_left_x:.0f} (>= right {bar_right_x:.0f})")
                            bar_left_x = self._last_bar_left_x  # Keep old position
                            if bar_left_x is not None:
                                bar_center_x = (bar_left_x + bar_right_x) / 2.0
                                bar_center_found = True
                elif bar_right_x is not None:
                    # Only right bar found - use last known left position
                    bar_left_x = self._last_bar_left_x  # Use last known left position
                    if bar_left_x is not None:
                        # Validate: right must be greater than left
                        if bar_right_x > bar_left_x:
                            bar_center_x = (bar_left_x + bar_right_x) / 2.0
                            bar_center_found = True
                        else:
                            # Invalid: right <= left, use old positions
                            print(f"⚠️ Color mode: Rejected right bar {bar_right_x:.0f} (<= left {bar_left_x:.0f})")
                            bar_right_x = self._last_bar_right_x  # Keep old position
                            if bar_right_x is not None:
                                bar_center_x = (bar_left_x + bar_right_x) / 2.0
                                bar_center_found = True
                
                # Arrow fallback logic: ONLY triggers if NO bar colors were detected in this frame
                # If arrow is found, it updates ONE side (whichever is closer), OTHER side uses old position
                if not any_bar_detected_this_frame and arrow_enabled and arrow_center_x is not None:
                    last_center = self._last_bar_center_x
                    box_size = self._last_bar_box_size

                    # If we have previous bar data, determine which side the arrow is on
                    if last_center is not None and box_size is not None and box_size > 0:
                        # Get last known bar positions for validation
                        last_left = self._last_bar_left_x
                        last_right = self._last_bar_right_x

                        # Determine which side based on center comparison
                        arrow_on_left_side = arrow_center_x < last_center

                        # SMART VALIDATION: Check if arrow is actually near the bar we think it is
                        # Calculate distances to both last known bars
                        dist_to_left = abs(arrow_center_x - last_left) if last_left is not None else float('inf')
                        dist_to_right = abs(arrow_center_x - last_right) if last_right is not None else float('inf')

                        # Self-correction: If arrow is much closer to the opposite bar, we detected wrong side!
                        # Threshold: arrow should be within reasonable distance (box_size / 4) of expected bar
                        proximity_threshold = box_size / 4

                        if arrow_on_left_side:
                            # We think arrow is on LEFT, but verify it's actually near left bar
                            if dist_to_right < dist_to_left and dist_to_right < proximity_threshold:
                                # Arrow is actually closer to RIGHT bar - we were wrong!
                                print(f"🔧 Arrow mode: SELF-CORRECTION - Arrow at {arrow_center_x:.0f} closer to RIGHT bar ({dist_to_right:.0f}px) than LEFT ({dist_to_left:.0f}px)")
                                arrow_on_left_side = False  # Flip the decision

                        else:
                            # We think arrow is on RIGHT, but verify it's actually near right bar
                            if dist_to_left < dist_to_right and dist_to_left < proximity_threshold:
                                # Arrow is actually closer to LEFT bar - we were wrong!
                                print(f"🔧 Arrow mode: SELF-CORRECTION - Arrow at {arrow_center_x:.0f} closer to LEFT bar ({dist_to_left:.0f}px) than RIGHT ({dist_to_right:.0f}px)")
                                arrow_on_left_side = True  # Flip the decision

                        # Now apply the corrected decision
                        if arrow_on_left_side:
                            # Arrow is on the LEFT side - update left bar, keep right bar from memory
                            bar_left_x = arrow_center_x
                            bar_right_x = self._last_bar_right_x

                            if bar_right_x is None:
                                # If no right bar in memory, calculate from box size
                                bar_right_x = bar_left_x + box_size

                            # Validate: ensure left < right
                            if bar_left_x < bar_right_x:
                                self._last_bar_left_x = bar_left_x
                                self._last_bar_right_x = bar_right_x
                                bar_center_x = (bar_left_x + bar_right_x) / 2.0
                                self._last_bar_center_x = bar_center_x
                                bar_center_found = True
                                print(f"⬅️ Arrow mode: Arrow LEFT of center - L={bar_left_x:.0f} (arrow), R={bar_right_x:.0f} (kept)")
                            else:
                                print(f"⚠️ Arrow mode: Invalid - arrow left {bar_left_x:.0f} >= right {bar_right_x:.0f}")
                        else:
                            # Arrow is on the RIGHT side - update right bar, keep left bar from memory
                            bar_right_x = arrow_center_x
                            bar_left_x = self._last_bar_left_x

                            if bar_left_x is None:
                                # If no left bar in memory, calculate from box size
                                bar_left_x = bar_right_x - box_size

                            # Validate: ensure left < right
                            if bar_left_x < bar_right_x:
                                self._last_bar_left_x = bar_left_x
                                self._last_bar_right_x = bar_right_x
                                bar_center_x = (bar_left_x + bar_right_x) / 2.0
                                self._last_bar_center_x = bar_center_x
                                bar_center_found = True
                                print(f"➡️ Arrow mode: Arrow RIGHT of center - L={bar_left_x:.0f} (kept), R={bar_right_x:.0f} (arrow)")
                            else:
                                print(f"⚠️ Arrow mode: Invalid - left {bar_left_x:.0f} >= arrow right {bar_right_x:.0f}")

                    # Fallback: Try to establish initial box size from previous positions
                    elif self._last_bar_left_x is not None and self._last_bar_right_x is not None:
                        box_size = self._last_bar_right_x - self._last_bar_left_x
                        last_center = (self._last_bar_left_x + self._last_bar_right_x) / 2.0

                        if box_size > 0:
                            self._last_bar_box_size = box_size
                            self._last_bar_center_x = last_center

                            # Determine side based on arrow position relative to last center
                            if arrow_center_x < last_center:
                                bar_left_x = arrow_center_x
                                bar_right_x = bar_left_x + box_size
                                print(f"⬅️ Arrow mode: Initial LEFT - L={bar_left_x:.0f} (arrow), R={bar_right_x:.0f} (size={box_size:.0f})")
                            else:
                                bar_right_x = arrow_center_x
                                bar_left_x = bar_right_x - box_size
                                print(f"➡️ Arrow mode: Initial RIGHT - L={bar_left_x:.0f} (size={box_size:.0f}), R={bar_right_x:.0f} (arrow)")

                            self._last_bar_left_x = bar_left_x
                            self._last_bar_right_x = bar_right_x
                            bar_center_x = (bar_left_x + bar_right_x) / 2.0
                            self._last_bar_center_x = bar_center_x
                            bar_center_found = True
                        else:
                            # Invalid box size (<=0) - use default based on fish area width
                            default_box_size = width // 2
                            bar_left_x = arrow_center_x
                            bar_right_x = bar_left_x + default_box_size

                            self._last_bar_left_x = bar_left_x
                            self._last_bar_right_x = bar_right_x
                            self._last_bar_box_size = default_box_size

                            bar_center_x = (bar_left_x + bar_right_x) / 2.0
                            self._last_bar_center_x = bar_center_x
                            bar_center_found = True
                            print(f"⚠️ Arrow mode: Invalid box size (<=0), using fish area width/2={default_box_size}px - L={bar_left_x:.0f}, R={bar_right_x:.0f}")

                    else:
                        # No previous data - assume a default box size based on fish area width
                        # Default box size: half the width of the fish area (reasonable estimate)
                        default_box_size = width // 2

                        # Start with arrow as left bar, calculate right from default size
                        bar_left_x = arrow_center_x
                        bar_right_x = bar_left_x + default_box_size

                        # Save these initial estimates
                        self._last_bar_left_x = bar_left_x
                        self._last_bar_right_x = bar_right_x
                        self._last_bar_box_size = default_box_size

                        bar_center_x = (bar_left_x + bar_right_x) / 2.0
                        self._last_bar_center_x = bar_center_x
                        bar_center_found = True
                        print(f"⚠️ Arrow mode: No previous data, using fish area width/2 as default box size={default_box_size}px - L={bar_left_x:.0f}, R={bar_right_x:.0f}")

                # Update bars_found_previously flag for next frame optimization
                # If bars were detected from colors (not arrow fallback), we can skip arrow scanning next time
                bars_detected_from_colors = (detection_result.get("bar_left_x") is not None or
                                            detection_result.get("bar_right_x") is not None)
                bars_found_previously = bars_detected_from_colors

                # Show visual overlay of detected elements (for debugging)
                self._show_fish_visualization(
                    frame, target_line_x, bar_left_x, bar_right_x, bar_center_x, arrow_center_x,
                    width, height, x1, y1,
                    target_left_x=target_left_x, target_right_x=target_right_x, target_middle_x=target_middle_x
                )

                # PD Control (only if both target line and bar center are available)
                if target_line_last_x is not None and bar_center_found and bar_center_x is not None:
                    
                    # STEP 1: Edge detection - determine if at edges and whether to update bar positions
                    current_bar_width = abs(bar_right_x - bar_left_x) if bar_left_x is not None and bar_right_x is not None else 0
                    
                    # Initialize transition state (default: not in transition)
                    in_transition = False
                    
                    # Lock edge threshold when entering edge zone (don't update while at edge)
                    if not hasattr(self, '_locked_edge_threshold') or self._locked_edge_threshold is None:
                        # Not at edge or first time - calculate from current bar width
                        edge_threshold = current_bar_width * bar_ratio_from_side
                        self._locked_edge_threshold = edge_threshold
                    else:
                        # Already at edge - use locked threshold
                        edge_threshold = self._locked_edge_threshold
                    
                    target_at_left_edge = target_line_last_x < edge_threshold
                    target_at_right_edge = target_line_last_x > (width - edge_threshold)
                    target_at_edge = target_at_left_edge or target_at_right_edge
                    
                    # Update bar positions ONLY if in safe zone (not at edges)
                    if not target_at_edge:
                        # Clear locked threshold when in safe zone
                        self._locked_edge_threshold = None
                        if bar_left_x is not None:
                            self._last_bar_left_x = bar_left_x
                        if bar_right_x is not None:
                            self._last_bar_right_x = bar_right_x
                        if bar_center_x is not None:
                            self._last_bar_center_x = bar_center_x
                        # Update box size for arrow fallback
                        if bar_left_x is not None and bar_right_x is not None:
                            self._last_bar_box_size = bar_right_x - bar_left_x
                    
                    # STEP 2: Calculate error (ALWAYS, regardless of edge state)
                    # Use current detection for error calculation
                    error = target_line_last_x - bar_center_x
                    
                    # STEP 3: Stability state check (ALWAYS, regardless of edge state)
                    # Use MEMORY positions for stability check (only updated in safe zone)
                    if stability_state:
                        # Initialize reference positions on first detection
                        if stability_initial_target_x is None:
                            stability_initial_target_x = target_line_last_x
                            stability_initial_bar_x = self._last_bar_center_x if self._last_bar_center_x is not None else bar_center_x
                            print(f"📌 STABILITY: Initial positions - Target: {target_line_last_x:.0f}, Bar: {stability_initial_bar_x:.0f}")
                        
                        # Check if target line or bar has moved by 3 pixels (scaled to current resolution)
                        # Compare using MEMORY positions (which only update in safe zone)
                        stability_threshold = 3 * (width / 517)
                        target_moved = abs(target_line_last_x - stability_initial_target_x) >= stability_threshold
                        # Use memory bar position for comparison, fall back to current if memory not available
                        current_tracked_bar_x = self._last_bar_center_x if self._last_bar_center_x is not None else bar_center_x
                        bar_moved = abs(current_tracked_bar_x - stability_initial_bar_x) >= stability_threshold
                        
                        if target_moved or bar_moved:
                            # Exit stability mode
                            stability_state = False
                            print(f"🔄 STABILITY: Movement detected! Target moved: {target_moved}, Bar moved: {bar_moved}")
                            print(f"⚙️ STABILITY: Switching to normal PD control after {stability_scan_count} scans")
                        else:
                            # Stay in stability mode - alternate every 2 scans
                            stability_scan_count += 1
                            if stability_scan_count % 2 == 0:
                                stability_alternate_state = not stability_alternate_state
                            
                            # Stability alternation sets should_hold, but edge can override below
                            should_hold = stability_alternate_state
                            
                            # Update error for derivative calculation even in stability mode
                            last_error = error
                            last_target_x = target_line_last_x
                    
                    # STEP 4: Normal PD control (if not in stability)
                    if not stability_state:
                        # Select control algorithm based on mode
                        if control_mode in ["Normal", "Steady"]:
                            # P term - proportional to how far we need to move
                            p_term = kp * error
                            
                            # D term - ASYMMETRIC damping based on situation
                            d_term = 0.0
                            time_delta = current_time - last_scan_time
                            if last_target_x is not None and last_error is not None and time_delta > 0.001:
                                # Calculate bar velocity (how fast bar is moving)
                                last_bar_x = last_target_x - last_error
                                bar_velocity = (bar_center_x - last_bar_x) / time_delta
                                
                                # Determine if we're approaching or chasing
                                error_magnitude_decreasing = abs(error) < abs(last_error)
                                bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                
                                if error_magnitude_decreasing and bar_moving_toward_target:
                                    # APPROACHING TARGET - Strong damping to prevent overshoot (2x)
                                    damping_multiplier = 2.0
                                    d_term = -kd * damping_multiplier * bar_velocity
                                else:
                                    # CHASING TARGET - Minimal damping to allow fast movement (0.5x)
                                    damping_multiplier = 0.5
                                    d_term = -kd * damping_multiplier * bar_velocity
                            
                            # Combined control signal (PD controller output)
                            control_signal = p_term + d_term
                            control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp
                            
                            # DIRECTIONAL DECISION: Convert continuous signal to binary hold/release
                            if control_signal > 0:
                                should_hold = True
                            else:
                                should_hold = False
                        
                        elif control_mode == "NigGamble":
                            # NIGGAMBLE MODE: (Clone of Normal for now - will be modified)
                            p_term = kp * error
                            
                            # D term - ASYMMETRIC damping
                            d_term = 0.0
                            time_delta = current_time - last_scan_time
                            if last_target_x is not None and last_error is not None and time_delta > 0.001:
                                last_bar_x = last_target_x - last_error
                                bar_velocity = (bar_center_x - last_bar_x) / time_delta
                                
                                error_magnitude_decreasing = abs(error) < abs(last_error)
                                bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                
                                if error_magnitude_decreasing and bar_moving_toward_target:
                                    damping_multiplier = 2.0
                                    d_term = -kd * damping_multiplier * bar_velocity
                                else:
                                    damping_multiplier = 0.5
                                    d_term = -kd * damping_multiplier * bar_velocity
                            
                            control_signal = p_term + d_term
                            control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp
                            
                            if control_signal > 0:
                                should_hold = True
                            else:
                                should_hold = False
                        
                        # Update PD state for next iteration
                        last_error = error
                        last_target_x = target_line_last_x
                    
                    # STEP 5: Execute mouse control
                    # Apply edge overrides
                    if target_at_left_edge:
                        should_hold = False  # Force RELEASE at left edge
                        print(f"⬅️ EDGE: Left ({target_line_last_x:.0f} < {edge_threshold:.0f}) - FORCE RELEASE")
                    elif target_at_right_edge:
                        should_hold = True  # Force HOLD at right edge
                        print(f"➡️ EDGE: Right ({target_line_last_x:.0f} > {width - edge_threshold:.0f}) - FORCE HOLD")
                    elif in_transition:
                        print(f"⏳ TRANSITION: {'HOLD' if should_hold else 'RELEASE'}")
                    
                    # Execute the mouse action
                    mouse_action_taken = False
                    if should_hold and not is_holding_click:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        is_holding_click = True
                        mouse_action_taken = True
                        if stability_state:
                            print(f"� STABILITY #{stability_scan_count}: HOLD (Target: {target_line_last_x:.0f}, Bar: {bar_center_x:.0f}, Error: {error:.1f})")
                        elif not target_at_edge and not in_transition:
                            print(f"�🔒 HOLD [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f}")
                    elif not should_hold and is_holding_click:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        is_holding_click = False
                        mouse_action_taken = True
                        if stability_state:
                            print(f"� STABILITY #{stability_scan_count}: RELEASE (Target: {target_line_last_x:.0f}, Bar: {bar_center_x:.0f}, Error: {error:.1f})")
                        elif not target_at_edge and not in_transition:
                            print(f"�🔓 RELEASE [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f}")

                    if not mouse_action_taken and not stability_state and not target_at_edge and not in_transition:
                        current_state = "HOLDING" if is_holding_click else "RELEASED"
                        print(f"⚡ {current_state} [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f}")
                    
                else:
                    # No tracking data - alternate hold/release to keep bar moving
                    if is_holding_click:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        is_holding_click = False
                        print("🔓 FALLBACK RELEASE - No tracking data")
                    else:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        is_holding_click = True
                        print("🔒 FALLBACK HOLD - No tracking data")
                
                last_scan_time = current_time
                time.sleep(scan_delay)
            
            # Cleanup
            if is_holding_click:
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                print("✅ Final RELEASE")
            
            # Close visualization window
            try:
                if hasattr(self, '_debug_overlay') and self._debug_overlay:
                    self._debug_overlay.destroy()
                    self._debug_overlay = None
            except:
                pass

            if camera and not use_mss:
                camera.release()
                print("📷 DXCam camera released")
            elif use_mss and mss_instance:
                mss_instance.close()
                print("📷 MSS instance closed")

            # Close cast visualization overlays at end of fish stage
            self._cleanup_cast_overlays()

            print("✅ === FISH STAGE ENDED ===")
            return "restart"  # Return to main loop
            
        except Exception as e:
            print(f"❌ Error in fish stage: {e}")
            import traceback
            traceback.print_exc()
            
            # Cleanup on error
            if 'is_holding_click' in locals() and is_holding_click:
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            if 'camera' in locals() and camera and not use_mss:
                try:
                    camera.release()
                except:
                    pass
            elif 'mss_instance' in locals() and mss_instance:
                try:
                    mss_instance.close()
                except:
                    pass
            return "restart"

    def _execute_fish_stage_line(self):  # AI_TARGET: FISH_LINE_DETECTION
        try:
            # Load fish line settings for current rod
            current_rod = self.settings.get("fish_rod_type", "Default")
            scan_fps = self._get_rod_specific_setting("fish_line_scan_fps", 150)
            fish_lost_timeout = self._get_rod_specific_setting("fish_line_lost_timeout", 1.0)
            bar_ratio = self._get_rod_specific_setting("fish_line_bar_ratio", 0.6)
            control_mode = self._get_rod_specific_setting("fish_line_control_mode", "Normal")
            kp = self._get_rod_specific_setting("fish_line_kp", 0.9)
            kd = self._get_rod_specific_setting("fish_line_kd", 0.3)
            pd_clamp = self._get_rod_specific_setting("fish_line_pd_clamp", 1.0)

            print(f"⚙️ Line Settings: FPS={scan_fps}, Lost Timeout={fish_lost_timeout}s, Bar Ratio={bar_ratio}, Mode={control_mode}")
            print(f"⚙️ PD Settings: KP={kp}, KD={kd}, PD Clamp={pd_clamp}")

            # Fish area coordinates
            if not self.fish_box:
                print("⚠️ No fish area set - cannot proceed")
                return "restart"

            x1, y1, x2, y2 = self.fish_box["x1"], self.fish_box["y1"], self.fish_box["x2"], self.fish_box["y2"]
            width = x2 - x1
            height = y2 - y1
            image_center_x = width // 2

            print(f"🐟 Fish area: ({x1},{y1}) to ({x2},{y2}), size: {width}x{height}")

            # Import for mouse control (must be before cursor movement)
            from ctypes import windll

            # Move cursor to top middle of shake area (anti-Roblox detection)
            if self.shake_box:
                shake_center_x = (self.shake_box["x1"] + self.shake_box["x2"]) // 2
                shake_top_y = self.shake_box["y1"]
                print(f"🖱️ Moving cursor to shake area top-middle: ({shake_center_x}, {shake_top_y})")
                windll.user32.SetCursorPos(shake_center_x, shake_top_y)
                # Move 1 pixel down relatively (anti-Roblox detection)
                windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
                print(f"🖱️ Moved cursor 1px down relatively")

            # Initialize capture using MSS (more reliable for fish area)

            # Tracking state variables
            initial_target_gap = None
            last_target_left_x = None
            last_target_right_x = None
            last_left_bar_x = None
            last_right_bar_x = None
            fish_lost_timer = 0.0
            last_scan_time = time.time()
            is_initial_run = True
            locked_edge_threshold_line = None  # Clear edge lock from previous fish

            # Exit condition checking variables
            last_exit_check_time = time.time()
            exit_check_interval = 0.5  # Check every 500ms during valid lines
            invalid_line_alternate_counter = 0  # Counter for alternating checks during invalid lines

            # Stability detection variables (same as Color mode)
            stability_state = True  # Start in stability mode
            stability_initial_target_x = None
            stability_initial_bar_x = None
            stability_scan_count = 0
            stability_alternate_state = False  # Alternates between hold/release
            stability_start_time = None  # Time when first bar detected
            stability_warmup_time = 0.2  # 200ms warmup period before checking movement
            stability_movement_frames = 0  # Track consecutive frames with movement

            # Teleport detection variables - prevent sudden jumps unless consistent
            # Use percentage-based threshold: if line moves > 50% of screen width, it's likely detection error
            # At 1032px width, 50% = ~516px, which catches major detection errors while allowing natural movement
            TELEPORT_THRESHOLD_PERCENT = 0.50  # 50% of fish area width
            TELEPORT_THRESHOLD = int(width * TELEPORT_THRESHOLD_PERCENT)  # Convert to pixels
            TELEPORT_CONFIRM_TIME = 0.15  # Time in seconds to confirm a teleport (150ms)
            
            # Tracking for potential teleports
            potential_teleport_target_left = None
            potential_teleport_target_right = None
            potential_teleport_left_bar = None
            potential_teleport_right_bar = None
            teleport_first_detected_time = None

            # PD control variables (same as Color mode)
            last_error = None
            last_target_x = None
            is_holding_click = False
            
            # Edge transition tracking (for bar_ratio edge detection)
            was_at_edge = False  # Were we at edge last scan?
            edge_transition_time = None  # When did we leave edge?
            edge_transition_action = None  # What action to do during transition (hold/release)

            # Mouse event constants
            MOUSEEVENTF_LEFTDOWN = 0x0002
            MOUSEEVENTF_LEFTUP = 0x0004

            # Calculate scan delay
            base_scan_delay = 1.0 / scan_fps if scan_fps > 0 else 0.005

            print(f"🔄 Starting line tracking loop...")
            print(f"🔍 DEBUG: Start/Stop state = {self.global_hotkey_states['Start/Stop']}, is_quitting = {self.is_quitting}")

            frame_counter = 0
            while self.global_hotkey_states["Start/Stop"] and not self.is_quitting:
                current_time = time.time()
                frame_counter += 1
                
                # Debug: Check loop state every frame for first 5 frames
                if frame_counter <= 5:
                    print(f"🎞️ Frame {frame_counter}: Start/Stop={self.global_hotkey_states['Start/Stop']}, is_quitting={self.is_quitting}")


                # Capture fish area
                try:
                    with mss.mss() as sct:
                        monitor = {"top": y1, "left": x1, "width": width, "height": height}
                        screenshot = sct.grab(monitor)
                        frame = cv2.cvtColor(np.asarray(screenshot), cv2.COLOR_BGRA2BGR)
                except Exception as e:
                    print(f"❌ Capture error: {e}")
                    time.sleep(base_scan_delay)
                    continue

                # Detect lines in frame (always detect all lines, sanity checks prevent invalid bar positions)
                line_coordinates = self._detect_lines_in_frame(frame)

                # Debug output - show detected lines (every 100th frame to reduce overhead)
                if frame_counter % 100 == 0:
                    print(f"🔍 DEBUG: Detected {len(line_coordinates)} lines at {line_coordinates if len(line_coordinates) <= 6 else f'{line_coordinates[:6]}...'}")

                # Check exit condition based on line count
                should_check_exit = False
                if len(line_coordinates) in [2, 3, 4]:
                    # Valid line count - check every 500ms
                    if current_time - last_exit_check_time >= exit_check_interval:
                        should_check_exit = True
                        last_exit_check_time = current_time
                else:
                    # Invalid line count - check once every alternate
                    invalid_line_alternate_counter += 1
                    if invalid_line_alternate_counter % 2 == 0:
                        should_check_exit = True
                
                if should_check_exit:
                    # Check bottom left corner for green color
                    exit_result = self._check_fish_exit_condition()
                    if exit_result == "fish_stage":
                        # Green color found - fish stage has ended
                        print(f"🐟 Fish stage exit condition met - green color detected in bottom left")
                        break

                # Process lines - ACCEPT ANY NUMBER OF LINES (minimum 2 for target pair)
                if len(line_coordinates) >= 2:
                    # Reset fish lost timer
                    fish_lost_timer = 0.0

                    if is_initial_run or initial_target_gap is None:
                        # Initial run - detect target and bars
                        distance_coords = sorted([(abs(coord - image_center_x), coord) for coord in line_coordinates], key=lambda x: x[0])
                        target_pair = sorted([distance_coords[0][1], distance_coords[1][1]])
                        target_left_x = target_pair[0]
                        target_right_x = target_pair[1]
                        initial_target_gap = target_right_x - target_left_x

                        # Find bars from remaining lines (nearest to left and right edges)
                        remaining = [x for x in line_coordinates if x != target_left_x and x != target_right_x]
                        if len(remaining) >= 2:
                            # Multiple remaining lines: leftmost is left bar, rightmost is right bar
                            left_bar_x = min(remaining)
                            right_bar_x = max(remaining)
                        elif len(remaining) == 1:
                            # Single remaining line: determine which bar it's closest to
                            single_line = remaining[0]
                            if single_line < target_left_x:
                                # It's the left bar
                                left_bar_x = single_line
                                right_bar_x = width * 0.75  # Reasonable default for first run
                            else:
                                # It's the right bar
                                left_bar_x = width * 0.25  # Reasonable default for first run
                                right_bar_x = single_line
                        else:
                            # Only 2 lines (target only): use reasonable defaults
                            left_bar_x = width * 0.25
                            right_bar_x = width * 0.75

                        last_target_left_x = target_left_x
                        last_target_right_x = target_right_x
                        last_left_bar_x = left_bar_x
                        last_right_bar_x = right_bar_x

                        print(f"📌 Initial: Lines={len(line_coordinates)}, Target=({target_left_x:.0f}, {target_right_x:.0f}), Gap={initial_target_gap:.0f}, Bars=({left_bar_x:.0f}, {right_bar_x:.0f})")
                        is_initial_run = False
                    else:
                        # SUBSEQUENT RUNS: Find best target pair matching initial gap
                        best_gap_diff = float('inf')
                        target_left_x = last_target_left_x
                        target_right_x = last_target_right_x

                        for i in range(len(line_coordinates) - 1):
                            curr_left = line_coordinates[i]
                            curr_right = line_coordinates[i + 1]
                            curr_gap = curr_right - curr_left
                            gap_diff = abs(curr_gap - initial_target_gap)

                            if gap_diff < best_gap_diff:
                                best_gap_diff = gap_diff
                                target_left_x = curr_left
                                target_right_x = curr_right
                        
                        # Validate: if gap > 4x initial, keep old target
                        actual_gap = target_right_x - target_left_x
                        if actual_gap > initial_target_gap * 4:
                            target_left_x = last_target_left_x
                            target_right_x = last_target_right_x
                        
                        # Get remaining lines (not target)
                        remaining = [x for x in line_coordinates if x != target_left_x and x != target_right_x]
                        
                        # Assign bars to nearest lines from remaining
                        if len(remaining) >= 2:
                            # Multiple bars: find nearest to left edge (0) and right edge (width)
                            left_bar_x = min(remaining)  # Leftmost remaining line
                            right_bar_x = max(remaining)  # Rightmost remaining line
                        elif len(remaining) == 1:
                            # Single remaining line: assign to nearest bar position based on target middle
                            single_line = remaining[0]
                            target_middle_x_temp = (target_left_x + target_right_x) / 2.0
                            
                            if single_line < target_middle_x_temp:
                                # Line is left of target - it's the left bar
                                left_bar_x = single_line
                                right_bar_x = last_right_bar_x if last_right_bar_x is not None else width
                            else:
                                # Line is right of target - it's the right bar
                                right_bar_x = single_line
                                left_bar_x = last_left_bar_x if last_left_bar_x is not None else 0
                        else:
                            # Only 2 lines (target only): freeze both bars at last position
                            left_bar_x = last_left_bar_x if last_left_bar_x is not None else width * 0.25
                            right_bar_x = last_right_bar_x if last_right_bar_x is not None else width * 0.75

                    # Calculate positions for overlay and edge detection
                    target_middle_x = (target_left_x + target_right_x) / 2.0
                    bar_middle_x = (left_bar_x + right_bar_x) / 2.0
                    
                    # Calculate edge detection variables
                    current_bar_width = abs(right_bar_x - left_bar_x) if left_bar_x is not None and right_bar_x is not None else 0
                    edge_threshold = current_bar_width * bar_ratio
                    target_at_left_edge = target_middle_x < edge_threshold
                    target_at_right_edge = target_middle_x > (width - edge_threshold)
                    target_at_edge = target_at_left_edge or target_at_right_edge
                    
                    # EDGE MODE OVERRIDE: Fix bars to screen edges
                    if target_at_left_edge:
                        # Target at left edge: force left bar to 0
                        left_bar_x = 0
                        bar_middle_x = (left_bar_x + right_bar_x) / 2.0
                        print(f"⬅️ EDGE OVERRIDE: Left edge detected, left_bar fixed to 0")
                    elif target_at_right_edge:
                        # Target at right edge: force right bar to width
                        right_bar_x = width
                        bar_middle_x = (left_bar_x + right_bar_x) / 2.0
                        print(f"➡️ EDGE OVERRIDE: Right edge detected, right_bar fixed to {width}")
                    
                    # Show visual overlay of detected line elements (after edge override)
                    self._show_line_visualization(
                        frame, target_left_x, target_right_x, left_bar_x, right_bar_x,
                        target_middle_x, bar_middle_x, width, height, x1, y1
                    )
                    
                    # Calculate error (used by all paths)
                    error = target_middle_x - bar_middle_x
                    
                    # Initialize control variables (may be overwritten by PD control)
                    control_signal = 0.0
                    p_term = 0.0
                    d_term = 0.0
                    
                    # THREE-WAY BRANCH: Stability OR Edge OR Normal PD
                    if stability_state:
                        # === STABILITY MODE PATH (once exited, never re-enter) ===
                        current_time = time.time()
                        
                        # Start timer on first bar detection
                        if stability_start_time is None:
                            stability_start_time = current_time
                            print(f"⏱️ STABILITY: Starting 200ms warmup period...")
                        
                        # Check if warmup period has passed
                        elapsed_time = current_time - stability_start_time
                        if elapsed_time < stability_warmup_time:
                            # Still in warmup - just alternate hold/release
                            stability_scan_count += 1
                            if stability_scan_count % 2 == 0:
                                stability_alternate_state = not stability_alternate_state
                            should_hold = stability_alternate_state
                            print(f"⏳ STABILITY #{stability_scan_count}: {'HOLD' if should_hold else 'RELEASE'} (warmup {elapsed_time*1000:.0f}ms/200ms)")
                            # Update error for derivative calculation
                            last_error = error
                            last_target_x = target_middle_x
                        else:
                            # Warmup complete - set initial position if not set yet
                            if stability_initial_target_x is None:
                                stability_initial_target_x = target_middle_x
                                # Use memory bar position for initial value
                                memory_bar_middle_x = (last_left_bar_x + last_right_bar_x) / 2.0 if last_left_bar_x is not None and last_right_bar_x is not None else bar_middle_x
                                stability_initial_bar_x = memory_bar_middle_x
                                print(f"📌 STABILITY: Initial positions set after 200ms warmup - Target: {target_middle_x:.0f}, Bar: {stability_initial_bar_x:.0f}")
                        
                            # Now check for movement (only after warmup complete)
                            if stability_initial_target_x is not None:
                                # Compare using MEMORY positions (which only update in safe zone)
                                stability_threshold = 3 * (width / 517)
                                target_moved = abs(target_middle_x - stability_initial_target_x) >= stability_threshold
                                # Use memory bar position for comparison
                                memory_bar_middle_x = (last_left_bar_x + last_right_bar_x) / 2.0 if last_left_bar_x is not None and last_right_bar_x is not None else bar_middle_x
                                bar_moved = abs(memory_bar_middle_x - stability_initial_bar_x) >= stability_threshold

                                # Require movement to persist for 3 frames to avoid false positives
                                if target_moved or bar_moved:
                                    stability_movement_frames += 1
                                    print(f"🔍 STABILITY: Movement frame {stability_movement_frames}/3 - memory_bar={memory_bar_middle_x:.1f}, initial={stability_initial_bar_x:.1f}, diff={abs(memory_bar_middle_x - stability_initial_bar_x):.1f}")
                                    if stability_movement_frames >= 3:
                                        # Exit stability mode and reset all stability state
                                        stability_state = False
                                        stability_movement_frames = 0  # RESET counter
                                        stability_initial_target_x = None  # RESET initial positions
                                        stability_initial_bar_x = None
                                        print(f"🔄 STABILITY: Movement detected! Target moved: {target_moved}, Bar moved: {bar_moved}")
                                        print(f"⚙️ STABILITY: Switching to normal PD control after {stability_scan_count} scans")
                                else:
                                    # Reset counter if no movement
                                    if stability_movement_frames > 0:
                                        print(f"🔍 STABILITY: Movement RESET (was {stability_movement_frames}) - memory_bar={memory_bar_middle_x:.1f}, initial={stability_initial_bar_x:.1f}")
                                    stability_movement_frames = 0
                                
                                if stability_state:  # Still in stability after movement check
                                    # Stay in stability mode - alternate every 2 scans
                                    stability_scan_count += 1
                                    if stability_scan_count % 2 == 0:
                                        stability_alternate_state = not stability_alternate_state

                                    # Stability sets should_hold
                                    should_hold = stability_alternate_state
                                    
                                    # Update error for derivative calculation even in stability mode
                                    last_error = error
                                    last_target_x = target_middle_x
                        
                        # Update memory in stability mode
                        last_target_left_x = target_left_x
                        last_target_right_x = target_right_x
                        last_left_bar_x = left_bar_x
                        last_right_bar_x = right_bar_x
                    
                    else:
                        # NOT in stability mode - check for edge or normal PD
                        
                        if target_at_edge:
                            # === EDGE PATH: Fix bars + Override control + Update memory ===
                            
                            # Fix bars to screen edges when target enters bar ratio zones
                            if target_at_left_edge:
                                # Target in left zone - fix left bar to 0, right bar stays as detected
                                print(f"📍 Target at LEFT edge - FORCING left_bar to 0, right_bar stays at {right_bar_x:.0f}")
                                left_bar_x = 0
                                should_hold = False
                                print(f"⬅️ EDGE: Left ({target_middle_x:.0f} < {edge_threshold:.0f}) - FORCE RELEASE")
                            elif target_at_right_edge:
                                # Target in right zone - fix right bar to width, left bar stays as detected
                                print(f"📍 Target at RIGHT edge - FORCING right_bar to {width}, left_bar stays at {left_bar_x:.0f}")
                                right_bar_x = width
                                should_hold = True
                                print(f"➡️ EDGE: Right ({target_middle_x:.0f} > {width - edge_threshold:.0f}) - FORCE HOLD")
                            
                            # Recalculate bar_middle_x after edge fixing
                            bar_middle_x = (left_bar_x + right_bar_x) / 2.0
                            
                            # Update memory - at edge, save the edge-fixed positions
                            if last_left_bar_x is None or last_right_bar_x is None:
                                # First detection - initialize even at edge
                                last_target_left_x = target_left_x
                                last_target_right_x = target_right_x
                                last_left_bar_x = left_bar_x
                                last_right_bar_x = right_bar_x
                            # Note: We DON'T update memory at edges to preserve real bar positions
                        
                        else:
                            # === NORMAL PD PATH: PD control + Update memory ===
                            current_time = time.time()
                            
                            # Select control algorithm based on mode
                            if control_mode in ["Normal", "Steady"]:
                                # NORMAL/STEADY MODE: PD control with asymmetric damping
                                # P term - proportional to how far we need to move
                                p_term = kp * error
                            
                                # D term - ASYMMETRIC damping based on situation
                                d_term = 0.0
                                time_delta = current_time - last_scan_time
                                if last_target_x is not None and last_error is not None and time_delta > 0.001:
                                    # Calculate bar velocity (how fast bar is moving)
                                    last_bar_x = last_target_x - last_error
                                    bar_velocity = (bar_middle_x - last_bar_x) / time_delta
                                    
                                    # Determine if we're approaching or chasing
                                    error_magnitude_decreasing = abs(error) < abs(last_error)
                                    
                                    # Check if bar is moving toward target
                                    bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                    
                                    if error_magnitude_decreasing and bar_moving_toward_target:
                                        # APPROACHING TARGET - Strong damping to prevent overshoot (2x instead of 5x)
                                        damping_multiplier = 2.0
                                        d_term = -kd * damping_multiplier * bar_velocity
                                    else:
                                        # CHASING TARGET - Minimal damping to allow fast movement (0.5x instead of 0.2x)
                                        damping_multiplier = 0.5
                                        d_term = -kd * damping_multiplier * bar_velocity
                                
                                # Combined control signal (PD controller output)
                                control_signal = p_term + d_term
                                control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp

                                # DIRECTIONAL DECISION: Convert continuous signal to binary hold/release
                                # Positive = need to move bar right = HOLD
                                # Negative = need to move bar left = RELEASE
                                # D term naturally prevents overshoot by opposing velocity
                                if control_signal > 0:
                                    should_hold = True
                                else:
                                    should_hold = False
                            
                            elif control_mode == "NigGamble":
                                # NIGGAMBLE MODE: (Clone of Normal for now - will be modified)
                                # P term - proportional to how far we need to move
                                p_term = kp * error
                                
                                # D term - ASYMMETRIC damping based on situation
                                d_term = 0.0
                                time_delta = current_time - last_scan_time
                                if last_target_x is not None and last_error is not None and time_delta > 0.001:
                                    # Calculate bar velocity (how fast bar is moving)
                                    last_bar_x = last_target_x - last_error
                                    bar_velocity = (bar_middle_x - last_bar_x) / time_delta
                                    
                                    # Determine if we're approaching or chasing
                                    error_magnitude_decreasing = abs(error) < abs(last_error)
                                    
                                    # Check if bar is moving toward target
                                    bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                    
                                    if error_magnitude_decreasing and bar_moving_toward_target:
                                        # APPROACHING TARGET - Strong damping to prevent overshoot (2x)
                                        damping_multiplier = 2.0
                                        d_term = -kd * damping_multiplier * bar_velocity
                                    else:
                                        # CHASING TARGET - Minimal damping to allow fast movement (0.5x)
                                        damping_multiplier = 0.5
                                        d_term = -kd * damping_multiplier * bar_velocity
                                
                                # Combined control signal (PD controller output)
                                control_signal = p_term + d_term
                                control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp

                                # DIRECTIONAL DECISION: Convert continuous signal to binary hold/release
                                if control_signal > 0:
                                    should_hold = True
                                else:
                                    should_hold = False
                            
                            elif control_mode == "NigGamble":
                                # NIGGAMBLE MODE
                                p_term = kp * error
                                
                                d_term = 0.0
                                time_delta = current_time - last_scan_time
                                if last_target_x is not None and last_error is not None and time_delta > 0.001:
                                    last_bar_x = last_target_x - last_error
                                    bar_velocity = (bar_middle_x - last_bar_x) / time_delta
                                    
                                    error_magnitude_decreasing = abs(error) < abs(last_error)
                                    bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
                                    
                                    if error_magnitude_decreasing and bar_moving_toward_target:
                                        damping_multiplier = 2.0
                                        d_term = -kd * damping_multiplier * bar_velocity
                                    else:
                                        damping_multiplier = 0.5
                                        d_term = -kd * damping_multiplier * bar_velocity
                                
                                control_signal = p_term + d_term
                                control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp
                                
                                if control_signal > 0:
                                    should_hold = True
                                else:
                                    should_hold = False
                            
                            # Update PD state for next iteration
                            last_error = error
                            last_target_x = target_middle_x
                            
                            # Update memory (normal zone - not at edge)
                            last_target_left_x = target_left_x
                            last_target_right_x = target_right_x
                            last_left_bar_x = left_bar_x
                            last_right_bar_x = right_bar_x
                    
                    # Execute mouse control
                    mouse_action_taken = False
                    if should_hold and not is_holding_click:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        is_holding_click = True
                        mouse_action_taken = True
                        if stability_state:
                            print(f"� STABILITY #{stability_scan_count}: HOLD (Target: {target_middle_x:.0f}, Bar: {bar_middle_x:.0f}, Error: {error:.1f})")
                        elif not target_at_edge:
                            print(f"🔒 HOLD [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f} | Bars: L={left_bar_x:.0f}, R={right_bar_x:.0f}")
                    elif not should_hold and is_holding_click:
                        windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        is_holding_click = False
                        mouse_action_taken = True
                        if stability_state:
                            print(f"📊 STABILITY #{stability_scan_count}: RELEASE (Target: {target_middle_x:.0f}, Bar: {bar_middle_x:.0f}, Error: {error:.1f})")
                        elif not target_at_edge:
                            print(f"🔓 RELEASE [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f} | Bars: L={left_bar_x:.0f}, R={right_bar_x:.0f}")
                    
                    if not mouse_action_taken and not stability_state and not target_at_edge:
                        current_state = "HOLDING" if is_holding_click else "RELEASED"
                        print(f"⚡ {current_state} [{control_mode}] - Error: {error:.1f}, Control: {control_signal:.1f}, P: {p_term:.1f}, D: {d_term:.1f} | Bars: L={left_bar_x:.0f}, R={right_bar_x:.0f}, Target: L={target_left_x:.0f}, R={target_right_x:.0f}")

                else:
                    # Less than 2 lines detected (cannot identify target pair)
                    # Increment fish lost timer
                    fish_lost_timer += (current_time - last_scan_time)
                    
                    if fish_lost_timer >= fish_lost_timeout:
                        print(f"⚠️ Insufficient lines ({len(line_coordinates)}) for {fish_lost_timeout}s - fish likely caught or lost")
                        break

                last_scan_time = current_time

                # FPS delay
                time.sleep(base_scan_delay)

            # Loop exited - log reason
            if not self.global_hotkey_states["Start/Stop"]:
                print(f"⚡ Fish stage exited: Start/Stop hotkey toggled OFF")
            elif self.is_quitting:
                print(f"⚡ Fish stage exited: Application quitting")
            
            # Cleanup - ensure mouse is released
            if is_holding_click:
                windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                is_holding_click = False
                print("⚡ Cleanup: Released mouse")
            
            # Close visualization window
            try:
                if hasattr(self, '_debug_overlay') and self._debug_overlay:
                    self._debug_overlay.destroy()
                    self._debug_overlay = None
            except:
                pass

            # Close cast visualization overlays at end of fish stage
            self._cleanup_cast_overlays()

            print("✅ === FISH STAGE ENDED ===")
            return "restart"

        except Exception as e:
            print(f"⚡ Error in line fish stage: {e}")
            import traceback
            traceback.print_exc()

            # Cleanup on error - ensure mouse is released
            try:
                if is_holding_click:
                    from ctypes import windll
                    windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # MOUSEEVENTF_LEFTUP
                    print("⚡ Error cleanup: Released mouse")
            except:
                pass

            return "restart"

    def _destroy_arrow(self, arrow_window):
        """Safely destroy an arrow window."""
        try:
            if arrow_window and arrow_window.winfo_exists():
                arrow_window.destroy()
        except:
            pass

    def _clear_color_arrows(self):
        """Clear all color arrow displays."""
        try:
            # Clear old arrow system
            if hasattr(self, '_color_arrows'):
                print(f"⚡ ARROWS: Clearing {len(self._color_arrows)} old arrow windows")
                for arrow in self._color_arrows:
                    try:
                        arrow.destroy()
                    except:
                        pass
                self._color_arrows = []
            
            # Clear new fish arrow system
            if hasattr(self, '_fish_arrows'):
                print(f"⚡ ARROWS: Clearing {len(self._fish_arrows)} fish arrow windows")
                for arrow_info in self._fish_arrows.values():
                    try:
                        arrow_info['window'].destroy()
                    except:
                        pass
                self._fish_arrows = {}
            
        except Exception as e:
            print(f"⚡ Error clearing arrows: {e}")

    def _send_key_press(self, key_char):
        """
        Send a keyboard key press using win32api.
        Handles any single character or special key names like 'Enter'.
        """
        import win32api
        
        # Handle special key names
        if key_char.lower() == "enter":
            vk_code = win32con.VK_RETURN
            scan_code = 0
        elif len(key_char) == 1:
            # Use VkKeyScanA to get the correct virtual key and shift state for any character
            result = win32api.VkKeyScan(key_char)
            if result == -1:
                print(f"    ⚡ Cannot map key: {key_char}")
                return
            
            vk_code = result & 0xFF  # Lower byte is the virtual key code
            shift_state = (result >> 8) & 0xFF  # Higher byte contains shift state
            
            # Handle shift state if needed
            need_shift = (shift_state & 1) != 0
            need_ctrl = (shift_state & 2) != 0
            need_alt = (shift_state & 4) != 0
            
            # Press modifier keys if needed
            if need_shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, 0, 0)
            if need_ctrl:
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
            if need_alt:
                win32api.keybd_event(win32con.VK_MENU, 0, 0, 0)
            
            # Press the main key
            scan_code = win32api.MapVirtualKey(vk_code, 0)
            win32api.keybd_event(vk_code, scan_code, 0, 0)  # Key down
            win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)  # Key up
            
            # Release modifier keys if needed
            if need_alt:
                win32api.keybd_event(win32con.VK_MENU, 0, win32con.KEYEVENTF_KEYUP, 0)
            if need_ctrl:
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
            if need_shift:
                win32api.keybd_event(win32con.VK_SHIFT, 0, win32con.KEYEVENTF_KEYUP, 0)
            
            return
        else:
            print(f"    ⚡ Unsupported key format: {key_char}")
            return

        # For special keys like Enter that don't need VkKeyScan
        scan_code = win32api.MapVirtualKey(vk_code, 0)
        win32api.keybd_event(vk_code, scan_code, 0, 0)  # Key down
        time.sleep(0.01)  # Small delay
        win32api.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)  # Key up

    def _click_at_position(self, x, y, click_count):
        """
        Move mouse to position and click using windll.
        Performs click_count clicks as fast as possible (no artificial delay).
        Moves cursor down by 1 pixel relatively to register with Roblox.
        """
        # Move mouse to position
        windll.user32.SetCursorPos(x, y)

        # Move cursor down by 1 pixel relatively to register with Roblox
        windll.user32.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)

        # Perform clicks with 5ms delay between multiple clicks
        for i in range(click_count):
            windll.user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

            # Add 5ms delay between clicks (but not after the last click)
            if i < click_count - 1:
                time.sleep(0.03)  # 30 milliseconds

    def _execute_fish_block(self):
        """
        Fish block - handles fish detection and response.
        Note: Actual fish detection is handled by _execute_fish_stage()
        """
        print("  Fish block executed (fish detection handled by fish stage)")
        # Fish detection logic is implemented in _execute_fish_stage()

    def quit_app(self):
        """Triggers the application quit process."""
        if self.is_quitting:
            return
            
        self.is_quitting = True
        print("Exit hotkey triggered - Quitting application...")
        
        # Clean up any active cameras before exit
        if hasattr(self, '_active_cameras'):
            print(f"🧹 Cleaning up {len(self._active_cameras)} active camera(s)...")
            for camera in self._active_cameras[:]:  # Use slice to avoid modification during iteration
                try:
                    camera.release()
                    self._active_cameras.remove(camera)
                except Exception as e:
                    print(f"⚠️ Camera cleanup error: {e}")
            print("✅ Camera cleanup complete")
        
        # Save config before quitting
        print("⚡ Saving configuration...")
        self._save_config()
        
        # Stop bot immediately if running
        self.global_hotkey_states["Start/Stop"] = False
        
        # Schedule the cleanup and destruction in the main Tkinter loop
        # Use shorter delay for faster exit
        self.after(10, self._perform_quit)
    # AI_SYSTEM_END: FISH_SYSTEM

    # AI_SYSTEM_START: CONFIG_SYSTEM
    def _save_config(self):  # AI_TARGET: CONFIG_SAVE
        try:
            # Clean up orphaned rod settings before saving
            self._cleanup_orphaned_rod_settings()
            
            # Collect ALL data that needs to be saved
            config_data = {
                # All settings
                "settings": self.settings,
                
                # Global GUI settings
                "global_gui_settings": self.global_gui_settings,
                
                # Hotkey configuration
                "hotkeys": {name: data['key'] for name, data in self.hotkey_manager.hotkeys.items()},
                
                # Area coordinates
                "fish_box": self.fish_box,
                "shake_box": self.shake_box,
                
                # Bottom button states (block toggles)
                "bottom_button_states": self.bottom_button_states,
                
                # Comet minigame state
                "rocks_slashed": self.rocks_slashed,
                "minigame_state": {
                    "fisch_gui_enabled": self.fisch_gui_enabled_var.get(),
                    "minigame_enabled": self.minigame_enabled_var.get(),
                    "auto_slash_enabled": self.auto_slash_var.get()
                },
                
                # Shop system (upgrades, comets, rebirths)
                "shop_data": {
                    "comets": self.comets,
                    "total_comets_earned": self.total_comets_earned,
                    "rebirths": self.rebirths,
                    "rebirth_count": self.rebirth_count,
                    "rebirth_multiplier": self.rebirth_multiplier,
                    "upgrade_levels": self.upgrade_levels,
                    "max_upgrade_levels": self.max_upgrade_levels,
                    "playtime_tracking": self.playtime_tracking,
                    "stats": self.stats  # FIXED: Save stats including luck procs
                }
            }
            
            # Convert to JSON
            json_str = json.dumps(config_data, indent=2)
            
            # Encode to base64
            encoded = base64.b64encode(json_str.encode()).decode()
            
            # Multi-layer fallback save system - tries multiple locations until one works
            save_locations = [
                self.CONFIG_FILE,  # Primary location (exe dir or script dir)
                os.path.join(os.getenv('APPDATA'), 'IRUS_COMET', 'Config.txt'),  # AppData
                os.path.join(os.path.expanduser('~'), 'Documents', 'IRUS_COMET', 'Config.txt'),  # Documents
                os.path.join(os.getenv('TEMP'), 'IRUS_COMET', 'Config.txt'),  # Temp folder as last resort
            ]
            
            saved_successfully = False
            
            for attempt_path in save_locations:
                try:
                    # Ensure directory exists
                    os.makedirs(os.path.dirname(attempt_path), exist_ok=True)
                    
                    # Direct write with proper error handling (no temp file to avoid Windows issues)
                    # Use exclusive creation first to avoid overwrite issues
                    try:
                        # Try to write directly - most reliable on Windows
                        with open(attempt_path, 'w') as f:
                            f.write(encoded)
                            f.flush()  # Force write to disk
                            os.fsync(f.fileno())  # Ensure written to physical disk
                        
                        # Verify it worked by reading back
                        with open(attempt_path, 'r') as verify_f:
                            if verify_f.read() == encoded:
                                # Success!
                                if self.CONFIG_FILE != attempt_path:
                                    self.CONFIG_FILE = attempt_path
                                saved_successfully = True
                                break
                    except (PermissionError, OSError):
                        # File might be locked, try next location
                        continue
                            
                except (PermissionError, OSError, IOError):
                    # This location failed, try next one
                    continue
                except Exception:
                    # Unexpected error, try next location
                    continue
            
            if not saved_successfully:
                # All locations failed - try one last emergency save to desktop
                try:
                    desktop = os.path.join(os.path.expanduser('~'), 'Desktop')
                    emergency_path = os.path.join(desktop, 'IRUS_COMET_Config.txt')
                    with open(emergency_path, 'w') as f:
                        f.write(encoded)
                    self.CONFIG_FILE = emergency_path
                except:
                    # Even desktop failed - settings won't persist this session
                    pass
            
        except Exception:
            # Silent failure - don't crash the app
            pass
    
    def _cleanup_orphaned_rod_settings(self):
        """Remove settings for rods that no longer exist"""
        try:
            current_rod_types = self.settings.get("rod_types", [])
            keys_to_remove = []
            
            # Find all rod-specific setting keys
            for key in list(self.settings.keys()):
                # Check if key ends with _RodName pattern
                for potential_rod in ["_" + rod for rod in current_rod_types]:
                    if key.endswith(potential_rod):
                        break  # This rod exists, keep its settings
                else:
                    # Check if this is a rod-specific setting (ends with _SomeName)
                    if any(key.endswith(f"_{suffix}") for suffix in [
                        "color", "tolerance", "threshold", "delay"
                    ]):
                        # Extract potential rod name
                        for setting_type in ["fish_target_line_color", "fish_arrow_color",
                                            "fish_left_bar_color", "fish_right_bar_color",
                                            "fish_target_line_tolerance", "fish_arrow_tolerance",
                                            "fish_left_bar_tolerance", "fish_right_bar_tolerance"]:
                            if key.startswith(setting_type + "_"):
                                potential_rod_name = key[len(setting_type) + 1:]
                                if potential_rod_name and potential_rod_name not in current_rod_types:
                                    keys_to_remove.append(key)
                                break
            
            # Remove orphaned settings
            for key in keys_to_remove:
                del self.settings[key]
                
            if keys_to_remove:
                print(f"  ⚡ Cleaned up {len(keys_to_remove)} orphaned rod settings")
                
        except Exception as e:
            print(f"  ⚡ Error cleaning orphaned rod settings: {e}")
    
    def _load_config(self):  # AI_TARGET: CONFIG_LOAD
        try:
            # Try to find config in multiple locations
            search_locations = [
                self.CONFIG_FILE,  # Primary location
                os.path.join(os.getenv('APPDATA'), 'IRUS_COMET', 'Config.txt'),  # AppData
                os.path.join(os.path.expanduser('~'), 'Documents', 'IRUS_COMET', 'Config.txt'),  # Documents
                os.path.join(os.getenv('TEMP'), 'IRUS_COMET', 'Config.txt'),  # Temp
                os.path.join(os.path.expanduser('~'), 'Desktop', 'IRUS_COMET_Config.txt'),  # Desktop emergency
            ]
            
            config_found = False
            encoded = None
            
            for location in search_locations:
                if os.path.exists(location):
                    try:
                        with open(location, 'r') as f:
                            encoded = f.read().strip()
                        if encoded:
                            # Update config path for future saves
                            self.CONFIG_FILE = location
                            config_found = True
                            break
                    except:
                        continue
            
            if not config_found or not encoded:
                return
                
            # Decode from base64
            try:
                decoded = base64.b64decode(encoded.encode()).decode()
            except Exception:
                self._create_backup_config()
                return
            
            # Parse JSON with validation
            try:
                config_data = json.loads(decoded)
            except json.JSONDecodeError:
                self._create_backup_config()
                return
            
            # Validate config structure
            if not isinstance(config_data, dict):
                return
            
            # Apply settings with validation
            if "settings" in config_data and isinstance(config_data["settings"], dict):
                self._validate_and_update_settings(config_data["settings"])
            
            if "global_gui_settings" in config_data:
                self.global_gui_settings.update(config_data["global_gui_settings"])
            
            # Load hotkey configuration
            if "hotkeys" in config_data:
                saved_hotkeys = config_data["hotkeys"]
                for option_name, key in saved_hotkeys.items():
                    if option_name in self.hotkey_manager.hotkeys:
                        # Update the hotkey and rebind it
                        self.hotkey_manager.update_hotkey(option_name, key)
                print(f"  ⌨️ Loaded hotkey configuration: {saved_hotkeys}")
            
            if "fish_box" in config_data:
                self.fish_box = config_data["fish_box"]
            
            if "shake_box" in config_data:
                self.shake_box = config_data["shake_box"]
            
            if "bottom_button_states" in config_data:
                self.bottom_button_states.update(config_data["bottom_button_states"])
            
            if "rocks_slashed" in config_data:
                self.rocks_slashed = config_data["rocks_slashed"]
            
            if "minigame_state" in config_data:
                ms = config_data["minigame_state"]
                # Safely set BooleanVars if they exist
                if hasattr(self, 'fisch_gui_enabled_var') and self.fisch_gui_enabled_var:
                    self.fisch_gui_enabled_var.set(ms.get("fisch_gui_enabled", True))
                if hasattr(self, 'minigame_enabled_var') and self.minigame_enabled_var:
                    self.minigame_enabled_var.set(ms.get("minigame_enabled", False))
                if hasattr(self, 'auto_slash_var') and self.auto_slash_var:
                    self.auto_slash_var.set(ms.get("auto_slash_enabled", False))
            
            if "shop_data" in config_data:
                shop = config_data["shop_data"]
                # Validate and clamp numeric values to prevent crashes
                self.comets = max(0.0, float(shop.get("comets", 0.0)))
                self.total_comets_earned = max(0.0, float(shop.get("total_comets_earned", 0.0)))
                self.rebirths = max(0, int(shop.get("rebirths", 0)))
                self.rebirth_count = max(0, int(shop.get("rebirth_count", 0)))
                self.rebirth_multiplier = max(1.0, float(shop.get("rebirth_multiplier", 1.0)))
                
                # Sync rebirth variables (use the higher value if they differ)
                if self.rebirth_count != self.rebirths:
                    sync_value = max(self.rebirth_count, self.rebirths)
                    self.rebirth_count = sync_value
                    self.rebirths = sync_value
                    print(f"🔄 Synchronized rebirth count to {sync_value}")
                
                # Validate upgrade levels (ensure all values are non-negative integers)
                if "upgrade_levels" in shop:
                    for key, value in shop["upgrade_levels"].items():
                        try:
                            validated_value = max(0, int(value))
                            self.upgrade_levels[key] = validated_value
                        except (ValueError, TypeError):
                            print(f"⚠️ Invalid upgrade level for {key}: {value}, resetting to 0")
                            self.upgrade_levels[key] = 0
                
                # Validate max upgrade levels
                if "max_upgrade_levels" in shop:
                    for key, value in shop["max_upgrade_levels"].items():
                        try:
                            validated_value = max(1, int(value))
                            self.max_upgrade_levels[key] = validated_value
                        except (ValueError, TypeError):
                            print(f"⚠️ Invalid max upgrade level for {key}: {value}, using default")
                
                if "playtime_tracking" in shop:
                    self.playtime_tracking.update(shop["playtime_tracking"])
                
                # FIXED: Load stats including luck procs to prevent loss
                if "stats" in shop:
                    # Validate and load stats (preserve existing stats if invalid)
                    for key, value in shop["stats"].items():
                        try:
                            if isinstance(value, (int, float)):
                                self.stats[key] = max(0, value)  # Ensure non-negative
                            else:
                                self.stats[key] = value  # Keep strings/other types as-is
                        except (ValueError, TypeError):
                            print(f"⚠️ Invalid stat value for {key}: {value}, keeping current value")
                    print(f"⚡ Loaded {len(shop['stats'])} statistics")
                
                # CRITICAL: Recalculate all upgrade effects after loading
                # This ensures upgrades actually apply when launching the app
                self._recalculate_all_upgrades()
                print(f"⚡ Recalculated {len(self.upgrade_levels)} upgrade effects")
            
            print(f"✅ Config loaded successfully from {self.CONFIG_FILE}")
            print(f"⚡ Loaded {len(self.settings)} settings, {self.rebirths} rebirths (count: {self.rebirth_count}, multiplier: {self.rebirth_multiplier:.1f}x), {self.comets:.2f} comets")
            
            # Apply visual states to match loaded checkbox values
            # Schedule after a small delay to ensure canvas is fully ready
            self.after(50, self._apply_loaded_visual_states)
            
        except Exception as e:
            print(f"❌ Error loading config: {e}")
            import traceback
            traceback.print_exc()
    
    def _apply_loaded_visual_states(self):
        """Apply visual states to match loaded configuration values."""
        try:
            # Apply Fisch GUI visual state
            if hasattr(self, 'fisch_gui_enabled_var'):
                fisch_enabled = self.fisch_gui_enabled_var.get()
                self._toggle_fisch_gui_elements(fisch_enabled)
                print(f"🎨 Applied Fisch GUI state: {'enabled' if fisch_enabled else 'disabled'}")
            
            # Apply Comet Minigame visual state  
            if hasattr(self, 'minigame_enabled_var'):
                minigame_enabled = self.minigame_enabled_var.get()
                self._toggle_minigame_elements(minigame_enabled)
                print(f"🎨 Applied Comet Minigame state: {'enabled' if minigame_enabled else 'disabled'}")
                
            # Apply Auto Collect visual state
            if hasattr(self, 'auto_slash_var'):
                auto_collect_enabled = self.auto_slash_var.get()
                # The auto collect doesn't have a separate toggle function, but we can ensure trail state
                if auto_collect_enabled:
                    # Initialize trail head position if auto collect is enabled
                    if hasattr(self, 'canvas'):
                        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
                        if c_w > 0 and c_h > 0:
                            self.auto_trail_head_x = c_w // 2
                            self.auto_trail_head_y = c_h // 2
                print(f"🎨 Applied Auto Collect state: {'enabled' if auto_collect_enabled else 'disabled'}")
            
            # Apply tab colors based on enabled/disabled states
            if hasattr(self, 'tab_items') and hasattr(self, 'bottom_button_states'):
                self._update_all_tab_colors()
                print("🎨 Applied tab colors based on enabled/disabled states")
            
            # Apply bottom button colors based on enabled/disabled states
            if hasattr(self, 'bottom_buttons') and hasattr(self, 'bottom_button_states'):
                self._update_bottom_button_colors()
                print("🎨 Applied bottom button colors based on enabled/disabled states")
            
            # Apply flow box colors based on enabled/disabled states
            if hasattr(self, 'fish_rect') and hasattr(self, 'shake_rect') and hasattr(self, 'bottom_button_states'):
                # Reset color cache to force update when loading configuration
                if hasattr(self, '_current_fish_color'):
                    delattr(self, '_current_fish_color')
                if hasattr(self, '_current_shake_color'):
                    delattr(self, '_current_shake_color')
                self._update_flow_box_colors()
                print("🎨 Applied flow box colors based on enabled/disabled states")
                
        except Exception as e:
            print(f"⚠️ Error applying visual states: {e}")
            print("⚡ Using default settings")
    
    def _validate_and_update_settings(self, loaded_settings):
        """Validate and apply settings with range checking"""
        validation_rules = {
            # Timing settings (0.0 to 10.0 seconds)
            "cast_delay1": (0.0, 10.0), "cast_delay2": (0.0, 10.0), "cast_delay3": (0.0, 10.0),
            "perfect_delay1": (0.0, 10.0), "perfect_delay2": (0.0, 10.0), "perfect_delay3": (0.0, 10.0),
            "perfect_delay4": (0.0, 10.0), "perfect_delay5": (0.0, 10.0), "perfect_delay6": (0.0, 10.0),
            "perfect_delay7": (0.0, 10.0), "perfect_delay8": (0.0, 10.0), "perfect_delay9": (0.0, 10.0),
            "perfect_delay10": (0.0, 10.0),
            
            # Zoom and look settings (1 to 50)
            "zoom_out": (1, 50), "zoom_in": (1, 50), "final_zoom_in": (1, 50),
            "look_down": (1, 5000), "look_up": (1, 5000), "final_look_up": (1, 5000),
            
            # Tolerance settings (0 to 255)
            "perfect_cast_green_color_tolerance": (0, 255), "perfect_cast_white_color_tolerance": (0, 255),
            "shake_color_tolerance": (0, 255), "nav_color_tolerance": (0, 255),
            "fish_target_line_tolerance": (0, 255), "fish_left_bar_tolerance": (0, 255), 
            "fish_right_bar_tolerance": (0, 255),
            
            # FPS settings (1 to 10000)
            "perfect_cast_scan_fps": (1, 10000), "shake_scan_fps": (1, 10000), 
            "nav_scan_fps": (1, 10000), "fish_scan_fps": (1, 10000), "fish_line_scan_fps": (1, 10000),
            
            # Percentage settings (1 to 100)
            "perfect_cast_release_percentage": (1, 100),
            "fish_bar_ratio_from_side": (0.1, 0.9), "fish_line_bar_ratio": (0.1, 0.9),
            "fish_line_min_density": (0.1, 1.0),
            
            # Click count (1 to 10)
            "shake_click_count": (1, 10), "circle_click_count": (1, 10),
            
            # Timeout settings (0.1 to 30.0 seconds) 
            "perfect_cast_fail_scan_timeout": (0.1, 30.0), "shake_duplicate_timeout": (0.1, 30.0),
            "shake_fail_cast_timeout": (0.1, 30.0), "nav_fail_cast_timeout": (0.1, 30.0),
            "circle_duplicate_timeout": (0.1, 30.0), "circle_fail_cast_timeout": (0.1, 30.0),
            "fish_lost_timeout": (0.1, 30.0), "fish_line_lost_timeout": (0.1, 30.0),
        }
        
        invalid_count = 0
        for key, value in loaded_settings.items():
            try:
                # Check if this setting has validation rules
                if key in validation_rules:
                    min_val, max_val = validation_rules[key]
                    if isinstance(value, (int, float)):
                        if min_val <= value <= max_val:
                            self.settings[key] = value
                        else:
                            print(f"  ⚠️ Value out of range for {key}: {value} (expected {min_val}-{max_val})")
                            invalid_count += 1
                    else:
                        print(f"  ⚠️ Invalid type for {key}: {type(value)} (expected number)")
                        invalid_count += 1
                else:
                    # No validation rule, accept as-is (for string settings, bools, etc.)
                    self.settings[key] = value
            except Exception as e:
                print(f"  ⚠️ Error validating setting {key}: {e}")
                invalid_count += 1
        
        if invalid_count > 0:
            print(f"  ⚡ Found {invalid_count} invalid settings, using defaults for those")
    
    def _create_backup_config(self):
        """Create a backup of corrupted config and reset to defaults"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                backup_path = f"{self.CONFIG_FILE}.backup.{int(time.time())}"
                import shutil
                shutil.copy2(self.CONFIG_FILE, backup_path)
                print(f"  💾 Corrupted config backed up to: {backup_path}")
            
            print("  🔧 Resetting to default configuration...")
            # The settings will remain at their default values
            
        except Exception as e:
            print(f"  ⚠️ Warning: Could not create config backup: {e}")

    def _initialize_bot_state(self):
        """Initialize/reset all bot state variables when starting."""
        print("⚡ Initializing bot state variables...")
        
        # Reset mouse state
        try:
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            windll.user32.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            print("  ✅ Released all mouse buttons")
        except Exception as e:
            print(f"  ⚡ Error releasing mouse: {e}")
        
        # Reload settings to ensure latest values are used
        print("  ⚡ Reloading current settings...")
        # Settings are already in self.settings, just log confirmation
        fish_track_style = self.settings.get("fish_track_style", "Color")
        shake_style = self.settings.get("shake_style", "Pixel")
        print(f"  ⚡ Current mode: Shake={shake_style}, Fish={fish_track_style}")
        
        # Initialize fish stage variables
        self._last_bar_left_x = None
        self._last_bar_right_x = None
        
        # CRITICAL: Force cleanup ALL dxcam instances globally
        # This ensures no leftover cameras from previous runs
        if DXCAM_AVAILABLE:
            try:
                import dxcam
                # Delete all existing dxcam devices to force fresh start
                if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                    dxcam._device_info.clear()
                    print("  ✅ Cleared global dxcam device cache")
                elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                    dxcam.device_info.clear()
                    print("  ✅ Cleared global dxcam device cache")
                else:
                    print("  ⚡ DXCam device cache not accessible (may not exist)")
            except Exception as e:
                print(f"  ⚡ Could not clear dxcam cache: {e}")
        
        # Clear any existing camera references in our tracking
        if hasattr(self, '_active_cameras'):
            camera_count = len(self._active_cameras)
            for camera in self._active_cameras:
                try:
                    if camera is not None:
                        camera.release()
                except:
                    pass
            self._active_cameras.clear()
            if camera_count > 0:
                print(f"  ✅ Released {camera_count} tracked camera(s)")
        else:
            self._active_cameras = []
        
        # Close any visualization windows
        try:
            if hasattr(self, '_debug_overlay') and self._debug_overlay:
                self._debug_overlay.destroy()
                self._debug_overlay = None
                print("  ✅ Closed debug overlay")
        except:
            pass
        
        print("✅ Bot state initialized successfully")
    
    def _start_playtime_tracking(self):
        """Start tracking playtime for statistics."""
        import time
        self._session_start_time = time.time()
        self._schedule_playtime_update()
        
    def _schedule_playtime_update(self):
        """Schedule periodic playtime updates every minute."""
        import time
        current_time = time.time()
        
        # Update total playtime
        if hasattr(self, '_last_playtime_update'):
            elapsed = current_time - self._last_playtime_update
            self.stats['total_playtime_seconds'] = self.stats.get('total_playtime_seconds', 0) + elapsed
        
        self._last_playtime_update = current_time
        
        # Schedule next update in 60 seconds
        self.after(60000, self._schedule_playtime_update)
    
    # AI_SYSTEM_END: CONFIG_SYSTEM

    def _cleanup_bot_resources(self):  # AI_TARGET: RESOURCE_CLEANUP
        """Clean up all bot resources when stopping."""
        print("⚡ Cleaning up bot resources...")
        
        # Release mouse if held (both left and right buttons for safety)
        try:
            windll.user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            windll.user32.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            print("  ✅ Released mouse buttons")
        except Exception as e:
            print(f"  ⚡ Error releasing mouse: {e}")
        
        # Clean up any active camera instances
        if hasattr(self, '_active_cameras'):
            camera_count = len(self._active_cameras)
            for camera in self._active_cameras:
                try:
                    if camera is not None:
                        camera.release()
                except Exception as e:
                    print(f"  ⚡ Error releasing camera: {e}")
            self._active_cameras.clear()
            if camera_count > 0:
                print(f"  ✅ Released {camera_count} camera instance(s)")
        
        # CRITICAL: Force global dxcam cleanup
        if DXCAM_AVAILABLE:
            try:
                import dxcam
                # Clear device cache
                if hasattr(dxcam, '_device_info') and hasattr(dxcam._device_info, 'clear'):
                    dxcam._device_info.clear()
                    print("  ✅ Cleared dxcam device cache")
                elif hasattr(dxcam, 'device_info') and isinstance(dxcam.device_info, dict):
                    dxcam.device_info.clear()
                    print("  ✅ Cleared dxcam device cache")
                # Small delay to let system clean up
                time.sleep(0.1)
            except Exception as e:
                print(f"  ⚡ Could not clear dxcam cache: {e}")
        
        # Reset fish stage variables
        self._last_bar_left_x = None
        self._last_bar_right_x = None
        
        # Close any debug/visualization windows
        try:
            if hasattr(self, '_debug_overlay') and self._debug_overlay:
                self._debug_overlay.destroy()
                self._debug_overlay = None
                print("  ✅ Closed debug overlay")
        except:
            pass
        
        print("✅ Bot resources cleaned up successfully")

    def _perform_quit(self):
        """Performs the actual cleanup and destruction."""
        # Clean up bot resources first
        self._cleanup_bot_resources()
        
        self.hotkey_manager._unhook_all()
        
        if self.basic_settings_view:
            self.basic_settings_view.destroy()
            self.basic_settings_view = None
        
        if self.support_view:
            self.support_view.destroy()
            self.support_view = None
        
        if self.cast_view:
            self.cast_view.destroy()
            self.cast_view = None
        
        if self.shake_view:
            self.shake_view.destroy()
            self.shake_view = None
        
        if self.fish_view:
            self.fish_view.destroy()
            self.fish_view = None
        
        if self.discord_view:
            self.discord_view.destroy()
            self.discord_view = None

        if self.misc_view:
            self.misc_view.destroy()
            self.misc_view = None
            
        self.destroy()

    # --- Number Formatting Utility ---
    
    def _format_large_number(self, number):
        """
        Format large numbers with proper abbreviations (K, M, B, T, Qa, Qi, Sx, Sp, Oc, No, Dc, etc.)
        """
        if number < 1000:
            return f"{number:.0f}"
        
        # Define the suffixes for large numbers
        suffixes = [
            (1e63, "Vg"),    # Vigintillion
            (1e60, "Nv"),    # Novemdecillion  
            (1e57, "Od"),    # Octodecillion
            (1e54, "Sd"),    # Septendecillion
            (1e51, "Sx"),    # Sexdecillion
            (1e48, "Qi"),    # Quindecillion
            (1e45, "Qa"),    # Quattuordecillion
            (1e42, "Td"),    # Tredecillion
            (1e39, "Dd"),    # Duodecillion
            (1e36, "Ud"),    # Undecillion
            (1e33, "Dc"),    # Decillion
            (1e30, "No"),    # Nonillion
            (1e27, "Oc"),    # Octillion
            (1e24, "Sp"),    # Septillion
            (1e21, "Sx"),    # Sextillion
            (1e18, "Qt"),    # Quintillion
            (1e15, "Qd"),    # Quadrillion
            (1e12, "T"),     # Trillion
            (1e9,  "B"),     # Billion
            (1e6,  "M"),     # Million
            (1e3,  "K"),     # Thousand
        ]
        
        for value, suffix in suffixes:
            if number >= value:
                formatted = number / value
                if formatted >= 100:
                    return f"{formatted:.0f}{suffix}"
                elif formatted >= 10:
                    return f"{formatted:.1f}{suffix}"
                else:
                    return f"{formatted:.2f}{suffix}"
        
        return f"{number:.0f}"

    # --- Star/Trail Color Methods (Updated for Red Stars on Blue) ---

    def _get_star_color(self, step):
        """
        Generates a smooth color based on the fade step, starting from background color
        and fading to target color (White for menu, Red for tab_view).
        """
        max_half_step = self.fade_steps / 2
        
        if step < max_half_step:
            # Fade from background color to target color
            brightness = int(255 * (step / max_half_step))
        else:
            # Fade from target color back to background color
            fade_out_step = step - max_half_step
            brightness = int(255 * (1 - (fade_out_step / max_half_step)))
            
        brightness = max(0, min(255, brightness))
        
        if self.app_state == 'tab_view':
            # Background is blue (#4A90E2), target is red
            # Interpolate between blue background and red
            bg_r, bg_g, bg_b = 0x4A, 0x90, 0xE2  # Blue background
            target_r, target_g, target_b = 255, 0, 0  # Red target
            
            # Linear interpolation
            ratio = brightness / 255.0
            r = int(bg_r + (target_r - bg_r) * ratio)
            g = int(bg_g + (target_g - bg_g) * ratio)
            b = int(bg_b + (target_b - bg_b) * ratio)
            
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Background is black, target is white
            hex_b = f"{brightness:02x}"
            return f"#{hex_b}{hex_b}{hex_b}"

    def _get_trail_color(self, step):
        """
        Generates a smooth color for the trail dot, fading from target color to background.
        """
        if step >= self.trail_lifetime: 
            # Return background color when trail expires
            return "#4A90E2" if self.app_state == 'tab_view' else "#000000"
            
        brightness = int(255 * (1 - (step / self.trail_lifetime)))
        brightness = max(0, min(255, brightness))
        
        if self.app_state == 'tab_view':
            # Background is blue (#4A90E2), trail starts as red and fades to blue
            bg_r, bg_g, bg_b = 0x4A, 0x90, 0xE2  # Blue background
            target_r, target_g, target_b = 255, 0, 0  # Red trail start
            
            # Linear interpolation from red to blue
            ratio = brightness / 255.0
            r = int(bg_r + (target_r - bg_r) * ratio)
            g = int(bg_g + (target_g - bg_g) * ratio)
            b = int(bg_b + (target_b - bg_b) * ratio)
            
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Background is black, trail starts white and fades to black
            hex_b = f"{brightness:02x}"
            return f"#{hex_b}{hex_b}{hex_b}"

    # --- Original/Modified Animation and Menu Methods ---

    def _on_canvas_resize(self, event):
        """Updates dynamic elements when the canvas size changes (optimized for performance)."""
        # Store current dimensions
        self._pending_width = event.width
        self._pending_height = event.height
        
        # Throttle resize events during rapid resizing
        import time
        current_time = time.time()
        if not hasattr(self, '_last_resize_time'):
            self._last_resize_time = 0
        
        # Only do immediate updates if enough time has passed (30 FPS limit)
        if current_time - self._last_resize_time > 0.033:
            self._last_resize_time = current_time
            
            # Update only the most critical elements IMMEDIATELY (live)
            if self.app_state == 'menu' or self.app_state == 'zooming_out':
                self._update_central_label_position()  # IRUS COMET text (most important)
                # Skip other immediate updates to reduce lag
        
        # Cancel pending debounced updates
        if self._resize_after_id:
            self.after_cancel(self._resize_after_id)
        
        # Schedule full updates after 300ms of no resize events (increased from 150ms)
        self._resize_after_id = self.after(300, self._do_canvas_resize_full)
    
    def _do_canvas_resize_full(self):
        """Deferred resize handler for complete updates (optimized)."""
        self._resize_after_id = None
        
        if not hasattr(self, '_pending_width'):
            return
        
        # Do all the updates that were skipped during immediate resize
        if self.app_state == 'menu' or self.app_state == 'zooming_out':
            self._update_menu_positions()  # Rotary wheel
            self._update_bottom_button_positions()  # Bottom buttons
            self._update_flow_arrows()  # Flow chart arrows
        
        canvas_width = self._pending_width
        canvas_height = self._pending_height
        
        # Update star density
        self.max_stars = int(canvas_width * canvas_height * self.star_density_factor)
        self.max_stars = max(self.base_max_stars, self.max_stars)
        
        # Close shop if open during resize to prevent lag
        if hasattr(self, 'shop_frame') and self.shop_frame and hasattr(self, 'is_shop_open') and self.is_shop_open:
            self._hide_shop()
        
        # Update other UI elements
        self._update_rocks_slashed_label_position()
        self._update_auto_slash_checkbox_position()
        self._update_shop_button_position()
        
        if self.app_state == 'tab_view':
            self._update_back_button_position()

    def create_star(self):
        """Generates a new star at a random location on the canvas."""
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 1 or c_h < 1: return

        x, y = random.randint(0, c_w), random.randint(0, c_h)
        
        star_id = self.canvas.create_oval(
            x - self.star_size/2, y - self.star_size/2, x + self.star_size/2, y + self.star_size/2,
            fill=self._get_star_color(0), outline=""
        )
        self.canvas.tag_lower(star_id, "all") 
        self.stars.append({'id': star_id, 'step': 0})

    def animate_stars(self):
        """Star animation loop."""
        # Performance optimization: Check if more than 3 comets on screen
        current_comet_count = len(self.active_rocks) if hasattr(self, 'active_rocks') else 0
        performance_mode_needed = current_comet_count > 3
        
        # Update performance mode flag for logging
        if performance_mode_needed != self.performance_mode_active:
            self.performance_mode_active = performance_mode_needed
            if performance_mode_needed:
                print(f"⚡ Performance mode: Pausing star animations ({current_comet_count} comets on screen)")
            else:
                print(f"✨ Performance mode: Resuming star animations ({current_comet_count} comets on screen)")
        
        # If performance mode is active, fade out existing stars but don't create new ones
        if performance_mode_needed:
            if len(self.stars) > 0:
                stars_to_keep = []
                for star in self.stars:
                    star['step'] += 1
                    if star['step'] >= self.fade_steps:
                        self.canvas.delete(star['id'])
                        continue
                    
                    # Continue fading existing stars
                    self.canvas.itemconfig(star['id'], fill=self._get_star_color(star['step']))
                    stars_to_keep.append(star)
                
                self.stars = stars_to_keep
            
            self.after(self.animation_delay_ms, self.animate_stars)
            return
        
        # If minigame is disabled, fade out existing stars
        if not self.minigame_enabled_var.get():
            # Let existing stars fade out naturally
            if len(self.stars) > 0:
                stars_to_keep = []
                for star in self.stars:
                    star['step'] += 1
                    if star['step'] >= self.fade_steps:
                        self.canvas.delete(star['id'])
                        continue
                    
                    # Continue fading
                    self.canvas.itemconfig(star['id'], fill=self._get_star_color(star['step']))
                    stars_to_keep.append(star)
                
                self.stars = stars_to_keep
            
            self.after(self.animation_delay_ms, self.animate_stars)
            return
        
        # Skip animation if bot is running
        if not self.animations_running:
            self.after(self.animation_delay_ms, self.animate_stars)
            return

        if self.app_state == 'zooming_in' or self.app_state == 'zooming_out' or self.app_state == 'tab_view':
            # Don't create new stars during zoom or in tab view
            self.after(self.animation_delay_ms, self.animate_stars)
            return

        if len(self.stars) < self.max_stars:
            creation_probability = min(1.0, (self.max_stars - len(self.stars)) / (self.fade_steps / 2))
            if random.random() < creation_probability:
                self.create_star()

        stars_to_keep = []
        for star in self.stars:
            star['step'] += 1
            if star['step'] >= self.fade_steps:
                self.canvas.delete(star['id'])
                continue
            
            # Recalculate color based on current app_state (red or white)
            self.canvas.itemconfig(star['id'], fill=self._get_star_color(star['step']))
            stars_to_keep.append(star)

        self.stars = stars_to_keep
        self.after(self.animation_delay_ms, self.animate_stars)
        
    def _on_mouse_move(self, event):
        """Captures mouse movement and creates a trail dot."""
        # Performance optimization: Don't create trail if more than 3 comets on screen
        current_comet_count = len(self.active_rocks) if hasattr(self, 'active_rocks') else 0
        if current_comet_count > 3:
            return
        
        # Only create trail in menu state, not in auto mode, and when minigame is enabled
        if self.app_state == 'menu' and not self.auto_slash_var.get() and self.minigame_enabled_var.get():
            self._create_trail_dot(event.x, event.y)

    def _create_trail_dot(self, x, y):
        """Creates a single dot at the current mouse position."""
        if len(self.trail_elements) >= self.trail_max_elements:
            oldest = self.trail_elements.pop(0)
            self.canvas.delete(oldest['id'])
        
        # Use conditional color for initial dot creation
        dot_id = self.canvas.create_oval(x-3, y-3, x+3, y+3, fill=self._get_trail_color(0), outline="")
        self.canvas.tag_lower(dot_id, "all")
        
        self.trail_elements.append({
            'id': dot_id, 'step': 0, 'center_x': x, 'center_y': y,
        })

    def animate_trail(self):
        """Trail animation loop."""
        # Performance optimization: Check if more than 3 comets on screen
        current_comet_count = len(self.active_rocks) if hasattr(self, 'active_rocks') else 0
        performance_mode_needed = current_comet_count > 3
        
        # If performance mode is active, fade out existing trails but don't create new ones
        if performance_mode_needed:
            if len(self.trail_elements) > 0:
                elements_to_keep = []
                for element in self.trail_elements:
                    element['step'] += 1

                    if element['step'] >= self.trail_lifetime:
                        self.canvas.delete(element['id'])
                        continue
                    
                    # Continue fading existing trails
                    new_color = self._get_trail_color(element['step'])
                    size_ratio = 1 - (element['step'] / self.trail_lifetime)
                    current_size = self.trail_size * size_ratio
                    
                    self.canvas.coords(element['id'], element['center_x'] - current_size/2, element['center_y'] - current_size/2,
                                         element['center_x'] + current_size/2, element['center_y'] + current_size/2)
                    self.canvas.itemconfig(element['id'], fill=new_color)
                    
                    elements_to_keep.append(element)

                self.trail_elements = elements_to_keep
            
            # CRITICAL FIX: Update auto trail even in performance mode!
            self._update_auto_trail()
            
            self.after(self.animation_delay_ms, self.animate_trail)
            return
        
        # If minigame is disabled, fade out existing trail elements
        if not self.minigame_enabled_var.get():
            # Let existing trails fade out naturally
            if len(self.trail_elements) > 0:
                elements_to_keep = []
                for element in self.trail_elements:
                    element['step'] += 1

                    if element['step'] >= self.trail_lifetime:
                        self.canvas.delete(element['id'])
                        continue
                    
                    # Continue fading
                    new_color = self._get_trail_color(element['step'])
                    size_ratio = 1 - (element['step'] / self.trail_lifetime)
                    current_size = self.trail_size * size_ratio
                    
                    self.canvas.coords(element['id'], element['center_x'] - current_size/2, element['center_y'] - current_size/2,
                                         element['center_x'] + current_size/2, element['center_y'] + current_size/2)
                    self.canvas.itemconfig(element['id'], fill=new_color)
                    
                    elements_to_keep.append(element)

                self.trail_elements = elements_to_keep
            
            self.after(self.animation_delay_ms, self.animate_trail)
            return
        
        # Skip animation if bot is running
        if not self.animations_running:
            self.after(self.animation_delay_ms, self.animate_trail)
            return

        # Regular trail animation
        elements_to_keep = []
        for element in self.trail_elements:
            element['step'] += 1

            if element['step'] >= self.trail_lifetime or self.app_state == 'zooming_in':
                self.canvas.delete(element['id'])
                continue
            
            # Recalculate color based on current app_state (red or white)
            new_color = self._get_trail_color(element['step'])
            size_ratio = 1 - (element['step'] / self.trail_lifetime)
            current_size = self.trail_size * size_ratio
            
            self.canvas.coords(element['id'], element['center_x'] - current_size/2, element['center_y'] - current_size/2,
                                 element['center_x'] + current_size/2, element['center_y'] + current_size/2)
            self.canvas.itemconfig(element['id'], fill=new_color)
            
            elements_to_keep.append(element)

        self.trail_elements = elements_to_keep
        
        # Update auto trail if enabled
        self._update_auto_trail()
        
        self.after(self.animation_delay_ms, self.animate_trail)


    def _create_central_label(self):
        """Creates the central 'IRUS COMET' label."""
        if self.central_label_id:
            self.canvas.delete(self.central_label_id)
            self.central_label_id = None
            
        self.central_label_id = self.canvas.create_text(
            0, 0,
            text=self.central_label_text,
            fill="#CCCCFF",
            font=(self.central_font.cget("family"), self.central_font.cget("size"), self.central_font.cget("weight")),
            anchor="center"
        )
        self.canvas.tag_raise(self.central_label_id)
        self._update_central_label_position()

    def _update_central_label_position(self):
        """Repositions the central label."""
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w > 1 and c_h > 1 and self.central_label_id:
            self.canvas.coords(self.central_label_id, c_w / 2, c_h / 2 - self.central_label_offset_y)

    def _create_bottom_buttons(self):
        """Creates toggle buttons at the bottom of the screen."""
        # Clear existing buttons
        for button_data in self.bottom_buttons:
            self.canvas.delete(button_data['rect_id'])
            self.canvas.delete(button_data['text_id'])
        self.bottom_buttons = []
        
        button_width = 80
        button_height = 35
        button_spacing = 20
        
        for i, name in enumerate(self.bottom_button_names):
            # Get the color from tab_colors, use a special color for Start
            if name == "Start":
                button_color = "#FF6B35"  # Orange color for Start button
            else:
                button_color = self.tab_colors.get(name, "#2E2E2E")
            
            # Create rectangle button
            rect_id = self.canvas.create_rectangle(
                0, 0, button_width, button_height,
                fill=button_color, outline="white", width=2,
                tags="bottom_button"
            )
            
            # Create text label
            text_id = self.canvas.create_text(
                0, 0, text=name, fill="white", 
                font=("Inter", 12, "bold"), anchor="center",
                tags="bottom_button_text"
            )
            
            button_data = {
                'rect_id': rect_id,
                'text_id': text_id,
                'name': name,
                'original_color': button_color,
                'index': i
            }
            self.bottom_buttons.append(button_data)
            
            # Bind click events only for toggleable buttons (not Start)
            if name != "Start":
                self.canvas.tag_bind(rect_id, "<Button-1>", lambda e, idx=i: self._on_bottom_button_click(idx))
                self.canvas.tag_bind(text_id, "<Button-1>", lambda e, idx=i: self._on_bottom_button_click(idx))
            
        self._update_bottom_button_positions()
        
        # Update button colors to reflect their current states
        self._update_bottom_button_colors()
        
        # Only update flow box colors if this is the initial creation (not during resize)
        if not hasattr(self, '_buttons_created_once'):
            self._update_flow_box_colors()
            self._buttons_created_once = True

    def _update_bottom_button_positions(self):
        """Updates the positions of bottom toggle buttons."""
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 1 or c_h < 1: return
        
        button_width = 80
        button_height = 35
        button_spacing = 20
        
        total_width = len(self.bottom_button_names) * button_width + (len(self.bottom_button_names) - 1) * button_spacing
        start_x = (c_w - total_width) / 2
        button_y = c_h / 2 + self.bottom_button_offset_y
        
        for i, button_data in enumerate(self.bottom_buttons):
            button_x = start_x + i * (button_width + button_spacing)
            
            # Update rectangle position
            self.canvas.coords(
                button_data['rect_id'],
                button_x, button_y - button_height/2,
                button_x + button_width, button_y + button_height/2
            )
            
            # Update text position
            self.canvas.coords(
                button_data['text_id'],
                button_x + button_width/2, button_y
            )

    def _on_bottom_button_click(self, button_index):
        """Handles bottom button clicks to toggle their state."""
        if self.app_state != 'menu': return
        
        button_data = self.bottom_buttons[button_index]
        button_name = button_data['name']
        
        # Skip if this is the Start button (cosmetic only)
        if button_name == "Start":
            return
        
        # Toggle the state
        current_state = self.bottom_button_states[button_name]
        self.bottom_button_states[button_name] = not current_state
        
        # Update button appearance
        if self.bottom_button_states[button_name]:
            # Active state - original color
            new_color = button_data['original_color']
            print(f"Bottom Button: {button_name} activated")
        else:
            # Toggled off state - gray color
            new_color = "#666666"
            print(f"Bottom Button: {button_name} deactivated")
        
        # Update the button color
        self.canvas.itemconfig(button_data['rect_id'], fill=new_color)
        
        # Update flow box colors when Fish or Shake buttons are toggled
        self._update_flow_box_colors()
        
        # Also update the corresponding tab color in menu
        if self.app_state == 'menu':
            self._update_all_tab_colors()

    def _create_flow_arrows(self):
        """Creates arrows showing the flow between bottom buttons."""
        # Clear existing arrows
        for arrow_id in self.flow_arrows:
            self.canvas.delete(arrow_id)
        self.flow_arrows = []
        
        self._update_flow_arrows()

    def _update_flow_arrows(self):
        """Updates the positions of flow arrows between buttons."""
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 1 or c_h < 1 or len(self.bottom_buttons) < 5: return
        
        # Clear existing arrows
        for arrow_id in self.flow_arrows:
            self.canvas.delete(arrow_id)
        self.flow_arrows = []
        
        button_width = 80
        button_height = 35
        button_spacing = 20
        arrow_color = "#FFFFFF"
        arrow_width = 2
        
        # Calculate button positions (same as in _update_bottom_button_positions)
        total_width = len(self.bottom_button_names) * button_width + (len(self.bottom_button_names) - 1) * button_spacing
        start_x = (c_w - total_width) / 2
        button_y = c_h / 2 + self.bottom_button_offset_y
        
        # Create arrows: Start → Misc → Cast → Shake → Fish
        for i in range(4):  # 4 arrows for 5 buttons
            button_x1 = start_x + i * (button_width + button_spacing)
            button_x2 = start_x + (i + 1) * (button_width + button_spacing)
            
            # Arrow start and end points - positioned at button center level
            arrow_start_x = button_x1 + button_width + 5
            arrow_end_x = button_x2 - 5
            arrow_y = button_y  # Same level as button centers
            
            # Create arrow line with initial state based on Fisch GUI toggle
            initial_state = 'normal' if self.fisch_gui_enabled_var.get() else 'hidden'
            arrow_line = self.canvas.create_line(
                arrow_start_x, arrow_y,
                arrow_end_x, arrow_y,
                fill=arrow_color, width=arrow_width,
                tags="flow_arrow", state=initial_state
            )
            self.flow_arrows.append(arrow_line)
            
            # Create arrowhead
            arrowhead = self.canvas.create_polygon(
                arrow_end_x - 8, arrow_y - 4,
                arrow_end_x, arrow_y,
                arrow_end_x - 8, arrow_y + 4,
                fill=arrow_color, outline=arrow_color,
                tags="flow_arrow", state=initial_state
            )
            self.flow_arrows.append(arrowhead)
        
        # Create the return arrow: Fish → up → back to Misc
        fish_button_x = start_x + 4 * (button_width + button_spacing)  # Fish is now at index 4
        misc_button_x = start_x + 1 * (button_width + button_spacing)  # Misc is still at index 1
        
        # Arrow going up from Fish
        up_start_x = fish_button_x + button_width / 2
        up_start_y = button_y - button_height / 2 - 5  # Start from top of button
        up_end_y = button_y - button_height - 25  # Go up but not too far
        
        up_line = self.canvas.create_line(
            up_start_x, up_start_y,
            up_start_x, up_end_y,
            fill=arrow_color, width=arrow_width,
            tags="flow_arrow", state=initial_state
        )
        self.flow_arrows.append(up_line)
        
        # Arrow going left from top to above Misc
        left_start_x = up_start_x
        left_end_x = misc_button_x + button_width / 2
        left_y = up_end_y
        
        left_line = self.canvas.create_line(
            left_start_x, left_y,
            left_end_x, left_y,
            fill=arrow_color, width=arrow_width,
            tags="flow_arrow", state=initial_state
        )
        self.flow_arrows.append(left_line)
        
        # Arrow going down to Misc
        down_start_x = left_end_x
        down_start_y = left_y
        down_end_y = button_y - button_height / 2 - 5  # End at top of Misc button
        
        down_line = self.canvas.create_line(
            down_start_x, down_start_y,
            down_start_x, down_end_y,
            fill=arrow_color, width=arrow_width,
            tags="flow_arrow", state=initial_state
        )
        self.flow_arrows.append(down_line)
        
        # Arrowhead pointing down to Misc
        down_arrowhead = self.canvas.create_polygon(
            down_start_x - 4, down_end_y - 8,
            down_start_x, down_end_y,
            down_start_x + 4, down_end_y - 8,
            fill=arrow_color, outline=arrow_color,
            tags="flow_arrow", state=initial_state
        )
        self.flow_arrows.append(down_arrowhead)
        
        # Lower all arrows below buttons and text
        for arrow_id in self.flow_arrows:
            self.canvas.tag_lower(arrow_id, "bottom_button")
            self.canvas.tag_lower(arrow_id, "bottom_button_text")


    def _create_menu_tabs(self):
        """Initial creation or re-creation of menu tab circles and text."""
        for item in self.tab_items:
            self.canvas.delete(item['icon_id'])
            self.canvas.delete(item['text_id'])
        self.tab_items = []
        
        for i, tab_name in enumerate(self.menu_tabs):
            # Get original tab color
            original_color = self.tab_colors.get(tab_name, "#2E2E2E")
            
            # Check if this tab is enabled - use gray color if disabled
            is_enabled = True
            if tab_name in ["Basic", "Misc", "Cast", "Shake", "Fish", "Discord"]:
                is_enabled = self.bottom_button_states.get(tab_name, True)
            
            tab_color = original_color if is_enabled else "#666666"
            
            icon_id = self.canvas.create_oval(0, 0, 0, 0, fill=tab_color, outline="white", width=2)
            text_id = self.canvas.create_text(0, 0, text=tab_name, fill="white", font=("Inter", 12), anchor="center")
            
            tab_data = {
                'icon_id': icon_id, 'text_id': text_id, 'text': tab_name,
                'current_size': self.tab_base_size, 'center_x': 0, 'center_y': 0,
            }
            self.tab_items.append(tab_data)
            
            self.canvas.tag_bind(icon_id, "<Enter>", partial(self._on_tab_enter, index=i))
            self.canvas.tag_bind(icon_id, "<Leave>", partial(self._on_tab_leave, index=i))
            self.canvas.tag_bind(text_id, "<Enter>", partial(self._on_tab_enter, index=i))
            self.canvas.tag_bind(text_id, "<Leave>", partial(self._on_tab_leave, index=i))

            if tab_name in ["Basic", "Support", "Cast", "Shake", "Fish", "Discord", "Misc"]:
                self.canvas.tag_bind(icon_id, "<Button-1>", partial(self._on_tab_click, index=i))
                self.canvas.tag_bind(text_id, "<Button-1>", partial(self._on_tab_click, index=i))
            
            self.canvas.tag_raise(icon_id)
            self.canvas.tag_raise(text_id)

        self._update_menu_positions()
    
    def _update_all_tab_colors(self):
        """Update the colors of all tab icons based on their enabled/disabled state."""
        if not hasattr(self, 'tab_items') or not self.tab_items:
            return
            
        for i, tab_item in enumerate(self.tab_items):
            if i >= len(self.menu_tabs):
                continue
                
            tab_name = self.menu_tabs[i]
            
            # Get original tab color
            original_color = self.tab_colors.get(tab_name, "#2E2E2E")
            
            # Check if this tab is enabled - use gray color if disabled
            is_enabled = True
            if tab_name in ["Basic", "Misc", "Cast", "Shake", "Fish", "Discord"]:
                is_enabled = self.bottom_button_states.get(tab_name, True)
            
            tab_color = original_color if is_enabled else "#666666"
            
            # Update the existing tab icon color
            self.canvas.itemconfig(tab_item['icon_id'], fill=tab_color)

    def _update_flow_box_colors(self):
        """Update the colors of Fish Box and Shake Box rectangles based on their enabled/disabled state."""
        if not hasattr(self, 'fish_rect') or not hasattr(self, 'shake_rect'):
            return
        if not hasattr(self, 'bottom_button_states'):
            return
            
        # Cache colors to avoid repeated updates with same values
        fish_enabled = self.bottom_button_states.get("Fish", True)
        shake_enabled = self.bottom_button_states.get("Shake", True)
        
        # Calculate new colors
        fish_color = "#2196F3" if fish_enabled else "#666666"
        shake_color = "#f44336" if shake_enabled else "#666666"
        
        # Only update if colors have changed (performance optimization)
        current_fish_color = getattr(self, '_current_fish_color', None)
        current_shake_color = getattr(self, '_current_shake_color', None)
        
        if current_fish_color != fish_color:
            self.canvas.itemconfig(self.fish_rect, fill=fish_color, outline=fish_color)
            self._current_fish_color = fish_color
        
        if current_shake_color != shake_color:
            self.canvas.itemconfig(self.shake_rect, fill=shake_color, outline=shake_color)
            self._current_shake_color = shake_color

    def _update_bottom_button_colors(self):
        """Update the colors of all bottom buttons based on their enabled/disabled state."""
        if not hasattr(self, 'bottom_buttons') or not self.bottom_buttons:
            return
        if not hasattr(self, 'bottom_button_states'):
            return
            
        for button_data in self.bottom_buttons:
            button_name = button_data['name']
            
            # Skip Start button (it's not toggleable)
            if button_name == "Start":
                continue
                
            # Get current state and update color accordingly
            is_enabled = self.bottom_button_states.get(button_name, True)
            
            if is_enabled:
                # Active state - use original color
                new_color = button_data['original_color']
            else:
                # Disabled state - use gray color
                new_color = "#666666"
            
            # Update the button color
            self.canvas.itemconfig(button_data['rect_id'], fill=new_color)

    def _update_menu_positions(self):
        """Calculates and sets the positions of all menu tabs."""
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 1 or c_h < 1: return

        num_tabs = len(self.menu_tabs)
        angle_increment = (2 * math.pi) / num_tabs

        for i, tab_data in enumerate(self.tab_items):
            tab_angle = self.current_angle + (i * angle_increment)
            
            x = c_w / 2 + self.menu_radius * math.cos(tab_angle)
            y = c_h / 2 + self.menu_radius * math.sin(tab_angle)

            tab_data['center_x'] = x
            tab_data['center_y'] = y
            
            current_size = tab_data['current_size']
            half_size = current_size / 2

            self.canvas.coords(tab_data['icon_id'], x - half_size, y - half_size, x + half_size, y + half_size)
            self.canvas.coords(tab_data['text_id'], x, y)
            
            font_size = int(12 * (current_size / self.tab_base_size))
            self.canvas.itemconfig(tab_data['text_id'], font=("Inter", max(10, font_size)))

    def _on_tab_enter(self, event, index=None):
        """Handles mouse entering a tab."""
        if self.app_state != 'menu': return 
        if index is not None:
            self.hovered_tab_index = index
            self.is_rotating = False 
        
    def _on_tab_leave(self, event, index=None):
        """Handles mouse leaving a tab."""
        if self.app_state != 'menu': return
        if index is not None and self.hovered_tab_index == index:
            self.hovered_tab_index = -1
            self.is_rotating = True 

    def _on_tab_click(self, event, index=None):
        """Handles a tab click and starts the zoom-in animation."""
        if index is None or self.app_state != 'menu':
            return
        
        tab_name = self.menu_tabs[index]
        if tab_name not in ["Basic", "Support", "Cast", "Shake", "Fish", "Discord", "Misc"]:
            return

        self.app_state = 'zooming_in'
        self.is_rotating = False
        self.hovered_tab_index = -1
        
        tab_data = self.tab_items[index]
        
        self.zoomed_tab_data = {
            'x': tab_data['center_x'],
            'y': tab_data['center_y'],
            'color': self.tab_colors[tab_name],
            'title': tab_data['text']
        }
        
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        dist_x = max(abs(c_w - tab_data['center_x']), abs(0 - tab_data['center_x']))
        dist_y = max(abs(c_h - tab_data['center_y']), abs(0 - tab_data['center_y']))
        max_dist = math.sqrt(dist_x**2 + dist_y**2)
        tab_data['target_size'] = max_dist * 2.1 
        
        self.canvas.tag_raise(tab_data['icon_id'])
        self.canvas.tag_raise(tab_data['text_id'])

        self.canvas.delete(self.central_label_id)
        self.central_label_id = None
        
        # Hide bottom buttons and arrows during zoom
        for button_data in self.bottom_buttons:
            self.canvas.itemconfig(button_data['rect_id'], state='hidden')
            self.canvas.itemconfig(button_data['text_id'], state='hidden')
        for arrow_id in self.flow_arrows:
            self.canvas.itemconfig(arrow_id, state='hidden')
        
        # Hide rock slashing elements during tab view
        if self.rocks_slashed_label_id:
            self.canvas.itemconfig(self.rocks_slashed_label_id, state='hidden')
        if self.auto_slash_checkbox:
            self.auto_slash_checkbox.place_forget()
        if self.shop_button:
            self.shop_button.place_forget()
        
        # Hide main menu buttons immediately when zoom starts
        if self.fisch_gui_toggle_checkbox:
            self.fisch_gui_toggle_checkbox.place_forget()
        if self.minigame_toggle_checkbox:
            self.minigame_toggle_checkbox.place_forget()
        
        for item in self.tab_items:
            if item != tab_data:
                self.canvas.delete(item['icon_id'])
                self.canvas.delete(item['text_id'])
        self.tab_items = [tab_data] 

        self._zoom_in_tab(tab_data)

    def _zoom_in_tab(self, tab_data):
        """Animates the tab expanding to cover the screen."""
        if self.app_state != 'zooming_in': return

        current_size = tab_data['current_size']
        target_size = tab_data['target_size']
        
        if current_size < target_size:
            new_size = min(target_size, current_size + 150) 
            tab_data['current_size'] = new_size
            half_size = new_size / 2

            x, y = tab_data['center_x'], tab_data['center_y']
            self.canvas.coords(tab_data['icon_id'], x - half_size, y - half_size, x + half_size, y + half_size)
            
            self.canvas.itemconfigure(tab_data['text_id'], fill="")
            
            self.after(10, lambda: self._zoom_in_tab(tab_data))
        else:
            tab_color = self.zoomed_tab_data.get('color', 'black')
            self.canvas.config(bg=tab_color) 
            self.canvas.delete(tab_data['icon_id']) 
            self.canvas.delete(tab_data['text_id']) 
            self.tab_items = [] 
            
            # Clear stars/trails when the zoom is finished (they will be re-created/re-animated later)
            for star in self.stars: self.canvas.delete(star['id'])
            self.stars = []
            for trail in self.trail_elements: self.canvas.delete(trail['id'])
            self.trail_elements = []

            self.app_state = 'tab_view'
            self._show_tab_view()

    # --- Tab View and Zoom Out Functions ---

    def _show_tab_view(self):
        """Creates the 'Back' button, and the specific tab content (BasicSettingsView)."""
        
        # 1. Create the Back Button (Top Left)
        back_size = 50
        padding = 20
        back_x = padding + back_size / 2
        back_y = padding + back_size / 2
        
        button_color = self.zoomed_tab_data['color'] 
        
        self.back_button_id = self.canvas.create_oval(
            back_x - back_size/2, back_y - back_size/2,
            back_x + back_size/2, back_y + back_size/2,
            fill="black", outline="white", width=2 
        )
        self.back_text_id = self.canvas.create_text(
            back_x, back_y,
            text="Back",
            fill="white",
            font=("Inter", 12, "bold"),
            anchor="center"
        )
        
        self.canvas.tag_bind(self.back_button_id, "<Button-1>", self._on_back_click)
        self.canvas.tag_bind(self.back_text_id, "<Button-1>", self._on_back_click)
        
        self.current_tab_title_id = None 

        # 2. Add the specific view content
        title = self.zoomed_tab_data.get('title', 'Selected')
        if title == "Basic":
            self.basic_settings_view = BasicSettingsView(
                master=self, 
                hotkey_manager=self.hotkey_manager,
                back_command=lambda: self._on_back_click(None) 
            )
            # Optimized spacing for better fit and aesthetics
            self.basic_settings_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.basic_settings_view.tkraise()
            
            # Apply initial "Always On Top" setting from global settings
            if self.global_gui_settings["Always On Top"]:
                self.wm_attributes("-topmost", True)
        
        elif title == "Support":
            self.support_view = SupportView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics  
            self.support_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.support_view.tkraise()
        
        elif title == "Cast":
            self.cast_view = CastView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics
            self.cast_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.cast_view.tkraise()
        
        elif title == "Shake":
            self.shake_view = ShakeView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics
            self.shake_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.shake_view.tkraise()
        
        elif title == "Fish":
            self.fish_view = FishView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics
            self.fish_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.fish_view.tkraise()
        
        elif title == "Discord":
            self.discord_view = DiscordView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics
            self.discord_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.discord_view.tkraise()
        
        elif title == "Misc":
            self.misc_view = MiscView(
                master=self,
                back_command=lambda: self._on_back_click(None)
            )
            # Optimized spacing for better fit and aesthetics
            self.misc_view.grid(row=0, column=0, sticky="nsew", padx=80, pady=(70, 30))
            self.misc_view.tkraise()

    def _update_back_button_position(self):
        """Ensures the back button stays in the top-left on resize."""
        if self.back_button_id and self.back_text_id:
            back_size = 50
            padding = 20
            back_x = padding + back_size / 2
            back_y = padding + back_size / 2
            
            self.canvas.coords(self.back_button_id, back_x - back_size/2, back_y - back_size/2, back_x + back_size/2, back_y + back_size/2)
            self.canvas.coords(self.back_text_id, back_x, back_y)
            
    def _on_back_click(self, event):
        """Initializes the zoom-out transition and cleans up view."""
        if self.app_state != 'tab_view': return

        # Destroy views - settings are saved in centralized dictionary, don't need GUI anymore
        if self.basic_settings_view:
            self.basic_settings_view.destroy()
            self.basic_settings_view = None

        if self.support_view:
            self.support_view.destroy()
            self.support_view = None

        if self.cast_view:
            self.cast_view.destroy()
            self.cast_view = None

        if self.shake_view:
            self.shake_view.destroy()
            self.shake_view = None

        if self.fish_view:
            self.fish_view.destroy()
            self.fish_view = None

        if self.discord_view:
            self.discord_view.destroy()
            self.discord_view = None

        if self.misc_view:
            self.misc_view.destroy()
            self.misc_view = None

        self.app_state = 'zooming_out'
        
        self.canvas.delete(self.back_button_id)
        self.canvas.delete(self.back_text_id)
        self.back_button_id = self.back_text_id = self.current_tab_title_id = None

        self.canvas.config(bg="black") 
        self._create_central_label() 
        self._create_menu_tabs()
        self._update_menu_positions()
        
        # Show bottom buttons and arrows again
        for button_data in self.bottom_buttons:
            self.canvas.itemconfig(button_data['rect_id'], state='normal')
            self.canvas.itemconfig(button_data['text_id'], state='normal')
        for arrow_id in self.flow_arrows:
            self.canvas.itemconfig(arrow_id, state='normal')
        self._update_bottom_button_positions()
        self._update_flow_arrows()
        
        # Show rock slashing elements again when returning to menu (only if minigame enabled)
        if self.rocks_slashed_label_id and self.minigame_enabled_var.get():
            self.canvas.itemconfig(self.rocks_slashed_label_id, state='normal')
        
        # Restore main menu toggle checkboxes (Auto Collect and Shop will be shown in _reset_to_menu)
        if self.fisch_gui_toggle_checkbox:
            self.fisch_gui_toggle_checkbox.place(x=10, y=10)
        if self.minigame_toggle_checkbox:
            self.minigame_toggle_checkbox.place(x=10, y=40)

        # Re-create stars and trails for the zoom-out transition
        for _ in range(self.base_max_stars // 2): 
            self.create_star()
        
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        dist_x = max(abs(c_w - self.zoomed_tab_data['x']), abs(0 - self.zoomed_tab_data['x']))
        dist_y = max(abs(c_h - self.zoomed_tab_data['y']), abs(0 - self.zoomed_tab_data['y']))
        max_dist = math.sqrt(dist_x**2 + dist_y**2)
        initial_size = max_dist * 2.1

        zoom_circle_id = self.canvas.create_oval(
            0, 0, 0, 0, fill=self.zoomed_tab_data['color'], outline="", tags="zoom_circle"
        )
        self.canvas.tag_raise(zoom_circle_id) 
        
        zoom_data = {
            'id': zoom_circle_id,
            'current_size': initial_size,
            'target_size': self.tab_base_size,
            'x': self.zoomed_tab_data['x'],
            'y': self.zoomed_tab_data['y']
        }
        
        self._zoom_out_tab(zoom_data)


    def _zoom_out_tab(self, zoom_data):
        """Animates the circle shrinking to the original tab's position."""
        if self.app_state != 'zooming_out': 
            self.canvas.delete(zoom_data['id'])
            return

        current_size = zoom_data['current_size']
        target_size = zoom_data['target_size']

        if current_size > target_size:
            new_size = max(target_size, current_size - 150)
            zoom_data['current_size'] = new_size
            half_size = new_size / 2

            x, y = zoom_data['x'], zoom_data['y']
            self.canvas.coords(zoom_data['id'], x - half_size, y - half_size, x + half_size, y + half_size)
            
            self.after(10, lambda: self._zoom_out_tab(zoom_data))
        else:
            self.canvas.delete(zoom_data['id'])
            self._reset_to_menu()
            

    def _reset_to_menu(self):
        """Restores the main menu view state."""
        self.app_state = 'menu'
        self.is_rotating = True
        self.zoomed_tab_data = {}
        
        # Now that app_state is 'menu', update button positions (will show them if minigame enabled)
        self._update_auto_slash_checkbox_position()
        self._update_shop_button_position()


    def animate_menu(self):
        """
        Animation loop for the menu: handles rotation and hover scaling.
        """
        # Skip animation if bot is running
        if not self.animations_running:
            self.after(self.animation_delay_ms, self.animate_menu)
            return

        if self.app_state not in ['menu', 'zooming_out']:
            self.after(self.animation_delay_ms, self.animate_menu)
            return
            
        if self.is_rotating:
            self.current_angle += self.rotation_speed
            if self.current_angle >= 2 * math.pi:
                self.current_angle -= 2 * math.pi
        
        if self.app_state == 'menu':
            for i, tab_data in enumerate(self.tab_items):
                target_size = self.tab_hover_size if i == self.hovered_tab_index else self.tab_base_size
                
                if tab_data['current_size'] < target_size:
                    tab_data['current_size'] = min(target_size, tab_data['current_size'] + 4) 
                elif tab_data['current_size'] > target_size:
                    tab_data['current_size'] = max(target_size, tab_data['current_size'] - 4) 
        
        self._update_menu_positions()

        self.after(self.animation_delay_ms, self.animate_menu)

    # --- Rock Slashing Mini-Game ---
    
    def _create_rocks_slashed_label(self):
        """Creates the 'Comets Collected' counter label below the minigame checkbox."""
        # Delete old label if it exists
        if hasattr(self, 'rocks_slashed_label_id') and self.rocks_slashed_label_id:
            self.canvas.delete(self.rocks_slashed_label_id)
            
        # Create as canvas text instead of CTkLabel to avoid background
        self.rocks_slashed_label_id = self.canvas.create_text(
            20, 140,
            text=f"Comets Collected: {self.rocks_slashed:.2f}",
            fill="#FFFFFF",
            font=("Inter", 12, "bold"),
            anchor="nw",
            state='hidden'  # Start hidden
        )
    
    def _update_rocks_slashed_label_position(self):
        """Ensures the comets collected label stays below the shop button."""
        # Only update position if minigame is enabled
        if hasattr(self, 'rocks_slashed_label_id') and self.rocks_slashed_label_id and self.minigame_enabled_var.get():
            self.canvas.coords(self.rocks_slashed_label_id, 20, 140)
    
    def _update_rocks_slashed_counter(self):
        """Updates the comets collected counter display with throttling for performance."""
        # Enhanced throttling - reduce UI updates during rapid collection
        import time
        current_time = time.time()
        if not hasattr(self, '_last_counter_update'):
            self._last_counter_update = 0
            self._last_counter_value = 0
            self._update_batch_counter = 0
        
        self._update_batch_counter += 1
        
        # Performance optimization: Longer delays during rapid collection
        min_update_interval = 0.2 if len(self.active_rocks) > 2 else 0.1  # 200ms vs 100ms
        
        # Only update if enough time passed OR value changed significantly
        time_diff = current_time - self._last_counter_update
        value_diff = abs(self.rocks_slashed - self._last_counter_value)
        significant_change = (value_diff > max(10, self.rocks_slashed * 0.02))  # Increased thresholds
        
        # Batch updates - only update UI every 5th call during rapid collection
        frequent_updates = (self._update_batch_counter % 5 == 0) if len(self.active_rocks) > 2 else True
        
        if time_diff < min_update_interval and not significant_change and not frequent_updates:
            return  # Skip update for performance
            
        if hasattr(self, 'rocks_slashed_label_id') and self.rocks_slashed_label_id:
            # Use new number formatting for large numbers
            display_text = f"Comets Collected: {self._format_large_number(self.rocks_slashed)}"
            self.canvas.itemconfig(self.rocks_slashed_label_id, text=display_text)
        
        # Update shop subtitle if shop is open
        if hasattr(self, 'shop_subtitle') and self.shop_subtitle and self.shop_subtitle.winfo_exists():
            try:
                shop_text = f"You have {self._format_large_number(self.rocks_slashed)} Comets"
                self.shop_subtitle.configure(text=shop_text)
            except:
                pass  # Shop window was destroyed
        
        # Update shop button states if shop is open (heavily throttled)
        if (hasattr(self, 'shop_upgrade_widgets') and self.shop_upgrade_widgets and 
            significant_change and time_diff > 0.5):  # Only update shop every 500ms
            self._update_shop_buttons()
            
        # Update tracking variables
        self._last_counter_update = current_time
        self._last_counter_value = self.rocks_slashed
    
    def _create_fisch_gui_toggle(self):
        """Creates the Fisch GUI toggle checkbox at the very top."""
        self.fisch_gui_toggle_checkbox = ctk.CTkCheckBox(
            self,
            text="Fisch GUI",
            variable=self.fisch_gui_enabled_var,
            command=self._on_fisch_gui_toggle,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#00FF00",  # Green color
            fg_color="#4A90E2",
            hover_color="#5BA3F5",
            checkmark_color="white"
        )
        self.fisch_gui_toggle_checkbox.place(x=10, y=10)
    
    def _create_minigame_toggle(self):
        """Creates the Comet Minigame toggle checkbox below Fisch GUI."""
        self.minigame_toggle_checkbox = ctk.CTkCheckBox(
            self,
            text="Comet Minigame",
            variable=self.minigame_enabled_var,
            command=self._on_minigame_toggle,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFD700",
            fg_color="#4A90E2",
            hover_color="#5BA3F5",
            checkmark_color="white"
        )
        self.minigame_toggle_checkbox.place(x=10, y=40)  # Moved down from y=10
    
    def _create_auto_slash_checkbox(self):
        """Creates the Auto Collect checkbox below the comets collected counter."""
        self.auto_slash_checkbox = ctk.CTkCheckBox(
            self,
            text="Auto Collect",
            variable=self.auto_slash_var,
            command=self._on_auto_slash_toggle,
            font=ctk.CTkFont(size=12),
            text_color="#FFFFFF",
            fg_color="#4A90E2",
            hover_color="#5BA3F5",
            checkmark_color="white"
        )
        self.auto_slash_checkbox.place(x=20, y=75)  # Moved down from y=45
    
    def _create_shop_button(self):
        """Creates the Shop button below the Auto Collect checkbox."""
        self.shop_button = ctk.CTkButton(
            self,
            text="🛒 Shop",
            command=self._toggle_shop,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color="#FFD700",
            hover_color="#FFA500",
            text_color="#000000",
            width=120,
            height=30,
            corner_radius=8
        )
        self.shop_button.place(x=20, y=105)  # Moved down from y=75
    
    def _update_auto_slash_checkbox_position(self):
        """Ensures the auto collect checkbox stays in correct position."""
        if self.auto_slash_checkbox:
            # Only show the checkbox when in menu state AND minigame is enabled
            if self.app_state == 'menu' and self.minigame_enabled_var.get():
                self.auto_slash_checkbox.place(x=20, y=75)  # Updated from y=45
            else:
                # Hide the checkbox when not in menu state or minigame disabled
                self.auto_slash_checkbox.place_forget()
    
    def _update_shop_button_position(self):
        """Ensures the shop button stays in correct position."""
        if hasattr(self, 'shop_button') and self.shop_button:
            # Only show the button when in menu state AND minigame is enabled
            if self.app_state == 'menu' and self.minigame_enabled_var.get():
                self.shop_button.place(x=20, y=105)  # Updated from y=75
            else:
                # Hide the button when not in menu state or minigame disabled
                self.shop_button.place_forget()
    
    def _toggle_shop(self):
        """Toggle the shop window visibility."""
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            # Shop window exists, close it
            self._hide_shop()
        else:
            # Shop doesn't exist, create and show it
            self._open_shop()
    
    def _open_shop(self):
        """Create the shop interface in a separate window (optimized for performance)."""
        # Check if shop window already exists
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            # Window exists, just bring it to front and refresh if needed
            self.shop_window.lift()
            self.shop_window.focus_force()
            # Light refresh only if significant changes
            if not hasattr(self, '_last_shop_refresh_comets'):
                self._last_shop_refresh_comets = 0
            if abs(self.rocks_slashed - self._last_shop_refresh_comets) > (self.rocks_slashed * 0.1):
                self._quick_refresh_shop_ui()
                self._last_shop_refresh_comets = self.rocks_slashed
            return

        print("Creating shop window (optimized)...")

        # Create shop as a separate top-level window
        self.shop_window = ctk.CTkToplevel(self)
        self.shop_window.title("⚡ Comet Shop")
        self.shop_window.geometry("800x700")

        # Performance: Disable topmost initially to reduce window manager overhead
        self.shop_window.attributes("-topmost", False)
        
        # Handle window close
        self.shop_window.protocol("WM_DELETE_WINDOW", self._hide_shop)
        
        # Initialize refresh tracking
        self._last_shop_refresh_comets = self.rocks_slashed

        # Main container
        main_frame = ctk.CTkFrame(self.shop_window, fg_color="#1E1E1E")
        main_frame.pack(fill="both", expand=True, padx=15, pady=15)

        # Shop title
        shop_title = ctk.CTkLabel(
            main_frame,
            text="🛒 Comet Shop",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#FFD700"
        )
        shop_title.pack(pady=(10, 5))

        # Subtitle (store reference for updating)
        self.shop_subtitle = ctk.CTkLabel(
            main_frame,
            text=f"You have {self.rocks_slashed:.1f} Comets",
            font=ctk.CTkFont(size=14),
            text_color="#FFFFFF"
        )
        self.shop_subtitle.pack(pady=(0, 10))

        # Button row (Stats and Close)
        button_row = ctk.CTkFrame(main_frame, fg_color="transparent")
        button_row.pack(pady=(0, 10))

        # Stats button
        stats_button = ctk.CTkButton(
            button_row,
            text="📊 Stats",
            command=self._show_stats_panel,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#3498DB",
            hover_color="#2980B9",
            text_color="#FFFFFF",
            width=100,
            height=30,
            corner_radius=8
        )
        stats_button.pack(side="left", padx=5)

        # Shop items container
        items_container = ctk.CTkScrollableFrame(
            main_frame,
            fg_color="#2B2B2B",
            corner_radius=10
        )
        items_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Create upgrade items
        self._create_shop_upgrades(items_container)

        # Enable topmost after creation to avoid window manager overhead during creation
        self.shop_window.after(100, lambda: self.shop_window.attributes("-topmost", True))
        self.shop_window.after(150, lambda: self.shop_window.lift())
        self.shop_window.after(200, lambda: self.shop_window.focus_force())

        # Close button
        close_button = ctk.CTkButton(
            main_frame,
            text="Close",
            command=self._hide_shop,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#E74C3C",
            hover_color="#C0392B",
            text_color="#FFFFFF",
            width=120,
            height=35,
            corner_radius=8
        )
        close_button.pack(pady=(0, 10))

        self.is_shop_open = True

        # Update shop button text
        if hasattr(self, 'shop_button') and self.shop_button:
            self.shop_button.configure(text="🛒 Shop (Open)")

        # Immediate refresh on shop open, then start auto-refresh timer
        self._execute_shop_refresh_batch()
        self._schedule_shop_refresh()
    
    def _show_shop(self):
        """Show the shop window."""
        # Just call _open_shop since we're using a window now
        self._open_shop()

    def _hide_shop(self):
        """Hide/destroy the shop window."""
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            self.shop_window.destroy()
            self.shop_window = None

        self.is_shop_open = False

        # Update shop button text
        if hasattr(self, 'shop_button') and self.shop_button:
            self.shop_button.configure(text="🛒 Shop")
    
    def _create_shop_upgrades(self, container):
        """Create all shop upgrade items."""

        # 10-TIER UPGRADE SYSTEM (5 upgrades per tier!)
        # BALANCED PROGRESSION - Total to first rebirth: ~20-40 hours of active play
        # 
        # MAJOR BALANCE UPDATE v2: Fixed tier 4 being too cheap and tier 8 unlock issues
        # - Tier 4: MASSIVELY increased costs (12-16x) and scaling (1.66-1.75x) due to tier 3 luck being OP
        # - Tier 5+ unlock requirements adjusted: T5 needs 60 T4 upgrades, T8/T9 need 28 instead of 32
        # - Tiers 5-9: SIGNIFICANTLY increased costs and reduced multiplicative effects
        # - Base costs increased 5x for T5-T9 with much more aggressive scaling (1.65-2.7x vs 1.45-2.2x)
        # - Multiplicative bonuses reduced: T5 (15%→8%, 10%→6%), T6 (5%→3%, 4%→2.5%), 
        #   T7 (1.05→1.03, 1.06→1.04), T8 (1.07→1.04, 1.06→1.03), T9 (1.15→1.08, 1.18→1.10)
        # - Enhanced debugging for tier 5+ purchases to track cost vs income balance
        # 
        # Tier 1: 15-30 min | Tier 2: 45-90 min | Tier 3: 2-3 hours | Tier 4: 6-8 hours (REBALANCED)
        # Tier 5: 1-1.5 hours | Tier 6: 2-3 hours | Tier 7: 3-5 hours | Tier 8: 5-10 hours | Tier 9: 10-20 hours
        # Total: ~25-45 hours for meaningful progression with proper tier 4 balance
        
        upgrades = [
            # ===== TIER 1: BASICS (30 seconds - 2 min) =====
            {
                "name": "⚡ Rock Value",
                "desc": "More comets per rock",
                "effect": lambda lvl: f"+{lvl * 2:.0f} base",
                "base_cost": 10,  # Reduced from 25 to 10
                "scaling": 1.12,  # Reduced from 1.25 to 1.12 for much smoother progression
                "type": "tier1_production",
                "tier": 1,
                "max_level": 50
            },
            {
                "name": "🌟 Collection Power",
                "desc": "Multiplicative % boost",
                "effect": lambda lvl: f"+{lvl * 5}%",
                "base_cost": 30,  # Reduced from 75 to 30
                "scaling": 1.10,  # Reduced from 1.20 to 1.10 for smoother progression
                "type": "tier1_multiplier",
                "tier": 1,
                "max_level": 50
            },
            {
                "name": "⚡ Lucky Rocks",
                "desc": "Chance for 2x comets",
                "effect": lambda lvl: f"{lvl * 2}% for 2x",
                "base_cost": 60,  # Reduced from 150 to 60
                "scaling": 1.13,  # Reduced from 1.22 to 1.13 for smoother progression
                "type": "tier1_luck",
                "tier": 1,
                "max_level": 40
            },
            {
                "name": "⚡ Extra Comets",
                "desc": "Flat bonus per rock",
                "effect": lambda lvl: f"+{lvl} flat",
                "base_cost": 25,  # Reduced from 75 to 25
                "scaling": 1.08,  # Reduced from 1.15 to 1.08 for much smoother progression
                "type": "tier1_bonus",
                "tier": 1,
                "max_level": 50
            },
            {
                "name": "🌟 Collection Boost",
                "desc": "Multiplicative % boost",
                "effect": lambda lvl: f"+{lvl * 3}%",
                "base_cost": 45,  # Reduced from 120 to 45
                "scaling": 1.11,  # Reduced from 1.18 to 1.11 for smoother progression
                "type": "tier1_power",
                "tier": 1,
                "max_level": 40
            },

            # ===== TIER 2: SPEED (2-4 min) =====
            {
                "name": "🌟 Chase Speed",
                "desc": "Auto-collect trail faster",
                "effect": lambda lvl: f"+{lvl * 15}% speed",
                "base_cost": 1000,  # Reduced from 2500 to 1000
                "scaling": 1.18,    # Reduced from 1.35 to 1.18 for much smoother progression
                "type": "tier2_speed",
                "tier": 2,
                "max_level": 40,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) >= 10  # Reduced from 15 to 10
            },
            {
                "name": "⚡ Rock Spawn",
                "desc": "Rocks appear faster",
                "effect": lambda lvl: f"{max(1000 - lvl * 38, 50)}ms wait" if lvl < 25 else "50ms wait (MAX)",
                "base_cost": 1500,  # Reduced from 4000 to 1500
                "scaling": 1.20,    # Reduced from 1.40 to 1.20 for much smoother progression
                "type": "tier2_spawn",
                "tier": 2,
                "max_level": 25,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) >= 10  # Reduced from 15 to 10
            },
            {
                "name": "⚡ Rock Capacity",
                "desc": "More rocks on screen",
                "effect": lambda lvl: f"{1 + lvl * 2} max",
                "base_cost": 2500,  # Reduced from 6000 to 2500
                "scaling": 1.15,    # Reduced from 1.25 to 1.15 for smoother progression
                "type": "tier2_rocks",
                "tier": 2,
                "max_level": 30,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) >= 10  # Reduced from 15 to 10
            },
            {
                "name": "⚡ Fire Rate",
                "desc": "Multiplicative % boost",
                "effect": lambda lvl: f"+{lvl * 8}%",
                "base_cost": 650,
                "scaling": 1.14,    # Reduced from 1.23 to 1.14 for smoother progression
                "type": "tier2_fire",
                "tier": 2,
                "max_level": 50,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) >= 15
            },
            {
                "name": "⚡ Efficiency",
                "desc": "Multiplicative % boost",
                "effect": lambda lvl: f"+{lvl * 4}%",
                "base_cost": 900,
                "scaling": 1.16,    # Reduced from 1.24 to 1.16 for smoother progression
                "type": "tier2_collection",
                "tier": 2,
                "max_level": 50,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) >= 15
            },

            # ===== TIER 3: LUCK (30-45 min) - BALANCED LUCK EFFECTS =====
            {
                "name": "⚡ Lucky Streak",
                "desc": "Amplifies ALL luck procs",
                "effect": lambda lvl: f"+{lvl * 5}% luck power",  # NERFED: 10% -> 5%
                "base_cost": 20000,  # Increased further to 20k
                "scaling": 1.40,     # Increased scaling to 1.40
                "type": "tier3_fortune",
                "tier": 3,
                "max_level": 30,     # Reduced max level 40 -> 30
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) >= 15
            },
            {
                "name": "⚡ Big Bonus",
                "desc": "Rare 5x multiplier",
                "effect": lambda lvl: f"{lvl * 0.8:.1f}% for 5x",  # NERFED: 1% -> 0.8% per level
                "base_cost": 35000,  # Increased from 25k to 35k
                "scaling": 1.42,     # Increased scaling
                "type": "tier3_jackpot",
                "tier": 3,
                "max_level": 25,     # Reduced max level 30 -> 25
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) >= 15
            },
            {
                "name": "🌟 Comet Burst",
                "desc": "Random extra comets",
                "effect": lambda lvl: f"{lvl * 2}% proc",  # NERFED: 3% -> 2% per level
                "base_cost": 50000,  # Increased from 40k to 50k
                "scaling": 1.44,     # Increased scaling
                "type": "tier3_burst",
                "tier": 3,
                "max_level": 30,     # Reduced max level 35 -> 30
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) >= 25
            },
            {
                "name": "⚡ Double Power",
                "desc": "Amplifies 2x chance",
                "effect": lambda lvl: f"+{lvl * 6}% to 2x",  # NERFED: 10% -> 6% per level
                "base_cost": 70000,  # Increased from 55k to 70k
                "scaling": 1.41,     # Increased scaling
                "type": "tier3_double",
                "tier": 3,
                "max_level": 35,     # Reduced max level 40 -> 35
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) >= 25
            },
            {
                "name": "⚡ Triple Luck",
                "desc": "3x comets chance",
                "effect": lambda lvl: f"{lvl * 1.5:.1f}% for 3x",  # NERFED: 2% -> 1.5% per level
                "base_cost": 90000,  # Increased from 75k to 90k
                "scaling": 1.45,     # Increased scaling
                "type": "tier3_triple",
                "tier": 3,
                "max_level": 30,     # Reduced max level 35 -> 30
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) >= 25
            },

            # ===== TIER 4: POWER (2-4 hours) - MAJOR REBALANCE =====
            {
                "name": "⚡ Super Collector",
                "desc": "MULTIPLICATIVE +50%",
                "effect": lambda lvl: f"+{lvl * 50}%",
                "base_cost": 100000000,  # Increased from 8M to 100M (12.5x increase for 20 Qa balance)
                "scaling": 1.68,         # Much more aggressive scaling
                "type": "tier4_super_prod",
                "tier": 4,
                "max_level": 30,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']]) >= 35
            },
            {
                "name": "⚡ Rock Crusher",
                "desc": "MULTIPLICATIVE +30%",
                "effect": lambda lvl: f"+{lvl * 30}%",
                "base_cost": 150000000,  # Increased from 12M to 150M (12.5x increase)
                "scaling": 1.72,         # Much more aggressive scaling
                "type": "tier4_strength",
                "tier": 4,
                "max_level": 30,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']]) >= 35
            },
            {
                "name": "⚡ Critical Strike",
                "desc": "Boosts luck effectiveness",
                "effect": lambda lvl: f"+{lvl * 20}% luck amp",
                "base_cost": 120000000,  # Increased from 10M to 120M (12x increase)
                "scaling": 1.75,         # Much more aggressive scaling
                "type": "tier4_critical",
                "tier": 4,
                "max_level": 25,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']]) >= 35
            },
            {
                "name": "⚡ Mega Harvest",
                "desc": "MULTIPLICATIVE +40%",
                "effect": lambda lvl: f"+{lvl * 40}%",
                "base_cost": 200000000,  # Increased from 15M to 200M (13.3x increase)
                "scaling": 1.70,         # Much more aggressive scaling
                "type": "tier4_mega",
                "tier": 4,
                "max_level": 28,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']]) >= 35
            },
            {
                "name": "🌟 Power Strike",
                "desc": "MULTIPLICATIVE +35%",
                "effect": lambda lvl: f"+{lvl * 35}%",
                "base_cost": 180000000,  # Increased from 11M to 180M (16.4x increase)
                "scaling": 1.66,         # Much more aggressive scaling
                "type": "tier4_thunder",
                "tier": 4,
                "max_level": 32,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']]) >= 35
            },

            # ===== TIER 5: MASTERY (For 1-5Qa Balance) - REASONABLE SCALING =====
            {
                "name": "⚡ Idle Income",
                "desc": "Comets per second",
                "effect": lambda lvl: f"+{self._format_large_number(lvl * 5000000000000000)}/s",  # 5Qa per level for max 100Qa
                "base_cost": 1000000000000000,  # 1Qa (appropriate for current Qa income level)
                "scaling": 1.8,                 # Much gentler scaling - similar to tier 2/3
                "type": "tier5_passive",
                "tier": 5,
                "max_level": 20,                # Max 20 levels = 100Qa/s passive income
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier4_{k}', 0) for k in ['super_prod', 'strength', 'critical', 'mega', 'thunder']]) >= 60
            },
            {
                "name": "⚡ Synergy",
                "desc": "Multiplies ALL upgrades",
                "effect": lambda lvl: f"+{lvl * 10}%",  # Boosted back to 10% - strong multiplicative bonus
                "base_cost": 1500000000000000,  # 1.5Qa (appropriate for current Qa income level)
                "scaling": 1.85,                # Much gentler scaling - similar to tier 2/3
                "type": "tier5_efficiency",
                "tier": 5,
                "max_level": 15,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier4_{k}', 0) for k in ['super_prod', 'strength', 'critical', 'mega', 'thunder']]) >= 60
            },
            {
                "name": "⚡ Cost Saver",
                "desc": "Cheaper upgrades",
                "effect": lambda lvl: f"-{min(lvl * 2, 50)}%",
                "base_cost": 1200000000000000,  # 1.2Qa (appropriate for current Qa income level)
                "scaling": 1.75,                # Much gentler scaling - similar to tier 2/3
                "type": "tier5_energy",
                "tier": 5,
                "max_level": 25,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier4_{k}', 0) for k in ['super_prod', 'strength', 'critical', 'mega', 'thunder']]) >= 60
            },
            {
                "name": "⚡ Accelerator",
                "desc": "MULTIPLICATIVE +12%",
                "effect": lambda lvl: f"+{lvl * 12}%",   # Boosted from 8% to 12% - strong multiplicative bonus
                "base_cost": 2000000000000000,  # 2Qa (appropriate for current Qa income level)
                "scaling": 1.82,                # Much gentler scaling - similar to tier 2/3
                "type": "tier5_growth",
                "tier": 5,
                "max_level": 18,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier4_{k}', 0) for k in ['super_prod', 'strength', 'critical', 'mega', 'thunder']]) >= 60
            },
            {
                "name": "⚡ Refund System",
                "desc": "Get comets back",
                "effect": lambda lvl: f"{min(lvl * 5, 50)}% back",
                "base_cost": 800000000000000,   # 0.8Qa (appropriate for current Qa income level)
                "scaling": 1.78,                # Much gentler scaling - similar to tier 2/3
                "type": "tier5_recycler",
                "tier": 5,
                "max_level": 10,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier4_{k}', 0) for k in ['super_prod', 'strength', 'critical', 'mega', 'thunder']]) >= 60
            },

            # ===== TIER 6: MULTIPLIERS (For 1Qi+ Balance) - MAJOR REBALANCE FOR QA+ INCOME =====
            {
                "name": "⚡ True Multiplier",
                "desc": "MULTIPLICATIVE gain",
                "effect": lambda lvl: f"+{lvl * 3}%",   # Reduced from 5% to 3%
                "base_cost": 500000000000000000,  # 500Qa (100x increase from 5T for Qa+ income)
                "scaling": 3.0,                   # Much more aggressive scaling
                "type": "tier6_true_multi",
                "tier": 6,
                "max_level": 20,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier5_{k}', 0) for k in ['passive', 'efficiency', 'energy', 'growth', 'recycler']]) >= 55
            },
            {
                "name": "⚡ Income Amplifier",
                "desc": "Double idle income",
                "effect": lambda lvl: f"{2 ** lvl:.0f}x",
                "base_cost": 800000000000000000,  # 800Qa (100x increase from 8T for Qa+ income)
                "scaling": 3.05,                  # Much more aggressive scaling
                "type": "tier6_income",
                "tier": 6,
                "max_level": 15,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier5_{k}', 0) for k in ['passive', 'efficiency', 'energy', 'growth', 'recycler']]) >= 55
            },
            {
                "name": "⚡ Power Amplifier",
                "desc": "Multiplicative power",
                "effect": lambda lvl: f"+{lvl * 2.5}%",  # Reduced from 4% to 2.5%
                "base_cost": 1200000000000000000, # 1.2Qi (100x increase from 12T for Qa+ income)
                "scaling": 3.2,                   # Much more aggressive scaling
                "type": "tier6_amplifier",
                "tier": 6,
                "max_level": 18,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier5_{k}', 0) for k in ['passive', 'efficiency', 'energy', 'growth', 'recycler']]) >= 55
            },
            {
                "name": "⚡ Compound Interest",
                "desc": "Multiplicative stacking",
                "effect": lambda lvl: f"+{lvl * 2}%",    # Reduced from 3% to 2%
                "base_cost": 700000000000000000,  # 700Qa (100x increase from 7T for Qa+ income)
                "scaling": 3.15,                  # Much more aggressive scaling
                "type": "tier6_compound",
                "tier": 6,
                "max_level": 20,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier5_{k}', 0) for k in ['passive', 'efficiency', 'energy', 'growth', 'recycler']]) >= 55
            },
            {
                "name": "🌟 Synergy Boost",
                "desc": "Multiplicative synergy",
                "effect": lambda lvl: f"+{lvl * 2.5}%",  # Reduced from 4% to 2.5%
                "base_cost": 1000000000000000000, # 1Qi (100x increase from 10T for Qa+ income)
                "scaling": 3.25,                  # Much more aggressive scaling
                "type": "tier6_synergy",
                "tier": 6,
                "max_level": 16,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier5_{k}', 0) for k in ['passive', 'efficiency', 'energy', 'growth', 'recycler']]) >= 55
            },

            # ===== TIER 7: EXPONENTIAL (For 10Qi+ Balance) - MAJOR REBALANCE FOR QA++ INCOME =====
            {
                "name": "⚡ Exponential Power",
                "desc": "1.03^level multiplier",
                "effect": lambda lvl: f"{1.03 ** lvl:.2f}x",  # Reduced from 1.05 to 1.03
                "base_cost": 10000000000000000000,  # 10Qi (100x increase from 100T for Qa++ income)
                "scaling": 3.3,                     # Much more aggressive scaling
                "type": "tier7_exponential",
                "tier": 7,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier6_{k}', 0) for k in ['true_multi', 'income', 'amplifier', 'compound', 'synergy']]) >= 45
            },
            {
                "name": "🌟 Supernova",
                "desc": "1.04^level explosive",
                "effect": lambda lvl: f"{1.04 ** lvl:.2f}x",  # Reduced from 1.06 to 1.04
                "base_cost": 15000000000000000000,  # 15Qi (100x increase from 150T for Qa++ income)
                "scaling": 3.35,                    # Much more aggressive scaling
                "type": "tier7_supernova",
                "tier": 7,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier6_{k}', 0) for k in ['true_multi', 'income', 'amplifier', 'compound', 'synergy']]) >= 45
            },
            {
                "name": "⚡ Comet Storm",
                "desc": "Additive +15% (strong!)",
                "effect": lambda lvl: f"+{lvl * 15}%",   # Reduced from 25% to 15%
                "base_cost": 20000000000000000000,  # 20Qi (100x increase from 200T for Qa++ income)
                "scaling": 3.4,                     # Much more aggressive scaling
                "type": "tier7_storm",
                "tier": 7,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier6_{k}', 0) for k in ['true_multi', 'income', 'amplifier', 'compound', 'synergy']]) >= 45
            },
            {
                "name": "⚡ Blazing Trail",
                "desc": "1.02^level power",
                "effect": lambda lvl: f"{1.02 ** lvl:.2f}x",  # Reduced from 1.04 to 1.02
                "base_cost": 13000000000000000000,  # 13Qi (100x increase from 130T for Qa++ income)
                "scaling": 3.38,                    # Much more aggressive scaling
                "type": "tier7_inferno",
                "tier": 7,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier6_{k}', 0) for k in ['true_multi', 'income', 'amplifier', 'compound', 'synergy']]) >= 25
            },
            {
                "name": "🌟 Lightning Chain",
                "desc": "Additive +12% (strong!)",
                "effect": lambda lvl: f"+{lvl * 12}%",   # Reduced from 20% to 12%
                "base_cost": 17000000000000000000,  # 17Qi (100x increase from 170T for Qa++ income)
                "scaling": 3.45,                    # Much more aggressive scaling
                "type": "tier7_lightning",
                "tier": 7,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier6_{k}', 0) for k in ['true_multi', 'income', 'amplifier', 'compound', 'synergy']]) >= 25
            },

            # ===== TIER 8: SUPREME (For 200Qi+ Balance) - MAJOR REBALANCE FOR QA+++ INCOME =====
            {
                "name": "⚡ Supreme Power",
                "desc": "1.04^level MASSIVE",
                "effect": lambda lvl: f"{1.04 ** lvl:.2f}x",  # Reduced from 1.07 to 1.04
                "base_cost": 200000000000000000000,  # 200Qi (100x increase from 2Qa for Qa+++ income)
                "scaling": 3.6,                      # Much more aggressive scaling
                "type": "tier8_ultimate",
                "tier": 8,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier7_{k}', 0) for k in ['exponential', 'supernova', 'storm', 'inferno', 'lightning']]) >= 15
            },
            {
                "name": "⚡ Cosmic Force",
                "desc": "1.03^level cosmic",
                "effect": lambda lvl: f"{1.03 ** lvl:.2f}x",  # Reduced from 1.06 to 1.03
                "base_cost": 300000000000000000000,  # 300Qi (100x increase from 3Qa for Qa+++ income)
                "scaling": 3.65,                     # Much more aggressive scaling
                "type": "tier8_cosmic",
                "tier": 8,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier7_{k}', 0) for k in ['exponential', 'supernova', 'storm', 'inferno', 'lightning']]) >= 15
            },
            {
                "name": "🌟 Overdrive Mode",
                "desc": "1.025^level overdrive",
                "effect": lambda lvl: f"{1.025 ** lvl:.3f}x",  # Reduced from 1.05 to 1.025
                "base_cost": 400000000000000000000,  # 400Qi (100x increase from 4Qa for Qa+++ income)
                "scaling": 3.55,                     # Much more aggressive scaling
                "type": "tier8_overdrive",
                "tier": 8,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier7_{k}', 0) for k in ['exponential', 'supernova', 'storm', 'inferno', 'lightning']]) >= 15
            },
            {
                "name": "⚡ Transcendence",
                "desc": "1.03^level breakthrough",
                "effect": lambda lvl: f"{1.03 ** lvl:.2f}x",  # Reduced from 1.06 to 1.03
                "base_cost": 340000000000000000000,  # 340Qi (100x increase from 3.4Qa for Qa+++ income)
                "scaling": 3.7,                      # Much more aggressive scaling
                "type": "tier8_transcendent",
                "tier": 8,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier7_{k}', 0) for k in ['exponential', 'supernova', 'storm', 'inferno', 'lightning']]) >= 15
            },
            {
                "name": "⚡ Absolute Zero",
                "desc": "1.025^level pure power",
                "effect": lambda lvl: f"{1.025 ** lvl:.3f}x",  # Reduced from 1.05 to 1.025
                "base_cost": 260000000000000000000,  # 260Qi (100x increase from 2.6Qa for Qa+++ income)
                "scaling": 3.6,                      # Much more aggressive scaling
                "type": "tier8_absolute",
                "tier": 8,
                "max_level": 8,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier7_{k}', 0) for k in ['exponential', 'supernova', 'storm', 'inferno', 'lightning']]) >= 15
            },

            # ===== TIER 9: ASCENSION (For 2Sx+ Balance - Ultimate Endgame) - MAJOR REBALANCE FOR QA++++ INCOME =====
            {
                "name": "⚡ Ascended Power",
                "desc": "1.08^level endgame!!!",
                "effect": lambda lvl: f"{1.08 ** lvl:.2f}x",   # Reduced from 1.15 to 1.08
                "base_cost": 2000000000000000000000,  # 2Sx (100x increase from 20Qa for Qa++++ income)
                "scaling": 4.7,                       # Even more extreme scaling
                "type": "tier9_godmode",
                "tier": 9,
                "max_level": 6,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier8_{k}', 0) for k in ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute']]) >= 15
            },
            {
                "name": "🔄 Infinite Loop",
                "desc": "1.10^level massive!!!",
                "effect": lambda lvl: f"{1.10 ** lvl:.2f}x",   # Reduced from 1.18 to 1.10
                "base_cost": 10000000000000000000000,  # 10Sx (100x increase from 100Qa for Qa++++ income)
                "scaling": 4.9,                        # Even more extreme scaling
                "type": "tier9_infinity",
                "tier": 9,
                "max_level": 6,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier8_{k}', 0) for k in ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute']]) >= 15
            },
            {
                "name": "⚡ All-Powerful",
                "desc": "1.09^level ultimate",
                "effect": lambda lvl: f"{1.09 ** lvl:.2f}x",   # Reduced from 1.17 to 1.09
                "base_cost": 20000000000000000000000,  # 20Sx (100x increase from 200Qa for Qa++++ income)
                "scaling": 4.8,                        # Even more extreme scaling
                "type": "tier9_omnipotent",
                "tier": 9,
                "max_level": 6,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier8_{k}', 0) for k in ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute']]) >= 15
            },
            {
                "name": "⚡ Eternal Flame",
                "desc": "1.10^level timeless",
                "effect": lambda lvl: f"{1.10 ** lvl:.2f}x",   # Reduced from 1.18 to 1.10
                "base_cost": 15000000000000000000000,  # 15Sx (100x increase from 150Qa for Qa++++ income)
                "scaling": 4.75,                       # Even more extreme scaling
                "type": "tier9_eternal",
                "tier": 9,
                "max_level": 6,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier8_{k}', 0) for k in ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute']]) >= 15
            },
            {
                "name": "⚡ All-Seeing",
                "desc": "1.08^level knowing",
                "effect": lambda lvl: f"{1.08 ** lvl:.2f}x",   # Reduced from 1.16 to 1.08
                "base_cost": 16000000000000000000000,  # 16Sx (100x increase from 160Qa for Qa++++ income)
                "scaling": 4.85,                       # Even more extreme scaling
                "type": "tier9_omniscient",
                "tier": 9,
                "max_level": 6,
                "requirement": lambda: sum([self.upgrade_levels.get(f'tier8_{k}', 0) for k in ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute']]) >= 15
            }
        ]

        # Track upgrade levels
        if not hasattr(self, 'upgrade_levels'):
            self.upgrade_levels = {}
            for upgrade in upgrades:
                self.upgrade_levels[upgrade['type']] = 0
        
        # Track shop upgrade buttons for dynamic updating
        self.shop_upgrade_widgets = []
        self.shop_tier_requirement_labels = {}  # Store tier requirement labels for updating
        self.is_shop_open = False

        # Group upgrades by tier
        tiers = {}
        for upgrade_data in upgrades:
            tier = upgrade_data.get('tier', 1)
            if tier not in tiers:
                tiers[tier] = []
            tiers[tier].append(upgrade_data)

        # Create tier sections in order
        tier_names = {
            1: "TIER 1: FOUNDATION",
            2: "TIER 2: AUTOMATION",
            3: "TIER 3: LUCK",
            4: "TIER 4: POWER",
            5: "TIER 5: PASSIVE",
            6: "TIER 6: MULTIPLICATIVE",
            7: "TIER 7: EXPONENTIAL",
            8: "TIER 8: ULTIMATE",
            9: "TIER 9: GOD TIER"
        }

        tier_colors = {
            1: "#FFFFFF",    # White
            2: "#90EE90",    # Light Green
            3: "#4CAF50",    # Green
            4: "#00BCD4",    # Cyan
            5: "#2196F3",    # Blue
            6: "#9C27B0",    # Purple
            7: "#FF9800",    # Orange
            8: "#F44336",    # Red
            9: "#FFD700"     # Gold
        }

        # Tier requirements info (updated for balanced progression)
        tier_requirements = {
            1: None,
            2: ("Tier 1", 15),
            3: ("Tier 2", 25),
            4: ("Tier 3", 35),
            5: ("Tier 4", 60),   # Increased from 45 to 60 - tier 4 has 143 max levels, need ~42%
            6: ("Tier 5", 55),
            7: ("Tier 6", 25),   # Reduced from 70 to 25 - more reasonable progression
            8: ("Tier 7", 15),   # Reduced from 28 to 15 - tier 7 has 40 max, need 15 (38%)
            9: ("Tier 8", 15)    # Reduced from 28 to 15 - tier 8 has 40 max, need 15 (38%)
        }

        for tier_num in sorted(tiers.keys()):
            # Tier header with requirement
            header_text = f"--- {tier_names.get(tier_num, f'TIER {tier_num}')} ---"

            tier_label = ctk.CTkLabel(
                container,
                text=header_text,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=tier_colors.get(tier_num, "#FFD700")
            )
            tier_label.pack(pady=(15, 2))

            # Show requirement for locked tiers
            if tier_num in tier_requirements and tier_requirements[tier_num]:
                prev_tier_name, required_levels = tier_requirements[tier_num]

                # Calculate current progress in previous tier
                prev_tier_num = tier_num - 1
                if prev_tier_num in tiers:
                    prev_tier_progress = sum([
                        self.upgrade_levels.get(upgrade['type'], 0)
                        for upgrade in tiers[prev_tier_num]
                    ])

                    is_unlocked = prev_tier_progress >= required_levels

                    if is_unlocked:
                        req_text = f"✅ Unlocked!"
                        req_color = "#00FF00"
                    else:
                        req_text = f"Unlock: Buy {required_levels} {prev_tier_name} upgrades total ({prev_tier_progress}/{required_levels})"
                        req_color = "#FF6B6B"

                    req_label = ctk.CTkLabel(
                        container,
                        text=req_text,
                        font=ctk.CTkFont(size=10),
                        text_color=req_color
                    )
                    req_label.pack(pady=(0, 3))

                    # Store reference for dynamic updates
                    if not hasattr(self, 'tier_requirement_labels'):
                        self.tier_requirement_labels = {}
                    self.tier_requirement_labels[tier_num] = req_label
                    self.shop_tier_requirement_labels[tier_num] = {
                        'label': req_label,
                        'prev_tier_num': prev_tier_num,
                        'prev_tier_name': prev_tier_name,
                        'required_levels': required_levels,
                        'tiers': tiers
                    }

            # Create upgrade cards in this tier
            for upgrade_data in tiers[tier_num]:
                self._create_upgrade_card(container, upgrade_data)

        # Add TIER 10: REBIRTH button
        self._create_rebirth_section(container)

    def _create_rebirth_section(self, container):
        """Create Tier 10: Rebirth section."""
        # Calculate rebirth multiplier gain (2x per rebirth - multiplicative!)
        next_multiplier = self.rebirth_multiplier * 2.0

        # Compact rebirth header
        rebirth_header = ctk.CTkLabel(
            container,
            text="--- TIER 10: REBIRTH ---",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#FF0000"
        )
        rebirth_header.pack(pady=(15, 5))

        # Compact rebirth card
        rebirth_card = ctk.CTkFrame(
            container,
            fg_color="#2b2b2b",
            corner_radius=8,
            border_width=2
        )
        rebirth_card.pack(fill="x", padx=5, pady=5)
        
        # Store reference to update border color
        self.rebirth_card = rebirth_card

        # Card content
        content_frame = ctk.CTkFrame(rebirth_card, fg_color="transparent")
        content_frame.pack(fill="x", padx=15, pady=12)

        # Title row
        title_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        title_frame.pack(fill="x", pady=(0, 8))

        title = ctk.CTkLabel(
            title_frame,
            text="🌟 COSMIC REBIRTH",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#FF4444"
        )
        title.pack(side="left")

        status = ctk.CTkLabel(
            title_frame,
            text="",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        status.pack(side="right")
        self.rebirth_status_label = status

        # Description
        desc = ctk.CTkLabel(
            content_frame,
            text="Reset everything to gain a permanent 2x multiplier (multiplicative!)",
            font=ctk.CTkFont(size=11),
            text_color="#AAAAAA"
        )
        desc.pack(anchor="w", pady=(0, 8))

        # Stats in horizontal layout
        stats_frame = ctk.CTkFrame(content_frame, fg_color="#1a1a1a", corner_radius=5)
        stats_frame.pack(fill="x", pady=8)

        stats_inner = ctk.CTkFrame(stats_frame, fg_color="transparent")
        stats_inner.pack(fill="x", padx=10, pady=8)

        # Left side: Current stats
        left_stats = ctk.CTkFrame(stats_inner, fg_color="transparent")
        left_stats.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            left_stats,
            text=f"Rebirths: {self.rebirth_count}",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFD700"
        ).pack(anchor="w")

        ctk.CTkLabel(
            left_stats,
            text=f"Current: {self.rebirth_multiplier:.1f}x",
            font=ctk.CTkFont(size=12),
            text_color="#4CAF50"
        ).pack(anchor="w", pady=(2, 0))

        # Right side: Next stats
        right_stats = ctk.CTkFrame(stats_inner, fg_color="transparent")
        right_stats.pack(side="right", fill="x", expand=True)

        ctk.CTkLabel(
            right_stats,
            text=f"After Rebirth: {next_multiplier:.1f}x",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#2196F3"
        ).pack(anchor="e")

        gain_text = f"(+{next_multiplier - self.rebirth_multiplier:.1f}x gain)"
        ctk.CTkLabel(
            right_stats,
            text=gain_text,
            font=ctk.CTkFont(size=11),
            text_color="#888888"
        ).pack(anchor="e", pady=(2, 0))

        # Requirement
        req_label = ctk.CTkLabel(
            content_frame,
            text="",
            font=ctk.CTkFont(size=11)
        )
        req_label.pack(pady=(5, 8))
        self.rebirth_req_label = req_label

        # Rebirth button - command will check dynamically
        rebirth_btn = ctk.CTkButton(
            content_frame,
            text="",
            font=ctk.CTkFont(size=18, weight="bold"),
            height=60,
            command=self._attempt_rebirth
        )
        rebirth_btn.pack(fill="x", pady=(15, 0))
        self.rebirth_button = rebirth_btn
        
        # Initial update
        self._update_rebirth_button()

    def _can_rebirth(self):
        """Check if player can rebirth (maxed out all Tier 9 upgrades)."""
        tier9_upgrades = ['godmode', 'infinity', 'omnipotent', 'eternal', 'omniscient']
        tier9_max_level = 6  # Each tier 9 upgrade has max level 6
        
        # Check if ALL tier 9 upgrades are maxed out
        for upgrade_key in tier9_upgrades:
            current_level = self.upgrade_levels.get(f'tier9_{upgrade_key}', 0)
            if current_level < tier9_max_level:
                return False
        return True
    
    def _update_rebirth_button(self):
        """Update rebirth button state based on current progress."""
        if not hasattr(self, 'rebirth_button'):
            return
            
        can_rebirth = self._can_rebirth()
        
        # Update button appearance
        self.rebirth_button.configure(
            text="🌟 REBIRTH NOW 🌟" if can_rebirth else "⚡ LOCKED (Max all Tier 9 first!)",
            fg_color="#FF0000" if can_rebirth else "#333333",
            hover_color="#CC0000" if can_rebirth else "#333333",
            text_color="#FFFFFF" if can_rebirth else "#666666",
            state="normal" if can_rebirth else "disabled"
        )
        
        # Update status label
        if hasattr(self, 'rebirth_status_label'):
            self.rebirth_status_label.configure(
                text="✅ READY!" if can_rebirth else "⚡ Locked",
                text_color="#00FF00" if can_rebirth else "#666666"
            )
        
        # Update requirement label
        if hasattr(self, 'rebirth_req_label'):
            req_text = "Requirement: ✅ Met!" if can_rebirth else "Requirement: Max out ALL Tier 9 upgrades (level 6)"
            self.rebirth_req_label.configure(
                text=req_text,
                text_color="#00FF00" if can_rebirth else "#FF6B6B"
            )
        
        # Update card border
        if hasattr(self, 'rebirth_card'):
            self.rebirth_card.configure(
                border_color="#FF0000" if can_rebirth else "#444444"
            )
    
    def _attempt_rebirth(self):
        """Attempt to perform rebirth - checks if eligible first."""
        if not self._can_rebirth():
            return
        self._perform_rebirth()

    def _perform_rebirth(self):
        """Perform a rebirth - reset all upgrades and increase multiplier."""
        new_multiplier = self.rebirth_multiplier * 2.0

        # Confirm dialog
        confirm = messagebox.askyesno(
            "Cosmic Rebirth",
            f"Are you sure you want to rebirth?\n\n"
            f"This will:\n"
            f"• Reset ALL upgrades to level 0\n"
            f"• Reset your comet count to 0\n"
            f"• DOUBLE your permanent multiplier from {self.rebirth_multiplier:.1f}x to {new_multiplier:.1f}x\n\n"
            f"You will be Rebirth {self.rebirth_count + 1}!"
        )

        if not confirm:
            return

        # Perform rebirth
        self.rebirth_count += 1
        self.rebirths = self.rebirth_count  # Keep both variables in sync
        self.rebirth_multiplier = new_multiplier

        # Reset all upgrades
        for key in self.upgrade_levels.keys():
            self.upgrade_levels[key] = 0

        # Reset comets
        self.rocks_slashed = 0

        # Reset stats (keep lifetime stats separate if desired)
        self.stats['total_rocks_collected'] = 0
        self.stats['total_comets_earned'] = 0.0
        self.stats['total_comets_spent'] = 0.0
        self.stats['double_procs'] = 0
        self.stats['triple_procs'] = 0
        self.stats['mega_procs'] = 0
        self.stats['ultra_procs'] = 0

        # Recalculate everything
        self._recalculate_all_upgrades()
        self._update_rocks_slashed_counter()

        # Close and reopen shop to refresh
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            self.shop_window.destroy()
            self._show_shop()

        # Show success message
        messagebox.showinfo(
            "Rebirth Complete!",
            f"⚡ REBIRTH {self.rebirth_count} ACHIEVED! 🎉\n\n"
            f"Your power multiplier is now {self.rebirth_multiplier:.1f}x!\n"
            f"Time to climb even higher!"
        )

    def _create_upgrade_card(self, container, upgrade_data):
        """Create a compact Cookie Clicker-style upgrade card."""
        upgrade_type = upgrade_data["type"]
        current_level = self.upgrade_levels.get(upgrade_type, 0)
        max_level = upgrade_data.get("max_level", 999)

        # Check if upgrade is locked by requirement
        is_locked = False
        if "requirement" in upgrade_data:
            try:
                is_locked = not upgrade_data["requirement"]()
            except:
                is_locked = False

        # Check if maxed out
        is_maxed = current_level >= max_level

        # Calculate cost for next level (with cost reduction)
        cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
        cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))

        # Format cost for display with proper number abbreviations
        cost_display = self._format_large_number(cost)

        # Compact card frame - MUCH smaller padding
        card = ctk.CTkFrame(
            container,
            fg_color="#2b2b2b" if not is_locked else "#1a1a1a",
            corner_radius=5,
            border_width=1,
            border_color="#4a4a4a" if not is_locked else "#3a3a3a"
        )
        card.pack(fill="x", padx=5, pady=2)

        # Single horizontal line layout
        content_frame = ctk.CTkFrame(card, fg_color="transparent")
        content_frame.pack(fill="x", padx=8, pady=4)

        # Left: Name + Level (compact)
        left_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="x", expand=True)

        # Name and level on same line
        name_level_text = f"{upgrade_data['name']} Lv.{current_level}"
        if is_maxed:
            name_level_text += " [MAX]"

        title = ctk.CTkLabel(
            left_frame,
            text=name_level_text,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#FFD700" if is_maxed else ("#666666" if is_locked else "#FFFFFF"),
            anchor="w"
        )
        title.pack(side="left", anchor="w")

        # Description (very small, inline)
        desc = ctk.CTkLabel(
            left_frame,
            text=f" - {upgrade_data['desc']}",
            font=ctk.CTkFont(size=10),
            text_color="#888888",
            anchor="w"
        )
        desc.pack(side="left", anchor="w", padx=(5, 0))

        # Middle: Current effect (compact)
        if not is_locked:
            if current_level > 0:
                effect_text = upgrade_data["effect"](current_level)
            else:
                effect_text = upgrade_data["effect"](1)  # Show level 1 effect

            effect = ctk.CTkLabel(
                content_frame,
                text=effect_text,
                font=ctk.CTkFont(size=11),
                text_color="#7ED321" if current_level > 0 else "#666666"
            )
            effect.pack(side="left", padx=10)
        else:
            effect = ctk.CTkLabel(
                content_frame,
                text="—",
                font=ctk.CTkFont(size=11),
                text_color="#666666"
            )
            effect.pack(side="left", padx=10)

        # Right: Cost + Buy button (very compact)
        buy_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
        buy_frame.pack(side="right")

        can_afford = self.rocks_slashed >= cost and not is_locked and not is_maxed

        if is_maxed:
            button_text = "⭐ MAX"
            button_color = "#2d5016"
        elif is_locked:
            button_text = "⚡ Locked"
            button_color = "#3a3a3a"
        else:
            button_text = f"{cost_display}"
            button_color = "#4CAF50" if can_afford else "#444444"

        buy_button = ctk.CTkButton(
            buy_frame,
            text=button_text,
            command=lambda: self._purchase_upgrade(upgrade_type, upgrade_data),
            font=ctk.CTkFont(size=11, weight="bold"),
            fg_color=button_color,
            hover_color="#45a049" if can_afford and not is_maxed else button_color,
            text_color="#FFFFFF" if can_afford or is_maxed else "#777777",
            width=80,
            height=24,
            corner_radius=4,
            state="normal" if can_afford else "disabled"
        )
        buy_button.pack()

        # Store reference for updates
        self.shop_upgrade_widgets.append({
            'button': buy_button,
            'title': title,
            'effect_label': effect,
            'upgrade_type': upgrade_type,
            'upgrade_data': upgrade_data
        })
    
    def _purchase_upgrade(self, upgrade_type, upgrade_data):
        """Handle upgrade purchase with spam protection."""
        import time  # Import time at the beginning of the function
        
        # SPAM PROTECTION: Limit clicks to prevent rapid-fire purchases
        current_time = time.time()
        if not hasattr(self, '_last_purchase_times'):
            self._last_purchase_times = {}
        
        # Check if this specific upgrade was clicked too recently (50ms cooldown)
        last_purchase_time = self._last_purchase_times.get(upgrade_type, 0)
        if current_time - last_purchase_time < 0.05:  # 50ms = 20 clicks/second max
            return  # Silently ignore spam clicks
        
        # Update last purchase time for this upgrade
        self._last_purchase_times[upgrade_type] = current_time
        
        current_level = self.upgrade_levels.get(upgrade_type, 0)
        max_level = upgrade_data.get("max_level", 999)

        # Check if maxed
        if current_level >= max_level:
            print(f"⚠️ {upgrade_data['name']} is already at max level!")
            return

        # Check requirements
        if "requirement" in upgrade_data:
            try:
                if not upgrade_data["requirement"]():
                    print(f"🔒 {upgrade_data['name']} is locked! Check requirements.")
                    return
            except:
                pass

        # Apply cost reduction if available (tier5_energy: -2% per level, max 50%)
        cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
        cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))

        if self.rocks_slashed >= cost:
            # Apply refund if available (tier5_recycler: 5% per level, max 50%)
            refund_rate = min(self.upgrade_levels.get('tier5_recycler', 0) * 0.05, 0.50)
            actual_cost = int(cost * (1 - refund_rate))
            
            # Deduct actual cost (after refund)
            self.rocks_slashed -= actual_cost

            # === ENHANCED STATISTICS TRACKING ===
            
            # Basic spending stats
            self.stats['total_comets_spent'] += actual_cost
            self.stats['total_upgrades_purchased'] += 1
            self.stats['current_session_upgrades'] = self.stats.get('current_session_upgrades', 0) + 1
            
            # Track most expensive purchase
            if actual_cost > self.stats.get('most_expensive_purchase', 0):
                self.stats['most_expensive_purchase'] = actual_cost
                
            # Track energy savings (if cost reduction applied)
            if cost_reduction > 0:
                savings_amount = upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * cost_reduction
                self.stats['energy_savings_total'] = self.stats.get('energy_savings_total', 0) + savings_amount
            
            # Track tier-specific purchases and highest tier reached
            tier_num = upgrade_data.get("tier", 1)
            tier_key = f'tier{tier_num}_upgrades'
            self.stats[tier_key] = self.stats.get(tier_key, 0) + 1
            
            # Update highest tier reached
            if tier_num > self.stats.get('highest_tier_reached', 1):
                self.stats['highest_tier_reached'] = tier_num

            # Increase level
            self.upgrade_levels[upgrade_type] += 1
            new_level = self.upgrade_levels[upgrade_type]

            # Recalculate all multipliers and bonuses
            self._recalculate_all_upgrades()

            # Update counter displays
            self._update_rocks_slashed_counter()

            # Use new instant refresh with debounce for immediate visual feedback
            self._instant_shop_refresh_with_debounce()
            
            # Update tier requirement text after purchase (throttled)
            if not hasattr(self, '_last_tier_update') or time.time() - self._last_tier_update > 0.5:
                self._update_tier_requirements()
                self._last_tier_update = time.time()
            
            # Update rebirth button if it exists (throttled)
            if not hasattr(self, '_last_rebirth_update') or time.time() - self._last_rebirth_update > 1.0:
                self._update_rebirth_button()
                self._last_rebirth_update = time.time()

            # Print purchase message with max level indicator and refund info
            max_indicator = f" [{new_level}/{max_level}]" if max_level < 999 else ""
            
            # Enhanced debug output for tier 5+ to track progression balance
            tier_num = upgrade_data.get("tier", 1)
            if tier_num >= 5:
                comets_per_rock = self.base_comets_per_rock * self.comet_multiplier
                rocks_needed = actual_cost / comets_per_rock if comets_per_rock > 0 else float('inf')
                print(f"🔍 TIER {tier_num} DEBUG: {upgrade_data['name']} L{new_level} | Cost: {actual_cost:,.0f} | Per Rock: {comets_per_rock:.1f} | Rocks Needed: {rocks_needed:.1f}")
            
            if refund_rate > 0:
                print(f"⚡ Purchased {upgrade_data['name']} Level {new_level}{max_indicator} for {actual_cost:,.0f} comets ({refund_rate*100:.0f}% refund: saved {cost - actual_cost:,.0f} comets)!")
            else:
                print(f"⚡ Purchased {upgrade_data['name']} Level {new_level}{max_indicator} for {actual_cost:,.0f} comets!")

            # Celebrate max level
            if new_level >= max_level:
                print(f"🎉 {upgrade_data['name']} is now MAX LEVEL! 🎉")
        else:
            print(f"❌ Not enough comets! Need {cost:,.0f}, have {self.rocks_slashed:.2f}")
    
    def _create_shop_upgrades_optimized(self, container):
        """Create shop upgrades with performance optimizations - batched creation."""
        # First get all upgrade data (same as original function)
        upgrades = self._get_upgrade_definitions()
        
        # Initialize storage for UI elements
        self.shop_upgrade_widgets = []
        self.shop_tier_requirement_labels = {}
        
        # Group by tiers for organized display
        tiers = {}
        for upgrade in upgrades:
            tier = upgrade["tier"]
            if tier not in tiers:
                tiers[tier] = []
            tiers[tier].append(upgrade)
        
        # Create tier sections in batches to reduce initial lag
        self._create_tiers_batched(container, tiers, 0)
    
    def _create_tiers_batched(self, container, tiers, tier_index):
        """Create tier sections in batches for better performance."""
        tier_keys = sorted(tiers.keys())
        
        if tier_index >= len(tier_keys):
            print("✅ Shop creation complete!")
            return
        
        # Create next batch of tiers (2 tiers at a time)
        batch_size = 2
        for i in range(batch_size):
            current_index = tier_index + i
            if current_index >= len(tier_keys):
                break
                
            tier_num = tier_keys[current_index]
            tier_upgrades = tiers[tier_num]
            self._create_tier_section(container, tier_num, tier_upgrades, tiers)
        
        # Schedule next batch after a small delay to prevent UI freezing
        if tier_index + batch_size < len(tier_keys):
            container.after(10, lambda: self._create_tiers_batched(container, tiers, tier_index + batch_size))
    
    def _create_tier_section(self, container, tier_num, tier_upgrades, all_tiers):
        """Create a single tier section with all its upgrades."""
        # Tier section
        tier_frame = ctk.CTkFrame(container, fg_color="#353535", corner_radius=8)
        tier_frame.pack(fill="x", padx=5, pady=8)
        
        # Tier header
        tier_header = ctk.CTkLabel(
            tier_frame,
            text=f"🌟 TIER {tier_num}",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="#FFD700"
        )
        tier_header.pack(pady=(10, 5))
        
        # Create requirement label for this tier
        self._create_tier_requirement_label(tier_frame, tier_num, all_tiers)
        
        # Create all upgrades for this tier
        for upgrade_data in tier_upgrades:
            self._create_single_upgrade_widget(tier_frame, upgrade_data)
    
    def _update_tier_requirements(self):
        """Update tier requirement text dynamically after purchases."""
        if not hasattr(self, 'tier_requirement_labels'):
            return
            
        # Define tier names for display
        tier_names = {
            1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4", 5: "Tier 5",
            6: "Tier 6", 7: "Tier 7", 8: "Tier 8", 9: "Tier 9", 10: "Tier 10"
        }
        
        # Update each tier's requirement text
        for tier_num, req_label in self.tier_requirement_labels.items():
            if tier_num <= 1:  # Tier 1 has no requirements
                continue
                
            try:
                prev_tier_num = tier_num - 1
                prev_tier_name = tier_names.get(prev_tier_num, f"Tier {prev_tier_num}")
                
                # Calculate progress for previous tier
                tier_keys = {
                    1: ['production', 'multiplier', 'luck', 'bonus', 'power'],
                    2: ['speed', 'spawn', 'rocks', 'fire', 'collection'],
                    3: ['fortune', 'jackpot', 'burst', 'double', 'triple'],
                    4: ['super_prod', 'strength', 'critical', 'mega', 'thunder'],
                    5: ['passive', 'efficiency', 'energy', 'growth', 'recycler'],
                    6: ['true_multi', 'income', 'amplifier', 'compound', 'synergy'],
                    7: ['exponential', 'supernova', 'storm', 'inferno', 'lightning'],
                    8: ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute'],
                    9: ['godmode', 'infinity', 'omnipotent', 'eternal', 'omniscient']
                }
                
                prev_keys = tier_keys.get(prev_tier_num, [])
                prev_tier_progress = sum([self.upgrade_levels.get(f'tier{prev_tier_num}_{k}', 0) for k in prev_keys])
                
                # Define requirements
                required_levels = 15 + (prev_tier_num - 1) * 10  # 15, 25, 35, etc.
                
                is_unlocked = prev_tier_progress >= required_levels
                
                if is_unlocked:
                    req_text = f"✅ Unlocked!"
                    req_color = "#00FF00"
                else:
                    req_text = f"Unlock: Buy {required_levels} {prev_tier_name} upgrades total ({prev_tier_progress}/{required_levels})"
                    req_color = "#FF6B6B"
                
                # Update the label
                req_label.configure(text=req_text, text_color=req_color)
                
            except Exception as e:
                print(f"⚠️ Error updating tier {tier_num} requirements: {e}")

    def _recalculate_all_upgrades(self):
        """Recalculate all upgrade effects based on current levels."""

        # === TIER 1: BASE PRODUCTION ===
        tier1_prod = self.upgrade_levels.get('tier1_production', 0)
        tier1_bonus = self.upgrade_levels.get('tier1_bonus', 0)
        base_comets = 1.0 + (tier1_prod * 2) + tier1_bonus

        # === MULTIPLICATIVE MULTIPLIERS (Tier 1-2 for better early game!) ===
        multiplicative_total = 1.0

        # Tier 1: Multiplier (+5% per level, MULTIPLICATIVE!)
        tier1_mult = self.upgrade_levels.get('tier1_multiplier', 0)
        multiplicative_total *= (1.0 + tier1_mult * 0.05)
        
        # Tier 1: Power (+3% per level, MULTIPLICATIVE!)
        tier1_power = self.upgrade_levels.get('tier1_power', 0)
        multiplicative_total *= (1.0 + tier1_power * 0.03)

        # Tier 2: Fire Rate (+8% per level, MULTIPLICATIVE!)
        tier2_fire = self.upgrade_levels.get('tier2_fire', 0)
        multiplicative_total *= (1.0 + tier2_fire * 0.08)
        
        # Tier 2: Efficiency (+4% per level, MULTIPLICATIVE!)
        tier2_coll = self.upgrade_levels.get('tier2_collection', 0)
        multiplicative_total *= (1.0 + tier2_coll * 0.04)

        # === TIER 4: POWER - ALL MULTIPLICATIVE! ===
        # Tier 4: Super Production (+50% per level, MULTIPLICATIVE!)
        tier4_super = self.upgrade_levels.get('tier4_super_prod', 0)
        multiplicative_total *= (1.0 + tier4_super * 0.50)
        
        # Tier 4: Strength (+30% per level, MULTIPLICATIVE!)
        tier4_str = self.upgrade_levels.get('tier4_strength', 0)
        multiplicative_total *= (1.0 + tier4_str * 0.30)
        
        # Tier 4: Mega Power (+40% per level, MULTIPLICATIVE!)
        tier4_mega = self.upgrade_levels.get('tier4_mega', 0)
        multiplicative_total *= (1.0 + tier4_mega * 0.40)
        
        # Tier 4: Thunder Strike (+35% per level, MULTIPLICATIVE!)
        tier4_thunder = self.upgrade_levels.get('tier4_thunder', 0)
        multiplicative_total *= (1.0 + tier4_thunder * 0.35)

        # === TIER 5: MASTERY - ALL MULTIPLICATIVE! ===
        # Tier 5: Growth (+8% per level, MULTIPLICATIVE!)  # Reduced from 15% to 8%
        tier5_growth = self.upgrade_levels.get('tier5_growth', 0)
        multiplicative_total *= (1.0 + tier5_growth * 0.08)
        
        # Tier 5: Efficiency (+6% to ALL MULTIPLICATIVE upgrades)  # Reduced from 10% to 6%
        tier5_eff = self.upgrade_levels.get('tier5_efficiency', 0)
        efficiency_multiplier = 1.0 + (tier5_eff * 0.06)
        multiplicative_total *= efficiency_multiplier

        # === TIER 7: HUGE ADDITIVE BONUSES (for variety) ===
        additive_bonus = 0.0
        
        # Tier 7: Storm (+15% per level, ADDITIVE for big numbers)  # Reduced from 25% to 15%
        additive_bonus += self.upgrade_levels.get('tier7_storm', 0) * 0.15
        
        # Tier 7: Lightning (+12% per level, ADDITIVE for big numbers)  # Reduced from 20% to 12%
        additive_bonus += self.upgrade_levels.get('tier7_lightning', 0) * 0.12
        
        # Apply additive bonuses if any
        if additive_bonus > 0:
            multiplicative_total *= (1.0 + additive_bonus)

        # === TIER 6+: MORE MULTIPLICATIVE ===
        
        # Tier 6: TRUE Multiplier (0.03x per level, multiplicative)  # Reduced from 5% to 3%
        tier6_true = self.upgrade_levels.get('tier6_true_multi', 0)
        multiplicative_total *= (1.0 + tier6_true * 0.03)
        
        # Tier 6: Amplifier (0.025x per level)  # Reduced from 4% to 2.5%
        tier6_amp = self.upgrade_levels.get('tier6_amplifier', 0)
        multiplicative_total *= (1.0 + tier6_amp * 0.025)
        
        # Tier 6: Compounding (0.02x per level)  # Reduced from 3% to 2%
        tier6_comp = self.upgrade_levels.get('tier6_compound', 0)
        multiplicative_total *= (1.0 + tier6_comp * 0.02)
        
        # Tier 6: Synergy (0.025x per level)  # Reduced from 4% to 2.5%
        tier6_syn = self.upgrade_levels.get('tier6_synergy', 0)
        multiplicative_total *= (1.0 + tier6_syn * 0.025)

        # NOTE: tier6_income is intentionally NOT here - it only applies to passive income

        # Tier 7: Exponential Power (1.03^level, EXPONENTIAL but controlled)  # Reduced from 1.05 to 1.03
        tier7_exp = self.upgrade_levels.get('tier7_exponential', 0)
        if tier7_exp > 0:
            multiplicative_total *= (1.03 ** tier7_exp)
        
        # Tier 7: Supernova (1.04^level)  # Reduced from 1.06 to 1.04
        tier7_super = self.upgrade_levels.get('tier7_supernova', 0)
        if tier7_super > 0:
            multiplicative_total *= (1.04 ** tier7_super)
        
        # Tier 7: Inferno (1.02^level)  # Reduced from 1.04 to 1.02
        tier7_inferno = self.upgrade_levels.get('tier7_inferno', 0)
        if tier7_inferno > 0:
            multiplicative_total *= (1.02 ** tier7_inferno)

        # Tier 8: Ultimate Power (1.04^level, ULTIMATE!)  # Reduced from 1.07 to 1.04
        tier8_ult = self.upgrade_levels.get('tier8_ultimate', 0)
        if tier8_ult > 0:
            multiplicative_total *= (1.04 ** tier8_ult)

        # Tier 8: Cosmic Boost (1.03^level)  # Reduced from 1.06 to 1.03
        tier8_cosmic = self.upgrade_levels.get('tier8_cosmic', 0)
        if tier8_cosmic > 0:
            multiplicative_total *= (1.03 ** tier8_cosmic)
        
        # Tier 8: Overdrive (1.025^level)  # Reduced from 1.05 to 1.025
        tier8_over = self.upgrade_levels.get('tier8_overdrive', 0)
        if tier8_over > 0:
            multiplicative_total *= (1.025 ** tier8_over)
        
        # Tier 8: Transcendent (1.03^level)  # Reduced from 1.06 to 1.03
        tier8_trans = self.upgrade_levels.get('tier8_transcendent', 0)
        if tier8_trans > 0:
            multiplicative_total *= (1.03 ** tier8_trans)
        
        # Tier 8: Absolute (1.025^level)  # Reduced from 1.05 to 1.025
        tier8_abs = self.upgrade_levels.get('tier8_absolute', 0)
        if tier8_abs > 0:
            multiplicative_total *= (1.025 ** tier8_abs)

        # Tier 9: GOD MODE (1.08^level - powerful endgame)  # Reduced from 1.15 to 1.08
        tier9_god = self.upgrade_levels.get('tier9_godmode', 0)
        if tier9_god > 0:
            multiplicative_total *= (1.08 ** tier9_god)

        # Tier 9: Infinity (1.10^level)  # Reduced from 1.18 to 1.10
        tier9_inf = self.upgrade_levels.get('tier9_infinity', 0)
        if tier9_inf > 0:
            multiplicative_total *= (1.10 ** tier9_inf)
        
        # Tier 9: Omnipotent (1.09^level)  # Reduced from 1.17 to 1.09
        tier9_omni = self.upgrade_levels.get('tier9_omnipotent', 0)
        if tier9_omni > 0:
            multiplicative_total *= (1.09 ** tier9_omni)
        
        # Tier 9: Eternal (1.10^level)  # Reduced from 1.18 to 1.10
        tier9_eternal = self.upgrade_levels.get('tier9_eternal', 0)
        if tier9_eternal > 0:
            multiplicative_total *= (1.10 ** tier9_eternal)
        
        # Tier 9: Omniscient (1.08^level)  # Reduced from 1.16 to 1.08
        tier9_omnis = self.upgrade_levels.get('tier9_omniscient', 0)
        if tier9_omnis > 0:
            multiplicative_total *= (1.08 ** tier9_omnis)

        # REBIRTH MULTIPLIER (permanent bonus from rebirths)
        multiplicative_total *= self.rebirth_multiplier

        # Final multiplier is already in multiplicative_total
        total_multiplier = multiplicative_total

        # Store for use in collection
        self.comet_multiplier = total_multiplier
        self.base_comets_per_rock = base_comets

        # === SPEED & AUTOMATION ===
        # Tier 2: Speed (+10% per level, capped at 300% for smooth movement)
        tier2_speed = self.upgrade_levels.get('tier2_speed', 0)
        chase_speed_bonus = min(tier2_speed * 0.10, 3.0)  # Cap at 300% to prevent teleporting
        base_speed = 4
        self.auto_trail_speed = base_speed * (1 + chase_speed_bonus)
        
        # === ANIMATION SPEED BOOST ===
        # Calculate total tier progress for animation speed scaling
        total_tier_progress = (
            sum([self.upgrade_levels.get(f'tier1_{k}', 0) for k in ['production', 'multiplier', 'luck', 'bonus', 'power']]) +
            sum([self.upgrade_levels.get(f'tier2_{k}', 0) for k in ['speed', 'spawn', 'rocks', 'fire', 'collection']]) +
            sum([self.upgrade_levels.get(f'tier3_{k}', 0) for k in ['fortune', 'jackpot', 'burst', 'double', 'triple']])
        )
        
        # Animation speed boost: Start fast, get faster with upgrades
        # Base 30ms (33 FPS) -> Scale down to 16ms (62 FPS) with upgrades
        animation_speed_multiplier = 1.0 + (total_tier_progress * 0.02)  # +2% speed per upgrade level
        self.animation_delay_ms = max(16, int(self.base_animation_delay_ms / animation_speed_multiplier))
        
        # Debug output for animation speed
        if total_tier_progress > 0:
            fps = 1000 / self.animation_delay_ms
            print(f"⚡ Animation Speed: {self.animation_delay_ms}ms ({fps:.1f} FPS) | Tier Progress: {total_tier_progress}")

        # Tier 2: Spawn Rate (1000ms base → 50ms max: -38ms per level)
        tier2_spawn = self.upgrade_levels.get('tier2_spawn', 0)
        self.rock_spawn_interval = max(50, int(1000 - (tier2_spawn * 38)))

        # Tier 2: Max Rocks (1 + 2*level)
        tier2_rocks = self.upgrade_levels.get('tier2_rocks', 0)
        self.max_rocks_count = 1 + (tier2_rocks * 2)

        # === LUCK AMPLIFIER ===
        # Tier 1: Lucky Rocks (2% base chance for 2x per level)
        tier1_luck = self.upgrade_levels.get('tier1_luck', 0)
        tier1_luck_base_chance = tier1_luck * 2  # 2% per level

        # Tier 3: Double Power (+10% amplifier to 2x chance per level)
        tier3_double = self.upgrade_levels.get('tier3_double', 0)
        double_amplifier = 1.0 + (tier3_double * 0.10)

        # Tier 3: Lucky Streak (+10% to luck power per level)
        tier3_fortune = self.upgrade_levels.get('tier3_fortune', 0)
        fortune_boost = 1.0 + (tier3_fortune * 0.10)

        # Tier 4: Critical Hit (+20% to ALL luck per level)
        tier4_crit = self.upgrade_levels.get('tier4_critical', 0)
        crit_boost = 1.0 + (tier4_crit * 0.20)

        # Apply efficiency multiplier to luck (multiplicative stacking)
        self.luck_amplifier = fortune_boost * crit_boost * efficiency_multiplier
        
        # Store tier1 base 2x chance and tier3 amplifier separately for collection
        self.tier1_luck_chance = tier1_luck_base_chance
        self.double_luck_amplifier = double_amplifier

        # === PASSIVE INCOME ===
        # Tier 5: Passive Income (5Qa comets/sec per level - maxes at 100Qa/s!)
        tier5_passive = self.upgrade_levels.get('tier5_passive', 0)

        # Tier 6: Income Booster (2^level multiplier to passive)
        tier6_income = self.upgrade_levels.get('tier6_income', 0)
        income_boost = 2 ** tier6_income if tier6_income > 0 else 1

        self.passive_income_rate = tier5_passive * 5000000000000000 * income_boost  # 5Qa per level, max 100Qa/s at level 20

        if self.passive_income_rate > 0 and not hasattr(self, '_passive_income_timer'):
            self._start_passive_income()

        # Enhanced debug output - track tier progression balance
        comets_per_rock = base_comets * total_multiplier
        total_tier_levels = sum(self.upgrade_levels.values())
        
        # Calculate average tier (simplified to avoid complex nested lists)
        tier_weights = 0
        tier_counts = 0
        for tier in range(1, 10):
            tier_total = sum(self.upgrade_levels.get(k, 0) for k in self.upgrade_levels.keys() if f'tier{tier}_' in k)
            tier_weights += tier * tier_total
            tier_counts += tier_total
        avg_tier = tier_weights / max(tier_counts, 1)
        
        print(f"⚡ Power: Base={base_comets:.1f} | Multiplier={total_multiplier:.2e}x | Per Rock={comets_per_rock:.2f} | Rebirth={self.rebirth_multiplier:.1f}x | Avg Tier={avg_tier:.1f}")
        
        # Extra debug for high-tier analysis
        if total_tier_levels >= 50:  # Only show when significant progress
            tier5_plus = sum(self.upgrade_levels.get(k, 0) for k in self.upgrade_levels.keys() if any(f'tier{t}_' in k for t in range(5, 10)))
            print(f"📊 High-Tier Progress: T5-T9 Levels={tier5_plus} | Total Comets={self.rocks_slashed:.2e}")
    
    def _start_passive_income(self):
        """Start passive income generation."""
        self._passive_income_timer = True
        self._passive_income_tick()

    def _passive_income_tick(self):
        """Generate passive income every second."""
        if hasattr(self, '_passive_income_timer'):
            # Use the calculated passive_income_rate from _recalculate_all_upgrades
            if hasattr(self, 'passive_income_rate') and self.passive_income_rate > 0:
                income = self.passive_income_rate
                self.rocks_slashed += income
                self._update_rocks_slashed_counter()
            # Schedule next tick
            self.after(1000, self._passive_income_tick)

    def _close_shop(self):
        """Alias for _hide_shop (for compatibility)."""
        self._hide_shop()

    def _show_stats_panel(self):
        """Show statistics overlay panel."""
        # Check if stats window already exists
        if hasattr(self, 'stats_window') and self.stats_window and self.stats_window.winfo_exists():
            # Window exists, just bring it to front
            self.stats_window.lift()
            self.stats_window.focus_force()
            return

        # Create stats window
        self.stats_window = ctk.CTkToplevel(self)
        self.stats_window.title("⚡ Statistics")
        self.stats_window.geometry("500x600")
        self.stats_window.attributes("-topmost", True)
        self.stats_window.lift()
        self.stats_window.focus_force()

        # Handle window close
        self.stats_window.protocol("WM_DELETE_WINDOW", lambda: self.stats_window.destroy())

        # Main container
        main_frame = ctk.CTkFrame(self.stats_window, fg_color="#1E1E1E")
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # Title
        title = ctk.CTkLabel(
            main_frame,
            text="📊 Your Statistics",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="#FFD700"
        )
        title.pack(pady=(10, 20))

        # Scrollable stats container
        self.stats_container = ctk.CTkScrollableFrame(main_frame, fg_color="#2B2B2B")
        self.stats_container.pack(fill="both", expand=True, padx=10, pady=10)

        # Populate stats with current data
        self._refresh_stats_data()
        self._populate_stats_ui()

        # Close button
        close_btn = ctk.CTkButton(
            main_frame,
            text="Close",
            command=self.stats_window.destroy,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#E74C3C",
            hover_color="#C0392B",
            width=120,
            height=35
        )
        close_btn.pack(pady=10)

    def _populate_stats_ui(self):
        """Populate comprehensive stats display with proper number formatting."""
        if not hasattr(self, 'stats_container') or not self.stats_container:
            return

        # Clear existing widgets
        for widget in self.stats_container.winfo_children():
            widget.destroy()

        # === COLLECTION STATISTICS ===
        self._add_stat_category(self.stats_container, "🎯 Collection Statistics")
        self._add_stat_row(self.stats_container, "Rocks Collected", f"{self.stats['total_rocks_collected']:,}")
        self._add_stat_row(self.stats_container, "Total Comets Earned", self._format_large_number(self.stats['total_comets_earned']))
        self._add_stat_row(self.stats_container, "Current Balance", self._format_large_number(self.rocks_slashed))
        self._add_stat_row(self.stats_container, "Highest Balance Ever", self._format_large_number(self.stats.get('highest_balance_reached', 0)))
        self._add_stat_row(self.stats_container, "Best Single Collection", self._format_large_number(self.stats['highest_single_collection']))

        # Calculate efficiency metrics
        avg_per_rock = self.stats['total_comets_earned'] / max(1, self.stats['total_rocks_collected'])
        current_per_rock = self.base_comets_per_rock * self.comet_multiplier
        self._add_stat_row(self.stats_container, "Lifetime Avg/Rock", self._format_large_number(avg_per_rock))
        self._add_stat_row(self.stats_container, "Current Power/Rock", self._format_large_number(current_per_rock))

        # === LUCK STATISTICS (Independent System) ===
        self._add_stat_category(self.stats_container, "🍀 Luck System Statistics")
        total_procs = (self.stats['double_procs'] + self.stats['triple_procs'] + 
                      self.stats['jackpot_procs'] + self.stats['burst_procs'])
        self._add_stat_row(self.stats_container, "Total Lucky Hits", f"{total_procs:,}")
        
        # Individual luck types with percentages
        if self.stats['total_rocks_collected'] > 0:
            double_rate = (self.stats['double_procs'] / self.stats['total_rocks_collected']) * 100
            triple_rate = (self.stats['triple_procs'] / self.stats['total_rocks_collected']) * 100 
            jackpot_rate = (self.stats['jackpot_procs'] / self.stats['total_rocks_collected']) * 100
            burst_rate = (self.stats['burst_procs'] / self.stats['total_rocks_collected']) * 100
            overall_rate = (total_procs / self.stats['total_rocks_collected']) * 100
            
            self._add_stat_row(self.stats_container, "⚡ Double (2x) Hits", f"{self.stats['double_procs']:,} ({double_rate:.2f}%)")
            self._add_stat_row(self.stats_container, "⚡ Triple (3x) Hits", f"{self.stats['triple_procs']:,} ({triple_rate:.2f}%)")  
            self._add_stat_row(self.stats_container, "⚡ Jackpot (5x) Hits", f"{self.stats['jackpot_procs']:,} ({jackpot_rate:.2f}%)")
            self._add_stat_row(self.stats_container, "💥 Burst Bonuses", f"{self.stats['burst_procs']:,} ({burst_rate:.2f}%)")
            self._add_stat_row(self.stats_container, "🎲 Overall Luck Rate", f"{overall_rate:.2f}%")
        
        # Combo hits (when multiple luck procs trigger at once)
        if self.stats.get('luck_combos_hit', 0) > 0:
            self._add_stat_row(self.stats_container, "🎆 Multi-Luck Combos", f"{self.stats['luck_combos_hit']:,}")

        # === UPGRADE PROGRESSION ===
        self._add_stat_category(self.stats_container, "� Upgrade Progression")
        self._add_stat_row(self.stats_container, "Total Upgrades Bought", f"{self.stats['total_upgrades_purchased']:,}")
        self._add_stat_row(self.stats_container, "Total Comets Invested", self._format_large_number(self.stats['total_comets_spent']))
        
        # Calculate total upgrade levels across all tiers
        total_levels = sum(self.upgrade_levels.values())
        self._add_stat_row(self.stats_container, "Total Upgrade Levels", f"{total_levels:,}")
        self._add_stat_row(self.stats_container, "Highest Tier Reached", f"Tier {self.stats.get('highest_tier_reached', 1)}")
        
        # Most expensive purchase and savings
        if self.stats.get('most_expensive_purchase', 0) > 0:
            self._add_stat_row(self.stats_container, "Most Expensive Purchase", self._format_large_number(self.stats['most_expensive_purchase']))
        if self.stats.get('energy_savings_total', 0) > 0:
            self._add_stat_row(self.stats_container, "Energy Cost Savings", self._format_large_number(self.stats['energy_savings_total']))

        # === TIER BREAKDOWN ===
        self._add_stat_category(self.stats_container, "🏆 Tier Breakdown")
        tier_names = ["Basic", "Speed", "Fortune", "Power", "Mastery", "Multiplicative", "Exponential", "Supreme", "Ascension"]
        
        for tier in range(1, 10):
            tier_key = f'tier{tier}_upgrades'
            tier_count = self.stats.get(tier_key, 0)
            if tier_count > 0 or tier <= 5:  # Always show tiers 1-5, only show 6+ if have upgrades
                tier_name = tier_names[tier-1] if tier <= len(tier_names) else f"Tier {tier}"
                
                # Calculate current levels in this tier
                current_tier_levels = sum([self.upgrade_levels.get(k, 0) for k in self.upgrade_levels.keys() 
                                         if f'tier{tier}_' in k])
                
                self._add_stat_row(self.stats_container, f"T{tier}: {tier_name}", 
                                 f"{tier_count} bought ({current_tier_levels} levels)")

        # === CURRENT POWER ANALYSIS ===
        self._add_stat_category(self.stats_container, "⚡ Current Power Analysis")
        self._add_stat_row(self.stats_container, "Base Production", f"{self.base_comets_per_rock:.2f} comets/rock")
        
        # Format large multipliers appropriately
        if self.comet_multiplier >= 1e6:
            mult_display = self._format_large_number(self.comet_multiplier) + "x"
        else:
            mult_display = f"{self.comet_multiplier:,.2f}x"
        self._add_stat_row(self.stats_container, "Total Multiplier", mult_display)
        
        self._add_stat_row(self.stats_container, "Luck Amplifier", f"{self.luck_amplifier:.2f}x")
        self._add_stat_row(self.stats_container, "Rocks On Screen", f"{self.max_rocks_count}")
        self._add_stat_row(self.stats_container, "Spawn Rate", f"Every {self.rock_spawn_interval}ms")
        
        # Passive income if applicable
        if hasattr(self, 'passive_income_rate') and self.passive_income_rate > 0:
            self._add_stat_row(self.stats_container, "Passive Income/sec", self._format_large_number(self.passive_income_rate))

        # === SESSION & EFFICIENCY ===
        self._add_stat_category(self.stats_container, "📊 Session & Efficiency")
        
        # Session earnings
        session_earnings = self.stats.get('current_session_earnings', 0)
        if session_earnings > 0:
            self._add_stat_row(self.stats_container, "Session Earnings", self._format_large_number(session_earnings))
        
        session_upgrades = self.stats.get('current_session_upgrades', 0)
        if session_upgrades > 0:
            self._add_stat_row(self.stats_container, "Session Upgrades", f"{session_upgrades}")

        # Calculate collection efficiency
        if self.stats['total_rocks_collected'] > 10:  # Only show if meaningful sample
            rocks_per_hour = 0
            if self.stats.get('total_playtime_seconds', 0) > 60:  # At least 1 minute played
                hours_played = self.stats['total_playtime_seconds'] / 3600
                rocks_per_hour = self.stats['total_rocks_collected'] / hours_played
                comets_per_hour = self.stats['total_comets_earned'] / hours_played
                
                self._add_stat_row(self.stats_container, "Rocks/Hour", f"{rocks_per_hour:.1f}")
                self._add_stat_row(self.stats_container, "Comets/Hour", self._format_large_number(comets_per_hour))

        # Total playtime
        if self.stats.get('total_playtime_seconds', 0) > 0:
            hours = self.stats['total_playtime_seconds'] // 3600
            minutes = (self.stats['total_playtime_seconds'] % 3600) // 60
            playtime_str = f"{int(hours)}h {int(minutes)}m" if hours > 0 else f"{int(minutes)}m"
            self._add_stat_row(self.stats_container, "Total Playtime", playtime_str)
    
    def _refresh_stats_data(self):
        """Refresh current stats data before displaying."""
        import time
        
        # Update current balance tracking
        self.stats['current_balance'] = self.rocks_slashed
        
        # Update highest balance if current is higher
        if self.rocks_slashed > self.stats.get('highest_balance_reached', 0):
            self.stats['highest_balance_reached'] = self.rocks_slashed
        
        # Update playtime
        if hasattr(self, '_last_playtime_update'):
            current_time = time.time()
            elapsed = current_time - self._last_playtime_update
            self.stats['total_playtime_seconds'] = self.stats.get('total_playtime_seconds', 0) + elapsed
            self._last_playtime_update = current_time

    def _add_stat_category(self, container, title):
        """Add a category header to stats."""
        label = ctk.CTkLabel(
            container,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color="#3498DB",
            anchor="w"
        )
        label.pack(anchor="w", padx=15, pady=(15, 5))

    def _add_stat_row(self, container, label_text, value_text):
        """Add a stat row."""
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", padx=15, pady=3)

        label = ctk.CTkLabel(
            row,
            text=label_text + ":",
            font=ctk.CTkFont(size=13),
            text_color="#CCCCCC",
            anchor="w"
        )
        label.pack(side="left", fill="x", expand=True)

        value = ctk.CTkLabel(
            row,
            text=value_text,
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#7ED321",
            anchor="e"
        )
        value.pack(side="right")
    
    def _quick_refresh_shop_ui(self):
        """Quick lightweight refresh after purchase - only updates essentials."""
        # Update subtitle with current comet count
        if hasattr(self, 'shop_subtitle') and self.shop_subtitle and self.shop_subtitle.winfo_exists():
            try:
                self.shop_subtitle.configure(text=f"You have {self.rocks_slashed:.1f} Comets")
            except:
                return  # Shop window destroyed, abort refresh

        # Update tier requirement labels (lightweight)
        for tier_num, req_data in self.shop_tier_requirement_labels.items():
            prev_tier_num = req_data['prev_tier_num']
            prev_tier_name = req_data['prev_tier_name']
            required_levels = req_data['required_levels']
            tiers = req_data['tiers']
            label = req_data['label']

            # Calculate current progress
            prev_tier_progress = sum([
                self.upgrade_levels.get(upgrade['type'], 0)
                for upgrade in tiers[prev_tier_num]
            ])

            is_unlocked = prev_tier_progress >= required_levels

            if is_unlocked:
                req_text = f"✅ Unlocked!"
                req_color = "#00FF00"
            else:
                req_text = f"Unlock: Buy {required_levels} {prev_tier_name} upgrades total ({prev_tier_progress}/{required_levels})"
                req_color = "#FF6B6B"

            label.configure(text=req_text, text_color=req_color)

        # Update upgrade widgets (optimized - minimal work)
        for widget_data in self.shop_upgrade_widgets:
            upgrade_type = widget_data['upgrade_type']
            upgrade_data = widget_data['upgrade_data']
            button = widget_data['button']
            title = widget_data['title']
            effect_label = widget_data['effect_label']

            current_level = self.upgrade_levels.get(upgrade_type, 0)
            max_level = upgrade_data.get("max_level", 999)
            is_maxed = current_level >= max_level

            # Check if locked
            is_locked = False
            if "requirement" in upgrade_data:
                try:
                    is_locked = not upgrade_data["requirement"]()
                except:
                    pass

            # Update title
            name_level_text = f"{upgrade_data['name']} Lv.{current_level}"
            if is_maxed:
                name_level_text += " [MAX]"
            title.configure(
                text=name_level_text,
                text_color="#FFD700" if is_maxed else ("#666666" if is_locked else "#FFFFFF")
            )

            # Update effect
            if is_locked:
                effect_text = "🔒"
                effect_color = "#666666"
            elif current_level > 0:
                effect_text = upgrade_data["effect"](current_level)
                effect_color = "#7ED321"
            else:
                effect_text = upgrade_data["effect"](1)
                effect_color = "#666666"
            effect_label.configure(text=effect_text, text_color=effect_color)

            # Update button
            if is_maxed:
                button.configure(
                    text="⭐ MAX",
                    fg_color="#2d5016",
                    text_color="#FFFFFF",
                    state="disabled"
                )
            elif is_locked:
                button.configure(
                    text="🔒 Locked",
                    fg_color="#3a3a3a",
                    text_color="#777777",
                    state="disabled"
                )
            else:
                # Calculate cost with reduction
                cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
                cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))

                # Format cost
                cost_display = self._format_large_number(cost)

                can_afford = self.rocks_slashed >= cost
                button_color = "#4CAF50" if can_afford else "#444444"

                button.configure(
                    text=cost_display,
                    fg_color=button_color,
                    hover_color="#45a049" if can_afford else button_color,
                    text_color="#FFFFFF" if can_afford else "#777777",
                    state="normal" if can_afford else "disabled"
                )

    def _refresh_shop_ui(self):
        """Refresh all shop UI elements without recreating the shop."""
        # Update subtitle with current comet count
        if hasattr(self, 'shop_subtitle') and self.shop_subtitle:
            self.shop_subtitle.configure(text=f"You have {self.rocks_slashed:.1f} Comets")

        # Update tier requirement labels
        for tier_num, req_data in self.shop_tier_requirement_labels.items():
            prev_tier_num = req_data['prev_tier_num']
            prev_tier_name = req_data['prev_tier_name']
            required_levels = req_data['required_levels']
            tiers = req_data['tiers']
            label = req_data['label']

            # Calculate current progress
            prev_tier_progress = sum([
                self.upgrade_levels.get(upgrade['type'], 0)
                for upgrade in tiers[prev_tier_num]
            ])

            is_unlocked = prev_tier_progress >= required_levels

            if is_unlocked:
                req_text = f"✅ Unlocked!"
                req_color = "#00FF00"
            else:
                req_text = f"Unlock: Buy {required_levels} {prev_tier_name} upgrades total ({prev_tier_progress}/{required_levels})"
                req_color = "#FF6B6B"

            label.configure(text=req_text, text_color=req_color)

        # Update all upgrade cards
        for widget_data in self.shop_upgrade_widgets:
            upgrade_type = widget_data['upgrade_type']
            upgrade_data = widget_data['upgrade_data']
            button = widget_data['button']
            title = widget_data['title']
            effect_label = widget_data['effect_label']

            # Get updated level and cost
            current_level = self.upgrade_levels.get(upgrade_type, 0)
            max_level = upgrade_data.get("max_level", 999)

            # Check if locked
            is_locked = False
            if "requirement" in upgrade_data:
                try:
                    is_locked = not upgrade_data["requirement"]()
                except:
                    pass

            # Check if maxed
            is_maxed = current_level >= max_level

            # Calculate cost with reduction
            cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
            cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))

        # Format cost for display with proper number abbreviations
        cost_display = self._format_large_number(cost)
        
        # Update title (name + level)
        name_level_text = f"{upgrade_data['name']} Lv.{current_level}"
        if is_maxed:
            name_level_text += " [MAX]"

        title.configure(
            text=name_level_text,
            text_color="#FFD700" if is_maxed else ("#666666" if is_locked else "#FFFFFF")
        )

        # Update effect label
        if is_locked:
            effect_text = "🔒"
            effect_color = "#666666"
        elif current_level > 0:
            effect_text = upgrade_data["effect"](current_level)
            effect_color = "#7ED321"
        else:
            effect_text = upgrade_data["effect"](1)  # Show level 1 effect
            effect_color = "#666666"

        effect_label.configure(text=effect_text, text_color=effect_color)

        # Update button
        can_afford = self.rocks_slashed >= cost and not is_locked and not is_maxed

        if is_maxed:
            button_text = "⭐ MAX"
            button_color = "#2d5016"
        elif is_locked:
            button_text = "⚡ Locked"
            button_color = "#3a3a3a"
        else:
            button_text = f"{cost_display}"
            button_color = "#4CAF50" if can_afford else "#444444"

        button.configure(
            text=button_text,
            fg_color=button_color,
            hover_color="#45a049" if can_afford and not is_maxed else button_color,
            text_color="#FFFFFF" if can_afford or is_maxed else "#777777",
            state="normal" if can_afford else "disabled"
        )
    
    def _update_shop_buttons(self):
        """Update shop button states based on current comet count (lightweight version)."""
        # Safety check: Skip if shop widgets don't exist or window is destroyed
        if not hasattr(self, 'shop_upgrade_widgets'):
            return
        
        for widget_data in self.shop_upgrade_widgets:
            upgrade_type = widget_data['upgrade_type']
            upgrade_data = widget_data['upgrade_data']
            button = widget_data['button']
            
            # Safety check: Skip if button was destroyed
            try:
                if not button.winfo_exists():
                    continue
            except:
                continue

            # Calculate current cost (tier5_energy: -2% per level, max 50%)
            current_level = self.upgrade_levels.get(upgrade_type, 0)
            cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
            cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))

            # Update button state based on affordability
            can_afford = self.rocks_slashed >= cost
            try:
                button.configure(
                    fg_color="#4CAF50" if can_afford else "#666666",
                    hover_color="#45a049" if can_afford else "#555555",
                    state="normal" if can_afford else "disabled"
                )
            except:
                # Button was destroyed, skip
                continue

    def _schedule_shop_refresh(self):
        """Schedule automatic shop refresh with proper button updates."""
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            # Force full shop refresh including button states
            self._execute_shop_refresh_batch()
            # Schedule next refresh in 500ms
            self.after(500, self._schedule_shop_refresh)
    
    def _schedule_shop_refresh_optimized(self):
        """Optimized shop refresh with batching and throttling."""
        if not hasattr(self, '_pending_shop_refresh'):
            self._pending_shop_refresh = False
        
        if self._pending_shop_refresh:
            return  # Already scheduled
        
        self._pending_shop_refresh = True
        
        # Batch the refresh to happen after a short delay
        self.after(50, self._execute_shop_refresh_batch)
        
        # Also schedule continuous refresh while shop is open (less frequent)
        if hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists():
            # Continue refreshing every 1000ms for background updates
            self.after(1000, self._schedule_shop_refresh_optimized)
    
    def _instant_shop_refresh_with_debounce(self):
        """Instant refresh with 500ms debounce for spam-click protection."""
        import time
        current_time = time.time()
        
        # Initialize debounce tracking
        if not hasattr(self, '_last_instant_refresh'):
            self._last_instant_refresh = 0
        if not hasattr(self, '_pending_debounce_refresh'):
            self._pending_debounce_refresh = False
        
        # If enough time has passed since last refresh, do instant refresh
        if current_time - self._last_instant_refresh >= 0.5:  # 500ms cooldown
            self._last_instant_refresh = current_time
            self._execute_shop_refresh_batch()  # Instant refresh
            
        # Always schedule a debounced refresh for spam-click scenarios
        if not self._pending_debounce_refresh:
            self._pending_debounce_refresh = True
            self.after(500, self._execute_debounced_refresh)
    
    def _execute_debounced_refresh(self):
        """Execute refresh after debounce period ends."""
        import time
        self._pending_debounce_refresh = False
        self._last_instant_refresh = time.time()
        self._execute_shop_refresh_batch()
    
    def _execute_shop_refresh_batch(self):
        """Execute the batched shop refresh operations."""
        self._pending_shop_refresh = False
        
        # Check if shop window exists
        if not (hasattr(self, 'shop_window') and self.shop_window and self.shop_window.winfo_exists()):
            return
        
        # Only do lightweight updates
        try:
            # Update subtitle
            if hasattr(self, 'shop_subtitle') and self.shop_subtitle and self.shop_subtitle.winfo_exists():
                if self.rocks_slashed >= 1000000:
                    shop_text = f"You have {self.rocks_slashed/1000000:.2f}M Comets"
                elif self.rocks_slashed >= 1000:
                    shop_text = f"You have {self.rocks_slashed/1000:.2f}K Comets"
                else:
                    shop_text = f"You have {self.rocks_slashed:.2f} Comets"
                self.shop_subtitle.configure(text=shop_text)
            
            # Update ALL upgrade button states, not just first 10
            if hasattr(self, 'shop_upgrade_widgets') and self.shop_upgrade_widgets:
                for widget_data in self.shop_upgrade_widgets:  # Update ALL upgrades
                    try:
                        upgrade_type = widget_data.get('upgrade_type')
                        upgrade_data = widget_data.get('upgrade_data')
                        button = widget_data.get('button')
                        
                        if not upgrade_type or not upgrade_data or not button:
                            continue
                        
                        # Ensure button still exists
                        if not button.winfo_exists():
                            continue
                        
                        current_level = self.upgrade_levels.get(upgrade_type, 0)
                        max_level = upgrade_data.get("max_level", 999)
                        
                        # Check if maxed
                        is_maxed = current_level >= max_level
                        
                        # Update title with current level
                        title_label = widget_data.get('title')
                        if title_label and title_label.winfo_exists():
                            name_level_text = f"{upgrade_data['name']} Lv.{current_level}"
                            if is_maxed:
                                name_level_text += " [MAX]"
                            title_label.configure(
                                text=name_level_text,
                                text_color="#FFD700" if is_maxed else "#FFFFFF"
                            )
                        
                        # Update effect text
                        effect_label = widget_data.get('effect_label')
                        if effect_label and effect_label.winfo_exists():
                            if current_level > 0:
                                effect_text = upgrade_data["effect"](current_level)
                                effect_label.configure(
                                    text=effect_text,
                                    text_color="#7ED321"
                                )
                            else:
                                effect_text = upgrade_data["effect"](1)  # Show level 1 effect
                                effect_label.configure(
                                    text=effect_text,
                                    text_color="#666666"
                                )
                        
                        if is_maxed:
                            # Show as maxed out
                            button.configure(
                                fg_color="#FFD700",  # Gold color for maxed
                                state="disabled",
                                text="⭐ MAX"
                            )
                        else:
                            # Calculate cost with reductions
                            cost_reduction = min(self.upgrade_levels.get('tier5_energy', 0) * 0.02, 0.50)
                            cost = int(upgrade_data["base_cost"] * (upgrade_data["scaling"] ** current_level) * (1 - cost_reduction))
                            
                            can_afford = self.rocks_slashed >= cost
                            
                            # Format cost display using comprehensive formatter
                            cost_display = self._format_large_number(cost)
                            

                            # Update button with new cost and state
                            button.configure(
                                fg_color="#4CAF50" if can_afford else "#666666",
                                state="normal" if can_afford else "disabled",
                                text=cost_display,
                                hover_color="#45a049" if can_afford else "#666666",
                                text_color="#FFFFFF" if can_afford else "#777777"
                            )
                        
                    except Exception as e:
                        continue
            
            # Update tier requirement labels
            if hasattr(self, 'tier_requirement_labels'):
                tier_names = {
                    1: "Tier 1", 2: "Tier 2", 3: "Tier 3", 4: "Tier 4", 5: "Tier 5",
                    6: "Tier 6", 7: "Tier 7", 8: "Tier 8", 9: "Tier 9", 10: "Tier 10"
                }
                
                for tier_num, req_label in self.tier_requirement_labels.items():
                    if tier_num <= 1:  # Tier 1 has no requirements
                        continue
                        
                    try:
                        prev_tier_num = tier_num - 1
                        prev_tier_name = tier_names.get(prev_tier_num, f"Tier {prev_tier_num}")
                        
                        # Calculate progress for previous tier
                        tier_keys = {
                            1: ['production', 'multiplier', 'luck', 'bonus', 'power'],
                            2: ['speed', 'spawn', 'rocks', 'fire', 'collection'],
                            3: ['fortune', 'jackpot', 'burst', 'double', 'triple'],
                            4: ['super_prod', 'strength', 'critical', 'mega', 'thunder'],
                            5: ['passive', 'efficiency', 'energy', 'growth', 'recycler'],
                            6: ['true_multi', 'income', 'amplifier', 'compound', 'synergy'],
                            7: ['exponential', 'supernova', 'storm', 'inferno', 'lightning'],
                            8: ['ultimate', 'cosmic', 'overdrive', 'transcendent', 'absolute'],
                            9: ['godmode', 'infinity', 'omnipotent', 'eternal', 'omniscient']
                        }
                        
                        prev_keys = tier_keys.get(prev_tier_num, [])
                        prev_tier_progress = sum([self.upgrade_levels.get(f'tier{prev_tier_num}_{k}', 0) for k in prev_keys])
                        
                        # Define requirements
                        required_levels = 15 + (prev_tier_num - 1) * 10  # 15, 25, 35, etc.
                        
                        is_unlocked = prev_tier_progress >= required_levels
                        
                        if is_unlocked:
                            req_text = f"✅ Unlocked!"
                            req_color = "#00FF00"
                        else:
                            req_text = f"Unlock: Buy {required_levels} {prev_tier_name} upgrades total ({prev_tier_progress}/{required_levels})"
                            req_color = "#FF6B6B"
                        
                        # Update the label
                        if req_label and req_label.winfo_exists():
                            req_label.configure(text=req_text, text_color=req_color)
                    except:
                        continue
                        
        except:
            pass  # Shop window destroyed or error occurred
    
    def _on_auto_slash_toggle(self):
        """Called when auto collect checkbox is toggled."""
        enabled = self.auto_slash_var.get()
        print(f"Auto Collect {'enabled' if enabled else 'disabled'}")
        
        if not enabled:
            # Clear auto trail when disabled
            for element in self.auto_trail_elements:
                self.canvas.delete(element['id'])
            self.auto_trail_elements = []
            
            # Enable hover interaction for all existing rocks when auto collect is disabled
            for rock in self.active_rocks:
                self.canvas.tag_bind(rock['id'], "<Enter>", lambda e, r=rock: self._slash_rock(r))
        else:
            # Initialize trail head position at center of screen when enabled
            c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            self.auto_trail_head_x = c_w // 2 if c_w > 0 else 400
            self.auto_trail_head_y = c_h // 2 if c_h > 0 else 300
            
            # Disable hover interaction for all existing rocks when auto Collect is enabled
            for rock in self.active_rocks:
                self.canvas.tag_unbind(rock['id'], "<Enter>")
    
    def _on_fisch_gui_toggle(self):
        """Called when Fisch GUI toggle checkbox is changed."""
        enabled = self.fisch_gui_enabled_var.get()
        print(f"Fisch GUI {'enabled' if enabled else 'disabled'}")
        self._toggle_fisch_gui_elements(enabled)
    
    def _toggle_fisch_gui_elements(self, enabled):
        """Show or hide Fisch GUI elements (rotary wheel, flow arrows, bottom buttons)."""
        if enabled:
            # Show Fisch GUI elements
            if hasattr(self, 'central_label') and self.central_label:
                self.central_label.place(relx=0.5, rely=0.5, anchor="center")
            
            # Show menu tabs (rotary wheel) - stored in tab_items
            if hasattr(self, 'tab_items'):
                for tab_data in self.tab_items:
                    if 'icon_id' in tab_data:
                        self.canvas.itemconfigure(tab_data['icon_id'], state='normal')
                    if 'text_id' in tab_data:
                        self.canvas.itemconfigure(tab_data['text_id'], state='normal')
            
            # Show flow arrows
            if hasattr(self, 'flow_arrows'):
                for arrow_id in self.flow_arrows:
                    self.canvas.itemconfigure(arrow_id, state='normal')
            
            # Show bottom buttons
            if hasattr(self, 'bottom_buttons'):
                for button_data in self.bottom_buttons:
                    if 'rect_id' in button_data:
                        self.canvas.itemconfigure(button_data['rect_id'], state='normal')
                    if 'text_id' in button_data:
                        self.canvas.itemconfigure(button_data['text_id'], state='normal')
        else:
            # Hide Fisch GUI elements
            if hasattr(self, 'central_label') and self.central_label:
                self.central_label.place_forget()
            
            # Hide menu tabs (rotary wheel)
            if hasattr(self, 'tab_items'):
                for tab_data in self.tab_items:
                    if 'icon_id' in tab_data:
                        self.canvas.itemconfigure(tab_data['icon_id'], state='hidden')
                    if 'text_id' in tab_data:
                        self.canvas.itemconfigure(tab_data['text_id'], state='hidden')
            
            # Hide flow arrows
            if hasattr(self, 'flow_arrows'):
                for arrow_id in self.flow_arrows:
                    self.canvas.itemconfigure(arrow_id, state='hidden')
            
            # Hide bottom buttons (they are canvas items, not widgets)
            if hasattr(self, 'bottom_buttons'):
                for button_data in self.bottom_buttons:
                    if 'rect_id' in button_data:
                        self.canvas.itemconfigure(button_data['rect_id'], state='hidden')
                    if 'text_id' in button_data:
                        self.canvas.itemconfigure(button_data['text_id'], state='hidden')
    
    def _on_minigame_toggle(self):
        """Called when minigame toggle checkbox is changed."""
        enabled = self.minigame_enabled_var.get()
        print(f"Comet Minigame {'enabled' if enabled else 'disabled'}")
        self._toggle_minigame_elements(enabled)
    
    def _toggle_minigame_elements(self, enabled):
        """Show or hide all minigame elements."""
        if enabled:
            # Show minigame elements
            if self.rocks_slashed_label_id:
                self.canvas.itemconfigure(self.rocks_slashed_label_id, state='normal')
            
            # Use position update methods to respect app_state
            self._update_auto_slash_checkbox_position()
            self._update_shop_button_position()
            
            # Enable star animations
            self.animations_running = True
        else:
            # Hide minigame elements
            if self.rocks_slashed_label_id:
                self.canvas.itemconfigure(self.rocks_slashed_label_id, state='hidden')
            if self.auto_slash_checkbox:
                self.auto_slash_checkbox.place_forget()
            if hasattr(self, 'shop_button') and self.shop_button:
                self.shop_button.place_forget()
            
            # Close shop if open
            if hasattr(self, 'shop_frame') and self.shop_frame:
                self._close_shop()
            
            # Clear all rocks if they exist
            for rock in self.active_rocks[:]:  # Use slice to safely iterate
                self.canvas.delete(rock['id'])
            self.active_rocks.clear()
            
            # Clear auto trail immediately (it's red and distracting)
            for element in self.auto_trail_elements:
                self.canvas.delete(element['id'])
            self.auto_trail_elements = []
            
            # Clear comet trail particles immediately
            for particle in self.comet_trail_particles[:]:
                self.canvas.delete(particle['id'])
            self.comet_trail_particles.clear()
            
            # Don't clear stars or trail_elements - let them fade out naturally
            # The animate_stars() and animate_trail() functions will handle the fadeout
    
    def _cleanup_excessive_particles(self):
        """Cleanup particles if they exceed safe limits (memory management)."""
        max_safe_particles = 100  # Safety limit to prevent memory issues
        
        # Cleanup nebula particles if too many
        if hasattr(self, 'nebula_particles') and len(self.nebula_particles) > max_safe_particles:
            excess = len(self.nebula_particles) - max_safe_particles
            for _ in range(excess):
                if self.nebula_particles:
                    particle = self.nebula_particles.pop(0)
                    if 'id' in particle:
                        self.canvas.delete(particle['id'])
        
        # Cleanup animation comets if too many
        if hasattr(self, 'animation_comets') and len(self.animation_comets) > max_safe_particles:
            excess = len(self.animation_comets) - max_safe_particles
            for _ in range(excess):
                if self.animation_comets:
                    comet = self.animation_comets.pop(0)
                    if 'id' in comet:
                        self.canvas.delete(comet['id'])
    
    def _create_auto_trail_dot(self, x, y):
        """Creates a trail dot for auto collect mode."""
        if len(self.auto_trail_elements) >= self.trail_max_elements:
            oldest = self.auto_trail_elements.pop(0)
            self.canvas.delete(oldest['id'])
        
        # Use different color for auto trail (red to distinguish from normal trail)
        # Make it larger and brighter for better visibility
        dot_id = self.canvas.create_oval(x-4, y-4, x+4, y+4, fill="#FF0000", outline="#FFFFFF", width=2)
        # Ensure auto trail is always visible on top of other elements
        self.canvas.tag_raise(dot_id)
        
        self.auto_trail_elements.append({
            'id': dot_id, 'step': 0, 'center_x': x, 'center_y': y,
        })
        
        # Debug logging removed - trail creation is working properly
    
    def _get_auto_trail_color(self, step):
        """Generates color for auto trail (red theme)."""
        if step >= self.auto_trail_lifetime: 
            return "#4A90E2" if self.app_state == 'tab_view' else "#000000"
            
        # Keep auto trail more visible - slower fade and brighter colors
        brightness = int(255 * (1 - (step / self.auto_trail_lifetime) * 0.7))  # Only fade to 30% instead of 0%
        brightness = max(76, min(255, brightness))  # Minimum brightness of 76 (30% of 255)
        
        if self.app_state == 'tab_view':
            # Background is blue, trail starts as bright red and fades to dimmer red
            ratio = brightness / 255.0
            r = int(255 * ratio)
            g = int(50 * ratio)  # Keep some red tint
            b = int(50 * ratio)
            
            return f"#{r:02x}{g:02x}{b:02x}"
        else:
            # Bright red trail fading to dimmer red (more visible than before)
            hex_r = f"{brightness:02x}"
            hex_g = f"{max(32, brightness//4):02x}"  # Some green for visibility
            hex_b = f"{max(32, brightness//4):02x}"  # Some blue for visibility
            return f"#{hex_r}{hex_g}{hex_b}"
    
    def _update_auto_trail(self):
        """Updates auto trail that chases rocks."""
        # Debug: Check why auto trail might not be running
        if hasattr(self, '_auto_trail_debug_counter'):
            self._auto_trail_debug_counter += 1
        else:
            self._auto_trail_debug_counter = 1
            
        # Auto trail debug removed - system is working properly now
        if not self.auto_slash_var.get() or self.app_state != 'menu' or not self.minigame_enabled_var.get():
            return
            
        # Always update trail head position, even without active rocks
        if self.active_rocks:
            # Find the closest rock to the trail head
            closest_rock = None
            min_distance = float('inf')
            
            for rock in self.active_rocks:
                dx = rock['x'] - self.auto_trail_head_x
                dy = rock['y'] - self.auto_trail_head_y
                distance = (dx**2 + dy**2)**0.5
                
                if distance < min_distance:
                    min_distance = distance
                    closest_rock = rock
            
            if closest_rock:
                # Chase the closest rock - move trail head towards it
                rock_x = closest_rock['x']
                rock_y = closest_rock['y']
                
                # Calculate direction vector to rock
                dx = rock_x - self.auto_trail_head_x
                dy = rock_y - self.auto_trail_head_y
                distance = (dx**2 + dy**2)**0.5
                
                if distance > 0:
                    # Normalize direction and apply speed
                    move_x = (dx / distance) * self.auto_trail_speed
                    move_y = (dy / distance) * self.auto_trail_speed
                    
                    # Update trail head position
                    self.auto_trail_head_x += move_x
                    self.auto_trail_head_y += move_y
        else:
            # No rocks - trail moves randomly or stays in place
            # Keep the trail visible by making small random movements
            import random
            self.auto_trail_head_x += random.uniform(-1, 1)
            self.auto_trail_head_y += random.uniform(-1, 1)
            
            # Keep trail within screen bounds
            c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
            if c_w > 0 and c_h > 0:
                self.auto_trail_head_x = max(20, min(c_w - 20, self.auto_trail_head_x))
                self.auto_trail_head_y = max(20, min(c_h - 20, self.auto_trail_head_y))
        
        # Always create trail dot at current head position - auto collect should always be visible!
        self._create_auto_trail_dot(self.auto_trail_head_x, self.auto_trail_head_y)
        
        # Check for collision between trail head and rocks (throttled for performance only)
        self.collision_check_counter += 1
        current_comet_count = len(self.active_rocks)
        
        # Throttle collision detection based on comet count for performance
        collision_check_frequency = 1  # Check every frame by default
        if current_comet_count > 5:
            collision_check_frequency = 3  # Check every 3rd frame with many comets
        elif current_comet_count > 3:
            collision_check_frequency = 2  # Check every 2nd frame with some comets
            
        if self.active_rocks and self.collision_check_counter % collision_check_frequency == 0:
            self._check_trail_rock_collision()
        
        # Animate existing auto trail elements
        elements_to_keep = []
        for element in self.auto_trail_elements:
            element['step'] += 1

            if element['step'] >= self.auto_trail_lifetime:
                self.canvas.delete(element['id'])
                continue
            
            new_color = self._get_auto_trail_color(element['step'])
            size_ratio = 1 - (element['step'] / self.auto_trail_lifetime)
            current_size = self.trail_size * size_ratio
            
            self.canvas.coords(element['id'], 
                              element['center_x'] - current_size/2, 
                              element['center_y'] - current_size/2,
                              element['center_x'] + current_size/2, 
                              element['center_y'] + current_size/2)
            self.canvas.itemconfig(element['id'], fill=new_color)
            
            elements_to_keep.append(element)

        self.auto_trail_elements = elements_to_keep
    
    def _check_trail_rock_collision(self):
        """Checks if auto trail head is colliding with any rock."""
        if not self.active_rocks or not self.auto_slash_var.get():
            return
        
        # Check collision between trail head and each rock
        for rock in self.active_rocks[:]:  # Use slice to safely modify list during iteration
            rock_x = rock['x']
            rock_y = rock['y']
            rock_radius = rock['size'] / 2
            
            # Calculate distance between trail head and rock center
            distance = ((self.auto_trail_head_x - rock_x)**2 + (self.auto_trail_head_y - rock_y)**2)**0.5
            
            if distance < rock_radius + 8:  # Collision buffer
                # Trail head hit this rock - slash it!
                self._slash_rock(rock)
                
                # Don't move trail head - let it continue naturally
                # The comet disappears, trail keeps moving smoothly
                
                # Only slash one rock per frame
                break
    
    def _create_rock(self):
        """Creates a new bouncing rock."""
        # Check max rocks limit from upgrade (default 1)
        max_rocks = getattr(self, 'max_rocks_count', 1 + self.upgrade_levels.get('max_rocks', 0) * 2)
        
        if len(self.active_rocks) >= max_rocks or self.app_state != 'menu' or not self.minigame_enabled_var.get():
            return
            
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 100 or c_h < 100:
            return
            
        # Random starting position (avoiding edges)
        x = random.randint(50, c_w - 50)
        y = random.randint(50, c_h - 50)
        
        # Random velocity (DVD logo style)
        velocity_x = random.choice([-2, -1, 1, 2])
        velocity_y = random.choice([-2, -1, 1, 2])
        
        # Create rock visual (simple emoji)
        rock_id = self.canvas.create_text(
            x, y,
            text="🪨",
            font=("Arial", 20),
            fill="#888888",
            tags="rock"
        )
        
        rock_data = {
            'id': rock_id,
            'x': x,
            'y': y,
            'velocity_x': velocity_x,
            'velocity_y': velocity_y,
            'size': 20
        }
        
        # Bind hover event for slashing (only if auto collect is disabled)
        if not self.auto_slash_var.get():
            self.canvas.tag_bind(rock_id, "<Enter>", lambda e, rock=rock_data: self._slash_rock(rock))
        
        self.active_rocks.append(rock_data)
        
        # Lower rock below UI elements but above stars
        self.canvas.tag_lower(rock_id)
    
    def _create_comet_trail_particle(self, x, y, velocity_x, velocity_y):
        """Creates a single particle for the comet trail with scattering effect."""
        # Add random scatter perpendicular to velocity direction
        scatter_strength = 1.5
        perpendicular_x = -velocity_y * random.uniform(-scatter_strength, scatter_strength)
        perpendicular_y = velocity_x * random.uniform(-scatter_strength, scatter_strength)

        # Particle size varies for depth effect
        size = random.uniform(2, 5)

        # Choose color from gradient
        color = random.choice(self.comet_trail_colors)

        # Create particle as a small oval
        particle_id = self.canvas.create_oval(
            x - size, y - size, x + size, y + size,
            fill=color,
            outline="",
            tags="comet_trail"
        )

        # Store particle data
        particle = {
            'id': particle_id,
            'x': x,
            'y': y,
            'velocity_x': perpendicular_x * 0.3,  # Slower scatter drift
            'velocity_y': perpendicular_y * 0.3,
            'age': 0,
            'size': size,
            'color': color
        }

        # Lower trail particles below rock but above stars
        self.canvas.tag_lower(particle_id)

        return particle

    def _update_comet_trail(self):
        """Updates comet trail particles - creates new ones and animates existing ones (optimized)."""
        # Performance optimization: Only update trail every 3rd frame
        self.comet_trail_update_counter += 1
        if self.comet_trail_update_counter % 3 != 0:
            return
        
        # Performance mode: Disable trail updates when >3 comets on screen
        if len(self.active_rocks) > 3:
            # Just age existing particles faster and remove them
            for particle in self.comet_trail_particles[:]:
                particle['age'] += 3  # Age much faster in performance mode
                if particle['age'] >= self.comet_particle_lifetime:
                    self.canvas.delete(particle['id'])
                    self.comet_trail_particles.remove(particle)
            return
        
        if not self.active_rocks:
            # Fade out existing particles when rocks are gone
            for particle in self.comet_trail_particles[:]:
                particle['age'] += 2  # Age faster when no rocks
                if particle['age'] >= self.comet_particle_lifetime:
                    self.canvas.delete(particle['id'])
                    self.comet_trail_particles.remove(particle)
            return

        # Create trail particles for active rocks (reduced frequency)
        for rock in self.active_rocks:
            # Only spawn particles every 3rd update for performance
            if self.comet_trail_update_counter % 6 == 0:  # Even less frequent spawning
                # Spawn particles slightly behind the rock
                offset_x = -rock['velocity_x'] * random.uniform(3, 8)
                offset_y = -rock['velocity_y'] * random.uniform(3, 8)

                particle = self._create_comet_trail_particle(
                    rock['x'] + offset_x,
                    rock['y'] + offset_y,
                    rock['velocity_x'],
                    rock['velocity_y']
                )
                self.comet_trail_particles.append(particle)

        # Limit number of particles (more aggressive cleanup)
        while len(self.comet_trail_particles) > self.comet_trail_max_particles:
            oldest = self.comet_trail_particles.pop(0)
            self.canvas.delete(oldest['id'])

        # Update existing particles
        for particle in self.comet_trail_particles[:]:
            particle['age'] += 1

            # Apply drift velocity
            particle['x'] += particle['velocity_x']
            particle['y'] += particle['velocity_y']

            # Slow down drift over time
            particle['velocity_x'] *= 0.95
            particle['velocity_y'] *= 0.95

            # Calculate opacity based on age (fade out)
            opacity = 1.0 - (particle['age'] / self.comet_particle_lifetime)

            if particle['age'] >= self.comet_particle_lifetime or opacity <= 0:
                # Remove dead particles
                self.canvas.delete(particle['id'])
                self.comet_trail_particles.remove(particle)
            else:
                # Update particle position
                size = particle['size']
                self.canvas.coords(
                    particle['id'],
                    particle['x'] - size,
                    particle['y'] - size,
                    particle['x'] + size,
                    particle['y'] + size
                )

                # Update opacity by adjusting color with alpha
                # Convert hex color to RGB and back with opacity
                hex_color = particle['color']
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)

                # Blend with black background based on opacity
                r = int(r * opacity)
                g = int(g * opacity)
                b = int(b * opacity)

                new_color = f"#{r:02x}{g:02x}{b:02x}"
                self.canvas.itemconfig(particle['id'], fill=new_color)

    def _slash_rock(self, rock=None):
        """Called when cursor hovers over a rock - destroys it and increases counter."""
        # If no specific rock provided, try to get first rock (for auto collect)
        if rock is None:
            if not self.active_rocks:
                return
            rock = self.active_rocks[0]

        # Check if rock is still in the list (might have been removed already)
        if rock not in self.active_rocks:
            return

        # Remove rock from list and canvas
        self.canvas.delete(rock['id'])
        self.active_rocks.remove(rock)

        # === CALCULATE COMETS EARNED ===
        # Start with base comets
        base = getattr(self, 'base_comets_per_rock', 1.0)

        # Apply main production multiplier
        comets_earned = base * self.comet_multiplier

        # Track what luck procs we got (for visual feedback and stats)
        luck_procs = []
        luck_messages = []

        # Get luck amplifier
        luck_amp = getattr(self, 'luck_amplifier', 1.0)

        # INDEPENDENT LUCK CHECKS - Each can trigger separately!
        
        # Check burst chance (additive bonus) - always independent
        burst_level = self.upgrade_levels.get('tier3_burst', 0)
        if burst_level > 0:
            burst_chance = burst_level * 3 * luck_amp  # No longer capped at 45%
            
            # Handle multiple procs for chances > 100%
            guaranteed_procs = int(burst_chance // 100)
            remaining_chance = burst_chance % 100
            
            total_burst_procs = guaranteed_procs
            if remaining_chance > 0 and random.random() * 100 < remaining_chance:
                total_burst_procs += 1
            
            if total_burst_procs > 0:
                burst_bonus = burst_level * 3 * total_burst_procs
                comets_earned += burst_bonus
                for _ in range(total_burst_procs):
                    luck_procs.append('burst')
                luck_messages.append(f"💥 BURST x{total_burst_procs}! +{burst_bonus:.1f} comets ({burst_chance:.1f}%)")

        # Check for double (tier1_luck base chance + tier3_double amplifier)
        tier1_2x_chance = getattr(self, 'tier1_luck_chance', 0)
        if tier1_2x_chance > 0:
            # Base 2x chance from tier1_luck (2% per level)
            # Amplifier from tier3_double (+10% per level)
            double_amp = getattr(self, 'double_luck_amplifier', 1.0)
            # Final chance = base * amplifier * global luck amplifier
            double_chance = tier1_2x_chance * double_amp * luck_amp
            
            # Handle multiple procs for chances > 100%
            guaranteed_procs = int(double_chance // 100)
            remaining_chance = double_chance % 100
            
            total_double_procs = guaranteed_procs
            if remaining_chance > 0 and random.random() * 100 < remaining_chance:
                total_double_procs += 1
            
            if total_double_procs > 0:
                # Apply additive 2x multipliers (base + 2x + 2x + 2x...)
                # Each proc adds the base amount again
                additional_comets = comets_earned * total_double_procs
                comets_earned += additional_comets
                for _ in range(total_double_procs):
                    luck_procs.append('double')
                luck_messages.append(f"⚡ LUCKY x{total_double_procs}! +{additional_comets:.1f} comets! ({double_chance:.1f}%)")

        # Check for triple - independent of double
        triple_level = self.upgrade_levels.get('tier3_triple', 0)
        if triple_level > 0:
            triple_chance = triple_level * 2 * luck_amp
            
            # Handle multiple procs for chances > 100%
            guaranteed_procs = int(triple_chance // 100)
            remaining_chance = triple_chance % 100
            
            total_triple_procs = guaranteed_procs
            if remaining_chance > 0 and random.random() * 100 < remaining_chance:
                total_triple_procs += 1
            
            if total_triple_procs > 0:
                # Apply additive 3x multipliers (base + 3x + 3x + 3x...)
                # Each proc adds 3x the base amount
                additional_comets = comets_earned * 3 * total_triple_procs
                comets_earned += additional_comets
                for _ in range(total_triple_procs):
                    luck_procs.append('triple')
                luck_messages.append(f"⚡ BIG WIN x{total_triple_procs}! +{additional_comets:.1f} comets! ({triple_chance:.1f}%)")

        # Check jackpot (5x multiplier) - independent of all others
        jackpot_level = self.upgrade_levels.get('tier3_jackpot', 0)
        if jackpot_level > 0:
            jackpot_chance = jackpot_level * luck_amp
            
            # Handle multiple procs for chances > 100%
            guaranteed_procs = int(jackpot_chance // 100)
            remaining_chance = jackpot_chance % 100
            
            total_jackpot_procs = guaranteed_procs
            if remaining_chance > 0 and random.random() * 100 < remaining_chance:
                total_jackpot_procs += 1
            
            if total_jackpot_procs > 0:
                # Apply additive 5x multipliers (base + 5x + 5x + 5x...)
                # Each proc adds 5x the base amount
                additional_comets = comets_earned * 5 * total_jackpot_procs
                comets_earned += additional_comets
                for _ in range(total_jackpot_procs):
                    luck_procs.append('jackpot')
                luck_messages.append(f"⚡ JACKPOT x{total_jackpot_procs}! +{additional_comets:.1f} comets! ({jackpot_chance:.1f}%)")

        # Combine messages if multiple procs
        if len(luck_procs) > 1:
            luck_message = f"🎰 MEGA LUCKY! {' + '.join(luck_messages)}"
        elif len(luck_procs) == 1:
            luck_message = luck_messages[0]
        else:
            luck_message = ""

        # === UPDATE ENHANCED STATISTICS ===
        
        # Basic collection stats
        self.stats['total_rocks_collected'] += 1
        self.stats['total_comets_earned'] += comets_earned
        self.stats['current_session_earnings'] = self.stats.get('current_session_earnings', 0) + comets_earned
        
        # Track record collections
        if comets_earned > self.stats['highest_single_collection']:
            self.stats['highest_single_collection'] = comets_earned
            
        # Update balance tracking
        self.rocks_slashed += comets_earned
        if self.rocks_slashed > self.stats.get('highest_balance_reached', 0):
            self.stats['highest_balance_reached'] = self.rocks_slashed

        # Track luck procs (each type counted independently)
        luck_proc_counts = {}
        for proc in luck_procs:
            luck_proc_counts[proc] = luck_proc_counts.get(proc, 0) + 1
            if proc == 'double':
                self.stats['double_procs'] += 1
            elif proc == 'triple':
                self.stats['triple_procs'] += 1
            elif proc == 'jackpot':
                self.stats['jackpot_procs'] += 1
            elif proc == 'burst':
                self.stats['burst_procs'] += 1
        
        # Track combo hits (when multiple different luck types trigger)
        unique_luck_types = len(set(luck_procs))
        if unique_luck_types > 1:
            self.stats['luck_combos_hit'] = self.stats.get('luck_combos_hit', 0) + 1
            
        # Track collection mode for analysis
        if hasattr(self, 'auto_slash_var') and self.auto_slash_var.get():
            self.stats['auto_collect_time_seconds'] = self.stats.get('auto_collect_time_seconds', 0) + (self.animation_delay_ms / 1000.0)
        else:
            self.stats['manual_collect_time_seconds'] = self.stats.get('manual_collect_time_seconds', 0) + (self.animation_delay_ms / 1000.0)

        self._update_rocks_slashed_counter()

        # Enhanced visual feedback (debug prints removed to reduce spam)
        if luck_procs:
            pass  # Luck messages still processed internally
        # No more comet earning spam in console
    
    def _update_rock_position(self):
        """Updates rock position with DVD logo bouncing behavior."""
        if not self.active_rocks:
            return
            
        c_w, c_h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if c_w < 1 or c_h < 1:
            return
        
        # Update all active rocks
        for rock in self.active_rocks:
            # Update position
            rock['x'] += rock['velocity_x']
            rock['y'] += rock['velocity_y']
            
            # Bounce off walls (DVD logo style)
            half_size = rock['size'] // 2
            
            # Left/right walls
            if rock['x'] - half_size <= 0:
                rock['x'] = half_size
                rock['velocity_x'] = abs(rock['velocity_x'])  # Bounce right
            elif rock['x'] + half_size >= c_w:
                rock['x'] = c_w - half_size
                rock['velocity_x'] = -abs(rock['velocity_x'])  # Bounce left
                
            # Top/bottom walls
            if rock['y'] - half_size <= 0:
                rock['y'] = half_size
                rock['velocity_y'] = abs(rock['velocity_y'])  # Bounce down
            elif rock['y'] + half_size >= c_h:
                rock['y'] = c_h - half_size
                rock['velocity_y'] = -abs(rock['velocity_y'])  # Bounce up
            
            # Update canvas position
            self.canvas.coords(rock['id'], rock['x'], rock['y'])
    
    def animate_rocks(self):
        """Rock animation loop - handles spawning and movement."""
        # Skip animation if bot is running
        if not self.animations_running:
            self.after(self.animation_delay_ms, self.animate_rocks)
            return

        if self.app_state == 'menu':
            # Handle rock spawning timer
            self.rock_spawn_timer += self.animation_delay_ms

            # Spawn new rocks if timer elapsed and under max limit
            if self.rock_spawn_timer >= self.rock_spawn_interval:
                self._create_rock()
                self.rock_spawn_timer = 0

            # Update existing rocks positions
            if self.active_rocks:
                self._update_rock_position()

            # Update comet trail particles
            self._update_comet_trail()
        else:
            # Clean up rocks when not in menu
            for rock in self.active_rocks[:]:
                self.canvas.delete(rock['id'])
            self.active_rocks.clear()
            self.rock_spawn_timer = 0

            # Clean up trail particles when not in menu
            for particle in self.comet_trail_particles[:]:
                self.canvas.delete(particle['id'])
            self.comet_trail_particles.clear()

        # Continue animation loop
        self.after(self.animation_delay_ms, self.animate_rocks)


if __name__ == "__main__":
    print("🎣 Starting IRUS COMET...")
    print(f"Python version: {sys.version}")
    
    # Detect if running as compiled executable (works for both PyInstaller and Nuitka)
    is_compiled = getattr(sys, 'frozen', False) or '__compiled__' in globals()
    print(f"Running as compiled: {is_compiled}")
    
    # Check if this is first launch (no config file)
    # Handle both script and compiled exe paths
    if is_compiled:
        # Running as compiled executable - try exe directory first
        exe_dir = os.path.dirname(sys.executable)
        config_path = os.path.join(exe_dir, "Config.txt")
        
        # Test write permissions
        try:
            test_file = os.path.join(exe_dir, ".write_test")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            print(f"Compiled mode - Config path: {config_path}")
        except (PermissionError, OSError):
            # No write permission - use AppData instead
            appdata = os.path.join(os.getenv('APPDATA'), 'IRUS_COMET')
            os.makedirs(appdata, exist_ok=True)
            config_path = os.path.join(appdata, "Config.txt")
            print(f"Compiled mode (AppData fallback) - Config path: {config_path}")
    else:
        # Running as script
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Config.txt")
        print(f"Script mode - Config path: {config_path}")
    
    is_first_launch = not os.path.exists(config_path)
    print(f"First launch: {is_first_launch}")
    print(f"Config exists: {os.path.exists(config_path)}")
    
    if is_first_launch:
        print("=" * 60)
        print("⚡ FIRST LAUNCH DETECTED")
        print("=" * 60)
        
        # Step 1: Show Terms of Use
        print("\n⚡ Step 1: Showing Terms of Use...")
        root = ctk.CTk()
        root.withdraw()  # Hide root window
        
        terms_dialog = TermsOfUseDialog(root)
        root.wait_window(terms_dialog)
        
        if not terms_dialog.accepted:
            print("❌ Terms of Use declined - exiting")
            root.destroy()
            exit(0)
        
        print("✅ Terms of Use accepted")
        root.destroy()
        
        # Step 2: Auto-subscribe to YouTube
        print("\n⚡ Step 2: Auto-subscribing to YouTube channel...")
        auto_subscribe_to_youtube()
        
        # Step 3: Create minimal config to mark as not first launch
        print("\n⚡ Step 3: Creating initial configuration...")
        try:
            # Calculate default scaled coordinates (same logic as StarryNightApp.__init__)
            import tkinter as tk
            temp_root = tk.Tk()
            current_width = temp_root.winfo_screenwidth()
            current_height = temp_root.winfo_screenheight()
            temp_root.destroy()
            
            reference_width = 2560
            reference_height = 1440
            scale_x = current_width / reference_width
            scale_y = current_height / reference_height
            
            # Default coordinates at 2560x1440
            fish_box_default = {"x1": 765, "y1": 1217, "x2": 1797, "y2": 1255}
            shake_box_default = {"x1": 530, "y1": 235, "x2": 2030, "y2": 900}
            
            # Scale to current resolution
            default_fish_box = {
                "x1": int(fish_box_default["x1"] * scale_x),
                "y1": int(fish_box_default["y1"] * scale_y),
                "x2": int(fish_box_default["x2"] * scale_x),
                "y2": int(fish_box_default["y2"] * scale_y)
            }
            default_shake_box = {
                "x1": int(shake_box_default["x1"] * scale_x),
                "y1": int(shake_box_default["y1"] * scale_y),
                "x2": int(shake_box_default["x2"] * scale_x),
                "y2": int(shake_box_default["y2"] * scale_y)
            }
            
            minimal_config = {
                "first_launch_completed": True,
                "settings": {},
                "global_gui_settings": {},
                "hotkeys": {},
                "fish_box": default_fish_box,
                "shake_box": default_shake_box,
                "bottom_button_states": {},
                "rocks_slashed": 0.0,
                "minigame_state": {},
                "shop_data": {}
            }
            json_str = json.dumps(minimal_config, indent=2)
            encoded = base64.b64encode(json_str.encode()).decode()
            with open(config_path, 'w') as f:
                f.write(encoded)
            print("✅ Initial config created")
        except Exception as e:
            print(f"⚡ Error creating config: {e}")
            import traceback
            traceback.print_exc()
        
        print("\n⚡ Step 4: Launching main application...")
        print("=" * 60)
    
    # Launch main application
    print("⚡ Creating main application window...")
    try:
        app = StarryNightApp()
        print("✅ App created, starting mainloop...")
        app.mainloop()
    except KeyboardInterrupt:
        app.quit_app()
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
    
    print("🎣 IRUS COMET closed")