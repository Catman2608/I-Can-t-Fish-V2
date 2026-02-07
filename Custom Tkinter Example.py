from customtkinter import *

set_appearance_mode("dark")
#set_default_color_theme("Hades.json")  # Must be a json file in the same directory or a built-in theme like "blue"
set_default_color_theme("blue")

app = CTk()
app.geometry("800x550")
app.title("Longest Fisching V1.1")
# App = outside of tabs, [tab name] = inside tabs
lbl = CTkLabel(app, text="Settings", font=("Inconsolata", 20))
lbl.grid(row=0, column=0, pady=20)
# img = Image.open("start.png")
tabview = CTkTabview(master=app, width=780, height=400)
tabview.grid(row=1, column=0, pady=20, padx=20, sticky="nsew")
tabview.add("General Settings")
tabview.add("Shake Settings")
tabview.add("Minigame Settings")
# Button example
# All parameters for CTk button: 
# btn = CTkButton(master=app, text="Click Me", corner_radius=32, fg_color="#4158D0", hover_color="#C850C0" , border_color="#FFCC70", border_width=2, image= CTkImage(dark_image=img, light_image=img))
# From foreground color can be applied to lbl and combo box
def rebind():
    print("Start key rebinded to F5")
    print(f"Entered value: {entry.get('0.0', 'end')}")
def save_settings():
    print("Settings saved")
# Scrollable frame example: 
# frame = CTkScrollableFrame (master=app, fg_color="#8D6F3A", border_color="#FFCC70", border_width=2, orientation="vertical", scrollbar_button_color="#FFCC70")
frame = CTkFrame(master=tabview.tab("General Settings"), fg_color = "#222222", border_color = "#00FF00", border_width = 2)
btn = CTkButton(master=frame, text="Start", corner_radius=32, command=rebind)
btn.grid(row=1, column=0, pady=20, padx=20, sticky="w")
# Combo box
combobox = CTkComboBox(master=frame, values = ["Click", "Navigation"], command=save_settings)
combobox.grid(row=2, column=0, pady=20, padx=20, sticky="w")

# Debate: Checkbox or switch
# Checkbox example
checkbox = CTkCheckBox(master=frame, text="Auto Select Rod", checkbox_height = 30, checkbox_width = 30, corner_radius = 2)
checkbox.grid(row=3, column=0, pady=20, padx=20, sticky="w")
# Switch example
switch = CTkSwitch(master=frame, text="Perfect Cast")
switch.grid(row=4, column=0, pady=20, padx=20, sticky="w")

# Second frame
frame2 = CTkFrame(master=tabview.tab("General Settings"), fg_color = "#222222", border_color = "#FFF000", border_width = 2)

# Slider example
# All parameters for CTK Slider:
# slider = CTkSlider(master=app, from_=0, to = 100 number_of_steps=5, button_color="#C850C0", progress_color= "#C850C0", orientation="vertical")
slider = CTkSlider(master=frame2, from_ = 0, to=2, number_of_steps = 0.1)
slider.grid(row=0, column=0, pady=20, padx=20, sticky="w")

# Text input example
entry = CTkEntry(master=frame2, placeholder_text="255255255", width = 130, text_color = "#FFFFFF")
entry.grid(row=1, column=0, pady=20, padx=20, sticky="w")

# Textbox example (used in rhythm quiz)
textbox = CTkTextbox(master=frame2, scrollbar_button_color = "#676767", corner_radius = 16, border_color = "#676767", border_width = 2)
textbox.grid(row=2, column=0, rowspan=5, padx=20, pady=20, sticky="nw")

frame.grid(row=0, column=0, pady=20, padx=20, sticky="nsew")
frame2.grid(row=0, column=1, pady=20, padx=20, sticky="nsew")

app.grid_rowconfigure(0, weight=0)
app.grid_rowconfigure(1, weight=1)
app.grid_columnconfigure(0, weight=1)

app.mainloop()
