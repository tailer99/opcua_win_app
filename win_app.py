import sys
import logging
from datetime import datetime

from PyQt5.QtGui import QStandardItem, QIcon, QStandardItemModel
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import QtCore, QtGui, QtWidgets
import opcua
from opcua import Node
from asyncua import ua
from asyncua.sync import Client, SyncNode
from asyncua.tools import endpoint_to_strings

from uawidgets import *
from uawidgets import tree_widget, refs_widget, attrs_widget
from uawidgets.utils import trycatchslot

logger = logging.getLogger(__name__)


class DataChangeHandler(QObject):
    data_change_fired = pyqtSignal(object, str, str)

    def datachange_notification(self, node, val, data):
        print(' datachange_notification start ', node, val, data.monitored_item.Value.Value)
        if data.monitored_item.Value.SourceTimestamp:
            data_ts = data.monitored_item.Value.SourceTimestamp.isoformat()
        elif data.monitored_item.Value.ServerTimestamp:
            data_ts = data.monitored_item.Value.ServerTimestamp.isoformat()
        else:
            data_ts = datetime.now().isoformat()
        self.data_change_fired.emit(node, str(val), data_ts)


class DataChangeUI(object):

    def __init__(self, window, client):
        self.window = window
        self.client = client
        self._subhandler = DataChangeHandler()
        self._subscribed_nodes = []
        self.model = QStandardItemModel()
        self.window.subView.setModel(self.model)
        self.window.subView.horizontalHeader().setSectionResizeMode(1)

        self.window.actionSubscribeDataChange.triggered.connect(self._subscribe)
        self.window.actionUnsubscribeDataChange.triggered.connect(self._unsubscribe)

        # populate contextual menu
        self.window.addAction(self.window.actionSubscribeDataChange)
        self.window.addAction(self.window.actionUnsubscribeDataChange)

        # handle subscriptions
        self._subhandler.data_change_fired.connect(self._update_subscription_model, type=Qt.QueuedConnection)

        # accept drops
        self.model.canDropMimeData = self.canDropMimeData
        self.model.dropMimeData = self.dropMimeData

    def canDropMimeData(self, mdata, action, row, column, parent):
        return True

    def dropMimeData(self, mdata, action, row, column, parent):
        node = self.uaclient.client.get_node(mdata.text())
        self._subscribe(node)
        return True

    def clear(self):
        self._subscribed_nodes = []
        self.model.clear()

    def show_error(self, *args):
        self.window.show_error(*args)

    @trycatchslot
    def _subscribe(self, node=None):
        if not isinstance(node, SyncNode):
            node = self.window.get_current_node()
            if node is None:
                return
        if node in self._subscribed_nodes:
            logger.warning("allready subscribed to node: %s ", node)
            return
        self.model.setHorizontalHeaderLabels(["DisplayName", "Value", "Timestamp"])
        text = node.read_display_name().Text
        row = [QStandardItem(text), QStandardItem("No Data yet"), QStandardItem("")]
        row[0].setData(node)
        self.model.appendRow(row)
        self._subscribed_nodes.append(node)
        self.window.subDockWidget.raise_()
        try:
            self.window.subscribe_datachange(node, self._subhandler)
        except Exception as ex:
            self.window.show_error(ex)
            idx = self.model.indexFromItem(row[0])
            self.model.takeRow(idx.row())
            raise

    @trycatchslot
    def _unsubscribe(self):
        node = self.window.get_current_node()
        if node is None:
            return
        self.window.unsubscribe_datachange(node)
        print(' before  _subscribed_nodes  : ', self._subscribed_nodes)
        self._subscribed_nodes.remove(node)
        print(' after   _subscribed_nodes  : ', self._subscribed_nodes)
        i = 0
        while self.model.item(i):
            item = self.model.item(i)
            if item.data() == node:
                print(' Found : ', node)
                self.model.removeRow(i)
            i += 1

    def _update_subscription_model(self, node, value, timestamp):
        i = 0
        while self.model.item(i):
            item = self.model.item(i)
            if item.data() == node:
                it = self.model.item(i, 1)
                it.setText(value)
                it_ts = self.model.item(i, 2)
                it_ts.setText(timestamp)
            i += 1


class EventHandler(QObject):
    event_fired = pyqtSignal(object)

    def event_notification(self, event):
        print(' event_notification start ', event)
        self.event_fired.emit(event)


class EventUI(object):

    def __init__(self, window, uaclient):
        self.window = window
        self.uaclient = uaclient
        self._handler = EventHandler()
        self._subscribed_nodes = []  # FIXME: not really needed
        self.model = QStandardItemModel()
        self.window.eventView.setModel(self.model)
        self.window.actionSubscribeEvent.triggered.connect(self._subscribe)
        self.window.actionUnsubscribeEvents.triggered.connect(self._unsubscribe)
        # context menu
        self.window.addAction(self.window.actionSubscribeEvent)
        self.window.addAction(self.window.actionUnsubscribeEvents)
        self.window.addAction(self.window.actionAddToGraph)
        self._handler.event_fired.connect(self._update_event_model, type=Qt.QueuedConnection)

        # accept drops
        self.model.canDropMimeData = self.canDropMimeData
        self.model.dropMimeData = self.dropMimeData

    def canDropMimeData(self, mdata, action, row, column, parent):
        return True

    def show_error(self, *args):
        self.window.show_error(*args)

    def dropMimeData(self, mdata, action, row, column, parent):
        node = self.uaclient.client.get_node(mdata.text())
        self._subscribe(node)
        return True

    def clear(self):
        self._subscribed_nodes = []
        self.model.clear()

    @trycatchslot
    def _subscribe(self, node=None):
        logger.info("Subscribing to %s", node)
        print("11Subscribing to ", node)
        if not node:
            node = self.window.get_current_node()
            if node is None:
                return
        if node in self._subscribed_nodes:
            logger.info("already subscribed to event for node: %s", node)
            return
        logger.info("Subscribing to events for %s", node)
        print("22Subscribing to ", node)
        self.window.eventDockWidget.raise_()
        print("33Subscribing to ", node)
        try:
            self.window.subscribe_events(node, self._handler)
            print("44Subscribing to ", node)
        except Exception as ex:
            print("55Subscribing to ", node)
            self.window.show_error(ex)
            raise
        else:
            self._subscribed_nodes.append(node)
            print("66Subscribing to ", node)
        print("77Subscribing to ", node)

    @trycatchslot
    def _unsubscribe(self):
        node = self.window.get_current_node()
        if node is None:
            return
        print(' before  _subscribed_nodes  : ', self._subscribed_nodes)
        self._subscribed_nodes.remove(node)
        print(' before  _subscribed_nodes  : ', self._subscribed_nodes)
        self.window.unsubscribe_events(node)

    @trycatchslot
    def _update_event_model(self, event):
        self.model.appendRow([QStandardItem(str(event))])


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 200, 300, 200)
        self.setWindowTitle("OPC UA Trans")

        self.setObjectName("MainWindow")
        # self.move(100, 50)
        # self.resize(922, 879)
        # icon = QtGui.QIcon()
        # icon.addPixmap(QtGui.QPixmap("../network.svg"), QtGui.QIcon.Normal, QtGui.QIcon.Off)
        # self.setWindowIcon(icon)

        self.centralWidget = QtWidgets.QWidget(self)
        self.centralWidget.setObjectName("centralWidget")

        self.gridCentral = QtWidgets.QGridLayout(self.centralWidget)
        self.gridCentral.setContentsMargins(11, 11, 11, 11)
        self.gridCentral.setSpacing(6)
        self.gridCentral.setObjectName("gridCentral")

        self.splitter = QtWidgets.QSplitter(self.centralWidget)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.splitter.sizePolicy().hasHeightForWidth())
        self.splitter.setSizePolicy(sizePolicy)
        self.splitter.setOrientation(QtCore.Qt.Horizontal)
        self.splitter.setObjectName("splitter")

        self.treeView = QtWidgets.QTreeView(self.splitter)
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.treeView.sizePolicy().hasHeightForWidth())
        self.treeView.setSizePolicy(sizePolicy)
        self.treeView.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self.treeView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.treeView.setDragEnabled(True)
        self.treeView.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.treeView.setObjectName("treeView")
        self.gridCentral.addWidget(self.splitter, 0, 0, 1, 1)
        self.setCentralWidget(self.centralWidget)

        #############################
        #############################

        self.addrDockWidget = QtWidgets.QDockWidget(self)
        self.addrDockWidget.setObjectName("addrDockWidget")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Minimum)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addrDockWidget.sizePolicy().hasHeightForWidth())
        self.addrDockWidget.setSizePolicy(sizePolicy)
        self.addrDockWidget.setFeatures(QtWidgets.QDockWidget.NoDockWidgetFeatures)
        self.addrDockWidget.setAllowedAreas(QtCore.Qt.TopDockWidgetArea)

        self.addrDockWidgetContents = QtWidgets.QWidget()
        self.addrDockWidgetContents.setObjectName("addrDockWidgetContents")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addrDockWidgetContents.sizePolicy().hasHeightForWidth())
        self.addrDockWidgetContents.setSizePolicy(sizePolicy)

        self.gridAddr = QtWidgets.QGridLayout(self.addrDockWidgetContents)
        self.gridAddr.setObjectName("gridAddress")
        self.gridAddr.setContentsMargins(11, 11, 11, 11)
        self.gridAddr.setSpacing(6)

        self.connectButton = QtWidgets.QPushButton(self.addrDockWidgetContents)
        self.connectButton.setObjectName("connectButton")
        self.gridAddr.addWidget(self.connectButton, 1, 4, 1, 1)

        self.disconnectButton = QtWidgets.QPushButton(self.addrDockWidgetContents)
        self.disconnectButton.setObjectName("disconnectButton")
        self.gridAddr.addWidget(self.disconnectButton, 1, 5, 1, 1)

        self.addrComboBox = QtWidgets.QComboBox(self.addrDockWidgetContents)
        self.addrComboBox.setObjectName("addrComboBox")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.addrComboBox.sizePolicy().hasHeightForWidth())
        self.addrComboBox.setSizePolicy(sizePolicy)
        self.addrComboBox.setEditable(True)
        self.addrComboBox.setInsertPolicy(QtWidgets.QComboBox.InsertAtTop)
        self.gridAddr.addWidget(self.addrComboBox, 1, 2, 1, 1)

        self.connectOptionButton = QtWidgets.QPushButton(self.addrDockWidgetContents)
        self.connectOptionButton.setObjectName("connectOptionButton")
        self.gridAddr.addWidget(self.connectOptionButton, 1, 3, 1, 1)

        self.addrDockWidget.setWidget(self.addrDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(4), self.addrDockWidget)

        ###################

        self.attrDockWidget = QtWidgets.QDockWidget(self)
        self.attrDockWidget.setObjectName("attrDockWidget")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.attrDockWidget.sizePolicy().hasHeightForWidth())
        self.attrDockWidget.setSizePolicy(sizePolicy)
        # self.attrDockWidget.setMinimumSize(QtCore.QSize(400, 170))
        self.attrDockWidget.setMinimumSize(QtCore.QSize(500, 300))

        self.attrDockWidgetContents = QtWidgets.QWidget()
        self.attrDockWidgetContents.setObjectName("attrDockWidgetContents")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.attrDockWidgetContents.sizePolicy().hasHeightForWidth())
        self.attrDockWidgetContents.setSizePolicy(sizePolicy)
        self.attrDockWidgetContents.setMinimumSize(QtCore.QSize(100, 0))

        self.gridAttr = QtWidgets.QGridLayout(self.attrDockWidgetContents)
        self.gridAttr.setObjectName("gridAttr")
        self.gridAttr.setContentsMargins(11, 11, 11, 11)
        self.gridAttr.setSpacing(6)

        self.attrView = QtWidgets.QTreeView(self.attrDockWidgetContents)
        self.attrView.setObjectName("attrView")
        self.attrView.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.attrView.setEditTriggers(QtWidgets.QAbstractItemView.AllEditTriggers)
        self.attrView.setProperty("showDropIndicator", False)
        self.attrView.setTextElideMode(QtCore.Qt.ElideNone)
        self.attrView.setAutoExpandDelay(-1)
        self.attrView.setIndentation(18)
        self.attrView.setSortingEnabled(True)
        self.attrView.setWordWrap(True)
        self.gridAttr.addWidget(self.attrView, 0, 0, 1, 2)

        spacerItem = QtWidgets.QSpacerItem(40, 20, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Minimum)
        self.gridAttr.addItem(spacerItem, 1, 0, 1, 1)

        self.attrRefreshButton = QtWidgets.QPushButton(self.attrDockWidgetContents)
        self.attrRefreshButton.setObjectName("attrRefreshButton")
        self.gridAttr.addWidget(self.attrRefreshButton, 1, 1, 1, 1)

        self.attrDockWidget.setWidget(self.attrDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.attrDockWidget)

        #######################

        self.subDockWidget = QtWidgets.QDockWidget(self)
        self.subDockWidget.setObjectName("subDockWidget")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.subDockWidget.sizePolicy().hasHeightForWidth())
        self.subDockWidget.setSizePolicy(sizePolicy)

        self.subDockWidgetContents = QtWidgets.QWidget()
        self.subDockWidgetContents.setObjectName("subDockWidgetContents")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.subDockWidgetContents.sizePolicy().hasHeightForWidth())
        self.subDockWidgetContents.setSizePolicy(sizePolicy)

        self.gridSub = QtWidgets.QGridLayout(self.subDockWidgetContents)
        self.gridSub.setContentsMargins(11, 11, 11, 11)
        self.gridSub.setSpacing(6)
        self.gridSub.setObjectName("gridSub")

        self.subView = QtWidgets.QTableView(self.subDockWidgetContents)
        self.subView.setObjectName("subView")
        self.subView.setAcceptDrops(True)
        self.subView.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
        self.subView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.subView.setDragDropOverwriteMode(False)
        self.subView.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.gridSub.addWidget(self.subView, 0, 0, 1, 1)

        self.subDockWidget.setWidget(self.subDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.subDockWidget)

        ########################

        self.refDockWidget = QtWidgets.QDockWidget(self)
        self.refDockWidget.setObjectName("refDockWidget")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.refDockWidget.sizePolicy().hasHeightForWidth())
        self.refDockWidget.setSizePolicy(sizePolicy)

        self.refDockWidgetContents = QtWidgets.QWidget()
        self.refDockWidgetContents.setObjectName("refDockWidgetContents")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.refDockWidgetContents.sizePolicy().hasHeightForWidth())
        self.refDockWidgetContents.setSizePolicy(sizePolicy)

        self.refVertLayout = QtWidgets.QVBoxLayout(self.refDockWidgetContents)
        self.refVertLayout.setObjectName("refVertLayout")
        self.refVertLayout.setContentsMargins(11, 11, 11, 11)
        self.refVertLayout.setSpacing(6)

        self.refView = QtWidgets.QTableView(self.refDockWidgetContents)
        self.refView.setObjectName("refView")
        self.refView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.refVertLayout.addWidget(self.refView)

        self.refDockWidget.setWidget(self.refDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.refDockWidget)

        ######################

        self.eventDockWidget = QtWidgets.QDockWidget(self)
        self.eventDockWidget.setObjectName("eventDockWidget")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.eventDockWidget.sizePolicy().hasHeightForWidth())
        self.eventDockWidget.setSizePolicy(sizePolicy)

        self.eventDockWidgetContents = QtWidgets.QWidget()
        self.eventDockWidgetContents.setObjectName("eventDockWidgetContents")

        self.gridEventLayout = QtWidgets.QGridLayout(self.eventDockWidgetContents)
        self.gridEventLayout.setObjectName("gridEventLayout")
        self.gridEventLayout.setContentsMargins(11, 11, 11, 11)
        self.gridEventLayout.setSpacing(6)

        self.eventView = QtWidgets.QListView(self.eventDockWidgetContents)
        self.eventView.setObjectName("eventView")
        self.eventView.setAcceptDrops(True)
        self.eventView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.eventView.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.gridEventLayout.addWidget(self.eventView, 0, 0, 1, 1)

        self.eventDockWidget.setWidget(self.eventDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.eventDockWidget)

        ######################

        self.logDockWidget = QtWidgets.QDockWidget(self)
        self.logDockWidget.setObjectName("logDockWidget")

        self.logDockWidgetContents = QtWidgets.QWidget()
        self.logDockWidgetContents.setObjectName("logDockWidgetContents")

        self.gridLogLayout = QtWidgets.QGridLayout(self.logDockWidgetContents)
        self.gridLogLayout.setObjectName("gridLogLayout")
        self.gridLogLayout.setContentsMargins(11, 11, 11, 11)
        self.gridLogLayout.setSpacing(6)

        self.logTextEdit = QtWidgets.QTextEdit(self.logDockWidgetContents)
        self.logTextEdit.setObjectName("logTextEdit")
        self.gridLogLayout.addWidget(self.logTextEdit, 0, 0, 1, 1)

        self.logDockWidget.setWidget(self.logDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(8), self.logDockWidget)

        #######################

        self.graphDockWidget = QtWidgets.QDockWidget(self)
        self.graphDockWidget.setObjectName("graphDockWidget")

        self.graphDockWidgetContents = QtWidgets.QWidget()
        self.graphDockWidgetContents.setObjectName("graphDockWidgetContents")

        self.gridGraphLayout = QtWidgets.QGridLayout(self.graphDockWidgetContents)
        self.gridGraphLayout.setObjectName("gridGraphLayout")
        self.gridGraphLayout.setContentsMargins(11, 11, 11, 11)
        self.gridGraphLayout.setSpacing(6)

        self.graphLayout = QtWidgets.QVBoxLayout()
        self.graphLayout.setObjectName("graphLayout")
        self.graphLayout.setSpacing(6)

        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setSpacing(6)

        self.labelNumberOfPoints = QtWidgets.QLabel(self.graphDockWidgetContents)
        self.labelNumberOfPoints.setObjectName("labelNumberOfPoints")
        self.horizontalLayout.addWidget(self.labelNumberOfPoints)

        self.spinBoxNumberOfPoints = QtWidgets.QSpinBox(self.graphDockWidgetContents)
        self.spinBoxNumberOfPoints.setObjectName("spinBoxNumberOfPoints")
        self.spinBoxNumberOfPoints.setMinimum(10)
        self.spinBoxNumberOfPoints.setMaximum(100)
        self.spinBoxNumberOfPoints.setProperty("value", 30)
        self.horizontalLayout.addWidget(self.spinBoxNumberOfPoints)

        self.labelInterval = QtWidgets.QLabel(self.graphDockWidgetContents)
        self.labelInterval.setObjectName("labelInterval")
        self.horizontalLayout.addWidget(self.labelInterval)

        self.spinBoxInterval = QtWidgets.QSpinBox(self.graphDockWidgetContents)
        self.spinBoxInterval.setObjectName("spinBoxInterval")
        self.spinBoxInterval.setMinimum(1)
        self.spinBoxInterval.setMaximum(3600)
        self.spinBoxInterval.setProperty("value", 5)
        self.horizontalLayout.addWidget(self.spinBoxInterval)

        self.buttonApply = QtWidgets.QPushButton(self.graphDockWidgetContents)
        self.buttonApply.setObjectName("buttonApply")
        self.horizontalLayout.addWidget(self.buttonApply)
        self.graphLayout.addLayout(self.horizontalLayout)
        self.gridGraphLayout.addLayout(self.graphLayout, 0, 0, 1, 1)

        self.graphDockWidget.setWidget(self.graphDockWidgetContents)
        self.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.graphDockWidget)

        ########################
        #############################

        self.menuBar = QtWidgets.QMenuBar(self)
        self.menuBar.setGeometry(QtCore.QRect(0, 0, 922, 21))
        self.menuBar.setObjectName("menuBar")
        self.menuOPC_UA_Client = QtWidgets.QMenu(self.menuBar)
        self.menuOPC_UA_Client.setObjectName("menuOPC_UA_Client")
        self.menuSettings = QtWidgets.QMenu(self.menuBar)
        self.menuSettings.setObjectName("menuSettings")
        self.setMenuBar(self.menuBar)

        self.statusBar = QtWidgets.QStatusBar(self)
        self.statusBar.setObjectName("statusBar")
        self.setStatusBar(self.statusBar)

        self.actionConnect = QtWidgets.QAction(self)
        self.actionConnect.setObjectName("actionConnect")
        self.actionDisconnect = QtWidgets.QAction(self)
        self.actionDisconnect.setObjectName("actionDisconnect")
        self.actionSubscribeDataChange = QtWidgets.QAction(self)
        self.actionSubscribeDataChange.setObjectName("actionSubscribeDataChange")
        self.actionUnsubscribeDataChange = QtWidgets.QAction(self)
        self.actionUnsubscribeDataChange.setObjectName("actionUnsubscribeDataChange")
        self.actionSubscribeEvent = QtWidgets.QAction(self)
        self.actionSubscribeEvent.setObjectName("actionSubscribeEvent")
        self.actionUnsubscribeEvents = QtWidgets.QAction(self)
        self.actionUnsubscribeEvents.setObjectName("actionUnsubscribeEvents")
        self.actionCopyPath = QtWidgets.QAction(self)
        self.actionCopyPath.setObjectName("actionCopyPath")
        self.actionCopyNodeId = QtWidgets.QAction(self)
        self.actionCopyNodeId.setObjectName("actionCopyNodeId")
        self.actionAddToGraph = QtWidgets.QAction(self)
        self.actionAddToGraph.setObjectName("actionAddToGraph")
        self.actionRemoveFromGraph = QtWidgets.QAction(self)
        self.actionRemoveFromGraph.setObjectName("actionRemoveFromGraph")
        self.actionCall = QtWidgets.QAction(self)
        self.actionCall.setObjectName("actionCall")
        self.actionDark_Mode = QtWidgets.QAction(self)
        self.actionDark_Mode.setCheckable(True)
        self.actionDark_Mode.setObjectName("actionDark_Mode")

        self.menuOPC_UA_Client.addAction(self.actionConnect)
        self.menuOPC_UA_Client.addAction(self.actionDisconnect)
        self.menuOPC_UA_Client.addAction(self.actionCopyPath)
        self.menuOPC_UA_Client.addAction(self.actionCopyNodeId)
        self.menuOPC_UA_Client.addAction(self.actionSubscribeDataChange)
        self.menuOPC_UA_Client.addAction(self.actionUnsubscribeDataChange)
        self.menuOPC_UA_Client.addAction(self.actionSubscribeEvent)
        self.menuOPC_UA_Client.addAction(self.actionUnsubscribeEvents)
        self.menuSettings.addAction(self.actionDark_Mode)

        self.menuBar.addAction(self.menuOPC_UA_Client.menuAction())
        self.menuBar.addAction(self.menuSettings.menuAction())

        self.retranslateUi()
        QtCore.QMetaObject.connectSlotsByName(self)

        ###########################################

        # w = QWidget()
        # self.addrDockWidget.setTitleBarWidget(w)

        # tabify some docks
        self.tabifyDockWidget(self.attrDockWidget, self.eventDockWidget)

        # self.tabifyDockWidget(self.eventDockWidget, self.subDockWidget)
        self.tabifyDockWidget(self.subDockWidget, self.refDockWidget)
        self.tabifyDockWidget(self.refDockWidget, self.graphDockWidget)

        # self.treePoint = QTreeWidget(self)
        # self.treePoint.setGeometry(10, 30, 600, 500)

        # self.btnConnect = QPushButton("Connect", self)
        # self.btnConnect.move(1200, 100)
        # self.btnConnect.clicked.connect(self.connect)
        #
        # self.btnSearch = QPushButton("Search", self)
        # self.btnSearch.move(1200, 150)
        # self.btnSearch.clicked.connect(self.search_node)

        #############################
        #############################

        # setup QSettings for application and get a settings object
        QCoreApplication.setOrganizationName("SKCC")
        QCoreApplication.setApplicationName("OpcUaClient")
        self.settings = QSettings()

        self._address_list = self.settings.value("address_list", ["opc.tcp://10.178.59.49:7560/", "opc.tcp://localhost:4840", ])
        self._address_list_max_count = int(self.settings.value("address_list_max_count", 5))

        # init widgets
        # for i, addr in enumerate(self._address_list):
        #     self.addrComboBox.insertItem(i, addr)
        self.addrComboBox.addItems(self._address_list)

        #################################################
        #################################################

        # self.uaclient = Client()

        self.tree_ui = tree_widget.TreeWidget(self.treeView)
        self.tree_ui.error.connect(self.show_error)
        self.setup_context_menu_tree()
        # self.ui.treeView.selectionModel().currentChanged.connect(self._update_actions_state)
        self.treeView.selectionModel().selectionChanged.connect(self.show_refs)
        self.treeView.selectionModel().selectionChanged.connect(self.show_attrs)
        self.attrRefreshButton.clicked.connect(self.show_attrs)
        # 상단 메뉴에서 연결
        self.actionCopyPath.triggered.connect(self.tree_ui.copy_path)
        self.actionCopyNodeId.triggered.connect(self.tree_ui.copy_nodeid)

        self.connectButton.clicked.connect(self.connect)
        self.disconnectButton.clicked.connect(self.disconnect)
        # self.connectOptionButton.clicked.connect(self.show_connection_dialog)
        # 상단 메뉴에서 연결
        self.actionConnect.triggered.connect(self.connect)
        self.actionDisconnect.triggered.connect(self.disconnect)
        self.actionDark_Mode.triggered.connect(self.dark_mode)

        self.refs_ui = refs_widget.RefsWidget(self.refView)
        self.refs_ui.error.connect(self.show_error)
        self.attrs_ui = attrs_widget.AttrsWidget(self.attrView)
        self.attrs_ui.error.connect(self.show_error)

        # TODO 동작 안함
        self.addrComboBox.currentTextChanged.connect(self._uri_changed)
        self._uri_changed(self.addrComboBox.currentText())  # force update for current value at startup

        # TODO 동작 안함
        # print(int(self.settings.value("main_window_width", 1000)), int(self.settings.value("main_window_height", 800)))
        self.resize(int(self.settings.value("main_window_width", 1000)), int(self.settings.value("main_window_height", 800)))
        data = self.settings.value("main_window_state", None)
        if data:
            self.restoreState(data)

        ##############################

        self.client = None
        self._connected = False
        self._datachange_sub = None
        self._event_sub = None
        self._subs_datachange = {}
        self._subs_event = {}

        self.security_mode = None
        self.security_policy = None
        self.certificate_path = None
        self.private_key_path = None

        ##############################

    def _reset(self):
        self.client = None
        self._connected = False
        self._datachange_sub = None
        self._event_sub = None
        self._subs_datachange = {}
        self._subs_event = {}

    def retranslateUi(self):
        _translate = QtCore.QCoreApplication.translate
        self.setWindowTitle(_translate("MainWindow", "FreeOpcUa Client"))
        self.menuOPC_UA_Client.setTitle(_translate("MainWindow", "Act&ions"))
        self.menuSettings.setTitle(_translate("MainWindow", "Settings"))
        self.attrDockWidget.setWindowTitle(_translate("MainWindow", "&Attributes"))
        self.attrRefreshButton.setText(_translate("MainWindow", "Refresh"))
        self.connectButton.setText(_translate("MainWindow", "Connect"))
        self.disconnectButton.setText(_translate("MainWindow", "Disconnect"))
        self.connectOptionButton.setText(_translate("MainWindow", "Connect options"))
        self.subDockWidget.setWindowTitle(_translate("MainWindow", "S&ubscriptions"))
        self.refDockWidget.setWindowTitle(_translate("MainWindow", "&References"))
        self.eventDockWidget.setWindowTitle(_translate("MainWindow", "&Events"))
        self.graphDockWidget.setWindowTitle(_translate("MainWindow", "&Graph"))
        self.labelNumberOfPoints.setText(_translate("MainWindow", "Number of Points"))
        self.labelInterval.setText(_translate("MainWindow", "Intervall [s]"))
        self.buttonApply.setText(_translate("MainWindow", "Apply"))

        self.actionConnect.setText(_translate("MainWindow", "&Connect"))
        self.actionDisconnect.setText(_translate("MainWindow", "&Disconnect"))
        self.actionDisconnect.setToolTip(_translate("MainWindow", "Disconnect from server"))
        self.actionSubscribeDataChange.setText(_translate("MainWindow", "&Subscribe to data change"))
        self.actionSubscribeDataChange.setToolTip(_translate("MainWindow", "Subscribe to data change from selected node"))
        self.actionUnsubscribeDataChange.setText(_translate("MainWindow", "&Unsubscribe to DataChange"))
        self.actionUnsubscribeDataChange.setToolTip(_translate("MainWindow", "Unsubscribe to DataChange for current node"))
        self.actionSubscribeEvent.setText(_translate("MainWindow", "Subscribe to &events"))
        self.actionSubscribeEvent.setToolTip(_translate("MainWindow", "Subscribe to events from selected node"))
        self.actionUnsubscribeEvents.setText(_translate("MainWindow", "U&nsubscribe to Events"))
        self.actionUnsubscribeEvents.setToolTip(_translate("MainWindow", "Unsubscribe to Events from current node"))
        self.actionCopyPath.setText(_translate("MainWindow", "Copy &Path"))
        self.actionCopyPath.setToolTip(_translate("MainWindow", "Copy path to node to clipboard"))
        self.actionCopyNodeId.setText(_translate("MainWindow", "C&opy NodeId"))
        self.actionCopyNodeId.setToolTip(_translate("MainWindow", "Copy NodeId to clipboard"))
        self.actionAddToGraph.setText(_translate("MainWindow", "Add to &Graph"))
        self.actionAddToGraph.setToolTip(_translate("MainWindow", "Add this node to the graph"))
        self.actionAddToGraph.setShortcut(_translate("MainWindow", "Ctrl+G"))
        self.actionRemoveFromGraph.setText(_translate("MainWindow", "Remove from Graph"))
        self.actionRemoveFromGraph.setToolTip(_translate("MainWindow", "Remove this node from the graph"))
        self.actionRemoveFromGraph.setShortcut(_translate("MainWindow", "Ctrl+Shift+G"))
        self.actionCall.setText(_translate("MainWindow", "Call"))
        self.actionCall.setToolTip(_translate("MainWindow", "Call Ua Method"))
        self.actionDark_Mode.setText(_translate("MainWindow", "Dark Mode"))
        self.actionDark_Mode.setStatusTip(_translate("MainWindow", "Enables Dark Mode Theme"))

    @trycatchslot
    def connect(self):
        endpoint_url = self.addrComboBox.currentText()
        endpoint_url = endpoint_url.strip()
        try:
            self.client = Client(endpoint_url, timeout=2)
            self.client.connect()

            # client 연결 후 초기화 시킴
            self.datachange_ui = DataChangeUI(self, self.client)
            self.event_ui = EventUI(self, self.client)

            # self.graph_ui = GraphUI(self, self.uaclient)
        except Exception as ex:
            self.show_error(ex)
            raise

        self._update_address_list(endpoint_url)

        self.retrieve_tree()

    # Tree 항목들을 조회후 펼치기
    def retrieve_tree(self):

        root_node = self.client.nodes.root
        # self.tree_ui.set_root_node(self.client.nodes.root)
        # print('root_node_attr : ', type(root_node), self.get_node_attrs(root_node))

        descs = root_node.get_children_descriptions()
        descs.sort(key=lambda x: x.BrowseName)
        for node in descs:
            if node.DisplayName.Text == "Objects":
                # print(type(node), type(node.NodeId), node.NodeId)
                c_descs = self.client.get_node(node.NodeId).get_children_descriptions()
                # print(c_descs)
                for c_node in c_descs:
                    if c_node.DisplayName.Text == "Server":
                        pass
                    else:
                        root_node = self.client.get_node(c_node.NodeId)
        # print(' root_node : ', root_node)
        self.tree_ui.set_root_node(root_node)
        self.treeView.setFocus()
        self.treeView.expandToDepth(5)

        # print(self.treeView.currentIndex().row(), self.treeView.currentIndex().data())
        # print(self.treeView.currentIndex().child(0,0).data())

    def disconnect(self):
        try:
            self.client.disconnect()
        finally:
            self._reset()

    def _update_address_list(self, uri):
        if uri == self._address_list[0]:
            return
        if uri in self._address_list:
            self._address_list.remove(uri)
        self._address_list.insert(0, uri)
        if len(self._address_list) > self._address_list_max_count:
            self._address_list.pop(-1)

    def get_current_node(self, idx=None):
        return self.tree_ui.get_current_node(idx)

    def get_child_node(self, node):
        if not isinstance(node, SyncNode):
            node = self.client.get_node(node)

        c_node = node.get_children()
        return c_node

    @staticmethod
    def get_children(node):
        descs = node.get_children_descriptions()
        descs.sort(key=lambda x: x.BrowseName)
        return descs

    def search_node(self):
        root_node_id = self.client.nodes.root
        print('a ', root_node_id, type(root_node_id))

        #nodeid = ua.NodeId.from_string(uri)
        # nodeid = 'i=84' Root
        node = self.get_child_node(str(root_node_id))
        print('node : ', node)
        print(self.get_node_attrs(node[0]))
        # node[0] i=85 Objects
        node1 = self.client.get_node(str(node[0])).get_children()

        print(node1, len(node1), type(node1), type(node1[1]), node1[1])
        print(self.get_node_attrs(node1[1]))

        node2 = self.client.get_node(str(node1[1])).get_children()
        print('node2 : ', node2)
        print(self.get_node_attrs(node2[0]))
        node2x = node1[1].get_children()
        print('node2x : ', node2x)
        print(self.get_node_attrs(node2x[1]))
        for node in node2x:
            print(node.get_children_descriptions())
            print(self.get_node_attrs(node))
        # a = 0
        # while a <= 20:
        #     if len(node1) > 0:
        #         node1 = self.client.get_node(str(node1[1])).get_children()
        #         print(node1, len(node1), type(node1))
        #         a += 1

    def get_node_attrs(self, node):
        if not isinstance(node, SyncNode):
            node = self.client.get_node(node)
        attrs = node.read_attributes([ua.AttributeIds.DisplayName, ua.AttributeIds.BrowseName, ua.AttributeIds.NodeId])

        return node, [attr.Value.Value.to_string() for attr in attrs]

    def setup_context_menu_tree(self):
        self.treeView.setContextMenuPolicy(Qt.CustomContextMenu)
        self.treeView.customContextMenuRequested.connect(self._show_context_menu_tree)
        self._contextMenu = QMenu()
        self._contextMenu.addAction(self.actionCopyPath)
        self._contextMenu.addAction(self.actionCopyNodeId)
        self._contextMenu.addSeparator()
        self._contextMenu.addAction(self.actionCall)
        self._contextMenu.addSeparator()

    def _show_context_menu_tree(self, position):
        node = self.tree_ui.get_current_node()
        if node:
            self._contextMenu.exec_(self.treeView.viewport().mapToGlobal(position))

    def addAction(self, action):
        self._contextMenu.addAction(action)

    def load_current_node(self):
        mysettings = self.settings.value("current_node", None)
        if mysettings is None:
            return
        uri = self.addrComboBox.currentText()
        if uri in mysettings:
            nodeid = ua.NodeId.from_string(mysettings[uri])
            node = self.client.get_node(nodeid)
            self.tree_ui.expand_to_node(node)

    def _uri_changed(self, uri):
        self.load_security_settings(uri)

    @trycatchslot
    def show_refs(self, selection):
        if isinstance(selection, QItemSelection):
            if not selection.indexes():  # no selection
                return

        node = self.get_current_node()
        if node:
            self.refs_ui.show_refs(node)

    @trycatchslot
    def show_attrs(self, selection):
        if isinstance(selection, QItemSelection):
            if not selection.indexes():  # no selection
                return

        node = self.get_current_node()
        if node:
            self.attrs_ui.show_attrs(node)

    def load_security_settings(self, uri):
        self.security_mode = None
        self.security_policy = None
        self.certificate_path = None
        self.private_key_path = None

        mysettings = self.settings.value("security_settings", None)
        if mysettings is None:
            return
        if uri in mysettings:
            mode, policy, cert, key = mysettings[uri]
            self.security_mode = mode
            self.security_policy = policy
            self.certificate_path = cert
            self.private_key_path = key

    def save_security_settings(self, uri):
        mysettings = self.settings.value("security_settings", None)
        if mysettings is None:
            mysettings = {}
        mysettings[uri] = [self.security_mode,
                           self.security_policy,
                           self.certificate_path,
                           self.private_key_path]
        self.settings.setValue("security_settings", mysettings)

    def dark_mode(self):
        self.settings.setValue("dark_mode", self.actionDark_Mode.isChecked())

        msg = QMessageBox()
        msg.setIcon(QMessageBox.Information)
        msg.setText("Restart for changes to take effect")
        msg.exec_()

    def subscribe_datachange(self, node, handler):
        if not self._datachange_sub:
            self._datachange_sub = self.client.create_subscription(500, handler)
        handle = self._datachange_sub.subscribe_data_change(node)
        print(' subscription : ', self._datachange_sub, '  , handle : ', handle)
        self._subs_datachange[node.nodeid] = handle
        print(' subscribe_datachange -- _subs_datachange : ', self._subs_datachange)
        return handle

    def unsubscribe_datachange(self, node):
        print(' unsubscribe_datachange1 -- _subs_datachange : ', self._subs_datachange)
        self._datachange_sub.unsubscribe(self._subs_datachange[node.nodeid])
        if node.nodeid in self._subs_datachange:
            del self._subs_datachange[node.nodeid]
        print(' unsubscribe_datachange2 -- _subs_datachange : ', self._subs_datachange)

    def subscribe_events(self, node, handler):
        print(' subscribe_events1 -- _event_sub : ', self._event_sub)
        if not self._event_sub:
            print("subscirbing with handler: ", handler, dir(handler))
            self._event_sub = self.client.create_subscription(500, handler)
            print(' subscribe_events11 -- _event_sub : ', self._event_sub)
        print(' subscribe_events12 -- _event_sub : ', self._event_sub)
        # 기본 이벤트 항목 호출
        # handle = self._event_sub.subscribe_events()
        # limit(setpoint) 와 ackedKnowledge 정보도 포함
        handle = self._event_sub.subscribe_events(evtypes=ua.ObjectIds.LimitAlarmType)
        self._subs_event[node.nodeid] = handle
        print(' subscribe_events2 -- _event_sub : ', self._event_sub)
        print(' subscribe_events2 -- _subs_event : ', self._subs_event)
        return handle

    def unsubscribe_events(self, node):
        self._event_sub.unsubscribe(self._subs_event[node.nodeid])
        if node.nodeid in self._subs_event:
            del self._subs_event[node.nodeid]

    def show_error(self, msg):
        logger.warning("showing error: %s")
        self.statusBar.show()
        self.statusBar.setStyleSheet("QStatusBar { background-color : red; color : black; }")
        self.statusBar.showMessage(str(msg))
        # QTimer.singleShot(1500, self.statusBar.hide)
        QTimer.singleShot(1500, self.statusBar.showMessage(''))


if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = MainWindow()
    window.setGeometry(10, 10, 1200, 800)

    window.show()
    # window.showFullScreen()

    sys.exit(app.exec_())
