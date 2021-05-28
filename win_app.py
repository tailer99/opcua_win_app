import sys

from PyQt5.QtWidgets import *


class MyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # self.setGeometry(100, 200, 300, 200)
        self.setWindowTitle("OPC UA Trans")

        self.btnSearch = QPushButton("시작", self)
        self.btnSearch.move(100, 100)
        

if __name__ == '__main__':

    app = QApplication(sys.argv)
    window = MyWindow()
    window.setGeometry(10, 10, 1200, 800)

    window.show()
    # window.showFullScreen()

    sys.exit(app.exec_())
