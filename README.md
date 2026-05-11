## 项目更新说明
### 关注我的哔哩哔哩 (Follow me on Bilibili)
📺 [我的哔哩哔哩主页](https://space.bilibili.com/30070651) - 获取更多 ComfyUI 相关教程和内容
节点讲解视频：
B站：https://www.bilibili.com/video/BV1L85762E6z
YouTube:https://youtu.be/iC2bpHGVzZc
### 优化功能
筛选逻辑在处理数字类型时，采用精准匹配（例如数字ID筛选，筛选条件为ID+1时，不会影响ID=10/21这些行），其余类型仍旧使用包含匹配（2026.05.05更新）
### 新增功能
多媒体上传节点支持音频上传，优化缓存逻辑（2026.05.04更新）
1. 多媒体上传节点支持音频上传
   - 新增 audio_input 输入端口，与视频、图片互斥
   - 支持 ComfyUI 标准 AUDIO 格式转换
2. 读取节点缓存逻辑优化
   - 图片、音频、视频、文本节点均设置为每次读取最新内容
### 新增功能
- 音频获取节点 ：新增 "获取音频（飞书多维表格）" 节点，支持从飞书多维表格中读取音频文件
- 完整的音频处理 ：支持多种音频格式（mp3、wav、aac、flac、ogg、wma、m4a）
- 与现有节点一致的使用体验 ：支持相同的筛选语法和参数配置
### 使用方法
1. 配置飞书API ：使用 "配置节点（飞书）" 填写应用信息
2. 添加音频节点 ：在 "飞书工具" 分类中找到 "获取音频（飞书多维表格）" 节点
3. 设置参数 ：
   - 连接飞书配置
   - 指定目标列名（默认："音频"）
   - 设置筛选条件（可选）
   - 选择音频索引
   - 配置提取列名（可选）
4. 连接工作流 ：将音频输出连接到其他音频处理节点
### 兼容性说明
- 保持与原项目完全兼容
- 音频节点使用ComfyUI标准音频格式，可直接与其他音频处理节点配合使用
### 项目地址
- GitHub： https://github.com/wjc573/comfyui-feishu-table
- 基于原项目： https://github.com/loobayn/comfyui-feishu-table

### 以下为原项目的简介

# ComfyUI 飞书多维表格插件

这是一个用于ComfyUI的飞书多维表格集成插件，支持读取、写入、上传图片和获取图片等功能。

## 功能特性

- **飞书多维表格节点**: 读取表格数据，支持筛选和多种输出格式
- **飞书多维表格写入节点**: 将文本写入指定单元格，支持筛选条件
- **飞书多维表格附件上传节点**: 上传图片到表格，支持筛选和添加新行
- **飞书图片获取节点**: 从表格中获取图片，支持筛选和索引选择
- **飞书配置节点**: 集中管理飞书API配置



## 安装方法

### 方法一：通过 ComfyUI Manager 安装（推荐）
1. 打开 ComfyUI Manager
2. 搜索 "Feishu Table Integration"
3. 点击安装并重启 ComfyUI

### 方法二：Git Clone 安装
```bash
# 进入 ComfyUI 的 custom_nodes 目录
cd ComfyUI/custom_nodes/

# 克隆仓库
git clone https://github.com/loobayn/comfyui-feishu-table.git

# 安装依赖
cd comfyui-feishu-table
pip install -r requirements.txt
```

### 方法三：手动安装
1. 下载本仓库的 ZIP 文件
2. 解压到 `ComfyUI/custom_nodes/` 目录
3. 重启 ComfyUI

## 使用方法

### 📖 可视化使用指南
![使用指南](https://github.com/loobayn/comfyui-feishu-table/blob/main/usage_guide.jpg)

### 第一步：配置飞书 API
1. 在 ComfyUI 节点列表中找到 **"飞书工具"** 分类
2. 添加 **"配置节点（飞书）"** 到工作流
3. 填入你的飞书应用信息：
   - **App ID**: 飞书应用的 App ID
   - **App Secret**: 飞书应用的 App Secret
   - **多维表格链接**: 直接粘贴飞书多维表格的分享链接（节点会自动提取 App Token 和 Table ID）

### 第二步：使用功能节点

#### 📖 读取表格数据
- 使用 **"获取文本（飞书多维表格）"** 节点
- 连接配置节点
- 设置筛选条件（可选）
- 选择输出格式（文本/JSON/列表等）

#### ✏️ 写入表格数据
- 使用 **"写入文本（飞书多维表格）"** 节点
- 连接配置节点和文本输入
- 指定要写入的字段名
- 设置筛选条件定位目标行

#### 🖼️ 处理图片
- **上传图片**: 使用 **"上传多媒体（飞书多维表格）"** 节点
- **获取图片**: 使用 **"获取图片（飞书多维表格）"** 节点
- 支持筛选条件和索引选择

#### 🎬 处理视频
- **获取视频**: 使用 **"获取视频（飞书多维表格）"** 节点
- 支持从表格中提取视频文件

#### 🔍 文本筛选
- 使用 **"文本筛选（飞书）"** 节点
- 对获取的文本数据进行进一步处理和筛选

### 第三步：连接工作流
将各个节点按需连接，构建完整的数据处理工作流。配置节点可以同时连接多个功能节点，实现复杂的数据操作。

## 筛选条件语法说明

本插件支持强大的筛选功能，可以精确定位和操作表格数据：

### 📋 列名筛选
在 **"筛选列名"** 字段中，每行输入一个列名，指定要输出的列：
```
文本
内容  
进度
状态
```

### 🔍 行筛选条件
在 **"筛选条件"** 字段中，使用以下语法筛选行：

#### 包含筛选（+）
- `列名+关键词` - 仅包含该列包含关键词的行
- `列名+非空值` - 仅包含该列非空的行

#### 排除筛选（-）
- `列名-关键词` - 排除该列包含关键词的行  
- `列名-空值` - 排除该列为空的行
- `列名-非空值` - 排除该列非空的行

#### 筛选示例
```
进度+完成          # 只显示"进度"列包含"完成"的行
状态-空值          # 排除"状态"列为空的行
类型+非空值        # 只显示"类型"列有内容的行
备注-已处理        # 排除"备注"列包含"已处理"的行
```

#### 组合筛选
可以同时使用多个筛选条件，每行一个：
```
状态+进行中
优先级+高
负责人+非空值
备注-已完成
```

### 💡 筛选技巧
- **留空筛选列名**：将不返回任何数据
- **留空筛选条件**：返回所有行的指定列
- **多条件组合**：所有条件都必须满足（AND 逻辑）
- **关键词匹配**：支持部分匹配，不区分大小写



---

## ⚖️ 免责声明与安全警告 (Disclaimer & Security Warning)

### ⚠️ 重要安全提醒

**密钥存储风险**：本节点设计的 AppID 和 AppSecret 会存储在 ComfyUI 的工作流（Workflow）数据中。

**分享提示**：当您将保存了密钥的工作流（JSON 或带有元数据的图片）分享给他人时，您的飞书 API 凭证也会随之泄露。请在分享工作流前务必清除相关敏感信息。

### 免责声明

**非官方关联**： 本项目是一个独立开发的开源节点，与飞书（Feishu/Lark）及其母公司字节跳动无官方关联。作者尊重并维护飞书的相关知识产权。

**合规性警告**： 用户在使用本节点连接飞书多维表格时，必须遵守飞书的《开发者服务协议》及相关 API 使用规范。严禁将本工具用于任何违反法律法规、干扰飞书正常服务或侵犯他人隐私的行为。

**无担保责任**：本软件按"原样"提供。作者不对因使用本软件（包括但不限于密钥泄露、数据意外删除、账号封禁）引起的任何损害承担责任。

**隐私说明**：本节点不会向第三方服务器上传您的任何凭证。所有凭证仅存在于您本地生成的工作流文件中。

---

### ⚠️ Important Security Notice

**Credential Storage Risk**: The AppID and AppSecret entered into this node are stored in plain text within the ComfyUI workflow data.

**Sharing Risks**: If you share your workflow files (either the .json file or .png images with embedded metadata), your Feishu API credentials will be exposed to whoever receives the file.

**Safety Recommendation**: Always remove your Feishu configuration nodes or clear the sensitive fields before sharing your workflows publicly.

### Disclaimer

**Non-Affiliation**: This project is an independent open-source tool and is NOT officially affiliated with Feishu (Lark) or ByteDance. The author respects and upholds all relevant intellectual property rights of Feishu.

**Compliance**: Users are strictly required to comply with the Feishu Developer Service Agreement and relevant API usage policies. Use of this tool for illegal activities, privacy infringement, or interference with Feishu services is strictly prohibited.

**Limitation of Liability**: This software is provided "AS IS", without warranty of any kind. The author shall not be held liable for any claims, damages, or other liabilities arising from the use of this software, including but not limited to credential leakage, accidental data loss or corruption, or account suspension.

**Privacy Commitment**: This node runs entirely on the client side. It does not upload your credentials to any third-party servers. All sensitive data remains strictly within your locally generated workflow files.

---

## ☕️ 支持与捐赠 (Support & Donation)

如果本工具为您的工作带来了便利，不妨请我喝杯咖啡！您的支持是我持续更新的动力。💖

If this tool has improved your productivity or simplified your workflow, feel free to buy me a coffee! Your support keeps me motivated to continue maintaining and updating this project. 💖

### 关注我的哔哩哔哩 (Follow me on Bilibili)
📺 [我的哔哩哔哩主页](https://space.bilibili.com/345888235) - 获取更多 ComfyUI 相关教程和内容

### 捐赠支持 (Donation)
![支持二维码](./donation-qr.jpg)

---

## 许可证

MIT License
