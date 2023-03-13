import PySimpleGUI as sg
from io import BytesIO
import webbrowser
import logging

from app.search import Search, DuplicateSearch
from app.utils import download_files, ImageList, open_location
from app.gui.settings import popup_imgur_settings, popup_local_settings, popup_reddit_settings, popup_wallhaven_settings
from app.gui.color_picker import popup_color_chooser
from app.gui.scan_popup import popup_scan
from app.db import wallpaper_by_id, WallpaperQuery, set_duplicate, get_tags
from app.config import app_name


logger = logging.getLogger(__name__)


# Main control buttons
# Icons snagged from https://fonts.google.com/icons, each image 24x24

def search_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAl0lEQVQ4y83TTQqCYBSFYQcOawvpGnQqtD1dgEvI3FQKYnsovsHTtAStDyI6w8N9uf9J8t9SOZkwOaneBadar2qlW0CLoFHYKTQC2q1iCI5PzlFgtTAd6oVXo1sDZpQLr8S8BtywX3h73GMzXGN76L81pZU99HGb7jHKP7ml2VmVJEYMss+PMTfEItnPkItDzGNlUeG/1gNQx9gqKvwkpwAAAABJRU5ErkJggg=="
    return sg.Button("", key="-SEARCH_BUTTON-", tooltip="Find images with the search selection", image_data=icon)


def color_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAzklEQVQ4y2NgoDP4z/o/9P/i/7f+f/7/9f/9/2v+p/7nw6c84P/t/+jg3f/q/yzYFDP9b/+PCxz+L4qpoeM/PnDmPy+qcn+4VOV/HiBGZYHAbFSvItwONOk/LxoLBP7+10doCEGyHJcN///3ITQs+U8MuIzQcAOrieg2fkBo+ITFzZh++oSugZANJ9CdRAjkkObp8//ZsAcrLuVSuCIOHXz+f/x/LpLpGEkDAa7/Z8KXtLElPht8GrAl72JC+Q01A/37b01KFn32P5dhQAAAHTo/oMB+IfwAAAAASUVORK5CYII="
    return sg.Button("", key="-COLOR_BUTTON-", tooltip="Select a color to search by", image_data=icon)


def image_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAdklEQVQ4y2NgGKzgv8f/x//xgcf/PVA1PPpPCDxC1UAEGNVAHQ2f/gf//0JYwxk4KwwoHk9Iw7b/zP9Xgll9UJn5+DTc/y8EZHMCbTn8nxUqw/X/Ci4N3/8bQXnS/yWR5LQgPsHUkIwzLcdTIVhJTt6kZqDBBAAPVzwcrVgiHgAAAABJRU5ErkJggg=="
    return sg.Button("", key="-IMAGE_BUTTON-", tooltip="Find images similar to a selected image", image_data=icon)


def clear_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAVklEQVQ4y+WSuw0AIAgFXYIt3L9jCgc6CxuJRnk1lHCX8GutdtBx7MgaTr8LDoyoYAzA78IqbsqZeSpfPEIpPCg5fFOyuCyILYlDi2uVD6e/hvp8dWIC7Ay2TVN2BKMAAAAASUVORK5CYII="
    return sg.Button("", key="-CLEAR_BUTTON-", tooltip="Clear search filters", image_data=icon)


def download_button():
    icon = "iVBORw0KGgoAAAANSUhEUgAAABgAAAAYCAQAAABKfvVzAAAAO0lEQVQ4y2NgGArgPxIY1YChsP4/LlBPmpZ60mypJ+SDepKUo2mpJzZx1JOkHKqlfpAla3RAHQ1DFgAAJlDoEZ5sVPAAAAAASUVORK5CYII="
    return sg.Button("", key="-DOWNLOAD_BUTTON-", tooltip="Download selected images", image_data=icon)


# 500x281 (16:9) placeholder image
placeholder_image = "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"

def main_window():
    """Launch the app and any background processes"""

    search = Search()
    table_data, image_srcs = search.find()
    color_bttn = color_button()
    orig_button_color = color_bttn.ButtonColor
    download_bttn = download_button()
    ar_buttons = [
        sg.Radio("16:9", "AR", key="-RATIO_16:9-"),
        sg.Radio("16:10", "AR", key="-RATIO_16:10-"),
        sg.Radio("4:3", "AR", key="-RATIO_4:3-"),
        sg.Radio("9:16", "AR", key="-RATIO_9:16-"),
    ]
    type_buttons = [
        sg.Checkbox("local", key="-TYPE_LOCAL-"),
        sg.Checkbox("reddit", key="-TYPE_REDDIT-"),
        sg.Checkbox("wallhaven", key="-TYPE_WALLHAVEN-"),
        sg.Checkbox("imgur", key="-TYPE_IMGUR-"),
    ]

    # TODO: Possible for some sort of autocomplete?
    tags = get_tags()
    tag_input = sg.Combo(tags, size=(12, 1), key='-TAG_INPUT-')
    tag_search = [tag_input]

    search_layout = sg.Column([
        [sg.Push(), sg.Frame('', [
            tag_search + ar_buttons + [color_bttn, search_button(), image_button()]
        ,
            [sg.Push()] + type_buttons + [clear_button(), download_bttn]
        ])]
    ], expand_x=True)

    item_menu = ['', ['Open', "Mark Duplicate", "Clear Selection"]]
    table = sg.Table(table_data, headings=("ID", "Name", "Source"), size=(18, 18),
                        enable_events=True, right_click_menu=item_menu, right_click_selects=True, key="-IMAGE_LIST-")
    list_layout = sg.Column([
        [table]])

    image_elem = sg.Image(data=placeholder_image)

    view_layout = sg.Column([
        [image_elem]])
    status_bar = sg.StatusBar("...", expand_x=True, auto_size_text=True, size=(1, 1))
    status_layout = [[
            status_bar
        ]]

    top_menu = sg.Menu([
                ["File", ["Settings", ["Local", "Reddit", "Imgur", "Wallhaven"], "Update Images", "Find Duplicates"]],
                ["Help", ["About"]],
            ],
            key="-MENUBAR-", pad=0,
        )

    layout = [
        [top_menu],
        [search_layout],
        [sg.Frame('', [[list_layout, view_layout]])],
        [status_layout]
    ]
    window = sg.Window(
        app_name,
        layout,
        finalize=True,
    )

    images = ImageList([], window=window)
    images.load_images(image_srcs)
    status_bar.update(f"Loading images")

    while True:
        event, values = window.read()
        logger.info(f"Main window event - {event}  {values}")
        images.from_queue()

        if event == sg.WIN_CLOSED or event == "Quit" or event == "Exit":
            logger.info('Closing application')
            break

        # Settings and configs
        elif event == "Local":
            popup_local_settings()
        elif event == "Reddit":
            popup_reddit_settings()
        elif event == "Imgur":
            popup_imgur_settings()
        elif event == "Wallhaven":
            popup_wallhaven_settings()
        elif event == "Update Images":
            popup_scan()
            search.color_search.reload()

        elif event == "Find Duplicates":
            dupes = DuplicateSearch()
            results = dupes.duplicates()

            # This whole section is a bit whack but the images need to be grouped
            # with their duplicates but that cannot be done through SQL so we get
            # get all the images and order them manually
            ids = []
            for key, item in results.items():
                ids.append(key)
                ids.extend(item)
            logger.info(f'Found {len(ids)} potential duplicate images')

            # Query limit can cause errors if there are more duplicates
            # than the limit here as we need all ids
            query = WallpaperQuery({"ids": ids})
            id_to_obj = {obj.id: obj for obj in query(limit=1000)}
            ordered_objs = []
            for key, item in results.items():
                ordered_objs.append(id_to_obj[key])
                ordered_objs.extend((id_to_obj[_id] for _id in item))

            table_data, image_srcs = search.parse_query(ordered_objs)
            table.update(values=table_data)
            if image_srcs:
                images.clear()
                # TODO: Because of the caveat above, this has the potential to
                # dispatch a lot of image loads (100+), should limit or fix
                images.load_images(image_srcs)
                status_bar.update(f"Loading {len(ids)} duplicate images")
        elif event == "Clear Selection":
            table.update(select_rows=[])
            logger.info('Clear table selection')
        elif event == "Mark Duplicate":
            ids = values["-IMAGE_LIST-"]
            ids = [table_data[ix][0] for ix in ids]
            set_duplicate(ids)
            logger.info(f'Setting image {ids} as duplicate')

        # Select downloads
        elif event == "-DOWNLOAD_BUTTON-":
            if values["-IMAGE_LIST-"] == []:
                status_bar.update("No images selected to download")
                logger.info('No images selected for downloading')
            else:
                ix = values["-IMAGE_LIST-"]
                ids = [table_data[i][0] for i in ix]
                status_bar.update("Downloading files...")
                thread = window.start_thread(lambda: download_files(ids), "-DOWNLOAD_THREAD-")
                download_bttn.update(disabled=True)
                logger.info(f'Thread {thread.ident} started for image downloading')

        elif event == "-IMAGE_BUTTON-":
            if values["-IMAGE_LIST-"] == []:
                logger.info('No image selected for compare')
            else:
                ix = values["-IMAGE_LIST-"][0]
                _id = table_data[ix][0]
                dupes = DuplicateSearch()
                ids = dupes.similar(_id)
                logger.info(f'Found {len(ids)} similar images to image {_id}')
                if ids:
                    search.ids = ids
                    table_data, image_srcs = search.find()
                    # Query results are ordered by id so we reorder them
                    table_data, image_srcs = zip(*sorted(zip(table_data, image_srcs), key=lambda x: ids.index(x[0][0])))
                    table.update(values=table_data)
                    if image_srcs:
                        images.clear()
                        images.load_images(image_srcs)
                        status_bar.update("Loading images")

        # Color search selected
        elif event == "-COLOR_BUTTON-":
            hex_color_str = popup_color_chooser()
            logger.info(f"Color selected - {hex_color_str}")
            if hex_color_str is not None:
                color_bttn.update(button_color=hex_color_str)
                search.colors = hex_color_str
            else:
                search.colors = None
                search.query_data["colors"] = None
                color_bttn.update(button_color=orig_button_color)
        # Collect search params and begin loading images
        elif event == "-SEARCH_BUTTON-":
            for key, value in values.items():
                if key.startswith("-RATIO_") and value:
                    w, h = key.strip("-").replace("RATIO_", "").split(":")
                    ar = float(w) / float(h)
                    search.query_data["aspect_ratio"] = ar
                elif key.startswith("-TYPE_") and value:
                    src_type = key.strip("-").replace("TYPE_", "").lower()
                    if value:
                        if search.query_data["source_types"] is None:
                            search.query_data["source_types"] = [src_type]
                        else:
                            search.query_data["source_types"].append(src_type)

            if values['-TAG_INPUT-']:
                search.tags = [values['-TAG_INPUT-']]

            table_data, image_srcs = search.find()
            table.update(values=table_data)
            if image_srcs:
                images.clear()
                images.load_images(image_srcs)
                status_bar.update("Loading images")
        # Clear search params
        elif event == "-CLEAR_BUTTON-":
            logger.info("Clearing search parameters")
            search.clear()
            for each in ar_buttons:
                each.update(value=False)
            for each in type_buttons:
                each.update(value=False)
            color_bttn.update(button_color=orig_button_color)
            tag_input.update(value="")

        elif event == "-SCAN_THREAD-":
            thread_id = values["-SCAN_THREAD-"]
            logger.info(f"Thread {thread_id} completed for image scans")
            status_bar.update("Scan done")

        elif event == "-DOWNLOAD_THREAD-":
            thread_id, err_count = values["-DOWNLOAD_THREAD-"]
            status_bar.update(f"Download done with {len(err_count)} failed files!")
            download_bttn.update(disabled=False)
            logger.info(f"Thread {thread_id} completed for image downloads")

        # Row select event
        elif event == "-IMAGE_LIST-":
            # Load the selected image and use a dummy image if
            # image array has not been fully loaded or if
            # the specific image data errored in loading
            try:
                selection = values["-IMAGE_LIST-"][0]
                image = images[selection]
                if image is None:
                    raise ValueError()
            except (IndexError, ValueError):
                image_elem.update(data=placeholder_image)
            else:
                # simplegui api only supports png
                image_bytes = BytesIO()
                image.save(image_bytes, format="PNG")
                image_elem.update(data=image_bytes.getvalue())
        # Open event on a single image row
        elif event == "Open":
            selection = values["-IMAGE_LIST-"][0]
            image_id = table_data[selection][0]
            image = wallpaper_by_id(image_id)
            logger.info(f"Opening location for image {image_id}")
            if image.source_type == "local":
                open_location(image.src_path)
            else:
                webbrowser.open(image.src_path)

    window.close()
