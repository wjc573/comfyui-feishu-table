"""
飞书多维表格视频获取节点
从指定列（附件/视频字段）中按筛选条件获取视频，下载到本地临时目录，
并输出为 VIDEO（可预览）+ 状态信息 + 提取的文本内容。
支持与其它节点一致的筛选语法：列名+关键词 / 列名-关键词 / 列名+非空值 / 列名-空值 / 列名-非空值
"""

from typing import Any, Dict, List, Optional, Tuple
import io
import json
import os
import re
import tempfile
from urllib.parse import urlparse, parse_qs

import requests


# 依赖按需导入（用于视频解码预览）
try:
    import torch
except Exception:
    torch = None
try:
    import numpy as np
except Exception:
    np = None

AV_AVAILABLE = False
AV_MODULE = None
try:
    import av as _av
    AV_AVAILABLE = True
    AV_MODULE = _av
except Exception:
    AV_AVAILABLE = False


class FeishuFetchVideoNode:
    """飞书多维表格视频获取节点"""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "飞书配置": ("FEISHU_CONFIG",),
                "目标列名": ("STRING", {"default": "视频", "multiline": False}),
                "筛选条件": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "筛选条件（每行一条）：\n列名+关键词 / 列名-关键词 / 列名+非空值 / 列名-空值 / 列名-非空值"
                }),
                "视频索引": ("INT", {
                    "default": 1,
                    "min": 1,
                    "max": 64,
                    "step": 1,
                    "label": "选择第几个视频"
                }),
                "提取列名": ("STRING", {
                    "default": "",
                    "multiline": True,
                    "placeholder": "要提取的其他列名（每行一个），如：\n任务\n状态\n备注\n\n留空则不提取其他内容"
                }),
            },
            "optional": {
                "列分隔符": ("STRING", {
                    "multiline": True,
                    "default": " | ",
                    "placeholder": "自定义列分隔符，默认为 ' | '。例如：\n- 使用逗号：, \n- 使用分号：; \n- 使用制表符：\\t\n- 使用换行：\\n\n- 使用自定义符号：→\n- 使用多个字符：---\n- 留空则使用默认分隔符"
                })
            }
        }

    RETURN_TYPES = ("VIDEO", "STRING", "STRING", "IMAGE")
    RETURN_NAMES = ("视频", "状态信息", "提取的内容", "使用说明")
    FUNCTION = "fetch_videos"
    CATEGORY = "飞书工具"
    OUTPUT_NODE = True

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # 返回时间戳，让ComfyUI每次都重新执行（每次获取最新）
        import time
        return str(time.time())

    # =============== 基础 API ===============
    def get_access_token(self, app_id: str, app_secret: str) -> Optional[str]:
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            payload = {"app_id": app_id, "app_secret": app_secret}
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 0:
                return data.get("tenant_access_token")
            return None
        except Exception:
            return None

    def extract_table_info(self, table_url: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            parsed = urlparse(table_url)
            path_parts = parsed.path.split('/')
            app_id = None
            if 'base' in path_parts:
                idx = path_parts.index('base')
                if len(path_parts) > idx + 1:
                    app_id = path_parts[idx + 1]
            table_id = parse_qs(parsed.query).get('table', [None])[0]
            return app_id, table_id
        except Exception:
            return None, None

    def get_table_records(self, access_token: str, app_id: str, table_id: str, page_size: int = 100) -> List[Dict]:
        records: List[Dict] = []
        try:
            url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_id}/tables/{table_id}/records"
            params: Dict[str, Any] = {"page_size": page_size}
            headers = {"Authorization": f"Bearer {access_token}"}
            while True:
                r = requests.get(url, headers=headers, params=params, timeout=30)
                if r.status_code != 200:
                    break
                j = r.json()
                if j.get('code') != 0:
                    break
                batch = j.get('data', {}).get('items', [])
                records.extend(batch)
                page_token = j.get('data', {}).get('page_token')
                if not page_token:
                    break
                params["page_token"] = page_token
        except Exception:
            pass
        return records

    # =============== 筛选 ===============
    def _is_empty_value(self, v: Any) -> bool:
        if v is None:
            return True
        if isinstance(v, str) and not v.strip():
            return True
        if isinstance(v, list) and len(v) == 0:
            return True
        if isinstance(v, dict):
            text_content = v.get('text', '') or v.get('name', '') or str(v)
            return not text_content or not text_content.strip()
        return False

    def _value_contains(self, v: Any, needle: str) -> bool:
        if v is None:
            return False
        needle_l = str(needle).lower()
        if isinstance(v, list):
            return any(needle_l in str(x).lower() for x in v)
        if isinstance(v, dict):
            text_content = v.get('text', '') or v.get('name', '') or str(v)
            return needle_l in text_content.lower()
        return needle_l in str(v).lower()

    def _check_condition(self, v: Any, cond: str) -> bool:
        if cond == "空值":
            return self._is_empty_value(v)
        if cond == "非空值":
            return not self._is_empty_value(v)
        return self._value_contains(v, cond)

    def filter_records(self, records: List[Dict], filter_condition: str) -> List[Dict]:
        if not filter_condition.strip():
            return records
        include_conds: List[Tuple[str, str]] = []
        exclude_conds: List[Tuple[str, str]] = []
        for raw in filter_condition.strip().split('\n'):
            line = raw.strip()
            if not line:
                continue
            m = re.match(r"^\s*([^+\-=\s]+)\s*([+-])\s*(.+?)\s*$", line)
            if m:
                col = m.group(1).strip()
                op = m.group(2)
                val = m.group(3).strip()
                (include_conds if op == '+' else exclude_conds).append((col, val))
                continue
            if '=' in line:
                col, val = line.split('=', 1)
                include_conds.append((col.strip(), val.strip()))

        out: List[Dict] = []
        for rec in records:
            fields = rec.get('fields', {})
            ok_inc = True
            if include_conds:
                for col, val in include_conds:
                    if not self._check_condition(fields.get(col, None), val):
                        ok_inc = False
                        break
            if not ok_inc:
                continue
            hit_exc = False
            for col, val in exclude_conds:
                if self._check_condition(fields.get(col, None), val):
                    hit_exc = True
                    break
            if not hit_exc:
                out.append(rec)
        return out

    # =============== 下载视频 ===============
    def _get_tmp_download_urls(self, access_token: str, file_tokens: List[str], table_id: str) -> Dict[str, str]:
        if not file_tokens:
            return {}
        try:
            url = "https://open.feishu.cn/open-apis/drive/v1/medias/batch_get_tmp_download_url"
            params = {
                "file_tokens": ",".join(file_tokens),
                "extra": json.dumps({"bitablePerm": {"tableId": table_id, "rev": 5}})
            }
            headers = {"Authorization": f"Bearer {access_token}"}
            response = requests.get(url, headers=headers, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == 0:
                    tmp_urls: Dict[str, str] = {}
                    items = data.get("data", {}).get("tmp_download_urls", [])
                    for item in items:
                        ft = item.get("file_token")
                        tu = item.get("tmp_download_url")
                        if ft and tu:
                            tmp_urls[ft] = tu
                    return tmp_urls
        except Exception:
            pass
        return {}

    def _download_file_by_tmp_url(self, tmp_url: str) -> Optional[bytes]:
        try:
            response = requests.get(tmp_url, timeout=120, allow_redirects=True)
            if response.status_code == 200 and response.content:
                return response.content
        except Exception:
            pass
        return None

    def _download_file_by_file_token(self, access_token: str, file_token: str) -> Optional[bytes]:
        headers = {"Authorization": f"Bearer {access_token}"}
        # 依次尝试三种路径
        urls = [
            ("https://open.feishu.cn/open-apis/drive/v1/files/download", {"file_token": file_token}),
            (f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download", None),
            (f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download", None),
        ]
        for base, params in urls:
            try:
                resp = requests.get(base, headers=headers, params=params, timeout=120, allow_redirects=True)
                if resp.status_code == 200 and resp.content:
                    return resp.content
            except Exception:
                continue
        return None

    def _gather_video_tokens(self, records: List[Dict], target_column: str) -> List[Dict]:
        video_exts = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.gif', '.webp')
        result: List[Dict] = []
        for rec in records:
            fields = rec.get('fields', {})
            val = fields.get(target_column)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict) and item.get('file_token'):
                        name = item.get('name') or ''
                        if not name or os.path.splitext(name)[1].lower() in video_exts:
                            result.append({
                                'file_token': item['file_token'],
                                'name': name or f"{item['file_token']}.mp4",
                                'record': rec,
                                'fields': fields
                            })
        return result

    # =============== 构造 VIDEO ===============
    class _VideoFromPath:
        def __init__(self, file_path: str):
            self.file_path = file_path
            self._components_cache = None
            self._dimensions_cache = None

        def get_dimensions(self):
            """获取视频的宽度和高度，ComfyUI的SaveVideo节点需要此方法"""
            if self._dimensions_cache is not None:
                return self._dimensions_cache
            
            # 如果没有PyAV等依赖，返回默认尺寸
            if not AV_AVAILABLE or AV_MODULE is None:
                self._dimensions_cache = (1920, 1080)  # 默认1080p尺寸
                return self._dimensions_cache
            
            try:
                with AV_MODULE.open(self.file_path, mode='r') as container:
                    video_streams = [s for s in container.streams if s.type == 'video']
                    if not video_streams:
                        self._dimensions_cache = (1920, 1080)  # 默认尺寸
                        return self._dimensions_cache
                    
                    video_stream = video_streams[0]
                    width = video_stream.width or 1920
                    height = video_stream.height or 1080
                    self._dimensions_cache = (width, height)
                    return self._dimensions_cache
            except Exception:
                # 出错时返回默认尺寸
                self._dimensions_cache = (1920, 1080)
                return self._dimensions_cache

        def get_components(self):
            if self._components_cache is not None:
                return self._components_cache
            # 无依赖时提供占位，避免节点报错；预览需安装 PyAV+Torch+NumPy
            if not AV_AVAILABLE or AV_MODULE is None or torch is None or np is None:
                from fractions import Fraction
                self._components_cache = {
                    "images": None,
                    "audio": None,
                    "frame_rate": Fraction(30, 1),
                    "metadata": {"file_path": self.file_path},
                }
                return self._components_cache
            from fractions import Fraction
            try:
                with AV_MODULE.open(self.file_path, mode='r') as container:
                    video_streams = [s for s in container.streams if s.type == 'video']
                    if not video_streams:
                        raise Exception("未找到视频流")
                    video_stream = video_streams[0]
                    frames = []
                    for frame in container.decode(video=0):
                        arr = frame.to_ndarray(format='rgb24')
                        img = torch.from_numpy(arr).float() / 255.0
                        frames.append(img)
                        if len(frames) >= 300:  # 保护性上限，避免超长视频卡住
                            break
                    images = torch.stack(frames) if len(frames) > 0 else torch.zeros(0, 3, 0, 0)
                    frame_rate = Fraction(video_stream.average_rate) if video_stream.average_rate else Fraction(30, 1)
                    self._components_cache = {
                        "images": images,
                        "audio": None,
                        "frame_rate": frame_rate,
                        "metadata": {
                            "file_path": self.file_path,
                            "frame_count": len(frames),
                            "resolution": f"{video_stream.width}x{video_stream.height}",
                        },
                    }
                    return self._components_cache
            except Exception:
                self._components_cache = {
                    "images": None,
                    "audio": None,
                    "frame_rate": Fraction(30, 1),
                    "metadata": {"file_path": self.file_path},
                }
                return self._components_cache

        def save_to(self, output_path: str, format=None, codec=None, metadata=None):
            """保存视频到指定路径，ComfyUI的SaveVideo节点需要此方法"""
            import shutil
            try:
                # 简单的文件复制，保持原始格式
                shutil.copy2(self.file_path, output_path)
            except Exception as e:
                # 如果复制失败，尝试使用PyAV重新编码（如果可用）
                if AV_AVAILABLE and AV_MODULE is not None:
                    try:
                        with AV_MODULE.open(self.file_path, mode='r') as input_container:
                            with AV_MODULE.open(output_path, mode='w') as output_container:
                                # 复制视频流
                                input_stream = input_container.streams.video[0]
                                output_stream = output_container.add_stream('libx264', rate=input_stream.rate)
                                output_stream.width = input_stream.width
                                output_stream.height = input_stream.height
                                output_stream.pix_fmt = 'yuv420p'
                                
                                # 添加元数据
                                if metadata:
                                    for key, value in metadata.items():
                                        if isinstance(value, dict):
                                            output_container.metadata[key] = json.dumps(value)
                                        else:
                                            output_container.metadata[key] = str(value)
                                
                                # 复制帧
                                for frame in input_container.decode(video=0):
                                    for packet in output_stream.encode(frame):
                                        output_container.mux(packet)
                                
                                # 刷新编码器
                                for packet in output_stream.encode():
                                    output_container.mux(packet)
                    except Exception:
                        # 如果PyAV也失败了，至少尝试简单复制
                        shutil.copy2(self.file_path, output_path)

    def _load_usage_image(self):
        """加载使用说明图片（从节点目录中加载）"""
        import os
        from PIL import Image
        
        # 从节点目录中加载图片
        current_dir = os.path.dirname(__file__)
        usage_image_path = os.path.join(current_dir, "usage_guide.jpg")
        
        try:
            # 检查文件是否存在
            if os.path.exists(usage_image_path):
                # 加载图片
                img = Image.open(usage_image_path)
                if img.mode != 'RGB':
                    img = img.convert('RGB')
                
                print(f"✅ 成功加载使用说明图片: {usage_image_path}, 尺寸: {img.width}x{img.height}")
                
                # 转换为tensor
                return self._to_single_image(img)
            else:
                print(f"⚠️ 使用说明图片不存在: {usage_image_path}")
                # 如果文件不存在，返回一个带文字的占位图片
                return self._create_placeholder_usage_image()
                
        except Exception as e:
            print(f"❌ 加载使用说明图片失败: {str(e)}")
            # 出错时返回占位图片
            return self._create_placeholder_usage_image()

    def _create_placeholder_usage_image(self):
        """创建一个带文字的占位使用说明图片"""
        from PIL import Image, ImageDraw, ImageFont
        import torch
        import numpy as np
        
        try:
            # 创建一个白色背景的图片
            width, height = 400, 300
            img = Image.new('RGB', (width, height), color='white')
            draw = ImageDraw.Draw(img)
            
            # 尝试使用系统字体，如果失败则使用默认字体
            try:
                # Windows系统字体
                font = ImageFont.truetype("msyh.ttc", 20)  # 微软雅黑
            except:
                try:
                    font = ImageFont.truetype("arial.ttf", 20)
                except:
                    font = ImageFont.load_default()
            
            # 绘制文字
            text_lines = [
                "使用说明图片",
                "",
                "图片文件路径:",
                "节点目录/usage_guide.jpg",
                "",
                "图片文件缺失，请联系开发者"
            ]
            
            y_offset = 50
            for line in text_lines:
                # 计算文字位置（居中）
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                draw.text((x, y_offset), line, fill='black', font=font)
                y_offset += 30
            
            print("✅ 创建了占位使用说明图片")
            return self._to_single_image(img)
            
        except Exception as e:
            print(f"❌ 创建占位图片失败: {str(e)}")
            # 最后的备用方案：返回纯色图片
            return torch.zeros((1, 300, 400, 3), dtype=torch.float32)

    def _to_single_image(self, image):
        """将单张图片转换为tensor"""
        if image is None:
            return torch.zeros((1, 64, 64, 3), dtype=torch.float32)
        
        # 直接转换原始图片，不进行任何缩放
        arr = np.asarray(image).astype(np.float32) / 255.0
        tensor = torch.from_numpy(arr)
        
        # 添加批次维度 (H, W, C) -> (1, H, W, C)
        return tensor.unsqueeze(0)

    def _save_temp_video(self, data: bytes, suggested_name: str) -> str:
        # 使用 ComfyUI 的临时目录（与图片、音频节点保持一致）
        try:
            import folder_paths
            temp_dir = folder_paths.get_temp_directory()
        except Exception:
            temp_dir = tempfile.gettempdir()
        
        ext = os.path.splitext(suggested_name)[1].lower() or ".mp4"
        safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]+", "_", os.path.splitext(suggested_name)[0])
        file_path = os.path.join(temp_dir, f"feishu_video_{safe_name}{ext}")
        # 若同名存在，创建唯一临时文件
        if os.path.exists(file_path):
            fd, tmp = tempfile.mkstemp(suffix=ext, prefix="feishu_video_")
            os.close(fd)
            file_path = tmp
        with open(file_path, 'wb') as f:
            f.write(data)
        return file_path

    def _extract_single_record_content(self, video_record: Dict, extract_columns: str, column_separator: str = " | ") -> str:
        """提取单条记录的其他列内容，使用与获取文本节点相同的格式"""
        if not extract_columns.strip():
            return ""
        
        # 兼容多种分隔符：英文逗号, 中文逗号，顿号、英文/中文分号，以及换行/回车
        parts = re.split(r"[\,\uFF0C\u3001;\uFF1B\n\r]+", extract_columns.strip())
        column_names = [col.strip() for col in parts if col.strip()]
        if not column_names:
            return ""
        
        fields = video_record['fields']
        record_index = 1  # 视频节点只处理单条记录，所以索引固定为1
        
        # 使用与获取文本节点相同的格式，字段内容用***标记
        line_parts = []
        for col_name in column_names:
            if col_name in fields:
                value = fields[col_name]
                if value is None or value == "" or (isinstance(value, list) and len(value) == 0):
                    line_parts.append(f"获取结果{record_index}&{col_name}***(空)***")
                elif isinstance(value, list):
                    # 处理列表类型字段（如富文本、附件等）
                    if value and isinstance(value[0], dict):
                        # 富文本或附件字段
                        if 'text' in value[0]:
                            text_content = ', '.join([item.get('text', '') for item in value if item.get('text')])
                            line_parts.append(f"获取结果{record_index}&{col_name}***({text_content})***")
                        elif 'name' in value[0]:
                            # 附件字段
                            names = [item.get('name', '') for item in value if item.get('name')]
                            line_parts.append(f"获取结果{record_index}&{col_name}***({', '.join(names)})***")
                        else:
                            line_parts.append(f"获取结果{record_index}&{col_name}***({str(value)})***")
                    else:
                        # 普通列表
                        content = ', '.join(map(str, value))
                        line_parts.append(f"获取结果{record_index}&{col_name}***({content})***")
                else:
                    # 普通字段
                    line_parts.append(f"获取结果{record_index}&{col_name}***({value})***")
            else:
                line_parts.append(f"获取结果{record_index}&{col_name}***(空)***")
        
        # 使用分隔符连接各列数据，并添加结尾标识
        line_content = column_separator.join(line_parts)
        return f"{line_content}&获取结果{record_index}#"

    # =============== 主入口 ===============
    def fetch_videos(self, 飞书配置: dict, 目标列名: str, 筛选条件: str,
                     视频索引: int, 提取列名: str = "", 列分隔符: str = " | ") -> Tuple[Any, str, str]:
        # 配置
        app_id = 飞书配置.get("app_id", "")
        app_secret = 飞书配置.get("app_secret", "")
        table_url = 飞书配置.get("table_url", "")
        url_app_id = 飞书配置.get("url_app_id", "")
        table_id = 飞书配置.get("table_id", "")

        if not app_id or not app_secret or not table_url:
            return None, "错误：配置信息不完整，请检查飞书配置节点", ""
        if not url_app_id or not table_id:
            return None, "错误：表格链接格式无效，请检查飞书配置节点", ""

        # 1. token
        token = self.get_access_token(app_id, app_secret)
        if not token:
            return None, "错误：无法获取访问令牌", ""

        # 2. 拉取记录并筛选
        records = self.get_table_records(token, url_app_id, table_id)
        if not records:
            return None, "错误：未获取到任何记录", ""
        filtered = self.filter_records(records, 筛选条件)
        if not filtered:
            return None, "错误：筛选条件未匹配到记录", ""

        # 3. 收集视频 token
        all_video_records = self._gather_video_tokens(filtered, 目标列名)
        if not all_video_records:
            return None, "错误：目标列未找到任何视频附件", ""

        # 4. 按序选择
        if 视频索引 > len(all_video_records):
            return None, f"错误：视频索引 {视频索引} 超出范围，总共只有 {len(all_video_records)} 个视频", ""
        selected = all_video_records[视频索引 - 1]

        # 处理自定义分隔符，如果为空则使用默认分隔符
        if 列分隔符 is None or 列分隔符 == "":
            列分隔符 = " | "
        
        # 处理特殊字符转义
        列分隔符 = 列分隔符.replace('\\n', '\n').replace('\\t', '\t')
        
        # 额外信息
        extracted_content = self._extract_single_record_content(selected, 提取列名, 列分隔符)

        # 5. 获取临时下载链接并下载
        file_token = selected['file_token']
        tmp_urls = self._get_tmp_download_urls(token, [file_token], table_id)
        data = None
        if file_token in tmp_urls:
            data = self._download_file_by_tmp_url(tmp_urls[file_token])
        if data is None:
            data = self._download_file_by_file_token(token, file_token)
        if data is None:
            return None, "错误：视频下载失败", extracted_content

        # 6. 保存到本地临时目录
        suggested_name = selected.get('name') or f"{file_token}.mp4"
        local_path = self._save_temp_video(data, suggested_name)

        # 7. 构造 VIDEO 对象
        video_obj = self._VideoFromPath(local_path)

        # 8. 组织状态信息（尽量提供可读信息）
        size_mb = len(data) / (1024 * 1024)
        status = f"成功获取第 {视频索引} 个视频，保存于: {local_path}（{size_mb:.2f} MB）"
        if not AV_AVAILABLE or torch is None or np is None:
            status += "；提示：未检测到 PyAV/Torch/NumPy，预览可能不可用"

        # 8. 加载使用说明图片
        usage_image = self._load_usage_image()
        
        return video_obj, status, extracted_content, usage_image


# 节点注册映射（由 __init__.py 汇总导出）
NODE_CLASS_MAPPINGS = {
    "FeishuFetchVideoNode": FeishuFetchVideoNode,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FeishuFetchVideoNode": "获取视频（飞书多维表格）",
}


