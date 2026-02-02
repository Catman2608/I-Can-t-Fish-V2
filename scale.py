from PIL import ImageGrab
import pyautogui

screen_w, screen_h = pyautogui.size()
shot = ImageGrab.grab()
img_w, img_h = shot.size

pixel_scale = img_w / screen_w
print(pixel_scale)