"""
ComfyUI 飞书多维表格插件
用于获取飞书多维表格内容并进行筛选的节点
"""

from .feishu_table_node import FeishuTableNode
from .feishu_write_node import FeishuWriteNode

from .feishu_fetch_image_node import FeishuFetchImageNode
from .feishu_fetch_video_node import FeishuFetchVideoNode
from .feishu_fetch_audio_node import FeishuFetchAudioNode
from .feishu_config_node import FeishuConfigNode
from .feishu_text_editor_node import FeishuTextEditorNode
from .feishu_video_upload_node import FeishuVideoUploadNode

# 节点类映射
NODE_CLASS_MAPPINGS = {
    "FeishuTableNode": FeishuTableNode,
    "FeishuWriteNode": FeishuWriteNode,

    "FeishuFetchImageNode": FeishuFetchImageNode,
    "FeishuFetchVideoNode": FeishuFetchVideoNode,
    "FeishuFetchAudioNode": FeishuFetchAudioNode,
    "FeishuConfigNode": FeishuConfigNode,
    "FeishuTextEditorNode": FeishuTextEditorNode,
    "FeishuVideoUploadNode": FeishuVideoUploadNode
}

# 节点显示名称映射
NODE_DISPLAY_NAME_MAPPINGS = {
    "FeishuTableNode": "获取文本（飞书多维表格）",
    "FeishuWriteNode": "写入文本（飞书多维表格）",

    "FeishuFetchImageNode": "获取图片（飞书多维表格）",
    "FeishuFetchVideoNode": "获取视频（飞书多维表格）",
    "FeishuFetchAudioNode": "获取音频（飞书多维表格）",
    "FeishuConfigNode": "配置节点（飞书）",
    "FeishuTextEditorNode": "文本筛选（飞书）",
    "FeishuVideoUploadNode": "上传多媒体（飞书多维表格）"
}

# 设置web目录，用于前端扩展
WEB_DIRECTORY = "./js"

# 导出所有内容
__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']
