import asyncio
import configparser
import sys
import os
import logging
import logging.handlers
from datetime import datetime, timedelta

from PyQt5.QtGui import QStandardItem, QStandardItemModel
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5 import QtCore, QtGui, QtWidgets
from asyncua import ua, common, client, sync
from asyncua.sync import Client, SyncNode

from uawidgets import tree_widget, refs_widget, attrs_widget, logger
from uawidgets.utils import trycatchslot

import pymysql
# import send_message

logger = None
t_logger = None
d_logger = None
s_logger = None
e_logger = None
c_logger = None  # only console

gv_sys1_id = 0
gv_user_id = 'EDGE'
# TODO db 접속 여부 확인해서 없으면 db 관련 내용들은 모두 skip 되도록 처리
# TODO db 도 여러가지 사용할 수 있게 모듈 처리

gv_db_conn_info = {'dbServer': 'DEV'}

gv_ini_file_name = 'config.ini'
gv_email_send_yn = 'N'
gv_email_userid = ''
gv_email_passwd = ''
gv_line_send_yn = 'N'
gv_line_group_id = ''
gv_line_access_token = ''

# static 건별 입력 기준
gv_write_interval = 120
# dynamic 전체 건수 작성 기준
gv_dynamic_write_interval = 600

# 로그 파일명
gv_log_folder = 'logs'
gv_main_log_file_name = 'main'
gv_tree_log_file_name = 'tree'
gv_static_log_file_name = 'static'
gv_dynamic_log_file_name = 'dynamic'
gv_event_log_file_name = 'event'
gv_etc_log_file_name = 'etc'
gv_event_subscription_id = 0


class MysqlDBConn:

    def __init__(self, dbServer='DEV'):

        self.read_config(dbServer)

        hostIp = gv_db_conn_info['hostIp']
        port = int(gv_db_conn_info['port'])
        userNm = gv_db_conn_info['userNm']
        passWd = gv_db_conn_info['passWd']
        dbName = gv_db_conn_info['dbName']

        self.conn = pymysql.connect(host=hostIp, port=port, user=userNm, password=passWd,
                                    db=dbName, charset='utf8mb4')

    def read_config(self, dbServer):
        global gv_db_conn_info

        config_file = configparser.ConfigParser()
        current_dir = os.path.abspath(os.path.curdir)
        ini_file = current_dir + '/' + gv_ini_file_name
        if config_file.read(ini_file, encoding='utf-8'):

            if config_file.has_section('DB'):
                if config_file.has_section(dbServer):
                    gv_db_conn_info['dbServer'] = dbServer
                    gv_db_conn_info['hostIp'] = config_file[dbServer]['hostIp']
                    gv_db_conn_info['port'] = config_file[dbServer]['port']
                    gv_db_conn_info['userNm'] = config_file[dbServer]['userNm']
                    gv_db_conn_info['passWd'] = config_file[dbServer]['passWd']
                    gv_db_conn_info['dbName'] = config_file[dbServer]['dbName']
        else:
            logger.warning('!! DB ini file not found!!')


class TlsSMTPHandler(logging.handlers.SMTPHandler):
    def emit(self, record):
        """
        Emit a record.

        Format the record and send it to the specified addressees.
        """
        try:
            import smtplib
            try:
                from email.utils import formatdate
            except ImportError:
                formatdate = self.date_time
            port = self.mailport
            if not port:
                port = smtplib.SMTP_PORT
            smtp = smtplib.SMTP(self.mailhost, port)
            msg = "From: %s\r\nTo: %s\r\nSubject: %s\r\nDate: %s\r\n\r\n%s" % (
                self.fromaddr,
                # string.join(self.toaddrs, ","),
                self.toaddrs,
                self.getSubject(record),
                formatdate(), record)

            if self.username:
                smtp.ehlo()  # for tls add this line
                smtp.starttls()  # for tls add this line
                smtp.ehlo()  # for tls add this line
                smtp.login(self.username, self.password)
            # print('email msg : ', msg)
            smtp.sendmail(self.fromaddr, self.toaddrs, msg)
            smtp.quit()
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


class DataChangeHandler(QObject):
    data_change_fired = pyqtSignal(object, str, str)
    write_change_log_fired = pyqtSignal(object)

    def __init__(self):
        super().__init__()

        self.inserted_data = {}
        self.cur_update_time = datetime.now()
        self.last_update_time = datetime.now()

        self.dynamic_inserted_data = {}
        self.dynamic_cur_update_time = datetime.now()
        self.dynamic_last_update_time = datetime.now()

        self.conn = None
        self.connect_db()

    def connect_db(self):
        try:
            self.conn = MysqlDBConn(gv_db_conn_info['dbServer']).conn
            msg = '### DataChange connected to DB ### ' + gv_db_conn_info['dbServer']
            s_logger.info(msg)
            self.write_change_log_fired.emit(msg)

        except Exception as e:
            msg = 'DataChangeHandler : DB Conn Error -- ' + str(e)
            s_logger.error(msg)
            self.write_change_log_fired.emit(msg)
            sys.exit('finished due to DB Connection Error')

    def datachange_notification(self, node, val, data):
        # print('datachange_notification start ', node, val, data.monitored_item.Value.SourceTimestamp)

        # DB 연결 여부 확인
        self.conn.ping(True)

        if data.monitored_item.Value.SourceTimestamp:
            data_ts = data.monitored_item.Value.SourceTimestamp.strftime('%Y-%m-%d %H:%M:%S')
        elif data.monitored_item.Value.ServerTimestamp:
            data_ts = data.monitored_item.Value.ServerTimestamp.isoformat().strftime('%Y-%m-%d %H:%M:%S')
        else:
            data_ts = datetime.now().isoformat().strftime('%Y-%m-%d %H:%M:%S')

        if isinstance(val, ua.DynamicDataType):
            # print('waveform')
            # print(' Extension : ', val.MeasurementId, '  ', val.NumberOfSamples, val)
            self.insert_dynamic_data(node, val, data_ts)

        else:
            # print('trend', node, data)
            self.insert_static_data(node, val, data_ts)

        self.data_change_fired.emit(node, str(val), data_ts)

    # insert WAVEFORM table
    def insert_dynamic_data(self, node, val, data_ts):

        with self.conn.cursor() as curs:
            try:

                # 로그에 10분간의 건수 작성
                self.dynamic_cur_update_time = datetime.now()

                # 10분에 1번 건수 쓰기
                # print(self.dynamic_cur_update_time - self.dynamic_last_update_time,
                #       timedelta(seconds=gv_dynamic_write_interval), val.MeasurementId)
                if self.dynamic_cur_update_time - self.dynamic_last_update_time >= \
                        timedelta(seconds=gv_dynamic_write_interval):
                    write_cnt = len(self.dynamic_inserted_data)

                    msg = ' ### dynamic insert count ' + str(write_cnt)
                    d_logger.info(msg)
                    self.write_change_log_fired.emit(msg)

                    # Item List 초기화
                    self.dynamic_inserted_data.clear()
                    self.dynamic_last_update_time = self.dynamic_cur_update_time

                # 건별 데이터 입력
                crt_wk = int(datetime.now().strftime('%W'))

                measurement_id, point_id, company_id, measurement_name = \
                    self.search_item_id(curs, gv_sys1_id, node)
                # print('measurement_id, point_id, company_id : ', measurement_id, point_id, company_id)

                sql = "insert ignore into SDA_WAVEFORM(CRT_WK, SYS1_ID, POINT_ID, MEASUREMENT_ID, " \
                      "UTC_TIME_STAMP, NO_OF_DATA, C_DATA, UNIT_NAME, SUB_UNIT_NAME, RPM," \
                      "FMAX, FMAX_UNIT_NAME, SAMPLING_PERIOD, SAMPLING_PERIOD_UNIT_NAME, CREATE_DT) " \
                      "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
                record = (crt_wk, gv_sys1_id, point_id, measurement_id,
                          val.UTCTimestamp.strftime('%Y-%m-%d %H:%M:%S'), val.NumberOfSamples, str(val.Data),
                          val.UnitName, val.SubunitName, int(val.RPM),
                          val.Fmax, val.FmaxUnitName, round(val.SamplingPeriod, 18), val.SamplingPeriodUnitName)
                # print('input data :', record)

                curs.execute(sql, record)
                self.conn.commit()

                self.dynamic_inserted_data[str(node.nodeid)] = len(self.dynamic_inserted_data) + 1

                # 건별로 파일에 작성
                # print('dynamic insert ok', datetime.now(), measurement_id, measurement_name)
                msg = ' dynamic data insert : ' + str(measurement_id) + ' ' + measurement_name + data_ts
                d_logger.info(msg)
                # self.write_change_log_fired.emit(msg)

            except Exception as e:
                msg = ' dynamic data INSERT error occured ' + str(e)
                d_logger.info(msg)
                self.write_change_log_fired.emit(msg)

    # insert TREND table
    def insert_static_data(self, node, val, data_ts):

        with self.conn.cursor() as curs:
            try:
                aggr_time_cd = '2M'

                self.cur_update_time = datetime.now()
                # 2분에 1번 쓰기
                # 입력시간 조건이 되었는지와 입력된 건인지 비교하여 데이터 INSERT 수행
                if self.cur_update_time - self.last_update_time >= timedelta(seconds=gv_write_interval):
                    write_cnt = len(self.inserted_data)

                    # print(datetime.now().strftime('%Y%m%d%H%M%S') + ' static insert count ' + str(write_cnt))
                    msg = ' ### static insert count ' + str(write_cnt)
                    s_logger.info(msg)
                    self.write_change_log_fired.emit(msg)

                    # Item List 초기화
                    self.inserted_data.clear()
                    self.last_update_time = self.cur_update_time

                if str(node.nodeid) in self.inserted_data:
                    pass
                else:
                    measurement_id, point_id, company_id, measurement_name = \
                        self.search_item_id(curs, gv_sys1_id, node)
                    # print('measurement_id, point_id, company_id : ', measurement_id, point_id, company_id)

                    sql = "insert ignore into SDA_TREND(CRT_MONTH, SYS1_ID, POINT_ID, MEASUREMENT_ID, " \
                          "AGGR_TIME_CD, SOURCE_DT, VAL, VAL_TYPE, CREATE_DT) " \
                          "values (%s, %s, %s, %s, %s, %s, round(%s,3), %s, NOW())"
                    record = (datetime.now().month, gv_sys1_id, point_id, measurement_id,
                              aggr_time_cd, data_ts, val, 2)
                    curs.execute(sql, record)
                    self.conn.commit()

                    self.inserted_data[str(node.nodeid)] = len(self.inserted_data) + 1

                    # print('static insert ok', datetime.now(), measurement_id, measurement_name)
                    # msg = ' static data insert : ' + str(measurement_id) + ' ' + measurement_name + data_ts
                    # s_logger.info(msg)
                    # self.write_change_log_fired.emit(msg)

            except Exception as e:
                msg = ' static data INSERT error occured ' + str(e)
                s_logger.info(msg)
                self.write_change_log_fired.emit(msg)

    # using NodeID find ITEM_ID
    def search_item_id(self, curs, sys1_id, node_id):

        # search ITEM ID
        sql = "select ITEM_ID, P_ITEM_ID, L1_ITEM_ID, ITEM_NAME " \
              "from SDA_TREE where SYS1_ID = %s and NODE_ID = %s and GUBUN = 'S'"
        record = (sys1_id, node_id)
        curs.execute(sql, record)
        item_id, p_item_id, l1_item_id, item_name = curs.fetchone()

        return item_id, p_item_id, l1_item_id, item_name


class DataChangeUI(object):

    def __init__(self, window, client):
        self.window = window
        self.client = client
        self._handler = DataChangeHandler()
        self._subscribed_nodes = []
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["DisplayName", "Value", "Timestamp"])

        self.window.subView.setModel(self.model)
        # self.window.subView.horizontalHeader().setSectionResizeMode(1)

        self.window.actionSubscribeDataChange.triggered.connect(self._subscribe)
        self.window.actionUnsubscribeDataChange.triggered.connect(self._unsubscribe)

        # populate contextual menu
        self.window.addAction(self.window.actionSubscribeDataChange)
        self.window.addAction(self.window.actionUnsubscribeDataChange)

        # handle subscriptions
        self._handler.data_change_fired.connect(self._update_subscription_model, type=Qt.QueuedConnection)
        self._handler.write_change_log_fired.connect(self._write_change_log_model, type=Qt.QueuedConnection)

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
            # logger.warning("already subscribed to node: %s ", node)
            return

        # TODO 컬럼 사이즈 키우기
        text = node.read_display_name().Text
        row = [QStandardItem(text), QStandardItem("No Data yet"), QStandardItem("")]
        row[0].setData(node)
        self.model.appendRow(row)

        self._subscribed_nodes.append(node)
        self.window.subDockWidget.raise_()

        try:
            self.window.subscribe_datachange(node, self._handler)
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

        if node in self._subscribed_nodes:
            self.window.unsubscribe_datachange(node)
            self._subscribed_nodes.remove(node)

            i = 0
            while self.model.item(i):
                item = self.model.item(i)
                if item.data() == node:
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

    @trycatchslot
    def _write_change_log_model(self, msg):
        # print('log message :', msg)
        self.window.logTextEdit.append(msg)


class EventHandler(QObject):
    event_fired = pyqtSignal(object)
    config_change_event_fired = pyqtSignal(object)
    write_event_log_fired = pyqtSignal(object)
    email_stop_yn = 'N'
    line_stop_yn = 'N'

    def __init__(self):
        super().__init__()

        self.conn = None
        self.connect_db()
        self.read_config()

        # if gv_line_send_yn == 'Y':
        #     send_message.init_line_message()

    def connect_db(self):
        try:
            self.conn = MysqlDBConn(gv_db_conn_info['dbServer']).conn
            msg = '### Event connected to DB ### ' + gv_db_conn_info['dbServer']
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)

        except Exception as e:
            msg = 'EventHandler : DB Conn Error -- ' + str(e)
            e_logger.error(msg)
            self.write_event_log_fired.emit(msg)
            sys.exit('finished due to DB Connection Error')

    def status_change_notification(self, status):
        print(' status_change_notification start ', type(status), status)

    def event_notification(self, event):
        e_logger.info(' event_notification start ' + str(event))
        # print(' event info :  EventType - ', event.EventType, type(event.EventType),
        #       ' , Severity - ', event.Severity, type(event.Severity),
        #       ' , Message - ', event.Message.Text, type(event.Message.Text))

        msg = event.SourceName + ' Severity - ' + str(event.Severity) + ' , Message - ' + event.Message.Text
        self.write_event_log_fired.emit(' event_notification start : ' + msg)

        if str(event.EventType) == "i=2789":
            msg = ' refresh Required : ' + event.Message.Text    # Address space and nodes updated.
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)

            # call Condition Refresh function
            self.config_change_event_fired.emit(event)

        elif str(event.EventType) == "i=2787":
            msg = ' refresh started : ' + event.Message.Text   # Condition refresh started
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)
            # TODO delete comment
            self.email_stop_yn = 'Y'
            # self.line_stop_yn = 'Y'

            # Refresh 될 때 기존 event 중 active 인거 모두 inactive 로 바꿔준다
            self.clean_events()

        elif str(event.EventType) == "i=2788":
            msg = ' refresh complete : ' + event.Message.Text   # Condition refresh completed
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)
            self.email_stop_yn = 'N'
            self.line_stop_yn = 'N'

        elif event.Severity == 100:
            msg = ' server event occurred : ' + event.Message.Text
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)

        # 알람 등록 처리
        elif event.ActiveState.Text == 'Active':

            search_state = self.search_event_node_id(event)[0]
            # e_logger.info('check search_state : ' + str(search_state))

            # if not found
            if search_state == 0:
                # e_logger.info(' not found ')
                self.insert_event_data(event)

            # active state found
            elif search_state == 1:
                msg = '=== already active alarm exists, skip event : ' + str(event)
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

            # inactive state found
            elif search_state == -1:
                # e_logger.info(' exists, but inactive ')
                self.update_event_data(event)

            else:
                msg = '=== active other case occurred : ' + str(event)
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

        # 알람 해지 처리
        elif event.ActiveState.Text == 'Inactive':

            search_state = self.search_event_node_id(event)[0]
            # e_logger.info('check search_state : ' + str(search_state))

            # if not found
            if search_state == 0:
                msg = '!! Event inactive, but not found !!'
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

                self.insert_event_data(event)

            # active state found
            elif search_state == 1:
                # e_logger.info(' exists, active ')
                self.update_event_data(event)

            # inactive state found
            elif search_state == -1:
                msg = '=== already inactive alarm exists, skip event : ' + str(event)
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

            else:
                msg = '=== inactive other case occurred : ' + str(event)
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

        else:
            msg = 'other case : ' + str(event)
            e_logger.info(msg)
            self.write_event_log_fired.emit(msg)

    # 모든 알람을 inactive 처리하고 새로 받은 알람들만 active 로 등록
    def clean_events(self):

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                left_dt = ''
                is_active = 0

                sql = "update SDA_EVENT " \
                      "set    UTC_LEFT_DT = %s, IS_ACTIVE = %s, " \
                      "       UPDATE_ID = 'CLEAR', UPDATE_DT = NOW() " \
                      "where  SYS1_ID = %s " \
                      "and    IS_ACTIVE = 1 "

                record = (left_dt, is_active, int(gv_sys1_id))

                # print(sql, '    ', record)
                treat_cnt = curs.execute(sql, record)

                msg = '기존 알람 inactive 건수 : ' + str(treat_cnt)
                e_logger.info(msg)
                self.write_event_log_fired.emit(msg)

                self.conn.commit()

            except Exception as e:
                msg = 'EVENT DATA CLEAR error occurred : ' + str(e)
                e_logger.error(msg)
                self.write_event_log_fired.emit(msg)

    def insert_event_data(self, event):

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                condition_id = str(event.Value)
                node_id = str(event.SourceNode)

                measurement_id, point_id, company_id = self.search_item_id(curs, gv_sys1_id, event.SourceNode)
                # print('measurement_id, point_id, company_id : ', measurement_id, point_id, company_id)

                alarm_level = event.ConditionName[-1]

                if event.ActiveState.Text == 'Active':
                    utc_entered_dt = event.Time.strftime('%Y-%m-%d %H:%M:%S')
                    utc_left_dt = ''
                    is_active = 1
                elif event.ActiveState.Text == 'Inactive':
                    utc_entered_dt = event.Time.strftime('%Y-%m-%d %H:%M:%S')
                    utc_left_dt = event.Time.strftime('%Y-%m-%d %H:%M:%S')
                    is_active = 0
                else:
                    utc_entered_dt = ''
                    utc_left_dt = ''
                    is_active = 2

                measurement = event.SourceName[event.SourceName.rfind('>') + 1:]
                machine_temp = event.SourceName[:event.SourceName.rfind('>')]
                point = machine_temp[machine_temp.rfind('>') + 1:]
                machine = machine_temp[:machine_temp.rfind('>')]

                if not isinstance(event.TriggerValue, float):
                    trigger_value = 0
                else:
                    trigger_value = round(event.TriggerValue, 3)

                utc_receive_dt = event.ReceiveTime.strftime('%Y-%m-%d %H:%M:%S')

                if not isinstance(event.HighHighLimit, float):
                    over_highhigh_value = 0
                else:
                    over_highhigh_value = round(event.HighHighLimit, 3)

                if not isinstance(event.BaseHighHighLimit, float):
                    under_highhigh_value = 0
                else:
                    under_highhigh_value = round(event.BaseHighHighLimit, 3)

                if not isinstance(event.HighLimit, float):
                    over_high_value = 0
                else:
                    over_high_value = round(event.HighLimit, 3)

                if not isinstance(event.BaseHighLimit, float):
                    under_high_value = 0
                else:
                    under_high_value = round(event.BaseHighLimit, 3)

                if not isinstance(event.LowLimit, float):
                    over_low_value = 0
                else:
                    over_low_value = round(event.LowLimit, 3)

                if not isinstance(event.BaseLowLimit, float):
                    under_low_value = 0
                else:
                    under_low_value = round(event.BaseLowLimit, 3)

                if not isinstance(event.LowLowLimit, float):
                    over_lowlow_value = 0
                else:
                    over_lowlow_value = round(event.LowLowLimit, 3)

                if not isinstance(event.BaseLowLowLimit, float):
                    under_lowlow_value = 0
                else:
                    under_lowlow_value = round(event.BaseLowLowLimit, 3)

                sql = "insert into SDA_EVENT(SYS1_ID, CONDITION_ID, POINT_ID, MEASUREMENT_ID, " \
                      "ALARM_LEVEL, UTC_ENTERED_DT, UTC_LEFT_DT, IS_ACTIVE, MACHINE, POINT, MEASUREMENT, " \
                      "TRIGGER_VALUE, UTC_RECEIVE_DT, SMS_SEND_YN, NODE_ID, " \
                      "OVER_HIGHHIGH_VALUE, UNDER_HIGHHIGH_VALUE, OVER_HIGH_VALUE, UNDER_HIGH_VALUE, " \
                      "OVER_LOW_VALUE, UNDER_LOW_VALUE, OVER_LOWLOW_VALUE, UNDER_LOWLOW_VALUE, " \
                      "CREATE_ID, CREATE_DT) " \
                      "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, " \
                      " round(%s,3), %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())"
                record = (
                    gv_sys1_id, condition_id, point_id, measurement_id, alarm_level, utc_entered_dt, utc_left_dt, is_active,
                    machine, point, measurement, trigger_value, utc_receive_dt, 'N', node_id,
                    over_highhigh_value, under_highhigh_value, over_high_value, under_high_value,
                    over_low_value, under_low_value, over_lowlow_value, under_lowlow_value,
                    gv_user_id)

                # print(sql, '    ', record)
                curs.execute(sql, record)

                self.conn.commit()

                self.event_fired.emit(event)

                # email 발송 여부 확인후 발송처리
                if gv_email_send_yn == 'Y' and self.email_stop_yn == 'N':
                    # TODO addr, msg 보강
                    subject = 'Alarm Occured'
                    to_addr = ['tailer9999@gmail.com', 'tailer99@sk.com']
                    msg = event.SourceName + ' Severity - ' + str(event.Severity) + ' , Message - ' + event.Message.Text
                    self.send_email(subject, to_addr, msg)

                # # line message 발송 여부 확인후 발송처리
                # if gv_line_send_yn == 'Y' and self.line_stop_yn == 'N':
                #     # TODO addr, msg 보강
                #     to_id = gv_line_group_id
                #     msg = event.SourceName + ' Severity - ' + str(event.Severity) + ' , Message - ' + event.Message.Text
                #     send_message.send_line_message(to_id, msg)

            except Exception as e:
                msg = 'EVENT DATA INSERT error occurred : ' + str(e)
                e_logger.error(msg)
                self.write_event_log_fired.emit(msg)

    def update_event_data(self, event):

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                condition_id = str(event.Value)

                if event.ActiveState.Text == 'Active':
                    utc_left_dt = ''
                    is_active = 1
                elif event.ActiveState.Text == 'Inactive':
                    utc_left_dt = event.Time.strftime('%Y-%m-%d %H:%M:%S')
                    is_active = 0
                else:
                    utc_left_dt = ''
                    is_active = 2

                sql = "update SDA_EVENT " \
                      "set    UTC_LEFT_DT = %s, IS_ACTIVE = %s, " \
                      "       UPDATE_ID = %s, UPDATE_DT = NOW() " \
                      "where  SYS1_ID = %s " \
                      "and    CONDITION_ID = %s "
                record = (utc_left_dt, is_active, gv_user_id, gv_sys1_id, condition_id)

                # e_logger.error(sql + '    ' + str(record))
                curs.execute(sql, record)

                self.conn.commit()

                self.event_fired.emit(event)

                # email 발송 여부 확인후 발송처리
                if gv_email_send_yn == 'Y' and self.email_stop_yn == 'N':
                    # TODO addr, msg 보강
                    subject = 'Alarm Occured'
                    to_addr = ['tailer9999@gmail.com', 'tailer99@sk.com']
                    msg = event.SourceName + ' Severity - ' + str(event.Severity) + ' , Message - ' + event.Message.Text
                    self.send_email(subject, to_addr, msg)

                # # line message 발송 여부 확인후 발송처리
                # if gv_line_send_yn == 'Y' and self.line_stop_yn == 'N':
                #     # TODO addr, msg 보강
                #     to_id = gv_line_group_id
                #     msg = event.SourceName + ' Severity - ' + str(
                #         event.Severity) + ' , Message - ' + event.Message.Text
                #     send_message.send_line_message(to_id, msg)

            except Exception as e:
                msg = 'EVENT DATA UPDATE error occurred : ' + str(e)
                e_logger.error(msg)
                self.write_event_log_fired.emit(msg)

    # using NodeID find ITEM_ID
    def search_item_id(self, curs, sys1_id, node_id):

        # search ITEM ID
        sql = "select ITEM_ID, P_ITEM_ID, L1_ITEM_ID from SDA_TREE " \
              "where SYS1_ID = %s and NODE_ID = %s and GUBUN = 'S'"
        record = (sys1_id, node_id)
        curs.execute(sql, record)
        item_id, p_item_id, l1_item_id = curs.fetchone()

        return item_id, p_item_id, l1_item_id

    # using endpoint_url find SYS1_ID
    def search_event_node_id(self, event):

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                sql = "select ifnull(max(case when IS_ACTIVE = 1 then 1 else -1 end),0) " \
                      "from SDA_EVENT " \
                      "where SYS1_ID = %s " \
                      "and CONDITION_ID = %s "
                record = (int(gv_sys1_id), str(event.Value))

                # print(sql, '    ', record)
                curs.execute(sql, record)
                active_state = curs.fetchone()

                return active_state

            except Exception as e:
                msg = 'EVENT DATA FIND error occurred : ' + str(e)
                e_logger.error(msg)
                self.write_event_log_fired.emit(msg)

    def read_config(self):
        global gv_email_send_yn
        global gv_email_userid
        global gv_email_passwd
        global gv_line_send_yn
        global gv_line_group_id
        global gv_line_access_token

        config_file = configparser.ConfigParser()
        if config_file.read(gv_ini_file_name, encoding='utf-8'):

            if config_file.has_section('EMAIL'):
                gv_email_send_yn = config_file['EMAIL']['email_send_yn']
                gv_email_userid = config_file['EMAIL']['userId']
                gv_email_passwd = config_file['EMAIL']['passWd']

            if config_file.has_section('LINE'):
                gv_line_send_yn = config_file['LINE']['line_send_yn']
                gv_line_group_id = config_file['LINE']['groupId']
                gv_line_access_token = config_file['LINE']['access_token']

        else:
            logger.warning('!! ini file not found!!')

    def send_email(self, subject, to_addr, msg):
        gmail_sender = TlsSMTPHandler(('smtp.gmail.com', 587), 'ppdm@ppdm.io', to_addr,
                                      subject, (gv_email_userid, gv_email_passwd))
        gmail_sender.emit(msg)


class EventUI(object):

    def __init__(self, window, uaclient):
        self.window = window
        self.uaclient = uaclient
        self._handler = EventHandler()
        self._subscribed_nodes = []
        self.model = QStandardItemModel()
        self.model.setHorizontalHeaderLabels(["DisplayName", "Severity", "Message", "TriggerValue", "Timestamp"])

        self.window.eventView.setModel(self.model)
        self.window.actionSubscribeEvent.triggered.connect(self._subscribe)
        self.window.actionUnsubscribeEvents.triggered.connect(self._unsubscribe)
        # context menu
        self.window.addAction(self.window.actionSubscribeEvent)
        self.window.addAction(self.window.actionUnsubscribeEvents)
        self.window.addAction(self.window.actionAddToGraph)
        self._handler.event_fired.connect(self._update_event_model, type=Qt.QueuedConnection)
        self._handler.config_change_event_fired.connect(self._reconnect_server, type=Qt.QueuedConnection)

        # accept drops
        self.model.canDropMimeData = self.canDropMimeData
        self.model.dropMimeData = self.dropMimeData

        self._handler.write_event_log_fired.connect(self._write_event_log_model, type=Qt.QueuedConnection)

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
        if not node:
            node = self.window.get_current_node()
            if node is None:
                return
        if node in self._subscribed_nodes:
            msg = "already subscribed to event for node: %s" + str(node)
            logger.info(msg)
            self.write_event_log_fired.emit(msg)
            return

        self.window.eventDockWidget.raise_()
        try:
            self.window.subscribe_events(node, self._handler)
        except Exception as ex:
            self.window.show_error(ex)
            raise
        else:
            self._subscribed_nodes.append(node)

    @trycatchslot
    def _unsubscribe(self):
        # node = self.window.get_current_node()
        node = ''
        if len(self._subscribed_nodes) > 0:
            # self._subscribed_nodes.remove(node)
            self._subscribed_nodes.clear()
            self.window.unsubscribe_events(node)

    @trycatchslot
    def _update_event_model(self, event):
        # print('event :', event)

        row = [QStandardItem(str(event.SourceName)), QStandardItem(str(event.Severity)),
               QStandardItem(event.Message.Text), QStandardItem(str(round(event.TriggerValue,3))),
               QStandardItem(str(event.Time))]
        self.model.appendRow(row)

    @trycatchslot
    def _write_event_log_model(self, msg):
        # print('log message :', msg)
        self.window.logTextEdit.append(msg)

    @trycatchslot
    def _reconnect_server(self, event):
        self.window.reconnect()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # ### TODO DELETE mail test
        # subject = 'Alarm Occured'
        # to_addr = ['tailer9999@gmail.com']
        # self.send_email(subject, to_addr, 'Mail Test')
        # ###

        global logger
        logger = self.make_logger("main", "main")
        logger.info('### main process started ###')

        global t_logger
        t_logger = self.make_logger("tree", "tree")
        global s_logger
        s_logger = self.make_logger("static", "static")
        global d_logger
        d_logger = self.make_logger("dynamic", "dynamic")
        global e_logger
        e_logger = self.make_logger("event", "event")

        self.setGeometry(100, 300, 300, 200)
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
        self.attrDockWidget.setMinimumSize(QtCore.QSize(500, 300))

        self.attrDockWidgetContents = QtWidgets.QWidget()
        self.attrDockWidgetContents.setObjectName("attrDockWidgetContents")
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        # sizePolicy.setHeightForWidth(self.attrDockWidgetContents.sizePolicy().hasHeightForWidth())
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
        sizePolicy = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.eventDockWidgetContents.sizePolicy().hasHeightForWidth())
        self.eventDockWidgetContents.setSizePolicy(sizePolicy)

        self.gridEventLayout = QtWidgets.QGridLayout(self.eventDockWidgetContents)
        self.gridEventLayout.setObjectName("gridEventLayout")
        self.gridEventLayout.setContentsMargins(11, 11, 11, 11)
        self.gridEventLayout.setSpacing(6)

        self.eventView = QtWidgets.QTableView(self.eventDockWidgetContents)
        self.eventView.setObjectName("eventView")
        self.eventView.setAcceptDrops(True)
        self.eventView.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.eventView.setDragDropMode(QtWidgets.QAbstractItemView.DropOnly)
        self.eventView.setSizeAdjustPolicy(QtWidgets.QAbstractScrollArea.AdjustToContents)
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

        #############################
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

        # tabify some docks
        self.tabifyDockWidget(self.attrDockWidget, self.eventDockWidget)
        self.tabifyDockWidget(self.refDockWidget, self.subDockWidget)

        #############################
        #############################

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

        #################################################
        #################################################

        # setup QSettings for application and get a settings object
        QCoreApplication.setOrganizationName("SKCC")
        QCoreApplication.setApplicationName("OpcUaClient")
        self.settings = QSettings()

        self.conn = None
        # DB connect
        self.connect_db()

        # read System1 list
        address_list = self.read_sys1_list()

        self._address_list = self.settings.value("address_list", address_list)
        self._address_list_max_count = int(self.settings.value("address_list_max_count", 5))
        self.addrComboBox.addItems(self._address_list)

        # TODO 동작 안함
        self.addrComboBox.currentTextChanged.connect(self._uri_changed)
        self._uri_changed(self.addrComboBox.currentText())  # force update for current value at startup

        # TODO 동작 안함
        # print(int(self.settings.value("main_window_width", 1000)), int(self.settings.value("main_window_height", 800)))
        self.resize(int(self.settings.value("main_window_width", 1200)),
                    int(self.settings.value("main_window_height", 900)))
        data = self.settings.value("main_window_state", None)
        if data:
            self.restoreState(data)

        ##########################################

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

        self.datachange_ui = None
        self.event_ui = None

        self.treeList = []
        self.level = 0
        self.type_def = []
        self.node_class_def = []
        self.itemSetPointList = []
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

        self.actionConnect.setText(_translate("MainWindow", "&Connect"))
        self.actionDisconnect.setText(_translate("MainWindow", "&Disconnect"))
        self.actionDisconnect.setToolTip(_translate("MainWindow", "Disconnect from server"))
        self.actionSubscribeDataChange.setText(_translate("MainWindow", "&Subscribe to data change"))
        self.actionSubscribeDataChange.setToolTip(
            _translate("MainWindow", "Subscribe to data change from selected node"))
        self.actionUnsubscribeDataChange.setText(_translate("MainWindow", "&Unsubscribe to DataChange"))
        self.actionUnsubscribeDataChange.setToolTip(
            _translate("MainWindow", "Unsubscribe to DataChange for current node"))
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

    # TODO DELETE mail test 용 주석 처리
    # def read_config(self):
    #     global gv_email_send_yn
    #     global gv_email_userid
    #     global gv_email_passwd
    #
    #     config_file = configparser.ConfigParser()
    #     if config_file.read(gv_ini_file_name, encoding='utf-8'):
    #
    #         if config_file.has_section('EMAIL'):
    #             gv_email_send_yn = config_file['EMAIL']['email_send_yn']
    #             gv_email_userid = config_file['EMAIL']['userId']
    #             gv_email_passwd = config_file['EMAIL']['passWd']
    #     else:
    #         logger.warning('!! ini file not found!!')
    #
    # def send_email(self, subject, to_addr, msg):
    #     self.read_config()
    #     gmail_sender = TlsSMTPHandler(('smtp.gmail.com', 587), 'ppdm@ppdm.io', to_addr,
    #                                   subject, (gv_email_userid, gv_email_passwd))
    #     gmail_sender.emit(msg)

    def connect_db(self):

        # check EDGE DB connection
        try:
            self.conn = MysqlDBConn(gv_db_conn_info['dbServer']).conn
            db_info = gv_db_conn_info['dbServer'] + ' ( ' + gv_db_conn_info['hostIp'] + ':' + \
                      gv_db_conn_info['port'] + ' )'
            logger.info('### connected to DB : ' + db_info)
            self.logTextEdit.append('### connected to DB : ' + db_info)

        except Exception as e:
            # print('MainWindow : DB Conn Error -- ', e)
            msg = 'MainWindow : DB Conn Error -- ' + str(e)
            logger.error(msg)
            self.logTextEdit.append(msg)
            sys.exit('finished due to DB Connection Error')

    def read_sys1_list(self):

        sys1_address_list = []

        # search sys1_address
        with self.conn.cursor() as curs:
            try:
                sql = "select ENDPOINT_URL from SDA_SYS1_LIST where USE_YN = 'Y' order by CREATE_DT desc"
                curs.execute(sql)
                address_list = curs.fetchall()
                # print(address_list)
                for address in address_list:
                    sys1_address_list.append(address[0])

            except Exception as e:
                # print('search sys1 endpoint url error occurred : ', e)
                msg = 'search sys1 endpoint url error occurred' + str(e)
                logger.error(msg)
                self.logTextEdit.append(msg)

        return sys1_address_list

    @trycatchslot
    def connect(self):
        # DB 연결 여부 확인
        self.conn.ping(True)

        # connect System1 Server
        endpoint_url = self.addrComboBox.currentText()
        endpoint_url = endpoint_url.strip()
        logger.info('### connecting to System1 ( ' + endpoint_url + ' )')

        try:
            global gv_sys1_id

            with self.conn.cursor() as curs:
                try:
                    gv_sys1_id = self.search_sys1_id(curs, endpoint_url)

                except Exception as e:
                    msg = 'search System1 id error occurred : ' + str(e)
                    logger.error(msg)
                    self.logTextEdit.append(msg)

            self.client = Client(endpoint_url)
            self.client.connect()

            msg = '### connected to System1 ( ' + endpoint_url + ' )'
            logger.info(msg)
            self.logTextEdit.append(msg)

            # client 연결 후 초기화 시킴
            self.datachange_ui = DataChangeUI(self, self.client)
            self.event_ui = EventUI(self, self.client)

        except Exception as e:
            msg = 'System1 Connection Error occurred' + str(e)
            logger.error(msg)
            self.logTextEdit.append(msg)
            raise

        self._update_address_list(endpoint_url)

        # ExtensionObject 의 DynamicDataType 정의 불러오기
        self.client.load_type_definitions()
        # self.client.load_enums()
        # print('start : ', datetime.now())
        self.retrieve_tree()
        # print('end : ', datetime.now())

        # insert tree item to db
        self.insert_tree_items()

        # insert item setpoint to db
        self.insert_item_setpoint()

        # subscribe items
        self.subscribe_all_items()

        # subscribe events
        self.subscribe_all_events()

    # Tree 항목들을 조회후 펼치기
    def retrieve_tree(self):

        root_node = self.client.nodes.root
        self.tree_ui.set_root_node(self.client.nodes.root)
        # print('root_node_attr : ', type(root_node), self.get_node_attrs(root_node))

        # 정렬순서 초기값
        disp_ord = ''

        descs = root_node.get_children_descriptions()
        # print('descs : ', descs)
        descs.sort(key=lambda x: x.BrowseName)
        for node in descs:
            if node.DisplayName.Text == "Objects":
                # print(type(node), type(node.NodeId), node.NodeId)
                c_descs = self.client.get_node(node.NodeId).get_children_descriptions()
                node_ref = self.client.get_node(node.NodeId).get_references()
                # print('c_descs : ', c_descs)
                # print('node_ref : ', len(node_ref), node_ref)

                for c_node in node_ref:
                    # print(type(c_node.ReferenceTypeId), c_node.ReferenceTypeId, '  ', c_node)
                    if c_node.DisplayName.Text == "Server":
                        pass
                    elif not c_node.IsForward:
                        # print('parents : ', c_node.DisplayName.Text, ua.object_ids.ObjectIdNames[c_node.TypeDefinition.Identifier])
                        pass
                    elif str(c_node.ReferenceTypeId) == 'i=40':
                        pass
                    else:
                        root_node = self.client.get_node(c_node.NodeId)

                        # tree 에 저장할 값 설정
                        item_type = ua.object_ids.ObjectIdNames[c_node.TypeDefinition.Identifier]
                        nodeId = c_node.NodeId.__str__()
                        item_name = c_node.DisplayName.Text
                        gubun = ''
                        p_nodeId = ''
                        # print('folder insert : ', item_type, nodeId, item_name, self.level, disp_ord, gubun)
                        self.treeList.append([item_type, nodeId, item_name, self.level, disp_ord, gubun, p_nodeId])

        self.tree_ui.set_root_node(root_node)
        self.treeView.setFocus()
        self.treeView.expandToDepth(0)

        child_node = root_node.get_children_descriptions()
        # print('ROOT CHILD desc : ', len(child_node), child_node)

        for node in child_node[:2]:
            t_logger.info(node.DisplayName.Text)
            if 'Devices' in node.DisplayName.Text:
                continue
                # gubun = 'D'
                # # Machines 만 하위 item 처리함
                # self.get_child_node2([str(node.NodeId)], gubun, self.level + 1, disp_ord, nodeId)
            else:
                gubun = 'M'
                self.get_child_node2([str(node.NodeId)], gubun, self.level + 1, disp_ord, nodeId)

        # treeview 의 아이템들 사이즈에 맞게 확장
        self.treeView.resizeColumnToContents(0)
        # self.treeView.resizeColumnToContents(1)

    # Hierachy 정보 insert
    def insert_tree_items(self):

        msg = '\n################################################\n' \
              'START TREE DATA COLLECTION (' + datetime.now().strftime('%Y%m%d %H%M%S') + ') \n' \
              '################################################\n'
        t_logger.info(msg)
        self.logTextEdit.append(msg)

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                sql = 'delete from SDA_TREE where SYS1_ID = %s'
                curs.execute(sql, gv_sys1_id)
                self.conn.commit()

            except Exception as e:
                # print('TREE DATA DELETE error occured : ', e)
                msg = 'TREE DATA DELETE error occured : ', str(e)
                t_logger.error(msg)
                self.logTextEdit.append(msg)

        l1_item_id = 0
        l2_item_id = 0

        for item in self.treeList:
            # print(item)
            t_logger.info(str(item))

            with self.conn.cursor() as curs:
                try:

                    item_class = item[0]
                    node_id = item[1]
                    item_name = item[2]
                    item_level = item[3]
                    display_ord = item[4]

                    item_id = self.search_item_id(curs, gv_sys1_id, node_id, item_name, item_class)[0]
                    item_type = self.search_item_type(curs, gv_sys1_id, item_name, item_class)[0]

                    if item_level == 2:
                        l1_item_id = item_id
                        l2_item_id = 0
                    if item_level == 3:
                        l2_item_id = item_id

                    p_node_id = item[6]

                    if item_type == 'sensor':
                        gubun = 'S'
                    else:
                        gubun = item[5]

                    sql = "insert ignore into SDA_TREE(ITEM_ID, ITEM_NAME, ITEM_TYPE, ITEM_LEVEL, P_ITEM_ID, " \
                          "       DISPLAY_ORD, L1_ITEM_ID, L2_ITEM_ID, SYS1_ID, NODE_ID, GUBUN, CREATE_DT) " \
                          "SELECT %s, %s, %s, %s, " \
                          "       ifnull((SELECT ITEM_ID FROM SDA_TREE WHERE SYS1_ID = %s AND NODE_ID = %s AND gubun = %s),0), " \
                          "       %s, %s, %s, %s, %s, %s, NOW()"
                    record = (item_id, item_name, item_type, item_level, gv_sys1_id, p_node_id, item[5],
                              display_ord, l1_item_id, l2_item_id, gv_sys1_id, node_id, gubun)
                    curs.execute(sql, record)
                    self.conn.commit()

                except Exception as e:
                    msg = 'TREE DATA INSERT error occured : ', str(e)
                    t_logger.error(msg)
                    self.logTextEdit.append(msg)

    # SetPoint 정보 insert
    def insert_item_setpoint(self):

        # DB 연결 여부 확인
        self.conn.ping(True)

        with self.conn.cursor() as curs:
            try:
                sql = 'delete from SDA_ITEM_SET_POINT where SYS1_ID = %s'
                curs.execute(sql, gv_sys1_id)
                self.conn.commit()

            except Exception as e:
                msg = 'TREE DATA DELETE error occured : ', str(e)
                t_logger.error(msg)
                self.logTextEdit.append(msg)

        for item in self.itemSetPointList:
            # print(item[0], type(item[0]), item)
            t_logger.info(str(item))

            with self.conn.cursor() as curs:
                try:
                    node_id = item[0]
                    item_name = item[1]

                    item_id = self.search_item_id(curs, gv_sys1_id, node_id, item_name, item_class=None)

                    alarm_type = item[2].get('Alarm Type')
                    over_highhigh = item[2].get('Over.HighHighLimit')
                    over_high = item[2].get('Over.HighLimit')
                    under_high = item[2].get('Under.HighLimit')
                    under_highhigh = item[2].get('Under.HighHighLimit')
                    unit = item[3]
                    subunit = item[4]

                    range_low = item[5].get('Low')
                    range_high = item[5].get('High')

                    sql = "insert ignore into SDA_ITEM_SET_POINT(SYS1_ID, ITEM_ID, ITEM_NAME, ALARM_TYPE, OVER_HIGHHIGH, OVER_HIGH, " \
                          "       UNDER_HIGH, UNDER_HIGHHIGH, UNIT, SUBUNIT, RANGE_LOW, RANGE_HIGH, CREATE_DT)" \
                          "SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s," \
                          "       (SELECT NAME FROM SDA_SUBUNIT_CODE WHERE CODE = %s), " \
                          "       round(%s,4), round(%s,4), NOW()"
                    record = (gv_sys1_id, item_id, item_name, alarm_type, over_highhigh, over_high,
                              under_high, under_highhigh, unit, subunit, range_low, range_high)
                    curs.execute(sql, record)
                    self.conn.commit()

                except Exception as e:
                    msg = 'TREE DATA INSERT error occured : ' + str(e)
                    t_logger.error(msg)
                    self.logTextEdit.append(msg)

    # Static, Dynamic Data Change subscribe
    def subscribe_all_items(self):

        msg = '\n################################################\n' \
              'START STATIC DATA COLLECTION (' + datetime.now().strftime('%Y%m%d %H%M%S') + ') \n' \
              '################################################\n'
        s_logger.info(msg)
        self.logTextEdit.append(msg)

        msg = '\n################################################\n' \
              'START DYNAMIC DATA COLLECTION (' + datetime.now().strftime('%Y%m%d %H%M%S') + ') \n' \
              '################################################\n'
        d_logger.info(msg)
        self.logTextEdit.append(msg)

        # print(' item Tree list')
        for item in self.treeList:

            if item[0] in ('AnalogItemType', 'BaseDataVariableType') and item[5] == 'M':
                # print('subscribe item : ', item)
                node = self.client.get_node(item[1])
                self.datachange_ui._subscribe(node)

        # print(' ### item setpoint ###')
        # for item in self.itemSetPointList:
        #     print(item)

    # Event subscribe
    def subscribe_all_events(self):

        msg = '\n################################################\n' \
              'START EVENT DATA COLLECTION (' + datetime.now().strftime('%Y%m%d %H%M%S') + ') \n' \
              '################################################\n'
        e_logger.info(msg)
        self.logTextEdit.append(msg)

        # print(self.treeList[1][1], '  ', self.treeList[1])
        node = self.client.get_node(self.treeList[1][1])
        self.event_ui._subscribe(node)

    # subscribe all again
    def reconnect(self):

        msg = '================== subscribe all items again ====='
        logger.info(msg)
        self.logTextEdit.append(msg)

        # system1 configure 정보가 바뀌어서 다시 접속해서 정보를 받아옴
        self.disconnect()
        self.connect()

    def get_child_node2(self, nodeList, gubun, level, disp_ord, p_node):
        # print('nodeList : ', nodeList)

        if not isinstance(nodeList, list):
            nodeList = list(nodeList)

        for idx, node in enumerate(nodeList):
            # print('>>> current node : ', idx, node)

            # 다음 루프 대상 초기화
            next_node = []

            if not isinstance(node, SyncNode):
                node = self.client.get_node(node)

            # insert 할 변수들 초기화
            tag_name = ''
            item_set_point = {}
            item_EURange = {}
            item_Engineering_Unit = ''
            item_Subunit = 0

            node_ref = node.get_references()
            # print('node       ref : ', len(node_ref), node_ref)
            # print('node child ref : ', len(node.get_children_descriptions()), node.get_children_descriptions())

            for c_node in node_ref:
                # print('loop node ref : ', c_node)

                str_type_def = ua.object_ids.ObjectIdNames[c_node.ReferenceTypeId.Identifier]

                if str_type_def == 'HasNotifier':
                    continue
                if str_type_def == 'HasTypeDefinition':
                    # item_type : BaseObjectType(object), AnalogItemType(trend), BaseDataVariableType(waveform)
                    item_type = c_node.DisplayName.Text

                    if item_type not in self.type_def:
                        # print('type_definition : ', item_type, ' - ', c_node)
                        t_logger.info('type_definition : ' + str(item_type) + ' - ' + str(c_node))
                        self.type_def.append(item_type)

                # print('1-', item_type, c_node.ReferenceTypeId.Identifier, str_type_def)

                # 부모 정보( IsForward == False )
                if not c_node.IsForward:
                    continue
                # TODO 제외할 대상을 DB 에 반영하여 읽어오도록 수정
                elif c_node.DisplayName.Text == 'RFCC':
                    continue
                elif c_node.DisplayName.Text == '금호석유화학':
                    continue
                elif str_type_def in ('HasTypeDefinition', 'HasCondition'):
                    pass

                elif c_node.DisplayName.Text == 'Tag Name':
                    # print(c_node.DisplayName.Text, ' : ', c_node)
                    tag_name = self.client.get_node(c_node.NodeId).read_value()
                    # print(tag_name)

                elif c_node.DisplayName.Text == 'EURange':
                    node_attr_value = self.client.get_node(c_node.NodeId).read_value()
                    # print(node_attr_value.Low, node_attr_value.High, node_attr_value, ' : ', c_node)
                    item_EURange['Low'] = node_attr_value.Low
                    item_EURange['High'] = node_attr_value.High

                elif c_node.DisplayName.Text == 'EngineeringUnits':
                    node_attr_value = self.client.get_node(c_node.NodeId).read_value()
                    # print(node_attr_value.DisplayName.Text, node_attr_value, ' : ', c_node)
                    item_Engineering_Unit = node_attr_value.DisplayName.Text

                elif c_node.DisplayName.Text == 'Subunit':
                    node_attr_value = self.client.get_node(c_node.NodeId).read_value()
                    # print(node_attr_value, ' : ', c_node)
                    item_Subunit = node_attr_value

                elif c_node.DisplayName.Text == 'Standard - Condition Monitoring Alarm':
                    node_attr_value = self.get_node_attrs(c_node.NodeId)
                    # print(node_attr_value)
                    # print('>>>> ', type(node_attr_value), node_attr_value[4].Text, node_attr_value, ' : ', c_node)
                    item_set_point[node_attr_value[4].Text.split(' - ')[0]] = node_attr_value[4].Text.split(' - ')[1]
                    # print(' setpoint_descriptions ', self.client.get_node(c_node.NodeId).get_children_descriptions())
                    set_point_nodes = self.client.get_node(c_node.NodeId).get_children_descriptions()
                    for set_node in set_point_nodes:
                        # print('set point node : ', set_node.DisplayName.Text, '  ', set_node)
                        node_attr_value = self.client.get_node(set_node.NodeId).read_value()
                        # print(set_node.DisplayName.Text, round(node_attr_value, 4))
                        item_set_point[set_node.DisplayName.Text] = round(node_attr_value, 4)

                    # print('item_set_point :::: ', item_set_point)

                else:
                    next_node.append(self.client.get_node(c_node.NodeId))

            node_attrs = self.get_node_attrs(node)
            # print(gubun, level, ' , node desc : ', node, ' attrs : ', node_attrs, node_attrs[0].Text)

            nodeId = str(node.nodeid)
            # next step 의 Parent Node Id
            parent_nodeId = nodeId
            # icon_grp = str(node.read_node_class()).split('.')[1]
            item_name = node_attrs[0].Text
            item_type = ua.object_ids.ObjectIdNames[node.read_type_definition().Identifier]

            if tag_name > '' and 'Channel' not in tag_name:
                # print('tag name check : ', tag_name)
                item_type = tag_name
            elif tag_name > '' and 'Channel' in tag_name:
                # print('tag name check : ', tag_name)
                item_type = 'point'
            elif item_type == 'AnalogItemType':
                # print('Static Value : ', item_type, '  ', item_name)

                # print('items :::: ', item_type, guid, item_name, item_level, tag_name, item_set_point,
                #                      item_EURange, item_Engineering_Unit, item_Subunit)

                # Trend Value 에만 존재함
                # 중복되지 않게 machine 에서만 추가함
                if gubun == 'M':
                    self.itemSetPointList.append([nodeId, item_name, item_set_point,
                                                  item_Engineering_Unit, item_Subunit, item_EURange])

            # elif item_type == 'BaseDataVariableType':
            #     print('Dynamic Value', item_type, '  ', item_name)

            if level == 1:
                display_ord = gubun
            else:
                display_ord = disp_ord + '_' + str(idx + 1).zfill(2)
            # print('insert : ', item_type, nodeId, item_name, level, idx, gubun, p_nodeId)
            self.treeList.append([item_type, nodeId, item_name, level, display_ord, gubun, p_node])

            if len(next_node) > 0:
                # print('child node : ', next_node)
                self.get_child_node2(next_node, gubun, level + 1, display_ord, parent_nodeId)

    def disconnect(self):
        try:
            if isinstance(self.client, Client):
                logger.info(' disconnecting.. from System1 ')
                self.client.disconnect()
                logger.info(' disconnected from System1 ')
                self.logTextEdit.append(' disconnected from System1 ')
            else:
                logger.info(' not connected from System1 ')
                self.logTextEdit.append(' not connected from System1 ')
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
        # descs.sort(key=lambda x: x.BrowseName)
        return descs

    # using NodeID find ITEM_ID
    def search_item_id(self, curs, sys1_id, node_id, item_name, item_class):

        # search ITEM ID
        sql = 'select ITEM_ID from SDA_NODE_ITEM_MAPPING where SYS1_ID = %s and NODE_ID = %s'
        record = (sys1_id, node_id)
        curs.execute(sql, record)
        item_id = curs.fetchone()
        search_cnt = curs.rowcount

        # if not found
        if search_cnt == 0:
            sql = "insert into SDA_NODE_ITEM_MAPPING(SYS1_ID, NODE_ID, ITEM_NAME, ITEM_CLASS, CREATE_DT) " \
                  "select %s, %s, %s, %s, NOW()"
            record = (sys1_id, node_id, item_name, item_class)
            curs.execute(sql, record)
            self.conn.commit()

            sql = 'select ITEM_ID from SDA_NODE_ITEM_MAPPING where SYS1_ID = %s and NODE_ID = %s'
            record = (sys1_id, node_id)
            curs.execute(sql, record)
            item_id = curs.fetchone()

        return item_id

    def make_logger(self, l_type, name=None):
        # 로그 저장할 폴더 생성
        current_dir = os.path.abspath(os.path.curdir)
        log_dir = '{}/{}'.format(current_dir, gv_log_folder)
        # os.makedirs(log_dir, exist_ok=True)
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)

        if l_type == 'main':
            log_file_name = log_dir + '/' + gv_main_log_file_name + '.log'
        elif l_type == 'static':
            log_file_name = log_dir + '/' + gv_static_log_file_name + '.log'
        elif l_type == 'dynamic':
            log_file_name = log_dir + '/' + gv_dynamic_log_file_name + '.log'
        elif l_type == 'tree':
            log_file_name = log_dir + '/' + gv_tree_log_file_name + '.log'
        elif l_type == 'event':
            log_file_name = log_dir + '/' + gv_event_log_file_name + '.log'
        elif l_type == 'console':
            pass
        else:
            log_file_name = gv_etc_log_file_name + '.log'

        #
        # ###  참고 ---  logger 를 생성할 때 json 파일을 이용해서 만드는 로직
        # with open("logging.json", "rt") as file:
        #     config = json.load(file)
        #
        # logging.config.dictConfig(config)
        # logger = logging.getLogger()
        #

        # 1 logger instance를 만든다.
        logger = logging.getLogger(name)

        # 2 logger의 level을 가장 낮은 수준인 DEBUG로 설정해둔다.
        logger.setLevel(logging.DEBUG)

        # 3 formatter 지정
        formatter = logging.Formatter("[%(asctime)s] - %(name)s - %(levelname)s - %(message)s")

        if l_type != 'console':
            # create daily log file
            file_handler = logging.handlers.TimedRotatingFileHandler(
                filename=log_file_name, when='d', interval=1, encoding='utf-8'
            )
            file_handler.suffix = '_%Y%m%d'

            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        # 4 handler instance 생성
        console = logging.StreamHandler()
        # 5 handler 별로 다른 level 설정
        console.setLevel(logging.DEBUG)
        # 6 handler 출력 format 지정
        console.setFormatter(formatter)
        # 7 logger에 handler 추가
        logger.addHandler(console)

        return logger

    # using ItemClass find ItemType
    def search_item_type(self, curs, sys1_id, item_name, item_class):

        # search ITEM ID
        sql = 'select ITEM_TYPE from SDA_NODE_ITEM_TYPE where SYS1_ID = %s and ITEM_CLASS = %s'
        record = (sys1_id, item_class)
        curs.execute(sql, record)
        item_type = curs.fetchone()
        search_cnt = curs.rowcount

        # if not found
        if search_cnt == 0:

            # 기초 로직일 뿐 신규 항목 발생시 db table 값만 업데이트 해주고 다시 실행하면 반영됨
            if item_class == 'FolderType':
                item_type = 'folder'
            elif item_class in ('AnalogItemType', 'BaseDataVariableType'):
                item_type = 'sensor'
            elif item_class == item_name:
                item_type = 'object'
            elif item_class in ('BaseObjectType', 'Non-Rotating Machine'):
                item_type = 'object'
            else:
                item_type = item_class

            sql = "insert into SDA_NODE_ITEM_TYPE(SYS1_ID, ITEM_CLASS, ITEM_TYPE, CREATE_DT, CREATE_USER_ID) " \
                  "select %s, %s, %s, NOW(), %s"
            record = (sys1_id, item_class, item_type, gv_user_id)
            curs.execute(sql, record)
            self.conn.commit()

            sql = 'select ITEM_TYPE from SDA_NODE_ITEM_TYPE where SYS1_ID = %s and ITEM_CLASS = %s'
            record = (sys1_id, item_class)
            curs.execute(sql, record)
            item_type = curs.fetchone()

        return item_type

    # using endpoint_url find SYS1_ID
    def search_sys1_id(self, curs, endpoint_url):
        # print('endpoint_url : ', endpoint_url, type(endpoint_url))

        # search SYS1 ID
        sql = 'select SYS1_ID from SDA_SYS1_LIST where ENDPOINT_URL = %s'
        record = endpoint_url
        curs.execute(sql, record)
        sys1_id = curs.fetchone()
        search_cnt = curs.rowcount

        # if not found
        if search_cnt == 0:
            sql = "insert into SDA_SYS1_LIST(ENDPOINT_URL, CREATE_DT, CREATE_USER_ID) " \
                  "select %s, NOW(), %s"
            record = (endpoint_url, gv_user_id)
            curs.execute(sql, record)
            self.conn.commit()

            sql = 'select SYS1_ID from SDA_SYS1_LIST where ENDPOINT_URL = %s'
            record = endpoint_url
            curs.execute(sql, record)
            sys1_id = curs.fetchone()

        # print('sys1_id : ', type(sys1_id), sys1_id, type(sys1_id[0]), sys1_id[0])

        return str(sys1_id[0]).zfill(2)

    def get_node_attrs(self, node):
        if not isinstance(node, SyncNode):
            node = self.client.get_node(node)
        attrs = node.read_attributes(
            [ua.AttributeIds.DisplayName, ua.AttributeIds.BrowseName, ua.AttributeIds.NodeId, ua.AttributeIds.NodeClass,
             ua.AttributeIds.Description])
        # attrs = node.read_attributes([])

        return [attr.Value.Value for attr in attrs]

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

        self._subs_datachange[node.nodeid] = handle
        return handle

    def unsubscribe_datachange(self, node):
        self._datachange_sub.unsubscribe(self._subs_datachange[node.nodeid])
        if node.nodeid in self._subs_datachange:
            del self._subs_datachange[node.nodeid]

    # to make conditionId column, create event filter manually
    def create_event_filter(self, tloop, evtypes):

        evfilter = get_filter_from_event_type(tloop, evtypes)
        op = ua.SimpleAttributeOperand()
        op.TypeDefinitionId = ua.TwoByteNodeId(0)
        op.AttributeId = ua.AttributeIds.Value
        op.BrowsePath = []
        evfilter.SelectClauses.append(op)
        # print(' add condition id : ', op, evfilter.SelectClauses)

        return evfilter

    def subscribe_events(self, node, handler):
        if not self._event_sub:
            self._event_sub = self.client.create_subscription(500, handler)

            # subscription 생성후 id 를 저장해 놓음
            global gv_event_subscription_id
            gv_event_subscription_id = self._event_sub.aio_obj.subscription_id

        evtypes = [self.client.get_node('ns=2;i=1002')]
        # print('evtypes : ', evtypes)

        evfilter = self.create_event_filter(node.tloop, evtypes)
        handle = self._event_sub.subscribe_events(evtypes=evtypes, sourcenode=node, evfilter=evfilter)

        # print('check :: ', type(self._event_sub), handle)
        self._subs_event[node.nodeid] = handle
        e_logger.info('MainWindow Event Subscribed !!')
        self.logTextEdit.append('MainWindow Event Subscribed !!')

        # call method condition refresh
        # 기존 알람들 조회
        inputArgs = ua.Variant(gv_event_subscription_id, ua.VariantType.UInt32)
        # print('before sub event : gv_event_subscription_id = ', gv_event_subscription_id)
        self.client.get_node('i=2782').call_method('ConditionRefresh', inputArgs)

        return handle

    def unsubscribe_events(self, node):

        self._event_sub.unsubscribe(self._subs_event[node.nodeid])
        if node.nodeid in self._subs_event:
            del self._subs_event[node.nodeid]

        e_logger.info('Event UnSubscribed !!')
        self.logTextEdit.append('Event UnSubscribed !!')

    def show_error(self, msg):
        logger.error("showing error: %s", msg)
        self.logTextEdit.append('error msg : ', msg)

        self.statusBar.show()
        self.statusBar.setStyleSheet("QStatusBar { background-color : red; color : black; }")
        self.statusBar.showMessage(str(msg))
        # QTimer.singleShot(1500, self.statusBar.hide)
        QTimer.singleShot(1500, self.statusBar.showMessage(''))


@sync.syncfunc(aio_func=common.events.get_filter_from_event_type)
def get_filter_from_event_type(eventtypes):
    pass

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MainWindow()
    window.setGeometry(10, 10, 1200, 800)

    window.show()
    # window.showFullScreen()

    sys.exit(app.exec_())
