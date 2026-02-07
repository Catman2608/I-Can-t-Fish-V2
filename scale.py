from AppKit import NSEvent

loc = NSEvent.mouseLocation()
# Get X and Y coordinates
print("x:", loc.x, "y:", loc.y)