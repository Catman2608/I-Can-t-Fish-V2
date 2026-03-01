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
global p_gain_entry, d_gain_entry, velocity_smoothing_entry, cast_duration_slider, shake_click_pos
shake_click_pos = None
prev_error = 0.0
last_time = None
# PID smoothing state
pid_integral = 0.0
prev_derivative = 0.0
## Focus on Roblox
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
# Configs
config_var = StringVar()
tooltip_labels = {}
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

window.title("Fisch V14")
window.geometry("800x550")

window.config(bg="#1d1d1d")

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
overlay = None
debug_window = None
macro_running = False

config_var = StringVar(master=window)
config_var.set("Select Rod")

# === Helper Functions and Classes ===
def create_label(parent, text, row, column, fg="white", bg="#1d1d1d", font=("Segoe UI", 9), sticky="w", pady=5, padx=0):
    """Create a label with consistent styling"""
    if platform.system() == "Windows":
        lbl = Label(parent, text=text, bg=bg, fg=fg, font=font)
    elif platform.system() == "Darwin":  # macOS
        lbl = ttk.Label(parent, text=text, style="Dark.TLabel")
    lbl.grid(row=row, column=column, sticky=sticky, pady=pady, padx=padx)
    return lbl

def create_entry(parent, row, column, width=12, sticky="w", padx=10, pady=5):
    """Create an entry field"""
    entry = Entry(parent, width=width)
    entry.grid(row=row, column=column, sticky=sticky, padx=padx, pady=pady)
    return entry

def create_group(parent, text, row, columnspan=2, fg="#00ff00", padx=15, pady=15):
    """Create a labeled group frame"""
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

# Create Tabs
notebook = ttk.Notebook(window)
notebook.pack(expand=True, fill="both")

# Create frames

# First tab (scrollable)
tab1_container = Frame(notebook, bg="#1d1d1d")
tab1_container.pack(fill="both", expand=True)

# Canvas + Scrollbar
canvas = Canvas(tab1_container, bg="#1d1d1d", highlightthickness=0)
canvas.pack(side="left", fill="both", expand=True)

scrollbar = Scrollbar(tab1_container, orient="vertical", command=canvas.yview)
scrollbar.pack(side="right", fill="y")

canvas.configure(yscrollcommand=scrollbar.set)

# Inside frame that will contain all widgets
tab1 = Frame(canvas, bg="#1d1d1d")
canvas.create_window((0,0), window=tab1, anchor="nw")

# Make scrolling resize dynamically
def update_scroll_region(event):
    canvas.configure(scrollregion=canvas.bbox("all"))

tab1.bind("<Configure>", update_scroll_region)

# Enable mouse wheel scrolling
def _on_mousewheel(event):
    canvas.yview_scroll(int(-1*(event.delta/120)), "units")

# Bind to the canvas AND the tab1 frame
canvas.bind("<MouseWheel>", _on_mousewheel)
tab1.bind("<MouseWheel>", _on_mousewheel)

# Add tab to notebook
notebook.add(tab1_container, text="General Settings")

# Second tab
tab2 = Frame(notebook, bg="#1d1d1d")

# Second tab adding (no scroll wheel)
notebook.add(tab2, text="Shake Settings")

# Third tab
tab3_container = Frame(notebook, bg="#1d1d1d")
tab3_container.pack(fill="both", expand=True)

# Canvas + Scrollbar
canvas3 = Canvas(tab3_container, bg="#1d1d1d", highlightthickness=0)
canvas3.pack(side="left", fill="both", expand=True)

scrollbar3 = Scrollbar(tab3_container, orient="vertical", command=canvas3.yview)
scrollbar3.pack(side="right", fill="y")

canvas3.configure(yscrollcommand=scrollbar3.set)

# Inside frame
tab3 = Frame(canvas3, bg="#1d1d1d")
canvas3.create_window((0, 0), window=tab3, anchor="nw")

# Auto-resize scroll region
def update_scroll_region_tab3(event):
    canvas3.configure(scrollregion=canvas3.bbox("all"))

tab3.bind("<Configure>", update_scroll_region_tab3)

# Mouse wheel for tab3
def _on_mousewheel_tab3(event):
    canvas3.yview_scroll(int(-1*(event.delta/120)), "units")

canvas3.bind("<MouseWheel>", _on_mousewheel_tab3)
tab3.bind("<MouseWheel>", _on_mousewheel_tab3)

# Third tab adding
notebook.add(tab3_container, text="Minigame Settings")

# === Buttons ===
def show_overlay_simple():
    global overlay
    if overlay and overlay.winfo_exists():
        overlay.destroy()

    overlay = Toplevel()
    overlay.title("Overlay")
    overlay.config(bg="black")

    # Remove window decorations
    overlay.overrideredirect(True)

    # Always on top
    overlay.attributes("-topmost", True)

    # Transparency
    overlay.attributes("-alpha", 0.93)

    # ✅ Platform-specific click-through
    if platform.system() == "Darwin":
        overlay.attributes("-transparent", True)
    elif platform.system() == "Windows":
        overlay.attributes("-disabled", True)

    # Position bottom-left
    screen_width = overlay.winfo_screenwidth()
    screen_height = overlay.winfo_screenheight()
    overlay.geometry(f"240x120+20+{screen_height - 140}")

    # Grid configuration
    overlay.grid_columnconfigure(0, weight=1)

    # === Text ===
    Label(
        overlay,
        text="Fisch Macro V14",
        fg="#00c8ff",
        bg="black",
        font=("Segoe UI", 12, "bold")
    ).grid(row=0, column=0, pady=(8, 2), sticky="n")

    Label(
        overlay,
        text="Press F5 to start",
        fg="white",
        bg="black",
        font=("Segoe UI", 10)
    ).grid(row=1, column=0)

    Label(
        overlay,
        text="Press F6 to change bar areas",
        fg="white",
        bg="black",
        font=("Segoe UI", 10)
    ).grid(row=2, column=0)

    Label(
        overlay,
        text="Press F7 to stop",
        fg="white",
        bg="black",
        font=("Segoe UI", 10)
    ).grid(row=3, column=0, pady=(0, 5))


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

# Create entry widgets for stability profiles
p_gain_entry = None
d_gain_entry = None
# Bar color and deadzone entries
bar_color_entry = None
arrow_color_entry = None
fish_color_entry = None
left_right_deadzone_entry = None
center_deadzone_entry = None
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

def save_settings(name):
    # Check if the entry widgets exist
    if p_gain_entry is None or d_gain_entry is None:
        create_label(tab1, "Error: Entry widgets not initialized", 0, 1, fg="#00ff00", font=("Segoe UI", 9, "bold"), pady=(10, 5))
        return

    # Base data from PID entries
    data = {
        "proportional_gain": p_gain_entry.get(),
        "derivative_gain": d_gain_entry.get()
    }

    # Save checkbox states if available
    try:
        global checkbox_vars
        if isinstance(checkbox_vars, dict):
            for key, var in checkbox_vars.items():
                # Store as boolean
                data[key] = bool(var.get())
    except Exception:
        # If checkbox_vars isn"t ready yet, skip
        pass

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
        json_save(data, "shake_spam_delay", "shake_spam_entry")
        json_save(data, "shake_wait_until_click", "shake_wait_entry")

        # Bar color & deadzone
        json_save(data, "bar_color", "bar_color_entry")
        json_save(data, "rightbar_color", "rightbar_color_entry")
        json_save(data, "arrow_color", "arrow_color_entry")
        json_save(data, "fish_color", "fish_color_entry")
        json_save(data, "left_right_deadzone", "left_right_deadzone_entry")
        json_save(data, "center_deadzone", "center_deadzone_entry")
        json_save(data, "velocity_smoothing", "velocity_smoothing_entry")
    except Exception:
        pass

    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    print("Saved config:", name)
    
def load_settings(name):
    # Check if the entry widgets exist
    if p_gain_entry is None or d_gain_entry is None:
        print("Error: Entry widgets not initialized")
        return

    path = os.path.join(CONFIG_DIR, f"{name}.json")
    if not os.path.exists(path):
        print("Config not found")
        return

    with open(path, "r") as f:
        data = json.load(f)

    json_load_entry(data, "proportional_gain", "p_gain_entry")
    json_load_entry(data, "derivative_gain", "d_gain_entry")

    # Restore checkbox states if present
    global checkbox_vars
    if isinstance(checkbox_vars, dict):
        for key, var in checkbox_vars.items():
            try:
                var.set(bool(data.get(key, False)))
            except Exception:
                pass

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
    json_load_entry(data, "shake_spam_delay", "shake_spam_entry")
    json_load_entry(data, "shake_wait_until_click", "shake_wait_entry")
    # Minigame timing
    json_load_entry(data, "bar_color", "bar_color_entry")
    json_load_entry(data, "rightbar_color", "rightbar_color_entry")
    json_load_entry(data, "arrow_color", "arrow_color_entry")
    json_load_entry(data, "fish_color", "fish_color_entry")
    json_load_entry(data, "left_right_deadzone", "left_right_deadzone_entry")
    json_load_entry(data, "center_deadzone", "center_deadzone_entry")
    json_load_entry(data, "velocity_smoothing", "velocity_smoothing_entry")
    print(f"Loaded config: ", name)

def get_pid_gains():
    try:
        kp = float(p_gain_entry.get())
    except:
        kp = 0.6

    try:
        kd = float(d_gain_entry.get())
    except:
        kd = 0.2

    # Small integral term to reduce steady-state error (tunable constant)
    ki = 0.02

    return kp, kd, ki

def pid_control(error):
    global prev_error, last_time, pid_integral

    now = time.perf_counter()
    if last_time is None:
        last_time = now
        prev_error = error
        return 0.0

    dt = now - last_time
    if dt <= 0:
        return 0.0

    kp, kd, ki = get_pid_gains()

    # Integral
    pid_integral += error * dt
    pid_integral = max(-100, min(100, pid_integral))  # anti-windup clamp

    # Derivative
    derivative = (error - prev_error) / dt

    output = (
        kp * error +
        ki * pid_integral +
        kd * derivative
    )

    prev_error = error
    last_time = now

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
    show_overlay_simple()  # show small startup overlay

def stop_clicked(event=None):
    global macro_running, overlay, restart_pending, minigame_window
    global prev_error, last_time
    global shake_click_pos
    shake_click_pos = None

    prev_error = 0.0
    last_time = None
    macro_running = False
    restart_pending = False

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

def get_bar_edges_image(img, start_x=570, start_y=860, bar_b=255, bar_g=255, bar_r=255):
    px = img.load()
    w, h = img.size
    y = int(h * 0.55)  # slightly below center (more reliable)
    bar_b_tolerance = bar_b - 15
    bar_g_tolerance = bar_g - 15
    bar_r_tolerance = bar_r - 15
    left_edge = None
    right_edge = None

    for x in range(w):
        r, g, b = px[x, y]
        if r > bar_r_tolerance and g > bar_g_tolerance and b > bar_b_tolerance:
            left_edge = start_x + x
            break

    for x in range(w - 1, -1, -1):
        r, g, b = px[x, y]
        if r > bar_r_tolerance and g > bar_g_tolerance and b > bar_b_tolerance:
            right_edge = start_x + x
            break

    return left_edge, right_edge

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
    global macro_running
    macro_running = False
    global shake_click_pos
    shake_click_pos = None
    set_mouse(False)
    window.after(0, show_minigame_window)
    window.after(150, lambda: threading.Thread(
        target=macro_loop,
        daemon=True
    ).start())

# Prevent spam clicks and stuck mouse
def set_mouse(state: bool):
    global mouse_down
    if state and not mouse_down:
        mouse.press(MouseButton.left)
        mouse_down = True
    elif not state and mouse_down:
        mouse.release(MouseButton.left)
        mouse_down = False

# Run macro
def macro_loop(event=None):
    # Global variables & calculations
    shake_area_left = SCREEN_WIDTH / 4
    shake_area_top = SCREEN_HEIGHT / 8
    shake_area_right = SCREEN_WIDTH / 1.2736
    shake_area_bottom = SCREEN_HEIGHT / 1.3409
    FishBarLeft = SCREEN_WIDTH/3.3160
    FishBarRight = SCREEN_WIDTH/1.4317
    FishBarTop = SCREEN_HEIGHT/1.2
    FishBarBottom = SCREEN_HEIGHT/1.1512
    global macro_running, shake_click_pos
    cast_duration = cast_duration_slider.get()
    bar_entry = bar_color_entry.get()
    bar_a = bar_entry[0]
    bar_b = bar_entry[1]
    bar_c = bar_entry[2]
    bar_b = int(bar_a + bar_b + bar_c)
    bar_d = bar_entry[3]
    bar_e = bar_entry[4]
    bar_f = bar_entry[5]
    bar_g = int(bar_d + bar_e + bar_f)
    bar_h = bar_entry[6]
    bar_i = bar_entry[7]
    bar_j = bar_entry[8]
    bar_r = int(bar_h + bar_i + bar_j)
    rightbar_entry = rightbar_color_entry.get()
    rightbar_a = rightbar_entry[0]
    rightbar_b = rightbar_entry[1]
    rightbar_c = rightbar_entry[2]
    rightbar_b = int(rightbar_a + rightbar_b + rightbar_c)
    rightbar_d = rightbar_entry[3]
    rightbar_e = rightbar_entry[4]
    rightbar_f = rightbar_entry[5]
    rightbar_g = int(rightbar_d + rightbar_e + rightbar_f)
    rightbar_h = rightbar_entry[6]
    rightbar_i = rightbar_entry[7]
    rightbar_j = rightbar_entry[8]
    rightbar_r = int(rightbar_h + rightbar_i + rightbar_j)
    arrow_entry = arrow_color_entry.get()
    arrow_a = arrow_entry[0]
    arrow_b = arrow_entry[1]
    arrow_c = arrow_entry[2]
    arrow_b = int(arrow_a + arrow_b + arrow_c)
    arrow_d = arrow_entry[3]
    arrow_e = arrow_entry[4]
    arrow_f = arrow_entry[5]
    arrow_g = int(arrow_d + arrow_e + arrow_f)
    arrow_h = arrow_entry[6]
    arrow_i = arrow_entry[7]
    arrow_j = arrow_entry[8]
    arrow_r = int(arrow_h + arrow_i + arrow_j)
    fish_entry = fish_color_entry.get()
    fish_a = fish_entry[0]
    fish_b = fish_entry[1]
    fish_c = fish_entry[2]
    fish_b = int(fish_a + fish_b + fish_c)
    fish_d = fish_entry[3]
    fish_e = fish_entry[4]
    fish_f = fish_entry[5]
    fish_g = int(fish_d + fish_e + fish_f)
    fish_h = fish_entry[6]
    fish_i = fish_entry[7]
    fish_j = fish_entry[8]
    fish_r = int(fish_h + fish_i + fish_j)
    try:
        macro_running = True
        fish_miss_count = 0
        MAX_FISH_MISSES = 15

        
        # Show minigame window
        show_minigame_window()
        CANVAS_X_OFFSET = 570
        CANVAS_Y_OFFSET = 860

        # --- Pre actions ---
        mouse.position = (960, 300)
        if checkbox_vars["auto_zoom_var"].get():
            for _ in range(20):
                mouse.scroll(0, 1)
                time.sleep(0.05)
            mouse.scroll(0, -1)
        time.sleep(0.1)
        if checkbox_vars["auto_select_rod_var"].get():
            # Press "2" then "1"
            keyboard.press("2")
            time.sleep(0.05)
            keyboard.release("2")
            time.sleep(0.1)
            keyboard.press("1")
            time.sleep(0.05)
            keyboard.release("1")
            time.sleep(0.2)
        mouse.press(MouseButton.left)
        time.sleep(cast_duration)
        mouse.release(MouseButton.left)
        time.sleep(1)

        # --- Fish detection ---
        fish_detected = False
        attempts = 0
        shake_no_white_counter = 0
        SHAKE_NO_WHITE_TIMEOUT = 2.0  # seconds
        shake_last_white_time = time.time()
        
        while macro_running and not fish_detected and attempts < 50:
            force_game_focus()

            scan_delay = get_entry_float(shake_scan_entry, 0.05)

            if shake_mode_var.get() == 'Click':
                # Search for white pixel in the specified area
                found = pixel_search(shake_area_left, shake_area_top, shake_area_right, shake_area_bottom, (255, 255, 255), 6)
                
                if found:
                    # Reset the no-white timer since we found white
                    shake_last_white_time = time.time()
                    
                    # Move mouse to the white pixel and click it
                    mouse.position = found
                    mouse.press(MouseButton.left)
                    time.sleep(0.003)
                    mouse.release(MouseButton.left)
                    
                    # Store for potential reuse (optional)
                    if shake_click_pos is None:
                        shake_click_pos = found
                else:
                    # No white pixel found - check if timeout reached
                    current_time = time.time()
                    time_since_last_white = current_time - shake_last_white_time
                    
                    if time_since_last_white >= SHAKE_NO_WHITE_TIMEOUT:
                        print("No white pixel found for 2 seconds, restarting macro...")
                        set_mouse(False)
                        time.sleep(0.5)
                        restart_macro()
                        return
            elif shake_mode_var.get() == 'Navigation':
                keyboard.press(Key.enter)
                time.sleep(0.003)
                keyboard.release(Key.enter)

            time.sleep(scan_delay)

            # Fish detect (stable check)
            stable = 0
            while stable < 8:
                if pixel_search(FishBarLeft, FishBarTop, FishBarBottom, FishBarRight, (fish_b, fish_g, fish_r), 0):
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

        if not fish_detected:
            macro_running = False
            window.after(0, hide_minigame_window)
            return

        max_left = 0
        max_right = 0
        # --- Fishing bar loop ---
        while macro_running:
            clear_minigame()
            img = capture_region(FishBarLeft, FishBarTop, FishBarRight, FishBarBottom)
            fish_pos = pixel_search_image(img, FishBarLeft, FishBarTop, (fish_b, fish_g, fish_r), 0)
            if fish_pos is None:
                fish_miss_count += 1

                # release mouse briefly to avoid stuck input
                set_mouse(False)

                if fish_miss_count >= MAX_FISH_MISSES:
                    set_mouse(False)
                    time.sleep(0.5)
                    restart_macro()
                    return

                time.sleep(0.02)
                continue
            else:
                fish_miss_count = 0

            left_edge, right_edge = get_bar_edges_image(img, FishBarLeft, FishBarTop, bar_b, bar_g, bar_r) # Get bar edges
            bar_size = right_edge - left_edge if left_edge and right_edge else None
            deadzone = bar_size * 0.5 if bar_size else None
            if bar_size:
                max_left = 570 + deadzone
                max_right = 1350 - deadzone
            else:
                max_left = None
                max_right = None
            fish_edge = fish_pos[0] + 10
            # convert screen → canvas space
            cx1 = fish_pos[0] - CANVAS_X_OFFSET
            cx2 = fish_edge - CANVAS_X_OFFSET
            arrow = None
            arrow_right = None
            arrow = pixel_search_image(img, FishBarLeft, FishBarTop, (arrow_b, arrow_g, arrow_r), 5)
            # Action 1 and 2: Max left and max right
            if max_left and fish_pos[0] <= max_left:
                set_mouse(False)
                # Draw deadzones
                dx1 = max_left - 20 - CANVAS_X_OFFSET
                dx2 = max_left - CANVAS_X_OFFSET
                draw_box(dx1, 10, dx2, 40, "#000000", "blue")

            elif max_right and fish_pos[0] >= max_right:
                set_mouse(True)
                # Draw deadzones
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
                elif control < -on_thresh:
                    set_mouse(False)
                else:
                    # Action 0: Within deadzone
                    if abs(control) < off_thresh:
                        set_mouse(False)

            # Action 5 and 6: Failback (Arrow only)
            elif arrow:
                distance = arrow[0] - fish_pos[0]
                set_mouse(distance < -6)

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
            time.sleep(0.01)
    except Exception as e:
        set_mouse(False)
        macro_running = False
        print("Macro crashed:", e)  
        window.after(0, clear_minigame)  
        window.after(0, stop_clicked)
# Key binds
def on_press(key):
    try:
        if key == Key.f5:  # Start macro
            if macro_running:
                return  # already running
            # UI must be on main thread
            window.after(0, show_minigame_window)

            # Macro logic runs in background
            threading.Thread(
                target=macro_loop,
                daemon=True
            ).start()

        elif key == Key.f6:  # Restart macro
            window.after(0, restart_macro)

        elif key == Key.f7:  # Stop macro
            window.after(0, clear_minigame)
            window.after(0, stop_clicked)

        elif key == Key.f8:
            print("Debug key pressed")

    except Exception as e:
        print(f"Key handler error: {e}")

listener = KeyListener(on_press=on_press)
listener.daemon = True
listener.start()

# Bottom status bar (show start/stop buttons, versions and status)
bottom_frame = Frame(window, bg="#1d1d1d")
bottom_frame.pack(fill="x", pady=10)

Label(
    bottom_frame,
    text="V14 | Config:",
    font=("Segoe UI", 9),
    bg="#1d1d1d",
    fg="white"
).grid(row=0, column=0, padx=(10, 5))

# Config Dropdown
config_dropdown = ttk.Combobox(
    bottom_frame,
    textvariable=config_var,
    state="readonly",
    width=20
)

config_dropdown.grid(column=1, row=0, padx=10)

rod_configs = load_rod_configs()
config_dropdown["values"] = rod_configs
config_var.set(rod_configs[0])
config_dropdown.bind("<<ComboboxSelected>>", on_rod_selected)

start_btn = Button(
    bottom_frame,
    text="Start",
    command=lambda: window.after(0, start_clicked),
    font=("Segoe UI", 9),  # Font
    width=12,                       # Button width
    height=2,                       # Button height
    bg="#f0f0f0",                 # Button color
    fg="black",                     # Button text color
    activebackground="#f0f0f0",
    activeforeground="black"
)

start_btn.grid(column=2, row=0, padx=10, pady=10)

save_btn = Button(
    bottom_frame,
    text="Save Settings",
    command=lambda: save_settings(config_var.get()),
    font=("Segoe UI", 9),  # Font
    width=12,                       # Button width
    height=2,                       # Button height
    bg="#f0f0f0",                 # Button color
    fg="black",                     # Button text color
    activebackground="#f0f0f0",
    activeforeground="black"
)
save_btn.grid(column=3, row=0, padx=10, pady=10)

load_btn = Button(
    bottom_frame,
    text="Load Settings",
    command=lambda: load_settings(config_var.get()),
    font=("Segoe UI", 9),  # Font
    width=12,                       # Button width
    height=2,                       # Button height
    bg="#f0f0f0",                 # Button color
    fg="black",                     # Button text color
    activebackground="#f0f0f0",
    activeforeground="black"
)

load_btn.grid(column=4, row=0, padx=10, pady=10)

stop_btn = Button(
    bottom_frame,
    text="Stop",
    command=stop_clicked,
    font=("Segoe UI", 9),  # Font
    width=12,                       # Button width
    height=2,                       # Button height
    bg="#f0f0f0",                 # Button color
    fg="black",                     # Button text color
    activebackground="#f0f0f0",
    activeforeground="black"
)

stop_btn.grid(column=5, row=0, padx=10, pady=10)

# General Settings
create_label(tab1, "General Settings", 0, 0, fg="#00ff00", font=("Segoe UI", 9, "bold"), pady=(10, 5))

# Automation Options
checkbox_group = create_group(tab1, "Automation Options", 1)

# Checkboxes for groupbox
checkbox_options = [
    ("Auto Select Rod", "auto_select_rod_var"),
    ("Auto Zoom In", "auto_zoom_var"),
    ("Fish Overlay", "fish_overlay_var")
]

checkbox_vars = create_checkboxes(checkbox_group, checkbox_options)

# Timing Group
timing_group = create_group(tab1, "Timing Options", 2)

# Sliders and text labels
create_label(timing_group, "Wait For Bobber to Land (seconds):", 1, 0)
create_entry(timing_group, 1, 1)
bobber_delay_entry = create_entry(timing_group, 1, 1, pady=0)
create_label(timing_group, "Bait Delay (seconds):", 2, 0)
create_entry(timing_group, 2, 1, pady=0)
bait_delay_entry = create_entry(timing_group, 2, 1, pady=0)
create_label(timing_group, "Restart Delay (seconds):", 3, 0)
restart_delay_entry = create_entry(timing_group, 3, 1, pady=0)

# Casting Group
casting_group = create_group(tab1, "Casting Options", 3)
create_label(casting_group, "Hold Rod Cast Duration (seconds):", 0, 0)
cast_duration_slider = create_slider(casting_group, 0, 1, 0.2, 2, 0.1)

# Shake Settings
tab2.grid_rowconfigure(1, weight=1)
tab2.grid_columnconfigure(0, weight=1)

create_label(tab2, "Shake Settings", 0, 0, fg="#87CEEB", font=("Segoe UI", 9, "bold"), pady=10)

# Shake Config
shake_config_group = create_group(tab2, "Shake Configuration", 1, fg="#87CEEB")
shake_config_group.grid(sticky="nsew")  # Update to expand

create_label(shake_config_group, "UI Navigation Key:", 1, 0)
shake_ui_entry = create_entry(shake_config_group, 1, 1)

create_label(shake_config_group, "Shake Mode:", 2, 0)

shake_mode_var = StringVar()
shake_mode_var.set("Click")  # default option

shake_mode_dropdown = ttk.Combobox(
    shake_config_group,
    textvariable=shake_mode_var,
    values=["Click", "Navigation", "Wait"],
    state="readonly",
    width=15
)
shake_mode_dropdown.grid(row=2, column=1, sticky="w", padx=10, pady=5)

create_label(shake_config_group, "Click Shake Color Tolerance:", 3, 0)
shake_color_entry = create_entry(shake_config_group, 3, 1)

create_label(shake_config_group, "Scan Delay (seconds):", 4, 0)
shake_scan_entry = create_entry(shake_config_group, 4, 1)

create_label(shake_config_group, "Click Delay (seconds):", 5, 0)
shake_spam_entry = create_entry(shake_config_group, 5, 1)

create_label(shake_config_group, "Wait Until Clicking (seconds):", 6, 0)
shake_wait_entry = create_entry(shake_config_group, 6, 1)

# Minigame Settings
tab3.grid_rowconfigure(1, weight=1)
tab3.grid_columnconfigure(0, weight=1)

create_label(tab3, "Minigame Settings", 0, 0, fg="#e87b07", font=("Segoe UI", 9, "bold"), pady=10)

# Fish Settings
fish_settings_group = create_group(tab3, "Bar Colors (BBB-GGG-RRR)", 1, fg="#e87b07")
fish_settings_group.grid(sticky="nsew")

create_label(fish_settings_group, "Bar Color Left:", 0, 0)
bar_color_entry = create_entry(fish_settings_group, 0, 1)

create_label(fish_settings_group, "Bar Color Right:", 1, 0)
rightbar_color_entry = create_entry(fish_settings_group, 1, 1)

create_label(fish_settings_group, "Arrow Color:", 2, 0)
arrow_color_entry = create_entry(fish_settings_group, 2, 1)

create_label(fish_settings_group, "Fish Color:", 3, 0)
fish_color_entry = create_entry(fish_settings_group, 3, 1)

# Move Check Settings
move_check_group = create_group(tab3, "Deadzone Settings", 2, fg="#e87b07")
move_check_group.grid(sticky="nsew")

create_label(move_check_group, "Left Right Deadzone Area:", 0, 0)
left_right_deadzone_entry = create_entry(move_check_group, 0, 1)
create_label(move_check_group, "Center deadzone area:", 1, 0)
center_deadzone_entry = create_entry(move_check_group, 1, 1)

# Stability Profiles
stability_group = create_group(tab3, "Stability Profiles", 3, fg="#e87b07")
stability_group.grid(sticky="nsew")

create_label(stability_group, "Proportional Gain:", 0, 0)
# Create p_gain_entry and store it globally
p_gain_entry = create_entry(stability_group, 0, 1)

create_label(stability_group, "Derivative Gain:", 1, 0)
# Create d_gain_entry and store it globally  
d_gain_entry = create_entry(stability_group, 1, 1)

create_label(stability_group, "Velocity Smoothing:", 2, 0)
create_entry(stability_group, 2, 1)
velocity_smoothing_entry = create_entry(stability_group, 2, 1)

# Show GUI
window.mainloop()