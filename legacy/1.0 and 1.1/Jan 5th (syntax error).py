# Initialization
## Tkinter GUI
from tkinter import *
from tkinter import ttk
from tkinter import StringVar
import os
import threading
## macOS check
import platform
system = platform.system()
## Keyboard, mouse clicks and pixel search
### pip install pynput
### pip install pillow
from pynput.keyboard import Listener as KeyListener, Key, KeyCode, Controller as KeyboardController
from pynput.mouse import Controller as MouseController, Button as MouseButton
# Delay
import time
## macOS Pixel Search
import subprocess
import mss
import mss.tools
from PIL import Image
mouse_down = False
## Save and Load Configs
import json
global shake_click_pos
shake_click_pos = None
prev_error = 0.0
last_time = None
# PID smoothing state
pid_integral = 0.0
prev_derivative = 0.0
## Focus on Roblox (Windows)
if platform.system() == "Windows":
    import ctypes
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)

# tkinter window
window = Tk()
# Screen width and height
SCREEN_WIDTH = window.winfo_screenwidth()
SCREEN_HEIGHT = window.winfo_screenheight()
config_var = StringVar()
config_var.set("Click")  # temporary default
style = ttk.Style()
minigame_canvas = None
minigame_window = None
restart_pending = False
# macOS mouse and keyboard
keyboard = KeyboardController()
mouse = MouseController()

try:
    style.theme_use("clam")
except:
    pass

# Configure TTK Style for macOS compatibility
style.configure("Dark.TCheckbutton",
                background="#1d1d1d",
                foreground="white",
                fieldbackground="#1d1d1d")

style.map("Dark.TCheckbutton",
          background=[("active", "#3a3a3a")],
          foreground=[("active", "white")])

style.configure("Dark.TLabel",
                background="#1d1d1d",
                foreground="white")

# Configure TTK Dark Mode
style.configure("DarkCheck.TCheckbutton",
                background="#1d1d1d",
                foreground="white",
                fieldbackground="#1d1d1d")

style.map("DarkCheck.TCheckbutton",
          background=[("active", "#3a3a3a")],
          foreground=[("active", "white")])

# Global variables
debug_window = None

config_var = StringVar(master=window)
config_var.set("Select Rod")

# === Helper Functions and Classes ===
def get_macos_font(font):
    """
    Boost font size on macOS to match ttk scaling
    """
    if platform.system() == "Darwin":
        family, size, *rest = font
        return (family, int(size * 1.5), *rest)
    return font

def create_label(
    parent, text, row, column,
    fg="white", bg="#1d1d1d",
    font=("Segoe UI", 9),
    sticky="w", pady=5, padx=0
):
    system = platform.system()
    use_font = get_macos_font(font)

    lbl = Label(
        parent,
        text=text,
        fg=fg,
        bg=bg,
        font=use_font
    )

    lbl.grid(row=row, column=column, sticky=sticky, pady=pady, padx=padx)
    return lbl

def ToolTip(text="", row=4):
    if not overlay:
        return

    if row == 4:
        overlay.set_status(text)
    else:
        overlay.set_debug(text)

def create_entry(parent, row, column, width=12, sticky="w", padx=10, pady=5):
    """Create an entry field"""
    entry = Entry(parent, width=width)
    entry.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
    return entry

def create_group(parent, text, row, columnspan=2, fg="#00ff00", padx=15, pady=15):
    """Create a labeled group frame"""
    system = platform.system()
    group = LabelFrame(
        parent,
        text=f" {text} ",
        font=("Segoe UI", 9, "bold"),
        bg="#1d1d1d",
        fg=fg,
        borderwidth=2,
        relief="groove",
        labelanchor="nw",
        padx=20,
        pady=20
    )
    group.grid(column=0, row=row, columnspan=columnspan, padx=padx, pady=pady, sticky="we")
    return group

def create_checkboxes(parent, options, style_name="DarkCheck.TCheckbutton"):
    """Create multiple checkboxes from a list"""
    checkbox_vars = {}
    for i, (label, var_name) in enumerate(options):
        checkbox_vars[var_name] = BooleanVar()
        ttk.Checkbutton(
            parent,
            text=label,
            variable=checkbox_vars[var_name],
            style=style_name
        ).grid(row=i, column=0, sticky="w", pady=5)
    return checkbox_vars

def create_slider(parent, row, column, from_val, to_val, resolution=0.2, length=80):
    """Create a slider with consistent styling"""
    slider = Scale(
        parent,
        from_=from_val,
        to=to_val,
        orient=HORIZONTAL,
        resolution=resolution,
        fg="white",
        bg="#1d1d1d",
        troughcolor="#444444",
        highlightthickness=0,
        length=length
    )
    slider.grid(row=row, column=column, sticky="w", padx=10)
    return slider

# === Dark mode for ttk Notebook ===
style.configure("TNotebook",
                background="#1d1d1d",
                borderwidth=0)

style.configure("TNotebook.Tab",
                background="#1d1d1d",
                foreground="white",
                padding=[10, 5],
                font=("Segoe UI", 9))

style.map("TNotebook.Tab",
          background=[("selected", "#1d1d1d"),
                      ("active", "#3a3a3a")],
          foreground=[("selected", "white"),
                      ("active", "white")])

# === Custom blocks ===
def show_minigame_window():
    global minigame_window, minigame_canvas

    if minigame_window and minigame_window.winfo_exists():
        minigame_window.deiconify()
        minigame_window.lift()
        return

    minigame_window = Toplevel(window)
    minigame_window.geometry("800x50+560+660")
    minigame_window.overrideredirect(True)
    minigame_window.attributes("-topmost", True)

    minigame_canvas = Canvas(
        minigame_window,
        width=800,
        height=60,
        bg="#1d1d1d",
        highlightthickness=0
    )
    minigame_canvas.pack(fill="both", expand=True)


def hide_minigame_window():
    global minigame_window
    if minigame_window and minigame_window.winfo_exists():
        minigame_window.withdraw()

def draw_box(x1, y1, x2, y2, fill, outline):
    if not minigame_canvas or not minigame_canvas.winfo_exists():
        return

    def _draw():
        minigame_canvas.create_rectangle(
            x1, y1, x2, y2,
            outline=outline,
            width=2,
            fill=fill
        )

    minigame_canvas.after(0, _draw)

def clear_minigame():
    if not minigame_canvas or not minigame_canvas.winfo_exists():
        return

    minigame_canvas.after(0, lambda: minigame_canvas.delete("all"))

# Create the entry widgets that are referenced in save_settings and load_settings
CONFIG_DIR = "configs"
if not os.path.exists(CONFIG_DIR):
    os.makedirs(CONFIG_DIR)
# Timing entries
restart_delay_entry = None
def json_save(data, key, var_name):
    entry = globals().get(var_name)
    if entry is not None:
        data[key] = entry.get()
def json_save_slider(data, key, var_name):
    scale = globals().get(var_name)
    if scale is not None:
        data[key] = scale.get()

def json_load_entry(data, key, var_name, default=""):
    entry = globals().get(var_name)
    if entry is not None:
        entry.delete(0, END)
        entry.insert(0, data.get(key, default))
def json_load_var(data, key, var_name):
    var = globals().get(var_name)
    if var is not None:
        var.set(data.get(key, var.get()))
def json_load_slider(data, key, var_name):
    scale = globals().get(var_name)
    if scale is not None:
        scale.set(data.get(key, scale.get()))
class Overlay:
    def __init__(self, parent):
        self.parent = parent
        self.win = None
        self.labels = {}

    def show(self):
        if self.win and self.win.winfo_exists():
            self.win.destroy()

        self.win = Toplevel(self.parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.config(bg="black")

        if platform.system() == "Windows":
            self.win.attributes("-disabled", True)
        elif platform.system() == "Darwin":
            self.win.attributes("-transparent", True)

        # Bottom-left corner
        screen_h = self.win.winfo_screenheight()
        self.win.geometry(f"240x140+20+{screen_h - 160}")

        self._build_labels()

    def _build_labels(self):
        Label(
            self.win,
            text="Fisch Macro V14",
            fg="#00c8ff",
            bg="black",
            font=("Segoe UI", 12, "bold")
        ).pack(pady=(8, 4))

        Label(
            self.win,
            text="F5: Start | F6: Restart | F7: Stop",
            fg="white",
            bg="black",
            font=("Segoe UI", 9)
        ).pack()

        self.labels["status"] = Label(
            self.win,
            text="",
            fg="white",
            bg="black",
            font=("Segoe UI", 10)
        )
        self.labels["status"].pack(pady=(6, 0))

        self.labels["debug"] = Label(
            self.win,
            text="",
            fg="white",
            bg="black",
            font=("Segoe UI", 9)
        )
        self.labels["debug"].pack()

    def set_status(self, text):
        if self.win and self.win.winfo_exists():
            self.labels["status"].config(text=text)

    def set_debug(self, text):
        if self.win and self.win.winfo_exists():
            self.labels["debug"].config(text=text)

    def destroy(self):
        if self.win and self.win.winfo_exists():
            self.win.destroy()

overlay = Overlay(window)
overlay.show()

class TkinterGUI:
    def __init__(self, root):
        self.root = root

        # Window
        self.root.title("Fisch V14")
        self.root.geometry("800x550")
        self.root.config(bg="#1d1d1d")

        # Notebook
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(expand=True, fill="both")

        self.tab1 = Frame(self.notebook, bg="#1d1d1d")
        self.tab2 = Frame(self.notebook, bg="#1d1d1d")
        self.tab3 = Frame(self.notebook, bg="#1d1d1d")

        self.notebook.add(self.tab1, text="General Settings")
        self.notebook.add(self.tab2, text="Shake Settings")
        self.notebook.add(self.tab3, text="Minigame Settings")

        self._build_general_tab()
        self._build_shake_tab()
        self._build_minigame_tab()
        self._build_bottom_bar()

    # ======================================================
    # GENERAL TAB
    # ======================================================
    def _build_general_tab(self):
        create_label(self.tab1, "General Settings", 0, 0,
                     fg="#00ff00", font=("Segoe UI", 9, "bold"), pady=(10, 5))

        # Automation Options
        self.checkbox_group = create_group(self.tab1, "Automation Options", 1)

        checkbox_options = [
            ("Auto Select Rod", "auto_select_rod_var"),
            ("Auto Zoom In", "auto_zoom_var"),
            ("Fish Overlay", "fish_overlay_var"),
        ]

        self.checkbox_vars = create_checkboxes(self.checkbox_group, checkbox_options)

        # Timing Options
        timing_group = create_group(self.tab1, "Timing Options", 2)

        create_label(timing_group, "Wait For Bobber to Land (seconds):", 1, 0)
        self.bobber_delay_entry = create_entry(timing_group, 1, 1)

        create_label(timing_group, "Bait Delay (seconds):", 2, 0)
        self.bait_delay_entry = create_entry(timing_group, 2, 1)

        create_label(timing_group, "Restart Delay (seconds):", 3, 0)
        self.restart_delay_entry = create_entry(timing_group, 3, 1)

        # Casting Options
        casting_group = create_group(self.tab1, "Casting Options", 3)
        create_label(casting_group, "Hold Rod Cast Duration (seconds):", 0, 0)
        self.cast_duration_slider = create_slider(
            casting_group, 0, 1, 0.2, 2, 0.1
        )

    # ======================================================
    # SHAKE TAB
    # ======================================================
    def _build_shake_tab(self):
        create_label(self.tab2, "Shake Settings", 0, 0,
                     fg="#87CEEB", font=("Segoe UI", 9, "bold"), pady=10)

        shake_group = create_group(self.tab2, "Shake Configuration", 1, fg="#87CEEB")
        shake_group.grid(sticky="nsew")

        create_label(shake_group, "UI Navigation Key:", 1, 0)
        self.shake_ui_entry = create_entry(shake_group, 1, 1)

        create_label(shake_group, "Shake Mode:", 2, 0)
        self.shake_mode_var = StringVar(value="Click")

        self.shake_mode_dropdown = ttk.Combobox(
            shake_group,
            textvariable=self.shake_mode_var,
            values=["Click", "Navigation", "Wait"],
            state="readonly",
            width=15
        )
        self.shake_mode_dropdown.grid(row=2, column=1, sticky="w", padx=10, pady=5)

        create_label(shake_group, "Click Shake Color Tolerance:", 3, 0)
        self.shake_color_entry = create_entry(shake_group, 3, 1)

        create_label(shake_group, "Scan Delay (seconds):", 4, 0)
        self.shake_scan_entry = create_entry(shake_group, 4, 1)

        create_label(shake_group, "Click Delay (seconds):", 5, 0)
        self.shake_spam_entry = create_entry(shake_group, 5, 1)

        create_label(shake_group, "Wait Until Clicking (seconds):", 6, 0)
        self.shake_wait_entry = create_entry(shake_group, 6, 1)

    # ======================================================
    # MINIGAME TAB
    # ======================================================
    def _build_minigame_tab(self):
        create_label(self.tab3, "Minigame Settings", 0, 0,
                     fg="#e87b07", font=("Segoe UI", 9, "bold"), pady=10)

        fish_group = create_group(self.tab3, "Bar Colors (BBB-GGG-RRR)", 1, fg="#e87b07")

        create_label(fish_group, "Bar Color Left:", 0, 0)
        self.bar_color_entry = create_entry(fish_group, 0, 1)

        create_label(fish_group, "Bar Color Right:", 1, 0)
        self.rightbar_color_entry = create_entry(fish_group, 1, 1)

        create_label(fish_group, "Arrow Color:", 2, 0)
        self.arrow_color_entry = create_entry(fish_group, 2, 1)

        create_label(fish_group, "Fish Color:", 3, 0)
        self.fish_color_entry = create_entry(fish_group, 3, 1)

        deadzone_group = create_group(self.tab3, "Deadzone Settings", 2, fg="#e87b07")

        create_label(deadzone_group, "Left Right Deadzone Area:", 0, 0)
        self.left_right_deadzone_entry = create_entry(deadzone_group, 0, 1)

        create_label(deadzone_group, "Center Deadzone Area:", 1, 0)
        self.center_deadzone_entry = create_entry(deadzone_group, 1, 1)

        stability_group = create_group(self.tab3, "Stability Profiles", 3, fg="#e87b07")

        create_label(stability_group, "Proportional Gain:", 0, 0)
        self.p_gain_entry = create_entry(stability_group, 0, 1)

        create_label(stability_group, "Derivative Gain:", 1, 0)
        self.d_gain_entry = create_entry(stability_group, 1, 1)

        create_label(stability_group, "Velocity Smoothing:", 2, 0)
        self.velocity_smoothing_entry = create_entry(stability_group, 2, 1)

    # ======================================================
    # BOTTOM BAR
    # ======================================================
    def _build_bottom_bar(self):
        bottom = Frame(self.root, bg="#1d1d1d")
        bottom.pack(fill="x", pady=10)

        ttk.Label(bottom, text="Config:",
                  background="#1d1d1d", foreground="white").grid(row=0, column=0)

        self.config_var = StringVar(value="Select Rod")
        self.config_dropdown = ttk.Combobox(
            bottom, textvariable=self.config_var,
            state="readonly", width=20
        )
        self.config_dropdown.grid(row=0, column=1, padx=10)

        self.start_btn = Button(bottom, text="Start", width=12)
        self.start_btn.grid(row=0, column=2, padx=5)

        self.stop_btn = Button(bottom, text="Stop", width=12)
        self.stop_btn.grid(row=0, column=3, padx=5)

class MacroState:
    def __init__(self):
        # Core control
        self.running = False
        self.tooltip_labels = False

        # Toggles
        self.cast_duration_slider = False
        self.shake_click_pos = False

        # PID / logic values
        self.p_gain = 0.5
        self.d_gain = 0.1
        self.velocity_smoothing = 6

        # Colors (R, G, B)
        self.bar_color = (255, 255, 255)
        self.fish_color = (255, 100, 100)

        # Timing
        self.cast_delay = 0.25
        self.shake_delay = 0.05
        
        # Add missing attributes that are referenced elsewhere
        self.restart_pending = False
        self.prev_error = 0.0
        self.last_time = None
        self.pid_integral = 0.0
        self.prev_derivative = 0.0
        self.mouse_down = False

macro_state = MacroState()

def save_settings(name, gui):
    data = {
        "proportional_gain": gui.p_gain_entry.get(),
        "derivative_gain": gui.d_gain_entry.get(),
        "velocity_smoothing": gui.velocity_smoothing_entry.get(),
        "shake_mode": gui.shake_mode_var.get(),
    }

    for key, var in gui.checkbox_vars.items():
        data[key] = bool(var.get())

    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    # Save settings from other fields if they exist
    try:
        # Timing options
        json_save(data, "restart_delay", "restart_delay_entry")
        json_save(data, "bait_delay", "bait_delay_entry")
        json_save(data, "bobber_delay", "bobber_delay_entry")
        json_save_slider(data, "cast_duration", "cast_duration_slider")

        # Shake config
        json_save(data, "shake_mode", "shake_mode_var")
        json_save(data, "shake_ui_key", "shake_ui_entry")
        json_save(data, "shake_color_tolerance", "shake_color_entry")
        json_save(data, "shake_scan_delay", "shake_scan_entry")
        json_save(data, "shake_click_delay", "shake_click_entry")
        json_save(data, "shake_wait_until_click", "shake_wait_entry")

        # Bar color & deadzone
        json_save(data, "bar_color", "bar_color_entry")
        json_save(data, "rightbar_color", "rightbar_color_entry")
        json_save(data, "arrow_color", "arrow_color_entry")
        json_save(data, "fish_color", "fish_color_entry")
        json_save(data, "left_right_deadzone", "left_right_deadzone_entry")
        json_save(data, "velocity_smoothing", "velocity_smoothing_entry")
    except Exception:
        pass

    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    gui.status_label.config(text= f"Saved config: {name}")
    
def load_settings(name, gui):
    path = os.path.join(CONFIG_DIR, f"{name}.json")
    if not os.path.exists(path):
        gui.status_label.config(text="Config not found")
        return

    with open(path, "r") as f:
        data = json.load(f)

    # tk variables
    json_load_var(data, "shake_mode", "shake_mode_var")
    # Timing settings
    json_load_entry(data, "restart_delay", "restart_delay_entry")
    json_load_entry(data, "bait_delay", "bait_delay_entry")
    json_load_entry(data, "bobber_delay", "bobber_delay_entry")
    json_load_slider(data, "cast_duration", "cast_duration_slider")
    # Shake settings
    json_load_entry(data, "shake_ui_key", "shake_ui_entry")
    json_load_entry(data, "shake_color_tolerance", "shake_color_entry")
    json_load_entry(data, "shake_scan_delay", "shake_scan_entry")
    json_load_entry(data, "shake_click_delay", "shake_click_entry")
    json_load_entry(data, "shake_wait_until_click", "shake_wait_entry")
    # Minigame timing
    json_load_entry(data, "bar_color", "bar_color_entry")
    json_load_entry(data, "rightbar_color", "rightbar_color_entry")
    json_load_entry(data, "arrow_color", "arrow_color_entry")
    json_load_entry(data, "fish_color", "fish_color_entry")
    json_load_entry(data, "left_right_deadzone", "left_right_deadzone_entry")
    json_load_entry(data, "velocity_smoothing", "velocity_smoothing_entry")
    gui.status_label.config(text= f"Loaded Config: {name}")

def get_pid_gains():
    try:
        kp = float(gui.p_gain_entry.get())
    except:
        kp = 0.6

    try:
        kd = float(gui.d_gain_entry.get())
    except:
        kd = 0.2

    # Small integral term to reduce steady-state error (tunable constant)
    ki = 0.02

    return kp, kd, ki

def pid_control(error):
    """PID control function using macro_state"""
    now = time.perf_counter()
    if macro_state.last_time is None:
        macro_state.last_time = now
        macro_state.prev_error = error
        return 0.0

    dt = now - macro_state.last_time
    if dt <= 0:
        return 0.0

    kp, kd, ki = get_pid_gains()

    # Integral
    macro_state.pid_integral += error * dt
    macro_state.pid_integral = max(-100, min(100, macro_state.pid_integral))  # anti-windup clamp

    # Derivative
    derivative = (error - macro_state.prev_error) / dt

    output = (
        kp * error +
        ki * macro_state.pid_integral +
        kd * derivative
    )

    macro_state.prev_error = error
    macro_state.last_time = now

    return output

def get_entry_float(entry, default=0.1):
    """Safely parse a Tkinter Entry's value to float with a fallback."""
    try:
        return float(entry.get())
    except Exception:
        try:
            return float(default)
        except Exception:
            return 0.1

def start_clicked(event=None):
    window.withdraw()      # hide main GUI
    overlay.show()  # show small startup overlay

def stop_clicked(event=None):
    """Stop the macro and clean up"""
    global overlay, restart_pending, minigame_window
    
    macro_state.prev_error = 0.0
    macro_state.last_time = None
    macro_state.running = True
    macro_state.restart_pending = False
    macro_state.shake_click_pos = None

    # Remove overlay if it exists
    if overlay and overlay.winfo_exists():
        overlay.destroy()

    # Hide minigame window
    hide_minigame_window()

    # Check if main window is visible
    if window.winfo_viewable():
        # Main window is already shown → close macro/app
        window.destroy()   # exit application
        return
    else:
        # Main window is hidden → bring it back
        window.deiconify()
        window.lift()
        window.focus_force()

def load_rod_configs():
    config_dir = "configs"

    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    rods = []
    for file in os.listdir(config_dir):
        if file.lower().endswith(".json"):
            rods.append(os.path.splitext(file)[0])

    return rods if rods else ["No configs"]

def on_rod_selected(event):
    load_settings(config_var.get())

def pixel_search(start_x, start_y, end_x, end_y, target_rgb, tolerance):
    if system == "Windows":
        # Windows: Use ImageGrab
        screenshot = ImageGrab.grab(bbox=(start_x, start_y, end_x, end_y))
    else:
        # macOS/Linux: Use mss
        with mss.mss() as sct:
            monitor = {
                "top": start_y,
                "left": start_x,
                "width": end_x - start_x,
                "height": end_y - start_y
            }
            screenshot = sct.grab(monitor)
            screenshot = Image.frombytes("RGB", screenshot.size, screenshot.rgb)
    
    width, height = screenshot.size

    for y in range(height):
        for x in range(width):
            r, g, b = screenshot.getpixel((x, y))
            if abs(r - target_rgb[0]) <= tolerance and \
               abs(g - target_rgb[1]) <= tolerance and \
               abs(b - target_rgb[2]) <= tolerance:
                return (start_x + x, start_y + y)
    return None

def pixel_search_image(img, start_x, start_y, target_rgb, tolerance, step=3):
    px = img.load()
    w, h = img.size

    tr, tg, tb = target_rgb

    for y in range(0, h, step):
        for x in range(0, w, step):
            r, g, b = px[x, y]
            if (
                abs(r - tr) <= tolerance and
                abs(g - tg) <= tolerance and
                abs(b - tb) <= tolerance
            ):
                return (start_x + x, start_y + y)

    return None

def get_bar_edges_image(img, start_x, start_y, bar_b=255, bar_g=255, bar_r=255, rightbar_b=255, rightbar_g=255, rightbar_r=255):
    px = img.load()
    w, h = img.size
    y = int(h * 0.55)  # slightly below center (more reliable)
    bar_b_tolerance = bar_b - 15
    bar_g_tolerance = bar_g - 15
    bar_r_tolerance = bar_r - 15
    rightbar_b_tolerance = bar_b - 15
    rightbar_g_tolerance = bar_g - 15
    rightbar_r_tolerance = bar_r - 15
    left_edge = None
    right_edge = None

    for x in range(w):
        r, g, b = px[x, y]
        if r > bar_r_tolerance and g > bar_g_tolerance and b > bar_b_tolerance:
            left_edge = start_x + x
            break

    for x in range(w - 1, -1, -1):
        r, g, b = px[x, y]
        if r > rightbar_r_tolerance and g > rightbar_g_tolerance and b > rightbar_b_tolerance:
            right_edge = start_x + x
            break

    return left_edge, right_edge

def parse_rgb(color_str):
    """
    Accepts:
    - 'BBB-GGG-RRR'
    - 'BBBGGGRRR'
    - '#RRGGBB'

    Returns:
    (R, G, B)
    """
    try:
        s = color_str.strip()

        # --- HEX FORMAT: #RRGGBB ---
        if s.startswith("#") and len(s) == 7:
            r = int(s[1:3], 16)
            g = int(s[3:5], 16)
            b = int(s[5:7], 16)
            return (r, g, b)

        # --- DECIMAL FORMAT: BBB-GGG-RRR or BBBGGGRRR ---
        s = s.replace("-", "")
        if len(s) != 9 or not s.isdigit():
            raise ValueError

        b = int(s[0:3])
        g = int(s[3:6])
        r = int(s[6:9])

        return (r, g, b)

    except Exception:
        # Safe fallback (white)
        return (255, 255, 255)

def capture_region(start_x, start_y, end_x, end_y):
    if system == "Windows":
        return ImageGrab.grab(bbox=(start_x, start_y, end_x, end_y))
    else:
        with mss.mss() as sct:
            monitor = {
                "top": start_y,
                "left": start_x,
                "width": end_x - start_x,
                "height": end_y - start_y
            }
            img = sct.grab(monitor)
            return Image.frombytes("RGB", img.size, img.rgb)

def force_game_focus():
    if system == "Windows":
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        user32.SwitchToThisWindow(hwnd, True)
        time.sleep(0.05)

    elif system == "Darwin":
        # Simulate Cmd+Tab to switch back to previous app (Roblox)
        keyboard.press(Key.cmd)
        keyboard.press(Key.tab)
        time.sleep(0.05)
        keyboard.release(Key.tab)
        keyboard.release(Key.cmd)

    time.sleep(0.1)

def restart_macro():
    """Restart the macro"""
    macro_state.running = True
    macro_state.shake_click_pos = None
    set_mouse(False)
    window.after(0, show_minigame_window)
    window.after(150, lambda: threading.Thread(
        target=macro_loop,
        daemon=True
    ).start())

# Prevent click clicks and stuck mouse
def set_mouse(state: bool):
    """Set mouse press state"""
    if state and not macro_state.mouse_down:
        mouse.press(MouseButton.left)
        macro_state.mouse_down = True
    elif not state and macro_state.mouse_down:
        mouse.release(MouseButton.left)
        macro_state.mouse_down = False

# Run macro
def macro_loop(event=None):
    # Screen resolution (most important)
    shake_area_left = SCREEN_WIDTH / 4
    shake_area_top = SCREEN_HEIGHT / 8
    shake_area_right = SCREEN_WIDTH / 1.2736
    shake_area_bottom = SCREEN_HEIGHT / 1.3409
    FishBarLeft = SCREEN_WIDTH/3.3160
    FishBarRight = SCREEN_WIDTH/1.4317
    FishBarTop = SCREEN_HEIGHT/1.2
    FishBarBottom = SCREEN_HEIGHT/1.1512
    
    # Use macro_state instead of global variables
    cast_duration = gui.cast_duration_slider.get()
    bar_entry = bar_color_entry.get()
    bait_delay_b = get_entry_float(gui.bait_delay_entry, 0.5)
    click_delay = get_entry_float(gui.shake_click_entry, 0.05)
    bobber_delay = get_entry_float(gui.bobber_delay_entry, 0.05)
    restart_delay = get_entry_float(restart_delay_entry, 0.05)
    velocity_smoothing_left = get_entry_float(gui.velocity_smoothing_entry, 0.1)
    velocity_smoothing_right = velocity_smoothing_left / 2
    bait_delay = bait_delay_b / 10 # For 10 detection loops across the original bait delay
    left_right_deadzone = get_entry_float(left_right_deadzone_entry, 0.5)
    bar_rgb = parse_rgb(bar_color_entry.get())
    rightbar_rgb = parse_rgb(gui.rightbar_color_entry.get())
    arrow_rgb = parse_rgb(arrow_color_entry.get())
    arrow_a = arrow_rgb[0]
    arrow_b = arrow_rgb[1]
    arrow_c = arrow_rgb[2]
    arrow_b = int(arrow_a + arrow_b + arrow_c)
    arrow_d = arrow_rgb[3]
    arrow_e = arrow_rgb[4]
    arrow_f = arrow_rgb[5]
    arrow_g = int(arrow_d + arrow_e + arrow_f)
    arrow_h = arrow_rgb[6]
    arrow_i = arrow_rgb[7]
    arrow_j = arrow_rgb[8]
    arrow_r = int(arrow_h + arrow_i + arrow_j)
    fish_rgb = parse_rgb(fish_color_entry.get())
    fish_a = fish_rgb[0]
    fish_b = fish_rgb[1]
    fish_c = fish_rgb[2]
    fish_b = int(fish_a + fish_b + fish_c)
    fish_d = fish_rgb[3]
    fish_e = fish_rgb[4]
    fish_f = fish_rgb[5]
    fish_g = int(fish_d + fish_e + fish_f)
    fish_h = fish_rgb[6]
    fish_i = fish_rgb[7]
    fish_j = fish_rgb[8]
    fish_r = int(fish_h + fish_i + fish_j)
    
    ToolTip("Macro started", 4)
    
    try:
        macro_state.running = True  # Use macro_state
        fish_miss_count = 0
        MAX_FISH_MISSES = 15

        # Show minigame window
        show_minigame_window()
        CANVAS_X_OFFSET = 570
        CANVAS_Y_OFFSET = 860

        # --- Pre actions ---
        mouse.position = (300, 150)
        if gui.checkbox_vars["auto_zoom_var"].get():
            ToolTip("Current Task: Zoom In", 5)
            for _ in range(20):
                mouse.scroll(0, 1)
                time.sleep(0.05)
            mouse.scroll(0, -1)
        time.sleep(0.1)
        if gui.checkbox_vars["auto_select_rod_var"].get():
            ToolTip("Current Task: Press 2 and 1", 5)
            # Press "2" then "1"
            keyboard.press("2")
            time.sleep(0.05)
            keyboard.release("2")
            time.sleep(0.1)
            keyboard.press("1")
            time.sleep(0.05)
            keyboard.release("1")
            time.sleep(0.2)
        ToolTip(f"Casting rod for {cast_duration} seconds", 4)
        mouse.press(MouseButton.left)
        time.sleep(cast_duration)
        mouse.release(MouseButton.left)
        time.sleep(bobber_delay)
        ToolTip("Shaking", 4)
        img = capture_region(FishBarLeft, FishBarTop, FishBarRight, FishBarBottom)
        # --- Fish detection ---
        fish_detected = False
        attempts = 0
        shake_no_white_counter = 0
        SHAKE_NO_WHITE_TIMEOUT = 2.0  # seconds
        shake_last_white_time = time.time()
        
        while macro_state.running and not fish_detected and attempts < 400:
            force_game_focus()

            scan_delay = get_entry_float(gui.shake_scan_entry, 0.05)

            if gui.shake_mode_var.get() == 'Click':
                # Search for white pixel in the specified area
                found = pixel_search(shake_area_left, shake_area_top, shake_area_right, shake_area_bottom, (255, 255, 255), 6)
                
                if found:
                    # Reset the no-white timer since we found white
                    shake_last_white_time = time.time()
                    
                    # Move mouse to the white pixel and click it
                    mouse.position = found
                    mouse.press(MouseButton.left)
                    time.sleep(click_delay)
                    mouse.release(MouseButton.left)
                    
                    # Store for potential reuse (optional)
                    if shake_click_pos is None:
                        shake_click_pos = found
                else:
                    # No white pixel found - check if timeout reached
                    current_time = time.time()
                    time_since_last_white = current_time - shake_last_white_time
                    
                    if time_since_last_white >= SHAKE_NO_WHITE_TIMEOUT:
                        ToolTip("Shake Timer Reached (2 seconds). Restarting...", 4)
                        set_mouse(False)
                        time.sleep(0.5)
                        restart_macro()
                        return
            elif gui.shake_mode_var.get() == 'Navigation':
                keyboard.press(Key.enter)
                time.sleep(click_delay)
                keyboard.release(Key.enter)

            time.sleep(scan_delay)

            # Fish detect (stable check)
            stable = 0
            while stable < 8:
                if pixel_search(FishBarLeft, FishBarTop, FishBarBottom, FishBarRight, (fish_b, fish_g, fish_r), 5):
                    stable += 1
                    time.sleep(0.005)
                else:
                    break

            if stable >= 8:
                fish_detected = True
                mouse.press(MouseButton.left)
                time.sleep(0.003)
                mouse.release(MouseButton.left)
                break

            attempts += 1
            ToolTip(f"Shakes: {attempts}", 5)

        if not fish_detected:
            macro_state.running
            window.after(0, hide_minigame_window)
            return

        max_left = 0
        max_right = 0
        # --- Fishing bar loop ---
        while macro_state.running:
            ToolTip("Playing Bar Minigame", 4)
            clear_minigame()
            img = capture_region(FishBarLeft, FishBarTop, FishBarRight, FishBarBottom)
            fish_pos = pixel_search_image(img, FishBarLeft, FishBarTop, (fish_b, fish_g, fish_r), 5)
            if fish_pos is None:
                fish_miss_count += 1

                # release mouse briefly to avoid stuck input
                set_mouse(False)

                if fish_miss_count >= MAX_FISH_MISSES:
                    set_mouse(False)
                    time.sleep(restart_delay)
                    set_mouse(False)
                    restart_macro()
                    return

                time.sleep(0.02)
                continue
            else:
                fish_miss_count = 0

            left_edge, right_edge = get_bar_edges_image(
                img,
                FishBarLeft, FishBarTop,
                bar_rgb[2], bar_rgb[1], bar_rgb[0],      # B, G, R
                rightbar_rgb[2], rightbar_rgb[1], rightbar_rgb[0]
            )

            bar_size = right_edge - left_edge if left_edge and right_edge else None
            deadzone = bar_size * left_right_deadzone if bar_size else None
            if bar_size:
                max_left = FishBarLeft + deadzone
                max_right = FishBarRight - deadzone
            else:
                max_left = None
                max_right = None
            fish_edge = fish_pos[0] + 10
            # convert screen → canvas space
            cx1 = fish_pos[0] - CANVAS_X_OFFSET
            cx2 = fish_edge - CANVAS_X_OFFSET
            arrow = None
            arrow_right = None
            arrow = pixel_search_image(img, FishBarLeft, FishBarTop, (arrow_b, arrow_g, arrow_r), 15)
            # Action 1 and 2: Max left and max right
            if max_left and fish_pos[0] <= max_left:
                set_mouse(False)
                # Draw deadzones and tooltips
                ToolTip("Direction: Max Left", 5)
                dx1 = max_left - 20 - CANVAS_X_OFFSET
                dx2 = max_left - CANVAS_X_OFFSET
                draw_box(dx1, 10, dx2, 40, "#000000", "blue")

            elif max_right and fish_pos[0] >= max_right:
                set_mouse(True)
                # Draw deadzones and tooltips
                ToolTip("Direction: Max Right", 5)
                dx3 = max_right - CANVAS_X_OFFSET
                dx4 = max_right + 20 - CANVAS_X_OFFSET
                draw_box(dx3, 10, dx4, 40, "#000000", "blue")

            # Action 0, 3 and 4: PID Control
            elif left_edge is not None and right_edge is not None:
                bar_center = (left_edge + right_edge) // 2
                bx1 = left_edge - CANVAS_X_OFFSET
                bx2 = right_edge - CANVAS_X_OFFSET
                draw_box(bx1, 10, bx2, 40, "#000000", "green")
                # Draw deadzones
                dx1 = max_left - 20 - CANVAS_X_OFFSET
                dx2 = max_left - CANVAS_X_OFFSET
                draw_box(dx1, 10, dx2, 40, "#000000", "blue")
                dx3 = max_right - CANVAS_X_OFFSET
                dx4 = max_right + 20 - CANVAS_X_OFFSET
                draw_box(dx3, 10, dx4, 40, "#000000", "blue")
                # PID calculation
                error = fish_pos[0] - bar_center
                control = pid_control(error)

                # Map PID output to mouse clicks using hysteresis to avoid jitter/oscillation
                control = max(-100, min(100, control))

                # Hysteresis thresholds (tune if necessary)
                on_thresh = 6.0
                off_thresh = 3.0

                if control > on_thresh:
                    set_mouse(True)
                    ToolTip("Tracking Direction: >", 5)
                elif control < -on_thresh:
                    set_mouse(False)
                    ToolTip("Tracking Direction: <", 5)
                else:
                    # Action 0: Within deadzone
                    if abs(control) < off_thresh:
                        ToolTip("Stabilizing", 5)
                        set_mouse(False)

            # Action 5 and 6: Failback (Arrow only)
            elif arrow:
                distance = arrow[0] - fish_pos[0]
                set_mouse(distance < -6)
                if distance < -6 == True:
                    ToolTip("Tracking Direction: > (Fast)", 5)
                else:
                    ToolTip("Tracking Direction: < (Fast)", 5)
            # Action 7 (hidden): No fish, no bar, no arrow
            else:
                set_mouse(False)

            # --- Draw fish and arrow box ---
            if left_edge is None and right_edge is None and arrow is not None:
                arrow_right = arrow[0] + 15
                ax1 = arrow[0] - CANVAS_X_OFFSET
                ax2 = arrow_right - CANVAS_X_OFFSET
                draw_box(ax1, 15, ax2, 35, "#000000", "yellow")

            draw_box(cx1, 10, cx2, 40, "#000000", "red")
            # Debug code
            time.sleep(0.01)
    except Exception as e:
        set_mouse(False)
        macro_state.running = True
        gui.status_label.config(text= f"Macro Crashed: {e}") 
        window.after(0, clear_minigame)  
        window.after(0, stop_clicked)
# Key binds
def on_press(key):
    try:
        if key == Key.f5:  # Start macro
            if macro_state.macro_state.running:  # Use macro_state
                return  # already running
            # ... rest of function
            
        elif key == Key.f6:  # Restart macro
            window.after(0, restart_macro)

        elif key == Key.f7:  # Stop macro
            window.after(0, clear_minigame)
            window.after(0, stop_clicked)

        elif key == Key.f8:
            ToolTip("Debug Key Pressed", 1)

    except Exception as e:
        ToolTip(f"Key handler error: {e}", 1)

listener = KeyListener(on_press=on_press)
listener.daemon = True
listener.start()
# Show GUI
gui = TkinterGUI(window)
overlay = Overlay(window)

window.mainloop()