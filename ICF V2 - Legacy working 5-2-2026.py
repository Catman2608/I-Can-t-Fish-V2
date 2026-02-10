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
        self.vars = {}     # Entry / Slider / Combobox vars
        self.vars = {}        # IntVar / StringVar / BooleanVar
        self.checkboxes = {}   # CTkCheckBox vars
        self.comboboxes = {}   # CTkComboBox vars
        
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

        try:
            BASE_DIR = os.path.dirname(os.path.abspath(__file__))
            logo_image = CTkImage(
                light_image=Image.open(os.path.join(BASE_DIR, "icf_light.png")),
                dark_image=Image.open(os.path.join(BASE_DIR, "icf_dark.png")),
                size=(256, 54)
            )
            self.logo_image = logo_image

            logo_label = CTkLabel(self, image=self.logo_image, text="")
            logo_label.grid(row=0, column=0, columnspan=6, pady=10)
        except:
            logo_label = CTkLabel(self, text="[I CANT FISH V2] BY LONGEST")
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

        auto_zoom_var = StringVar(value="off")
        self.vars["auto_zoom_in"] = auto_zoom_var
        auto_zoom_cb = CTkCheckBox(automation, text="Auto Zoom In", 
                                  variable=auto_zoom_var, onvalue="on", offvalue="off")
        auto_zoom_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")

        fish_overlay_var = StringVar(value="off")
        self.vars["fish_overlay"] = fish_overlay_var
        fish_overlay_cb = CTkCheckBox(automation, text="Fish Overlay", 
                                     variable=fish_overlay_var, onvalue="on", offvalue="off")
        fish_overlay_cb.grid(row=2, column=0, padx=12, pady=8, sticky="w")
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
            command=lambda v: self.load_settings(v)
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

        CTkCheckBox(
            casting,
            text="Perfect Cast (slower)",
            variable=perfect_cast_var,
            onvalue="on",
            offvalue="off"
        ).grid(row=0, column=0, padx=12, pady=8, sticky="w")

        # ---- Cast duration ----
        CTkLabel(casting, text="Cast duration").grid(
            row=1, column=0, padx=12, pady=8, sticky="w"
        )

        cast_duration_var = StringVar(value="0.6")
        self.vars["cast_duration"] = cast_duration_var

        cast_duration_entry = CTkEntry(
            casting,
            width=120,
            textvariable=cast_duration_var
        )
        cast_duration_entry.grid(row=1, column=1, padx=12, pady=8, sticky="w")


        # ---- Delay after casting ----
        CTkLabel(casting, text="Delay after casting").grid(
            row=2, column=0, padx=12, pady=8, sticky="w"
        )

        casting_delay_var = StringVar(value="0.6")
        self.vars["casting_delay"] = casting_delay_var

        casting_delay_entry = CTkEntry(
            casting,
            width=120,
            textvariable=casting_delay_var
        )
        casting_delay_entry.grid(row=2, column=1, padx=12, pady=8, sticky="w")


        # ---- Perfect cast tolerance ----
        CTkLabel(casting, text="Perfect Cast Tolerance:").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        perfect_cast_tolerance_var = StringVar(value="5")
        self.vars["perfect_cast_tolerance"] = perfect_cast_tolerance_var

        perfect_cast_tolerance_entry = CTkEntry(
            casting,
            width=120,
            textvariable=perfect_cast_tolerance_var
        )
        perfect_cast_tolerance_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")

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
        # Capture Mode Settings 
        capture_settings = CTkFrame(
            parent, fg_color="#222222",
            border_color="#50e3c2", border_width=2
        )
        capture_settings.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(capture_settings, text="Capture Mode:").grid(
            row=0, column=0, padx=12, pady=6, sticky="w"
        )

        capture_var = StringVar(value="DXCAM")
        self.vars["capture_mode"] = capture_var
        capture_cb = CTkComboBox(
            capture_settings,
            values=["DXCAM", "MSS"],
            variable=capture_var,
            command=lambda v: self.set_status(f"Capture mode: {v}")
        )
        capture_cb.grid(row=0, column=1, padx=12, pady=6, sticky="w")
        self.comboboxes["capture_mode"] = capture_cb

        # Fish Overlay Settings 
        overlay_settings = CTkFrame(
            parent, fg_color="#222222",
            border_color="#50e3c2", border_width=2
        )
        overlay_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")

        bar_size_var = StringVar(value="off")
        self.vars["bar_size"] = bar_size_var
        bar_size_cb = CTkCheckBox(overlay_settings, text="Show Bar Size", 
                                     variable=bar_size_var, onvalue="on", offvalue="off")
        bar_size_cb.grid(row=0, column=0, padx=12, pady=8, sticky="w")

        bar_ratio2_var = StringVar(value="off")
        self.vars["bar_ratio2"] = bar_ratio2_var
        bar_ratio2_cb = CTkCheckBox(overlay_settings, text="Show Bar Ratio", 
                                     variable=bar_ratio2_var, onvalue="on", offvalue="off")
        bar_ratio2_cb.grid(row=1, column=0, padx=12, pady=8, sticky="w")

        # Perfect Cast Settings 
        pfc1_settings = CTkFrame(
            parent, fg_color="#222222",
            border_color="#50e3c2", border_width=2
        )
        pfc1_settings.grid(row=1, column=0, padx=20, pady=20, sticky="nw")
        
    # SHAKE SETTINGS TAB
    def build_shake_tab(self, parent):
        frame = CTkFrame(
            parent,
            fg_color="#222222",
            border_color="#bd10e0",
            border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        # ---- Shake mode ----
        CTkLabel(frame, text="Shake mode:").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )

        shake_mode_var = StringVar(value="Click")
        self.vars["shake_mode"] = shake_mode_var

        shake_cb = CTkComboBox(
            frame,
            values=["Click", "Navigation"],
            variable=shake_mode_var,
            command=lambda v: self.set_status(f"Shake mode: {v}")
        )
        shake_cb.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.comboboxes["shake_mode"] = shake_cb

        # ---- Shake tolerance ----
        CTkLabel(frame, text="Click Shake Color Tolerance:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        shake_tolerance_var = StringVar(value="5")
        self.vars["shake_tolerance"] = shake_tolerance_var

        CTkEntry(
            frame,
            width=120,
            textvariable=shake_tolerance_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")

        # ---- Shake scan delay ----
        CTkLabel(frame, text="Shake Scan Delay:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        shake_scan_delay_var = StringVar(value="0.01")
        self.vars["shake_scan_delay"] = shake_scan_delay_var

        CTkEntry(
            frame,
            width=120,
            textvariable=shake_scan_delay_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")

        # ---- Shake failsafe ----
        CTkLabel(frame, text="Shake Failsafe (attempts):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )

        shake_failsafe_var = StringVar(value="20")
        self.vars["shake_failsafe"] = shake_failsafe_var

        CTkEntry(
            frame,
            width=120,
            textvariable=shake_failsafe_var
        ).grid(row=3, column=1, padx=12, pady=10, sticky="w")

    # MINIGAME SETTINGS TAB
    def build_minigame_tab(self, parent):
        frame = CTkFrame(
            parent, fg_color="#222222",
            border_color="#7ed321", border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(frame, text="Left Bar Color (#RRGGBB):").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        left_color_var = StringVar(value="#F1F1F1")
        self.vars["left_color"] = left_color_var
        CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=left_color_var).grid(row=0, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(frame, text="Right Bar Color (#RRGGBB):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        right_color_var = StringVar(value="#FFFFFF")
        self.vars["right_color"] = right_color_var
        CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=right_color_var).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Arrow Color (#RRGGBB):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        arrow_color_var = StringVar(value="#848587")
        self.vars["arrow_color"] = arrow_color_var
        CTkEntry(frame, placeholder_text="#848587", width=120, textvariable=arrow_color_var).grid(row=2, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Fish Color (#RRGGBB):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        fish_color_var = StringVar(value="#434B5B")
        self.vars["fish_color"] = fish_color_var
        CTkEntry(frame, placeholder_text="#FFFFFF", width=120, textvariable=fish_color_var).grid(row=3, column=1, padx=12, pady=10, sticky="w")
        
        left_tolerance_var = StringVar(value="8")
        self.vars["left_tolerance"] = left_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=0, column=2, padx=12, pady=10, sticky="w"
        )
        left_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=left_tolerance_var)
        left_tolerance_entry.grid(row=0, column=3, padx=12, pady=10, sticky="w")
        
        right_tolerance_var = StringVar(value="8")
        self.vars["right_tolerance"] = right_tolerance_var
        CTkLabel(frame, text="Tolerance:").grid(
            row=1, column=2, padx=12, pady=10, sticky="w"
        )
        right_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=right_tolerance_var)
        right_tolerance_entry.grid(row=1, column=3, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=2, column=2, padx=12, pady=10, sticky="w"
        )

        arrow_tolerance_var = StringVar(value="8")
        self.vars["arrow_tolerance"] = arrow_tolerance_var
        arrow_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=120, textvariable=arrow_tolerance_var)
        arrow_tolerance_entry.grid(row=2, column=3, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=3, column=2, padx=12, pady=10, sticky="w"
        )

        fish_tolerance_var = StringVar(value="5")
        self.vars["fish_tolerance"] = fish_tolerance_var

        CTkEntry(
            frame,
            width=120,
            textvariable=fish_tolerance_var
        ).grid(row=3, column=3, padx=12, pady=10, sticky="w")
        
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

        bar_ratio_var = StringVar(value="0.5")
        self.vars["bar_ratio"] = bar_ratio_var

        CTkEntry(
            frame2,
            width=120,
            textvariable=bar_ratio_var
        ).grid(row=0, column=1, padx=12, pady=10, sticky="w")
        
        CTkLabel(frame2, text="Scan delay (seconds):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        minigame_scan_delay_var = StringVar(value="0.01")
        self.vars["minigame_scan_delay"] = minigame_scan_delay_var
        minigame_scan_delay_entry = CTkEntry(frame2, placeholder_text="0.01", width=120, textvariable=minigame_scan_delay_var)
        minigame_scan_delay_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")

        CTkLabel(frame2, text="Restart Delay:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        restart_delay_var = StringVar(value="1")
        self.vars["restart_delay"] = restart_delay_var

        CTkEntry(
            frame2,
            width=120,
            textvariable=restart_delay_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")

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

        p_gain_var = StringVar(value="0.01")
        self.vars["proportional_gain"] = p_gain_var

        CTkEntry(
            frame3,
            width=120,
            textvariable=p_gain_var
        ).grid(row=0, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(frame3, text="Derivative gain:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )

        d_gain_var = StringVar(value="0.01")
        self.vars["derivative_gain"] = d_gain_var

        CTkEntry(
            frame3,
            width=120,
            textvariable=d_gain_var
        ).grid(row=1, column=1, padx=12, pady=10, sticky="w")
        CTkLabel(frame3, text="Velocity Smoothing:").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )

        velocity_smoothing_var = StringVar(value="6")
        self.vars["velocity_smoothing"] = velocity_smoothing_var

        CTkEntry(
            frame3,
            width=120,
            textvariable=velocity_smoothing_var
        ).grid(row=2, column=1, padx=12, pady=10, sticky="w")

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
        self.vars["webhook_url"] = webhook_url_entry

        CTkLabel(webhook_combobox, text="User ID:").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        user_id_entry = CTkEntry(webhook_combobox, placeholder_text="[Copy your user ID and paste it here]", width=240)
        user_id_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.vars["user_id"] = user_id_entry
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
        
        # Write to file
        path = os.path.join(config_dir, name)
        try:
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            self.save_last_config_name(name)
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
        
        self.save_last_config_name(name)
        self.set_status(f"Loaded Config: {name}")
    def _get_screen_size(self):
        self.update_idletasks()  # ensure Tk is initialized
        width = self.winfo_screenwidth()
        height = self.winfo_screenheight()
        return width, height
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
    
    def _find_bar_edges(
        self,
        frame,
        left_hex,
        right_hex,
        tolerance=8,
        tolerance2=8,
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
            np.abs(line - right_bgr) <= tolerance2,
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
        Find max left and right of the bar
        bar_ratio: fraction from bar edge (0.0 - 0.5 recommended)
        """
        bar_width = right_bar_x - left_bar_x
        bar_ratio = max(0.05, min(0.45, bar_ratio))  # clamp for safety

        left_target = left_bar_x + bar_width * bar_ratio
        right_target = right_bar_x - bar_width * bar_ratio

        if fish_x < left_target:
            return left_target
        elif fish_x > right_target:
            return right_target
        else:
            return None  # inside safe zone

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
                self._execute_cast_perfect()
            else:
                self._execute_cast_normal()

            # Optional delay after cast
            try:
                delay = float(self.vars["casting_delay"].get() or 0.6)
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
        duration = float(self.vars["cast_duration"].get() or 0.6)
        time.sleep(duration)  # adjust cast strength
        mouse_controller.release(Button.left)
        time.sleep(0.2)

    def _execute_cast_perfect(self):
        # Hold mouse to start cast
        mouse_controller.press(Button.left)

        # Reset tracking buffers
        white_positions = []
        white_timestamps = []

        last_green_mid = None
        last_green_y = None

        start_time = time.time()

        while self.running:
            frame = self._capture_cast_region()

            # 1. Detect green bar
            green = self._find_green(frame, last_green_mid, last_green_y)
            if not green:
                continue

            green_mid_x, green_y, left_x, right_x = green
            last_green_mid = green_mid_x
            last_green_y = green_y

            # 2. Detect white indicator BELOW green
            white = find_white_below_green(
                frame,
                green_y,
                left_x,
                right_x,
                self.vars["white_tolerance"].get()
            )

            if white:
                white_positions.append(white)
                white_timestamps.append(time.time())

                if len(white_positions) > 5:
                    white_positions.pop(0)
                    white_timestamps.pop(0)

            # 3. Predict & release
            speed = calculate_speed_and_predict(white_positions, white_timestamps)

            if speed is not None:
                predicted_y = white[1] + speed * self.vars["perfect_cast_reaction_time"].get()

                if predicted_y >= green_y:
                    mouse_controller.release(Button.left)
                    return

            # Safety timeout
            if time.time() - start_time > 3.5:
                mouse_controller.release(Button.left)
                return

    def _execute_shake_click(self):
        self.set_status("Shake Mode: Click")

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

        # --- Regions ---
        # macOS-safe coordinates
        fish_left = int(self.SCREEN_WIDTH / 3.3684)
        fish_top = int(self.SCREEN_HEIGHT / 1.2766)
        fish_right = int(self.SCREEN_WIDTH / 1.42)
        fish_bottom = int(self.SCREEN_HEIGHT / 1.1335)

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
        # macOS-safe coordinates
        fish_left = int(self.SCREEN_WIDTH / 3.3684)
        fish_top = int(self.SCREEN_HEIGHT / 1.2766)
        fish_right = int(self.SCREEN_WIDTH / 1.42)
        fish_bottom = int(self.SCREEN_HEIGHT / 1.1335)

        fish_hex = self.vars["fish_color"].get()
        arrow_hex = self.vars["arrow_color"].get()
        left_bar_hex = self.vars["left_color"].get()
        right_bar_hex = self.vars["right_color"].get()

        left_tol = int(self.vars["left_tolerance"].get() or 8)
        right_tol = int(self.vars["right_tolerance"].get() or 8)
        arrow_tol = int(self.vars["arrow_tolerance"].get() or 8)
        fish_tol = int(self.vars["fish_tolerance"].get() or 5)
        bar_ratio = float(self.vars["bar_ratio"].get() or 0.5)

        try:
            thresh = float(self.vars["velocity_smoothing"].get() or 10)
        except:
            thresh = 10

        DEADZONE = 8
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

            fish_center = self._find_color_center(img, fish_hex, fish_tol)
            arrow_center = self._find_color_center(img, arrow_hex, arrow_tol)
            left_bar_center, right_bar_center = self._find_bar_edges(img, left_bar_hex, right_bar_hex, left_tol, right_tol)

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
                arrow_centroid_x = self._find_arrow_centroid(img, arrow_hex, arrow_tol)
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