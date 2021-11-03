import os
from PyQt5 import QtCore, QtWidgets
from app.gui.settings_dialog import Ui_Dialog
from app.gui.image_list import ImageList
from app.db import all_wallpapers, create_session, bulk_update_wallpapers, not_downloaded
from app.async_utils import download as async_download
from app.config import get_config
from time import sleep


class MyDialog(QtWidgets.QDialog):
    def __init__(self):
        super().__init__()
        self.ui = Ui_Dialog()
        self.ui.setupUi(self)


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        self.window = MainWindow
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(800, 600)

        self.centralwidget = ImageList(MainWindow)
        self.centralwidget.setup_ui()
        session = create_session()
        wallpapers = all_wallpapers(session, 100)
        self.centralwidget.unloaded_items = wallpapers
        self.centralwidget.add_images(10)
        MainWindow.setCentralWidget(self.centralwidget)


        self.menubar = QtWidgets.QMenuBar(MainWindow)
        self.menubar.setGeometry(QtCore.QRect(0, 0, 1075, 30))
        self.menubar.setObjectName("menubar")
        self.menuFile = QtWidgets.QMenu(self.menubar)
        self.menuFile.setObjectName("menuFile")
        self.menuActions = QtWidgets.QMenu(self.menubar)
        self.menuActions.setObjectName("menuActions")
        MainWindow.setMenuBar(self.menubar)
        self.statusbar = QtWidgets.QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)
        self.actionPreferences = QtWidgets.QAction(MainWindow)
        self.actionPreferences.setObjectName("actionPreferences")
        self.actionDownload = QtWidgets.QAction(MainWindow)
        self.actionDownload.setObjectName("actionDownload")
        self.actionFind_Duplicates = QtWidgets.QAction(MainWindow)
        self.actionFind_Duplicates.setObjectName("actionFind_Duplicates")
        self.actionAnalyze = QtWidgets.QAction(MainWindow)
        self.actionAnalyze.setObjectName("actionAnalyze")
        self.menuFile.addAction(self.actionPreferences)
        self.menuActions.addAction(self.actionDownload)
        self.menuActions.addAction(self.actionFind_Duplicates)
        self.menuActions.addAction(self.actionAnalyze)
        self.menubar.addAction(self.menuFile.menuAction())
        self.menubar.addAction(self.menuActions.menuAction())

        self.actionPreferences.triggered.connect(self.showPreferences)
        self.actionDownload.triggered.connect(self.download)

        self.retranslateUi(MainWindow)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.menuFile.setTitle(_translate("MainWindow", "File"))
        self.menuActions.setTitle(_translate("MainWindow", "Actions"))
        self.actionPreferences.setText(_translate("MainWindow", "Preferences"))
        self.actionDownload.setText(_translate("MainWindow", "Download"))
        self.actionFind_Duplicates.setText(_translate("MainWindow", "Find Duplicates"))
        self.actionAnalyze.setText(_translate("MainWindow", "Analyze"))

    def showPreferences(self):
        self.myPreferencesWindow = MyDialog()
        self.myPreferencesWindow.show()

    def download(self, limit=12, batch=5):
        diag = QtWidgets.QProgressDialog("Downloading", "Cancel", 0, 100, self.window)
        diag.setModal(True)
        diag.show()

        limit = 12
        batch = 5

        number_of_full_runs = limit // batch
        leftover = limit % batch
        config = get_config()

        session = create_session()
        wallpapers = not_downloaded(session, limit)

        def _download(items):
            urls = []
            filenames = []
            ids = []

            for item in items:
                urls.append(item.source_url)
                filenames.append(os.path.join(config["Core"]["downloadlocation"], item.filename))
                ids.append(item.id)

            async_download(urls, filenames)

            mappings = []
            for _id in ids:
                mappings.append({
                    "id": _id, "downloaded": True
                })
            bulk_update_wallpapers(session, mappings)

        for i in range(number_of_full_runs):
            wallpaper_batch = wallpapers[:batch]
            _download(wallpaper_batch)
            wallpapers = wallpapers[batch:]
            diag.setValue((i / number_of_full_runs) * 100)
        
        if leftover:
            _download(wallpapers)

        diag.setValue(100)
        diag.close()

