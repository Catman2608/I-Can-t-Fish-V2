# Initialization
from customtkinter import *
import os
import glob
# Keyboard and Mouse
from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController
# Mouse Button
from pynput.mouse import Button
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
# ctypes and windll doesn't work on non-windows systems so I don't use it there
# OpenCV and MSS for pixel search
import cv2
import numpy as np
import mss
# Initialize controllers
keyboard_controller = KeyboardController()
mouse_controller = MouseController()
# Screen width and height
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
# Set appearance
set_default_color_theme("blue")
set_appearance_mode("dark")

class App(CTk):
    def __init__(self):
        super().__init__()
        self.widgets = {}     # Entry / Slider / Combobox widgets
        self.vars = {}        # IntVar / StringVar / BooleanVar
        self.checkboxes = {}   # CTkCheckBox widgets
        self.comboboxes = {}   # CTkComboBox widgets

        # Window 
        self.geometry("800x550")
        self.title("I Can't Fish V2")

        # Macro state
        self.macro_running = False
        self.macro_thread = None

        # Start hotkey listener
        self.key_listener = KeyListener(on_press=self.on_key_press)
        self.key_listener.daemon = True
        self.key_listener.start()

        # Status Bar 
        self.status_label = CTkLabel(self, text="Macro Status: Idle")
        self.status_label.grid(
            row=0, column=0, columnspan=6,
            pady=15, padx=20, sticky="w"
        )

        # Tabs 
        self.tabs = CTkTabview(self)
        self.tabs.grid(
            row=1, column=0, columnspan=6,
            padx=20, pady=10, sticky="nsew"
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

        for i in range(6):
            self.grid_columnconfigure(i, weight=0)
        self.grid_columnconfigure(5, weight=1)  # empty stretch column

        last = self.load_last_config_name()
        self.load_settings(last or "default.json")
    # BASIC SETTINGS TAB
    def build_basic_tab(self, parent):
        # Automation 
        automation = CTkFrame(
            parent, fg_color="#222222",
            border_color="#4a90e2", border_width=2
        )
        automation.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        # Create and store checkboxes with StringVar
        auto_rod_var = StringVar(value="off")
        self.vars["auto_select_rod"] = auto_rod_var
        auto_rod_cb = CTkCheckBox(automation, text="Auto Select Rod", 
                                 variable=auto_rod_var, onvalue="on", offvalue="off")
        auto_rod_cb.grid(row=0, column=0, padx=12, pady=8, sticky="w")
        self.checkboxes["auto_select_rod"] = auto_rod_cb

        auto_zoom_var = StringVar(value="off")
        self.vars["auto_zoom_in"] = auto_zoom_var
        auto_zoom_cb = CTkCheckBox(automation, text="Auto Zoom In", 
                                  variable=auto_zoom_var, onvalue="on", offvalue="off")
        auto_zoom_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        self.checkboxes["auto_zoom_in"] = auto_zoom_cb

        fish_overlay_var = StringVar(value="off")
        self.vars["fish_overlay"] = fish_overlay_var
        fish_overlay_cb = CTkCheckBox(automation, text="Fish Overlay", 
                                     variable=fish_overlay_var, onvalue="on", offvalue="off")
        fish_overlay_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")
        self.checkboxes["fish_overlay"] = fish_overlay_cb

        CTkLabel(automation, text="Capture Mode:").grid(
            row=3, column=0, padx=12, pady=6, sticky="w"
        )

        capture_var = StringVar(value="DXCAM")
        self.vars["capture_mode"] = capture_var
        capture_cb = CTkComboBox(
            automation,
            values=["DXCAM", "MSS"],
            variable=capture_var,
            command=lambda v: self.set_status(f"Capture mode: {v}")
        )
        capture_cb.grid(row=3, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["capture_mode"] = capture_cb

        #  Configs 
        configs = CTkFrame(
            parent, fg_color="#222222",
            border_color="#4a90e2", border_width=2
        )
        configs.grid(row=0, column=1, padx=20, pady=20, sticky="nw")

        CTkLabel(configs, text="Active Configuration:").grid(
            row=0, column=0, padx=12, pady=6, sticky="w"
        )

        config_list = self.load_configs()
        config_var = StringVar(value=config_list[0] if config_list else "default.json")
        self.vars["active_config"] = config_var
        config_cb = CTkComboBox(
            configs,
            values=config_list,
            variable=config_var,
            command=lambda v: self.set_status(f"Loaded {v}")
        )
        config_cb.grid(row=0, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["active_config"] = config_cb

        CTkLabel(configs, text="F5: Start | F7: Stop").grid(
            row=1, column=0, padx=12, pady=6, sticky="w"
        )
        CTkButton(
            configs,
            text="Rebind Hotkeys",
            corner_radius=32,
            command=lambda: self.set_status("Press a key to rebind...")
        ).grid(row=1, column=1, padx=12, pady=12, sticky="w")

        #  Casting 
        casting = CTkFrame(
            parent, fg_color="#222222",
            border_color="#4a90e2", border_width=2
        )
        casting.grid(row=1, column=0, padx=20, pady=20, sticky="nw")

        perfect_cast_var = StringVar(value="off")
        self.vars["perfect_cast"] = perfect_cast_var
        perfect_cast_cb = CTkCheckBox(casting, text="Perfect Cast (slower)", 
                                     variable=perfect_cast_var, onvalue="on", offvalue="off")
        perfect_cast_cb.grid(row=0, column=0, padx=12, pady=12, sticky="w")
        self.checkboxes["perfect_cast"] = perfect_cast_cb

        CTkLabel(casting, text="Cast duration").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        cast_duration_entry = CTkEntry(casting, placeholder_text="0.6", width=120)
        cast_duration_entry.grid(row=1, column=1, padx=12, pady=8, sticky="w")
        self.widgets["cast_duration"] = cast_duration_entry
        
        CTkLabel(casting, text="Delay after casting").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        casting_delay_entry = CTkEntry(casting, placeholder_text="0.6", width=120)
        casting_delay_entry.grid(row=2, column=1, padx=12, pady=8, sticky="w")
        self.widgets["casting_delay"] = casting_delay_entry

        support = CTkFrame(
            parent, fg_color="#222222",
            border_color="#4a90e2", border_width=2
        )
        support.grid(row=1, column=1, padx=20, pady=20, sticky="nw")
        CTkLabel(support, text="Join Longest's Automation Hub Discord").grid(
            row=0, column=0, padx=12, pady=8, sticky="w"
        )
        CTkLabel(support, text="If it's your first time, watch the video below").grid(
            row=1, column=0, padx=12, pady=8, sticky="w"
        )
        CTkLabel(support, text="I Can't Fish V2 Tutorial").grid(
            row=2, column=0, padx=12, pady=8, sticky="w"
        )
    # MISC SETTINGS TAB
    def build_misc_tab(self, parent):
        # Auto Select Rod Settings 
        auto_select_rod = CTkFrame(
            parent, fg_color="#222222",
            border_color="#50e3c2", border_width=2
        )
        auto_select_rod.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
    # SHAKE SETTINGS TAB
    def build_shake_tab(self, parent):
        frame = CTkFrame(
            parent, fg_color="#222222",
            border_color="#bd10e0", border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(frame, text="Shake mode:").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )

        shake_var = StringVar(value="Click")
        self.vars["shake_mode"] = shake_var
        shake_cb = CTkComboBox(
            frame,
            values=["Click", "Navigation"],
            variable=shake_var,
            command=lambda v: self.set_status(f"Shake mode: {v}")
        )
        shake_cb.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["shake_mode"] = shake_cb

        CTkLabel(frame, text="Click Shake Color Tolerance:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        shake_color_entry = CTkEntry(frame, placeholder_text="5", width=140)
        shake_color_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["shake_color_tolerance"] = shake_color_entry
        
        CTkLabel(frame, text="Shake Scan Delay:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        shake_delay_entry = CTkEntry(frame, placeholder_text="5", width=140)
        shake_delay_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["shake_scan_delay"] = shake_delay_entry
        
        CTkLabel(frame, text="Shake Failsafe (attempts):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        shake_failsafe_entry = CTkEntry(frame, placeholder_text="41", width=140)
        shake_failsafe_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["shake_failsafe"] = shake_failsafe_entry
    # MINIGAME SETTINGS TAB
    def build_minigame_tab(self, parent):
        frame = CTkFrame(
            parent, fg_color="#222222",
            border_color="#7ed321", border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        left_color_var = StringVar(value="#F1F1F1")
        self.vars["left_bar_color"] = left_color_var
        CTkLabel(frame, text="Left Bar Color (#RRGGBB):").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        left_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140, textvariable=left_color_var)
        left_color_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["left_bar_color"] = left_color_entry

        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_bar_color"] = right_color_var
        CTkLabel(frame, text="Right Bar Color (#RRGGBB):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        right_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140, textvariable=right_color_var)
        right_color_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["right_bar_color"] = right_color_entry
        
        arrow_color_var = StringVar(value="#FFFFFF")
        self.vars["arrow_color"] = arrow_color_var
        CTkLabel(frame, text="Arrow Color (#RRGGBB):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        arrow_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140, textvariable=arrow_color_var)
        arrow_color_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["arrow_color"] = arrow_color_entry
        
        CTkLabel(frame, text="Fish Color (#RRGGBB):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        fish_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140, textvariable=fish_color_var)
        fish_color_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["fish_color"] = fish_color_entry
        
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=0, column=2, padx=12, pady=10, sticky="w"
        )
        left_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=140, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=0, column=3, padx=12, pady=10, sticky="w")
        self.widgets["left_tolerance"] = left_tolerance_entry
        
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=1, column=2, padx=12, pady=10, sticky="w"
        )
        right_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=140, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=1, column=3, padx=12, pady=10, sticky="w")
        self.widgets["right_tolerance"] = right_tolerance_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=2, column=2, padx=12, pady=10, sticky="w"
        )
        arrow_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=140)
        arrow_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        self.widgets["arrow_tolerance"] = arrow_tolerance_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=3, column=2, padx=12, pady=10, sticky="w"
        )
        shake_tolerance_var = StringVar(value="5")
        self.vars["shake_tolerance"] = shake_tolerance_var
        fish_tolerance_entry = CTkEntry(frame, placeholder_text="0", width=140, textvariable=shake_tolerance_var)
        fish_tolerance_entry.grid(row=3, column=3, padx=12, pady=10, sticky="w")
        self.widgets["fish_tolerance"] = fish_tolerance_entry
        
        frame2 = CTkFrame(
            parent,
            fg_color="#222222",
            border_color="#7ed321",
            border_width=2
        )
        frame2.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        
        CTkLabel(frame2, text="Bar Ratio From Side:").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        bar_ratio_entry = CTkEntry(frame2, placeholder_text="0.5", width=140)
        bar_ratio_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["bar_ratio"] = bar_ratio_entry
        
        CTkLabel(frame2, text="Scan delay (seconds):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        shake_scan_delay_var = StringVar(value="0.01")
        self.vars["shake_scan_delay"] = shake_scan_delay_var
        scan_delay_entry = CTkEntry(frame2, placeholder_text="0.01", width=140, textvariable=shake_scan_delay_var)
        scan_delay_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["scan_delay"] = scan_delay_entry
        
        CTkLabel(frame2, text="Proportional gain:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        p_gain_entry = CTkEntry(frame2, placeholder_text="0.01", width=140)
        p_gain_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["proportional_gain"] = p_gain_entry
        
        CTkLabel(frame2, text="Derivative gain:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        d_gain_entry = CTkEntry(frame2, placeholder_text="0.01", width=140)
        d_gain_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["derivative_gain"] = d_gain_entry
    # SUPPORT SETTINGS TAB
    def build_support_tab(self, parent):
        # Discord Webhook Settings
        webhook_combobox = CTkFrame(
            parent, fg_color="#222222",
            border_color="#5865f2", border_width=2
        )
        webhook_combobox.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
    # Save and load settings
    def load_configs(self):
        config_dir = os.path.join(os.path.dirname(__file__), "configs")
        if not os.path.isdir(config_dir):
            return ["No configs found"]

        files = [
            os.path.basename(f)
            for f in glob.glob(os.path.join(config_dir, "*.json"))
        ]
        return files or ["No configs found"]
    def get_config_path(self, config_name):
        config_dir = os.path.join(os.path.dirname(__file__), "configs")
        return os.path.join(config_dir, config_name)
    def _save_entry(self, data, key, widget_name):
        widget = self.widgets.get(widget_name)
        if widget:
            data[key] = widget.get()
    def _save_var(self, data, key, var_name):
        var = self.vars.get(var_name)
        if var:
            data[key] = var.get()
    def _load_entry(self, data, key, widget_name, default=""):
        widget = self.widgets.get(widget_name)
        if widget:
            widget.delete(0, END)
            widget.insert(0, data.get(key, default))
    def _load_var(self, data, key, var_name):
        var = self.vars.get(var_name)
        if var:
            var.set(data.get(key, var.get()))
    def save_last_config_name(self, config_name):
        path = os.path.join(os.path.dirname(__file__), "last_config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"last_config": config_name}, f)

    def load_last_config_name(self):
        path = os.path.join(os.path.dirname(__file__), "last_config.json")
        if not os.path.exists(path):
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("last_config")
        except Exception:
            return None
    def save_settings(self, config_name):
        """Save all settings to JSON file"""
        data = {}
        
        # Save checkbox states
        for key, var in self.vars.items():
            if key in ["auto_select_rod", "auto_zoom_in", "fish_overlay", "perfect_cast"]:
                data[key] = var.get()
        
        # Save combobox values
        for key, cb in self.comboboxes.items():
            data[key] = cb.get()
        
        # Save entry values
        for key, widget in self.widgets.items():
            if isinstance(widget, CTkEntry):
                data[key] = widget.get()
        
        # Create configs directory if it doesn't exist
        config_dir = os.path.join(os.path.dirname(__file__), "configs")
        if not os.path.isdir(config_dir):
            os.makedirs(config_dir, exist_ok=True)
        
        # Save to file
        path = self.get_config_path(config_name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        # Update last config
        self.save_last_config_name(config_name)
        
        # Update combobox list
        config_list = self.load_configs()
        if self.comboboxes.get("active_config"):
            self.comboboxes["active_config"].configure(values=config_list)
            self.vars["active_config"].set(config_name)
        
        self.set_status(f"Saved settings to: {config_name}")
    
    def load_settings(self, config_name):
        """Load settings from JSON file"""
        path = self.get_config_path(config_name)
        
        if not os.path.exists(path):
            self.set_status(f"Config not found: {config_name}")
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Load checkbox states
            for key, var in self.vars.items():
                if key in data:
                    var.set(data[key])
            
            # Load combobox values
            for key, cb in self.comboboxes.items():
                if key in data and data[key] in cb.cget("values"):
                    cb.set(data[key])
            
            # Load entry values
            for key, widget in self.widgets.items():
                if key in data and isinstance(widget, CTkEntry):
                    widget.delete(0, END)
                    widget.insert(0, str(data[key]))
            
            # Update last config
            self.save_last_config_name(config_name)
            
            self.set_status(f"Loaded settings from: {config_name}")
            
        except Exception as e:
            print(f"Error loading config: {str(e)}")
    # Macro functions
    def on_key_press(self, key):
        try:
            if key == Key.f5 and not self.macro_running:
                # Save settings before starting
                config_name = self.vars["active_config"].get()
                self.save_settings(config_name)

                self.macro_running = True
                self.after(0, self.withdraw)
                threading.Thread(target=self.start_macro, daemon=True).start()

            elif key == Key.f7:
                self.stop_macro()

        except Exception as e:
            print("Hotkey error:", e)
            
    def set_status(self, text, key=None):
        self.status_label.configure(text=text)
        start_key = key
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
        mouse_controller.position = (x + 1, y)
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
    
    def _find_color_bounds(self, frame, target_color_hex, tolerance=10):
        """
        Find the bounding box of a color in a frame.
        
        Args:
            frame: BGR numpy array from cv2/mss
            target_color_hex: Hex color code (e.g., "#FFFFFF")
            tolerance: Color tolerance range (0-255)
        
        Returns:
            Dictionary with keys: min_x, max_x, min_y, max_y, or None if no pixels found
        """
        pixels = self._pixel_search(frame, target_color_hex, tolerance)
        if not pixels:
            return None
        
        x_coords = [p[0] for p in pixels]
        y_coords = [p[1] for p in pixels]
        
        return {
            "min_x": min(x_coords),
            "max_x": max(x_coords),
            "min_y": min(y_coords),
            "max_y": max(y_coords),
            "width": max(x_coords) - min(x_coords),
            "height": max(y_coords) - min(y_coords),
            "center_x": (min(x_coords) + max(x_coords)) // 2,
            "center_y": (min(y_coords) + max(y_coords)) // 2
        }
    
    def _find_white_pixel(self, frame, tolerance=10):
        """
        Find first white pixel in frame.
        
        Args:
            frame: BGR numpy array
            tolerance: Color tolerance for white
        
        Returns:
            (x, y) tuple of first white pixel, or None if not found
        """
        # Define white color range with tolerance
        lower_white = np.array([
            max(0, 255 - tolerance),
            max(0, 255 - tolerance),
            max(0, 255 - tolerance)
        ])
        upper_white = np.array([255, 255, 255])
        
        # Create mask for white pixels
        mask = np.all((frame >= lower_white) & (frame <= upper_white), axis=-1)
        
        # Find first white pixel
        white_pixels = np.argwhere(mask)
        if len(white_pixels) > 0:
            y, x = white_pixels[0]
            return (int(x), int(y))
        
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
    def _execute_cast_normal(self):
        # Basic cast: hold left click briefly
        mouse_controller.press(Button.left)
        duration = float(self.widgets["cast_duration"].get() or 0.6)
        time.sleep(duration)  # adjust cast strength
        mouse_controller.release(Button.left)
        time.sleep(0.2)

    def _execute_shake_click(self):
        self.set_status("Shake Mode: Click")

        shake_left = 400
        shake_top = 175
        shake_right = 1500
        shake_bottom = 800

        fish_left = 570
        fish_top = 860
        fish_right = 1350
        fish_bottom = 940

        fish_hex = self.vars["fish_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())
        delay = float(self.vars["shake_scan_delay"].get())

        while self.macro_running:
            shake_area = self._grab_screen_region(shake_left, shake_top, shake_right, shake_bottom)
            if shake_area is None:
                time.sleep(delay)
                continue
            detection_area = self._grab_screen_region(fish_left, fish_top, fish_right, fish_bottom)
            if detection_area is None:
                time.sleep(delay)
                continue

            # 1️⃣ Check for fish color FIRST (highest priority)
            fish_center = self._find_color_center(detection_area, fish_hex, tolerance)
            if fish_center:
                self.set_status("Entering Minigame")
                return  # exit shake mode cleanly

            # 2️⃣ Look for white shake pixel
            white_pixel = self._find_white_pixel(shake_area, tolerance)
            if white_pixel:
                x, y = white_pixel
                screen_x = shake_left + x
                screen_y = shake_top + y
                self._click_at(screen_x, screen_y)

            time.sleep(delay * 10)
    def _enter_minigame(self):
        print("Entering Bar Minigame")

        fish_left = 550
        fish_top = 860
        fish_right = 1370
        fish_bottom = 910

        fish_hex = self.vars["fish_color"].get()
        arrow_hex = self.vars["arrow_color"].get()
        left_bar_hex = self.vars["left_bar_color"].get()
        right_bar_hex = self.vars["right_bar_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())

        DEADZONE = 8  # similar to old left_right_deadzone feel
        mouse_down = False
        fish_miss_count = 0
        MAX_FISH_MISSES = 20

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

        while self.macro_running:
            img = self._grab_screen_region(
                fish_left, fish_top, fish_right, fish_bottom
            )

            if img is None:
                time.sleep(0.01)
                continue

            fish_center = self._find_color_center(img, fish_hex, tolerance)
            arrow_center = self._find_color_center(img, arrow_hex, tolerance)
            left_bar_center = self._find_color_center(img, left_bar_hex, tolerance)
            right_bar_center = self._find_color_center(img, right_bar_hex, tolerance)

            # ---- FISH NOT FOUND (old fail-safe logic) ----
            if not fish_center:
                fish_miss_count += 1
                release_mouse()

                if fish_miss_count >= MAX_FISH_MISSES:
                    release_mouse()
                    time.sleep(0.3)
                    return

                time.sleep(0.02)
                continue
            else:
                fish_miss_count = 0

            fish_x = fish_center[0] + fish_left

            # ---- BAR LOGIC (primary, like old version) ----
            if left_bar_center and right_bar_center:
                left_x = left_bar_center[0] + fish_left
                right_x = right_bar_center[0] + fish_left
                bar_center = (left_x + right_x) // 2

                if fish_x > bar_center:
                    hold_mouse()
                elif fish_x < bar_center:
                    release_mouse()
                # else: inside deadzone → do nothing

            # ---- ARROW FALLBACK (old Action 5/6) ----
            elif arrow_center:
                arrow_x = arrow_center[0] + fish_left
                delta = arrow_x - fish_x

                if delta < -6:
                    hold_mouse()
                else:
                    release_mouse()

            # ---- NOTHING FOUND ----
            else:
                release_mouse()

            time.sleep(0.01)
    def start_macro(self): # completed
        print("Macro started")
        self.macro_running = True
        self.set_status("Macro Status: Running")
        mouse_controller.position = (960, 300)
        if self.vars["auto_zoom_in"].get() == "on":
            # Beginning Alignment (no tooltips)
            for _ in range(20):
                mouse_controller.scroll(0, 1)
                time.sleep(0.05)
            mouse_controller.scroll(0, -1)
            time.sleep(0.1)
        while self.macro_running:
            # Tooltips are removed because it takes up lots of storage
            # Macro logic only
            if self.vars["auto_select_rod"].get() == "on":
                keyboard_controller.press("2")
                time.sleep(0.05)
                keyboard_controller.release("2")
                time.sleep(0.1)
                keyboard_controller.press("1")
                time.sleep(0.05)
                keyboard_controller.release("1")
                time.sleep(0.2)
            # Casting logic
            if self.vars["perfect_cast"].get() == "on":
                # Perfect Cast Logic Here (not implemented)
                pass
            else:
                self._execute_cast_normal()
            # Shake logic
            if self.vars["shake_mode"].get() == "Click":
                self._execute_shake_click()
            else:
                # Navigation shake logic here (not implemented)
                pass
            # Minigame logic
            self._enter_minigame()
        # Stop macro logic here
    def stop_macro(self):
        if not self.macro_running:
            return
        self.macro_running = False
        self.after(0, self.deiconify)  # show window safely
        self.set_status("Macro Status: Stopped")
        print("Macro stopped")
if __name__ == "__main__":
    app = App()
    app.mainloop()