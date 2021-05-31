import sys
import logging
from datetime import datetime

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import QtCore, QtGui, QtWidgets
import opcua
from asyncua import ua
from asyncua.sync import Client, SyncNode
from asyncua.tools import endpoint_to_strings

from uawidgets import *
from uawidgets import tree_widget, refs_widget, attrs_widget
from uawidgets.utils import trycatchslot

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setGeometry(100, 200, 300, 200)
        self.setWindowTitle("OPC UA Trans")

        self.setObjectName("MainWindow")
        self.move(100, 50)
        self.resize(922, 879)
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
        self.treeView.selectionModel().selectionChanged.connect(self.show_attrs)

        self.refs_ui = refs_widget.RefsWidget(self.refView)
        self.refs_ui.error.connect(self.show_error)
        self.attrs_ui = attrs_widget.AttrsWidget(self.attrView)
        self.attrs_ui.error.connect(self.show_error)

        # self.datachange_ui = DataChangeUI(self, self.uaclient)
        # self.event_ui = EventUI(self, self.uaclient)
        # self.graph_ui = GraphUI(self, self.uaclient)

        ##############################

        self.client = None

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

    def connect(self):
        endpoint_url = 'opc.tcp://10.178.59.49:7560/System1OPCUAServer'
        self.client = Client(endpoint_url, timeout=2)
        self.client.connect()

    def disconnect(self):
        self.client.disconnect()

    def get_child_node(self, nodeid):
        print(nodeid, type(nodeid), self.client)

        node = self.client.get_node('i=84').get_children()
        print(node)
        return node

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

    @trycatchslot
    def show_attrs(self, selection):
        if isinstance(selection, QItemSelection):
            if not selection.indexes(): # no selection
                return

        node = self.get_current_node()
        if node:
            self.attrs_ui.show_attrs(node)

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
