import PySimpleGUI as sg
import webbrowser
import os

from app.config import config


def add_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAH0lEQVQ4y2NgGAUw8B8IRjXgUoQLUEfDaDyQqmF4AwADqmeZrHJtnQAAAABJRU5ErkJggg=="
    return sg.Button("", key="-ADD_BUTTON-", tooltip="Add a local directory as an image source", image_data=icon)


def remove_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAGUlEQVQ4y2NgGAWjgBD4jwdQR8MoGAXIAAAreDfJ/wHj0gAAAABJRU5ErkJggg=="
    return sg.Button("", key="-REMOVE_BUTTON-", tooltip="Remove the selected directories as image sources", image_data=icon)


def popup_local_settings():
    info_text = """
Configure the download location and local image sources below.
The download location is used to download selected images from the main app.
The local image sources are the directories where desired searchable image files are stored.
"""
    info_col = sg.Column([[sg.Frame("", [
                    [sg.Text(info_text)],
                ],)]])

    image_dirs = config.core.image_dirs
    folder_browse = sg.FolderBrowse("", visible=False, key="-FOLDER_SELECT-", enable_events=True)
    listbox = sg.Listbox(image_dirs, enable_events=True, key="-DIR_LIST-", size=(None, 5), expand_x=True, tooltip="Selectable list of local image sources")
    data_col = sg.Column([[sg.Frame("", [
                        [sg.Text(f"Download Location: {config.core.download_loc}"),
                        sg.FolderBrowse(key="-DOWNLOAD_LOC-", tooltip="Browse for a local directory to download images to"),
                        sg.Push()],
                        [sg.Text("Local Image Directories")],
                        [listbox,
                        add_button(), remove_button(), folder_browse],
                    ],
                                    element_justification="left",
                                    expand_x=True,
                )
            ]
        ],
        expand_x=True,
    )
    button_col = sg.Column([[sg.Button("Ok"), sg.Button("Cancel")]])
    layout_edit = [[info_col], [data_col], [button_col]]

    window = sg.Window("Local Config Info", layout_edit, finalize=True)

    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == "Cancel":
            break
        elif event == "-ADD_BUTTON-":
            folder_browse.click()
            window.write_event_value("-SELECT-", True)
        elif event == "-SELECT-":
            folder = values["-FOLDER_SELECT-"]
            # FolderBrowser returns paths with forward slashes
            # even on windows so it must be cleaned else file locs are wrong
            folder = os.path.abspath(folder)
            image_dirs.append(folder)
            listbox.update(values=image_dirs)
        elif event == "-REMOVE_BUTTON-":
            dirs = values["-DIR_LIST-"]
            if dirs:
                for _dir in dirs:
                    ix = image_dirs.index(_dir)
                    image_dirs.pop(ix)
            listbox.update(values=image_dirs)
        elif event == "Ok":
            config.core.image_dirs = image_dirs
            if values["-DOWNLOAD_LOC-"]:
                folder = values["-DOWNLOAD_LOC-"]
                # FolderBrowser returns paths with forward slashes
                # even on windows so it must be cleaned else file locs are wrong
                folder = os.path.abspath(folder)
                config.core.download_loc = folder
            config.update()
            break

    window.close()


def popup_reddit_settings():
    info_text = """
This uses the Reddit Web API and requires your account details and a registered client application to use.
Please setup a script client application to authenticate with and enter the details below.
The app will add any saved posts from the /r/wallpaper subreddit to the search data.
"""
    info_url = "https://www.reddit.com/prefs/apps"
    info_col = sg.Column([[sg.Frame("", [
                    [sg.Text(info_text)],
                    [sg.Text(info_url,
                            justification="center",
                            expand_x=True,
                            font=("Courier New", 10, "underline"),
                            enable_events=True,
                            key="-INFO_LINK-")],
                ],)]])
    data_col = sg.Column([[sg.Frame("", [
                        [sg.Text("Enabled:"),
                        sg.Radio("True",
                                "enabled",
                                default=config.reddit.enabled == "True",
                                key="-REDDIT_ENABLED-"),
                        sg.Radio("False",
                                "enabled",
                                default=config.reddit.enabled == "False",
                                key="-REDDIT_DISABLED-"),
                        sg.Push()],
                        [sg.Text("Username:"),
                        sg.Input(key="-REDDIT_USERNAME-",
                                default_text=config.reddit.username)],
                        [sg.Text("Password:"),
                        sg.Input(key="-REDDIT_PASSWORD-",
                                password_char="*",
                                default_text=config.reddit.password)],
                        [sg.Text("Client ID:"),
                        sg.Input(key="-REDDIT_CLIENT_ID-",
                                default_text=config.reddit.client_id)],
                        [sg.Text("Client Secret:"),
                        sg.Input(key="-REDDIT_CLIENT_SECRET-",
                                password_char="*",
                                default_text=config.reddit.client_secret)],
                    ],
                                    element_justification="left",
                                    expand_x=True,
                )
            ]
        ],
        expand_x=True,
    )
    button_col = sg.Column([[sg.Button("Ok"), sg.Button("Cancel")]])
    layout_edit = [[info_col], [data_col], [button_col]]

    window = sg.Window("Reddit Connection Info", layout_edit, finalize=True)

    # These events only exists to change the cursor when hovering a link
    window["-INFO_LINK-"].bind("<Enter>", "-MOUSE_OVER-")
    window["-INFO_LINK-"].bind("<Leave>", "-MOUSE_AWAY-")

    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED or event == "Cancel":
            break
        elif event == "Ok":
            config.reddit.enabled = "True" if values["-REDDIT_ENABLED-"] else "False"
            config.reddit.username = values["-REDDIT_USERNAME-"]
            config.reddit.password = values["-REDDIT_PASSWORD-"]
            config.reddit.client_id = values["-REDDIT_CLIENT_ID-"]
            config.reddit.client_secret = values["-REDDIT_CLIENT_SECRET-"]
            config.update()
            break
        # hacky hyperlink
        elif event == "-INFO_LINK-":
            webbrowser.open(info_url)
            continue
        elif event == "-INFO_LINK--MOUSE_OVER-":
            window.set_cursor("hand2")
            continue
        elif event == "-INFO_LINK--MOUSE_AWAY-":
            window.set_cursor("arrow")
            continue

    window.close()


def popup_imgur_settings():
    info_text = """
This uses the Imgur Web API and requires your account details and a registered client application to use.
Please setup a client application to authenticate with and enter the details below.
The app will add any images from your favorites galleries to the search data.
"""
    info_url = "https://imgur.com/account/settings/apps"
    info_col = sg.Column([[sg.Frame("", [
                    [sg.Text(info_text)],
                    [sg.Text(info_url,
                            justification="center",
                            expand_x=True,
                            font=("Courier New", 10, "underline"),
                            enable_events=True,
                            key="-INFO_LINK-")],
                ],)]])
    data_col = sg.Column([[sg.Frame("", [
                        [sg.Text("Enabled:"),
                        sg.Radio("True",
                                "enabled",
                                default=config.imgur.enabled == "True",
                                key="-IMGUR_ENABLED-"),
                        sg.Radio("False",
                                "enabled",
                                default=config.imgur.enabled == "False",
                                key="-IMGUR_DISABLED-"),
                        sg.Push()],
                        [sg.Text("Access Token:"),
                        sg.Input(key="-IMGUR_ACCESS_TOKEN-",
                                default_text=config.imgur.access_token)],
                        [sg.Text("Refresh Token:"),
                        sg.Input(key="-IMGUR_REFRESH_TOKEN-",
                                password_char="*",
                                default_text=config.imgur.refresh_token)],
                        [sg.Text("Client ID:"),
                        sg.Input(key="-IMGUR_CLIENT_ID-",
                                default_text=config.imgur.client_id)],
                        [sg.Text("Client Secret:"),
                        sg.Input(key="-IMGUR_CLIENT_SECRET-",
                                password_char="*",
                                default_text=config.imgur.client_secret)],
                    ],
                                    element_justification="left",
                                    expand_x=True,
                )
            ]
        ],
        expand_x=True,
    )
    button_col = sg.Column([[sg.Button("Ok"), sg.Button("Cancel")]])
    layout_edit = [[info_col], [data_col], [button_col]]

    window = sg.Window("Imgur Connection Info", layout_edit, finalize=True)

    # These events only exists to change the cursor when hovering a link
    window["-INFO_LINK-"].bind("<Enter>", "-MOUSE_OVER-")
    window["-INFO_LINK-"].bind("<Leave>", "-MOUSE_AWAY-")

    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED or event == "Cancel":
            break
        elif event == "Ok":
            config.imgur.enabled = "True" if values["-IMGUR_ENABLED-"] else "False"
            config.imgur.access_token = values["-IMGUR_ACCESS_TOKEN-"]
            config.imgur.refresh_token = values["-IMGUR_REFRESH_TOKEN-"]
            config.imgur.client_id = values["-IMGUR_CLIENT_ID-"]
            config.imgur.client_secret = values["-IMGUR_CLIENT_SECRET-"]
            config.update()
            break
        # hacky hyperlink
        elif event == "-INFO_LINK-":
            webbrowser.open(info_url)
            continue
        elif event == "-INFO_LINK--MOUSE_OVER-":
            window.set_cursor("hand2")
            continue
        elif event == "-INFO_LINK--MOUSE_AWAY-":
            window.set_cursor("arrow")
            continue

    window.close()


def popup_wallhaven_settings():
    info_text = """
This uses the Wallhaven Web API and requires your account details and an application key to use.
Please follow the link below to setup or aquire the creds.
The app will add any images from your default collection to search data.
"""
    info_url = "https://wallhaven.cc/settings/account"
    info_col = sg.Column([[sg.Frame("", [
                    [sg.Text(info_text)],
                    [sg.Text(info_url,
                            justification="center",
                            expand_x=True,
                            font=("Courier New", 10, "underline"),
                            enable_events=True,
                            key="-INFO_LINK-")],
                ],)]])
    data_col = sg.Column([[sg.Frame("", [
                        [sg.Text("Enabled:"),
                        sg.Radio("True",
                                "enabled",
                                default=config.wallhaven.enabled == "True",
                                key="-WALLHAVEN_ENABLED-"),
                        sg.Radio("False",
                                "enabled",
                                default=config.wallhaven.enabled == "False",
                                key="-WALLHAVEN_DISABLED-"),
                        sg.Push()],
                        [sg.Text("Username:"),
                        sg.Input(key="-WALLHAVEN_USERNAME-",
                                default_text=config.wallhaven.username)],
                        [sg.Text("API Key:"),
                        sg.Input(key="-WALLHAVEN_API_KEY-",
                                default_text=config.wallhaven.api_key)],
                    ],
                                    element_justification="left",
                                    expand_x=True,
                )
            ]
        ],
        expand_x=True,
    )
    button_col = sg.Column([[sg.Button("Ok"), sg.Button("Cancel")]])
    layout_edit = [[info_col], [data_col], [button_col]]

    window = sg.Window("Wallhaven Connection Info", layout_edit, finalize=True)

    # These events only exists to change the cursor when hovering a link
    window["-INFO_LINK-"].bind("<Enter>", "-MOUSE_OVER-")
    window["-INFO_LINK-"].bind("<Leave>", "-MOUSE_AWAY-")

    while True:
        event, values = window.read()

        if event == sg.WINDOW_CLOSED or event == "Cancel":
            break
        elif event == "Ok":
            config.wallhaven.enabled = "True" if values["-WALLHAVEN_ENABLED-"] else "False"
            config.wallhaven.api_key = values["-WALLHAVEN_API_KEY-"]
            config.wallhaven.username = values["-WALLHAVEN_USERNAME-"]
            config.update()
            break
        # hacky hyperlink
        elif event == "-INFO_LINK-":
            webbrowser.open(info_url)
            continue
        elif event == "-INFO_LINK--MOUSE_OVER-":
            window.set_cursor("hand2")
            continue
        elif event == "-INFO_LINK--MOUSE_AWAY-":
            window.set_cursor("arrow")
            continue

    window.close()
