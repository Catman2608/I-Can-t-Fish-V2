import customtkinter as ctk
import keyboard
import tkinter as tk
from tkinter import messagebox
import time
import threading
from PIL import ImageGrab, ImageDraw, ImageTk, Image
import pygetwindow as gw
import webbrowser
import mouse
import win32api
import win32con
import win32gui
import numpy as np
import ctypes
import cv2
import mss
from collections import deque
import json
import os
import sys

# Set DPI awareness to handle Windows scaling properly
# This ensures Tkinter coordinates match ImageGrab coordinates
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # Fallback for older Windows
    except:
        pass  # If both fail, continue without DPI awareness


class DualAreaSelector:
    """Full-screen overlay for selecting both Fish Box and Shake Box simultaneously"""

    def __init__(self, parent, screenshot, shake_area, fish_area, callback):
        self.callback = callback
        self.screenshot = screenshot

        # Create fullscreen window
        self.window = tk.Toplevel(parent)
        self.window.attributes('-fullscreen', True)
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
            font=("Arial", 12, "bold"), fill='#f44336'
        )

        # Create Fish Box (Blue)
        self.fish_rect = self.canvas.create_rectangle(
            self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2,
            outline='#2196F3', width=2, fill='#2196F3', stipple='gray50'
        )
        fish_label_x = self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2
        self.fish_label = self.canvas.create_text(
            fish_label_x, self.fish_y1 - 20, text="Fish Area",
            font=("Arial", 12, "bold"), fill='#2196F3'
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
        
        # Start zoom window
        self.show_zoom(0, 0)

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

    def show_zoom(self, x, y):
        """Display mini zoom window using OpenCV for better performance"""
        # Create zoom window on first use
        if not self.zoom_window_created:
            cv2.namedWindow(self.zoom_window_name, cv2.WINDOW_NORMAL)
            cv2.setWindowProperty(self.zoom_window_name, cv2.WND_PROP_TOPMOST, 1)
            
            # Remove window decorations
            time.sleep(0.05)  # Give window time to be created
            self.zoom_hwnd = win32gui.FindWindow(None, self.zoom_window_name)
            if self.zoom_hwnd:
                style = win32gui.GetWindowLong(self.zoom_hwnd, win32con.GWL_STYLE)
                style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
                win32gui.SetWindowLong(self.zoom_hwnd, win32con.GWL_STYLE, style)
                win32gui.SetWindowPos(self.zoom_hwnd, win32con.HWND_TOPMOST, 0, 0, 
                                     self.zoom_window_size, self.zoom_window_size + self.info_height,
                                     win32con.SWP_NOMOVE | win32con.SWP_FRAMECHANGED)
            self.zoom_window_created = True
            
            # Start continuous update loop
            self._update_zoom_loop()
    
    def _update_zoom_loop(self):
        """Continuously update zoom window at ~30 FPS"""
        if not self.zoom_window_created:
            return
        
        # Get current cursor position
        try:
            cursor_x, cursor_y = win32api.GetCursorPos()
        except:
            # If window is being destroyed, stop the loop
            self.zoom_update_job = None
            return
        
        # Calculate capture region
        half_size = self.zoom_capture_size // 2
        left = max(0, cursor_x - half_size)
        top = max(0, cursor_y - half_size)
        
        # Adjust if near screen edges
        if left + self.zoom_capture_size > self.screen_width:
            left = self.screen_width - self.zoom_capture_size
        if top + self.zoom_capture_size > self.screen_height:
            top = self.screen_height - self.zoom_capture_size
        
        try:
            # Use frozen screenshot
            cropped = self.screenshot.crop((left, top, left + self.zoom_capture_size, top + self.zoom_capture_size))
            img = np.array(cropped)
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            
            # Zoom in using nearest neighbor interpolation
            zoomed = cv2.resize(img, (self.zoom_window_size, self.zoom_window_size), interpolation=cv2.INTER_NEAREST)
            
            # Draw crosshair at center
            center = self.zoom_window_size // 2
            crosshair_size = 10
            cv2.line(zoomed, (center - crosshair_size, center), (center + crosshair_size, center), (0, 0, 255), 2)
            cv2.line(zoomed, (center, center - crosshair_size), (center, center + crosshair_size), (0, 0, 255), 2)
            
            # Get color at cursor
            center_pixel_y = cursor_y - top
            center_pixel_x = cursor_x - left
            center_pixel_y = max(0, min(center_pixel_y, img.shape[0] - 1))
            center_pixel_x = max(0, min(center_pixel_x, img.shape[1] - 1))
            
            color_bgr = img[center_pixel_y, center_pixel_x]
            b, g, r = color_bgr
            
            # Create display with info area
            display = np.ones((self.zoom_window_size + self.info_height, self.zoom_window_size, 3), dtype=np.uint8) * 40
            display[:self.zoom_window_size, :] = zoomed
            
            # Add white border around zoom area
            cv2.rectangle(display, (0, 0), (self.zoom_window_size-1, self.zoom_window_size-1), (255, 255, 255), 2)
            
            # Add color text
            color_text = f"BGR: ({int(b)}, {int(g)}, {int(r)})"
            cv2.putText(display, color_text, (10, self.zoom_window_size + 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # Add position text
            pos_text = f"Pos: ({cursor_x}, {cursor_y})"
            cv2.putText(display, pos_text, (10, self.zoom_window_size + 15), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
            
            # Display the zoom window
            cv2.imshow(self.zoom_window_name, display)
            cv2.waitKey(1)
            
            # Move window to follow cursor (with offset)
            if self.zoom_hwnd:
                offset_x = 30
                offset_y = 30
                win_x = cursor_x + offset_x
                win_y = cursor_y + offset_y
                
                # Adjust if too close to screen edges
                if win_x + self.zoom_window_size > self.screen_width:
                    win_x = cursor_x - self.zoom_window_size - offset_x
                if win_y + self.zoom_window_size + self.info_height > self.screen_height:
                    win_y = cursor_y - self.zoom_window_size - self.info_height - offset_y
                
                # Move the window
                win32gui.SetWindowPos(self.zoom_hwnd, win32con.HWND_TOPMOST, win_x, win_y, 
                                     self.zoom_window_size, self.zoom_window_size + self.info_height,
                                     win32con.SWP_NOSIZE)
        except:
            # If any error occurs, stop the loop
            self.zoom_update_job = None
            return
        
        # Schedule next update (~30 FPS = 33ms)
        self.zoom_update_job = self.window.after(33, self._update_zoom_loop)

    def update_boxes(self):
        """Update both boxes and their labels"""
        self.canvas.coords(self.shake_rect, self.shake_x1, self.shake_y1, self.shake_x2, self.shake_y2)
        self.canvas.coords(self.shake_label, self.shake_x1 + (self.shake_x2 - self.shake_x1) // 2, self.shake_y1 - 20)

        self.canvas.coords(self.fish_rect, self.fish_x1, self.fish_y1, self.fish_x2, self.fish_y2)
        self.canvas.coords(self.fish_label, self.fish_x1 + (self.fish_x2 - self.fish_x1) // 2, self.fish_y1 - 20)

        self.create_all_handles()


class VideoRecorder:
    """In-memory video recorder using lossless PNG compression"""
    def __init__(self, fps=60, quality=70):
        self.compressed_frames = deque()
        self.quality = quality  # Not used for PNG, kept for compatibility
        self.fps = fps
        self.is_recording = False
        
    def start_recording(self):
        """Start recording"""
        self.is_recording = True
        self.compressed_frames.clear()
        
    def add_frame(self, frame):
        """Add a frame (BGR numpy array)"""
        if self.is_recording:
            # Compress to PNG in memory (lossless, pixel-perfect)
            # PNG compression level 1 = fast compression, still lossless
            _, buffer = cv2.imencode('.png', frame, 
                                    [cv2.IMWRITE_PNG_COMPRESSION, 1])
            self.compressed_frames.append(buffer)
            
    def stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        
    def playback(self, loop=False, speed=1.0):
        """Play back the recording with trackbar slider"""
        if not self.compressed_frames:
            print("No frames recorded!")
            return
        
        print(f"\nPlayback started - Use trackbar to scrub through frames")
        print("Close window to exit")
        
        window_name = 'Playback'
        
        # Create window with trackbar
        cv2.namedWindow(window_name)
        
        # Get first frame to determine size
        buffer = self.compressed_frames[0]
        first_frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        frame_height, frame_width = first_frame.shape[:2]
        
        print(f"Playback window: {frame_width}x{frame_height}")
        
        # Create trackbar (slider)
        total_frames = len(self.compressed_frames)
        cv2.createTrackbar('Frame', window_name, 0, total_frames - 1, lambda x: None)
        
        current_frame = 0
        
        try:
            while True:
                # Check if window still exists
                try:
                    # Get trackbar position (user may have moved slider)
                    trackbar_pos = cv2.getTrackbarPos('Frame', window_name)
                    current_frame = trackbar_pos
                except cv2.error:
                    # Window was closed
                    break
                
                # Decode and display current frame (no overlays)
                buffer = self.compressed_frames[current_frame]
                frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
                
                cv2.imshow(window_name, frame)
                
                # Just wait for window close
                if cv2.waitKey(30) & 0xFF == 27:  # ESC to exit
                    break
        except Exception as e:
            print(f"Playback error: {e}")
        finally:
            # Ensure window is destroyed
            try:
                cv2.destroyWindow(window_name)
            except:
                pass
        
    def get_memory_usage_mb(self):
        """Get approximate memory usage"""
        total_bytes = sum(len(buf) for buf in self.compressed_frames)
        return total_bytes / (1024 * 1024)


class ColorPicker:
    """Zoom window color picker - click to select a color"""
    
    def __init__(self, callback):
        """
        callback: function(bgr_color) - called when user clicks to select a color
        """
        self.callback = callback
        self.selected_color = None
        self.is_running = False
        self.click_detected = False
        
        # Screen capture setup
        import mss
        self.sct = mss.mss()
        self.monitor = self.sct.monitors[1]
        
        # Zoom settings
        self.zoom_size = 200
        self.zoom_factor = 4
        self.capture_size = self.zoom_size // self.zoom_factor
        self.info_height = 70  # Extra height for instructions
        
        # Window setup
        self.window_name = f'Color Picker - {id(self)}'  # Unique window name
        
    def get_cursor_pos(self):
        """Get cursor position"""
        return win32api.GetCursorPos()
    
    def capture_around_cursor(self, x, y):
        """Capture area around cursor position"""
        half_size = self.capture_size // 2
        left = max(0, x - half_size)
        top = max(0, y - half_size)
        width = self.capture_size
        height = self.capture_size
        
        # Adjust if near screen edges
        if left + width > self.monitor["width"]:
            left = self.monitor["width"] - width
        if top + height > self.monitor["height"]:
            top = self.monitor["height"] - height
        
        # Capture region
        region = {
            "left": left,
            "top": top,
            "width": width,
            "height": height
        }
        
        screenshot = self.sct.grab(region)
        img = np.array(screenshot)
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        
        return img, left, top
    
    def on_mouse_event(self, nCode, wParam, lParam):
        """Global mouse hook callback"""
        if self.is_running and wParam == 0x0201:  # WM_LBUTTONDOWN
            self.click_detected = True
            return 1  # Consume the click
        return 0
    
    def run(self):
        """Start the color picker"""
        if self.is_running:
            return  # Already running, don't start again
            
        self.is_running = True
        self.selected_color = None
        self.click_detected = False
        
        # Set up global mouse hook
        def mouse_callback(nCode, wParam, lParam):
            return self.on_mouse_event(nCode, wParam, lParam)
        
        import pynput
        from pynput import mouse
        
        mouse_listener = None
        
        def on_click(x, y, button, pressed):
            """Handle mouse clicks"""
            if pressed and button == mouse.Button.left and self.is_running:
                self.click_detected = True
                return False  # Stop listener
        
        # Start mouse listener in separate thread
        mouse_listener = mouse.Listener(on_click=on_click)
        mouse_listener.start()
        
        # Create window
        cv2.namedWindow(self.window_name, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(self.window_name, cv2.WND_PROP_TOPMOST, 1)
        
        # Remove window decorations
        time.sleep(0.05)
        hwnd = win32gui.FindWindow(None, self.window_name)
        if hwnd:
            style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
            style &= ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)
            win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
            win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 
                                 self.zoom_size, self.zoom_size + self.info_height,
                                 win32con.SWP_NOMOVE | win32con.SWP_FRAMECHANGED)
        
        try:
            while self.is_running:
                # Check if click was detected
                if self.click_detected and self.selected_color is not None:
                    self.callback(self.selected_color)
                    self.is_running = False
                    break
                
                # Get cursor position
                cursor_x, cursor_y = self.get_cursor_pos()
                
                # Capture area around cursor
                img, left, top = self.capture_around_cursor(cursor_x, cursor_y)
                
                # Zoom in
                zoomed = cv2.resize(img, (self.zoom_size, self.zoom_size), interpolation=cv2.INTER_NEAREST)
                
                # Draw crosshair
                center = self.zoom_size // 2
                crosshair_size = 10
                cv2.line(zoomed, (center - crosshair_size, center), (center + crosshair_size, center), (0, 0, 255), 2)
                cv2.line(zoomed, (center, center - crosshair_size), (center, center + crosshair_size), (0, 0, 255), 2)
                
                # Get color at cursor
                center_pixel_y = cursor_y - top
                center_pixel_x = cursor_x - left
                center_pixel_y = max(0, min(center_pixel_y, img.shape[0] - 1))
                center_pixel_x = max(0, min(center_pixel_x, img.shape[1] - 1))
                
                color_bgr = img[center_pixel_y, center_pixel_x]
                b, g, r = color_bgr
                self.selected_color = [int(b), int(g), int(r)]
                
                # Create display
                display = np.ones((self.zoom_size + self.info_height, self.zoom_size, 3), dtype=np.uint8) * 40
                display[:self.zoom_size, :] = zoomed
                
                # Add border
                cv2.rectangle(display, (0, 0), (self.zoom_size-1, self.zoom_size-1), (255, 255, 255), 2)
                
                # Add color info
                color_text = f"BGR: ({int(b)}, {int(g)}, {int(r)})"
                cv2.putText(display, color_text, (10, self.zoom_size + 20), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
                
                # Add instructions
                instruction_text = "Click anywhere to select | ESC to cancel"
                cv2.putText(display, instruction_text, (10, self.zoom_size + 45), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)
                
                # Display
                cv2.imshow(self.window_name, display)
                
                # Move window to follow cursor
                offset_x = 30
                offset_y = 30
                win_x = cursor_x + offset_x
                win_y = cursor_y + offset_y
                
                if win_x + self.zoom_size > self.monitor["width"]:
                    win_x = cursor_x - self.zoom_size - offset_x
                if win_y + self.zoom_size + self.info_height > self.monitor["height"]:
                    win_y = cursor_y - self.zoom_size - self.info_height - offset_y
                
                if hwnd:
                    win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, win_x, win_y, 
                                         self.zoom_size, self.zoom_size + self.info_height,
                                         win32con.SWP_NOSIZE)
                
                # Check for ESC to cancel
                key = cv2.waitKey(30) & 0xFF  # 30ms delay for smooth updates
                if key == 27:  # ESC
                    self.is_running = False
                    self.selected_color = None
                    break
                    
        except Exception as e:
            print(f"ColorPicker error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                if mouse_listener:
                    mouse_listener.stop()
            except:
                pass
            try:
                cv2.destroyWindow(self.window_name)
            except:
                pass
            try:
                self.sct.close()
            except:
                pass


class SimpleApp:
    storage = {
        "config": {
            "hotkeys": {"start_stop": "F3", "change_scan": "F1", "exit": "F4"},
            "areas": {"shake": {"x": 530, "y": 235, "width": 1500, "height": 665},
                     "fish": {"x": 765, "y": 1217, "width": 1032, "height": 38}},
            "toggles": {"always_on_top": True, "auto_minimize": True, "auto_move_roblox": True, "auto_focus_roblox": True, "auto_zoom_in": True, "auto_select_rod": True, "perfect_cast_overlay": True, "fish_overlay": True},
            "protected_rods": ["Default"],
            "hotbar": {"fishing_rod": "1", "equipment_bag": "2"},
            "auto_select_rod": {"delay1": "0.0", "delay2": "0.5", "delay3": "0.1"},
            "auto_zoom_in": {"delay1": "0.0", "zoom_in_amount": "12", "delay2": "0.25", "zoom_out_amount": "1", "delay3": "0.0"},
            "cast": {"method": "Perfect", "auto_look_down": True, "green_tolerance": 5, "white_tolerance": 5,
                     "fail_release_timeout": 20.0, "release_timing": 0.0, "delay1": "0.0", "delay2": "0.0", "delay3": "0.0", "delay4": "1.2",
                     "capture_mode": "Windows Capture",
                     "normal_delay1": "0.0", "normal_delay2": "0.5", "normal_delay3": "1.0"},
            "shake": {"method": "Pixel",
                     "pixel_white_tolerance": 0, "pixel_duplicate_bypass": 1.0, "pixel_double_click": False, "pixel_double_click_delay": 25,
                     "fail_shake_timeout": 5.0,
                     "navigation_spam_delay": 25, "navigation_fail_timeout": 30.0},
            "fish": {"method": "Color",
                    "delay_after_end": 1.0,
                    "rod_type": "Default",
                    "move_check_stabilize_threshold": 10,
                    "move_check_movement_threshold_percent": 0.005,
                    "kp": 0.5,
                    "kd": 0.3,
                    "velocity_smoothing": 0.2,
                    "stopping_distance_multiplier": 3.0,
                    "rods": {
                        "Default": {
                            "target_colors": [[91, 75, 67]],  # List of BGR color tuples: [[B, G, R], ...]
                            "bar_colors": [[255, 255, 255], [241, 241, 241], [69, 96, 75], [67, 92, 74], [65, 87, 75], [64, 84, 77], [62, 81, 77], [59, 76, 78], [57, 71, 78], [54, 67, 78], [52, 62, 79], [48, 57, 79], [46, 53, 80], [46, 50, 82], [42, 46, 81], [41, 42, 82], [39, 40, 83], [37, 36, 83]],
                            "target_tolerance": 0,
                            "bar_tolerance": 5
                        }
                    }},
            "state_check": {"green_tolerance": 5, "top_corner_ratio": 80, "right_corner_ratio": 25},
        },
    }

    @staticmethod
    def _get_config_path():
        """Get the path to Config.txt in the same directory as the script/exe"""
        if getattr(sys, 'frozen', False):
            # Running as compiled exe
            app_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(app_dir, "Config.txt")

    def _load_config(self):
        """Load config from Config.txt if it exists, otherwise use defaults"""
        config_path = self._get_config_path()
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    loaded_storage = json.load(f)
                    self.storage = loaded_storage
                    print(f"Config loaded from: {config_path}")
            except Exception as e:
                print(f"Error loading config: {e}")
                print("Using default configuration")
                self._save_config()  # Save defaults
        else:
            # Config doesn't exist yet - will be created with defaults
            print(f"Config doesn't exist yet. Will create: {config_path}")
            self._save_config()

    def _save_config(self):
        """Save current config to Config.txt"""
        config_path = self._get_config_path()
        
        try:
            with open(config_path, 'w') as f:
                json.dump(self.storage, f, indent=4)
            print(f"Config saved to: {config_path}")
        except Exception as e:
            print(f"Error saving config: {e}")

    def __init__(self):
        # Load config before setting up UI
        self._load_config()
        
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.root = ctk.CTk()
        self.root.title("IRUS Idiotproof")
        
        # Add window close protocol to save config
        self.root.protocol("WM_DELETE_WINDOW", self._on_window_close)

        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        window_width = min(int(screen_width * 0.8), 800)
        window_height = min(int(screen_height * 0.8), 600)

        self.root.geometry(f"{window_width}x{window_height}")
        self.root.minsize(500, 300)
        self.root.resizable(True, True)

        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Resolution scaling
        self.current_width = screen_width
        self.current_height = screen_height
        self.scale_x = self.current_width / 2560
        self.scale_y = self.current_height / 1440

        self._scale_default_areas()
        self.root.after(0, self._center_window)

        # Hotkey state
        self.hotkey_labels = {"start_stop": None, "change_scan": None, "exit": None}
        self.waiting_for_hotkey = False
        self.hotkey_waiting_for = None
        self.hotkey_listeners = {}

        # Hotbar state
        self.waiting_for_hotbar = False
        self.hotbar_waiting_for = None
        self.fishing_rod_hotbar = self.storage["config"]["hotbar"]["fishing_rod"]
        self.equipment_bag_hotbar = self.storage["config"]["hotbar"]["equipment_bag"]

        # Auto Select Rod delays
        self.auto_rod_delay1 = self.storage["config"]["auto_select_rod"]["delay1"]
        self.auto_rod_delay2 = self.storage["config"]["auto_select_rod"]["delay2"]
        self.auto_rod_delay3 = self.storage["config"]["auto_select_rod"]["delay3"]

        # Area selector state
        self.area_selector_active = False
        
        # Color picker state
        self.active_color_picker = None

        # Loop state
        self.is_running = False
        self.stop_event = threading.Event()  # Event-based interruption

        # Video recording state
        self.video_recorder = None
        self.is_recording_video = False
        self.recording_thread = None
        self.video_has_data = False

        # Toggle states (load from centralized storage)
        self.always_on_top = self.storage["config"]["toggles"]["always_on_top"]
        self.auto_minimize = self.storage["config"]["toggles"]["auto_minimize"]
        self.auto_move_roblox = self.storage["config"]["toggles"]["auto_move_roblox"]
        self.auto_focus_roblox = self.storage["config"]["toggles"]["auto_focus_roblox"]
        self.auto_zoom_in = self.storage["config"]["toggles"]["auto_zoom_in"]
        self.auto_select_rod = self.storage["config"]["toggles"]["auto_select_rod"]
        self.perfect_cast_overlay = self.storage["config"]["toggles"]["perfect_cast_overlay"]
        self.fish_overlay = self.storage["config"]["toggles"]["fish_overlay"]

        # Auto Zoom In settings
        self.auto_zoom_in_delay1 = self.storage["config"]["auto_zoom_in"]["delay1"]
        self.auto_zoom_in_amount = self.storage["config"]["auto_zoom_in"]["zoom_in_amount"]
        self.auto_zoom_in_delay2 = self.storage["config"]["auto_zoom_in"]["delay2"]
        self.auto_zoom_out_amount = self.storage["config"]["auto_zoom_in"]["zoom_out_amount"]
        self.auto_zoom_in_delay3 = self.storage["config"]["auto_zoom_in"]["delay3"]

        # Cast settings
        self.auto_look_down = self.storage["config"]["cast"]["auto_look_down"]
        self.green_tolerance = self.storage["config"]["cast"]["green_tolerance"]
        self.white_tolerance = self.storage["config"]["cast"]["white_tolerance"]
        self.fail_release_timeout = self.storage["config"]["cast"]["fail_release_timeout"]
        self.release_timing = self.storage["config"]["cast"]["release_timing"]
        self.cast_delay1 = self.storage["config"]["cast"]["delay1"]
        self.cast_delay2 = self.storage["config"]["cast"]["delay2"]
        self.cast_delay3 = self.storage["config"]["cast"]["delay3"]
        self.cast_delay4 = self.storage["config"]["cast"]["delay4"]
        self.normal_cast_delay1 = self.storage["config"]["cast"]["normal_delay1"]
        self.normal_cast_delay2 = self.storage["config"]["cast"]["normal_delay2"]
        self.normal_cast_delay3 = self.storage["config"]["cast"]["normal_delay3"]

        # Setup hotkeys after window is fully created
        self.root.after(100, self._setup_global_hotkeys)
        self.root.bind("<Key>", self._on_key_press)
        self.create_widgets()
        
        # Apply always on top at startup if enabled
        if self.always_on_top:
            self.root.attributes('-topmost', True)
            self.root.bind('<FocusIn>', self._maintain_topmost)
            self.root.bind('<Visibility>', self._maintain_topmost)

    def _scale_default_areas(self):
        """Scale areas based on resolution"""
        fish_presets = {
            (2560, 1440): {"x": 764, "y": 1216, "width": 1030, "height": 40},
            (1920, 1200): {"x": 573, "y": 1015, "width": 772, "height": 30},
            (1920, 1080): {"x": 573, "y": 909, "width": 773, "height": 30},
            (1680, 1050): {"x": 502, "y": 886, "width": 675, "height": 26},
            (1600, 1200): {"x": 477, "y": 1019, "width": 644, "height": 26},
            (1280, 1024): {"x": 382, "y": 869, "width": 515, "height": 20},
            (1280, 800): {"x": 382, "y": 672, "width": 514, "height": 19},
            (1280, 720): {"x": 382, "y": 602, "width": 514, "height": 19},
            (1024, 768): {"x": 304, "y": 647, "width": 414, "height": 17},
            (800, 600): {"x": 238, "y": 502, "width": 322, "height": 13},
        }

        shake_presets = {(2560, 1440): {"x": 530, "y": 235, "width": 1500, "height": 665}}

        current_res = (self.current_width, self.current_height)

        # Fish area
        if current_res in fish_presets:
            scaled_fish = fish_presets[current_res]
        else:
            scaled_fish = {
                "x": round(0.299414 * self.current_width - 1.63),
                "y": round(0.858462 * self.current_height - 14.01),
                "width": round(0.401687 * self.current_width + 0.87),
                "height": round(0.024583 * self.current_height - 0.84),
            }

        # Shake area
        if current_res in shake_presets:
            scaled_shake = shake_presets[current_res]
        else:
            shake_default = {"x": 530, "y": 235, "width": 1500, "height": 665}
            scaled_shake = {
                "x": round(shake_default["x"] * self.scale_x),
                "y": round(shake_default["y"] * self.scale_y),
                "width": round(shake_default["width"] * self.scale_x),
                "height": round(shake_default["height"] * self.scale_y),
            }

        self.storage["config"]["areas"]["fish"] = scaled_fish
        self.storage["config"]["areas"]["shake"] = scaled_shake

    def _validate_delay_input(self, action, index, value_if_allowed, prior_value, text, validation_type, trigger_type, widget_name):
        """Validate that input is a valid decimal number"""
        # Allow empty string
        if value_if_allowed == "":
            return True
        
        # Allow deletion
        if action == "0":  # deletion
            return True
        
        # Check if the result would be a valid number format
        try:
            # Allow just a decimal point or numbers with decimal
            if value_if_allowed == ".":
                return True
            # Allow numbers that start with decimal
            if value_if_allowed.startswith(".") and value_if_allowed[1:].replace(".", "").isdigit():
                return True
            # Check if it's a valid float format (allows multiple decimals during typing)
            if value_if_allowed.replace(".", "", 1).isdigit():
                return True
            return False
        except:
            return False

    def _save_delay_values(self, event=None):
        """Save delay values to storage"""
        try:
            value1 = self.auto_rod_delay1_entry.get()
            self.storage["config"]["auto_select_rod"]["delay1"] = value1 if value1 else "0.0"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value2 = self.auto_rod_delay2_entry.get()
            self.storage["config"]["auto_select_rod"]["delay2"] = value2 if value2 else "0.0"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value3 = self.auto_rod_delay3_entry.get()
            self.storage["config"]["auto_select_rod"]["delay3"] = value3 if value3 else "0.0"
        except (AttributeError, tk.TclError):
            pass

    def _save_zoom_values(self, event=None):
        """Save zoom values to storage"""
        try:
            value1 = self.auto_zoom_in_delay1_entry.get()
            self.storage["config"]["auto_zoom_in"]["delay1"] = value1 if value1 else "0.0"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value2 = self.auto_zoom_in_amount_entry.get()
            self.storage["config"]["auto_zoom_in"]["zoom_in_amount"] = value2 if value2 else "12"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value3 = self.auto_zoom_in_delay2_entry.get()
            self.storage["config"]["auto_zoom_in"]["delay2"] = value3 if value3 else "0.0"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value4 = self.auto_zoom_out_amount_entry.get()
            self.storage["config"]["auto_zoom_in"]["zoom_out_amount"] = value4 if value4 else "1"
        except (AttributeError, tk.TclError):
            pass
        
        try:
            value5 = self.auto_zoom_in_delay3_entry.get()
            self.storage["config"]["auto_zoom_in"]["delay3"] = value5 if value5 else "0.0"
        except (AttributeError, tk.TclError):
            pass

    def _center_window(self):
        """Center the window on screen"""
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = (self.root.winfo_screenwidth() // 2) - (width // 2)
        y = (self.root.winfo_screenheight() // 2) - (height // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def create_widgets(self):
        """Create the main GUI"""
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(4, weight=1)  # Make column 4 expand to fill space

        # Title
        title_label = ctk.CTkLabel(self.main_frame, text="IRUS Idiotproof - made for the disabled", 
                                   font=ctk.CTkFont(size=18, weight="bold"))
        title_label.grid(row=0, column=0, pady=15, sticky="w", padx=10)

        # YouTube button
        youtube_btn = ctk.CTkButton(self.main_frame, text="Youtube", width=100,
                                    command=lambda: webbrowser.open("https://www.youtube.com/@AsphaltCake/?sub_confirmation=1"))
        youtube_btn.grid(row=0, column=1, pady=15, padx=5, sticky="w")

        # Discord button
        discord_btn = ctk.CTkButton(self.main_frame, text="Discord", width=100,
                                   command=lambda: webbrowser.open("https://discord.gg/vKVBbyfHTD"))
        discord_btn.grid(row=0, column=2, pady=15, padx=5, sticky="w")

        # PayPal button
        paypal_btn = ctk.CTkButton(self.main_frame, text="Paypal", width=100,
                                  command=lambda: webbrowser.open("https://www.paypal.com/paypalme/JLim862"))
        paypal_btn.grid(row=0, column=3, pady=15, padx=5, sticky="w")

        # Tabs
        self.tabview = ctk.CTkTabview(self.main_frame, anchor="w")
        self.tabview.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=5, pady=5)
        self.tabview.add("Basic")
        self.tabview.add("Misc")
        self.tabview.add("Cast")
        self.tabview.add("Shake")
        self.tabview.add("Fish")

        self._create_basic_tab()
        self._create_misc_tab()
        self._create_cast_tab()
        self._create_shake_tab()
        self._create_fish_tab()
        
        # Create color manager frame (hidden initially)
        self._create_color_manager_frame()

    def _create_basic_tab(self):
        """Create the Basic tab with hotkey settings"""
        parent = self.tabview.tab("Basic")
        
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(3, weight=1)  # Make column 3 expand to fill space

        row = 0  # Dynamic row counter
        
        # Capture Settings Section
        capture_settings_label = ctk.CTkLabel(scroll_frame, text="Capture Settings", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        capture_settings_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))
        row += 1

        # Capture Mode Selection
        capture_mode_label = ctk.CTkLabel(scroll_frame, text="Capture Mode:", font=ctk.CTkFont(size=12))
        capture_mode_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.capture_mode_var = tk.StringVar(value=self.storage["config"].get("capture_mode", "Windows Capture"))
        capture_mode_menu = ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.capture_mode_var,
            values=["Windows Capture", "MSS"],
            width=150,
            command=self._on_capture_mode_change
        )
        capture_mode_menu.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Separator (spans full width)
        separator_capture = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30")
        separator_capture.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1
        
        # Hotkey Settings Section
        hotkeys_label = ctk.CTkLabel(scroll_frame, text="Hotkey Settings", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        hotkeys_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))
        row += 1

        hotkeys = self.storage["config"]["hotkeys"]

        # Start/Stop hotkey
        label = ctk.CTkLabel(scroll_frame, text="Start/Stop:", font=ctk.CTkFont(size=12))
        label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.hotkey_labels["start_stop"] = ctk.CTkLabel(
            scroll_frame, text=hotkeys["start_stop"],
            font=ctk.CTkFont(size=12, weight="bold"), text_color="green"
        )
        self.hotkey_labels["start_stop"].grid(row=row, column=1, sticky="w", padx=10, pady=8)
        btn = ctk.CTkButton(scroll_frame, text="Rebind Hotkey", command=lambda: self._start_rebind("start_stop"), width=120)
        btn.grid(row=row, column=2, sticky="w", padx=10, pady=8)
        row += 1

        # Change Scan Area hotkey
        label = ctk.CTkLabel(scroll_frame, text="Change Scan Area:", font=ctk.CTkFont(size=12))
        label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.hotkey_labels["change_scan"] = ctk.CTkLabel(
            scroll_frame, text=hotkeys["change_scan"],
            font=ctk.CTkFont(size=12, weight="bold"), text_color="green"
        )
        self.hotkey_labels["change_scan"].grid(row=row, column=1, sticky="w", padx=10, pady=8)
        btn = ctk.CTkButton(scroll_frame, text="Rebind Hotkey", command=lambda: self._start_rebind("change_scan"), width=120)
        btn.grid(row=row, column=2, sticky="w", padx=10, pady=8)
        row += 1

        # Exit hotkey
        label = ctk.CTkLabel(scroll_frame, text="Exit:", font=ctk.CTkFont(size=12))
        label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        self.hotkey_labels["exit"] = ctk.CTkLabel(
            scroll_frame, text=hotkeys["exit"],
            font=ctk.CTkFont(size=12, weight="bold"), text_color="green"
        )
        self.hotkey_labels["exit"].grid(row=row, column=1, sticky="w", padx=10, pady=8)
        btn = ctk.CTkButton(scroll_frame, text="Rebind Hotkey", command=lambda: self._start_rebind("exit"), width=120)
        btn.grid(row=row, column=2, sticky="w", padx=10, pady=8)
        row += 1

        # Separator (spans full width)
        separator1 = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30")
        separator1.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1

        # Hotbar Settings Section
        hotbar_label = ctk.CTkLabel(scroll_frame, text="Hotbar Settings", 
                                    font=ctk.CTkFont(size=14, weight="bold"))
        hotbar_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(5, 5))
        row += 1

        # Fishing Rod hotbar
        fishing_rod_label = ctk.CTkLabel(scroll_frame, text="Fishing Rod:", font=ctk.CTkFont(size=12))
        fishing_rod_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.fishing_rod_value = ctk.CTkLabel(
            scroll_frame, text=self.fishing_rod_hotbar,
            font=ctk.CTkFont(size=12, weight="bold"), text_color="green"
        )
        self.fishing_rod_value.grid(row=row, column=1, sticky="w", padx=10, pady=8)

        fishing_rod_btn = ctk.CTkButton(scroll_frame, text="Rebind Hotbar", command=lambda: self._start_rebind_hotbar("fishing_rod"), width=120)
        fishing_rod_btn.grid(row=row, column=2, sticky="w", padx=10, pady=8)
        row += 1

        # Equipment Bag hotbar
        equipment_bag_label = ctk.CTkLabel(scroll_frame, text="Equipment Bag:", font=ctk.CTkFont(size=12))
        equipment_bag_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.equipment_bag_value = ctk.CTkLabel(
            scroll_frame, text=self.equipment_bag_hotbar,
            font=ctk.CTkFont(size=12, weight="bold"), text_color="green"
        )
        self.equipment_bag_value.grid(row=row, column=1, sticky="w", padx=10, pady=8)

        equipment_bag_btn = ctk.CTkButton(scroll_frame, text="Rebind Hotbar", command=lambda: self._start_rebind_hotbar("equipment_bag"), width=120)
        equipment_bag_btn.grid(row=row, column=2, sticky="w", padx=10, pady=8)
        row += 1

        # Separator (spans full width)
        separator2 = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30")
        separator2.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1

        # State Check Settings Section
        state_check_label = ctk.CTkLabel(scroll_frame, text="State Check Settings", 
                                         font=ctk.CTkFont(size=14, weight="bold"))
        state_check_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(5, 5))
        row += 1

        # Green Tolerance
        green_tolerance_label = ctk.CTkLabel(scroll_frame, text="Green Tolerance:", font=ctk.CTkFont(size=12))
        green_tolerance_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        green_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())

        self.state_check_green_tolerance_var = tk.IntVar(value=self.storage["config"]["state_check"].get("green_tolerance", 0))
        green_tolerance_slider = ctk.CTkSlider(
            scroll_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.state_check_green_tolerance_var,
            command=self._on_state_check_green_tolerance_change,
            width=200
        )
        green_tolerance_slider.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        
        self.state_check_green_tolerance_value_label = ctk.CTkLabel(scroll_frame, text=str(self.state_check_green_tolerance_var.get()), font=ctk.CTkFont(size=12))
        self.state_check_green_tolerance_value_label.grid(row=row, column=2, sticky="w", padx=5, pady=5)
        self.state_check_green_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1

        # Top Corner Ratio
        top_corner_ratio_label = ctk.CTkLabel(scroll_frame, text="Top Corner Ratio:", font=ctk.CTkFont(size=12))
        top_corner_ratio_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        top_corner_ratio_label.bind("<Button-1>", lambda e: self.root.focus())

        self.top_corner_ratio_var = tk.IntVar(value=self.storage["config"]["state_check"].get("top_corner_ratio", 85))
        top_corner_ratio_slider = ctk.CTkSlider(
            scroll_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.top_corner_ratio_var,
            command=self._on_top_corner_ratio_change,
            width=200
        )
        top_corner_ratio_slider.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        
        self.top_corner_ratio_value_label = ctk.CTkLabel(scroll_frame, text=f"{self.top_corner_ratio_var.get()}%", font=ctk.CTkFont(size=12))
        self.top_corner_ratio_value_label.grid(row=row, column=2, sticky="w", padx=5, pady=5)
        self.top_corner_ratio_value_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1

        # Right Corner Ratio
        right_corner_ratio_label = ctk.CTkLabel(scroll_frame, text="Right Corner Ratio:", font=ctk.CTkFont(size=12))
        right_corner_ratio_label.grid(row=row, column=0, sticky="w", padx=10, pady=5)
        right_corner_ratio_label.bind("<Button-1>", lambda e: self.root.focus())

        self.right_corner_ratio_var = tk.IntVar(value=self.storage["config"]["state_check"].get("right_corner_ratio", 20))
        right_corner_ratio_slider = ctk.CTkSlider(
            scroll_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.right_corner_ratio_var,
            command=self._on_right_corner_ratio_change,
            width=200
        )
        right_corner_ratio_slider.grid(row=row, column=1, sticky="w", padx=10, pady=5)
        
        self.right_corner_ratio_value_label = ctk.CTkLabel(scroll_frame, text=f"{self.right_corner_ratio_var.get()}%", font=ctk.CTkFont(size=12))
        self.right_corner_ratio_value_label.grid(row=row, column=2, sticky="w", padx=5, pady=5)
        self.right_corner_ratio_value_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1

        # Separator (spans full width)
        separator3 = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30")
        separator3.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1

        # Overlay Settings Section
        overlay_label = ctk.CTkLabel(scroll_frame, text="Overlay Settings", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        overlay_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(5, 5))
        row += 1

        # Perfect Cast Overlay
        perfect_cast_overlay_label = ctk.CTkLabel(scroll_frame, text="Perfect Cast Overlay:", font=ctk.CTkFont(size=12))
        perfect_cast_overlay_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.perfect_cast_overlay_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.perfect_cast_overlay else "OFF", width=100,
            command=self._toggle_perfect_cast_overlay,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.perfect_cast_overlay:
            self.perfect_cast_overlay_switch.select()
        else:
            self.perfect_cast_overlay_switch.deselect()
        self.perfect_cast_overlay_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Fish Overlay
        fish_overlay_label = ctk.CTkLabel(scroll_frame, text="Fish Overlay:", font=ctk.CTkFont(size=12))
        fish_overlay_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.fish_overlay_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.fish_overlay else "OFF", width=100,
            command=self._toggle_fish_overlay,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.fish_overlay:
            self.fish_overlay_switch.select()
        else:
            self.fish_overlay_switch.deselect()
        self.fish_overlay_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Separator (spans full width)
        separator3 = ctk.CTkFrame(scroll_frame, height=2, fg_color="gray30")
        separator3.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1

        # GUI Settings Section
        gui_settings_label = ctk.CTkLabel(scroll_frame, text="GUI Settings", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        gui_settings_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(5, 5))
        row += 1

        # Always On Top
        always_on_top_label = ctk.CTkLabel(scroll_frame, text="Always On Top:", font=ctk.CTkFont(size=12))
        always_on_top_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.always_on_top_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.always_on_top else "OFF", width=100,
            command=self._toggle_always_on_top,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.always_on_top:
            self.always_on_top_switch.select()
        else:
            self.always_on_top_switch.deselect()
        self.always_on_top_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Auto Minimize
        auto_minimize_label = ctk.CTkLabel(scroll_frame, text="Auto Minimize:", font=ctk.CTkFont(size=12))
        auto_minimize_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.auto_minimize_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.auto_minimize else "OFF", width=100,
            command=self._toggle_auto_minimize,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.auto_minimize:
            self.auto_minimize_switch.select()
        else:
            self.auto_minimize_switch.deselect()
        self.auto_minimize_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Auto Focus Roblox
        auto_focus_label = ctk.CTkLabel(scroll_frame, text="Auto Focus Roblox:", font=ctk.CTkFont(size=12))
        auto_focus_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.auto_focus_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.auto_focus_roblox else "OFF", width=100,
            command=self._toggle_auto_focus_roblox,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.auto_focus_roblox:
            self.auto_focus_switch.select()
        else:
            self.auto_focus_switch.deselect()
        self.auto_focus_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

        # Auto Move Roblox
        auto_move_roblox_label = ctk.CTkLabel(scroll_frame, text="Auto Move Roblox:", font=ctk.CTkFont(size=12))
        auto_move_roblox_label.grid(row=row, column=0, sticky="w", padx=10, pady=8)
        
        self.auto_move_roblox_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.auto_move_roblox else "OFF", width=100,
            command=self._toggle_auto_move_roblox,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.auto_move_roblox:
            self.auto_move_roblox_switch.select()
        else:
            self.auto_move_roblox_switch.deselect()
        self.auto_move_roblox_switch.grid(row=row, column=1, sticky="w", padx=10, pady=8)
        row += 1

    def _create_fish_tab(self):
        """Create the Fish tab with fish method settings"""
        parent = self.tabview.tab("Fish")
        
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(1, weight=1)

        # Fish Settings Section
        fish_label = ctk.CTkLabel(scroll_frame, text="Fish Settings", 
                                  font=ctk.CTkFont(size=14, weight="bold"))
        fish_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        # Fish Method
        fish_method_label = ctk.CTkLabel(scroll_frame, text="Fish Method:", font=ctk.CTkFont(size=12))
        fish_method_label.grid(row=1, column=0, sticky="w", padx=10, pady=8)
        
        self.fish_method_var = tk.StringVar(value=self.storage["config"]["fish"]["method"])
        fish_method_menu = ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.fish_method_var,
            values=["Color", "Disabled"],
            width=150,
            command=self._on_fish_method_change
        )
        fish_method_menu.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        # Disabled Fish Section (row 2)
        self.disabled_fish_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.disabled_fish_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        disabled_fish_label = ctk.CTkLabel(self.disabled_fish_frame, text="Fish is disabled", 
                                           font=ctk.CTkFont(size=13), text_color="gray60")
        disabled_fish_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))

        # Color Fish Settings Section (row 3)
        self.color_fish_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.color_fish_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        color_fish_header = ctk.CTkLabel(self.color_fish_frame, text="Color Fish Settings", 
                                          font=ctk.CTkFont(size=13, weight="bold"))
        color_fish_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))
        
        # Delay After End
        delay_after_end_label = ctk.CTkLabel(self.color_fish_frame, text="Delay After End:", font=ctk.CTkFont(size=12))
        delay_after_end_label.grid(row=1, column=0, sticky="w", padx=20, pady=5)
        delay_after_end_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.delay_after_end_var = tk.DoubleVar(value=self.storage["config"]["fish"]["delay_after_end"])
        delay_after_end_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.0,
            to=10.0,
            number_of_steps=100,
            variable=self.delay_after_end_var,
            command=self._on_delay_after_end_change,
            width=200
        )
        delay_after_end_slider.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        self.delay_after_end_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.delay_after_end_var.get():.1f}s", font=ctk.CTkFont(size=12))
        self.delay_after_end_value_label.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.delay_after_end_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Gap
        gap_label = ctk.CTkLabel(self.color_fish_frame, text="")
        gap_label.grid(row=2, column=0, columnspan=3, pady=5)
        
        # Rod Type
        rod_type_label = ctk.CTkLabel(self.color_fish_frame, text="Rod Type:", font=ctk.CTkFont(size=12))
        rod_type_label.grid(row=3, column=0, sticky="w", padx=20, pady=5)
        rod_type_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Get available rod types from storage
        available_rods = list(self.storage["config"]["fish"].get("rods", {"Default": {}}).keys())
        current_rod = self.storage["config"]["fish"].get("rod_type", "Default")
        if current_rod not in available_rods:
            current_rod = "Default"
            self.storage["config"]["fish"]["rod_type"] = current_rod
        
        # Ensure current rod has tolerance values
        if current_rod in self.storage["config"]["fish"]["rods"]:
            rod_data = self.storage["config"]["fish"]["rods"][current_rod]
            if "target_tolerance" not in rod_data:
                rod_data["target_tolerance"] = 0
            if "bar_tolerance" not in rod_data:
                rod_data["bar_tolerance"] = 0
        
        self.rod_type_var = tk.StringVar(value=current_rod)
        self.rod_type_menu = ctk.CTkOptionMenu(
            self.color_fish_frame,
            variable=self.rod_type_var,
            values=available_rods,
            width=150,
            command=self._on_rod_type_change
        )
        self.rod_type_menu.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        # Add Rod Type Button
        add_rod_button = ctk.CTkButton(
            self.color_fish_frame,
            text="Add",
            width=60,
            command=self._add_rod_type
        )
        add_rod_button.grid(row=3, column=2, sticky="w", padx=(5, 0), pady=5)
        
        # Delete Rod Type Button
        delete_rod_button = ctk.CTkButton(
            self.color_fish_frame,
            text="Delete",
            width=60,
            command=self._delete_rod_type,
            fg_color="#8B0000",
            hover_color="#A52A2A"
        )
        delete_rod_button.grid(row=3, column=3, sticky="w", padx=5, pady=5)
        
        # Color Manager Button
        color_manager_label = ctk.CTkLabel(self.color_fish_frame, text="Color Manager:", font=ctk.CTkFont(size=12))
        color_manager_label.grid(row=4, column=0, sticky="w", padx=20, pady=5)
        color_manager_label.bind("<Button-1>", lambda e: self.root.focus())
        
        color_manager_button = ctk.CTkButton(
            self.color_fish_frame,
            text="Open Color Manager",
            width=150,
            command=self._open_color_manager
        )
        color_manager_button.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        
        # Target Color Tolerance
        target_tolerance_label = ctk.CTkLabel(self.color_fish_frame, text="Target Color Tolerance:", font=ctk.CTkFont(size=12))
        target_tolerance_label.grid(row=5, column=0, sticky="w", padx=20, pady=5)
        target_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Get tolerance from current rod
        current_rod_data = self.storage["config"]["fish"]["rods"].get(current_rod, {})
        current_target_tolerance = current_rod_data.get("target_tolerance", 0)
        
        self.target_tolerance_var = tk.IntVar(value=current_target_tolerance)
        target_tolerance_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.target_tolerance_var,
            command=self._on_target_tolerance_change,
            width=200
        )
        target_tolerance_slider.grid(row=5, column=1, sticky="w", padx=10, pady=5)
        
        self.target_tolerance_value_label = ctk.CTkLabel(self.color_fish_frame, text=str(current_target_tolerance), font=ctk.CTkFont(size=12))
        self.target_tolerance_value_label.grid(row=5, column=2, sticky="w", padx=5, pady=5)
        self.target_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Bar Color Tolerance
        bar_tolerance_label = ctk.CTkLabel(self.color_fish_frame, text="Bar Color Tolerance:", font=ctk.CTkFont(size=12))
        bar_tolerance_label.grid(row=6, column=0, sticky="w", padx=20, pady=5)
        bar_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Get tolerance from current rod
        current_bar_tolerance = current_rod_data.get("bar_tolerance", 0)
        
        self.bar_tolerance_var = tk.IntVar(value=current_bar_tolerance)
        bar_tolerance_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.bar_tolerance_var,
            command=self._on_bar_tolerance_change,
            width=200
        )
        bar_tolerance_slider.grid(row=6, column=1, sticky="w", padx=10, pady=5)
        
        self.bar_tolerance_value_label = ctk.CTkLabel(self.color_fish_frame, text=str(current_bar_tolerance), font=ctk.CTkFont(size=12))
        self.bar_tolerance_value_label.grid(row=6, column=2, sticky="w", padx=5, pady=5)
        self.bar_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Gap / Separator
        separator1 = ctk.CTkLabel(self.color_fish_frame, text="", font=ctk.CTkFont(size=6))
        separator1.grid(row=7, column=0, columnspan=3, pady=5)
        
        # Move Check Settings Header
        move_check_header = ctk.CTkLabel(self.color_fish_frame, text="Move Check Settings", 
                                         font=ctk.CTkFont(size=12, weight="bold"))
        move_check_header.grid(row=8, column=0, columnspan=3, sticky="w", padx=20, pady=(10, 5))
        
        # Move Check Stabilize Threshold
        stabilize_threshold_label = ctk.CTkLabel(self.color_fish_frame, text="Stabilize Threshold (frames):", font=ctk.CTkFont(size=12))
        stabilize_threshold_label.grid(row=9, column=0, sticky="w", padx=20, pady=5)
        stabilize_threshold_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.stabilize_threshold_var = tk.IntVar(value=self.storage["config"]["fish"].get("move_check_stabilize_threshold", 10))
        stabilize_threshold_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=1,
            to=30,
            number_of_steps=29,
            variable=self.stabilize_threshold_var,
            command=self._on_stabilize_threshold_change,
            width=200
        )
        stabilize_threshold_slider.grid(row=9, column=1, sticky="w", padx=10, pady=5)
        
        self.stabilize_threshold_value_label = ctk.CTkLabel(self.color_fish_frame, text=str(self.stabilize_threshold_var.get()), font=ctk.CTkFont(size=12))
        self.stabilize_threshold_value_label.grid(row=9, column=2, sticky="w", padx=5, pady=5)
        self.stabilize_threshold_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Move Check Movement Threshold Percent
        movement_threshold_label = ctk.CTkLabel(self.color_fish_frame, text="Movement Threshold (%):", font=ctk.CTkFont(size=12))
        movement_threshold_label.grid(row=10, column=0, sticky="w", padx=20, pady=5)
        movement_threshold_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.movement_threshold_var = tk.DoubleVar(value=self.storage["config"]["fish"].get("move_check_movement_threshold_percent", 0.005))
        movement_threshold_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.001,
            to=0.02,
            number_of_steps=190,
            variable=self.movement_threshold_var,
            command=self._on_movement_threshold_change,
            width=200
        )
        movement_threshold_slider.grid(row=10, column=1, sticky="w", padx=10, pady=5)
        
        self.movement_threshold_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.movement_threshold_var.get():.3f}", font=ctk.CTkFont(size=12))
        self.movement_threshold_value_label.grid(row=10, column=2, sticky="w", padx=5, pady=5)
        self.movement_threshold_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Gap / Separator
        separator2 = ctk.CTkLabel(self.color_fish_frame, text="", font=ctk.CTkFont(size=6))
        separator2.grid(row=11, column=0, columnspan=3, pady=5)
        
        # Controller Settings Header
        controller_header = ctk.CTkLabel(self.color_fish_frame, text="PD Controller Settings", 
                                         font=ctk.CTkFont(size=12, weight="bold"))
        controller_header.grid(row=12, column=0, columnspan=3, sticky="w", padx=20, pady=(10, 5))
        
        # Kp (Proportional Gain)
        kp_label = ctk.CTkLabel(self.color_fish_frame, text="Kp (Proportional Gain):", font=ctk.CTkFont(size=12))
        kp_label.grid(row=13, column=0, sticky="w", padx=20, pady=5)
        kp_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.kp_var = tk.DoubleVar(value=self.storage["config"]["fish"].get("kp", 0.5))
        kp_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.0,
            to=2.0,
            number_of_steps=200,
            variable=self.kp_var,
            command=self._on_kp_change,
            width=200
        )
        kp_slider.grid(row=13, column=1, sticky="w", padx=10, pady=5)
        
        self.kp_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.kp_var.get():.2f}", font=ctk.CTkFont(size=12))
        self.kp_value_label.grid(row=13, column=2, sticky="w", padx=5, pady=5)
        self.kp_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Kd (Derivative Gain)
        kd_label = ctk.CTkLabel(self.color_fish_frame, text="Kd (Derivative Gain):", font=ctk.CTkFont(size=12))
        kd_label.grid(row=14, column=0, sticky="w", padx=20, pady=5)
        kd_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.kd_var = tk.DoubleVar(value=self.storage["config"]["fish"].get("kd", 0.3))
        kd_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.0,
            to=2.0,
            number_of_steps=200,
            variable=self.kd_var,
            command=self._on_kd_change,
            width=200
        )
        kd_slider.grid(row=14, column=1, sticky="w", padx=10, pady=5)
        
        self.kd_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.kd_var.get():.2f}", font=ctk.CTkFont(size=12))
        self.kd_value_label.grid(row=14, column=2, sticky="w", padx=5, pady=5)
        self.kd_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Velocity Smoothing
        velocity_smoothing_label = ctk.CTkLabel(self.color_fish_frame, text="Velocity Smoothing:", font=ctk.CTkFont(size=12))
        velocity_smoothing_label.grid(row=15, column=0, sticky="w", padx=20, pady=5)
        velocity_smoothing_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.velocity_smoothing_var = tk.DoubleVar(value=self.storage["config"]["fish"].get("velocity_smoothing", 0.7))
        velocity_smoothing_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.0,
            to=1.0,
            number_of_steps=100,
            variable=self.velocity_smoothing_var,
            command=self._on_velocity_smoothing_change,
            width=200
        )
        velocity_smoothing_slider.grid(row=15, column=1, sticky="w", padx=10, pady=5)
        
        self.velocity_smoothing_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.velocity_smoothing_var.get():.2f}", font=ctk.CTkFont(size=12))
        self.velocity_smoothing_value_label.grid(row=15, column=2, sticky="w", padx=5, pady=5)
        self.velocity_smoothing_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Stopping Distance Multiplier
        stopping_distance_label = ctk.CTkLabel(self.color_fish_frame, text="Stopping Distance Multiplier:", font=ctk.CTkFont(size=12))
        stopping_distance_label.grid(row=16, column=0, sticky="w", padx=20, pady=5)
        stopping_distance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.stopping_distance_var = tk.DoubleVar(value=self.storage["config"]["fish"].get("stopping_distance_multiplier", 3.0))
        stopping_distance_slider = ctk.CTkSlider(
            self.color_fish_frame,
            from_=0.0,
            to=10.0,
            number_of_steps=100,
            variable=self.stopping_distance_var,
            command=self._on_stopping_distance_change,
            width=200
        )
        stopping_distance_slider.grid(row=16, column=1, sticky="w", padx=10, pady=5)
        
        self.stopping_distance_value_label = ctk.CTkLabel(self.color_fish_frame, text=f"{self.stopping_distance_var.get():.1f}", font=ctk.CTkFont(size=12))
        self.stopping_distance_value_label.grid(row=16, column=2, sticky="w", padx=5, pady=5)
        self.stopping_distance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Show/hide based on current method
        self._update_fish_settings_visibility()

    def _on_fish_method_change(self, value):
        """Save fish method to storage when changed"""
        self.storage["config"]["fish"]["method"] = value
        self._update_fish_settings_visibility()
    
    def _update_fish_settings_visibility(self):
        """Show/hide fish settings based on selected method"""
        method = self.fish_method_var.get()
        
        # Hide all frames first
        self.disabled_fish_frame.grid_remove()
        self.color_fish_frame.grid_remove()
        
        # Show the appropriate frame
        if method == "Disabled":
            self.disabled_fish_frame.grid()
        elif method == "Color":
            self.color_fish_frame.grid()
        # Line method has no settings frame yet
    
    # Fish setting callbacks
    def _on_rod_type_change(self, value):
        """When rod type changes, save it and update GUI with that rod's tolerances"""
        self.storage["config"]["fish"]["rod_type"] = value
        self._load_rod_tolerances(value)
    
    def _add_rod_type(self):
        """Add a new rod type with default colors"""
        dialog = ctk.CTkInputDialog(text="Enter new rod type name:", title="Add Rod Type")
        
        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        rod_name = dialog.get_input()
        
        if rod_name and rod_name.strip():
            rod_name = rod_name.strip()
            
            # Check if rod type already exists
            if rod_name in self.storage["config"]["fish"]["rods"]:
                # Show error - rod already exists
                error_dialog = ctk.CTkToplevel(self.root)
                error_dialog.title("Error")
                error_dialog.geometry("300x100")
                error_label = ctk.CTkLabel(error_dialog, text=f"Rod type '{rod_name}' already exists!", 
                                          font=ctk.CTkFont(size=12))
                error_label.pack(pady=20)
                ok_button = ctk.CTkButton(error_dialog, text="OK", command=error_dialog.destroy)
                ok_button.pack(pady=10)
                error_dialog.transient(self.root)
                error_dialog.grab_set()
                return
            
            # Create new rod type with default colors and tolerances
            self.storage["config"]["fish"]["rods"][rod_name] = {
                "target_colors": [],
                "bar_colors": [],
                "target_tolerance": 0,
                "bar_tolerance": 0
            }
            
            # Update dropdown menu
            available_rods = list(self.storage["config"]["fish"]["rods"].keys())
            self.rod_type_menu.configure(values=available_rods)
            
            # Set as current rod type and load its tolerances
            self.rod_type_var.set(rod_name)
            self.storage["config"]["fish"]["rod_type"] = rod_name
            self._load_rod_tolerances(rod_name)
    
    def _delete_rod_type(self):
        """Delete the currently selected rod type"""
        current_rod = self.rod_type_var.get()
        
        # Don't allow deleting protected rods
        protected_rods = self.storage["config"].get("protected_rods", ["Default"])
        if current_rod in protected_rods:
            error_dialog = ctk.CTkToplevel(self.root)
            error_dialog.title("Error")
            error_dialog.geometry("350x150")
            error_dialog.resizable(False, False)
            
            # Center the dialog
            error_dialog.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (error_dialog.winfo_width() // 2)
            y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (error_dialog.winfo_height() // 2)
            error_dialog.geometry(f"+{x}+{y}")
            
            error_label = ctk.CTkLabel(error_dialog, text=f"Cannot delete the '{current_rod}' rod type!\n(Protected Rod)", 
                                      font=ctk.CTkFont(size=13))
            error_label.pack(pady=30)
            ok_button = ctk.CTkButton(error_dialog, text="OK", width=100, command=error_dialog.destroy)
            ok_button.pack(pady=20)
            error_dialog.transient(self.root)
            error_dialog.grab_set()
            return
        
        # Confirmation dialog
        confirm_dialog = ctk.CTkToplevel(self.root)
        confirm_dialog.title("Confirm Delete")
        confirm_dialog.geometry("350x150")
        confirm_dialog.resizable(False, False)
        
        # Center the dialog
        confirm_dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (confirm_dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (confirm_dialog.winfo_height() // 2)
        confirm_dialog.geometry(f"+{x}+{y}")
        
        confirm_label = ctk.CTkLabel(confirm_dialog, text=f"Delete rod type '{current_rod}'?", 
                                     font=ctk.CTkFont(size=13))
        confirm_label.pack(pady=30)
        
        def confirm_delete():
            # Delete the rod type
            if current_rod in self.storage["config"]["fish"]["rods"]:
                del self.storage["config"]["fish"]["rods"][current_rod]
            
            # Update dropdown menu
            available_rods = list(self.storage["config"]["fish"]["rods"].keys())
            self.rod_type_menu.configure(values=available_rods)
            
            # Switch to Default and load its tolerances
            self.rod_type_var.set("Default")
            self.storage["config"]["fish"]["rod_type"] = "Default"
            self._load_rod_tolerances("Default")
            
            confirm_dialog.destroy()
        
        button_frame = ctk.CTkFrame(confirm_dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        yes_button = ctk.CTkButton(button_frame, text="Yes", width=100, command=confirm_delete,
                                   fg_color="#8B0000", hover_color="#A52A2A")
        yes_button.pack(side="left", padx=10)
        
        no_button = ctk.CTkButton(button_frame, text="No", width=100, command=confirm_dialog.destroy)
        no_button.pack(side="left", padx=10)
        
        confirm_dialog.transient(self.root)
        confirm_dialog.grab_set()
    
    def _open_color_manager(self):
        """Open the color manager view"""
        # Update rod type display
        current_rod = self.storage["config"]["fish"]["rod_type"]
        self.color_manager_rod_label.configure(text=f"Rod: {current_rod}")
        
        # Refresh content with current rod's colors
        self._create_color_manager_content()
        
        # Hide the main tabview
        self.tabview.grid_remove()
        
        # Show the color manager frame
        self.color_manager_frame.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=5, pady=5)
    
    def _close_color_manager(self):
        """Close the color manager and return to main view"""
        # Hide the color manager frame
        self.color_manager_frame.grid_remove()
        
        # Show the main tabview
        self.tabview.grid(row=1, column=0, columnspan=5, sticky="nsew", padx=5, pady=5)
    
    def _create_color_manager_frame(self):
        """Create the color manager frame (hidden by default)"""
        self.color_manager_frame = ctk.CTkFrame(self.main_frame)
        self.color_manager_frame.grid_rowconfigure(1, weight=1)
        self.color_manager_frame.grid_columnconfigure(0, weight=1)
        
        # Header with back button
        header_frame = ctk.CTkFrame(self.color_manager_frame, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        # Back button
        back_button = ctk.CTkButton(
            header_frame,
            text="← Back",
            width=100,
            command=self._close_color_manager
        )
        back_button.grid(row=0, column=0, padx=5, sticky="w")
        
        # Title
        title_label = ctk.CTkLabel(
            header_frame,
            text="Color Manager",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.grid(row=0, column=1, padx=20, sticky="w")
        
        # Selected Rod Type display (in a frame for visibility)
        rod_display_frame = ctk.CTkFrame(
            header_frame,
            fg_color=("gray75", "gray25"),
            corner_radius=6
        )
        rod_display_frame.grid(row=0, column=2, padx=20, sticky="w")
        
        self.color_manager_rod_label = ctk.CTkLabel(
            rod_display_frame,
            text="",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=("gray10", "gray90")
        )
        self.color_manager_rod_label.pack(padx=15, pady=8)
        
        # Content area (scrollable)
        content_scroll = ctk.CTkScrollableFrame(self.color_manager_frame, fg_color="transparent")
        content_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        content_scroll.grid_columnconfigure(0, weight=1)
        
        # Store content scroll for dynamic updates
        self.color_manager_content = content_scroll
        
        # Initial content will be created when opened
        self._create_color_manager_content()
        
        # Hide by default
        self.color_manager_frame.grid_remove()
    
    def _create_color_manager_content(self):
        """Create/update the color manager content based on selected rod"""
        # Clear existing content
        for widget in self.color_manager_content.winfo_children():
            widget.destroy()
        
        content_scroll = self.color_manager_content
        row = 0
        
        # Video Capture Section
        video_capture_label = ctk.CTkLabel(content_scroll, text="Video Capture", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        video_capture_label.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))
        row += 1
        
        # Video capture buttons
        video_button_frame = ctk.CTkFrame(content_scroll, fg_color="transparent")
        video_button_frame.grid(row=row, column=0, columnspan=4, sticky="w", padx=20, pady=10)
        
        self.record_video_button = ctk.CTkButton(
            video_button_frame,
            text="Record Video",
            width=150,
            command=self._start_video_recording
        )
        self.record_video_button.grid(row=0, column=0, padx=5)
        
        playback_video_button = ctk.CTkButton(
            video_button_frame,
            text="Playback Video",
            width=150,
            command=self._playback_video
        )
        playback_video_button.grid(row=0, column=1, padx=5)
        
        # Video status label
        self.video_status_label = ctk.CTkLabel(
            video_button_frame,
            text="No Video Data",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.video_status_label.grid(row=0, column=2, padx=20)
        
        row += 1
        
        # Separator
        separator1 = ctk.CTkFrame(content_scroll, height=2, fg_color="gray30")
        separator1.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1
        
        # Target Colors Section
        target_header_frame = ctk.CTkFrame(content_scroll, fg_color="transparent")
        target_header_frame.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))
        
        target_colors_label = ctk.CTkLabel(target_header_frame, text="Target Colors", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        target_colors_label.grid(row=0, column=0, sticky="w", padx=0)
        
        add_target_button = ctk.CTkButton(
            target_header_frame,
            text="Add Color",
            width=100,
            command=lambda: self._add_color_with_picker("target_colors")
        )
        add_target_button.grid(row=0, column=1, sticky="w", padx=10)
        
        default_target_button = ctk.CTkButton(
            target_header_frame,
            text="Default",
            width=100,
            command=lambda: self._restore_default_colors("target_colors")
        )
        default_target_button.grid(row=0, column=2, sticky="w", padx=5)
        row += 1
        
        # Display target colors
        self._display_colors(content_scroll, row, "target_colors")
        row += len(self._get_rod_colors("target_colors")) + 1
        
        # Separator
        separator2 = ctk.CTkFrame(content_scroll, height=2, fg_color="gray30")
        separator2.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1
        
        # Bar Colors Section
        bar_header_frame = ctk.CTkFrame(content_scroll, fg_color="transparent")
        bar_header_frame.grid(row=row, column=0, columnspan=4, sticky="w", padx=10, pady=(10, 5))
        
        bar_colors_label = ctk.CTkLabel(bar_header_frame, text="Bar Colors", 
                                     font=ctk.CTkFont(size=14, weight="bold"))
        bar_colors_label.grid(row=0, column=0, sticky="w", padx=0)
        
        add_bar_button = ctk.CTkButton(
            bar_header_frame,
            text="Add Color",
            width=100,
            command=lambda: self._add_color_with_picker("bar_colors")
        )
        add_bar_button.grid(row=0, column=1, sticky="w", padx=10)
        
        default_bar_button = ctk.CTkButton(
            bar_header_frame,
            text="Default",
            width=100,
            command=lambda: self._restore_default_colors("bar_colors")
        )
        default_bar_button.grid(row=0, column=2, sticky="w", padx=5)
        row += 1
        
        # Display bar colors
        self._display_colors(content_scroll, row, "bar_colors")
        row += len(self._get_rod_colors("bar_colors")) + 1
        
        # Separator
        separator3 = ctk.CTkFrame(content_scroll, height=2, fg_color="gray30")
        separator3.grid(row=row, column=0, columnspan=4, sticky="ew", padx=0, pady=15)
        row += 1
    
    def _get_rod_colors(self, color_type):
        """Get colors for the current rod type"""
        current_rod = self.storage["config"]["fish"]["rod_type"]
        if current_rod in self.storage["config"]["fish"]["rods"]:
            return self.storage["config"]["fish"]["rods"][current_rod].get(color_type, [])
        return []
    
    def _display_colors(self, parent, start_row, color_type):
        """Display list of colors with color boxes and delete buttons"""
        colors = self._get_rod_colors(color_type)
        
        if not colors:
            no_colors_label = ctk.CTkLabel(
                parent,
                text="No colors added",
                font=ctk.CTkFont(size=12),
                text_color="gray"
            )
            no_colors_label.grid(row=start_row, column=0, sticky="w", padx=30, pady=5)
            return
        
        for i, color in enumerate(colors):
            row = start_row + i
            
            # Create frame for each color entry
            color_frame = ctk.CTkFrame(parent, fg_color="transparent")
            color_frame.grid(row=row, column=0, columnspan=4, sticky="w", padx=30, pady=5)
            
            # Color value text (BGR format)
            b, g, r = color
            color_text = f"B:{b}, G:{g}, R:{r}"
            color_label = ctk.CTkLabel(
                color_frame,
                text=color_text,
                font=ctk.CTkFont(size=12),
                width=150
            )
            color_label.grid(row=0, column=0, padx=5)
            
            # Color preview box
            color_box = ctk.CTkLabel(
                color_frame,
                text="",
                width=30,
                height=20,
                fg_color=self._bgr_to_hex(color),
                corner_radius=3
            )
            color_box.grid(row=0, column=1, padx=5)
            
            # Delete button (red X)
            delete_button = ctk.CTkButton(
                color_frame,
                text="✕",
                width=30,
                height=25,
                fg_color="#8B0000",
                hover_color="#A52A2A",
                command=lambda ct=color_type, idx=i: self._delete_color(ct, idx)
            )
            delete_button.grid(row=0, column=2, padx=5)
    
    def _bgr_to_hex(self, bgr_color):
        """Convert BGR tuple to hex color string"""
        b, g, r = bgr_color
        return f"#{r:02x}{g:02x}{b:02x}"
    
    def _delete_color(self, color_type, index):
        """Delete a color from the current rod's color list"""
        current_rod = self.storage["config"]["fish"]["rod_type"]
        if current_rod in self.storage["config"]["fish"]["rods"]:
            colors = self.storage["config"]["fish"]["rods"][current_rod].get(color_type, [])
            if 0 <= index < len(colors):
                deleted_color = colors.pop(index)
                print(f"Deleted {color_type} color at index {index}: {deleted_color}")
                # Refresh the color manager display
                self._create_color_manager_content()
    
    def _add_color_with_picker(self, color_type):
        """Open color picker to add a color to the specified color type"""
        # Don't allow multiple pickers at once
        if self.active_color_picker is not None and self.active_color_picker.is_running:
            print("Color picker already active!")
            return
        
        def on_color_selected(bgr_color):
            """Callback when color is picked"""
            current_rod = self.storage["config"]["fish"]["rod_type"]
            
            if current_rod in self.storage["config"]["fish"]["rods"]:
                # Add the new color to the list
                if color_type not in self.storage["config"]["fish"]["rods"][current_rod]:
                    self.storage["config"]["fish"]["rods"][current_rod][color_type] = []
                
                self.storage["config"]["fish"]["rods"][current_rod][color_type].append(bgr_color)
                print(f"Added color {bgr_color} to {color_type} for rod '{current_rod}'")
                
                # Refresh the color manager display
                self.root.after(100, self._create_color_manager_content)
        
        # Run color picker in a separate thread to avoid blocking the GUI
        def run_picker():
            self.active_color_picker = ColorPicker(on_color_selected)
            self.active_color_picker.run()
            self.active_color_picker = None  # Clear when done
        
        picker_thread = threading.Thread(target=run_picker, daemon=True)
        picker_thread.start()
    
    def _restore_default_colors(self, color_type):
        """Restore default colors for the specified color type"""
        current_rod = self.storage["config"]["fish"]["rod_type"]
        
        # Default colors based on type
        default_colors = {
            "target_colors": [[91, 75, 67]],
            "bar_colors": [[241, 241, 241], [255, 255, 255]]
        }
        
        if current_rod in self.storage["config"]["fish"]["rods"] and color_type in default_colors:
            # Restore the default colors
            self.storage["config"]["fish"]["rods"][current_rod][color_type] = default_colors[color_type].copy()
            print(f"Restored default {color_type} for rod '{current_rod}'")
            # Refresh the color manager display
            self._create_color_manager_content()
    
    def _load_rod_tolerances(self, rod_name):
        """Load tolerance values for the specified rod and update GUI"""
        if rod_name in self.storage["config"]["fish"]["rods"]:
            rod_data = self.storage["config"]["fish"]["rods"][rod_name]
            
            # Get tolerances with defaults
            target_tol = rod_data.get("target_tolerance", 0)
            bar_tol = rod_data.get("bar_tolerance", 0)
            
            # Update GUI sliders and labels
            self.target_tolerance_var.set(target_tol)
            self.target_tolerance_value_label.configure(text=str(target_tol))
            
            self.bar_tolerance_var.set(bar_tol)
            self.bar_tolerance_value_label.configure(text=str(bar_tol))
    
    def _on_target_tolerance_change(self, value):
        """Save target tolerance to current rod type"""
        int_val = int(float(value))
        current_rod = self.storage["config"]["fish"]["rod_type"]
        if current_rod in self.storage["config"]["fish"]["rods"]:
            self.storage["config"]["fish"]["rods"][current_rod]["target_tolerance"] = int_val
        self.target_tolerance_value_label.configure(text=str(int_val))
    
    def _on_bar_tolerance_change(self, value):
        """Save bar tolerance to current rod type"""
        int_val = int(float(value))
        current_rod = self.storage["config"]["fish"]["rod_type"]
        if current_rod in self.storage["config"]["fish"]["rods"]:
            self.storage["config"]["fish"]["rods"][current_rod]["bar_tolerance"] = int_val
        self.bar_tolerance_value_label.configure(text=str(int_val))
    
    def _start_video_recording(self):
        """Start video recording in a background thread"""
        if self.is_recording_video:
            # Emergency stop - cancel recording
            print("Emergency stop - cancelling video recording")
            self.is_recording_video = False
            if self.video_recorder:
                self.video_recorder = None
            self.video_has_data = False
            self.root.after(0, self._update_video_status, "No Video Data")
            self.root.after(0, self._update_record_button, "Record Video")
            return
        
        # Start recording
        self.is_recording_video = True
        self.root.after(0, self._update_record_button, "Stop Recording")
        self.root.after(0, self._update_video_status, "Starting...")
        
        # Minimize GUI
        if self.auto_minimize:
            self.root.iconify()
        
        # Focus Roblox
        if self.auto_focus_roblox:
            self._focus_roblox_window()
        
        # Start recording thread
        self.recording_thread = threading.Thread(target=self._video_recording_loop, daemon=True)
        self.recording_thread.start()
    
    def _video_recording_loop(self):
        """Main video recording loop (runs in background thread)"""
        try:
            # Initialize video recorder
            fish_area = self.storage["config"]["areas"]["fish"]
            green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
            top_corner_ratio = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
            right_corner_ratio = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
            
            recorder = VideoRecorder(fps=60, quality=70)
            
            with mss.mss(compression_level=0) as sct:
                monitor = sct.monitors[1]
                screen_width = monitor["width"]
                screen_height = monitor["height"]
                
                # Calculate green corner region
                safety_top = int(screen_height * top_corner_ratio)
                safety_right = int(screen_width * right_corner_ratio)
                green_region = {
                    "top": safety_top,
                    "left": 0,
                    "width": safety_right,
                    "height": screen_height - safety_top
                }
                
                # LOOP 1: Wait for green to disappear
                self.root.after(0, self._update_video_status, "Waiting for bobber...")
                print("[VIDEO] Waiting for green to disappear...")
                
                while self.is_recording_video:
                    screenshot = sct.grab(green_region)
                    frame_array = np.array(screenshot)[:, :, :3]
                    
                    # Check for green
                    b_match = np.abs(frame_array[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                    g_match = np.abs(frame_array[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                    r_match = np.abs(frame_array[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                    green_found = np.any(b_match & g_match & r_match)
                    
                    if not green_found:
                        print("[VIDEO] Green disappeared! Starting recording...")
                        break
                    time.sleep(0.05)
                
                if not self.is_recording_video:
                    self.root.after(0, self._update_video_status, "Cancelled")
                    self.root.after(0, self._update_record_button, "Record Video")
                    return
                
                # LOOP 2: Record until green appears
                self.root.after(0, self._update_video_status, "Recording...")
                recorder.start_recording()
                
                # Define fish capture region (3x height)
                fish_region = {
                    "top": fish_area["y"],
                    "left": fish_area["x"],
                    "width": fish_area["width"],
                    "height": fish_area["height"] * 3
                }
                
                frame_count = 0
                start_time = time.time()
                last_frame_time = start_time
                frame_delay = 1.0 / 60.0
                
                while self.is_recording_video:
                    # Limit to 60 FPS
                    current_time = time.time()
                    time_since_last_frame = current_time - last_frame_time
                    if time_since_last_frame < frame_delay:
                        time.sleep(frame_delay - time_since_last_frame)
                        current_time = time.time()
                    
                    last_frame_time = current_time
                    
                    # Capture fish area
                    fish_frame = sct.grab(fish_region)
                    fish_array = np.array(fish_frame)[:, :, :3]
                    recorder.add_frame(fish_array)
                    frame_count += 1
                    
                    # Check if green appeared
                    screenshot = sct.grab(green_region)
                    frame_array = np.array(screenshot)[:, :, :3]
                    b_match = np.abs(frame_array[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                    g_match = np.abs(frame_array[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                    r_match = np.abs(frame_array[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                    green_found = np.any(b_match & g_match & r_match)
                    
                    if green_found:
                        print(f"[VIDEO] Green appeared! Stopping recording... ({frame_count} frames)")
                        break
                
                recorder.stop_recording()
                
                # Check if recording was cancelled
                if not self.is_recording_video:
                    print("[VIDEO] Recording cancelled")
                    self.root.after(0, self._update_video_status, "No Video Data")
                    self.root.after(0, self._update_record_button, "Record Video")
                    return
                
                # Save recorder and update status
                self.video_recorder = recorder
                self.video_has_data = True
                elapsed = time.time() - start_time
                print(f"[VIDEO] Recording complete: {elapsed:.2f}s, {frame_count} frames")
                
                self.root.after(0, self._update_video_status, "Ready For Playback")
                self.root.after(0, self._update_record_button, "Record Video")
                self.is_recording_video = False
                
                # Restore GUI
                self.root.after(100, self.root.deiconify)
                
        except Exception as e:
            print(f"[VIDEO] Error: {e}")
            import traceback
            traceback.print_exc()
            self.is_recording_video = False
            self.root.after(0, self._update_video_status, "Error")
            self.root.after(0, self._update_record_button, "Record Video")
    
    def _playback_video(self):
        """Open video playback window"""
        if not self.video_has_data or not self.video_recorder:
            print("No video data to playback")
            messagebox.showwarning("No Video", "No video data available. Please record a video first.")
            return
        
        print("Opening video playback...")
        # Run playback in a thread so it doesn't block GUI
        threading.Thread(target=self.video_recorder.playback, daemon=True).start()
    
    def _update_video_status(self, status):
        """Update video status label"""
        color_map = {
            "No Video Data": "gray",
            "Starting...": "orange",
            "Waiting for bobber...": "yellow",
            "Recording...": "red",
            "Ready For Playback": "green",
            "Cancelled": "gray",
            "Error": "red"
        }
        self.video_status_label.configure(text=status, text_color=color_map.get(status, "gray"))
    
    def _update_record_button(self, text):
        """Update record button text"""
        # Find the record button and update it
        # This will be set when creating the button
        if hasattr(self, 'record_video_button'):
            self.record_video_button.configure(text=text)
    
    def _on_stabilize_threshold_change(self, value):
        int_val = int(float(value))
        self.storage["config"]["fish"]["move_check_stabilize_threshold"] = int_val
        self.stabilize_threshold_value_label.configure(text=str(int_val))
    
    def _on_movement_threshold_change(self, value):
        self.storage["config"]["fish"]["move_check_movement_threshold_percent"] = float(value)
        self.movement_threshold_value_label.configure(text=f"{float(value):.3f}")
    
    def _on_kp_change(self, value):
        self.storage["config"]["fish"]["kp"] = float(value)
        self.kp_value_label.configure(text=f"{float(value):.2f}")
    
    def _on_kd_change(self, value):
        self.storage["config"]["fish"]["kd"] = float(value)
        self.kd_value_label.configure(text=f"{float(value):.2f}")
    
    def _on_velocity_smoothing_change(self, value):
        self.storage["config"]["fish"]["velocity_smoothing"] = float(value)
        self.velocity_smoothing_value_label.configure(text=f"{float(value):.2f}")
    
    def _on_stopping_distance_change(self, value):
        self.storage["config"]["fish"]["stopping_distance_multiplier"] = float(value)
        self.stopping_distance_value_label.configure(text=f"{float(value):.1f}")
    
    def _on_delay_after_end_change(self, value):
        self.storage["config"]["fish"]["delay_after_end"] = float(value)
        self.delay_after_end_value_label.configure(text=f"{float(value):.1f}s")

    def _create_misc_tab(self):
        """Create the Misc tab with settings"""
        parent = self.tabview.tab("Misc")
        
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(1, weight=1)
        scroll_frame.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # Misc Settings Section
        misc_label = ctk.CTkLabel(scroll_frame, text="Misc Settings", 
                                  font=ctk.CTkFont(size=14, weight="bold"))
        misc_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        misc_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # Auto Zoom In
        auto_zoom_in_label = ctk.CTkLabel(scroll_frame, text="Auto Zoom In:", font=ctk.CTkFont(size=12))
        auto_zoom_in_label.grid(row=1, column=0, sticky="w", padx=10, pady=8)
        auto_zoom_in_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_in_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.auto_zoom_in else "OFF", width=100,
            command=self._toggle_auto_zoom_in,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.auto_zoom_in:
            self.auto_zoom_in_switch.select()
        else:
            self.auto_zoom_in_switch.deselect()
        self.auto_zoom_in_switch.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        # Auto Zoom In Options Frame (collapsible section)
        self.auto_zoom_in_frame = ctk.CTkFrame(scroll_frame, fg_color="gray25")
        self.auto_zoom_in_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        # Bind click on frame to unfocus entries
        self.auto_zoom_in_frame.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        # Hide frame if toggle is off
        if not self.auto_zoom_in:
            self.auto_zoom_in_frame.grid_remove()

        # Register validation command with all parameters
        vcmd = (self.root.register(self._validate_delay_input), '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')

        # AutoZoomDelay1
        auto_zoom_delay1_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay1_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        auto_zoom_delay1_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_in_delay1_entry = ctk.CTkEntry(
            self.auto_zoom_in_frame,
            width=60,
            justify="center"
        )
        self.auto_zoom_in_delay1_entry.grid(row=0, column=1, padx=(10, 5), pady=(15, 5), sticky="w")
        self.auto_zoom_in_delay1_entry.insert(0, self.auto_zoom_in_delay1)
        self.auto_zoom_in_delay1_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_zoom_in_delay1_entry.bind("<Return>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        auto_zoom_delay1_s_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay1_s_label.grid(row=0, column=2, padx=(0, 20), pady=(15, 5), sticky="w")
        auto_zoom_delay1_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # Zoom In Amount
        zoom_in_amount_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="Zoom In Amount:",
            font=ctk.CTkFont(size=12)
        )
        zoom_in_amount_label.grid(row=1, column=0, padx=20, pady=5, sticky="w")
        zoom_in_amount_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_in_amount_entry = ctk.CTkEntry(
            self.auto_zoom_in_frame,
            width=60,
            justify="center"
        )
        self.auto_zoom_in_amount_entry.grid(row=1, column=1, padx=(10, 20), pady=5, sticky="w")
        self.auto_zoom_in_amount_entry.insert(0, self.auto_zoom_in_amount)
        self.auto_zoom_in_amount_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_zoom_in_amount_entry.bind("<Return>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # AutoZoomDelay2
        auto_zoom_delay2_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay2_label.grid(row=2, column=0, padx=20, pady=5, sticky="w")
        auto_zoom_delay2_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_in_delay2_entry = ctk.CTkEntry(
            self.auto_zoom_in_frame,
            width=60,
            justify="center"
        )
        self.auto_zoom_in_delay2_entry.grid(row=2, column=1, padx=(10, 5), pady=5, sticky="w")
        self.auto_zoom_in_delay2_entry.insert(0, self.auto_zoom_in_delay2)
        self.auto_zoom_in_delay2_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_zoom_in_delay2_entry.bind("<Return>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        auto_zoom_delay2_s_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay2_s_label.grid(row=2, column=2, padx=(0, 20), pady=5, sticky="w")
        auto_zoom_delay2_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # Zoom Out Amount
        zoom_out_amount_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="Zoom Out Amount:",
            font=ctk.CTkFont(size=12)
        )
        zoom_out_amount_label.grid(row=3, column=0, padx=20, pady=5, sticky="w")
        zoom_out_amount_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_out_amount_entry = ctk.CTkEntry(
            self.auto_zoom_in_frame,
            width=60,
            justify="center"
        )
        self.auto_zoom_out_amount_entry.grid(row=3, column=1, padx=(10, 20), pady=5, sticky="w")
        self.auto_zoom_out_amount_entry.insert(0, self.auto_zoom_out_amount)
        self.auto_zoom_out_amount_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_zoom_out_amount_entry.bind("<Return>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # AutoZoomDelay3
        auto_zoom_delay3_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay3_label.grid(row=4, column=0, padx=20, pady=(5, 15), sticky="w")
        auto_zoom_delay3_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_zoom_in_delay3_entry = ctk.CTkEntry(
            self.auto_zoom_in_frame,
            width=60,
            justify="center"
        )
        self.auto_zoom_in_delay3_entry.grid(row=4, column=1, padx=(10, 5), pady=(5, 15), sticky="w")
        self.auto_zoom_in_delay3_entry.insert(0, self.auto_zoom_in_delay3)
        self.auto_zoom_in_delay3_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_zoom_in_delay3_entry.bind("<Return>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        auto_zoom_delay3_s_label = ctk.CTkLabel(
            self.auto_zoom_in_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_zoom_delay3_s_label.grid(row=4, column=2, padx=(0, 20), pady=(5, 15), sticky="w")
        auto_zoom_delay3_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))

        # Auto Select Rod
        auto_select_rod_label = ctk.CTkLabel(scroll_frame, text="Auto Select Rod:", font=ctk.CTkFont(size=12))
        auto_select_rod_label.grid(row=3, column=0, sticky="w", padx=10, pady=8)
        auto_select_rod_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        self.auto_select_rod_switch = ctk.CTkSwitch(
            scroll_frame, text="ON" if self.auto_select_rod else "OFF", width=100,
            command=self._toggle_auto_select_rod,
            font=ctk.CTkFont(size=12, weight="bold")
        )
        if self.auto_select_rod:
            self.auto_select_rod_switch.select()
        else:
            self.auto_select_rod_switch.deselect()
        self.auto_select_rod_switch.grid(row=3, column=1, sticky="w", padx=10, pady=8)

        # Auto Select Rod Options Frame (collapsible section)
        self.auto_select_rod_frame = ctk.CTkFrame(scroll_frame, fg_color="gray25")
        self.auto_select_rod_frame.grid(row=4, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        # Bind click on frame to unfocus entries
        self.auto_select_rod_frame.bind("<Button-1>", lambda e: (self._save_delay_values(), self._save_zoom_values(), self.root.focus()))
        
        # Hide frame if toggle is off
        if not self.auto_select_rod:
            self.auto_select_rod_frame.grid_remove()

        # Register validation command with all parameters
        vcmd = (self.root.register(self._validate_delay_input), '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')

        # AutoRodDelay1
        auto_rod_delay1_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay1_label.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")
        auto_rod_delay1_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        self.auto_rod_delay1_entry = ctk.CTkEntry(
            self.auto_select_rod_frame,
            width=60,
            justify="center"
        )
        self.auto_rod_delay1_entry.grid(row=0, column=1, padx=(10, 5), pady=(15, 5), sticky="w")
        self.auto_rod_delay1_entry.insert(0, self.auto_rod_delay1)
        self.auto_rod_delay1_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_rod_delay1_entry.bind("<Return>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        auto_rod_delay1_s_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay1_s_label.grid(row=0, column=2, padx=(0, 20), pady=(15, 5), sticky="w")
        auto_rod_delay1_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))

        # AutoRodEquipmentBag
        auto_rod_equipment_bag_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="Equipment Bag:",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_equipment_bag_label.grid(row=1, column=0, padx=20, pady=5, sticky="w")
        auto_rod_equipment_bag_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        self.auto_rod_equipment_bag_entry = ctk.CTkEntry(
            self.auto_select_rod_frame,
            width=60,
            state="disabled",
            justify="center"
        )
        self.auto_rod_equipment_bag_entry.grid(row=1, column=1, padx=(10, 5), pady=5, sticky="w")
        self.auto_rod_equipment_bag_entry.configure(state="normal")
        self.auto_rod_equipment_bag_entry.insert(0, self.equipment_bag_hotbar)
        self.auto_rod_equipment_bag_entry.configure(state="disabled")

        # AutoRodDelay2
        auto_rod_delay2_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay2_label.grid(row=2, column=0, padx=20, pady=5, sticky="w")
        auto_rod_delay2_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        self.auto_rod_delay2_entry = ctk.CTkEntry(
            self.auto_select_rod_frame,
            width=60,
            justify="center"
        )
        self.auto_rod_delay2_entry.grid(row=2, column=1, padx=(10, 5), pady=5, sticky="w")
        self.auto_rod_delay2_entry.insert(0, self.auto_rod_delay2)
        self.auto_rod_delay2_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_rod_delay2_entry.bind("<Return>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        auto_rod_delay2_s_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay2_s_label.grid(row=2, column=2, padx=(0, 20), pady=5, sticky="w")
        auto_rod_delay2_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))

        # AutoRodFishingRod
        auto_rod_fishing_rod_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="Fishing Rod:",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_fishing_rod_label.grid(row=3, column=0, padx=20, pady=5, sticky="w")
        auto_rod_fishing_rod_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        self.auto_rod_fishing_rod_entry = ctk.CTkEntry(
            self.auto_select_rod_frame,
            width=60,
            state="disabled",
            justify="center"
        )
        self.auto_rod_fishing_rod_entry.grid(row=3, column=1, padx=(10, 5), pady=5, sticky="w")
        self.auto_rod_fishing_rod_entry.configure(state="normal")
        self.auto_rod_fishing_rod_entry.insert(0, self.fishing_rod_hotbar)
        self.auto_rod_fishing_rod_entry.configure(state="disabled")

        # AutoRodDelay3
        auto_rod_delay3_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="Delay:",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay3_label.grid(row=4, column=0, padx=20, pady=(5, 15), sticky="w")
        auto_rod_delay3_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        self.auto_rod_delay3_entry = ctk.CTkEntry(
            self.auto_select_rod_frame,
            width=60,
            justify="center"
        )
        self.auto_rod_delay3_entry.grid(row=4, column=1, padx=(10, 5), pady=(5, 15), sticky="w")
        self.auto_rod_delay3_entry.insert(0, self.auto_rod_delay3)
        self.auto_rod_delay3_entry.configure(validate="key", validatecommand=vcmd)
        self.auto_rod_delay3_entry.bind("<Return>", lambda e: (self._save_delay_values(), self.root.focus()))
        
        auto_rod_delay3_s_label = ctk.CTkLabel(
            self.auto_select_rod_frame,
            text="s",
            font=ctk.CTkFont(size=12)
        )
        auto_rod_delay3_s_label.grid(row=4, column=2, padx=(0, 20), pady=(5, 15), sticky="w")
        auto_rod_delay3_s_label.bind("<Button-1>", lambda e: (self._save_delay_values(), self.root.focus()))

    def _create_cast_tab(self):
        """Create the Cast tab with cast method settings"""
        parent = self.tabview.tab("Cast")
        
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(1, weight=1)

        # Cast Settings Section
        cast_label = ctk.CTkLabel(scroll_frame, text="Cast Settings", 
                                  font=ctk.CTkFont(size=14, weight="bold"))
        cast_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        # Cast Method
        cast_method_label = ctk.CTkLabel(scroll_frame, text="Cast Method:", font=ctk.CTkFont(size=12))
        cast_method_label.grid(row=1, column=0, sticky="w", padx=10, pady=8)
        
        self.cast_method_var = tk.StringVar(value=self.storage["config"]["cast"]["method"])
        cast_method_menu = ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.cast_method_var,
            values=["Normal", "Perfect", "Disabled"],
            width=150,
            command=self._on_cast_method_change
        )
        cast_method_menu.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        # Disabled Cast Section
        self.disabled_cast_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.disabled_cast_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        disabled_cast_label = ctk.CTkLabel(self.disabled_cast_frame, text="Cast is disabled", 
                                           font=ctk.CTkFont(size=13), text_color="gray60")
        disabled_cast_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))

        # Normal Cast Section (initially visible if Normal is selected)
        self.normal_cast_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.normal_cast_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        # Normal Cast Settings Label
        normal_label = ctk.CTkLabel(self.normal_cast_frame, text="Normal Cast Settings", 
                                    font=ctk.CTkFont(size=13, weight="bold"))
        normal_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))
        
        # Normal Cast Flow Frame
        self.normal_cast_flow_frame = ctk.CTkFrame(self.normal_cast_frame, fg_color="gray25")
        self.normal_cast_flow_frame.grid(row=1, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        self.normal_cast_flow_frame.bind("<Button-1>", lambda e: (self._save_normal_cast_delay_values(), self.root.focus()))
        
        # Create the Normal Cast flow
        self._create_normal_cast_flow()

        # Perfect Cast Section (initially visible if Perfect is selected)
        self.perfect_cast_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.perfect_cast_frame.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        # Perfect Cast Settings Label
        perfect_label = ctk.CTkLabel(self.perfect_cast_frame, text="Perfect Cast Settings", 
                                     font=ctk.CTkFont(size=13, weight="bold"))
        perfect_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))
        
        # Green Color Tolerance
        green_tolerance_label = ctk.CTkLabel(self.perfect_cast_frame, text="Green Color Tolerance:", font=ctk.CTkFont(size=12))
        green_tolerance_label.grid(row=1, column=0, sticky="w", padx=20, pady=5)
        green_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.green_tolerance_var = tk.IntVar(value=self.green_tolerance)
        green_tolerance_slider = ctk.CTkSlider(
            self.perfect_cast_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.green_tolerance_var,
            command=self._on_cast_green_tolerance_change,
            width=200
        )
        green_tolerance_slider.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        self.green_tolerance_value_label = ctk.CTkLabel(self.perfect_cast_frame, text=str(self.green_tolerance), font=ctk.CTkFont(size=12))
        self.green_tolerance_value_label.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.green_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # White Color Tolerance
        white_tolerance_label = ctk.CTkLabel(self.perfect_cast_frame, text="White Color Tolerance:", font=ctk.CTkFont(size=12))
        white_tolerance_label.grid(row=2, column=0, sticky="w", padx=20, pady=5)
        white_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.white_tolerance_var = tk.IntVar(value=self.white_tolerance)
        white_tolerance_slider = ctk.CTkSlider(
            self.perfect_cast_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.white_tolerance_var,
            command=self._on_white_tolerance_change,
            width=200
        )
        white_tolerance_slider.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        self.white_tolerance_value_label = ctk.CTkLabel(self.perfect_cast_frame, text=str(self.white_tolerance), font=ctk.CTkFont(size=12))
        self.white_tolerance_value_label.grid(row=2, column=2, sticky="w", padx=5, pady=5)
        self.white_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Fail Release Timeout
        fail_timeout_label = ctk.CTkLabel(self.perfect_cast_frame, text="Fail Release Timeout:", font=ctk.CTkFont(size=12))
        fail_timeout_label.grid(row=3, column=0, sticky="w", padx=20, pady=5)
        fail_timeout_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.fail_timeout_var = tk.DoubleVar(value=self.fail_release_timeout)
        fail_timeout_slider = ctk.CTkSlider(
            self.perfect_cast_frame,
            from_=0.0,
            to=20.0,
            number_of_steps=200,
            variable=self.fail_timeout_var,
            command=self._on_fail_timeout_change,
            width=200
        )
        fail_timeout_slider.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        self.fail_timeout_value_label = ctk.CTkLabel(self.perfect_cast_frame, text=f"{self.fail_release_timeout:.1f}s", font=ctk.CTkFont(size=12))
        self.fail_timeout_value_label.grid(row=3, column=2, sticky="w", padx=5, pady=5)
        self.fail_timeout_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Release Timing instruction label
        release_timing_instruction = ctk.CTkLabel(
            self.perfect_cast_frame, 
            text="Release too late? Click <  |  Release too early? Click >",
            font=ctk.CTkFont(size=11),
            text_color="gray70"
        )
        release_timing_instruction.grid(row=4, column=0, columnspan=3, sticky="w", padx=20, pady=(8, 2))
        release_timing_instruction.bind("<Button-1>", lambda e: self.root.focus())
        
        # Release Timing
        release_timing_label = ctk.CTkLabel(self.perfect_cast_frame, text="Release Timing:", font=ctk.CTkFont(size=12))
        release_timing_label.grid(row=5, column=0, sticky="w", padx=20, pady=5)
        release_timing_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Display value with direction indicator
        def get_timing_display(value):
            if value < -0.01:
                return f"{abs(value):.1f} Earlier"
            elif value > 0.01:
                return f"{value:.1f} Later"
            else:
                return "Default"
        
        # Store the display function for use in callback
        self._get_timing_display = get_timing_display
        
        # Frame for increment/decrement buttons and value display
        timing_control_frame = ctk.CTkFrame(self.perfect_cast_frame, fg_color="transparent")
        timing_control_frame.grid(row=5, column=1, sticky="w", padx=10, pady=5)
        
        # Left (Earlier) button
        left_button = ctk.CTkButton(
            timing_control_frame,
            text="◀",
            width=40,
            height=28,
            font=ctk.CTkFont(size=16),
            command=lambda: self._adjust_release_timing(-0.5)
        )
        left_button.grid(row=0, column=0, padx=(0, 5))
        
        # Value display in the middle
        self.release_timing_value_label = ctk.CTkLabel(
            timing_control_frame, 
            text=get_timing_display(self.release_timing), 
            font=ctk.CTkFont(size=12),
            width=100
        )
        self.release_timing_value_label.grid(row=0, column=1, padx=5)
        self.release_timing_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Right (Later) button
        right_button = ctk.CTkButton(
            timing_control_frame,
            text="▶",
            width=40,
            height=28,
            font=ctk.CTkFont(size=16),
            command=lambda: self._adjust_release_timing(0.5)
        )
        right_button.grid(row=0, column=2, padx=(5, 0))
        
        # Auto Look Down
        auto_look_down_label = ctk.CTkLabel(self.perfect_cast_frame, text="Auto Look Down:", font=ctk.CTkFont(size=12))
        auto_look_down_label.grid(row=6, column=0, sticky="w", padx=20, pady=(5, 15))
        auto_look_down_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.auto_look_down_var = tk.BooleanVar(value=self.auto_look_down)
        auto_look_down_checkbox = ctk.CTkCheckBox(
            self.perfect_cast_frame,
            text="",
            variable=self.auto_look_down_var,
            command=self._toggle_auto_look_down,
            width=20
        )
        auto_look_down_checkbox.grid(row=6, column=1, sticky="w", padx=10, pady=(5, 15))
        
        # Perfect Cast Flow Frame (collapsible section)
        self.perfect_cast_flow_frame = ctk.CTkFrame(self.perfect_cast_frame, fg_color="gray25")
        self.perfect_cast_flow_frame.grid(row=7, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        self.perfect_cast_flow_frame.bind("<Button-1>", lambda e: (self._save_cast_delay_values(), self.root.focus()))
        
        # Create the single unified flow
        self._create_perfect_cast_flow()
        
        # Update visibility based on initial value
        self._update_perfect_cast_visibility()

    def _on_cast_method_change(self, value):
        """Save cast method to storage when changed"""
        self.storage["config"]["cast"]["method"] = value
        self._update_perfect_cast_visibility()
    
    def _on_capture_mode_change(self, value):
        """Save global capture mode to storage when changed"""
        self.storage["config"]["capture_mode"] = value
    
    def _update_perfect_cast_visibility(self):
        """Show or hide the cast settings based on cast method"""
        method = self.cast_method_var.get()
        
        if method == "Normal":
            self.disabled_cast_frame.grid_remove()
            self.normal_cast_frame.grid()
            self.perfect_cast_frame.grid_remove()
        elif method == "Perfect":
            self.disabled_cast_frame.grid_remove()
            self.normal_cast_frame.grid_remove()
            self.perfect_cast_frame.grid()
        else:  # Disabled
            self.disabled_cast_frame.grid()
            self.normal_cast_frame.grid_remove()
            self.perfect_cast_frame.grid_remove()
    
    def _on_cast_green_tolerance_change(self, value):
        """Update green tolerance when slider changes"""
        tolerance = int(value)
        self.green_tolerance = tolerance
        self.storage["config"]["cast"]["green_tolerance"] = tolerance
        self.green_tolerance_value_label.configure(text=str(tolerance))
    
    def _on_white_tolerance_change(self, value):
        """Update white tolerance when slider changes"""
        tolerance = int(value)
        self.white_tolerance = tolerance
        self.storage["config"]["cast"]["white_tolerance"] = tolerance
        self.white_tolerance_value_label.configure(text=str(tolerance))
    
    def _create_shake_tab(self):
        """Create the Shake tab with shake method settings"""
        parent = self.tabview.tab("Shake")
        
        # Create scrollable frame
        scroll_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=5, pady=5)
        scroll_frame.grid_columnconfigure(1, weight=1)

        # Shake Settings Section
        shake_label = ctk.CTkLabel(scroll_frame, text="Shake Settings", 
                                  font=ctk.CTkFont(size=14, weight="bold"))
        shake_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        # Shake Method
        shake_method_label = ctk.CTkLabel(scroll_frame, text="Shake Method:", font=ctk.CTkFont(size=12))
        shake_method_label.grid(row=1, column=0, sticky="w", padx=10, pady=8)
        
        self.shake_method_var = tk.StringVar(value=self.storage["config"]["shake"]["method"])
        shake_method_menu = ctk.CTkOptionMenu(
            scroll_frame,
            variable=self.shake_method_var,
            values=["Pixel", "Navigation", "Disabled"],
            width=150,
            command=self._on_shake_method_change
        )
        shake_method_menu.grid(row=1, column=1, sticky="w", padx=10, pady=8)

        # Disabled Shake Section (row 2)
        self.disabled_shake_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.disabled_shake_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        disabled_shake_label = ctk.CTkLabel(self.disabled_shake_frame, text="Shake is disabled", 
                                            font=ctk.CTkFont(size=13), text_color="gray60")
        disabled_shake_label.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))

        # Pixel Shake Section (row 3)
        self.pixel_shake_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.pixel_shake_frame.grid(row=3, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        pixel_shake_header = ctk.CTkLabel(self.pixel_shake_frame, text="Pixel Shake Settings", 
                                          font=ctk.CTkFont(size=13, weight="bold"))
        pixel_shake_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))
        
        # White Color Tolerance
        pixel_white_tolerance_label = ctk.CTkLabel(self.pixel_shake_frame, text="White Color Tolerance:", font=ctk.CTkFont(size=12))
        pixel_white_tolerance_label.grid(row=1, column=0, sticky="w", padx=20, pady=5)
        pixel_white_tolerance_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.pixel_white_tolerance_var = tk.IntVar(value=self.storage["config"]["shake"]["pixel_white_tolerance"])
        pixel_white_tolerance_slider = ctk.CTkSlider(
            self.pixel_shake_frame,
            from_=0,
            to=20,
            number_of_steps=20,
            variable=self.pixel_white_tolerance_var,
            command=self._on_pixel_white_tolerance_change,
            width=200
        )
        pixel_white_tolerance_slider.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        self.pixel_white_tolerance_value_label = ctk.CTkLabel(self.pixel_shake_frame, text=str(self.pixel_white_tolerance_var.get()), font=ctk.CTkFont(size=12))
        self.pixel_white_tolerance_value_label.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.pixel_white_tolerance_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Duplicate Pixel Bypass
        pixel_duplicate_bypass_label = ctk.CTkLabel(self.pixel_shake_frame, text="Duplicate Pixel Bypass:", font=ctk.CTkFont(size=12))
        pixel_duplicate_bypass_label.grid(row=2, column=0, sticky="w", padx=20, pady=5)
        pixel_duplicate_bypass_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.pixel_duplicate_bypass_var = tk.DoubleVar(value=self.storage["config"]["shake"]["pixel_duplicate_bypass"])
        pixel_duplicate_bypass_slider = ctk.CTkSlider(
            self.pixel_shake_frame,
            from_=0.0,
            to=10.0,
            number_of_steps=100,
            variable=self.pixel_duplicate_bypass_var,
            command=self._on_pixel_duplicate_bypass_change,
            width=200
        )
        pixel_duplicate_bypass_slider.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        self.pixel_duplicate_bypass_value_label = ctk.CTkLabel(self.pixel_shake_frame, text=f"{self.pixel_duplicate_bypass_var.get():.1f}s", font=ctk.CTkFont(size=12))
        self.pixel_duplicate_bypass_value_label.grid(row=2, column=2, sticky="w", padx=5, pady=5)
        self.pixel_duplicate_bypass_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Fail Shake Timeout
        fail_shake_timeout_label = ctk.CTkLabel(self.pixel_shake_frame, text="Fail Shake Timeout:", font=ctk.CTkFont(size=12))
        fail_shake_timeout_label.grid(row=3, column=0, sticky="w", padx=20, pady=5)
        fail_shake_timeout_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.fail_shake_timeout_var = tk.DoubleVar(value=self.storage["config"]["shake"]["fail_shake_timeout"])
        fail_shake_timeout_slider = ctk.CTkSlider(
            self.pixel_shake_frame,
            from_=0.0,
            to=20.0,
            number_of_steps=200,
            variable=self.fail_shake_timeout_var,
            command=self._on_fail_shake_timeout_change,
            width=200
        )
        fail_shake_timeout_slider.grid(row=3, column=1, sticky="w", padx=10, pady=5)
        
        self.fail_shake_timeout_value_label = ctk.CTkLabel(self.pixel_shake_frame, text=f"{self.fail_shake_timeout_var.get():.1f}s", font=ctk.CTkFont(size=12))
        self.fail_shake_timeout_value_label.grid(row=3, column=2, sticky="w", padx=5, pady=5)
        self.fail_shake_timeout_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Double Click
        pixel_double_click_label = ctk.CTkLabel(self.pixel_shake_frame, text="Double Click:", font=ctk.CTkFont(size=12))
        pixel_double_click_label.grid(row=4, column=0, sticky="w", padx=20, pady=5)
        pixel_double_click_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.pixel_double_click_var = tk.BooleanVar(value=self.storage["config"]["shake"]["pixel_double_click"])
        pixel_double_click_checkbox = ctk.CTkCheckBox(
            self.pixel_shake_frame,
            text="",
            variable=self.pixel_double_click_var,
            command=self._toggle_pixel_double_click,
            width=20
        )
        pixel_double_click_checkbox.grid(row=4, column=1, sticky="w", padx=10, pady=5)
        
        # Double Click Delay
        pixel_double_click_delay_label = ctk.CTkLabel(self.pixel_shake_frame, text="Double Click Delay:", font=ctk.CTkFont(size=12))
        pixel_double_click_delay_label.grid(row=5, column=0, sticky="w", padx=20, pady=5)
        pixel_double_click_delay_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.pixel_double_click_delay_var = tk.IntVar(value=self.storage["config"]["shake"]["pixel_double_click_delay"])
        pixel_double_click_delay_slider = ctk.CTkSlider(
            self.pixel_shake_frame,
            from_=0,
            to=50,
            number_of_steps=50,
            variable=self.pixel_double_click_delay_var,
            command=self._on_pixel_double_click_delay_change,
            width=200
        )
        pixel_double_click_delay_slider.grid(row=5, column=1, sticky="w", padx=10, pady=5)
        
        self.pixel_double_click_delay_value_label = ctk.CTkLabel(self.pixel_shake_frame, text=f"{self.pixel_double_click_delay_var.get()}ms", font=ctk.CTkFont(size=12))
        self.pixel_double_click_delay_value_label.grid(row=5, column=2, sticky="w", padx=5, pady=5)
        self.pixel_double_click_delay_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Spacer (row 6 - empty)
        spacer_label = ctk.CTkLabel(self.pixel_shake_frame, text="", font=ctk.CTkFont(size=12))
        spacer_label.grid(row=6, column=0, columnspan=3, sticky="w", padx=0, pady=5)

        # Navigation Shake Section (row 4)
        self.navigation_shake_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.navigation_shake_frame.grid(row=4, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        navigation_shake_header = ctk.CTkLabel(self.navigation_shake_frame, text="Navigation Shake Settings", 
                                               font=ctk.CTkFont(size=13, weight="bold"))
        navigation_shake_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))

        # Enter Spam Delay (row 1)
        navigation_spam_delay_label = ctk.CTkLabel(self.navigation_shake_frame, text="Enter Spam Delay:", font=ctk.CTkFont(size=12))
        navigation_spam_delay_label.grid(row=1, column=0, sticky="w", padx=20, pady=5)
        navigation_spam_delay_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.navigation_spam_delay_var = tk.IntVar(value=self.storage["config"]["shake"]["navigation_spam_delay"])
        navigation_spam_delay_slider = ctk.CTkSlider(
            self.navigation_shake_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            variable=self.navigation_spam_delay_var,
            command=self._on_navigation_spam_delay_change,
            width=200
        )
        navigation_spam_delay_slider.grid(row=1, column=1, sticky="w", padx=10, pady=5)
        
        self.navigation_spam_delay_value_label = ctk.CTkLabel(self.navigation_shake_frame, 
                                                             text=f"{self.navigation_spam_delay_var.get()}ms", 
                                                             font=ctk.CTkFont(size=12))
        self.navigation_spam_delay_value_label.grid(row=1, column=2, sticky="w", padx=5, pady=5)
        self.navigation_spam_delay_value_label.bind("<Button-1>", lambda e: self.root.focus())
        
        # Fail Shake Timeout (row 2)
        navigation_fail_timeout_label = ctk.CTkLabel(self.navigation_shake_frame, text="Fail Shake Timeout:", font=ctk.CTkFont(size=12))
        navigation_fail_timeout_label.grid(row=2, column=0, sticky="w", padx=20, pady=5)
        navigation_fail_timeout_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.navigation_fail_timeout_var = tk.DoubleVar(value=self.storage["config"]["shake"]["navigation_fail_timeout"])
        navigation_fail_timeout_slider = ctk.CTkSlider(
            self.navigation_shake_frame,
            from_=0.0,
            to=30.0,
            number_of_steps=300,
            variable=self.navigation_fail_timeout_var,
            command=self._on_navigation_fail_timeout_change,
            width=200
        )
        navigation_fail_timeout_slider.grid(row=2, column=1, sticky="w", padx=10, pady=5)
        
        self.navigation_fail_timeout_value_label = ctk.CTkLabel(self.navigation_shake_frame, 
                                                               text=f"{self.navigation_fail_timeout_var.get():.1f}s", 
                                                               font=ctk.CTkFont(size=12))
        self.navigation_fail_timeout_value_label.grid(row=2, column=2, sticky="w", padx=5, pady=5)
        self.navigation_fail_timeout_value_label.bind("<Button-1>", lambda e: self.root.focus())

        # Circle Shake Section (row 5)
        self.circle_shake_frame = ctk.CTkFrame(scroll_frame, fg_color="transparent")
        self.circle_shake_frame.grid(row=5, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))
        
        circle_shake_header = ctk.CTkLabel(self.circle_shake_frame, text="Circle Shake Settings", 
                                           font=ctk.CTkFont(size=13, weight="bold"))
        circle_shake_header.grid(row=0, column=0, columnspan=3, sticky="w", padx=0, pady=(5, 10))
        
        # Update visibility based on initial value
        self._update_shake_visibility()

    def _on_shake_method_change(self, value):
        """Save shake method to storage when changed"""
        # Show setup message when switching to Navigation mode
        if value == "Navigation":
            self._show_navigation_setup_dialog()
        
        self.storage["config"]["shake"]["method"] = value
        self._update_shake_visibility()
    
    def _show_navigation_setup_dialog(self):
        """Show custom dialog for navigation mode setup"""
        # Create custom dialog
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Setup Required For Usage")
        dialog.geometry("450x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center the dialog on parent window
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - (dialog.winfo_width() // 2)
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - (dialog.winfo_height() // 2)
        dialog.geometry(f"+{x}+{y}")
        
        # Message text
        message = ctk.CTkLabel(
            dialog,
            text="Using navigation mode requires you to activate and prepare it\nbefore using the macro.\n\n"
                 "Press YES to watch the video on how to set it up.",
            font=ctk.CTkFont(size=13),
            justify="center"
        )
        message.pack(pady=30, padx=20)
        
        # Button frame
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)
        
        def on_yes():
            # YES button clicked (im an idiot) - open tutorial video
            import webbrowser
            webbrowser.open("https://youtu.be/4IXNCQFOcqg")
            dialog.destroy()
        
        def on_no():
            # NO button clicked (im smart)
            dialog.destroy()
            pass  # Do nothing for now
        
        # YES button
        yes_button = ctk.CTkButton(
            button_frame,
            text="YES, im an idiot",
            command=on_yes,
            width=150,
            font=ctk.CTkFont(size=12)
        )
        yes_button.pack(side="left", padx=10)
        
        # NO button
        no_button = ctk.CTkButton(
            button_frame,
            text="NO, im smart",
            command=on_no,
            width=150,
            font=ctk.CTkFont(size=12)
        )
        no_button.pack(side="left", padx=10)
        
        # Wait for dialog to close
        dialog.wait_window()
    
    def _update_shake_visibility(self):
        """Show or hide shake frames based on shake method"""
        method = self.shake_method_var.get()
        
        # Hide all frames first
        self.disabled_shake_frame.grid_remove()
        self.pixel_shake_frame.grid_remove()
        self.navigation_shake_frame.grid_remove()
        self.circle_shake_frame.grid_remove()
        
        # Show the appropriate frame
        if method == "Disabled":
            self.disabled_shake_frame.grid()
        elif method == "Pixel":
            self.pixel_shake_frame.grid()
        elif method == "Navigation":
            self.navigation_shake_frame.grid()
        elif method == "Circle":
            self.circle_shake_frame.grid()
    
    def _on_pixel_white_tolerance_change(self, value):
        """Save pixel white tolerance to storage when changed"""
        int_value = int(value)
        self.storage["config"]["shake"]["pixel_white_tolerance"] = int_value
        self.pixel_white_tolerance_value_label.configure(text=str(int_value))
    
    def _on_pixel_duplicate_bypass_change(self, value):
        """Save pixel duplicate bypass to storage when changed"""
        self.storage["config"]["shake"]["pixel_duplicate_bypass"] = value
        self.pixel_duplicate_bypass_value_label.configure(text=f"{value:.1f}s")
    
    def _on_fail_shake_timeout_change(self, value):
        """Save fail shake timeout to storage when changed"""
        self.storage["config"]["shake"]["fail_shake_timeout"] = float(value)
        self.fail_shake_timeout_value_label.configure(text=f"{float(value):.1f}s")
    
    def _toggle_pixel_double_click(self):
        """Toggle pixel double click"""
        self.storage["config"]["shake"]["pixel_double_click"] = self.pixel_double_click_var.get()
    
    def _on_pixel_double_click_delay_change(self, value):
        """Save pixel double click delay to storage when changed"""
        int_value = int(value)
        self.storage["config"]["shake"]["pixel_double_click_delay"] = int_value
        self.pixel_double_click_delay_value_label.configure(text=f"{int_value}ms")
    
    def _on_navigation_spam_delay_change(self, value):
        """Save navigation spam delay to storage when changed"""
        int_value = int(value)
        self.storage["config"]["shake"]["navigation_spam_delay"] = int_value
        self.navigation_spam_delay_value_label.configure(text=f"{int_value}ms")
    
    def _on_navigation_fail_timeout_change(self, value):
        """Save navigation fail timeout to storage when changed"""
        self.storage["config"]["shake"]["navigation_fail_timeout"] = float(value)
        self.navigation_fail_timeout_value_label.configure(text=f"{float(value):.1f}s")
    
    def _on_state_check_green_tolerance_change(self, value):
        """Save green tolerance to storage when changed"""
        int_value = int(value)
        self.storage["config"]["state_check"]["green_tolerance"] = int_value
        self.state_check_green_tolerance_value_label.configure(text=str(int_value))
    
    def _on_top_corner_ratio_change(self, value):
        """Save top corner ratio to storage when changed"""
        int_value = int(value)
        self.storage["config"]["state_check"]["top_corner_ratio"] = int_value
        self.top_corner_ratio_value_label.configure(text=f"{int_value}%")
    
    def _on_right_corner_ratio_change(self, value):
        """Save right corner ratio to storage when changed"""
        int_value = int(value)
        self.storage["config"]["state_check"]["right_corner_ratio"] = int_value
        self.right_corner_ratio_value_label.configure(text=f"{int_value}%")
    
    def _on_fail_timeout_change(self, value):
        """Update fail release timeout when slider changes"""
        timeout = float(value)
        self.fail_release_timeout = timeout
        self.storage["config"]["cast"]["fail_release_timeout"] = timeout
        self.fail_timeout_value_label.configure(text=f"{timeout:.1f}s")
    
    def _adjust_release_timing(self, increment):
        """Adjust release timing by increment amount (0.5 or -0.5)"""
        # Clamp value between -50.0 and 50.0
        new_timing = max(-50.0, min(50.0, self.release_timing + increment))
        self.release_timing = new_timing
        self.storage["config"]["cast"]["release_timing"] = new_timing
        self.release_timing_value_label.configure(text=self._get_timing_display(new_timing))
    
    def _toggle_auto_look_down(self):
        """Toggle Auto Look Down and save to storage"""
        self.auto_look_down = self.auto_look_down_var.get()
        self.storage["config"]["cast"]["auto_look_down"] = self.auto_look_down
    
    def _create_normal_cast_flow(self):
        """Create flow for Normal Cast"""
        vcmd = (self.root.register(self._validate_delay_input), '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')
        
        row = 0
        
        # Delay 1
        delay1_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay1_label.grid(row=row, column=0, padx=20, pady=(15, 5), sticky="w")
        delay1_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.normal_cast_delay1_var = tk.StringVar(value=self.normal_cast_delay1)
        self.normal_cast_delay1_var.trace_add("write", lambda *args: self._on_normal_cast_delay1_change())
        self.normal_cast_delay1_entry = ctk.CTkEntry(self.normal_cast_flow_frame, width=60, justify="center", textvariable=self.normal_cast_delay1_var)
        self.normal_cast_delay1_entry.grid(row=row, column=1, padx=(10, 5), pady=(15, 5), sticky="w")
        self.normal_cast_delay1_entry.configure(validate="key", validatecommand=vcmd)
        self.normal_cast_delay1_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay1_s_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay1_s_label.grid(row=row, column=2, padx=(0, 20), pady=(15, 5), sticky="w")
        delay1_s_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Hold Left Click
        hold_click_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="Hold Left Click", font=ctk.CTkFont(size=12))
        hold_click_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        hold_click_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Delay 2
        delay2_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay2_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        delay2_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.normal_cast_delay2_var = tk.StringVar(value=self.normal_cast_delay2)
        self.normal_cast_delay2_var.trace_add("write", lambda *args: self._on_normal_cast_delay2_change())
        self.normal_cast_delay2_entry = ctk.CTkEntry(self.normal_cast_flow_frame, width=60, justify="center", textvariable=self.normal_cast_delay2_var)
        self.normal_cast_delay2_entry.grid(row=row, column=1, padx=(10, 5), pady=5, sticky="w")
        self.normal_cast_delay2_entry.configure(validate="key", validatecommand=vcmd)
        self.normal_cast_delay2_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay2_s_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay2_s_label.grid(row=row, column=2, padx=(0, 20), pady=5, sticky="w")
        delay2_s_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Release Left Click
        release_click_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="Release Left Click", font=ctk.CTkFont(size=12))
        release_click_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        release_click_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Delay 3
        delay3_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay3_label.grid(row=row, column=0, padx=20, pady=(5, 15), sticky="w")
        delay3_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.normal_cast_delay3_var = tk.StringVar(value=self.normal_cast_delay3)
        self.normal_cast_delay3_var.trace_add("write", lambda *args: self._on_normal_cast_delay3_change())
        self.normal_cast_delay3_entry = ctk.CTkEntry(self.normal_cast_flow_frame, width=60, justify="center", textvariable=self.normal_cast_delay3_var)
        self.normal_cast_delay3_entry.grid(row=row, column=1, padx=(10, 5), pady=(5, 15), sticky="w")
        self.normal_cast_delay3_entry.configure(validate="key", validatecommand=vcmd)
        self.normal_cast_delay3_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay3_s_label = ctk.CTkLabel(self.normal_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay3_s_label.grid(row=row, column=2, padx=(0, 20), pady=(5, 15), sticky="w")
        delay3_s_label.bind("<Button-1>", lambda e: self.root.focus())
    
    def _create_perfect_cast_flow(self):
        """Create single unified flow for Perfect Cast"""
        vcmd = (self.root.register(self._validate_delay_input), '%d', '%i', '%P', '%s', '%S', '%v', '%V', '%W')
        
        row = 0
        
        # Delay 1
        delay1_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay1_label.grid(row=row, column=0, padx=20, pady=(15, 5), sticky="w")
        delay1_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.cast_delay1_var = tk.StringVar(value=self.cast_delay1)
        self.cast_delay1_var.trace_add("write", lambda *args: self._on_cast_delay1_change())
        self.cast_delay1_entry = ctk.CTkEntry(self.perfect_cast_flow_frame, width=60, justify="center", textvariable=self.cast_delay1_var)
        self.cast_delay1_entry.grid(row=row, column=1, padx=(10, 5), pady=(15, 5), sticky="w")
        self.cast_delay1_entry.configure(validate="key", validatecommand=vcmd)
        self.cast_delay1_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay1_s_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay1_s_label.grid(row=row, column=2, padx=(0, 20), pady=(15, 5), sticky="w")
        delay1_s_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Auto Look Down (if enabled)
        look_down_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Auto Look Down (if enabled)", font=ctk.CTkFont(size=12))
        look_down_label.grid(row=row, column=0, columnspan=3, padx=20, pady=5, sticky="w")
        look_down_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Delay 2
        delay2_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay2_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        delay2_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.cast_delay2_var = tk.StringVar(value=self.cast_delay2)
        self.cast_delay2_var.trace_add("write", lambda *args: self._on_cast_delay2_change())
        self.cast_delay2_entry = ctk.CTkEntry(self.perfect_cast_flow_frame, width=60, justify="center", textvariable=self.cast_delay2_var)
        self.cast_delay2_entry.grid(row=row, column=1, padx=(10, 5), pady=5, sticky="w")
        self.cast_delay2_entry.configure(validate="key", validatecommand=vcmd)
        self.cast_delay2_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay2_s_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay2_s_label.grid(row=row, column=2, padx=(0, 20), pady=5, sticky="w")
        delay2_s_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Hold Left Click
        hold_click_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Hold Left Click", font=ctk.CTkFont(size=12))
        hold_click_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        hold_click_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Delay 3
        delay3_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay3_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        delay3_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.cast_delay3_var = tk.StringVar(value=self.cast_delay3)
        self.cast_delay3_var.trace_add("write", lambda *args: self._on_cast_delay3_change())
        self.cast_delay3_entry = ctk.CTkEntry(self.perfect_cast_flow_frame, width=60, justify="center", textvariable=self.cast_delay3_var)
        self.cast_delay3_entry.grid(row=row, column=1, padx=(10, 5), pady=5, sticky="w")
        self.cast_delay3_entry.configure(validate="key", validatecommand=vcmd)
        self.cast_delay3_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay3_s_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay3_s_label.grid(row=row, column=2, padx=(0, 20), pady=5, sticky="w")
        delay3_s_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Perfect Cast Release
        release_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Perfect Cast Release", font=ctk.CTkFont(size=12))
        release_label.grid(row=row, column=0, padx=20, pady=5, sticky="w")
        release_label.bind("<Button-1>", lambda e: self.root.focus())
        row += 1
        
        # Delay 4
        delay4_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="Delay:", font=ctk.CTkFont(size=12))
        delay4_label.grid(row=row, column=0, padx=20, pady=(5, 15), sticky="w")
        delay4_label.bind("<Button-1>", lambda e: self.root.focus())
        
        self.cast_delay4_var = tk.StringVar(value=self.cast_delay4)
        self.cast_delay4_var.trace_add("write", lambda *args: self._on_cast_delay4_change())
        self.cast_delay4_entry = ctk.CTkEntry(self.perfect_cast_flow_frame, width=60, justify="center", textvariable=self.cast_delay4_var)
        self.cast_delay4_entry.grid(row=row, column=1, padx=(10, 5), pady=(5, 15), sticky="w")
        self.cast_delay4_entry.configure(validate="key", validatecommand=vcmd)
        self.cast_delay4_entry.bind("<Return>", lambda e: self.root.focus())
        
        delay4_s_label = ctk.CTkLabel(self.perfect_cast_flow_frame, text="s", font=ctk.CTkFont(size=12))
        delay4_s_label.grid(row=row, column=2, padx=(0, 20), pady=(5, 15), sticky="w")
        delay4_s_label.bind("<Button-1>", lambda e: self.root.focus())
    
    def _on_cast_delay1_change(self):
        """Save delay1 immediately when changed"""
        value = self.cast_delay1_var.get()
        self.storage["config"]["cast"]["delay1"] = value if value else "0.0"
        self.cast_delay1 = value if value else "0.0"
    
    def _on_cast_delay2_change(self):
        """Save delay2 immediately when changed"""
        value = self.cast_delay2_var.get()
        self.storage["config"]["cast"]["delay2"] = value if value else "0.0"
        self.cast_delay2 = value if value else "0.0"
    
    def _on_cast_delay3_change(self):
        """Save delay3 immediately when changed"""
        value = self.cast_delay3_var.get()
        self.storage["config"]["cast"]["delay3"] = value if value else "0.0"
        self.cast_delay3 = value if value else "0.0"
    
    def _on_cast_delay4_change(self):
        """Save delay4 immediately when changed"""
        value = self.cast_delay4_var.get()
        self.storage["config"]["cast"]["delay4"] = value if value else "0.0"
        self.cast_delay4 = value if value else "0.0"
    
    def _save_cast_delay_values(self):
        """Save cast delay values from entries to storage"""
        try:
            value1 = self.cast_delay1_entry.get()
            self.storage["config"]["cast"]["delay1"] = value1 if value1 else "0.0"
            self.cast_delay1 = value1 if value1 else "0.0"
        except:
            pass
        
        try:
            value2 = self.cast_delay2_entry.get()
            self.storage["config"]["cast"]["delay2"] = value2 if value2 else "0.0"
            self.cast_delay2 = value2 if value2 else "0.0"
        except:
            pass
        
        try:
            value3 = self.cast_delay3_entry.get()
            self.storage["config"]["cast"]["delay3"] = value3 if value3 else "0.0"
            self.cast_delay3 = value3 if value3 else "0.0"
        except:
            pass
        
        try:
            value4 = self.cast_delay4_entry.get()
            self.storage["config"]["cast"]["delay4"] = value4 if value4 else "0.0"
            self.cast_delay4 = value4 if value4 else "0.0"
        except:
            pass
    
    def _on_normal_cast_delay1_change(self):
        """Save normal cast delay1 immediately when changed"""
        value = self.normal_cast_delay1_var.get()
        self.storage["config"]["cast"]["normal_delay1"] = value if value else "0.0"
        self.normal_cast_delay1 = value if value else "0.0"
    
    def _on_normal_cast_delay2_change(self):
        """Save normal cast delay2 immediately when changed"""
        value = self.normal_cast_delay2_var.get()
        self.storage["config"]["cast"]["normal_delay2"] = value if value else "0.0"
        self.normal_cast_delay2 = value if value else "0.0"
    
    def _on_normal_cast_delay3_change(self):
        """Save normal cast delay3 immediately when changed"""
        value = self.normal_cast_delay3_var.get()
        self.storage["config"]["cast"]["normal_delay3"] = value if value else "0.0"
        self.normal_cast_delay3 = value if value else "0.0"
    
    def _save_normal_cast_delay_values(self):
        """Save normal cast delay values from entries to storage"""
        try:
            value1 = self.normal_cast_delay1_entry.get()
            self.storage["config"]["cast"]["normal_delay1"] = value1 if value1 else "0.0"
            self.normal_cast_delay1 = value1 if value1 else "0.0"
        except:
            pass
        
        try:
            value2 = self.normal_cast_delay2_entry.get()
            self.storage["config"]["cast"]["normal_delay2"] = value2 if value2 else "0.0"
            self.normal_cast_delay2 = value2 if value2 else "0.0"
        except:
            pass
        
        try:
            value3 = self.normal_cast_delay3_entry.get()
            self.storage["config"]["cast"]["normal_delay3"] = value3 if value3 else "0.0"
            self.normal_cast_delay3 = value3 if value3 else "0.0"
        except:
            pass

    def _start_rebind(self, hotkey_name):
        """Start hotkey rebinding"""
        if self.waiting_for_hotkey:
            return
        self.waiting_for_hotkey = True
        self.hotkey_waiting_for = hotkey_name
        self.hotkey_labels[hotkey_name].configure(text="PRESS A KEY")
        
        # Temporarily disable all global hotkeys to prevent conflicts during rebinding
        try:
            keyboard.unhook_all()
        except:
            pass

    def _start_rebind_hotbar(self, hotbar_name):
        """Start hotbar rebinding"""
        if self.waiting_for_hotbar:
            return
        self.waiting_for_hotbar = True
        self.hotbar_waiting_for = hotbar_name
        
        if hotbar_name == "fishing_rod":
            self.fishing_rod_value.configure(text="PRESS A KEY")
        elif hotbar_name == "equipment_bag":
            self.equipment_bag_value.configure(text="PRESS A KEY")

    def _get_auto_rod_delay1(self):
        """Get the first auto rod delay value"""
        try:
            value = self.auto_rod_delay1_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_select_rod"]["delay1"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _get_auto_rod_delay2(self):
        """Get the second auto rod delay value"""
        try:
            value = self.auto_rod_delay2_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_select_rod"]["delay2"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _get_auto_rod_delay3(self):
        """Get the third auto rod delay value"""
        try:
            value = self.auto_rod_delay3_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_select_rod"]["delay3"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _get_auto_zoom_delay1(self):
        """Get the first auto zoom delay value"""
        try:
            value = self.auto_zoom_in_delay1_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_zoom_in"]["delay1"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _get_auto_zoom_in_amount(self):
        """Get the zoom in amount value"""
        try:
            value = self.auto_zoom_in_amount_entry.get()
            amount = int(value) if value else 12
            self.storage["config"]["auto_zoom_in"]["zoom_in_amount"] = value
            return amount
        except (ValueError, AttributeError):
            return 12

    def _get_auto_zoom_delay2(self):
        """Get the second auto zoom delay value"""
        try:
            value = self.auto_zoom_in_delay2_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_zoom_in"]["delay2"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _get_auto_zoom_out_amount(self):
        """Get the zoom out amount value"""
        try:
            value = self.auto_zoom_out_amount_entry.get()
            amount = int(value) if value else 1
            self.storage["config"]["auto_zoom_in"]["zoom_out_amount"] = value
            return amount
        except (ValueError, AttributeError):
            return 1

    def _get_auto_zoom_delay3(self):
        """Get the third auto zoom delay value"""
        try:
            value = self.auto_zoom_in_delay3_entry.get()
            delay = float(value) if value else 0.0
            self.storage["config"]["auto_zoom_in"]["delay3"] = value
            return delay
        except (ValueError, AttributeError):
            return 0.0

    def _toggle_always_on_top(self):
        """Toggle always on top"""
        self.always_on_top = not self.always_on_top
        self.storage["config"]["toggles"]["always_on_top"] = self.always_on_top
        if self.always_on_top:
            self.always_on_top_switch.configure(text="ON")
            # Enable always on top
            self.root.attributes('-topmost', True)
            # Bind events to maintain topmost status
            self.root.bind('<FocusIn>', self._maintain_topmost)
            self.root.bind('<Visibility>', self._maintain_topmost)
        else:
            self.always_on_top_switch.configure(text="OFF")
            # Disable always on top
            self.root.attributes('-topmost', False)
            # Unbind events
            self.root.unbind('<FocusIn>')
            self.root.unbind('<Visibility>')

    def _maintain_topmost(self, event=None):
        """Maintain topmost status when focus changes (only if enabled)"""
        if self.always_on_top:
            self.root.attributes('-topmost', True)

    def _toggle_auto_minimize(self):
        """Toggle auto minimize"""
        self.auto_minimize = not self.auto_minimize
        self.storage["config"]["toggles"]["auto_minimize"] = self.auto_minimize
        if self.auto_minimize:
            self.auto_minimize_switch.configure(text="ON")
        else:
            self.auto_minimize_switch.configure(text="OFF")

    def _toggle_auto_move_roblox(self):
        """Toggle auto move Roblox"""
        self.auto_move_roblox = not self.auto_move_roblox
        self.storage["config"]["toggles"]["auto_move_roblox"] = self.auto_move_roblox
        if self.auto_move_roblox:
            self.auto_move_roblox_switch.configure(text="ON")
        else:
            self.auto_move_roblox_switch.configure(text="OFF")

    def _toggle_auto_focus_roblox(self):
        """Toggle auto focus Roblox"""
        self.auto_focus_roblox = not self.auto_focus_roblox
        self.storage["config"]["toggles"]["auto_focus_roblox"] = self.auto_focus_roblox
        if self.auto_focus_roblox:
            self.auto_focus_switch.configure(text="ON")
        else:
            self.auto_focus_switch.configure(text="OFF")

    def _toggle_auto_zoom_in(self):
        """Toggle auto zoom in"""
        self.auto_zoom_in = not self.auto_zoom_in
        self.storage["config"]["toggles"]["auto_zoom_in"] = self.auto_zoom_in
        if self.auto_zoom_in:
            self.auto_zoom_in_switch.configure(text="ON")
            # Show the options frame
            self.auto_zoom_in_frame.grid(row=2, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        else:
            self.auto_zoom_in_switch.configure(text="OFF")
            # Hide the options frame
            self.auto_zoom_in_frame.grid_remove()

    def _toggle_auto_select_rod(self):
        """Toggle auto select rod"""
        self.auto_select_rod = not self.auto_select_rod
        self.storage["config"]["toggles"]["auto_select_rod"] = self.auto_select_rod
        if self.auto_select_rod:
            self.auto_select_rod_switch.configure(text="ON")
            # Show the options frame
            self.auto_select_rod_frame.grid(row=4, column=0, columnspan=3, sticky="w", padx=30, pady=(0, 10))
        else:
            self.auto_select_rod_switch.configure(text="OFF")
            # Hide the options frame
            self.auto_select_rod_frame.grid_remove()

    def _toggle_perfect_cast_overlay(self):
        """Toggle perfect cast overlay"""
        self.perfect_cast_overlay = not self.perfect_cast_overlay
        self.storage["config"]["toggles"]["perfect_cast_overlay"] = self.perfect_cast_overlay
        if self.perfect_cast_overlay:
            self.perfect_cast_overlay_switch.configure(text="ON")
        else:
            self.perfect_cast_overlay_switch.configure(text="OFF")

    def _toggle_fish_overlay(self):
        """Toggle fish overlay"""
        self.fish_overlay = not self.fish_overlay
        self.storage["config"]["toggles"]["fish_overlay"] = self.fish_overlay
        if self.fish_overlay:
            self.fish_overlay_switch.configure(text="ON")
        else:
            self.fish_overlay_switch.configure(text="OFF")

    def _setup_global_hotkeys(self):
        """Setup global hotkey listeners"""
        # Remove all existing hotkeys first
        try:
            keyboard.unhook_all()
        except:
            pass
        
        # Register new hotkeys
        hotkeys = self.storage["config"]["hotkeys"]
        keyboard.add_hotkey(hotkeys["exit"], lambda: self.root.after(0, self._exit_application))
        keyboard.add_hotkey(hotkeys["change_scan"], lambda: self.root.after(0, self._toggle_area_selector))
        keyboard.add_hotkey(hotkeys["start_stop"], lambda: self.root.after(0, self._toggle_start_stop))

    def _exit_application(self):
        """Exit the application"""
        # Save config before exiting
        self._save_config()
        self.root.quit()

    def _on_window_close(self):
        """Handle window close event (X button)"""
        # Save config before closing
        self._save_config()
        self.root.destroy()

    def _on_key_press(self, event):
        """Handle key press events for hotkey rebinding and hotbar rebinding"""
        # Handle hotbar rebinding
        if self.waiting_for_hotbar:
            key_name = event.keysym
            
            # Only accept numeric keys 0-9
            if key_name in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                # Update the hotbar value
                if self.hotbar_waiting_for == "fishing_rod":
                    self.fishing_rod_hotbar = key_name
                    self.storage["config"]["hotbar"]["fishing_rod"] = key_name
                    self.fishing_rod_value.configure(text=key_name)
                    # Also update Auto Select Rod entry if it exists
                    if hasattr(self, 'auto_rod_fishing_rod_entry'):
                        self.auto_rod_fishing_rod_entry.configure(state="normal")
                        self.auto_rod_fishing_rod_entry.delete(0, tk.END)
                        self.auto_rod_fishing_rod_entry.insert(0, key_name)
                        self.auto_rod_fishing_rod_entry.configure(state="disabled")
                elif self.hotbar_waiting_for == "equipment_bag":
                    self.equipment_bag_hotbar = key_name
                    self.storage["config"]["hotbar"]["equipment_bag"] = key_name
                    self.equipment_bag_value.configure(text=key_name)
                    # Also update Auto Select Rod entry if it exists
                    if hasattr(self, 'auto_rod_equipment_bag_entry'):
                        self.auto_rod_equipment_bag_entry.configure(state="normal")
                        self.auto_rod_equipment_bag_entry.delete(0, tk.END)
                        self.auto_rod_equipment_bag_entry.insert(0, key_name)
                        self.auto_rod_equipment_bag_entry.configure(state="disabled")
                
                # Reset state
                self.waiting_for_hotbar = False
                self.hotbar_waiting_for = None
            else:
                # Invalid key - restore original value
                if self.hotbar_waiting_for == "fishing_rod":
                    self.fishing_rod_value.configure(text=self.fishing_rod_hotbar)
                elif self.hotbar_waiting_for == "equipment_bag":
                    self.equipment_bag_value.configure(text=self.equipment_bag_hotbar)
                
                # Reset state
                self.waiting_for_hotbar = False
                self.hotbar_waiting_for = None
            
            return "break"
        
        # Handle hotkey rebinding
        if not self.waiting_for_hotkey:
            return "break"

        key_name = event.keysym
        old_hotkey = self.storage["config"]["hotkeys"][self.hotkey_waiting_for]

        # Check if this key is already in use by another hotkey
        for hotkey_type, assigned_key in self.storage["config"]["hotkeys"].items():
            # Skip non-string values (like freeze_while_toggled boolean)
            if not isinstance(assigned_key, str):
                continue
            if hotkey_type != self.hotkey_waiting_for and assigned_key.lower() == key_name.lower():
                # Key is already in use - reject and restore original
                self.hotkey_labels[self.hotkey_waiting_for].configure(text=old_hotkey)
                self.waiting_for_hotkey = False
                self.hotkey_waiting_for = None
                
                # Show error message briefly
                self.hotkey_labels[hotkey_type].configure(text_color="red")
                self.root.after(500, lambda: self.hotkey_labels[hotkey_type].configure(text_color="green"))
                
                # Re-enable hotkeys
                self._setup_global_hotkeys()
                return "break"

        # Update the hotkey in storage
        self.storage["config"]["hotkeys"][self.hotkey_waiting_for] = key_name
        display_name = key_name.upper() if len(key_name) == 1 else key_name
        self.hotkey_labels[self.hotkey_waiting_for].configure(text=display_name)

        # Reset state
        self.waiting_for_hotkey = False
        self.hotkey_waiting_for = None
        
        # Re-register all global hotkeys with the new binding
        self._setup_global_hotkeys()
        
        return "break"

    def _toggle_area_selector(self):
        """Toggle the area selector overlay"""
        if self.area_selector_active:
            if hasattr(self, 'area_selector') and self.area_selector:
                try:
                    shake_coords = {
                        "x": int(self.area_selector.shake_x1),
                        "y": int(self.area_selector.shake_y1),
                        "width": int(self.area_selector.shake_x2 - self.area_selector.shake_x1),
                        "height": int(self.area_selector.shake_y2 - self.area_selector.shake_y1)
                    }
                    fish_coords = {
                        "x": int(self.area_selector.fish_x1),
                        "y": int(self.area_selector.fish_y1),
                        "width": int(self.area_selector.fish_x2 - self.area_selector.fish_x1),
                        "height": int(self.area_selector.fish_y2 - self.area_selector.fish_y1)
                    }
                    self.storage["config"]["areas"]["shake"] = shake_coords
                    self.storage["config"]["areas"]["fish"] = fish_coords
                    
                    # Print the new areas
                    print(f"Shake Area Set: x={shake_coords['x']}, y={shake_coords['y']}, width={shake_coords['width']}, height={shake_coords['height']}")
                    print(f"Fish Area Set: x={fish_coords['x']}, y={fish_coords['y']}, width={fish_coords['width']}, height={fish_coords['height']}")
                except:
                    pass

                try:
                    self.area_selector.window.destroy()
                except:
                    pass
            
            # Close the zoom window if it exists
            try:
                if self.area_selector and self.area_selector.zoom_window_created:
                    # Cancel scheduled updates
                    if self.area_selector.zoom_update_job:
                        self.area_selector.window.after_cancel(self.area_selector.zoom_update_job)
                        self.area_selector.zoom_update_job = None
                    cv2.destroyWindow(self.area_selector.zoom_window_name)
                    self.area_selector.zoom_window_created = False
                    self.area_selector.zoom_hwnd = None
            except:
                pass
            
            self.area_selector_active = False
            
            # Restore window if auto minimize is enabled
            if self.auto_minimize:
                self.root.deiconify()
                self.root.lift()
                self.root.focus_force()
        else:
            # Minimize window before opening area selector if auto minimize is enabled
            if self.auto_minimize:
                self.root.iconify()
                # Small delay to ensure window is minimized before screenshot
                self.root.after(100, self._open_area_selector)
            else:
                self._open_area_selector()

    def _open_area_selector(self):
        """Open the area selector overlay"""
        if self.area_selector_active:
            return

        self.area_selector_active = True
        
        # Always take screenshot (always frozen mode)
        screenshot = ImageGrab.grab()
        
        shake_area = self.storage["config"]["areas"]["shake"]
        fish_area = self.storage["config"]["areas"]["fish"]

        self.area_selector = DualAreaSelector(self.root, screenshot, shake_area, fish_area, None)

    def _toggle_start_stop(self):
        """Toggle the main loop on/off"""
        # Don't allow start/stop while area selector is active
        if self.area_selector_active:
            print("Cannot start/stop while area selector is open")
            return
        
        if self.is_running:
            # Stop the loop - set event to interrupt immediately
            self.is_running = False
            self.stop_event.set()  # Signal all waits to stop immediately
            print("STOPPING...")
        else:
            # Start the loop from the beginning
            self.stop_event.clear()  # Clear the stop signal
            self.is_running = True
            print("STARTED")
            
            # Run one-time initialization before starting the loop
            self._on_start()
            
            # Start the main loop in a separate thread so GUI remains responsive
            loop_thread = threading.Thread(target=self._run_loop, daemon=True)
            loop_thread.start()

    def _check_windows_capture(self):
        """Check if Windows Capture is available and working (only if selected)"""
        # Check if user selected Windows Capture mode
        capture_mode = self.storage["config"].get("capture_mode", "Windows Capture")
        
        if capture_mode != "Windows Capture":
            # MSS mode selected, no need to check Windows Capture
            return True
        
        print("Checking Windows Capture availability...")
        
        # Test 1: Import check
        try:
            from windows_capture import WindowsCapture, Frame, InternalCaptureControl
            print("Windows Capture: Library imported successfully")
        except ImportError as e:
            print(f"Windows Capture: Import failed - {e}")
            messagebox.showerror(
                "Windows Capture Not Available",
                f"Windows Capture library is not available.\n\n"
                f"This may be due to:\n"
                f"- Running on Windows 10 (requires Windows 11)\n"
                f"- Library not installed\n\n"
                f"Please switch to MSS mode in Misc tab → Capture Mode"
            )
            self.stop_event.set()
            self.is_running = False
            return False
        
        # Test 2: Create capture instance
        try:
            test_capture = WindowsCapture(
                cursor_capture=False,
                draw_border=False,
                monitor_index=1,
                window_name=None,
            )
            print("Windows Capture: Instance created successfully")
        except Exception as e:
            print(f"Windows Capture: Failed to create capture - {e}")
            messagebox.showerror(
                "Windows Capture Failed",
                f"Failed to initialize Windows Capture.\n\n"
                f"Error: {str(e)}\n\n"
                f"Please switch to MSS mode in Misc tab → Capture Mode"
            )
            self.stop_event.set()
            self.is_running = False
            return False
        
        # Test 3: Verify capture can start (quick test)
        test_successful = False
        
        @test_capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal test_successful
            test_successful = True
            capture_control.stop()
        
        @test_capture.event
        def on_closed():
            pass
        
        try:
            # Start capture in non-blocking mode
            test_capture.start_free_threaded()
            
            # Wait up to 2 seconds for a frame
            wait_time = 0
            while not test_successful and wait_time < 2.0:
                time.sleep(0.1)
                wait_time += 0.1
            
            # Small cleanup delay
            time.sleep(0.1)
            
            if not test_successful:
                print("Windows Capture: No frames received")
                messagebox.showerror(
                    "Windows Capture Not Working",
                    f"Windows Capture started but received no frames.\n\n"
                    f"This may indicate:\n"
                    f"- Windows 11 Graphics Capture API is disabled\n"
                    f"- Display driver issues\n"
                    f"- System compatibility problems\n\n"
                    f"Please switch to MSS mode in Misc tab → Capture Mode"
                )
                self.stop_event.set()
                self.is_running = False
                return False
            
            print("Windows Capture: Verified working successfully")
            return True
            
        except Exception as e:
            print(f"Windows Capture: Start test failed - {e}")
            messagebox.showerror(
                "Windows Capture Error",
                f"Windows Capture failed to start.\n\n"
                f"Error: {str(e)}\n\n"
                f"Please switch to MSS mode in Misc tab → Capture Mode"
            )
            self.stop_event.set()
            self.is_running = False
            return False

    def _on_start(self):
        """Runs once when the loop starts"""
        print("Running one-time setup on start...")
        
        # Check Windows Capture if selected
        if not self._check_windows_capture():
            return  # Check failed, stop event already set
        
        # Initialize auto zoom ran once flag
        if self.auto_zoom_in:
            # If Cast Method is Perfect, skip auto zoom
            if self.cast_method_var.get() == "Perfect":
                self.auto_zoom_ran_once = True
            else:
                self.auto_zoom_ran_once = False
        
        # Auto minimize if enabled
        if self.auto_minimize:
            self.root.iconify()
        
        # Auto move Roblox if enabled
        if self.auto_move_roblox:
            self._move_roblox_to_monitor1()
        
        # Auto focus Roblox if enabled
        if self.auto_focus_roblox:
            self._focus_roblox_window()
        
        time.sleep(0.5)  # Small delay to ensure all setup is done
        # Add any one-time initialization here

    def _focus_roblox_window(self):
        """Focus on the Roblox window"""
        try:
            # Search for Roblox window (case-insensitive)
            windows = gw.getWindowsWithTitle('Roblox')
            if windows:
                roblox_window = windows[0]
                roblox_window.activate()
                print("Focused on Roblox window")
            else:
                print("Roblox window not found")
        except Exception as e:
            print(f"Error focusing Roblox window: {e}")

        # Move cursor to center of screen
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2
        win32api.SetCursorPos((center_x, center_y))

    def _move_roblox_to_monitor1(self):
        """Move Roblox window to monitor 1 (primary monitor), maximize it, and enter fullscreen if needed"""
        try:
            # Find Roblox window
            roblox_windows = gw.getWindowsWithTitle('Roblox')
            
            if not roblox_windows:
                print("Move Roblox: Window not found")
                return False
            
            # Get the first Roblox window
            roblox = roblox_windows[0]
            
            print(f"Move Roblox: Found '{roblox.title}'")
            
            # Move to monitor 1 (position 0, 0 is top-left of primary monitor)
            roblox.moveTo(0, 0)
            time.sleep(0.1)
            
            # Maximize the window
            roblox.maximize()
            
            print("Move Roblox: Moved to monitor 1 and maximized")
            
            time.sleep(0.3)  # Wait for window to settle
            
            # Check if it's already fullscreen
            hwnd = roblox._hWnd
            left, top, right, bottom = win32gui.GetWindowRect(hwnd)
            width = right - left
            height = bottom - top
            
            screen_width = win32api.GetSystemMetrics(0)
            screen_height = win32api.GetSystemMetrics(1)
            
            is_fullscreen = (width >= screen_width and height >= screen_height)
            
            if is_fullscreen:
                print("Move Roblox: Already in fullscreen mode")
            else:
                print("Move Roblox: Entering fullscreen mode (pressing F11)...")
                roblox.activate()
                time.sleep(0.2)
                keyboard.press_and_release('f11')
                print("Move Roblox: Pressed F11")
            
            return True
            
        except Exception as e:
            print(f"Move Roblox: Error - {e}")
            return False

    def _on_stop(self):
        """Runs once when the loop stops (called after loop actually stops)"""
        print("Running one-time cleanup on stop...")
        
        # Restore window if auto minimize was enabled
        if self.auto_minimize:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
        
        # Add any one-time cleanup here

    def _run_loop(self):
        """Main loop that cycles through Misc > Cast > Shake > Fish"""
        while self.is_running and not self.stop_event.is_set():
            # Execute Misc
            self._misc()
            if self.stop_event.is_set():
                break
            
            # Execute Cast
            self._cast()
            if self.stop_event.is_set():
                break
            
            # Execute Shake
            shake_result = self._shake()
            if self.stop_event.is_set():
                break
            
            # If shake timed out, skip fish and restart loop
            if shake_result == "timeout":
                print("Shake timed out - restarting loop")
                continue
            
            # Execute Fish
            self._fish()
            if self.stop_event.is_set():
                break
        
        # Loop has stopped - run cleanup
        self._on_stop()
        print("STOPPED")

    def _misc(self):
        """Misc function - Auto Zoom In and Auto Select Rod"""
        # Auto Zoom In (runs once per session)
        if self.auto_zoom_in and not self.auto_zoom_ran_once:
            self.auto_zoom_ran_once = True
            
            # Get zoom values
            delay1 = self._get_auto_zoom_delay1()
            zoom_in_amount = self._get_auto_zoom_in_amount()
            delay2 = self._get_auto_zoom_delay2()
            zoom_out_amount = self._get_auto_zoom_out_amount()
            delay3 = self._get_auto_zoom_delay3()
            
            print(f"Auto Zoom In: Delay {delay1}s")
            if self.stop_event.wait(timeout=delay1):
                return  # Interrupted
            
            if self.stop_event.is_set():
                return
            
            print(f"Auto Zoom In: Zooming in {zoom_in_amount} times")
            for i in range(zoom_in_amount):
                if self.stop_event.is_set():
                    return
                mouse.wheel(1)  # Scroll up to zoom in
                if self.stop_event.wait(timeout=0.025):
                    return  # Interrupted
            
            print(f"Auto Zoom In: Delay {delay2}s")
            if self.stop_event.wait(timeout=delay2):
                return  # Interrupted
            
            if self.stop_event.is_set():
                return
            
            print(f"Auto Zoom In: Zooming out {zoom_out_amount} times")
            for i in range(zoom_out_amount):
                if self.stop_event.is_set():
                    return
                mouse.wheel(-1)  # Scroll down to zoom out
                if self.stop_event.wait(timeout=0.025):
                    return  # Interrupted
            
            print(f"Auto Zoom In: Delay {delay3}s")
            if self.stop_event.wait(timeout=delay3):
                return  # Interrupted
            
            print("Auto Zoom In: Complete")
        
        # Auto Select Rod
        if self.auto_select_rod:
            # Get delay values
            delay1 = self._get_auto_rod_delay1()
            delay2 = self._get_auto_rod_delay2()
            delay3 = self._get_auto_rod_delay3()
            
            print(f"Auto Select Rod: Delay {delay1}s")
            if self.stop_event.wait(timeout=delay1):
                return  # Interrupted
            
            print(f"Auto Select Rod: Pressing Equipment Bag ({self.equipment_bag_hotbar})")
            keyboard.send(self.equipment_bag_hotbar)
            
            print(f"Auto Select Rod: Delay {delay2}s")
            if self.stop_event.wait(timeout=delay2):
                return  # Interrupted
            
            print(f"Auto Select Rod: Pressing Fishing Rod ({self.fishing_rod_hotbar})")
            keyboard.send(self.fishing_rod_hotbar)
            
            print(f"Auto Select Rod: Delay {delay3}s")
            if self.stop_event.wait(timeout=delay3):
                return  # Interrupted
            
            print("Auto Select Rod: Complete")
        
        # If both are disabled
        if not self.auto_zoom_in and not self.auto_select_rod:
            print("Misc (All features disabled)")

    def _auto_look_down(self):
        """
        Automatically look down in Roblox.
        Moves cursor to center of primary monitor, then simulates right-click drag downward.
        """
        # Get center of primary monitor (always monitor 1)
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        center_x = screen_width // 2
        center_y = screen_height // 2
        
        # Move cursor to center of screen
        win32api.SetCursorPos((center_x, center_y))
        if self.stop_event.wait(timeout=0.05):
            return  # Interrupted
        
        # Press right mouse button
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
        if self.stop_event.wait(timeout=0.05):
            # Release right mouse button before stopping
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return  # Interrupted
        
        # Send relative movement events to look down
        for i in range(10):
            if self.stop_event.is_set():
                # Release right mouse button before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                return
            win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 250, 0, 0)
            if self.stop_event.wait(timeout=0.001):
                # Release right mouse button before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
                return  # Interrupted
        
        if self.stop_event.wait(timeout=0.05):
            # Release right mouse button before stopping
            win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            return  # Interrupted
        
        # Release right mouse button
        win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)

    def _cast(self):
        """Cast function"""
        # Get cast method from storage
        cast_method = self.storage["config"]["cast"]["method"]
        
        if cast_method == "Disabled":
            print("Cast: Disabled")
            return
        
        elif cast_method == "Normal":
            print("Cast: Normal mode")
            
            # Get normal cast delay1
            try:
                delay1 = float(self.storage["config"]["cast"]["normal_delay1"])
            except (ValueError, KeyError):
                delay1 = 0.0
            
            print(f"Cast: Delay {delay1}s")
            if self.stop_event.wait(timeout=delay1):
                return  # Interrupted
            
            if self.stop_event.is_set():
                return
            
            # Hold left click down
            print("Cast: Holding Left Click Down")
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            
            # Get normal cast delay2
            try:
                delay2 = float(self.storage["config"]["cast"]["normal_delay2"])
            except (ValueError, KeyError):
                delay2 = 0.5
            
            print(f"Cast: Delay {delay2}s")
            if self.stop_event.wait(timeout=delay2):
                # Release left click before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return  # Interrupted
            
            if self.stop_event.is_set():
                # Release left click before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return
            
            # Release left click
            print("Cast: Releasing Left Click")
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            
            # Get normal cast delay3
            try:
                delay3 = float(self.storage["config"]["cast"]["normal_delay3"])
            except (ValueError, KeyError):
                delay3 = 1.0
            
            print(f"Cast: Delay {delay3}s")
            if self.stop_event.wait(timeout=delay3):
                return  # Interrupted
            
            print("Cast: Normal Cast Complete")
        
        elif cast_method == "Perfect":
            print("Cast: Perfect mode")
            
            # Get delay1
            try:
                delay1 = float(self.storage["config"]["cast"]["delay1"])
            except (ValueError, KeyError):
                delay1 = 0.0
            
            print(f"Cast: Delay {delay1}s")
            if self.stop_event.wait(timeout=delay1):
                return  # Interrupted
            
            if self.stop_event.is_set():
                return
            
            # Execute auto look down (only if enabled)
            if self.storage["config"]["cast"]["auto_look_down"]:
                print("Cast: Auto Look Down")
                self._auto_look_down()
                
                if self.stop_event.is_set():
                    return
            else:
                print("Cast: Auto Look Down (skipped - disabled)")
            
            # Get delay2
            try:
                delay2 = float(self.storage["config"]["cast"]["delay2"])
            except (ValueError, KeyError):
                delay2 = 0.0
            
            print(f"Cast: Delay {delay2}s")
            if self.stop_event.wait(timeout=delay2):
                return  # Interrupted
            
            if self.stop_event.is_set():
                return
            
            # Hold left click down
            print("Cast: Holding Left Click Down")
            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
            
            # Get delay3
            try:
                delay3 = float(self.storage["config"]["cast"]["delay3"])
            except (ValueError, KeyError):
                delay3 = 0.0
            
            print(f"Cast: Delay {delay3}s")
            if self.stop_event.wait(timeout=delay3):
                # Release left click before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return  # Interrupted
            
            if self.stop_event.is_set():
                # Release left click before stopping
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return
            
            # Perfect cast release detection
            print("Cast: Perfect Cast Release")
            release_success = self._perfect_cast_release()
            
            if not release_success:
                # If failed, release left click anyway
                print("Cast: Perfect Cast Release - Failed, releasing click")
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                return
            
            print("Cast: Perfect Cast Release - Complete")
            
            # Get delay4
            try:
                delay4 = float(self.storage["config"]["cast"]["delay4"])
            except (ValueError, KeyError):
                delay4 = 0.0
            
            print(f"Cast: Delay {delay4}s")
            if self.stop_event.wait(timeout=delay4):
                return  # Interrupted

    def _perfect_cast_release(self):
        """
        Scans for green and white Y coordinates and releases left click when
        the top white Y reaches 95% of the area from green Y to bottom white Y.
        Returns True if successful, False if interrupted or failed.
        """
        # Get capture mode from storage
        capture_mode = self.storage["config"].get("capture_mode", "Windows Capture")
        
        if capture_mode == "Windows Capture":
            return self._perfect_cast_release_windows_capture()
        else:
            return self._perfect_cast_release_mss()
    
    def _perfect_cast_release_windows_capture(self):
        """Perfect cast release using Windows Capture"""
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
        
        # Get tolerances from storage
        tolerance_green = self.storage["config"]["cast"]["green_tolerance"]
        tolerance_white = self.storage["config"]["cast"]["white_tolerance"]
        show_overlay = self.storage["config"]["toggles"]["perfect_cast_overlay"]
        fail_timeout = self.storage["config"]["cast"]["fail_release_timeout"]
        
        # Start timeout timer
        scan_start_time = time.time()
        
        # Tracking variables
        tracking_mode = False
        green_left_x = None
        green_right_x = None
        green_y = None
        white_y_top = None
        white_y_bottom = None
        green_padding = 50
        arrow_offset = 30
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        
        # Calculate crop offset (13% from top)
        crop_top_percent = 0.13
        crop_offset_y = int(screen_height * crop_top_percent)
        
        # Flag to track if we should release
        should_release = False
        release_executed = False
        scan_failed = False
        reached_bottom_5_percent = False  # Must reach bottom 5% before allowing 95% release
        
        # Variables for speed tracking and predictive release
        last_fill_percentage = None
        last_frame_time = None
        speed_samples = []  # Store recent speed measurements for averaging
        max_speed_samples = 20  # Number of samples to average
        
        # Create overlay if enabled
        overlay = None
        canvas = None
        arrow_ids = {}
        
        if show_overlay:
            # Create overlay for primary monitor
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-topmost', True)
            overlay.attributes('-transparentcolor', 'black')
            overlay.overrideredirect(True)
            overlay.geometry(f"{screen_width}x{screen_height}+0+0")
            overlay.configure(bg='black')
            
            canvas = tk.Canvas(overlay, bg='black', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            
            arrow_ids = {
                'green_left_horiz': None, 'green_left_vert': None,
                'green_right_horiz': None, 'green_right_vert': None,
                'white_top_left': None, 'white_top_right': None,
                'white_bottom_left': None, 'white_bottom_right': None,
                'white_bottom_up_left': None, 'white_bottom_up_right': None
            }
        
        def get_arrow_coords_horizontal(x, y, direction):
            size = 15
            if direction == 'left':
                return [x-size, y, x, y-size//2, x, y+size//2]
            else:
                return [x+size, y, x, y-size//2, x, y+size//2]
        
        def get_arrow_coords_vertical(x, y, direction):
            size = 15
            if direction == 'up':
                return [x, y-size, x-size//2, y, x+size//2, y]
            else:
                return [x, y+size, x-size//2, y, x+size//2, y]
        
        def update_or_create_arrow(canvas, arrow_id, coords, color):
            if arrow_id:
                try:
                    canvas.coords(arrow_id, *coords)
                    return arrow_id
                except:
                    return canvas.create_polygon(coords, fill=color, outline=color)
            else:
                return canvas.create_polygon(coords, fill=color, outline=color)
        
        # Create capture
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=True,
            monitor_index=1,
            window_name=None,
        )
        
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal tracking_mode, green_left_x, green_right_x, green_y
            nonlocal white_y_top, white_y_bottom, should_release, release_executed, scan_failed
            nonlocal canvas, arrow_ids, reached_bottom_5_percent
            nonlocal last_fill_percentage, last_frame_time, speed_samples
            
            # Check for timeout
            elapsed_time = time.time() - scan_start_time
            if elapsed_time > fail_timeout and not release_executed:
                print(f"Cast: Timeout after {elapsed_time:.1f}s - Forcing release")
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                release_executed = True
                scan_failed = True
                capture_control.stop()
                return
            
            # Check if stop event is set
            if self.stop_event.is_set():
                capture_control.stop()
                return
            
            try:
                buffer_view = np.frombuffer(frame.frame_buffer, dtype=np.uint8)
                frame_array = buffer_view.reshape((frame.height, frame.width, 4))
                
                # Crop away top 13% of the screen
                cropped_frame = frame_array[crop_offset_y:, :, :]
                bgr = cropped_frame[:, :, :3]
                
                if not tracking_mode:
                    # Search for green bar
                    target_green = np.array([75, 172, 97], dtype=np.int16)
                    
                    b_match = np.abs(bgr[:, :, 0].astype(np.int16) - target_green[0]) <= tolerance_green
                    g_match = np.abs(bgr[:, :, 1].astype(np.int16) - target_green[1]) <= tolerance_green
                    r_match = np.abs(bgr[:, :, 2].astype(np.int16) - target_green[2]) <= tolerance_green
                    
                    mask = r_match & g_match & b_match
                    rows, cols = np.nonzero(mask)
                    
                    if rows.size > 0:
                        found_y = rows[0]
                        same_row_mask = rows == found_y
                        cols_in_row = cols[same_row_mask]
                        
                        green_left_x = int(np.min(cols_in_row))
                        green_right_x = int(np.max(cols_in_row))
                        green_y = found_y  # Y coordinate relative to cropped frame (already offset)
                        
                        tracking_mode = True
                        print(f"Cast: Found green bar at Y={green_y} (relative to crop)")
                
                else:
                    # Track green bar with padding
                    green_top = max(0, green_y - green_padding)
                    green_bottom = min(screen_height, green_y + green_padding)
                    green_left = max(0, green_left_x - green_padding)
                    green_right = min(screen_width, green_right_x + green_padding)
                    
                    green_frame = bgr[green_top:green_bottom, green_left:green_right, :]
                    
                    target_green = np.array([75, 172, 97], dtype=np.int16)
                    
                    b_match = np.abs(green_frame[:, :, 0].astype(np.int16) - target_green[0]) <= tolerance_green
                    g_match = np.abs(green_frame[:, :, 1].astype(np.int16) - target_green[1]) <= tolerance_green
                    r_match = np.abs(green_frame[:, :, 2].astype(np.int16) - target_green[2]) <= tolerance_green
                    
                    mask = r_match & g_match & b_match
                    rows, cols = np.nonzero(mask)
                    
                    if rows.size > 0:
                        found_y_relative = rows[0]
                        same_row_mask = rows == found_y_relative
                        cols_in_row = cols[same_row_mask]
                        
                        green_left_x = int(np.min(cols_in_row)) + green_left
                        green_right_x = int(np.max(cols_in_row)) + green_left
                        green_y = found_y_relative + green_top
                        
                        # Update overlay arrows for green if enabled (adjust Y coordinates back to screen space)
                        if show_overlay and canvas:
                            screen_y = green_y + crop_offset_y  # Convert back to screen coordinates
                            arrow_ids['green_right_horiz'] = update_or_create_arrow(canvas, arrow_ids.get('green_right_horiz'), 
                                                                                    get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_y, 'left'), 'red')
                            arrow_ids['green_right_vert'] = update_or_create_arrow(canvas, arrow_ids.get('green_right_vert'), 
                                                                                   get_arrow_coords_vertical(green_right_x, screen_y - arrow_offset, 'down'), 'red')
                            arrow_ids['green_left_horiz'] = update_or_create_arrow(canvas, arrow_ids.get('green_left_horiz'), 
                                                                                   get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_y, 'right'), 'red')
                            arrow_ids['green_left_vert'] = update_or_create_arrow(canvas, arrow_ids.get('green_left_vert'), 
                                                                                  get_arrow_coords_vertical(green_left_x, screen_y - arrow_offset, 'down'), 'red')
                        
                        # Search for white bar below green (scan to 90% of cropped screen height)
                        scan_bottom = int((screen_height - crop_offset_y) * 0.9)
                        white_frame = bgr[green_y:scan_bottom, green_left_x:green_right_x, :]
                        
                        target_white = np.array([243, 254, 255], dtype=np.int16)
                        
                        b_match_w = np.abs(white_frame[:, :, 0].astype(np.int16) - target_white[0]) <= tolerance_white
                        g_match_w = np.abs(white_frame[:, :, 1].astype(np.int16) - target_white[1]) <= tolerance_white
                        r_match_w = np.abs(white_frame[:, :, 2].astype(np.int16) - target_white[2]) <= tolerance_white
                        
                        mask_white = r_match_w & g_match_w & b_match_w
                        rows_white, cols_white = np.nonzero(mask_white)
                        
                        if rows_white.size > 0:
                            white_y_top = rows_white[0] + green_y
                            white_y_bottom = rows_white[-1] + green_y
                            
                            # Calculate the fill percentage first to determine offset
                            total_distance = white_y_bottom - green_y
                            current_distance = white_y_top - green_y
                            
                            if total_distance > 0:
                                current_time = time.time()
                                actual_fill_percentage = (1 - (current_distance / total_distance)) * 100
                                
                                # Calculate speed-based position offset (only when going up)
                                fill_speed = 0
                                position_offset_percent = 0
                                
                                if last_fill_percentage is not None and last_frame_time is not None:
                                    time_delta = current_time - last_frame_time
                                    if time_delta > 0:
                                        instant_fill_speed = (actual_fill_percentage - last_fill_percentage) / time_delta  # % per second
                                        
                                        # Only apply offset when bar is going UP
                                        if instant_fill_speed > 0:
                                            # Add to speed samples for averaging
                                            speed_samples.append(instant_fill_speed)
                                            if len(speed_samples) > max_speed_samples:
                                                speed_samples.pop(0)  # Remove oldest sample
                                            
                                            # Use averaged speed for smoother prediction
                                            fill_speed = sum(speed_samples) / len(speed_samples)
                                            
                                            import math
                                            # Get release timing adjustment from storage
                                            release_timing = self.storage["config"]["cast"]["release_timing"]
                                            
                                            # Calculate base offset using logarithmic curve
                                            # More aggressive curve: faster bars get more base offset
                                            # Increased coefficient from 1.2 to 1.5 for more aggressive scaling
                                            base_offset = 1.5 * math.log(1 + fill_speed / 25.0)
                                            
                                            # Only apply multiplier for EARLIER releases (negative slider values)
                                            if release_timing < 0:
                                                # Apply release timing as a curve multiplier that scales with speed
                                                # release_timing ranges from -50 to 0 for "earlier"
                                                # The effect is stronger on fast bars, weaker on slow bars
                                                
                                                # Calculate base multiplier from slider
                                                # -50 = 11.0x, 0 = 1.0x
                                                base_multiplier = 1.0 - (release_timing / 5.0)
                                                
                                                # Scale the multiplier effect based on speed with smooth curve
                                                # Uses exponential scaling: slow bars get minimal effect, fast bars get strong effect
                                                speed_scale = min(6.0, (fill_speed / 100.0) ** 2)
                                                
                                                # Apply scaled multiplier: slow bars affected less, fast bars affected more
                                                timing_multiplier = 1.0 + (base_multiplier - 1.0) * speed_scale
                                                
                                                # Apply multiplier to base offset with increased cap
                                                position_offset_percent = max(0.0, min(50.0, base_offset * timing_multiplier))
                                            else:
                                                # For "later" releases (positive slider), don't modify the curve
                                                # Keep default prediction, threshold will be adjusted instead
                                                position_offset_percent = base_offset
                                
                                # Calculate predicted white_y_top position based on offset
                                # offset is in percentage, convert to pixels
                                offset_pixels = (position_offset_percent / 100.0) * total_distance
                                predicted_white_y_top = white_y_top - offset_pixels  # Subtract because Y decreases going up
                                
                                # Apply position offset to get predicted fill percentage
                                predicted_fill_percentage = actual_fill_percentage + position_offset_percent
                                
                                # Update overlay arrows at PREDICTED position if enabled (adjust Y coordinates back to screen space)
                                if show_overlay and canvas:
                                    screen_white_y_top = int(predicted_white_y_top) + crop_offset_y
                                    screen_white_y_bottom = white_y_bottom + crop_offset_y
                                    
                                    arrow_ids['white_top_left'] = update_or_create_arrow(canvas, arrow_ids.get('white_top_left'), 
                                                                                         get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_white_y_top, 'right'), 'yellow')
                                    arrow_ids['white_top_right'] = update_or_create_arrow(canvas, arrow_ids.get('white_top_right'), 
                                                                                          get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_white_y_top, 'left'), 'yellow')
                                    
                                    if white_y_bottom != white_y_top:
                                        arrow_ids['white_bottom_left'] = update_or_create_arrow(canvas, arrow_ids.get('white_bottom_left'), 
                                                                                               get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_white_y_bottom, 'right'), 'cyan')
                                        arrow_ids['white_bottom_right'] = update_or_create_arrow(canvas, arrow_ids.get('white_bottom_right'), 
                                                                                                get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_white_y_bottom, 'left'), 'cyan')
                                        arrow_ids['white_bottom_up_left'] = update_or_create_arrow(canvas, arrow_ids.get('white_bottom_up_left'), 
                                                                                                  get_arrow_coords_vertical(green_left_x, screen_white_y_bottom + arrow_offset, 'up'), 'cyan')
                                        arrow_ids['white_bottom_up_right'] = update_or_create_arrow(canvas, arrow_ids.get('white_bottom_up_right'), 
                                                                                                   get_arrow_coords_vertical(green_right_x, screen_white_y_bottom + arrow_offset, 'up'), 'cyan')
                                    
                                    canvas.update()
                                
                                # Adjust bottom threshold by offset so we can still detect it
                                bottom_threshold = 5.0 + position_offset_percent
                                
                                # Check if we've reached bottom threshold (start position)
                                if predicted_fill_percentage <= bottom_threshold and not reached_bottom_5_percent:
                                    reached_bottom_5_percent = True
                                    # Reset speed tracking when entering bottom - fresh start for new cycle
                                    last_fill_percentage = None
                                    last_frame_time = None
                                    speed_samples.clear()  # Clear speed samples for new cycle
                                    print(f"Cast: Reached bottom (Predicted Fill: {predicted_fill_percentage:.1f}%, Actual: {actual_fill_percentage:.1f}%, Offset: {position_offset_percent:.1f}%)")
                                
                                # Detect if bar jumped back to bottom (huge negative change means reset)
                                if last_fill_percentage is not None and (actual_fill_percentage - last_fill_percentage) < -50:
                                    # Bar cycled back to bottom, reset tracking
                                    last_fill_percentage = None
                                    last_frame_time = None
                                    speed_samples.clear()  # Clear speed samples on reset
                                
                                # Update tracking variables BEFORE checking threshold (use actual fill for speed calculation)
                                last_fill_percentage = actual_fill_percentage
                                last_frame_time = current_time
                                
                                # Get release timing for threshold adjustment
                                release_timing = self.storage["config"]["cast"]["release_timing"]
                                
                                # Calculate dynamic threshold
                                # Negative slider (earlier): uses curve multiplier, threshold stays at 95.5%
                                # Positive slider (later): curve unchanged, threshold increases
                                # 0 = 95.5%, +50 = 100%
                                if release_timing <= 0:
                                    release_threshold = 95.5
                                else:
                                    # Scale from 95.5% to 100% as slider goes from 0 to +50
                                    release_threshold = 95.5 + (release_timing / 50.0) * 4.5
                                
                                # Only check for release after we've reached bottom
                                if reached_bottom_5_percent and predicted_fill_percentage >= release_threshold and not release_executed:
                                    print(f"Speed: {fill_speed:.1f}%/s, Offset: {position_offset_percent:.1f}%, Actual: {actual_fill_percentage:.1f}%, Predicted: {predicted_fill_percentage:.1f}%, Threshold: {release_threshold:.1f}%")
                                    
                                    # Release left click
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    release_executed = True
                                    should_release = True
                                    
                                    # Stop capture
                                    capture_control.stop()
                    else:
                        # Lost tracking
                        tracking_mode = False
                        
                        # Clear arrows if overlay enabled
                        if show_overlay and canvas:
                            for key in list(arrow_ids.keys()):
                                if arrow_ids[key]:
                                    try:
                                        canvas.delete(arrow_ids[key])
                                    except:
                                        pass
                                    arrow_ids[key] = None
            
            except Exception as e:
                print(f"Cast: Scan error: {e}")
                scan_failed = True
                capture_control.stop()
        
        @capture.event
        def on_closed():
            pass
        
        # Start capture
        capture.start()
        
        # Cleanup overlay
        if overlay:
            try:
                overlay.destroy()
            except:
                pass
        
        # Return success status
        if release_executed:
            return True
        elif scan_failed:
            return False
        else:
            # Stopped by user or other reason
            return False

    def _perfect_cast_release_mss(self):
        """Perfect cast release using MSS - OPTIMIZED VERSION"""
        import mss
        import math
        import msvcrt
        
        print("Cast: Using MSS capture mode (OPTIMIZED)")
        
        # Get tolerances from storage
        tolerance_green = self.storage["config"]["cast"]["green_tolerance"]
        tolerance_white = self.storage["config"]["cast"]["white_tolerance"]
        show_overlay = self.storage["config"]["toggles"]["perfect_cast_overlay"]
        fail_timeout = self.storage["config"]["cast"]["fail_release_timeout"]
        
        # Pre-compiled target colors for faster comparison
        target_green = np.array([75, 172, 97], dtype=np.int16)
        target_white = np.array([243, 254, 255], dtype=np.int16)
        
        # Start timeout timer
        scan_start_time = time.time()
        
        # Tracking variables - reset for new monitor
        tracking_mode = False
        green_left_x = None
        green_right_x = None
        green_y = None
        white_y_top = None
        white_y_bottom = None
        green_padding = 50
        arrow_offset = 30
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        
        # Calculate crop offset (13% from top) - MSS will capture from this point
        crop_top_percent = 0.13
        crop_offset_y = int(screen_height * crop_top_percent)
        
        # Flag to track if we should release
        release_executed = False
        scan_failed = False
        reached_bottom_5_percent = False
        
        # Variables for speed tracking and predictive release
        last_fill_percentage = None
        last_frame_time = None
        speed_samples = []
        max_speed_samples = 20
        
        # Create overlay if enabled
        overlay = None
        canvas = None
        arrow_ids = {}
        
        if show_overlay:
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-topmost', True)
            overlay.attributes('-transparentcolor', 'black')
            overlay.overrideredirect(True)
            overlay.geometry(f"{screen_width}x{screen_height}+0+0")
            overlay.configure(bg='black')
            
            canvas = tk.Canvas(overlay, bg='black', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
            
            arrow_ids = {
                'green_left_horiz': None, 'green_left_vert': None,
                'green_right_horiz': None, 'green_right_vert': None,
                'white_top_left': None, 'white_top_right': None,
                'white_bottom_left': None, 'white_bottom_right': None,
                'white_bottom_up_left': None, 'white_bottom_up_right': None
            }
        
        def get_arrow_coords_horizontal(x, y, direction):
            size = 15
            if direction == 'left':
                return [x-size, y, x, y-size//2, x, y+size//2]
            else:
                return [x+size, y, x, y-size//2, x, y+size//2]
        
        def get_arrow_coords_vertical(x, y, direction):
            size = 15
            if direction == 'up':
                return [x, y-size, x-size//2, y, x+size//2, y]
            else:
                return [x, y+size, x-size//2, y, x+size//2, y]
        
        def update_or_create_arrow(canvas, arrow_id, coords, color):
            if arrow_id:
                try:
                    canvas.coords(arrow_id, *coords)
                    return arrow_id
                except:
                    return canvas.create_polygon(coords, fill=color, outline=color)
            else:
                return canvas.create_polygon(coords, fill=color, outline=color)
        
        # MSS capture loop with optimizations - Windows Capture style (no coordinate conversion)
        try:
            with mss.mss(compression_level=0) as sct:  # No compression for speed
                monitor = sct.monitors[1]
                
                # Get actual monitor dimensions from MSS
                full_screen_width = monitor["width"]
                full_screen_height = monitor["height"]
                
                # Adjust screen dimensions for cropped capture (without top 13%)
                screen_width = full_screen_width
                screen_height = full_screen_height - crop_offset_y
                
                # Show monitor setup info only once per session
                if not hasattr(self, '_mss_monitor_setup_shown'):
                    print(f"Cast: MSS using monitor 1 - full size: {full_screen_width}x{full_screen_height}, capturing from Y={crop_offset_y} (crop: 13%)")
                    self._mss_monitor_setup_shown = True
                
                # Test screenshot format once to optimize conversion method
                test_shot = sct.grab({"top": 0, "left": 0, "width": 1, "height": 1})
                use_bgra = hasattr(test_shot, 'bgra')
                use_raw = hasattr(test_shot, 'raw') and not use_bgra
                
                # Pre-allocate region dictionary to avoid repeated allocation
                region_dict = {"top": 0, "left": 0, "width": 0, "height": 0}
                
                while not release_executed and not scan_failed and not self.stop_event.is_set():
                    # Check for timeout
                    elapsed_time = time.time() - scan_start_time
                    if elapsed_time > fail_timeout:
                        print(f"Cast: Timeout after {elapsed_time:.1f}s - Forcing release")
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        release_executed = True
                        scan_failed = True
                        break
                    
                    # Simple capture approach like Windows Capture (no coordinate conversion)
                    if tracking_mode and green_y is not None and green_left_x is not None and green_right_x is not None:
                        # Define optimized capture region around known green bar area
                        capture_padding = 150
                        
                        # Calculate region bounds in cropped coordinates (relative to crop_offset_y)
                        region_left = max(0, green_left_x - capture_padding)
                        region_top = max(0, green_y - capture_padding)
                        region_right = min(screen_width, green_right_x + capture_padding)
                        region_bottom = int(screen_height * 0.9)  # Scan to 90% of cropped screen height
                        
                        # Ensure minimum size and valid dimensions
                        region_width = max(100, region_right - region_left)
                        region_height = max(100, region_bottom - region_top)
                        
                        # Final bounds check
                        if region_left + region_width > screen_width:
                            region_width = screen_width - region_left
                        if region_top + region_height > screen_height:
                            region_height = screen_height - region_top
                        
                        # Convert to absolute screen coordinates for MSS (add crop_offset_y)
                        region_dict["top"] = int(region_top + monitor["top"] + crop_offset_y)
                        region_dict["left"] = int(region_left + monitor["left"])
                        region_dict["width"] = int(region_width)
                        region_dict["height"] = int(region_height)
                        
                        screenshot = sct.grab(region_dict)
                        
                        # Track region offset for coordinate conversion
                        region_offset_x = region_left
                        region_offset_y = region_top
                    else:
                        # Full monitor capture for initial green bar detection - start from crop_offset_y
                        region_dict["top"] = monitor["top"] + crop_offset_y
                        region_dict["left"] = monitor["left"]
                        region_dict["width"] = screen_width
                        region_dict["height"] = screen_height
                        
                        screenshot = sct.grab(region_dict)
                        
                        # No region offset in full screen mode
                        region_offset_x = 0
                        region_offset_y = 0
                    
                    # Optimized NumPy conversion with pre-tested method
                    try:
                        if use_bgra:
                            bgr = np.frombuffer(screenshot.bgra, dtype=np.uint8).reshape(screenshot.height, screenshot.width, 4)[:, :, :3]
                        elif use_raw:
                            bgr = np.frombuffer(screenshot.raw, dtype=np.uint8).reshape(screenshot.height, screenshot.width, 4)[:, :, :3] 
                        else:
                            # Direct array conversion for RGB
                            bgr = np.frombuffer(screenshot.rgb, dtype=np.uint8).reshape(screenshot.height, screenshot.width, 3)
                    except:
                        # Safe fallback
                        bgr = np.array(screenshot)[:, :, :3]
                    
                    # Check frame size on first capture only
                    if not tracking_mode and green_y is None and not hasattr(self, '_mss_frame_check_shown'):
                        frame_height, frame_width = bgr.shape[:2]
                        
                        if frame_width != screen_width or frame_height != screen_height:
                            print(f"Cast: Frame size mismatch - adjusting dimensions")
                            # Update our screen dimensions to match actual frame
                            screen_width = frame_width
                            screen_height = frame_height
                        
                        self._mss_frame_check_shown = True
                    
                    if not tracking_mode:
                        # Search for green bar (optimized with fewer temporary arrays)
                        mask = (np.abs(bgr[:, :, 0].astype(np.int16) - target_green[0]) <= tolerance_green) & \
                               (np.abs(bgr[:, :, 1].astype(np.int16) - target_green[1]) <= tolerance_green) & \
                               (np.abs(bgr[:, :, 2].astype(np.int16) - target_green[2]) <= tolerance_green)
                        
                        rows, cols = np.nonzero(mask)
                        
                        if rows.size > 0:
                            found_y = rows[0]
                            same_row_mask = rows == found_y
                            cols_in_row = cols[same_row_mask]
                            
                            # Convert to monitor coordinates (like Windows Capture)
                            green_left_x = cols_in_row.min() + region_offset_x
                            green_right_x = cols_in_row.max() + region_offset_x
                            green_y = found_y + region_offset_y
                            
                            tracking_mode = True
                            # Show green bar detection only once
                            if not hasattr(self, '_mss_green_detection_shown'):
                                print(f"Cast: Found green bar at Y={green_y} (MSS tracking mode)")
                                self._mss_green_detection_shown = True
                    
                    else:
                        # Track green bar with padding (convert screen to region coordinates)
                        screen_green_top = max(0, green_y - green_padding)
                        screen_green_bottom = min(screen_height, green_y + green_padding)
                        screen_green_left = max(0, green_left_x - green_padding)
                        screen_green_right = min(screen_width, green_right_x + green_padding)
                        
                        # Convert to region-relative coordinates
                        green_top = max(0, screen_green_top - region_offset_y)
                        green_bottom = min(bgr.shape[0], screen_green_bottom - region_offset_y)
                        green_left = max(0, screen_green_left - region_offset_x)
                        green_right = min(bgr.shape[1], screen_green_right - region_offset_x)
                        
                        # Coordinate tracking simplified (Windows Capture style)
                        
                        # Check if coordinates are valid
                        if green_top >= green_bottom or green_left >= green_right:
                            if not hasattr(self, '_mss_coord_error_shown'):
                                print(f"Cast: Invalid green region coordinates - tracking reset")
                                self._mss_coord_error_shown = True
                            tracking_mode = False
                            continue
                        
                        green_frame = bgr[green_top:green_bottom, green_left:green_right, :]
                        
                        # Check green frame size
                        if green_frame.size == 0:
                            if not hasattr(self, '_mss_empty_frame_shown'):
                                print(f"Cast: Empty green frame - tracking reset")
                                self._mss_empty_frame_shown = True
                            tracking_mode = False
                            continue
                        
                        # Optimized green tracking with fewer temporary arrays
                        mask = (np.abs(green_frame[:, :, 0].astype(np.int16) - target_green[0]) <= tolerance_green) & \
                               (np.abs(green_frame[:, :, 1].astype(np.int16) - target_green[1]) <= tolerance_green) & \
                               (np.abs(green_frame[:, :, 2].astype(np.int16) - target_green[2]) <= tolerance_green)
                        
                        rows, cols = np.nonzero(mask)
                        
                        if rows.size > 0:
                            found_y_relative = rows[0]
                            same_row_mask = rows == found_y_relative
                            cols_in_row = cols[same_row_mask]
                            
                            # Convert back to monitor coordinates (like Windows Capture)
                            green_left_x = cols_in_row.min() + green_left + region_offset_x
                            green_right_x = cols_in_row.max() + green_left + region_offset_x
                            green_y = found_y_relative + green_top + region_offset_y
                            
                            # Update overlay arrows for green if enabled (adjust Y coordinates back to screen space)
                            if show_overlay and canvas:
                                screen_y = green_y + crop_offset_y  # Convert back to full screen coordinates
                                arrow_ids['green_left_horiz'] = update_or_create_arrow(
                                    canvas, arrow_ids['green_left_horiz'],
                                    get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_y, 'right'),
                                    'red'
                                )
                                arrow_ids['green_left_vert'] = update_or_create_arrow(
                                    canvas, arrow_ids['green_left_vert'],
                                    get_arrow_coords_vertical(green_left_x, screen_y - arrow_offset, 'down'),
                                    'red'
                                )
                                arrow_ids['green_right_horiz'] = update_or_create_arrow(
                                    canvas, arrow_ids['green_right_horiz'],
                                    get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_y, 'left'),
                                    'red'
                                )
                                arrow_ids['green_right_vert'] = update_or_create_arrow(
                                    canvas, arrow_ids['green_right_vert'],
                                    get_arrow_coords_vertical(green_right_x, screen_y - arrow_offset, 'down'),
                                    'red'
                                )
                            
                            # Search for white bar below green (use region-relative coordinates)
                            region_green_y = green_y - region_offset_y
                            white_frame = bgr[region_green_y:, :, :]
                            
                            # Optimized white detection with fewer temporary arrays
                            mask_white = (np.abs(white_frame[:, :, 0].astype(np.int16) - target_white[0]) <= tolerance_white) & \
                                        (np.abs(white_frame[:, :, 1].astype(np.int16) - target_white[1]) <= tolerance_white) & \
                                        (np.abs(white_frame[:, :, 2].astype(np.int16) - target_white[2]) <= tolerance_white)
                            
                            rows_white, cols_white = np.nonzero(mask_white)
                            
                            if rows_white.size > 0:
                                # Convert back to monitor coordinates (like Windows Capture)
                                white_y_top = rows_white[0] + region_green_y + region_offset_y
                                white_y_bottom = rows_white[-1] + region_green_y + region_offset_y
                                
                                total_distance = white_y_bottom - green_y
                                current_distance = white_y_top - green_y
                                
                                if total_distance > 0:
                                    actual_fill_percentage = (1 - (current_distance / total_distance)) * 100
                                    
                                    # Calculate speed and offset for prediction
                                    current_time = time.time()
                                    fill_speed = 0
                                    offset_percentage = 0
                                    
                                    if last_fill_percentage is not None and last_frame_time is not None:
                                        time_delta = current_time - last_frame_time
                                        if time_delta > 0:
                                            fill_change = actual_fill_percentage - last_fill_percentage
                                            
                                            # Reset tracking if negative jump > 50% (bar cycled to bottom)
                                            if fill_change < -50:
                                                speed_samples.clear()
                                                last_fill_percentage = None
                                                last_frame_time = None
                                                reached_bottom_5_percent = False
                                                offset_percentage = 0
                                            else:
                                                # Only track speed when going upward
                                                if fill_change > 0:
                                                    fill_speed = fill_change / time_delta
                                                    speed_samples.append(fill_speed)
                                                    if len(speed_samples) > max_speed_samples:
                                                        speed_samples.pop(0)
                                                
                                                # Use average speed (even when going downward, use last calculated offset)
                                                if speed_samples:
                                                    avg_speed = sum(speed_samples) / len(speed_samples)
                                                    
                                                    # Get release timing from storage
                                                    release_timing = self.storage["config"]["cast"]["release_timing"]
                                                    
                                                    # Calculate base offset using logarithmic formula
                                                    base_offset = 1.5 * math.log(1 + avg_speed / 25.0)
                                                    
                                                    # Apply advanced timing multiplier if release_timing < 0
                                                    if release_timing < 0:
                                                        base_multiplier = 1.0 - (release_timing / 5.0)
                                                        speed_scaling = min(6.0, (avg_speed / 100.0) ** 2)
                                                        timing_multiplier = base_multiplier + (base_multiplier - 1.0) * speed_scaling
                                                        offset_percentage = base_offset * timing_multiplier
                                                    else:
                                                        offset_percentage = base_offset
                                                    
                                                    # Cap offset at 50%
                                                    offset_percentage = min(50.0, offset_percentage)
                                    
                                    # Calculate predicted position (only if not resetting)
                                    if last_fill_percentage is not None:
                                        predicted_fill_percentage = actual_fill_percentage + offset_percentage
                                        offset_pixels = int((offset_percentage / 100.0) * total_distance)
                                        predicted_white_y_top = white_y_top - offset_pixels
                                        
                                        # Speed tracking is working - no debug spam needed
                                    else:
                                        # First frame - no prediction yet
                                        predicted_fill_percentage = actual_fill_percentage
                                        predicted_white_y_top = white_y_top
                                    
                                    # Adjust bottom threshold by offset so we can still detect it
                                    bottom_threshold = 5.0 + offset_percentage
                                    
                                    # Check if we've reached bottom threshold (start position)
                                    if predicted_fill_percentage <= bottom_threshold and not reached_bottom_5_percent:
                                        reached_bottom_5_percent = True
                                        # Reset speed tracking when entering bottom - fresh start for new cycle
                                        last_fill_percentage = None
                                        last_frame_time = None
                                        speed_samples.clear()
                                        print(f"Cast: Reached bottom (Predicted Fill: {predicted_fill_percentage:.1f}%, Actual: {actual_fill_percentage:.1f}%, Offset: {offset_percentage:.1f}%)")
                                    
                                    # Update overlay (adjust Y coordinates back to screen space)
                                    if show_overlay and canvas:
                                        screen_white_y_top = predicted_white_y_top + crop_offset_y
                                        screen_white_y_bottom = white_y_bottom + crop_offset_y
                                        
                                        # Top arrows (yellow for predicted position) - use green bar x positions
                                        arrow_ids['white_top_left'] = update_or_create_arrow(
                                            canvas, arrow_ids['white_top_left'],
                                            get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_white_y_top, 'right'),
                                            'yellow'
                                        )
                                        arrow_ids['white_top_right'] = update_or_create_arrow(
                                            canvas, arrow_ids['white_top_right'],
                                            get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_white_y_top, 'left'),
                                            'yellow'
                                        )
                                        
                                        # Bottom arrows (cyan for actual bottom) - use green bar x positions
                                        if white_y_bottom != white_y_top:
                                            arrow_ids['white_bottom_left'] = update_or_create_arrow(
                                                canvas, arrow_ids['white_bottom_left'],
                                                get_arrow_coords_horizontal(green_left_x - arrow_offset, screen_white_y_bottom, 'right'),
                                                'cyan'
                                            )
                                            arrow_ids['white_bottom_right'] = update_or_create_arrow(
                                                canvas, arrow_ids['white_bottom_right'],
                                                get_arrow_coords_horizontal(green_right_x + arrow_offset, screen_white_y_bottom, 'left'),
                                                'cyan'
                                            )
                                            arrow_ids['white_bottom_up_left'] = update_or_create_arrow(
                                                canvas, arrow_ids['white_bottom_up_left'],
                                                get_arrow_coords_vertical(green_left_x, screen_white_y_bottom + arrow_offset, 'up'),
                                                'cyan'
                                            )
                                            arrow_ids['white_bottom_up_right'] = update_or_create_arrow(
                                                canvas, arrow_ids['white_bottom_up_right'],
                                                get_arrow_coords_vertical(green_right_x, screen_white_y_bottom + arrow_offset, 'up'),
                                                'cyan'
                                            )
                                    
                                    # Check for release condition
                                    # Get release timing from storage for threshold calculation
                                    release_timing = self.storage["config"]["cast"]["release_timing"]
                                    
                                    # Calculate release threshold based on slider
                                    if release_timing <= 0:
                                        release_threshold = 95.5
                                    else:
                                        # Scale from 95.5% to 100% as slider goes from 0 to +50
                                        release_threshold = 95.5 + (release_timing / 50.0) * 4.5
                                    
                                    # Only check for release after we've reached bottom
                                    if reached_bottom_5_percent and predicted_fill_percentage >= release_threshold:
                                        print(f"Cast: Perfect! Releasing at {predicted_fill_percentage:.1f}%")
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                        release_executed = True
                                        break
                                    
                                    # Update for next iteration
                                    last_fill_percentage = actual_fill_percentage
                                    last_frame_time = current_time
                        else:
                            # Lost tracking of green bar - go back to full scan mode
                            if not hasattr(self, '_mss_lost_tracking_shown'):
                                print(f"Cast: Lost green bar tracking - returning to full scan")
                                self._mss_lost_tracking_shown = True
                            tracking_mode = False
                            green_y = None
                            green_left_x = None  
                            green_right_x = None
                    
                    # Update overlay if enabled
                    if show_overlay and canvas:
                        try:
                            canvas.update()
                        except:
                            pass
                    
                    # No delay - maximum responsiveness for casting
        
        except Exception as e:
            print(f"Cast: MSS capture error: {e}")
            if not release_executed:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                release_executed = True
                scan_failed = True
        
        # Cleanup overlay
        if overlay:
            try:
                overlay.destroy()
            except:
                pass
        
        # Return success status
        if release_executed:
            return True
        elif scan_failed:
            return False
        else:
            return False

    def _shake(self):
        """Shake function - Returns 'timeout' if shake times out, None otherwise"""
        # Get shake method from storage
        shake_method = self.storage["config"]["shake"]["method"]
        
        if shake_method == "Disabled":
            print("Shake: Disabled")
            return None
        
        elif shake_method == "Pixel":
            print("Shake: Pixel mode")
            return self._shake_pixel()
        
        elif shake_method == "Navigation":
            print("Shake: Navigation mode")
            return self._shake_navigation()
        
        else:
            print(f"Shake: Unknown method '{shake_method}'")
            return None

    def _shake_navigation(self):
        """Navigation shake detection - spams navigation key - Returns 'timeout' if timed out"""
        # Get capture mode from storage
        capture_mode = self.storage["config"].get("capture_mode", "Windows Capture")
        
        if capture_mode == "MSS":
            print("Shake: Using MSS capture mode")
            return self._shake_navigation_mss()
        else:
            print("Shake: Using Windows Capture mode")
            return self._shake_navigation_windows_capture()
    
    def _shake_navigation_windows_capture(self):
        """Navigation shake detection using Windows Capture"""
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
        
        # Get settings from storage
        spam_delay_ms = self.storage["config"]["shake"]["navigation_spam_delay"]
        fail_timeout = self.storage["config"]["shake"]["navigation_fail_timeout"]
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        
        print(f"Shake: Navigation - Spam delay: {spam_delay_ms}ms")
        print(f"Shake: Navigation - Fail timeout: {fail_timeout}s")
        print(f"Shake: Navigation - Green tolerance: {green_tolerance}")
        
        # Target green color (BGR format)
        target_green = np.array([155, 255, 155], dtype=np.uint8)  # #9bff9b in BGR
        
        # Tracking variables
        is_capturing = True
        shake_timeout_start = time.time()
        shake_timed_out = False
        spam_delay_seconds = spam_delay_ms / 1000.0
        
        # Create capture
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=True,
            monitor_index=1,
            window_name=None,
        )
        
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal is_capturing, shake_timeout_start, shake_timed_out
            
            # Check if stop event is set
            if self.stop_event.is_set():
                is_capturing = False
                capture_control.stop()
                return
            
            try:
                # Check for timeout
                elapsed_time = time.time() - shake_timeout_start
                if elapsed_time > fail_timeout:
                    print(f"Shake: Navigation timeout after {elapsed_time:.1f}s - Green still present")
                    shake_timed_out = True
                    is_capturing = False
                    capture_control.stop()
                    return
                
                # Convert frame to numpy array (BGR format)
                buffer_view = np.frombuffer(frame.frame_buffer, dtype=np.uint8)
                frame_array = buffer_view.reshape((frame.height, frame.width, 4))
                
                # Check green in bottom-left corner of FULL SCREEN (not shake area)
                safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
                safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
                safety_top = int(frame.height * safety_top_percent)
                safety_right = int(frame.width * safety_right_percent)
                safety_box = frame_array[safety_top:frame.height, 0:safety_right, :3]
                
                # Check if green pixel exists (#9bff9b = BGR 155, 255, 155)
                b_match = np.abs(safety_box[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                g_match = np.abs(safety_box[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                r_match = np.abs(safety_box[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                
                green_found = np.any(b_match & g_match & r_match)
                
                if green_found:
                    # Green still present - spam Enter key
                    keyboard.send('enter')
                    time.sleep(spam_delay_seconds)
                else:
                    # Green gone - shake complete!
                    print("Shake: Navigation - Green disappeared, shake complete")
                    is_capturing = False
                    capture_control.stop()
                    return
            
            except Exception as e:
                print(f"Shake: Navigation frame error: {e}")
                is_capturing = False
                capture_control.stop()
        
        @capture.event
        def on_closed():
            pass
        
        # Start capture in background thread
        try:
            print("Shake: Navigation - Starting capture")
            capture.start_free_threaded()
            
            # Keep running until capturing stops or stop event is set
            while is_capturing and not self.stop_event.is_set():
                time.sleep(0.1)
            
            # Cleanup
            is_capturing = False
            time.sleep(0.1)
            
            print("Shake: Navigation - Complete")
            return "timeout" if shake_timed_out else None
        except Exception as e:
            print(f"Shake: Failed to start Navigation capture: {e}")
            return None
    
    def _shake_navigation_mss(self):
        """Navigation shake detection using MSS - captures only green corner"""
        import mss
        
        # Get settings from storage
        spam_delay_ms = self.storage["config"]["shake"]["navigation_spam_delay"]
        fail_timeout = self.storage["config"]["shake"]["navigation_fail_timeout"]
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        
        print(f"Shake: Navigation (MSS) - Spam delay: {spam_delay_ms}ms")
        print(f"Shake: Navigation (MSS) - Fail timeout: {fail_timeout}s")
        print(f"Shake: Navigation (MSS) - Green tolerance: {green_tolerance}")
        
        # Tracking variables
        shake_timeout_start = time.time()
        shake_timed_out = False
        spam_delay_seconds = spam_delay_ms / 1000.0
        
        try:
            with mss.mss(compression_level=0) as sct:
                monitor = sct.monitors[1]
                
                # Calculate green corner region (bottom-left corner)
                safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
                safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
                
                screen_width = monitor["width"]
                screen_height = monitor["height"]
                
                safety_top = int(screen_height * safety_top_percent)
                safety_right = int(screen_width * safety_right_percent)
                
                # Region to capture (bottom-left corner only)
                region = {
                    "top": safety_top,
                    "left": 0,
                    "width": safety_right,
                    "height": screen_height - safety_top
                }
                
                print(f"Shake: Navigation (MSS) - Capturing green corner: top={safety_top}, width={safety_right}, height={region['height']}")
                
                while not self.stop_event.is_set():
                    # Check for timeout
                    elapsed_time = time.time() - shake_timeout_start
                    if elapsed_time > fail_timeout:
                        print(f"Shake: Navigation timeout after {elapsed_time:.1f}s - Green still present")
                        shake_timed_out = True
                        break
                    
                    # Capture only the green corner region
                    screenshot = sct.grab(region)
                    
                    # Convert to numpy array (BGR format)
                    frame_array = np.array(screenshot)[:, :, :3]  # Remove alpha channel
                    
                    # Check if green pixel exists (#9bff9b = BGR 155, 255, 155)
                    b_match = np.abs(frame_array[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                    g_match = np.abs(frame_array[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                    r_match = np.abs(frame_array[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                    
                    green_found = np.any(b_match & g_match & r_match)
                    
                    if green_found:
                        # Green still present - spam Enter key
                        keyboard.send('enter')
                        time.sleep(spam_delay_seconds)
                    else:
                        # Green gone - shake complete!
                        print("Shake: Navigation (MSS) - Green disappeared, shake complete")
                        break
                
                print("Shake: Navigation (MSS) - Complete")
                return "timeout" if shake_timed_out else None
                
        except Exception as e:
            print(f"Shake: Navigation (MSS) - Error: {e}")
            return None

    def _shake_pixel(self):
        """Pixel shake detection - scans for white pixels and clicks them - Returns 'timeout' if timed out"""
        # Get capture mode from storage
        capture_mode = self.storage["config"].get("capture_mode", "Windows Capture")
        
        if capture_mode == "MSS":
            print("Shake: Using MSS capture mode")
            return self._shake_pixel_mss()
        else:
            print("Shake: Using Windows Capture mode")
            return self._shake_pixel_windows_capture()
    
    def _shake_pixel_windows_capture(self):
        """Pixel shake detection using Windows Capture"""
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
        
        # Get settings from storage
        white_tolerance = self.storage["config"]["shake"]["pixel_white_tolerance"]
        duplicate_bypass = self.storage["config"]["shake"]["pixel_duplicate_bypass"]
        double_click = self.storage["config"]["shake"]["pixel_double_click"]
        double_click_delay_ms = self.storage["config"]["shake"]["pixel_double_click_delay"]
        fail_shake_timeout = self.storage["config"]["shake"]["fail_shake_timeout"]
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
        safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
        
        # Get shake area from storage
        shake_area = self.storage["config"]["areas"]["shake"]
        crop_x = shake_area["x"]
        crop_y = shake_area["y"]
        crop_width = shake_area["width"]
        crop_height = shake_area["height"]
        
        print(f"Shake: Pixel - White tolerance: {white_tolerance}, Duplicate bypass: {duplicate_bypass}s")
        print(f"Shake: Pixel - Double click: {double_click}, Delay: {double_click_delay_ms}ms")
        print(f"Shake: Pixel - Fail timeout: {fail_shake_timeout}s")
        print(f"Shake: Pixel - Green tolerance: {green_tolerance}")
        print(f"Shake: Pixel - Shake area: ({crop_x}, {crop_y}) {crop_width}x{crop_height}")
        
        # Tracking variables
        last_target_pixel = None
        last_move_time = 0
        is_capturing = True
        shake_timeout_start = time.time()  # Start timeout timer
        shake_timed_out = False  # Track if we timed out
        
        # Create capture
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=True,
            monitor_index=1,
            window_name=None,
        )
        
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal last_target_pixel, last_move_time, is_capturing, shake_timeout_start, shake_timed_out
            
            # Check if stop event is set
            if self.stop_event.is_set():
                is_capturing = False
                capture_control.stop()
                return
            
            try:
                # Convert to numpy array (full screen)
                buffer_view = np.frombuffer(frame.frame_buffer, dtype=np.uint8)
                frame_array = buffer_view.reshape((frame.height, frame.width, 4))
                
                # Crop for green region check (bottom-left corner)
                safety_top = int(frame.height * safety_top_percent)
                safety_right = int(frame.width * safety_right_percent)
                safety_box = frame_array[safety_top:frame.height, 0:safety_right, :3]
                
                # Check if green pixel exists (#9bff9b = RGB 155, 255, 155)
                b_match = np.abs(safety_box[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                g_match = np.abs(safety_box[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                r_match = np.abs(safety_box[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                
                # If green not there, stop the loop
                if not np.any(b_match & g_match & r_match):
                    print("Shake: Pixel - Green check failed, stopping")
                    is_capturing = False
                    capture_control.stop()
                    return
                
                # Green is still there - check timeout
                elapsed = time.time() - shake_timeout_start
                if elapsed > fail_shake_timeout:
                    print(f"Shake: Pixel - Timeout reached ({fail_shake_timeout}s), no pixel found")
                    shake_timed_out = True
                    is_capturing = False
                    capture_control.stop()
                    return
                
                # Green is still there - crop for shake area
                x1, y1 = crop_x, crop_y
                x2, y2 = crop_x + crop_width, crop_y + crop_height
                cropped = frame_array[y1:y2, x1:x2, :3]
                
                # Find first instance of white pixel (#ffffff = RGB 255, 255, 255)
                b_match = np.abs(cropped[:, :, 0].astype(np.int16) - 255) <= white_tolerance
                g_match = np.abs(cropped[:, :, 1].astype(np.int16) - 255) <= white_tolerance
                r_match = np.abs(cropped[:, :, 2].astype(np.int16) - 255) <= white_tolerance
                
                white_mask = b_match & g_match & r_match
                
                # Stop when found (get first white pixel)
                if np.any(white_mask):
                    white_coords = np.nonzero(white_mask)
                    first_y = white_coords[0][0]
                    first_x = white_coords[1][0]
                    
                    screen_x = crop_x + first_x
                    screen_y = crop_y + first_y
                    current_pixel = (screen_x, screen_y)
                    current_time = time.perf_counter()
                    
                    # Check if same pixel - wait for duplicate bypass timer
                    should_click = False
                    if last_target_pixel != current_pixel:
                        # New pixel found - reset timeout timer
                        shake_timeout_start = time.time()
                        should_click = True
                        last_move_time = current_time
                        last_target_pixel = current_pixel
                    elif (current_time - last_move_time) >= duplicate_bypass:
                        # Same pixel but bypass timer expired - click again but DON'T reset timeout
                        should_click = True
                        last_move_time = current_time
                    
                    if should_click:
                        # Move mouse there instantly
                        win32api.SetCursorPos((screen_x, screen_y))
                        # Move mouse down by 1 px for anti-roblox
                        win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 1, 0, 0)
                        
                        # Click or double click depending on GUI setting
                        if double_click:
                            # Double click
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            time.sleep(double_click_delay_ms / 1000.0)
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        else:
                            # Single click
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                
                # Loop again (no delays)
            
            except Exception as e:
                print(f"Shake: Pixel error: {e}")
                is_capturing = False
                capture_control.stop()
        
        @capture.event
        def on_closed():
            pass
        
        # Start capture in background thread
        try:
            print("Shake: Pixel - Starting capture")
            capture.start_free_threaded()
            
            # Keep running until capturing stops or stop event is set
            while is_capturing and not self.stop_event.is_set():
                time.sleep(0.1)
            
            # Cleanup
            is_capturing = False
            time.sleep(0.1)
            
            print("Shake: Pixel - Complete")
            return "timeout" if shake_timed_out else None
        except Exception as e:
            print(f"Shake: Failed to start Pixel capture: {e}")
            return None
    
    def _shake_pixel_mss(self):
        """Pixel shake detection using MSS - optimized region capture"""
        import mss
        import threading
        
        # Get settings from storage
        white_tolerance = self.storage["config"]["shake"]["pixel_white_tolerance"]
        duplicate_bypass = self.storage["config"]["shake"]["pixel_duplicate_bypass"]
        double_click = self.storage["config"]["shake"]["pixel_double_click"]
        double_click_delay_ms = self.storage["config"]["shake"]["pixel_double_click_delay"]
        fail_shake_timeout = self.storage["config"]["shake"]["fail_shake_timeout"]
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
        safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
        
        # Get shake area from storage
        shake_area = self.storage["config"]["areas"]["shake"]
        crop_x = shake_area["x"]
        crop_y = shake_area["y"]
        crop_width = shake_area["width"]
        crop_height = shake_area["height"]
        
        print(f"Shake: Pixel (MSS) - White tolerance: {white_tolerance}, Duplicate bypass: {duplicate_bypass}s")
        print(f"Shake: Pixel (MSS) - Double click: {double_click}, Delay: {double_click_delay_ms}ms")
        print(f"Shake: Pixel (MSS) - Fail timeout: {fail_shake_timeout}s")
        print(f"Shake: Pixel (MSS) - Green tolerance: {green_tolerance}")
        print(f"Shake: Pixel (MSS) - Shake area: ({crop_x}, {crop_y}) {crop_width}x{crop_height}")
        
        # Tracking variables
        last_target_pixel = None
        last_move_time = 0
        is_capturing = True
        shake_timeout_start = time.time()  # Start timeout timer
        shake_timed_out = False  # Track if we timed out
        
        def capture_loop():
            """MSS capture loop"""
            nonlocal last_target_pixel, last_move_time, is_capturing, shake_timeout_start, shake_timed_out
            
            try:
                with mss.mss(compression_level=0) as sct:
                    monitor = sct.monitors[1]
                    screen_width = monitor["width"]
                    screen_height = monitor["height"]
                    
                    # Calculate green check region (bottom-left corner)
                    safety_top = int(screen_height * safety_top_percent)
                    safety_right = int(screen_width * safety_right_percent)
                    green_region = {
                        "top": safety_top + monitor["top"],
                        "left": monitor["left"],
                        "width": safety_right,
                        "height": screen_height - safety_top
                    }
                    
                    # Calculate shake area region
                    shake_region = {
                        "top": crop_y + monitor["top"],
                        "left": crop_x + monitor["left"],
                        "width": crop_width,
                        "height": crop_height
                    }
                    
                    while is_capturing and not self.stop_event.is_set():
                        try:
                            # Capture only the regions we need
                            green_screenshot = sct.grab(green_region)
                            shake_screenshot = sct.grab(shake_region)
                            
                            # Convert to numpy arrays
                            green_array = np.array(green_screenshot)[:, :, :3]  # Drop alpha channel
                            shake_array = np.array(shake_screenshot)[:, :, :3]  # Drop alpha channel
                            
                            # Safety check: green pixel #9bff9b
                            # MSS returns BGR format
                            b_match = np.abs(green_array[:, :, 0].astype(np.int16) - 155) <= green_tolerance
                            g_match = np.abs(green_array[:, :, 1].astype(np.int16) - 255) <= green_tolerance
                            r_match = np.abs(green_array[:, :, 2].astype(np.int16) - 155) <= green_tolerance
                            
                            if not np.any(b_match & g_match & r_match):
                                print("Shake: Pixel (MSS) - Green check failed, stopping")
                                is_capturing = False
                                return
                            
                            # Green is still there - check timeout
                            elapsed = time.time() - shake_timeout_start
                            if elapsed > fail_shake_timeout:
                                print(f"Shake: Pixel (MSS) - Timeout reached ({fail_shake_timeout}s), no pixel found")
                                shake_timed_out = True
                                is_capturing = False
                                return
                                is_capturing = False
                                return
                            
                            # Search for first white pixel (#ffffff) - BGR format
                            b_match = np.abs(shake_array[:, :, 0].astype(np.int16) - 255) <= white_tolerance
                            g_match = np.abs(shake_array[:, :, 1].astype(np.int16) - 255) <= white_tolerance
                            r_match = np.abs(shake_array[:, :, 2].astype(np.int16) - 255) <= white_tolerance
                            
                            white_mask = b_match & g_match & r_match
                            white_found = np.any(white_mask)
                            
                            # If white pixel found, move cursor and click
                            if white_found:
                                white_coords = np.nonzero(white_mask)
                                first_y = white_coords[0][0]
                                first_x = white_coords[1][0]
                                
                                # Coordinates are already relative to shake region, just add crop offset
                                screen_x = crop_x + first_x
                                screen_y = crop_y + first_y
                                current_pixel = (screen_x, screen_y)
                                current_time = time.perf_counter()
                                
                                should_move = False
                                
                                if last_target_pixel != current_pixel:
                                    # New pixel found - reset timeout timer
                                    shake_timeout_start = time.time()
                                    should_move = True
                                    last_move_time = current_time
                                elif (current_time - last_move_time) >= duplicate_bypass:
                                    # Same pixel but bypass timer expired - click again but DON'T reset timeout
                                    should_move = True
                                    last_move_time = current_time
                                
                                if should_move:
                                    win32api.SetCursorPos((screen_x, screen_y))
                                    win32api.mouse_event(win32con.MOUSEEVENTF_MOVE, 0, 1, 0, 0)
                                    
                                    if double_click:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                        time.sleep(double_click_delay_ms / 1000)
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    else:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    
                                    last_target_pixel = current_pixel
                        
                        except Exception as e:
                            print(f"Shake: Pixel (MSS) error: {e}")
                            is_capturing = False
                            return
            
            except Exception as e:
                print(f"Shake: Failed to initialize MSS: {e}")
                is_capturing = False
        
        # Start capture in background thread
        try:
            print("Shake: Pixel (MSS) - Starting capture")
            capture_thread = threading.Thread(target=capture_loop, daemon=True)
            capture_thread.start()
            
            # Keep running until capturing stops or stop event is set
            while is_capturing and not self.stop_event.is_set():
                time.sleep(0.1)
            
            # Cleanup
            is_capturing = False
            time.sleep(0.1)
            
            print("Shake: Pixel (MSS) - Complete")
            return "timeout" if shake_timed_out else None
        except Exception as e:
            print(f"Shake: Failed to start Pixel (MSS) capture: {e}")
            return None

    def _fish(self):
        """Fish function"""
        # Get fish method from storage
        fish_method = self.storage["config"]["fish"]["method"]
        
        if fish_method == "Disabled":
            print("Fish: Disabled")
            return
        
        elif fish_method == "Color":
            print("Fish: Color mode")
            
            # Get capture mode from storage
            capture_mode = self.storage["config"].get("capture_mode", "Windows Capture")
            
            if capture_mode == "MSS":
                print("Fish: Using MSS capture mode")
                self._fish_color_mss()
            else:
                print("Fish: Using Windows Capture mode")
                self._fish_color_windows_capture()
            
            # Delay after fish ends
            delay_after_end = self.storage["config"]["fish"]["delay_after_end"]
            if delay_after_end > 0:
                print(f"Fish: Delay after end {delay_after_end}s")
                if self.stop_event.wait(timeout=delay_after_end):
                    return
        
        else:
            print(f"Fish: Unknown method '{fish_method}'")

    def _fish_color_windows_capture(self):
        """Color-based fish detection using Windows Capture"""
        from windows_capture import WindowsCapture, Frame, InternalCaptureControl
        
        print("Fish: Color (Windows Capture) - Starting")
        
        # Get settings from storage
        fish_area = self.storage["config"]["areas"]["fish"]
        
        # Get current rod type and its colors
        current_rod = self.storage["config"]["fish"]["rod_type"]
        rod_colors = self.storage["config"]["fish"]["rods"].get(current_rod, {})
        
        target_colors = [tuple(c) for c in rod_colors.get("target_colors", [[91, 75, 67]])]
        bar_colors = [tuple(c) for c in rod_colors.get("bar_colors", [[241, 241, 241], [255, 255, 255]])]
        
        target_tolerance = rod_colors.get("target_tolerance", 0)
        bar_tolerance = rod_colors.get("bar_tolerance", 0)
        
        # State check settings
        green_check_color = (155, 255, 155)  # RGB #9bff9b
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
        safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
        
        # Move check stabilization
        move_check_stabilize_threshold = self.storage["config"]["fish"]["move_check_stabilize_threshold"]
        move_check_movement_threshold_percent = self.storage["config"]["fish"]["move_check_movement_threshold_percent"]
        
        # PD Controller tuning parameters
        kp = self.storage["config"]["fish"].get("kp", 0.5)
        kd = self.storage["config"]["fish"].get("kd", 0.3)
        velocity_smoothing = self.storage["config"]["fish"].get("velocity_smoothing", 0.7)
        stopping_distance_multiplier = self.storage["config"]["fish"].get("stopping_distance_multiplier", 3.0)
        
        # Visual overlay
        show_overlay = self.storage["config"]["toggles"]["fish_overlay"]
        
        # Calculate pixel values based on fish area width
        move_check_movement_threshold = int(fish_area["width"] * move_check_movement_threshold_percent)
        
        print(f"Fish: Rod type: {current_rod}")
        print(f"Fish: Fish area: ({fish_area['x']}, {fish_area['y']}) {fish_area['width']}x{fish_area['height']}")
        
        # State tracking
        green_found_ready = False
        move_check_ready = False
        move_check_initial_target = None
        move_check_initial_bar = None
        move_check_stable_count = 0
        move_check_click_state = False
        move_check_last_target = None
        move_check_last_bar = None
        
        # Color check (loop 3) tracking
        color_check_click_state = False
        color_check_previous_bar = None
        color_check_previous_target = None
        color_check_previous_time = None
        color_check_bar_velocity = 0.0
        color_check_target_velocity = 0.0
        color_check_bar_left = None
        color_check_bar_right = None
        color_check_min_reachable = None
        color_check_max_reachable = None
        color_check_bar_width = None
        
        # Visual overlay
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        overlay = None
        canvas = None
        arrow_ids = {}
        
        if show_overlay:
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-topmost', True)
            overlay.attributes('-transparentcolor', 'black')
            overlay.overrideredirect(True)
            overlay.geometry(f"{screen_width}x{screen_height}+0+0")
            overlay.configure(bg='black')
            
            canvas = tk.Canvas(overlay, bg='black', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
        
        def get_arrow_coords_down(x, y):
            """Get coordinates for downward pointing arrow"""
            size = 15
            return [x, y+size, x-size//2, y, x+size//2, y]
        
        def update_or_create_arrow(arrow_id, coords, color):
            """Update existing arrow or create new one"""
            if arrow_id:
                try:
                    canvas.coords(arrow_id, *coords)
                    return arrow_id
                except:
                    return canvas.create_polygon(coords, fill=color, outline=color)
            else:
                return canvas.create_polygon(coords, fill=color, outline=color)
        
        # Create capture instance
        capture = WindowsCapture(
            cursor_capture=False,
            draw_border=True,
            monitor_index=1,
            window_name=None,
        )
        
        is_capturing = True
        
        @capture.event
        def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
            nonlocal green_found_ready, move_check_ready, move_check_initial_target, move_check_initial_bar
            nonlocal move_check_stable_count, move_check_click_state, move_check_last_target, move_check_last_bar
            nonlocal color_check_click_state, color_check_previous_bar, color_check_previous_target
            nonlocal color_check_previous_time, color_check_bar_velocity, color_check_target_velocity
            nonlocal color_check_bar_left, color_check_bar_right
            nonlocal color_check_min_reachable, color_check_max_reachable, color_check_bar_width
            nonlocal is_capturing
            
            # Check if stop event is set
            if self.stop_event.is_set():
                if move_check_click_state or color_check_click_state:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                is_capturing = False
                capture_control.stop()
                return
            
            # Convert frame to numpy array
            buffer_view = np.frombuffer(frame.frame_buffer, dtype=np.uint8)
            frame_array = buffer_view.reshape((frame.height, frame.width, 4))
            
            # Check for green pixel in bottom-left corner
            frame_height, frame_width = frame_array.shape[:2]
            safety_top = int(frame_height * safety_top_percent)
            safety_right = int(frame_width * safety_right_percent)
            safety_box = frame_array[safety_top:frame_height, 0:safety_right, :3]
            
            # Check if green pixel exists
            b_match = np.abs(safety_box[:, :, 0].astype(np.int16) - green_check_color[2]) <= green_tolerance
            g_match = np.abs(safety_box[:, :, 1].astype(np.int16) - green_check_color[1]) <= green_tolerance
            r_match = np.abs(safety_box[:, :, 2].astype(np.int16) - green_check_color[0]) <= green_tolerance
            green_present = np.any(b_match & g_match & r_match)
            
            # Loop 1: Wait for green to disappear
            if not green_found_ready:
                if not green_present:
                    green_found_ready = True
                return
            
            # Loop 2: Move check - scan for target and bar, exit if they move
            if not move_check_ready:
                # Check if green reappeared - exit immediately
                if green_present:
                    if move_check_click_state:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        move_check_click_state = False
                    is_capturing = False
                    capture_control.stop()
                    return
                
                # Spam left click
                if move_check_click_state:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    move_check_click_state = False
                else:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    move_check_click_state = True
                
                # Crop to fish area
                cropped = frame_array[
                    fish_area["y"]:fish_area["y"] + fish_area["height"],
                    fish_area["x"]:fish_area["x"] + fish_area["width"],
                    :3
                ]
                
                height, width = cropped.shape[:2]
                
                left_x = None
                right_x = None
                
                # Scan for leftmost target pixel
                for y in range(height):
                    for x in range(width):
                        pixel = cropped[y, x]
                        for target_color in target_colors:
                            if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                left_x = fish_area["x"] + x
                                break
                        if left_x is not None:
                            break
                    if left_x is not None:
                        break
                
                # Scan for rightmost target pixel
                if left_x is not None:
                    for y in range(height):
                        for x in range(width - 1, -1, -1):
                            pixel = cropped[y, x]
                            for target_color in target_colors:
                                if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                    abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                    abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                    right_x = fish_area["x"] + x
                                    break
                            if right_x is not None:
                                break
                        if right_x is not None:
                            break
                    
                    middle_x = (left_x + right_x) // 2
                    
                    # Scan for bar left edge
                    bar_left_found = False
                    bar_left_x = None
                    for y in range(height):
                        for x in range(width):
                            pixel = cropped[y, x]
                            for bar_color in bar_colors:
                                if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                    abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                    abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                    bar_left_found = True
                                    bar_left_x = fish_area["x"] + x
                                    break
                            if bar_left_found:
                                break
                        if bar_left_found:
                            break
                    
                    # Scan for bar right edge
                    bar_right_found = False
                    bar_right_x = None
                    if bar_left_found:
                        for y in range(height):
                            for x in range(width - 1, -1, -1):
                                pixel = cropped[y, x]
                                for bar_color in bar_colors:
                                    if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                        abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                        abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                        bar_right_found = True
                                        bar_right_x = fish_area["x"] + x
                                        break
                                if bar_right_found:
                                    break
                            if bar_right_found:
                                break
                    
                    # Check if we have valid target and bar readings
                    if bar_left_found and bar_right_found:
                        bar_middle = (bar_left_x + bar_right_x) // 2
                        
                        # Update overlay arrows (loop 2 - move check)
                        if show_overlay:
                            arrow_y = fish_area["y"] - 20
                            arrow_ids['target'] = update_or_create_arrow(arrow_ids.get('target'), get_arrow_coords_down(middle_x, arrow_y), '#00ff00')
                            arrow_ids['bar_left'] = update_or_create_arrow(arrow_ids.get('bar_left'), get_arrow_coords_down(bar_left_x, arrow_y), '#0000ff')
                            arrow_ids['bar_right'] = update_or_create_arrow(arrow_ids.get('bar_right'), get_arrow_coords_down(bar_right_x, arrow_y), '#0000ff')
                            arrow_ids['bar_middle'] = update_or_create_arrow(arrow_ids.get('bar_middle'), get_arrow_coords_down(bar_middle, arrow_y), '#87CEEB')
                            canvas.update()
                        
                        # Stabilization phase
                        if move_check_initial_target is None:
                            if move_check_last_target is not None and move_check_last_bar is not None:
                                if middle_x == move_check_last_target and bar_middle == move_check_last_bar:
                                    move_check_stable_count += 1
                                else:
                                    move_check_stable_count = 1
                            else:
                                move_check_stable_count = 1
                            
                            move_check_last_target = middle_x
                            move_check_last_bar = bar_middle
                            
                            if move_check_stable_count >= move_check_stabilize_threshold:
                                move_check_initial_target = middle_x
                                move_check_initial_bar = bar_middle
                        else:
                            # Check if movement exceeded threshold
                            target_moved = abs(middle_x - move_check_initial_target) > move_check_movement_threshold
                            bar_moved = abs(bar_middle - move_check_initial_bar) > move_check_movement_threshold
                            
                            if target_moved or bar_moved:
                                # Ensure left click is held when transitioning to loop 3
                                if not move_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    move_check_click_state = True
                                move_check_ready = True
                                return
                    else:
                        move_check_stable_count = 0
                else:
                    move_check_stable_count = 0
                
                return
            
            # Loop 3: Color check - Scan for target and bar with controller
            # Handle transition from loop 2 to loop 3
            if move_check_click_state:
                # Loop 2 was holding mouse - transfer control to loop 3
                color_check_click_state = True
                move_check_click_state = False  # Reset loop 2 flag
            elif color_check_previous_bar is None:
                # First frame of color check - ensure mouse is held down
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                color_check_click_state = True
            
            # Crop to fish area
            cropped = frame_array[
                fish_area["y"]:fish_area["y"] + fish_area["height"],
                fish_area["x"]:fish_area["x"] + fish_area["width"],
                :3
            ]
            
            height, width = cropped.shape[:2]
            
            left_x = None
            right_x = None
            
            # Scan for leftmost target pixel
            for y in range(height):
                for x in range(width):
                    pixel = cropped[y, x]
                    for target_color in target_colors:
                        if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                            abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                            abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                            left_x = fish_area["x"] + x
                            break
                    if left_x is not None:
                        break
                if left_x is not None:
                    break
            
            # Scan for rightmost target pixel  
            if left_x is not None:
                for y in range(height):
                    for x in range(width - 1, -1, -1):
                        pixel = cropped[y, x]
                        for target_color in target_colors:
                            if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                right_x = fish_area["x"] + x
                                break
                        if right_x is not None:
                            break
                    if right_x is not None:
                        break
                
                middle_x = (left_x + right_x) // 2
                
                # Scan for bar left edge
                bar_left_found = False
                bar_left_x = None
                for y in range(height):
                    for x in range(width):
                        pixel = cropped[y, x]
                        for bar_color in bar_colors:
                            if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                bar_left_found = True
                                bar_left_x = fish_area["x"] + x
                                break
                        if bar_left_found:
                            break
                    if bar_left_found:
                        break
                
                # Scan for bar right edge
                bar_right_found = False
                bar_right_x = None
                if bar_left_found:
                    for y in range(height):
                        for x in range(width - 1, -1, -1):
                            pixel = cropped[y, x]
                            for bar_color in bar_colors:
                                if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                    abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                    abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                    bar_right_found = True
                                    bar_right_x = fish_area["x"] + x
                                    break
                            if bar_right_found:
                                break
                        if bar_right_found:
                            break
                
                if bar_left_found and bar_right_found:
                    bar_middle = (bar_left_x + bar_right_x) // 2
                    
                    # Calculate bar width and reachable bounds
                    if color_check_min_reachable is None:
                        bar_width = bar_right_x - bar_left_x
                        color_check_bar_width = bar_width
                        color_check_bar_left = bar_left_x
                        color_check_bar_right = bar_right_x
                        color_check_min_reachable = fish_area["x"] + bar_width // 2
                        color_check_max_reachable = fish_area["x"] + fish_area["width"] - bar_width // 2
                    
                    # Update overlay arrows (bar mode)
                    if show_overlay:
                        arrow_y = fish_area["y"] - 20
                        arrow_ids['target'] = update_or_create_arrow(arrow_ids.get('target'), get_arrow_coords_down(middle_x, arrow_y), '#00ff00')
                        arrow_ids['bar_left'] = update_or_create_arrow(arrow_ids.get('bar_left'), get_arrow_coords_down(bar_left_x, arrow_y), '#0000ff')
                        arrow_ids['bar_right'] = update_or_create_arrow(arrow_ids.get('bar_right'), get_arrow_coords_down(bar_right_x, arrow_y), '#0000ff')
                        arrow_ids['bar_middle'] = update_or_create_arrow(arrow_ids.get('bar_middle'), get_arrow_coords_down(bar_middle, arrow_y), '#87CEEB')
                        arrow_ids['min_reach'] = update_or_create_arrow(arrow_ids.get('min_reach'), get_arrow_coords_down(color_check_min_reachable, arrow_y), '#ffff00')
                        arrow_ids['max_reach'] = update_or_create_arrow(arrow_ids.get('max_reach'), get_arrow_coords_down(color_check_max_reachable, arrow_y), '#ffff00')
                        canvas.update()
                    
                    # Calculate velocities
                    current_time = time.perf_counter()
                    if color_check_previous_bar is not None and color_check_previous_target is not None:
                        delta_time = current_time - color_check_previous_time
                        if delta_time > 0:
                            raw_bar_velocity = (bar_middle - color_check_previous_bar) / delta_time
                            raw_target_velocity = (middle_x - color_check_previous_target) / delta_time
                            
                            color_check_bar_velocity = (velocity_smoothing * raw_bar_velocity + 
                                                        (1 - velocity_smoothing) * color_check_bar_velocity)
                            color_check_target_velocity = (velocity_smoothing * raw_target_velocity + 
                                                           (1 - velocity_smoothing) * color_check_target_velocity)
                    
                    # Update previous values
                    color_check_previous_bar = bar_middle
                    color_check_previous_target = middle_x
                    color_check_previous_time = current_time
                    
                    # Calculate error and relative velocity
                    error = bar_middle - middle_x
                    relative_velocity = color_check_bar_velocity - color_check_target_velocity
                    
                    # Calculate stopping distance based on relative velocity
                    stopping_distance = abs(relative_velocity) * stopping_distance_multiplier
                    
                    # Controller logic with unreachable zones
                    if middle_x < color_check_min_reachable:
                        # Target unreachable left - release to move left
                        if color_check_click_state:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            color_check_click_state = False
                    elif middle_x > color_check_max_reachable:
                        # Target unreachable right - hold to move right
                        if not color_check_click_state:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            color_check_click_state = True
                    else:
                        # Check if target is on the bar
                        target_on_bar = bar_left_x <= middle_x <= bar_right_x
                        
                        if target_on_bar:
                            # Target is ON the bar - use stopping distance logic for precise alignment
                            if error < -stopping_distance:
                                # Bar is left of target (beyond stopping distance) - hold to move right
                                if not color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    color_check_click_state = True
                            elif error > stopping_distance:
                                # Bar is right of target (beyond stopping distance) - release to move left
                                if color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    color_check_click_state = False
                            else:
                                # Within stopping distance - counter-thrust based on velocity
                                if relative_velocity > 0:
                                    # Moving right relative to target - apply left thrust (release)
                                    if color_check_click_state:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                        color_check_click_state = False
                                else:
                                    # Moving left relative to target - apply right thrust (hold)
                                    if not color_check_click_state:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                        color_check_click_state = True
                        else:
                            # Target is OFF the bar - use PD to chase it
                            control_output = kp * error + kd * relative_velocity
                            
                            if control_output > 0:
                                # Bar too far right or moving right - release to move left
                                if color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    color_check_click_state = False
                            else:
                                # Bar too far left or moving left - hold to move right
                                if not color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    color_check_click_state = True
            else:
                # Target not found - check for green to exit
                if green_present:
                    # Alternate click state to keep bar moving
                    if color_check_click_state:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        color_check_click_state = False
                    else:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                        color_check_click_state = True
                else:
                    # Green not present - fish ended
                    if color_check_click_state:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        color_check_click_state = False
                    is_capturing = False
                    capture_control.stop()
                    return
        
        @capture.event
        def on_closed():
            pass
        
        # Start capture
        try:
            print("Fish: Color (Windows Capture) - Starting capture")
            capture.start_free_threaded()
            
            # Keep running until capturing stops or stop event is set
            while is_capturing and not self.stop_event.is_set():
                time.sleep(0.1)
            
            # Cleanup
            is_capturing = False
            if move_check_click_state or color_check_click_state:
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
            time.sleep(0.1)
            
            # Cleanup overlay
            if overlay:
                try:
                    overlay.destroy()
                except:
                    pass
            
            print("Fish: Color (Windows Capture) - Complete")
        except Exception as e:
            print(f"Fish: Failed to start Color (Windows Capture) capture: {e}")
            if overlay:
                try:
                    overlay.destroy()
                except:
                    pass
    
    def _fish_color_mss(self):
        """Color-based fish detection using MSS"""
        import mss
        
        print("Fish: Color (MSS) - Starting")
        
        # Get settings from storage
        fish_area = self.storage["config"]["areas"]["fish"]
        
        # Get current rod type and its colors
        current_rod = self.storage["config"]["fish"]["rod_type"]
        rod_colors = self.storage["config"]["fish"]["rods"].get(current_rod, {})
        
        target_colors = [tuple(c) for c in rod_colors.get("target_colors", [[91, 75, 67]])]
        bar_colors = [tuple(c) for c in rod_colors.get("bar_colors", [[241, 241, 241], [255, 255, 255]])]
        
        target_tolerance = rod_colors.get("target_tolerance", 0)
        bar_tolerance = rod_colors.get("bar_tolerance", 0)
        
        # State check settings
        green_check_color = (155, 255, 155)  # RGB #9bff9b
        green_tolerance = self.storage["config"]["state_check"]["green_tolerance"]
        safety_top_percent = self.storage["config"]["state_check"]["top_corner_ratio"] / 100.0
        safety_right_percent = self.storage["config"]["state_check"]["right_corner_ratio"] / 100.0
        
        # Move check stabilization
        move_check_stabilize_threshold = self.storage["config"]["fish"]["move_check_stabilize_threshold"]
        move_check_movement_threshold_percent = self.storage["config"]["fish"]["move_check_movement_threshold_percent"]
        
        # PD Controller tuning parameters
        kp = self.storage["config"]["fish"].get("kp", 0.5)
        kd = self.storage["config"]["fish"].get("kd", 0.3)
        velocity_smoothing = self.storage["config"]["fish"].get("velocity_smoothing", 0.7)
        stopping_distance_multiplier = self.storage["config"]["fish"].get("stopping_distance_multiplier", 3.0)
        
        # Visual overlay
        show_overlay = self.storage["config"]["toggles"]["fish_overlay"]
        
        # Calculate pixel values based on fish area width
        move_check_movement_threshold = int(fish_area["width"] * move_check_movement_threshold_percent)
        
        print(f"Fish: Rod type: {current_rod}")
        print(f"Fish: Fish area: ({fish_area['x']}, {fish_area['y']}) {fish_area['width']}x{fish_area['height']}")
        
        # State tracking
        green_found_ready = False
        move_check_ready = False
        move_check_initial_target = None
        move_check_initial_bar = None
        move_check_stable_count = 0
        move_check_click_state = False
        move_check_last_target = None
        move_check_last_bar = None
        
        # Color check (loop 3) tracking
        color_check_click_state = False
        color_check_previous_bar = None
        color_check_previous_target = None
        color_check_previous_time = None
        color_check_bar_velocity = 0.0
        color_check_target_velocity = 0.0
        color_check_bar_left = None
        color_check_bar_right = None
        color_check_min_reachable = None
        color_check_max_reachable = None
        color_check_bar_width = None
        
        # Visual overlay
        screen_width = win32api.GetSystemMetrics(0)
        screen_height = win32api.GetSystemMetrics(1)
        overlay = None
        canvas = None
        arrow_ids = {}
        
        if show_overlay:
            overlay = tk.Toplevel(self.root)
            overlay.attributes('-topmost', True)
            overlay.attributes('-transparentcolor', 'black')
            overlay.overrideredirect(True)
            overlay.geometry(f"{screen_width}x{screen_height}+0+0")
            overlay.configure(bg='black')
            
            canvas = tk.Canvas(overlay, bg='black', highlightthickness=0)
            canvas.pack(fill='both', expand=True)
        
        def get_arrow_coords_down(x, y):
            """Get coordinates for downward pointing arrow"""
            size = 15
            return [x, y+size, x-size//2, y, x+size//2, y]
        
        def update_or_create_arrow(arrow_id, coords, color):
            """Update existing arrow or create new one"""
            if arrow_id:
                try:
                    canvas.coords(arrow_id, *coords)
                    return arrow_id
                except:
                    return canvas.create_polygon(coords, fill=color, outline=color)
            else:
                return canvas.create_polygon(coords, fill=color, outline=color)
        
        # Create MSS instance for screen capture
        sct = mss.mss()
        
        # Get screen dimensions for green check area
        monitor = sct.monitors[1]  # Primary monitor
        screen_width = monitor["width"]
        screen_height = monitor["height"]
        
        # Calculate green check region (bottom-left corner)
        safety_top = int(screen_height * safety_top_percent)
        safety_right = int(screen_width * safety_right_percent)
        green_check_region = {
            "left": 0,
            "top": safety_top,
            "width": safety_right,
            "height": screen_height - safety_top
        }
        
        # Fish area region for MSS capture
        fish_region = {
            "left": fish_area["x"],
            "top": fish_area["y"],
            "width": fish_area["width"],
            "height": fish_area["height"]
        }
        
        # Main capture loop
        running = True
        while running and not self.stop_event.is_set():
            frame_start = time.perf_counter()
            
            # Capture green check area
            green_screenshot = sct.grab(green_check_region)
            green_array = np.array(green_screenshot, dtype=np.uint8)[:, :, :3]  # Remove alpha channel, keep BGR
            
            # Check if green pixel exists (MSS uses BGRA, so B=0, G=1, R=2)
            b_match = np.abs(green_array[:, :, 0].astype(np.int16) - green_check_color[2]) <= green_tolerance
            g_match = np.abs(green_array[:, :, 1].astype(np.int16) - green_check_color[1]) <= green_tolerance
            r_match = np.abs(green_array[:, :, 2].astype(np.int16) - green_check_color[0]) <= green_tolerance
            green_present = np.any(b_match & g_match & r_match)
            
            # First loop: Wait for green to disappear, then exit to next loop
            if not green_found_ready:
                if not green_present:
                    # Green disappeared, exit this loop and proceed to move check
                    green_found_ready = True
                    print("Green check: Green disappeared, starting move check")
                # Keep scanning for green to disappear
                continue
            
            # Second loop: Move check - scan for target and bar, exit if they move more than threshold
            if not move_check_ready:
                # Check if green reappeared - exit immediately
                if green_present:
                    # Release mouse if holding before exiting
                    if move_check_click_state:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        move_check_click_state = False
                    print("Move check: Green reappeared, exiting")
                    running = False
                    break
                
                # Spam left click - alternate between press and release
                if move_check_click_state:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                    move_check_click_state = False
                else:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                    move_check_click_state = True
                
                # Capture fish area directly
                fish_screenshot = sct.grab(fish_region)
                cropped = np.array(fish_screenshot, dtype=np.uint8)[:, :, :3]  # Remove alpha channel, keep BGR
                
                # Get dimensions
                height, width = cropped.shape[:2]
                
                left_x = None
                right_x = None
                
                # Scan left to right, row by row for leftmost
                for y in range(height):
                    for x in range(width):
                        pixel = cropped[y, x]
                        # Check if pixel matches target colors with tolerance
                        for target_color in target_colors:
                            if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                # Found leftmost!
                                left_x = fish_area["x"] + x
                                break
                        if left_x is not None:
                            break
                    if left_x is not None:
                        break
                
                # If found, scan right to left for rightmost
                if left_x is not None:
                    for y in range(height):
                        for x in range(width - 1, -1, -1):
                            pixel = cropped[y, x]
                            # Check if pixel matches target colors with tolerance
                            for target_color in target_colors:
                                if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                    abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                    abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                    # Found rightmost!
                                    right_x = fish_area["x"] + x
                                    break
                            if right_x is not None:
                                break
                        if right_x is not None:
                            break
                    
                    # Calculate middle
                    middle_x = (left_x + right_x) // 2
                    
                    # Now scan from left to right for Bar Left colors
                    bar_left_found = False
                    bar_left_x = None
                    for y in range(height):
                        for x in range(width):  # Scan entire width left to right
                            pixel = cropped[y, x]
                            # Check against all Bar colors with tolerance
                            for bar_color in bar_colors:
                                if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                    abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                    abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                    bar_left_found = True
                                    bar_left_x = fish_area["x"] + x
                                    break
                            if bar_left_found:
                                break
                        if bar_left_found:
                            break
                    
                    # Now scan from right to left for Bar Right colors
                    bar_right_found = False
                    bar_right_x = None
                    if bar_left_found:
                        for y in range(height):
                            for x in range(width - 1, -1, -1):  # Scan right to left
                                pixel = cropped[y, x]
                                # Check against all Bar colors with tolerance
                                for bar_color in bar_colors:
                                    if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                        abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                        abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                        bar_right_found = True
                                        bar_right_x = fish_area["x"] + x
                                        break
                                if bar_right_found:
                                    break
                            if bar_right_found:
                                break
                    
                    # Check if we have valid target and bar readings
                    if bar_left_found and bar_right_found:
                        bar_middle = (bar_left_x + bar_right_x) // 2
                        
                        # Update overlay arrows (loop 2 - move check)
                        if show_overlay:
                            arrow_y = fish_area["y"] - 20
                            # Target middle (green)
                            arrow_ids['target'] = update_or_create_arrow(
                                arrow_ids.get('target'), 
                                get_arrow_coords_down(middle_x, arrow_y), 
                                '#00ff00'
                            )
                            # Bar left edge (blue)
                            arrow_ids['bar_left'] = update_or_create_arrow(
                                arrow_ids.get('bar_left'), 
                                get_arrow_coords_down(bar_left_x, arrow_y), 
                                '#0000ff'
                            )
                            # Bar right edge (blue)
                            arrow_ids['bar_right'] = update_or_create_arrow(
                                arrow_ids.get('bar_right'), 
                                get_arrow_coords_down(bar_right_x, arrow_y), 
                                '#0000ff'
                            )
                            # Bar middle (lighter blue)
                            arrow_ids['bar_middle'] = update_or_create_arrow(
                                arrow_ids.get('bar_middle'), 
                                get_arrow_coords_down(bar_middle, arrow_y), 
                                '#87CEEB'
                            )
                            canvas.update()
                        
                        # Stabilization phase - need stable readings before setting initial positions
                        if move_check_initial_target is None:
                            # Check if positions match the last reading
                            if move_check_last_target is not None and move_check_last_bar is not None:
                                if middle_x == move_check_last_target and bar_middle == move_check_last_bar:
                                    # Positions match, increment counter
                                    move_check_stable_count += 1
                                else:
                                    # Positions changed, reset counter
                                    move_check_stable_count = 1
                            else:
                                # First reading, start counter
                                move_check_stable_count = 1
                            
                            # Update last positions
                            move_check_last_target = middle_x
                            move_check_last_bar = bar_middle
                            
                            if move_check_stable_count >= move_check_stabilize_threshold:
                                # Set initial positions after stabilization
                                move_check_initial_target = middle_x
                                move_check_initial_bar = bar_middle
                        else:
                            # Check if movement exceeded threshold
                            target_moved = abs(middle_x - move_check_initial_target) > move_check_movement_threshold
                            bar_moved = abs(bar_middle - move_check_initial_bar) > move_check_movement_threshold
                            
                            if target_moved or bar_moved:
                                # Ensure left click is held when transitioning to loop 3
                                if not move_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    move_check_click_state = True
                                move_check_ready = True
                                continue
                    else:
                        # No valid bar found, reset stabilization count
                        move_check_stable_count = 0
                else:
                    # No target found, reset stabilization count
                    move_check_stable_count = 0
                
                continue
            
            # Third loop: Color check - Scan for target and bar
            # Handle transition from loop 2 to loop 3
            if move_check_click_state:
                # Loop 2 was holding mouse - transfer control to loop 3
                color_check_click_state = True
                move_check_click_state = False  # Reset loop 2 flag
            # Ensure mouse is held down at start of color check (safety check)
            elif color_check_previous_bar is None:
                # First frame of color check - ensure mouse is held down
                win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                color_check_click_state = True
            
            # Capture fish area directly
            fish_screenshot = sct.grab(fish_region)
            cropped = np.array(fish_screenshot, dtype=np.uint8)[:, :, :3]  # Remove alpha channel, keep BGR
            
            # Get dimensions
            height, width = cropped.shape[:2]
            
            left_x = None
            right_x = None
            
            # Scan left to right, row by row for leftmost
            for y in range(height):
                for x in range(width):
                    pixel = cropped[y, x]
                    # Check if pixel matches target colors with tolerance
                    for target_color in target_colors:
                        if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                            abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                            abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                            # Found leftmost!
                            left_x = fish_area["x"] + x
                            break
                    if left_x is not None:
                        break
                if left_x is not None:
                    break
            
            # If found, scan right to left for rightmost
            if left_x is not None:
                for y in range(height):
                    for x in range(width - 1, -1, -1):
                        pixel = cropped[y, x]
                        # Check if pixel matches target colors with tolerance
                        for target_color in target_colors:
                            if (abs(int(pixel[0]) - target_color[0]) <= target_tolerance and 
                                abs(int(pixel[1]) - target_color[1]) <= target_tolerance and 
                                abs(int(pixel[2]) - target_color[2]) <= target_tolerance):
                                # Found rightmost!
                                right_x = fish_area["x"] + x
                                break
                        if right_x is not None:
                            break
                    if right_x is not None:
                        break
                
                # Calculate middle
                middle_x = (left_x + right_x) // 2
                
                # Now scan from left to right for Bar Left colors
                bar_left_found = False
                bar_left_x = None
                for y in range(height):
                    for x in range(width):  # Scan entire width left to right
                        pixel = cropped[y, x]
                        # Check against all Bar colors with tolerance
                        for bar_color in bar_colors:
                            if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                bar_left_found = True
                                bar_left_x = fish_area["x"] + x
                                break
                        if bar_left_found:
                            break
                    if bar_left_found:
                        break
                
                # Now scan from right to left for Bar Right colors
                bar_right_found = False
                bar_right_x = None
                if bar_left_found:
                    for y in range(height):
                        for x in range(width - 1, -1, -1):  # Scan right to left
                            pixel = cropped[y, x]
                            # Check against all Bar colors with tolerance
                            for bar_color in bar_colors:
                                if (abs(int(pixel[0]) - bar_color[0]) <= bar_tolerance and 
                                    abs(int(pixel[1]) - bar_color[1]) <= bar_tolerance and 
                                    abs(int(pixel[2]) - bar_color[2]) <= bar_tolerance):
                                    bar_right_found = True
                                    bar_right_x = fish_area["x"] + x
                                    break
                            if bar_right_found:
                                break
                        if bar_right_found:
                            break
                
                timing = (time.perf_counter() - frame_start) * 1000
                if bar_left_found and bar_right_found:
                    bar_middle = (bar_left_x + bar_right_x) // 2
                    
                    # Calculate bar width and reachable bounds (only once)
                    if color_check_min_reachable is None:
                        bar_width = bar_right_x - bar_left_x
                        color_check_bar_width = bar_width
                        color_check_bar_left = bar_left_x
                        color_check_bar_right = bar_right_x
                        # Min reachable = left edge of area + half bar width
                        color_check_min_reachable = fish_area["x"] + bar_width // 2
                        # Max reachable = right edge of area - half bar width
                        color_check_max_reachable = fish_area["x"] + fish_area["width"] - bar_width // 2
                    
                    # Update overlay arrows (loop 3 - color check)
                    if show_overlay:
                        arrow_y = fish_area["y"] - 20
                        arrow_ids['target'] = update_or_create_arrow(arrow_ids.get('target'), get_arrow_coords_down(middle_x, arrow_y), '#00ff00')
                        arrow_ids['bar_left'] = update_or_create_arrow(arrow_ids.get('bar_left'), get_arrow_coords_down(bar_left_x, arrow_y), '#0000ff')
                        arrow_ids['bar_right'] = update_or_create_arrow(arrow_ids.get('bar_right'), get_arrow_coords_down(bar_right_x, arrow_y), '#0000ff')
                        arrow_ids['bar_middle'] = update_or_create_arrow(arrow_ids.get('bar_middle'), get_arrow_coords_down(bar_middle, arrow_y), '#87CEEB')
                        arrow_ids['min_reach'] = update_or_create_arrow(arrow_ids.get('min_reach'), get_arrow_coords_down(color_check_min_reachable, arrow_y), '#ffff00')
                        arrow_ids['max_reach'] = update_or_create_arrow(arrow_ids.get('max_reach'), get_arrow_coords_down(color_check_max_reachable, arrow_y), '#ffff00')
                        canvas.update()
                    
                    # Calculate velocities
                    current_time = time.perf_counter()
                    if color_check_previous_bar is not None and color_check_previous_target is not None:
                        delta_time = current_time - color_check_previous_time
                        if delta_time > 0:
                            # Calculate raw velocities
                            raw_bar_velocity = (bar_middle - color_check_previous_bar) / delta_time
                            raw_target_velocity = (middle_x - color_check_previous_target) / delta_time
                            
                            # Smooth velocities
                            color_check_bar_velocity = (velocity_smoothing * raw_bar_velocity + 
                                                        (1 - velocity_smoothing) * color_check_bar_velocity)
                            color_check_target_velocity = (velocity_smoothing * raw_target_velocity + 
                                                           (1 - velocity_smoothing) * color_check_target_velocity)
                    
                    # Update previous values
                    color_check_previous_bar = bar_middle
                    color_check_previous_target = middle_x
                    color_check_previous_time = current_time
                    
                    # Calculate error and relative velocity
                    error = bar_middle - middle_x  # Positive = bar is right of target
                    relative_velocity = color_check_bar_velocity - color_check_target_velocity
                    
                    # Calculate stopping distance based on relative velocity
                    stopping_distance = abs(relative_velocity) * stopping_distance_multiplier
                    
                    # Determine action
                    action = "NONE"
                    
                    # Check if target is unreachable at edges
                    if middle_x < color_check_min_reachable:
                        # Target is too far left, rest at left edge
                        if color_check_click_state:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            color_check_click_state = False
                            action = "RELEASE (target unreachable left)"
                        else:
                            action = "RELEASE (target unreachable left)"
                    elif middle_x > color_check_max_reachable:
                        # Target is too far right, rest at right edge
                        if not color_check_click_state:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                            color_check_click_state = True
                            action = "HOLD (target unreachable right)"
                        else:
                            action = "HOLD (target unreachable right)"
                    else:
                        # Check if target is on the bar
                        target_on_bar = bar_left_x <= middle_x <= bar_right_x
                        
                        if target_on_bar:
                            # Target is ON the bar - use stopping distance logic for precise alignment
                            if error < -stopping_distance:
                                # Bar is left of target (beyond stopping distance) - hold to move right
                                if not color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    color_check_click_state = True
                                    action = "HOLD (accelerate right)"
                                else:
                                    action = "HOLD (continue right)"
                            elif error > stopping_distance:
                                # Bar is right of target (beyond stopping distance) - release to move left
                                if color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    color_check_click_state = False
                                    action = "RELEASE (accelerate left)"
                                else:
                                    action = "RELEASE (continue left)"
                            else:
                                # Within stopping distance - counter-thrust based on velocity
                                if relative_velocity > 0:
                                    # Moving right relative to target - apply left thrust (release)
                                    if color_check_click_state:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                        color_check_click_state = False
                                        action = "COUNTER-THRUST (release)"
                                    else:
                                        action = "COUNTER-THRUST (continue release)"
                                else:
                                    # Moving left relative to target - apply right thrust (hold)
                                    if not color_check_click_state:
                                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                        color_check_click_state = True
                                        action = "COUNTER-THRUST (hold)"
                                    else:
                                        action = "COUNTER-THRUST (continue hold)"
                        else:
                            # Target is OFF the bar - use PD to chase it
                            control_output = kp * error + kd * relative_velocity
                            
                            if control_output > 0:
                                # Need to move left (release mouse)
                                if color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                                    color_check_click_state = False
                                    action = "PD RELEASE (move left)"
                                else:
                                    action = "PD RELEASE (continue left)"
                            else:
                                # Need to move right (hold mouse)
                                if not color_check_click_state:
                                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                                    color_check_click_state = True
                                    action = "PD HOLD (move right)"
                                else:
                                    action = "PD HOLD (continue right)"
                else:
                    # Bar not found - check for green to exit
                    if green_present:
                        # Release mouse if holding before exiting
                        if color_check_click_state:
                            win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                            color_check_click_state = False
                        print("Color check: Green reappeared, exiting")
                        running = False
                        break
            else:
                # Target not found - check for green to exit
                if green_present:
                    # Release mouse if holding before exiting
                    if color_check_click_state:
                        win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                        color_check_click_state = False
                    print("Color check: Green reappeared, exiting")
                    running = False
                    break
        
        # Clean up
        try:
            sct.close()
        except:
            pass
        
        # Cleanup overlay
        if overlay:
            try:
                overlay.destroy()
            except:
                pass
        
        print("Fish: Color (MSS) - Complete")

    def run(self):
        """Start the application"""
        try:
            self.root.mainloop()
        finally:
            # Cleanup
            try:
                keyboard.remove_all_hotkeys()
            except:
                pass
            
            # Close zoom window if it exists
            try:
                if self.zoom_window_created:
                    cv2.destroyWindow(self.zoom_window_name)
            except:
                pass
            
            # Close mss instance
            try:
                self.sct.close()
            except:
                pass


def check_config_and_terms():
    """Check for Config.txt and show Terms of Use if needed - runs BEFORE app creation"""
    # Get config path
    if getattr(sys, 'frozen', False):
        app_dir = os.path.dirname(sys.executable)
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
    
    config_path = os.path.join(app_dir, "Config.txt")
    
    # If config exists, we're good to go (return tuple: accepted_terms, is_first_launch)
    if os.path.exists(config_path):
        print(f"Config found: {config_path}")
        return (True, False)  # Config exists, not first launch
    
    # Config doesn't exist - show Terms of Use
    print("Config.txt not found. Showing Terms of Use...")
    
    # Initialize CustomTkinter appearance
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    
    # Create a simple root window for the dialog
    terms_root = ctk.CTk()
    terms_root.withdraw()
    
    # Create the dialog
    dialog = ctk.CTkToplevel(terms_root)
    dialog.title("Terms of Use")
    dialog.geometry("800x700")
    dialog.resizable(True, True)
    dialog.minsize(600, 500)  # Set minimum size so elements don't get hidden
    
    # Center the dialog
    dialog.update_idletasks()
    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    x = (screen_width - 800) // 2
    y = (screen_height - 700) // 2
    dialog.geometry(f"800x700+{x}+{y}")
    
    # Make dialog modal
    dialog.transient(terms_root)
    dialog.grab_set()
    
    # Configure grid for proper resizing
    dialog.grid_rowconfigure(1, weight=1)  # Make the text area expandable
    dialog.grid_columnconfigure(0, weight=1)
    
    # Result variable
    accepted = [False]
    
    def close_dialog(accept_status):
        """Helper to properly close the dialog"""
        accepted[0] = accept_status
        try:
            dialog.grab_release()
        except:
            pass
        dialog.destroy()
        terms_root.quit()  # Exit the mainloop
    
    # Title (fixed at top)
    title_label = ctk.CTkLabel(dialog, text="IRUS Idiotproof - Terms of Use", font=ctk.CTkFont(size=18, weight="bold"))
    title_label.grid(row=0, column=0, pady=15, padx=20, sticky="ew")
    
    # Terms text (scrollable, expandable)
    terms_text = ctk.CTkTextbox(dialog, wrap="word", font=ctk.CTkFont(family="Consolas", size=11))
    terms_text.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))
    
    # Terms content
    terms_content = """═══════════════════════════════════════════════════════════════════════
                    IRUS IDIOTPROOF - TERMS OF USE
                          by AsphaltCake
═══════════════════════════════════════════════════════════════════════

By using IRUS IDIOTPROOF, you agree to the following terms and conditions.


1. USAGE RIGHTS
───────────────────────────────────────────────────────────────────────

YOU ARE ALLOWED TO:
  • Use IRUS IDIOTPROOF for personal purposes
  • Study and reverse engineer the code for educational purposes
  • Modify the code for your own personal use
  • Share your modifications with proper attribution

YOU ARE NOT ALLOWED TO:
  • Repackage or redistribute this software as your own
  • Remove or modify credits to the original author (AsphaltCake)
  • Sell or monetize this software or its derivatives
  • Claim ownership of the original codebase

IF YOU SHARE MODIFICATIONS:
  • You MUST credit AsphaltCake as the original author
  • You MUST link to the original source (YouTube channel)
  • You MUST clearly indicate what changes you made
  • You may NOT claim the entire work as your own creation


2. INTENDED USE & GAME COMPLIANCE
───────────────────────────────────────────────────────────────────────

  • This software is designed for ROBLOX FISCH
  
  • You are responsible for ensuring your use complies with the game's 
    Terms of Service and any applicable rules
    
  • The author is NOT responsible for any account actions (bans, 
    suspensions) resulting from your use of this software
    
  • Use at your own risk - automation is allowed by the game rules


3. LIABILITY DISCLAIMER
───────────────────────────────────────────────────────────────────────

  • The author is NOT liable for any damages or account issues
  
  • No guarantee of functionality, compatibility, or performance
  
  • Use of this software is entirely at your own risk


4. PRIVACY & DATA COLLECTION
───────────────────────────────────────────────────────────────────────

  • This software stores configuration data locally on your device
  
  • No personal data is collected or transmitted to external servers
  
  • Your settings and preferences are stored in a local config file only


5. CREDITS & ATTRIBUTION
───────────────────────────────────────────────────────────────────────

Original Author: AsphaltCake
YouTube: https://www.youtube.com/@AsphaltCake
Discord: https://discord.gg/vKVBbyfHTD

If you share, modify, or redistribute this software:
  • REQUIRED: Credit "AsphaltCake" as the original creator
  • REQUIRED: Link to the original source
  • REQUIRED: Indicate any changes you made
  • FORBIDDEN: Claim the entire work as your own


6. TERMS UPDATES
───────────────────────────────────────────────────────────────────────

  • These terms may be updated at any time
  
  • Continued use of the software constitutes acceptance of updated terms


7. ACCEPTANCE
───────────────────────────────────────────────────────────────────────

By clicking "Accept" below, you acknowledge that you have read, 
understood, and agree to these Terms of Use.

If you do not agree to these terms, click "Decline" and do not use 
this software.


═══════════════════════════════════════════════════════════════════════
                  Thank you for using IRUS IDIOTPROOF!
═══════════════════════════════════════════════════════════════════════
"""
    
    terms_text.insert("1.0", terms_content)
    terms_text.configure(state="disabled")
    
    # Checkbox and buttons frame (fixed at bottom)
    bottom_frame = ctk.CTkFrame(dialog, fg_color="transparent")
    bottom_frame.grid(row=2, column=0, pady=15, padx=20, sticky="ew")
    
    # Checkbox
    agree_var = tk.BooleanVar()
    agree_checkbox = ctk.CTkCheckBox(bottom_frame, text="I have read and agree to the Terms of Use", 
                                   variable=agree_var, font=ctk.CTkFont(size=13))
    agree_checkbox.pack(pady=8)
    
    # Buttons frame
    button_frame = ctk.CTkFrame(bottom_frame, fg_color="transparent")
    button_frame.pack(pady=8)
    
    def on_accept():
        if agree_var.get():
            close_dialog(True)
        else:
            # Create a simple messagebox using CTkToplevel
            msg_box = ctk.CTkToplevel(dialog)
            msg_box.title("Terms Required")
            msg_box.geometry("400x150")
            msg_box.resizable(False, False)
            msg_box.transient(dialog)
            msg_box.grab_set()
            
            # Center the messagebox
            msg_box.update_idletasks()
            x = dialog.winfo_x() + (dialog.winfo_width() // 2) - (msg_box.winfo_width() // 2)
            y = dialog.winfo_y() + (dialog.winfo_height() // 2) - (msg_box.winfo_height() // 2)
            msg_box.geometry(f"400x150+{x}+{y}")
            
            msg_label = ctk.CTkLabel(msg_box, text="Please check the box to accept the Terms of Use.", 
                                    font=ctk.CTkFont(size=14))
            msg_label.pack(pady=35)
            
            ok_button = ctk.CTkButton(msg_box, text="OK", width=120, height=32, command=msg_box.destroy,
                                     font=ctk.CTkFont(size=13))
            ok_button.pack(pady=10)
    
    def on_decline():
        close_dialog(False)
    
    accept_button = ctk.CTkButton(button_frame, text="Accept", width=160, height=36, command=on_accept, 
                                 fg_color="#4CAF50", hover_color="#45a049", 
                                 font=ctk.CTkFont(size=14, weight="bold"))
    accept_button.pack(side="left", padx=10)
    
    decline_button = ctk.CTkButton(button_frame, text="Decline", width=160, height=36, command=on_decline,
                                  fg_color="#f44336", hover_color="#da190b",
                                  font=ctk.CTkFont(size=14, weight="bold"))
    decline_button.pack(side="left", padx=10)
    
    # Handle window close (X button) - treat as decline
    dialog.protocol("WM_DELETE_WINDOW", on_decline)
    
    # Run the mainloop - this will block until the dialog is closed
    terms_root.mainloop()
    
    # Clean up properly - cancel all pending after callbacks
    try:
        # Cancel any pending after callbacks to prevent errors
        for after_id in terms_root.tk.call('after', 'info'):
            try:
                terms_root.after_cancel(after_id)
            except:
                pass
    except:
        pass
    
    # Destroy the window
    try:
        terms_root.quit()  # Exit mainloop first
        terms_root.destroy()
    except:
        pass
    
    # Small delay to ensure cleanup completes
    import time
    time.sleep(0.1)
    
    if accepted[0]:
        print("Terms accepted. App will start and create config.")
        return (True, True)  # Terms accepted, is first launch
    else:
        print("Terms declined. Exiting.")
        return (False, False)  # Terms declined


def auto_subscribe_to_youtube():
    """
    Attempt to auto-subscribe to YouTube channel.
    Opens browser with subscribe link and attempts automated subscription.
    Times out after 15 seconds if unsuccessful.
    """
    YOUTUBE_CHANNEL_URL = "https://www.youtube.com/@AsphaltCake?sub_confirmation=1"
    TIMEOUT_SECONDS = 15
    
    print("\n" + "="*50)
    print("AUTO-SUBSCRIBE TO YOUTUBE CHANNEL")
    print("="*50)
    
    try:
        import webbrowser
        import pyautogui
        
        # Open YouTube channel with subscribe confirmation
        print(f"🌐 Opening YouTube channel in browser...")
        webbrowser.open(YOUTUBE_CHANNEL_URL)
        
        # Wait for browser to load
        print("⏳ Waiting for browser to load...")
        start_time = time.time()
        browser_found = False
        
        # Try to find browser window (timeout after a few seconds)
        while time.time() - start_time < 5:
            try:
                def window_enum_callback(hwnd, windows):
                    if win32gui.IsWindowVisible(hwnd):
                        window_text = win32gui.GetWindowText(hwnd)
                        browser_keywords = ['Chrome', 'Firefox', 'Edge', 'Opera', 'Brave', 'YouTube']
                        if any(keyword.lower() in window_text.lower() for keyword in browser_keywords):
                            windows.append((hwnd, window_text))
                    return True
                
                windows = []
                win32gui.EnumWindows(window_enum_callback, windows)
                
                if windows:
                    browser_found = True
                    print(f"✅ Browser window found: {windows[0][1]}")
                    break
                
                time.sleep(0.2)
            except Exception as e:
                print(f"⚠️ Error checking for browser: {e}")
                break
        
        if not browser_found:
            print("⚠️ Browser window not detected, continuing anyway...")
            time.sleep(3)  # Give some time for page to load
            return False
        
        # Wait for YouTube page to load
        print("⏳ Waiting for YouTube page to load...")
        time.sleep(3.5)
        
        # Try to focus browser window
        print("🖱️ Attempting to focus browser...")
        try:
            if windows:
                hwnd = windows[0][0]
                if win32gui.IsIconic(hwnd):
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
        except Exception as e:
            print(f"⚠️ Could not focus browser: {e}")
        
        # Navigate to subscribe button using Tab and Enter
        print("🧭 Navigating to Subscribe button...")
        try:
            pyautogui.press('tab')
            time.sleep(0.2)
            pyautogui.press('tab')
            time.sleep(0.2)
            pyautogui.press('enter')
            time.sleep(0.5)
            
            print("✅ Subscribe sequence executed!")
        except Exception as e:
            print(f"⚠️ Error during navigation: {e}")
        
        # Close the tab
        print("❌ Closing YouTube tab...")
        try:
            pyautogui.hotkey('ctrl', 'w')
            time.sleep(0.3)
        except Exception as e:
            print(f"⚠️ Error closing tab: {e}")
        
        print("✅ Auto-subscribe sequence completed!")
        print("="*50 + "\n")
        return True
        
    except ImportError as e:
        print(f"⚠️ Required module not available: {e}")
        print("Skipping auto-subscribe...")
        return False
    except Exception as e:
        print(f"❌ Auto-subscribe failed: {e}")
        print("Continuing to main application...")
        return False


if __name__ == "__main__":
    # Check config and show Terms of Use BEFORE creating the app
    terms_result = check_config_and_terms()
    
    # Unpack the result: (accepted, is_first_launch)
    terms_accepted, is_first_launch = terms_result
    
    if not terms_accepted:
        os._exit(0)
    
    # AUTO-SUBSCRIBE: Only runs on first launch (after accepting terms)
    # This runs after terms acceptance but before main app launches
    # Times out automatically if it fails - won't block app startup
    if is_first_launch:
        print("\n🎉 First launch detected - attempting auto-subscribe...")
        try:
            auto_subscribe_to_youtube()
        except Exception as e:
            print(f"Auto-subscribe error (non-critical): {e}")
        
        # Small delay before launching main app
        time.sleep(0.5)
    
    # Terms accepted or config exists - create and run the app
    app = SimpleApp()
    app.run()