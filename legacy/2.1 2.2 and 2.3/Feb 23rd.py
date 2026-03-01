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
# OpenCV and MSS for image/pixel search
import cv2
import numpy as np
import mss
# Initialize controllers
keyboard_controller = KeyboardController()
mouse_controller = MouseController()
# Set appearance
set_default_color_theme("blue")
# from AppKit import NSEvent
# Last Config Path / Fix macOS DMG issues
if sys.platform == "darwin":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
else:
    pass # You're on Windows
LAST_CONFIG_PATH = "last_config.json"
class ShakeAreaSelector(CTkToplevel):
    def __init__(self, parent, area, callback):
        super().__init__(parent)

        self.callback = callback

        self.title("Shake Area Selector")

        # Apply saved geometry
        geometry_string = f"{area['width']}x{area['height']}+{area['x']}+{area['y']}"
        self.geometry(geometry_string)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        CTkLabel(self, text="Select SHAKE area").pack(pady=20)
        self.transient(parent)      # Keep on top of parent
        self.focus_force()          # Force focus (important on macOS)
        self.lift()                 # Bring to front
    def on_close(self):
        # Force geometry update
        self.update_idletasks()

        area_data = {
            "x": self.winfo_x(),
            "y": self.winfo_y(),
            "width": self.winfo_width(),
            "height": self.winfo_height()
        }

        self.callback(area_data)
        self.destroy()

class FishAreaSelector(CTkToplevel):
    def __init__(self, parent, area, callback):
        super().__init__(parent)

        self.callback = callback

        self.title("Fish Area Selector")

        geometry_string = f"{area['width']}x{area['height']}+{area['x']}+{area['y']}"
        self.geometry(geometry_string)

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        CTkLabel(self, text="Select FISH area").pack(pady=20)

        self.transient(parent)      # Keep on top of parent
        self.focus_force()          # Force focus (important on macOS)
        self.lift()                 # Bring to front
    def on_close(self):
        # Force geometry update
        self.update_idletasks()

        area_data = {
            "x": self.winfo_x(),
            "y": self.winfo_y(),
            "width": self.winfo_width(),
            "height": self.winfo_height()
        }

        self.callback(area_data)
        self.destroy()

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
        self.title("I Can't Fish V2.2")

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
            text="I CAN'T FISH V2.2",
            font=CTkFont(size=16, weight="bold")
        )
        logo_label.grid(row=0, column=0, columnspan=6, pady=5, padx=20, sticky="w")
        # Bar Areas Variables
        self.shake_selector = None
        self.fish_selector = None

        # Top Bar Frame (Status + Buttons)
        top_bar = CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        top_bar.grid_columnconfigure(0, weight=1)

        # Status label (left side)
        self.status_label = CTkLabel(top_bar, text="Macro status: Idle")
        self.status_label.grid(row=0, column=0, sticky="w")

        # Buttons frame (right side)
        button_frame = CTkFrame(top_bar, fg_color="transparent")
        button_frame.grid(row=0, column=1, sticky="e")

        CTkButton(
            button_frame,
            text="Website",
            corner_radius=32,
            command=self.open_link("https://sites.google.com/view/icf-automation-network/")
        ).pack(side="left", padx=6)

        CTkButton(
            button_frame,
            text="YouTube",
            corner_radius=32,
            command=self.open_link("https://www.youtube.com/@HexaTitanGaming")
        ).pack(side="left", padx=6)

        CTkButton(
            button_frame,
            text="Tutorial",
            corner_radius=32,
            command=self.open_link("https://docs.google.com/document/d/1qjhgcONxpZZbSAEYiSCXoUXGjQwd7Jghf4EysWC4Cps/edit?usp=drive_link")
        ).pack(side="left", padx=6)

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
        self.tabs.add("Advanced")

        # Build tabs
        self.build_basic_tab(self.tabs.tab("Basic"))
        self.build_misc_tab(self.tabs.tab("Misc"))
        self.build_shake_tab(self.tabs.tab("Shake"))
        self.build_minigame_tab(self.tabs.tab("Minigame"))
        self.build_advanced_tab(self.tabs.tab("Advanced"))

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
        # Start key
        CTkLabel(configs, text="Start Key").grid(
            row=2, column=0, padx=12, pady=6, sticky="w"
        )
        CTkLabel(configs, text="Screenshot Key").grid(
            row=3, column=0, padx=12, pady=6, sticky="w"
        )
        CTkLabel(configs, text="Stop Key").grid(
            row=4, column=0, padx=12, pady=6, sticky="w"
        )
        # Start, screenshot and stop key changer
        start_key_var = StringVar(value="F5")
        self.vars["start_key"] = start_key_var
        start_key_entry = CTkEntry(
            configs,
            width=120,
            textvariable=start_key_var
        )
        start_key_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        screenshot_key_var = StringVar(value="F8")
        self.vars["screenshot_key"] = screenshot_key_var
        screenshot_key_entry = CTkEntry(
            configs,
            width=120,
            textvariable=screenshot_key_var
        )
        screenshot_key_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")

        stop_key_var = StringVar(value="F7")
        self.vars["stop_key"] = stop_key_var
        stop_key_entry = CTkEntry(
            configs,
            width=120,
            textvariable=stop_key_var
        )
        stop_key_entry.grid(row=4, column=1, padx=12, pady=10, sticky="w")
        CTkButton(
            configs,
            text="Change Bar Areas",
            corner_radius=32,
            command=self.open_dual_area_selector
        ).grid(row=5, column=0, padx=12, pady=12, sticky="w")
        CTkButton(
            configs,
            text="Save Misc Settings",
            corner_radius=32,
            command=self.save_misc_settings
        ).grid(row=5, column=1, padx=12, pady=12, sticky="w")
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

        cast_delay_var = StringVar(value="0.6")
        self.vars["cast_delay"] = cast_delay_var

        cast_delay_entry = CTkEntry(
            casting,
            width=120,
            textvariable=cast_delay_var
        )
        cast_delay_entry.grid(row=3, column=1, padx=12, pady=8, sticky="w")
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
        CTkLabel(pfc1_settings, text="Perfect Cast Sequence", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        CTkLabel(pfc1_settings, text="Zoom Amount:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        perfect_cast_zoom_var = StringVar(value="4")
        self.vars["perfect_cast_zoom"] = perfect_cast_zoom_var

        perfect_cast_zoom_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=perfect_cast_zoom_var
        )
        perfect_cast_zoom_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc1_settings, text="Look Down Amount (pixels):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_cast_lookdown_var = StringVar(value="1200")
        self.vars["perfect_cast_lookdown"] = perfect_cast_lookdown_var

        perfect_cast_lookdown_entry = CTkEntry(
            pfc1_settings,
            width=120,
            textvariable=perfect_cast_lookdown_var
        )
        perfect_cast_lookdown_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        # Perfect Cast Release Settings 
        pfc2_settings = CTkFrame(
            scroll,
            border_width=2
        )
        pfc2_settings.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        # ---- Perfect cast tolerance ----
        CTkLabel(pfc2_settings, text="Perfect Cast Release Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(pfc2_settings, text="Green (Perfect Cast) Tolerance:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        perfect_cast_tolerance_var = StringVar(value="18")
        self.vars["perfect_cast_tolerance"] = perfect_cast_tolerance_var

        perfect_cast_tolerance_entry = CTkEntry(
            pfc2_settings,
            width=120,
            textvariable=perfect_cast_tolerance_var
        )
        perfect_cast_tolerance_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc2_settings, text="White (Perfect Cast) Tolerance:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_cast2_tolerance_var = StringVar(value="16")
        self.vars["perfect_cast2_tolerance"] = perfect_cast2_tolerance_var

        perfect_cast2_tolerance_entry = CTkEntry(
            pfc2_settings,
            width=120,
            textvariable=perfect_cast2_tolerance_var
        )
        perfect_cast2_tolerance_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pfc2_settings, text="Perfect Cast Scan FPS:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        cast_scan_delay_var = StringVar(value="0.05")
        self.vars["cast_scan_delay"] = cast_scan_delay_var

        cast_scan_delay_entry = CTkEntry(
            pfc2_settings,
            width=120,
            textvariable=cast_scan_delay_var
        )
        cast_scan_delay_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")

        # Fish Overlay Settings 
        overlay_settings = CTkFrame(
            scroll,
            border_width=2
        )
        overlay_settings.grid(row=3, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(overlay_settings, text="Overlay Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        bar_size_var = StringVar(value="off")
        self.vars["bar_size"] = bar_size_var
        bar_size_cb = CTkCheckBox(overlay_settings, text="Show Bar Size", 
                                     variable=bar_size_var, onvalue="on", offvalue="off")
        bar_size_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        # Arrow Tracking Settings
        arrow_settings = CTkFrame(
            scroll,
            border_width=2
        )
        arrow_settings.grid(row=4, column=0, padx=20, pady=20, sticky="nw")
        centroid_tracking_var = StringVar(value="off")
        self.vars["centroid_tracking"] = centroid_tracking_var
        centroid_tracking_cb = CTkCheckBox(arrow_settings, text="Use Centroid Tracking", variable=centroid_tracking_var, onvalue="on", offvalue="off")
        centroid_tracking_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
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
        # Notes
        notes1 = CTkFrame(
            parent,
            border_width=2
        )
        notes1.grid(row=0, column=1, padx=20, pady=20, sticky="nw")
        CTkLabel(notes1, text="Notes", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(notes1, text="Click for mouse clicks | Navigation for keyboard spam").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        CTkLabel(notes1, text="Determines the tolerance to detect the shaking text").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        CTkLabel(notes1, text="Adjust delay values for your latency").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        CTkLabel(notes1, text="The amount of failed attempts before restarting the macro").grid(row=4, column=0, padx=12, pady=10, sticky="w")
    # MINIGAME SETTINGS TAB
    def build_minigame_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Toggle between image and pixel + eyedropper tool
        bar_toggle_settings = CTkFrame(scroll, border_width=2)
        bar_toggle_settings.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(bar_toggle_settings, text="Fish Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(bar_toggle_settings, text="Fish Method:").grid( row=1, column=0, padx=12, pady=10, sticky="w" )
        fishing_mode_var = StringVar(value="Pixel")
        self.vars["fishing_mode"] = fishing_mode_var
        fishing_cb = CTkComboBox( bar_toggle_settings, values=["Image", "Pixel"], variable=fishing_mode_var, command=lambda v: self.set_status(f"fishing mode: {v}") )
        fishing_cb.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["fishing_mode"] = fishing_cb
        CTkButton( bar_toggle_settings, text="Pick Colors", corner_radius=32, command=self._pick_colors ).grid(row=0, column=1, padx=12, pady=12, sticky="w")
        # Image Search Settings
        image_settings = CTkFrame( scroll, border_width=2 )
        image_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(image_settings, text="Image Search Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(image_settings, text="Left Bar Confidence:").grid( row=1, column=0, padx=12, pady=10, sticky="w" )
        left_confidence_var = StringVar(value="0.5")
        self.vars["left_confidence"] = left_confidence_var
        CTkEntry(image_settings, width=120, textvariable=left_confidence_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(image_settings, text="Right Bar Confidence:").grid( row=2, column=0, padx=12, pady=10, sticky="w" )
        right_confidence_var = StringVar(value="0.01")
        self.vars["right_confidence"] = right_confidence_var
        right_confidence_entry = CTkEntry(image_settings, placeholder_text="0.01", width=120, textvariable=right_confidence_var)
        right_confidence_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(image_settings, text="Fish Confidence:").grid( row=3, column=0, padx=12, pady=10, sticky="w" )
        fish_confidence_var = StringVar(value="1")
        self.vars["fish_confidence"] = fish_confidence_var
        CTkEntry( image_settings, width=120, textvariable=fish_confidence_var ).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        # Pixel Settings
        pixel_settings = CTkFrame( scroll, border_width=2 )
        pixel_settings.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(pixel_settings, text="Bar Colors", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(pixel_settings, text="Left Bar Color:").grid( row=2, column=0, padx=12, pady=10, sticky="w" )
        left_color_var = StringVar(value="#F1F1F1")
        self.vars["left_color"] = left_color_var
        CTkEntry(pixel_settings, placeholder_text="#F1F1F1", width=120, textvariable=left_color_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Right Bar Color:").grid( row=3, column=0, padx=12, pady=10, sticky="w" )
        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_color"] = right_color_var
        CTkEntry(pixel_settings, placeholder_text="#FFFFFF", width=120, textvariable=right_color_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Arrow Color:").grid( row=4, column=0, padx=12, pady=10, sticky="w" )
        arrow_color_var = StringVar(value="#848587")
        self.vars["arrow_color"] = arrow_color_var
        CTkEntry(pixel_settings, placeholder_text="#848587", width=120, textvariable=arrow_color_var).grid(row=4, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Fish Color:").grid( row=5, column=0, padx=12, pady=10, sticky="w" )
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        CTkEntry(pixel_settings, placeholder_text="#434B5B", width=120, textvariable=fish_color_var).grid(row=5, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Fish Color 2:").grid( row=6, column=0, padx=12, pady=10, sticky="w" )
        fish2_color_var = StringVar(value="#434B5B")
        self.vars["fish2_color"] = fish2_color_var
        CTkEntry(pixel_settings, placeholder_text="#434B5B", width=120, textvariable=fish2_color_var).grid(row=6, column=1, padx=12, pady=10, sticky="w")
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(pixel_settings, text="Tolerance:").grid( row=2, column=2, padx=12, pady=10, sticky="w" )
        left_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(pixel_settings, text="Tolerance:").grid( row=3, column=2, padx=12, pady=10, sticky="w" )
        right_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=3, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid( row=4, column=2, padx=12, pady=10, sticky="w" )
        arrow_tolerance_var = StringVar(value="8")
        self.vars["arrow_tolerance"] = arrow_tolerance_var
        arrow_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=arrow_tolerance_var)
        arrow_tolerance_entry.grid(row=4, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid( row=5, column=2, padx=12, pady=10, sticky="w" )
        fish_tolerance_var = StringVar(value="0")
        self.vars["fish_tolerance"] = fish_tolerance_var
        CTkEntry( pixel_settings, width=120, textvariable=fish_tolerance_var ).grid(row=5, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid( row=6, column=2, padx=12, pady=10, sticky="w" )
        fish2_tolerance_var = StringVar(value="0")
        self.vars["fish2_tolerance"] = fish2_tolerance_var
        CTkEntry( pixel_settings, width=120, textvariable=fish2_tolerance_var ).grid(row=6, column=3, padx=12, pady=10, sticky="w")
        # Minigame Timing and Limits
        ratio_settings = CTkFrame(
            scroll,
            border_width=2
        )
        ratio_settings.grid(row=3, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(ratio_settings, text="Minigame Timing & Limits", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(ratio_settings, text="Bar Ratio From Side:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        bar_ratio_var = StringVar(value="0.5")
        self.vars["bar_ratio"] = bar_ratio_var

        CTkEntry(
            ratio_settings,
            width=120,
            textvariable=bar_ratio_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(ratio_settings, text="Scan delay (seconds):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        minigame_scan_delay_var = StringVar(value="0.01")
        self.vars["minigame_scan_delay"] = minigame_scan_delay_var
        minigame_scan_delay_entry = CTkEntry(ratio_settings, placeholder_text="0.01", width=120, textvariable=minigame_scan_delay_var)
        minigame_scan_delay_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(ratio_settings, text="Restart Delay:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        restart_delay_var = StringVar(value="1")
        self.vars["restart_delay"] = restart_delay_var

        CTkEntry(
            ratio_settings,
            width=120,
            textvariable=restart_delay_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        pid_settings = CTkFrame(
            scroll,
            border_width=2
        )
        pid_settings.grid(row=4, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(pid_settings, text="PID Controller Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(pid_settings, text="Proportional gain:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        p_gain_var = StringVar(value="0.01")
        self.vars["proportional_gain"] = p_gain_var

        CTkEntry(
            pid_settings,
            width=120,
            textvariable=p_gain_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pid_settings, text="Derivative gain:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        d_gain_var = StringVar(value="0.01")
        self.vars["derivative_gain"] = d_gain_var
        CTkEntry(
            pid_settings,
            width=120,
            textvariable=d_gain_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pid_settings, text="Velocity Smoothing:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        velocity_smoothing_var = StringVar(value="6")
        self.vars["velocity_smoothing"] = velocity_smoothing_var

        CTkEntry(
            pid_settings,
            width=120,
            textvariable=velocity_smoothing_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")
    # SUPPORT SETTINGS TAB
    def build_advanced_tab(self, parent):
        # Shake Colors
        advanced_colors = CTkFrame(
            parent,
            border_width=2
        )
        advanced_colors.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(advanced_colors, text="Advanced Colors", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")   
        CTkLabel(advanced_colors, text="#RRGGBB", font=CTkFont(size=14, weight="bold")).grid(row=0, column=1, padx=12, pady=8, sticky="w")
        CTkLabel(advanced_colors, text="Shake Color:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        shake_color_var = StringVar(value="#FFFFFF")
        self.vars["shake_color"] = shake_color_var

        CTkEntry(
            advanced_colors,
            width=120,
            textvariable=shake_color_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(advanced_colors, text="Perfect Cast Color:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_color_var = StringVar(value="#5FA84B")
        self.vars["perfect_color"] = perfect_color_var

        CTkEntry(
            advanced_colors,
            width=120,
            textvariable=perfect_color_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")
    # Save and load settings
    def load_configs(self):
        """Load list of available config files."""
        config_dir = "configs"
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        # Get config names from subdirectories
        config_names = [
            name for name in os.listdir(config_dir)
            if os.path.isdir(os.path.join(config_dir, name))
        ]

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
            clean_bar_areas = {}

            for key in ["shake", "fish"]:
                area = self.bar_areas.get(key)

                if isinstance(area, dict):
                    clean_bar_areas[key] = {
                        "x": int(area.get("x", 0)),
                        "y": int(area.get("y", 0)),
                        "width": int(area.get("width", 0)),
                        "height": int(area.get("height", 0))
                    }
                else:
                    clean_bar_areas[key] = None

            data = {
                "last_rod": self.current_rod_name,
                "bar_areas": clean_bar_areas,

                # 🔥 Save hotkeys
                "start_key": self.vars["start_key"].get(),
                "screenshot_key": self.vars["screenshot_key"].get(),
                "stop_key": self.vars["stop_key"].get()
            }
            with open("last_config.json", "w") as f:
                json.dump(data, f, indent=4)
            # 🔥 Immediately update active hotkeys
            self.hotkey_start = self._string_to_key(self.vars["start_key"].get())
            self.hotkey_screenshot = self._string_to_key(self.vars["screenshot_key"].get())
            self.hotkey_stop = self._string_to_key(self.vars["stop_key"].get())
        except Exception as e:
            import traceback
            traceback.print_exc()

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

        # Get rod folder based on config name
        rod_folder = os.path.join(config_dir, name.replace(".json", ""))
        os.makedirs(rod_folder, exist_ok=True)

        path = os.path.join(rod_folder, "config.json")
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
        rod_folder = os.path.join(config_dir, name.replace(".json", ""))
        path = os.path.join(rod_folder, "config.json")

        if not os.path.exists(path):
            self.set_status(f"Config not found: {name}")
            return
        # Get rod folder based on config name
        left_bar_path  = os.path.join(rod_folder, "left_bar.png")
        right_bar_path = os.path.join(rod_folder, "right_bar.png")
        fish_path      = os.path.join(rod_folder, "fish.png")

        self.templates = {
            "left_bar":  cv2.imread(left_bar_path, 0)  if os.path.exists(left_bar_path)  else None,
            "right_bar": cv2.imread(right_bar_path, 0) if os.path.exists(right_bar_path) else None,
            "fish":      cv2.imread(fish_path, 0)      if os.path.exists(fish_path)      else None,
        }
        
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

        self.save_last_config_name(name)
        self.set_status(f"Loaded Config: {name}")
    def load_misc_settings(self):
        """Load miscellaneous settings from last_config.json."""
        try:
            if os.path.exists("last_config.json"):
                with open("last_config.json", "r") as f:
                    data = json.load(f)
                    self.current_rod_name = data.get("last_rod", "Basic Rod")
                    self.bar_areas = data.get("bar_areas", {"shake": None, "fish": None})
                    # 🔥 Load hotkeys if present
                    start_key = data.get("start_key", "F5")
                    screenshot_key = data.get("screenshot_key", "F8")
                    stop_key = data.get("stop_key", "F7")

                    self.vars["start_key"].set(start_key)
                    self.vars["screenshot_key"].set(screenshot_key)
                    self.vars["stop_key"].set(stop_key)

                    # Convert to pynput keys
                    self.hotkey_start = self._string_to_key(start_key)
                    self.hotkey_screenshot = self._string_to_key(screenshot_key)
                    self.hotkey_stop = self._string_to_key(stop_key)
            else:
                self.current_rod_name = "Basic Rod"
                self.bar_areas = {"fish": None, "shake": None}
        except:
            self.current_rod_name = "Basic Rod"
            self.bar_areas = {"fish": None, "shake": None}
    # Macro functions
    def _string_to_key(self, key_string):
        key_string = key_string.strip().lower()

        try:
            return Key[key_string]
        except KeyError:
            return key_string  # normal character keys
    def on_key_press(self, key):
        try:
            if key == self.hotkey_start and not self.macro_running:
                config_name = self.vars["active_config"].get()
                self.save_settings(config_name)

                self.macro_running = True
                self.after(0, self.withdraw)
                threading.Thread(target=self.start_macro, daemon=True).start()

            elif key == self.hotkey_screenshot:
                self._take_debug_screenshot()

            elif key == self.hotkey_stop:
                self.stop_macro()

        except Exception as e:
            print("Hotkey error:", e)
    def set_status(self, text, key=None):
        self.status_label.configure(text=text)
    # Utility functions
    def _take_debug_screenshot(self):
        """Capture the configured fish area and save a debug image.

        The fish region is defined in ``self.bar_areas['fish']`` and is expected to
        be a dict containing ``x, y, width, height``. If the area is missing or
        invalid, the method logs a status message and returns early. The resulting
        screenshot is written to ``debug_fish.png`` in the current working
        directory and a status update is shown on the main window.
        """
        area = self.bar_areas.get("fish")
        # Validate the stored area
        if not isinstance(area, dict):
            self.set_status("Fish area not set (cannot take screenshot)")
            return

        try:
            x = int(area.get("x", 0))
            y = int(area.get("y", 0))
            w = int(area.get("width", 0))
            h = int(area.get("height", 0))
        except Exception:
            self.set_status("Fish area invalid")
            return

        if w <= 0 or h <= 0:
            self.set_status("Fish area has nonpositive dimensions")
            return

        # grab the specified region
        img = self._grab_screen_region(x, y, x + w, y + h)
        if img is None:
            self.set_status("Failed to grab fish area")
            return

        try:
            cv2.imwrite("debug_bar.png", img)
            self.set_status("Saved bar-area debug screenshot → debug_bar.png")
        except Exception as e:
            self.set_status(f"Error saving screenshot: {e}")

    def _pick_colors(self):
        print("Not implemented yet")
    def open_link(self, url):
        """Open a URL in the default web browser."""
        return lambda: webbrowser.open(url)
    
    def open_dual_area_selector(self):
        self.update_idletasks()
        # If already open → close both
        if self.shake_selector or self.fish_selector:
            if self.shake_selector and self.shake_selector.winfo_exists():
                self.shake_selector.on_close()
            if self.fish_selector and self.fish_selector.winfo_exists():
                self.fish_selector.on_close()

            self.shake_selector = None
            self.fish_selector = None
            self.set_status("Area selector closed")
            return

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()

        # Failback areas (if you don't set bar areas it will failback to these values)
        def default_shake_area():
            left = int(screen_w * 0.2083)
            top = int(screen_h * 0.162)
            right = int(screen_w * 0.7813)
            bottom = int(screen_h * 0.74)
            return {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top
            }

        def default_fish_area():
            left = int(screen_w * 0.2844)
            top = int(screen_h * 0.7981)
            right = int(screen_w * 0.7141)
            bottom = int(screen_h * 0.8370)
            return {
                "x": left,
                "y": top,
                "width": right - left,
                "height": bottom - top
            }

        shake_area = (
            self.bar_areas.get("shake")
            if isinstance(self.bar_areas.get("shake"), dict)
            else default_shake_area()
        )

        fish_area = (
            self.bar_areas.get("fish")
            if isinstance(self.bar_areas.get("fish"), dict)
            else default_fish_area()
        )
        # ---- TEMPLATE HEIGHT FAILSAFE ----
        if (
            isinstance(fish_area, dict)
            and self.templates.get("fish") is not None
            and self.templates.get("left_bar") is not None
        ):

            fish_template_h = self.templates["fish"].shape[0]
            bar_template_h  = self.templates["left_bar"].shape[0]

            min_required_height = int((fish_template_h + bar_template_h) + 5)  # Add some padding

            if fish_area["height"] < min_required_height:

                old_height = fish_area["height"]

                # Keep top position stable
                fish_area["height"] = min_required_height

                # Prevent going off bottom of screen
                if fish_area["y"] + fish_area["height"] > screen_h:
                    fish_area["y"] = screen_h - fish_area["height"]

                # Prevent negative Y
                if fish_area["y"] < 0:
                    fish_area["y"] = 0

                self.set_status(
                    f"Bar height too small ({old_height}) → corrected to {min_required_height}"
                )
        def on_shake_done(shake):
            self.bar_areas["shake"] = shake

        def on_fish_done(fish):
            self.bar_areas["fish"] = fish
            self.save_misc_settings()
            self.set_status("Bar areas saved")

        # Screenshot
        with mss.mss() as sct:
            monitor = sct.monitors[1]
            shot = sct.grab(monitor)
            screenshot = Image.frombytes("RGB", shot.size, shot.rgb)

        self.shake_selector = ShakeAreaSelector(
            parent=self,
            area=shake_area,
            callback=on_shake_done
        )

        self.fish_selector = FishAreaSelector(
            parent=self,
            area=fish_area,
            callback=on_fish_done
        )
    # Image processing and interaction functions
    def _find_template(self, frame, template, confidence=0.85):
        if template is None or frame is None:
            return None
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        result = cv2.matchTemplate(gray_frame, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val >= confidence:
            h, w = template.shape
            return max_loc[0] + w // 2   # X relative to frame
        return None
    def _prepare_templates(self):
        """Convert templates to grayscale once."""
        for key in self.templates:
            if self.templates[key] is None:
                continue

            if len(self.templates[key].shape) == 3:
                self.templates[key] = cv2.cvtColor(
                    self.templates[key],
                    cv2.COLOR_BGR2GRAY
                )
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
        Using vectorized detection.
        """

        if frame is None:
            return None

        # Convert color
        target_bgr = np.array(self._hex_to_bgr(target_color_hex), dtype=np.int16)

        # Convert frame for safe subtraction
        frame_int = frame.astype(np.int16)

        tol = int(np.clip(tolerance, 0, 255))

        # Vectorized absolute tolerance comparison
        mask = np.all(np.abs(frame_int - target_bgr) <= tol, axis=2)

        y_coords, x_coords = np.where(mask)

        if len(x_coords) == 0:
            return None

        # Center calculation (vectorized mean)
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

        h, w = frame.shape[:2]
        y = int(h * scan_height_ratio)

        # Convert to BGR
        left_bgr = np.array(self._hex_to_bgr(left_hex), dtype=np.int16)
        right_bgr = np.array(self._hex_to_bgr(right_hex), dtype=np.int16)

        # Extract single horizontal scan line
        line = frame[y].astype(np.int16)

        # Clamp tolerances
        tol_l = int(np.clip(tolerance, 0, 255))
        tol_r = int(np.clip(tolerance2, 0, 255))

        bar_x_coords = None

        # --- LEFT BAR COLOR ---
        if left_hex is not None:
            lower_l = left_bgr - tol_l
            upper_l = left_bgr + tol_l

            left_mask = np.all((line >= lower_l) & (line <= upper_l), axis=1)
            left_indices = np.where(left_mask)[0]

            if left_indices.size > 0:
                bar_x_coords = left_indices

        # --- RIGHT BAR COLOR ---
        if right_hex is not None:
            lower_r = right_bgr - tol_r
            upper_r = right_bgr + tol_r

            right_mask = np.all((line >= lower_r) & (line <= upper_r), axis=1)
            right_indices = np.where(right_mask)[0]

            if right_indices.size > 0:
                if bar_x_coords is not None:
                    bar_x_coords = np.concatenate([bar_x_coords, right_indices])
                else:
                    bar_x_coords = right_indices

        # --- FINAL EDGE EXTRACTION ---
        if bar_x_coords is not None and bar_x_coords.size > 0:
            bar_left_x = int(np.min(bar_x_coords))
            bar_right_x = int(np.max(bar_x_coords))
            return bar_left_x, bar_right_x

        return None, None

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

    def _find_shake_pixel(self, frame, hex, tolerance=10):
        tolerance = int(np.clip(tolerance, 0, 255))
        b, g, r = self._hex_to_bgr(hex)
        white = np.array([b, g, r], dtype=np.int16)
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
    # Image processing and interaction functions related to minigame
    def _do_image_search(self, img, img_h):
        fish_template = self.templates["fish"]
        bar_template  = self.templates["left_bar"]

        fish_template_h = fish_template.shape[0]
        bar_template_h  = bar_template.shape[0]
        # Get confidence levels
        left_confidence  = float(self.vars["left_confidence"].get()  or 0.8)
        right_confidence = float(self.vars["right_confidence"].get() or 0.8)
        fish_confidence  = float(self.vars["fish_confidence"].get()  or 0.8)

        # ---- Fish region (remove bottom bar part) ----
        fish_region = img[:img_h - bar_template_h, :]
        fish_x = self._find_template(fish_region, fish_template, fish_confidence)

        # ---- Bar region (remove top fish part) ----
        bar_region = img[fish_template_h:, :]
        left_x = self._find_template(bar_region, bar_template, left_confidence)
        right_x = self._find_template(bar_region, self.templates["right_bar"], right_confidence)
        return fish_x, left_x, right_x
    def _do_pixel_search(self, img):
        fish_hex = self.vars["fish_color"].get()
        left_bar_hex = self.vars["left_color"].get()
        right_bar_hex = self.vars["right_color"].get()

        left_tol = int(self.vars["left_tolerance"].get() or 8)
        right_tol = int(self.vars["right_tolerance"].get() or 8)
        fish_tol = int(self.vars["fish_tolerance"].get() or 1)
        fish_center = self._find_color_center(img, fish_hex, fish_tol)
        left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, right_bar_hex, left_tol, right_tol)
        if left_bar_center is None:
            left_bar_center, right_bar_center = self._find_bar_edges(img, right_bar_hex, right_bar_hex, right_tol, right_tol)
        elif right_bar_center is None:
            left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, left_bar_hex, left_tol, left_tol)
        return fish_center, left_bar_center, right_bar_center
    # Start macro and main loop
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
                continue

            # Lowest green pixel
            green_x, green_y = max(green_pixels, key=lambda p: p[1])

            shake_pixels = self._pixel_search(
                frame,
                "#d4d3ca",
                white_tolerance
            )
            if not shake_pixels:
                time.sleep(float(self.vars["cast_scan_delay"].get()))
                continue
            white_x, white_y = min(shake_pixels, key=lambda p: p[1])
            if shake_pixels and green_pixels:
                distance = abs(green_y - white_y)
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
        delay = float(self.vars["cast_delay"].get() or 0.2)
        time.sleep(duration)  # adjust cast strength
        mouse_controller.release(Button.left)
        time.sleep(delay)  # wait for cast to register
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
        shake_hex = self.vars["shake_color"].get()

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

            # 2️⃣ Look for shake pixel
            shake_pixel = self._find_shake_pixel(shake_area, shake_hex, tolerance)
            if shake_pixel:
                x, y = shake_pixel
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

                fish_x = self._find_color_center(
                    detection_area, fish_hex, tolerance
                )

                if fish_x:
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

                fish_x = self._find_color_center(
                    detection_area, fish_hex, tolerance
                )

                if fish_x:
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
        # Load bar/fish images
        # --- PREPARE TEMPLATES ONCE ---
        for key in ["fish", "left_bar", "right_bar"]:
            template = self.templates.get(key)

            if template is None:
                continue

            # Convert to grayscale once
            if len(template.shape) == 3:
                template = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        # Arrow tracking variables
        arrow_hex = self.vars["arrow_color"].get()
        arrow_tol = int(self.vars["arrow_tolerance"].get() or 8)
        bar_ratio = float(self.vars["bar_ratio"].get() or 0.5)
        scan_delay = float(self.vars["minigame_scan_delay"].get() or 0.05)

        try:
            thresh = float(self.vars["velocity_smoothing"].get() or 8)
            use_centroid = self.vars["centroid_tracking"].get()
        except:
            thresh = 8
            use_centroid = False

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
                return

            img_h = img.shape[0]
            mode = self.vars["fishing_mode"].get()

            if mode == "Image":
                fish_x, left_x, right_x = self._do_image_search(img, img_h)
            else:
                fish_x, left_x, right_x = self._do_pixel_search(img)

            # ---- Arrow ----
            arrow_center = self._find_color_center(img, arrow_hex, arrow_tol)

            # ---- FISH NOT FOUND ----
            if fish_x is not None:
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
            bars_found = left_x is not None and right_x is not None
            if mode == "Image":
                fish_x = fish_x + fish_left
            else:
                fish_x = fish_x[0] + fish_left
            if bars_found and left_x is not None and right_x is not None:
                bar_center = int((left_x + right_x) / 2 + fish_left)
                bar_size = abs(right_x - left_x)
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
            elif arrow_center:

                capture_width = fish_right - fish_left
                arrow_indicator_x = self._find_arrow_indicator_x(img, arrow_hex, arrow_tol, mouse_down)

                if self.vars["fish_overlay"].get() == "on":
                    self.draw_bar_minigame(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left)

                if arrow_indicator_x is None:
                    pid_found = 1
                    return

                arrow_screen_x = arrow_indicator_x + fish_left

                if use_centroid:
                    estimated_bar_center = self._update_arrow_box_estimation(
                        arrow_indicator_x,
                        mouse_down,
                        capture_width
                    )

                    if estimated_bar_center is not None:
                        bar_center = int(estimated_bar_center + fish_left)
                        pid_found = 0

                        if self.vars["fish_overlay"].get() == "on":
                            self.draw_bar_minigame(
                                bar_center=bar_center,
                                box_size=40,
                                color="yellow",
                                canvas_offset=fish_left
                            )
                    else:
                        pid_found = 1

                else:
                    distance = arrow_screen_x - fish_x

                    if abs(distance) < 15:
                        pid_found = 0
                    elif distance < 0:
                        pid_found = 2
                    else:
                        pid_found = 1

                    if self.vars["fish_overlay"].get() == "on":
                        self.draw_bar_minigame(
                            bar_center=arrow_screen_x,
                            box_size=20,
                            color="yellow",
                            canvas_offset=fish_left
                        )

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