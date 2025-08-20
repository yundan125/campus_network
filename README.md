校园网自动认证工具

项目简介

这是一个基于Python的校园网自动认证工具，专为燕山大学校园网环境设计。该工具能够自动检测网络连接状态，在断开时自动执行认证流程，无需人工干预。支持两种认证页面（auth.ysu.edu.cn和auth1.ysu.edu.cn），并能处理123.123.123.123由于HTTPS安全认证错误的特殊跳转页面。

功能特点

• 自动网络检测：定期检查网络连接状态

• 智能认证流程：自动识别认证页面类型并执行相应操作

• 多页面支持：支持auth.ysu.edu.cn和auth1.ysu.edu.cn两种认证页面

• 特殊跳转处理：自动处理123.123.123.123的"继续访问网站"按钮

• 系统托盘图标：后台运行，提供便捷操作入口

• 日志记录：详细记录操作过程，便于调试

• 配置文件管理：通过config.json轻松配置账号信息

运行环境要求

• 操作系统：Windows 10/11

• Python：3.8+

• 依赖库（打包程序中不出意外的话已经打包所有依赖库）：

  • selenium

  • pystray

  • Pillow

  • requests

  • tkinter

安装指南

1. 克隆仓库

git clone https://github.com/yourusername/campus-network-auth.git
cd campus-network-auth


2. 安装依赖

pip install -r requirements.txt


4. 配置账号信息（不要删除双引号，check_interval为检测是否有网络连接的周期时间（以秒为单位），timeout是各种等待操作的最大超时时间（以秒为单位））

编辑config.json文件：
{
  "username": "学号",
  "password": "密码",
  "portal_url": "http://123.123.123.123",
  "service_provider": "你的服务商（如中国电信、中国移动、中国联通、校园网）",
  "check_interval": 60,
  "timeout": 15
}


使用说明

运行程序

压缩包中的exe可执行程序


系统托盘操作

程序启动后会在系统托盘显示图标：
• 左键点击：显示/隐藏主窗口

• 右键菜单：

  • 显示主窗口

  • 重新开始

  • 强制停止

  • 退出

主窗口功能

主窗口显示详细日志信息：
• 实时显示网络状态

• 记录认证过程

• 显示错误信息

配置文件说明

config.json文件包含以下配置项：

配置项 说明 示例值

username 校园网账号（学号） "202312013456"

password 校园网密码 "your_password"

portal_url 认证入口URL "http://123.123.123.123"

service_provider 服务提供商 "中国电信"、"中国移动"、"中国联通"、"校园网"

check_interval 网络检查间隔（秒） 60

timeout 操作超时时间（秒） 15

打包为可执行文件



贡献指南

欢迎贡献代码！请遵循以下步骤：
1. Fork仓库
2. 创建新分支：git checkout -b feature/your-feature
3. 提交更改：git commit -m 'Add some feature'
4. 推送到分支：git push origin feature/your-feature
5. 提交Pull Request

联系方式

如有任何问题或建议，请联系：
• 邮箱：2693327171@qq.com

• GitHub Issues：https://github.com/yundan125/campus_network/issues

注意：本项目仅用于学习和技术交流，请遵守学校网络使用规定。
