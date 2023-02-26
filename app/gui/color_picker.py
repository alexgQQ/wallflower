import PySimpleGUI as sg
from typing import Optional, Tuple

# TODO: I do like my color selector but there is a 
# built in `ColorChooserButton` elem for RGB like color selection
def popup_color_chooser() -> Optional[str]:
    """Show a grid of various colors and return the selection"""

    # Map based on the basic X11 color chart
    color_map = {
        "Pink": "#ffc0cb",
        "Light Pink": "#ffb6c1",
        "Hot Pink": "#ff69b4",
        "Deep Pink": "#ff1493",
        "Pale Violet Red": "#db7093",
        "Medium Violet Red": "#c71585",
        "Light Salmon": "#ffa07a",
        "Salmon": "#fa8072",
        "Dark Salmon": "#e9967a",
        "Light Coral": "#f08080",
        "Indian Red": "#cd5c5c",
        "Crimson": "#dc143c",
        "Firebrick": "#b22222",
        "Dark Red": "#8b0000",
        "Red": "#ff0000",
        "Orange Red": "#ff4500",
        "Tomato": "#ff6347",
        "Coral": "#ff7f50",
        "Dark Orange": "#ff8c00",
        "Orange": "#ffa500",
        "Yellow": "#ffff00",
        "Light Yellow": "#ffffe0",
        "Lemon Chiffon": "#fffacd",
        "Light Goldenrod Yellow": "#fafad2",
        "Papaya Whip": "#ffefd5",
        "Moccasin": "#ffe4b5",
        "Peach Puff": "#ffdab9",
        "Pale Goldenrod": "#eee8aa",
        "Khaki": "#f0e68c",
        "Dark Khaki": "#bdb76b",
        "Gold": "#ffd700",
        "Cornsilk": "#fff8dc",
        "Blanched Almond": "#ffebcd",
        "Bisque": "#ffe4c4",
        "Navajo White": "#ffdead",
        "Wheat": "#f5deb3",
        "Burlywood": "#deb887",
        "Tan": "#d2b48c",
        "Rosy Brown": "#bc8f8f",
        "Sandy Brown": "#f4a460",
        "Goldenrod": "#daa520",
        "Dark Goldenrod": "#b8860b",
        "Peru": "#cd853f",
        "Chocolate": "#d2691e",
        "Saddle Brown": "#8b4513",
        "Sienna": "#a0522d",
        "Brown": "#a52a2a",
        "Maroon": "#800000",
        "Lavender": "#e6e6fa",
        "Thistle": "#d8bfd8",
        "Plum": "#dda0dd",
        "Violet": "#ee82ee",
        "Orchid": "#da70d6",
        # "Fuchsia": "#ff00ff",
        # TODO: Duplicates in this list cause issues with event keys!
        "Magenta": "#ff00ff",
        "Medium Orchid": "#ba55d3",
        "Medium Purple": "#9370db",
        "Blue Violet": "#8a2be2",
        "Dark Violet": "#9400d3",
        "Dark Orchid": "#9932cc",
        "Dark Magenta": "#8b008b",
        "Purple": "#800080",
        "Indigo": "#4b0082",
        "Dark Slate Blue": "#483d8b",
        "Slate Blue": "#6a5acd",
        "Medium Slate Blue": "#7b68ee",
        "Light Steel Blue": "#b0c4de",
        "Powder Blue": "#b0e0e6",
        "Light Blue": "#add8e6",
        "Sky Blue": "#87ceeb",
        "Light Sky Blue": "#87cefa",
        "Deep Sky Blue": "#00bfff",
        "Dodger Blue": "#1e90ff",
        "Cornflower Blue": "#6495ed",
        "Steel Blue": "#4682b4",
        "Royal Blue": "#4169e1",
        "Blue": "#0000ff",
        "Medium Blue": "#0000cd",
        "Dark Blue": "#00008b",
        "Navy": "#000080",
        "Midnight Blue": "#191970",
        "Aqua": "#00ffff",
        "Cyan": "#00ffff",
        "Light Cyan": "#e0ffff",
        "Pale Turquoise": "#afeeee",
        "Aquamarine": "#7fffd4",
        "Turquoise": "#40e0d0",
        "Medium Turquoise": "#48d1cc",
        "Dark Turquoise": "#00ced1",
        "Light Sea Green": "#20b2aa",
        "Cadet Blue": "#5f9ea0",
        "Dark Cyan": "#008b8b",
        "Teal": "#008080",
        "Dark Olive Green": "#556b2f",
        "Olive": "#808000",
        "Olive Drab": "#6b8e23",
        "Yellow Green": "#9acd32",
        "Lime Green": "#32cd32",
        "Lime": "#00ff00",
        "Lawn Green": "#7cfc00",
        "Chartreuse": "#7fff00",
        "Green Yellow": "#adff2f",
        "Spring Green": "#00ff7f",
        "Medium Spring Green": "#00fa9a",
        "Light Green": "#90ee90",
        "Pale Green": "#98fb98",
        "Dark Sea Green": "#8fbc8f",
        "Medium Aquamarine": "#66cdaa",
        "Medium Sea Green": "#3cb371",
        "Sea Green": "#2e8b57",
        "Forest Green": "#228b22",
        "Green": "#008000",
        "Dark Green": "#006400",
        "White": "#ffffff",
        "Snow": "#fffafa",
        "Honeydew": "#f0fff0",
        "Mint Cream": "#f5fffa",
        "Azure": "#f0ffff",
        "Alice Blue": "#f0f8ff",
        "Ghost White": "#f8f8ff",
        "White Smoke": "#f5f5f5",
        "Seashell": "#fff5ee",
        "Beige": "#f5f5dc",
        "Old Lace": "#fdf5e6",
        "Floral White": "#fffaf0",
        "Ivory": "#fffff0",
        "Antique White": "#faebd7",
        "Linen": "#faf0e6",
        "Lavender Blush": "#fff0f5",
        "Misty Rose": "#ffe4e1",
        "Gainsboro": "#dcdcdc",
        "Light Gray": "#d3d3d3",
        "Silver": "#c0c0c0",
        "Dark Gray": "#a9a9a9",
        "Gray": "#808080",
        "Dim Gray": "#696969",
        "Light Slate Gray": "#778899",
        "Slate Gray": "#708090",
        "Dark Slate Gray": "#2f4f4f",
        "Black": "#000000",
    }

    def ColorButton(color: Tuple[str, str]):
        # TODO: Button elems don't carry a value so I bake it into the key
        # this makes for some gross string checking and breaks if a color value is
        # duplicated as psg adds a suffix for duplicates -COLOR-#ffffff -> -COLOR-#ffffff0
        return sg.B(button_color=('white', color[1]), pad=(0, 0), size=(None, None), key=f"COLOR-{color[1]}", tooltip=f'{color[0]}:{color[1]}', border_width=0)

    num_colors = len(list(color_map.keys()))
    row_len = 18

    grid = [[ColorButton(list(color_map.items())[c + j * row_len]) for c in range(0, row_len)] for j in range(0, num_colors // row_len)]
    grid += [[ColorButton(list(color_map.items())[c + num_colors - num_colors % row_len]) for c in range(0, num_colors % row_len)]]

    window = sg.Window('Color Picker', grid, finalize=True)

    while True:
        event, values = window.read()
        if event == sg.WIN_CLOSED or event == "Quit":
            hex_color = None
            break
        elif event.startswith("COLOR-"):
            hex_color = event.replace("COLOR-", "")
            break
    window.close()
    return hex_color
