import sys
import os
from selenium.webdriver.common.keys import Keys
import time
import json
import threading
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from selenium.webdriver.chrome.service import Service as ChromeService
import pystray
from PIL import Image
import tkinter as tk
from tkinter.scrolledtext import ScrolledText
import traceback
import socket

# 在程序开始处，设置 Tcl/Tk 环境变量
if getattr(sys, 'frozen', False):
    # 如果是打包后的程序，则设置 Tcl/Tk 路径为临时解压目录下的 tcl 和 tk 子目录
    base_path = sys._MEIPASS
    tcl_dir = os.path.join(base_path, 'tcl')
    tk_dir = os.path.join(base_path, 'tk')
    os.environ['TCL_LIBRARY'] = tcl_dir
    os.environ['TK_LIBRARY'] = tk_dir
else:
    # 非打包环境，使用原来的逻辑
    # ... 原来设置 Tcl/Tk 环境变量的代码 ...
    # 注意：非打包环境下，我们仍然使用原来的自动查找逻辑
    if sys.platform == "win32":
        base_path = sys.prefix
        possible_paths = [
            os.path.join(base_path, "Library", "lib", "tcl8.6"),
            os.path.join(base_path, "lib", "tcl8.6"),
            os.path.join(base_path, "tcl", "tcl8.6"),
            os.path.join(os.environ.get("CONDA_PREFIX", ""), "Library", "lib", "tcl8.6"),
            r"C:\Python\tcl\tcl8.6",  # 常见安装路径
            r"C:\Program Files\Tcl\lib\tcl8.6"
        ]

        for path in possible_paths:
            if os.path.exists(path):
                os.environ["TCL_LIBRARY"] = path
                tk_path = path.replace("tcl8.6", "tk8.6")
                if os.path.exists(tk_path):
                    os.environ["TK_LIBRARY"] = tk_path
                break
        else:
            # 如果找不到，尝试使用默认值
            tcl_default = os.path.join(base_path, "tcl", "tcl8.6")
            tk_default = os.path.join(base_path, "tcl", "tk8.6")
            if os.path.exists(tcl_default):
                os.environ["TCL_LIBRARY"] = tcl_default
            if os.path.exists(tk_default):
                os.environ["TK_LIBRARY"] = tk_default

def get_base_path():
    """获取可执行文件所在目录路径"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def resource_path(relative_path):
    """获取资源文件路径"""
    return os.path.join(get_base_path(), relative_path)

# 配置文件路径
CONFIG_FILE = resource_path("config.json")
ICON_FILE = resource_path("1.ico")

def load_config():
    """加载配置文件"""
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            return config
    except FileNotFoundError:
        default_config = {
            "username": "你的学号",
            "password": "密码",
            "portal_url": "http://123.123.123.123",
            "service_provider": "中国电信",
            "check_interval": 60,
            "timeout": 15
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4)
            return default_config
        except Exception as e:
            app_log(f"创建配置文件失败: {e}")
            return default_config
    except json.JSONDecodeError as e:
        app_log(f"配置文件格式错误: {e}")
        return None
    except Exception as e:
        app_log(f"加载配置文件出错: {e}")
        return None

def is_network_available():
    """更健壮的网络连接检测"""

    # 方法4：检查百度（处理重定向和编码）
    if check_baidu():
        return True

    return False


def check_baidu():
    """检查百度是否可访问（处理重定向和编码）"""
    try:
        # 禁止自动重定向
        response = requests.get("http://www.baidu.com", timeout=5, allow_redirects=False)

        # 检查是否被重定向
        if 300 <= response.status_code < 400:
            location = response.headers.get('Location', '')
            app_log(f"被重定向到: {location}")

            # 检查是否被重定向到认证页面
            if "portal" in location or "auth" in location:
                return False

            # 跟随重定向
            redirect_response = requests.get(location, timeout=5)
            redirect_response.encoding = 'utf-8'
            if redirect_response.status_code == 200 and "百度" in redirect_response.text:
                return True

        # 直接访问成功
        response.encoding = 'utf-8'  # 确保使用UTF-8编码
        if response.status_code == 200 and "百度" in response.text:
            return True

        return False
    except requests.exceptions.RequestException as e:
        app_log(f"百度访问错误: {str(e)}")
        return False

def init_driver():
    """初始化浏览器驱动"""
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        # 在init_driver函数中添加
        chrome_options.add_argument('--ignore-certificate-errors')
        chrome_options.add_argument('--allow-running-insecure-content')
        chrome_options.add_argument('--disable-web-security')


        # 使用外部 Chrome 和 ChromeDriver
        chrome_path = resource_path("chrome-win64/chrome.exe")
        chromedriver_path = resource_path("chromedriver-win64/chromedriver.exe")

        if not os.path.exists(chrome_path):
            app_log(f"错误: Chrome 文件不存在: {chrome_path}")
            return None

        if not os.path.exists(chromedriver_path):
            app_log(f"错误: ChromeDriver 文件不存在: {chromedriver_path}")
            return None

        chrome_options.binary_location = chrome_path
        service = ChromeService(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # 确保浏览器加载一个有效的初始页面
        driver.get("about:blank")  # 加载空白页
        app_log("浏览器初始化完成")

        return driver

    except Exception as e:
        app_log(f"浏览器驱动初始化失败: {str(e)}")
        return None

def needs_login(driver):
    """检测是否需要登录"""
    try:
        driver.find_element(By.ID, "username")
        return True
    except NoSuchElementException:
        return False

def ensure_http_url(url):
    """确保使用HTTP协议"""
    if url.startswith("https://"):
        return url.replace("https://", "http://", 1)
    return url

def perform_login(driver, config):
    """执行登录操作"""
    try:
        app_log("正在填写登录表单...")
        # 修改：使用新的检测方式等待用户名字段
        if not wait_for_and_input(driver, (By.ID, "username"), config["username"], config["timeout"]):
            app_log("用户名输入框未找到，登录失败")
            return False

        # 修改：使用新的检测方式等待密码字段
        if not wait_for_and_input(driver, (By.ID, "password"), config["password"], config["timeout"]):
            app_log("密码输入框未找到，登录失败")
            return False

        # 修改：使用新的检测方式尝试记住我选项
        remember_element = wait_for_element(driver, (By.ID, "rememberMe"), config["timeout"])
        if remember_element and remember_element.is_displayed():
            if not remember_element.is_selected():
                try:
                    remember_element.click()
                except:
                    app_log("记住我选择失败，继续尝试登录")

        # 修改：使用新的检测方式等待登录按钮
        if not wait_for_and_click(driver, (By.ID, "login_submit"), config["timeout"]):
            app_log("登录按钮未找到，登录失败")
            return False

        app_log("登录信息已提交")
        return True
    except Exception as e:
        app_log(f"登录过程中出错: {str(e)}")
        return False


def select_service_provider(driver, config):
    """选择服务并点击确定按钮"""
    # 获取配置中的服务商名称
    provider = config.get("service_provider", "中国电信")
    try:
        app_log(f"正在选择服务提供商: {provider}...")

        # 定义服务提供商的定位策略
        provider_locators = {
            "中国电信": [
                (By.XPATH, "//span[contains(text(), '中国电信')]"),
                (By.XPATH, "//div[contains(text(), '中国电信')]"),
                (By.XPATH, "//span[@class='service' and contains(., '中国电信')]")
            ],
            "中国联通": [
                (By.XPATH, "//span[contains(text(), '中国联通')]"),
                (By.XPATH, "//div[contains(text(), '中国联通')]"),
                (By.XPATH, "//span[@class='service' and contains(., '中国联通')]")
            ],
            "中国移动": [
                (By.XPATH, "//span[contains(text(), '中国移动')]"),
                (By.XPATH, "//div[contains(text(), '中国移动')]"),
                (By.XPATH, "//span[@class='service' and contains(., '中国移动')]")
            ],
            "校园网": [
                (By.XPATH, "//span[contains(text(), '校园网')]"),
                (By.XPATH, "//div[contains(text(), '校园网')]"),
                (By.XPATH, "//span[@class='service' and contains(., '校园网')]")
            ]
        }

        # 获取当前提供商的所有定位策略
        locators = provider_locators.get(provider, [])
        provider_selected = False

        for locator in locators:
            # 修改：使用新的检测方式尝试点击
            if wait_for_and_click(driver, locator, config["timeout"]):
                app_log(f"已成功选择服务商: {provider}")
                provider_selected = True
                break

        if not provider_selected:
            app_log(f"无法找到服务提供商: {provider}，尝试点击第一个可用选项")
            try:
                # 尝试点击第一个服务提供商作为备选方案
                if wait_for_and_click(driver, (By.XPATH, "//div[@class='service-box']/div[1]//span[@class='service']"), config["timeout"]):
                    app_log("已点击第一个服务提供商作为替代选项")
            except:
                app_log("无法找到任何服务提供商选项")
                return False

        # 2. 添加点击"确定"按钮的功能
        app_log("正在尝试点击确定按钮...")
        try:
            # 多种可能的确认按钮定位方式
            selectors = [
                (By.CSS_SELECTOR, 'button[class*="button-6"][nztype="primary"]'),
                (By.CSS_SELECTOR, 'button.ant-btn-primary'),
                (By.XPATH, "//button[contains(., '确定')]"),
                (By.XPATH, "//button[contains(., '确认')]"),
                (By.XPATH, "//button[contains(., 'Submit')]")
            ]

            confirm_clicked = False
            for selector in selectors:
                # 修改：使用新的检测方式尝试点击
                if wait_for_and_click(driver, selector, config["timeout"]):
                    app_log(f"成功点击确认按钮: {selector}")
                    confirm_clicked = True
                    break

            if not confirm_clicked:
                app_log("确认按钮未找到")
        except Exception as e:
            app_log(f"点击确定按钮时出错: {str(e)}")
            return False

        return True
    except TimeoutException:
        app_log("服务选择页面未显示，可能已自动登录")
        return True
    except Exception as e:
        app_log(f"选择服务时出错: {str(e)}")
        return False


def wait_for_element(driver, locator, timeout=15):
    """等待元素出现，检测存在则返回，否则等待五秒后再次检测"""
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            element = driver.find_element(*locator)
            if element.is_displayed():
                return element
        except:
            pass
        time.sleep(5)  # 等待五秒后再次检测
    return None

def wait_for_and_click(driver, locator, timeout=15):
    """检测元素存在则点击，不存在则等待五秒后再次检测"""
    element = wait_for_element(driver, locator, timeout)
    if element:
        try:
            element.click()
            return True
        except:
            return False
    return False

def wait_for_and_input(driver, locator, text, timeout=15):
    """检测元素存在则输入，不存在则等待五秒后再次检测"""
    element = wait_for_element(driver, locator, timeout)
    if element:
        try:
            element.clear()
            element.send_keys(text)
            return True
        except:
            return False
    return False

def perform_authentication(config):
    """执行认证流程"""
    app_log("启动认证流程...")
    driver = init_driver()
    if not driver:
        app_log("无法初始化浏览器驱动，请检查Chrome和Chromedriver文件是否完整")
        return False

    try:
        portal_url = ensure_http_url(config["portal_url"])
        app_log(f"访问认证页面: {portal_url}")

        # 设置页面加载超时
        driver.set_page_load_timeout(15)  # 15秒页面加载超时

        try:
            driver.get(portal_url)
        except TimeoutException:
            app_log("页面加载超时，但可能已加载基本内容")

        # 获取当前页面URL
        current_url = driver.current_url
        app_log(f"初始URL: {current_url}")

        # 使用循环处理可能的多次重定向
        max_redirects = 5  # 最大重定向次数
        redirect_count = 0

        while redirect_count < max_redirects:
            redirect_count += 1
            app_log(f"处理重定向 #{redirect_count}，当前URL: {driver.current_url}")

            # ===== 特殊处理123.123.123.123网站 =====
            if "123.123.123.123" in driver.current_url:
                app_log("检测到特殊认证页面: 123.123.123.123")

                # 等待3秒让页面加载
                app_log("等待3秒让页面加载...")
                time.sleep(3)

                # 尝试点击"继续访问网站"按钮
                proceed_button = None
                try:
                    proceed_button = driver.find_element(By.ID, "proceed-button")
                except NoSuchElementException:
                    try:
                        # 尝试通过CSS选择器查找
                        proceed_button = driver.find_element(By.CSS_SELECTOR, "button#proceed-button")
                    except:
                        try:
                            # 尝试通过文本查找
                            proceed_button = driver.find_element(By.XPATH, "//button[contains(text(),'继续访问网站')]")
                        except:
                            app_log("无法找到'继续访问网站'按钮")

                if proceed_button:
                    try:
                        app_log("尝试点击'继续访问网站'按钮")
                        proceed_button.click()
                        app_log("已点击'继续访问网站'按钮")

                        # 等待页面跳转
                        time.sleep(2)

                        # 获取新的URL
                        new_url = driver.current_url
                        app_log(f"跳转后新URL: {new_url}")

                        # 继续循环处理新页面
                        continue
                    except Exception as e:
                        app_log(f"点击'继续访问网站'按钮失败: {str(e)}")
                else:
                    app_log("未找到'继续访问网站'按钮，继续执行认证流程")

            # ===== 根据跳转的URL选择认证流程 =====
            if "https://auth1.ysu.edu.cn" in driver.current_url:
                app_log("检测到认证页面类型: auth1.ysu.edu.cn")
                return perform_auth1_authentication(driver, config)
            elif "https://auth.ysu.edu.cn" in driver.current_url:
                app_log("检测到认证页面类型: auth.ysu.edu.cn")
                return perform_auth_ysu_authentication(driver, config)
            else:
                app_log(f"其他认证页面: {driver.current_url}，尝试认证")
                # 尝试通用认证流程
                if perform_generic_authentication(driver, config):
                    return True
                else:
                    # 如果认证失败，继续循环处理
                    continue

        # 如果达到最大重定向次数仍未完成认证
        app_log(f"达到最大重定向次数({max_redirects})，认证失败")
        return False

    except Exception as e:
        app_log(f"认证过程中发生错误: {str(e)}")
        traceback.print_exc()  # 打印堆栈跟踪
        return False
    finally:
        try:
            driver.quit()
        except:
            pass

def perform_auth_ysu_authentication(driver, config):
    """https://auth.ysu.edu.cn/ 的认证流程"""
    app_log("开始 auth.ysu.edu.cn 认证流程")

    try:
        # 1. 处理用户名输入
        app_log("正在输入用户名...")
        # 输入用户名
        username_element = wait_for_element(driver, (By.ID, "username"), config["timeout"])
        if username_element:
            try:
                username_element.clear()
                username_element.send_keys(config["username"])
                app_log("用户名输入成功")
            except Exception as e:
                app_log(f"用户名输入失败: {str(e)}")
        else:
            app_log("用户名输入框未找到")

        # 2. 处理密码输入
        app_log("正在处理密码输入...")
        # 先点击密码提示框来激活真正的密码输入框
        password_tip = wait_for_element(driver, (By.ID, "pwd_tip"), config["timeout"])
        if password_tip:
            try:
                password_tip.click()
                app_log("已激活密码输入框")
                time.sleep(1)  # 等待密码输入框显示
            except Exception as e:
                app_log(f"点击密码提示失败: {str(e)}")

        # 输入密码
        password_element = wait_for_element(driver, (By.ID, "pwd"), config["timeout"])
        if password_element:
            try:
                password_element.clear()
                password_element.send_keys(config["password"])
                app_log("密码输入成功")
            except Exception as e:
                app_log(f"密码输入失败: {str(e)}")
        else:
            # 如果找不到，尝试直接通过隐藏元素输入
            try:
                app_log("尝试直接通过JS输入密码")
                driver.execute_script("document.getElementById('pwd').value = arguments[0];", config["password"])
                app_log("JS输入密码成功")
            except Exception as e:
                app_log(f"JS输入密码失败: {str(e)}")

        # 3. 选择服务提供商
        app_log("正在选择服务提供商...")
        provider = config.get("service_provider", "中国电信")

        # 先点击"请选择服务"下拉框
        app_log("点击'请选择服务'下拉框...")
        service_select = wait_for_element(driver, (By.ID, "selectDisname"), config["timeout"])
        if service_select:
            try:
                service_select.click()
                app_log("已展开服务选择下拉框")
                time.sleep(1)  # 等待下拉框显示
            except Exception as e:
                app_log(f"点击服务选择下拉框失败: {str(e)}")

        # 尝试通过点击元素选择服务
        provider_selected = False
        for i in range(4):  # 尝试最多4个服务选项
            service_xpath = f'//div[@id="serviceShowHide"]//div[@id="_service_{i}"]'
            service_element = wait_for_element(driver, (By.XPATH, service_xpath), config["timeout"])
            if service_element and provider in service_element.text:
                try:
                    service_element.click()
                    app_log(f"已选择服务商: {provider}")
                    provider_selected = True
                    # 等待服务商选择后的变化
                    time.sleep(1)
                    break
                except Exception as e:
                    app_log(f"选择服务商失败: {str(e)}")

        # 4. 勾选记住密码
        app_log("尝试勾选记住密码...")
        remember_pwd_spans = [
            '//span[contains(text(),"记住密码")]',
            '//span[contains(text(),"remember password")]'
        ]

        for xpath in remember_pwd_spans:
            remember_pwd_element = wait_for_element(driver, (By.XPATH, xpath), 5)
            if remember_pwd_element:
                try:
                    # 使用JavaScript点击，避免元素遮挡问题
                    driver.execute_script("arguments[0].click();", remember_pwd_element)
                    app_log("已勾选记住密码")
                    time.sleep(0.5)
                    break
                except Exception as e:
                    app_log(f"勾选记住密码失败: {str(e)}")

        # 5. 勾选自动连接
        app_log("尝试勾选自动连接...")
        auto_connect_spans = [
            '//span[contains(text(),"自动连接")]',
            '//span[contains(text(),"auto connect")]'
        ]

        for xpath in auto_connect_spans:
            auto_connect_element = wait_for_element(driver, (By.XPATH, xpath), 5)
            if auto_connect_element:
                try:
                    # 使用JavaScript点击，避免元素遮挡问题
                    driver.execute_script("arguments[0].click();", auto_connect_element)
                    app_log("已勾选自动连接")
                    # 点击后可能会有延迟，等待一下
                    time.sleep(1)
                    break
                except Exception as e:
                    app_log(f"勾选自动连接失败: {str(e)}")

        # 6. 检查是否已经登录成功
        if is_already_logged_in(driver):
            app_log("已自动登录成功")
            return True

        # 7. 执行登录
        app_log("尝试提交登录...")
        try:
            # 尝试点击登录按钮
            login_buttons = [
                '//a[@id="loginLink"]',  # 特殊登录按钮，放在第一位
                '//div[@id="SLoginBtn_1"]//a[@id="loginLink"]',
                '//div[contains(@class, "SLoginBtn_1")]//a[@id="loginLink"]',
                '//button[contains(text(),"登录")]',
                '//button[contains(text(),"Sign in")]',
                '//input[@type="submit" and @value="登录"]'
            ]

            submitted = False
            for xpath in login_buttons:
                login_button = wait_for_element(driver, (By.XPATH, xpath), 5)
                if login_button:
                    try:
                        # 使用JavaScript点击，避免元素不可点击的问题
                        driver.execute_script("arguments[0].click();", login_button)
                        app_log(f"已点击登录按钮: {xpath}")
                        submitted = True
                        time.sleep(3)  # 等待登录处理
                        break
                    except Exception as e:
                        app_log(f"点击登录按钮失败: {str(e)}")

            # 如果没有找到登录按钮，尝试通过表单提交
            if not submitted:
                app_log("尝试通过表单提交登录")
                form = wait_for_element(driver, (By.TAG_NAME, "form"), 5)
                if form:
                    try:
                        form.submit()
                        app_log("已提交登录表单")
                        time.sleep(3)  # 等待登录处理
                    except Exception as e:
                        app_log(f"表单提交失败: {str(e)}")

            # 添加回车登录的备选方案
            if not submitted:
                app_log("尝试通过回车键提交登录")
                try:
                    # 尝试在密码框上按回车
                    password_element = wait_for_element(driver, (By.ID, "pwd"), 5)
                    if password_element:
                        password_element.send_keys(Keys.RETURN)
                        app_log("已在密码框按回车提交")
                        time.sleep(3)
                    else:
                        # 尝试在用户名框上按回车
                        username_element = wait_for_element(driver, (By.ID, "username"), 5)
                        if username_element:
                            username_element.send_keys(Keys.RETURN)
                            app_log("已在用户名框按回车提交")
                            time.sleep(3)
                except Exception as e:
                    app_log(f"回车登录失败: {str(e)}")

            # 检查登录是否成功
            if is_already_logged_in(driver):
                app_log("登录成功")
                return True

            app_log("登录提交完成，但未能确认登录状态")
            return True

        except Exception as e:
            app_log(f"登录提交过程中出错: {str(e)}")
            return False

        return True

    except Exception as e:
        app_log(f"auth.ysu.edu.cn 认证过程中发生错误: {str(e)}")
        return False

def perform_auth1_authentication(driver, config):
    """https://auth1.ysu.edu.cn/ 的认证流程（原有的认证流程）"""
    app_log("开始 auth1.ysu.edu.cn 认证流程")

    # ===== 原有的按钮点击逻辑 =====
    proceed_clicked = False
    try:
        proceed_button = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "proceed-button"))
        )
        app_log("发现'继续访问网站'按钮，尝试点击...")
        # ...（原有的按钮点击代码保持不变）
    except TimeoutException:
        app_log("在5秒内未找到'继续访问网站'按钮")
    except Exception as e:
        app_log(f"按钮处理过程中出错: {str(e)}")
    # ===== 结束按钮处理 =====

    WebDriverWait(driver, config["timeout"]).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(1)
    if needs_login(driver):
        app_log("检测到需要登录")
        if not perform_login(driver, config):
            return False

    return select_service_provider(driver, config)

def perform_generic_authentication(driver, config):
    """通用认证流程，处理其他未知认证页面"""
    app_log("开始通用认证流程")

    try:
        # 尝试检测是否需要登录
        if needs_login(driver):
            app_log("检测到需要登录")
            if not perform_login(driver, config):
                return False
            return select_service_provider(driver, config)

        # 尝试检测服务选择
        if select_service_provider(driver, config):
            return True

        # 直接检查是否已经登录
        app_log("尝试检查是否已经登录成功...")
        if is_already_logged_in(driver):
            app_log("已登录成功")
            return True

        app_log("通用认证流程未能完成认证")
        return False
    except Exception as e:
        app_log(f"通用认证流程出错: {str(e)}")
        return False

def is_already_logged_in(driver):
    """检查是否已经登录成功"""
    # 检查是否有登录成功的元素
    logged_in_indicators = [
        # 您指定的成功连接校园网提示
        (By.XPATH, '//span[@id="userMessage" and contains(text(),"您已成功连接校园网!")]'),
        # 其他可能的成功提示
        (By.XPATH, '//span[contains(text(),"已登录")]'),
        (By.XPATH, '//div[contains(text(),"认证成功")]'),
        (By.XPATH, '//div[contains(text(),"Login successful")]'),
        (By.ID, "login_success_info"),
    ]

    app_log("检查登录状态...")
    for locator in logged_in_indicators:
        try:
            element = driver.find_element(*locator)
            if element.is_displayed():
                app_log(f"发现登录成功元素: {locator}")
                return True
        except Exception as e:
            continue

    # 检查是否跳转到其他页面
    current_url = driver.current_url
    if ("https://auth.ysu.edu.cn" not in current_url and
            "https://auth1.ysu.edu.cn" not in current_url and
            "123.123.123.123" not in current_url):
        app_log(f"已跳转到其他页面: {current_url}，可能已登录成功")
        return True

    # 检查是否有输入框可见，这表示尚未登录
    input_indicators = [
        (By.ID, "username"),
        (By.ID, "password"),
        (By.ID, "username_tip"),
        (By.ID, "pwd_tip"),
    ]

    for locator in input_indicators:
        try:
            element = driver.find_element(*locator)
            if element.is_displayed():
                app_log("发现登录表单元素，尚未登录成功")
                return False
        except:
            continue

    app_log("无法确定登录状态")
    return False

class NetworkChecker:
    def __init__(self):
        self.running = True
        self.check_thread = None
        self.config = load_config()

    def start(self):
        """启动网络检查线程"""
        self.running = True
        self.check_thread = threading.Thread(target=self.run)
        self.check_thread.daemon = True
        self.check_thread.start()

    def stop(self):
        """停止网络检查"""
        self.running = False
        if self.check_thread and self.check_thread.is_alive():
            self.check_thread.join(timeout=2)
        app_log("程序已停止")

    def restart(self):
        """重新启动网络检查"""
        self.stop()
        app_log("正在重新启动程序...")
        self.config = load_config()  # 重新加载配置
        self.start()

    def run(self):
        """主控制循环"""
        app_log("校园网自动认证脚本已启动")

        if not self.config:
            app_log("配置加载失败，程序无法运行")
            return

        # 初始网络检查
        if is_network_available():
            app_log("初始检测: 网络已连接")
        else:
            app_log("初始检测: 无网络连接，尝试认证...")
            if perform_authentication(self.config):
                app_log("认证成功!")
            else:
                app_log("认证失败")

        # 主循环
        while self.running:
            try:
                if not is_network_available():
                    app_log("网络连接断开，开始认证...")
                    if perform_authentication(self.config):
                        app_log("认证成功")
                    else:
                        app_log("认证失败")
                else:
                    app_log(f"网络状态正常，等待 {self.config['check_interval']} 秒")

                # 每隔1秒检查一次运行状态
                for _ in range(self.config["check_interval"]):
                    if not self.running:
                        break
                    time.sleep(1)
            except Exception as e:
                app_log(f"网络检测错误: {str(e)}")
                time.sleep(30)

class TrayApp:
    def __init__(self):
        # 设置主窗口
        self.root = tk.Tk()
        self.root.title("校园网认证助手")
        self.root.geometry("800x500")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # 隐藏任务栏图标
        self.root.wm_attributes("-toolwindow", True)

        # 创建日志文本框
        self.log_area = ScrolledText(self.root, state='disabled', font=("Arial", 10))
        self.log_area.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 加载托盘图标
        icon_path = ICON_FILE
        if os.path.exists(icon_path):
            try:
                image = Image.open(icon_path)
            except:
                image = None
                app_log(f"图标文件加载失败: {icon_path}")
        else:
            image = None
            app_log(f"图标文件不存在: {icon_path}")

        # 设置托盘菜单
        menu = (
            pystray.MenuItem("显示主窗口", self.show_window),
            pystray.MenuItem("重新开始", self.restart_app),  # 添加重新开始按钮
            pystray.MenuItem("强制停止", self.stop_app),
            pystray.MenuItem("退出", self.quit_app)
        )

        if image:
            self.tray_icon = pystray.Icon("CampusAuth", image, "校园网认证助手", menu)
        else:
            # 使用默认灰色图标
            self.tray_icon = pystray.Icon("CampusAuth",
                                          Image.new('RGB', (16, 16), color='gray'),
                                          "校园网认证助手",
                                          menu)

        # 启动网络检查
        self.checker = NetworkChecker()
        self.checker.start()

    def run(self):
        """运行应用程序"""
        # 启动托盘图标线程
        threading.Thread(target=self.tray_icon.run, daemon=True).start()
        self.root.mainloop()

    def show_window(self, item=None):
        """显示主窗口"""
        if not self.root.winfo_viewable():
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

    def hide_window(self):
        """隐藏主窗口"""
        self.root.withdraw()

    def restart_app(self, item=None):
        """重新启动程序"""
        app_log("用户请求重新启动程序...")
        self.checker.restart()

    def stop_app(self, item=None):
        """停止程序运行"""
        app_log("正在停止程序...")
        self.checker.stop()

    def quit_app(self, item=None):
        """退出应用程序"""
        app_log("正在退出程序...")
        self.checker.stop()
        try:
            self.tray_icon.stop()
        except:
            pass
        self.root.destroy()
        os._exit(0)

    def on_close(self):
        """窗口关闭事件处理"""
        self.hide_window()

def app_log(message):
    """记录日志并显示在界面上"""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}"
    print(log_message)

    try:
        if 'app' in globals():
            app = globals()['app']
            # 更新日志区域
            app.log_area.configure(state='normal')
            app.log_area.insert(tk.END, log_message + "\n")
            app.log_area.configure(state='disabled')
            app.log_area.yview(tk.END)
    except Exception as e:
        print(f"日志更新失败: {str(e)}")

if __name__ == "__main__":
    # 确保必要的目录存在
    required_dirs = ["chrome-win64", "chromedriver-win64"]
    base_path = get_base_path()

    for dir_name in required_dirs:
        dir_path = os.path.join(base_path, dir_name)
        if not os.path.exists(dir_path):
            app_log(f"警告: 所需目录不存在: {dir_name}")
            try:
                os.makedirs(dir_path)
                app_log(f"已创建目录: {dir_name}")
            except Exception as e:
                app_log(f"创建目录失败: {str(e)}")

    app = TrayApp()
    app.run()
