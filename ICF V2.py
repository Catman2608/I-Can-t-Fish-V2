# Initialization
from customtkinter import *
import tkinter as tk
from PIL import Image
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
        
        # Screen size (cache once – thread safe)
        self.SCREEN_WIDTH = self.winfo_screenwidth()
        self.SCREEN_HEIGHT = self.winfo_screenheight()

        # Window 
        self.geometry("800x550")
        self.title("I Can't Fish V2")

        # Macro state
        self.macro_running = False
        self.macro_thread = None

        # PID state variables
        self.pid_integral = 0.0
        self.prev_error = 0.0
        self.last_time = None

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

        # Start hotkey listener
        self.key_listener = KeyListener(on_press=self.on_key_press)
        self.key_listener.daemon = True
        self.key_listener.start()

        # Status Bar 
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        logo_image = CTkImage(
            light_image=Image.open(os.path.join(BASE_DIR, "icf_light.png")),
            dark_image=Image.open(os.path.join(BASE_DIR, "icf_dark.png")),
            size=(256, 54)
        )
        self.logo_image = logo_image

        logo_label = CTkLabel(self, image=self.logo_image, text="")
        logo_label.grid(row=0, column=0, columnspan=6, pady=10)
        # Status Label 
        self.status_label = CTkLabel(self, text="Macro status: Idle") 
        self.status_label.grid( row=0, column=0, columnspan=6, pady=15, padx=20, sticky="w")
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
        self.init_minigame_window()
        self.show_minigame()
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

        CTkLabel(casting, text="Perfect Cast Tolerance:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_cast_tolerance_entry = CTkEntry(casting, placeholder_text="5", width=120)
        perfect_cast_tolerance_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["perfect_cast_tolerance"] = perfect_cast_tolerance_entry

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

        shake_color_entry = CTkEntry(frame, placeholder_text="5", width=120)
        shake_color_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["shake_color_tolerance"] = shake_color_entry
        
        CTkLabel(frame, text="Shake Scan Delay:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        shake_delay_entry = CTkEntry(frame, placeholder_text="5", width=120)
        shake_delay_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["shake_scan_delay"] = shake_delay_entry
        
        CTkLabel(frame, text="Shake Failsafe (attempts):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        shake_failsafe_entry = CTkEntry(frame, placeholder_text="41", width=120)
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
        left_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=left_color_var)
        left_color_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["left_bar_color"] = left_color_entry

        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_bar_color"] = right_color_var
        CTkLabel(frame, text="Right Bar Color (#RRGGBB):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        right_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=right_color_var)
        right_color_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["right_bar_color"] = right_color_entry
        
        arrow_color_var = StringVar(value="#FFFFFF")
        self.vars["arrow_color"] = arrow_color_var
        CTkLabel(frame, text="Arrow Color (#RRGGBB):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        arrow_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=arrow_color_var)
        arrow_color_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["arrow_color"] = arrow_color_entry
        
        CTkLabel(frame, text="Fish Color (#RRGGBB):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        fish_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=fish_color_var)
        fish_color_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["fish_color"] = fish_color_entry
        
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=0, column=2, padx=12, pady=10, sticky="w"
        )
        left_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=0, column=3, padx=12, pady=10, sticky="w")
        self.widgets["left_tolerance"] = left_tolerance_entry
        
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=1, column=2, padx=12, pady=10, sticky="w"
        )
        right_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=1, column=3, padx=12, pady=10, sticky="w")
        self.widgets["right_tolerance"] = right_tolerance_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=2, column=2, padx=12, pady=10, sticky="w"
        )
        arrow_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120)
        arrow_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        self.widgets["arrow_tolerance"] = arrow_tolerance_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=3, column=2, padx=12, pady=10, sticky="w"
        )
        shake_tolerance_var = StringVar(value="5")
        self.vars["shake_tolerance"] = shake_tolerance_var
        fish_tolerance_entry = CTkEntry(frame, placeholder_text="0", width=120, textvariable=shake_tolerance_var)
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
        bar_ratio_entry = CTkEntry(frame2, placeholder_text="0.5", width=120)
        bar_ratio_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["bar_ratio"] = bar_ratio_entry
        
        CTkLabel(frame2, text="Scan delay (seconds):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        shake_scan_delay_var = StringVar(value="0.01")
        self.vars["shake_scan_delay"] = shake_scan_delay_var
        scan_delay_entry = CTkEntry(frame2, placeholder_text="0.01", width=120, textvariable=shake_scan_delay_var)
        scan_delay_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["scan_delay"] = scan_delay_entry

        CTkLabel(frame2, text="Restart Delay:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        restart_delay_entry = CTkEntry(frame2, placeholder_text="1", width=120)
        restart_delay_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["restart_delay"] = restart_delay_entry

        frame3 = CTkFrame(
            parent,
            fg_color="#222222",
            border_color="#7ed321",
            border_width=2
        )
        frame3.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(frame3, text="Proportional gain:").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        p_gain_entry = CTkEntry(frame3, placeholder_text="0.01", width=120)
        p_gain_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["proportional_gain"] = p_gain_entry
        
        CTkLabel(frame3, text="Derivative gain:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        d_gain_entry = CTkEntry(frame3, placeholder_text="0.01", width=120)
        d_gain_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["derivative_gain"] = d_gain_entry

        CTkLabel(frame3, text="Velocity Smoothing:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        velocity_smoothing_entry = CTkEntry(frame3, placeholder_text="6", width=120)
        velocity_smoothing_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["velocity_smoothing"] = velocity_smoothing_entry
    # SUPPORT SETTINGS TAB
    def build_support_tab(self, parent):
        # Discord Webhook Settings
        webhook_combobox = CTkFrame(
            parent, fg_color="#222222",
            border_color="#5865f2", border_width=2
        )
        webhook_combobox.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(webhook_combobox, text="Webhook URL:").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        webhook_url_entry = CTkEntry(webhook_combobox, placeholder_text="[Enter webhook link here]", width=240)
        webhook_url_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["webhook_url"] = webhook_url_entry

        CTkLabel(webhook_combobox, text="User ID:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        user_id_entry = CTkEntry(webhook_combobox, placeholder_text="[Copy your user ID and paste it here]", width=240)
        user_id_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["user_id"] = user_id_entry
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

        # Save color vars explicitly
        for key in ["left_bar_color", "right_bar_color", "arrow_color", "fish_color", "bar_ratio", "velocity_smoothing"]:
            if key in self.vars:
                data[key] = self.vars[key].get()

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
            
    def load_settings(self, config_name):
        """Load settings from JSON file"""
        path = self.get_config_path(config_name)

        if not os.path.exists(path):
            self.set_status(f"Config not found: {config_name}")
            return
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Load color vars explicitly
            for key in ["left_bar_color", "right_bar_color", "arrow_color", "fish_color", "bar_ratio", "velocity_smoothing"]:
                if key in data and key in self.vars:
                    self.vars[key].set(data[key])
            
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
    def _get_screen_size(self):
        self.update_idletasks()  # ensure Tk is initialized
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        return width, height

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
    
    def _find_bar_edges(
        self,
        frame,
        left_hex,
        right_hex,
        tolerance=12,
        scan_height_ratio=0.55
    ):
        if frame is None:
            return None, None

        h, w, _ = frame.shape
        y = int(h * scan_height_ratio)

        left_bgr = self._hex_to_bgr(left_hex)
        right_bgr = self._hex_to_bgr(right_hex)

        if left_bgr is None or right_bgr is None:
            return None, None

        tolerance = int(np.clip(tolerance, 0, 255))

        line = frame[y].astype(np.int16)

        left_mask = np.all(
            np.abs(line - left_bgr) <= tolerance,
            axis=1
        )

        right_mask = np.all(
            np.abs(line - right_bgr) <= tolerance,
            axis=1
        )

        left_indices = np.where(left_mask)[0]
        right_indices = np.where(right_mask)[0]

        if left_indices.size == 0 or right_indices.size == 0:
            return None, None

        return int(left_indices[0]), int(right_indices[-1])

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
            kp = float(self.widgets["proportional_gain"].get() or 0.6)
        except:
            kp = 0.6
        
        try:
            kd = float(self.widgets["derivative_gain"].get() or 0.2)
        except:
            kd = 0.2
        
        # Small integral term to reduce steady-state error
        ki = 0.02
        
        return kp, kd, ki
    
    def _pid_control(self, error):
        """
        PID control calculation for minigame bar tracking.
        
        Args:
            error: Current position error (fish_pos - bar_center)
        
        Returns:
            Control output value
        """
        now = time.perf_counter()
        
        if self.last_time is None:
            self.last_time = now
            self.prev_error = error
            return 0.0
        
        dt = now - self.last_time
        if dt <= 0:
            return 0.0
        
        kp, kd, ki = self._get_pid_gains()
        
        # Integral
        self.pid_integral += error * dt
        self.pid_integral = max(-100, min(100, self.pid_integral))  # anti-windup clamp
        
        # Derivative
        derivative = (error - self.prev_error) / dt
        
        output = (
            kp * error +
            ki * self.pid_integral +
            kd * derivative
        )
        
        self.prev_error = error
        self.last_time = now
        
        return output
    
    def _reset_pid_state(self):
        """Reset PID control state variables."""
        self.pid_integral = 0.0
        self.prev_error = 0.0
        self.last_time = None
        
        # Also reset arrow estimation state
        self.last_indicator_x = None
        self.last_holding_state = None
        self.estimated_box_length = None
        self.last_left_x = None
        self.last_right_x = None
        self.last_known_box_center_x = None
    
    def _find_arrow_centroid(self, frame, arrow_hex, tolerance):
        """
        Find the centroid (center point) of the arrow indicator using contour detection.
        
        Args:
            frame: BGR numpy array
            arrow_hex: Hex color of arrow
            tolerance: Color tolerance
        
        Returns:
            X coordinate of arrow centroid, or None if not found
        """
        pixels = self._pixel_search(frame, arrow_hex, tolerance)
        if not pixels:
            return None
        
        # Create a mask from pixels
        mask = np.zeros((frame.shape[0], frame.shape[1]), dtype=np.uint8)
        for x, y in pixels:
            mask[y, x] = 255
        
        # Find contours
        try:
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not contours:
                return None
            
            # Get largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            
            # Calculate centroid
            M = cv2.moments(largest_contour)
            if M["m00"] != 0:
                centroid_x = int(M["m10"] / M["m00"])
                return centroid_x
        except:
            return None
        
        return None
    
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
        
        # Clamp to capture bounds
        if self.last_left_x < 0:
            self.last_left_x = 0.0
            self.last_right_x = self.estimated_box_length
        elif self.last_right_x > capture_width:
            self.last_right_x = float(capture_width)
            self.last_left_x = self.last_right_x - self.estimated_box_length
        
        # Calculate and store center
        box_center = (self.last_left_x + self.last_right_x) / 2.0
        self.last_known_box_center_x = box_center
        
        # Update tracking variables for next frame
        self.last_indicator_x = arrow_centroid_x
        self.last_holding_state = is_holding
        
        return box_center
    # === MINIGAME WINDOW (instance methods) ===
    def init_minigame_window(self):
        """
        Create the minigame window and canvas (only once).
        """
        if self.minigame_window and self.minigame_window.winfo_exists():
            return

        self.minigame_window = tk.Toplevel(self)
        self.minigame_window.geometry("800x50+560+660")
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
        - Fishing bar
        """

        # Guard against missing center
        if bar_center is None:
            return

        # Calculate bar edges
        left_edge = bar_center - box_size
        right_edge = bar_center + box_size

        # Main bar
        bx1 = left_edge - canvas_offset
        bx2 = right_edge - canvas_offset
        self.draw_box(bx1, bar_y1, bx2, bar_y2, fill="#000000", outline=color)

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
                pass  # future perfect cast
            else:
                self._execute_cast_normal()

            # Optional delay after cast
            try:
                delay = float(self.widgets["casting_delay"].get() or 0.6)
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

    def _execute_cast_normal(self):
        # Basic cast: hold left click briefly
        mouse_controller.press(Button.left)
        duration = float(self.widgets["cast_duration"].get() or 0.6)
        time.sleep(duration)  # adjust cast strength
        mouse_controller.release(Button.left)
        time.sleep(0.2)

    def _execute_shake_click(self):
        self.set_status("Shake Mode: Click")
        width, height = self._get_screen_size()

        shake_left = int(self.SCREEN_WIDTH / 4.8)
        shake_top = int(self.SCREEN_HEIGHT / 6.1714)
        shake_right = int(self.SCREEN_WIDTH / 1.28)
        shake_bottom = int(self.SCREEN_HEIGHT / 1.35)

        # 434 705 1029 794
        # macOS-safe coordinates
        fish_left = int(self.SCREEN_WIDTH / 3.3684)
        fish_top = int(self.SCREEN_HEIGHT / 1.2766)
        fish_right = int(self.SCREEN_WIDTH / 1.42)
        fish_bottom = int(self.SCREEN_HEIGHT / 1.1335)

        fish_hex = self.vars["fish_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())
        scan_delay = float(self.vars["shake_scan_delay"].get())
        failsafe = int(self.widgets["shake_failsafe"].get() or 40)

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

        # --- Regions ---
        width, height = self._get_screen_size()
        # macOS-safe coordinates
        fish_left = int(self.SCREEN_WIDTH / 3.3684)
        fish_top = int(self.SCREEN_HEIGHT / 1.2766)
        fish_right = int(self.SCREEN_WIDTH / 1.42)
        fish_bottom = int(self.SCREEN_HEIGHT / 1.1335)

        fish_hex = self.vars["fish_color"].get()
        tolerance = int(self.vars["shake_tolerance"].get())
        scan_delay = float(self.vars["shake_scan_delay"].get())
        failsafe = int(self.widgets["shake_failsafe"].get() or 20)

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
        width, height = self._get_screen_size()

        # macOS-safe coordinates
        fish_left = int(self.SCREEN_WIDTH / 3.3684)
        fish_top = int(self.SCREEN_HEIGHT / 1.2766)
        fish_right = int(self.SCREEN_WIDTH / 1.42)
        fish_bottom = int(self.SCREEN_HEIGHT / 1.1335)

        fish_hex = self.vars["fish_color"].get()
        arrow_hex = self.vars["arrow_color"].get()
        left_bar_hex = self.vars["left_bar_color"].get()
        right_bar_hex = self.vars["right_bar_color"].get()

        try:
            thresh = float(self.widgets["velocity_smoothing"].get() or 10)
        except:
            thresh = 10

        try:
            bar_ratio = float(self.widgets["bar_ratio"].get() or 0.5)
        except:
            bar_ratio = 0.5
        tolerance = int(self.vars["shake_tolerance"].get())

        DEADZONE = 8  # similar to old bar_ratio feel
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

        while self.macro_running: # Main macro loop
            img = self._grab_screen_region(
                fish_left, fish_top, fish_right, fish_bottom
            )

            if img is None:
                time.sleep(0.01)
                continue

            fish_center = self._find_color_center(img, fish_hex, tolerance)
            arrow_center = self._find_color_center(img, arrow_hex, tolerance)
            left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, right_bar_hex, tolerance)

            # ---- FISH NOT FOUND ----
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

            # ---- BARS NOT FOUND ----
            bars_found = left_bar_center is not None and right_bar_center is not None

            fish_x = fish_center[0] + fish_left
            self.clear_minigame()

            # Bar Logic
            if left_bar_center is not None and right_bar_center is not None:
                bar_center = int((left_bar_center + right_bar_center) / 2 + fish_left)

                bar_size = abs(right_bar_center - left_bar_center)
                deadzone = bar_size * bar_ratio

                max_left = fish_left + deadzone
                max_right = fish_right - deadzone
            else:
                bar_center = None
                max_left = fish_left
                max_right = fish_right

            # Max left and right is added back
            if fish_x < max_left or fish_x > max_right:
                if fish_x < max_left:
                    self.draw_bar_minigame(bar_center=max_left, box_size=7, color="lightblue", canvas_offset=fish_left)
                    self.draw_bar_minigame(bar_center=fish_x, box_size=5, color="red", canvas_offset=fish_left)
                    release_mouse()
                else:
                    hold_mouse()
                    self.draw_bar_minigame(bar_center=max_right, box_size=7, color="lightblue", canvas_offset=fish_left)
                    self.draw_bar_minigame(bar_center=fish_x, box_size=5, color="red", canvas_offset=fish_left)
            elif left_bar_center and right_bar_center:
                if bars_found and self.vars["fish_overlay"].get() == "on":
                    self.draw_bar_minigame(bar_center=bar_center, box_size=20, color="green", canvas_offset=fish_left)
                    self.draw_bar_minigame(bar_center=fish_x, box_size=5, color="red", canvas_offset=fish_left)

                # PID calculation
                error = fish_x - bar_center
                control = self._pid_control(error)
                
                # Map PID output to mouse clicks using hysteresis
                control = max(-100, min(100, control))
                
                # Hysteresis thresholds for smooth control
                on_thresh = thresh  # threshold to start holding
                off_thresh = int(thresh / 2)  # threshold to release

                if control > on_thresh:
                    if bars_found and self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(bar_center=bar_center + 50, box_size=5, color="green", canvas_offset=fish_left)
                    hold_mouse()
                elif control < -on_thresh:
                    if bars_found and self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(bar_center=bar_center - 50, box_size=5, color="green", canvas_offset=fish_left)
                    release_mouse()
                else:
                    # Within deadzone
                    if abs(control) < off_thresh:
                        if bars_found and self.vars["fish_overlay"].get() == "on":
                            self.draw_bar_minigame(bar_center=bar_center - 50, box_size=5, color="green", canvas_offset=fish_left)
                        release_mouse()

            # ---- ARROW FALLBACK (IRUS-style box estimation) ----
            elif arrow_center:
                # Use arrow to estimate bar center (IRUS 675 logic)
                capture_width = fish_right - fish_left
                arrow_centroid_x = self._find_arrow_centroid(img, arrow_hex, tolerance)
                if self.vars["fish_overlay"].get() == "on":
                    self.draw_bar_minigame(bar_center=fish_x, box_size=5, color="red", canvas_offset=fish_left)

                if arrow_centroid_x is not None:
                    # Estimate bar center using arrow-based logic
                    estimated_bar_center = self._update_arrow_box_estimation(
                        arrow_centroid_x, 
                        mouse_down,  # is_holding
                        capture_width
                    )
                    
                    if estimated_bar_center is not None:
                        if self.vars["fish_overlay"].get() == "on":
                            arrow_center = estimated_bar_center + fish_left
                            self.draw_bar_minigame(bar_center=arrow_center, box_size=20, color="yellow", canvas_offset=fish_left)
                        # Convert from relative to screen coordinates
                        bar_center = int(estimated_bar_center + fish_left)
                        
                        # PID calculation with estimated bar
                        error = fish_x - bar_center
                        control = self._pid_control(error)
                        
                        # Map PID output to mouse clicks using hysteresis
                        control = max(-100, min(100, control))
                        
                        on_thresh = 10
                        off_thresh = 5
                        
                        if control > on_thresh:
                            if self.vars["fish_overlay"].get() == "on":
                                self.draw_bar_minigame(bar_center=arrow_center + 50, box_size=5, color="yellow", canvas_offset=fish_left)
                            hold_mouse()
                        elif control < -on_thresh:
                            if self.vars["fish_overlay"].get() == "on":
                                self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=5, color="yellow", canvas_offset=fish_left)
                            release_mouse()
                        else:
                            if abs(control) < off_thresh:
                                if self.vars["fish_overlay"].get() == "on":
                                    self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=5, color="yellow", canvas_offset=fish_left)
                                release_mouse()
                    else:
                        if self.vars["fish_overlay"].get() == "on":
                            self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=5, color="yellow", canvas_offset=fish_left)
                        release_mouse()
                else:
                    if self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(bar_center=arrow_center - 50, box_size=5, color="yellow", canvas_offset=fish_left)
                    release_mouse()
            # ---- NOTHING FOUND ----
            else:
                release_mouse()

            time.sleep(0.01)
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