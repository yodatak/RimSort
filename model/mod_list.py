# Need rework

from logger_tt import logger
import os
import shutil
from pathlib import Path
from time import sleep
from typing import Any, List, Optional

from PySide6.QtCore import Qt, QEvent, QModelIndex, QObject, Signal
from PySide6.QtGui import QAction, QCursor, QDropEvent, QFocusEvent, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QMenu,
)

from model.mod_list_item import ModListItemInner
from model.dialogue import show_dialogue_conditional, show_warning
from util.generic import (
    delete_files_except_extension,
    open_url_browser,
    platform_specific_open,
)
from util.metadata import edit_workshop_acf_data


class ModListWidget(QListWidget):
    """
    Subclass for QListWidget. Used to store lists for
    active and inactive mods. Mods can be rearranged within
    their own lists or moved from one list to another.
    """

    edit_rules_signal = Signal(bool, str, str)
    item_added_signal = Signal(str)
    key_press_signal = Signal(str)
    list_update_signal = Signal(str)
    mod_info_signal = Signal(str)
    recalculate_warnings_signal = Signal()
    re_git_signal = Signal(list)
    steamcmd_downloader_signal = Signal(list)
    steamworks_subscription_signal = Signal(list)

    def __init__(self, csharp_icon_enable: bool) -> None:
        """
        Initialize the ListWidget with a dict of mods.
        Keys are the package ids and values are a dict of
        mod attributes. See tags:
        https://rimworldwiki.com/wiki/About.xml
        """
        logger.info("Starting ModListWidget initialization")

        super(ModListWidget, self).__init__()

        self.steam_db = None
        self.steamcmd_appworkshop_acf_path = None

        # Allow for dragging and dropping between lists
        self.setDefaultDropAction(Qt.MoveAction)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)

        # Allow for selecting and moving multiple items
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)

        # When an item is clicked, display the mod information
        self.currentItemChanged.connect(self.mod_clicked)

        # When an item is double clicked, move it to the opposite list
        self.itemDoubleClicked.connect(self.mod_double_clicked)

        # Add an eventFilter for per mod_list_item context menu
        self.installEventFilter(self)

        # Disable horizontal scroll bar
        self.horizontalScrollBar().setEnabled(False)
        self.horizontalScrollBar().setVisible(False)

        # Store icon paths
        self.csharp_icon_enable = csharp_icon_enable
        self.csharp_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/csharp.png")
            ).resolve()
        )
        self.git_icon_path = str(
            Path(os.path.join(os.path.dirname(__file__), "../data/git.png")).resolve()
        )
        self.local_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/local_icon.png")
            ).resolve()
        )
        self.ludeon_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/ludeon_icon.png")
            ).resolve()
        )
        self.steamcmd_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/steamcmd_icon.png")
            ).resolve()
        )
        self.steam_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/steam_icon.png")
            ).resolve()
        )
        self.warning_icon_path = str(
            Path(
                os.path.join(os.path.dirname(__file__), "../data/warning.png")
            ).resolve()
        )
        self.error_icon_path = str(
            Path(os.path.join(os.path.dirname(__file__), "../data/error.png")).resolve()
        )

        # Allow inserting custom list items
        self.model().rowsInserted.connect(
            self.handle_rows_inserted, Qt.QueuedConnection
        )

        # Handle removing items to update count
        self.model().rowsAboutToBeRemoved.connect(
            self.handle_rows_removed, Qt.QueuedConnection
        )

        # This set is used to keep track of mods that have been loaded
        # into widgets. Used for an optimization strategy for `handle_rows_inserted`
        self.uuids = set()
        self.ignore_warning_list = []
        logger.info("Finished ModListWidget initialization")

    def dropEvent(self, event: QDropEvent) -> None:
        ret = super().dropEvent(event)
        self.list_update_signal.emit("drop")
        return ret

    def eventFilter(self, source_object: QObject, event: QEvent) -> None:
        """
        https://doc.qt.io/qtforpython/overviews/eventsandfilters.html

        Takes source object and filters an event at the ListWidget level, executes
        an action based on a per-mod_list_item contextMenu

        :param object: the source object returned from the event
        :param event: the QEvent type
        """
        if event.type() == QEvent.ContextMenu and source_object is self:
            # Get the position of the right-click event
            pos = QCursor.pos()
            # Convert the global position to the list widget's coordinate system
            pos_local = self.mapFromGlobal(pos)
            # Get the item at the local position
            item = self.itemAt(pos_local)
            if not isinstance(item, QListWidgetItem):
                logger.debug("Mod list right-click non-QListWidgetItem")
                return super().eventFilter(source_object, event)

            # Otherwise, begin calculation
            logger.info("USER ACTION: Open right-click mod_list_item contextMenu")

            # CONVERSIONS
            # A list to track any publishedfileids for conversion to SteamCMD from local
            tosteamcmd_publishedfileids = []

            # GIT MOD PATHS
            # A list of git mod paths to update
            git_paths = []

            # STEAMCMD MOD PFIDS
            # A list to track any SteamCMD mod paths
            steamcmd_mod_paths = []
            # A list track any SteamCMD mod publishedfileids
            steamcmd_publishedfileids = []

            # STEAM SUBSCRIBE/UNSUBSCRIBE
            # A list to track any workshop mod paths
            steam_mod_paths = []
            # A list to track any workshop mod publishedfileids
            steam_publishedfileids = []

            # Define our QMenu & QActions
            contextMenu = QMenu()
            # Toggle warning action
            toggle_warning_action = None
            # Open folder action
            open_folder_action = None
            # Open URL in browser action
            open_url_browser_action = None
            # Open URL in Steam
            open_mod_steam_action = None
            # Local <-> SteamCMD conversion option
            convert_local_action = None
            convert_steamcmd_action = None
            # Edit mod rules
            edit_mod_rules_action = None
            # Update/Re-download/re-subscribe git/steamcmd/steam mods
            re_git_action = None
            re_steamcmd_action = None
            re_steam_action = None
            # Unsubscribe + delete mod
            unsubscribe_mod_steam_action = None
            # Delete mod
            delete_mod_action = None

            # Get all selected QListWidgetItems
            selected_items = self.selectedItems()
            # Single item selected
            if len(selected_items) == 1:
                source_item = selected_items[0]
                if type(source_item) is QListWidgetItem:
                    source_widget = self.itemWidget(source_item)
                    # Retrieve metadata
                    widget_json_data = source_widget.json_data
                    mod_data_source = widget_json_data.get("data_source")
                    # Open folder action text
                    open_folder_action = QAction()
                    open_folder_action.setText("Open folder")
                    # If we have a "url" or "steam_url"
                    if widget_json_data.get("url") or widget_json_data.get("steam_url"):
                        open_url_browser_action = QAction()
                        open_url_browser_action.setText("Open URL in browser")
                    # If we have a "steam_uri"
                    if widget_json_data.get("steam_uri"):
                        open_mod_steam_action = QAction()
                        open_mod_steam_action.setText("Open mod in Steam")
                    # Conversion options (local <-> SteamCMD) + re-download (SteamCMD)
                    if mod_data_source == "local":
                        mod_folder_name = widget_json_data["folder"]
                        mod_folder_path = widget_json_data["path"]
                        if widget_json_data.get("steamcmd") and widget_json_data.get(
                            "publishedfileid"
                        ):
                            steamcmd_mod_paths.append(mod_folder_path)
                            steamcmd_publishedfileids.append(
                                widget_json_data["publishedfileid"]
                            )
                            # Convert steamcmd mods -> local
                            convert_local_action = QAction()
                            convert_local_action.setText("Convert mod to local")
                            # Re-download steamcmd mods
                            re_steamcmd_action = QAction()
                            re_steamcmd_action.setText("Re-download mod with SteamCMD")
                        elif (
                            self.steam_db
                            and len(self.steam_db) > 0
                            and mod_folder_name in self.steam_db.keys()
                        ):
                            convert_steamcmd_action = QAction()
                            convert_steamcmd_action.setText(
                                "Try to convert mod to SteamCMD"
                            )
                            mod_about_folder_path = os.path.join(
                                mod_folder_path, "About"
                            )
                            if not os.path.exists(mod_about_folder_path):
                                logger.debug(
                                    f"Mod About folder missing. Writing {mod_folder_name} to {mod_about_folder_path}"
                                )
                                os.makedirs(mod_about_folder_path)
                            mod_publishedfileid_txt_path = os.path.join(
                                mod_about_folder_path, "PublishedFileId.txt"
                            )
                            if not os.path.exists(mod_publishedfileid_txt_path):
                                logger.warning(
                                    f"PublishedFileId.txt missing. Writing {mod_folder_name} to {mod_publishedfileid_txt_path}"
                                )
                                with open(
                                    mod_publishedfileid_txt_path, "w"
                                ) as mod_publishedfileid_txt:
                                    mod_publishedfileid_txt.write(mod_folder_name)
                            tosteamcmd_publishedfileids.append(mod_folder_name)
                        # Update git mods if local mod with git repo, but not steamcmd
                        elif widget_json_data.get(
                            "git_repo"
                        ) and not widget_json_data.get("steamcmd"):
                            re_git_action = QAction()
                            re_git_action.setText("Update mod with git")
                            git_paths.append(mod_folder_path)
                    # Edit mod rules with Rule Editor (only for individual mods)
                    edit_mod_rules_action = QAction()
                    edit_mod_rules_action.setText("Edit mod with Rule Editor")
                    # Ignore error action
                    toggle_warning_action = QAction()
                    toggle_warning_action.setText("Toggle warning")
                    # If Workshop, and pfid, allow Steam actions
                    if mod_data_source == "workshop" and widget_json_data.get(
                        "publishedfileid"
                    ):
                        mod_folder_path = widget_json_data["path"]
                        publishedfileid = widget_json_data["publishedfileid"]
                        steam_mod_paths.append(mod_folder_path)
                        steam_publishedfileids.append(int(publishedfileid))
                        # Re-subscribe steam mods
                        if mod_data_source == "workshop":
                            re_steam_action = QAction()
                            re_steam_action.setText("Re-subscribe mod with Steam")
                        # Unsubscribe steam mods
                        unsubscribe_mod_steam_action = QAction()
                        unsubscribe_mod_steam_action.setText(
                            "Unsubscribe mod with Steam"
                        )
                    # Prohibit deletion of game files
                    if not (
                        widget_json_data["data_source"] == "expansion"
                        or widget_json_data["packageId"].startswith("ludeon.rimworld")
                    ):
                        delete_mod_action = QAction()
                        # Delete mod action text
                        delete_mod_action.setText("Delete mod")
            # Multiple items selected
            elif len(selected_items) > 1:  # Multiple items selected
                for source_item in selected_items:
                    if type(source_item) is QListWidgetItem:
                        source_widget = self.itemWidget(source_item)
                        # Retrieve metadata
                        widget_json_data = source_widget.json_data
                        mod_data_source = widget_json_data.get("data_source")
                        # Open folder action text
                        open_folder_action = QAction()
                        open_folder_action.setText("Open folder(s)")
                        # If we have a "url" or "steam_url"
                        if widget_json_data.get("url") or widget_json_data.get(
                            "steam_url"
                        ):
                            open_url_browser_action = QAction()
                            open_url_browser_action.setText("Open URL(s) in browser")
                        # Conversion options (local <-> SteamCMD)
                        if mod_data_source == "local":
                            mod_folder_name = widget_json_data["folder"]
                            mod_folder_path = widget_json_data["path"]
                            if widget_json_data.get(
                                "steamcmd"
                            ) and widget_json_data.get("publishedfileid"):
                                steamcmd_mod_paths.append(mod_folder_path)
                                steamcmd_publishedfileids.append(
                                    widget_json_data["publishedfileid"]
                                )
                                # Convert steamcmd mods -> local
                                if not convert_local_action:
                                    convert_local_action = QAction()
                                    convert_local_action.setText(
                                        "Convert mod(s) to local"
                                    )
                                # Re-download steamcmd mods
                                if not re_steamcmd_action:
                                    re_steamcmd_action = QAction()
                                    re_steamcmd_action.setText(
                                        "Re-download mod(s) with SteamCMD"
                                    )
                            elif (
                                self.steam_db
                                and len(self.steam_db) > 0
                                and mod_folder_name in self.steam_db.keys()
                            ):
                                if not convert_steamcmd_action:
                                    convert_steamcmd_action = QAction()
                                    convert_steamcmd_action.setText(
                                        "Convert mod(s) to SteamCMD"
                                    )
                                mod_about_folder_path = os.path.join(
                                    mod_folder_path, "About"
                                )
                                if not os.path.exists(mod_about_folder_path):
                                    logger.debug(
                                        f"Mod About folder missing. Writing {mod_folder_name} to {mod_about_folder_path}"
                                    )
                                    os.makedirs(mod_about_folder_path)
                                mod_publishedfileid_txt_path = os.path.join(
                                    mod_about_folder_path, "PublishedFileId.txt"
                                )
                                if not os.path.exists(mod_publishedfileid_txt_path):
                                    logger.warning(
                                        f"PublishedFileId.txt missing. Writing {mod_folder_name} to {mod_publishedfileid_txt_path}"
                                    )
                                    with open(
                                        mod_publishedfileid_txt_path, "w"
                                    ) as mod_publishedfileid_txt:
                                        mod_publishedfileid_txt.write(mod_folder_name)
                                tosteamcmd_publishedfileids.append(mod_folder_name)
                            # Update git mods if local mod with git repo, but not steamcmd
                            elif widget_json_data.get(
                                "git_repo"
                            ) and not widget_json_data.get("steamcmd"):
                                if not re_git_action:
                                    re_git_action = QAction()
                                    re_git_action.setText("Update mod(s) with git")
                                git_paths.append(widget_json_data["path"])
                        # No "Edit mod rules" when multiple selected
                        # Toggle warning
                        if not toggle_warning_action:
                            toggle_warning_action = QAction()
                            toggle_warning_action.setText("Toggle warning(s)")
                        # If Workshop, and pfid, allow Steam actions
                        if mod_data_source == "workshop" and widget_json_data.get(
                            "publishedfileid"
                        ):
                            mod_folder_path = widget_json_data["path"]
                            publishedfileid = widget_json_data["publishedfileid"]
                            steam_mod_paths.append(mod_folder_path)
                            steam_publishedfileids.append(int(publishedfileid))
                            # Re-subscribe steam mods
                            if not re_steam_action:
                                re_steam_action = QAction()
                                re_steam_action.setText(
                                    "Re-subscribe mod(s) with Steam"
                                )
                            # Unsubscribe steam mods
                            if not unsubscribe_mod_steam_action:
                                unsubscribe_mod_steam_action = QAction()
                                unsubscribe_mod_steam_action.setText(
                                    "Unsubscribe mod(s) with Steam"
                                )
                        # Prohibit deletion of game files
                        if not (
                            widget_json_data["data_source"] == "expansion"
                            or widget_json_data["packageId"].startswith(
                                "ludeon.rimworld"
                            )
                        ):
                            if not delete_mod_action:
                                delete_mod_action = QAction()
                                # Delete mod action text
                                delete_mod_action.setText("Delete mod(s)")
            # Put together our contextMenu
            if open_folder_action:
                contextMenu.addAction(open_folder_action)
            if open_url_browser_action:
                contextMenu.addAction(open_url_browser_action)
            if open_mod_steam_action:
                contextMenu.addAction(open_mod_steam_action)
            if toggle_warning_action:
                contextMenu.addAction(toggle_warning_action)
            if delete_mod_action:
                contextMenu.addAction(delete_mod_action)
            contextMenu.addSeparator()
            if edit_mod_rules_action or toggle_warning_action:
                misc_options_menu = QMenu(title="Miscellaneous options")
                if edit_mod_rules_action:
                    misc_options_menu.addAction(edit_mod_rules_action)
                if re_git_action:
                    misc_options_menu.addAction(re_git_action)
                contextMenu.addMenu(misc_options_menu)
            if (
                convert_local_action
                or convert_steamcmd_action
                or re_steamcmd_action
                or re_steam_action
                or unsubscribe_mod_steam_action
            ):
                workshop_actions_menu = QMenu(title="Workshop (SteamCMD/Steam)")
                if convert_local_action:
                    workshop_actions_menu.addAction(convert_local_action)
                if convert_steamcmd_action:
                    workshop_actions_menu.addAction(convert_steamcmd_action)
                if re_steamcmd_action:
                    workshop_actions_menu.addAction(re_steamcmd_action)
                if re_steam_action:
                    workshop_actions_menu.addAction(re_steam_action)
                if unsubscribe_mod_steam_action:
                    workshop_actions_menu.addAction(unsubscribe_mod_steam_action)
                contextMenu.addMenu(workshop_actions_menu)
            # Execute QMenu and return it's ACTION
            action = contextMenu.exec_(self.mapToGlobal(event.pos()))
            if action:  # Handle the action for all selected items
                if (  # ACTION: Update git mod(s)
                    action == re_git_action and len(git_paths) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(git_paths)} git mods to be updated.",
                        information="Do you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Updating {len(git_paths)} git mod(s)"
                        )
                        self.re_git_signal.emit(git_paths)
                    return True
                elif (  # ACTION: Convert SteamCMD mod(s) -> local
                    action == convert_local_action
                    and len(steamcmd_publishedfileids) > 0
                ):
                    edit_workshop_acf_data(
                        appworkshop_acf_path=self.steamcmd_appworkshop_acf_path,
                        operation="delete",
                        publishedfileids=steamcmd_publishedfileids,
                    )
                    return True
                elif (  # ACTION: Convert local mod(s) -> SteamCMD
                    action == convert_steamcmd_action
                    and len(tosteamcmd_publishedfileids) > 0
                ):
                    edit_workshop_acf_data(
                        appworkshop_acf_path=self.steamcmd_appworkshop_acf_path,
                        operation="add",
                        publishedfileids=tosteamcmd_publishedfileids,
                    )
                    return True
                elif (  # ACTION: Re-download SteamCMD mod(s)
                    action == re_steamcmd_action and len(steamcmd_publishedfileids) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(steamcmd_publishedfileids)} mods for deletion + re-download.",
                        information="\nThis operation will recursively delete all files, except for .dds textures found, "
                        + "and attempt to re-download the mods via SteamCMD. Do you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Deleting + redownloading {len(steamcmd_publishedfileids)} SteamCMD mod(s)"
                        )
                        for path in steamcmd_mod_paths:
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                        self.steamcmd_downloader_signal.emit(steamcmd_publishedfileids)
                    return True
                elif (  # ACTION: Re-subscribe to mod(s) with Steam
                    action == re_steam_action and len(steam_publishedfileids) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(steam_publishedfileids)} mods for unsubscribe + re-subscribe.",
                        information="\nThis operation will potentially delete .dds textures leftover. Steam is unreliable for this. Do you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Unsubscribing + re-subscribing to {len(steam_publishedfileids)} mod(s)"
                        )
                        for path in steam_mod_paths:
                            delete_files_except_extension(
                                directory=path, extension=".dds"
                            )
                        self.steamworks_subscription_signal.emit(
                            ["unsubscribe", steam_publishedfileids]
                        )
                        self.steamworks_subscription_signal.emit(
                            ["subscribe", steam_publishedfileids]
                        )
                    return True
                elif (  # ACTION: Unsubscribe & delete mod(s) with steam
                    action == unsubscribe_mod_steam_action
                    and len(steam_publishedfileids) > 0
                ):
                    # Prompt user
                    answer = show_dialogue_conditional(
                        title="Are you sure?",
                        text=f"You have selected {len(steam_publishedfileids)} mods for unsubscribe.",
                        information="\nDo you want to proceed?",
                    )
                    if answer == "&Yes":
                        logger.debug(
                            f"Unsubscribing from {len(steam_publishedfileids)} mod(s)"
                        )
                        self.steamworks_subscription_signal.emit(
                            ["unsubscribe", steam_publishedfileids]
                        )
                    return True
                # Execute action for each selected mod
                for source_item in selected_items:
                    if type(source_item) is QListWidgetItem:
                        source_widget = self.itemWidget(source_item)
                        # Retrieve metadata
                        widget_json_data = source_widget.json_data
                        mod_data_source = widget_json_data.get("data_source")
                        mod_path = widget_json_data["path"]
                        # Toggle warning action
                        if action == toggle_warning_action:
                            self.toggle_warning(widget_json_data["packageId"])
                        # Open folder action
                        elif action == open_folder_action:  # ACTION: Open folder
                            if os.path.exists(mod_path):  # If the path actually exists
                                logger.info(f"Opening folder: {mod_path}")
                                platform_specific_open(mod_path)
                        # Open url action
                        elif (
                            action == open_url_browser_action
                        ):  # ACTION: Open URL in browser
                            if widget_json_data.get("url") or widget_json_data.get(
                                "steam_url"
                            ):  # If we have some form of "url" to work with...
                                url = self.get_mod_url(widget_json_data)
                                if url != "":
                                    logger.info(f"Opening url in browser: {url}")
                                    open_url_browser(url)
                        # Open Steam URI with Steam action
                        elif (
                            action == open_mod_steam_action
                        ):  # ACTION: Open steam:// uri in Steam
                            if widget_json_data.get(
                                "steam_uri"
                            ):  # If we have steam_uri
                                platform_specific_open(widget_json_data["steam_uri"])
                        # Edit mod rules action
                        elif action == edit_mod_rules_action:
                            self.edit_rules_signal.emit(
                                True, "user_rules", widget_json_data["packageId"]
                            )
                        # Delete mods action
                        elif action == delete_mod_action and (
                            not widget_json_data["data_source"] == "expansion"
                            or not widget_json_data["packageId"].startswith(
                                "ludeon.rimworld"
                            )
                        ):  # ACTION: Delete mod
                            logger.info(f"Deleting mod at: {mod_path}")
                            shutil.rmtree(mod_path)
            return True
        return super().eventFilter(source_object, event)

    def focusOutEvent(self, e: QFocusEvent) -> None:
        """
        Slot to handle unhighlighting any items in the
        previous list when clicking out of that list.
        """
        self.clearFocus()
        return super().focusOutEvent(e)

    def keyPressEvent(self, e):
        """
        This event occurs when the user presses a key while the mod
        list is in focus.
        """
        key_pressed = QKeySequence(e.key()).toString()
        if (
            key_pressed == "Left"
            or key_pressed == "Right"
            or key_pressed == "Return"
            or key_pressed == "Space"
        ):
            self.key_press_signal.emit(key_pressed)
        else:
            return super().keyPressEvent(e)

    def handle_other_list_row_added(self, uuid: str) -> None:
        self.uuids.discard(uuid)

    def handle_rows_inserted(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are inserted.

        When mods are inserted into the mod list, either through the
        `recreate_mod_list` method above or automatically through dragging
        and dropping on the UI, this function is called. For single-item
        inserts, which happens through the above method or through dragging
        and dropping individual mods, `first` equals `last` and the below
        loop is just run once. In this loop, a custom widget is created,
        which displays the text, icons, etc, and is added to the list item.

        For dragging and dropping multiple items, the loop is run multiple
        times. Importantly, even for multiple items, the number of list items
        is set BEFORE the loop starts running, e.g. if we were dragging 3 mods
        onto a list of 100 mods, this method is called once and by the start
        of this method, `self.count()` is already 103; there are 3 "empty"
        list items that do not have widgets assigned to them.

        However, inserting the initial `n` mods with `recreate_mod_list` has
        an inefficiency: it is only able to insert one at a time. This means
        this method is called `n` times for the first `n` mods.
        One optimization here (saving about 1 second with a 200 mod list) is
        to not emit the list update signal until the number of widgets is
        equal to the number of items. If widgets < items, that means
        widgets are still being added. Only when widgets == items does it mean
        we are done with adding the initial set of mods. We can do this
        by keeping track of the number of widgets currently loaded in the list
        through a set of package_ids (this is imperfect, we will need to switch
        this to using UUID keys TODO). This way, we easily compare `self.count()`
        to the length of the set.

        :param parent: parent to get rows under (not used)
        :param first: index of first item inserted
        :param last: index of last item inserted
        """
        for idx in range(first, last + 1):
            item = self.item(idx)
            if item is not None and self.itemWidget(item) is None:
                data = item.data(Qt.UserRole)
                widget = ModListItemInner(
                    data,
                    csharp_icon_enable=self.csharp_icon_enable,
                    csharp_icon_path=self.csharp_icon_path,
                    git_icon_path=self.git_icon_path,
                    local_icon_path=self.local_icon_path,
                    ludeon_icon_path=self.ludeon_icon_path,
                    steamcmd_icon_path=self.steamcmd_icon_path,
                    steam_icon_path=self.steam_icon_path,
                    warning_icon_path=self.warning_icon_path,
                )
                widget.toggle_warning_signal.connect(self.toggle_warning)
                if data.get("invalid"):
                    widget.main_label.setStyleSheet("QLabel { color : red; }")
                item.setSizeHint(widget.sizeHint())
                self.setItemWidget(item, widget)
                self.uuids.add(data["uuid"])
                self.item_added_signal.emit(data["uuid"])

        if len(self.uuids) == self.count():
            self.list_update_signal.emit(str(self.count()))

    def handle_rows_removed(self, parent: QModelIndex, first: int, last: int) -> None:
        """
        This slot is called when rows are removed.
        Emit a signal with the count of objects remaining to update
        the count label. For some reason this seems to call twice on
        dragging and dropping multiple mods.

        The condition is required because when we `do_clear` or `do_import`,
        the existing list needs to be "wiped", and this counts as `n`
        calls to this function. When this happens, `self.uuids` is
        cleared and `self.count()` remains at the previous number, so we can
        just check for equality here.

        :param parent: parent to get rows under (not used)
        :param first: index of first item removed (not used)
        :param last: index of last item removed (not used)
        """
        if len(self.uuids) == self.count():
            self.list_update_signal.emit(str(self.count()))

    def get_item_widget_at_index(self, idx: int) -> Optional[ModListItemInner]:
        item = self.item(idx)
        if item:
            return self.itemWidget(item)
        return None

    def get_list_items_by_dict(self) -> dict[str, Any]:
        """
        Get a dict of all row item's widgets data. Equal to `mods` in
        recreate mod list.

        :return: a dict of mod data
        """
        logger.info("Returning a list of all mod items by json data")
        mod_dict = {}
        for i in range(self.count()):
            item = self.itemWidget(self.item(i))
            if item:
                # Assume uuid always there, as this should be added when the list item's json data is populated
                mod_dict[item.json_data["uuid"]] = item.json_data
        logger.info(f"Collected json data for {len(mod_dict)} mods")
        return mod_dict

    def get_mod_url(self, widget_json_data) -> str:
        url = ""
        if (  # Workshop mod URL priority: steam_url > url
            widget_json_data["data_source"] == "workshop"
        ):  # If the mod was parsed from a Steam mods source
            if widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # If the steam_url exists
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            elif widget_json_data.get("url") and isinstance(
                widget_json_data["url"],
                str,
            ):  # Otherwise, check if local metadata url exists
                url = widget_json_data["url"]  # Use the local metadata url
            else:  # Otherwise, warn & do nothing
                logger.debug(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        elif (  # Local mod URL priority: url > steam_url
            widget_json_data["data_source"] == "local"
        ):  # If the mod was parsed from a local mods source
            if widget_json_data.get("url") and isinstance(
                widget_json_data["url"],
                str,
            ):  # If the local metadata url exists
                url = widget_json_data["url"]  # Use the local metadata url
            elif widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # Otherwise, if the mod has steam_url
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            else:  # Otherwise, warn & do nothing
                logger.warning(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        elif (  # Expansions don't have url - always use steam_url if available
            widget_json_data["data_source"] == "expansion"
        ):  # Otherwise, the mod MUST be an expansion
            if widget_json_data.get("steam_url") and isinstance(
                widget_json_data["steam_url"], str
            ):  # If the steam_url exists
                url = widget_json_data.get("steam_url")  # Use the Steam URL
            else:  # Otherwise, warn & do nothing
                logger.debug(
                    f"Unable to get url for mod {widget_package_id}"
                )  # TODO: Make warning visible
        else:  # ??? Not possible
            logger.debug(
                f"Tried to parse URL for a mod that does not have a data_source? Erroneous json data: {widget_json_data}"
            )
        return url

    def get_widgets_and_items(self) -> list[tuple[ModListItemInner, QListWidgetItem]]:
        return [
            (self.itemWidget(self.item(i)), self.item(i)) for i in range(self.count())
        ]

    def mod_clicked(self, current: QListWidgetItem, previous: QListWidgetItem) -> None:
        """
        Method to handle clicking on a row or navigating between rows with
        the keyboard. Look up the mod's data by uuid
        """
        if current is not None:
            self.mod_info_signal.emit(current.data(Qt.UserRole)["uuid"])

    def mod_double_clicked(self, item: QListWidgetItem):
        widget = ModListItemInner = self.itemWidget(item)
        self.key_press_signal.emit("DoubleClick")

    def recreate_mod_list(self, mods: dict[str, Any]) -> None:
        """
        Clear all mod items and add new ones from a dict.

        :param mods: dict of mod data
        """
        logger.info("Internally recreating mod list")
        self.clear()
        self.uuids = set()
        if mods:
            for mod_json_data in mods.values():
                list_item = QListWidgetItem(self)
                list_item.setData(Qt.UserRole, mod_json_data)
                self.addItem(list_item)

    def toggle_warning(self, packageId: str) -> None:
        if not (packageId in self.ignore_warning_list):
            self.ignore_warning_list.append(packageId)
        else:
            self.ignore_warning_list.remove(packageId)
        self.recalculate_warnings_signal.emit()
