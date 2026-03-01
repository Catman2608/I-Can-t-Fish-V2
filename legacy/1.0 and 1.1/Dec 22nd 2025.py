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
global p_gain_entry, d_gain_entry
prev_error = 0.0
last_time = None
## Focus on Roblox
if platform.system() == 'Windows':
    import ctypes
    from PIL import ImageGrab
    user32 = ctypes.windll.user32
    width = user32.GetSystemMetrics(0)
    height = user32.GetSystemMetrics(1)
elif platform.system() == 'Darwin':  # macOS
    from AppKit import NSScreen
    frame = NSScreen.mainScreen().frame()
    width = frame.size.width
    height = frame.size.height

# tkinter window
window = Tk()
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

window.title("Fisch V14")
window.geometry("800x550")

window.config(bg="#1d1d1d")

# Configure TTK Style for macOS compatibility
style.configure("Dark.TCheckbutton",
                background="#1d1d1d",
                foreground="white",
                fieldbackground="#1d1d1d")

style.map("Dark.TCheckbutton",
          background=[('active', '#3a3a3a')],
          foreground=[('active', 'white')])

style.configure("Dark.TLabel",
                background="#1d1d1d",
                foreground="white")

# Configure TTK Dark Mode
style.configure("DarkCheck.TCheckbutton",
                background="#1d1d1d",
                foreground="white",
                fieldbackground="#1d1d1d")

style.map("DarkCheck.TCheckbutton",
          background=[('active', '#3a3a3a')],
          foreground=[('active', 'white')])

# Global variables
overlay = None
debug_window = None
macro_running = False

config_var = StringVar(master=window)
config_var.set("Select Rod")

# === Helper Functions and Classes ===
def create_label(parent, text, row, column, fg="white", bg="#1d1d1d", font=("Segoe UI", 9), sticky="w", pady=5, padx=0):
    """Create a label with consistent styling"""
    if platform.system() == 'Windows':
        lbl = Label(parent, text=text, bg=bg, fg=fg, font=font)
    elif platform.system() == 'Darwin':  # macOS
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

    # Remove border
    overlay.overrideredirect(True)

    # Always on top
    overlay.attributes("-topmost", True)

    # Prevent overlay from stealing focus
    overlay.attributes("-disabled", True)

    # Optional transparency (0.0–1.0)
    overlay.attributes("-alpha", 0.93)

    # Get screen dimensions and position at bottom left
    screen_width = overlay.winfo_screenwidth()
    screen_height = overlay.winfo_screenheight()
    
    # Set size and position (240x120 at bottom left)
    overlay.geometry(f"240x120+20+{screen_height - 140}")

    # Draggable overlay
    def start_move(event):
        overlay.x = event.x
        overlay.y = event.y

    def on_motion(event):
        x = event.x_root - overlay.x
        y = event.y_root - overlay.y
        overlay.geometry(f"+{x}+{y}")

    overlay.bind("<ButtonPress-1>", start_move)
    overlay.bind("<B1-Motion>", on_motion)

    # === Text ===
    Label(
        overlay, text="Fisch Macro V14",
        fg="#00c8ff", bg="black",
        font=("Segoe UI", 12, "bold")
    ).pack(pady=(8, 2))

    Label(
        overlay, text="Press F5 to start",
        fg="white", bg="black",
        font=("Segoe UI", 10)
    ).pack()

    Label(
        overlay, text="Press F6 to change bar areas",
        fg="white", bg="black",
        font=("Segoe UI", 10)
    ).pack()

    Label(
        overlay, text="Press F7 to stop",
        fg="white", bg="black",
        font=("Segoe UI", 10)
    ).pack(pady=(0, 5))

def show_minigame_window():
    global minigame_window, minigame_canvas

    if minigame_window and minigame_window.winfo_exists():
        minigame_window.deiconify()
        minigame_window.lift()
        return

    minigame_window = Toplevel(window)
    minigame_window.geometry("800x60+570+660")
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

def save_settings(name):
    # Check if the entry widgets exist
    if p_gain_entry is None or d_gain_entry is None:
        print("Error: Entry widgets not initialized")
        return
        
    data = {
        "proportional_gain": p_gain_entry.get(),
        "derivative_gain": d_gain_entry.get()
    }

    path = os.path.join(CONFIG_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    print(f"Saved config: {name}")
    
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

    p_gain_entry.delete(0, END)
    p_gain_entry.insert(0, data.get("proportional_gain", ""))

    d_gain_entry.delete(0, END)
    d_gain_entry.insert(0, data.get("derivative_gain", ""))

    print(f"Loaded config: {name}")

def get_pid_gains():
    try:
        kp = float(p_gain_entry.get())
    except:
        kp = 0.6

    try:
        kd = float(d_gain_entry.get())
    except:
        kd = 0.2

    return kp, kd

def pid_control(error):
    global prev_error, last_time

    now = time.perf_counter()
    if last_time is None:
        last_time = now
        prev_error = error
        return 0.0

    dt = now - last_time
    if dt <= 0:
        return 0.0


    kp, kd = get_pid_gains()


    derivative = (error - prev_error) / dt
    output = kp * error + kd * derivative


    prev_error = error
    last_time = now


    return output

def start_clicked(event=None):
    window.withdraw()      # hide main GUI
    show_overlay_simple()  # show small startup overlay

def stop_clicked(event=None):
    global macro_running, overlay, restart_pending, minigame_window
    global prev_error, last_time

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

def change_bar_width(event=None):
    print("Change bar width clicked")

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
    if system == 'Windows':
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

def get_bar_edges_image(img, start_x=570, start_y=860):
    px = img.load()
    w, h = img.size
    y = int(h * 0.55)  # slightly below center (more reliable)

    left_edge = None
    right_edge = None

    for x in range(w):
        r, g, b = px[x, y]
        if r > 240 and g > 240 and b > 240:
            left_edge = start_x + x
            break

    for x in range(w - 1, -1, -1):
        r, g, b = px[x, y]
        if r > 240 and g > 240 and b > 240:
            right_edge = start_x + x
            break

    return left_edge, right_edge

def capture_region(start_x, start_y, end_x, end_y):
    if system == 'Windows':
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
    if system == 'Windows':
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        user32.SwitchToThisWindow(hwnd, True)
        time.sleep(0.05)
        
    elif system == 'Darwin':  # macOS
        # Focus the window behind the current foreground window
        applescript = '''
    tell application "System Events"
        set procList to (every process whose visible is true)
        set frontApps to name of procList

        -- The first app in frontApps is the current frontmost window (Python)
        -- The second is the window UNDER it
        if (count of frontApps) > 1 then
            set targetApp to item 2 of frontApps
            tell application targetApp to activate
        end if
    end tell
    '''
        try:
            subprocess.run(['osascript', '-e', applescript],
                           capture_output=True, check=True)
        except Exception as e:
            print("Could not focus the window behind Python:", e)

    time.sleep(0.1)

def restart_macro():
    global macro_running
    macro_running = False

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
    # Global variables
    global macro_running
    macro_running = True
    fish_miss_count = 0
    MAX_FISH_MISSES = 15

    
    # Show minigame window
    show_minigame_window()
    CANVAS_X_OFFSET = 570
    CANVAS_Y_OFFSET = 860

    # --- Pre actions ---
    mouse.position = (300, 150)
    for _ in range(20):
        mouse.scroll(0, 1)
        time.sleep(0.05)
    mouse.scroll(0, -1)
    time.sleep(0.1)
    mouse.press(MouseButton.left)
    time.sleep(0.48)
    mouse.release(MouseButton.left)
    time.sleep(1)

    # --- Fish detection ---
    fish_detected = False
    attempts = 0

    while macro_running and not fish_detected and attempts < 50:
        force_game_focus()
        keyboard.press(Key.enter)
        time.sleep(0.03)
        keyboard.release(Key.enter)

        found = pixel_search(570, 860, 1350, 910, (67, 75, 91), 15)
        if found:
            for i in range(9):
                found = pixel_search(570, 860, 1350, 910, (67, 75, 91), 15)
                time.sleep(0.02)
                if not found:
                    break
            if i >= 8:
                fish_detected = True
                mouse.position = found
                mouse.click(MouseButton.left)
                break

        attempts += 1
        time.sleep(0.1)

    if not fish_detected:
        stop_clicked()
        return
    max_left = 0
    max_right = 0
    # --- Fishing bar loop ---
    while macro_running:
        clear_minigame()
        img = capture_region(570, 860, 1350, 910)
        fish_pos = pixel_search_image(img, 570, 860, (67, 75, 91), 0)
        if fish_pos is None:
            fish_miss_count += 1

            # release mouse briefly to avoid stuck input
            set_mouse(False)

            if fish_miss_count >= MAX_FISH_MISSES:
                time.sleep(0.5)
                restart_macro()
                return

            time.sleep(0.02)
            continue
        else:
            fish_miss_count = 0
        left_edge, right_edge = get_bar_edges_image(img) # Get bar edges
        bar_size = right_edge - left_edge if left_edge and right_edge else None
        deadzone = bar_size * 0.4 if bar_size else None
        fish_edge = fish_pos[0] + 10
        # convert screen → canvas space
        cx1 = fish_pos[0] - CANVAS_X_OFFSET
        cx2 = fish_edge - CANVAS_X_OFFSET
        arrow = None
        arrow_right = None
        arrow = pixel_search_image(img, 570, 860, (135, 133, 132), 5)
        # Action 1 and 2: PID Control
        if left_edge is not None and right_edge is not None:
            # Find arrow position
            arrow_right = None
            if arrow:
                arrow_right = arrow[0] + 20
            # Calculate bar center
            bar_center = (left_edge + right_edge) // 2
            bx1 = left_edge - CANVAS_X_OFFSET
            bx2 = right_edge - CANVAS_X_OFFSET
            max_left = left_edge + deadzone
            max_right = right_edge - deadzone

            draw_box(bx1, 5, bx2, 55, "#ffffff", "green")
            error = fish_pos[0] - bar_center
            control = pid_control(error)

            # Deadzone (prevents jitter)
            if abs(error) < 4:
                set_mouse(False)

            # Clamp output
            control = max(-100, min(100, control))

            # Convert PID output to click behavior
            if control > 0:
                set_mouse(True)
            else:
                set_mouse(False)
        # Action 3 and 4: Max left and right
        elif fish_pos[0] <= max_left:
            set_mouse(False)
        elif fish_pos[0] >= max_right:
            set_mouse(True)
        # Action 5 and 6: Simple Arrow Follow
        else:
            arrow_right = arrow[0] + 15
            if arrow:
                distance = arrow[0] - fish_pos[0]
                if distance < -6:
                    set_mouse(True)
                else:
                    set_mouse(False)

        # --- Draw fish and arrow box ---
        if arrow:
            ax1 = arrow[0] - CANVAS_X_OFFSET
            ax2 = arrow_right - CANVAS_X_OFFSET
            draw_box(ax1, 20, ax2, 40, "#848587", "yellow")

        draw_box(cx1, 0, cx2, 60, "#434b5b", "red")
        time.sleep(0.01)
    
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
    command=lambda: threading.Thread(target=start_clicked, daemon=True).start(),
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
    ("Auto Select Rod", "auto_refresh_var"),
    ("Auto Zoom In", "auto_zoom_var"),
    ("Fish Overlay", "fish_overlay_var")
]

checkbox_vars = create_checkboxes(checkbox_group, checkbox_options)

# Timing Group
timing_group = create_group(tab1, "Timing Options", 2)

# Sliders and text labels
create_label(timing_group, "Wait For Bobber to Land (seconds):", 1, 0)
create_entry(timing_group, 1, 1)
create_label(timing_group, "Bait Delay (seconds):", 2, 0)
create_entry(timing_group, 2, 1, pady=0)

# Casting Group
casting_group = create_group(tab1, "Casting Options", 3)
create_label(casting_group, "Hold Rod Cast Duration (seconds):", 0, 0)
cast_duration_slider = create_slider(casting_group, 0, 1, 0.3, 2, 0.2)

# Shake Settings
tab2.grid_rowconfigure(1, weight=1)
tab2.grid_columnconfigure(0, weight=1)

create_label(tab2, "Shake Settings", 0, 0, fg="#87CEEB", font=("Segoe UI", 9, "bold"), pady=10)

# Shake Config
shake_config_group = create_group(tab2, "Shake Configuration", 1, fg="#87CEEB")
shake_config_group.grid(sticky="nsew")  # Update to expand

create_label(shake_config_group, "UI Navigation Key:", 1, 0)
create_entry(shake_config_group, 1, 1)

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
create_entry(shake_config_group, 3, 1)

create_label(shake_config_group, "Scan Delay (ms):", 4, 0)
create_entry(shake_config_group, 4, 1)

create_label(shake_config_group, "Spam Delay (ms):", 5, 0)
create_entry(shake_config_group, 5, 1)

create_label(shake_config_group, "Wait Until Clicking (seconds):", 6, 0)
create_entry(shake_config_group, 6, 1)

# Minigame Settings
tab3.grid_rowconfigure(1, weight=1)
tab3.grid_columnconfigure(0, weight=1)

create_label(tab3, "Minigame Settings", 0, 0, fg="#e87b07", font=("Segoe UI", 9, "bold"), pady=10)

# Fish Settings
fish_settings_group = create_group(tab3, "Fish Settings", 1, fg="#e87b07")
fish_settings_group.grid(sticky="nsew")

create_label(fish_settings_group, "Restart Delay (seconds):", 0, 0)
duration_slider = create_slider(fish_settings_group, 0, 1, 0.5, 5, 0.25)

create_label(fish_settings_group, "Bar Color:", 1, 0)
create_entry(fish_settings_group, 1, 1)

create_label(fish_settings_group, "Arrow Color:", 2, 0)
create_entry(fish_settings_group, 2, 1)

create_label(fish_settings_group, "Fish Color:", 3, 0)
create_entry(fish_settings_group, 3, 1)

# Move Check Settings
move_check_group = create_group(tab3, "Move Check Settings", 2, fg="#e87b07")
move_check_group.grid(sticky="nsew")

create_label(move_check_group, "Stabilize Delay (ms):", 0, 0)
create_entry(move_check_group, 0, 1)
create_label(move_check_group, "Click Amount (ms):", 1, 0)
create_entry(move_check_group, 1, 1)

# Stability Profiles - CREATE THE ENTRY WIDGETS HERE
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

# Show GUI
window.mainloop()