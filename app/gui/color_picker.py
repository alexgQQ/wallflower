import PySimpleGUI as sg
from typing import Optional


# There is a very annoying quirk with the `ColorChooserButton` button
# in that it doesn't emit an event, but rather silently insert the
# selected value to the target element. However I want to use an event to
# trigger a visual color change on select, so I made it an inline popup window
# to accommodate it all.
def popup_color_chooser() -> Optional[str]:
    """Show an RGB color selector and return the selected value"""
    color_in = sg.In("", key="-COLOR_IN-", visible=False)
    bttn = sg.ColorChooserButton("", key="-COLOR_BUTTON-", visible=False)
    # By default the color chooser will target the element to the left
    window = sg.Window('Color Picker', [[color_in, bttn]], finalize=True)
    bttn.click()
    window.close()
    # Color choose returns either the hex string or a blank string if cancelled 
    hex_color = color_in.get()
    hex_color = None if not hex_color else hex_color
    return hex_color
