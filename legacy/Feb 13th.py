# Initialization
from customtkinter import *
import tkinter as tk
from PIL import Image, ImageTk
import os
import glob
# Keyboard and Mouse
from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController
# Mouse Button
from pynput.mouse import Button
# Web browsing
import webbrowser
# Key Listeners
import threading
from pynput.keyboard import Listener as KeyListener, Key
macro_running = False
macro_thread = None
# Key Inputs must be on seperate thread
import threading
# Time
import time
import json
# OpenCV and MSS for pixel search
import cv2
import numpy as np
import mss
# Initialize controllers
keyboard_controller = KeyboardController()
mouse_controller = MouseController()
# Set appearance
set_default_color_theme("blue")
set_appearance_mode("dark")
# from AppKit import NSEvent
# Area Selector
LAST_CONFIG_PATH = "last_config.json"
class DualAreaSelector:
    """Full-screen overlay for selecting both Fish Box and Shake Box simultaneously"""

    def __init__(self, parent, screenshot, shake_area, fish_area, callback):
        self.callback = callback
        self.screenshot = screenshot

        # Create fullscreen window
        self.window = tk.Toplevel(parent)
        self.window = tk.Toplevel(parent)
        self.window.overrideredirect(True)   # borderless
        self.window.attributes('-topmost', True)
        self.window.geometry(
            f"{self.window.winfo_screenwidth()}x{self.window.winfo_screenheight()}+0+0"
        )
        self.window.configure(cursor="cross")
        self.window.attributes('-topmost', True)
        self.window.configure(cursor='cross')

        # Get screen dimensions
        self.screen_width = self.window.winfo_screenwidth()
        self.screen_height = self.window.winfo_screenheight()

        # Create canvas
        self.canvas = tk.Canvas(self.window, width=self.screen_width, height=self.screen_height, highlightthickness=0)
        self.canvas.pack()
        
        # Display screenshot (always frozen mode)
        self.photo = ImageTk.PhotoImage(screenshot)
        self.canvas.create_image(0, 0, image=self.photo, anchor='nw')

        # Initialize box coordinates
        self.shake_x1, self.shake_y1 = shake_area["x"], shake_area["y"]
        self.shake_x2, self.shake_y2 = self.shake_x1 + shake_area["width"], self.shake_y1 + shake_area["height"]
        self.fish_x1, self.fish_y1 = fish_area["x"], fish_area["y"]
        self.fish_x2, self.fish_y2 = self.fish_x1 + fish_area["width"], self.fish_y1 + fish_area["height"]

        # Drawing state
        self.dragging = False
        self.active_box = None
        self.drag_corner = None
        self.resize_threshold = 10

        # Create Shake Box (Red)
        self.shake_rect = self.canvas.create_rectangle(
            self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2,
            outline='#f44336', width=2, fill='#f44336', stipple='gray50'
        )
        shake_label_x = self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2
        self.shake_label = self.canvas.create_text(
            shake_label_x, self.shake_y1 - 20, text="Shake Area",
            font=("Segoe UI", 12, "bold"), fill='#f44336'
        )

        # Create Fish Box (Blue)
        self.fish_rect = self.canvas.create_rectangle(
            self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2,
            outline='#2196F3', width=2, fill='#2196F3', stipple='gray50'
        )
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        self.fish_label = self.canvas.create_text(
            fish_label_x, self.fish_y1 - 20, text="Fish Area",
            font=("Segoe UI", 12, "bold"), fill='#2196F3'
        )

        # Corner handles
        self.fish_handles = []
        self.shake_handles = []
        self.create_all_handles()

        # Zoom window (using OpenCV for better performance)
        self.zoom_window_size = 200
        self.zoom_factor = 4
        self.zoom_capture_size = self.zoom_window_size // self.zoom_factor
        self.info_height = 50
        self.zoom_window_name = 'Zoom View'
        self.zoom_window_created = False
        self.zoom_hwnd = None
        self.zoom_update_job = None  # For scheduled updates
        
        # Track current cursor to avoid unnecessary changes
        self.current_cursor = 'cross'

        # Bind events (canvas only, not window)
        self.canvas.bind('<Button-1>', self.on_mouse_down)
        self.canvas.bind('<B1-Motion>', self.on_mouse_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_mouse_up)
        self.canvas.bind('<Motion>', self.on_mouse_move)
        
        # Close on Escape key
        self.window.bind('<Escape>', lambda e: self.window.destroy())
        
        # Save / Cancel controls
        try:
            btn_frame = tk.Frame(self.window, bg='')
            save_btn = tk.Button(btn_frame, text="Save Areas", command=self._on_save, bg="#333", fg="white")
            cancel_btn = tk.Button(btn_frame, text="Cancel", command=self.close, bg="#333", fg="white")
            save_btn.pack(side="left", padx=4)
            cancel_btn.pack(side="left", padx=4)
            # place at top-right
            self.canvas.create_window(self.screen_width - 20, 20, window=btn_frame, anchor='ne')
        except Exception:
            pass

        # Start zoom window
        self.show_zoom()

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
        else:
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2
            color = '#f44336'
            handles_list = self.shake_handles

        for handle in handles_list:
            self.canvas.delete(handle)
        handles_list.clear()

        corners = [(x1, y1, 'nw'), (x2, y1, 'ne'), (x1, y2, 'sw'), (x2, y2, 'se')]

        for x, y, corner in corners:
            # Outer handle
            handle = self.canvas.create_rectangle(
                x - handle_size, y - handle_size,
                x + handle_size, y + handle_size,
                fill='', outline=color, width=2
            )
            handles_list.append(handle)

            # Corner marker
            corner_marker = self.canvas.create_rectangle(
                x - corner_marker_size, y - corner_marker_size,
                x + corner_marker_size, y + corner_marker_size,
                fill='red', outline='white', width=1
            )
            handles_list.append(corner_marker)

            # Crosshair
            line1 = self.canvas.create_line(x - handle_size, y, x + handle_size, y, fill='yellow', width=1)
            line2 = self.canvas.create_line(x, y - handle_size, x, y + handle_size, fill='yellow', width=1)
            handles_list.append(line1)
            handles_list.append(line2)

    def get_corner_at_position(self, x, y, box_type):
        """Determine which corner is near the cursor"""
        if box_type == 'fish':
            x1, y1, x2, y2 = self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2
        else:
            x1, y1, x2, y2 = self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2

        corners = {'nw': (x1, y1), 'ne': (x2, y1), 'sw': (x1, y2), 'se': (x2, y2)}
        
        for corner, (cx, cy) in corners.items():
            if abs(x - cx) < self.resize_threshold and abs(y - cy) < self.resize_threshold:
                return corner
        return None

    def is_inside_box(self, x, y, box_type):
        """Check if point is inside a specific box"""
        if box_type == 'fish':
            return self.fish_x1 < x < self.fish_x2 and self.fish_y1 < y < self.fish_y2
        else:
            return self.shake_x1 < x < self.shake_x2 and self.shake_y1 < y < self.shake_y2

    def on_mouse_down(self, event):
        """Handle mouse button press"""
        self.drag_start_x = event.x
        self.drag_start_y = event.y

        for box in ['fish', 'shake']:
            corner = self.get_corner_at_position(event.x, event.y, box)
            if corner:
                self.dragging = True
                self.active_box = box
                self.drag_corner = corner
                return

            if self.is_inside_box(event.x, event.y, box):
                self.dragging = True
                self.active_box = box
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
                self.fish_x1, self.fish_y1 = event.x, event.y
            elif self.drag_corner == 'ne':
                self.fish_x2, self.fish_y1 = event.x, event.y
            elif self.drag_corner == 'sw':
                self.fish_x1, self.fish_y2 = event.x, event.y
            elif self.drag_corner == 'se':
                self.fish_x2, self.fish_y2 = event.x, event.y

            if self.fish_x1 > self.fish_x2:
                self.fish_x1, self.fish_x2 = self.fish_x2, self.fish_x1
            if self.fish_y1 > self.fish_y2:
                self.fish_y1, self.fish_y2 = self.fish_y2, self.fish_y1
        else:
            if self.drag_corner == 'move':
                self.shake_x1 += dx
                self.shake_y1 += dy
                self.shake_x2 += dx
                self.shake_y2 += dy
            elif self.drag_corner == 'nw':
                self.shake_x1, self.shake_y1 = event.x, event.y
            elif self.drag_corner == 'ne':
                self.shake_x2, self.shake_y1 = event.x, event.y
            elif self.drag_corner == 'sw':
                self.shake_x1, self.shake_y2 = event.x, event.y
            elif self.drag_corner == 'se':
                self.shake_x2, self.shake_y2 = event.x, event.y

            if self.shake_x1 > self.shake_x2:
                self.shake_x1, self.shake_x2 = self.shake_x2, self.shake_x1
            if self.shake_y1 > self.shake_y2:
                self.shake_y1, self.shake_y2 = self.shake_y2, self.shake_y1

        self.update_boxes()
        self.drag_start_x = event.x
        self.drag_start_y = event.y

    def on_mouse_up(self, event):
        """Handle mouse button release"""
        self.dragging = False
        self.active_box = None
        self.drag_corner = None

    def on_mouse_move(self, event):
        """Handle mouse movement"""
        fish_corner = self.get_corner_at_position(event.x, event.y, 'fish')
        shake_corner = self.get_corner_at_position(event.x, event.y, 'shake')

        # Determine what cursor should be shown
        new_cursor = 'cross'
        if fish_corner or shake_corner:
            corner = fish_corner or shake_corner
            cursors = {'nw': 'top_left_corner', 'ne': 'top_right_corner',
                      'sw': 'bottom_left_corner', 'se': 'bottom_right_corner'}
            new_cursor = cursors.get(corner, 'cross')
        elif self.is_inside_box(event.x, event.y, 'fish') or self.is_inside_box(event.x, event.y, 'shake'):
            new_cursor = 'fleur'
        
        # Only update cursor if it actually changed
        if new_cursor != self.current_cursor:
            self.window.configure(cursor=new_cursor)
            self.current_cursor = new_cursor

    def show_zoom(self):
        """Create Tk-based zoom window (cross-platform)"""
        if hasattr(self, "zoom_window"):
            return

        self.zoom_window = tk.Toplevel(self.window)
        self.zoom_window.overrideredirect(True)
        self.zoom_window.attributes("-topmost", True)

        size = self.zoom_window_size
        self.zoom_canvas = tk.Canvas(
            self.zoom_window,
            width=size,
            height=size + self.info_height,
            highlightthickness=0,
            bg="#2b2b2b"
        )
        self.zoom_canvas.pack()

        self._update_zoom_loop()

    def _update_zoom_loop(self):
        if not self.window.winfo_exists():
            return

        # Get cursor position (cross-platform)
        cursor_x = self.window.winfo_pointerx()
        cursor_y = self.window.winfo_pointery()

        half = self.zoom_capture_size // 2
        left = max(0, cursor_x - half)
        top = max(0, cursor_y - half)

        if left + self.zoom_capture_size > self.screen_width:
            left = self.screen_width - self.zoom_capture_size
        if top + self.zoom_capture_size > self.screen_height:
            top = self.screen_height - self.zoom_capture_size

        # Crop frozen screenshot
        cropped = self.screenshot.crop(
            (left, top, left + self.zoom_capture_size, top + self.zoom_capture_size)
        )

        # Resize (nearest neighbor)
        zoomed = cropped.resize(
            (self.zoom_window_size, self.zoom_window_size),
            Image.NEAREST
        )

        self.zoom_photo = ImageTk.PhotoImage(zoomed)

        self.zoom_canvas.delete("all")
        self.zoom_canvas.create_image(0, 0, image=self.zoom_photo, anchor="nw")

        # Crosshair
        c = self.zoom_window_size // 2
        self.zoom_canvas.create_line(c - 10, c, c + 10, c, fill="red", width=2)
        self.zoom_canvas.create_line(c, c - 10, c, c + 10, fill="red", width=2)

        # Color info
        px = zoomed.getpixel((c, c))
        color_text = f"RGB: {px}"
        pos_text = f"Pos: ({cursor_x}, {cursor_y})"

        self.zoom_canvas.create_text(
            10, self.zoom_window_size + 15,
            text=pos_text, anchor="w", fill="white", font=("Segoe UI", 9)
        )
        self.zoom_canvas.create_text(
            10, self.zoom_window_size + 35,
            text=color_text, anchor="w", fill="white", font=("Segoe UI", 9)
        )

        # Move zoom window near cursor
        offset = 30
        zx = cursor_x + offset
        zy = cursor_y + offset

        if zx + self.zoom_window_size > self.screen_width:
            zx = cursor_x - self.zoom_window_size - offset
        if zy + self.zoom_window_size > self.screen_height:
            zy = cursor_y - self.zoom_window_size - offset

        self.zoom_window.geometry(f"+{zx}+{zy}")

        self.window.after(33, self._update_zoom_loop)

    def update_boxes(self):
        """Update both boxes and their labels"""
        self.canvas.coords(self.shake_rect, self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2)
        self.canvas.coords(self.shake_label, self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2, self.shake_y1 - 20)

        self.canvas.coords(self.fish_rect, self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2)
        self.canvas.coords(self.fish_label, self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2, self.fish_y1 - 20)

        self.create_all_handles()
    def _on_save(self):
        """Collect current areas and invoke callback, then close."""
        try:
            shake = {
                "x": int(self.shake_x1),
                "y": int(self.shake_y1),
                "width": int(self.shake_x2 - self.shake_x1),
                "height": int(self.shake_y2 - self.shake_y1)
            }

            fish = {
                "x": int(self.fish_x1),
                "y": int(self.fish_y1),
                "width": int(self.fish_x2 - self.fish_x1),
                "height": int(self.fish_y2 - self.fish_y1)
            }

            if callable(self.callback):
                try:
                    self.callback(shake, fish)
                except Exception:
                    pass
        finally:
            try:
                self.close()
            except:
                pass
    def close(self):
        try:
            if self.zoom_window and self.zoom_window.winfo_exists():
                self.zoom_window.destroy()
        except:
            pass

        if self.window.winfo_exists():
            self.window.destroy()

# Main app
class App(CTk):
    def __init__(self):
        super().__init__()
        self.vars = {}     # Entry / Slider / Combobox vars
        self.vars = {}        # IntVar / StringVar / BooleanVar
        self.checkboxes = {}   # CTkCheckBox vars
        self.comboboxes = {}   # CTkComboBox vars
        
        # Screen size (cache once – thread safe)
        self.SCREEN_WIDTH = self.winfo_screenwidth()
        self.SCREEN_HEIGHT = self.winfo_screenheight()

        # Window 
        self.geometry("800x550")
        self.title("I Can't Fish V2.1")

        # Macro state
        self.macro_running = False
        self.macro_thread = None

        # PID state variables
        self.pid_integral = 0.0
        self.prev_error = 0.0
        self.last_time = None
        self.prev_measurement = None
        self.filtered_derivative = 0.0
        self.last_bar_size = None

        # Arrow-based box estimation variables
        self.last_indicator_x = None
        self.last_holding_state = None
        self.estimated_box_length = None
        self.last_left_x = None
        self.last_right_x = None
        self.last_known_box_center_x = None
        # Minigame overlay window and canvas
        self.minigame_window = None
        self.minigame_canvas = None
        self.pid_source = None  # "bar" or "arrow"

        # Hotkey variables
        self.hotkey_start = Key.f5
        self.hotkey_stop = Key.f7
        self.hotkey_reserved = Key.f8
        self.hotkey_labels = {}  # Store label widgets for dynamic updates

        # Start hotkey listener
        self.key_listener = KeyListener(on_press=self.on_key_press)
        self.key_listener.daemon = True
        self.key_listener.start()

        # Status Bar 
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Logo Label
        logo_label = CTkLabel(
            self, 
            text="I CAN'T FISH V2.1",
            font=CTkFont(size=16, weight="bold")
        )
        logo_label.grid(row=0, column=0, columnspan=6, pady=5, padx=20, sticky="w")
        
        # Status Label 
        self.status_label = CTkLabel(self, text="Macro status: Idle") 
        self.status_label.grid(row=1, column=0, columnspan=6, pady=5, padx=20, sticky="w")
        # Tabs 
        self.tabs = CTkTabview(
            self,
            anchor="w",
        )

        self.tabs.grid(
            row=2, column=0,
            padx=20, pady=10,
            sticky="nsew"
        )

        self.tabs.add("Basic")
        self.tabs.add("Misc")
        self.tabs.add("Shake")
        self.tabs.add("Minigame")
        self.tabs.add("Support")

        # Build tabs
        self.build_basic_tab(self.tabs.tab("Basic"))
        self.build_misc_tab(self.tabs.tab("Misc"))
        self.build_shake_tab(self.tabs.tab("Shake"))
        self.build_minigame_tab(self.tabs.tab("Minigame"))
        self.build_support_tab(self.tabs.tab("Support"))

        # Grid behavior
        self.grid_columnconfigure(0, weight=1)

        self.grid_rowconfigure(0, weight=0)  # Logo
        self.grid_rowconfigure(1, weight=0)  # Status
        self.grid_rowconfigure(2, weight=1)  # Tabs take remaining space

        last = self.load_last_config_name()
        self.bar_areas = {"fish": None, "shake": None}
        self.load_misc_settings()
        self.load_settings(last or "default.json")
        self.init_minigame_window()
        self.show_minigame()
        # Arrow variables
        self.initial_bar_size = None
        # Utility variables
        self.area_selector = None
    # BASIC SETTINGS TAB
    def build_basic_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        #  Configs 
        configs = CTkFrame(scroll, border_width=2)
        configs.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(configs, text="Basic Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(configs, text="Rod Type:").grid(
            row=1, column=0, padx=12, pady=6, sticky="w"
        )

        config_list = self.load_configs()
        config_var = StringVar(value=config_list[0] if config_list else "default.json")
        self.vars["active_config"] = config_var
        config_cb = CTkComboBox(
            configs,
            values=config_list,
            variable=config_var,
            command=lambda v: self.load_settings(v)
        )
        config_cb.grid(row=1, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["active_config"] = config_cb

        CTkLabel(configs, text="Start Key").grid(
            row=2, column=0, padx=12, pady=6, sticky="w"
        )
        CTkLabel(configs, text="Stop Key").grid(
            row=3, column=0, padx=12, pady=6, sticky="w"
        )
        self.hotkey_labels["start"] = CTkLabel(configs, text=self._get_key_name(self.hotkey_start))
        self.hotkey_labels["start"].grid(
            row=2, column=1, padx=12, pady=6, sticky="w"
        )
        self.hotkey_labels["stop"] = CTkLabel(configs, text=self._get_key_name(self.hotkey_stop))
        self.hotkey_labels["stop"].grid(
            row=3, column=1, padx=12, pady=6, sticky="w"
        )
        CTkButton(
            configs,
            text="Change Bar Areas",
            corner_radius=32,
            command=self.open_dual_area_selector
        ).grid(row=4, column=0, padx=12, pady=12, sticky="w")
        CTkButton(
            configs,
            text="Rebind Hotkeys",
            corner_radius=32,
            command=self.rebind_hotkeys
        ).grid(row=4, column=1, padx=12, pady=12, sticky="w")
        # Automation 
        automation = CTkFrame(scroll, border_width=2)
        automation.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(automation, text="Automation Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        # Create and store checkboxes with StringVar
        auto_rod_var = StringVar(value="off")
        self.vars["auto_select_rod"] = auto_rod_var
        auto_rod_cb = CTkCheckBox(automation, text="Auto Select Rod", 
                                 variable=auto_rod_var, onvalue="on", offvalue="off")
        auto_rod_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")

        auto_zoom_var = StringVar(value="off")
        self.vars["auto_zoom_in"] = auto_zoom_var
        auto_zoom_cb = CTkCheckBox(automation, text="Auto Zoom In", 
                                  variable=auto_zoom_var, onvalue="on", offvalue="off")
        auto_zoom_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")

        fish_overlay_var = StringVar(value="off")
        self.vars["fish_overlay"] = fish_overlay_var
        fish_overlay_cb = CTkCheckBox(automation, text="Fish Overlay", 
                                     variable=fish_overlay_var, onvalue="on", offvalue="off")
        fish_overlay_cb.grid(row=3, column=0, padx=12, pady=8, sticky="w")

        #  Casting 
        casting = CTkFrame(
            scroll,
            border_width=2
        )
        casting.grid(row=3, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(casting, text="Casting Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        perfect_cast_var = StringVar(value="off")
        self.vars["perfect_cast"] = perfect_cast_var

        CTkCheckBox(
            casting,
            text="Perfect Cast (slower)",
            variable=perfect_cast_var,
            onvalue="on",
            offvalue="off"
        ).grid(row=1, column=0, padx=12, pady=8, sticky="w")
        # ---- Cast duration ----
        CTkLabel(casting, text="Cast duration").grid(
            row=2, column=0, padx=12, pady=8, sticky="w"
        )

        cast_duration_var = StringVar(value="0.6")
        self.vars["cast_duration"] = cast_duration_var

        cast_duration_entry = CTkEntry(
            casting,
            width=120,
            textvariable=cast_duration_var
        )
        cast_duration_entry.grid(row=2, column=1, padx=12, pady=8, sticky="w")


        # ---- Delay after casting ----
        CTkLabel(casting, text="Delay after casting").grid(
            row=3, column=0, padx=12, pady=8, sticky="w"
        )

        cast_duration_var = StringVar(value="0.6")
        self.vars["cast_duration"] = cast_duration_var

        cast_duration_entry = CTkEntry(
            casting,
            width=120,
            textvariable=cast_duration_var
        )
        cast_duration_entry.grid(row=3, column=1, padx=12, pady=8, sticky="w")
    # MISC SETTINGS TAB
    def build_misc_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Capture Mode Settings 
        capture_settings = CTkFrame(
            scroll,
            border_width=2
        )
        capture_settings.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(capture_settings, text="Capture Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(capture_settings, text="Capture Mode:").grid(
            row=1, column=0, padx=12, pady=6, sticky="w"
        )

        capture_var = StringVar(value="DXCAM")
        self.vars["capture_mode"] = capture_var
        capture_cb = CTkComboBox(
            capture_settings,
            values=["DXCAM", "MSS"],
            variable=capture_var,
            command=lambda v: self.set_status(f"Capture mode: {v}")
        )
        capture_cb.grid(row=1, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["capture_mode"] = capture_cb

        # Perfect Cast Settings 
        pfc1_settings = CTkFrame(
            scroll,
            border_width=2
        )
        pfc1_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        
        # ---- Perfect cast tolerance ----
        CTkLabel(pfc1_settings, text="Green (Perfect Cast) Tolerance:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        CTkLabel(pfc1_settings, text="Perfect Cast Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        perfect_cast_tolerance_var = StringVar(value="18")
        self.vars["perfect_cast_tolerance"] = perfect_cast_tolerance_var

        perfect_cast_tolerance_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=perfect_cast_tolerance_var
        )
        perfect_cast_tolerance_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc1_settings, text="White (Perfect Cast) Tolerance:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_cast2_tolerance_var = StringVar(value="16")
        self.vars["perfect_cast2_tolerance"] = perfect_cast2_tolerance_var

        perfect_cast2_tolerance_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=perfect_cast2_tolerance_var
        )
        perfect_cast2_tolerance_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc1_settings, text="Perfect Cast Reaction Time:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        reaction_time_var = StringVar(value="0.01")
        self.vars["reaction_time"] = reaction_time_var

        reaction_time_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=reaction_time_var
        )
        reaction_time_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc1_settings, text="Perfect Cast Scan FPS:").grid(
            row=4, column=0, padx=12, pady=10, sticky="w"
        )

        cast_scan_delay_var = StringVar(value="0.05")
        self.vars["cast_scan_delay"] = cast_scan_delay_var

        cast_scan_delay_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=cast_scan_delay_var
        )
        cast_scan_delay_entry.grid(row=4, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pfc1_settings, text="Green Y Lock Tolerance:").grid(
            row=5, column=0, padx=12, pady=10, sticky="w"
        )

        green_y_tol_var = StringVar(value="3")
        self.vars["perfect_cast_green_y_tol"] = green_y_tol_var

        CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=green_y_tol_var
        ).grid(row=5, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pfc1_settings, text="Min White Samples:").grid(
            row=6, column=0, padx=12, pady=10, sticky="w"
        )

        min_white_var = StringVar(value="3")
        self.vars["perfect_cast_min_white"] = min_white_var

        CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=min_white_var
        ).grid(row=6, column=1, padx=12, pady=10, sticky="w")

        # Fish Overlay Settings 
        overlay_settings = CTkFrame(
            scroll,
            border_width=2
        )
        overlay_settings.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(overlay_settings, text="Overlay Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        bar_size_var = StringVar(value="off")
        self.vars["bar_size"] = bar_size_var
        bar_size_cb = CTkCheckBox(overlay_settings, text="Show Bar Size", 
                                     variable=bar_size_var, onvalue="on", offvalue="off")
        bar_size_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
    # SHAKE SETTINGS TAB
    def build_shake_tab(self, parent):
        shake_configuration = CTkFrame(
            parent,
            border_width=2
        )
        shake_configuration.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(shake_configuration, text="Shake Configuration", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        # ---- Shake mode ----
        CTkLabel(shake_configuration, text="Shake mode:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        shake_mode_var = StringVar(value="Click")
        self.vars["shake_mode"] = shake_mode_var

        shake_cb = CTkComboBox(
            shake_configuration,
            values=["Click", "Navigation"],
            variable=shake_mode_var,
            command=lambda v: self.set_status(f"Shake mode: {v}")
        )
        shake_cb.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["shake_mode"] = shake_cb

        # ---- Shake tolerance ----
        CTkLabel(shake_configuration, text="Click Shake Color Tolerance:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        shake_tolerance_var = StringVar(value="5")
        self.vars["shake_tolerance"] = shake_tolerance_var

        CTkEntry(
            shake_configuration,
            width=120,
            textvariable=shake_tolerance_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        # ---- Shake scan delay ----
        CTkLabel(shake_configuration, text="Shake Scan Delay:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        shake_scan_delay_var = StringVar(value="0.01")
        self.vars["shake_scan_delay"] = shake_scan_delay_var

        CTkEntry(
            shake_configuration,
            width=120,
            textvariable=shake_scan_delay_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        # ---- Shake failsafe ----
        CTkLabel(shake_configuration, text="Shake Failsafe (attempts):").grid(
            row=4, column=0, padx=12, pady=10, sticky="w"
        )

        shake_failsafe_var = StringVar(value="20")
        self.vars["shake_failsafe"] = shake_failsafe_var

        CTkEntry(
            shake_configuration,
            width=120,
            textvariable=shake_failsafe_var
        ).grid(row=4, column=1, padx=12, pady=10, sticky="w")

    # MINIGAME SETTINGS TAB
    def build_minigame_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        frame = CTkFrame(
            scroll,
            border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(frame, text="Bar Colors (#RRGGBB)", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(frame, text="Left Bar Color:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        left_color_var = StringVar(value="#F1F1F1")
        self.vars["left_color"] = left_color_var
        CTkEntry(frame, placeholder_text="#F1F1F1", width=120, textvariable=left_color_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(frame, text="Right Bar Color:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_color"] = right_color_var
        CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=right_color_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Arrow Color:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        arrow_color_var = StringVar(value="#848587")
        self.vars["arrow_color"] = arrow_color_var
        CTkEntry(frame, placeholder_text="#848587", width=120, textvariable=arrow_color_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Fish Color:").grid(
            row=4, column=0, padx=12, pady=10, sticky="w"
        )
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        CTkEntry(frame, placeholder_text="#434B5B", width=120, textvariable=fish_color_var).grid(row=4, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Fish Color 2:").grid(
            row=5, column=0, padx=12, pady=10, sticky="w"
        )
        fish2_color_var = StringVar(value="#434B5B")
        self.vars["fish2_color"] = fish2_color_var
        CTkEntry(frame, placeholder_text="#434B5B", width=120, textvariable=fish2_color_var).grid(row=5, column=1, padx=12, pady=10, sticky="w")
        
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=1, column=2, padx=12, pady=10, sticky="w"
        )
        left_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=1, column=3, padx=12, pady=10, sticky="w")
        
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=2, column=2, padx=12, pady=10, sticky="w"
        )
        right_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=3, column=2, padx=12, pady=10, sticky="w"
        )

        arrow_tolerance_var = StringVar(value="8")
        self.vars["arrow_tolerance"] = arrow_tolerance_var
        arrow_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=arrow_tolerance_var)
        arrow_tolerance_entry.grid(row=3, column=3, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=4, column=2, padx=12, pady=10, sticky="w"
        )

        fish_tolerance_var = StringVar(value="0")
        self.vars["fish_tolerance"] = fish_tolerance_var

        CTkEntry(
            frame,
            width=120,
            textvariable=fish_tolerance_var
        ).grid(row=4, column=3, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=5, column=2, padx=12, pady=10, sticky="w"
        )

        fish2_tolerance_var = StringVar(value="0")
        self.vars["fish2_tolerance"] = fish2_tolerance_var

        CTkEntry(
            frame,
            width=120,
            textvariable=fish2_tolerance_var
        ).grid(row=5, column=3, padx=12, pady=10, sticky="w")
        
        frame2 = CTkFrame(
            scroll,
            border_width=2
        )
        frame2.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(frame2, text="Minigame Timing & Limits", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(frame2, text="Bar Ratio From Side:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        bar_ratio_var = StringVar(value="0.5")
        self.vars["bar_ratio"] = bar_ratio_var

        CTkEntry(
            frame2,
            width=120,
            textvariable=bar_ratio_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame2, text="Scan delay (seconds):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        minigame_scan_delay_var = StringVar(value="0.01")
        self.vars["minigame_scan_delay"] = minigame_scan_delay_var
        minigame_scan_delay_entry = CTkEntry(frame2, placeholder_text="0.01", width=120, textvariable=minigame_scan_delay_var)
        minigame_scan_delay_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(frame2, text="Restart Delay:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        restart_delay_var = StringVar(value="1")
        self.vars["restart_delay"] = restart_delay_var

        CTkEntry(
            frame2,
            width=120,
            textvariable=restart_delay_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        frame3 = CTkFrame(
            scroll,
            border_width=2
        )
        frame3.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(frame3, text="PID Controller Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(frame3, text="Proportional gain:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        p_gain_var = StringVar(value="0.01")
        self.vars["proportional_gain"] = p_gain_var

        CTkEntry(
            frame3,
            width=120,
            textvariable=p_gain_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(frame3, text="Derivative gain:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        d_gain_var = StringVar(value="0.01")
        self.vars["derivative_gain"] = d_gain_var
        CTkEntry(
            frame3,
            width=120,
            textvariable=d_gain_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(frame3, text="Velocity Smoothing:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        velocity_smoothing_var = StringVar(value="6")
        self.vars["velocity_smoothing"] = velocity_smoothing_var

        CTkEntry(
            frame3,
            width=120,
            textvariable=velocity_smoothing_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")
    # SUPPORT SETTINGS TAB
    def build_support_tab(self, parent):
        # Support Button
        support_frame = CTkFrame(
            parent,
            border_width=2
        )
        support_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(support_frame, text="Support & Community", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")    
        CTkButton(
            support_frame,
            text="Join Discord Server",
            corner_radius=32,
            command=self.open_link("https://bit.ly/4r3b2EM")
        ).grid(row=1, column=0, padx=12, pady=12, sticky="w")
        CTkButton(
            support_frame,
            text="YouTube Channel",
            corner_radius=32,
            command=self.open_link("https://www.youtube.com/@HexaTitanGaming")
        ).grid(row=1, column=1, padx=12, pady=12, sticky="w")
    # Save and load settings
    def load_configs(self):
        """Load list of available config files."""
        config_dir = "configs"
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        config_files = glob.glob(os.path.join(config_dir, "*.json"))
        config_names = [os.path.basename(f) for f in config_files]
        
        if not config_names:
            # Create default config if none exists
            self.save_settings("default.json")
            config_names = ["default.json"]
        
        return sorted(config_names)
    
    def load_last_config_name(self):
        """Load the name of the last used config."""
        try:
            if os.path.exists("last_config.json"):
                with open("last_config.json", "r") as f:
                    data = json.load(f)
                    return data.get("last_config", "default.json")
        except:
            pass
        return "default.json"
    
    def save_last_config_name(self, name):
        """Save the name of the last used config."""
        try:
            with open("last_config.json", "w") as f:
                json.dump({"last_config": name}, f)
        except:
            pass
    
    def save_misc_settings(self):
        """Save miscellaneous settings to last_config.json."""
        try:
            data = {
                "last_rod": self.current_rod_name,
                "bar_areas": self.bar_areas
            }
            with open("last_config.json", "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving misc settings: {e}")
    
    def save_settings(self, name):
        """Save all settings to a JSON config file."""
        config_dir = "configs"
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        
        data = {}
        
        # Save all StringVar and related variables
        try:
            for key, var in self.vars.items():
                if hasattr(var, 'get'):
                    data[key] = var.get()
                else:
                    data[key] = var
        except Exception as e:
            print(f"Error saving vars: {e}")
        
        # Save checkbox states
        try:
            for key, checkbox in self.checkboxes.items():
                data[f"checkbox_{key}"] = checkbox.get()
        except Exception as e:
            print(f"Error saving checkboxes: {e}")
        
        # Save combobox states
        try:
            for key, combobox in self.comboboxes.items():
                data[f"combobox_{key}"] = combobox.get()
        except Exception as e:
            print(f"Error saving comboboxes: {e}")
        
        # Save hotkeys
        try:
            data["hotkey_start"] = self._get_key_name(self.hotkey_start)
            data["hotkey_stop"] = self._get_key_name(self.hotkey_stop)
        except Exception as e:
            print(f"Error saving hotkeys: {e}")
        
        # Write to file
        path = os.path.join(config_dir, name)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            self.save_last_config_name(name)
            self.save_misc_settings()  # Also save misc settings
            self.set_status(f"Saved Config: {name}")
        except Exception as e:
            self.set_status(f"Error saving config: {e}")
    
    def load_settings(self, name):
        """Load settings from a JSON config file."""
        config_dir = "configs"
        path = os.path.join(config_dir, name)
        
        if not os.path.exists(path):
            self.set_status(f"Config not found: {name}")
            return
        
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except Exception as e:
            self.set_status(f"Error loading config: {e}")
            return
        
        # Load StringVar and related variables
        try:
            for key, var in self.vars.items():
                if hasattr(var, 'set') and key in data:
                    var.set(data[key])
        except Exception as e:
            print(f"Error loading vars: {e}")
        
        # Load checkbox states
        try:
            for key, checkbox in self.checkboxes.items():
                checkbox_key = f"checkbox_{key}"
                if checkbox_key in data:
                    checkbox.set(data[checkbox_key])
        except Exception as e:
            print(f"Error loading checkboxes: {e}")
        
        # Load combobox states
        try:
            for key, cb in self.comboboxes.items():
                if key in data:
                    cb.set(data[key])
        except Exception as e:
            print(f"Error loading comboboxes: {e}")
        
        # Load hotkeys
        try:
            if "hotkey_start" in data:
                self.hotkey_start = self._key_name_to_key(data["hotkey_start"])
            if "hotkey_stop" in data:
                self.hotkey_stop = self._key_name_to_key(data["hotkey_stop"])
            # Update labels if they exist
            if "start" in self.hotkey_labels:
                self.hotkey_labels["start"].configure(text=self._get_key_name(self.hotkey_start))
            if "stop" in self.hotkey_labels:
                self.hotkey_labels["stop"].configure(text=self._get_key_name(self.hotkey_stop))
        except Exception as e:
            print(f"Error loading hotkeys: {e}")
        
        self.save_last_config_name(name)
        self.set_status(f"Loaded Config: {name}")
    def load_misc_settings(self):
        """Load miscellaneous settings from last_config.json."""
        try:
            if os.path.exists("last_config.json"):
                with open("last_config.json", "r") as f:
                    data = json.load(f)
                    self.current_rod_name = data.get("last_rod", "Basic Rod")
                    self.bar_areas = data.get("bar_areas", {
                        "fish": None,
                        "shake": None
                    })
            else:
                self.current_rod_name = "Basic Rod"
                self.bar_areas = {"fish": None, "shake": None}
        except:
            self.current_rod_name = "Basic Rod"
            self.bar_areas = {"fish": None, "shake": None}
    # Macro functions
    def on_key_press(self, key):
        try:
            if key == self.hotkey_start and not self.macro_running:
                # Save settings before starting
                config_name = self.vars["active_config"].get()
                self.save_settings(config_name)

                self.macro_running = True
                self.after(0, self.withdraw)
                threading.Thread(target=self.start_macro, daemon=True).start()

            elif key == self.hotkey_stop:
                self.stop_macro()

            elif key == self.hotkey_reserved:
                # self.close()
                pass  # Reserved for future use
        except Exception as e:
            print("Hotkey error:", e)
            
    def set_status(self, text, key=None):
        self.status_label.configure(text=text)
    
    def _get_key_name(self, key):
        """Convert a pynput Key object to a readable string name."""
        if isinstance(key, Key):
            return key.name.upper()
        else:
            return str(key).replace("'", "")
    
    def _key_name_to_key(self, key_name):
        """Convert a string key name back to a pynput Key object."""
        key_name = key_name.lower()
        try:
            return Key[key_name]
        except KeyError:
            # If it's not a special key, return the string as is
            return key_name
    
    def rebind_hotkeys(self):
        """Open dialog to rebind hotkeys."""
        dialog = CTkToplevel(self)
        dialog.title("Rebind Hotkeys")
        dialog.geometry("400x300")
        dialog.resizable(False, False)
        
        # Make it stay on top
        dialog.attributes('-topmost', True)
        
        # Center the dialog
        dialog.transient(self)
        dialog.grab_set()
        
        # Title
        CTkLabel(dialog, text="Press the key you want to bind", font=CTkFont(size=14, weight="bold")).pack(pady=10)
        
        # Start key rebinding
        CTkLabel(dialog, text="Start Macro Key", font=CTkFont(size=12)).pack(pady=5)
        start_info = CTkLabel(dialog, text=f"Current: {self._get_key_name(self.hotkey_start)}", text_color="gray")
        start_info.pack(pady=2)
        
        def bind_start_key():
            dialog.withdraw()
            self.set_status("Press START key (20 sec timeout)...")
            
            captured_key = [None]
            
            def listen_for_start(key):
                if captured_key[0] is None:
                    captured_key[0] = key
                    return False  # Stop listener
            
            listener = KeyListener(on_press=listen_for_start)
            listener.start()
            listener.join(timeout=20)  # Wait max 20 seconds
            
            if captured_key[0] is not None:
                self.hotkey_start = captured_key[0]
                start_info.configure(text=f"Current: {self._get_key_name(self.hotkey_start)}")
                if "start" in self.hotkey_labels:
                    self.hotkey_labels["start"].configure(text=self._get_key_name(self.hotkey_start))
                self.set_status(f"Start key bound to {self._get_key_name(self.hotkey_start)}")
            else:
                self.set_status("Start key binding cancelled")
            
            dialog.deiconify()
        
        CTkButton(dialog, text="Bind Start Key", command=bind_start_key, corner_radius=8).pack(pady=10)
        
        # Stop key rebinding
        CTkLabel(dialog, text="Stop Macro Key", font=CTkFont(size=12)).pack(pady=5)
        stop_info = CTkLabel(dialog, text=f"Current: {self._get_key_name(self.hotkey_stop)}", text_color="gray")
        stop_info.pack(pady=2)
        
        def bind_stop_key():
            dialog.withdraw()
            self.set_status("Press STOP key (20 sec timeout)...")
            
            captured_key = [None]
            
            def listen_for_stop(key):
                if captured_key[0] is None:
                    captured_key[0] = key
                    return False  # Stop listener
            
            listener = KeyListener(on_press=listen_for_stop)
            listener.start()
            listener.join(timeout=20)  # Wait max 20 seconds
            
            if captured_key[0] is not None:
                self.hotkey_stop = captured_key[0]
                stop_info.configure(text=f"Current: {self._get_key_name(self.hotkey_stop)}")
                if "stop" in self.hotkey_labels:
                    self.hotkey_labels["stop"].configure(text=self._get_key_name(self.hotkey_stop))
                self.set_status(f"Stop key bound to {self._get_key_name(self.hotkey_stop)}")
            else:
                self.set_status("Stop key binding cancelled")
            
            dialog.deiconify()
        
        CTkButton(dialog, text="Bind Stop Key", command=bind_stop_key, corner_radius=8).pack(pady=10)
        
        # Save button
        def save_and_close():
            config_name = self.vars["active_config"].get()
            self.save_settings(config_name)
            self.set_status("Hotkeys saved!")
            dialog.destroy()
        
        CTkButton(dialog, text="Save & Close", command=save_and_close, corner_radius=8, fg_color="green").pack(pady=15)
    
    # Utility functions
    def open_link(self, url):
        """Open a URL in the default web browser."""
        return lambda: webbrowser.open(url)
    
    def open_dual_area_selector(self):
        # Toggle OFF if already open
        if self.area_selector and self.area_selector.window.winfo_exists():
            self.area_selector.close()
            self.area_selector = None
            self.set_status("Area selector closed")
            return

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        def default_area():
            return {
                "x": int(screen_w * 0.3),
                "y": int(screen_h * 0.4),
                "width": 200,
                "height": 150
            }

        shake_area = (
            self.bar_areas.get("shake")
            if isinstance(self.bar_areas.get("shake"), dict)
            else default_area()
        )

        fish_area = (
            self.bar_areas.get("fish")
            if isinstance(self.bar_areas.get("fish"), dict)
            else default_area()
        )

        def on_done(shake, fish):
            self.bar_areas = {
                "shake": shake,
                "fish": fish
            }

            self.save_misc_settings()

            self.area_selector = None
            self.set_status("Bar areas saved")

        # Take screenshot
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            screenshot = Image.frombytes("RGB", shot.size, shot.rgb)

        self.area_selector = DualAreaSelector(
            parent=self,
            screenshot=screenshot,
            shake_area=shake_area,
            fish_area=fish_area,
            callback=on_done
        )

        self.set_status("Area selector opened (ESC or click button again to close)")

    # Pixel Search Functions
    def _pixel_search(self, frame, target_color_hex, tolerance=10):
        """
        Search for a specific color in a frame and return all matching pixel coordinates.
        
        Args:
            frame: BGR numpy array from cv2/mss
            target_color_hex: Hex color code (e.g., "#FFFFFF")
            tolerance: Color tolerance range (0-255)
        
        Returns:
            List of (x, y) tuples of matching pixels, or empty list if none found
        """
        if frame is None or frame.size == 0:
            return []
        
        # Convert hex to BGR
        bgr_color = self._hex_to_bgr(target_color_hex)
        if bgr_color is None:
            return []
        
        # Create color range with tolerance
        lower_bound = np.array([
            max(0, bgr_color[0] - tolerance),
            max(0, bgr_color[1] - tolerance),
            max(0, bgr_color[2] - tolerance)
        ])
        upper_bound = np.array([
            min(255, bgr_color[0] + tolerance),
            min(255, bgr_color[1] + tolerance),
            min(255, bgr_color[2] + tolerance)
        ])
        
        # Create mask for matching colors
        mask = cv2.inRange(frame, lower_bound, upper_bound)
        y_coords, x_coords = np.where(mask > 0)
        
        # Return as list of (x, y) tuples
        if len(x_coords) > 0:
            return list(zip(x_coords, y_coords))
        return []
    
    def _grab_screen_region(self, left, top, right, bottom):
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return None

        with mss.mss() as sct:
            monitor = {
                "left": left,
                "top": top,
                "width": width,
                "height": height
            }
            img = np.array(sct.grab(monitor))
            return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    def _click_at(self, x, y):
        mouse_controller.position = (x, y)
        time.sleep(0.01)

        # micro-jitter
        mouse_controller.position = (x + 3, y + 3)
        mouse_controller.position = (x, y)

        mouse_controller.press(Button.left)
        time.sleep(0.04)
        mouse_controller.release(Button.left)

    def _find_color_center(self, frame, target_color_hex, tolerance=10):
        """
        Find the center point of a color cluster in a frame.
        
        Args:
            frame: BGR numpy array from cv2/mss
            target_color_hex: Hex color code (e.g., "#FFFFFF")
            tolerance: Color tolerance range (0-255)
        
        Returns:
            (x, y) tuple of center point, or None if no pixels found
        """
        pixels = self._pixel_search(frame, target_color_hex, tolerance)
        if not pixels:
            return None
        
        # Calculate average position
        x_coords = [p[0] for p in pixels]
        y_coords = [p[1] for p in pixels]
        center_x = int(np.mean(x_coords))
        center_y = int(np.mean(y_coords))

        return (center_x, center_y)
    
    def _find_bar_edges(
        self,
        frame,
        left_hex,
        right_hex,
        tolerance=15,
        tolerance2=15,
        scan_height_ratio=0.55
    ):
        if frame is None:
            return None, None

        h, w, _ = frame.shape
        y = int(h * scan_height_ratio)

        left_bgr = np.array(self._hex_to_bgr(left_hex), dtype=np.int16)
        right_bgr = np.array(self._hex_to_bgr(right_hex), dtype=np.int16)

        line = frame[y].astype(np.int16)

        tol_l = int(np.clip(tolerance, 0, 255))
        tol_r = int(np.clip(tolerance2, 0, 255))

        # V1-style threshold comparison
        left_mask = np.all(line >= (left_bgr - tol_l), axis=1)
        right_mask = np.all(line >= (right_bgr - tol_r), axis=1)

        left_indices = np.where(left_mask)[0]
        right_indices = np.where(right_mask)[0]

        left_edge = int(left_indices[0]) if left_indices.size else None
        right_edge = int(right_indices[-1]) if right_indices.size else None

        return left_edge, right_edge

    def _find_color_bounds(self, frame, target_color_hex, tolerance=10):
        pixels = self._pixel_search(frame, target_color_hex, tolerance)
        if not pixels:
            return None

        xs, ys = zip(*pixels)

        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        return {
            "min_x": min_x,
            "max_x": max_x,
            "min_y": min_y,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
            "center_x": (min_x + max_x) / 2,
            "center_y": (min_y + max_y) / 2
        }

    def _find_white_pixel(self, frame, tolerance=10):
        tolerance = int(np.clip(tolerance, 0, 255))

        white = np.array([255, 255, 255], dtype=np.int16)
        frame_i = frame.astype(np.int16)

        mask = np.all(
            np.abs(frame_i - white) <= tolerance,
            axis=-1
        )

        coords = np.argwhere(mask)
        if coords.size > 0:
            y, x = coords[0]
            return int(x), int(y)

        return None

    def _hex_to_bgr(self, hex_color):
        """
        Convert hex color to BGR tuple for OpenCV.
        
        Args:
            hex_color: Hex color string (e.g., "#FFFFFF")
        
        Returns:
            (B, G, R) tuple or None if invalid
        """
        if hex_color is None or hex_color.lower() in ["none", "#none", ""]:
            return None
        
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (b, g, r)  # BGR format for OpenCV
            except ValueError:
                return None
        return None
    
    def _get_pid_gains(self):
        """Get PID gains from config, with sensible defaults."""
        try:
            kp = float(self.vars["proportional_gain"].get() or 0.6)
        except:
            kp = 0.6
        
        try:
            kd = float(self.vars["derivative_gain"].get() or 0.2)
        except:
            kd = 0.2
        
        # Small integral term to reduce steady-state error
        ki = 0.02
        
        return kp, kd, ki
    
    def _pid_control(self, error):
        now = time.perf_counter()

        if self.pid_last_time is None:
            self.pid_last_time = now
            self.pid_prev_error = error
            return 0.0

        dt = now - self.pid_last_time
        if dt <= 0:
            return 0.0

        kp, kd, ki = self._get_pid_gains()

        # Integral (anti-windup)
        self.pid_integral += error * dt
        self.pid_integral = max(-100, min(100, self.pid_integral))

        # Derivative
        derivative = (error - self.pid_prev_error) / dt

        output = (
            kp * error +
            ki * self.pid_integral +
            kd * derivative
        )

        self.pid_prev_error = error
        self.pid_last_time = now

        return output

    def _reset_pid_state(self):
        """Reset PID control state variables."""
        self.pid_integral = 0.0
        self.prev_error = 0.0
        self.last_time = None
        # Clear PID source so next detection resets state correctly
        self.prev_measurement = None
        self.filtered_derivative = 0.0
        self.pid_source = None

        # Also reset arrow estimation state
        self.last_indicator_x = None
        self.last_holding_state = None
        self.estimated_box_length = None
        self.last_left_x = None
        self.last_right_x = None
        self.last_known_box_center_x = None
    
    def _find_arrow_indicator_x(self, frame, arrow_hex, tolerance, is_holding):
        """
        IRUS-style arrow tracking:
        - If holding: arrow is RIGHT edge → use max X
        - If not holding: arrow is LEFT edge → use min X
        Returns indicator X or None.
        """
        pixels = self._pixel_search(frame, arrow_hex, tolerance)
        if not pixels:
            return None

        xs = [x for x, _ in pixels]

        indicator_x = max(xs) if is_holding else min(xs)

        # Small jitter filter
        if self.last_indicator_x is not None:
            if abs(indicator_x - self.last_indicator_x) < 2:
                indicator_x = self.last_indicator_x

        return indicator_x

    def _update_arrow_box_estimation(self, arrow_centroid_x, is_holding, capture_width):
        """
        Estimate box position based on arrow indicator using IRUS-style logic.
        
        If holding: arrow is on RIGHT edge, extend LEFT
        If not holding: arrow is on LEFT edge, extend RIGHT
        When state swaps: measure distance between arrows to get box size
        
        Args:
            arrow_centroid_x: X coordinate of arrow center
            is_holding: Whether mouse button is currently held
            capture_width: Width of capture region
        
        Returns:
            Estimated bar center X coordinate, or None if can't estimate
        """
        # Handle missing arrow
        if arrow_centroid_x is None:
            if self.last_known_box_center_x is not None:
                return self.last_known_box_center_x
            return None
        
        # Check if state swapped (holding <-> not holding)
        state_swapped = (self.last_holding_state is not None and 
                        is_holding != self.last_holding_state)
        
        # When swapping: measure new box size from arrow positions
        if state_swapped and self.last_indicator_x is not None:
            new_box_size = abs(arrow_centroid_x - self.last_indicator_x)
            if new_box_size >= 10:  # Reasonable minimum
                self.estimated_box_length = new_box_size
        
        # Set default box size if we don't have one
        if self.estimated_box_length is None or self.estimated_box_length <= 0:
            self.estimated_box_length = min(capture_width * 0.3, 200)
        
        # Position the box based on current hold state
        if is_holding:
            # Holding: arrow is on RIGHT, extend LEFT
            self.last_right_x = float(arrow_centroid_x)
            self.last_left_x = self.last_right_x - self.estimated_box_length
        else:
            # Not holding: arrow is on LEFT, extend RIGHT
            self.last_left_x = float(arrow_centroid_x)
            self.last_right_x = self.last_left_x + self.estimated_box_length
        
        # Clamp to capture bounds (keep arrow anchored)
        if self.last_left_x < 0:
            self.last_left_x = 0.0
            self.last_right_x = min(self.estimated_box_length, capture_width)
        
        if self.last_right_x > capture_width:
            self.last_right_x = float(capture_width)
            self.last_left_x = max(0.0, self.last_right_x - self.estimated_box_length)
        
        # Calculate and store center
        box_center = (self.last_left_x + self.last_right_x) / 2.0
        self.last_known_box_center_x = box_center
        
        # Update tracking variables for next frame
        self.last_indicator_x = arrow_centroid_x
        self.last_holding_state = is_holding
        
        return box_center
    def _find_bar_target(self, fish_x, left_bar_x, right_bar_x, bar_ratio):
        """
        Symmetric safe-zone around fish_x.
        bar_ratio: fraction of bar width (0.0 - 0.5 recommended)
        """
        bar_width = right_bar_x - left_bar_x
        bar_ratio = max(0.05, min(0.45, bar_ratio))

        half_zone = bar_width * bar_ratio * 0.5

        left_limit  = fish_x - half_zone
        right_limit = fish_x + half_zone

        if fish_x < left_limit:
            return left_limit
        elif fish_x > right_limit:
            return right_limit
        else:
            return None

    # === MINIGAME WINDOW (instance methods) ===
    def init_minigame_window(self):
        """
        Create the minigame window and canvas (only once).
        """
        if self.minigame_window and self.minigame_window.winfo_exists():
            return

        self.minigame_window = tk.Toplevel(self)
        self.minigame_window.geometry("800x50+560+660")
        if sys.platform == "darwin":
            self.minigame_window.overrideredirect(False)
        else:
            self.minigame_window.overrideredirect(True)
        self.minigame_window.attributes("-topmost", True)

        self.minigame_canvas = tk.Canvas(
            self.minigame_window,
            width=800,
            height=60,
            bg="#1d1d1d",
            highlightthickness=0
        )
        self.minigame_canvas.pack(fill="both", expand=True)

    def show_minigame(self):
        if self.minigame_window and self.minigame_window.winfo_exists():
            self.minigame_window.deiconify()
            self.minigame_window.lift()

    def hide_minigame(self):
        if self.minigame_window and self.minigame_window.winfo_exists():
            self.minigame_window.withdraw()

    def clear_minigame(self):
        if not self.minigame_canvas or not self.minigame_canvas.winfo_exists():
            return
        self.minigame_canvas.delete("all")
        self.initial_bar_size = None

    def draw_box(self, x1, y1, x2, y2, fill="#000000", outline="white"):
        if not self.minigame_canvas or not self.minigame_canvas.winfo_exists():
            return

        def _draw():
            self.minigame_canvas.create_rectangle(
                x1, y1, x2, y2,
                outline=outline,
                width=2,
                fill=fill
            )

        self.minigame_canvas.after(0, _draw)

    def draw_bar_minigame(
        self,
        bar_center,
        box_size,
        color,
        canvas_offset,
        bar_y1=10,
        bar_y2=40,
    ):
        """
        Draws:
        - Square box with size
        """

        # Guard against missing center
        if bar_center is None:
            return
        
        box_size = int(box_size / 2)
        # Calculate bar edges
        left_edge = bar_center - box_size
        right_edge = bar_center + box_size

        # Main bar
        bx1 = left_edge - canvas_offset
        bx2 = right_edge - canvas_offset
        self.draw_box(bx1, bar_y1, bx2, bar_y2, fill="#000000", outline=color)
    def _find_white_below_green(self, frame, green_y, left_x, right_x, tolerance):
        """
        Find the white indicator below the green bar.
        Returns (x, y) or None
        """

        h, w, _ = frame.shape

        # Clamp bounds
        left_x = max(0, int(left_x))
        right_x = min(w - 1, int(right_x))
        start_y = min(h - 1, int(green_y + 2))

        best = None
        best_y = h

        tol = int(tolerance)

        for y in range(start_y, h):
            row = frame[y, left_x:right_x]

            # White ≈ high RGB, low variance
            mask = (
                (row[:, 0] > 255 - tol) &
                (row[:, 1] > 255 - tol) &
                (row[:, 2] > 255 - tol)
            )

            if mask.any():
                x = left_x + int(mask.argmax())
                best = (x, y)
                break

        return best
    def _calculate_speed_and_predict(self, positions, timestamps):
        """
        Calculate vertical speed of the white indicator using prediction mode.
        Returns speed in pixels per second, or None if unstable.
        """

        if len(positions) < 3:
            return None

        # Use last N samples (Comet uses small window)
        N = min(5, len(positions))
        pos = positions[-N:]
        time = timestamps[-N:]

        # Extract Y only (white moves vertically)
        ys = [p[1] for p in pos]

        # Compute deltas
        dy = ys[-1] - ys[0]
        dt = time[-1] - time[0]

        # Safety guards
        if dt <= 0:
            return None

        # Ignore tiny jitter (noise filter)
        if abs(dy) < 2:
            return None

        speed = dy / dt  # pixels per second

        # Clamp insane speeds (helps on lag spikes)
        max_speed = 8000
        speed = max(-max_speed, min(max_speed, speed))

        return speed

    def start_macro(self):
        # 434 705 1029 794
        self.macro_running = True
        self._reset_pid_state()
        self.set_status("Macro Status: Running")

        # Initial camera alignment (ONLY ONCE)
        mouse_controller.position = (960, 300)
        if self.vars["auto_zoom_in"].get() == "on":
            for _ in range(20):
                mouse_controller.scroll(0, 1)
                time.sleep(0.05)
            mouse_controller.scroll(0, -1)
            time.sleep(0.1)

        # 🔁 MAIN MACRO LOOP
        while self.macro_running:

            # 1️⃣ Select rod
            if self.vars["auto_select_rod"].get() == "on":
                self.set_status("Selecting rod")
                keyboard_controller.press("2")
                time.sleep(0.05)
                keyboard_controller.release("2")
                time.sleep(0.1)
                keyboard_controller.press("1")
                time.sleep(0.05)
                keyboard_controller.release("1")
                time.sleep(0.2)
            # 2: Fish Overlay
            if self.vars["fish_overlay"].get() == "on":
                self.show_minigame()
            else:
                self.hide_minigame()
            if not self.macro_running:
                break

            # 2️⃣ Cast
            self.set_status("Casting")
            if self.vars["perfect_cast"].get() == "on":
                self._execute_cast_perfect()
            else:
                self._execute_cast_normal()

            # Optional delay after cast
            try:
                delay = float(self.vars["cast_duration"].get() or 0.6)
                time.sleep(delay)
            except:
                time.sleep(0.6)

            if not self.macro_running:
                break

            # 3️⃣ Shake
            self.set_status("Shaking")
            if self.vars["shake_mode"].get() == "Click":
                self._execute_shake_click()
            else:
                self._execute_shake_navigation()

            if not self.macro_running:
                break

            # 4️⃣ Fish (minigame)
            self.set_status("Fishing")
            self._enter_minigame()

            # ⬅️ When minigame ends, loop repeats from Select Rod
    def _execute_cast_perfect(self):
        # Hold click
        mouse_controller.press(Button.left)
        # Get shake area
        shake = self.bar_areas.get("shake")
        if isinstance(shake, dict):
            shake_left   = shake["x"]
            shake_top    = shake["y"]
            shake_right  = shake["x"] + shake["width"]
            shake_bottom = shake["y"] + shake["height"]
        else:
            # fallback (old ratio logic)
            shake_left   = int(self.SCREEN_WIDTH * 0.2083)
            shake_top    = int(self.SCREEN_HEIGHT * 0.162)
            shake_right  = int(self.SCREEN_WIDTH * 0.7813)
            shake_bottom = int(self.SCREEN_HEIGHT * 0.74)
        # Other variables
        start_time = time.time()
        white_tolerance = int(self.vars["perfect_cast2_tolerance"].get())
        green_tolerance = int(self.vars["perfect_cast_tolerance"].get())

        while self.macro_running:
            frame = self._grab_screen_region(shake_left, shake_top, shake_right, shake_bottom)

            green_pixels = self._pixel_search(
                frame,
                "#5fa84b",
                green_tolerance
            )

            if not green_pixels:
                if time.time() - start_time > 3.5:
                    mouse_controller.release(Button.left)
                    return
                time.sleep(float(self.vars["cast_scan_delay"].get()))
                print("Green not found")
                continue

            # Lowest green pixel
            green_x, green_y = max(green_pixels, key=lambda p: p[1])

            white_pixels = self._pixel_search(
                frame,
                "#d4d3ca",
                white_tolerance
            )
            if not white_pixels:
                print("White not found")
                time.sleep(float(self.vars["cast_scan_delay"].get()))
                continue
            white_x, white_y = min(white_pixels, key=lambda p: p[1])
            if white_pixels and green_pixels:
                distance = abs(green_y - white_y)
                print(distance)
                if distance < 30:
                    mouse_controller.release(Button.left)
            if time.time() - start_time > 3.5:
                mouse_controller.release(Button.left)
                return

            time.sleep(float(self.vars["cast_scan_delay"].get()))

    def _execute_cast_normal(self):
        # Basic cast: hold left click briefly
        mouse_controller.press(Button.left)
        duration = float(self.vars["cast_duration"].get() or 0.6)
        time.sleep(duration)  # adjust cast strength
        mouse_controller.release(Button.left)
        time.sleep(0.2)
    def _execute_shake_click(self):
        self.set_status("Shake Mode: Click")
        # --- SHAKE AREA ---
        shake = self.bar_areas.get("shake")
        if isinstance(shake, dict):
            shake_left   = shake["x"]
            shake_top    = shake["y"]
            shake_right  = shake["x"] + shake["width"]
            shake_bottom = shake["y"] + shake["height"]
        else:
            # fallback (old ratio logic)
            shake_left   = int(self.SCREEN_WIDTH * 0.2083)
            shake_top    = int(self.SCREEN_HEIGHT * 0.162)
            shake_right  = int(self.SCREEN_WIDTH * 0.7813)
            shake_bottom = int(self.SCREEN_HEIGHT * 0.74)

        # --- FISH AREA ---
        fish = self.bar_areas.get("fish")
        if isinstance(fish, dict):
            fish_left   = fish["x"]
            fish_top    = fish["y"]
            fish_right  = fish["x"] + fish["width"]
            fish_bottom = fish["y"] + fish["height"]
        else:
            fish_left   = int(self.SCREEN_WIDTH  * 0.2844)
            fish_top    = int(self.SCREEN_HEIGHT * 0.7981)
            fish_right  = int(self.SCREEN_WIDTH  * 0.7141)
            fish_bottom = int(self.SCREEN_HEIGHT * 0.8370)


        shake_area = self.bar_areas["shake"]
        print(shake_area)

        fish_hex = self.vars["fish_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())
        scan_delay = float(self.vars["shake_scan_delay"].get())
        failsafe = int(self.vars["shake_failsafe"].get() or 40)

        # initialize attempts counter to avoid UnboundLocalError
        attempts = 0

        while self.macro_running and attempts < failsafe:
            shake_area = self._grab_screen_region(shake_left, shake_top, shake_right, shake_bottom)
            if shake_area is None:
                time.sleep(scan_delay)
                continue
            detection_area = self._grab_screen_region(fish_left, fish_top, fish_right, fish_bottom)
            if detection_area is None:
                time.sleep(scan_delay)
                continue

            # 2️⃣ Look for white shake pixel
            white_pixel = self._find_white_pixel(shake_area, tolerance)
            if white_pixel:
                x, y = white_pixel
                screen_x = shake_left + x
                screen_y = shake_top + y
                self._click_at(screen_x, screen_y)

            # 2️⃣.5 Stable fish detection
            stable = 0
            while stable < 8 and self.macro_running:
                detection_area = self._grab_screen_region(
                    fish_left, fish_top, fish_right, fish_bottom
                )

                if detection_area is None:
                    break

                fish_center = self._find_color_center(
                    detection_area, fish_hex, tolerance
                )

                if fish_center:
                    stable += 1
                    time.sleep(0.005)
                else:
                    break

            # 3️⃣ Fish detected → enter minigame
            if stable >= 8:
                self.set_status("Entering Minigame")

                mouse_controller.press(Button.left)
                time.sleep(0.003)
                mouse_controller.release(Button.left)

                return  # exit shake cleanly

            attempts += 1
            time.sleep(scan_delay)

    def _execute_shake_navigation(self):
        self.set_status("Shake Mode: Navigation")
        # --- FISH AREA ---
        fish = self.bar_areas.get("fish")
        if isinstance(fish, dict):
            fish_left   = fish["x"]
            fish_top    = fish["y"]
            fish_right  = fish["x"] + fish["width"]
            fish_bottom = fish["y"] + fish["height"]
        else:
            fish_left   = int(self.SCREEN_WIDTH  * 0.2844)
            fish_top    = int(self.SCREEN_HEIGHT * 0.7981)
            fish_right  = int(self.SCREEN_WIDTH  * 0.7141)
            fish_bottom = int(self.SCREEN_HEIGHT * 0.8370)

        fish_hex = self.vars["fish_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())
        scan_delay = float(self.vars["shake_scan_delay"].get())
        failsafe = int(self.vars["shake_failsafe"].get() or 20)

        attempts = 0

        while self.macro_running and attempts < failsafe:

            # 1️⃣ Navigation shake (Enter key)
            keyboard_controller.press(Key.enter)
            time.sleep(0.03)
            keyboard_controller.release(Key.enter)

            time.sleep(scan_delay)

            # 2️⃣ Stable fish detection (old logic preserved)
            stable = 0
            while stable < 8 and self.macro_running:
                detection_area = self._grab_screen_region(
                    fish_left, fish_top, fish_right, fish_bottom
                )

                if detection_area is None:
                    break

                fish_center = self._find_color_center(
                    detection_area, fish_hex, tolerance
                )

                if fish_center:
                    stable += 1
                    time.sleep(0.005)
                else:
                    break

            # 3️⃣ Fish detected → enter minigame
            if stable >= 8:
                self.set_status("Entering Minigame")

                mouse_controller.press(Button.left)
                time.sleep(0.003)
                mouse_controller.release(Button.left)

                return  # exit shake cleanly

            attempts += 1
            time.sleep(scan_delay)

    def _enter_minigame(self):
        # --- FISH AREA ---
        fish = self.bar_areas.get("fish")
        if isinstance(fish, dict):
            fish_left   = fish["x"]
            fish_top    = fish["y"]
            fish_right  = fish["x"] + fish["width"]
            fish_bottom = fish["y"] + fish["height"]
        else:
            fish_left   = int(self.SCREEN_WIDTH  * 0.2844)
            fish_top    = int(self.SCREEN_HEIGHT * 0.7981)
            fish_right  = int(self.SCREEN_WIDTH  * 0.7141)
            fish_bottom = int(self.SCREEN_HEIGHT * 0.8370)

        fish_hex = self.vars["fish_color"].get()
        fish2_hex = self.vars["fish_color"].get()
        arrow_hex = self.vars["arrow_color"].get()
        left_bar_hex = self.vars["left_color"].get()
        right_bar_hex = self.vars["right_color"].get()

        left_tol = int(self.vars["left_tolerance"].get() or 8)
        right_tol = int(self.vars["right_tolerance"].get() or 8)
        arrow_tol = int(self.vars["arrow_tolerance"].get() or 8)
        fish_tol = int(self.vars["fish_tolerance"].get() or 5)
        bar_ratio = float(self.vars["bar_ratio"].get() or 0.5)

        scan_delay = float(self.vars["minigame_scan_delay"].get() or 0.1)

        try:
            thresh = float(self.vars["velocity_smoothing"].get() or 10)
        except:
            thresh = 10

        DEADZONE = 8
        mouse_down = False
        fish_miss_count = 0
        MAX_FISH_MISSES = 20

        self.pid_prev_error = 0.0
        self.pid_integral = 0.0
        self.pid_last_time = None

        def hold_mouse():
            nonlocal mouse_down
            if not mouse_down:
                mouse_controller.press(Button.left)
                mouse_down = True

        def release_mouse():
            nonlocal mouse_down
            if mouse_down:
                mouse_controller.release(Button.left)
                mouse_down = False

        while self.macro_running: # Main macro loop
            img = self._grab_screen_region(
                fish_left, fish_top, fish_right, fish_bottom
            )

            if img is None:
                time.sleep(0.01)
                continue

            fish_center = self._find_color_center(img, fish_hex, fish_tol)
            fish2_center = self._find_color_center(img, fish2_hex, fish_tol)
            arrow_center = self._find_color_center(img, arrow_hex, arrow_tol)
            left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, right_bar_hex, left_tol, right_tol)
            if left_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges(img, right_bar_hex, right_bar_hex, right_tol, right_tol)
            elif right_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, left_bar_hex, left_tol, left_tol)

            # ---- FISH NOT FOUND ----
            if fish_center is not None:
                fish_miss_count = 0

            elif fish2_center is not None:
                fish_center = fish2_center
                fish_miss_count = 0

            else:
                # Neither fish color found
                fish_miss_count += 1
                release_mouse()

                if fish_miss_count >= MAX_FISH_MISSES:
                    release_mouse()
                    time.sleep(0.3)
                    return

                time.sleep(0.02)
                continue
            # ---- CLEAR MINIGAME ----
            self.clear_minigame()
            # ---- BARS NOT FOUND ----
            bars_found = left_bar_center is not None and right_bar_center is not None
            fish_x = fish_center[0] + fish_left
            if bars_found and left_bar_center is not None and right_bar_center is not None:
                bar_center = int((left_bar_center + right_bar_center) / 2 + fish_left)
                bar_size = abs(right_bar_center - left_bar_center)
                if self.initial_bar_size is None:
                    self.initial_bar_size = bar_size
                deadzone = bar_size * bar_ratio
                max_left = fish_left + deadzone
                max_right = fish_right - deadzone
                pid_found = 0 # 0: PID 1: Release 2: Hold 3: Do nothing
            else:
                bar_center = None
                max_left = None
                max_right = None
                pid_found = 3
            if bars_found and bar_center is not None: # Bar found
                if max_left is not None and fish_x <= max_left: # Max left and right check (inside bar)
                    if self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(bar_center=max_left, box_size=15, color="lightblue", canvas_offset=fish_left)
                        if self.vars["bar_size"].get() == "on":
                            self.draw_bar_minigame(bar_center=bar_center,box_size=bar_size, color="green", canvas_offset=fish_left)
                        else:
                            self.draw_bar_minigame(bar_center=bar_center,box_size=40, color="green", canvas_offset=fish_left)
                        self.draw_bar_minigame(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left)
                    pid_found = 1
                
                elif max_right is not None and fish_x >= max_right:
                    if self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(bar_center=max_right, box_size=15, color="lightblue", canvas_offset=fish_left)
                        if self.vars["bar_size"].get() == "on":
                            self.draw_bar_minigame(bar_center=bar_center,box_size=bar_size, color="green", canvas_offset=fish_left)
                        else:
                            self.draw_bar_minigame(bar_center=bar_center,box_size=40, color="green", canvas_offset=fish_left)
                        self.draw_bar_minigame(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left)
                    pid_found = 2
                else:
                    if self.vars["fish_overlay"].get() == "on":
                        # Main code
                        if self.vars["bar_size"].get() == "on":
                            self.draw_bar_minigame(bar_center=bar_center,box_size=bar_size, color="green", canvas_offset=fish_left)
                        else:
                            self.draw_bar_minigame(bar_center=bar_center,box_size=40, color="green", canvas_offset=fish_left)
                        self.draw_bar_minigame(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left)
                        # Debug code
                        self.draw_bar_minigame(bar_center=max_left, box_size=15, color="lightblue", canvas_offset=fish_left)
                        self.draw_bar_minigame(bar_center=max_right, box_size=15, color="lightblue", canvas_offset=fish_left)
                    pid_found = 0
            elif arrow_center: # Arrow found
                # Find arrow position
                capture_width = fish_right - fish_left
                arrow_indicator_x = self._find_arrow_indicator_x(img, arrow_hex, arrow_tol, mouse_down)
                if self.vars["fish_overlay"].get() == "on":
                    self.draw_bar_minigame(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left)
                # Calculate distance between arrow and fish
                distance = abs((arrow_center[0] + fish_left) - fish_x)
                threshold = self.initial_bar_size if self.initial_bar_size else 300
                if distance < threshold: # Check if distance is below initial_bar_size to use bar center logic.
                    if arrow_indicator_x is not None:
                        # Estimate bar center using arrow-based logic
                        estimated_bar_center = self._update_arrow_box_estimation(arrow_indicator_x, mouse_down, capture_width)
                        
                        if estimated_bar_center is not None:
                            if self.vars["fish_overlay"].get() == "on":
                                arrow_center = estimated_bar_center + fish_left
                                self.draw_bar_minigame(bar_center=arrow_center,box_size=40, color="yellow", canvas_offset=fish_left)
                            # Convert from relative to screen coordinates
                            bar_center = int(estimated_bar_center + fish_left)
                            pid_found = 0
                        else:
                            if self.vars["fish_overlay"].get() == "on":
                                self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=10, color="yellow", canvas_offset=fish_left)
                            pid_found = 1
                    else:
                        if self.vars["fish_overlay"].get() == "on":
                            self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=10, color="yellow", canvas_offset=fish_left)
                else:
                    if distance < 0: # Fish is left of arrow
                        pid_found = 2
                    else:
                        pid_found = 1
                    self.draw_bar_minigame(bar_center=arrow_center[0],box_size=20, color="yellow", canvas_offset=fish_left)
            else: # No arrow / bar found
                pid_found = 1
            # PID calculation
            if pid_found == 0 and bar_center is not None:
                error = fish_x - bar_center
                control = self._pid_control(error)

                # Map PID output to mouse clicks using hysteresis to avoid jitter/oscillation
                control = max(-100, min(100, control))

                # Hysteresis thresholds (tune if necessary)
                on_thresh = thresh
                off_thresh = thresh * 0.5

                if control > on_thresh:
                    hold_mouse()
                elif control < -on_thresh:
                    release_mouse()
                else:
                    # Action 0: Within deadzone
                    if abs(control) < off_thresh:
                        release_mouse()
            elif pid_found == 1:
                release_mouse()
            elif pid_found == 2:
                hold_mouse()
            time.sleep(scan_delay)
    def stop_macro(self):
        if not self.macro_running:
            return
        self.macro_running = False
        self._reset_pid_state()
        self.hide_minigame()
        self.after(0, self.deiconify)  # show window safely
        self.set_status("Macro Status: Stopped")
if __name__ == "__main__":
    app = App()
    app.mainloop()