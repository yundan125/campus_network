# app.py
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import platform
import subprocess
import gzip
from datetime import datetime

from PySide6 import QtCore, QtGui, QtWidgets
import requests

# -----------------------------
# 应用常量与资源
# -----------------------------
APP_NAME = "CloudLight燕山大学校园网认证程序2.5"
DEFAULT_CONFIG = {
    "user": "",
    "pwd": "",
    "type": "校园网",
    "check_interval_sec": 30.0,           # 周期检测间隔（秒）
    "post_login_check_host": "www.baidu.com",
    "post_login_ping_timeout_ms": 1500,
    "reconnect_wait_sec": 5.0,            # 重连时等待时间（秒）
    "auto_start_monitor": True,
    "auto_start_with_windows": False
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
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

ICON_PATH = resource_path("app.ico")

# -----------------------------
# 原有登录逻辑
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
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/64.0.3282.140 Safari/537.36 Edge/17.17134',
            'Accept-Encoding': 'gzip, deflate'
        }
        self.isLogined = None
        self.alldata = None

    def _json_from_response(self, res):
        try:
            return res.json()
        except Exception:
            data = res.content
            if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
                try:
                    decompressed = gzip.decompress(data)
                    return json.loads(decompressed.decode('utf-8'))
                except Exception:
                    pass
            return json.loads(data.decode('utf-8', errors='strict'))

    def tst_net(self):
        res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
        if 'success.jsp' in res.url:
            self.isLogined = True
        else:
            self.isLogined = False
        return self.isLogined

    def login(self, user, pwd, type, code=''):
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
            login_json = self._json_from_response(res)
            self.userindex = login_json.get('userIndex')
            self.info = login_json.get('message', '')
            if login_json.get('result') == 'success':
                return (True, '认证成功')
            else:
                return (False, self.info)
        return (True, '已经在线')

    def get_alldata(self):
        res = requests.get('http://10.11.0.1/eportal/InterFace.do?method=getOnlineUserInfo', timeout=5)
        self.alldata = self._json_from_response(res)
        return self.alldata

    def logout(self):
        if self.alldata is None:
            self.get_alldata()
        res = requests.post(self.url + 'logout', headers=self.header,
                            data={'userIndex': self.alldata.get('userIndex')}, timeout=8)
        logout_json = self._json_from_response(res)
        self.info = logout_json.get('message', '')
        if logout_json.get('result') == 'success':
            return (True, '下线成功')
        else:
            return (False, self.info)

# -----------------------------
# 监控 worker
# -----------------------------
class MonitorWorker(QtCore.QObject):
    log = QtCore.Signal(str)
    runningChanged = QtCore.Signal(bool)

    def __init__(self, cfg_getter):
        super().__init__()
        self._cfg_getter = cfg_getter
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
        self.log.emit(self._ts() + "监控已启动")
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
        interval_sec = max(1.0, interval_sec)
        self._timer.setInterval(int(interval_sec * 1000))

    # 仅用于“认证成功后”的外网检查
    def _ping_once(self, host, timeout_ms):
        system = platform.system().lower()
        if 'windows' in system:
            cmd = ['ping', '-n', '1', '-w', str(int(timeout_ms)), host]
            CREATE_NO_WINDOW = 0x08000000
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=(int(timeout_ms) / 1000.0 + 1),
                    creationflags=CREATE_NO_WINDOW,
                    startupinfo=si
                )
                return proc.returncode == 0
            except Exception:
                return False
        else:
            cmd = ['ping', '-c', '1', host]
            try:
                proc = subprocess.run(
                    cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=(int(timeout_ms) / 1000.0 + 1)
                )
                return proc.returncode == 0
            except Exception:
                return False

    def _sleep_with_cancel(self, sec):
        """可中断睡眠：避免长等待期间无法停止。"""
        end = time.time() + max(0.0, float(sec))
        while self._running and time.time() < end:
            time.sleep(min(0.1, end - time.time()))

    @QtCore.Slot()
    def _tick(self):
        if not self._running:
            return
        self._apply_interval_from_cfg()
        cfg = self._cfg_getter()

        # 1) 检查是否在线
        try:
            online = self._main.tst_net()
        except Exception as e:
            self.log.emit(self._ts() + f"检测异常：{e}")
            online = False

        if online:
            self.log.emit(self._ts() + "网络正常（已在线）")
            return

        # 2) 尝试认证
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
            return

        # 3) 若认证成功但外网不通 → 持续重试直到通或停止
        if state:
            host = cfg.get("post_login_check_host", "www.baidu.com")
            tout = int(cfg.get("post_login_ping_timeout_ms", 1500))
            wait_sec = float(cfg.get("reconnect_wait_sec", 5.0))

            while self._running:
                self.log.emit(self._ts() + f"认证成功，3 秒后检查外网连通性（{host}）...")
                self._sleep_with_cancel(3.0)
                if not self._running:
                    break

                ok = False
                try:
                    ok = self._ping_once(host, tout)
                except Exception as e:
                    self.log.emit(self._ts() + f"外网检查异常：{e}")
                    ok = False

                if ok:
                    self.log.emit(self._ts() + f"外网连通性正常（{host} 可达）")
                    break  # 成功，结束重试

                # 外网不通 → 下线并重试
                self.log.emit(self._ts() + "外网不通，执行下线并重试认证...")
                try:
                    self._main.logout()
                except Exception as e:
                    self.log.emit(self._ts() + f"下线异常：{e}")

                self.log.emit(self._ts() + f"等待 {wait_sec} 秒后再重试认证...")
                self._sleep_with_cancel(wait_sec)
                if not self._running:
                    break

                try:
                    state2, info2 = self._main.login(
                        user=cfg.get("user", ""),
                        pwd=cfg.get("pwd", ""),
                        type=cfg.get("type", "校园网")
                    )
                    self.log.emit(self._ts() + f"重试认证结果：{info2}")
                except Exception as e:
                    self.log.emit(self._ts() + f"重试认证异常：{e}")
                    # 等待后继续下一轮
                    continue

                # 若重试认证失败也继续下一轮；成功则回到 while 顶部再次做 3 秒后外网检查
            return

# -----------------------------
# 设置对话框
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

        self.sp_interval = QtWidgets.QDoubleSpinBox()
        self.sp_interval.setRange(1.0, 86400.0)
        self.sp_interval.setDecimals(2)
        self.sp_interval.setSingleStep(1.0)
        self.sp_interval.setValue(float(self.cfg.get("check_interval_sec", 30.0)))

        self.sp_reconnect_wait = QtWidgets.QDoubleSpinBox()
        self.sp_reconnect_wait.setRange(0.0, 60.0)
        self.sp_reconnect_wait.setDecimals(1)
        self.sp_reconnect_wait.setSingleStep(0.5)
        self.sp_reconnect_wait.setValue(float(self.cfg.get("reconnect_wait_sec", 5.0)))

        self.chk_auto_monitor = QtWidgets.QCheckBox("启动时自动开始监控")
        self.chk_auto_monitor.setChecked(bool(self.cfg.get("auto_start_monitor", True)))

        self.chk_boot = QtWidgets.QCheckBox("开机自启")
        self.chk_boot.setChecked(bool(self.cfg.get("auto_start_with_windows", False)))

        form.addRow("账号：", self.ed_user)
        form.addRow("密码：", self.ed_pwd)
        form.addRow("运营商：", self.cmb_type)
        form.addRow("检测间隔（秒）：", self.sp_interval)
        form.addRow("重连时等待时间（秒）：", self.sp_reconnect_wait)
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
        self.cfg["reconnect_wait_sec"] = float(self.sp_reconnect_wait.value())
        self.cfg["auto_start_monitor"] = bool(self.chk_auto_monitor.isChecked())
        self.cfg["auto_start_with_windows"] = bool(self.chk_boot.isChecked())
        return self.cfg

# -----------------------------
# 主窗口
# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowFlag(QtCore.Qt.Tool)  # 不在任务栏显示
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.resize(780, 460)

        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.setCentralWidget(self.log_view)

        tb = QtWidgets.QToolBar()
        self.addToolBar(QtCore.Qt.TopToolBarArea, tb)
        self.btn_start = QtGui.QAction("开始", self)
        self.btn_stop = QtGui.QAction("停止", self)
        self.btn_settings = QtGui.QAction("设置", self)
        tb.addAction(self.btn_start)
        tb.addAction(self.btn_stop)
        tb.addSeparator()
        tb.addAction(self.btn_settings)

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

        self.btn_start.triggered.connect(self.start_monitor)
        self.btn_stop.triggered.connect(self.stop_monitor)
        self.btn_settings.triggered.connect(self.open_settings)
        self.act_start.triggered.connect(self.start_monitor)
        self.act_stop.triggered.connect(self.stop_monitor)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit.triggered.connect(self.exit_app)

        self.cfg = load_config()

        self.worker = MonitorWorker(self.get_config)
        self.worker_thread = QtCore.QThread(self)
        self.worker.moveToThread(self.worker_thread)
        self.worker.log.connect(self.append_log)
        self.worker.runningChanged.connect(self.on_running_changed)
        self.worker_thread.start()

        if self.cfg.get("auto_start_monitor", True):
            QtCore.QTimer.singleShot(500, self.start_monitor)

        self.apply_autostart(self.cfg.get("auto_start_with_windows", False))
        self.hide()  # 初始隐藏，只在托盘

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
        if reason == QtWidgets.QSystemTrayIcon.Trigger:  # 单击托盘图标
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

            self.apply_autostart(new_cfg.get("auto_start_with_windows", False))

            self.cfg = new_cfg
            save_config(self.cfg)

            self.append_log(self.ts() + "已保存设置")
            self.show_message("设置已保存")

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
        # 优雅退出
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
