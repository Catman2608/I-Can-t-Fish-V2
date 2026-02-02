# Initialization
from customtkinter import *
import os
import glob
# Keyboard and Mouse
from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController
# Key Listeners
import threading
from pynput.keyboard import Listener as KeyListener, Key
macro_running = False
macro_thread = None
# Key Inputs
import threading
# Time
import time
import json
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

        #  Window 
        self.geometry("800x550")
        self.title("I Can't Fish V2")

        # Macro state
        self.macro_running = False
        self.macro_thread = None

        # Start hotkey listener
        self.key_listener = KeyListener(on_press=self.on_key_press)
        self.key_listener.daemon = True
        self.key_listener.start()

        #  Status Bar 
        self.status_label = CTkLabel(self, text="Macro Status: Idle")
        self.status_label.grid(
            row=0, column=0, columnspan=6,
            pady=15, padx=20, sticky="w"
        )

        #  Tabs 
        self.tabs = CTkTabview(self)
        self.tabs.grid(
            row=1, column=0, columnspan=6,
            padx=20, pady=10, sticky="w"
        )

        self.tabs.add("General Settings")
        self.tabs.add("Shake Settings")
        self.tabs.add("Minigame Settings")

        # Build tabs
        self.build_general_tab(self.tabs.tab("General Settings"))
        self.build_shake_tab(self.tabs.tab("Shake Settings"))
        self.build_minigame_tab(self.tabs.tab("Minigame Settings"))

        self.grid_columnconfigure(0, weight=1)
        last = self.load_last_config_name()
        self.load_settings(last or "default.json")
    # GENERAL SETTINGS TAB
    def build_general_tab(self, parent):
        #  Automation 
        automation = CTkFrame(
            parent, fg_color="#222222",
            border_color="#ff0000", border_width=2
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
            border_color="#ff0000", border_width=2
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
            border_color="#ff0000", border_width=2
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
            border_color="#ff0000", border_width=2
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
    # SHAKE SETTINGS TAB
    def build_shake_tab(self, parent):
        frame = CTkFrame(
            parent, fg_color="#222222",
            border_color="#ff7a00", border_width=2
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
            border_color="#ffe200", border_width=2
        )
        frame.grid(row=0, column=0, padx=20, pady=20, sticky="nw")

        CTkLabel(frame, text="Left Bar Color (#RRGGBB):").grid(
            row=0, column=0, padx=12, pady=10, sticky="w"
        )
        left_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140)
        left_color_entry.grid(row=0, column=1, padx=12, pady=10, sticky="w")
        self.widgets["left_bar_color"] = left_color_entry
        
        CTkLabel(frame, text="Right Bar Color (#RRGGBB):").grid(
            row=1, column=0, padx=12, pady=10, sticky="w"
        )
        right_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140)
        right_color_entry.grid(row=1, column=1, padx=12, pady=10, sticky="w")
        self.widgets["right_bar_color"] = right_color_entry
        
        CTkLabel(frame, text="Arrow Color (#RRGGBB):").grid(
            row=2, column=0, padx=12, pady=10, sticky="w"
        )
        arrow_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140)
        arrow_color_entry.grid(row=2, column=1, padx=12, pady=10, sticky="w")
        self.widgets["arrow_color"] = arrow_color_entry
        
        CTkLabel(frame, text="Fish Color (#RRGGBB):").grid(
            row=3, column=0, padx=12, pady=10, sticky="w"
        )
        fish_color_entry = CTkEntry(frame, placeholder_text="#FFFFFF", width=140)
        fish_color_entry.grid(row=3, column=1, padx=12, pady=10, sticky="w")
        self.widgets["fish_color"] = fish_color_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=0, column=2, padx=12, pady=10, sticky="w"
        )
        left_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=140)
        left_tolerance_entry.grid(row=0, column=3, padx=12, pady=10, sticky="w")
        self.widgets["left_tolerance"] = left_tolerance_entry
        
        CTkLabel(frame, text="Tolerance:").grid(
            row=1, column=2, padx=12, pady=10, sticky="w"
        )
        right_tolerance_entry = CTkEntry(frame, placeholder_text="8", width=140)
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
        fish_tolerance_entry = CTkEntry(frame, placeholder_text="0", width=140)
        fish_tolerance_entry.grid(row=3, column=3, padx=12, pady=10, sticky="w")
        self.widgets["fish_tolerance"] = fish_tolerance_entry
        
        frame2 = CTkFrame(
            parent,
            fg_color="#222222",
            border_color="#ffe200",
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
        scan_delay_entry = CTkEntry(frame2, placeholder_text="0.01", width=140)
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
                self.macro_running = True
                threading.Thread(target=self.start_macro, daemon=True).start()

            elif key == Key.f7:
                self.stop_macro()

        except Exception as e:
            print("Hotkey error:", e)
    def set_status(self, text, key):
        self.status_label.configure(text=text)
        start_key = key
    def start_macro(self):
        print("Macro started")
        while self.macro_running:
            # macro logic only
            time.sleep(0.01)
    def stop_macro(self):
        if not self.macro_running:
            return
        self.after(0, self.deiconify)
        print("Macro stopped")
if __name__ == "__main__":
    app = App()
    app.mainloop()