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
APP_NAME = "CloudLight燕山大学校园网认证程序2.9"
DEFAULT_CONFIG = {
    "user": "",
    "pwd": "",
    "type": "校园网",

    # 周期性检测（按 ping 判断是否有网）
    "check_host": "www.baidu.com",     # 主：百度
    "fallback_check_host": "223.5.5.5",# 备：阿里 AliDNS
    "tertiary_check_host": "119.29.29.29",  # 第三：腾讯 DNS
    "ping_timeout_ms": 1500,
    "check_interval_sec": 30.0,             # 周期检测间隔（秒）

    # 登录成功后的二次校验（留空/0 则回退到上面的目标与超时）
    "post_login_check_host": "",
    "post_login_fallback_host": "",
    "post_login_tertiary_host": "",
    "post_login_ping_timeout_ms": 0,

    # 重连等待
    "reconnect_wait_sec": 5.0,

    # 程序行为
    "auto_start_monitor": True,
    "auto_start_with_windows": False,

    # 日志保留
    "max_log_lines": 1000
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
# 原有登录逻辑（增强：安全解析 + 认证前先下线）
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

    # —— 安全解析：JSON —— #
    def _json_from_response(self, res):
        """
        安全解析 JSON：
        1) 优先 res.json()
        2) 若失败，检查 gzip 头（1F 8B），尝试手动解压再解析
        3) 再失败则按 UTF-8 严格解析
        """
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

    # —— 安全解析：文本（用于从 HTML 中提取 queryString） —— #
    def _text_from_response(self, res):
        try:
            return res.text
        except Exception:
            pass
        data = res.content
        try:
            if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
                return gzip.decompress(data).decode('utf-8', errors='replace')
            return data.decode('utf-8', errors='replace')
        except Exception:
            return ''

    def tst_net(self):
        """是否已通过校园网认证（不代表外网可达）"""
        res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
        self.isLogined = ('success.jsp' in res.url)
        return self.isLogined

    def _try_logout_once(self):
        """无论是否在线，都尝试获取 userIndex 并调用 logout，失败忽略。"""
        try:
            if self.alldata is None:
                try:
                    res_info = requests.get('http://10.11.0.1/eportal/InterFace.do?method=getOnlineUserInfo', timeout=5)
                    self.alldata = self._json_from_response(res_info)
                except Exception:
                    self.alldata = None

            user_index = None
            if isinstance(self.alldata, dict):
                user_index = self.alldata.get('userIndex')

            if user_index:
                res = requests.post(self.url + 'logout', headers=self.header,
                                    data={'userIndex': user_index}, timeout=8)
                _ = self._json_from_response(res)
        except Exception:
            pass
        finally:
            self.alldata = None

    def login(self, user, pwd, type, code=''):
        # 1) 无论是否在线，先“尝试下线”一次
        self._try_logout_once()

        # 2) 刷新状态
        if self.isLogined is None:
            try:
                self.tst_net()
            except Exception:
                self.isLogined = False

        # 3) 执行登录流程
        if user == '' or pwd == '':
            return (False, '用户名或密码为空')

        # 3.1 先拿 queryString
        res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
        html = self._text_from_response(res)
        query = re.findall(r"href='.*?\?(.*?)'", html, re.S)
        if not query:
            query = re.findall(r'href="[^"]+\?([^"]+)"', html, re.S)
        query_string = query[0] if query else ''

        # 3.2 提交
        self.data = {
            'userId': user,
            'password': pwd,
            'service': self.services.get(type, self.services['校园网']),
            'operatorPwd': '',
            'operatorUserId': '',
            'validcode': code,
            'passwordEncrypt': 'False',
            'queryString': query_string
        }
        res = requests.post(self.url + 'login', headers=self.header, data=self.data, timeout=8)
        login_json = self._json_from_response(res)
        self.userindex = login_json.get('userIndex')
        self.info = login_json.get('message', '')
        if login_json.get('result') == 'success':
            self.isLogined = True
            return (True, '认证成功')
        else:
            self.isLogined = False
            return (False, self.info)

    def get_alldata(self):
        res = requests.get('http://10.11.0.1/eportal/InterFace.do?method=getOnlineUserInfo', timeout=5)
        self.alldata = self._json_from_response(res)
        return self.alldata

    def logout(self):
        if self.alldata is None:
            self.get_alldata()
        user_index = None
        if isinstance(self.alldata, dict):
            user_index = self.alldata.get('userIndex')
        if not user_index:
            user_index = ''
        res = requests.post(self.url + 'logout', headers=self.header,
                            data={'userIndex': user_index}, timeout=8)
        logout_json = self._json_from_response(res)
        self.info = logout_json.get('message', '')
        if logout_json.get('result') == 'success':
            self.isLogined = False
            return (True, '下线成功')
        else:
            return (False, self.info)

# -----------------------------
# 监控 worker（QTimer 驱动，按 ping 三级检测）
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

    def _ping_once(self, host, timeout_ms):
        """静默 ping：Windows 下不弹出终端窗口"""
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

    def _ping_chain_ok(self, hosts, timeout_ms):
        """
        依次按 hosts 进行 ping；任一成功即判定可达。
        返回：(是否可达, 命中的 host 或最后一个尝试的 host)
        """
        tried = None
        for h in hosts:
            h = (h or '').strip()
            if not h:
                continue
            # 跳过重复 host
            if tried == h:
                continue
            tried = h
            if self._ping_once(h, timeout_ms):
                return True, h
        # 全部失败：返回最后尝试的 host（用于日志）
        return False, tried

    def _sleep_with_cancel(self, sec):
        """可中断睡眠，停止时能快速退出等待。"""
        end = time.time() + max(0.0, float(sec))
        while self._running and time.time() < end:
            time.sleep(min(0.1, end - time.time()))

    @QtCore.Slot()
    def _tick(self):
        if not self._running:
            return
        self._apply_interval_from_cfg()
        cfg = self._cfg_getter()

        # 读取检测参数（三级链：主→备→第三）
        primary = (cfg.get("check_host") or "www.baidu.com").strip()
        fallback = (cfg.get("fallback_check_host") or "223.5.5.5").strip()
        tertiary = (cfg.get("tertiary_check_host") or "119.29.29.29").strip()
        try:
            tout = int(cfg.get("ping_timeout_ms", 1500))
        except Exception:
            tout = 1500

        # 1) 先按三级 ping 检测外网是否可达
        ok, hit = self._ping_chain_ok([primary, fallback, tertiary], tout)
        if ok:
            self.log.emit(self._ts() + f"网络正常 | ping {hit} 成功")
            return

        # 2) 不通则尝试认证（认证前先下线的逻辑在 Main.login() 内部已实现）
        self.log.emit(self._ts() + f"外网不通（{primary} / {fallback} / {tertiary} 均失败），尝试认证校园网...")
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

        # 3) 若认证成功但外网仍不通 → 持续重试直到通或停止（三级 ping）
        if state:
            post_primary   = (cfg.get("post_login_check_host") or primary).strip()
            post_fallback  = (cfg.get("post_login_fallback_host") or fallback).strip()
            post_tertiary  = (cfg.get("post_login_tertiary_host") or tertiary).strip()
            post_tout = int(cfg.get("post_login_ping_timeout_ms") or tout)
            wait_sec = float(cfg.get("reconnect_wait_sec", 5.0))

            while self._running:
                self.log.emit(self._ts() + f"认证成功，3 秒后检查外网连通性（{post_primary} / {post_fallback} / {post_tertiary}）...")
                self._sleep_with_cancel(3.0)
                if not self._running:
                    break

                ok2, hit2 = self._ping_chain_ok([post_primary, post_fallback, post_tertiary], post_tout)
                if ok2:
                    self.log.emit(self._ts() + f"外网连通性正常（{hit2} 可达）")
                    break  # 成功，结束重试

                # 外网不通 → 下线并重试
                self.log.emit(self._ts() + "外网仍不可达，执行下线并重试认证...")
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
                    continue
            return

# -----------------------------
# 设置对话框（加入主/备/第三 ping 目标 & 日志限量）
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

        # 检测参数（按 ping）
        self.ed_host = QtWidgets.QLineEdit(self.cfg.get("check_host", "www.baidu.com"))
        self.ed_fallback = QtWidgets.QLineEdit(self.cfg.get("fallback_check_host", "223.5.5.5"))
        self.ed_tertiary = QtWidgets.QLineEdit(self.cfg.get("tertiary_check_host", "119.29.29.29"))

        self.sp_ping_timeout = QtWidgets.QSpinBox()
        self.sp_ping_timeout.setRange(200, 20000)
        self.sp_ping_timeout.setSingleStep(100)
        self.sp_ping_timeout.setValue(int(self.cfg.get("ping_timeout_ms", 1500)))

        self.sp_interval = QtWidgets.QDoubleSpinBox()
        self.sp_interval.setRange(0.01, 86400.0)
        self.sp_interval.setDecimals(2)
        self.sp_interval.setSingleStep(1.0)
        self.sp_interval.setValue(float(self.cfg.get("check_interval_sec", 30.0)))

        self.sp_reconnect_wait = QtWidgets.QDoubleSpinBox()
        self.sp_reconnect_wait.setRange(0.0, 60.0)
        self.sp_reconnect_wait.setDecimals(1)
        self.sp_reconnect_wait.setSingleStep(0.5)
        self.sp_reconnect_wait.setValue(float(self.cfg.get("reconnect_wait_sec", 5.0)))

        self.sp_max_lines = QtWidgets.QSpinBox()
        self.sp_max_lines.setRange(100, 20000)
        self.sp_max_lines.setSingleStep(100)
        self.sp_max_lines.setValue(int(self.cfg.get("max_log_lines", 1000)))

        # 登录后二次校验（可选）
        self.ed_post_host = QtWidgets.QLineEdit(self.cfg.get("post_login_check_host", ""))
        self.ed_post_fallback = QtWidgets.QLineEdit(self.cfg.get("post_login_fallback_host", ""))
        self.ed_post_tertiary = QtWidgets.QLineEdit(self.cfg.get("post_login_tertiary_host", ""))
        self.sp_post_timeout = QtWidgets.QSpinBox()
        self.sp_post_timeout.setRange(0, 20000)  # 0 表示回退到 ping_timeout_ms
        self.sp_post_timeout.setSingleStep(100)
        self.sp_post_timeout.setValue(int(self.cfg.get("post_login_ping_timeout_ms", 0)))

        form.addRow("账号：", self.ed_user)
        form.addRow("密码：", self.ed_pwd)
        form.addRow("运营商：", self.cmb_type)
        form.addRow("检测目标（主）：", self.ed_host)
        form.addRow("检测目标（备-阿里）：", self.ed_fallback)
        form.addRow("检测目标（第三-腾讯）：", self.ed_tertiary)
        form.addRow("ping 超时（毫秒）：", self.sp_ping_timeout)
        form.addRow("检测间隔（秒）：", self.sp_interval)
        form.addRow("重连时等待时间（秒）：", self.sp_reconnect_wait)
        form.addRow("日志最多保留行数：", self.sp_max_lines)
        form.addRow("登录后检测目标（主，可留空）：", self.ed_post_host)
        form.addRow("登录后检测目标（备，可留空）：", self.ed_post_fallback)
        form.addRow("登录后检测目标（第三，可留空）：", self.ed_post_tertiary)
        form.addRow("登录后 ping 超时（毫秒，0=沿用）：", self.sp_post_timeout)

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
        self.cfg["check_host"] = self.ed_host.text().strip() or "www.baidu.com"
        self.cfg["fallback_check_host"] = self.ed_fallback.text().strip() or "223.5.5.5"
        self.cfg["tertiary_check_host"] = self.ed_tertiary.text().strip() or "119.29.29.29"
        self.cfg["ping_timeout_ms"] = int(self.sp_ping_timeout.value())
        self.cfg["check_interval_sec"] = float(self.sp_interval.value())
        self.cfg["reconnect_wait_sec"] = float(self.sp_reconnect_wait.value())
        self.cfg["max_log_lines"] = int(self.sp_max_lines.value())
        self.cfg["post_login_check_host"] = self.ed_post_host.text().strip()
        self.cfg["post_login_fallback_host"] = self.ed_post_fallback.text().strip()
        self.cfg["post_login_tertiary_host"] = self.ed_post_tertiary.text().strip()
        self.cfg["post_login_ping_timeout_ms"] = int(self.sp_post_timeout.value())
        self.cfg["auto_start_monitor"] = bool(self.cfg.get("auto_start_monitor", True))
        self.cfg["auto_start_with_windows"] = bool(self.cfg.get("auto_start_with_windows", False))
        return self.cfg

# -----------------------------
# 主窗口（含日志裁剪）
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

    def _trim_logs(self):
        """裁剪 QTextEdit 仅保留配置中的最多行数，避免越用越卡。"""
        max_lines = int(self.cfg.get("max_log_lines", 1000))
        doc = self.log_view.document()
        block_count = doc.blockCount()
        if block_count <= max_lines:
            return
        # 删除最早的多余行
        extra = block_count - max_lines
        cursor = QtGui.QTextCursor(doc)
        cursor.beginEditBlock()
        cursor.movePosition(QtGui.QTextCursor.Start)
        for _ in range(extra):
            cursor.select(QtGui.QTextCursor.BlockUnderCursor)
            cursor.removeSelectedText()
            cursor.deleteChar()  # 删除换行
        cursor.endEditBlock()

    @QtCore.Slot(str)
    def append_log(self, s: str):
        self.log_view.append(s)
        self._trim_logs()

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
