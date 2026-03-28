# Initialization
from customtkinter import *
import tkinter as tk
import os
import subprocess
# Keyboard and Mouse
import pyautogui
import keyboard as keyboard_lib
# Web browsing
import webbrowser
# Key Listeners
import threading
macro_running = False
macro_thread = None
# Key Inputs must be on seperate thread
import threading
# Time
import time
import json
# Discord and Text logs
import requests
import io
# OpenCV for pixel searches and NumPy for arrow calculations
import cv2
import numpy as np
# DXCAM and MSS for capturing the screen (also a guard for DXCAM on macOS)
try:
    import dxcam
except Exception:
    dxcam = None
import mss
# PyAutoGUI pauses and failsafe
pyautogui.PAUSE = 0.003
pyautogui.FAILSAFE = False
# Set appearance
set_default_color_theme("blue")
# from AppKit import NSEvent
# Last Config Path / Fix macOS DMG issues
def get_base_path():
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))
if sys.platform == "darwin":
    user_config_dir = os.path.join(os.path.expanduser("~"), 
                                   "Library", "Application Support", 
                                   "IcantFishV2", "configs")
else:
    user_config_dir = os.path.join(os.path.expanduser("~"),
                                   "AppData","Roaming",
                                   "IcantFishV2","configs")

os.makedirs(user_config_dir, exist_ok=True)
BASE_PATH = get_base_path()

if sys.platform == "darwin" and getattr(sys, "frozen", False):
    # Only use Application Support when bundled
    USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), "Library", 
                                   "Application Support", "IcantFishV2", 
                                   "configs")
elif sys.platform == "win32" and getattr(sys, "frozen", False):
    # Only use AppData/Roaming when bundled
    USER_CONFIG_DIR = os.path.join(os.path.expanduser("~"), "AppData",
                                   "Roaming", "IcantFishV2",
                                   "configs")
else:
    # During development, use local project folder
    USER_CONFIG_DIR = os.path.join(BASE_PATH, "configs")

os.makedirs(USER_CONFIG_DIR, exist_ok=True)
if sys.platform == "darwin":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
else:
    pass # You're on Windows, no need to change the working directory
class DualAreaSelector:
    HANDLE_SIZE = 8

    def __init__(self, parent, shake_area, fish_area, callback):
        self.parent = parent
        self.callback = callback

        self.window = tk.Toplevel(parent)
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)

        self.window.configure(bg="black")
        self.window.attributes("-alpha", 0.5)
        w = self.window.winfo_screenwidth()
        h = self.window.winfo_screenheight()
        self.window.geometry(f"{w}x{h}+0+0")

        self.canvas = tk.Canvas(self.window, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.shake = shake_area.copy()
        self.fish = fish_area.copy()

        self.dragging = None
        self.resize_corner = None
        self.active_area = None

        self.start_x = 0
        self.start_y = 0

        self.dragging = None
        self.resize_corner = None
        self.active_area = None

        self.draw_boxes()

        self.canvas.bind("<Button-1>", self.mouse_down)
        self.canvas.bind("<B1-Motion>", self.mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self.mouse_up)
        self.canvas.bind("<Motion>", self.mouse_move)

        self.window.protocol("WM_DELETE_WINDOW", self.close)

    # ---------------- DRAW ----------------

    def draw_boxes(self):

        self.canvas.delete("all")

        self.draw_area(self.shake, "#ff6b35")
        self.draw_area(self.fish, "#7ed321")

    def draw_area(self, area, color):

        x1 = area["x"]
        y1 = area["y"]
        x2 = x1 + area["width"]
        y2 = y1 + area["height"]

        self.canvas.create_rectangle(x1, y1, x2, y2, 
                                     outline=color, width=3, 
                                     fill=color, stipple="gray25")

        for x, y in [(x1,y1),(x2,y1),(x1,y2),(x2,y2)]:
            self.canvas.create_rectangle(x-self.HANDLE_SIZE, y-self.HANDLE_SIZE,
                                         x+self.HANDLE_SIZE,y+self.HANDLE_SIZE, 
                                         fill="white",outline="")
    # Resizer / hit test
    def inside(self, x, y, area):
        return (
            area["x"] <= x <= area["x"] + area["width"] and
            area["y"] <= y <= area["y"] + area["height"]
        )

    def get_handle(self, x, y, area):
        x1 = area["x"]
        y1 = area["y"]
        x2 = x1 + area["width"]
        y2 = y1 + area["height"]
        handles = { "nw": (x1,y1), "ne": (x2,y1), 
                   "sw": (x1,y2), "se": (x2,y2) }
        for name,(hx,hy) in handles.items():

            if abs(x-hx) <= self.HANDLE_SIZE and abs(y-hy) <= self.HANDLE_SIZE:
                return name

        return None
    # Detect mouse input from user
    def mouse_down(self, e):
        self.start_x = e.x
        self.start_y = e.y

        for area,name in [(self.fish,"fish"),(self.shake,"shake")]:

            handle = self.get_handle(e.x,e.y,area)

            if handle:
                self.resize_corner = handle
                self.active_area = area
                return

            if self.inside(e.x,e.y,area):
                self.dragging = name
                self.active_area = area
                return

    def mouse_drag(self, e):
        if not self.dragging and not self.resize_corner:
            return
        dx = e.x - self.start_x
        dy = e.y - self.start_y

        if self.resize_corner:

            a = self.active_area

            if "e" in self.resize_corner:
                a["width"] += dx
            if "s" in self.resize_corner:
                a["height"] += dy
            if "w" in self.resize_corner:
                a["x"] += dx
                a["width"] -= dx
            if "n" in self.resize_corner:
                a["y"] += dy
                a["height"] -= dy

        elif self.dragging:
            a = self.active_area
            a["x"] += dx
            a["y"] += dy
        self.start_x = e.x
        self.start_y = e.y
        self.draw_boxes()

    def mouse_up(self, e):
        self.dragging = None
        self.resize_corner = None
        self.active_area = None

    def mouse_move(self, e):
        for area in [self.fish,self.shake]:
            handle = self.get_handle(e.x,e.y,area)
            if handle:
                cursor = {
                    "nw":"size_nw_se",
                    "se":"size_nw_se",
                    "ne":"size_ne_sw",
                    "sw":"size_ne_sw"
                }[handle]

                self.canvas.config(cursor=cursor)
                return

            if self.inside(e.x,e.y,area):
                self.canvas.config(cursor="fleur")
                return

        self.canvas.config(cursor="")

    # Save
    def close(self):

        self.callback(self.shake,self.fish)
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
        self.geometry("800x600")
        self.title("I Can't Fish V2.4")

        # Macro state
        self.macro_running = False
        self.macro_thread = None

        # P/D state variables
        self.prev_error = 0.0      # previous error term
        self.last_time = None      # timestamp of last PD sample
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
        self.overlay_window = None
        self.overlay_canvas = None
        self.pid_source = None  # "bar" or "arrow"

        # Hotkey variables (stored as lowercase strings, e.g. "f5")
        self.hotkey_start = "f5"
        self.hotkey_change_areas = "f6"
        self.hotkey_stop = "f7"
        self.hotkey_screenshot = "f8"
        self.hotkey_labels = {}  # Store label widgets for dynamic updates

        # MSS and DXCAM-related variables
        self.sct = mss.mss()

        # Start hotkey listener using the `keyboard` library
        self._register_hotkeys()

        # Status Bar 
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Top Bar Frame (Status + Buttons)
        top_bar = CTkFrame(self, fg_color="transparent")
        top_bar.grid(row=0, column=0, padx=20, pady=10, sticky="ew")

        top_bar.grid_columnconfigure(0, weight=1)

        # Logo Label
        logo_label = CTkLabel(
            top_bar, 
            text="I CAN'T FISH V2.4",
            font=CTkFont(size=16, weight="bold")
        )
        logo_label.grid(row=0, column=0, sticky="w")

        # Status label (left side)
        self.status_label = CTkLabel(top_bar, text="Macro status: Idle")
        self.status_label.grid(row=1, column=0, pady=5, sticky="w")

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
            text="Upcoming Features",
            corner_radius=32,
            command=self.open_link("https://docs.google.com/document/d/1WwWWMR-eN-R-GO42IioToHpWTgiXkLoiNE_4NeE-GsU/edit?tab=t.0")
       ).pack(side="left", padx=6)

        CTkButton(
            button_frame,
            text="Tutorial",
            corner_radius=32,
            command=self.open_link("https://docs.google.com/document/d/1qjhgcONxpZZbSAEYiSCXoUXGjQwd7Jghf4EysWC4Cps/edit?usp=drive_link")
       ).pack(side="left", padx=6)

        # Bar Areas Variables
        self.shake_selector = None
        self.fish_selector = None

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
        self.tabs.add("Cast")
        self.tabs.add("Shake")
        self.tabs.add("Fish")
        self.tabs.add("Logging")
        # self.tabs.add("Utilities")
        self.tabs.add("Advanced")

        # Build tabs
        self.build_basic_tab(self.tabs.tab("Basic"))
        self.build_misc_tab(self.tabs.tab("Misc"))
        self.build_cast_tab(self.tabs.tab("Cast"))
        self.build_shake_tab(self.tabs.tab("Shake"))
        self.build_fishing_tab(self.tabs.tab("Fish"))
        self.build_logging_tab(self.tabs.tab("Logging"))
        # self.build_utilities_tab(self.tabs.tab("Utilities"))
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
        self.init_overlay_window()
        # Perfect cast variables
        self.right_mouse_down = False
        # Capture backend
        self.camera = None

        if sys.platform == "win32" and dxcam:
            try:
                self.camera = dxcam.create()
                self.camera.start(target_fps=60)
            except Exception:
                self.camera = None
        # Arrow variables
        self.initial_bar_size = None
        # Utility variables
        self.area_selector = None
        self.last_fish_x = None
    # BASIC SETTINGS TAB
    def build_basic_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Capture Mode Settings 
        capture_settings = CTkFrame( scroll, border_width=2 )
        capture_settings.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(capture_settings, text="Capture Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(capture_settings, text="Capture Mode:").grid( row=1, column=0, padx=12, pady=6, sticky="w")
        if sys.platform == "darwin":
            CTkLabel(capture_settings, text="MSS").grid(row=1, column=1, padx=12, pady=6, sticky="w")
        else:
            capture_var = StringVar(value="DXCAM")
            self.vars["capture_mode"] = capture_var
            capture_cb = CTkComboBox(capture_settings, values=["DXCAM", "MSS"], 
                                    variable=capture_var, command=lambda v: self.set_status(f"Capture mode: {v}")
                                    )
            capture_cb.grid(row=1, column=1, padx=12, pady=6, sticky="w")
            self.comboboxes["capture_mode"] = capture_cb
        # Configs 
        configs = CTkFrame(scroll, border_width=2)
        configs.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(configs, text="Config Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(configs, text="Rod Type:").grid( row=1, column=0, padx=12, pady=6, sticky="w" )
        config_list = self.load_configs()
        config_var = StringVar(value=config_list[0] if config_list else "default.json")
        self.vars["active_config"] = config_var
        config_cb = CTkComboBox( configs, values=config_list, 
                                variable=config_var, command=lambda v: self.load_settings(v) )
        config_cb.grid(row=1, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["active_config"] = config_cb
        CTkButton(configs, text="Open Configs Folder", corner_radius=10, 
                  command=self.open_configs_folder
                  ).grid(row=2, column=0, padx=12, pady=12, sticky="w")
        # Save misc settings (most important)
        CTkButton(configs, text="Save Misc Settings", 
                  corner_radius=10, command=self.save_misc_settings
        ).grid(row=2, column=1, padx=12, pady=12, sticky="w")
        # Hotkey Settings
        hotkey_settings = CTkFrame(scroll, border_width=2)
        hotkey_settings.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(hotkey_settings, text="Hotkey Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        # Start key
        CTkLabel(hotkey_settings, text="Start Key").grid( row=1, column=0, padx=12, pady=6, sticky="w" )
        CTkLabel(hotkey_settings, text="Change Bar Areas Key").grid( row=2, column=0, padx=12, pady=6, sticky="w" )
        CTkLabel(hotkey_settings, text="Stop Key").grid( row=3, column=0, padx=12, pady=6, sticky="w" )
        CTkLabel(hotkey_settings, text="Screenshot Key").grid( row=4, column=0, padx=12, pady=6, sticky="w" )
        # Start, screenshot and stop key changer
        start_key_var = StringVar(value="F5")
        self.vars["start_key"] = start_key_var
        start_key_entry = CTkEntry( hotkey_settings, width=120, textvariable=start_key_var )
        start_key_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        change_bar_areas_key_var = StringVar(value="F6")
        self.vars["change_bar_areas_key"] = change_bar_areas_key_var
        change_bar_areas_key_entry = CTkEntry( hotkey_settings, width=120, textvariable=change_bar_areas_key_var )
        change_bar_areas_key_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        stop_key_var = StringVar(value="F7")
        self.vars["stop_key"] = stop_key_var
        stop_key_entry = CTkEntry( hotkey_settings, width=120, textvariable=stop_key_var )
        stop_key_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        screenshot_key_var = StringVar(value="F8")
        self.vars["screenshot_key"] = screenshot_key_var
        screenshot_key_entry = CTkEntry( hotkey_settings, width=120, textvariable=screenshot_key_var )
        screenshot_key_entry.grid(row=4, column=1, padx=12, pady=10, sticky="w")
        # Automation 
        automation = CTkFrame(scroll, border_width=2)
        automation.grid(row=3, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(automation, text="Automation Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        # Create and store checkboxes with StringVar
        auto_rod_var = StringVar(value="off")
        self.vars["auto_select_rod"] = auto_rod_var
        auto_rod_cb = CTkCheckBox(automation, text="Auto Select Rod", variable=auto_rod_var, onvalue="on", offvalue="off")
        auto_rod_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        auto_zoom_var = StringVar(value="off")
        self.vars["auto_zoom_in"] = auto_zoom_var
        auto_zoom_cb = CTkCheckBox(automation, text="Auto Zoom In", variable=auto_zoom_var, onvalue="on", offvalue="off")
        auto_zoom_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")
        # Overlay Options 
        overlay_options = CTkFrame(scroll, border_width=2)
        overlay_options.grid(row=4, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(overlay_options, text="Overlay Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        fish_overlay_var = StringVar(value="off")
        self.vars["fish_overlay"] = fish_overlay_var
        fish_overlay_cb = CTkCheckBox(overlay_options, text="Fish Overlay", variable=fish_overlay_var, onvalue="on", offvalue="off")
        fish_overlay_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        bar_size_var = StringVar(value="off")
        self.vars["bar_size"] = bar_size_var
        bar_size_cb = CTkCheckBox(overlay_options, text="Show Bar Size", variable=bar_size_var, onvalue="on", offvalue="off")
        bar_size_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")
    # MISC SETTINGS TAB
    def build_misc_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Sequence Options
        sequence_options = CTkFrame(scroll, border_width=2)
        sequence_options.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(sequence_options, text="Sequences Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(sequence_options, text="Select Rod Delay").grid( row=2, column=0, padx=12, pady=8, sticky="w")
        bag_delay_var = StringVar(value="0.2")
        self.vars["bag_delay"] = bag_delay_var
        bag_delay_entry = CTkEntry(sequence_options, width=120, textvariable=bag_delay_var)
        bag_delay_entry.grid(row=2, column=1, padx=12, pady=8, sticky="w")
        CTkLabel(sequence_options, text="Delay before casting").grid( row=3, column=0, padx=12, pady=8, sticky="w")
        casting_delay2_var = StringVar(value="0.0")
        self.vars["casting_delay2"] = casting_delay2_var
        casting_delay2_entry = CTkEntry(sequence_options, width=120, textvariable=casting_delay2_var)
        casting_delay2_entry.grid(row=3, column=1, padx=12, pady=8, sticky="w")
        # Arrow Tracking Settings
        arrow_settings = CTkFrame(scroll, border_width=2)
        arrow_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(arrow_settings, text="Minigame Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        centroid_tracking_var = StringVar(value="off")
        self.vars["centroid_tracking"] = centroid_tracking_var
        centroid_tracking_cb = CTkCheckBox(arrow_settings, text="Estimate Bar From Arrows", 
                                           variable=centroid_tracking_var, onvalue="on", 
                                           offvalue="off")
        centroid_tracking_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
        legacy_pixel_search_var = StringVar(value="off")
        self.vars["legacy_pixel_search"] = legacy_pixel_search_var
        legacy_pixel_search_cb = CTkCheckBox(arrow_settings, text="Use Legacy Pixel Search", 
                                           variable=legacy_pixel_search_var, onvalue="on", 
                                           offvalue="off")
        legacy_pixel_search_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")
    # CAST SETTINGS TAB
    def build_cast_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Casting Mode (Combobox)
        casting_mode = CTkFrame(scroll, border_width=2)
        casting_mode.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(casting_mode, text="Casting Mode:").grid(row=1, column=0, padx=12, pady=10, sticky="w" )
        casting_mode_var = StringVar(value="Normal")
        self.vars["casting_mode"] = casting_mode_var
        casting_cb = CTkComboBox(casting_mode, values=["Perfect", "Normal"], 
                               variable=casting_mode_var, command=lambda v: self.set_status(f"Casting Mode: {v}")
                               )
        casting_cb.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["casting_mode"] = casting_cb
        # Normal Casting Group
        normal_casting = CTkFrame(scroll, border_width=2)
        normal_casting.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(normal_casting, text="Normal Casting Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(normal_casting, text="Cast duration").grid(row=1, column=0, padx=12, pady=8, sticky="w")
        cast_duration_var = StringVar(value="0.6")
        self.vars["cast_duration"] = cast_duration_var
        cast_duration_entry = CTkEntry(normal_casting, width=120, textvariable=cast_duration_var)
        cast_duration_entry.grid(row=1, column=1, padx=12, pady=8, sticky="w")
        CTkLabel(normal_casting, text="Cast Delay").grid(row=2, column=0, padx=12, pady=8, sticky="w")
        cast_delay_var = StringVar(value="0.6")
        self.vars["cast_delay"] = cast_delay_var
        cast_delay_entry = CTkEntry(normal_casting, width=120, textvariable=cast_delay_var)
        cast_delay_entry.grid(row=2, column=1, padx=12, pady=8, sticky="w")
        # Perfect Cast Settings 
        perfect_casting = CTkFrame(scroll, border_width=2)
        perfect_casting.grid(row=2, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(perfect_casting, text="Perfect Casting Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(perfect_casting, text="Green (Perfect Cast) Tolerance:").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        perfect_cast_tolerance_var = StringVar(value="14")
        self.vars["perfect_cast_tolerance"] = perfect_cast_tolerance_var
        perfect_cast_tolerance_entry = CTkEntry(perfect_casting, width=120, textvariable=perfect_cast_tolerance_var)
        perfect_cast_tolerance_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(perfect_casting, text="White (Perfect Cast) Tolerance:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        perfect_cast2_tolerance_var = StringVar(value="12")
        self.vars["perfect_cast2_tolerance"] = perfect_cast2_tolerance_var
        perfect_cast2_tolerance_entry = CTkEntry(perfect_casting, width=120, textvariable=perfect_cast2_tolerance_var)
        perfect_cast2_tolerance_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(perfect_casting, text="Perfect Cast Scan FPS:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        cast_scan_delay_var = StringVar(value="0.05")
        self.vars["cast_scan_delay"] = cast_scan_delay_var
        cast_scan_delay_entry = CTkEntry(perfect_casting, width=120, textvariable=cast_scan_delay_var)
        cast_scan_delay_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(perfect_casting, text="Failsafe Release Timeout:").grid(row=4, column=0, padx=12, pady=10, sticky="w")
        perfect_max_time_var = StringVar(value="3.5")
        self.vars["perfect_max_time"] = perfect_max_time_var
        perfect_max_time_entry = CTkEntry(perfect_casting, width=120, textvariable=perfect_max_time_var)
        perfect_max_time_entry.grid(row=4, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(perfect_casting, text="Perfect Cast Release Method:").grid(row=5, column=0, padx=12, pady=10, sticky="w" )
        release_method_var = StringVar(value="Simple")
        self.vars["release_method"] = release_method_var
        release_method_cb = CTkComboBox(perfect_casting, values=["Velocity-based", "Simple"], 
                               variable=release_method_var, command=lambda v: self.set_status(f"Perfect Cast Release Method: {v}")
                               )
        release_method_cb.grid(row=5, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["release_method"] = release_method_cb

        CTkLabel(perfect_casting, text="Perfect Cast Release Delay:").grid(row=6, column=0, padx=12, pady=10, sticky="w")
        perfect_release_delay_var = StringVar(value="0")
        self.vars["perfect_release_delay"] = perfect_release_delay_var
        perfect_release_delay_entry = CTkEntry(perfect_casting, width=120, textvariable=perfect_release_delay_var)
        perfect_release_delay_entry.grid(row=6, column=1, padx=12, pady=10, sticky="w")
    # SHAKE SETTINGS TAB
    def build_shake_tab(self, parent):
        shake_configuration = CTkFrame(
            parent,
            border_width=2
        )
        shake_configuration.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        # Shake Configuration
        CTkLabel(shake_configuration, text="Shake Configuration", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkLabel(shake_configuration, text="Shake mode:").grid( row=1, column=0, padx=12, pady=10, sticky="w" )
        shake_mode_var = StringVar(value="Click")
        self.vars["shake_mode"] = shake_mode_var
        shake_cb = CTkComboBox( shake_configuration, values=["Click", "Navigation"], 
                               variable=shake_mode_var, command=lambda v: self.set_status(f"Shake mode: {v}")
                               )
        shake_cb.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["shake_mode"] = shake_cb
        CTkLabel(shake_configuration, text="Click Shake Color Tolerance:").grid( row=2, column=0, padx=12, pady=10, sticky="w" )
        shake_tolerance_var = StringVar(value="5")
        self.vars["shake_tolerance"] = shake_tolerance_var
        CTkEntry( shake_configuration, width=120, textvariable=shake_tolerance_var ).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(shake_configuration, text="Shake Scan Delay:").grid( row=3, column=0, padx=12, pady=10, sticky="w" )
        shake_scan_delay_var = StringVar(value="0.01")
        self.vars["shake_scan_delay"] = shake_scan_delay_var
        CTkEntry( shake_configuration, width=120, textvariable=shake_scan_delay_var ).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(shake_configuration, text="Shake Failsafe (attempts):").grid( row=4, column=0, padx=12, pady=10, sticky="w" )
        shake_failsafe_var = StringVar(value="20")
        self.vars["shake_failsafe"] = shake_failsafe_var
        CTkEntry( shake_configuration, width=120, textvariable=shake_failsafe_var ).grid(row=4, column=1, padx=12, pady=10, sticky="w")
    # FISHING SETTINGS TAB
    def build_fishing_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Pixel Settings
        pixel_settings = CTkFrame(scroll, border_width=2)
        pixel_settings.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(pixel_settings, text="Bar Colors", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        CTkButton(pixel_settings, text="Pick Colors", corner_radius=10, command=self._pick_colors).grid(row=0, column=1, padx=12, pady=12, sticky="w")
        CTkLabel(pixel_settings, text="Left Bar Color:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        left_color_var = StringVar(value="#F1F1F1")
        self.vars["left_color"] = left_color_var
        CTkEntry(pixel_settings, placeholder_text="#F1F1F1", width=120, textvariable=left_color_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Right Bar Color:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_color"] = right_color_var
        CTkEntry(pixel_settings, placeholder_text="#FFFFFF", width=120, textvariable=right_color_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Arrow Color:").grid(row=4, column=0, padx=12, pady=10, sticky="w")
        arrow_color_var = StringVar(value="#848587")
        self.vars["arrow_color"] = arrow_color_var
        CTkEntry(pixel_settings, placeholder_text="#848587", width=120, textvariable=arrow_color_var).grid(row=4, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Fish Color:").grid(row=5, column=0, padx=12, pady=10, sticky="w")
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        CTkEntry(pixel_settings, placeholder_text="#434B5B", width=120, textvariable=fish_color_var).grid(row=5, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Fish Color 2:").grid(row=6, column=0, padx=12, pady=10, sticky="w")
        fish2_color_var = StringVar(value="#434B5B")
        self.vars["fish2_color"] = fish2_color_var
        CTkEntry(pixel_settings, placeholder_text="#434B5B", width=120, textvariable=fish2_color_var).grid(row=6, column=1, padx=12, pady=10, sticky="w")
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(pixel_settings, text="Tolerance:").grid(row=2, column=2, padx=12, pady=10, sticky="w")
        left_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(pixel_settings, text="Tolerance:").grid(row=3, column=2, padx=12, pady=10, sticky="w")
        right_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=3, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid(row=4, column=2, padx=12, pady=10, sticky="w")
        arrow_tolerance_var = StringVar(value="8")
        self.vars["arrow_tolerance"] = arrow_tolerance_var
        arrow_tolerance_entry = CTkEntry(pixel_settings, placeholder_text="8", width=120, textvariable=arrow_tolerance_var)
        arrow_tolerance_entry.grid(row=4, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid(row=5, column=2, padx=12, pady=10, sticky="w")
        fish_tolerance_var = StringVar(value="0")
        self.vars["fish_tolerance"] = fish_tolerance_var
        CTkEntry(pixel_settings, width=120, textvariable=fish_tolerance_var).grid(row=5, column=3, padx=12, pady=10, sticky="w")
        CTkLabel(pixel_settings, text="Tolerance:").grid(row=6, column=2, padx=12, pady=10, sticky="w")
        fish2_tolerance_var = StringVar(value="0")
        self.vars["fish2_tolerance"] = fish2_tolerance_var
        CTkEntry(pixel_settings, width=120, textvariable=fish2_tolerance_var).grid(row=6, column=3, padx=12, pady=10, sticky="w")
        # Minigame Timing and Limits
        ratio_settings = CTkFrame(
            scroll,
            border_width=2
        )
        ratio_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
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

        CTkLabel(ratio_settings, text="Restart Delay:").grid(row=3, column=0, padx=12, pady=10, sticky="w" )

        restart_delay_var = StringVar(value="1")
        self.vars["restart_delay"] = restart_delay_var

        CTkEntry(ratio_settings, width=120, textvariable=restart_delay_var ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        pid_settings = CTkFrame(scroll, border_width=2 )
        pid_settings.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(pid_settings, text="PD Controller Settings", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        CTkLabel(pid_settings, text="Proportional gain:").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        p_gain_var = StringVar(value="0.9")
        self.vars["proportional_gain"] = p_gain_var
        CTkEntry(pid_settings, width=120, textvariable=p_gain_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pid_settings, text="Derivative gain:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        d_gain_var = StringVar(value="0.4")
        self.vars["derivative_gain"] = d_gain_var
        CTkEntry(pid_settings, width=120, textvariable=d_gain_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pid_settings, text="Stabilize Threshold:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        stabilize_threshold2_var = StringVar(value="6")
        self.vars["stabilize_threshold2"] = stabilize_threshold2_var
        CTkEntry(pid_settings, width=120, textvariable=stabilize_threshold2_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(pid_settings, text="P/D Clamp:").grid(row=4, column=0, padx=12, pady=10, sticky="w")
        pid_clamp_var = StringVar(value="100")
        self.vars["pid_clamp"] = pid_clamp_var
        CTkEntry(pid_settings, width=120, textvariable=pid_clamp_var).grid(row=4, column=1, padx=12, pady=10, sticky="w")
    # LOGGING SETTINGS TAB
    def build_logging_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Discord Webhook Settings
        discord_webhook = CTkFrame(scroll, border_width=2)
        discord_webhook.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(discord_webhook, text="Discord Webhook", font=CTkFont(size=16, weight="bold") ).grid(row=0, column=0, columnspan=2, padx=12, pady=(10, 5), sticky="w")

        discord_enabled_var = StringVar(value="off")
        self.vars["discord_enabled"] = discord_enabled_var
        discord_enabled_cb = CTkCheckBox(discord_webhook, text="Enable Discord Webhook", variable=discord_enabled_var, onvalue="on", offvalue="off")
        discord_enabled_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")

        CTkLabel(discord_webhook, text="Webhook URL:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        discord_webhook_url_var = StringVar(value="https://discord.com/api/webhooks/XXXXXXXXXX/XXXXXXXXXX")
        self.vars["discord_webhook_url"] = discord_webhook_url_var
        CTkEntry(discord_webhook, width=220, textvariable=discord_webhook_url_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(discord_webhook, text="Webhook name:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        discord_webhook_name_var = StringVar(value="I Can't Fish")
        self.vars["discord_webhook_name"] = discord_webhook_name_var
        CTkEntry(discord_webhook, width=120, textvariable=discord_webhook_name_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        # Test webhook button
        CTkButton( discord_webhook, text="Test Webhook", command=self.test_discord_webhook
                  ).grid(row=4, column=0, columnspan=2, padx=12, pady=12, sticky="w")
    # UTILITIES TAB
    def build_utilities_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        # Warning
        CTkLabel(scroll, text="These tools are not implemented yet", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        # Auto Totem
        auto_totem = CTkFrame(scroll, border_width=2)
        auto_totem.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(auto_totem, text="Auto Totem", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")
        
        CTkLabel(auto_totem, text="Auto Totem Mode:").grid(row=1, column=0, padx=12, pady=10, sticky="w" )
        auto_totem_mode_var = StringVar(value="Time")
        self.vars["auto_totem_mode"] = auto_totem_mode_var
        auto_totem_cb = CTkComboBox(auto_totem, values=["Time", "Cycles", "Disabled"], 
                               variable=auto_totem_mode_var, command=lambda v: self.set_status(f"Auto Totem mode: {v}")
                               )
        auto_totem_cb.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["auto_totem_mode"] = auto_totem_cb
        
        CTkLabel(auto_totem, text="Totem Delay (seconds):").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        totem_delay_var = StringVar(value="900")
        self.vars["totem_delay"] = totem_delay_var
        CTkEntry(auto_totem, width=120, textvariable=totem_delay_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(auto_totem, text="Totem Cycles:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        totem_cycles_var = StringVar(value="70")
        self.vars["totem_cycles"] = totem_cycles_var
        CTkEntry(auto_totem, width=120, textvariable=totem_cycles_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(auto_totem, text="Use Sundial When:").grid(row=4, column=0, padx=12, pady=10, sticky="w" )
        use_sundial_mode_var = StringVar(value="Disabled")
        self.vars["use_sundial_mode"] = use_sundial_mode_var
        use_sundial_cb = CTkComboBox(auto_totem, values=["Day", "Night", "Disabled"], 
                               variable=use_sundial_mode_var, command=lambda v: self.set_status(f"Macro now uses sundial totem when {v}")
                               )
        use_sundial_cb.grid(row=4, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["use_sundial_mode"] = use_sundial_cb

        # Auto Reconnect
        auto_reconnect = CTkFrame(scroll, border_width=2)
        auto_reconnect.grid(row=2, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(auto_reconnect, text="Auto Reconnect", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        auto_reconnect_var = StringVar(value="off")
        self.vars["auto_reconnect"] = auto_reconnect_var
        auto_reconnect_cb = CTkCheckBox(auto_reconnect, text="Auto Reconnect", variable=auto_reconnect_var, onvalue="on", offvalue="off")
        auto_reconnect_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")
    # ADVANCED SETTINGS TAB
    def build_advanced_tab(self, parent):
        scroll = CTkScrollableFrame(parent)
        scroll.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        # VERY important
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)

        # Advanced Colors
        advanced_colors = CTkFrame(scroll, border_width=2)
        advanced_colors.grid(row=0, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(advanced_colors, text="Advanced Colors", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w")   
        
        CTkLabel(advanced_colors, text="Shake Color:").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        shake_color_var = StringVar(value="#FFFFFF")
        self.vars["shake_color"] = shake_color_var
        CTkEntry(advanced_colors, width=120, textvariable=shake_color_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(advanced_colors, text="Perfect Cast (Green) Color:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        perfect_color_var = StringVar(value="#64a04c")
        self.vars["perfect_color"] = perfect_color_var
        CTkEntry(advanced_colors, width=120, textvariable=perfect_color_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(advanced_colors, text="Perfect Cast (White) Color:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        perfect_color2_var = StringVar(value="#d4d3ca")
        self.vars["perfect_color2"] = perfect_color2_var
        CTkEntry(advanced_colors, width=120, textvariable=perfect_color2_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")

        gift_settings = CTkFrame(scroll, border_width=2)
        gift_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        CTkLabel(gift_settings, text="Gift Box Options", font=CTkFont(size=14, weight="bold")).grid(row=0, column=0, padx=12, pady=8, sticky="w") 

        CTkLabel(gift_settings, text="Gift Box Color:").grid(row=1, column=0, padx=12, pady=10, sticky="w")
        gift_box_color_var = StringVar(value="#00990c")
        self.vars["gift_box_color"] = gift_box_color_var
        CTkEntry(gift_settings, width=120, textvariable=gift_box_color_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(gift_settings, text="Gift Box Tolerance:").grid(row=2, column=0, padx=12, pady=10, sticky="w")
        gift_box_tolerance_var = StringVar(value="2")
        self.vars["gift_box_tolerance"] = gift_box_tolerance_var
        CTkEntry(gift_settings, width=120, textvariable=gift_box_tolerance_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(gift_settings, text="Tracking Focus:").grid(row=3, column=0, padx=12, pady=10, sticky="w")
        tracking_focus_var = StringVar(value="Fish")
        self.vars["tracking_focus"] = tracking_focus_var
        tracking_cb = CTkComboBox(gift_settings, values=["Gift", "Gift + Fish", "Fish"], 
                                  variable=tracking_focus_var, command=lambda v: self.set_status(f"Tracking mode set to {v}"))
        tracking_cb.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["tracking_focus"] = tracking_cb

        CTkLabel(gift_settings, text="Ratio Before Tracking:").grid(row=4, column=0, padx=12, pady=10, sticky="w")
        gift_track_ratio_var = StringVar(value="0.1")
        self.vars["gift_track_ratio"] = gift_track_ratio_var
        CTkEntry(gift_settings, width=120, textvariable=gift_track_ratio_var).grid(row=4, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(gift_settings, text="Note Cooldown:").grid(row=5, column=0, padx=12, pady=10, sticky="w")
        note_cooldown_var = StringVar(value="0.2")
        self.vars["note_cooldown"] = note_cooldown_var
        CTkEntry(gift_settings, width=120, textvariable=note_cooldown_var).grid(row=5, column=1, padx=12, pady=10, sticky="w")
    # Save and load settings
    def load_configs(self):
        """Load list of available config files."""
        config_dir = USER_CONFIG_DIR
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

                # IMPORTANT: Save hotkeys
                "start_key": self.vars["start_key"].get(),
                "change_bar_areas_key": self.vars["change_bar_areas_key"].get(),
                "screenshot_key": self.vars["screenshot_key"].get(),
                "stop_key": self.vars["stop_key"].get()
            }
            with open("last_config.json", "w") as f:
                json.dump(data, f, indent=4)
            # IMPORTANT: Immediately update active hotkeys
            self.hotkey_start      = self._string_to_key(self.vars["start_key"].get())
            self.hotkey_change_areas = self._string_to_key(self.vars["change_bar_areas_key"].get())
            self.hotkey_screenshot = self._string_to_key(self.vars["screenshot_key"].get())
            self.hotkey_stop       = self._string_to_key(self.vars["stop_key"].get())
            self._register_hotkeys()
        except Exception as e:
            import traceback
            traceback.print_exc()

    def save_settings(self, name):
        """Save all settings to a JSON config file."""
        config_dir = USER_CONFIG_DIR
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
        except Exception as e:
            self.set_status(f"Error saving config: {e}")
    
    def load_settings(self, name):
        """Load settings from a JSON config file."""
        config_dir = USER_CONFIG_DIR
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
    def load_misc_settings(self):
        """Load miscellaneous settings from last_config.json."""
        try:
            if os.path.exists("last_config.json"):
                with open("last_config.json", "r") as f:
                    data = json.load(f)
                    self.current_rod_name = data.get("last_rod", "Basic Rod")
                    self.bar_areas = data.get("bar_areas", {"shake": None, "fish": None})
                    # IMPORTANT: Load hotkeys if present
                    start_key = data.get("start_key", "F5")
                    change_key = data.get("change_bar_areas_key", "F6")
                    screenshot_key = data.get("screenshot_key", "F8")
                    stop_key = data.get("stop_key", "F7")

                    self.vars["start_key"].set(start_key)
                    self.vars["change_bar_areas_key"].set(change_key)
                    self.vars["screenshot_key"].set(screenshot_key)
                    self.vars["stop_key"].set(stop_key)

                    # Convert to hotkey strings and re-register
                    self.hotkey_start        = self._string_to_key(start_key)
                    self.hotkey_change_areas = self._string_to_key(change_key)
                    self.hotkey_screenshot   = self._string_to_key(screenshot_key)
                    self.hotkey_stop         = self._string_to_key(stop_key)
                    self._register_hotkeys()
            else:
                self.current_rod_name = "Basic Rod"
                self.bar_areas = {"fish": None, "shake": None}
        except:
            self.current_rod_name = "Basic Rod"
            self.bar_areas = {"fish": None, "shake": None}
    # Macro functions
    def _string_to_key(self, key_string):
        """Normalise a hotkey string to lowercase (used by the keyboard library)."""
        return key_string.strip().lower()

    def _register_hotkeys(self):
        """Register all hotkeys using the `keyboard` library."""
        try:
            keyboard_lib.unhook_all()
        except Exception:
            pass

        def _on_start():
            self.on_key_press("start")
        def _on_change():
            self.on_key_press("change_areas")
        def _on_screenshot():
            self.on_key_press("screenshot")
        def _on_stop():
            self.on_key_press("stop")

        try:
            keyboard_lib.add_hotkey(self.hotkey_start,    _on_start,      suppress=False)
            keyboard_lib.add_hotkey(self.hotkey_change_areas, _on_change,  suppress=False)
            keyboard_lib.add_hotkey(self.hotkey_screenshot,   _on_screenshot, suppress=False)
            keyboard_lib.add_hotkey(self.hotkey_stop,     _on_stop,       suppress=False)
        except Exception as e:
            print("Hotkey registration error:", e)

    def on_key_press(self, action):
        try:
            if action == "start" and not self.macro_running:
                config_name = self.vars["active_config"].get()
                self.save_settings(config_name)
                self.macro_running = True
                self.after(0, self.withdraw)
                threading.Thread(target=self.start_macro, daemon=True).start()
            elif action == "change_areas":
                self.open_dual_area_selector()
            elif action == "screenshot":
                self._take_debug_screenshot()
            elif action == "stop":
                self.stop_macro()
        except Exception as e:
            print("Hotkey error:", e)
    def set_status(self, text, key=None):
        self.status_label.configure(text=text)
    # Utility functions
    def _take_debug_screenshot(self):
        """
        Capture the configured fish area and save a debug image.
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
    # Eyedropper-related functions
    def _pick_colors(self):
        """Live eyedropper tool without freezing screen."""
        self.eyedropper = tk.Toplevel(self)

        w = self.winfo_screenwidth()
        h = self.winfo_screenheight()

        self.eyedropper.geometry(f"{w}x{h}+0+0")
        self.eyedropper.attributes("-alpha", 0.01)
        self.eyedropper.attributes("-topmost", True)
        self.eyedropper.config(cursor="crosshair")

        # Create ONE capture object
        self.capture_mode = "mss"

        if sys.platform == "win32" and getattr(self, "dxcam_enabled", False):
            try:
                import dxcam
                self.cam = dxcam.create()
                self.capture_mode = "dxcam"
            except Exception:
                self.sct = mss.mss()
                self.capture_mode = "mss"
        else:
            self.sct = mss.mss()

        self.eyedropper.bind("<Motion>", self._update_hover_color)
        self.eyedropper.bind("<Button-1>", self._on_pick_color)
        self.eyedropper.bind("<Escape>", self._close_eyedropper)
    def _on_pick_color(self, event):
        x = self.winfo_pointerx()
        y = self.winfo_pointery()

        if self.capture_mode == "dxcam":
            frame = self.cam.grab(region=(x, y, x+1, y+1))
            if frame is None:
                return
            b, g, r = frame[0][0]

        else:
            monitor = {"left": x, "top": y, "width": 1, "height": 1}
            img = self.sct.grab(monitor)
            b = img.raw[0]
            g = img.raw[1]
            r = img.raw[2]

        hex_color = f"#{r:02X}{g:02X}{b:02X}"

        self.set_status(f"Picked: {hex_color}")
        self.last_picked_color = hex_color

        self._close_eyedropper()
    def _update_hover_color(self, event):
        x = self.winfo_pointerx()
        y = self.winfo_pointery()

        if self.capture_mode == "dxcam":
            frame = self.cam.grab(region=(x, y, x+1, y+1))
            if frame is None:
                return
            b, g, r = frame[0][0]

        else:  # MSS
            monitor = {"left": x, "top": y, "width": 1, "height": 1}
            img = self.sct.grab(monitor)
            b = img.raw[0]
            g = img.raw[1]
            r = img.raw[2]

        hex_color = f"#{r:02X}{g:02X}{b:02X}"

        self.set_status(f"Hover: {hex_color}  |  Click to pick")
    def _close_eyedropper(self, event=None):
        if hasattr(self, "sct"):
            self.sct.close()

        if hasattr(self, "cam"):
            self.cam.stop()

        if self.eyedropper:
            self.eyedropper.destroy()
    # Misc-related functions
    def open_link(self, url):
        """Open a URL in the default web browser."""
        return lambda: webbrowser.open(url)
    def open_dual_area_selector(self):
        self.update_idletasks()
        # Toggle OFF if already open
        if hasattr(self, "area_selector") and self.area_selector and self.area_selector.window.winfo_exists():
            self.area_selector.close()
            self.area_selector = None
            self.set_status("Area selector closed")
            return
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        # ---- Default fallback areas ----
        def default_shake_area():
            left = int(screen_w * 0.2083)
            top = int(screen_h * 0.162)
            right = int(screen_w * 0.7813)
            bottom = int(screen_h * 0.7778)
            return { "x": left, "y": top, "width": right - left, "height": bottom - top }
        def default_fish_area():
            left = int(screen_w * 0.2844)
            top = int(screen_h * 0.7981)
            right = int(screen_w * 0.7141)
            bottom = int(screen_h * 0.8370)
            return { "x": left, "y": top, "width": right - left, "height": bottom - top }
        # ---- Load saved areas or fallback ----
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
        # ---- Callback when user closes selector ----
        def on_done(shake, fish):
            self.bar_areas["shake"] = shake
            self.bar_areas["fish"] = fish
            self.save_misc_settings()
            self.area_selector = None
            self.set_status("Bar areas saved")
        # ---- Open selector ----
        self.area_selector = DualAreaSelector(parent=self, shake_area=shake_area, fish_area=fish_area, callback=on_done)
        self.set_status("Area selector opened (click button again to close)")
    def open_configs_folder(self):
        folder = USER_CONFIG_DIR
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":  # macOS
            subprocess.run(["open", folder])
        else:  # Linux
            subprocess.run(["xdg-open", folder])
    # Logging-related functions
    def _discord_text_worker(self, webhook_url, message_prefix, loop_count):
        """Worker function to send text webhook."""
        discord_webhook_name = self.vars["discord_webhook_name"].get()
        try:
            payload = {
                'content': f'{message_prefix}🎣 {discord_webhook_name} bot\n🔄 Loop #{loop_count}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': discord_webhook_name,
                'embeds': [{
                    'title': '⚡ Bot Status Update',
                    'description': f'Completed loop #{loop_count}',
                    'color': 0x5865F2,
                    'timestamp': time.strftime("%Y-%m-%dT%H:%M:%S")
                }]
            }
            
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200 or response.status_code == 204:
                self.set_status(f"Discord text sent (Loop #{loop_count})")
            else:
                self.set_status(f"Error: Discord text failed: {response.status_code}")
        except Exception as e:
            self.set_status(f"Error sending Discord text: {e}")
    def _discord_screenshot_worker(self, webhook_url, message_prefix, loop_count):
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = np.array(sct.grab(monitor))

            screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)

            _, buffer = cv2.imencode(".png", screenshot)
            img_byte_arr = io.BytesIO(buffer.tobytes())

            files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}

            payload = {
                'content': f'{message_prefix}🎣 **Fishing Macro** 🤖\n🔄 Loop #{loop_count}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': 'Fishing Macro'
            }

            response = requests.post(webhook_url, data=payload, files=files, timeout=10)

            if response.status_code in (200, 204):
                self.set_status(f"Discord screenshot sent (Loop #{loop_count})")
            else:
                self.set_status(f"Error: Discord screenshot failed: {response.status_code}")

        except Exception as e:
            self.set_status(f"Error: sending Discord screenshot: {e}")
    def test_discord_webhook(self):
        self.send_discord_webhook("**Discord Webhook is working**", 0)
    def send_discord_webhook(self, text, loop_count):
        if not self.vars["discord_enabled"].get() == "on":
            self.set_status("⚠ Discord webhook is disabled.")
            return
        # discord_webhook_url
        webhook_url = self.vars["discord_webhook_url"].get().strip()

        if not webhook_url.startswith("https://discord.com/api/webhooks/"):
            self.set_status("Error: Invalid webhook URL.")
            return

        self.set_status("Sending test webhook...")

        thread = threading.Thread(
            target=self._discord_text_worker,
            args=(webhook_url, f"{text}\n", loop_count),
            daemon=True
        )
        thread.start()
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
    def _init_capture_buffer(self, width, height):
        self._capture_buffer = np.empty((height, width, 3), dtype=np.uint8)
    def _grab_screen_region(self, left, top, right, bottom):
        # Grabs the current screen region
        width = right - left
        height = bottom - top

        if width <= 0 or height <= 0:
            return None

        # Reuse monitor dict to avoid allocations
        if not hasattr(self, "_monitor"):
            self._monitor = {}

        m = self._monitor
        m["left"] = left
        m["top"] = top
        m["width"] = width
        m["height"] = height

        # Ensure MSS exists for this thread
        if not hasattr(self, "_thread_local"):
            self._thread_local = threading.local()

        if not hasattr(self._thread_local, "sct"):
            self._thread_local.sct = mss.mss()

        sct = self._thread_local.sct

        # --- macOS ---
        if sys.platform == "darwin":
            img = sct.grab(m)

            # BGRA -> BGR directly into buffer
            frame = np.frombuffer(img.raw, dtype=np.uint8)
            frame = frame.reshape(img.height, img.width, 4)

            self._capture_buffer[:] = frame[:, :, :3]

            return self._capture_buffer

        # --- Windows ---
        mode = self.vars.get("capture_mode")

        if mode and mode.get() == "DXCAM" and self.camera:
            frame = self.camera.get_latest_frame()
            if frame is None:
                return None

            cropped = frame[top:bottom, left:right]
            return cv2.cvtColor(cropped, cv2.COLOR_RGB2BGR)

        # Fallback MSS
        img = np.array(sct.grab(m))[:, :, :3]
        return img

    def _click_at(self, x, y):
        pyautogui.moveTo(x, y, duration=0)
        time.sleep(0.03)
        pyautogui.moveRel(1, 0)
        time.sleep(0.01)
        pyautogui.moveRel(-1, 0)
        time.sleep(0.01)
        pyautogui.click()

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
    
    def _find_bar_edges(self, frame, 
                        left_hex, right_hex, 
                        tolerance=15, tolerance2=15, 
                        scan_height_ratio=0.5):
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

        left_edge = None
        right_edge = None
        # --- LEFT BAR COLOR ---
        if left_hex is not None:
            lower_l = left_bgr - tol_l
            upper_l = left_bgr + tol_l

            left_mask = np.all((line >= lower_l) & (line <= upper_l), axis=1)
            left_indices = np.where(left_mask)[0]

            if left_indices.size > 0:
                left_edge = left_indices.min()

        # --- RIGHT BAR COLOR ---
        if right_hex is not None:
            lower_r = right_bgr - tol_r
            upper_r = right_bgr + tol_r

            right_mask = np.all((line >= lower_r) & (line <= upper_r), axis=1)
            right_indices = np.where(right_mask)[0]

            if right_indices.size > 0:
                right_edge = right_indices.max()

        # --- FINAL EDGE EXTRACTION ---
        if left_edge is not None and right_edge is not None:
            return int(left_edge), int(right_edge)
        return None, None
    
    def _find_bar_edges_legacy(
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
        
        return kp, kd
    
    def _pid_control(self, error, bar_center_x=None):
        """
        Compute PD output using proportional gain system from comet reference.
        Uses velocity-based derivative with asymmetric damping.
        """

        now = time.perf_counter()
        pd_clamp = float(self.vars["pid_clamp"].get() or 1.0)  # Changed default to 1.0 like comet
        # first sample: initialize state and return zero control
        if self.last_time is None:
            self.last_time = now
            self.prev_error = error
            if bar_center_x is not None:
                self.last_bar_x = bar_center_x
            return 0.0

        dt = now - self.last_time
        if dt <= 0:
            return 0.0

        kp, kd = self._get_pid_gains()

        # P term - proportional to how far we need to move
        p_term = kp * error

        # D term - asymmetric damping based on situation
        d_term = 0.0
        if bar_center_x is not None and self.last_bar_x is not None and dt > 0:
            bar_velocity = (bar_center_x - self.last_bar_x) / dt
            error_magnitude_decreasing = abs(error) < abs(self.prev_error) if self.prev_error is not None else False
            bar_moving_toward_target = (bar_velocity > 0 and error > 0) or (bar_velocity < 0 and error < 0)
            damping_multiplier = 2.0 if (error_magnitude_decreasing and bar_moving_toward_target) else 0.5
            d_term = -kd * damping_multiplier * bar_velocity
        else:
            # Fallback to standard derivative
            if self.prev_error is not None and dt > 0:
                d_term = kd * (error - self.prev_error) / dt

        # Combined control signal (PD controller output)
        control_signal = p_term + d_term
        control_signal = max(-pd_clamp, min(pd_clamp, control_signal))  # Clamp output

        # update history
        self.prev_error = error
        self.last_time = now
        if bar_center_x is not None:
            self.last_bar_x = bar_center_x

        return control_signal

    def _reset_pid_state(self):
        """
        Reset PD control state variables.
        """
        # history fields used by ``_pid_control``
        self.prev_error = 0.0
        self.last_time = None
        self.last_bar_x = None

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
    # === MINIGAME WINDOW (instance methods) ===
    def init_overlay_window(self):
        """
        Create the minigame window and canvas (only once).
        """
        if self.overlay_window and self.overlay_window.winfo_exists():
            return

        self.overlay_window = tk.Toplevel(self)
        self.overlay_window.geometry("800x50+560+660")
        if sys.platform == "darwin":
            self.overlay_window.overrideredirect(False)
        else:
            self.overlay_window.overrideredirect(True)
        self.overlay_window.attributes("-topmost", True)

        self.overlay_canvas = tk.Canvas(
            self.overlay_window,
            width=800,
            height=60,
            bg="#1d1d1d",
            highlightthickness=0
        )
        self.overlay_canvas.pack(fill="both", expand=True)

    def show_overlay(self):
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.deiconify()
            self.overlay_window.lift()

    def hide_overlay(self):
        if self.overlay_window and self.overlay_window.winfo_exists():
            self.overlay_window.withdraw()

    def clear_overlay(self):
        if not self.overlay_canvas or not self.overlay_canvas.winfo_exists():
            return
        self.overlay_canvas.delete("all")
        self.initial_bar_size = None

    def draw_box(self, x1, y1, x2, y2, fill="#000000", outline="white"):
        if not self.overlay_canvas or not self.overlay_canvas.winfo_exists():
            return

        def _draw():
            self.overlay_canvas.create_rectangle(x1, y1, x2, y2, 
                                                 outline=outline, width=2, fill=fill)

        self.overlay_canvas.after(0, _draw)

    def draw_overlay(self,bar_center, box_size, 
                     color, canvas_offset, 
                     show_bar_center=False, 
                     bar_y1=10, bar_y2=40,):
        """
        Draws:
        - Square box with size
        - Optional gray center line
        """

        # Guard against missing center
        if bar_center is None:
            return

        box_size = int(box_size / 2)
        # Calculate bar edges
        left_edge = bar_center - box_size
        right_edge = bar_center + box_size

        # Convert to canvas coordinates
        bx1 = left_edge - canvas_offset
        bx2 = right_edge - canvas_offset
        center_x = bar_center - canvas_offset

        # Main bar
        self.draw_box(bx1, bar_y1, bx2, bar_y2, fill="#000000", outline=color)

        # Center line
        if show_bar_center == True:
            self.overlay_canvas.create_line(center_x, bar_y1, 
                                            center_x, bar_y2, 
                                            fill="gray", width=2)
    # Do pixel search function (I put it here because it's organized)
    def _do_pixel_search(self, img):
        fish_hex = self.vars["fish_color"].get()
        left_bar_hex = self.vars["left_color"].get()
        right_bar_hex = self.vars["right_color"].get()

        left_tol = int(self.vars["left_tolerance"].get() or 8)
        right_tol = int(self.vars["right_tolerance"].get() or 8)
        fish_tol = int(self.vars["fish_tolerance"].get() or 1)
        fish_center = self._find_color_center(img, fish_hex, fish_tol)

        legacy_pixel_search = self.vars["legacy_pixel_search"].get()
        # Use legacy pixel search if possible
        if legacy_pixel_search:
            left_bar_center, right_bar_center = self._find_bar_edges_legacy(img, left_bar_hex, right_bar_hex, left_tol, right_tol)
            if left_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges_legacy(img, right_bar_hex, right_bar_hex, right_tol, right_tol)
            elif right_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges_legacy(img, left_bar_hex, left_bar_hex, left_tol, left_tol)
        else:
            left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, right_bar_hex, left_tol, right_tol)
            if left_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges(img, right_bar_hex, right_bar_hex, right_tol, right_tol)
            elif right_bar_center is None:
                left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, left_bar_hex, left_tol, left_tol)
        return fish_center, left_bar_center, right_bar_center
    # Start macro and main loop
    def start_macro(self):
        # Get shake area for mouse movement areas
        shake = self.bar_areas.get("shake")
        if isinstance(shake, dict):
            shake_left   = shake["x"]
            shake_top    = shake["y"]
            shake_right  = shake["x"] + shake["width"]
            shake_bottom = shake["y"] + shake["height"]
            shake_x = int((shake_left + shake_right) / 2)
            shake_y = int((shake_top + shake_bottom) / 2)
        else:
            shake_x = int(self.SCREEN_WIDTH * 0.5)
            shake_y = int(self.SCREEN_HEIGHT * 0.3)
        # 434 705 1029 794
        self.macro_running = True
        self._reset_pid_state()
        self.set_status("Macro Status: Running")

        # Initial camera alignment (ONLY ONCE)
        pyautogui.moveTo(shake_x, shake_y)
        if self.vars["auto_zoom_in"].get() == "on":
            for _ in range(20):
                pyautogui.scroll(1)
                time.sleep(0.05)
            pyautogui.scroll(-1)
            time.sleep(0.1)
        # Set current cycle to 0
        current_cycle = 0
        cycle = 0
        # Loop: MAIN MACRO LOOP
        while self.macro_running:
            # Check Reconnect (not implemented yet)
            # Check Totem
            # Send Discord Webhook
            self.send_discord_webhook("Loop completed", cycle)
            # if not self.vars["auto_totem_mode"].get() == "Disabled":
            #    self.execute_totem(cycle)
            # 1. Select rod
            if self.vars["auto_select_rod"].get() == "on":
                bag_delay = float(self.vars["bag_delay"].get())
                self.set_status("Selecting rod")
                keyboard_lib.press('2')
                time.sleep(0.05)
                keyboard_lib.release('2')
                time.sleep(bag_delay)
                keyboard_lib.press('1')
                time.sleep(0.05)
                keyboard_lib.release('1')
                time.sleep(0.2)
            # 2: Fish Overlay
            if self.vars["fish_overlay"].get() == "on":
                self.show_overlay()
            else:
                self.hide_overlay()
            if not self.macro_running:
                break

            # 2. Cast
            self.set_status("Casting")
            if self.vars["casting_mode"].get() == "Perfect":
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

            # 3. Shake
            self.set_status("Shaking")
            if self.vars["shake_mode"].get() == "Click":
                self._execute_shake_click()
            else:
                self._execute_shake_navigation()

            if not self.macro_running:
                break

            # 4. Fish (minigame)
            self.set_status("Fishing")
            cycle = self._enter_minigame(current_cycle)
            # Restart: When minigame ends, loop repeats from Select Rod
    def execute_totem(self, cycle):
        required_cycle = float(self.vars["totem_cycles"].get())
        condition = cycle % required_cycle
        if condition == 0:
            pass # not implemented yet
    def _execute_cast_perfect(self):
        """
        Find perfect cast color and cast color
        Then, compare the distances between perfect cast color and cast color
        Then, release (if failsafe reached release anyways)
        """
        # Hold click
        pyautogui.mouseDown(button='left')
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
        # Time
        start_time = time.time()
        # Perfect colors
        white_color = self.vars["perfect_color2"].get()
        green_color = self.vars["perfect_color"].get()
        # Perfect tolerance
        white_tolerance = int(self.vars["perfect_cast2_tolerance"].get())
        green_tolerance = int(self.vars["perfect_cast_tolerance"].get())
        # Perfect release delay conversion
        release_delay = float(self.vars["perfect_release_delay"].get())
        max_time = float(self.vars["perfect_max_time"].get())
        if release_delay < 0:
            green_offset = abs(release_delay * 10)
            release_delay = 0
        else:
            green_offset = 0
        # Perfect cast loop
        while self.macro_running:
            frame = self._grab_screen_region(shake_left, shake_top, shake_right, shake_bottom)
            self.clear_overlay()
            green_pixels = self._pixel_search(frame, green_color, green_tolerance)
            if not green_pixels:
                if time.time() - start_time > max_time:
                    pyautogui.mouseUp(button='left')
                    return
                time.sleep(float(self.vars["cast_scan_delay"].get()))
                continue
            # Lowest green pixel
            green_x, green_y = max(green_pixels, key=lambda p: p[1])
            green_y = green_y + green_offset
            white_pixels = self._pixel_search(frame, white_color, white_tolerance)
            if not white_pixels:
                time.sleep(float(self.vars["cast_scan_delay"].get()))
                continue
            white_x, white_y = min(white_pixels, key=lambda p: abs(p[1] - green_y))
            if white_pixels and green_pixels: # If white and green found
                distance = abs(green_y - white_y)
                if distance < 30: # Perfect cast release condition
                    time.sleep(release_delay)
                    pyautogui.mouseUp(button='left')
                    return
            if time.time() - start_time > max_time: # Timer limit reached
                pyautogui.mouseUp(button='left')
                return
            time.sleep(float(self.vars["cast_scan_delay"].get()))
    def _execute_cast_normal(self):
        """Hold left click for user cast delay"""
        delay2 = float(self.vars["casting_delay2"].get() or 0.0)
        time.sleep(delay2)  # wait for cast to register in other games
        pyautogui.mouseDown(button='left')
        duration = float(self.vars["cast_duration"].get() or 0.6)
        delay = float(self.vars["cast_delay"].get() or 0.2)
        time.sleep(duration)  # adjust cast strength
        pyautogui.mouseUp(button='left')
        time.sleep(delay)  # wait for cast to register in fisch

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
        # Initialize attempts counter
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
            # 2. Look for shake pixel
            shake_pixel = self._find_shake_pixel(shake_area, shake_hex, tolerance)
            if shake_pixel:
                x, y = shake_pixel
                screen_x = shake_left + x
                screen_y = shake_top + y
                self._click_at(screen_x, screen_y)

            # 2..5 Stable fish detection
            stable = 0
            while stable < 8 and self.macro_running:
                detection_area = self._grab_screen_region(fish_left, fish_top, fish_right, fish_bottom)
                if detection_area is None:
                    break
                fish_x = self._find_color_center(detection_area, fish_hex, tolerance)
                if fish_x:
                    stable += 1
                    time.sleep(0.005)
                else:
                    break

            # 3. Fish detected → enter minigame
            if stable >= 8:
                self.set_status("Entering Minigame")
                pyautogui.mouseDown(button='left')
                time.sleep(0.003)
                pyautogui.mouseUp(button='left')
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
            # 1. Navigation shake (Enter key)
            keyboard_lib.press('enter')
            time.sleep(0.03)
            keyboard_lib.release('enter')
            time.sleep(scan_delay)
            # 2. Stable fish detection (old logic preserved)
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
            # 3. Fish detected → enter minigame
            if stable >= 8:
                self.set_status("Entering Minigame")
                pyautogui.mouseDown(button='left')
                time.sleep(0.003)
                pyautogui.mouseUp(button='left')
                return  # exit shake cleanly
            attempts += 1
            time.sleep(scan_delay)
    def _enter_minigame(self, cycle):
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
        # Restart delay
        restart_delay = float(self.vars["restart_delay"].get())
        # Gift box color and timer settings
        gift_box_hex = self.vars["gift_box_color"].get()
        gift_box_tol = int(self.vars["gift_box_tolerance"].get() or 8)
        gift_track_ratio = float(self.vars["gift_track_ratio"].get())
        # Arrow tracking variables
        arrow_hex = self.vars["arrow_color"].get()
        arrow_tol = int(self.vars["arrow_tolerance"].get() or 8)
        bar_ratio = float(self.vars["bar_ratio"].get() or 0.5)
        scan_delay = float(self.vars["minigame_scan_delay"].get() or 0.05)
        # Thresh / clamp settings
        thresh = float(self.vars["stabilize_threshold2"].get() or 8)
        pid_clamp = float(self.vars["pid_clamp"].get() or 100)
        use_centroid = self.vars["centroid_tracking"].get()
        mouse_down = False
        # Initialize/zero PD state before entering the tracking loop
        self.prev_error = 0.0
        self.last_time = None
        tracking_focus2 = self.vars["tracking_focus"].get()
        if tracking_focus2 == "Gift":
            tracking_focus = 0
        elif tracking_focus2 == "Gift + Fish":
            tracking_focus = 1
        else:
            tracking_focus = 2
        # Deadzone action
        deadzone_action = 0
        def hold_mouse():
            nonlocal mouse_down
            if not mouse_down:
                pyautogui.mouseDown(button='left')
                mouse_down = True
        def release_mouse():
            nonlocal mouse_down
            if mouse_down:
                pyautogui.mouseUp(button='left')
                mouse_down = False
        while self.macro_running: # Main macro loop
            gift_img = self._grab_screen_region(shake_left, shake_top, shake_right, shake_bottom)
            img = self._grab_screen_region(fish_left, fish_top, fish_right, fish_bottom)
            if img is None:
                return
            fish_x, left_x, right_x = self._do_pixel_search(img) # Check line 1750-1850 for details
            # ---- Arrow ----
            arrow_center = self._find_color_center(img, arrow_hex, arrow_tol)
            # ---- Gift box ----
            gift_box_pos = self._find_color_center(gift_img, gift_box_hex, gift_box_tol)
            # ---- FISH HANDLING ----
            if fish_x is not None:
                self.last_fish_x = fish_x
            else:
                if left_x is None and right_x is None:
                    release_mouse()
                    time.sleep(restart_delay)
                    hold_mouse()
                    time.sleep(0.003)
                    release_mouse()
                    cycle = cycle + 1
                    return cycle
                else:
                    fish_x = self.last_fish_x
            # ---- STABILIZE FRAME ----
            deadzone_action = deadzone_action + 1
            if deadzone_action == 2:
                deadzone_action = 0
            # ---- CLEAR MINIGAME ----
            self.clear_overlay()
            # ---- BARS NOT FOUND ----
            bars_found = left_x is not None and right_x is not None
            try:
                fish_x = fish_x[0] + fish_left
            except TypeError:
                fish_x = fish_x + fish_left
            except Exception as e:
                fish_x = None
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
                # Gift tracking logic
                if gift_box_pos is not None:
                    ## Step 1: Convert note to screen coordinates
                    shake_width = shake_right - shake_left
                    fish_width = fish_right - fish_left
                    gift_screen_x = int((gift_box_pos[0] / shake_width) * fish_width) + fish_left
                    gift_screen_y = gift_box_pos[1] - shake_top
                    gift_screen_y_ratio = gift_screen_y / (shake_bottom - shake_top)
                if gift_box_pos is not None and tracking_focus == 0:
                    if gift_screen_y_ratio >= gift_track_ratio:
                        fish_x = gift_screen_x
                        pid_found = 3
                elif tracking_focus == 1:
                    pass
                if max_left is not None and fish_x <= max_left: # Max left and right check (inside bar)
                    if self.vars["fish_overlay"].get() == "on":
                        if self.vars["bar_size"].get() == "on":
                            self.after(0, lambda _bc=bar_center, _bs=bar_size, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=_bs, color="green", canvas_offset=_fl, show_bar_center=True))
                        else:
                            self.after(0, lambda _bc=bar_center, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=40, color="green", canvas_offset=_fl))
                        self.after(0, lambda _ml=max_left, _fl=fish_left: self.draw_overlay(bar_center=_ml, box_size=15, color="lightblue", canvas_offset=_fl))
                        self.after(0, lambda _fx=fish_x, _fl=fish_left: self.draw_overlay(bar_center=_fx, box_size=10, color="red", canvas_offset=_fl))
                    pid_found = 1
                elif max_right is not None and fish_x >= max_right:
                    if self.vars["fish_overlay"].get() == "on":
                        if self.vars["bar_size"].get() == "on":
                            self.after(0, lambda _bc=bar_center, _bs=bar_size, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=_bs, color="green", canvas_offset=_fl, show_bar_center=True))
                        else:
                            self.after(0, lambda _bc=bar_center, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=40, color="green", canvas_offset=_fl))
                        self.after(0, lambda _mr=max_right, _fl=fish_left: self.draw_overlay(bar_center=_mr, box_size=15, color="lightblue", canvas_offset=_fl))
                        self.after(0, lambda _fx=fish_x, _fl=fish_left: self.draw_overlay(bar_center=_fx, box_size=10, color="red", canvas_offset=_fl))
                    pid_found = 2
                else:
                    if self.vars["fish_overlay"].get() == "on":
                        # Main code
                        if self.vars["bar_size"].get() == "on":
                            self.after(0, lambda _bc=bar_center, _bs=bar_size, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=_bs, color="green", canvas_offset=_fl, show_bar_center=True))
                        else:
                            self.after(0, lambda _bc=bar_center, _fl=fish_left: self.draw_overlay(bar_center=_bc, box_size=40, color="green", canvas_offset=_fl))
                        self.after(0, lambda _fx=fish_x, _fl=fish_left: self.draw_overlay(bar_center=_fx, box_size=10, color="red", canvas_offset=_fl))
                    pid_found = 0
            elif arrow_center:
                capture_width = fish_right - fish_left
                arrow_indicator_x = self._find_arrow_indicator_x(img, arrow_hex, arrow_tol, mouse_down)
                if self.vars["fish_overlay"].get() == "on":
                    self.after(0, lambda: self.draw_overlay(bar_center=fish_x, box_size=10, color="red", canvas_offset=fish_left))
                if arrow_indicator_x is None:
                    pid_found = 1
                    return
                arrow_screen_x = arrow_indicator_x + fish_left
                if use_centroid == "on":
                    estimated_bar_center = self._update_arrow_box_estimation(arrow_indicator_x, mouse_down, capture_width)
                    if estimated_bar_center is not None:
                        bar_center = int(estimated_bar_center + fish_left)
                        pid_found = 0
                        if self.vars["fish_overlay"].get() == "on":
                            self.after(0, lambda: self.draw_overlay(bar_center=bar_center,box_size=40,color="yellow",canvas_offset=fish_left))
                    else:
                        pid_found = 1
                else:
                    distance = arrow_screen_x - fish_x
                    if distance > 0:
                        pid_found = 1   # release mouse
                    elif distance < 0:
                        pid_found = 2   # hold mouse
                    else:
                        pid_found = 1
                    if self.vars["fish_overlay"].get() == "on":
                        self.after(0, lambda: self.draw_overlay(bar_center=arrow_screen_x,box_size=10,
                                          color="yellow",canvas_offset=fish_left, show_bar_center=False, bar_y1=20, bar_y2=30))
            else: # No arrow / bar found
                pid_found = 1
            # PID calculation
            if pid_found == 0 and bar_center is not None:
                error = fish_x - bar_center
                control = self._pid_control(error, bar_center)
                # Map PID output to mouse clicks using hysteresis to avoid jitter/oscillation
                control = max((0 - pid_clamp), min(pid_clamp, control))
                # Stabilize Deadzone Checker
                if control > thresh:
                    hold_mouse()
                elif control < -thresh:
                    release_mouse()
                else:
                    if deadzone_action == 1:
                        hold_mouse()
                    else:
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
        self.hide_overlay()
        self.after(0, self.deiconify)  # show window safely
        self.set_status("Macro Status: Stopped")
if __name__ == "__main__":
    app = App()
    app.mainloop()