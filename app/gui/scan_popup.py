import PySimpleGUI as sg
import logging
import threading
from math import ceil

from app.analyze import Crawler, Inspector

logger = logging.getLogger(__name__)


class Scanner:

    def __init__(self):
        self._cancel = False
        self.crawler = Crawler()
        self.inspector = Inspector() 

    def cancel(self):
        self._cancel = True
        self.crawler.cancel()
        self.inspector.cancel()

    def scan(self):
        new_images = self.crawler(600)
        for _ in range(ceil(new_images / 150)):
            if self._cancel:
                break
            self.inspector(limit=150, batch=50)
        logger.info(f'Thread {threading.get_ident()} complete for image scans')


def popup_scan():

    popup_test = sg.T('Gathering new images...')
    window = sg.Window('', [[popup_test], [sg.Cancel(s=10)]], finalize=True)
    scanner = Scanner()
    thread = window.start_thread(lambda: scanner.scan(), "-SCAN_THREAD-")
    logger.info(f'Thread {thread.ident} started for image scans')

    while True:
        event, values = window.read()
        if event == sg.WINDOW_CLOSED or event == "Cancel":
            logger.info('Image scanning cancelled')
            popup_test.update(value="Canceling...")
            scanner.cancel()
        elif event == "-SCAN_THREAD-":
            break

    window.close()
