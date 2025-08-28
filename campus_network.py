# app.py
# -*- coding: utf-8 -*-

import os
import sys
import json
import re
import time
import threading
import platform
import subprocess
from datetime import datetime

# 第三方
from PySide6 import QtCore, QtGui, QtWidgets
import requests

# -----------------------------
# 路径 & 资源
# -----------------------------
APP_NAME = "NetAutoAuth"
DEFAULT_CONFIG = {
    "user": "",
    "pwd": "",
    # 运营商可选：'校园网'、'中国移动'、'中国联通'、'中国电信' 或 '0'/'1'/'2'/'3'
    "type": "校园网",
    # 网络检测参数
    "check_host": "www.baidu.com",
    "check_interval_sec": 60,
    "ping_timeout_ms": 1500,
    # 程序行为
    "auto_start_monitor": True,      # 启动时自动开始监控
    "auto_start_with_windows": False # 是否开机自启
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
            # 补全缺省字段
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
    # PyInstaller 单文件运行态的资源目录
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)

ICON_PATH = resource_path("app.ico")

# -----------------------------
# 原有登录逻辑（基本不改动）
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
        if res.url.find('success.jsp')>0:
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

    def login(self,user,pwd,type,code=''):
        '''
        输入参数登入校园网，自动检测当前网络是否认证。
        :param user:登入id
        :param pwd:登入密码
        :param type:认证服务
        :param code:验证码
        :return:元祖第一项：是否认证状态；第二项：详细信息
        '''
        if self.isLogined == None:
            self.tst_net()
        if self.isLogined == False:
            if user == '' or pwd == '':
                return (False,'用户名或密码为空')
            self.data = {
                'userId': user,
                'password': pwd,
                'service': self.services[type],
                'operatorPwd': '',
                'operatorUserId': '',
                'validcode': code,
                'passwordEncrypt':'False'
            }
            res = requests.get('http://10.11.0.1', headers=self.header, timeout=5)
            queryString = re.findall(r"href='.*?\?(.*?)'", res.content.decode('utf-8'), re.S)
            self.data['queryString'] = queryString[0]

            res = requests.post(self.url + 'login', headers=self.header, data=self.data, timeout=8)
            login_json = json.loads(res.content.decode('utf-8'))
            self.userindex = login_json['userIndex']
            #self.info = login_json
            self.info = login_json['message']
            if login_json['result'] == 'success':
                return (True,'认证成功')
            else:
                return (False,self.info)
        return (True,'已经在线')

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
        if self.alldata==None:
            self.get_alldata()

        res = requests.post(self.url + 'logout', headers=self.header, data={'userIndex': self.alldata['userIndex']}, timeout=8)
        logout_json = json.loads(res.content.decode('utf-8'))
        #self.info = logout_json
        self.info = logout_json['message']
        if logout_json['result'] == 'success':
            return (True,'下线成功')
        else:
            return (False,self.info)

# -----------------------------
# 监控 Worker（线程）
# -----------------------------
class MonitorWorker(QtCore.QObject):
    log = QtCore.Signal(str)
    runningChanged = QtCore.Signal(bool)

    def __init__(self, cfg_getter):
        super().__init__()
        self._cfg_getter = cfg_getter  # 可调用，返回最新配置 dict
        self._running = False
        self._thread = None
        self._main = Main()

    def start(self):
        if self._running:
            return
        self._running = True
        self.runningChanged.emit(True)
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.log.emit(self._ts() + "监控线程已启动")

    def stop(self):
        if not self._running:
            return
        self._running = False
        self.runningChanged.emit(False)
        self.log.emit(self._ts() + "正在停止监控线程...")

    def _ts(self):
        return datetime.now().strftime("[%Y-%m-%d %H:%M:%S] ")

    # 在 app.py 内，替换 MonitorWorker._ping
def _ping(self, host, timeout_ms):
    system = platform.system().lower()
    if 'windows' in system:
        cmd = ['ping', '-n', '1', '-w', str(int(timeout_ms)), host]

        # 关键：在 Windows 下禁用控制台窗口
        # 1) 使用 CREATE_NO_WINDOW
        CREATE_NO_WINDOW = 0x08000000

        # 2) 同时准备 STARTUPINFO 把窗口隐藏（双保险）
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW  # 告诉子进程不要显示窗口
        # si.wShowWindow = 0  # 可不设，STARTF_USESHOWWINDOW 即可

        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=(int(timeout_ms)/1000.0 + 1),
                creationflags=CREATE_NO_WINDOW,   # <-- 不创建控制台窗口
                startupinfo=si                    # <-- 隐藏窗口
            )
            return proc.returncode == 0
        except Exception:
            return False

    else:
        # Linux / macOS 不会弹窗，按正常方式即可
        cmd = ['ping', '-c', '1', host]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=(int(timeout_ms)/1000.0 + 1)
            )
            return proc.returncode == 0
        except Exception:
            return False


    def _run_loop(self):
        while self._running:
            cfg = self._cfg_getter()
            host = cfg.get("check_host", "www.baidu.com")
            interval = max(5, int(cfg.get("check_interval_sec", 60)))
            tout = int(cfg.get("ping_timeout_ms", 1500))

            ok = self._ping(host, tout)
            if ok:
                self.log.emit(self._ts() + f"网络正常 | ping {host} 成功")
            else:
                self.log.emit(self._ts() + f"无网，尝试自动认证...")
                try:
                    self._main.tst_net()
                except Exception as e:
                    self.log.emit(self._ts() + f"认证状态检测异常：{e}")

                try:
                    state, info = self._main.login(
                        user=cfg.get("user",""),
                        pwd=cfg.get("pwd",""),
                        type=cfg.get("type","校园网")
                    )
                    self.log.emit(self._ts() + f"认证结果：{info}")
                except Exception as e:
                    self.log.emit(self._ts() + f"认证异常：{e}")

            # 分段睡眠，便于快速响应停止
            for _ in range(interval):
                if not self._running:
                    break
                time.sleep(1)

        self.log.emit(self._ts() + "监控线程已停止")

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

        self.ed_user = QtWidgets.QLineEdit(self.cfg.get("user",""))
        self.ed_pwd = QtWidgets.QLineEdit(self.cfg.get("pwd",""))
        self.ed_pwd.setEchoMode(QtWidgets.QLineEdit.Password)

        self.cmb_type = QtWidgets.QComboBox()
        self.cmb_type.addItems(["校园网", "中国移动", "中国联通", "中国电信", "0", "1", "2", "3"])
        idx = self.cmb_type.findText(self.cfg.get("type","校园网"))
        if idx >= 0: self.cmb_type.setCurrentIndex(idx)

        self.ed_host = QtWidgets.QLineEdit(self.cfg.get("check_host","www.baidu.com"))
        self.sp_interval = QtWidgets.QSpinBox()
        self.sp_interval.setRange(5, 86400)
        self.sp_interval.setValue(int(self.cfg.get("check_interval_sec",60)))

        self.sp_timeout = QtWidgets.QSpinBox()
        self.sp_timeout.setRange(200, 10000)
        self.sp_timeout.setSingleStep(100)
        self.sp_timeout.setValue(int(self.cfg.get("ping_timeout_ms",1500)))

        self.chk_auto_monitor = QtWidgets.QCheckBox("启动时自动开始监控")
        self.chk_auto_monitor.setChecked(bool(self.cfg.get("auto_start_monitor", True)))

        self.chk_boot = QtWidgets.QCheckBox("开机自启")
        self.chk_boot.setChecked(bool(self.cfg.get("auto_start_with_windows", False)))

        form.addRow("账号：", self.ed_user)
        form.addRow("密码：", self.ed_pwd)
        form.addRow("运营商：", self.cmb_type)
        form.addRow("检测目标：", self.ed_host)
        form.addRow("检测间隔（秒）：", self.sp_interval)
        form.addRow("ping 超时（毫秒）：", self.sp_timeout)
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
        self.cfg["check_host"] = self.ed_host.text().strip() or "www.baidu.com"
        self.cfg["check_interval_sec"] = int(self.sp_interval.value())
        self.cfg["ping_timeout_ms"] = int(self.sp_timeout.value())
        self.cfg["auto_start_monitor"] = bool(self.chk_auto_monitor.isChecked())
        self.cfg["auto_start_with_windows"] = bool(self.chk_boot.isChecked())
        return self.cfg

# -----------------------------
# 主窗口（仅显示日志；不驻留任务栏）
# -----------------------------
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        # 不在任务栏显示
        self.setWindowFlag(QtCore.Qt.Tool)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QtGui.QIcon(ICON_PATH))
        self.resize(720, 420)

        # 日志窗口
        self.log_view = QtWidgets.QTextEdit()
        self.log_view.setReadOnly(True)
        self.setCentralWidget(self.log_view)

        # 按钮
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

        # 信号连接
        self.btn_start.triggered.connect(self.start_monitor)
        self.btn_stop.triggered.connect(self.stop_monitor)
        self.btn_settings.triggered.connect(self.open_settings)
        self.act_start.triggered.connect(self.start_monitor)
        self.act_stop.triggered.connect(self.stop_monitor)
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit.triggered.connect(self.exit_app)

        # 配置 & 监控
        self.cfg = load_config()
        self.worker = MonitorWorker(self.get_config)
        self.worker.log.connect(self.append_log)
        self.worker.runningChanged.connect(self.on_running_changed)

        # 自启动（监控）
        if self.cfg.get("auto_start_monitor", True):
            QtCore.QTimer.singleShot(500, self.start_monitor)

        # 设置开机自启
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
        self.worker.start()
        self.show_message("监控已启动")

    def stop_monitor(self):
        self.worker.stop()
        self.show_message("监控已停止")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            # 读取新配置
            new_cfg = dlg.get_config()

            # 记录当前是否在运行（Stop 可点击就代表正在运行）
            was_running = self.act_stop.isEnabled()

            # 应用开机自启
            self.apply_autostart(new_cfg.get("auto_start_with_windows", False))

            # 更新内存中的配置并落盘
            self.cfg.update(new_cfg)           # 内存立即更新
            save_config(self.cfg)              # 写入 %APPDATA%\NetAutoAuth\config.json

            # 日志 & 提示
            self.append_log(self.ts() + "已保存设置")
            self.show_message("设置已保存")

            # 若监控线程正在运行，重启以立即生效（无需等下一轮循环）
            if was_running:
                self.worker.stop()
                # 稍等片刻再启动，确保线程干净退出
                QtCore.QTimer.singleShot(150, self.worker.start)



    def apply_autostart(self, enabled: bool):
        if platform.system().lower().startswith("win"):
            try:
                import winreg
                run_key = r"Software\Microsoft\Windows\CurrentVersion\Run"
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key, 0, winreg.KEY_ALL_ACCESS) as key:
                    app_key = APP_NAME
                    if enabled:
                        exe_path = sys.executable if getattr(sys, 'frozen', False) else sys.argv[0]
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
        self.show_message("程序最小化到托盘。右键托盘图标可退出。")

    def exit_app(self):
        # 优雅退出
        self.worker.stop()
        QtCore.QTimer.singleShot(300, QtWidgets.QApplication.instance().quit)

# -----------------------------
# 入口
# -----------------------------
def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 设置全局图标（影响托盘气泡等）
    app.setWindowIcon(QtGui.QIcon(ICON_PATH))

    w = MainWindow()
    # 初次在托盘里运行，如需打开窗口可双击托盘或右键菜单

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
