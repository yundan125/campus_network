# app.py
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import platform
import subprocess  # 仍保留（若后续需要扩展），不影响运行
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets
import requests

# -----------------------------
# 应用常量与资源
# -----------------------------
APP_NAME = "CloudLight校园网认证程序2.3"
DEFAULT_CONFIG = {
    "user": "",
    "pwd": "",
    # 运营商可选：'校园网'、'中国移动'、'中国联通'、'中国电信' 或 '0'/'1'/'2'/'3'
    "type": "校园网",
    # 检测参数（不再 ping，仅定时触发认证检查）
    "check_interval_sec": 30.0,   # 支持小数秒，建议 10~30
    # 程序行为
    "auto_start_monitor": True,        # 启动时自动开始监控
    "auto_start_with_windows": False   # 开机自启
}

def appdata_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, APP_NAME)
    os.makedirs(path, exist_ok=True)
    return path

def config_path():
    return os.path.join(appdata_dir(), "config.json")

def load_config():
    path = config_path()
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(config_path(), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

def resource_path(rel: str) -> str:
    if hasattr(sys, "_MEIPASS"):  # PyInstaller 单文件临时目录
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

ICON_PATH = resource_path("app.ico")

# -----------------------------
# 原有登录逻辑（尽量不改动）
# -----------------------------
class Main():
    def __init__(self):
        self.services = {
            '校园网': '%e6%a0%a1%e5%9b%ad%e7%bd%91',
            '中国移动': '%E4%B8%AD%E5%9B%BD%E7%A7%BB%E5%8A%A8',
            '中国联通': '%e4%b8%ad%e5%9b%bd%e8%81%94%e9%80%9a',
            '中国电信': '%e4%b8%ad%e5%9b%bd%e7%94%b5%e4%bf%a1',
            '0': '%e6%a0%a1%e5%9b%ad%e7%bd%91',
            '1': '%E4%B8%AD%E5%9B%BD%E7%A7%BB%E5%8A%A8',
            '2': '%e4%b8%ad%e5%9b%bd%e8%81%94%e9%80%9a',
            '3': '%e4%b8%ad%e5%9b%bd%e7%94%b5%e4%bf%a1'
        }
        self.url = 'http://auth.ysu.edu.cn/eportal/InterFace.do?method='
        self.header = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134'
        }
        self.isLogined = None
        self.alldata = None

    def tst_net(self):
        '''
        测试网络是否认证
        :return: 是否已经认证
        '''
        res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
        if 'success.jsp' in res.url:
            self.isLogined = True
        else:
            self.isLogined = False
        return self.isLogined

    def isCode(self):
        '''
        检测是否需要输入验证码
        未开放
        :return:是否需要验证码
        '''
        pass
        return False

    def login(self, user, pwd, type, code=''):
        '''
        输入参数登入校园网，自动检测当前网络是否认证。
        :param user:登入id
        :param pwd:登入密码
        :param type:认证服务
        :param code:验证码
        :return:元祖第一项：是否认证状态；第二项：详细信息
        '''
        if self.isLogined is None:
            self.tst_net()
        if self.isLogined is False:
            if user == '' or pwd == '':
                return (False, '用户名或密码为空')
            self.data = {
                'userId': user,
                'password': pwd,
                'service': self.services[type],
                'operatorPwd': '',
                'operatorUserId': '',
                'validcode': code,
                'passwordEncrypt': 'False'
            }
            res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
            queryString = re.findall(r"href='.*?\?(.*?)'", res.content.decode('utf-8'), re.S)
            self.data['queryString'] = queryString[0]

            res = requests.post(self.url + 'login', headers=self.header, data=self.data, timeout=8)
            login_json = json.loads(res.content.decode('utf-8'))
            self.userindex = login_json.get('userIndex')
            self.info = login_json.get('message', '')
            if login_json.get('result') == 'success':
                return (True, '认证成功')
            else:
                return (False, self.info)
        return (True, '已经在线')

    def get_alldata(self):
        '''
        获取当前认证账号全部信息
        #！！！注意！！！#此操作会获得账号alldata['userId']姓名alldata['userName']以及密码alldata['password']
        :return:全部数据的字典格式
        '''
        res = requests.get('http://10.11.0.1/eportal/InterFace.do?method=getOnlineUserInfo', timeout=5)
        try:
            self.alldata = json.loads(res.content.decode('utf-8'))
        except json.decoder.JSONDecodeError:
            print('数据解析失败，请稍后重试。')
        return self.alldata

    def logout(self):
        '''
        登出，操作内会自动获取特征码
        :return:元祖第一项：是否操作成功；第二项：详细信息
        '''
        if self.alldata is None:
            self.get_alldata()
        res = requests.post(self.url + 'logout', headers=self.header,
                            data={'userIndex': self.alldata.get('userIndex')}, timeout=8)
        logout_json = json.loads(res.content.decode('utf-8'))
        self.info = logout_json.get('message', '')
        if logout_json.get('result') == 'success':
            return (True, '下线成功')
        else:
            return (False, self.info)

# -----------------------------
# 监控 worker（QThread + QTimer 事件驱动；不再 ping）
# -----------------------------
class MonitorWorker(QtCore.QObject):
    log = QtCore.Signal(str)
    runningChanged = QtCore.Signal(bool)

    def __init__(self, cfg_getter):
        super().__init__()
        self._cfg_getter = cfg_getter   # 函数：返回最新配置 dict
        self._main = Main()
        self._running = False
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._tick)

    @QtCore.Slot()
    def start(self):
        if self._running:
            return
        self._running = True
        self.runningChanged.emit(True)
        self._apply_interval_from_cfg()
        self._timer.start()
        self.log.emit(self._ts() + "监控已启动（认证检测，无 ping）")
        # 立即执行一次
        QtCore.QTimer.singleShot(0, self._tick)

    @QtCore.Slot()
    def stop(self):
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        self.runningChanged.emit(False)
        self.log.emit(self._ts() + "监控已停止")

    def _ts(self):
        return datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")

    def _apply_interval_from_cfg(self):
        cfg = self._cfg_getter()
        try:
            interval_sec = float(cfg.get("check_interval_sec", 30.0))
        except Exception:
            interval_sec = 30.0
        interval_sec = max(1.0, interval_sec)  # 安全下限：1秒，避免过于频繁
        self._timer.setInterval(int(interval_sec * 1000))

    @QtCore.Slot()
    def _tick(self):
        if not self._running:
            return

        # 动态读取配置（设置里改了值，这里自动生效）
        self._apply_interval_from_cfg()
        cfg = self._cfg_getter()

        # 1) 直接检测是否已在线（访问 10.11.0.1）
        try:
            online = self._main.tst_net()
        except Exception as e:
            self.log.emit(self._ts() + f"检测异常：{e}")
            online = False

        if online:
            self.log.emit(self._ts() + "网络正常（已在线）")
            return

        # 2) 未在线则尝试认证
        self.log.emit(self._ts() + "未认证，尝试自动认证...")
        try:
            state, info = self._main.login(
                user=cfg.get("user", ""),
                pwd=cfg.get("pwd", ""),
                type=cfg.get("type", "校园网")
            )
            self.log.emit(self._ts() + f"认证结果：{info}")
        except Exception as e:
            self.log.emit(self._ts() + f"认证异常：{e}")

# -----------------------------
# 设置对话框（去掉 ping 相关项）
# -----------------------------
class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, cfg: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.setModal(True)
        self.cfg = cfg.copy()

        form = QtWidgets.QFormLayout()

        self.ed_user = QtWidgets.QLineEdit(self.cfg.get("user", ""))
        self.ed_pwd = QtWidgets.QLineEdit(self.cfg.get("pwd", ""))
        self.ed_pwd.setEchoMode(QtWidgets.QLineEdit.Password)

        self.cmb_type = QtWidgets.QComboBox()
        self.cmb_type.addItems(["校园网", "中国移动", "中国联通", "中国电信", "0", "1", "2", "3"])
        idx = self.cmb_type.findText(self.cfg.get("type", "校园网"))
        if idx >= 0:
            self.cmb_type.setCurrentIndex(idx)

        # 仅保留“检测间隔（秒）”
        self.sp_interval = QtWidgets.QDoubleSpinBox()
        self.sp_interval.setRange(0.01, 86400.0)   # 最小 1 秒，避免过于频繁
        self.sp_interval.setDecimals(2)
        self.sp_interval.setSingleStep(1.0)
        self.sp_interval.setValue(float(self.cfg.get("check_interval_sec", 30.0)))

        self.chk_auto_monitor = QtWidgets.QCheckBox("启动时自动开始监控")
        self.chk_auto_monitor.setChecked(bool(self.cfg.get("auto_start_monitor", True)))

        self.chk_boot = QtWidgets.QCheckBox("开机自启")
        self.chk_boot.setChecked(bool(self.cfg.get("auto_start_with_windows", False)))

        form.addRow("账号：", self.ed_user)
        form.addRow("密码：", self.ed_pwd)
        form.addRow("运营商：", self.cmb_type)
        form.addRow("检测间隔（秒）：", self.sp_interval)
        form.addRow("", self.chk_auto_monitor)
        form.addRow("", self.chk_boot)

        btn_ok = QtWidgets.QPushButton("保存")
        btn_cancel = QtWidgets.QPushButton("取消")
        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

        h = QtWidgets.QHBoxLayout()
        h.addStretch(1)
        h.addWidget(btn_ok)
        h.addWidget(btn_cancel)

        v = QtWidgets.QVBoxLayout(self)
        v.addLayout(form)
        v.addLayout(h)

    def get_config(self):
        self.cfg["user"] = self.ed_user.text().strip()
        self.cfg["pwd"] = self.ed_pwd.text()
        self.cfg["type"] = self.cmb_type.currentText().strip()
        self.cfg["check_interval_sec"] = float(self.sp_interval.value())
        self.cfg["auto_start_monitor"] = bool(self.chk_auto_monitor.isChecked())
        self.cfg["auto_start_with_windows"] = bool(self.chk_boot.isChecked())
        return self.cfg

# -----------------------------
# 主窗口（不在任务栏显示）
# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # 不在任务栏显示
        self.setWindowFlag(QtCore.Qt.Tool)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.resize(780, 460)

        # 日志视图
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.setCentralWidget(self.log_view)

        # 工具栏按钮
        tb = QtWidgets.QToolBar()
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        self.btn_start = QtGui.QAction("开始", self)
        self.btn_stop = QtGui.QAction("停止", self)
        self.btn_settings = QtGui.QAction("设置", self)
        tb.addAction(self.btn_start)
        tb.addAction(self.btn_stop)
        tb.addSeparator()
        tb.addAction(self.btn_settings)

        # 托盘
        self.tray = QtWidgets.QSystemTrayIcon(QtGui.QIcon(ICON_PATH), self)
        self.tray.setToolTip(APP_NAME)
        self.tray.activated.connect(self.on_tray_activated)

        menu = QtWidgets.QMenu()
        self.act_start = menu.addAction("开始")
        self.act_stop = menu.addAction("停止")
        menu.addSeparator()
        self.act_settings = menu.addAction("设置")
        self.act_exit = menu.addAction("退出程序")
        self.tray.setContextMenu(menu)
        self.tray.show()

        # 连接信号
        self.btn_start.triggered.connect(self.start_monitor)
        self.btn_stop.triggered.connect(self.stop_monitor)
        self.btn_settings.triggered.connect(self.open_settings)
        self.act_start.triggered.connect(self.start_monitor)
        self.act_stop.triggered.connect(self.stop_monitor)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit.triggered.connect(self.exit_app)

        # 配置与监控
        self.cfg = load_config()

        # Worker + 线程
        self.worker = MonitorWorker(self.get_config)
        self.worker_thread = QtCore.QThread(self)
        self.worker.moveToThread(self.worker_thread)
        self.worker.log.connect(self.append_log)
        self.worker.runningChanged.connect(self.on_running_changed)
        self.worker_thread.start()

        # 自启动监控
        if self.cfg.get("auto_start_monitor", True):
            QtCore.QTimer.singleShot(500, self.start_monitor)

        # 应用开机自启
        self.apply_autostart(self.cfg.get("auto_start_with_windows", False))

        # 初始隐藏（只在托盘）
        self.hide()

    def get_config(self):
        return self.cfg

    @QtCore.Slot(bool)
    def on_running_changed(self, running: bool):
        self.btn_start.setEnabled(not running)
        self.act_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.act_stop.setEnabled(running)

    @QtCore.Slot(str)
    def append_log(self, s: str):
        self.log_view.append(s)

    def on_tray_activated(self, reason):
        if reason == QtWidgets.QSystemTrayIcon.Trigger:  # 单击
            self.toggle_show()

    def toggle_show(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.raise_()
            self.activateWindow()

    def start_monitor(self):
        QtCore.QMetaObject.invokeMethod(self.worker, "start", QtCore.Qt.QueuedConnection)
        self.show_message("监控已启动")

    def stop_monitor(self):
        QtCore.QMetaObject.invokeMethod(self.worker, "stop", QtCore.Qt.QueuedConnection)
        self.show_message("监控已停止")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_cfg = dlg.get_config()
            was_running = self.act_stop.isEnabled()

            # 应用开机自启
            self.apply_autostart(new_cfg.get("auto_start_with_windows", False))

            # 更新并落盘
            self.cfg = new_cfg
            save_config(self.cfg)

            self.append_log(self.ts() + "已保存设置")
            self.show_message("设置已保存")

            # 若正在运行，立即生效（重启监控）
            if was_running:
                self.stop_monitor()
                QtCore.QTimer.singleShot(150, self.start_monitor)

    def apply_autostart(self, enabled: bool):
        if platform.system().lower().startswith("win"):
            try:
                import winreg
                run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_ALL_ACCESS) as key:
                    app_key = APP_NAME
                    if enabled:
                        exe_path = sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(sys.argv[0])
                        winreg.SetValueEx(key, app_key, 0, winreg.REG_SZ, f'"{exe_path}"')
                    else:
                        try:
                            winreg.DeleteValue(key, app_key)
                        except FileNotFoundError:
                            pass
            except Exception as e:
                self.append_log(self.ts() + f"设置开机自启失败：{e}")

    def show_message(self, text: str):
        self.tray.showMessage(APP_NAME, text, QtGui.QIcon(ICON_PATH), 2000)

    def ts(self):
        return datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")

    def closeEvent(self, event: QtGui.QCloseEvent):
        # 点击关闭仅最小化到托盘
        event.ignore()
        self.hide()
        self.show_message("程序已最小化到托盘。右键托盘图标可退出。")

    def exit_app(self):
        # 优雅退出：先停监控，再关闭线程与应用
        QtCore.QMetaObject.invokeMethod(self.worker, "stop", QtCore.Qt.QueuedConnection)
        QtCore.QTimer.singleShot(100, self._final_quit)

    def _final_quit(self):
        if hasattr(self, "worker_thread"):
            self.worker_thread.quit()
            self.worker_thread.wait(2000)
        QtWidgets.QApplication.instance().quit()

# -----------------------------
# 入口
# -----------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(QtGui.QIcon(ICON_PATH))

    w = MainWindow()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
